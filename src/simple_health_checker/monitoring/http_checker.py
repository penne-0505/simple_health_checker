from __future__ import annotations

import time
from datetime import timezone
from datetime import datetime

import aiohttp

from simple_health_checker.models import CheckResult, Monitor


class HTTPChecker:
    def __init__(self, user_agent: str):
        self._session: aiohttp.ClientSession | None = None
        self._user_agent = user_agent

    async def start(self) -> None:
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=None)
            self._session = aiohttp.ClientSession(timeout=timeout)

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def check(self, monitor: Monitor) -> CheckResult:
        if self._session is None:
            raise RuntimeError("HTTPChecker is not started")

        started = time.perf_counter()
        checked_at = datetime.now(timezone.utc)
        try:
            timeout = aiohttp.ClientTimeout(total=monitor.timeout_seconds)
            async with self._session.request(
                monitor.method.upper(),
                monitor.url,
                timeout=timeout,
                headers={"User-Agent": self._user_agent},
            ) as response:
                latency_ms = int((time.perf_counter() - started) * 1000)
                success = response.status in monitor.expected_status_codes
                detail = (
                    f"{monitor.method.upper()} {monitor.url} -> status={response.status}, "
                    f"expected={monitor.expected_status_codes}"
                )
                return CheckResult(
                    monitor_id=monitor.id or -1,
                    checked_at=checked_at,
                    success=success,
                    status_code=response.status,
                    latency_ms=latency_ms,
                    error=None if success else "unexpected status code",
                    detail=detail,
                )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            return CheckResult(
                monitor_id=monitor.id or -1,
                checked_at=checked_at,
                success=False,
                status_code=None,
                latency_ms=latency_ms,
                error=str(exc),
                detail=f"{monitor.method.upper()} {monitor.url} -> exception: {exc}",
            )
