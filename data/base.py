"""Abstract base class for data sources.

Defines the interface that all data sources (yfinance, FMP, etc.) must implement.
See SPEC.md Section 2.3 for required data fields.
"""

from abc import ABC, abstractmethod

import pandas as pd


class BaseDataSource(ABC):
    """Abstract interface for fetching market data for a single ticker."""

    @abstractmethod
    def get_price_history(
        self, ticker: str, period: str = "5y"
    ) -> pd.DataFrame:
        """Fetch OHLCV price history.

        Args:
            ticker: Stock symbol (e.g. "NVDA").
            period: Lookback period. Default "5y" per SPEC 2.3.1.

        Returns:
            DataFrame with columns: Open, High, Low, Close, Volume.
            Index is DatetimeIndex. Prices are adjusted (auto_adjust=True).
        """

    @abstractmethod
    def get_annual_financials(
        self, ticker: str
    ) -> dict[str, pd.DataFrame]:
        """Fetch annual financial statements (up to 5 years).

        Args:
            ticker: Stock symbol.

        Returns:
            Dict with keys: 'income_stmt', 'balance_sheet', 'cashflow'.
            Each value is a DataFrame with fiscal year dates as columns.
        """

    @abstractmethod
    def get_quarterly_financials(
        self, ticker: str
    ) -> dict[str, pd.DataFrame]:
        """Fetch quarterly financial statements (up to 5 quarters).

        Args:
            ticker: Stock symbol.

        Returns:
            Dict with keys: 'income_stmt', 'balance_sheet', 'cashflow'.
            Each value is a DataFrame with quarter-end dates as columns.
        """

    @abstractmethod
    def get_analyst_estimates(self, ticker: str) -> pd.DataFrame:
        """Fetch analyst EPS estimates (FY+1, FY+2).

        Args:
            ticker: Stock symbol.

        Returns:
            DataFrame from yfinance earnings_estimate or equivalent.
        """

    @abstractmethod
    def get_info(self, ticker: str) -> dict:
        """Fetch current snapshot info for a ticker.

        Args:
            ticker: Stock symbol.

        Returns:
            Dict containing fields listed in SPEC 2.3.2:
            freeCashflow, totalRevenue, trailingPegRatio, forwardPE,
            debtToEquity, totalCash, totalDebt, fiftyTwoWeekHigh,
            fiftyTwoWeekLow, numberOfAnalystOpinions, targetMeanPrice,
            marketCap, beta, etc.
        """
