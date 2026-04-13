from __future__ import annotations

import logging
from dataclasses import replace

import discord
from discord import app_commands

from simple_health_checker.config import AppConfig
from simple_health_checker.models import Monitor
from simple_health_checker.monitoring.service import MonitorService
from simple_health_checker.repository.base import MonitorRepository

logger = logging.getLogger(__name__)


def _parse_csv_ints(raw: str) -> list[int]:
    values: list[int] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        values.append(int(token))
    return values


def _monitor_to_text(monitor: Monitor) -> str:
    return (
        f"**{monitor.id} - {monitor.name}**\n"
        f"- url: `{monitor.url}`\n"
        f"- method: `{monitor.method}`\n"
        f"- timeout_seconds: `{monitor.timeout_seconds}`\n"
        f"- expected_status_codes: `{monitor.expected_status_codes}`\n"
        f"- interval_seconds: `{monitor.interval_seconds}`\n"
        f"- failure_threshold: `{monitor.failure_threshold}`\n"
        f"- recovery_threshold: `{monitor.recovery_threshold}`\n"
        f"- notification_channel_id: `{monitor.notification_channel_id}`\n"
        f"- alert_channel_id: `{monitor.alert_channel_id}`\n"
        f"- mention_role_id: `{monitor.mention_role_id}`\n"
        f"- mention_user_id: `{monitor.mention_user_id}`\n"
        f"- enabled: `{monitor.enabled}`"
    )


def _build_embed(*, title: str, description: str, success: bool = True) -> discord.Embed:
    color = discord.Color.green() if success else discord.Color.red()
    return discord.Embed(title=title, description=description, color=color)


async def _defer_response(interaction: discord.Interaction, *, ephemeral: bool = True) -> None:
    if interaction.response.is_done():
        return
    await interaction.response.defer(ephemeral=ephemeral, thinking=True)


async def _send_embed_response(
    interaction: discord.Interaction,
    *,
    title: str,
    description: str,
    success: bool = True,
    ephemeral: bool = True,
    view: discord.ui.View | None = None,
) -> None:
    embed = _build_embed(title=title, description=description, success=success)
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=ephemeral, view=view)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=ephemeral, view=view)


class MonitorFormModal(discord.ui.Modal):
    def __init__(self, title: str, initial: Monitor | None = None):
        super().__init__(title=title, timeout=300)
        initial = initial or Monitor(
            id=None,
            name="",
            url="https://example.com/health",
            method="GET",
            timeout_seconds=10,
            expected_status_codes=[200],
            interval_seconds=60,
            failure_threshold=3,
            recovery_threshold=2,
            notification_channel_id=0,
            alert_channel_id=None,
            mention_role_id=None,
            mention_user_id=None,
            enabled=True,
        )
        self.name_input = discord.ui.TextInput(label="name", default=initial.name, required=True, max_length=120)
        self.url_input = discord.ui.TextInput(label="url", default=initial.url, required=True, max_length=500)
        self.method_input = discord.ui.TextInput(label="method", default=initial.method, required=True, max_length=10)
        self.expected_input = discord.ui.TextInput(
            label="expected_status_codes (comma)", default=",".join(map(str, initial.expected_status_codes)), required=True
        )
        self.timing_input = discord.ui.TextInput(
            label="timeout,interval,failure,recovery",
            default=f"{initial.timeout_seconds},{initial.interval_seconds},{initial.failure_threshold},{initial.recovery_threshold}",
            required=True,
        )
        self.add_item(self.name_input)
        self.add_item(self.url_input)
        self.add_item(self.method_input)
        self.add_item(self.expected_input)
        self.add_item(self.timing_input)
        self.parsed_monitor: Monitor | None = None
        self.submit_interaction: discord.Interaction | None = None

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            timeout, interval, failure_th, recovery_th = [int(v.strip()) for v in self.timing_input.value.split(",")]
            expected_codes = _parse_csv_ints(self.expected_input.value)
            self.parsed_monitor = Monitor(
                id=None,
                name=self.name_input.value.strip(),
                url=self.url_input.value.strip(),
                method=self.method_input.value.strip().upper(),
                timeout_seconds=timeout,
                expected_status_codes=expected_codes,
                interval_seconds=interval,
                failure_threshold=failure_th,
                recovery_threshold=recovery_th,
                notification_channel_id=0,
                alert_channel_id=None,
                mention_role_id=None,
                mention_user_id=None,
                enabled=True,
            )
            self.submit_interaction = interaction
            await interaction.response.defer()
        except Exception as exc:
            await _send_embed_response(
                interaction,
                title="入力エラー",
                description=f"入力が不正です: `{exc}`",
                success=False,
            )


