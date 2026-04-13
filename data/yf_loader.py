"""YFinance data source implementation.

Fetches market data via yfinance with parquet caching and retry logic.
See SPEC.md Section 2 for data layer specifications.
"""

import functools
import logging
import time
from typing import Any, Callable

import pandas as pd
import yfinance as yf

from data.base import BaseDataSource
from data import cache_manager as cache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry decorator (replaces tenacity — zero extra dependencies)
# ---------------------------------------------------------------------------

_API_DELAY_SECONDS = 0.5
_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 1


def _retry_with_backoff(func: Callable) -> Callable:
    """Retry on exception with exponential backoff (1s, 2s, 4s).

    Also inserts a 0.5s delay before each API call to avoid Yahoo throttle.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                time.sleep(_API_DELAY_SECONDS)
                return func(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                wait = _BACKOFF_BASE_SECONDS * (2 ** attempt)
                logger.warning(
                    "Attempt %d/%d for %s failed: %s. Retrying in %ds...",
                    attempt + 1, _MAX_RETRIES, func.__name__, exc, wait,
                )
                time.sleep(wait)
        raise last_exc  # type: ignore[misc]

    return wrapper


# ---------------------------------------------------------------------------
# YFinanceSource
# ---------------------------------------------------------------------------

class YFinanceSource(BaseDataSource):
    """Data source backed by yfinance with parquet cache.

    Usage::

        src = YFinanceSource()
        prices = src.get_price_history("NVDA")
        fins = src.get_annual_financials("NVDA")
    """

    # -- prices -------------------------------------------------------------

    def get_price_history(
        self,
        ticker: str,
        period: str = "5y",
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """Fetch OHLCV history. Cache valid for the current day.

        Args:
            ticker: Stock symbol.
            period: Lookback period (default "5y").
            force_refresh: Skip cache and re-download.

        Returns:
            DataFrame with OHLCV columns indexed by date.
        """
        if not force_refresh:
            cached = cache.get_cached_prices(ticker)
            if cached is not None:
                logger.debug("Cache hit: prices for %s", ticker)
                return cached

        df = self._fetch_prices(ticker, period)
        cache.save_prices(ticker, df)
        logger.info("Fetched & cached prices for %s (%d rows)", ticker, len(df))
        return df

    @staticmethod
    @_retry_with_backoff
    def _fetch_prices(ticker: str, period: str) -> pd.DataFrame:
        t = yf.Ticker(ticker)
        df = t.history(period=period, auto_adjust=True)
        if df.empty:
            raise ValueError(f"No price data returned for {ticker}")
        return df

    # -- annual financials --------------------------------------------------

    def get_annual_financials(
        self,
        ticker: str,
        force_refresh: bool = False,
    ) -> dict[str, pd.DataFrame]:
        """Fetch annual income_stmt, balance_sheet, cashflow.

        Returns dict with keys: 'income_stmt', 'balance_sheet', 'cashflow'.
        """
        if not force_refresh:
            cached = cache.get_cached_financials(ticker, "annual")
            if cached is not None:
                logger.debug("Cache hit: annual financials for %s", ticker)
                return cached

        result = self._fetch_annual_financials(ticker)
        cache.save_financials(ticker, "annual", result)
        logger.info("Fetched & cached annual financials for %s", ticker)
        return result

    @staticmethod
    @_retry_with_backoff
    def _fetch_annual_financials(ticker: str) -> dict[str, pd.DataFrame]:
        t = yf.Ticker(ticker)
        return {
            "income_stmt": t.income_stmt,
            "balance_sheet": t.balance_sheet,
            "cashflow": t.cashflow,
        }

    # -- quarterly financials -----------------------------------------------

    def get_quarterly_financials(
        self,
        ticker: str,
        force_refresh: bool = False,
    ) -> dict[str, pd.DataFrame]:
        """Fetch quarterly income_stmt, balance_sheet, cashflow."""
        if not force_refresh:
            cached = cache.get_cached_financials(ticker, "quarterly")
            if cached is not None:
                logger.debug("Cache hit: quarterly financials for %s", ticker)
                return cached

        result = self._fetch_quarterly_financials(ticker)
        cache.save_financials(ticker, "quarterly", result)
        logger.info("Fetched & cached quarterly financials for %s", ticker)
        return result

    @staticmethod
    @_retry_with_backoff
    def _fetch_quarterly_financials(ticker: str) -> dict[str, pd.DataFrame]:
        t = yf.Ticker(ticker)
        return {
            "income_stmt": t.quarterly_income_stmt,
            "balance_sheet": t.quarterly_balance_sheet,
            "cashflow": t.quarterly_cashflow,
        }

    # -- analyst estimates --------------------------------------------------

    def get_analyst_estimates(
        self,
        ticker: str,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """Fetch analyst EPS estimates. Snapshots are never overwritten.

        Each day's fetch is saved as a separate file to build history.
        """
        if not force_refresh:
            cached = cache.get_cached_estimates(ticker)
            if cached is not None:
                logger.debug("Cache hit: estimates for %s", ticker)
                return cached

        df = self._fetch_estimates(ticker)
        cache.save_estimates(ticker, df)
        logger.info("Fetched & cached estimates for %s", ticker)
        return df

    @staticmethod
    @_retry_with_backoff
    def _fetch_estimates(ticker: str) -> pd.DataFrame:
        t = yf.Ticker(ticker)
        df = t.earnings_estimate
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            raise ValueError(f"No analyst estimates returned for {ticker}")
        return df

    # -- info ---------------------------------------------------------------

    def get_info(
        self,
        ticker: str,
        force_refresh: bool = False,
    ) -> dict:
        """Fetch ticker info snapshot. One snapshot per day.

        Returns dict with fields per SPEC 2.3.2.
        """
        if not force_refresh:
            cached = cache.get_cached_info(ticker)
            if cached is not None:
                logger.debug("Cache hit: info for %s", ticker)
                return cached

        info = self._fetch_info(ticker)
        cache.save_info(ticker, info)
        logger.info("Fetched & cached info for %s", ticker)
        return info

    @staticmethod
    @_retry_with_backoff
    def _fetch_info(ticker: str) -> dict:
        t = yf.Ticker(ticker)
        info = t.info
        if not info or info.get("regularMarketPrice") is None:
            raise ValueError(f"No info returned for {ticker}")
        return info

