"""Pool classification with upgrade/downgrade/kickout logic.

Implements SPEC Section 6: transition rules for MLB ↔ 3A pools.
Unlike quality_core.classify_pool() which only checks the current snapshot,
this module considers historical pool membership and consecutive-quarter
criteria for upgrades and downgrades.
"""

from datetime import date

import numpy as np
import pandas as pd

from screener import metrics
from screener.quality_core import (
    passes_mlb_hard_filter,
    passes_3a_hard_filter,
    has_growth_evidence,
)


# ---------------------------------------------------------------------------
# TTM helpers (rolling 4-quarter sums from quarterly data)
# ---------------------------------------------------------------------------

def _quarterly_ttm_fcf_margin(
    q_income: pd.DataFrame, q_cashflow: pd.DataFrame, offset: int = 0
) -> float | None:
    """Compute TTM FCF Margin ending at quarter `offset` from the latest.

    offset=0 → most recent 4 quarters, offset=1 → skip 1 quarter, etc.

    Returns:
        FCF Margin as decimal, or None if insufficient data.
    """
    fcf_row = metrics._safe_row(q_cashflow, "Free Cash Flow")
    rev_row = metrics._safe_row(q_income, "Total Revenue")
    if fcf_row is None or rev_row is None:
        return None

    common = fcf_row.dropna().index.intersection(rev_row.dropna().index)
    # yfinance returns newest-first; sort newest-first explicitly
    common = common.sort_values(ascending=False)
    start = offset
    end = offset + 4
    if len(common) < end:
        return None

    window = common[start:end]
    ttm_fcf = fcf_row[window].astype(float).sum()
    ttm_rev = rev_row[window].astype(float).sum()
    if ttm_rev == 0:
        return None
    return ttm_fcf / ttm_rev


def _quarterly_ttm_roic(
    q_income: pd.DataFrame,
    q_balance: pd.DataFrame,
    offset: int = 0,
    tax_rate: float = 0.21,
) -> float | None:
    """Compute TTM ROIC ending at quarter `offset` from the latest.

    NOPAT = sum of last 4 quarters Operating Income × (1 - tax_rate)
    Invested Capital = latest quarter's (Total Debt + Stockholders Equity)
    """
    op_row = metrics._safe_row(q_income, "Operating Income", "EBIT")
    if op_row is None:
        return None

    valid_cols = op_row.dropna().index.sort_values(ascending=False)
    start = offset
    end = offset + 4
    if len(valid_cols) < end:
        return None

    window = valid_cols[start:end]
    ttm_op = op_row[window].astype(float).sum()
    nopat = ttm_op * (1 - tax_rate)

    # Use the most recent quarter in the window for balance sheet
    bs_col = window[0]
    ic_row = metrics._safe_row(q_balance, "Invested Capital")
    if ic_row is not None and bs_col in ic_row.index and not pd.isna(ic_row[bs_col]):
        invested_cap = float(ic_row[bs_col])
    else:
        debt_row = metrics._safe_row(q_balance, "Total Debt")
        eq_row = metrics._safe_row(
            q_balance, "Stockholders Equity", "Common Stock Equity"
        )
        if debt_row is None or eq_row is None:
            return None
        if bs_col not in debt_row.index or bs_col not in eq_row.index:
            return None
        d = debt_row[bs_col]
        e = eq_row[bs_col]
        if pd.isna(d) or pd.isna(e):
            return None
        invested_cap = float(d) + float(e)

    if invested_cap == 0:
        return None
    return nopat / invested_cap


# ---------------------------------------------------------------------------
# Upgrade: 3A → MLB (SPEC 6.1)
# ---------------------------------------------------------------------------

