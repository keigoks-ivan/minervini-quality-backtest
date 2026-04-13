"""Quality scoring and moat proxy calculation.

Implements SPEC Section 3.2 (MLB quality bonus, 6 items, max 80 points)
and Section 3.5 (moat proxy score formula).

Key design decisions:
- Decision 13: Proportional scoring (% of available years) instead of absolute counts
- Decision 14: GM trend split into direction + downside volatility
- Decision 15: All volatility metrics use relative values, not absolute pp
"""

import pandas as pd

from screener import metrics


# ---------------------------------------------------------------------------
# GM Trend Score (SPEC 3.2 item C, Decision 14)
# ---------------------------------------------------------------------------

def gm_trend_score(
    annual_gm_series: pd.Series,
) -> tuple[int, dict]:
    """GM trend score: direction (0-5) + downside volatility (0-5).

    Uses relative change rates (not absolute pp) for cross-industry fairness
    (Decision 15).

    Args:
        annual_gm_series: Gross margins sorted oldest-first.

    Returns:
        (total_score: 0-10, breakdown dict)
    """
    gm_oldest = annual_gm_series.iloc[0]
    gm_newest = annual_gm_series.iloc[-1]
    gm_avg = annual_gm_series.mean()

    # === Direction (0-5) ===
    gm_change_pct = (gm_newest - gm_oldest) / gm_oldest if gm_oldest != 0 else 0

    if gm_change_pct >= 0.05:
        direction = 5
    elif gm_change_pct >= 0:
        direction = 3
    elif gm_change_pct >= -0.05:
        direction = 1
    else:
        direction = 0

    # === Downside volatility (0-5) ===
    yoy_changes = annual_gm_series.diff().dropna()
    declines = yoy_changes[yoy_changes < 0].abs()

    max_decline_relative = None
    if len(declines) == 0:
        downside = 5
    else:
        max_decline_relative = float(declines.max() / gm_avg) if gm_avg != 0 else 1.0
        if max_decline_relative < 0.05:
            downside = 4
        elif max_decline_relative < 0.10:
            downside = 2
        else:
            downside = 0

    total = direction + downside
    return total, {
        "direction": direction,
        "downside": downside,
        "gm_change_pct": round(gm_change_pct, 4),
        "max_decline_relative": round(max_decline_relative, 4) if max_decline_relative is not None else None,
    }


# ---------------------------------------------------------------------------
# Moat Proxy Score (SPEC 3.5, updated per Decision 14/15)
# ---------------------------------------------------------------------------

def moat_proxy_score(
    annual_income: pd.DataFrame,
    annual_balance: pd.DataFrame,
) -> tuple[float, dict]:
    """Financial moat proxy score (SPEC 3.5).

    Composite of three sub-scores:
    1. GM resilience (0-4): derived from GM trend score (Decision 14)
    2. ROIC average (0-3): higher avg → higher score
    3. Revenue growth consistency (0-3): proportional (Decision 13)

    Args:
        annual_income: Annual income statement DataFrame.
        annual_balance: Annual balance sheet DataFrame.

    Returns:
        (score: 0-10, breakdown: dict with sub-scores and raw values)
    """
    breakdown: dict = {}

    # 1. GM resilience (0-4) — scaled from GM trend score
    gm_series = metrics.gross_margin_series(annual_income)
    if gm_series is not None and len(gm_series) >= 2:
        gm_sorted = gm_series.sort_index()
        gm_trend_total, gm_trend_details = gm_trend_score(gm_sorted)
        gm_resilience = (gm_trend_total / 10) * 4
    else:
        gm_resilience = 0.0
        gm_trend_details = {}
    breakdown["gm_resilience"] = {
        "score": round(gm_resilience, 2),
        "max": 4,
        "gm_trend_total": gm_trend_total if gm_series is not None and len(gm_series) >= 2 else 0,
        "details": gm_trend_details,
    }

    # 2. ROIC average (0-3) — unchanged
    roic_s = metrics.roic_series(annual_income, annual_balance)
    if roic_s is not None and len(roic_s) >= 1:
        roic_avg = float(roic_s.mean())
        roic_score = max(0.0, min(3.0, roic_avg * 10))
    else:
        roic_avg = None
        roic_score = 0.0
    breakdown["roic_avg"] = {
        "score": round(roic_score, 2),
        "max": 3,
        "roic_avg": round(roic_avg, 4) if roic_avg is not None else None,
    }

    # 3. Revenue growth consistency (0-3) — proportional (Decision 13)
    rev_s = metrics.revenue_series(annual_income)
    if rev_s is not None and len(rev_s) >= 2:
        rev_sorted = rev_s.sort_index()
        rev_growth = rev_sorted.pct_change().dropna()
        positive_years = int((rev_growth > 0).sum())
        available_years = len(rev_growth)
        consistency_score = min(3.0, (positive_years / available_years) * 3.75)
    else:
        positive_years = 0
        available_years = 0
        consistency_score = 0.0
    breakdown["rev_consistency"] = {
        "score": round(consistency_score, 2),
        "max": 3,
        "positive_growth_years": positive_years,
        "available_years": available_years,
    }

    total = gm_resilience + roic_score + consistency_score
    return round(total, 2), breakdown


