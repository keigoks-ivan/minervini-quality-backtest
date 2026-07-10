"""Universe builder: S&P 500 + NASDAQ 100 from Wikipedia, TWSE from OpenAPI.

Implements SPEC Section 2.2: stock universe definition, caching, and filtering.
"""

import io
import json
import logging
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

from data.yf_loader import YFinanceSource

logger = logging.getLogger(__name__)

UNIVERSE_DIR = Path("data/universe")

_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
# Components table moved out of the Nasdaq-100 article on 2026-07-09;
# keep the old article as fallback in case the move is reverted.
_NDX_URLS = [
    "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies",
    "https://en.wikipedia.org/wiki/Nasdaq-100",
]
_TWSE_LIST_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"


def _fix_ticker(symbol: str) -> str:
    """Convert Wikipedia ticker format to yfinance format.

    Wikipedia uses dots (BRK.B), yfinance uses hyphens (BRK-B).
    """
    return symbol.strip().replace(".", "-")


def _fetch_html(url: str) -> str:
    """Fetch HTML with a proper User-Agent to avoid Wikipedia 403."""
    req = Request(url, headers={"User-Agent": "QGM-Universe-Builder/1.0"})
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


# ---------------------------------------------------------------------------
# Fetch tickers from Wikipedia
# ---------------------------------------------------------------------------

def fetch_sp500_tickers() -> list[str]:
    """Fetch current S&P 500 constituents from Wikipedia.

    Returns:
        Sorted list of tickers in yfinance format.
    """
    html = _fetch_html(_SP500_URL)
    tables = pd.read_html(io.StringIO(html))
    # First table has the constituents
    df = tables[0]
    tickers = df["Symbol"].apply(_fix_ticker).tolist()
    return sorted(set(tickers))


def fetch_ndx_tickers() -> list[str]:
    """Fetch current NASDAQ-100 constituents from Wikipedia.

    Returns:
        Sorted list of tickers in yfinance format.
    """
    for url in _NDX_URLS:
        try:
            html = _fetch_html(url)
            tables = pd.read_html(io.StringIO(html))
        except Exception as exc:
            logger.warning("Failed to fetch NDX components from %s: %s", url, exc)
            continue
        # The components table has a 'Ticker' column and ~100 rows; find it
        for t in tables:
            if "Ticker" in t.columns and len(t) >= 80:
                tickers = t["Ticker"].apply(_fix_ticker).tolist()
                return sorted(set(tickers))
    raise ValueError("Could not find NASDAQ-100 components table on Wikipedia")


def fetch_twse_tickers() -> list[str]:
    """Fetch TWSE-listed common stocks, excluding financials and non-equity types.

    Pre-filters by industry code (17 = financials) and 4-digit numeric
    ticker pattern to exclude ETFs, warrants, and preferred shares.
    Returns tickers with yfinance '.TW' suffix.
    """
    req = Request(_TWSE_LIST_URL, headers={"User-Agent": "QGM-TW/1.0"})
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    tickers = []
    for row in data:
        code = row.get("公司代號", "").strip()
        industry = row.get("產業別", "").strip()
        if industry == "17":  # Financials
            continue
        if not (len(code) == 4 and code.isdigit()):
            continue
        tickers.append(f"{code}.TW")
    return sorted(set(tickers))


# ---------------------------------------------------------------------------
# Build & cache universe
# ---------------------------------------------------------------------------

def build_universe(
    indexes: list[str] | None = None,
    cache_dir: str = "data/universe",
    force_refresh: bool = False,
) -> list[str]:
    """Build merged universe from specified indexes, with monthly cache.

    Args:
        indexes: List of index names. Default ['SP500', 'NDX'].
        cache_dir: Directory for parquet cache.
        force_refresh: Skip cache and re-fetch.

    Returns:
        Sorted, deduplicated list of tickers.
    """
    if indexes is None:
        indexes = ["SP500", "NDX"]

    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    month_str = date.today().strftime("%Y-%m")
    cache_key = "_".join(sorted(indexes)).lower()
    parquet_path = cache_path / f"universe_{cache_key}_{month_str}.parquet"

    # Back-compat: old US cache lacks cache_key prefix
    legacy_path = cache_path / f"universe_{month_str}.parquet"
    if not force_refresh and parquet_path.exists():
        df = pd.read_parquet(parquet_path)
        tickers = df["ticker"].tolist()
        logger.info("Loaded %d tickers from cache %s", len(tickers), parquet_path)
        return tickers
    if not force_refresh and set(indexes) == {"SP500", "NDX"} and legacy_path.exists():
        df = pd.read_parquet(legacy_path)
        tickers = df["ticker"].tolist()
        logger.info("Loaded %d tickers from legacy cache %s", len(tickers), legacy_path)
        return tickers

    all_tickers: set[str] = set()
    fetchers = {
        "SP500": fetch_sp500_tickers,
        "NDX": fetch_ndx_tickers,
        "TWSE": fetch_twse_tickers,
    }

    for idx in indexes:
        fetcher = fetchers.get(idx)
        if fetcher is None:
            logger.warning("Unknown index: %s, skipping", idx)
            continue
        tickers = fetcher()
        logger.info("Fetched %d tickers from %s", len(tickers), idx)
        all_tickers.update(tickers)

    result = sorted(all_tickers)

    # Cache
    df = pd.DataFrame({"ticker": result})
    df.to_parquet(parquet_path)
    logger.info("Cached %d tickers to %s", len(result), parquet_path)

    return result


