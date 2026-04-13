# QGM 品質成長動能系統 — 規格書

**Quality Growth Momentum System — Specification**

---

| 欄位 | 內容 |
|---|---|
| 版本 | v1.0 |
| 建立日期 | 2026-04-13 |
| 最後更新 | 2026-04-13 |
| 系統 Repo | `minervini-quality-backtest`（建議名稱） |
| 前端部署 | `research.investmquest.com/qgm/` |
| 當前 Phase | Phase 0（MVP，yfinance） |
| Source of Truth | 本文件為所有實作決策的唯一權威來源。程式碼、UI 文案、月報敘事如與本文件不一致，以本文件為準。 |

---

## 1. 系統目標與設計哲學

### 1.1 核心問題

傳統投資篩選框架存在二元對立：

- **純品質派（Munger/Buffett）**：重視護城河、長期 ROIC、穩定現金流。錯過早期爆發成長股（如早期 NVDA、SHOP）。
- **純技術派（Minervini/O'Neil）**：重視 Stage 2 趨勢、RS、VCP。會買到基本面脆弱的故事股，一旦風格切換回檔劇烈。

QGM 嘗試整合兩者：**用品質作為護欄、用技術抓時機**。品質層保證選股池不會有垃圾，技術層保證進場時機有動能，風險管理層（部位、停損）控制 3A 潛力股的不確定性。

### 1.2 設計原則

1. **雙層候選池（MLB + 3A）**：承認品質成熟股和成長加速股是不同物種，分池管理
2. **紀律補品質**：3A 股用更嚴格的技術門檻、更小部位、更緊停損來管理不確定性
3. **持股中狀態凍結**：進場時的池別鎖定，不因基本面變化改變風險管理規則
4. **慢升快降**：升級需 3 季持續達標，降級 2 季退化即觸發
5. **透明 Live Tracking**：系統啟動日起累積 out-of-sample 績效，不修改歷史
6. **5 年扎實 > 30 年虛張**：使用 yfinance 可得的 5 年資料，承認局限，不偽裝長歷史
7. **誠實標註代理**：財務護城河代理分標註為「推論」而非「評估」

### 1.3 關鍵設計決策記錄

以下為設計過程中做出的決策及理由，詳見第 13 節決策日誌。

| 決策 | 選擇 | 理由 |
|---|---|---|
| 期間長度 | 5 年（非 10 年） | yfinance 限制 + 更貼近當前公司形態 |
| EPS CAGR | 未來 2 年 + 過去 3 年 | FY+3 分析師資料離散度過高 |
| 護城河 | 加分項（非硬篩） | 避免代理分的假陰性誤殺好公司 |
| 資料源 | yfinance（Phase 0） | 先驗證邏輯，再付費升級 |
| 雙層池 | MLB + 3A | 同時捕捉品質股與早期爆發股 |
| 命名 | QGM（中性） | 避免 Minervini 商標疑慮 |
| 候選公開 | 完全公開 | 與主站透明定位一致 |
| 回測期 | 2020-2025 | 資料可得性 + 包含多次壓力測試 |

---

## 2. 資料層規格

### 2.1 資料源

**Phase 0（當前）**：yfinance（免費）
- 優點：零成本、API 穩定、覆蓋度足
- 限制：只有最新快照（無歷史分析師預估快照）、中型股以下財報覆蓋下降、有 rate limit

**Phase 1（未來）**：FMP Premium $59/月（年繳 ~$39/月）
- 當 MVP 驗證有 alpha 後升級
- 增加：quarterly 完整資料、分析師預估覆蓋更全、5 年內 point-in-time 資料

### 2.2 股票 Universe 定義

**主要池**：S&P 500 成分股 + NASDAQ 100 成分股（去重後約 550 支）

**原因**：
- yfinance 對大型股資料覆蓋最完整
- 分析師覆蓋人數足夠（> 10 位）保證預估可靠性
- 流動性充足，避免 QGM 訊號抓到無法實際進場的股票

**已知限制**：
- Survivorship bias：使用「當前」成分股，不是歷史成分股
- 回測報告需明確註明
- Phase 2 可考慮用 Russell 3000 歷史成分股（需付費資料源）

**排除規則**：
- SPAC、REIT、ADR（財務結構與一般企業不同）
- 上市未滿 3 年（資料不足計算過去 3 年 EPS CAGR）
- 市值 < $2B（流動性不足）

### 2.3 所需資料欄位清單

#### 2.3.1 價格與成交量（`Ticker.history`）

| 欄位 | 用途 | yfinance 來源 |
|---|---|---|
| Open/High/Low/Close/Volume | 日線 OHLCV | `history(period="5y")` |
| Adj Close | 除權息調整價 | `history(auto_adjust=True)` |

#### 2.3.2 當期財務快照（`Ticker.info`）

| 欄位 | QGM 用途 |
|---|---|
| `freeCashflow` | FCF Margin 分子 |
| `totalRevenue` | FCF Margin 分母、Revenue 基準 |
| `trailingPegRatio` | PEG 硬篩 |
| `forwardPE` | 備用 PEG 計算 |
| `debtToEquity` | D/E 硬篩（注意：yf 回傳 %，需 ÷100） |
| `totalCash` | 現金覆蓋負債 |
| `totalDebt` | 現金覆蓋負債 |
| `fiftyTwoWeekHigh` | 52W 高點距離 |
| `fiftyTwoWeekLow` | Trend Template |
| `numberOfAnalystOpinions` | 資料可靠性判斷（< 3 踢出） |
| `targetMeanPrice` | 參考用 |
| `marketCap` | Universe 篩選 |
| `beta` | WACC 代理計算（Phase 2） |

#### 2.3.3 分析師預估（`Ticker.earnings_estimate`）

| 期間 | 用途 |
|---|---|
| FY+1 EPS | EPS CAGR 2Y 分子 |
| FY+2 EPS | EPS CAGR 2Y 終值 |
| 當季 / 下季 EPS | 備用（未來可加加分項） |

#### 2.3.4 歷史財報（5 年 annual）

**income_stmt**：
- `Diluted EPS` → 過去 EPS CAGR、EPS 加速判斷
- `Total Revenue` → 營收成長、毛利率分母
- `Gross Profit` → 毛利率分子
- `Operating Income` / `EBIT` → ROIC 分子
- `Tax Provision` → 計算 NOPAT

