from __future__ import annotations

import logging
import sys

from simple_health_checker.config import AppConfig
from simple_health_checker.discord_ui.bot import HealthCheckerBot
from simple_health_checker.monitoring.http_checker import HTTPChecker
from simple_health_checker.monitoring.service import MonitorService
from simple_health_checker.notification.discord_notifier import DiscordNotifier
from simple_health_checker.repository.sqlite import SQLiteMonitorRepository


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        stream=sys.stdout,
    )


def main() -> None:
    setup_logging()
    config = AppConfig.from_env()

    repository = SQLiteMonitorRepository(config.sqlite_path)
    checker = HTTPChecker(config.request_user_agent)

    async def _run() -> None:
        await repository.initialize()
        monitor_service = MonitorService(
            repository=repository,
            checker=checker,
            poll_loop_seconds=config.poll_loop_seconds,
            max_parallel_checks=config.max_parallel_checks,
            summary_channel_id=config.summary_channel_id,
            summary_interval_seconds=config.summary_interval_seconds,
        )
        bot = HealthCheckerBot(
            config=config,
            repository=repository,
            monitor_service=monitor_service,
        )
        notifier = DiscordNotifier(bot)
        monitor_service.set_notifier(notifier)
        try:
            await bot.start(config.discord_token)
        finally:
            await repository.close()

    import asyncio

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("shutdown requested by keyboard interrupt")


if __name__ == "__main__":
    main()
