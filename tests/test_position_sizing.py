"""Test risk-based position sizing with regime multipliers."""

import pytest
from src.strategies.trend_momentum_atr_regime_adaptive import (
    _compute_alloc_pct,
    _apply_regime_multiplier,
)


def test_risk_based_stop_distance_8pct():
    """Test entry=100, stop=92 (8% distance), risk_per_trade=1% => base=12.5%."""
    config = {
        "allocation": {
            "alloc_mode": "risk_based",
            "risk_per_trade_pct": 0.01,  # Risk 1%
            "min_alloc_pct": 0.03,
            "max_alloc_pct": 0.15,
        }
    }

    # 8% stop distance: 1% / 8% = 12.5%
    result = _compute_alloc_pct(config, entry_price=100, sl=92)
    expected = 0.01 / 0.08  # 0.125
    assert result == 0.125, f"Expected 0.125 (12.5%), got {result}"


def test_risk_based_with_regime_multipliers():
    """Test regime multipliers applied to risk-based allocation."""
    config = {
        "allocation": {
            "alloc_mode": "risk_based",
            "risk_per_trade_pct": 0.01,
            "min_alloc_pct": 0.03,
            "max_alloc_pct": 0.15,
        }
    }

    # entry=100, stop=92 => 8% stop distance => base = 1% / 8% = 12.5%
    base_alloc = _compute_alloc_pct(config, entry_price=100, sl=92)
    assert base_alloc == 0.125, f"Expected base 0.125, got {base_alloc}"

    # BULL: 12.5% × 1.5 = 18.75%, clamped to 15%
    bull_result = _apply_regime_multiplier(base_alloc, 1.5, config)
    assert bull_result == 0.15, f"Expected 0.15 (clamped), got {bull_result}"

    # SIDEWAYS: 12.5% × 1.0 = 12.5%
    sideways_result = _apply_regime_multiplier(base_alloc, 1.0, config)
    assert sideways_result == 0.125, f"Expected 0.125, got {sideways_result}"

    # BEAR: 12.5% × 0.7 = 8.75%
    bear_result = _apply_regime_multiplier(base_alloc, 0.7, config)
    assert bear_result == 0.0875, f"Expected 0.0875, got {bear_result}"


def test_risk_based_different_stop_distances():
    """Test risk-based sizing with different stop distances."""
    config = {
        "allocation": {
            "alloc_mode": "risk_based",
            "risk_per_trade_pct": 0.01,  # Risk 1% of equity
            "min_alloc_pct": 0.03,
            "max_alloc_pct": 0.15,
        }
    }

    # 5% stop distance: 1% / 5% = 20%, clamped to 15%
    result = _compute_alloc_pct(config, entry_price=100, sl=95)
    assert result == 0.15, f"Expected 0.15 (clamped), got {result}"

    # 10% stop distance: 1% / 10% = 10%
    result = _compute_alloc_pct(config, entry_price=100, sl=90)
    assert result == 0.10, f"Expected 0.10, got {result}"

    # 20% stop distance: 1% / 20% = 5%
    result = _compute_alloc_pct(config, entry_price=100, sl=80)
    assert result == 0.05, f"Expected 0.05, got {result}"

    # 1% stop distance: 1% / 1% = 100%, clamped to 15%
    result = _compute_alloc_pct(config, entry_price=100, sl=99)
    assert result == 0.15, f"Expected 0.15 (clamped to max), got {result}"


def test_regime_multiplier_bull():
    """Test bull regime multiplier increases position size."""
    config = {
        "allocation": {
            "min_alloc_pct": 0.03,
            "max_alloc_pct": 0.15,
        }
    }

    base_alloc = 0.10
    bull_multiplier = 1.5

    result = _apply_regime_multiplier(base_alloc, bull_multiplier, config)
    assert result == 0.15, f"Expected 0.15 (10% * 1.5 = 15%), got {result}"


def test_regime_multiplier_bear():
    """Test bear regime multiplier decreases position size."""
    config = {
        "allocation": {
            "min_alloc_pct": 0.03,
            "max_alloc_pct": 0.15,
        }
    }

    base_alloc = 0.10
    bear_multiplier = 0.7

    result = _apply_regime_multiplier(base_alloc, bear_multiplier, config)
    assert result == 0.07, f"Expected 0.07 (10% * 0.7 = 7%), got {result}"


def test_regime_multiplier_sideways():
    """Test sideways regime uses base allocation."""
    config = {
        "allocation": {
            "min_alloc_pct": 0.03,
            "max_alloc_pct": 0.15,
        }
    }

    base_alloc = 0.10
    sideways_multiplier = 1.0

    result = _apply_regime_multiplier(base_alloc, sideways_multiplier, config)
    assert result == 0.10, f"Expected 0.10 (10% * 1.0 = 10%), got {result}"


def test_regime_multiplier_clamping():
    """Test regime multiplier respects min/max bounds."""
    config = {
        "allocation": {
            "min_alloc_pct": 0.03,
            "max_alloc_pct": 0.15,
        }
    }

    # Test max clamping with aggressive multiplier
    base_alloc = 0.12
    aggressive_multiplier = 2.0  # 12% * 2.0 = 24%, should clamp to 15%

    result = _apply_regime_multiplier(base_alloc, aggressive_multiplier, config)
    assert result == 0.15, f"Expected 0.15 (clamped), got {result}"

    # Test min clamping with defensive multiplier
    base_alloc = 0.05
    defensive_multiplier = 0.5  # 5% * 0.5 = 2.5%, should clamp to 3%

    result = _apply_regime_multiplier(base_alloc, defensive_multiplier, config)
    assert result == 0.03, f"Expected 0.03 (clamped), got {result}"


def test_no_hardcoded_015():
    """Test there are no hard-coded 0.15 values in position sizing."""
    config = {
        "allocation": {
            "alloc_mode": "risk_based",
            "risk_per_trade_pct": 0.01,
            "min_alloc_pct": 0.03,
            "max_alloc_pct": 0.20,  # Higher ceiling to avoid clamping
        }
    }

    # 8% stop distance: 1% / 8% = 12.5% (not 0.15)
    result1 = _compute_alloc_pct(config, entry_price=100, sl=92)
    assert result1 == 0.125, f"Expected 0.125, got {result1}"
    assert result1 != 0.15, "Position size should not be hard-coded to 0.15"

    # 10% stop distance: 1% / 10% = 10% (not 0.15)
    result2 = _compute_alloc_pct(config, entry_price=100, sl=90)
    assert result2 == 0.10, f"Expected 0.10, got {result2}"
    assert result2 != 0.15, "Position size should not be hard-coded to 0.15"

    # 20% stop distance: 1% / 20% = 5% (not 0.15)
    result3 = _compute_alloc_pct(config, entry_price=100, sl=80)
    assert result3 == 0.05, f"Expected 0.05, got {result3}"
    assert result3 != 0.15, "Position size should not be hard-coded to 0.15"


if __name__ == "__main__":
    # Run tests
    test_risk_based_stop_distance_8pct()
    test_risk_based_with_regime_multipliers()
    test_risk_based_different_stop_distances()
    test_regime_multiplier_bull()
    test_regime_multiplier_bear()
    test_regime_multiplier_sideways()
    test_regime_multiplier_clamping()
    test_no_hardcoded_015()
    print("✅ All risk-based position sizing tests passed!")
