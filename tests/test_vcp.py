"""Tests for VCP detector (Phase 0 MVP).

Uses synthetic data for unit tests and real data for integration.
"""

import numpy as np
import pandas as pd
import pytest
import yaml

from data.yf_loader import YFinanceSource
from patterns.vcp_detector import detect_pivot_breakout, detect_vcp_mvp

TICKERS = ["NVDA", "LULU", "GLW"]


@pytest.fixture(scope="module")
def source() -> YFinanceSource:
    return YFinanceSource()


@pytest.fixture(scope="module")
def params() -> dict:
    with open("configs/params.yaml") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def prices_map(source: YFinanceSource) -> dict[str, pd.DataFrame]:
    return {t: source.get_price_history(t) for t in TICKERS}


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

def _make_vcp_prices(
    base: float = 100.0,
    drawdown_pct: float = 0.15,
    volatility_decay: float = 0.5,
    n_days: int = 80,
) -> tuple[pd.Series, pd.Series]:
    """Create synthetic prices exhibiting a VCP pattern.

    Returns (prices, volumes) where:
    - First 40 days: higher volatility, then converging
    - Last 20 days: tight, low volume
    """
    dates = pd.date_range(end="2026-04-10", periods=n_days, freq="B")
    np.random.seed(42)

    # Build a convergence pattern
    prices = np.full(n_days, base)
    # First 20 days: moderate volatility
    prices[:20] = base + np.random.normal(0, base * 0.03, 20)
    # Days 20-40: larger swings (the "base")
    prices[20:40] = base * (1 - drawdown_pct / 2) + np.random.normal(0, base * 0.02, 20)
    # Days 40-60: tightening
    prices[40:60] = base * 0.98 + np.random.normal(0, base * 0.01, 20)
    # Days 60-80: very tight (VCP tight zone)
    prices[60:] = base * 0.99 + np.random.normal(0, base * 0.003, n_days - 60)

    prices = pd.Series(np.maximum(prices, base * 0.75), index=dates)

    # Volume: high early, declining to low
    volumes = np.concatenate([
        np.random.randint(2_000_000, 3_000_000, 50),  # High volume
        np.random.randint(500_000, 800_000, n_days - 50),  # Low volume
    ])
    volumes = pd.Series(volumes, index=dates)

    return prices, volumes


def _make_volatile_prices(n_days: int = 80) -> tuple[pd.Series, pd.Series]:
    """Prices with high, non-converging volatility."""
    dates = pd.date_range(end="2026-04-10", periods=n_days, freq="B")
    np.random.seed(99)
    prices = 100 + np.cumsum(np.random.normal(0, 3, n_days))
    prices = pd.Series(np.maximum(prices, 50), index=dates)
    volumes = pd.Series(np.random.randint(1_000_000, 2_000_000, n_days), index=dates)
    return prices, volumes


# ===================================================================
# TestVCPDetection
# ===================================================================

class TestVCPDetection:

    def test_vcp_all_conditions_met(self, params: dict) -> None:
        prices, volumes = _make_vcp_prices()
        result = detect_vcp_mvp(prices, volumes, params=params["vcp"])
        print(f"\n=== Synthetic VCP (all met) ===")
        print(f"  {result}")
        assert result["is_vcp"]
        assert result["conditions"]["drawdown_ok"]
        assert result["conditions"]["volatility_ok"]
        assert result["conditions"]["volume_ok"]
        assert result["pivot_price"] is not None

    def test_vcp_high_volatility_fails(self, params: dict) -> None:
        prices, volumes = _make_volatile_prices()
        result = detect_vcp_mvp(prices, volumes, params=params["vcp"])
        print(f"\n=== Volatile (should fail) ===")
        print(f"  volatility_ratio={result['volatility_ratio']}")
        # Either volatility or drawdown should fail
        assert not result["is_vcp"]

    def test_vcp_high_volume_fails(self, params: dict) -> None:
        """Volume stays high throughout → volume_ok should fail."""
        prices, _ = _make_vcp_prices()
        dates = prices.index
        # Flat high volume
        volumes = pd.Series([2_000_000] * len(dates), index=dates)
        result = detect_vcp_mvp(prices, volumes, params=params["vcp"])
        print(f"\n=== High volume (should fail volume) ===")
        print(f"  volume_ratio={result['volume_ratio']}")
        assert not result["conditions"]["volume_ok"]

    def test_vcp_large_drawdown_fails(self, params: dict) -> None:
        """40% drawdown within lookback window → drawdown_ok should fail."""
        dates = pd.date_range(end="2026-04-10", periods=80, freq="B")
        # Last 60 days: drops from 100 to 55 then recovers to 65
        # Ensures >25% drawdown within the 60-day lookback
        prices = pd.Series(
            np.concatenate([
                np.full(20, 100.0),        # days 0-19: flat (outside lookback)
                np.linspace(100, 55, 30),   # days 20-49: sharp drop
                np.linspace(57, 65, 30),    # days 50-79: slight recovery
            ]),
            index=dates,
        )
        volumes = pd.Series([1_000_000] * 80, index=dates)
        result = detect_vcp_mvp(prices, volumes, params=params["vcp"])
        print(f"\n=== Large drawdown ===")
        print(f"  max_drawdown={result['max_drawdown']}")
        assert not result["conditions"]["drawdown_ok"]
        assert result["max_drawdown"] > 0.25

    def test_vcp_insufficient_data(self, params: dict) -> None:
        dates = pd.date_range(end="2026-04-10", periods=30, freq="B")
        prices = pd.Series([100.0] * 30, index=dates)
        volumes = pd.Series([1_000_000] * 30, index=dates)
        result = detect_vcp_mvp(prices, volumes, params=params["vcp"])
        assert not result["is_vcp"]
        assert "error" in result


