"""IBD-style Relative Strength Rating calculation.

Implements SPEC Section 4.2.
RS Score = weighted return: 0.4×3M + 0.2×6M + 0.2×9M + 0.2×12M
RS Rating = percentile rank across the universe (1-99).
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def calculate_rs_score(prices: pd.Series) -> float | None:
    """Compute raw RS score using IBD weighted return formula.

    Args:
        prices: Close price Series with at least 252 trading days.

    Returns:
        Raw RS score (float), or None if insufficient data.
    """
    if prices is None or len(prices) < 252:
        return None

    current = float(prices.iloc[-1])

    r_3m = current / float(prices.iloc[-63]) - 1
    r_6m = current / float(prices.iloc[-126]) - 1
    r_9m = current / float(prices.iloc[-189]) - 1
    r_12m = current / float(prices.iloc[-252]) - 1

    return 0.4 * r_3m + 0.2 * r_6m + 0.2 * r_9m + 0.2 * r_12m


def calculate_rs_ratings(
    all_ticker_scores: dict[str, float],
) -> dict[str, int]:
    """Convert raw RS scores to 1-99 percentile ratings.

    Args:
        all_ticker_scores: {ticker: rs_score} for the universe.
            Tickers with None scores should be excluded before calling.

    Returns:
        {ticker: rating} where rating is 1-99.
    """
    if len(all_ticker_scores) < 30:
        logger.warning(
            "RS rating with only %d tickers — percentile rankings "
            "have limited statistical meaning",
            len(all_ticker_scores),
        )

    scores = pd.Series(all_ticker_scores)
    n = len(scores)

    ratings = {}
    for ticker, score in scores.items():
        pct_below = (scores < score).sum() / n
        rating = int(pct_below * 99) + 1
        ratings[ticker] = min(rating, 99)

    return ratings


def meets_rs_threshold(rs_rating: int, pool: str, params: dict) -> bool:
    """Check if RS rating meets the pool's minimum threshold.

    Args:
        rs_rating: 1-99 percentile rating.
        pool: 'MLB' or '3A'.
        params: technical_filter block from params.yaml.

    Returns:
        True if rating >= threshold for the pool.
    """
    if pool == "MLB":
        threshold = params["mlb"]["rs_rating_min"]
    elif pool == "3A":
        threshold = params["triple_a"]["rs_rating_min"]
    else:
        return False
    return rs_rating >= threshold
