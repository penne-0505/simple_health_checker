from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from simple_health_checker.models import Monitor, MonitorStatus
from simple_health_checker.repository.sqlite import SQLiteMonitorRepository


def _monitor(name: str = "repo-test") -> Monitor:
    return Monitor(
        id=None,
        name=name,
        url="https://example.com/health",
        method="GET",
        timeout_seconds=5,
        expected_status_codes=[200],
        interval_seconds=60,
        failure_threshold=2,
        recovery_threshold=2,
        notification_channel_id=111,
        alert_channel_id=222,
        mention_role_id=None,
        mention_user_id=None,
        enabled=True,
    )


@pytest.mark.asyncio
async def test_repository_initializes_and_creates_default_state(tmp_path: Path) -> None:
    repo = SQLiteMonitorRepository(tmp_path / "repo.sqlite3")
    try:
        await repo.initialize()
        created = await repo.create_monitor(_monitor())
        assert created.id is not None

        state = await repo.get_state(created.id)
        assert state.current_status == MonitorStatus.UNKNOWN
        assert state.consecutive_failures == 0
        assert state.consecutive_successes == 0

        due = await repo.list_due_monitors()
        assert len(due) == 1
        assert due[0][0].id == created.id
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_acl_grant_list_revoke_flow(tmp_path: Path) -> None:
    repo = SQLiteMonitorRepository(tmp_path / "acl.sqlite3")
    try:
        await repo.initialize()

        await repo.grant_acl_admin(1001, 9001)
        await repo.grant_acl_admin(1002, 9001)

        admins = await repo.list_acl_admins()
        assert admins == [1001, 1002]
        assert await repo.count_acl_admins() == 2
        assert await repo.is_acl_admin(1001) is True

        removed = await repo.revoke_acl_admin(1002, 9001)
        assert removed is True
        assert await repo.count_acl_admins() == 1
        assert await repo.is_acl_admin(1002) is False
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_repository_close_and_reinitialize_keeps_operability(tmp_path: Path) -> None:
    repo = SQLiteMonitorRepository(tmp_path / "lifecycle.sqlite3")
    try:
        await repo.initialize()
        first = await repo.create_monitor(_monitor("lifecycle-1"))
        assert first.id is not None

        await repo.close()

        second = await repo.create_monitor(_monitor("lifecycle-2"))
        assert second.id is not None
        listed = await repo.list_monitors()
        assert {m.name for m in listed} == {"lifecycle-1", "lifecycle-2"}
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_repository_handles_concurrent_read_write(tmp_path: Path) -> None:
    repo = SQLiteMonitorRepository(tmp_path / "concurrent.sqlite3")
    try:
        await repo.initialize()
        await repo.create_monitor(_monitor("c-0"))

        async def writer(idx: int) -> None:
            await repo.create_monitor(_monitor(f"c-{idx}"))

        async def reader() -> list:
            return await repo.list_monitors_with_states()

        write_tasks = [writer(i) for i in range(1, 6)]
        read_tasks = [reader() for _ in range(5)]
        results = await asyncio.gather(*write_tasks, *read_tasks)
        monitor_pairs = await repo.list_monitors_with_states()
        assert len(monitor_pairs) == 6
        assert any(isinstance(item, list) for item in results)
    finally:
        await repo.close()
