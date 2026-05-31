"""Programmatic launcher for FastAPI server."""

from __future__ import annotations

import uvicorn

from src.config.logging_config import setup_logging
from src.config.settings import get_settings


def main() -> None:
    """Run FastAPI app with configured host and port."""

    settings = get_settings()
    setup_logging(settings)

    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
