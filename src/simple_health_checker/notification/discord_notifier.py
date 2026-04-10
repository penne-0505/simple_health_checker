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
        embed = discord.Embed(
            title=f"{monitor.name} 状態変化",
            description=f"`{previous.value}` -> `{title}`",
            color=discord.Color.red() if current == MonitorStatus.DOWN else discord.Color.green(),
        )
        embed.add_field(name="last_error", value=f"`{state.last_error or '-'}`", inline=False)
        embed.add_field(name="latency_ms", value=f"`{state.last_latency_ms if state.last_latency_ms is not None else '-'}`", inline=True)
        embed.add_field(name="consecutive_failures", value=f"`{state.consecutive_failures}`", inline=True)
        embed.add_field(name="consecutive_successes", value=f"`{state.consecutive_successes}`", inline=True)
        await channel.send(content=mention_target.strip() or None, embed=embed)

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
        embed = discord.Embed(
            title="Health Check Summary",
            color=discord.Color.blue(),
        )
        embed.add_field(name="total monitors", value=f"`{total}`", inline=True)
        embed.add_field(name="enabled monitors", value=f"`{enabled}`", inline=True)
        embed.add_field(name="down monitors", value=down_text, inline=False)
        await channel.send(embed=embed)
