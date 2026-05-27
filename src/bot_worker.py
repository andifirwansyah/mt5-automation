"""Bootstrap entrypoint for trading bot worker."""

from __future__ import annotations

from loguru import logger

from src.config.logging_config import setup_logging
from src.config.settings import get_settings


def main() -> None:
    """Load settings and start bot worker bootstrap."""

    settings = get_settings()
    setup_logging(settings)

    logger.info("Bot worker started")
    logger.info(
        "Runtime flags: dry_run={dry_run}, auto_trade={auto_trade}, approval_required={approval_required}",
        dry_run=settings.dry_run,
        auto_trade=settings.auto_trade,
        approval_required=settings.approval_required,
    )


if __name__ == "__main__":
    main()
