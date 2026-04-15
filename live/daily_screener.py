"""QGM Daily Screener — end-to-end pipeline.

Ties together: universe → quality filter → trend template → RS rating → VCP
to produce the daily candidate list.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
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
        "run_timestamp": datetime.now(timezone(timedelta(hours=8))).isoformat(),
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
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>QGM Screener &middot; {{ date }} — InvestMQuest Research</title>
  <style>
:root{--brand:#1a56db;--brand-light:#eff6ff;--brand-dark:#1e40af;--bg:#f9fafb;--card:#fff;
      --text:#111827;--muted:#6b7280;--border:#e5e7eb;
      --green:#059669;--green-bg:#ecfdf5;
      --red:#dc2626;--red-bg:#fef2f2;
      --amber:#d97706;--amber-bg:#fffbeb;
      --mlb:#1a5f3f;--mlb-bg:#ecfdf5;
      --triple-a:#92400e;--triple-a-bg:#fffbeb}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
     background:var(--bg);color:var(--text);line-height:1.65;font-size:15px;
     min-height:100vh;display:flex;flex-direction:column}
a{color:var(--brand);text-decoration:none}a:hover{text-decoration:underline}
.container{max-width:1120px;margin:0 auto;padding:0 1.5rem;width:100%}

/* Header */
header{background:linear-gradient(135deg,#0f172a 0%,#1e293b 100%);padding:.75rem 0;box-shadow:0 1px 3px rgba(0,0,0,.1)}
.hdr-inner{display:flex;align-items:center;justify-content:space-between}
header .logo{font-size:1.15rem;font-weight:700;color:#fff;letter-spacing:-.02em}
header .logo span{color:#3b82f6}
header nav a{color:rgba(255,255,255,.7);margin-left:1.4rem;font-size:.85rem;font-weight:500;
             padding-bottom:4px;border-bottom:2px solid transparent;transition:all .2s}
header nav a:hover{color:#fff;text-decoration:none;border-bottom-color:rgba(255,255,255,.4)}
header nav a.active{color:#fff;border-bottom-color:#3b82f6}

/* Hero */
.hero{padding:2.5rem 0 2rem;background:linear-gradient(180deg,#f0f4ff 0%,var(--bg) 100%);
      border-bottom:1px solid var(--border);text-align:center}
.hero .eyebrow{display:inline-block;padding:.3rem .8rem;background:rgba(26,86,219,.08);
               color:var(--brand);border-radius:999px;font-size:.72rem;font-weight:600;
               letter-spacing:.04em;margin-bottom:.75rem;text-transform:uppercase}
.hero h1{font-size:2rem;font-weight:800;letter-spacing:-.03em;line-height:1.15;
         background:linear-gradient(135deg,#0f172a 0%,#1a56db 100%);
         -webkit-background-clip:text;-webkit-text-fill-color:transparent;
         background-clip:text;color:transparent;margin-bottom:.5rem}
.hero .sub{color:var(--muted);font-size:.92rem;max-width:560px;margin:0 auto}

/* Stat cards */
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:.85rem;margin:1.5rem 0}
.stat-card{background:var(--card);border:1px solid var(--border);border-radius:10px;
           padding:1.1rem 1.2rem;text-align:center;transition:box-shadow .2s}
.stat-card:hover{box-shadow:0 4px 12px rgba(0,0,0,.05)}
.stat-label{font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;
            margin-bottom:.3rem}
.stat-value{font-size:1.5rem;font-weight:700;color:var(--text)}

/* Section */
.section{margin-top:2rem}
.section-title{font-size:1.1rem;font-weight:700;color:var(--text);margin-bottom:.75rem;
               display:flex;align-items:center;gap:.5rem}
.section-title .count{font-size:.78rem;font-weight:600;color:var(--muted);
                      background:var(--border);border-radius:999px;padding:.15rem .6rem}
.empty-msg{background:var(--card);border:1px solid var(--border);border-radius:10px;
           padding:1.5rem;text-align:center;color:var(--muted);font-size:.9rem}
.section-desc{font-size:.8rem;color:var(--muted);line-height:1.6;margin-bottom:.75rem;
              padding:.7rem .9rem;background:var(--brand-light);border-radius:8px;
              border-left:3px solid var(--brand)}
.section-desc ul{margin:.3rem 0 0 1.1rem;padding:0}
.section-desc li{margin-bottom:.15rem}

/* Tables */
.table-wrap{background:var(--card);border:1px solid var(--border);border-radius:10px;
            overflow:hidden}
table{width:100%;border-collapse:collapse;font-size:.82rem}
th{background:#f8fafc;padding:.65rem .85rem;text-align:left;font-weight:600;font-size:.72rem;
   color:var(--muted);text-transform:uppercase;letter-spacing:.04em;
   border-bottom:1px solid var(--border);cursor:pointer;user-select:none;
   white-space:nowrap;transition:color .15s}
th:hover{color:var(--brand)}
th .sort-arrow{font-size:.65rem;margin-left:.25rem;opacity:.3}
th.sort-active .sort-arrow{opacity:1;color:var(--brand)}
td{padding:.6rem .85rem;border-bottom:1px solid #f1f5f9}
tr:last-child td{border-bottom:none}
tr:hover{background:#f8fafc}
td.ticker{font-weight:600;color:var(--text)}
.pool-mlb{color:var(--mlb);font-weight:600;font-size:.75rem;
          background:var(--mlb-bg);padding:.15rem .5rem;border-radius:4px;display:inline-block}
.pool-3a{color:var(--triple-a);font-weight:600;font-size:.75rem;
         background:var(--triple-a-bg);padding:.15rem .5rem;border-radius:4px;display:inline-block}
.pass{color:var(--green);font-weight:600}
.fail{color:var(--muted)}
.num{text-align:right;font-variant-numeric:tabular-nums}

/* Footer */
footer{background:#fff;border-top:1px solid var(--border);color:var(--muted);
       text-align:center;padding:1.25rem 0;font-size:.78rem;margin-top:auto}
footer a{color:var(--muted)}

/* Responsive */
@media(max-width:768px){
  .hero{padding:1.5rem 0 1.25rem}
  .hero h1{font-size:1.5rem}
  .stats{grid-template-columns:repeat(2,1fr);gap:.6rem}
  .stat-card{padding:.85rem .9rem}
  .stat-value{font-size:1.2rem}
  .table-wrap{border-radius:8px}
  table{font-size:.76rem}
  th,td{padding:.5rem .6rem}
  .hdr-inner{flex-direction:column;gap:.5rem}
  header nav{display:flex;flex-wrap:wrap;justify-content:center;gap:.4rem 0}
  header nav a{margin-left:0;margin-right:1rem;font-size:.78rem}
}
  </style>
</head>
<body>
<header>
  <div class="container hdr-inner">
    <a class="logo" href="/">InvestMQuest<span>.</span> Research</a>
    <nav>
      <a href="/">首頁</a>
      <a href="/briefing/">每日簡報</a>
      <a href="/weekly/">週報</a>
      <a href="/backtest/">回測</a>
      <a href="/research/">研究報告</a>
      <a href="/six-state/">六狀態機</a>
      <a href="/qgm/" class="active">QGM</a>
    </nav>
  </div>
</header>

<section class="hero">
  <div class="container">
    <span class="eyebrow">Quality Growth Momentum</span>
    <h1>QGM Daily Screener</h1>
    <p class="sub">品質成長動能系統 — 用品質作為護欄、用技術抓時機。每日自動掃描 S&amp;P 500 + NASDAQ 100。</p>
  </div>
</section>

<main class="container" style="flex:1;padding-top:.5rem;padding-bottom:2rem">

  <div class="stats">
    <div class="stat-card">
      <div class="stat-label">掃描日期</div>
      <div class="stat-value" style="font-size:1.15rem">{{ date }}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Universe</div>
      <div class="stat-value">{{ universe_size }}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Quality Pool</div>
      <div class="stat-value" style="font-size:1.1rem">{{ summary.mlb }} MLB + {{ summary['3a'] }} 3A</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Candidates</div>
      <div class="stat-value">{{ candidates|length }}</div>
    </div>
  </div>

  <div class="section">
    <h2 class="section-title">Candidates <span class="count">{{ candidates|length }}</span></h2>
    <div class="section-desc">
      通過所有篩選的最終候選標的，品質、趨勢、動能三者兼具：
      <ul>
        <li>Quality Pool 成員（通過基本面品質篩選）</li>
        <li>Trend Template PASS（Stage 2 上升趨勢確認）</li>
        <li>VCP 收斂型態偵測通過（波動率收斂 + 量能萎縮）</li>
        <li>RS Rating 達標（MLB &ge; 80, 3A &ge; 90）</li>
      </ul>
    </div>
    {% if candidates %}
    <div class="table-wrap">
    <table>
      <thead><tr>
        <th>Ticker</th><th>Pool</th><th>Quality</th><th class="num">RS</th><th class="num">Price</th>
        <th class="num">Pivot</th><th class="num">Vol Ratio</th><th class="num">Drawdown</th>
      </tr></thead>
      <tbody>
      {% for c in candidates %}
      <tr>
        <td class="ticker">{{ c.ticker }}</td>
        <td><span class="pool-{{ c.pool|lower }}">{{ c.pool }}</span></td>
        <td>{{ "%.1f"|format(c.quality_score) }}/80</td>
        <td class="num">{{ c.rs_rating or '-' }}</td>
        <td class="num">${{ "%.2f"|format(c.price) if c.price else '-' }}</td>
        <td class="num">${{ "%.2f"|format(c.vcp.pivot_price) if c.vcp else '-' }}</td>
        <td class="num">{{ "%.2f"|format(c.vcp.volatility_ratio) if c.vcp else '-' }}</td>
        <td class="num">{{ "%.1f"|format(c.vcp.max_drawdown * 100) if c.vcp else '-' }}%</td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
    </div>
    {% else %}
    <div class="empty-msg">No candidates today. Market may not have quality setups — patience.</div>
    {% endif %}
  </div>

  <div class="section">
    <h2 class="section-title">Watch List <span class="count">{{ watch_list|length }}</span></h2>
    <div class="section-desc">
      趨勢已確認但尚未完全就位的觀察標的，值得持續追蹤：
      <ul>
        <li>已通過 Quality Pool 基本面篩選</li>
        <li>Trend Template PASS（Stage 2 上升趨勢確認）</li>
        <li>缺少 VCP 收斂型態，或 RS Rating 未達門檻</li>
        <li>等待型態成熟或動能增強後可能升級為 Candidate</li>
      </ul>
    </div>
    {% if watch_list %}
    <div class="table-wrap">
    <table>
      <thead><tr>
        <th>Ticker</th><th>Pool</th><th>Quality</th><th class="num">RS</th><th class="num">Price</th>
        <th>VCP</th><th class="num">Vol Ratio</th>
      </tr></thead>
      <tbody>
      {% for w in watch_list[:30] %}
      <tr>
        <td class="ticker">{{ w.ticker }}</td>
        <td><span class="pool-{{ w.pool|lower }}">{{ w.pool }}</span></td>
        <td>{{ "%.1f"|format(w.quality_score) }}/80</td>
        <td class="num">{{ w.rs_rating or '-' }}</td>
        <td class="num">${{ "%.2f"|format(w.price) if w.price else '-' }}</td>
        <td class="{{ 'pass' if w.vcp and w.vcp.is_vcp else 'fail' }}">{{ 'YES' if w.vcp and w.vcp.is_vcp else 'NO' }}</td>
        <td class="num">{{ "%.2f"|format(w.vcp.volatility_ratio) if w.vcp else '-' }}</td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
    </div>
    {% else %}
    <div class="empty-msg">No watch list items.</div>
    {% endif %}
  </div>

  <div class="section">
    <h2 class="section-title">MLB Quality Pool <span class="count">{{ quality_pool|selectattr('pool','equalto','MLB')|list|length }}</span></h2>
    <div class="section-desc">
      大聯盟級品質股 — 成熟企業中兼具品質與成長的核心持股候選：
      <ul>
        <li><strong>FCF Margin</strong> &ge; 10% — 自由現金流佔營收比例</li>
        <li><strong>ROIC</strong> &ge; 15% — 投入資本回報率</li>
        <li><strong>EPS CAGR 前瞻 2 年</strong> &ge; 15% — 分析師預估盈餘年複合成長</li>
        <li><strong>PEG</strong> &le; 2.0 — 本益比相對成長率的合理性</li>
        <li><strong>D/E</strong> &le; 0.7 — 負債權益比（財務槓桿控制）</li>
      </ul>
      <strong>Quality 分數</strong>（滿分 80）用於排名，僅衡量品質穩定度：FCF 穩定度 (15) + ROIC 穩定度 (15) + 毛利率趨勢 (10) + 資本密度 (10) + 現金覆蓋負債 (10) + 護城河代理分 (20)。EPS CAGR 為入選硬篩門檻，通過後不重複計分。
    </div>
    <div class="table-wrap">
    <table>
      <thead><tr>
        <th>Ticker</th><th>Quality</th><th class="num">EPS Fwd</th><th class="num">ROIC</th><th class="num">FCF%</th><th class="num">PEG</th><th class="num">D/E</th><th class="num">RS</th><th>Trend</th><th>VCP</th>
      </tr></thead>
      <tbody>
      {% for q in quality_pool if q.pool == 'MLB' %}
      <tr>
        <td class="ticker">{{ q.ticker }}</td>
        <td>{{ "%.1f"|format(q.quality_score) }}/80</td>
        <td class="num">{% if q.hard_filter_details.eps_cagr_2y_fwd %}{{ "%.0f"|format(q.hard_filter_details.eps_cagr_2y_fwd.value * 100) }}%{% else %}-{% endif %}</td>
        <td class="num">{% if q.hard_filter_details.roic %}{{ "%.0f"|format(q.hard_filter_details.roic.value * 100) }}%{% else %}-{% endif %}</td>
        <td class="num">{% if q.hard_filter_details.fcf_margin %}{{ "%.0f"|format(q.hard_filter_details.fcf_margin.value * 100) }}%{% else %}-{% endif %}</td>
        <td class="num">{% if q.hard_filter_details.peg %}{{ "%.1f"|format(q.hard_filter_details.peg.value) }}{% else %}-{% endif %}</td>
        <td class="num">{% if q.hard_filter_details.debt_to_equity %}{{ "%.2f"|format(q.hard_filter_details.debt_to_equity.value) }}{% else %}-{% endif %}</td>
        <td class="num">{{ q.rs_rating or '-' }}</td>
        <td class="{{ 'pass' if q.trend_template and q.trend_template.all_pass else 'fail' }}">{{ 'PASS' if q.trend_template and q.trend_template.all_pass else 'FAIL' }}</td>
        <td class="{{ 'pass' if q.vcp and q.vcp.is_vcp else 'fail' }}">{{ 'YES' if q.vcp and q.vcp.is_vcp else 'NO' }}</td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
    </div>
  </div>

  <div class="section">
    <h2 class="section-title">3A Quality Pool <span class="count">{{ quality_pool|selectattr('pool','equalto','3A')|list|length }}</span></h2>
    <div class="section-desc">
      潛力加速股 — 高成長但不確定性較高，技術門檻更嚴格，部位更小、停損更緊：
      <ul>
        <li><strong>EPS CAGR 前瞻 2 年</strong> &ge; 30% — 分析師預估盈餘高速成長</li>
        <li><strong>FCF Margin</strong> &ge; 0% — 較寬鬆底線（允許高投資期）</li>
        <li><strong>ROIC</strong> &ge; 5% — 較寬鬆底線</li>
        <li><strong>PEG</strong> &le; 2.0, <strong>D/E</strong> &le; 0.7 — 同 MLB</li>
      </ul>
      <strong>Quality 分數</strong>（滿分 80）用於排名，僅衡量品質穩定度：FCF 穩定度 (15) + ROIC 穩定度 (15) + 毛利率趨勢 (10) + 資本密度 (10) + 現金覆蓋負債 (10) + 護城河代理分 (20)。EPS CAGR 為入選硬篩門檻，通過後不重複計分。
    </div>
    {% if quality_pool|selectattr('pool','equalto','3A')|list %}
    <div class="table-wrap">
    <table>
      <thead><tr>
        <th>Ticker</th><th>Quality</th><th class="num">EPS Fwd</th><th class="num">ROIC</th><th class="num">FCF%</th><th class="num">PEG</th><th class="num">D/E</th><th class="num">RS</th><th>Trend</th><th>VCP</th>
      </tr></thead>
      <tbody>
      {% for q in quality_pool if q.pool == '3A' %}
      <tr>
        <td class="ticker">{{ q.ticker }}</td>
        <td>{{ "%.1f"|format(q.quality_score) }}/80</td>
        <td class="num">{% if q.hard_filter_details.eps_cagr_2y_fwd %}{{ "%.0f"|format(q.hard_filter_details.eps_cagr_2y_fwd.value * 100) }}%{% else %}-{% endif %}</td>
        <td class="num">{% if q.hard_filter_details.roic %}{{ "%.0f"|format(q.hard_filter_details.roic.value * 100) }}%{% else %}-{% endif %}</td>
        <td class="num">{% if q.hard_filter_details.fcf_margin %}{{ "%.0f"|format(q.hard_filter_details.fcf_margin.value * 100) }}%{% else %}-{% endif %}</td>
        <td class="num">{% if q.hard_filter_details.peg %}{{ "%.1f"|format(q.hard_filter_details.peg.value) }}{% else %}-{% endif %}</td>
        <td class="num">{% if q.hard_filter_details.debt_to_equity %}{{ "%.2f"|format(q.hard_filter_details.debt_to_equity.value) }}{% else %}-{% endif %}</td>
        <td class="num">{{ q.rs_rating or '-' }}</td>
        <td class="{{ 'pass' if q.trend_template and q.trend_template.all_pass else 'fail' }}">{{ 'PASS' if q.trend_template and q.trend_template.all_pass else 'FAIL' }}</td>
        <td class="{{ 'pass' if q.vcp and q.vcp.is_vcp else 'fail' }}">{{ 'YES' if q.vcp and q.vcp.is_vcp else 'NO' }}</td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
    </div>
    {% else %}
    <div class="empty-msg">No 3A stocks today.</div>
    {% endif %}
  </div>

  <div style="margin-top:1.5rem;text-align:right">
    <a href="/qgm/archive/" style="font-size:.82rem;color:var(--muted)">Archive &rarr;</a>
  </div>

</main>

<footer>
  <div class="container">
    Generated: {{ run_timestamp }} &middot; Phase 0 MVP &middot; Not investment advice<br>
    &copy; 2026 InvestMQuest Research
  </div>
</footer>
<script>
(function(){
  function parseVal(txt){
    txt=txt.trim();
    if(txt==='-'||txt==='')return null;
    var n=parseFloat(txt.replace(/[$,%]/g,''));
    return isNaN(n)?txt:n;
  }
  function sortTable(th,colIdx){
    var table=th.closest('table'),tbody=table.querySelector('tbody');
    if(!tbody)return;
    var rows=Array.from(tbody.querySelectorAll('tr'));
    var cur=th.dataset.sortDir||'';
    var dir=(cur==='desc')?'asc':'desc';
    table.querySelectorAll('th').forEach(function(h){h.classList.remove('sort-active');h.dataset.sortDir='';
      var a=h.querySelector('.sort-arrow');if(a)a.textContent='\\u2195';});
    th.dataset.sortDir=dir;th.classList.add('sort-active');
    var arrow=th.querySelector('.sort-arrow');if(arrow)arrow.textContent=(dir==='desc')?'\\u2193':'\\u2191';
    rows.sort(function(a,b){
      var av=parseVal(a.cells[colIdx].textContent);
      var bv=parseVal(b.cells[colIdx].textContent);
      if(av===null&&bv===null)return 0;
      if(av===null)return 1;if(bv===null)return -1;
      if(typeof av==='string'&&typeof bv==='string'){
        var c=av.localeCompare(bv);return dir==='asc'?c:-c;
      }
      return dir==='asc'?av-bv:bv-av;
    });
    rows.forEach(function(r){tbody.appendChild(r);});
  }
  document.querySelectorAll('table').forEach(function(table){
    var ths=table.querySelectorAll('th');
    ths.forEach(function(th,i){
      var arrow=document.createElement('span');arrow.className='sort-arrow';arrow.textContent='\\u2195';
      th.appendChild(arrow);
      th.addEventListener('click',function(){sortTable(th,i);});
    });
    // Default sort: Quality column (index 1) descending
    if(ths.length>1){
      var qCol=ths[1];
      if(qCol.textContent.replace('\\u2195','').trim()==='Quality'){
        qCol.dataset.sortDir='asc';
        sortTable(qCol,1);
      }
    }
  });
})();
</script>
</body>
</html>
"""


def save_screener_output(result: dict, output_dir: str) -> None:
    """Save screener results as JSON snapshot and HTML report."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    _TPE = timezone(timedelta(hours=8))
    today = datetime.now(_TPE).strftime("%Y-%m-%d")

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

    # Latest symlinks (fixed filenames for stable URLs)
    import shutil
    latest_html = out / "latest.html"
    latest_json = out / "latest.json"
    shutil.copy2(html_path, latest_html)
    shutil.copy2(json_path, latest_json)
    logger.info("Copied latest.html and latest.json")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    result = run_daily_screener()
    n_cand = len(result["candidates"])
    n_watch = len(result["watch_list"])
    n_pool = len(result["quality_pool"])
    logger.info(
        "Done — %d candidates, %d watch list, %d quality pool",
        n_cand, n_watch, n_pool,
    )
