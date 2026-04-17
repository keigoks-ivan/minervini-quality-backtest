"""Tests for pool classifier and transition tracking.

Covers upgrade/downgrade/kickout logic with mocked data,
plus integration tests with real NVDA/LULU/GLW data.
"""

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
import yaml

from data.yf_loader import YFinanceSource
from screener.pool_classifier import (
    check_approaching_mlb,
    check_downgrade_mlb_to_3a,
    check_kickout,
    check_upgrade_3a_to_mlb,
    determine_current_pool,
)
from screener.pool_transition import (
    detect_transition,
    generate_monthly_events,
    load_pool_history,
    save_pool_history,
)

TICKERS = ["NVDA", "LULU", "GLW"]
HISTORY_DIR = Path("data/pool_history")


@pytest.fixture(scope="module")
def source() -> YFinanceSource:
    return YFinanceSource()


@pytest.fixture(scope="module")
def params() -> dict:
    with open("configs/params.yaml") as f:
        return yaml.safe_load(f)["quality_filter"]


@pytest.fixture(scope="module")
def ticker_data_map(source: YFinanceSource) -> dict[str, dict]:
    result = {}
    for t in TICKERS:
        result[t] = {
            "info": source.get_info(t),
            "annual": source.get_annual_financials(t),
            "quarterly": source.get_quarterly_financials(t),
            "estimates": source.get_analyst_estimates(t),
            "prices": source.get_price_history(t),
        }
    return result


@pytest.fixture(autouse=True)
def clean_history():
    """Clean pool history dir before and after each test."""
    if HISTORY_DIR.exists():
        shutil.rmtree(HISTORY_DIR)
    yield
    if HISTORY_DIR.exists():
        shutil.rmtree(HISTORY_DIR)


# ---------------------------------------------------------------------------
# Helper: build mock ticker_data with controllable quarterly values
# ---------------------------------------------------------------------------

