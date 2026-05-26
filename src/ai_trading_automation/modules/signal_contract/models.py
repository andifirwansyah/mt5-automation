"""Pydantic models for standardized signal contract."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SignalDirection(StrEnum):
    """Allowed signal directions."""

    BUY = "BUY"
    SELL = "SELL"
    WAIT = "WAIT"


class SignalContract(BaseModel):
    """Standardized signal contract consumed by downstream modules."""

    model_config = ConfigDict(str_strip_whitespace=True)

    signal_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    timeframe: str = Field(min_length=1)
    direction: SignalDirection
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    strategy_key: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1)
    created_at: datetime
    metadata: dict[str, str | float | int | bool | None] = Field(default_factory=dict)

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return str(value).upper()

    @field_validator("direction", mode="before")
    @classmethod
    def normalize_direction(cls, value: str | SignalDirection) -> SignalDirection:
        if isinstance(value, SignalDirection):
            return value
        normalized = str(value).upper()
        return SignalDirection(normalized)

    @model_validator(mode="after")
    def validate_price_fields_by_direction(self) -> "SignalContract":
        if self.direction in {SignalDirection.BUY, SignalDirection.SELL}:
            required_prices = {
                "entry_price": self.entry_price,
                "stop_loss": self.stop_loss,
                "take_profit": self.take_profit,
            }
            missing = [field for field, value in required_prices.items() if value is None]
            if missing:
                raise ValueError(
                    f"Missing required price fields for {self.direction}: {missing}"
                )

            if self.entry_price <= 0 or self.stop_loss <= 0 or self.take_profit <= 0:
                raise ValueError("entry_price, stop_loss, and take_profit must be positive.")

        return self
