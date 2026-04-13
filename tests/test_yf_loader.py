"""Tests for YFinanceSource data loader.

Tests against real yfinance API for NVDA, LULU, GLW.
Also tests cache-hit behavior with mocking.
"""

from unittest.mock import patch

import pandas as pd
import pytest

from data.yf_loader import YFinanceSource

# Tickers covering different sectors: tech, retail, industrial
TICKERS = ["NVDA", "LULU", "GLW"]

# QGM-required info fields from SPEC 2.3.2
QGM_INFO_FIELDS = [
    "freeCashflow",
    "totalRevenue",
    "trailingPegRatio",
    "forwardPE",
    "debtToEquity",
    "totalCash",
    "totalDebt",
    "fiftyTwoWeekHigh",
    "fiftyTwoWeekLow",
    "numberOfAnalystOpinions",
    "targetMeanPrice",
    "marketCap",
]


@pytest.fixture(scope="module")
def source() -> YFinanceSource:
    return YFinanceSource()


# ---------------------------------------------------------------------------
# Price history
# ---------------------------------------------------------------------------

class TestPriceHistory:

    @pytest.mark.parametrize("ticker", TICKERS)
    def test_returns_dataframe_with_5y_data(
        self, source: YFinanceSource, ticker: str
    ) -> None:
        df = source.get_price_history(ticker)
        assert isinstance(df, pd.DataFrame)
        assert not df.empty
        # Should have standard OHLCV columns
        for col in ("Open", "High", "Low", "Close", "Volume"):
            assert col in df.columns, f"Missing column: {col}"
        # 5 years of trading days: expect at least 1000 rows
        assert len(df) > 1000, f"Only {len(df)} rows for {ticker}"


# ---------------------------------------------------------------------------
# Annual financials
# ---------------------------------------------------------------------------

class TestAnnualFinancials:

    @pytest.mark.parametrize("ticker", TICKERS)
    def test_has_three_statements(
        self, source: YFinanceSource, ticker: str
    ) -> None:
        result = source.get_annual_financials(ticker)
        assert isinstance(result, dict)
        for key in ("income_stmt", "balance_sheet", "cashflow"):
            assert key in result, f"Missing key: {key}"
            assert isinstance(result[key], pd.DataFrame)
            assert not result[key].empty, f"{key} is empty for {ticker}"


# ---------------------------------------------------------------------------
# Quarterly financials
# ---------------------------------------------------------------------------

class TestQuarterlyFinancials:

    @pytest.mark.parametrize("ticker", TICKERS)
    def test_has_at_least_4_quarters(
        self, source: YFinanceSource, ticker: str
    ) -> None:
        result = source.get_quarterly_financials(ticker)
        inc = result["income_stmt"]
        assert inc.shape[1] >= 4, (
            f"Only {inc.shape[1]} quarters for {ticker}"
        )


# ---------------------------------------------------------------------------
# Analyst estimates
# ---------------------------------------------------------------------------

class TestAnalystEstimates:

    @pytest.mark.parametrize("ticker", TICKERS)
    def test_has_fy1_fy2(
        self, source: YFinanceSource, ticker: str
    ) -> None:
        df = source.get_analyst_estimates(ticker)
        assert isinstance(df, pd.DataFrame)
        assert not df.empty
        # yfinance earnings_estimate has rows for different periods
        # Should have at least 2 rows (current year, next year)
        assert len(df) >= 2, (
            f"Only {len(df)} estimate rows for {ticker}"
        )


# ---------------------------------------------------------------------------
# Info
# ---------------------------------------------------------------------------

class TestInfo:

    @pytest.mark.parametrize("ticker", TICKERS)
    def test_has_required_qgm_fields(
        self, source: YFinanceSource, ticker: str
    ) -> None:
        info = source.get_info(ticker)
        assert isinstance(info, dict)
        present = [f for f in QGM_INFO_FIELDS if f in info]
        # Allow some tolerance: at least 10 of 12 fields should exist
        assert len(present) >= 10, (
            f"Only {len(present)}/12 QGM fields present for {ticker}. "
            f"Missing: {set(QGM_INFO_FIELDS) - set(present)}"
        )


# ---------------------------------------------------------------------------
# Cache hit — second call should NOT hit the API
# ---------------------------------------------------------------------------

class TestCacheHit:

    def test_cache_hit_does_not_call_api(
        self, source: YFinanceSource
    ) -> None:
        # First call: populates cache (uses real API)
        source.get_price_history("NVDA")

        # Second call: should come from cache, not API
        with patch.object(
            YFinanceSource, "_fetch_prices", wraps=source._fetch_prices
        ) as mock_fetch:
            df = source.get_price_history("NVDA")
            mock_fetch.assert_not_called()
            assert isinstance(df, pd.DataFrame)
            assert not df.empty
