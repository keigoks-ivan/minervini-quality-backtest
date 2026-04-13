"""QGM Daily Screener — end-to-end pipeline.

Ties together: universe → quality filter → trend template → RS rating → VCP
to produce the daily candidate list.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import yaml
from jinja2 import Template
from tqdm import tqdm

from data.universe_builder import build_universe, filter_universe
from data.yf_loader import YFinanceSource
from patterns.rs_rating import calculate_rs_ratings, calculate_rs_score, meets_rs_threshold
from patterns.trend_template import check_trend_template
from patterns.vcp_detector import detect_vcp_mvp
from screener import metrics
from screener.quality_core import classify_pool
from screener.quality_score import calculate_quality_score

logger = logging.getLogger(__name__)


def _load_ticker_data(ticker: str, loader: YFinanceSource) -> dict:
    """Load all raw data for a single ticker."""
    return {
        "info": loader.get_info(ticker),
        "annual": loader.get_annual_financials(ticker),
        "quarterly": loader.get_quarterly_financials(ticker),
        "estimates": loader.get_analyst_estimates(ticker),
        "prices": loader.get_price_history(ticker),
    }


def _safe_get_nested(d: dict, *keys, default=None):
    """Safely traverse nested dicts."""
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
    return d


def run_daily_screener(
    params: dict | None = None,
    output_dir: str = "live/output",
    universe_tickers: list[str] | None = None,
    save_snapshots: bool = True,
) -> dict:
    """Execute the full daily screener pipeline.

    Args:
        params: Full params.yaml dict. Loaded from file if None.
        output_dir: Where to save JSON/HTML output.
        universe_tickers: Override universe (for testing). None = full universe.
        save_snapshots: Whether to write output files.

    Returns:
        Result dict with summary, candidates, watch_list, quality_pool.
    """
    if params is None:
        with open("configs/params.yaml") as f:
            params = yaml.safe_load(f)

    loader = YFinanceSource()
    qf_params = params["quality_filter"]
    tf_params = params["technical_filter"]
    vcp_params = params["vcp"]

    # 1. Build universe
    if universe_tickers is None:
        raw_tickers = build_universe()
        tickers, filter_stats = filter_universe(
            raw_tickers, params["universe"], loader
        )
    else:
        tickers = universe_tickers
        filter_stats = {"total_input": len(tickers), "total_output": len(tickers)}

    # 2. Process each ticker
    all_results: dict[str, dict] = {}
    rs_scores: dict[str, float] = {}
    errors: list[str] = []

    for ticker in tqdm(tickers, desc="Screening", unit="ticker"):
        try:
            td = _load_ticker_data(ticker, loader)
        except Exception as e:
            logger.warning("Failed to load data for %s: %s", ticker, e)
            errors.append(ticker)
            continue

        # Quality classification
        pool, pool_details = classify_pool(td, qf_params)

        # Quality score (compute for all, useful for ranking)
        try:
            q_score = calculate_quality_score(td)
        except Exception:
            q_score = {"total": 0, "breakdown": {}}

        # RS score (for all tickers with enough data)
        close = td["prices"]["Close"] if td["prices"] is not None else None
        if close is not None and len(close) >= 252:
            rs = calculate_rs_score(close)
            if rs is not None:
                rs_scores[ticker] = rs

        # Extract hard filter details from pool_details
        hard_filter = {}
        for pn in ("mlb", "triple_a"):
            if pn in pool_details and "checks" in pool_details[pn]:
                hard_filter = pool_details[pn]["checks"]
                break

        # Trend template + VCP (only if in a pool)
        trend_result = None
        vcp_result = None
        if pool is not None and td["prices"] is not None:
            trend_pass, trend_details = check_trend_template(td["prices"])
            trend_result = {"all_pass": trend_pass, "conditions": trend_details}

            vcp_result = detect_vcp_mvp(
                td["prices"]["Close"],
                td["prices"]["Volume"],
                params=vcp_params,
            )

        price = None
        if td["info"]:
            price = td["info"].get("currentPrice") or td["info"].get("regularMarketPrice")
        cap = td["info"].get("marketCap", 0) if td["info"] else 0

        all_results[ticker] = {
            "ticker": ticker,
            "pool": pool,
            "quality_score": q_score["total"],
            "quality_breakdown": q_score["breakdown"],
            "hard_filter_details": hard_filter,
            "trend_template": trend_result,
            "rs_score": rs_scores.get(ticker),
            "rs_rating": None,  # filled after ranking
            "vcp": vcp_result,
            "price": price,
            "market_cap_b": round(cap / 1e9, 1) if cap else None,
        }

    # 3. RS Ratings (percentile ranking across all scored tickers)
    rs_ratings = calculate_rs_ratings(rs_scores) if rs_scores else {}
    for ticker, rating in rs_ratings.items():
        if ticker in all_results:
            all_results[ticker]["rs_rating"] = rating

    # 4. Classify into buckets
    quality_pool = []
    candidates = []
    watch_list = []

    summary = {
        "mlb": 0,
        "3a": 0,
        "trend_confirmed_mlb": 0,
        "trend_confirmed_3a": 0,
        "vcp_setup_mlb": 0,
        "vcp_setup_3a": 0,
        "breakout_today_mlb": 0,
        "breakout_today_3a": 0,
    }

    for ticker, r in all_results.items():
        pool = r["pool"]
        if pool is None:
            continue

        quality_pool.append(r)

        if pool == "MLB":
            summary["mlb"] += 1
        else:
            summary["3a"] += 1

        trend = r["trend_template"]
        trend_pass = trend["all_pass"] if trend else False
        vcp = r["vcp"]
        vcp_pass = vcp["is_vcp"] if vcp else False
        rs_rating = r["rs_rating"] or 0

        # Check RS threshold
        rs_ok = False
        if pool and rs_rating:
            rs_ok = meets_rs_threshold(rs_rating, pool, tf_params)

        if trend_pass:
            if pool == "MLB":
                summary["trend_confirmed_mlb"] += 1
            else:
                summary["trend_confirmed_3a"] += 1

            if vcp_pass:
                if pool == "MLB":
                    summary["vcp_setup_mlb"] += 1
                else:
                    summary["vcp_setup_3a"] += 1

                if rs_ok:
                    candidates.append(r)
                else:
                    watch_list.append(r)
            else:
                watch_list.append(r)

    # Sort by quality score descending
    candidates.sort(key=lambda x: x["quality_score"], reverse=True)
    watch_list.sort(key=lambda x: x["quality_score"], reverse=True)
    quality_pool.sort(key=lambda x: x["quality_score"], reverse=True)

    result = {
        "run_timestamp": datetime.now().isoformat(),
        "universe_size": len(tickers),
        "summary": summary,
        "candidates": candidates,
        "watch_list": watch_list,
        "quality_pool": quality_pool,
        "rejected": {
            "data_errors": len(errors),
            "error_tickers": errors[:20],
            "universe_filter": filter_stats,
        },
    }

    if save_snapshots:
        save_screener_output(result, output_dir)

    return result


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>QGM Screener - {{ date }}</title>
  <style>
    body { font-family: -apple-system, sans-serif; max-width: 1200px; margin: 40px auto; padding: 0 20px; color: #333; }
    h1 { border-bottom: 2px solid #333; padding-bottom: 10px; }
    h2 { margin-top: 40px; }
    .summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin: 30px 0; }
    .stat { background: #f5f5f5; padding: 15px; border-radius: 4px; }
    .stat-label { font-size: 12px; color: #666; text-transform: uppercase; }
    .stat-value { font-size: 24px; font-weight: 700; }
    table { width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 13px; }
    th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee; }
    th { background: #fafafa; font-weight: 600; }
    .pool-mlb { color: #1a5f3f; font-weight: 600; }
    .pool-3a { color: #8b6f1a; font-weight: 600; }
    .pass { color: #1a5f3f; }
    .fail { color: #8b0000; }
  </style>
</head>
<body>
  <h1>QGM Screener &middot; {{ date }}</h1>

  <div class="summary">
    <div class="stat"><div class="stat-label">Universe</div><div class="stat-value">{{ universe_size }}</div></div>
    <div class="stat"><div class="stat-label">Quality Pool</div><div class="stat-value">{{ summary.mlb }} MLB + {{ summary['3a'] }} 3A</div></div>
    <div class="stat"><div class="stat-label">Trend Confirmed</div><div class="stat-value">{{ summary.trend_confirmed_mlb + summary.trend_confirmed_3a }}</div></div>
    <div class="stat"><div class="stat-label">Candidates</div><div class="stat-value">{{ candidates|length }}</div></div>
  </div>

  <h2>Candidates ({{ candidates|length }})</h2>
  {% if candidates %}
  <table>
    <tr>
      <th>Ticker</th><th>Pool</th><th>Quality</th><th>RS</th><th>Price</th>
      <th>Pivot</th><th>Vol Ratio</th><th>Drawdown</th>
    </tr>
    {% for c in candidates %}
    <tr>
      <td><strong>{{ c.ticker }}</strong></td>
      <td class="pool-{{ c.pool|lower }}">{{ c.pool }}</td>
      <td>{{ "%.1f"|format(c.quality_score) }}/80</td>
      <td>{{ c.rs_rating or '-' }}</td>
      <td>${{ "%.2f"|format(c.price) if c.price else '-' }}</td>
      <td>${{ "%.2f"|format(c.vcp.pivot_price) if c.vcp else '-' }}</td>
      <td>{{ "%.2f"|format(c.vcp.volatility_ratio) if c.vcp else '-' }}</td>
      <td>{{ "%.1f"|format(c.vcp.max_drawdown * 100) if c.vcp else '-' }}%</td>
    </tr>
    {% endfor %}
  </table>
  {% else %}
  <p>No candidates today. Market may not have quality setups — patience.</p>
  {% endif %}

  <h2>Watch List — Trend PASS, VCP pending ({{ watch_list|length }})</h2>
  {% if watch_list %}
  <table>
    <tr>
      <th>Ticker</th><th>Pool</th><th>Quality</th><th>RS</th><th>Price</th>
      <th>VCP</th><th>Vol Ratio</th>
    </tr>
    {% for w in watch_list[:30] %}
    <tr>
      <td><strong>{{ w.ticker }}</strong></td>
      <td class="pool-{{ w.pool|lower }}">{{ w.pool }}</td>
      <td>{{ "%.1f"|format(w.quality_score) }}/80</td>
      <td>{{ w.rs_rating or '-' }}</td>
      <td>${{ "%.2f"|format(w.price) if w.price else '-' }}</td>
      <td class="{{ 'pass' if w.vcp and w.vcp.is_vcp else 'fail' }}">{{ 'YES' if w.vcp and w.vcp.is_vcp else 'NO' }}</td>
      <td>{{ "%.2f"|format(w.vcp.volatility_ratio) if w.vcp else '-' }}</td>
    </tr>
    {% endfor %}
  </table>
  {% else %}
  <p>No watch list items.</p>
  {% endif %}

  <h2>Full Quality Pool ({{ quality_pool|length }})</h2>
  <table>
    <tr>
      <th>Ticker</th><th>Pool</th><th>Quality</th><th>RS</th><th>Trend</th><th>VCP</th>
    </tr>
    {% for q in quality_pool %}
    <tr>
      <td><strong>{{ q.ticker }}</strong></td>
      <td class="pool-{{ q.pool|lower }}">{{ q.pool }}</td>
      <td>{{ "%.1f"|format(q.quality_score) }}/80</td>
      <td>{{ q.rs_rating or '-' }}</td>
      <td class="{{ 'pass' if q.trend_template and q.trend_template.all_pass else 'fail' }}">{{ 'PASS' if q.trend_template and q.trend_template.all_pass else 'FAIL' }}</td>
      <td class="{{ 'pass' if q.vcp and q.vcp.is_vcp else 'fail' }}">{{ 'YES' if q.vcp and q.vcp.is_vcp else 'NO' }}</td>
    </tr>
    {% endfor %}
  </table>

  <hr>
  <p style="color: #999; font-size: 12px;">
    Generated: {{ run_timestamp }}<br>
    Phase 0 MVP &middot; Not investment advice
  </p>
</body>
</html>
"""


def save_screener_output(result: dict, output_dir: str) -> None:
    """Save screener results as JSON snapshot and HTML report."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")

    # JSON snapshot
    json_path = out / f"snapshot_{today}.json"

    # Make a JSON-serializable copy (strip non-serializable numpy types)
    def _clean(obj):
        import numpy as np
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_clean(i) for i in obj]
        return obj

    clean_result = _clean(result)
    json_path.write_text(
        json.dumps(clean_result, indent=2, ensure_ascii=False, default=str)
    )
    logger.info("Saved JSON snapshot to %s", json_path)

    # HTML report
    html_path = out / f"candidates_{today}.html"
    template = Template(_HTML_TEMPLATE)
    html = template.render(
        date=today,
        run_timestamp=result["run_timestamp"],
        universe_size=result["universe_size"],
        summary=result["summary"],
        candidates=result["candidates"],
        watch_list=result["watch_list"],
        quality_pool=result["quality_pool"],
    )
    html_path.write_text(html)
    logger.info("Saved HTML report to %s", html_path)
