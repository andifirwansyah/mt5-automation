"""Seed master data for symbol/timeframe/strategy baseline."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.infrastructure.database.models import Strategy, StrategyConfig
from src.infrastructure.database.session import SessionLocal
from src.repositories.market_repository import MarketRepository


TIMEFRAME_SEEDS: list[tuple[str, int, str]] = [
    ("M1", 1, "1 Minute"),
    ("M5", 5, "5 Minutes"),
    ("M15", 15, "15 Minutes"),
    ("M30", 30, "30 Minutes"),
    ("H1", 60, "1 Hour"),
    ("H4", 240, "4 Hours"),
    ("D1", 1440, "1 Day"),
]

STRATEGY_SEEDS: list[dict] = [
    {
        "code": "EMA_ATR_TREND",
        "name": "EMA ATR Trend Strategy",
        "description": "Trend following strategy using EMA structure and ATR SL/TP planning.",
        "config": {
            "lot_size": 0.01,
            "sl_atr_multiplier": 1.5,
            "tp_atr_multiplier": 2.5,
            "pullback_max_distance_atr": 1.6,
            "confirmation_min_body_atr": 0.04,
            "pullback_touch_required": False,
            "confirmation_bars": 1,
            "allow_high_volatility": True,
            "allow_momentum_continuation": True,
            "momentum_min_body_atr": 0.08
        },
    },
    {
        "code": "VOLATILITY_BREAKOUT",
        "name": "Volatility Breakout Strategy",
        "description": "Breakout strategy for high-volatility conditions.",
        "config": {
            "lot_size": 0.01,
            "breakout_buffer_atr": 0.08,
            "breakout_confirm_close": True,
            "breakout_min_body_atr": 0.15,
            "min_breakout_range_atr": 0.7,
            "sl_atr_multiplier": 1.2,
            "tp_atr_multiplier": 2.2,
            "allow_high_volatility": True,
        },
    },
    {
        "code": "RANGE_REVERSION",
        "name": "Range Reversion Strategy",
        "description": "Mean-reversion strategy for ranging market regime.",
        "config": {
            "lot_size": 0.01,
            "reversion_threshold_atr": 0.3,
            "boundary_tolerance_atr": 0.25,
            "min_range_width_atr": 1.0,
            "reversion_min_body_atr": 0.05,
            "sl_atr_multiplier": 1.2,
            "tp_atr_multiplier": 1.8,
            "allow_high_volatility": False,
        },
    },
    {
        "code": "LIQUIDITY_SWEEP_REVERSAL",
        "name": "Liquidity Sweep Reversal Strategy",
        "description": "Liquidity sweep reversal strategy for high-volatility reversal setups.",
        "config": {
            "lot_size": 0.01,
            "sweep_extension_atr": 0.3,
            "sweep_volume_multiplier": 1.3,
            "sweep_duration_bars": 3,
            "sweep_recovery_atr": 0.8,
            "min_touches_support": 2,
            "min_touches_resistance": 2,
            "level_tolerance_atr": 0.15,
            "level_lookback_periods": 20,
            "reversal_candle_body_atr": 0.3,
            "reversal_wick_ratio": 1.8,
            "reversal_min_bars": 2,
            "entry_price_mode": "aggressive",
            "stop_loss_atr_multiplier": 1.5,
            "take_profit_atr_multiplier": 2.5,
            "risk_reward_ratio_min": 1.5,
            "min_volatility_score": 0.5,
            "min_signal_confidence": 0.58,
            "allow_high_volatility": True,
        },
    },
]


def _seed_timeframes(market_repo: MarketRepository) -> dict[str, object]:
    rows: dict[str, object] = {}
    for code, minutes, description in TIMEFRAME_SEEDS:
        rows[code] = market_repo.get_or_create_timeframe(code=code, minutes=minutes, description=description)
    return rows


def _seed_symbol(market_repo: MarketRepository):
    return market_repo.get_or_create_symbol(
        name="XAUUSD",
        asset_class="METAL",
        digits=2,
        point=0.01,
        is_active=True,
        metadata={"seeded_by": "seed_master_data.py"},
    )


def _get_or_create_strategy(session, code: str, name: str, description: str) -> Strategy:
    strategy = session.execute(select(Strategy).where(Strategy.code == code)).scalar_one_or_none()
    if strategy is None:
        strategy = Strategy(
            code=code,
            name=name,
            description=description,
            is_active=True,
            metadata_json={"seeded_by": "seed_master_data.py"},
        )
        session.add(strategy)
        session.flush()
        return strategy

    strategy.name = name
    strategy.description = description
    strategy.is_active = True
    session.add(strategy)
    session.flush()
    return strategy


def _upsert_strategy_config(session, strategy_id, symbol_id, timeframe_id, config_payload: dict) -> StrategyConfig:
    row = session.execute(
        select(StrategyConfig).where(
            StrategyConfig.strategy_id == strategy_id,
            StrategyConfig.symbol_id == symbol_id,
            StrategyConfig.timeframe_id == timeframe_id,
        )
    ).scalar_one_or_none()

    if row is None:
        row = StrategyConfig(
            strategy_id=strategy_id,
            symbol_id=symbol_id,
            timeframe_id=timeframe_id,
            config=config_payload,
            is_active=True,
        )
        session.add(row)
        session.flush()
        return row

    row.config = config_payload
    row.is_active = True
    session.add(row)
    session.flush()
    return row


def main() -> None:
    session = SessionLocal()
    try:
        market_repo = MarketRepository(session)

        timeframe_rows = _seed_timeframes(market_repo)
        symbol = _seed_symbol(market_repo)

        seeded_strategies: list[str] = []
        seeded_configs = 0

        default_timeframe = timeframe_rows["M5"]
        for strategy_seed in STRATEGY_SEEDS:
            strategy = _get_or_create_strategy(
                session=session,
                code=strategy_seed["code"],
                name=strategy_seed["name"],
                description=strategy_seed["description"],
            )
            seeded_strategies.append(strategy.code)

            _upsert_strategy_config(
                session=session,
                strategy_id=strategy.id,
                symbol_id=symbol.id,
                timeframe_id=default_timeframe.id,
                config_payload=strategy_seed["config"],
            )
            seeded_configs += 1

        session.commit()

        print("[OK] Master data seeded")
        print(f"timeframes: {list(timeframe_rows.keys())}")
        print(f"symbol: {symbol.name}")
        print(f"strategies: {seeded_strategies}")
        print(f"strategy_configs: {seeded_configs}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
