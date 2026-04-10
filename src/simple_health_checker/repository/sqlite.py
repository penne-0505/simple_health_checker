from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from simple_health_checker.models import CheckResult, EventLog, Monitor, MonitorState, MonitorStatus
from simple_health_checker.repository.base import MonitorRepository


def _to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).isoformat()


def _from_iso(raw: str | None) -> datetime | None:
    if raw is None:
        return None
    return datetime.fromisoformat(raw)


class SQLiteMonitorRepository(MonitorRepository):
    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None
        self._write_lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self._write_lock:
            db = await self._get_db()
            await self._apply_pragmas(db)
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS monitors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    url TEXT NOT NULL,
                    method TEXT NOT NULL,
                    timeout_seconds INTEGER NOT NULL,
                    expected_status_codes TEXT NOT NULL,
                    interval_seconds INTEGER NOT NULL,
                    failure_threshold INTEGER NOT NULL,
                    recovery_threshold INTEGER NOT NULL,
                    notification_channel_id INTEGER NOT NULL,
                    alert_channel_id INTEGER,
                    mention_role_id INTEGER,
                    mention_user_id INTEGER,
                    enabled INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS monitor_state (
                    monitor_id INTEGER PRIMARY KEY,
                    current_status TEXT NOT NULL,
                    consecutive_successes INTEGER NOT NULL,
                    consecutive_failures INTEGER NOT NULL,
                    last_notified_status TEXT,
                    last_check_at TEXT,
                    last_change_at TEXT,
                    last_error TEXT,
                    last_latency_ms INTEGER,
                    FOREIGN KEY(monitor_id) REFERENCES monitors(id) ON DELETE CASCADE
                );
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS event_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    monitor_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    status_code INTEGER,
                    latency_ms INTEGER,
                    success INTEGER,
                    FOREIGN KEY(monitor_id) REFERENCES monitors(id) ON DELETE CASCADE
                );
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_acl (
                    user_id INTEGER PRIMARY KEY,
                    granted_by INTEGER NOT NULL,
                    granted_at TEXT NOT NULL
                );
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_acl_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    acted_by INTEGER NOT NULL,
                    acted_at TEXT NOT NULL
                );
                """
            )
            await db.execute("CREATE INDEX IF NOT EXISTS idx_event_logs_monitor_id ON event_logs(monitor_id);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_event_logs_checked_at ON event_logs(checked_at);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_admin_acl_audit_user_id ON admin_acl_audit(user_id);")
            await db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    async def _get_db(self) -> aiosqlite.Connection:
        if self._db is None:
            self._db = await aiosqlite.connect(self._db_path)
            await self._apply_pragmas(self._db)
            return self._db
        try:
            await self._db.execute("SELECT 1;")
        except (aiosqlite.OperationalError, aiosqlite.ProgrammingError, ValueError):
            await self._reconnect()
        return self._db

    async def _reconnect(self) -> None:
        if self._db is not None:
            try:
                await self._db.close()
            except Exception:
                pass
        self._db = await aiosqlite.connect(self._db_path)
        await self._apply_pragmas(self._db)

    async def _apply_pragmas(self, db: aiosqlite.Connection) -> None:
        await db.execute("PRAGMA journal_mode=WAL;")

    async def list_monitors(self) -> list[Monitor]:
        db = await self._get_db()
        cursor = await db.execute("SELECT * FROM monitors ORDER BY id ASC;")
        rows = await cursor.fetchall()
        return [self._to_monitor(row) for row in rows]

    async def list_monitors_with_states(self) -> list[tuple[Monitor, MonitorState]]:
        db = await self._get_db()
        cursor = await db.execute(
                """
                SELECT
                    m.id, m.name, m.url, m.method, m.timeout_seconds, m.expected_status_codes,
                    m.interval_seconds, m.failure_threshold, m.recovery_threshold,
                    m.notification_channel_id, m.alert_channel_id, m.mention_role_id, m.mention_user_id,
                    m.enabled, m.created_at, m.updated_at,
                    s.monitor_id, s.current_status, s.consecutive_successes, s.consecutive_failures,
                    s.last_notified_status, s.last_check_at, s.last_change_at, s.last_error, s.last_latency_ms
                FROM monitors m
                LEFT JOIN monitor_state s ON s.monitor_id = m.id
                ORDER BY m.id ASC;
                """
        )
        rows = await cursor.fetchall()
        pairs: list[tuple[Monitor, MonitorState]] = []
        for row in rows:
            monitor = self._to_monitor(row[:16])
            state = self._to_state(row[16:]) if row[16] is not None else MonitorState(monitor_id=monitor.id or -1)
            pairs.append((monitor, state))
        return pairs

    async def get_monitor(self, monitor_id: int) -> Monitor | None:
        db = await self._get_db()
        cursor = await db.execute("SELECT * FROM monitors WHERE id = ?;", (monitor_id,))
        row = await cursor.fetchone()
        return self._to_monitor(row) if row else None

    async def create_monitor(self, monitor: Monitor) -> Monitor:
        now = datetime.now(timezone.utc)
        async with self._write_lock:
            db = await self._get_db()
            cursor = await db.execute(
                """
                INSERT INTO monitors (
                    name, url, method, timeout_seconds, expected_status_codes,
                    interval_seconds, failure_threshold, recovery_threshold,
                    notification_channel_id, alert_channel_id, mention_role_id, mention_user_id,
                    enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    monitor.name,
                    monitor.url,
                    monitor.method.upper(),
                    monitor.timeout_seconds,
                    json.dumps(monitor.expected_status_codes),
                    monitor.interval_seconds,
                    monitor.failure_threshold,
                    monitor.recovery_threshold,
                    monitor.notification_channel_id,
                    monitor.alert_channel_id,
                    monitor.mention_role_id,
                    monitor.mention_user_id,
                    int(monitor.enabled),
                    _to_iso(now),
                    _to_iso(now),
                ),
            )
            monitor_id = cursor.lastrowid
            await db.execute(
                """
                INSERT INTO monitor_state (
                    monitor_id, current_status, consecutive_successes, consecutive_failures,
                    last_notified_status, last_check_at, last_change_at, last_error, last_latency_ms
                ) VALUES (?, ?, 0, 0, NULL, NULL, NULL, NULL, NULL);
                """,
                (monitor_id, MonitorStatus.UNKNOWN.value),
            )
            await db.commit()
        created = await self.get_monitor(monitor_id)
        if created is None:
            raise RuntimeError("failed to create monitor")
        return created

    async def update_monitor(self, monitor: Monitor) -> Monitor:
        if monitor.id is None:
            raise ValueError("monitor.id is required for update")
        now = datetime.now(timezone.utc)
        async with self._write_lock:
            db = await self._get_db()
            await db.execute(
                """
                UPDATE monitors
                SET name = ?, url = ?, method = ?, timeout_seconds = ?, expected_status_codes = ?,
                    interval_seconds = ?, failure_threshold = ?, recovery_threshold = ?,
                    notification_channel_id = ?, alert_channel_id = ?, mention_role_id = ?, mention_user_id = ?,
                    enabled = ?, updated_at = ?
                WHERE id = ?;
                """,
                (
                    monitor.name,
                    monitor.url,
                    monitor.method.upper(),
                    monitor.timeout_seconds,
                    json.dumps(monitor.expected_status_codes),
                    monitor.interval_seconds,
                    monitor.failure_threshold,
                    monitor.recovery_threshold,
                    monitor.notification_channel_id,
                    monitor.alert_channel_id,
                    monitor.mention_role_id,
                    monitor.mention_user_id,
                    int(monitor.enabled),
                    _to_iso(now),
                    monitor.id,
                ),
            )
            await db.commit()
        updated = await self.get_monitor(monitor.id)
        if updated is None:
            raise RuntimeError("failed to update monitor")
        return updated

    async def set_monitor_enabled(self, monitor_id: int, enabled: bool) -> None:
        async with self._write_lock:
            db = await self._get_db()
            await db.execute(
                "UPDATE monitors SET enabled = ?, updated_at = ? WHERE id = ?;",
                (int(enabled), _to_iso(datetime.now(timezone.utc)), monitor_id),
            )
            await db.commit()

    async def delete_monitor(self, monitor_id: int) -> None:
        async with self._write_lock:
            db = await self._get_db()
            await db.execute("DELETE FROM event_logs WHERE monitor_id = ?;", (monitor_id,))
            await db.execute("DELETE FROM monitor_state WHERE monitor_id = ?;", (monitor_id,))
            await db.execute("DELETE FROM monitors WHERE id = ?;", (monitor_id,))
            await db.commit()

    async def get_state(self, monitor_id: int) -> MonitorState:
        db = await self._get_db()
        cursor = await db.execute(
            "SELECT * FROM monitor_state WHERE monitor_id = ?;",
            (monitor_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return MonitorState(monitor_id=monitor_id)
        return self._to_state(row)

    async def upsert_state(self, state: MonitorState) -> None:
        async with self._write_lock:
            db = await self._get_db()
            await db.execute(
                """
                INSERT INTO monitor_state (
                    monitor_id, current_status, consecutive_successes, consecutive_failures,
                    last_notified_status, last_check_at, last_change_at, last_error, last_latency_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(monitor_id) DO UPDATE SET
                    current_status = excluded.current_status,
                    consecutive_successes = excluded.consecutive_successes,
                    consecutive_failures = excluded.consecutive_failures,
                    last_notified_status = excluded.last_notified_status,
                    last_check_at = excluded.last_check_at,
                    last_change_at = excluded.last_change_at,
                    last_error = excluded.last_error,
                    last_latency_ms = excluded.last_latency_ms;
                """,
                (
                    state.monitor_id,
                    state.current_status.value,
                    state.consecutive_successes,
                    state.consecutive_failures,
                    state.last_notified_status.value if state.last_notified_status else None,
                    _to_iso(state.last_check_at),
                    _to_iso(state.last_change_at),
                    state.last_error,
                    state.last_latency_ms,
                ),
            )
            await db.commit()

    async def list_due_monitors(self) -> list[tuple[Monitor, MonitorState]]:
        monitor_pairs = await self.list_monitors_with_states()
        now = datetime.now(timezone.utc)
        due: list[tuple[Monitor, MonitorState]] = []
        for monitor, state in monitor_pairs:
            if not monitor.enabled:
                continue
            if state.last_check_at is None:
                due.append((monitor, state))
                continue
            elapsed = (now - state.last_check_at).total_seconds()
            if elapsed >= monitor.interval_seconds:
                due.append((monitor, state))
        return due

    async def insert_check_result(self, result: CheckResult) -> None:
        event = EventLog(
            id=None,
            monitor_id=result.monitor_id,
            event_type="CHECK",
            message=result.detail,
            checked_at=result.checked_at,
            status_code=result.status_code,
            latency_ms=result.latency_ms,
            success=result.success,
        )
        await self.insert_event_log(event)

    async def insert_event_log(self, event_log: EventLog) -> None:
        async with self._write_lock:
            db = await self._get_db()
            await db.execute(
                """
                INSERT INTO event_logs (
                    monitor_id, event_type, message, checked_at, status_code, latency_ms, success
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    event_log.monitor_id,
                    event_log.event_type,
                    event_log.message,
                    _to_iso(event_log.checked_at),
                    event_log.status_code,
                    event_log.latency_ms,
                    None if event_log.success is None else int(event_log.success),
                ),
            )
            await db.commit()

    async def list_recent_events(self, monitor_id: int, limit: int = 10) -> list[EventLog]:
        db = await self._get_db()
        cursor = await db.execute(
                """
                SELECT id, monitor_id, event_type, message, checked_at, status_code, latency_ms, success
                FROM event_logs
                WHERE monitor_id = ?
                ORDER BY id DESC
                LIMIT ?;
                """,
                (monitor_id, limit),
        )
        rows = await cursor.fetchall()
        return [
            EventLog(
                id=row[0],
                monitor_id=row[1],
                event_type=row[2],
                message=row[3],
                checked_at=_from_iso(row[4]) or datetime.now(timezone.utc),
                status_code=row[5],
                latency_ms=row[6],
                success=bool(row[7]) if row[7] is not None else None,
            )
            for row in rows
        ]

    async def is_acl_admin(self, user_id: int) -> bool:
        db = await self._get_db()
        cursor = await db.execute("SELECT 1 FROM admin_acl WHERE user_id = ?;", (user_id,))
        row = await cursor.fetchone()
        return row is not None

    async def list_acl_admins(self) -> list[int]:
        db = await self._get_db()
        cursor = await db.execute("SELECT user_id FROM admin_acl ORDER BY granted_at ASC;")
        rows = await cursor.fetchall()
        return [int(row[0]) for row in rows]

    async def count_acl_admins(self) -> int:
        db = await self._get_db()
        cursor = await db.execute("SELECT COUNT(*) FROM admin_acl;")
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def grant_acl_admin(self, user_id: int, granted_by: int) -> None:
        now = _to_iso(datetime.now(timezone.utc))
        async with self._write_lock:
            db = await self._get_db()
            await db.execute(
                """
                INSERT INTO admin_acl (user_id, granted_by, granted_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO NOTHING;
                """,
                (user_id, granted_by, now),
            )
            await db.execute(
                """
                INSERT INTO admin_acl_audit (user_id, action, acted_by, acted_at)
                VALUES (?, 'GRANT', ?, ?);
                """,
                (user_id, granted_by, now),
            )
            await db.commit()

    async def revoke_acl_admin(self, user_id: int, revoked_by: int) -> bool:
        now = _to_iso(datetime.now(timezone.utc))
        async with self._write_lock:
            db = await self._get_db()
            cursor = await db.execute("DELETE FROM admin_acl WHERE user_id = ?;", (user_id,))
            deleted = cursor.rowcount > 0
            if deleted:
                await db.execute(
                    """
                    INSERT INTO admin_acl_audit (user_id, action, acted_by, acted_at)
                    VALUES (?, 'REVOKE', ?, ?);
                    """,
                    (user_id, revoked_by, now),
                )
            await db.commit()
        return deleted

    def _to_monitor(self, row: aiosqlite.Row | tuple) -> Monitor:
        return Monitor(
            id=row[0],
            name=row[1],
            url=row[2],
            method=row[3],
            timeout_seconds=row[4],
            expected_status_codes=list(json.loads(row[5])),
            interval_seconds=row[6],
            failure_threshold=row[7],
            recovery_threshold=row[8],
            notification_channel_id=row[9],
            alert_channel_id=row[10],
            mention_role_id=row[11],
            mention_user_id=row[12],
            enabled=bool(row[13]),
            created_at=_from_iso(row[14]) or datetime.now(timezone.utc),
            updated_at=_from_iso(row[15]) or datetime.now(timezone.utc),
        )

    def _to_state(self, row: aiosqlite.Row | tuple) -> MonitorState:
        return MonitorState(
            monitor_id=row[0],
            current_status=MonitorStatus(row[1]),
            consecutive_successes=row[2],
            consecutive_failures=row[3],
            last_notified_status=MonitorStatus(row[4]) if row[4] else None,
            last_check_at=_from_iso(row[5]),
            last_change_at=_from_iso(row[6]),
            last_error=row[7],
            last_latency_ms=row[8],
        )
