"""VCP (Volatility Contraction Pattern) detector — Phase 0 MVP.

Implements SPEC Section 5.1 (simplified VCP) and 5.3 (pivot breakout).
Phase 0 checks three conditions: drawdown, volatility contraction, volume dry-up.
No base count, handle, or shakeout detection (reserved for Phase 2).
"""

import pandas as pd


def detect_vcp_mvp(
    prices: pd.Series,
    volumes: pd.Series,
    lookback_days: int = 60,
    params: dict | None = None,
) -> dict:
    """Simplified VCP detection (SPEC 5.1).

    Three conditions must all be true:
    1. Max drawdown in last `lookback_days` < max_drawdown threshold (25%)
    2. Last 20-day std / last 60-day std < volatility_ratio_threshold (0.7)
    3. Last 10-day avg volume / last 50-day avg volume < volume_ratio_threshold (0.7)

    Args:
        prices: Close price Series.
        volumes: Volume Series (same index as prices).
        lookback_days: Lookback window (default 60).
        params: VCP params from params.yaml. Uses defaults if None.

    Returns:
        Dict with is_vcp, pivot_price, condition details, etc.
    """
    max_dd_thresh = 0.25
    vol_ratio_thresh = 0.7
    volume_ratio_thresh = 0.7
    if params:
        max_dd_thresh = params.get("max_drawdown", max_dd_thresh)
        vol_ratio_thresh = params.get("volatility_ratio_threshold", vol_ratio_thresh)
        volume_ratio_thresh = params.get("volume_ratio_threshold", volume_ratio_thresh)
        lookback_days = params.get("lookback_days", lookback_days)

    if len(prices) < lookback_days or len(volumes) < 50:
        return {
            "is_vcp": False,
            "error": f"insufficient data ({len(prices)} days, need {lookback_days})",
            "pivot_price": None,
            "max_drawdown": None,
            "volatility_ratio": None,
            "volume_ratio": None,
            "conditions": {
                "drawdown_ok": False,
                "volatility_ok": False,
                "volume_ok": False,
            },
            "current_price": float(prices.iloc[-1]) if len(prices) > 0 else None,
            "distance_to_pivot_pct": None,
        }

    recent = prices.iloc[-lookback_days:]

    # 1. Max drawdown
    peak = recent.max()
    trough = recent.min()
    max_drawdown = float((peak - trough) / peak) if peak != 0 else 0
    drawdown_ok = max_drawdown < max_dd_thresh

    # 2. Volatility contraction
    std_20 = float(prices.iloc[-20:].std())
    std_60 = float(prices.iloc[-60:].std())
    volatility_ratio = std_20 / std_60 if std_60 != 0 else float("inf")
    volatility_ok = volatility_ratio < vol_ratio_thresh

    # 3. Volume dry-up
    vol_10 = float(volumes.iloc[-10:].mean())
    vol_50 = float(volumes.iloc[-50:].mean())
    volume_ratio = vol_10 / vol_50 if vol_50 != 0 else float("inf")
    volume_ok = volume_ratio < volume_ratio_thresh

    # Pivot = last 20-day high
    pivot_price = float(prices.iloc[-20:].max())
    current_price = float(prices.iloc[-1])
    dist_to_pivot = (current_price - pivot_price) / pivot_price if pivot_price != 0 else 0

    is_vcp = drawdown_ok and volatility_ok and volume_ok

    return {
        "is_vcp": is_vcp,
        "pivot_price": round(pivot_price, 2),
        "max_drawdown": round(max_drawdown, 4),
        "volatility_ratio": round(volatility_ratio, 4),
        "volume_ratio": round(volume_ratio, 4),
        "conditions": {
            "drawdown_ok": drawdown_ok,
            "volatility_ok": volatility_ok,
            "volume_ok": volume_ok,
        },
        "current_price": round(current_price, 2),
        "distance_to_pivot_pct": round(dist_to_pivot, 4),
    }


def detect_pivot_breakout(
    prices: pd.Series,
    volumes: pd.Series,
    pivot_price: float,
    params: dict,
    pool: str,
) -> dict:
    """Confirm a pivot breakout on the latest day (SPEC 5.3).

    Two conditions:
    1. Today's close > pivot × 1.001
    2. Today's volume > 50MA volume × breakout_multiplier (MLB:1.4, 3A:1.5)

    Args:
        prices: Close price Series.
        volumes: Volume Series.
        pivot_price: Pivot price from VCP detection.
        params: technical_filter block from params.yaml.
        pool: 'MLB' or '3A'.

    Returns:
        Dict with is_breakout and condition details.
    """
    if pool == "MLB":
        multiplier = params["mlb"]["volume_breakout_multiplier"]
    else:
        multiplier = params["triple_a"]["volume_breakout_multiplier"]

    close_today = float(prices.iloc[-1])
    volume_today = float(volumes.iloc[-1])
    volume_50ma = float(volumes.iloc[-50:].mean()) if len(volumes) >= 50 else float(volumes.mean())

    pivot_threshold = pivot_price * 1.001
    price_ok = close_today > pivot_threshold

    volume_multiple = volume_today / volume_50ma if volume_50ma != 0 else 0
    volume_ok = volume_multiple > multiplier

    return {
        "is_breakout": price_ok and volume_ok,
        "close_today": round(close_today, 2),
        "pivot_threshold": round(pivot_threshold, 2),
        "price_threshold_met": price_ok,
        "volume_today": int(volume_today),
        "volume_50ma": round(volume_50ma, 0),
        "volume_multiple": round(volume_multiple, 2),
        "volume_multiplier_required": multiplier,
        "volume_threshold_met": volume_ok,
    }
