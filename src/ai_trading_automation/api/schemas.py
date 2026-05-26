"""HTTP schemas for API shell module."""

from datetime import datetime

from pydantic import BaseModel, Field


class PipelineRunRequestBody(BaseModel):
    dataset_path: str = Field(default="dataset")
    symbol: str = Field(default="XAUUSD")
    timeframe: str = Field(default="H1")
    account_balance: float = Field(default=10_000.0)
    requested_risk_percent: float = Field(default=0.5)
    daily_realized_loss: float = Field(default=0.0)
    open_positions_count: int = Field(default=0)
    persist_performance_report: bool = Field(default=False)


class HealthResponse(BaseModel):
    status: str
    service: str
    trading_mode: str
    live_trading_enabled: bool
    timestamp: datetime


class PipelineStatusResponse(BaseModel):
    pipeline_state: str
    message: str
    last_run_at: datetime | None
    last_decision: str | None = None


class PipelineRunResponse(BaseModel):
    accepted: bool
    message: str
    stage: str
    decision: str | None = None


class PipelineLastRunResponse(BaseModel):
    available: bool
    success: bool | None = None
    stage: str | None = None
    message: str | None = None
    decision: str | None = None
    run_at: datetime | None = None
    artifacts: dict | None = None
