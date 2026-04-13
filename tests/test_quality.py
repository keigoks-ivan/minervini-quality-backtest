"""Tests for quality metrics, hard filters, and scoring.

Uses real yfinance data for NVDA, LULU, GLW + F (Ford, high D/E).
"""

import json

import pytest
import yaml

from data.yf_loader import YFinanceSource
from screener import metrics
from screener.quality_core import (
    classify_pool,
    has_growth_evidence,
    passes_mlb_hard_filter,
)
from screener.quality_score import (
    calculate_quality_score,
    gm_trend_score,
    moat_proxy_score,
)

TICKERS = ["NVDA", "LULU", "GLW"]


@pytest.fixture(scope="module")
def source() -> YFinanceSource:
    return YFinanceSource()


@pytest.fixture(scope="module")
def params() -> dict:
    with open("configs/params.yaml") as f:
        return yaml.safe_load(f)["quality_filter"]


@pytest.fixture(scope="module")
def ticker_data_map(source: YFinanceSource) -> dict[str, dict]:
    """Load all data for test tickers (cached from prior test run)."""
    result = {}
    for t in TICKERS + ["F"]:
        result[t] = {
            "info": source.get_info(t),
            "annual": source.get_annual_financials(t),
            "quarterly": source.get_quarterly_financials(t),
            "estimates": source.get_analyst_estimates(t),
            "prices": source.get_price_history(t),
        }
    return result


# ===================================================================
# TestMetrics
# ===================================================================

class TestMetrics:

    def test_fcf_margin_nvda_reasonable(
        self, ticker_data_map: dict
    ) -> None:
        val = metrics.fcf_margin(ticker_data_map["NVDA"]["info"])
        assert val is not None
        assert 0.10 < val < 0.60, f"NVDA FCF Margin = {val}"

    def test_roic_nvda_reasonable(self, ticker_data_map: dict) -> None:
        data = ticker_data_map["NVDA"]["annual"]
        val = metrics.roic(data["income_stmt"], data["balance_sheet"])
        assert val is not None
        assert val > 0.25, f"NVDA ROIC = {val}"

    def test_eps_cagr_fwd_nvda_reasonable(
        self, ticker_data_map: dict
    ) -> None:
        data = ticker_data_map["NVDA"]
        eps_ttm = metrics.get_latest_eps_ttm(
            data["annual"]["income_stmt"]
        )
        val = metrics.eps_cagr_2y_forward(data["estimates"], eps_ttm)
        assert val is not None
        assert val > 0.10, f"NVDA EPS CAGR 2Y fwd = {val}"

    def test_debt_to_equity_nvda_low(
        self, ticker_data_map: dict
    ) -> None:
        val = metrics.debt_to_equity(ticker_data_map["NVDA"]["info"])
        assert val is not None
        assert val < 0.15, f"NVDA D/E = {val}"

    @pytest.mark.parametrize("ticker", TICKERS)
    def test_dist_from_52w_high_in_range(
        self, ticker_data_map: dict, ticker: str
    ) -> None:
        val = metrics.dist_from_52w_high(ticker_data_map[ticker]["info"])
        assert val is not None
        assert -1.0 <= val <= 0.0, f"{ticker} dist_52w_high = {val}"


# ===================================================================
# TestQualityCore
# ===================================================================

