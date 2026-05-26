"""Environment-backed application settings."""

from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass(slots=True)
class AppSettings:
    """Typed settings for runtime configuration."""

    app_env: str
    app_name: str
    db_connection: str
    database_url: str
    trade_journal_backend: str
    paper_execution_backend: str
    strict_db_runtime: bool

    @classmethod
    def from_env(cls) -> "AppSettings":
        """Load settings from environment variables and validate DB config."""
        load_dotenv(override=False)

        app_env = os.getenv("APP_ENV", "development")
        app_name = os.getenv("APP_NAME", "ai-trading-automation")
        db_connection = os.getenv("DB_CONNECTION", "mysql")
        database_url = os.getenv("DATABASE_URL", "").strip()
        trade_journal_backend = os.getenv("TRADE_JOURNAL_BACKEND", "file").strip().lower()
        paper_execution_backend = os.getenv("PAPER_EXECUTION_BACKEND", "memory").strip().lower()
        strict_db_runtime = os.getenv("STRICT_DB_RUNTIME", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        if not database_url:
            raise ValueError("DATABASE_URL is required.")

        if db_connection == "mysql" and not database_url.startswith("mysql+"):
            raise ValueError(
                "Invalid DATABASE_URL for MySQL. Expected prefix 'mysql+' (example: mysql+pymysql://...)."
            )

        if trade_journal_backend not in {"file", "db"}:
            raise ValueError("TRADE_JOURNAL_BACKEND must be one of: file, db.")

        if paper_execution_backend not in {"memory", "db"}:
            raise ValueError("PAPER_EXECUTION_BACKEND must be one of: memory, db.")

        return cls(
            app_env=app_env,
            app_name=app_name,
            db_connection=db_connection,
            database_url=database_url,
            trade_journal_backend=trade_journal_backend,
            paper_execution_backend=paper_execution_backend,
            strict_db_runtime=strict_db_runtime,
        )
