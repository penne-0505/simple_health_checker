from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(slots=True, frozen=True)
class AppConfig:
    discord_token: str
    sqlite_path: Path
    poll_loop_seconds: int
    max_parallel_checks: int
    command_guild_id: int | None
    summary_channel_id: int | None
    summary_interval_seconds: int
    request_user_agent: str

    @classmethod
    def from_env(cls) -> "AppConfig":
        load_dotenv()
        token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
        if not token:
            raise ValueError("DISCORD_BOT_TOKEN is required.")

        db_path = Path(os.getenv("SQLITE_PATH", "./data/health_checker.sqlite3")).resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)

        guild_id_raw = os.getenv("COMMAND_GUILD_ID", "").strip()
        summary_channel_raw = os.getenv("SUMMARY_CHANNEL_ID", "").strip()

        return cls(
            discord_token=token,
            sqlite_path=db_path,
            poll_loop_seconds=int(os.getenv("POLL_LOOP_SECONDS", "2")),
            max_parallel_checks=int(os.getenv("MAX_PARALLEL_CHECKS", "10")),
            command_guild_id=int(guild_id_raw) if guild_id_raw else None,
            summary_channel_id=int(summary_channel_raw) if summary_channel_raw else None,
            summary_interval_seconds=int(os.getenv("SUMMARY_INTERVAL_SECONDS", "3600")),
            request_user_agent=os.getenv("REQUEST_USER_AGENT", "simple-health-checker/0.1.0"),
        )