def check_upgrade_3a_to_mlb(
    ticker_data: dict,
    params: dict,
) -> tuple[bool, dict]:
    """Check if a 3A ticker qualifies for MLB upgrade (SPEC 6.1).

    Requires:
    1. FCF Margin ≥ 10% for 3 consecutive TTM quarters
    2. ROIC ≥ 15% for 3 consecutive TTM quarters
    3. Current period passes remaining MLB hard-filter conditions

    Args:
        ticker_data: Full data dict from yf_loader.
        params: quality_filter block from params.yaml.

    Returns:
        (qualifies: bool, details: dict with per-quarter TTM values)
    """
    q = ticker_data.get("quarterly", {})
    q_inc = q.get("income_stmt", pd.DataFrame())
    q_bs = q.get("balance_sheet", pd.DataFrame())
    q_cf = q.get("cashflow", pd.DataFrame())

    details: dict = {"fcf_ttm": [], "roic_ttm": []}
    quarters_needed = 3

    for offset in range(quarters_needed):
        fcf_m = _quarterly_ttm_fcf_margin(q_inc, q_cf, offset)
        roic_v = _quarterly_ttm_roic(q_inc, q_bs, offset)
        details["fcf_ttm"].append({"offset": offset, "value": fcf_m})
        details["roic_ttm"].append({"offset": offset, "value": roic_v})

    # Check consecutive quarters
    fcf_pass = all(
        d["value"] is not None and d["value"] >= 0.10
        for d in details["fcf_ttm"]
    )
    roic_pass = all(
        d["value"] is not None and d["value"] >= 0.15
        for d in details["roic_ttm"]
    )
    details["fcf_3q_pass"] = fcf_pass
    details["roic_3q_pass"] = roic_pass

    # Check current MLB hard filter
    mlb_pass, mlb_details = passes_mlb_hard_filter(ticker_data, params["mlb"])
    details["current_mlb_hard_filter"] = mlb_pass
    details["mlb_details"] = mlb_details

    qualifies = fcf_pass and roic_pass and mlb_pass
    details["qualifies"] = qualifies
    return qualifies, details


# ---------------------------------------------------------------------------
# Downgrade: MLB → 3A (SPEC 6.2)
# ---------------------------------------------------------------------------

def check_downgrade_mlb_to_3a(
    ticker_data: dict,
    params: dict,
) -> tuple[bool, dict]:
    """Check if an MLB ticker should be downgraded to 3A (SPEC 6.2).

    Triggers (any one):
    1. FCF Margin < 10% for 2 consecutive TTM quarters
    2. ROIC < 15% for 2 consecutive TTM quarters
    3. EPS CAGR estimate revised down > 15% for 2 consecutive quarters
       (Phase 0: skipped due to lack of historical estimate snapshots)

    Returns:
        (should_downgrade: bool, details: dict)
    """
    q = ticker_data.get("quarterly", {})
    q_inc = q.get("income_stmt", pd.DataFrame())
    q_bs = q.get("balance_sheet", pd.DataFrame())
    q_cf = q.get("cashflow", pd.DataFrame())

    details: dict = {"fcf_ttm": [], "roic_ttm": []}
    quarters_needed = 2

    for offset in range(quarters_needed):
        fcf_m = _quarterly_ttm_fcf_margin(q_inc, q_cf, offset)
        roic_v = _quarterly_ttm_roic(q_inc, q_bs, offset)
        details["fcf_ttm"].append({"offset": offset, "value": fcf_m})
        details["roic_ttm"].append({"offset": offset, "value": roic_v})

    fcf_fail = all(
        d["value"] is not None and d["value"] < 0.10
        for d in details["fcf_ttm"]
    )
    roic_fail = all(
        d["value"] is not None and d["value"] < 0.15
        for d in details["roic_ttm"]
    )

    details["fcf_2q_below"] = fcf_fail
    details["roic_2q_below"] = roic_fail
    details["eps_revision_check"] = "skipped (Phase 0: no historical estimate snapshots)"

    reasons = []
    if fcf_fail:
        reasons.append("FCF Margin < 10% for 2 consecutive TTM quarters")
    if roic_fail:
        reasons.append("ROIC < 15% for 2 consecutive TTM quarters")

    should_downgrade = fcf_fail or roic_fail
    details["should_downgrade"] = should_downgrade
    details["reasons"] = reasons
    return should_downgrade, details


# ---------------------------------------------------------------------------
# Kickout (SPEC 6.3)
# ---------------------------------------------------------------------------

