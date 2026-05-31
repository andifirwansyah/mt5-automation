"""Project-wide constants."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
LOGS_DIR: Path = PROJECT_ROOT / "logs"

API_V1_PREFIX: str = "/api/v1"
