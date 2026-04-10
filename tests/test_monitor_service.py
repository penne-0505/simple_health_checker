from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from simple_health_checker.models import CheckResult, Monitor, MonitorStatus
from simple_health_checker.monitoring.service import MonitorService
from simple_health_checker.repository.sqlite import SQLiteMonitorRepository


class SequenceChecker:
    def __init__(self, outcomes: list[tuple[bool, int | None, str | None]]):
        self._outcomes = outcomes

    async def start(self) -> None:
        return

    async def close(self) -> None:
        return

    async def check(self, monitor: Monitor) -> CheckResult:
        success, status_code, error = self._outcomes.pop(0)
        return CheckResult(
            monitor_id=monitor.id or -1,
            checked_at=datetime.now(timezone.utc),
            success=success,
            status_code=status_code,
            latency_ms=12,
            error=error,
            detail="test",
        )


class NotifierStub:
    def __init__(self) -> None:
        self.transitions: list[tuple[MonitorStatus, MonitorStatus]] = []

    async def send_transition(self, monitor, previous, current, state) -> None:  # noqa: ANN001
        del monitor, state
        self.transitions.append((previous, current))

    async def send_summary(self, **kwargs) -> None:  # noqa: ANN003
        del kwargs
        return


@pytest.mark.asyncio
async def test_state_transitions_and_notifications_follow_thresholds(tmp_path: Path) -> None:
    repo = SQLiteMonitorRepository(tmp_path / "service.sqlite3")
    try:
        await repo.initialize()

        monitor = await repo.create_monitor(
            Monitor(
                id=None,
                name="service-test",
                url="https://example.com/health",
                method="GET",
                timeout_seconds=5,
                expected_status_codes=[200],
                interval_seconds=60,
                failure_threshold=2,
                recovery_threshold=2,
                notification_channel_id=111,
                alert_channel_id=None,
                mention_role_id=None,
                mention_user_id=None,
                enabled=True,
            )
        )

        checker = SequenceChecker(
            [
                (False, 500, "fail-1"),
                (False, 500, "fail-2"),
                (False, 500, "fail-3"),
                (True, 200, None),
                (True, 200, None),
            ]
        )
        notifier = NotifierStub()
        service = MonitorService(
            repository=repo,
            checker=checker,
            poll_loop_seconds=10,
            max_parallel_checks=1,
            notifier=notifier,
            summary_channel_id=None,
        )

        await service.run_single_check(monitor)
        state = await repo.get_state(monitor.id or -1)
        assert state.current_status == MonitorStatus.UNKNOWN

        await service.run_single_check(monitor)
        state = await repo.get_state(monitor.id or -1)
        assert state.current_status == MonitorStatus.DOWN

        await service.run_single_check(monitor)
        state = await repo.get_state(monitor.id or -1)
        assert state.current_status == MonitorStatus.DOWN

        await service.run_single_check(monitor)
        state = await repo.get_state(monitor.id or -1)
        assert state.current_status == MonitorStatus.DOWN

        await service.run_single_check(monitor)
        state = await repo.get_state(monitor.id or -1)
        assert state.current_status == MonitorStatus.UP
        assert state.last_notified_status == MonitorStatus.UP

        assert notifier.transitions == [
            (MonitorStatus.UNKNOWN, MonitorStatus.DOWN),
            (MonitorStatus.DOWN, MonitorStatus.UP),
        ]
    finally:
        await repo.close()
