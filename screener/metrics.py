"""Derived metric calculations for QGM quality screening.

Pure computation — no filtering logic, no side effects.
Each function takes raw data from yf_loader and returns a numeric value.
See SPEC 2.4 for formula definitions.
"""

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_get(d: dict, *keys, default=None):
    """Try multiple keys in order, return the first non-None value."""
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return default


def _safe_row(df: pd.DataFrame, *row_names) -> pd.Series | None:
    """Try multiple row names, return first found Series or None."""
    for name in row_names:
        if name in df.index:
            return df.loc[name]
    return None


# ---------------------------------------------------------------------------
# 1. FCF Margin
# ---------------------------------------------------------------------------

def fcf_margin(info: dict) -> float | None:
    """Current FCF Margin = freeCashflow / totalRevenue.

    Args:
        info: Ticker.info dict from yfinance.

    Returns:
        FCF margin as decimal (e.g. 0.27), or None if data missing.
    """
    fcf = info.get("freeCashflow")
    rev = info.get("totalRevenue")
    if fcf is None or rev is None or rev == 0:
        return None
    return fcf / rev


# ---------------------------------------------------------------------------
# 2. ROIC
# ---------------------------------------------------------------------------

def roic(
    income_stmt: pd.DataFrame,
    balance_sheet: pd.DataFrame,
    tax_rate: float = 0.21,
) -> float | None:
    """Current ROIC = NOPAT / Invested Capital.

    Uses the most recent fiscal period (first column).
    NOPAT = Operating Income × (1 - tax_rate)
    Invested Capital = Total Debt + Stockholders Equity
    Falls back to Invested Capital row if available.

    Args:
        income_stmt: Annual income statement DataFrame.
        balance_sheet: Annual balance sheet DataFrame.
        tax_rate: Corporate tax rate (default 21%).

    Returns:
        ROIC as decimal (e.g. 0.34), or None if data missing.
    """
    if income_stmt.empty or balance_sheet.empty:
        return None

    latest_col = income_stmt.columns[0]

    op_income_row = _safe_row(income_stmt, "Operating Income", "EBIT")
    if op_income_row is None:
        return None
    op_income = op_income_row[latest_col]

    if pd.isna(op_income):
        return None

    nopat = op_income * (1 - tax_rate)

    # Try Invested Capital directly, else Total Debt + Stockholders Equity
    bs_col = balance_sheet.columns[0]
    invested_cap = None

    ic_row = _safe_row(balance_sheet, "Invested Capital")
    if ic_row is not None and not pd.isna(ic_row[bs_col]):
        invested_cap = ic_row[bs_col]

    if invested_cap is None:
        debt_row = _safe_row(balance_sheet, "Total Debt")
        equity_row = _safe_row(
            balance_sheet, "Stockholders Equity", "Common Stock Equity"
        )
        if debt_row is not None and equity_row is not None:
            debt = debt_row[bs_col]
            equity = equity_row[bs_col]
            if not pd.isna(debt) and not pd.isna(equity):
                invested_cap = debt + equity

    if invested_cap is None or invested_cap == 0:
        return None

    return nopat / invested_cap


# ---------------------------------------------------------------------------
# 3. EPS CAGR 2Y Forward
# ---------------------------------------------------------------------------

def eps_cagr_2y_forward(
    estimates: pd.DataFrame, latest_eps_ttm: float
) -> float | None:
    """Forward 2-year EPS CAGR = (eps_fy2 / eps_ttm)^(1/2) - 1.

    yfinance estimates index: ['0q', '+1q', '0y', '+1y']
    '0y' = current FY estimate, '+1y' = next FY estimate (= FY+2).

    Args:
        estimates: earnings_estimate DataFrame from yfinance.
        latest_eps_ttm: Most recent trailing 12-month diluted EPS.

    Returns:
        CAGR as decimal (e.g. 0.35 = 35%), or None if data missing
        or if TTM EPS is non-positive.
    """
    if estimates is None or estimates.empty:
        return None
    if latest_eps_ttm is None or latest_eps_ttm <= 0:
        return None

    if "+1y" not in estimates.index:
        return None

    eps_fy2 = estimates.loc["+1y", "avg"]
    if pd.isna(eps_fy2) or eps_fy2 <= 0:
        return None

    return (eps_fy2 / latest_eps_ttm) ** (1 / 2) - 1


