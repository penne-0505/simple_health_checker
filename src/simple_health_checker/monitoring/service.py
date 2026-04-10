from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from simple_health_checker.models import CheckResult, EventLog, Monitor, MonitorState, MonitorStatus
from simple_health_checker.monitoring.http_checker import HTTPChecker
from simple_health_checker.notification.discord_notifier import DiscordNotifier
from simple_health_checker.repository.base import MonitorRepository

logger = logging.getLogger(__name__)


class MonitorService:
    def __init__(
        self,
        *,
        repository: MonitorRepository,
        checker: HTTPChecker,
        poll_loop_seconds: int,
        max_parallel_checks: int,
        notifier: DiscordNotifier | None = None,
        summary_channel_id: int | None = None,
        summary_interval_seconds: int = 3600,
    ):
        self._repository = repository
        self._checker = checker
        self._poll_loop_seconds = poll_loop_seconds
        self._semaphore = asyncio.Semaphore(max_parallel_checks)
        self._notifier = notifier
        self._summary_channel_id = summary_channel_id
        self._summary_interval_seconds = summary_interval_seconds
        self._stopping = asyncio.Event()
        self._worker_task: asyncio.Task | None = None
        self._summary_task: asyncio.Task | None = None
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        await self._checker.start()
        self._worker_task = asyncio.create_task(self._run_loop(), name="monitor-loop")
        self._summary_task = asyncio.create_task(self._run_summary_loop(), name="summary-loop")
        self._started = True

    def set_notifier(self, notifier: DiscordNotifier) -> None:
        self._notifier = notifier

    async def close(self) -> None:
        if not self._started:
            return
        self._stopping.set()
        if self._worker_task:
            self._worker_task.cancel()
            await asyncio.gather(self._worker_task, return_exceptions=True)
        if self._summary_task:
            self._summary_task.cancel()
            await asyncio.gather(self._summary_task, return_exceptions=True)
        await self._checker.close()
        self._started = False

    async def run_single_check(
        self,
        monitor: Monitor,
        state: MonitorState | None = None,
    ) -> tuple[CheckResult, MonitorState]:
        if monitor.id is None:
            raise ValueError("monitor id is required")
        state = state or await self._repository.get_state(monitor.id)
        result = await self._checker.check(monitor)
        next_state = self._apply_result(monitor, state, result)
        await self._repository.insert_check_result(result)
        try:
            await self._emit_state_change_events(monitor, state, next_state, result)
        except Exception:
            logger.exception("state change emission failed monitor_id=%s", monitor.id)
        await self._repository.upsert_state(next_state)
        return result, next_state

    async def _run_loop(self) -> None:
        while not self._stopping.is_set():
            try:
                due = await self._repository.list_due_monitors()
                tasks = [asyncio.create_task(self._safe_check(m, s)) for (m, s) in due]
                if tasks:
                    await asyncio.gather(*tasks)
            except Exception:
                logger.exception("monitor loop error")
            await asyncio.sleep(self._poll_loop_seconds)

    async def _safe_check(self, monitor: Monitor, state: MonitorState) -> None:
        async with self._semaphore:
            try:
                await self.run_single_check(monitor, state=state)
            except Exception:
                logger.exception("check failed monitor_id=%s name=%s", monitor.id, monitor.name)

    def _apply_result(self, monitor: Monitor, state: MonitorState, result: CheckResult) -> MonitorState:
        now = datetime.now(timezone.utc)
        next_state = MonitorState(
            monitor_id=state.monitor_id,
            current_status=state.current_status,
            consecutive_successes=state.consecutive_successes,
            consecutive_failures=state.consecutive_failures,
            last_notified_status=state.last_notified_status,
            last_check_at=result.checked_at,
            last_change_at=state.last_change_at,
            last_error=result.error,
            last_latency_ms=result.latency_ms,
        )

        if result.success:
            next_state.consecutive_successes += 1
            next_state.consecutive_failures = 0
            if next_state.current_status != MonitorStatus.UP and next_state.consecutive_successes >= monitor.recovery_threshold:
                next_state.current_status = MonitorStatus.UP
                next_state.last_change_at = now
        else:
            next_state.consecutive_failures += 1
            next_state.consecutive_successes = 0
            if next_state.current_status != MonitorStatus.DOWN and next_state.consecutive_failures >= monitor.failure_threshold:
                next_state.current_status = MonitorStatus.DOWN
                next_state.last_change_at = now
        return next_state

    async def _emit_state_change_events(
        self,
        monitor: Monitor,
        previous_state: MonitorState,
        current_state: MonitorState,
        result: CheckResult,
    ) -> None:
        if monitor.id is None:
            return

        if previous_state.current_status != current_state.current_status:
            event = EventLog(
                id=None,
                monitor_id=monitor.id,
                event_type="STATE_CHANGE",
                message=(
                    f"state changed {previous_state.current_status.value} -> {current_state.current_status.value}; "
                    f"success={result.success}, code={result.status_code}, error={result.error or '-'}"
                ),
                checked_at=result.checked_at,
                status_code=result.status_code,
                latency_ms=result.latency_ms,
                success=result.success,
            )
            await self._repository.insert_event_log(event)
            if self._notifier:
                await self._notifier.send_transition(
                    monitor=monitor,
                    previous=previous_state.current_status,
                    current=current_state.current_status,
                    state=current_state,
                )
            current_state.last_notified_status = current_state.current_status

    async def _run_summary_loop(self) -> None:
        if self._summary_channel_id is None or self._notifier is None:
            return
        while not self._stopping.is_set():
            try:
                await asyncio.sleep(self._summary_interval_seconds)
                await self.send_summary_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("summary loop error")

    async def send_summary_once(self) -> None:
        if self._summary_channel_id is None or self._notifier is None:
            return
        monitor_pairs = await self._repository.list_monitors_with_states()
        down_monitors: list[str] = []
        enabled_count = 0
        for monitor, state in monitor_pairs:
            if monitor.enabled:
                enabled_count += 1
            if monitor.enabled and state.current_status == MonitorStatus.DOWN:
                down_monitors.append(monitor.name)
        await self._notifier.send_summary(
            channel_id=self._summary_channel_id,
            total=len(monitor_pairs),
            enabled=enabled_count,
            down_monitors=down_monitors,
        )
