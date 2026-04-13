"""Minervini Trend Template — 8 conditions for Stage 2 uptrend confirmation.

Implements SPEC Section 4.1. All 8 conditions must pass for Trend Confirmed.
Condition 8 (RS rating) is handled by rs_rating.py and marked SKIP here.
"""

import pandas as pd


def check_trend_template(
    prices: pd.DataFrame,
    as_of_date: pd.Timestamp | None = None,
) -> tuple[bool, dict]:
    """Check the 8 Minervini Trend Template conditions.

    Args:
        prices: OHLCV DataFrame with DatetimeIndex (auto_adjust=True).
        as_of_date: Date to evaluate. None = latest available date.
            For backtesting, pass a historical date.

    Returns:
        (all_pass: bool, details: dict per condition)
        If data is insufficient (< 200 trading days), returns
        (False, {'error': 'insufficient data', 'available_days': N}).
    """
    if prices is None or prices.empty:
        return False, {"error": "no price data"}

    close = prices["Close"]

    # Slice to as_of_date if specified
    if as_of_date is not None:
        close = close.loc[:as_of_date]

    if len(close) < 200:
        return False, {
            "error": "insufficient data",
            "available_days": len(close),
        }

    # Compute moving averages
    ma50 = close.rolling(50).mean()
    ma150 = close.rolling(150).mean()
    ma200 = close.rolling(200).mean()

    # Current values (last row)
    c = float(close.iloc[-1])
    m50 = float(ma50.iloc[-1])
    m150 = float(ma150.iloc[-1])
    m200 = float(ma200.iloc[-1])

    # 52-week high/low (last 252 trading days, or all available)
    lookback_252 = close.iloc[-min(252, len(close)):]
    w52_high = float(lookback_252.max())
    w52_low = float(lookback_252.min())

    details: dict = {}

    # Condition 1: Close > MA150 AND Close > MA200
    details["condition_1"] = {
        "desc": "Close > MA150 and Close > MA200",
        "pass": c > m150 and c > m200,
        "close": round(c, 2),
        "ma150": round(m150, 2),
        "ma200": round(m200, 2),
    }

    # Condition 2: MA150 > MA200
    details["condition_2"] = {
        "desc": "MA150 > MA200",
        "pass": m150 > m200,
        "ma150": round(m150, 2),
        "ma200": round(m200, 2),
    }

    # Condition 3: MA200 rising for at least 1 month (21 trading days)
    ma200_21d_ago = float(ma200.iloc[-22]) if len(ma200) >= 22 else float(ma200.iloc[0])
    ma200_rising = m200 > ma200_21d_ago
    details["condition_3"] = {
        "desc": "MA200 rising >= 1 month",
        "pass": ma200_rising,
        "ma200_now": round(m200, 2),
        "ma200_21d_ago": round(ma200_21d_ago, 2),
        "rising": ma200_rising,
    }

    # Condition 4: MA50 > MA150 > MA200 (full bull alignment)
    details["condition_4"] = {
        "desc": "MA50 > MA150 > MA200",
        "pass": m50 > m150 > m200,
        "ma50": round(m50, 2),
        "ma150": round(m150, 2),
        "ma200": round(m200, 2),
    }

    # Condition 5: Close > MA50
    details["condition_5"] = {
        "desc": "Close > MA50",
        "pass": c > m50,
        "close": round(c, 2),
        "ma50": round(m50, 2),
    }

    # Condition 6: Close > 30% above 52-week low
    pct_above_low = (c - w52_low) / w52_low if w52_low != 0 else 0
    details["condition_6"] = {
        "desc": "Close > 30% above 52W low",
        "pass": pct_above_low > 0.30,
        "close": round(c, 2),
        "52w_low": round(w52_low, 2),
        "pct_above": round(pct_above_low, 4),
    }

    # Condition 7: Close within 25% of 52-week high
    pct_below_high = (w52_high - c) / w52_high if w52_high != 0 else 0
    details["condition_7"] = {
        "desc": "Close within 25% of 52W high",
        "pass": pct_below_high < 0.25,
        "close": round(c, 2),
        "52w_high": round(w52_high, 2),
        "pct_below": round(pct_below_high, 4),
    }

    # Condition 8: RS rating — handled by rs_rating.py
    details["condition_8"] = {
        "desc": "RS Rating >= threshold (MLB:80 / 3A:90)",
        "pass": None,
        "note": "Evaluated separately by rs_rating.py",
    }

    # All pass = conditions 1-7 pass (condition 8 excluded)
    conditions_1_to_7 = [
        details[f"condition_{i}"]["pass"] for i in range(1, 8)
    ]
    all_pass = all(conditions_1_to_7)

    return all_pass, details