# ---------------------------------------------------------------------------
# 4. EPS CAGR 3Y Trailing
# ---------------------------------------------------------------------------

def eps_cagr_3y_trailing(annual_income: pd.DataFrame) -> float | None:
    """Trailing 3-year EPS CAGR = (eps_latest / eps_3y_ago)^(1/3) - 1.

    Takes the most recent and the 4th column (3 years back) of Diluted EPS.
    Columns are sorted newest-first by yfinance.

    Args:
        annual_income: Annual income statement DataFrame.

    Returns:
        CAGR as decimal, or None if EPS data missing or base EPS <= 0.
    """
    eps_row = _safe_row(annual_income, "Diluted EPS")
    if eps_row is None:
        return None

    # Need at least 4 periods (latest + 3 years back)
    valid = eps_row.dropna()
    if len(valid) < 4:
        return None

    eps_latest = valid.iloc[0]
    eps_3y_ago = valid.iloc[3]

    if pd.isna(eps_latest) or pd.isna(eps_3y_ago):
        return None
    if eps_3y_ago <= 0:
        return None

    return (eps_latest / eps_3y_ago) ** (1 / 3) - 1


# ---------------------------------------------------------------------------
# 5. Gross Margin
# ---------------------------------------------------------------------------

def gross_margin_current(income_stmt: pd.DataFrame) -> float | None:
    """Current gross margin = Gross Profit / Total Revenue.

    Uses the most recent fiscal period (first column).

    Returns:
        Gross margin as decimal (e.g. 0.75), or None if data missing.
    """
    if income_stmt.empty:
        return None

    col = income_stmt.columns[0]
    gp_row = _safe_row(income_stmt, "Gross Profit")
    rev_row = _safe_row(income_stmt, "Total Revenue")

    if gp_row is None or rev_row is None:
        return None

    gp = gp_row[col]
    rev = rev_row[col]
    if pd.isna(gp) or pd.isna(rev) or rev == 0:
        return None
    return gp / rev


# ---------------------------------------------------------------------------
# 6. PEG Ratio
# ---------------------------------------------------------------------------

def get_fy1_fy2_eps(estimates: "pd.DataFrame | None") -> tuple[float | None, float | None]:
    """Extract FY1 and FY2 consensus EPS from yfinance estimates.

    Returns:
        (fy1_eps, fy2_eps) — either can be None if data missing.
    """
    if estimates is None or estimates.empty:
        return None, None
    fy1 = None
    fy2 = None
    if "0y" in estimates.index:
        v = estimates.loc["0y", "avg"]
        if not pd.isna(v):
            fy1 = float(v)
    if "+1y" in estimates.index:
        v = estimates.loc["+1y", "avg"]
        if not pd.isna(v):
            fy2 = float(v)
    return fy1, fy2


def peg_ratio_fy2(
    price: float | None,
    fy2_eps: float | None,
    growth_rate: float | None,
) -> float | None:
    """PEG computed from FY2 forward P/E.

    PEG = (price / fy2_eps) / (growth_rate × 100)

    Args:
        price: Current stock price.
        fy2_eps: Next fiscal year consensus EPS estimate.
        growth_rate: Forward EPS growth rate as decimal (e.g., 0.15 for 15%).

    Returns:
        PEG ratio as float, or None if any input is missing/invalid.
    """
    if (
        price is None
        or fy2_eps is None
        or growth_rate is None
        or price <= 0
        or fy2_eps <= 0
        or growth_rate <= 0
    ):
        return None
    fy2_pe = price / fy2_eps
    return fy2_pe / (growth_rate * 100)


def peg_ratio(info: dict, growth_rate: float | None = None) -> float | None:
    """Legacy PEG ratio from info snapshot (kept for backward compat).

    Prefers trailingPegRatio. Falls back to forwardPE / (growth_rate × 100).
    """
    peg = info.get("trailingPegRatio")
    if peg is not None and not (isinstance(peg, float) and np.isnan(peg)):
        return peg
    fwd_pe = info.get("forwardPE")
    if (
        fwd_pe is not None
        and growth_rate is not None
        and growth_rate > 0
        and not (isinstance(fwd_pe, float) and np.isnan(fwd_pe))
    ):
        return fwd_pe / (growth_rate * 100)
    return None


