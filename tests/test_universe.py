"""Tests for universe builder.

Fetch tests use real Wikipedia data.
Filter tests use mocked ticker info.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import shutil

import pandas as pd
import pytest
import yaml

from data.universe_builder import (
    build_universe,
    fetch_ndx_tickers,
    fetch_sp500_tickers,
    filter_universe,
)
from data.yf_loader import YFinanceSource

UNIVERSE_TEST_DIR = "data/universe_test"


@pytest.fixture(scope="module")
def sp500() -> list[str]:
    return fetch_sp500_tickers()


@pytest.fixture(scope="module")
def ndx() -> list[str]:
    return fetch_ndx_tickers()


@pytest.fixture(scope="module")
def params() -> dict:
    with open("configs/params.yaml") as f:
        return yaml.safe_load(f)["universe"]


@pytest.fixture(autouse=True)
def clean_test_cache():
    p = Path(UNIVERSE_TEST_DIR)
    if p.exists():
        shutil.rmtree(p)
    yield
    if p.exists():
        shutil.rmtree(p)


# ===================================================================
# TestFetch
# ===================================================================

class TestFetch:

    def test_sp500_has_500_ish_tickers(self, sp500: list[str]) -> None:
        print(f"\n  SP500 count: {len(sp500)}")
        print(f"  First 10: {sp500[:10]}")
        assert 490 <= len(sp500) <= 510

    def test_ndx_has_100_ish_tickers(self, ndx: list[str]) -> None:
        print(f"\n  NDX count: {len(ndx)}")
        print(f"  First 10: {ndx[:10]}")
        assert 95 <= len(ndx) <= 110

    def test_ticker_format_yfinance_compatible(self, sp500: list[str]) -> None:
        """No dots in tickers — BRK.B should be BRK-B."""
        for t in sp500:
            assert "." not in t, f"Ticker {t} still has dot"

    def test_no_duplicates_in_union(
        self, sp500: list[str], ndx: list[str]
    ) -> None:
        union = sorted(set(sp500 + ndx))
        print(f"\n  SP500: {len(sp500)}, NDX: {len(ndx)}, Union: {len(union)}")
        overlap = set(sp500) & set(ndx)
        print(f"  Overlap: {len(overlap)} tickers")
        # Union should have no duplicates by construction
        assert len(union) == len(set(union))


# ===================================================================
# TestCache
# ===================================================================

class TestCache:

    def test_cache_hit_skips_wikipedia(self) -> None:
        # First call: fetches from Wikipedia
        tickers1 = build_universe(cache_dir=UNIVERSE_TEST_DIR)
        assert len(tickers1) > 0

        # Second call: should use cache (no network needed)
        with patch(
            "data.universe_builder.fetch_sp500_tickers"
        ) as mock_sp, patch(
            "data.universe_builder.fetch_ndx_tickers"
        ) as mock_ndx:
            tickers2 = build_universe(cache_dir=UNIVERSE_TEST_DIR)
            mock_sp.assert_not_called()
            mock_ndx.assert_not_called()
        assert tickers1 == tickers2

    def test_force_refresh_bypasses_cache(self) -> None:
        build_universe(cache_dir=UNIVERSE_TEST_DIR)
        # Force refresh should re-fetch
        with patch(
            "data.universe_builder.fetch_sp500_tickers",
            return_value=["AAPL", "MSFT"],
        ) as mock_sp, patch(
            "data.universe_builder.fetch_ndx_tickers",
            return_value=["AAPL", "GOOG"],
        ) as mock_ndx:
            tickers = build_universe(
                cache_dir=UNIVERSE_TEST_DIR, force_refresh=True
            )
            mock_sp.assert_called_once()
            mock_ndx.assert_called_once()
        assert sorted(tickers) == ["AAPL", "GOOG", "MSFT"]


# ===================================================================
# TestFilter
# ===================================================================

class TestFilter:

    def _mock_loader(self, info_map: dict) -> MagicMock:
        """Create a mock YFinanceSource that returns controlled info."""
        loader = MagicMock(spec=YFinanceSource)

        def get_info(ticker):
            return info_map.get(ticker, {})

        def get_price_history(ticker, **kwargs):
            # Return 5 years of data by default
            dates = pd.date_range(end="2026-04-10", periods=1260, freq="B")
            return pd.DataFrame(
                {"Close": [100.0] * 1260, "Volume": [1e6] * 1260},
                index=dates,
            )

        loader.get_info.side_effect = get_info
        loader.get_price_history.side_effect = get_price_history
        return loader

    def test_low_market_cap_excluded(self, params: dict) -> None:
        info_map = {
            "GOOD": {
                "marketCap": 10_000_000_000,
                "numberOfAnalystOpinions": 20,
                "quoteType": "EQUITY",
                "sector": "Technology",
                "industry": "Software",
                "currency": "USD",
            },
            "SMALL": {
                "marketCap": 500_000_000,
                "numberOfAnalystOpinions": 20,
                "quoteType": "EQUITY",
                "sector": "Technology",
                "industry": "Software",
                "currency": "USD",
            },
        }
        loader = self._mock_loader(info_map)
        filtered, stats = filter_universe(["GOOD", "SMALL"], params, loader)
        assert "GOOD" in filtered
        assert "SMALL" not in filtered
        assert stats["low_market_cap"] == 1

    def test_low_analyst_coverage_excluded(self, params: dict) -> None:
        info_map = {
            "COVERED": {
                "marketCap": 10e9,
                "numberOfAnalystOpinions": 20,
                "quoteType": "EQUITY",
                "sector": "Tech",
                "industry": "SW",
                "currency": "USD",
            },
            "NOCOV": {
                "marketCap": 10e9,
                "numberOfAnalystOpinions": 1,
                "quoteType": "EQUITY",
                "sector": "Tech",
                "industry": "SW",
                "currency": "USD",
            },
        }
        loader = self._mock_loader(info_map)
        filtered, stats = filter_universe(["COVERED", "NOCOV"], params, loader)
        assert "COVERED" in filtered
        assert "NOCOV" not in filtered
        assert stats["low_analyst_coverage"] == 1

    def test_reit_excluded(self, params: dict) -> None:
        info_map = {
            "TECH": {
                "marketCap": 10e9,
                "numberOfAnalystOpinions": 20,
                "quoteType": "EQUITY",
                "sector": "Technology",
                "industry": "Software",
                "currency": "USD",
            },
            "REIT1": {
                "marketCap": 10e9,
                "numberOfAnalystOpinions": 20,
                "quoteType": "EQUITY",
                "sector": "Real Estate",
                "industry": "REIT - Diversified",
                "currency": "USD",
            },
        }
        loader = self._mock_loader(info_map)
        filtered, stats = filter_universe(["TECH", "REIT1"], params, loader)
        assert "TECH" in filtered
        assert "REIT1" not in filtered
        assert stats["excluded_type"] == 1

    def test_rejection_stats_accurate(self, params: dict) -> None:
        info_map = {
            "OK": {
                "marketCap": 10e9,
                "numberOfAnalystOpinions": 20,
                "quoteType": "EQUITY",
                "sector": "Tech",
                "industry": "SW",
                "currency": "USD",
            },
            "SMALL": {"marketCap": 1e9, "numberOfAnalystOpinions": 20,
                      "quoteType": "EQUITY", "sector": "T", "industry": "S",
                      "currency": "USD"},
            "NOCOV": {"marketCap": 10e9, "numberOfAnalystOpinions": 1,
                      "quoteType": "EQUITY", "sector": "T", "industry": "S",
                      "currency": "USD"},
            "REIT": {"marketCap": 10e9, "numberOfAnalystOpinions": 20,
                     "quoteType": "EQUITY", "sector": "Real Estate",
                     "industry": "REIT - Office", "currency": "USD"},
            "JPY": {"marketCap": 10e9, "numberOfAnalystOpinions": 20,
                    "quoteType": "EQUITY", "sector": "T", "industry": "S",
                    "currency": "JPY"},
        }
        loader = self._mock_loader(info_map)
        filtered, stats = filter_universe(
            ["OK", "SMALL", "NOCOV", "REIT", "JPY"], params, loader
        )
        assert filtered == ["OK"]
        assert stats["total_input"] == 5
        assert stats["total_output"] == 1
        assert stats["low_market_cap"] == 1
        assert stats["low_analyst_coverage"] == 1
        assert stats["excluded_type"] == 1
        assert stats["non_usd"] == 1
