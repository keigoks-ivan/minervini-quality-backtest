"""Quality scoring and moat proxy calculation.

Implements SPEC Section 3.2 (MLB quality bonus, 6 items, max 80 points)
and Section 3.5 (moat proxy score formula).
"""

import numpy as np
import pandas as pd

from screener import metrics


def moat_proxy_score(
    annual_income: pd.DataFrame,
    annual_balance: pd.DataFrame,
) -> tuple[float, dict]:
    """Financial moat proxy score (SPEC 3.5).

    Composite of three sub-scores:
    1. GM stability (0-4): lower std → higher score
    2. 5Y ROIC average (0-3): higher avg → higher score
    3. Revenue growth consistency (0-3): more positive-growth years → higher

    Args:
        annual_income: Annual income statement DataFrame.
        annual_balance: Annual balance sheet DataFrame.

    Returns:
        (score: 0-10, breakdown: dict with sub-scores and raw values)
    """
    breakdown: dict = {}

    # 1. GM stability (0-4)
    gm_series = metrics.gross_margin_series(annual_income)
    if gm_series is not None and len(gm_series) >= 2:
        gm_std = gm_series.std()
        gm_score = max(0.0, min(4.0, 4.0 - gm_std * 20))
    else:
        gm_std = None
        gm_score = 0.0
    breakdown["gm_stability"] = {
        "score": round(gm_score, 2),
        "max": 4,
        "gm_std": round(gm_std, 4) if gm_std is not None else None,
    }

    # 2. 5Y ROIC average (0-3)
    roic_s = metrics.roic_series(annual_income, annual_balance)
    if roic_s is not None and len(roic_s) >= 1:
        roic_avg = roic_s.mean()
        roic_score = max(0.0, min(3.0, roic_avg * 10))
    else:
        roic_avg = None
        roic_score = 0.0
    breakdown["roic_avg"] = {
        "score": round(roic_score, 2),
        "max": 3,
        "roic_avg": round(roic_avg, 4) if roic_avg is not None else None,
    }

    # 3. Revenue growth consistency (0-3)
    rev_s = metrics.revenue_series(annual_income)
    if rev_s is not None and len(rev_s) >= 2:
        # rev_s is sorted newest-first, pct_change needs oldest-first
        rev_sorted = rev_s.sort_index()
        rev_growth = rev_sorted.pct_change().dropna()
        positive_years = int((rev_growth > 0).sum())
        consistency_score = min(3.0, positive_years * 0.75)
    else:
        positive_years = 0
        consistency_score = 0.0
    breakdown["rev_consistency"] = {
        "score": round(consistency_score, 2),
        "max": 3,
        "positive_growth_years": positive_years,
    }

    total = gm_score + roic_score + consistency_score
    return round(total, 2), breakdown


def calculate_quality_score(ticker_data: dict) -> dict:
    """Calculate full quality bonus score (SPEC 3.2, max 80 points).

    Six scoring items:
    A. 5Y normalized FCF Margin (0-15)
    B. 5Y ROIC stability (0-15)
    C. 5Y gross margin trend (0-10)
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

    # A. 5Y normalized FCF Margin (0-15)
    # Full score: 5Y mean > 15% AND single-year min > 10%
    fcf_row = metrics._safe_row(cf, "Free Cash Flow")
    rev_row = metrics._safe_row(inc, "Total Revenue")
    if fcf_row is not None and rev_row is not None:
        common = fcf_row.dropna().index.intersection(rev_row.dropna().index)
        if len(common) >= 2:
            fcf_vals = fcf_row[common].astype(float)
            rev_vals = rev_row[common].astype(float)
            mask = rev_vals != 0
            fcf_margins = fcf_vals[mask] / rev_vals[mask]
            avg = fcf_margins.mean()
            minimum = fcf_margins.min()
            if avg >= 0.15 and minimum >= 0.10:
                score_a = 15.0
            else:
                # Proportional: based on avg relative to 15% target
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

    # B. 5Y ROIC stability (0-15)
    # 4/5 years > 15% → 15, 3/5 → 10, 2/5 → 5
    roic_s = metrics.roic_series(inc, bs)
    if roic_s is not None and len(roic_s) >= 1:
        years_above = int((roic_s > 0.15).sum())
        total_years = len(roic_s)
        if years_above >= 4:
            score_b = 15.0
        elif years_above >= 3:
            score_b = 10.0
        elif years_above >= 2:
            score_b = 5.0
        else:
            score_b = 0.0
    else:
        years_above = 0
        total_years = 0
        score_b = 0.0
    breakdown["roic_5y_stability"] = {
        "score": round(score_b, 1),
        "max": 15,
        "years_above_15pct": years_above,
        "total_years": total_years,
    }

    # C. 5Y gross margin trend (0-10)
    # 3/5 years GM not declining → 10, 2/5 → 5
    gm_s = metrics.gross_margin_series(inc)
    if gm_s is not None and len(gm_s) >= 2:
        gm_sorted = gm_s.sort_index()
        gm_changes = gm_sorted.diff().dropna()
        years_not_declining = int((gm_changes >= 0).sum())
        if years_not_declining >= 3:
            score_c = 10.0
        elif years_not_declining >= 2:
            score_c = 5.0
        else:
            score_c = 0.0
    else:
        years_not_declining = 0
        score_c = 0.0
    breakdown["gm_5y_trend"] = {
        "score": round(score_c, 1),
        "max": 10,
        "years_not_declining": years_not_declining,
    }

    # D. Capital intensity (0-10)
    # < 10% → 10, linear decay to 20% → 0
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