**balance_sheet**：
- `Total Debt`
- `Total Equity` / `Stockholders Equity`
- `Invested Capital`（若無則用 Debt + Equity 合成）
- `Total Assets`

**cashflow**：
- `Free Cash Flow` → FCF Margin 歷史
- `Capital Expenditure` → CapEx/Rev

**quarterly_income_stmt**（5 季）：
- 用於 Minervini 式 EPS 加速判斷（最近 4 季 YoY 是否遞增）

### 2.4 計算欄位

系統內部計算的衍生指標：

| 欄位名 | 計算公式 |
|---|---|
| `fcf_margin` | `freeCashflow / totalRevenue` |
| `roic` | `(operating_income × (1 - 0.21)) / (total_debt + stockholders_equity)` |
| `eps_cagr_2y_fwd` | `(eps_fy2 / eps_ttm)^(1/2) - 1` |
| `eps_cagr_3y_trail` | `(eps_ttm / eps_3y_ago)^(1/3) - 1` |
| `gross_margin` | `gross_profit / total_revenue` |
| `capex_intensity_5y` | 5 年平均 `capex / revenue` |
| `rs_rating` | IBD 加權公式 percentile rank |
| `ma50` / `ma150` / `ma200` | `Close` 的滾動平均 |
| `dist_from_52w_high` | `(close - 52w_high) / 52w_high` |

### 2.5 Cache 策略

**儲存格式**：Parquet（小、快、保留 dtype）

**目錄結構**：
```
data/
├── cache/
│   ├── prices/
│   │   └── {ticker}_5y.parquet
│   ├── financials/
│   │   └── {ticker}_annual.parquet
│   │   └── {ticker}_quarterly.parquet
│   ├── estimates/
│   │   └── {ticker}_{YYYY-MM-DD}.parquet  # 每月快照（保留歷史）
│   └── info/
│       └── {ticker}_{YYYY-MM-DD}.parquet
└── universe/
    └── universe_{YYYY-MM}.parquet  # 每月快照
```

**更新頻率**：

| 資料 | 頻率 | 觸發時機 |
|---|---|---|
| 價格 | 每日 | GitHub Actions 交易日 06:00 TPE |
| 分析師預估 | 每月 1 日 | 累積歷史快照 |
| 財報 | 每季 | 依 earnings calendar 自動更新 |
| Universe 重分類 | 每月 1 日 | 產出月報 |

**快取失效**：
- 價格：當日更新後覆蓋
- 財報：當 `financials.columns.max()` 出現新日期時更新
- Estimates：**永不覆蓋舊快照**（用於建立歷史追蹤）

### 2.6 已知資料局限（需在回測報告聲明）

1. **Look-ahead bias**：yfinance 只給當前最新財報。回測進場決策理論上應使用當時可得的財報版本，但 Phase 0 無法做到
2. **Survivorship bias**：Universe 使用當前成分股
3. **Analyst estimates staleness**：FY+2 預估可能數月未更新
4. **Restated financials**：公司事後修正的財報會覆蓋原始版本

**緩解策略**：
- 回測頁面明確聲明這些 bias
- Live tracking 從系統上線日起沒有這些問題（天然乾淨）
- Phase 2 考慮付費資料源補齊

---

## 3. 品質篩選層規格

### 3.1 MLB 硬篩（6 條，全過才入 MLB 池）

| # | 條件 | 閾值 | 計算 |
|---|---|---|---|
| 1 | FCF Margin 當前 | **> 10%** | `fcf_margin > 0.10` |
| 2 | ROIC 當前 | **> 15%** | `roic > 0.15` |
| 3 | EPS CAGR 未來 2 年 | **> 20%** | `eps_cagr_2y_fwd > 0.20` |
| 4 | 過去 3 年 EPS CAGR | **> 15%** | `eps_cagr_3y_trail > 0.15` |
| 5 | PEG | **< 2** | `trailingPegRatio < 2.0` |
| 6 | D/E | **< 0.7** | `debtToEquity / 100 < 0.7` |

### 3.2 MLB 品質加分（6 項，合計 80 分）

通過硬篩後計算，用於排名。

| # | 項目 | 滿分 | 滿分條件 | 評分邏輯 |
|---|---|---|---|---|
| A | 5Y 正規化 FCF Margin | 15 | 可用年份均值 > 15% 且單年最低 > 10% | 達成得滿分，否則依比例遞減 |
| B | 5Y ROIC 穩定性（比例制） | 15 | ≥ 80% 可用年份 ROIC > 15% | ≥80% → 15 分，≥60% → 10 分，≥40% → 5 分，否則 0 分 |
| C | 5Y 毛利率趨勢（方向 + 韌性） | 10 | 方向分(0-5) + 下行波動分(0-5) | 見下方公式 |
| D | 資本密集度 | 10 | 可用年份平均 CapEx/Rev < 10% | < 10% 得 10 分，線性遞減至 20% 得 0 |
| E | 現金覆蓋總負債 | 10 | `totalCash > totalDebt` | 二元：是=10，否=0 |
| F | 財務護城河代理分 | 20 | 合成 0-10 → 乘以 2 | 見 3.5 |

**總分**：0-80，用於排名 percentile。

**B. ROIC 穩定性計算**：使用可用年份比例而非絕對年數，以適應 yfinance Phase 0 通常只有 4 年乾淨資料的現實。Phase 1 升級 FMP 後若取得 5 年完整資料，公式無需改動。

**C. GM 趨勢計算**（雙子分合成）：