# ---------------------------------------------------------------------------
# 7. Debt to Equity
# ---------------------------------------------------------------------------

def debt_to_equity(info: dict) -> float | None:
    """D/E ratio, converted from yfinance percentage to decimal.

    yfinance returns debtToEquity as percentage (e.g. 7.26 = 7.26%).
    We divide by 100 so downstream can compare directly to 0.7 threshold.

    Returns:
        D/E as decimal (e.g. 0.0726), or None if missing.
    """
    raw = info.get("debtToEquity")
    if raw is None:
        return None
    return raw / 100


# ---------------------------------------------------------------------------
# 8. Cash Covers Debt
# ---------------------------------------------------------------------------

def cash_covers_debt(info: dict) -> bool | None:
    """Whether totalCash > totalDebt.

    Returns:
        True if cash exceeds debt, False otherwise, None if data missing.
    """
    cash = info.get("totalCash")
    debt = info.get("totalDebt")
    if cash is None or debt is None:
        return None
    return cash > debt


# ---------------------------------------------------------------------------
# 9. Distance from 52-Week High
# ---------------------------------------------------------------------------

def dist_from_52w_high(info: dict) -> float | None:
    """(currentPrice - 52wHigh) / 52wHigh. Always <= 0.

    Returns:
        Negative decimal (e.g. -0.12 = 12% below high), or None.
    """
    price = _safe_get(info, "currentPrice", "regularMarketPrice")
    high = info.get("fiftyTwoWeekHigh")
    if price is None or high is None or high == 0:
        return None
    return (price - high) / high


# ---------------------------------------------------------------------------
# 10. CapEx Intensity 5Y Average
# ---------------------------------------------------------------------------

def capex_intensity_5y(
    annual_cashflow: pd.DataFrame, annual_income: pd.DataFrame
) -> float | None:
    """5-year average abs(CapEx) / Revenue.

    Note: yfinance Capital Expenditure is typically negative.

    Returns:
        Average ratio as decimal (e.g. 0.08), or None if data insufficient.
    """
    capex_row = _safe_row(annual_cashflow, "Capital Expenditure")
    rev_row = _safe_row(annual_income, "Total Revenue")

    if capex_row is None or rev_row is None:
        return None

    # Align on common columns
    common_cols = capex_row.dropna().index.intersection(rev_row.dropna().index)
    if len(common_cols) < 2:
        return None

    capex = capex_row[common_cols].astype(float)
    rev = rev_row[common_cols].astype(float)

    # Exclude zero-revenue years
    mask = rev != 0
    if mask.sum() == 0:
        return None

    ratios = capex[mask].abs() / rev[mask]
    return ratios.mean()


# ---------------------------------------------------------------------------
# Compound helpers for quality_core
# ---------------------------------------------------------------------------

def get_latest_eps_ttm(annual_income: pd.DataFrame) -> float | None:
    """Get the most recent Diluted EPS from annual income statement."""
    eps_row = _safe_row(annual_income, "Diluted EPS")
    if eps_row is None:
        return None
    valid = eps_row.dropna()
    if len(valid) == 0:
        return None
    return valid.iloc[0]


def gross_margin_series(annual_income: pd.DataFrame) -> pd.Series | None:
    """Return a Series of gross margins across all available fiscal years."""
    gp_row = _safe_row(annual_income, "Gross Profit")
    rev_row = _safe_row(annual_income, "Total Revenue")
    if gp_row is None or rev_row is None:
        return None
    common = gp_row.dropna().index.intersection(rev_row.dropna().index)
    if len(common) == 0:
        return None
    gp = gp_row[common].astype(float)
    rev = rev_row[common].astype(float)
    mask = rev != 0
    return (gp[mask] / rev[mask])