def _make_mock_ticker_data(
    q_fcf_margins: list[float],
    q_roics: list[float],
    info_overrides: dict | None = None,
    de_raw: float = 20.0,
    analyst_count: int = 30,
    peg: float = 1.5,
    eps_cagr_fwd: float = 0.25,
) -> dict:
    """Build a minimal ticker_data dict with controllable quarterly metrics.

    q_fcf_margins / q_roics: list of TTM values, newest first.
    These are used to construct fake quarterly DataFrames.
    """
    n_quarters = max(len(q_fcf_margins), len(q_roics), 5)
    # Use standard quarter-end dates (Mar/Jun/Sep/Dec), newest first
    dates = pd.date_range(end="2025-12-31", periods=n_quarters, freq="QE")[::-1]

    # Build quarterly income with Revenue=1B and Operating Income to match ROIC
    revenue = 1_000_000_000
    q_rev = pd.Series([revenue] * n_quarters, index=dates, name="Total Revenue")
    # Operating income per quarter to achieve target ROIC
    # TTM ROIC = sum(4Q op_inc) * 0.79 / invested_cap
    # We'll set invested_cap = 10B
    invested_cap = 10_000_000_000
    q_op = []
    for roic in q_roics:
        # roic = 4Q_sum * 0.79 / ic → single Q = roic * ic / (0.79 * 4)
        q_op.append(roic * invested_cap / (0.79 * 4))
    while len(q_op) < n_quarters:
        q_op.append(q_op[-1] if q_op else 0)
    q_op_series = pd.Series(q_op[:n_quarters], index=dates, name="Operating Income")

    q_income = pd.DataFrame(
        {"Total Revenue": q_rev, "Operating Income": q_op_series, "EBIT": q_op_series}
    ).T
    q_income.columns = dates

    # FCF per quarter
    q_fcf = []
    for fm in q_fcf_margins:
        q_fcf.append(fm * revenue)
    while len(q_fcf) < n_quarters:
        q_fcf.append(q_fcf[-1] if q_fcf else 0)
    q_fcf_series = pd.Series(q_fcf[:n_quarters], index=dates, name="Free Cash Flow")
    q_cashflow = pd.DataFrame({"Free Cash Flow": q_fcf_series}).T
    q_cashflow.columns = dates

    # Balance sheet
    q_debt = pd.Series([de_raw / 100 * invested_cap / 2] * n_quarters, index=dates, name="Total Debt")
    q_equity = pd.Series([invested_cap - q_debt.iloc[0]] * n_quarters, index=dates, name="Stockholders Equity")
    q_ic = pd.Series([invested_cap] * n_quarters, index=dates, name="Invested Capital")
    q_balance = pd.DataFrame({
        "Total Debt": q_debt,
        "Stockholders Equity": q_equity,
        "Invested Capital": q_ic,
    }).T
    q_balance.columns = dates

    # Annual — scale to annual totals (4× quarterly for flow items)
    annual_dates = dates[:4]
    a_rev_vals = [revenue * 4] * 4
    a_op_vals = [q_op[i] * 4 for i in range(min(4, len(q_op)))]
    a_fcf_vals = [q_fcf[i] * 4 for i in range(min(4, len(q_fcf)))]
    a_income = pd.DataFrame({
        "Total Revenue": pd.Series(a_rev_vals, index=annual_dates),
        "Operating Income": pd.Series(a_op_vals, index=annual_dates),
        "EBIT": pd.Series(a_op_vals, index=annual_dates),
    }).T
    a_income.columns = annual_dates
    a_balance = q_balance[annual_dates]
    a_cashflow = pd.DataFrame({
        "Free Cash Flow": pd.Series(a_fcf_vals, index=annual_dates),
    }).T
    a_cashflow.columns = annual_dates

    # Diluted EPS (kept for other metrics that may read it)
    eps_latest = 5.0
    eps_row = pd.Series(
        [eps_latest, eps_latest * 0.8, eps_latest * 0.6, eps_latest * 0.5],
        index=dates[:4],
        name="Diluted EPS",
    )
    a_income_with_eps = pd.concat([a_income, eps_row.to_frame().T])

    # Gross Profit
    gp_row = pd.Series([revenue * 0.7] * 4, index=dates[:4], name="Gross Profit")
    a_income_with_eps = pd.concat([a_income_with_eps, gp_row.to_frame().T])

    # Estimates
    est_index = ["0q", "+1q", "0y", "+1y"]
    eps_fy2 = eps_latest * (1 + eps_cagr_fwd) ** 2
    est_data = {
        "avg": [eps_latest * 0.3, eps_latest * 0.35, eps_latest * 1.1, eps_fy2],
        "low": [0] * 4,
        "high": [0] * 4,
        "yearAgoEps": [0] * 4,
        "numberOfAnalysts": [30] * 4,
        "growth": [0.2] * 4,
    }
    estimates = pd.DataFrame(est_data, index=est_index)

    info = {
        "freeCashflow": int(q_fcf_margins[0] * revenue * 4),
        "totalRevenue": revenue * 4,
        "trailingPegRatio": peg,
        "forwardPE": 20.0,
        "debtToEquity": de_raw,
        "totalCash": 5_000_000_000,
        "totalDebt": 2_000_000_000,
        "fiftyTwoWeekHigh": 200.0,
        "fiftyTwoWeekLow": 100.0,
        "numberOfAnalystOpinions": analyst_count,
        "targetMeanPrice": 180.0,
        "marketCap": 100_000_000_000,
        "currentPrice": 180.0,
        "regularMarketPrice": 180.0,
    }
    if info_overrides:
        info.update(info_overrides)

    # Prices (simple uptrend)
    price_dates = pd.date_range(end="2026-04-10", periods=300, freq="B")
    prices = pd.DataFrame({
        "Open": np.linspace(100, 180, 300),
        "High": np.linspace(102, 182, 300),
        "Low": np.linspace(98, 178, 300),
        "Close": np.linspace(100, 180, 300),
        "Volume": [1_000_000] * 300,
    }, index=price_dates)

    return {
        "info": info,
        "annual": {
            "income_stmt": a_income_with_eps,
            "balance_sheet": a_balance,
            "cashflow": a_cashflow,
        },
        "quarterly": {
            "income_stmt": q_income,
            "balance_sheet": q_balance,
            "cashflow": q_cashflow,
        },
        "estimates": estimates,
        "prices": prices,
    }


# ===================================================================
# TestUpgradeLogic
# ===================================================================