```python
def gm_trend_score(annual_gm_series: pd.Series) -> tuple[int, dict]:
    """
    annual_gm_series: 可用年份的 Gross Margin（按時間順序，oldest first）
    回傳 (total_score 0-10, breakdown dict)
    """
    gm_oldest = annual_gm_series.iloc[0]
    gm_newest = annual_gm_series.iloc[-1]
    gm_avg = annual_gm_series.mean()

    # === 方向分（0-5）===
    # 用相對變化率（非 pp），跨產業公平
    gm_change_pct = (gm_newest - gm_oldest) / gm_oldest

    if gm_change_pct >= 0.05:      # 提升 ≥ 5%
        direction = 5
    elif gm_change_pct >= 0:        # 持平或微升
        direction = 3
    elif gm_change_pct >= -0.05:    # 微降 < 5%
        direction = 1
    else:                            # 明顯下降
        direction = 0

    # === 下行波動分（0-5）===
    # 只看 YoY 下降幅度，上升不計入
    yoy_changes = annual_gm_series.diff().dropna()
    declines = yoy_changes[yoy_changes < 0].abs()

    if len(declines) == 0:
        downside = 5               # 從未下降
    else:
        max_decline_relative = declines.max() / gm_avg
        if max_decline_relative < 0.05:    # 最大單年降幅 < 平均 GM 的 5%
            downside = 4
        elif max_decline_relative < 0.10:  # < 10%
            downside = 2
        else:
            downside = 0

    return direction + downside, {...}
```

### 3.3 3A 硬篩（6 條，全過才入 3A 池）

| # | 條件 | 閾值 | 意義 |
|---|---|---|---|
| 1 | FCF Margin 當前 | **> 0%** | 不燒錢 |
| 2 | ROIC 當前 | **> 5%** 或改善中 | 寬鬆門檻 |
| 3 | EPS CAGR 未來 2 年 | **> 30%** | 加速度必須更強 |
| 4 | 過去 3 年 EPS CAGR | **> 25%** | 已有加速軌跡 |
| 5 | PEG | **< 2** | 同 MLB |
| 6 | D/E | **< 0.7** | 同 MLB |

### 3.4 3A 成長證據（至少滿足一條）

通過 3A 硬篩後，還需以下至少一項：

| 指標 | 閾值 | 計算 |
|---|---|---|
| 最近 4 季 EPS YoY 連續加速 | Q-4 < Q-3 < Q-2 < Q-1（YoY 成長率遞增） | 從 quarterly_income_stmt 計算 |
| 最近 4 季營收 YoY | > 25% | 同上 |
| 分析師 EPS 上修動能 | > 5% | **需有歷史快照資料，Phase 0 可能無法計算** |

**Phase 0 實務**：若無分析師歷史快照，前兩項擇一即可。

### 3.5 財務護城河代理分公式

**範圍**：0-10 分，乘以 2 得到 0-20 加分。

```python
def moat_proxy_score(annual_data: dict) -> float:
    """
    annual_data: 可用年份的年度財務資料
    回傳 0-10 分
    """
    # 1. GM 韌性 (0-4 分) — 沿用 GM Trend 底層邏輯
    gm_trend_total, _ = gm_trend_score(annual_data['gross_margin'])
    gm_resilience = (gm_trend_total / 10) * 4
    # GM Trend 滿分 10 → 韌性滿分 4

    # 2. 5Y ROIC 平均 (0-3 分) — 不變
    roic_avg = annual_data['roic'].mean()
    roic_score = max(0, min(3, roic_avg * 10))
    # ROIC 30% → 3 分, ROIC 0% → 0 分

    # 3. 營收成長一致性 (0-3 分) — 比例制
    rev_growth = annual_data['revenue'].pct_change().dropna()
    positive_years = (rev_growth > 0).sum()
    available_years = len(rev_growth)
    consistency_score = min(3, (positive_years / available_years) * 3.75)
    # 100% 正成長 → 3 分，80% → 3 分，75% → 2.81 分

    return gm_resilience + roic_score + consistency_score
```

**UI 標註**：必須顯示為「財務護城河代理分」，並說明為推論而非質化評估。

### 3.6 邊界處理

| 情境 | 處理 |
|---|---|
| 新 IPO 上市 < 3 年 | 排除於 Universe 外 |
| 財報某一季缺失 | 用前後季內插；若 > 2 季連續缺失則排除 |
| 分析師覆蓋 < 3 位 | 排除於 Universe 外 |
| 股票分割/合併 | 依 yfinance 自動調整（`auto_adjust=True`） |
| 財報貨幣非 USD | 排除於 Universe 外（Phase 0 只做 USD） |
| `totalDebt` 為 0 | D/E 視為 0，通過 |
| `freeCashflow` 為負 | MLB 不過；3A 看其他條件 |
| 財報重大變更（如會計準則改變） | 人工介入判斷，可能暫時排除 |

---

## 4. 技術篩選層規格

### 4.1 Trend Template（Minervini 原版 8 條）

適用於 MLB 和 3A 池的所有候選。

| # | 條件 | 計算 |
|---|---|---|
| 1 | 收盤價 > MA150 且 > MA200 | `close > ma150 and close > ma200` |
| 2 | MA150 > MA200 | 多頭排列 |
| 3 | MA200 上升 ≥ 1 個月 | `ma200[-1] > ma200[-21]` |
| 4 | MA50 > MA150 > MA200 | 完整多頭排列 |
| 5 | 收盤價 > MA50 | 短期強勢 |
| 6 | 收盤價距 52W 低點 > 30% | `(close - 52w_low) / 52w_low > 0.30` |
| 7 | 收盤價距 52W 高點 < 25% | `(52w_high - close) / 52w_high < 0.25` |
| 8 | RS Rating ≥ 門檻 | MLB ≥ 80 / 3A ≥ 90 |

**全過才算 Trend Confirmed**。

### 4.2 RS Rating 計算

**IBD 加權公式**：

```python
def rs_score(prices: pd.Series) -> float:
    """
    prices: 最近 252 日收盤價
    回傳原始 RS score（用於池內 ranking）
    """
    # 週期報酬
    r_3m = prices[-1] / prices[-63] - 1   # 63 交易日 ≈ 3 個月
    r_6m = prices[-1] / prices[-126] - 1
    r_9m = prices[-1] / prices[-189] - 1
    r_12m = prices[-1] / prices[-252] - 1
    
    # IBD 權重
    return 0.4 * r_3m + 0.2 * r_6m + 0.2 * r_9m + 0.2 * r_12m
```

**Percentile Ranking**：對整個 Quality Universe 的 RS score 做 1-99 排名。

```python
def rs_rating(all_rs_scores: pd.Series, ticker_rs: float) -> int:
    """回傳 1-99 的整數 rating"""
    percentile = (all_rs_scores < ticker_rs).sum() / len(all_rs_scores)
    return int(percentile * 99) + 1
```

