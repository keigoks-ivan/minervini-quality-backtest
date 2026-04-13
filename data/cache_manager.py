"""Parquet cache manager for market data.

Implements the cache strategy defined in SPEC 2.5:
- prices: daily freshness, overwrite on update
- financials: refresh if latest column > 90 days old
- estimates: monthly snapshots, never overwrite old ones
- info: daily snapshots
"""

from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

CACHE_ROOT = Path(__file__).parent / "cache"

# Subdirectory layout per SPEC 2.5
PRICES_DIR = CACHE_ROOT / "prices"
FINANCIALS_DIR = CACHE_ROOT / "financials"
ESTIMATES_DIR = CACHE_ROOT / "estimates"
INFO_DIR = CACHE_ROOT / "info"


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Prices cache: {ticker}_5y.parquet — valid if written today
# ---------------------------------------------------------------------------

def get_cached_prices(ticker: str) -> pd.DataFrame | None:
    """Return cached price DataFrame if it was written today, else None."""
    path = PRICES_DIR / f"{ticker}_5y.parquet"
    if not path.exists():
        return None
    mtime = datetime.fromtimestamp(path.stat().st_mtime).date()
    if mtime < date.today():
        return None
    return pd.read_parquet(path)


def save_prices(ticker: str, df: pd.DataFrame) -> Path:
    """Write price DataFrame to cache, overwriting any previous file."""
    _ensure_dir(PRICES_DIR)
    path = PRICES_DIR / f"{ticker}_5y.parquet"
    df.to_parquet(path)
    return path


# ---------------------------------------------------------------------------
# Financials cache: {ticker}_annual.parquet / {ticker}_quarterly.parquet
# Valid if the newest fiscal-period column is < 90 days old (relative to file
# mtime, not calendar — we can't know the exact earnings date).
# ---------------------------------------------------------------------------

_FINANCIALS_MAX_AGE_DAYS = 90

_STATEMENT_KEYS = ("income_stmt", "balance_sheet", "cashflow")


def _financials_path(ticker: str, freq: str, stmt: str) -> Path:
    return FINANCIALS_DIR / f"{ticker}_{freq}_{stmt}.parquet"


def get_cached_financials(
    ticker: str, freq: str
) -> dict[str, pd.DataFrame] | None:
    """Return cached financials dict if all three statements exist and are fresh.

    Args:
        ticker: Stock symbol.
        freq: 'annual' or 'quarterly'.

    Returns:
        Dict with keys 'income_stmt', 'balance_sheet', 'cashflow', or None.
    """
    result = {}
    for stmt in _STATEMENT_KEYS:
        path = _financials_path(ticker, freq, stmt)
        if not path.exists():
            return None
        mtime = datetime.fromtimestamp(path.stat().st_mtime).date()
        if (date.today() - mtime) > timedelta(days=_FINANCIALS_MAX_AGE_DAYS):
            return None
        result[stmt] = pd.read_parquet(path)
    return result


def save_financials(
    ticker: str, freq: str, statements: dict[str, pd.DataFrame]
) -> None:
    """Write each financial statement as a separate parquet file."""
    _ensure_dir(FINANCIALS_DIR)
    for stmt in _STATEMENT_KEYS:
        df = statements.get(stmt)
        if df is not None and not df.empty:
            path = _financials_path(ticker, freq, stmt)
            df.to_parquet(path)


# ---------------------------------------------------------------------------
# Estimates cache: {ticker}_{YYYY-MM-DD}.parquet — never overwrite old ones
# ---------------------------------------------------------------------------

def get_cached_estimates(ticker: str) -> pd.DataFrame | None:
    """Return today's estimate snapshot if it exists, else None."""
    _ensure_dir(ESTIMATES_DIR)
    today_str = date.today().isoformat()
    path = ESTIMATES_DIR / f"{ticker}_{today_str}.parquet"
    if not path.exists():
        return None
    return pd.read_parquet(path)


def save_estimates(ticker: str, df: pd.DataFrame) -> Path:
    """Save today's estimate snapshot. Never overwrites old dates."""
    _ensure_dir(ESTIMATES_DIR)
    today_str = date.today().isoformat()
    path = ESTIMATES_DIR / f"{ticker}_{today_str}.parquet"
    df.to_parquet(path)
    return path


# ---------------------------------------------------------------------------
# Info cache: {ticker}_{YYYY-MM-DD}.parquet — daily snapshot
# ---------------------------------------------------------------------------

def get_cached_info(ticker: str) -> dict | None:
    """Return today's info snapshot as dict if it exists, else None."""
    _ensure_dir(INFO_DIR)
    today_str = date.today().isoformat()
    path = INFO_DIR / f"{ticker}_{today_str}.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    return df.iloc[0].to_dict()


def save_info(ticker: str, info: dict) -> Path:
    """Save today's info snapshot as a single-row parquet."""
    _ensure_dir(INFO_DIR)
    today_str = date.today().isoformat()
    path = INFO_DIR / f"{ticker}_{today_str}.parquet"
    df = pd.DataFrame([info])
    df.to_parquet(path)
    return path
