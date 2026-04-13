"""MLB and 3A hard filter logic.

Implements SPEC Section 3.1 (MLB), 3.3 (3A), 3.4 (growth evidence).
All thresholds come from configs/params.yaml via the `params` argument.
"""

import pandas as pd

from screener import metrics


def _check(
    name: str, value: float | None, threshold: float, op: str
) -> dict:
    """Build a single filter-check result dict.

    Args:
        name: Metric name for reporting.
        value: Computed metric value (None = data missing).
        threshold: Threshold from params.yaml.
        op: Comparison operator — 'gt' (>) or 'lt' (<).

    Returns:
        Dict with keys: value, threshold, op, pass.
    """
    if value is None:
        return {
            "value": None, "threshold": threshold, "op": op, "pass": False
        }
    if op == "gt":
        passed = value > threshold
    else:  # lt
        passed = value < threshold
    return {"value": round(value, 6), "threshold": threshold, "op": op, "pass": passed}


def _run_hard_filter(
    ticker_data: dict, params: dict
) -> tuple[bool, dict]:
    """Shared logic for both MLB and 3A hard filters.

    Args:
        ticker_data: Dict with keys 'info', 'annual', 'quarterly', 'estimates'.
            'annual'/'quarterly' are dicts with 'income_stmt', 'balance_sheet', 'cashflow'.
        params: One of quality_filter.mlb or quality_filter.triple_a from params.yaml.

    Returns:
        (all_passed: bool, details: dict of per-condition results)
    """
    info = ticker_data["info"]
    annual = ticker_data["annual"]
    estimates = ticker_data["estimates"]

    inc = annual["income_stmt"]
    bs = annual["balance_sheet"]

    details = {}

    # 1. FCF Margin
    details["fcf_margin"] = _check(
        "fcf_margin",
        metrics.fcf_margin(info),
        params["fcf_margin_min"],
        "gt",
    )

    # 2. ROIC
    details["roic"] = _check(
        "roic",
        metrics.roic(inc, bs),
        params["roic_min"],
        "gt",
    )

    # 3. EPS CAGR 2Y Forward
    eps_ttm = metrics.get_latest_eps_ttm(inc)
    details["eps_cagr_2y_fwd"] = _check(
        "eps_cagr_2y_fwd",
        metrics.eps_cagr_2y_forward(estimates, eps_ttm),
        params["eps_cagr_2y_fwd_min"],
        "gt",
    )

    # 4. EPS CAGR 3Y Trailing
    details["eps_cagr_3y_trail"] = _check(
        "eps_cagr_3y_trail",
        metrics.eps_cagr_3y_trailing(inc),
        params["eps_cagr_3y_trail_min"],
        "gt",
    )

    # 5. PEG
    details["peg"] = _check(
        "peg",
        metrics.peg_ratio(info),
        params["peg_max"],
        "lt",
    )

    # 6. D/E
    details["debt_to_equity"] = _check(
        "debt_to_equity",
        metrics.debt_to_equity(info),
        params["debt_to_equity_max"],
        "lt",
    )

    all_passed = all(d["pass"] for d in details.values())
    return all_passed, details


def passes_mlb_hard_filter(
    ticker_data: dict, params: dict
) -> tuple[bool, dict]:
    """Check if ticker passes all 6 MLB hard-filter conditions (SPEC 3.1).

    Args:
        ticker_data: Raw data dict from yf_loader.
        params: quality_filter.mlb block from params.yaml.

    Returns:
        (passed: bool, details: dict with per-condition breakdown)
    """
    return _run_hard_filter(ticker_data, params)


def passes_3a_hard_filter(
    ticker_data: dict, params: dict
) -> tuple[bool, dict]:
    """Check if ticker passes all 6 3A hard-filter conditions (SPEC 3.3).

    Args:
        ticker_data: Raw data dict from yf_loader.
        params: quality_filter.triple_a block from params.yaml.

    Returns:
        (passed: bool, details: dict with per-condition breakdown)
    """
    return _run_hard_filter(ticker_data, params)


