"""Contracts for risk engine module."""

from dataclasses import dataclass, field

from ai_trading_automation.modules.signal_contract.models import SignalContract


@dataclass(slots=True)
class AccountRiskConfig:
    """Risk guard configuration for one risk calculation."""

    max_risk_per_trade_percent: float = 1.0
    max_daily_loss_percent: float = 3.0
    max_open_positions: int = 3


@dataclass(slots=True)
class RiskEngineRequest:
    """Input contract for risk plan calculation."""

    signal: SignalContract
    account_balance: float
    daily_realized_loss: float
    open_positions_count: int
    requested_risk_percent: float = 1.0
    config: AccountRiskConfig = field(default_factory=AccountRiskConfig)