**門檻**：
- MLB 池：RS ≥ 80
- 3A 池：RS ≥ 90

### 4.3 Moving Average 計算

使用**調整後收盤價**（除權除息後）計算。

```python
ma50 = close.rolling(50).mean()
ma150 = close.rolling(150).mean()
ma200 = close.rolling(200).mean()
```

**起始點**：MA200 需要至少 200 個交易日資料。新上市股票如資料不足，Trend Template 自動失敗。

---

## 5. VCP 偵測規格

### 5.1 Phase 0 MVP 版

**偵測目標**：簡化版波動收斂 + 量縮。

**演算法**：

```python
def detect_vcp_mvp(prices: pd.Series, volumes: pd.Series, 
                   lookback_days: int = 60) -> dict:
    """
    簡化 VCP：
    1. 最近 60 日最大回檔 < 25%
    2. 最近 20 日標準差 < 最近 60 日標準差 × 0.7（波動收斂）
    3. 最近 10 日平均量 < 最近 50 日平均量 × 0.7（量縮）
    
    回傳 dict:
        is_vcp: bool
        pivot_price: float (最近 20 日高點)
        volatility_ratio: float
        volume_ratio: float
    """
    recent = prices[-lookback_days:]
    
    # 1. 最大回檔
    max_drawdown = (recent.max() - recent.min()) / recent.max()
    cond_drawdown = max_drawdown < 0.25
    
    # 2. 波動收斂
    recent_std = prices[-20:].std()
    longer_std = prices[-60:].std()
    vol_ratio = recent_std / longer_std
    cond_volatility = vol_ratio < 0.7
    
    # 3. 量縮
    recent_vol = volumes[-10:].mean()
    avg_vol = volumes[-50:].mean()
    volume_ratio = recent_vol / avg_vol
    cond_volume = volume_ratio < 0.7
    
    # Pivot = 最近 20 日高點
    pivot = prices[-20:].max()
    
    return {
        'is_vcp': cond_drawdown and cond_volatility and cond_volume,
        'pivot_price': pivot,
        'volatility_ratio': vol_ratio,
        'volume_ratio': volume_ratio,
    }
```

### 5.2 Phase 2 完整版（未來）

- Base 識別（從 52W 高回落 10-35%、整理期 ≥ 5 週）
- Contraction 序列（至少 3 段遞減 pullback）
- Base count（從前一波 Stage 2 起算第幾個 base）
- Handle 偵測（cup-with-handle 的 5-15% 小回檔）
- Shakeout 偵測（假跌破 + 快速收復）

**此部分 Phase 0 不實作**，待 MVP 驗證邏輯後再升級。

### 5.3 Pivot Breakout 確認

當日進場訊號（Breakout Signal）需同時滿足：

| 條件 | MLB | 3A |
|---|---|---|
| 收盤價 > pivot × 1.001 | ✓ | ✓ |
| 當日 volume > 50MA volume × 1.4 | ✓ | 1.5 |
| Trend Template 8 條全過 | ✓ | ✓ |
| RS Rating | ≥ 80 | ≥ 90 |
| VCP 成立 | ✓ | ✓ |

**訊號觸發**：次一交易日開盤進場（非當日）。

### 5.4 可調參數表

所有閾值集中在 `configs/params.yaml`：

```yaml
quality_filter:
  mlb:
    fcf_margin_min: 0.10
    roic_min: 0.15
    eps_cagr_2y_fwd_min: 0.20
    eps_cagr_3y_trail_min: 0.15
    peg_max: 2.0
    debt_to_equity_max: 0.7
  triple_a:
    fcf_margin_min: 0.0
    roic_min: 0.05
    eps_cagr_2y_fwd_min: 0.30
    eps_cagr_3y_trail_min: 0.25
    peg_max: 2.0
    debt_to_equity_max: 0.7

technical_filter:
  mlb:
    rs_rating_min: 80
    volume_breakout_multiplier: 1.4
  triple_a:
    rs_rating_min: 90
    volume_breakout_multiplier: 1.5

vcp:
  lookback_days: 60
  max_drawdown: 0.25
  volatility_ratio_threshold: 0.7
  volume_ratio_threshold: 0.7

position_management:
  mlb:
    max_position_pct: 25
    stop_loss_pct: -7
    profit_take_pct: 22.5
  triple_a:
    max_position_pct: 15
    stop_loss_pct: -6
    profit_take_pct: 17.5
  max_concurrent_positions: 6
```

---

## 6. 升降級機制

### 6.1 3A → MLB 升級

**條件**（需全部滿足）：

1. FCF Margin ≥ 10% **連續 3 季 TTM**
2. ROIC ≥ 15% **連續 3 季 TTM**
3. 當期其他 MLB 硬篩條件全過（EPS CAGR 2Y 未來 > 20%、過去 3Y > 15%、PEG < 2、D/E < 0.7）

**注意**：升級不要求繼續滿足 3A 的「成長加速證據」——因為升級本身意味著從爆發期進入成熟期。

### 6.2 MLB → 3A 降級

**條件**（滿足任一即降）：

1. FCF Margin **連續 2 季 < 10%**
2. ROIC **連續 2 季 < 15%**
3. EPS CAGR 預估 **連續 2 季下修幅度 > 15%**

**降級後**：重新檢查是否符合 3A 硬篩。若不符合，直接踢出池。

### 6.3 踢出 Universe 條件

**任一觸發即踢出（無論 MLB 或 3A）**：

| 條件 | 閾值 |
|---|---|
| EPS CAGR 預估 | 連續 2 季 < 15% |
| D/E | 當期 > 1.0 |
| 分析師覆蓋 | < 3 位 |
| 股價 | 連續 3 個月跌破 MA200 |
| 重大會計事件（重編、SEC 調查等） | 立即，需人工介入 |

**踢出後**：進入「觀察名單」（watch list），每月重評是否符合任一池條件。

### 6.4 持股中狀態凍結（關鍵設計）

**原則**：進場時的池別鎖定在 position 物件上，不因基本面變化改變風險管理規則。

```python
position = {
    'ticker': 'NVDA',
    'entry_date': '2026-04-13',
    'entry_pool': '3A',           # ← 鎖定，持倉期間不變
    'entry_price': 145.80,
    'stop_loss': 137.05,          # 依 entry_pool 規格 (-6%)
    'position_size_pct': 15,      # 依 entry_pool 規格
    'profit_take_pct': 17.5,      # 依 entry_pool 規格
}
```

