from __future__ import annotations

from scripts.seed_runtime_configs import RUNTIME_CONFIG_SEEDS, validate_runtime_config_seeds


def test_runtime_config_seed_definitions_are_valid() -> None:
    validate_runtime_config_seeds()

    assert len(RUNTIME_CONFIG_SEEDS) == 33
    assert any(
        seed["config_key"] == "max_trades_per_day" and seed["update_reason"] == "restore after api test"
        for seed in RUNTIME_CONFIG_SEEDS
    )
    assert any(seed["config_key"] == "market_structure_override_min_confidence" for seed in RUNTIME_CONFIG_SEEDS)
    assert any(seed["config_key"] == "signal_quality_min_score" for seed in RUNTIME_CONFIG_SEEDS)