def check_kickout(
    ticker_data: dict,
    params: dict,
) -> tuple[bool, dict]:
    """Check if a ticker should be kicked out of the universe (SPEC 6.3).

    Triggers (any one):
    1. EPS CAGR estimate < 15% for 2 consecutive quarters (Phase 0: check current only)
    2. D/E > 1.0
    3. Analyst coverage < 3
    4. Price below MA200 for 3 consecutive months (~63 trading days)

    Returns:
        (should_kickout: bool, details: dict with per-condition results)
    """
    info = ticker_data["info"]
    details: dict = {}
    reasons = []

    # 1. EPS CAGR estimate — Phase 0: check current forward EPS CAGR
    inc = ticker_data["annual"]["income_stmt"]
    eps_ttm = metrics.get_latest_eps_ttm(inc)
    estimates = ticker_data.get("estimates")
    fwd_cagr = metrics.eps_cagr_2y_forward(estimates, eps_ttm)
    eps_kick = fwd_cagr is not None and fwd_cagr < 0.15
    details["eps_cagr_fwd"] = {
        "value": round(fwd_cagr, 4) if fwd_cagr is not None else None,
        "threshold": 0.15,
        "kick": eps_kick,
        "note": "Phase 0: single snapshot, not 2-quarter consecutive",
    }
    if eps_kick:
        reasons.append(f"EPS CAGR fwd {fwd_cagr:.2%} < 15%")

    # 2. D/E > 1.0
    de = metrics.debt_to_equity(info)
    de_kick = de is not None and de > 1.0
    details["debt_to_equity"] = {
        "value": round(de, 4) if de is not None else None,
        "threshold": 1.0,
        "kick": de_kick,
    }
    if de_kick:
        reasons.append(f"D/E {de:.4f} > 1.0")

    # 3. Analyst coverage < 3
    coverage = info.get("numberOfAnalystOpinions")
    cov_kick = coverage is not None and coverage < 3
    details["analyst_coverage"] = {
        "value": coverage,
        "threshold": 3,
        "kick": cov_kick,
    }
    if cov_kick:
        reasons.append(f"Analyst coverage {coverage} < 3")

    # 4. Price below MA200 for 3 consecutive months (~63 trading days)
    prices = ticker_data.get("prices")
    ma200_kick = False
    if prices is not None and not prices.empty and len(prices) >= 200:
        close = prices["Close"]
        ma200 = close.rolling(200).mean()
        recent_63 = (close.iloc[-63:] < ma200.iloc[-63:])
        ma200_kick = bool(recent_63.all())
    details["ma200_breach"] = {
        "consecutive_days_below": int(recent_63.sum()) if prices is not None and not prices.empty and len(prices) >= 200 else None,
        "threshold_days": 63,
        "kick": ma200_kick,
    }
    if ma200_kick:
        reasons.append("Price below MA200 for 63+ consecutive trading days")

    should_kickout = de_kick or cov_kick or ma200_kick
    # eps_kick is informational in Phase 0 (single snapshot, not consecutive)
    details["should_kickout"] = should_kickout
    details["reasons"] = reasons
    return should_kickout, details


# ---------------------------------------------------------------------------
# Approaching MLB (SPEC 6.7)
# ---------------------------------------------------------------------------

def check_approaching_mlb(
    ticker_data: dict,
    params: dict,
) -> tuple[bool, dict]:
    """Check if a 3A ticker is 1 quarter away from MLB upgrade (SPEC 6.7).

    Requires 2 (but not 3) consecutive TTM quarters meeting FCF/ROIC thresholds,
    plus current MLB hard-filter pass.

    Returns:
        (is_approaching: bool, details: dict)
    """
    q = ticker_data.get("quarterly", {})
    q_inc = q.get("income_stmt", pd.DataFrame())
    q_bs = q.get("balance_sheet", pd.DataFrame())
    q_cf = q.get("cashflow", pd.DataFrame())

    details: dict = {"fcf_ttm": [], "roic_ttm": []}

    for offset in range(3):
        fcf_m = _quarterly_ttm_fcf_margin(q_inc, q_cf, offset)
        roic_v = _quarterly_ttm_roic(q_inc, q_bs, offset)
        details["fcf_ttm"].append({"offset": offset, "value": fcf_m})
        details["roic_ttm"].append({"offset": offset, "value": roic_v})

    # Check: exactly 2 most recent quarters pass, but not all 3
    fcf_vals = [d["value"] for d in details["fcf_ttm"]]
    roic_vals = [d["value"] for d in details["roic_ttm"]]

    fcf_2q = (
        fcf_vals[0] is not None and fcf_vals[0] >= 0.10
        and fcf_vals[1] is not None and fcf_vals[1] >= 0.10
    )
    roic_2q = (
        roic_vals[0] is not None and roic_vals[0] >= 0.15
        and roic_vals[1] is not None and roic_vals[1] >= 0.15
    )

    # Already qualifies for full upgrade (3 consecutive)?
    fcf_3q = fcf_2q and fcf_vals[2] is not None and fcf_vals[2] >= 0.10
    roic_3q = roic_2q and roic_vals[2] is not None and roic_vals[2] >= 0.15

    already_qualifies = fcf_3q and roic_3q

    # Current MLB hard filter
    mlb_pass, _ = passes_mlb_hard_filter(ticker_data, params["mlb"])

    is_approaching = fcf_2q and roic_2q and mlb_pass and not already_qualifies
    details["fcf_2q_pass"] = fcf_2q
    details["roic_2q_pass"] = roic_2q
    details["already_qualifies_3q"] = already_qualifies
    details["current_mlb_hard_filter"] = mlb_pass
    details["is_approaching"] = is_approaching
    return is_approaching, details