**範例**：某股以 3A 規格進場（15% 部位、-6% 停損），持股期間升級至 MLB。此 position 的停損、部位上限、獲利了結都**維持 3A 規格**。只有未來**新的進場訊號**才會適用 MLB 規格。

### 6.5 降級不自動清倉

MLB 股降級至 3A 或被踢出 Universe 時：

- **技術停損、MA 出場規則照進場時的規格執行**
- **UI 標註警示**（候選頁、風險監控面板）
- **人工判斷是否主動出場**

此設計保留人類判斷空間，避免「一季財報差就自動賣掉長期贏家」的錯誤。

### 6.6 Transition Event Log

每月產出升降級事件記錄，格式：

```json
{
  "month": "2026-04",
  "events": [
    {
      "date": "2026-04-01",
      "ticker": "XYZ",
      "type": "upgrade",
      "from": "3A",
      "to": "MLB",
      "reason": "FCF Margin 連續 3 季 > 10% (8% → 11% → 12% → 13%)",
      "notable": true
    },
    {
      "date": "2026-04-01",
      "ticker": "ABC",
      "type": "downgrade",
      "from": "MLB",
      "to": "3A",
      "reason": "FCF Margin 從 16% 降至 8%，連續 2 季不達門檻"
    },
    {
      "date": "2026-04-01",
      "ticker": "DEF",
      "type": "kickout",
      "from": "MLB",
      "to": null,
      "reason": "EPS 預估連續下修 -18%"
    },
    {
      "date": "2026-04-01",
      "ticker": "GHI",
      "type": "entry",
      "from": null,
      "to": "3A",
      "reason": "首次符合 3A 條件，EPS YoY 加速中"
    }
  ]
}
```

### 6.7 接近升級標記

3A 池中**已滿足 2 季但差 1 季即升級**的股票，UI 特別標註：

```python
def is_approaching_mlb(last_2q: pd.DataFrame, current: dict) -> bool:
    """差 1 季即升級"""
    return all([
        (last_2q['fcf_margin'] >= 0.10).all(),
        (last_2q['roic'] >= 0.15).all(),
        passes_mlb_hard_filter_excluding_stability(current),
    ])
```

UI 顯示：`📈 接近升級（再 1 季達標）`

---

## 7. 回測設計

### 7.1 基本設定

| 項目 | 設定 |
|---|---|
| 回測期間 | 2020-01-01 ~ 2025-12-31（5 年） |
| 初始資金 | $100,000 USD |
| 最大同時持倉 | 6 檔 |
| 資料頻率 | 日線 |
| Universe | 當前 S&P 500 + NASDAQ 100（承認 survivorship bias） |

### 7.2 進出場規則

**進場**：Pivot Breakout 訊號觸發的次一交易日開盤價。

**出場系統 A（Minervini 原版）**：
- 硬停損：MLB -7% / 3A -6%（從進場價）
- 跌破 MA50 且收盤 → 全部退出
- 獲利 +22.5% (MLB) / +17.5% (3A) → 賣一半，剩餘移動停損至成本
- 連續 3 日跌破 MA21 → 退出

**出場系統 B（Pure MA 出場）**：
- 使用你現有的 Pure MA 系統出場邏輯（具體規則待你確認並補入此節）

**兩套獨立回測，產出對比表。**

### 7.3 部位管理

| 情境 | MLB | 3A |
|---|---|---|
| 單筆部位上限 | 25% AUM | 15% AUM |
| 訊號同時觸發優先 | 品質加分高者 | 品質加分高者 |
| 已滿 6 檔時新訊號 | 忽略，等待空位 | 同 |

### 7.4 交易成本假設

- 滑點：0.10%（IBKR 實測）
- 手續費：0.05%（IBKR 階梯費率）
- 每次交易總成本：約 0.15%

### 7.5 Benchmark（5 條對比線）

1. **SPY Buy & Hold**
2. **QQQ Buy & Hold**
3. **純技術策略**（不做品質篩，只用 Trend Template + VCP）
4. **QGM Pure MLB**（只進場 MLB 候選）
5. **QGM Pure 3A**（只進場 3A 候選）
6. **QGM Full**（MLB + 3A 混合）

### 7.6 報告指標

| 指標 | 計算 |
|---|---|
| CAGR | 年化報酬率 |
| Max Drawdown | 最大回撤 |
| Sharpe Ratio | 超額報酬 / 年化波動（Rf = 4%） |
| Calmar Ratio | CAGR / Max DD |
| Sortino Ratio | 超額報酬 / 下行波動 |
| 勝率 | 獲利交易 / 總交易 |
| 平均盈虧比 | 平均獲利 / 平均虧損 |
| 年度無虧損數 | 正報酬年份數 |
| Turnover | 年度持倉變動率 |
| 平均持倉天數 | |
| 最大連續虧損 | |
| **2022 熊市表現** | 單獨列出 |
| **COVID 崩盤表現** | 2020 Q1 單獨列出 |
| MLB 貢獻 vs 3A 貢獻 | 分解 |

### 7.7 Walk-Forward 驗證

- 訓練期：2020-01-01 ~ 2023-12-31（4 年）
- 驗證期：2024-01-01 ~ 2025-12-31（2 年）
- 確認參數在訓練期優化後，驗證期表現是否 degradation

---

## 8. Live Tracking

### 8.1 系統啟動

| 項目 | 設定 |
|---|---|
| 預計啟動日 | 2026-05-01 |
| 初始虛擬資金 | $100,000 |
| 訊號發布時間 | 每日 06:00 TPE（美股盤後） |

### 8.2 live_trades.csv 格式

單一資料源，每月追加，**絕不修改歷史記錄**。

```csv
entry_date,ticker,entry_pool,entry_price,position_size_pct,stop_loss,profit_take,exit_date,exit_price,exit_reason,pnl_pct,pnl_usd,notes
2026-05-01,NVDA,3A,145.80,15,137.05,171.07,,,,,
```