# ---------------------------------------------------------------------------
# Filter universe (SPEC 2.2 exclusion rules)
# ---------------------------------------------------------------------------

def filter_universe(
    tickers: list[str],
    params: dict,
    loader: YFinanceSource,
) -> tuple[list[str], dict]:
    """Apply SPEC 2.2 exclusion rules to a ticker list.

    Exclusions:
    - Market cap < min_market_cap_usd
    - Analyst coverage < min_analyst_coverage
    - Listed < min_listing_years
    - REIT, ADR (quoteType)
    - Non-USD currency

    Args:
        tickers: Raw ticker list from build_universe().
        params: universe block from params.yaml.
        loader: YFinanceSource instance for fetching info.

    Returns:
        (filtered_tickers, rejection_stats)
        rejection_stats: {'low_market_cap': 12, 'low_coverage': 3, ...}
    """
    # Market cap threshold: prefer market-specific key, fall back to USD
    min_cap = params.get("min_market_cap", params.get("min_market_cap_usd", 2_000_000_000))
    min_coverage = params.get("min_analyst_coverage", 3)
    min_years = params.get("min_listing_years", 3)
    allowed_currencies = set(params.get("allowed_currencies", ["USD"]))

    excluded_types = {"REIT", "ADR"}

    filtered = []
    stats = {
        "low_market_cap": 0,
        "low_analyst_coverage": 0,
        "short_listing_history": 0,
        "excluded_type": 0,
        "currency_mismatch": 0,
        "data_error": 0,
        "total_input": len(tickers),
    }

    for i, ticker in enumerate(tickers):
        if (i + 1) % 50 == 0:
            logger.info("Filtering %d/%d...", i + 1, len(tickers))

        try:
            info = loader.get_info(ticker)
        except Exception as e:
            logger.warning("Failed to get info for %s: %s", ticker, e)
            stats["data_error"] += 1
            continue

        # Market cap
        cap = info.get("marketCap")
        if cap is None or cap < min_cap:
            stats["low_market_cap"] += 1
            continue

        # Analyst coverage
        coverage = info.get("numberOfAnalystOpinions")
        if coverage is None or coverage < min_coverage:
            stats["low_analyst_coverage"] += 1
            continue

        # Quote type (REIT, ADR)
        qtype = info.get("quoteType", "")
        # Also check for REIT in industry/sector
        sector = info.get("sector", "")
        industry = info.get("industry", "")
        is_reit = (
            qtype in excluded_types
            or "REIT" in sector.upper()
            or "REIT" in industry.upper()
        )
        if is_reit:
            stats["excluded_type"] += 1
            continue

        # Currency
        currency = info.get("currency", "USD")
        if currency not in allowed_currencies:
            stats["currency_mismatch"] += 1
            continue

        # Listing years — check via price history length
        # 3 years ≈ 756 trading days; we have 5y data so check if ≥ 756 rows
        try:
            prices = loader.get_price_history(ticker)
            min_days = min_years * 252
            if len(prices) < min_days:
                stats["short_listing_history"] += 1
                continue
        except Exception:
            stats["short_listing_history"] += 1
            continue

        filtered.append(ticker)

    stats["total_output"] = len(filtered)
    stats["total_excluded"] = stats["total_input"] - stats["total_output"]
    logger.info(
        "Filtered universe: %d → %d (excluded %d)",
        stats["total_input"], stats["total_output"], stats["total_excluded"],
    )
    return sorted(filtered), stats