class TestUpgradeLogic:

    def test_upgrade_requires_3_consecutive_quarters(self, params: dict) -> None:
        # Need 7+ quarters for 3 TTM windows (each uses 4 quarters).
        # TTM FCF margin = average of 4 per-quarter FCF margins.

        # 2 TTM quarters meeting, 3rd does not → no upgrade
        # offset 0: avg(0.12,0.12,0.12,0.12) = 0.12 ✓
        # offset 1: avg(0.12,0.12,0.12,0.04) = 0.10 ✓ (barely)
        # offset 2: avg(0.12,0.12,0.04,0.04) = 0.08 ✗
        td_2q = _make_mock_ticker_data(
            q_fcf_margins=[0.12, 0.12, 0.12, 0.12, 0.04, 0.04, 0.04, 0.04],
            q_roics=[0.20, 0.20, 0.20, 0.20, 0.05, 0.05, 0.05, 0.05],
        )
        qualifies, details = check_upgrade_3a_to_mlb(td_2q, params)
        assert not qualifies, f"Should not upgrade with only 2Q: {details}"

        # 3 TTM quarters meeting → upgrade
        # offset 0: avg(0.12,0.12,0.12,0.12) = 0.12 ✓
        # offset 1: avg(0.12,0.12,0.12,0.12) = 0.12 ✓
        # offset 2: avg(0.12,0.12,0.12,0.04) = 0.10 ✓
        td_3q = _make_mock_ticker_data(
            q_fcf_margins=[0.12, 0.12, 0.12, 0.12, 0.12, 0.12, 0.04, 0.04],
            q_roics=[0.20, 0.20, 0.20, 0.20, 0.20, 0.20, 0.05, 0.05],
        )
        qualifies, details = check_upgrade_3a_to_mlb(td_3q, params)
        assert qualifies, f"Should upgrade with 3Q: {details}"

    def test_upgrade_also_requires_current_mlb_hard_filter(self, params: dict) -> None:
        # 3Q TTM pass but PEG > 2 via overpriced stock → no upgrade
        td = _make_mock_ticker_data(
            q_fcf_margins=[0.12, 0.11, 0.11, 0.08, 0.07],
            q_roics=[0.18, 0.16, 0.16, 0.10, 0.09],
            info_overrides={"currentPrice": 400, "regularMarketPrice": 400},
        )
        qualifies, details = check_upgrade_3a_to_mlb(td, params)
        assert not qualifies
        assert not details["current_mlb_hard_filter"]


# ===================================================================
# TestDowngradeLogic
# ===================================================================

class TestDowngradeLogic:

    def test_downgrade_on_2_consecutive_quarters_fcf(self, params: dict) -> None:
        # 1 quarter below → no downgrade
        td_1q = _make_mock_ticker_data(
            q_fcf_margins=[0.08, 0.12, 0.11, 0.11, 0.10],
            q_roics=[0.18, 0.18, 0.17, 0.16, 0.16],
        )
        should, details = check_downgrade_mlb_to_3a(td_1q, params)
        assert not should, f"Should not downgrade with only 1Q: {details}"

        # 2 quarters below → downgrade
        td_2q = _make_mock_ticker_data(
            q_fcf_margins=[0.08, 0.07, 0.11, 0.11, 0.10],
            q_roics=[0.18, 0.18, 0.17, 0.16, 0.16],
        )
        should, details = check_downgrade_mlb_to_3a(td_2q, params)
        assert should
        assert details["fcf_2q_below"]


# ===================================================================
# TestKickout
# ===================================================================

class TestKickout:

    def test_kickout_on_high_de(self, params: dict) -> None:
        td = _make_mock_ticker_data(
            q_fcf_margins=[0.15] * 5,
            q_roics=[0.20] * 5,
            de_raw=150.0,  # D/E = 1.5 > 1.0
        )
        should, details = check_kickout(td, params)
        assert should
        assert details["debt_to_equity"]["kick"]

    def test_kickout_on_analyst_coverage(self, params: dict) -> None:
        td = _make_mock_ticker_data(
            q_fcf_margins=[0.15] * 5,
            q_roics=[0.20] * 5,
            analyst_count=2,
        )
        should, details = check_kickout(td, params)
        assert should
        assert details["analyst_coverage"]["kick"]

    def test_kickout_on_ma200_breach(self, params: dict) -> None:
        td = _make_mock_ticker_data(
            q_fcf_margins=[0.15] * 5,
            q_roics=[0.20] * 5,
        )
        # Override prices: 200 days at 200, then 100 days at 50.
        # MA200 at end ≈ (100×200 + 100×50)/200 = 125. Close=50 < 125.
        # All last 63 days have close=50 < MA200 (which stays ~125+).
        price_dates = pd.date_range(end="2026-04-10", periods=300, freq="B")
        closes = np.concatenate([np.full(200, 200.0), np.full(100, 50.0)])
        prices = pd.DataFrame({
            "Open": closes,
            "High": closes + 1,
            "Low": closes - 1,
            "Close": closes,
            "Volume": [1_000_000] * 300,
        }, index=price_dates)
        td["prices"] = prices
        should, details = check_kickout(td, params)
        assert should
        assert details["ma200_breach"]["kick"]


# ===================================================================
# TestTransition
# ===================================================================

