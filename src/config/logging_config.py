"""Loguru configuration for bot and API runtime."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from src.config.constants import LOGS_DIR
from src.config.settings import AppSettings


def _ensure_logs_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def setup_logging(settings: AppSettings) -> None:
    """Configure application loggers and file sinks."""

    _ensure_logs_dir(LOGS_DIR)
    logger.remove()

    logger.add(
        sys.stdout,
        level=settings.log_level,
        enqueue=True,
        backtrace=True,
        diagnose=False,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name}:{function}:{line} | {message}",
    )

    logger.add(
        LOGS_DIR / "bot_worker.log",
        level=settings.log_level,
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        compression=settings.log_compression,
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )

    logger.add(
        LOGS_DIR / "api_server.log",
        level=settings.log_level,
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        compression=settings.log_compression,
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )

    logger.add(
        LOGS_DIR / "execution.log",
        level="INFO",
        filter=lambda record: record["extra"].get("channel") == "execution",
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        compression=settings.log_compression,
        enqueue=True,
    )

    logger.add(
        LOGS_DIR / "safety.log",
        level="INFO",
        filter=lambda record: record["extra"].get("channel") == "safety",
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        compression=settings.log_compression,
        enqueue=True,
    )

    logger.add(
        LOGS_DIR / "error.log",
        level="ERROR",
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        compression=settings.log_compression,
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )
