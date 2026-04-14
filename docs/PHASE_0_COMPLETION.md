# Phase 0 MVP Completion Report

**Date**: 2026-04-14
**Version**: v0.1.0

---

## 1. Scope & Objectives (from SPEC 12.1)

Phase 0 goal: validate the QGM logic end-to-end using free yfinance data, producing a working daily screener pipeline that identifies quality-growth stocks with Minervini-style technical setups.

**Budget**: $0/month (yfinance only)

---

## 2. Completed Modules

| Module | Files | Tests | Status |
|--------|-------|-------|--------|
| Data Layer | `data/base.py`, `yf_loader.py`, `cache_manager.py` | `test_yf_loader.py` (16 tests) | Done |
| Universe Builder | `data/universe_builder.py` | `test_universe.py` (10 tests) | Done |
| Quality Metrics | `screener/metrics.py` | via `test_quality.py` | Done |
| Quality Core (MLB/3A) | `screener/quality_core.py` | `test_quality.py` (15 tests) | Done |
| Quality Scoring | `screener/quality_score.py` | via `test_quality.py` | Done |
| Pool Classifier | `screener/pool_classifier.py` | `test_pool_transition.py` (14 tests) | Done |
| Pool Transition | `screener/pool_transition.py` | via `test_pool_transition.py` | Done |
| Trend Template | `patterns/trend_template.py` | `test_technical.py` (9 tests) | Done |
| RS Rating | `patterns/rs_rating.py` | via `test_technical.py` | Done |
| VCP Detector (MVP) | `patterns/vcp_detector.py` | `test_vcp.py` (9 tests) | Done |
| Daily Screener | `live/daily_screener.py` | `test_daily_screener.py` (6 tests) | Done |

**Total: 79 tests, all passing.**

---

## 3. Full Universe Results (2026-04-14)

### Pipeline Summary

| Metric | Count |
|--------|-------|
| Universe (SP500 + NDX, filtered) | 476 |
| MLB Pool | 20 |
| 3A Pool | 2 |
| **Quality Pool Total** | **22** |
| Trend Confirmed | 3 |
| VCP Setup | 0 |
| Candidates | 0 |

### Quality Pool (all 22 stocks, ranked by quality score)

| Ticker | Pool | Quality | RS | Trend | VCP |
|--------|------|---------|-----|-------|-----|
| FTNT | MLB | 78.2 | 22 | FAIL | NO |
| ADBE | MLB | 76.4 | 6 | FAIL | NO |
| RMD | MLB | 72.4 | 25 | FAIL | NO |
| NVDA | MLB | 69.6 | 71 | FAIL | NO |
| MCO | MLB | 68.0 | 21 | FAIL | YES |
| FFIV | MLB | 66.6 | 47 | FAIL | NO |
| APH | MLB | 66.3 | 87 | PASS | NO |
| MA | MLB | 64.6 | 26 | FAIL | NO |
| EXPE | MLB | 62.3 | 63 | FAIL | NO |
| EA | MLB | 60.5 | 66 | PASS | NO |
| META | MLB | 54.8 | 35 | FAIL | NO |
| GILD | MLB | 52.5 | 74 | FAIL | NO |
| INCY | MLB | 52.2 | 72 | FAIL | NO |
| TTD | MLB | 52.1 | 1 | FAIL | NO |
| LLY | 3A | 51.8 | 49 | FAIL | NO |
| DXCM | MLB | 50.5 | 19 | FAIL | NO |
| VRT | MLB | 50.0 | 97 | PASS | NO |
| BR | MLB | 48.9 | 5 | FAIL | NO |
| GDDY | MLB | 48.2 | 3 | FAIL | NO |
| PTC | MLB | 45.8 | 10 | FAIL | NO |
| INTU | MLB | 42.3 | 3 | FAIL | NO |
| ALNY | 3A | 25.0 | 39 | FAIL | NO |

### Watch List (Trend PASS, closest to candidate)

| Ticker | Pool | Quality | RS | Status |
|--------|------|---------|-----|--------|
| VRT | MLB | 50.0 | 97 | Trend PASS, RS 97, awaiting VCP formation |
| APH | MLB | 66.3 | 87 | Trend PASS, RS 87 (>80), awaiting VCP |
| EA | MLB | 60.5 | 66 | Trend PASS, RS 66 (<80 threshold) |

---

## 4. Calibration History (v1.0 -> v1.1)

### Decision 17: MLB EPS CAGR 2Y Fwd 20% -> 15%
- Empirical finding: MSFT (17.5%), META (19.9%), V (19.4%), MA (17.1%) all blocked by 20%
- Impact: MLB pool 5 -> 20 stocks

### Decision 18: 3A Turnaround Path
- Empirical finding: CRWD, NET, DDOG, MDB, SNOW all have negative base EPS, CAGR formula returns None
- Solution: Alternative path checking EPS turnaround + revenue CAGR > 25%
- Impact: Enables 3A classification for loss-to-profit companies

### Decision 19: D/E OR Net Debt/EBITDA
- Empirical finding: AAPL (D/E 1.03), MA (2.56) blocked due to buyback-reduced equity
- Solution: Pass if D/E < 0.7 OR Net Debt/EBITDA < 3.0
- Impact: Buyback-heavy quality companies no longer penalized

---

## 5. Known Limitations

1. **Look-ahead bias**: yfinance provides only current financial snapshots, not point-in-time
2. **Survivorship bias**: Using current SP500/NDX constituents, not historical
3. **4-year financials**: yfinance typically returns 4 usable years (5th is NaN)
4. **No historical estimate snapshots**: Cannot track analyst revision momentum
5. **Turnaround path**: Still blocked by ROIC and PEG for most SaaS companies
6. **VCP false positives**: Detected in downtrending stocks (mitigated by Trend Template layer)
7. **RS rating**: Meaningful only with full universe (500+ stocks), not small subsets
8. **Execution time**: Full pipeline takes ~25 minutes for 476 tickers (first run)

---

## 6. Phase 1 Upgrade Triggers

Per SPEC 12.2, Phase 1 activates when:

1. Phase 0 validation complete (this report)
2. Paper trading 3 months verifies logic is reasonable
3. Budget approved for FMP Premium ($59/month)

### Phase 1 Scope
- Data source: yfinance -> FMP Premium
- Add quarterly financial history for precise EPS acceleration
- Begin monthly analyst estimate snapshots
- Implement backtest engine (vectorbt)
- Deploy frontend at research.investmquest.com/qgm/