def has_growth_evidence(ticker_data: dict) -> tuple[bool, dict]:
    """Check 3A growth evidence requirements (SPEC 3.4).

    At least one must be true:
    1. Last 4 quarters EPS YoY growth is accelerating (each > previous).
    2. Recent 4-quarter TTM revenue YoY growth > 25%.

    Phase 0: if data is insufficient, fall back to checking whether
    the most recent annual revenue growth > 25%.

    Returns:
        (has_evidence: bool, details: dict)
    """
    details: dict = {}
    quarterly = ticker_data.get("quarterly", {})
    q_inc = quarterly.get("income_stmt", pd.DataFrame())

    # --- Evidence 1: EPS YoY acceleration over last 4 quarters ---
    eps_accel = False
    if not q_inc.empty and "Diluted EPS" in q_inc.index:
        eps = q_inc.loc["Diluted EPS"].dropna().sort_index()
        # Need at least 8 quarters (4 recent + 4 year-ago) for YoY
        if len(eps) >= 8:
            recent_4 = eps.iloc[-4:]
            yago_4 = eps.iloc[-8:-4]
            yoy_growth = (
                recent_4.values.astype(float) / yago_4.values.astype(float)
            ) - 1
            # Check if each quarter's YoY is higher than previous
            eps_accel = all(
                yoy_growth[i] > yoy_growth[i - 1]
                for i in range(1, len(yoy_growth))
                if not (pd.isna(yoy_growth[i]) or pd.isna(yoy_growth[i - 1]))
            )
            details["eps_yoy_acceleration"] = {
                "yoy_growth_rates": [round(g, 4) for g in yoy_growth],
                "pass": eps_accel,
            }
        else:
            details["eps_yoy_acceleration"] = {
                "pass": False,
                "reason": f"only {len(eps)} quarterly EPS data points",
            }
    else:
        details["eps_yoy_acceleration"] = {
            "pass": False,
            "reason": "quarterly EPS data unavailable",
        }

    # --- Evidence 2: Revenue TTM YoY > 25% ---
    rev_growth_pass = False
    rev_row = None
    if not q_inc.empty and "Total Revenue" in q_inc.index:
        rev_row = q_inc.loc["Total Revenue"].dropna().sort_index()

    if rev_row is not None and len(rev_row) >= 8:
        recent_ttm = rev_row.iloc[-4:].astype(float).sum()
        yago_ttm = rev_row.iloc[-8:-4].astype(float).sum()
        if yago_ttm > 0:
            rev_yoy = recent_ttm / yago_ttm - 1
            rev_growth_pass = rev_yoy > 0.25
            details["revenue_ttm_yoy"] = {
                "value": round(rev_yoy, 4),
                "threshold": 0.25,
                "pass": rev_growth_pass,
            }
        else:
            details["revenue_ttm_yoy"] = {"pass": False, "reason": "zero base revenue"}
    else:
        # Fallback: use annual revenue growth
        annual = ticker_data.get("annual", {})
        a_inc = annual.get("income_stmt", pd.DataFrame())
        rev_series = metrics.revenue_series(a_inc)
        if rev_series is not None and len(rev_series) >= 2:
            latest = float(rev_series.iloc[0])
            prev = float(rev_series.iloc[1])
            if prev > 0:
                annual_growth = latest / prev - 1
                rev_growth_pass = annual_growth > 0.25
                details["revenue_ttm_yoy"] = {
                    "value": round(annual_growth, 4),
                    "threshold": 0.25,
                    "pass": rev_growth_pass,
                    "fallback": "annual",
                }
            else:
                details["revenue_ttm_yoy"] = {"pass": False, "reason": "zero base revenue"}
        else:
            details["revenue_ttm_yoy"] = {"pass": False, "reason": "insufficient data"}

    has_evidence = eps_accel or rev_growth_pass
    details["overall"] = has_evidence
    return has_evidence, details


def classify_pool(
    ticker_data: dict, params: dict
) -> tuple[str | None, dict]:
    """Classify a ticker into MLB, 3A, or None.

    Checks MLB first (stricter). If MLB fails, checks 3A.
    3A additionally requires growth evidence (SPEC 3.4).

    Args:
        ticker_data: Raw data dict from yf_loader.
        params: Full quality_filter block from params.yaml
                (must contain 'mlb' and 'triple_a' sub-dicts).

    Returns:
        (pool: 'MLB' | '3A' | None, details: dict)
    """
    all_details: dict = {}

    # Try MLB first
    mlb_pass, mlb_details = passes_mlb_hard_filter(
        ticker_data, params["mlb"]
    )
    all_details["mlb"] = {"passed": mlb_pass, "checks": mlb_details}
    if mlb_pass:
        return "MLB", all_details

    # Try 3A
    aa_pass, aa_details = passes_3a_hard_filter(
        ticker_data, params["triple_a"]
    )
    all_details["triple_a"] = {"passed": aa_pass, "checks": aa_details}
    if not aa_pass:
        return None, all_details

    # 3A requires growth evidence
    growth_pass, growth_details = has_growth_evidence(ticker_data)
    all_details["growth_evidence"] = growth_details
    if not growth_pass:
        all_details["triple_a"]["passed"] = False
        all_details["triple_a"]["reason"] = "hard filter passed but no growth evidence"
        return None, all_details

    return "3A", all_details