def roic_series(
    annual_income: pd.DataFrame,
    annual_balance: pd.DataFrame,
    tax_rate: float = 0.21,
) -> pd.Series | None:
    """Return a Series of ROIC values across available fiscal years."""
    op_row = _safe_row(annual_income, "Operating Income", "EBIT")
    if op_row is None:
        return None

    # Try Invested Capital, else Debt + Equity
    ic_row = _safe_row(annual_balance, "Invested Capital")
    if ic_row is None:
        debt_row = _safe_row(annual_balance, "Total Debt")
        eq_row = _safe_row(
            annual_balance, "Stockholders Equity", "Common Stock Equity"
        )
        if debt_row is None or eq_row is None:
            return None
        common = (
            op_row.dropna().index
            .intersection(debt_row.dropna().index)
            .intersection(eq_row.dropna().index)
        )
        if len(common) == 0:
            return None
        nopat = op_row[common].astype(float) * (1 - tax_rate)
        ic = debt_row[common].astype(float) + eq_row[common].astype(float)
    else:
        common = op_row.dropna().index.intersection(ic_row.dropna().index)
        if len(common) == 0:
            return None
        nopat = op_row[common].astype(float) * (1 - tax_rate)
        ic = ic_row[common].astype(float)

    mask = ic != 0
    if mask.sum() == 0:
        return None
    return nopat[mask] / ic[mask]


def revenue_series(annual_income: pd.DataFrame) -> pd.Series | None:
    """Return Total Revenue across available fiscal years."""
    rev_row = _safe_row(annual_income, "Total Revenue")
    if rev_row is None:
        return None
    valid = rev_row.dropna().astype(float)
    return valid if len(valid) > 0 else None


# ---------------------------------------------------------------------------
# Net Debt / EBITDA (Decision 19)
# ---------------------------------------------------------------------------

def net_debt_to_ebitda(info: dict, quarterly_income: pd.DataFrame) -> float | None:
    """Net Debt / TTM EBITDA.

    Net Debt = Total Debt - Total Cash. Can be negative (cash > debt).
    EBITDA from TTM (last 4 quarters EBITDA summed).

    Returns:
        Ratio as float (can be negative if net-cash), or None if data missing.
    """
    total_debt = info.get("totalDebt")
    total_cash = info.get("totalCash")
    if total_debt is None or total_cash is None:
        return None

    net_debt = total_debt - total_cash

    # TTM EBITDA from quarterly income
    ebitda_row = _safe_row(quarterly_income, "EBITDA")
    if ebitda_row is None:
        # Fallback: Operating Income + D&A
        op_row = _safe_row(quarterly_income, "Operating Income", "EBIT")
        da_row = _safe_row(
            quarterly_income,
            "Reconciled Depreciation",
            "Depreciation And Amortization",
            "Depreciation Amortization Depletion",
        )
        if op_row is None:
            return None
        valid_cols = op_row.dropna().index.sort_values(ascending=False)
        if len(valid_cols) < 4:
            return None
        ttm_cols = valid_cols[:4]
        ttm_op = op_row[ttm_cols].astype(float).sum()
        ttm_da = 0
        if da_row is not None:
            da_vals = da_row.reindex(ttm_cols).dropna()
            ttm_da = da_vals.astype(float).sum() if len(da_vals) > 0 else 0
        ebitda = ttm_op + ttm_da
    else:
        valid_cols = ebitda_row.dropna().index.sort_values(ascending=False)
        if len(valid_cols) < 4:
            return None
        ebitda = ebitda_row[valid_cols[:4]].astype(float).sum()

    if ebitda <= 0:
        return None  # Negative EBITDA makes the ratio meaningless

    return net_debt / ebitda


# ---------------------------------------------------------------------------
# Revenue CAGR 3Y (for turnaround path, Decision 18)
# ---------------------------------------------------------------------------

def revenue_cagr_3y(annual_income: pd.DataFrame) -> float | None:
    """Trailing 3-year Revenue CAGR.

    Returns:
        CAGR as decimal, or None if data insufficient.
    """
    rev_row = _safe_row(annual_income, "Total Revenue")
    if rev_row is None:
        return None
    valid = rev_row.dropna()
    if len(valid) < 4:
        return None
    latest = float(valid.iloc[0])
    three_ago = float(valid.iloc[3])
    if three_ago <= 0:
        return None
    return (latest / three_ago) ** (1 / 3) - 1
