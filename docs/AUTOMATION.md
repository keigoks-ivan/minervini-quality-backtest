# QGM Daily Screener — Automation

## Overview

The daily screener runs via GitHub Actions at **07:00 TPE (23:00 UTC)** every day.

**Pipeline:**
1. Checkout `minervini-quality-backtest`
2. Install Python 3.12 + dependencies
3. Run `python -m live.daily_screener` (full universe scan)
4. Copy output HTML/JSON to `financial-analysis-bot/docs/qgm/`
5. Git push to deploy → live at `research.investmquest.com/qgm/`

**All date naming uses TPE (UTC+8) timezone** — both in Python output filenames and in the workflow archive copy. This ensures `candidates_2026-04-15.html` corresponds to the report readers see on April 15th in Taipei.

**Deployed files:**
- `/qgm/index.html` — redirects to latest.html
- `/qgm/latest.html` — current day's candidate report
- `/qgm/latest.json` — current day's full snapshot (machine-readable)
- `/qgm/archive/candidates_YYYY-MM-DD.html` — historical reports

## Manual Trigger

### GitHub UI
1. Go to **Actions** tab in `minervini-quality-backtest` repo
2. Select **Daily QGM Screener** workflow
3. Click **Run workflow** → **Run workflow**

### CLI
```bash
gh workflow run daily_screener.yml
gh run list --workflow=daily_screener.yml --limit=5   # check status
gh run watch                                           # live tail
```

## Viewing Results

### Execution logs
```bash
gh run list --workflow=daily_screener.yml --limit=5
gh run view <run-id> --log
```

### Output
- Web: https://research.investmquest.com/qgm/latest.html
- JSON: https://research.investmquest.com/qgm/latest.json

## Caching

Two caches accelerate subsequent runs:

| Cache | Key | Purpose |
|---|---|---|
| pip | `pip-{hash(requirements.txt)}` | Python packages |
| yfinance | `yf-cache-{hash(universe parquet)}` | Price/financial data from yfinance |

First run with empty cache takes ~30+ minutes. Subsequent runs with warm cache are significantly faster.

## Troubleshooting

### Workflow failed — checklist

1. **Check the log**: `gh run view <run-id> --log-failed`
2. **yfinance rate limit**: Most common failure. The screener has retry logic, but extended throttling can cause timeouts.
   - Fix: Re-trigger manually after 30 minutes
3. **Timeout (>60 min)**: Usually yfinance slowness on cache miss
   - Fix: Re-run; the partial cache from the failed run will speed up the retry
4. **`RESEARCH_REPO_TOKEN` auth error**: Token expired or insufficient permissions
   - Fix: See "Token Renewal" below
5. **Import errors**: New dependency not in `requirements.txt`
   - Fix: Add dependency, commit, re-run
6. **No changes to push**: Not a failure — the screener ran but output was identical to previous run

### Common error patterns

| Error | Cause | Fix |
|---|---|---|
| `HTTPError 429` | yfinance rate limit | Wait 30 min, re-trigger |
| `Permission denied` pushing to deploy repo | Token issue | Regenerate token |
| `ModuleNotFoundError` | Missing dependency | Update requirements.txt |

## Token Renewal

The `RESEARCH_REPO_TOKEN` is a GitHub Personal Access Token (PAT) with `repo` scope for `financial-analysis-bot`.

### When it expires:
1. Go to GitHub → Settings → Developer settings → Personal access tokens
2. Generate a new token with `repo` scope
3. Go to `minervini-quality-backtest` → Settings → Secrets and variables → Actions
4. Update `RESEARCH_REPO_TOKEN` with the new token

### Required token permissions:
- `repo` (full control of private repositories) — needed to push to `financial-analysis-bot`

## Concurrency

The workflow uses `concurrency: { group: daily-screener, cancel-in-progress: false }`.
This means if a run is already in progress, the next scheduled run will **queue** (not cancel the running one).

## Cost

GitHub Free tier for private repos: **2,000 minutes/month**.
- Typical run: ~15-30 min (warm cache) / ~30-45 min (cold cache)
- Daily usage: ~15-30 min × 30 days = 450-900 min/month
- Well within free tier limits