**欄位說明**：
- `entry_date`: 進場日期
- `entry_pool`: MLB 或 3A（鎖定）
- `exit_reason`: stop_loss / profit_take / trend_break / manual
- 未出場時後段欄位空白

### 8.3 In-Sample vs Out-of-Sample 呈現

回測頁明確分區：

```
Section A: In-Sample（2020-2025 歷史回測）
Section B: Out-of-Sample（Live Tracking，從 2026-05 起）
Section C: 兩者 CAGR / Max DD 對比（degradation 分析）
```

### 8.4 修正版本控制

演算法若在系統上線後修改（例如調整閾值），**不重跑歷史 Live 段**。新邏輯從修改日起套用，並在回測頁明確紀錄：

```
2026-08-01: 參數調整
- VCP volatility_ratio_threshold 從 0.7 改為 0.65
- 修改前 Live 績效：CAGR +5.2%
- 修改後 Live 績效：（從此日起累積）
```

---

## 9. 前端呈現規格

### 9.1 URL 結構

```
research.investmquest.com/qgm/
├── index.html            # 主頁：狀態條 + 候選 + 方法論摘要
├── candidates.html       # 當日突破訊號（每日更新）
├── universe.html         # Quality Universe 完整列表（月度更新）
├── backtest.html         # 回測報告 + Live Tracking
├── methodology.html      # 完整方法論（純內容頁）
└── monthly/              # 月報歸檔
    └── 2026-05.html
```

### 9.2 候選卡片規格

**MLB 卡片**：
- 實線邊框
- 左上 tag：`⚾ MLB - All-Star/Starter/Roster`
- 顯示品質加分（如 72/80）
- 部位建議：至多 25% AUM
- 停損：-7%

**3A 卡片**：
- 虛線邊框
- 左上 tag：`🚀 3A`
- 顯示「品質待驗證」+ 未達 MLB 門檻的警示
- 部位建議：至多 15% AUM
- 停損：-6%

**兩者共有欄位**：
- Ticker、當前價、當日漲跌、成交量倍數
- RS Rating、VCP 收斂段數
- Pivot 價、風險點（停損點）
- Mini 6M 日線圖（SVG）
- 基本面快照（FCF、ROIC、EPS CAGR、PEG、D/E）
- 系統備註（加分理由、警示因素）

### 9.3 Quality Universe 表格欄位

```
| Ticker | 池別 | 在池時間 | 品質分 | FCF% | ROIC | EPS CAGR (fwd/trail) | RS | Stage | 狀態變動 |
```

**互動性**：
- 可排序（預設 品質分 desc）
- 可篩選（MLB / 3A / 全部）
- 可搜尋（ticker）
- 使用 DataTables.js

**狀態變動欄位**：
- `—`：本月無變動
- `🎉 升級`：3A → MLB（本月）
- `⚠️ 降級`：MLB → 3A（本月）
- `📈 接近升級`：3A 再 1 季達標
- `🆕 新進`：本月新入池

### 9.4 UI 文案統一

| 概念 | 對外使用詞彙 | 避免使用 |
|---|---|---|
| 系統名 | QGM / 品質成長動能系統 | Minervini 系統 |
| 品質池 | Quality Universe | 白名單、選股池 |
| 主力池 | MLB / 主力 | 大聯盟（避免棒球用語過度） |
| 潛力池 | 3A / 潛力 | 小聯盟、B 級 |
| 技術形態 | VCP / 波動收斂形態 | - |
| 相對強度 | RS Rating / 相對強度 | - |
| 突破 | 樞紐突破 / Pivot Breakout | 買入訊號、進場點 |
| 護城河分數 | **財務護城河代理分** | 護城河評級（誤導） |
| 入場價 | 入場參考價 | 買進價（法律考量） |
| 停損 | 風險參考點 | 停損（中性描述） |
| 品質評分 | 品質分（X/80） | 分數、評級 |

### 9.5 公開度原則

- **所有候選（MLB + 3A）完全公開**
- 頂部固定區塊標明「非投資建議」
- 訊號發布時間明確（每日 06:00 TPE）
- 免責條款連結：/disclaimer
- AI 揭露：/ai-disclosure

### 9.6 視覺風格

- 字體：Fraunces（Serif 標題）+ Noto Serif TC（中文）+ JetBrains Mono（數據）
- 配色：米白背景 + 深紅強調（#8b0000）+ 深綠（成功）+ 琥珀（警示）
- 風格：編輯級金融刊物（類似 FT / Stratechery）
- 不使用：漸層紫、Inter 字體、一般 SaaS 風格

---

## 10. 基礎設施

### 10.1 Repo 結構

```
minervini-quality-backtest/
├── SPEC.md                          ← 本文件
├── README.md                        ← 快速開始指南
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
│   ├── live_trades.csv              ← Live tracking 單一資料源
│   └── monthly_report.py            ← 月報產出
├── reports/
│   ├── templates/                   ← Jinja2 HTML 模板
│   │   ├── index.html.j2
│   │   ├── candidates.html.j2
│   │   ├── universe.html.j2
│   │   └── backtest.html.j2
│   └── generator.py                 ← 靜態頁產出
├── notebooks/                       ← 視覺化 debug 用
│   └── vcp_calibration.ipynb
├── tests/
│   ├── test_quality_filter.py
│   ├── test_rs_rating.py
│   └── test_vcp_detector.py
└── .github/
    └── workflows/
        ├── daily_screener.yml       ← 每日 cron
        └── monthly_report.yml       ← 每月 cron
```

### 10.2 GitHub Actions Cron

**daily_screener.yml**：
- Schedule: 每交易日 22:00 UTC（= 次日 06:00 TPE，美股盤後）
- Steps:
  1. Checkout + setup Python
  2. 拉取 yfinance 資料（差額更新 cache）
  3. 跑 trend template + VCP 偵測
  4. 產出 `candidates.html`
  5. Commit + push to `research.investmquest.com` repo
  6. LINE Notify 推送（如有新訊號）

**monthly_report.yml**：
- Schedule: 每月 1 日 00:00 TPE
- Steps:
  1. 重跑 Quality Universe 分類
  2. 產出 transition events
  3. 重跑最新的回測（含 Live tracking 更新）
  4. 產出月報 HTML
  5. 發送 Email 摘要（SendGrid）

### 10.3 通知

