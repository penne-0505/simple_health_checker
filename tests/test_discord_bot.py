from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from simple_health_checker.config import AppConfig
from simple_health_checker.discord_ui.bot import HealthCheckerBot
from simple_health_checker.models import CheckResult, Monitor, MonitorState, MonitorStatus


class FakeResponse:
    def __init__(self) -> None:
        self._done = False
        self.deferred: list[dict[str, bool]] = []
        self.messages: list[dict] = []

    def is_done(self) -> bool:
        return self._done

    async def defer(self, *, ephemeral: bool = False, thinking: bool = False) -> None:
        self._done = True
        self.deferred.append({"ephemeral": ephemeral, "thinking": thinking})

    async def send_message(self, *, embed=None, ephemeral: bool = False, view=None) -> None:  # noqa: ANN001
        self._done = True
        self.messages.append({"embed": embed, "ephemeral": ephemeral, "view": view})


class FakeFollowup:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send(self, *, embed=None, ephemeral: bool = False, view=None) -> None:  # noqa: ANN001
        self.messages.append({"embed": embed, "ephemeral": ephemeral, "view": view})


class FakeInteraction:
    def __init__(self, user_id: int = 1234) -> None:
        self.user = SimpleNamespace(id=user_id)
        self.response = FakeResponse()
        self.followup = FakeFollowup()


class RepositoryStub:
    def __init__(self, *, monitors: dict[int, Monitor] | None = None, acl_admins: set[int] | None = None) -> None:
        self.monitors = monitors or {}
        self.acl_admins = acl_admins or set()
        self.set_enabled_calls: list[tuple[int, bool]] = []

    async def get_monitor(self, monitor_id: int) -> Monitor | None:
        return self.monitors.get(monitor_id)

    async def is_acl_admin(self, user_id: int) -> bool:
        return user_id in self.acl_admins

    async def set_monitor_enabled(self, monitor_id: int, enabled: bool) -> None:
        self.set_enabled_calls.append((monitor_id, enabled))


class MonitorServiceStub:
    def __init__(self) -> None:
        self.run_single_check_calls: list[int] = []
        self.summary_calls = 0

    async def run_single_check(self, monitor: Monitor) -> tuple[CheckResult, MonitorState]:
        self.run_single_check_calls.append(monitor.id or -1)
        return (
            CheckResult(
                monitor_id=monitor.id or -1,
                checked_at=monitor.created_at,
                success=True,
                status_code=200,
                latency_ms=15,
                error=None,
                detail="manual test",
            ),
            MonitorState(monitor_id=monitor.id or -1, current_status=MonitorStatus.UP),
        )

    async def send_summary_once(self) -> None:
        self.summary_calls += 1

    async def close(self) -> None:
        return


def _monitor(monitor_id: int = 1, name: str = "discord-bot-test") -> Monitor:
    return Monitor(
        id=monitor_id,
        name=name,
        url="https://example.com/health",
        method="GET",
        timeout_seconds=5,
        expected_status_codes=[200],
        interval_seconds=60,
        failure_threshold=2,
        recovery_threshold=2,
        notification_channel_id=100,
        alert_channel_id=None,
        mention_role_id=None,
        mention_user_id=None,
        enabled=True,
    )


def _config() -> AppConfig:
    return AppConfig(
        discord_token="token",
        sqlite_path=Path("/tmp/discord-bot-test.sqlite3"),
        poll_loop_seconds=1,
        max_parallel_checks=1,
        command_guild_id=None,
        summary_channel_id=None,
        summary_interval_seconds=60,
        request_user_agent="test-agent",
    )


def _get_monitor_command(bot: HealthCheckerBot, name: str):
    group = bot.tree.get_command("monitor")
    assert group is not None
    for command in group.commands:
        if command.name == name:
            return command
    raise AssertionError(f"command not found: {name}")


@pytest.mark.asyncio
async def test_monitor_check_defers_before_running_health_check() -> None:
    repo = RepositoryStub(monitors={1: _monitor(1)})
    service = MonitorServiceStub()
    bot = HealthCheckerBot(config=_config(), repository=repo, monitor_service=service)
    interaction = FakeInteraction()

    try:
        command = _get_monitor_command(bot, "check")
        await command.callback(interaction, monitor_id=1)

        assert interaction.response.deferred == [{"ephemeral": True, "thinking": True}]
        assert len(interaction.response.messages) == 0
        assert len(interaction.followup.messages) == 1
        assert service.run_single_check_calls == [1]
    finally:
        await bot.close()


@pytest.mark.asyncio
async def test_monitor_pause_returns_not_found_without_mutation() -> None:
    repo = RepositoryStub(monitors={}, acl_admins={1234})
    service = MonitorServiceStub()
    bot = HealthCheckerBot(config=_config(), repository=repo, monitor_service=service)
    interaction = FakeInteraction(user_id=1234)

    try:
        command = _get_monitor_command(bot, "pause")
        await command.callback(interaction, monitor_id=999)

        assert repo.set_enabled_calls == []
        assert len(interaction.response.messages) == 1
        assert interaction.response.messages[0]["embed"].title == "monitor 未検出"
    finally:
        await bot.close()
