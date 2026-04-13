# QGM — 品質成長動能系統 (Quality Growth Momentum System)

用品質作為護欄、用技術抓時機。整合 Munger/Buffett 品質派與 Minervini/O'Neil 技術派的選股框架。

> 完整規格請參閱 [SPEC.md](SPEC.md)

---

## Phase 進度

| Phase | 名稱 | 狀態 |
|-------|------|------|
| Phase 0 | MVP（yfinance + 基礎回測） | 進行中 |
| Phase 1 | Production（FMP Premium + vectorbt） | 待開始 |
| Phase 2 | Advanced（Russell 3000 + 進階策略） | 待開始 |

---

## Stack

- **Python** 3.11+
- **資料**: yfinance
- **分析**: pandas, numpy
- **回測**: vectorbt (Phase 1)
- **視覺化**: plotly, matplotlib
- **報表**: Jinja2
- **CI/CD**: GitHub Actions

---

## Repo 結構

```
minervini-quality-backtest/
├── SPEC.md                          ← 規格書（Source of Truth）
├── README.md                        ← 本文件
├── configs/
│   └── params.yaml                  ← 所有可調參數
├── data/
│   ├── yf_loader.py                 ← yfinance 資料層
│   ├── cache/                       ← parquet 快取（.gitignore）
│   └── universe/                    ← 月度 universe 快照
├── screener/
│   ├── quality_core.py              ← MLB/3A 硬篩
│   ├── quality_score.py             ← 加分項計算
│   ├── pool_classifier.py           ← 分類邏輯
│   └── pool_transition.py           ← 升降級判定
├── patterns/
│   ├── trend_template.py            ← 8 條趨勢條件
│   ├── rs_rating.py                 ← IBD 式 RS
│   └── vcp_detector.py              ← Phase 0 MVP 版
├── backtest/
│   ├── engine.py                    ← 主引擎（vectorbt）
│   ├── exit_minervini.py            ← 出場 A
│   ├── exit_puremma.py              ← 出場 B
│   └── metrics.py                   ← 績效指標
├── live/
│   ├── daily_screener.py            ← 每日訊號
│   ├── live_trades.csv              ← Live tracking
│   └── monthly_report.py            ← 月報產出
├── reports/
│   ├── templates/                   ← Jinja2 HTML 模板
│   └── generator.py                 ← 靜態頁產出
├── notebooks/                       ← 視覺化 debug 用
├── tests/                           ← 測試
└── .github/
    └── workflows/                   ← CI/CD
```