# ---------------------------------------------------------------------------
# Full Quality Score (SPEC 3.2)
# ---------------------------------------------------------------------------

def calculate_quality_score(ticker_data: dict) -> dict:
    """Calculate full quality bonus score (SPEC 3.2, max 80 points).

    Six scoring items:
    A. Normalized FCF Margin (0-15)
    B. ROIC stability — proportional (0-15, Decision 13)
    C. GM trend — direction + downside (0-10, Decision 14)
    D. Capital intensity (0-10)
    E. Cash covers debt (0-10)
    F. Moat proxy (0-20)

    Args:
        ticker_data: Dict with 'info', 'annual' (containing 'income_stmt',
                     'balance_sheet', 'cashflow').

    Returns:
        Dict with 'total' (0-80) and 'breakdown' per item.
    """
    info = ticker_data["info"]
    annual = ticker_data["annual"]
    inc = annual["income_stmt"]
    bs = annual["balance_sheet"]
    cf = annual["cashflow"]

    breakdown: dict = {}

    # A. Normalized FCF Margin (0-15)
    fcf_row = metrics._safe_row(cf, "Free Cash Flow")
    rev_row = metrics._safe_row(inc, "Total Revenue")
    if fcf_row is not None and rev_row is not None:
        common = fcf_row.dropna().index.intersection(rev_row.dropna().index)
        if len(common) >= 2:
            fcf_vals = fcf_row[common].astype(float)
            rev_vals = rev_row[common].astype(float)
            mask = rev_vals != 0
            fcf_margins = fcf_vals[mask] / rev_vals[mask]
            avg = float(fcf_margins.mean())
            minimum = float(fcf_margins.min())
            if avg >= 0.15 and minimum >= 0.10:
                score_a = 15.0
            else:
                score_a = max(0.0, min(15.0, (avg / 0.15) * 15))
        else:
            avg, minimum = None, None
            score_a = 0.0
    else:
        avg, minimum = None, None
        score_a = 0.0
    breakdown["fcf_5y_normalized"] = {
        "score": round(score_a, 1),
        "max": 15,
        "avg": round(avg, 4) if avg is not None else None,
        "min": round(minimum, 4) if minimum is not None else None,
    }

    # B. ROIC stability (0-15) — proportional (Decision 13)
    roic_s = metrics.roic_series(inc, bs)
    if roic_s is not None and len(roic_s) >= 1:
        years_above = int((roic_s > 0.15).sum())
        total_years = len(roic_s)
        pct_above = years_above / total_years
        if pct_above >= 0.80:
            score_b = 15.0
        elif pct_above >= 0.60:
            score_b = 10.0
        elif pct_above >= 0.40:
            score_b = 5.0
        else:
            score_b = 0.0
    else:
        years_above = 0
        total_years = 0
        pct_above = 0.0
        score_b = 0.0
    breakdown["roic_5y_stability"] = {
        "score": round(score_b, 1),
        "max": 15,
        "years_above_15pct": years_above,
        "total_years": total_years,
        "pct_above": round(pct_above, 4),
    }

    # C. GM trend (0-10) — direction + downside (Decision 14)
    gm_s = metrics.gross_margin_series(inc)
    if gm_s is not None and len(gm_s) >= 2:
        gm_sorted = gm_s.sort_index()
        score_c_int, gm_details = gm_trend_score(gm_sorted)
        score_c = float(score_c_int)
    else:
        score_c = 0.0
        gm_details = {}
    breakdown["gm_5y_trend"] = {
        "score": round(score_c, 1),
        "max": 10,
        **gm_details,
    }

    # D. Capital intensity (0-10)
    capex_avg = metrics.capex_intensity_5y(cf, inc)
    if capex_avg is not None:
        if capex_avg < 0.10:
            score_d = 10.0
        elif capex_avg > 0.20:
            score_d = 0.0
        else:
            score_d = max(0.0, (0.20 - capex_avg) / 0.10 * 10)
    else:
        score_d = 0.0
    breakdown["capex_intensity"] = {
        "score": round(score_d, 1),
        "max": 10,
        "avg_ratio": round(capex_avg, 4) if capex_avg is not None else None,
    }

    # E. Cash covers debt (0-10, binary)
    covers = metrics.cash_covers_debt(info)
    score_e = 10.0 if covers else 0.0
    breakdown["cash_covers_debt"] = {
        "score": round(score_e, 1),
        "max": 10,
        "covers": covers,
    }

    # F. Moat proxy (0-20) = raw 0-10 × 2
    raw_moat, moat_breakdown = moat_proxy_score(inc, bs)
    score_f = min(20.0, raw_moat * 2)
    breakdown["moat_proxy"] = {
        "score": round(score_f, 1),
        "max": 20,
        "raw_score": raw_moat,
        "breakdown": moat_breakdown,
    }

    total = score_a + score_b + score_c + score_d + score_e + score_f
    return {"total": round(total, 1), "breakdown": breakdown}