**LINE Notify**：
- 當日突破訊號（每日 06:00 TPE）
- 格式：「今日 QGM 訊號：MLB 2 支（NVDA, LULU），3A 1 支（XYZ）」

**Email（SendGrid，複用 morning-briefing 架構）**：
- 每月月報發送
- 訂閱者列表（手動維護或接 Substack）

### 10.4 部署

- 靜態 HTML 產出後 push 到 `research.investmquest.com` repo
- GitHub Pages 自動部署
- 自訂域名：`research.investmquest.com/qgm/*`

---

## 11. 命名規範

### 11.1 系統對外命名

| 對內（程式、SPEC） | 對外（UI、方法論、行銷） |
|---|---|
| QGM | 品質成長動能系統 / QGM |
| MLB pool | 主力池 / MLB |
| 3A pool | 潛力池 / 3A |
| Quality Universe | Quality Universe / 品質池 |

### 11.2 去商標化對照

| 原始術語（內部參考） | 對外稱呼 |
|---|---|
| Minervini Trend Template | 趨勢健康度 8 條 |
| SEPA | QGM 框架 |
| VCP (Volatility Contraction Pattern) | 波動收斂形態 / VCP（縮寫可保留，技術通用術語） |
| IBD RS Rating | 相對強度排名 / RS Rating |
| Stage Analysis | 階段分析（Weinstein 原創，通用） |
| CAN SLIM | 不直接使用 |

### 11.3 程式命名慣例

- 變數：`snake_case`（Python 標準）
- 類別：`PascalCase`
- 常數：`UPPER_SNAKE_CASE`
- 英文優先（方便未來協作）
- 註解可中文（內部理解用）

---

## 12. Phase 規劃

### 12.1 Phase 0：MVP（當前）

**目標**：驗證邏輯可行性，產出第一版系統。

**時程**：5-8 週

**交付物**：
- `yf_loader.py` + `quality_core.py` + `quality_score.py`
- `pool_classifier.py` + `pool_transition.py`
- `trend_template.py` + `rs_rating.py`
- `vcp_detector.py`（MVP 簡化版）
- 2020-2025 回測結果
- `/qgm/` 前端 4 頁（index, candidates, universe, methodology）

**驗收標準**：
- S&P 500 + NASDAQ 100 完整跑通，無 crash
- Quality Universe 月度快照合理（人工抽查 10 支）
- VCP 偵測在歷史已知案例（2020 NVDA、2021 MRNA）能抓到
- 回測結果優於 SPY Buy & Hold（至少 CAGR +3% 或 Sharpe +0.2）

**預算**：$0/月

### 12.2 Phase 1：Production（MVP 驗證後）

**觸發條件**：Phase 0 驗收通過 + Paper trading 3 個月驗證邏輯合理。

**升級項目**：
- 資料源：yfinance → FMP Premium $59/月（年繳 ~$39/月）
- 加入季度財報（Minervini 式 EPS 加速更精準）
- 從當月開始每月存分析師預估快照（累積歷史）
- 啟動正式 Live Tracking

### 12.3 Phase 2：Advanced（運行 6-12 個月後）

**觸發條件**：Live Tracking 累積 6+ 個月，系統有明確 alpha 證據。

**升級項目**：
- VCP 完整版（base count + handle + shakeout）
- 分析師上修動能加分項（需 6 個月累積的快照）
- 敏感度分析（grid search 關鍵參數）
- Walk-forward validation

### 12.4 Phase 3：Optional（選配）

- 付費 Morningstar Wide Moat Rating 整合
- Russell 3000 歷史成分股（需付費資料源）
- Point-in-time 財報與分析師預估
- 全球市場擴展（Japan, Malaysia）

---

## 13. 決策日誌

記錄關鍵設計決策的日期、內容、理由。未來回看時提供 context。

### 2026-04-13

**決策 1：資料期間 10 年 → 5 年**
- 理由：yfinance 限制（約 4-5 年歷史）、5 年涵蓋多次壓力測試、更貼近當前公司形態
- 影響：ROIC 穩定性從「10 年 ≥ 70%」改為「5 年 ≥ 80%（4/5 年）」

**決策 2：EPS CAGR 3 年 → 2 年 + 過去驗證**
- 理由：FY+3 分析師預估離散度高、覆蓋度低；加入過去 3 年實際 CAGR 作為 sanity check
- 影響：雙重驗證「未來 2Y > 20% + 過去 3Y > 15%」

**決策 3：護城河從硬篩降為加分項**
- 理由：代理分有假陽性（疫情期 Peloton）和假陰性（轉型期 Adobe）風險；避免誤殺
- 影響：護城河代理分 → 加分項 F，權重 20

**決策 4：資料源選擇 yfinance**
- 理由：MVP 階段先驗證邏輯，不先付費；yfinance 足以跑通整個系統
- 影響：承認 look-ahead bias 與 survivorship bias，在報告中聲明

**決策 5：候選池雙層化（MLB + 3A）**
- 理由：純品質派錯過早期爆發股；純技術派選到垃圾；分層設計兼顧兩者
- 影響：新增 3A 規格、升降級機制、持股凍結原則

**決策 6：系統命名 QGM（非 Minervini）**
- 理由：避免商標疑慮，建立獨立品牌識別
- 影響：對外文案全面去 Minervini 化，方法論頁低調致謝

**決策 7：候選頁完全公開**
- 理由：與主站「AI-disclosure + 透明」定位一致；內容行銷價值高
- 影響：候選頁有免責條款、訊號發布時間明確（06:00 TPE）

**決策 8：回測頁每月重跑**
- 理由：建立即時追蹤紀錄；live tracking 本身是最有價值的信用資產
- 影響：In-Sample + Out-of-Sample 分區呈現；修改參數不重跑歷史 Live 段

**決策 9：持股中狀態凍結**
- 理由：避免升降級造成風險管理規則中途改變
- 影響：`entry_pool` 欄位鎖定於 position 物件

**決策 10：升降級採持續性門檻（非即時）**
- 理由：避免單季跳點造成頻繁進出
- 影響：升級需連續 3 季達標、降級需連續 2 季退化

**決策 11：MLB FCF Margin 15% → 10%**
- 理由：承認中型成長股擴張期合理的利潤率水準；配合 3A FCF > 0% 形成清楚分層
- 影響：MLB 池範圍略擴大，預期池大小 60-80 支

