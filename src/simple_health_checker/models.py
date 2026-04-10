from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MonitorStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    UP = "UP"
    DOWN = "DOWN"


@dataclass(slots=True)
class Monitor:
    id: int | None
    name: str
    url: str
    method: str
    timeout_seconds: int
    expected_status_codes: list[int]
    interval_seconds: int
    failure_threshold: int
    recovery_threshold: int
    notification_channel_id: int
    alert_channel_id: int | None
    mention_role_id: int | None
    mention_user_id: int | None
    enabled: bool = True
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class MonitorState:
    monitor_id: int
    current_status: MonitorStatus = MonitorStatus.UNKNOWN
    consecutive_successes: int = 0
    consecutive_failures: int = 0
    last_notified_status: MonitorStatus | None = None
    last_check_at: datetime | None = None
    last_change_at: datetime | None = None
    last_error: str | None = None
    last_latency_ms: int | None = None


@dataclass(slots=True)
class CheckResult:
    monitor_id: int
    checked_at: datetime
    success: bool
    status_code: int | None
    latency_ms: int | None
    error: str | None
    detail: str


@dataclass(slots=True)
class EventLog:
    id: int | None
    monitor_id: int
    event_type: str
    message: str
    checked_at: datetime
    status_code: int | None = None
    latency_ms: int | None = None
    success: bool | None = None
