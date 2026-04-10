from __future__ import annotations

import logging

import discord

from simple_health_checker.models import Monitor, MonitorState, MonitorStatus

logger = logging.getLogger(__name__)


class DiscordNotifier:
    def __init__(self, bot: discord.Client):
        self._bot = bot

    async def send_transition(
        self,
        monitor: Monitor,
        previous: MonitorStatus,
        current: MonitorStatus,
        state: MonitorState,
    ) -> None:
        if current == previous:
            return
        target_channel_id = monitor.alert_channel_id if current == MonitorStatus.DOWN and monitor.alert_channel_id else monitor.notification_channel_id
        channel = self._bot.get_channel(target_channel_id)
        if not isinstance(channel, discord.abc.Messageable):
            logger.warning("notification channel not found for monitor=%s", monitor.name)
            return

        mention_target = ""
        if current == MonitorStatus.DOWN:
            if monitor.mention_role_id:
                mention_target = f"<@&{monitor.mention_role_id}> "
            elif monitor.mention_user_id:
                mention_target = f"<@{monitor.mention_user_id}> "

        title = "RECOVERED" if previous == MonitorStatus.DOWN and current == MonitorStatus.UP else current.value
        text = (
            f"{mention_target}**{monitor.name}** 状態変化: `{previous.value}` -> `{title}`\n"
            f"- last_error: `{state.last_error or '-'}`\n"
            f"- latency_ms: `{state.last_latency_ms if state.last_latency_ms is not None else '-'}`\n"
            f"- consecutive_failures: `{state.consecutive_failures}`\n"
            f"- consecutive_successes: `{state.consecutive_successes}`"
        )
        await channel.send(text)

    async def send_summary(
        self,
        *,
        channel_id: int,
        total: int,
        enabled: int,
        down_monitors: list[str],
    ) -> None:
        channel = self._bot.get_channel(channel_id)
        if not isinstance(channel, discord.abc.Messageable):
            logger.warning("summary channel not found: %s", channel_id)
            return
        down_text = ", ".join(down_monitors) if down_monitors else "なし"
        message = (
            "## Health Check Summary\n"
            f"- total monitors: `{total}`\n"
            f"- enabled monitors: `{enabled}`\n"
            f"- down monitors: {down_text}"
        )
        await channel.send(message)