class TestQualityCore:

    def test_nvda_likely_passes_mlb(
        self, ticker_data_map: dict, params: dict
    ) -> None:
        passed, details = passes_mlb_hard_filter(
            ticker_data_map["NVDA"], params["mlb"]
        )
        # Print details for human inspection regardless of pass/fail
        print("\n=== NVDA MLB Hard Filter ===")
        for k, v in details.items():
            status = "PASS" if v["pass"] else "FAIL"
            print(f"  {k}: {v['value']} {v['op']} {v['threshold']} → {status}")
        # NVDA should pass (high quality + high growth)
        assert passed, f"NVDA failed MLB. Details: {details}"

    def test_classify_all_three(
        self, ticker_data_map: dict, params: dict
    ) -> None:
        print("\n=== Pool Classification ===")
        for ticker in TICKERS:
            pool, details = classify_pool(
                ticker_data_map[ticker], params
            )
            print(f"\n--- {ticker}: {pool or 'NONE'} ---")
            for pool_name in ("mlb", "triple_a"):
                if pool_name in details:
                    d = details[pool_name]
                    print(f"  {pool_name} passed: {d['passed']}")
                    for k, v in d["checks"].items():
                        status = "PASS" if v["pass"] else "FAIL"
                        print(f"    {k}: {v['value']} → {status}")
            if "growth_evidence" in details:
                print(f"  growth_evidence: {details['growth_evidence'].get('overall')}")

            # Every ticker should be classifiable as something
            # (None is valid if the company genuinely doesn't qualify)
            assert pool in ("MLB", "3A", None)

    def test_mlb_failure_details_are_informative(
        self, ticker_data_map: dict, params: dict
    ) -> None:
        """Ford (F) should fail MLB due to high D/E and likely low ROIC."""
        passed, details = passes_mlb_hard_filter(
            ticker_data_map["F"], params["mlb"]
        )
        print("\n=== F (Ford) MLB Hard Filter ===")
        for k, v in details.items():
            status = "PASS" if v["pass"] else "FAIL"
            print(f"  {k}: {v['value']} {v['op']} {v['threshold']} → {status}")
        assert not passed, "Ford should NOT pass MLB"
        # D/E should specifically fail
        assert not details["debt_to_equity"]["pass"]


# ===================================================================
# TestQualityScore
# ===================================================================

class TestQualityScore:

    def test_nvda_score_is_positive(
        self, ticker_data_map: dict
    ) -> None:
        result = calculate_quality_score(ticker_data_map["NVDA"])
        print(f"\n=== NVDA Quality Score: {result['total']}/80 ===")
        for k, v in result["breakdown"].items():
            print(f"  {k}: {v['score']}/{v['max']}")
        assert result["total"] > 40

    def test_breakdown_structure(self, ticker_data_map: dict) -> None:
        result = calculate_quality_score(ticker_data_map["NVDA"])
        assert "total" in result
        assert "breakdown" in result
        expected_keys = {
            "fcf_5y_normalized",
            "roic_5y_stability",
            "gm_5y_trend",
            "capex_intensity",
            "cash_covers_debt",
            "moat_proxy",
        }
        assert set(result["breakdown"].keys()) == expected_keys
        for v in result["breakdown"].values():
            assert "score" in v
            assert "max" in v

    def test_moat_proxy_range(self, ticker_data_map: dict) -> None:
        data = ticker_data_map["NVDA"]["annual"]
        score, breakdown = moat_proxy_score(
            data["income_stmt"], data["balance_sheet"]
        )
        print(f"\n=== NVDA Moat Proxy: {score}/10 ===")
        for k, v in breakdown.items():
            print(f"  {k}: {v}")
        assert 0 <= score <= 10

    def test_gm_trend_direction_and_downside(
        self, ticker_data_map: dict
    ) -> None:
        """NVDA GM rose structurally (56.9%→71.1%), direction should be 5."""
        data = ticker_data_map["NVDA"]["annual"]
        gm_s = metrics.gross_margin_series(data["income_stmt"])
        assert gm_s is not None
        gm_sorted = gm_s.sort_index()
        total, details = gm_trend_score(gm_sorted)
        print(f"\n=== NVDA GM Trend Score: {total}/10 ===")
        print(f"  {details}")
        assert details["direction"] == 5, f"Expected direction=5, got {details['direction']}"
        assert details["downside"] >= 0
        assert total >= 5, f"NVDA GM trend should be >= 5, got {total}"

    def test_moat_proxy_gm_resilience(
        self, ticker_data_map: dict
    ) -> None:
        """NVDA moat GM resilience should benefit from structural improvement."""
        data = ticker_data_map["NVDA"]["annual"]
        score, breakdown = moat_proxy_score(
            data["income_stmt"], data["balance_sheet"]
        )
        gm_res = breakdown["gm_resilience"]
        print(f"\n=== NVDA Moat GM Resilience: {gm_res['score']}/4 ===")
        print(f"  gm_trend_total: {gm_res['gm_trend_total']}/10")
        # Should be better than old std-based score (was 2.37/4)
        assert gm_res["score"] >= 2.5, f"Expected >= 2.5, got {gm_res['score']}"