class TestTransition:

    def test_detect_upgrade_event(self) -> None:
        event = detect_transition("3A", "MLB", {
            "transition_type": "upgrade",
            "reason": "3 consecutive TTM quarters meeting MLB thresholds",
        })
        assert event is not None
        assert event["type"] == "upgrade"
        assert event["from"] == "3A"
        assert event["to"] == "MLB"
        assert event["notable"] is True

    def test_detect_stable_returns_none(self) -> None:
        event = detect_transition("MLB", "MLB", {
            "transition_type": "stable",
            "reason": "Continues to meet MLB criteria",
        })
        assert event is None

    def test_save_and_load_history(self) -> None:
        save_pool_history("TEST", "2026-01", "3A", {
            "transition_type": "entry",
            "reason": "test",
        })
        save_pool_history("TEST", "2026-02", "3A", {
            "transition_type": "stable",
            "reason": "test",
        })
        save_pool_history("TEST", "2026-03", "MLB", {
            "transition_type": "upgrade",
            "reason": "test upgrade",
        })

        history = load_pool_history("TEST")
        assert history == ["3A", "3A", "MLB"]

    def test_detect_entry_event(self) -> None:
        event = detect_transition(None, "3A", {
            "transition_type": "entry",
            "reason": "First-time classification as 3A",
        })
        assert event is not None
        assert event["type"] == "entry"
        assert event["from"] is None
        assert event["to"] == "3A"


# ===================================================================
# TestIntegration
# ===================================================================

class TestIntegration:

    def test_first_run_produces_entry_or_none(
        self, ticker_data_map: dict, params: dict
    ) -> None:
        """First run with no history → entry, kickout, or none for each ticker."""
        print("\n=== First Run (no history) ===")
        for ticker in TICKERS:
            pool, details = determine_current_pool(
                ticker_data_map[ticker], [], params
            )
            tt = details.get("transition_type")
            print(f"  {ticker}: pool={pool}, transition={tt}, reason={details.get('reason', '')}")
            if pool is not None:
                assert tt == "entry"
            else:
                # Ticker may be kicked out or simply not qualify
                assert tt in ("none", "kickout")

    def test_nvda_stable_mlb_with_history(
        self, ticker_data_map: dict, params: dict
    ) -> None:
        """NVDA with 5 months of MLB history → stable MLB."""
        history = ["MLB"] * 5
        pool, details = determine_current_pool(
            ticker_data_map["NVDA"], history, params
        )
        print(f"\n=== NVDA (5 months MLB history) ===")
        print(f"  pool={pool}, transition={details['transition_type']}")
        print(f"  reason={details.get('reason', '')}")
        assert pool == "MLB"
        assert details["transition_type"] == "stable"

    def test_approaching_mlb_flag(self, params: dict) -> None:
        """Mock ticker with 2 TTM quarters meeting → approaching but not 3."""
        # Need 7+ quarters. 2 TTM windows pass, 3rd does not.
        # offset 0: avg(0.12,0.12,0.12,0.12) = 0.12 ✓
        # offset 1: avg(0.12,0.12,0.12,0.04) = 0.10 ✓ (barely)
        # offset 2: avg(0.12,0.12,0.04,0.04) = 0.08 ✗
        td = _make_mock_ticker_data(
            q_fcf_margins=[0.12, 0.12, 0.12, 0.12, 0.04, 0.04, 0.04, 0.04],
            q_roics=[0.20, 0.20, 0.20, 0.20, 0.05, 0.05, 0.05, 0.05],
        )
        is_approaching, details = check_approaching_mlb(td, params)
        print(f"\n=== Approaching MLB ===")
        print(f"  is_approaching={is_approaching}")
        print(f"  fcf_2q={details['fcf_2q_pass']}, roic_2q={details['roic_2q_pass']}")
        print(f"  already_3q={details['already_qualifies_3q']}")
        assert is_approaching

    def test_full_pipeline_three_tickers(
        self, ticker_data_map: dict, params: dict
    ) -> None:
        """Full pipeline output for human review."""
        print("\n=== Full Pipeline ===")
        for ticker in TICKERS:
            td = ticker_data_map[ticker]

            # Scenario 1: First run
            pool, details = determine_current_pool(td, [], params)
            event = detect_transition(None, pool, details)

            print(f"\n--- {ticker} ---")
            print(f"  Pool: {pool or 'NONE'}")
            print(f"  Transition: {details['transition_type']}")
            print(f"  Reason: {details.get('reason', '')}")
            if event:
                print(f"  Event: {event['type']} ({event['from']} → {event['to']})")

            # Kickout check details
            kick = details.get("kickout_check", {})
            if kick:
                print(f"  Kickout check:")
                for k in ("debt_to_equity", "analyst_coverage", "ma200_breach"):
                    if k in kick:
                        print(f"    {k}: kick={kick[k].get('kick')}, value={kick[k].get('value')}")

            # Approaching MLB (only relevant for 3A)
            if pool == "3A":
                approaching, app_details = check_approaching_mlb(td, params)
                print(f"  Approaching MLB: {approaching}")

            # Save history
            save_pool_history(ticker, "2026-04", pool, details)

        # Verify saved files
        for ticker in TICKERS:
            history = load_pool_history(ticker)
            print(f"\n  {ticker} saved history: {history}")