### 2026-04-13（續）

**決策 12：接受極端 EPS CAGR 作為真實訊號**
- 觸發：NVDA 2023-2026 trailing 3Y EPS CAGR = 204%（FY2023 $0.174 → FY2026 $4.90，split-adjusted）
- 現象：經驗證為真實計算結果，非 bug
- 決定：不對 CAGR 設上限截斷
- 理由：
  1. split-adjusted EPS 比較是數學正確的
  2. 硬篩只要求 > 15%，extreme value 不影響入池判斷
  3. 人為截斷反而引入 bias（誰決定 100% 還是 200% 是天花板？）
- 但留意：
  - 極端 trailing CAGR 可能反映「爆發已發生」（late-stage）而非「爆發正在發生」
  - 未來若 CAGR 進入加分項排名計算，需考慮用 log 或 rank 壓縮 outlier
  - 3A 池本來就假設成長在前段，NVDA 這種案例反而應該在 MLB 池（已驗證的成熟高成長）
- 影響：目前無程式影響；未來若有加分項用到 trailing CAGR 需重新設計

**決策 13：比例制取代絕對年數**
- 觸發：yfinance Phase 0 三支測試股（NVDA/LULU/GLW）均只有 4 年乾淨財報（第 5 年為 NaN）
- 決定：所有「5Y 穩定性/一致性」類評分改用可用年份比例，而非絕對年數
- 理由：
  1. Phase 0 穩定只有 4 年，Phase 1 升級 FMP 可能有 5 年完整資料
  2. 比例制可無痛適應不同年份數，不用改門檻
  3. 語義更清楚（「75% 的年份達標」vs「3/4 年但門檻寫 4/5 年」）
- 影響：SPEC 3.2 項目 B（ROIC 穩定性）、項目 C（GM 趨勢）、SPEC 3.5 Moat Proxy 營收一致性

**決策 14：GM Trend 採方向 + 下行波動拆分**
- 觸發：NVDA GM 從 56.9% 結構性提升至 71.1%（AI 定價權），但 std=0.0816 被原公式判為「不穩定」（2.37/4 分）
- 決定：拆為方向分（0-5）+ 下行波動分（0-5），取代原本的 std 反向計分
- 理由：
  1. 原公式無法區分「GM 往上波動」和「GM 往下波動」
  2. 結構性提升（護城河強化）不應被懲罰
  3. 只看下行波動的幅度更符合護城河韌性的語義
- 影響：SPEC 3.2 項目 C、SPEC 3.5 Moat Proxy 中的 GM 子項連動修訂

**決策 15：所有波動性指標用相對值**
- 觸發：決策 14 設計過程中發現，用 absolute pp 門檻（如「最大降幅 < 3pp」）對不同 GM 水準的公司不公平（GM 30% 降 3pp = -10%，GM 70% 降 3pp = -4.3%）
- 決定：所有波動幅度用相對值（decline / avg GM），不用 absolute pp
- 理由：跨產業公平性。低 GM 行業（工業、零售）vs 高 GM 行業（軟體、半導體）應同一把尺
- 影響：SPEC 3.2 項目 C 的下行波動門檻定義

---

## 附錄 A：待確認項目（`[TBD]`）

以下項目尚需確認，不阻擋 Phase 0 執行但需儘快決定：

1. **Pure MA 出場規則的完整描述**（回測系統 B 需要）
2. **3A 「ROIC > 5% 或改善中」的「改善中」具體定義**（建議：YoY 提升 > 2 個百分點）
3. **Phase 0 是否實作分析師上修動能加分項**（需歷史快照，建議略過，等 Phase 1）
4. **月報 Email 訂閱者名單管理**（手動 vs 接 Substack API）
5. **Live Tracking 是否需要虛擬 IBKR 帳戶對接**（或純 CSV 夠用）
6. **[待決定] 加分項是否引入 trailing EPS CAGR 及其 outlier 處理**（相關：決策 12）

---

## 附錄 B：常見問題（Q&A）

**Q: 為什麼不用 Russell 3000？**
A: yfinance 對小型股的財報覆蓋下降，且 Russell 3000 歷史成分股需付費。Phase 0 先用 S&P 500 + NDX，資料品質最有保證。

**Q: 3A 股最後會變成垃圾股嗎？**
A: 會有一部分變成。但透過：(1) 更嚴格的技術門檻（RS ≥ 90）、(2) 更小部位（15%）、(3) 更緊停損（-6%）、(4) 更早獲利了結（+17.5%），單支 3A 失敗的總體損失可控。系統級期望：3A 貢獻整體 alpha 的 30-50%，但風險貢獻 < 25%。

**Q: 為什麼不做基本面 + 技術面同時即時篩？**
A: 基本面變化慢（季度），技術面變化快（日度）。分層設計讓月頻和日頻任務分離，不需每日重算基本面。

**Q: MLB 和 3A 同時都有訊號時怎麼辦？**
A: 按 `品質加分` 高者優先。若品質分接近（差 < 5），依 RS Rating 高者優先。

**Q: 系統會 overfit 2020-2025 的資料嗎？**
A: 可能會。緩解方式：(1) Walk-forward validation（訓練期 2020-2023、驗證期 2024-2025），(2) Live Tracking 累積 out-of-sample 證據，(3) 參數數量刻意少（主要靠閾值而非複雜模型）。

**Q: 好公司的品質分很高，為什麼會被踢出 Universe？**
A: Universe 不是永久名單，是動態的當前機會池。公司的「歷史品質」（反映於品質加分 80 分系統）和「當前動能」（反映於踢出條件：EPS 預估、MA200 趨勢）可能暫時衝突。範例：LULU 2026 年品質分 70+/80 高於許多同業，但分析師對未來成長預估極低（< 1%）且股價長期低於 MA200，系統判定為 kickout。若未來獲利回溫、技術面重新走強，會自動重新進入 Universe。系統追求的不是「擁有最好的公司」，而是「在正確時機持有動能上升的品質公司」。

---

**文件結束**

> 本規格書為 QGM 系統的完整設計藍圖。所有實作（程式碼、UI、月報）應以本文件為準。重大設計變更需更新本文件的決策日誌。
