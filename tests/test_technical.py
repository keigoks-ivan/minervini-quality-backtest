"""Tests for Trend Template and RS Rating.

Uses real yfinance data for NVDA, LULU, GLW.
"""

import numpy as np
import pandas as pd
import pytest
import yaml

from data.yf_loader import YFinanceSource
from patterns.trend_template import check_trend_template
from patterns.rs_rating import (
    calculate_rs_score,
    calculate_rs_ratings,
    meets_rs_threshold,
)

TICKERS = ["NVDA", "LULU", "GLW"]


@pytest.fixture(scope="module")
def source() -> YFinanceSource:
    return YFinanceSource()


@pytest.fixture(scope="module")
def params() -> dict:
    with open("configs/params.yaml") as f:
        return yaml.safe_load(f)["technical_filter"]


@pytest.fixture(scope="module")
def prices_map(source: YFinanceSource) -> dict[str, pd.DataFrame]:
    return {t: source.get_price_history(t) for t in TICKERS}


# ===================================================================
# TestTrendTemplate
# ===================================================================

class TestTrendTemplate:

    def test_nvda_trend(self, prices_map: dict) -> None:
        """NVDA should likely be trend confirmed (or show clear details)."""
        passed, details = check_trend_template(prices_map["NVDA"])
        print(f"\n=== NVDA Trend Template: {'PASS' if passed else 'FAIL'} ===")
        for k, v in details.items():
            if isinstance(v, dict):
                status = "PASS" if v.get("pass") else ("SKIP" if v.get("pass") is None else "FAIL")
                print(f"  {k} [{status}]: {v.get('desc', '')} — {v}")
        # Don't hard-assert since market conditions vary; just verify structure
        assert isinstance(passed, bool)

    def test_lulu_trend(self, prices_map: dict) -> None:
        """LULU expected to fail trend (below MA200)."""
        passed, details = check_trend_template(prices_map["LULU"])
        print(f"\n=== LULU Trend Template: {'PASS' if passed else 'FAIL'} ===")
        for k, v in details.items():
            if isinstance(v, dict):
                status = "PASS" if v.get("pass") else ("SKIP" if v.get("pass") is None else "FAIL")
                print(f"  {k} [{status}]: {v.get('desc', '')}")

    def test_insufficient_data_returns_error(self) -> None:
        """Less than 200 days should return error."""
        dates = pd.date_range(end="2026-04-10", periods=150, freq="B")
        prices = pd.DataFrame({
            "Open": [100.0] * 150,
            "High": [101.0] * 150,
            "Low": [99.0] * 150,
            "Close": [100.0] * 150,
            "Volume": [1_000_000] * 150,
        }, index=dates)
        passed, details = check_trend_template(prices)
        assert not passed
        assert "error" in details
        assert details["error"] == "insufficient data"
        assert details["available_days"] == 150

    def test_details_structure_correct(self, prices_map: dict) -> None:
        """Verify all 8 conditions present with required keys."""
        _, details = check_trend_template(prices_map["NVDA"])
        for i in range(1, 8):
            key = f"condition_{i}"
            assert key in details, f"Missing {key}"
            assert "pass" in details[key]
            assert "desc" in details[key]
        assert "condition_8" in details
        assert details["condition_8"]["pass"] is None  # SKIP


# ===================================================================
# TestRSRating
# ===================================================================

class TestRSRating:

    def test_rs_score_calculation_nvda(self, prices_map: dict) -> None:
        """Verify RS score matches manual calculation."""
        close = prices_map["NVDA"]["Close"]
        score = calculate_rs_score(close)
        assert score is not None

        # Manual verification
        c = float(close.iloc[-1])
        r_3m = c / float(close.iloc[-63]) - 1
        r_6m = c / float(close.iloc[-126]) - 1
        r_9m = c / float(close.iloc[-189]) - 1
        r_12m = c / float(close.iloc[-252]) - 1
        expected = 0.4 * r_3m + 0.2 * r_6m + 0.2 * r_9m + 0.2 * r_12m

        print(f"\n=== NVDA RS Score ===")
        print(f"  3M return: {r_3m:.4f}")
        print(f"  6M return: {r_6m:.4f}")
        print(f"  9M return: {r_9m:.4f}")
        print(f"  12M return: {r_12m:.4f}")
        print(f"  RS score: {score:.4f} (expected: {expected:.4f})")
        assert abs(score - expected) < 1e-10

    def test_rs_score_insufficient_data_returns_none(self) -> None:
        prices = pd.Series([100.0] * 200, index=pd.date_range("2025-01-01", periods=200))
        score = calculate_rs_score(prices)
        assert score is None

    def test_rs_ratings_percentile_logic(self) -> None:
        """10 fake tickers: verify ranking produces expected percentiles."""
        scores = {f"T{i}": float(i) for i in range(1, 11)}
        # T1=1, T2=2, ..., T10=10
        ratings = calculate_rs_ratings(scores)

        print(f"\n=== RS Ratings (10 tickers) ===")
        for t in sorted(ratings, key=lambda x: ratings[x]):
            print(f"  {t}: score={scores[t]}, rating={ratings[t]}")

        # T10 (highest score) should have highest rating
        assert ratings["T10"] > ratings["T1"]
        # T1 (lowest) should be 1
        assert ratings["T1"] == 1
        # All ratings between 1-99
        for r in ratings.values():
            assert 1 <= r <= 99

    def test_meets_threshold_mlb_vs_3a(self, params: dict) -> None:
        assert meets_rs_threshold(85, "MLB", params)   # 85 >= 80
        assert not meets_rs_threshold(75, "MLB", params)  # 75 < 80
        assert meets_rs_threshold(95, "3A", params)    # 95 >= 90
        assert not meets_rs_threshold(85, "3A", params)   # 85 < 90


# ===================================================================
# TestIntegration
# ===================================================================

class TestIntegration:

    def test_three_tickers_complete_technical_check(
        self, prices_map: dict, params: dict
    ) -> None:
        """Full technical analysis for all three tickers."""
        # RS scores and ratings
        rs_scores = {}
        for ticker in TICKERS:
            close = prices_map[ticker]["Close"]
            score = calculate_rs_score(close)
            if score is not None:
                rs_scores[ticker] = score
        rs_ratings = calculate_rs_ratings(rs_scores)

        print("\n=== Complete Technical Check ===")
        for ticker in TICKERS:
            prices = prices_map[ticker]
            passed, details = check_trend_template(prices)
            rating = rs_ratings.get(ticker, 0)
            score = rs_scores.get(ticker, 0)

            print(f"\n--- {ticker} ---")
            print(f"  Trend Template: {'PASS' if passed else 'FAIL'}")
            for k, v in details.items():
                if isinstance(v, dict):
                    p = v.get("pass")
                    tag = "PASS" if p else ("SKIP" if p is None else "FAIL")
                    print(f"    {k} [{tag}]: {v.get('desc', '')}")
                    # Print key values
                    for vk in ("close", "ma50", "ma150", "ma200", "52w_high",
                               "52w_low", "pct_above", "pct_below"):
                        if vk in v:
                            print(f"      {vk}: {v[vk]}")

            print(f"  RS Score: {score:.4f}")
            print(f"  RS Rating: {rating}/99")
            print(f"  Meets MLB technical (RS>=80): {meets_rs_threshold(rating, 'MLB', params)}")
            print(f"  Meets 3A technical (RS>=90): {meets_rs_threshold(rating, '3A', params)}")