class MonitorSelect(discord.ui.Select):
    def __init__(self, monitors: list[Monitor], repository: MonitorRepository):
        self._repository = repository
        options = [discord.SelectOption(label=f"{m.id}: {m.name}", value=str(m.id)) for m in monitors[:25] if m.id is not None]
        super().__init__(placeholder="監視対象を選択", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        monitor_id = int(self.values[0])
        monitor = await self._repository.get_monitor(monitor_id)
        if not monitor:
            await _send_embed_response(interaction, title="monitor 未検出", description="monitor が見つかりません。", success=False)
            return
        await _send_embed_response(interaction, title="監視対象詳細", description=_monitor_to_text(monitor))


class MonitorSelectView(discord.ui.View):
    def __init__(self, monitors: list[Monitor], repository: MonitorRepository):
        super().__init__(timeout=180)
        self.add_item(MonitorSelect(monitors, repository))


class MonitorDetailView(discord.ui.View):
    def __init__(self, app: "HealthCheckerBot", monitor_id: int):
        super().__init__(timeout=300)
        self.app = app
        self.monitor_id = monitor_id

    async def _require_admin(self, interaction: discord.Interaction) -> bool:
        if await self.app.has_manage_permission(interaction):
            return True
        await _send_embed_response(interaction, title="権限エラー", description="この操作は管理者のみ実行できます。", success=False)
        return False

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.secondary)
    async def pause(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._require_admin(interaction):
            return
        monitor = await self.app.get_monitor_or_respond(interaction, self.monitor_id)
        if monitor is None:
            return
        await self.app.repository.set_monitor_enabled(self.monitor_id, False)
        await _send_embed_response(interaction, title="操作完了", description=f"監視を停止しました: `{monitor.id}` {monitor.name}")

    @discord.ui.button(label="Resume", style=discord.ButtonStyle.success)
    async def resume(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._require_admin(interaction):
            return
        monitor = await self.app.get_monitor_or_respond(interaction, self.monitor_id)
        if monitor is None:
            return
        await self.app.repository.set_monitor_enabled(self.monitor_id, True)
        await _send_embed_response(interaction, title="操作完了", description=f"監視を再開しました: `{monitor.id}` {monitor.name}")

    @discord.ui.button(label="Check Now", style=discord.ButtonStyle.primary)
    async def check_now(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        monitor = await self.app.get_monitor_or_respond(interaction, self.monitor_id)
        if monitor is None:
            return
        await _defer_response(interaction)
        result, state = await self.app.monitor_service.run_single_check(monitor)
        await _send_embed_response(
            interaction,
            title="手動チェック結果",
            description=f"check完了 success={result.success}, code={result.status_code}, status={state.current_status.value}",
        )

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if not await self._require_admin(interaction):
            return
        monitor = await self.app.get_monitor_or_respond(interaction, self.monitor_id)
        if monitor is None:
            return
        await self.app.repository.delete_monitor(self.monitor_id)
        self.stop()
        await _send_embed_response(interaction, title="操作完了", description=f"削除しました: `{monitor.id}` {monitor.name}")


class HealthCheckerBot(discord.Client):
    def __init__(self, *, config: AppConfig, repository: MonitorRepository, monitor_service: MonitorService):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.config = config
        self.repository = repository
        self.monitor_service = monitor_service
        self.tree = app_commands.CommandTree(self)
        self._register_commands()

    def is_server_admin(self, interaction: discord.Interaction) -> bool:
        if isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator:
            return True
        return False

    async def has_manage_permission(self, interaction: discord.Interaction) -> bool:
        if self.is_server_admin(interaction):
            return True
        return await self.repository.is_acl_admin(interaction.user.id)

    async def _require_manage_permission(self, interaction: discord.Interaction) -> bool:
        if await self.has_manage_permission(interaction):
            return True
        await _send_embed_response(interaction, title="権限エラー", description="この操作は管理権限ユーザーのみ実行できます。", success=False)
        return False

    async def _require_server_admin(self, interaction: discord.Interaction) -> bool:
        if self.is_server_admin(interaction):
            return True
        await _send_embed_response(interaction, title="権限エラー", description="この操作はサーバー管理者のみ実行できます。", success=False)
        return False

    async def get_monitor_or_respond(self, interaction: discord.Interaction, monitor_id: int) -> Monitor | None:
        monitor = await self.repository.get_monitor(monitor_id)
        if monitor is not None:
            return monitor
        await _send_embed_response(interaction, title="monitor 未検出", description="monitor が見つかりません。", success=False)
        return None

    async def setup_hook(self) -> None:
        if self.config.command_guild_id:
            guild = discord.Object(id=self.config.command_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info("commands synced to guild=%s", self.config.command_guild_id)
        else:
            await self.tree.sync()
            logger.info("commands synced globally")

    async def on_ready(self) -> None:
        logger.info("logged in as %s", self.user)
        await self.monitor_service.start()

    async def close(self) -> None:
        await self.monitor_service.close()
        await super().close()

    def _register_commands(self) -> None:
        group = app_commands.Group(name="monitor", description="Health monitor management")
        auth_group = app_commands.Group(name="auth", description="Admin ACL management")

        @group.command(name="list", description="監視対象一覧を表示")
        async def list_monitors(interaction: discord.Interaction) -> None:
            monitors = await self.repository.list_monitors()
            if not monitors:
                await _send_embed_response(interaction, title="監視対象一覧", description="監視対象はまだありません。")
                return
            lines = [f"- `{m.id}` {m.name} ({'enabled' if m.enabled else 'disabled'})" for m in monitors]
            view = MonitorSelectView(monitors, self.repository)
            await _send_embed_response(interaction, title="監視対象一覧", description="\n".join(lines), view=view)

        @group.command(name="detail", description="監視対象の詳細表示")
        @app_commands.describe(monitor_id="monitor id")
        async def detail(interaction: discord.Interaction, monitor_id: int) -> None:
            monitor = await self.get_monitor_or_respond(interaction, monitor_id)
            if monitor is None:
                return
            view = MonitorDetailView(self, monitor_id)
            await _send_embed_response(interaction, title="監視対象詳細", description=_monitor_to_text(monitor), view=view)

        @group.command(name="add", description="監視対象を追加")
        @app_commands.describe(
            notification_channel="通知先チャンネル",
            alert_channel="アラートチャンネル",
            mention_role="DOWN時にメンションするロール",
            mention_user="DOWN時にメンションするユーザー",
            enabled="有効/無効",
        )
        async def add(
            interaction: discord.Interaction,
            notification_channel: discord.TextChannel,
            alert_channel: discord.TextChannel | None = None,
            mention_role: discord.Role | None = None,
            mention_user: discord.Member | None = None,
            enabled: bool = True,
        ) -> None:
            if not await self._require_manage_permission(interaction):
                return
            modal = MonitorFormModal("Add monitor")
            await interaction.response.send_modal(modal)
            await modal.wait()
            if modal.parsed_monitor is None:
                return
            monitor = replace(
                modal.parsed_monitor,
                notification_channel_id=notification_channel.id,
                alert_channel_id=alert_channel.id if alert_channel else None,
                mention_role_id=mention_role.id if mention_role else None,
                mention_user_id=mention_user.id if mention_user else None,
                enabled=enabled,
            )
            created = await self.repository.create_monitor(monitor)
            target = modal.submit_interaction or interaction
            await _send_embed_response(target, title="追加完了", description=f"追加しました: `{created.id}` {created.name}")

        @group.command(name="edit", description="監視対象を編集")
        @app_commands.describe(
            monitor_id="monitor id",
            notification_channel="通知先チャンネル",
            alert_channel="アラートチャンネル",
            mention_role="DOWN時にメンションするロール",
            mention_user="DOWN時にメンションするユーザー",
            enabled="有効/無効",
        )
        async def edit(
            interaction: discord.Interaction,
            monitor_id: int,
            notification_channel: discord.TextChannel | None = None,
            alert_channel: discord.TextChannel | None = None,
            mention_role: discord.Role | None = None,
            mention_user: discord.Member | None = None,
            enabled: bool | None = None,
        ) -> None:
            if not await self._require_manage_permission(interaction):
                return
            existing = await self.repository.get_monitor(monitor_id)
            if not existing:
                await _send_embed_response(interaction, title="monitor 未検出", description="monitor が見つかりません。", success=False)
                return
            modal = MonitorFormModal("Edit monitor", initial=existing)
            await interaction.response.send_modal(modal)
            await modal.wait()
            if modal.parsed_monitor is None:
                return
            monitor = replace(
                modal.parsed_monitor,
                id=monitor_id,
                notification_channel_id=notification_channel.id if notification_channel else existing.notification_channel_id,
                alert_channel_id=alert_channel.id if alert_channel else existing.alert_channel_id,
                mention_role_id=mention_role.id if mention_role else existing.mention_role_id,
                mention_user_id=mention_user.id if mention_user else existing.mention_user_id,
                enabled=enabled if enabled is not None else existing.enabled,
            )
            updated = await self.repository.update_monitor(monitor)
            target = modal.submit_interaction or interaction
            await _send_embed_response(target, title="更新完了", description=f"更新しました: `{updated.id}` {updated.name}")

        @group.command(name="pause", description="一時停止")
        async def pause(interaction: discord.Interaction, monitor_id: int) -> None:
            if not await self._require_manage_permission(interaction):
                return
            monitor = await self.get_monitor_or_respond(interaction, monitor_id)
            if monitor is None:
                return
            await self.repository.set_monitor_enabled(monitor_id, False)
            await _send_embed_response(interaction, title="操作完了", description=f"停止しました: `{monitor.id}` {monitor.name}")

        @group.command(name="resume", description="再開")
        async def resume(interaction: discord.Interaction, monitor_id: int) -> None:
            if not await self._require_manage_permission(interaction):
                return
            monitor = await self.get_monitor_or_respond(interaction, monitor_id)
            if monitor is None:
                return
            await self.repository.set_monitor_enabled(monitor_id, True)
            await _send_embed_response(interaction, title="操作完了", description=f"再開しました: `{monitor.id}` {monitor.name}")

        @group.command(name="delete", description="削除")
        async def delete(interaction: discord.Interaction, monitor_id: int) -> None:
            if not await self._require_manage_permission(interaction):
                return
            monitor = await self.get_monitor_or_respond(interaction, monitor_id)
            if monitor is None:
                return
            await self.repository.delete_monitor(monitor_id)
            await _send_embed_response(interaction, title="操作完了", description=f"削除しました: `{monitor.id}` {monitor.name}")

        @group.command(name="check", description="手動チェック")
        async def check(interaction: discord.Interaction, monitor_id: int) -> None:
            monitor = await self.get_monitor_or_respond(interaction, monitor_id)
            if monitor is None:
                return
            await _defer_response(interaction)
            result, state = await self.monitor_service.run_single_check(monitor)
            await _send_embed_response(
                interaction,
                title="手動チェック結果",
                description=(
                    f"manual check: success=`{result.success}` status_code=`{result.status_code}` "
                    f"current_state=`{state.current_status.value}`"
                ),
            )

        @group.command(name="history", description="直近履歴")
        async def history(interaction: discord.Interaction, monitor_id: int, limit: app_commands.Range[int, 1, 30] = 10) -> None:
            monitor = await self.get_monitor_or_respond(interaction, monitor_id)
            if monitor is None:
                return
            logs = await self.repository.list_recent_events(monitor_id, limit=limit)
            if not logs:
                await _send_embed_response(interaction, title="履歴", description=f"`{monitor.id}` {monitor.name} の履歴はありません。")
                return
            lines = [
                (
                    f"- `{log.checked_at.isoformat()}` [{log.event_type}] success={log.success} "
                    f"code={log.status_code} msg={log.message}"
                )
                for log in logs
            ]
            await _send_embed_response(interaction, title="直近履歴", description="\n".join(lines))

        @group.command(name="summary_now", description="定時サマリーを即時送信")
        async def summary_now(interaction: discord.Interaction) -> None:
            if not await self._require_manage_permission(interaction):
                return
            await _defer_response(interaction)
            await self.monitor_service.send_summary_once()
            await _send_embed_response(interaction, title="操作完了", description="サマリー送信を実行しました。")

        @auth_group.command(name="grant", description="管理操作権限を付与")
        @app_commands.describe(user="権限を付与するユーザー")
        async def auth_grant(interaction: discord.Interaction, user: discord.Member) -> None:
            if not await self._require_server_admin(interaction):
                return
            if user.bot:
                await _send_embed_response(interaction, title="入力エラー", description="bot アカウントには付与できません。", success=False)
                return
            await self.repository.grant_acl_admin(user.id, interaction.user.id)
            await _send_embed_response(interaction, title="権限付与", description=f"管理操作権限を付与しました: <@{user.id}>")

        @auth_group.command(name="revoke", description="管理操作権限を削除")
        @app_commands.describe(user="権限を削除するユーザー")
        async def auth_revoke(interaction: discord.Interaction, user: discord.Member) -> None:
            if not await self._require_server_admin(interaction):
                return
            if not await self.repository.is_acl_admin(user.id):
                await _send_embed_response(interaction, title="対象外", description="対象ユーザーは ACL 管理者ではありません。", success=False)
                return
            count = await self.repository.count_acl_admins()
            if count <= 1:
                await _send_embed_response(
                    interaction,
                    title="操作不可",
                    description="最後の ACL 管理者は削除できません。先に別ユーザーへ付与してください。",
                    success=False,
                )
                return
            deleted = await self.repository.revoke_acl_admin(user.id, interaction.user.id)
            if not deleted:
                await _send_embed_response(interaction, title="未検出", description="削除対象が見つかりませんでした。", success=False)
                return
            await _send_embed_response(interaction, title="権限削除", description=f"管理操作権限を削除しました: <@{user.id}>")

        @auth_group.command(name="list", description="管理操作権限ユーザー一覧")
        async def auth_list(interaction: discord.Interaction) -> None:
            if not await self._require_manage_permission(interaction):
                return
            user_ids = await self.repository.list_acl_admins()
            acl_lines = [f"- <@{user_id}> (`{user_id}`)" for user_id in user_ids] if user_ids else ["- (none)"]
            text = "## 管理操作権限一覧 (ACL)\n" + "\n".join(acl_lines)
            await _send_embed_response(interaction, title="管理操作権限一覧 (ACL)", description=text)

        self.tree.add_command(group)
        self.tree.add_command(auth_group)
