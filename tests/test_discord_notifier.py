from __future__ import annotations

import pytest

from simple_health_checker.models import Monitor, MonitorState, MonitorStatus
from simple_health_checker.notification import discord_notifier
from simple_health_checker.notification.discord_notifier import DiscordNotifier


class FakeChannel:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send(self, content=None, embed=None) -> None:  # noqa: ANN001
        self.messages.append({"content": content, "embed": embed})


class FakeBot:
    def __init__(self, channels: dict[int, FakeChannel], fetched_channels: dict[int, FakeChannel] | None = None) -> None:
        self._channels = channels
        self._fetched_channels = fetched_channels or {}
        self.fetch_calls: list[int] = []

    def get_channel(self, channel_id: int):
        return self._channels.get(channel_id)

    async def fetch_channel(self, channel_id: int):
        self.fetch_calls.append(channel_id)
        channel = self._fetched_channels.get(channel_id)
        if channel is None:
            raise discord_notifier.discord.NotFound(response=None, message="not found")  # type: ignore[arg-type]
        return channel


@pytest.mark.asyncio
async def test_down_uses_alert_channel_and_mentions_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discord_notifier.discord.abc, "Messageable", FakeChannel)
    notif_channel = FakeChannel()
    alert_channel = FakeChannel()
    bot = FakeBot({100: notif_channel, 200: alert_channel})
    notifier = DiscordNotifier(bot)  # type: ignore[arg-type]

    monitor = Monitor(
        id=1,
        name="notifier-test",
        url="https://example.com",
        method="GET",
        timeout_seconds=5,
        expected_status_codes=[200],
        interval_seconds=60,
        failure_threshold=2,
        recovery_threshold=2,
        notification_channel_id=100,
        alert_channel_id=200,
        mention_role_id=777,
        mention_user_id=None,
        enabled=True,
    )
    state = MonitorState(monitor_id=1, current_status=MonitorStatus.DOWN, consecutive_failures=2)
    await notifier.send_transition(monitor, MonitorStatus.UP, MonitorStatus.DOWN, state)

    assert len(alert_channel.messages) == 1
    assert "<@&777>" in (alert_channel.messages[0]["content"] or "")
    assert alert_channel.messages[0]["embed"] is not None
    assert len(notif_channel.messages) == 0


@pytest.mark.asyncio
async def test_recovered_uses_notification_channel_without_mention(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discord_notifier.discord.abc, "Messageable", FakeChannel)
    notif_channel = FakeChannel()
    alert_channel = FakeChannel()
    bot = FakeBot({100: notif_channel, 200: alert_channel})
    notifier = DiscordNotifier(bot)  # type: ignore[arg-type]

    monitor = Monitor(
        id=1,
        name="notifier-test",
        url="https://example.com",
        method="GET",
        timeout_seconds=5,
        expected_status_codes=[200],
        interval_seconds=60,
        failure_threshold=2,
        recovery_threshold=2,
        notification_channel_id=100,
        alert_channel_id=200,
        mention_role_id=777,
        mention_user_id=None,
        enabled=True,
    )
    state = MonitorState(monitor_id=1, current_status=MonitorStatus.UP, consecutive_successes=2)
    await notifier.send_transition(monitor, MonitorStatus.DOWN, MonitorStatus.UP, state)

    assert len(notif_channel.messages) == 1
    assert "<@&777>" not in (notif_channel.messages[0]["content"] or "")
    assert "RECOVERED" in notif_channel.messages[0]["embed"].description
    assert len(alert_channel.messages) == 0


@pytest.mark.asyncio
async def test_cache_miss_fetches_channel_before_sending(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discord_notifier.discord.abc, "Messageable", FakeChannel)
    notif_channel = FakeChannel()
    bot = FakeBot({}, fetched_channels={100: notif_channel})
    notifier = DiscordNotifier(bot)  # type: ignore[arg-type]

    monitor = Monitor(
        id=1,
        name="notifier-test",
        url="https://example.com",
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
    state = MonitorState(monitor_id=1, current_status=MonitorStatus.UP, consecutive_successes=2)
    await notifier.send_transition(monitor, MonitorStatus.DOWN, MonitorStatus.UP, state)

    assert bot.fetch_calls == [100]
    assert len(notif_channel.messages) == 1