# ===================================================================
# TestPivotBreakout
# ===================================================================

class TestPivotBreakout:

    def test_breakout_all_conditions_met(self, params: dict) -> None:
        dates = pd.date_range(end="2026-04-10", periods=60, freq="B")
        pivot = 100.0
        # Last day closes above pivot with big volume
        prices = pd.Series([98.0] * 59 + [101.0], index=dates)
        volumes = pd.Series([1_000_000] * 59 + [3_000_000], index=dates)
        result = detect_pivot_breakout(
            prices, volumes, pivot, params["technical_filter"], "MLB"
        )
        print(f"\n=== Breakout (should pass) ===")
        print(f"  {result}")
        assert result["is_breakout"]
        assert result["price_threshold_met"]
        assert result["volume_threshold_met"]

    def test_breakout_price_close_but_volume_low(self, params: dict) -> None:
        dates = pd.date_range(end="2026-04-10", periods=60, freq="B")
        pivot = 100.0
        prices = pd.Series([98.0] * 59 + [101.0], index=dates)
        volumes = pd.Series([1_000_000] * 60, index=dates)  # Flat volume
        result = detect_pivot_breakout(
            prices, volumes, pivot, params["technical_filter"], "MLB"
        )
        print(f"\n=== Price ok but volume low ===")
        print(f"  volume_multiple={result['volume_multiple']}")
        assert not result["is_breakout"]
        assert result["price_threshold_met"]
        assert not result["volume_threshold_met"]

    def test_mlb_vs_3a_volume_multiplier(self, params: dict) -> None:
        """Same volume: passes MLB (1.4x) but fails 3A (1.5x)."""
        dates = pd.date_range(end="2026-04-10", periods=60, freq="B")
        pivot = 100.0
        prices = pd.Series([98.0] * 59 + [101.0], index=dates)
        # Volume at exactly 1.45x average
        base_vol = 1_000_000
        today_vol = int(base_vol * 1.45)
        volumes = pd.Series([base_vol] * 59 + [today_vol], index=dates)

        mlb = detect_pivot_breakout(
            prices, volumes, pivot, params["technical_filter"], "MLB"
        )
        aa = detect_pivot_breakout(
            prices, volumes, pivot, params["technical_filter"], "3A"
        )
        print(f"\n=== MLB vs 3A multiplier ===")
        print(f"  MLB: volume_multiple={mlb['volume_multiple']}, pass={mlb['is_breakout']}")
        print(f"  3A:  volume_multiple={aa['volume_multiple']}, pass={aa['is_breakout']}")
        assert mlb["is_breakout"]  # 1.45 > 1.4
        assert not aa["is_breakout"]  # 1.45 < 1.5


# ===================================================================
# TestIntegration
# ===================================================================

class TestIntegration:

    def test_three_tickers_vcp_status(
        self, prices_map: dict, params: dict
    ) -> None:
        """Run VCP detection on real data for all three tickers."""
        print("\n=== VCP Detection (Real Data) ===")
        for ticker in TICKERS:
            df = prices_map[ticker]
            close = df["Close"]
            volume = df["Volume"]

            result = detect_vcp_mvp(close, volume, params=params["vcp"])
            print(f"\n--- {ticker} ---")
            print(f"  is_vcp: {result['is_vcp']}")
            print(f"  pivot_price: {result['pivot_price']}")
            print(f"  current_price: {result['current_price']}")
            print(f"  distance_to_pivot: {result['distance_to_pivot_pct']:.2%}")
            print(f"  max_drawdown: {result['max_drawdown']:.2%} (threshold <25%): "
                  f"{'OK' if result['conditions']['drawdown_ok'] else 'FAIL'}")
            print(f"  volatility_ratio: {result['volatility_ratio']:.4f} (threshold <0.7): "
                  f"{'OK' if result['conditions']['volatility_ok'] else 'FAIL'}")
            print(f"  volume_ratio: {result['volume_ratio']:.4f} (threshold <0.7): "
                  f"{'OK' if result['conditions']['volume_ok'] else 'FAIL'}")

            # If VCP detected, also check breakout
            if result["is_vcp"]:
                for pool in ("MLB", "3A"):
                    bo = detect_pivot_breakout(
                        close, volume, result["pivot_price"],
                        params["technical_filter"], pool,
                    )
                    print(f"  Breakout ({pool}): {bo['is_breakout']} "
                          f"(price={bo['price_threshold_met']}, vol={bo['volume_threshold_met']} "
                          f"@ {bo['volume_multiple']:.2f}x)")
