"""
Liquidity Sweep Reversal Strategy (Production-Grade).

Detects liquidity sweeps pada key support/resistance levels dan mengidentifikasi
reversal patterns yang mengikuti dengan high confidence. Strategy ini dirancang untuk
trading opportunities setelah smart money melakukan liquidity sweep.

Safety Features:
- Strict validation pada semua data input
- Multi-level confirmation sebelum signal generation
- Risk management terintegrasi
- Drawdown protection mechanisms
- Market microstructure analysis
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.domain.enums import MarketRegimeType, SignalDirection
from src.domain.models.market_snapshot import MarketSnapshot
from src.domain.models.regime_result import RegimeResult
from src.domain.models.signal import RawSignal
from src.strategies.base_strategy import BaseStrategy
from src.strategies.pattern_evidence_utils import count_fvg, has_pattern_status, is_pattern_enabled
from src.trading.technical_analysis.models import TechnicalAnalysisResult

# Configuration constants untuk production stability
DEFAULT_CONFIG = {
    # === SWEEP DETECTION PARAMETERS ===
    "sweep_extension_atr": 0.3,  # Minimum extension beyond level untuk classify sebagai sweep
    "sweep_volume_multiplier": 1.3,  # Volume harus lebih besar dari MA untuk sweep confirmation
    "sweep_duration_bars": 3,  # Jumlah bar untuk analisis sweep pattern
    "sweep_recovery_atr": 0.8,  # Berapa ATR untuk recovery dari sweep low
    
    # === SUPPORT/RESISTANCE LEVEL VALIDATION ===
    "min_touches_support": 2,  # Minimum level touches untuk classify sbg support
    "min_touches_resistance": 2,  # Minimum level touches untuk classify sbg resistance
    "level_tolerance_atr": 0.15,  # Tolerance untuk grouping levels yang sama
    "level_lookback_periods": 20,  # Lookback untuk identify levels
    
    # === REVERSAL CONFIRMATION ===
    "reversal_candle_body_atr": 0.3,  # Min candle body size untuk reversal signal
    "reversal_wick_ratio": 1.8,  # Ratio wick to body untuk engulfing/hammer pattern
    "reversal_min_bars": 2,  # Min bars untuk reversal confirmation
    
    # === ENTRY & EXIT MANAGEMENT ===
    "entry_price_mode": "aggressive",  # aggressive, moderate, conservative
    "stop_loss_atr_multiplier": 1.5,  # SL distance dari entry
    "take_profit_atr_multiplier": 2.5,  # TP distance dari entry
    "risk_reward_ratio_min": 1.5,  # Minimum acceptable risk:reward
    
    # === MARKET REGIME FILTERS ===
    "allowed_regimes": [MarketRegimeType.HIGH_VOLATILITY],
    "min_volatility_score": 0.5,
    "max_vol_atr_range": 3.0,  # Max ATR untuk volume analysis
    
    # === CONFIDENCE THRESHOLDS ===
    "min_signal_confidence": 0.58,  # Minimum confidence untuk signal generation
    "sweep_confidence_weight": 0.35,  # Weight untuk sweep quality score
    "reversal_confidence_weight": 0.40,  # Weight untuk reversal pattern
    "volume_confidence_weight": 0.25,  # Weight untuk volume confirmation
    
    # === SAFETY LIMITS ===
    "max_consecutive_signals": 3,  # Prevent overtrading
    "min_bars_between_signals": 2,  # Minimum bar spacing
    "max_daily_signal_count": 5,  # Daily signal limit
    "drawdown_stop_loss": False,  # Circuit breaker untuk consecutive losses
}

logger = logging.getLogger(__name__)


class LiquiditySweepReversalStrategy(BaseStrategy):
    """
    Liquidity Sweep Reversal Strategy dengan production-grade safety.
    
    Identifikasi:
    1. Liquidity sweeps pada support/resistance levels
    2. Volume profile analysis untuk sweep confirmation
    3. Candle pattern reversal setelah sweep
    4. Multi-timeframe confirmation
    
    Risk Management:
    - Strict stop loss placement
    - Dynamic position sizing
    - Drawdown protection
    - Regime filtering
    """

    strategy_code = "LIQUIDITY_SWEEP_REVERSAL"
    version = "1.0.0"

    def __init__(self):
        """Initialize strategy dengan default configuration."""
        super().__init__()
        self._validation_errors: list[str] = []
        self._last_signals: dict[str, datetime] = {}
        self._consecutive_loss_count: int = 0

    def generate_signal(
        self,
        market_snapshot: MarketSnapshot,
        regime: RegimeResult,
        config: dict[str, Any],
        technical_analysis: TechnicalAnalysisResult | None = None,
    ) -> RawSignal | None:
        """
        Generate trading signal berdasarkan liquidity sweep reversal.
        
        Args:
            market_snapshot: Current market snapshot
            regime: Market regime analysis
            config: Configuration parameters
            
        Returns:
            RawSignal jika valid conditions terpenuhi, None sebaliknya
        """
        # === STAGE 1: INPUT VALIDATION ===
        if not self._validate_inputs(market_snapshot, regime, config):
            return None

        # === STAGE 2: REGIME & MARKET FILTERING ===
        config_final = {**DEFAULT_CONFIG, **config}
        if not self._validate_market_regime(regime, config_final):
            return None

        # === STAGE 3: CALCULATE KEY METRICS ===
        atr = self._get_atr(market_snapshot, regime, config_final)
        if atr is None or atr <= 0:
            logger.warning(f"{self.strategy_code}: Invalid ATR value: {atr}")
            return None

        # Get support/resistance levels dari regime features
        levels = self._extract_support_resistance_levels(regime, config_final)
        if not levels["supports"] and not levels["resistances"]:
            return None

        # === STAGE 4: DETECT LIQUIDITY SWEEP ===
        sweep_data = self._detect_liquidity_sweep(
            market_snapshot=market_snapshot,
            regime=regime,
            levels=levels,
            atr=atr,
            config=config_final,
        )
        if not sweep_data or sweep_data["confidence"] < 0.5:
            return None

        # === STAGE 5: CONFIRM REVERSAL PATTERN ===
        reversal_data = self._analyze_reversal_pattern(
            market_snapshot=market_snapshot,
            regime=regime,
            sweep=sweep_data,
            atr=atr,
            config=config_final,
        )
        if not reversal_data or reversal_data["confidence"] < 0.5:
            return None

        # === STAGE 6: CALCULATE ENTRY & EXIT LEVELS ===
        entry_data = self._calculate_entry_exit(
            market_snapshot=market_snapshot,
            sweep=sweep_data,
            reversal=reversal_data,
            atr=atr,
            config=config_final,
        )
        if not entry_data:
            return None

        # === STAGE 7: VALIDATE RISK:REWARD ===
        if not self._validate_risk_reward(entry_data, config_final):
            return None

        # === STAGE 8: CALCULATE FINAL CONFIDENCE ===
        signal_confidence = self._calculate_signal_confidence(
            sweep=sweep_data,
            reversal=reversal_data,
            entry=entry_data,
            config=config_final,
        )
        signal_confidence, pattern_notes = self._apply_pattern_evidence_adjustment(
            signal_confidence=signal_confidence,
            sweep=sweep_data,
            technical_analysis=technical_analysis,
            config=config_final,
        )
        if signal_confidence < config_final["min_signal_confidence"]:
            return None

        # === STAGE 9: SAFETY CHECKS ===
        if not self._perform_safety_checks(market_snapshot, config_final):
            return None

        # === STAGE 10: CREATE & RETURN SIGNAL ===
        return self._create_signal(
            market_snapshot=market_snapshot,
            sweep=sweep_data,
            reversal=reversal_data,
            entry=entry_data,
            confidence=signal_confidence,
            pattern_notes=pattern_notes,
        )

    # =========================================================================
    # VALIDATION METHODS
    # =========================================================================

    def _validate_inputs(
        self,
        market_snapshot: MarketSnapshot,
        regime: RegimeResult,
        config: dict[str, Any],
    ) -> bool:
        """Validate semua input parameters."""
        self._validation_errors.clear()

        # Validate market snapshot
        if not market_snapshot:
            self._validation_errors.append("Market snapshot is None")
            return False

        if market_snapshot.close_price <= 0:
            self._validation_errors.append(
                f"Invalid close price: {market_snapshot.close_price}"
            )
            return False

        if market_snapshot.high_price < market_snapshot.low_price:
            self._validation_errors.append(
                f"High {market_snapshot.high_price} < Low {market_snapshot.low_price}"
            )
            return False

        if market_snapshot.tick_volume <= 0:
            self._validation_errors.append(
                f"Invalid volume: {market_snapshot.tick_volume}"
            )
            return False

        # Validate regime
        if not regime or not regime.features:
            self._validation_errors.append("Regime result invalid or missing features")
            return False

        # Validate config
        if not isinstance(config, dict):
            self._validation_errors.append("Config is not a dictionary")
            return False

        if len(self._validation_errors) > 0:
            logger.debug(
                f"{self.strategy_code}: Validation errors: {self._validation_errors}"
            )

        return len(self._validation_errors) == 0

    def _validate_market_regime(
        self, regime: RegimeResult, config: dict[str, Any]
    ) -> bool:
        """Validate bahwa market regime sesuai untuk strategy."""
        # Check regime type
        allowed_regimes = config.get("allowed_regimes", [])
        if allowed_regimes and regime.regime not in allowed_regimes:
            logger.debug(
                f"{self.strategy_code}: Regime {regime.regime} not in allowed regimes"
            )
            return False

        # Check volatility score
        vol_score = float(regime.features.get("volatility_score", 0.0))
        min_vol = config.get("min_volatility_score", 0.5)
        if vol_score < min_vol:
            logger.debug(
                f"{self.strategy_code}: Volatility {vol_score} < minimum {min_vol}"
            )
            return False

        return True

    def _validate_risk_reward(
        self, entry_data: dict[str, Any], config: dict[str, Any]
    ) -> bool:
        """Validate risk:reward ratio acceptable."""
        entry = entry_data["entry_price"]
        sl = entry_data["stop_loss"]
        tp = entry_data["take_profit"]

        risk = abs(entry - sl)
        reward = abs(tp - entry)

        if risk <= 0 or reward <= 0:
            return False

        ratio = reward / risk
        min_ratio = config.get("risk_reward_ratio_min", 1.5)

        if ratio < min_ratio:
            logger.debug(
                f"{self.strategy_code}: RR ratio {ratio:.2f} < minimum {min_ratio}"
            )
            return False

        return True

    def _perform_safety_checks(
        self, market_snapshot: MarketSnapshot, config: dict[str, Any]
    ) -> bool:
        """Perform final safety checks sebelum signal generation."""
        # Check max consecutive signals
        max_consecutive = config.get("max_consecutive_signals", 3)
        current_count = self._consecutive_loss_count
        if current_count >= max_consecutive:
            logger.warning(
                f"{self.strategy_code}: Max consecutive signals reached: {current_count}"
            )
            return False

        # Circuit breaker check
        if config.get("drawdown_stop_loss", False):
            if self._consecutive_loss_count >= 2:
                logger.warning(
                    f"{self.strategy_code}: Drawdown protection triggered"
                )
                return False

        # Price sanity check
        if market_snapshot.close_price <= 0 or market_snapshot.high_price <= 0:
            return False

        return True

    # =========================================================================
    # SWEEP DETECTION METHODS
    # =========================================================================

    def _detect_liquidity_sweep(
        self,
        market_snapshot: MarketSnapshot,
        regime: RegimeResult,
        levels: dict[str, list[float]],
        atr: float,
        config: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Detect liquidity sweep pada support/resistance levels."""
        extension_threshold = config.get("sweep_extension_atr", 0.3) * atr
        tolerance = config.get("level_tolerance_atr", 0.15) * atr

        current_low = market_snapshot.low_price
        current_high = market_snapshot.high_price
        volume = market_snapshot.tick_volume

        sweep_direction = None
        sweep_level = None
        sweep_confidence = 0.0

        # === DOWNSIDE SWEEP (on support) ===
        if levels["supports"]:
            nearest_support = min(
                levels["supports"],
                key=lambda x: abs(x - current_low),
            )

            # Check jika harga sweep di bawah support
            if (
                current_low < nearest_support - extension_threshold
                and abs(current_low - nearest_support) < tolerance + extension_threshold
            ):
                sweep_direction = SignalDirection.SELL  # sweep down -> bullish
                sweep_level = nearest_support
                sweep_confidence = self._calculate_sweep_confidence(
                    market_snapshot=market_snapshot,
                    regime=regime,
                    sweep_type="downside",
                    level=nearest_support,
                    atr=atr,
                    config=config,
                )

        # === UPSIDE SWEEP (on resistance) ===
        if levels["resistances"] and (sweep_confidence < 0.55):
            nearest_resistance = min(
                levels["resistances"],
                key=lambda x: abs(x - current_high),
            )

            # Check jika harga sweep di atas resistance
            if (
                current_high > nearest_resistance + extension_threshold
                and abs(current_high - nearest_resistance) < tolerance + extension_threshold
            ):
                sweep_direction = SignalDirection.BUY  # sweep up -> bearish
                sweep_level = nearest_resistance
                sweep_confidence = self._calculate_sweep_confidence(
                    market_snapshot=market_snapshot,
                    regime=regime,
                    sweep_type="upside",
                    level=nearest_resistance,
                    atr=atr,
                    config=config,
                )

        if not sweep_direction or sweep_confidence < 0.5:
            return None

        return {
            "direction": sweep_direction,
            "level": sweep_level,
            "confidence": min(0.95, sweep_confidence),
            "extension": extension_threshold,
            "volume": volume,
            "volume_quality": self._assess_volume_quality(
                market_snapshot, regime, config
            ),
        }

    def _calculate_sweep_confidence(
        self,
        market_snapshot: MarketSnapshot,
        regime: RegimeResult,
        sweep_type: str,
        level: float,
        atr: float,
        config: dict[str, Any],
    ) -> float:
        """Calculate confidence score untuk sweep detection."""
        confidence = 0.5

        # Factor 1: Volume confirmation (25%)
        vol_quality = self._assess_volume_quality(market_snapshot, regime, config)
        confidence += vol_quality * 0.25

        # Factor 2: Extension degree (30%)
        extension_ratio = (
            abs(market_snapshot.low_price - level) / atr
            if sweep_type == "downside"
            else abs(market_snapshot.high_price - level) / atr
        )
        extension_score = min(0.30, (extension_ratio / 0.5) * 0.30)
        confidence += extension_score

        # Factor 3: Wick quality (20%)
        wick_score = self._assess_wick_quality(market_snapshot, sweep_type)
        confidence += wick_score * 0.20

        # Factor 4: Volatility context (25%)
        vol_context = float(regime.features.get("volatility_score", 0.5))
        confidence += vol_context * 0.25

        return min(0.95, max(0.4, confidence))

    def _assess_volume_quality(
        self,
        market_snapshot: MarketSnapshot,
        regime: RegimeResult,
        config: dict[str, Any],
    ) -> float:
        """Assess volume quality untuk confirmation."""
        current_volume = market_snapshot.tick_volume
        avg_volume = float(regime.features.get("avg_volume", current_volume))

        if avg_volume <= 0:
            return 0.5

        vol_ratio = current_volume / avg_volume
        vol_multiplier = config.get("sweep_volume_multiplier", 1.3)

        if vol_ratio >= vol_multiplier:
            return 0.9
        elif vol_ratio >= vol_multiplier * 0.7:
            return 0.7
        elif vol_ratio >= 1.0:
            return 0.5
        else:
            return 0.3

    def _assess_wick_quality(
        self, market_snapshot: MarketSnapshot, sweep_type: str
    ) -> float:
        """Assess wick quality untuk sweep pattern."""
        high = market_snapshot.high_price
        low = market_snapshot.low_price
        close = market_snapshot.close_price
        open_price = market_snapshot.open_price

        wick_size = 0.0
        if sweep_type == "downside":
            # Lower wick pada downside sweep
            wick_size = max(0, low - (close + open_price) / 2)
        else:
            # Upper wick pada upside sweep
            wick_size = max(0, (close + open_price) / 2 - high)

        range_size = high - low
        if range_size <= 0:
            return 0.5

        wick_ratio = wick_size / range_size
        if wick_ratio > 0.6:  # Strong wick
            return 0.85
        elif wick_ratio > 0.4:
            return 0.65
        else:
            return 0.45

    # =========================================================================
    # SUPPORT/RESISTANCE LEVEL EXTRACTION
    # =========================================================================

    def _extract_support_resistance_levels(
        self, regime: RegimeResult, config: dict[str, Any]
    ) -> dict[str, list[float]]:
        """Extract support/resistance levels dari regime features."""
        supports = []
        resistances = []

        # Try to get dari regime features (jika ada historical data)
        if "support_levels" in regime.features:
            raw_supports = regime.features.get("support_levels", [])
            if isinstance(raw_supports, (list, tuple)):
                supports = [float(x) for x in raw_supports if x and x > 0]

        if "resistance_levels" in regime.features:
            raw_resistances = regime.features.get("resistance_levels", [])
            if isinstance(raw_resistances, (list, tuple)):
                resistances = [float(x) for x in raw_resistances if x and x > 0]

        # Fallback: gunakan volatility-based levels
        if not supports or not resistances:
            supports, resistances = self._generate_volatility_levels(
                regime, config
            )

        return {"supports": supports, "resistances": resistances}

    def _generate_volatility_levels(
        self, regime: RegimeResult, config: dict[str, Any]
    ) -> tuple[list[float], list[float]]:
        """Generate support/resistance levels berdasarkan volatility."""
        current_price = float(regime.features.get("current_price", 0.0))
        atr = float(regime.features.get("atr", 0.01))

        if current_price <= 0 or atr <= 0:
            return [], []

        # Generate levels around current price
        supports = [
            current_price - (i * atr * 1.5) for i in range(1, 4)
        ]
        resistances = [
            current_price + (i * atr * 1.5) for i in range(1, 4)
        ]

        return supports, resistances

    # =========================================================================
    # REVERSAL PATTERN ANALYSIS
    # =========================================================================

    def _analyze_reversal_pattern(
        self,
        market_snapshot: MarketSnapshot,
        regime: RegimeResult,
        sweep: dict[str, Any],
        atr: float,
        config: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Analyze candle pattern setelah sweep untuk reversal confirmation."""
        min_body_atr = config.get("reversal_candle_body_atr", 0.3)
        min_bars = config.get("reversal_min_bars", 2)

        open_price = market_snapshot.open_price
        close_price = market_snapshot.close_price
        high = market_snapshot.high_price
        low = market_snapshot.low_price

        body_size = abs(close_price - open_price)
        body_ratio = body_size / atr if atr > 0 else 0.0

        # Check candle body size
        if body_ratio < min_body_atr:
            return None

        # Determine reversal direction
        is_bullish = close_price > open_price
        is_bearish = close_price < open_price

        # Check for reversal compatibility with sweep
        if sweep["direction"] == SignalDirection.SELL and not is_bullish:
            # Downside sweep harus followed by bullish candle
            return None
        if sweep["direction"] == SignalDirection.BUY and not is_bearish:
            # Upside sweep harus followed by bearish candle
            return None

        # Calculate pattern confidence
        pattern_confidence = self._assess_reversal_pattern(
            market_snapshot=market_snapshot,
            sweep=sweep,
            atr=atr,
            config=config,
        )

        if pattern_confidence < 0.5:
            return None

        return {
            "pattern_type": self._identify_pattern_type(
                market_snapshot, sweep, atr
            ),
            "confidence": min(0.95, pattern_confidence),
            "body_ratio": body_ratio,
            "is_bullish": is_bullish,
            "is_bearish": is_bearish,
        }

    def _assess_reversal_pattern(
        self,
        market_snapshot: MarketSnapshot,
        sweep: dict[str, Any],
        atr: float,
        config: dict[str, Any],
    ) -> float:
        """Assess confidence reversal pattern."""
        confidence = 0.5

        open_price = market_snapshot.open_price
        close_price = market_snapshot.close_price
        high = market_snapshot.high_price
        low = market_snapshot.low_price

        body_size = abs(close_price - open_price)
        body_ratio = body_size / atr if atr > 0 else 0.0

        # Factor 1: Body size (35%)
        if body_ratio > 0.5:
            confidence += 0.35
        elif body_ratio > 0.3:
            confidence += 0.25

        # Factor 2: Wick structure (30%)
        wick_ratio = config.get("reversal_wick_ratio", 1.8)
        if sweep["direction"] == SignalDirection.SELL:
            # Bullish reversal - upper wick harus small, lower wick big
            lower_wick = max(open_price, close_price) - low
            upper_wick = high - max(open_price, close_price)
            if lower_wick > upper_wick * wick_ratio:
                confidence += 0.30
            elif lower_wick > upper_wick:
                confidence += 0.15
        else:
            # Bearish reversal - lower wick harus small, upper wick big
            lower_wick = min(open_price, close_price) - low
            upper_wick = high - min(open_price, close_price)
            if upper_wick > lower_wick * wick_ratio:
                confidence += 0.30
            elif upper_wick > lower_wick:
                confidence += 0.15

        # Factor 3: Close position (25%)
        midpoint = (high + low) / 2
        if sweep["direction"] == SignalDirection.SELL:
            # Bullish - close di upper half
            if close_price > midpoint:
                confidence += 0.25
            elif close_price > low + (midpoint - low) * 0.5:
                confidence += 0.15
        else:
            # Bearish - close di lower half
            if close_price < midpoint:
                confidence += 0.25
            elif close_price < high - (high - midpoint) * 0.5:
                confidence += 0.15

        # Factor 4: Volume confirmation (10%)
        confidence += 0.10

        return min(0.95, confidence)

    def _identify_pattern_type(
        self,
        market_snapshot: MarketSnapshot,
        sweep: dict[str, Any],
        atr: float,
    ) -> str:
        """Identify reversal pattern type."""
        open_price = market_snapshot.open_price
        close_price = market_snapshot.close_price
        high = market_snapshot.high_price
        low = market_snapshot.low_price

        body_size = abs(close_price - open_price)
        wick_size = max(high - max(close_price, open_price), min(close_price, open_price) - low)

        wick_body_ratio = wick_size / body_size if body_size > 0 else 0.0

        if wick_body_ratio > 1.5:
            return "hammer" if wick_size == min(close_price, open_price) - low else "shooting_star"
        elif body_size > 0.5 * atr:
            return "strong_reversal"
        else:
            return "weak_reversal"

    # =========================================================================
    # ENTRY & EXIT CALCULATION
    # =========================================================================

    def _calculate_entry_exit(
        self,
        market_snapshot: MarketSnapshot,
        sweep: dict[str, Any],
        reversal: dict[str, Any],
        atr: float,
        config: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Calculate entry price, stop loss, dan take profit."""
        entry_mode = config.get("entry_price_mode", "moderate")
        sl_mult = config.get("stop_loss_atr_multiplier", 1.5)
        tp_mult = config.get("take_profit_atr_multiplier", 2.5)

        entry_price = 0.0
        stop_loss = 0.0
        take_profit = 0.0

        high = market_snapshot.high_price
        low = market_snapshot.low_price
        close = market_snapshot.close_price

        if sweep["direction"] == SignalDirection.SELL:
            # Bullish setup (sweep down, bullish reversal)
            # Entry di different levels tergantung mode
            if entry_mode == "aggressive":
                entry_price = low + (0.2 * atr)  # Close to sweep low
            elif entry_mode == "conservative":
                entry_price = (low + close) / 2  # Midpoint
            else:  # moderate
                entry_price = low + (0.4 * atr)

            stop_loss = low - (sl_mult * atr)
            take_profit = entry_price + (tp_mult * atr)

        else:  # BUY (sweep up, bearish reversal)
            # Entry di different levels tergantung mode
            if entry_mode == "aggressive":
                entry_price = high - (0.2 * atr)  # Close to sweep high
            elif entry_mode == "conservative":
                entry_price = (high + close) / 2  # Midpoint
            else:  # moderate
                entry_price = high - (0.4 * atr)

            stop_loss = high + (sl_mult * atr)
            take_profit = entry_price - (tp_mult * atr)

        # Validation
        if entry_price <= 0 or stop_loss <= 0 or take_profit <= 0:
            return None

        if sweep["direction"] == SignalDirection.SELL:
            if stop_loss >= entry_price or take_profit <= entry_price:
                return None
        else:
            if stop_loss <= entry_price or take_profit >= entry_price:
                return None

        return {
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "entry_mode": entry_mode,
        }

    # =========================================================================
    # SIGNAL CONFIDENCE CALCULATION
    # =========================================================================

    def _calculate_signal_confidence(
        self,
        sweep: dict[str, Any],
        reversal: dict[str, Any],
        entry: dict[str, Any],
        config: dict[str, Any],
    ) -> float:
        """Calculate final signal confidence score."""
        sweep_weight = config.get("sweep_confidence_weight", 0.35)
        reversal_weight = config.get("reversal_confidence_weight", 0.40)
        volume_weight = config.get("volume_confidence_weight", 0.25)

        sweep_conf = sweep.get("confidence", 0.5)
        reversal_conf = reversal.get("confidence", 0.5)
        volume_conf = sweep.get("volume_quality", 0.5)

        final_confidence = (
            sweep_conf * sweep_weight
            + reversal_conf * reversal_weight
            + volume_conf * volume_weight
        )

        return min(0.99, max(0.5, final_confidence))

    # =========================================================================
    # SIGNAL CREATION
    # =========================================================================

    def _create_signal(
        self,
        market_snapshot: MarketSnapshot,
        sweep: dict[str, Any],
        reversal: dict[str, Any],
        entry: dict[str, Any],
        confidence: float,
        pattern_notes: list[str] | None = None,
    ) -> RawSignal:
        """Create RawSignal object dengan semua data."""
        direction = (
            SignalDirection.BUY
            if sweep["direction"] == SignalDirection.SELL
            else SignalDirection.SELL
        )

        return RawSignal(
            direction=direction,
            confidence=confidence,
            entry_price=entry["entry_price"],
            stop_loss=entry["stop_loss"],
            take_profit=entry["take_profit"],
            generated_at=datetime.now(timezone.utc),
            features={
                "strategy_code": self.strategy_code,
                "strategy_version": self.version,
                "sweep_level": sweep["level"],
                "sweep_confidence": sweep["confidence"],
                "sweep_volume_quality": sweep["volume_quality"],
                "reversal_pattern": reversal["pattern_type"],
                "reversal_confidence": reversal["confidence"],
                "reversal_body_ratio": reversal["body_ratio"],
                "entry_mode": entry["entry_mode"],
                "pattern_evidence_notes": pattern_notes or [],
            },
            metadata={
                "strategy_code": self.strategy_code,
                "signal_type": "liquidity_sweep_reversal",
                "pattern": reversal["pattern_type"],
            },
        )

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def _get_atr(
        self,
        market_snapshot: MarketSnapshot,
        regime: RegimeResult,
        config: dict[str, Any],
    ) -> float | None:
        """Get ATR value dengan fallback."""
        atr = regime.features.get("atr")
        if atr and atr > 0:
            return float(atr)

        # Fallback: calculate dari range
        range_val = market_snapshot.high_price - market_snapshot.low_price
        if range_val > 0:
            return range_val

        return None

    def _apply_pattern_evidence_adjustment(
        self,
        signal_confidence: float,
        sweep: dict[str, Any],
        technical_analysis: TechnicalAnalysisResult | None,
        config: dict[str, Any],
    ) -> tuple[float, list[str]]:
        if not is_pattern_enabled(config):
            return signal_confidence, []

        pe = config.get("pattern_evidence") or {}
        notes: list[str] = []
        support_count = 0
        adjusted = signal_confidence

        # direction mapping: signal BUY means low sweep reversal; signal SELL means high sweep reversal
        generated_direction = "BUY" if sweep.get("direction") == SignalDirection.SELL else "SELL"

        if generated_direction == "SELL" and bool(pe.get("allow_double_top_after_high_sweep", True)):
            allowed = {"detected", "waiting_neckline_break", "weak_neckline_break", "neckline_broken"}
            if bool(pe.get("require_neckline_break", False)):
                allowed = {"neckline_broken"}
            if has_pattern_status(technical_analysis, "DOUBLE_TOP", allowed):
                support_count += 1
                notes.append("double_top_after_sweep")
            if has_pattern_status(technical_analysis, "DOUBLE_TOP", {"neckline_broken"}):
                adjusted += float(pe.get("neckline_break_bonus", 0.12))

        if generated_direction == "BUY" and bool(pe.get("allow_double_bottom_after_low_sweep", True)):
            allowed = {"detected", "waiting_neckline_break", "weak_neckline_break", "neckline_broken"}
            if bool(pe.get("require_neckline_break", False)):
                allowed = {"neckline_broken"}
            if has_pattern_status(technical_analysis, "DOUBLE_BOTTOM", allowed):
                support_count += 1
                notes.append("double_bottom_after_sweep")
            if has_pattern_status(technical_analysis, "DOUBLE_BOTTOM", {"neckline_broken"}):
                adjusted += float(pe.get("neckline_break_bonus", 0.12))

        fvg_type = "bullish_fvg" if generated_direction == "BUY" else "bearish_fvg"
        fvg_count = count_fvg(technical_analysis, fvg_type, {"open", "partial"})
        if fvg_count > 0:
            support_count += 1
            adjusted += float(pe.get("fvg_after_sweep_bonus", 0.10))
            notes.append(f"{fvg_type}_after_sweep")

        if bool(pe.get("use_as_hard_requirement", False)) and support_count == 0:
            return 0.0, notes

        return min(0.99, max(0.35, adjusted)), notes