# ---------------------------------------------------------------------------
# Main entry: determine current pool
# ---------------------------------------------------------------------------

def determine_current_pool(
    ticker_data: dict,
    historical_pools: list[str | None],
    params: dict,
) -> tuple[str | None, dict]:
    """Determine current pool considering history and transition rules.

    This is the monthly-update entry point. It checks kickout first,
    then upgrade/downgrade based on previous pool, then fresh classification.

    Args:
        ticker_data: Full data dict from yf_loader.
        historical_pools: Past pool assignments, oldest → newest.
            Empty list = first run.
        params: quality_filter block from params.yaml.

    Returns:
        (current_pool: 'MLB' | '3A' | None, transition_details: dict)
    """
    prev_pool = historical_pools[-1] if historical_pools else None
    details: dict = {"prev_pool": prev_pool}

    # 1. Check kickout first
    kick, kick_details = check_kickout(ticker_data, params)
    details["kickout_check"] = kick_details
    if kick:
        details["transition_type"] = "kickout"
        details["reason"] = "; ".join(kick_details["reasons"])
        return None, details

    # 2. If previously MLB, check downgrade
    if prev_pool == "MLB":
        down, down_details = check_downgrade_mlb_to_3a(ticker_data, params)
        details["downgrade_check"] = down_details
        if down:
            # Downgraded — check if qualifies for 3A
            aa_pass, aa_details = passes_3a_hard_filter(
                ticker_data, params["triple_a"]
            )
            details["triple_a_recheck"] = aa_details
            if aa_pass:
                growth, growth_details = has_growth_evidence(ticker_data)
                details["growth_evidence"] = growth_details
                if growth:
                    details["transition_type"] = "downgrade"
                    details["reason"] = "; ".join(down_details["reasons"])
                    return "3A", details
            # Doesn't qualify for 3A either
            details["transition_type"] = "kickout"
            details["reason"] = (
                "Downgraded from MLB but doesn't qualify for 3A: "
                + "; ".join(down_details["reasons"])
            )
            return None, details
        else:
            # Still MLB — verify current snapshot still passes
            mlb_pass, mlb_details = passes_mlb_hard_filter(
                ticker_data, params["mlb"]
            )
            details["current_mlb_check"] = mlb_details
            if mlb_pass:
                details["transition_type"] = "stable"
                details["reason"] = "Continues to meet MLB criteria"
                return "MLB", details
            else:
                # Snapshot fails but no consecutive downgrade trigger yet
                details["transition_type"] = "stable"
                details["reason"] = (
                    "Current snapshot fails some MLB criteria but no "
                    "consecutive-quarter downgrade trigger yet"
                )
                return "MLB", details

    # 3. If previously 3A, check upgrade
    if prev_pool == "3A":
        up, up_details = check_upgrade_3a_to_mlb(ticker_data, params)
        details["upgrade_check"] = up_details
        if up:
            details["transition_type"] = "upgrade"
            details["reason"] = "3 consecutive TTM quarters meeting MLB thresholds"
            return "MLB", details

        # Check if still qualifies for 3A
        aa_pass, aa_details = passes_3a_hard_filter(
            ticker_data, params["triple_a"]
        )
        details["triple_a_recheck"] = aa_details
        if aa_pass:
            growth, growth_details = has_growth_evidence(ticker_data)
            details["growth_evidence"] = growth_details
            if growth:
                # Check approaching MLB
                approaching, approach_details = check_approaching_mlb(
                    ticker_data, params
                )
                details["approaching_mlb"] = approach_details
                details["transition_type"] = (
                    "promotion_watch" if approaching else "stable"
                )
                details["reason"] = (
                    "Approaching MLB (2/3 quarters met)"
                    if approaching
                    else "Continues to meet 3A criteria"
                )
                return "3A", details

        # Doesn't qualify for 3A anymore
        details["transition_type"] = "kickout"
        details["reason"] = "No longer meets 3A criteria"
        return None, details

    # 4. No previous pool (first run or was kicked out) — fresh classification
    from screener.quality_core import classify_pool

    pool, classify_details = classify_pool(ticker_data, params)
    details["fresh_classification"] = classify_details
    if pool is not None:
        details["transition_type"] = "entry"
        details["reason"] = f"First-time classification as {pool}"
    else:
        details["transition_type"] = "none"
        details["reason"] = "Does not qualify for any pool"
    return pool, details
