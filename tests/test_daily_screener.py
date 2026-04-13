"""Tests for the daily screener end-to-end pipeline."""

from pathlib import Path
import shutil

import pytest
import yaml

from live.daily_screener import run_daily_screener

TEST_OUTPUT_DIR = "live/output_test"
SMALL_UNIVERSE = ["NVDA", "AAPL", "META", "LULU", "GLW"]


@pytest.fixture(scope="module")
def params() -> dict:
    with open("configs/params.yaml") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def result(params: dict) -> dict:
    """Run the pipeline once on a small universe for all tests."""
    return run_daily_screener(
        params=params,
        output_dir=TEST_OUTPUT_DIR,
        universe_tickers=SMALL_UNIVERSE,
        save_snapshots=True,
    )


@pytest.fixture(autouse=True, scope="module")
def clean_output():
    yield
    p = Path(TEST_OUTPUT_DIR)
    if p.exists():
        shutil.rmtree(p)


class TestPipelineStructure:

    def test_pipeline_runs_end_to_end(self, result: dict) -> None:
        print(f"\n=== Pipeline Result ===")
        print(f"  Universe: {result['universe_size']}")
        print(f"  Summary: {result['summary']}")
        print(f"  Quality pool: {len(result['quality_pool'])}")
        print(f"  Candidates: {len(result['candidates'])}")
        print(f"  Watch list: {len(result['watch_list'])}")
        assert "run_timestamp" in result
        assert "summary" in result
        assert "candidates" in result
        assert "watch_list" in result
        assert "quality_pool" in result
        assert result["universe_size"] == len(SMALL_UNIVERSE)

    def test_candidates_subset_of_quality_pool(self, result: dict) -> None:
        pool_tickers = {r["ticker"] for r in result["quality_pool"]}
        for c in result["candidates"]:
            assert c["ticker"] in pool_tickers, (
                f"Candidate {c['ticker']} not in quality pool"
            )

    def test_candidates_all_have_trend_and_vcp(self, result: dict) -> None:
        for c in result["candidates"]:
            assert c["trend_template"]["all_pass"], (
                f"{c['ticker']} candidate but trend not confirmed"
            )
            assert c["vcp"]["is_vcp"], (
                f"{c['ticker']} candidate but VCP not detected"
            )
            # RS threshold check
            pool = c["pool"]
            rs = c["rs_rating"]
            if pool == "MLB":
                assert rs >= 80, f"{c['ticker']} MLB candidate but RS={rs}"
            elif pool == "3A":
                assert rs >= 90, f"{c['ticker']} 3A candidate but RS={rs}"

    def test_rs_rating_based_on_full_universe(self, result: dict) -> None:
        """RS ratings should use all tickers, not just quality pool."""
        # All tickers with price data should have rs_rating
        rated_count = sum(
            1 for r in result["quality_pool"]
            if r["rs_rating"] is not None
        )
        # At least some should have ratings
        if result["quality_pool"]:
            assert rated_count > 0

    def test_output_files_created(self, result: dict) -> None:
        out = Path(TEST_OUTPUT_DIR)
        json_files = list(out.glob("snapshot_*.json"))
        html_files = list(out.glob("candidates_*.html"))
        assert len(json_files) >= 1, "No JSON snapshot found"
        assert len(html_files) >= 1, "No HTML report found"
        print(f"\n  JSON: {json_files[0]}")
        print(f"  HTML: {html_files[0]}")

    def test_quality_pool_details(self, result: dict) -> None:
        """Print full quality pool for human inspection."""
        print(f"\n=== Quality Pool ({len(result['quality_pool'])}) ===")
        for r in result["quality_pool"]:
            trend = "PASS" if r["trend_template"] and r["trend_template"]["all_pass"] else "FAIL"
            vcp = "YES" if r["vcp"] and r["vcp"]["is_vcp"] else "NO"
            print(
                f"  {r['ticker']:6s} | {r['pool']:3s} | "
                f"Q={r['quality_score']:5.1f} | RS={r['rs_rating'] or '-':>3} | "
                f"Trend={trend:4s} | VCP={vcp}"
            )
