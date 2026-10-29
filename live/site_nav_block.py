"""Canonical InvestMQuest site header (imq-nav) blocks.

synced from financial-analysis-bot/scripts/site_nav.py — do not edit by hand
(regenerate with:
  python3 -c "import sys; sys.path.insert(0,'<financial-analysis-bot>/scripts');
              import site_nav; print(site_nav.full_nav_block('pick','qus'))"
 and likewise 'qtw'; each block is full_nav_block(group, item) verbatim:
 <style id=imq-nav-style> + <header class=imq-nav-root> + dropdown <script>).

Synced 2026-07-07（整站 IA v2：三群 研究/市場/工具 → 四群 選股/研究/市場/系統；
QGM 自「工具 quant」移入「選股 pick」，group key 一律 'pick'）。
2026-07-09 補：市場群加入「總經深度報告」(/macro/)，us/tw 兩塊皆已同步。
2026-07-10 補：選股主控台整併——精選清單／Pipeline 漏斗／決策引擎三條收斂進
/cockpit/ 單一入口（標籤改「選股主控台」），下拉自 9 條瘦身為 6 條，us/tw 兩塊皆已同步。
2026-07-11 補：整站 nav 重排——頂層順序改「首頁·市場·選股·研究·心智模型·系統·使用指南·搜尋」；
「使用說明」改「使用指南」；新增頂層「搜尋」(/search.html)；研究群首增「個股總覽」(/t/)；
市場群增「資產輪動雷達」(/rotation/radar.html)；系統群增「裁決實績」(/track-record/)與「公開資料」(/data.html)；
us/tw 兩塊皆已由 canonical full_nav_block 重生為 byte-identical。
2026-07-16 補：市場群 monitor 之後加入「偵測警報網」(/detective/)，us/tw 兩塊皆已同步。

Pages must insert NAV_BLOCKS[market] immediately after <body>, separated by a
single newline — mirroring site_nav.py's idempotent injector, so re-running
that injector over docs/ leaves these pages byte-identical.
2026-08-20 補（intel 2.0 Phase C）：canonical 大改後全量重生——市場群 13→7（monitor／
偵測警報網／產業輪動／擁擠交易／regime／催化劑 六條目收斂進 /intel/ 情報監視器分頁殼，
intel 升首位；每日簡報 08-17 掛回；補齊 07-17 以來累積的頂層「投資流程」等變更）。
us/tw 兩塊皆由 canonical full_nav_block 重生、byte-identical 驗證通過。
2026-08-20 補（研究區整併第二階段，nav 瘦身）：研究 ▾ 由 7 項收斂為 3 項——「個股研究」
(/t/)／「產業研究」(/id/)／「Tier Matrix」(/id/tier_matrix.html)。移除的 4 項（個股 DD／
供應鏈地圖／多股對比／期望落差綜合研判）已於研究區整併第一階段（20260820）收進 /t/ 或
/id/ 分頁。us/tw 兩塊研究下拉皆已同步；其餘群不受影響，只手動替換研究下拉區塊字元。
2026-08-23 補（系統群 nav 整併 phase 0 catch-up）：補齊「選股入口整頓第二批」落後——
選股群收斂為單一「選股主控台」，改渲染成頂層直連（不再是下拉）；系統群加回「市場偵探」
("det", /detective/，排首位)。us/tw 兩塊已由 canonical full_nav_block('pick', 'qus'/'qtw')
重生為 byte-identical（見 financial-analysis-bot notes/site-internal/root/
_consolidation_system_20260823.md）。
2026-08-23 補（系統群 nav 瘦身 phase 2）：MENU["system"] 8→4 項，只留系統主控台
(/long-track/，原「追蹤總覽」改名)／量化回測／期貨部位計算機／公開資料；市場偵探／
裁決實績／持倉週掃／實單主系統四個下拉項移除（頁面仍可直達，只是不進系統群選單）。
us/tw 兩塊已由 canonical full_nav_block('pick','qus'/'qtw') 重生為 byte-identical。
2026-09-13 補：同步 canonical 的「模擬」入口，置於「系統」之後。
2026-09-23 補：研究 ▾ 下拉新增「個股儀表板」(/stock-dash/)，緊接在「個股研究」之後；
us/tw 兩塊皆已由 canonical full_nav_block('pick','cockpit') 重生為 byte-identical。
2026-09-23 晚補：研究 ▾ 下拉新增「投資想法」(/ideas/)，置於「產業研究」之後、「Tier
Matrix」之前——canonical 同日同步。us/tw 兩塊皆已由 canonical
full_nav_block('pick','cockpit') 重生為 byte-identical。
2026-09-30 補（catch-up，含 09-24／09-25 落後）：研究 ▾ 下拉緊接「個股儀表板」之後
新增「ETF 儀表板」(/etf-dash/，canonical 2026-09-24 新增) 與「主動式 ETF」
(/active-etf/，canonical 2026-09-25 新增)；「個股研究」標籤改「研究清單」（canonical
2026-09-30，個股內容併入個股儀表板）。us/tw 兩塊皆已由 canonical
full_nav_block('pick','qus'/'qtw') 重生為 byte-identical。
2026-10-05 補：研究 ▾ 下拉緊接「研究清單」之後加回「DD Screener」(/dd-screener/)——
canonical 同日同步。us/tw 兩塊皆已由 canonical full_nav_block 重生為 byte-identical。
2026-10-08 補：市場 ▾ 下拉緊接「總經深度報告」之後新增「總經資料庫」(/macro/db/)——
canonical 同日同步，已重新驗證對 canonical byte-identical。
2026-10-16 補：市場 ▾ 下拉緊接「總經資料庫」之後新增「AI 信用監測」(/ai-credit/)——
canonical 同日同步。
2026-10-19 補（catch-up）：市場 ▾ 補「台股籌碼」「韓股籌碼」，選股 ▾ 補「CAN SLIM 選股」；研究 ▾ 拿掉「Tier Matrix」，頂層拿掉「使用指南」。QGM 已不在選單，us／tw 兩塊由 canonical full_nav_block('pick','qus'/'qtw') 重生為 byte-identical，只剩群高亮。
2026-10-21 補：市場 ▾ 拆組——市場 ▾ 只留 5 項（市況主控台／情報監視器／每日簡報／資產輪動雷達／財報分析），
新增下拉「總經與籌碼 ▾」(group "macrochip"，排市場之後、選股之前，7 項：總經深度報告／總經資料庫／
AI 信用監測／台股籌碼／韓股籌碼／全球市場／產業板塊)。canonical 同日同步，已驗證 byte-identical（us/tw 兩塊）。
2026-10-24 補：頂層重新排序——首頁｜市場 ▾｜總經與籌碼 ▾｜研究 ▾｜選股｜系統 ▾｜投資流程｜模擬｜心智模型｜搜尋（只換位置）。canonical 同日同步，已驗證 byte-identical（us/tw 兩塊）。
"""

# market -> canonical header block ('us' -> /qgm/ active, 'tw' -> /qgm-tw/ active)
NAV_BLOCKS = {
    "us": """<style id="imq-nav-style">
.imq-nav-root{background:linear-gradient(135deg,#081832 0%,#173564 100%);padding:.7rem 20px;font-size:13px;box-shadow:0 1px 3px rgba(0,0,0,.12);position:sticky;top:0;z-index:1000;font-family:'Inter','Noto Sans TC',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
.imq-nav-inner{max-width:1140px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap}
.imq-logo{font-weight:700;color:#fff !important;text-decoration:none !important;font-size:15px;letter-spacing:-.02em;flex-shrink:0;background:none !important;padding:0 !important}
.imq-logo:hover{color:#fff !important;text-decoration:none !important}
.imq-logo span{color:#d4b576}
.imq-menu{display:flex;align-items:center;gap:.15rem;flex-wrap:wrap;margin:0;padding:0;list-style:none}
.imq-menu > a,.imq-dd-btn{color:rgba(255,255,255,.7) !important;font-size:.8rem;font-weight:500;padding:.42rem .72rem;border-radius:6px;transition:all .15s;background:none;border:0;font-family:inherit;cursor:pointer;text-decoration:none !important;display:inline-flex;align-items:center;gap:.28rem;line-height:1.2;letter-spacing:0}
.imq-menu > a:hover,.imq-dd-btn:hover{color:#fff !important;background:rgba(255,255,255,.08)}
.imq-menu > a.active,.imq-dd.active > .imq-dd-btn{color:#fff !important;background:rgba(184,146,74,.26);font-weight:600}
.imq-dd{position:relative;display:inline-block}
.imq-dd-menu{display:none;position:absolute;top:100%;left:0;background:#0d2244;border:1px solid rgba(255,255,255,.1);border-radius:8px;padding:.35rem 0;min-width:180px;box-shadow:0 10px 28px rgba(0,0,0,.3);z-index:1001}
.imq-dd:hover .imq-dd-menu,.imq-dd:focus-within .imq-dd-menu,.imq-dd.open .imq-dd-menu{display:block}
.imq-dd-menu a{display:block;padding:.55rem 1rem;color:rgba(255,255,255,.75) !important;font-size:.78rem;text-decoration:none !important;white-space:nowrap;transition:all .12s;font-weight:500}
.imq-dd-menu a:hover{color:#fff !important;background:rgba(184,146,74,.20)}
.imq-dd-menu a.active{color:#fff !important;background:rgba(184,146,74,.26);font-weight:600}
.imq-caret{font-size:.6rem;opacity:.7;margin-top:1px}
.imq-subnav{background:#081832;padding:.45rem 20px;font-family:'Inter','Noto Sans TC',-apple-system,sans-serif}
.imq-subnav-inner{max-width:1140px;margin:0 auto;display:flex;gap:.3rem;flex-wrap:wrap}
.imq-subnav a{color:rgba(255,255,255,.55) !important;font-size:.74rem;font-weight:500;padding:.28rem .6rem;border-radius:5px;text-decoration:none !important}
.imq-subnav a:hover{color:#fff !important;background:rgba(255,255,255,.08)}
.imq-subnav a.active{color:#fff !important;background:rgba(184,146,74,.30);font-weight:600}
@media(min-width:1280px){.imq-nav-inner,.imq-subnav-inner,html body .wrap,html body .container,html body .masthead-inner,html body .crumb,html body .header-inner,html body .hero-inner,html body .cover-inner,html body header.top .inner,html body header.masthead .inner,html body header.site .inner,html body header.dd-head .hrow,html body header.top .hdr-row,html body .imq-foot .in,html body #tw .container,html body #us .container,html body #global .container,html body .lc-wrap,html body .course-nav-inner,html body .mm-hero,html body .mm-table-wrap,html body .mm-lolla-inner,html body .mm-tray-inner,html body .v19-frame{max-width:max(1240px,min(1700px,calc(100% - 48px)))}html body .shell,html body header.site .hdr-inner{max-width:max(1480px,min(1700px,calc(100% - 48px)))}html.imq-wb body{max-width:max(var(--imq-wb0),min(1700px,calc(100% - 48px)))}html.imq-wm body main,html.imq-wm body main.page{max-width:max(var(--imq-wm0),min(1700px,calc(100% - 48px)))}html body .v19-frame{width:auto}html body.v19-dd main.page{min-width:0}}
@media(max-width:768px){
  .imq-nav-root{padding:.55rem 12px}
  .imq-nav-inner{gap:.4rem}
  .imq-menu{width:100%;justify-content:flex-start;gap:.1rem}
  .imq-menu > a,.imq-dd-btn{font-size:.74rem;padding:.32rem .5rem}
  .imq-dd-menu{position:static;display:none;min-width:auto;box-shadow:none;background:rgba(255,255,255,.04);border:none;padding:.1rem 0 .3rem 1rem;margin:.1rem 0}
  .imq-dd.open .imq-dd-menu{display:block}
}
</style>
<header class="imq-nav-root">
  <div class="imq-nav-inner">
    <a class="imq-logo" href="/">InvestMQuest<span>.</span> Research</a>
    <nav class="imq-menu">
      <a href="/">首頁</a>
      <div class="imq-dd">
        <button type="button" class="imq-dd-btn">市場<span class="imq-caret">▾</span></button>
        <div class="imq-dd-menu">
          <a href="/market/">市況主控台</a>
          <a href="/intel/">情報監視器</a>
          <a href="/briefing/">每日簡報</a>
          <a href="/rotation/radar.html">資產輪動雷達</a>
          <a href="/earnings/">財報分析</a>
        </div>
      </div>
      <div class="imq-dd">
        <button type="button" class="imq-dd-btn">總經與籌碼<span class="imq-caret">▾</span></button>
        <div class="imq-dd-menu">
          <a href="/macro/">總經深度報告</a>
          <a href="/macro/db/">總經資料庫</a>
          <a href="/ai-credit/">AI 信用監測</a>
          <a href="/tw-chips/">台股籌碼</a>
          <a href="/kr-chips/">韓股籌碼</a>
          <a href="/etf-dash/?view=overview&tab=countries">全球市場</a>
          <a href="/etf-dash/?view=overview&tab=sectors">產業板塊</a>
        </div>
      </div>
      <div class="imq-dd">
        <button type="button" class="imq-dd-btn">研究<span class="imq-caret">▾</span></button>
        <div class="imq-dd-menu">
          <a href="/t/">研究清單</a>
          <a href="/dd-screener/">DD Screener</a>
          <a href="/canslim/">CAN SLIM 選股</a>
          <a href="/stock-dash/">個股儀表板</a>
          <a href="/etf-dash/">ETF 儀表板</a>
          <a href="/active-etf/">主動式 ETF</a>
          <a href="/id/">產業研究</a>
          <a href="/ideas/">投資想法</a>
        </div>
      </div>
      <a href="/cockpit/" class="active">選股</a>
      <div class="imq-dd">
        <button type="button" class="imq-dd-btn">系統<span class="imq-caret">▾</span></button>
        <div class="imq-dd-menu">
          <a href="/long-track/">系統主控台</a>
          <a href="/backtest/">量化回測</a>
          <a href="/tools/">期貨部位計算機</a>
          <a href="/data.html">公開資料</a>
        </div>
      </div>
      <a href="/flow/">投資流程</a>
      <a href="/simulation/">模擬</a>
      <a href="/mental-models/">心智模型</a>
      <a href="/search.html">搜尋</a>
    </nav>
  </div>
</header>
<script>(function(){document.querySelectorAll('.imq-dd-btn').forEach(function(btn){btn.addEventListener('click',function(e){e.preventDefault();var dd=btn.closest('.imq-dd');document.querySelectorAll('.imq-dd.open').forEach(function(d){if(d!==dd)d.classList.remove('open')});dd.classList.toggle('open')})});document.addEventListener('click',function(e){if(!e.target.closest('.imq-dd'))document.querySelectorAll('.imq-dd.open').forEach(function(d){d.classList.remove('open')})});})();(function(){var h=document.documentElement,b=document.body;if(!b)return;function cap(el){var m=parseFloat(getComputedStyle(el).maxWidth);return m>=600&&m<1700?m:0}var m=cap(b);if(m){h.classList.add('imq-wb');h.style.setProperty('--imq-wb0',m+'px')}var p=document.createElement('main');p.className='page';b.appendChild(p);m=cap(p);if(m){h.classList.add('imq-wm');h.style.setProperty('--imq-wm0',m+'px')}b.removeChild(p)})();</script>""",
    "tw": """<style id="imq-nav-style">
.imq-nav-root{background:linear-gradient(135deg,#081832 0%,#173564 100%);padding:.7rem 20px;font-size:13px;box-shadow:0 1px 3px rgba(0,0,0,.12);position:sticky;top:0;z-index:1000;font-family:'Inter','Noto Sans TC',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
.imq-nav-inner{max-width:1140px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap}
.imq-logo{font-weight:700;color:#fff !important;text-decoration:none !important;font-size:15px;letter-spacing:-.02em;flex-shrink:0;background:none !important;padding:0 !important}
.imq-logo:hover{color:#fff !important;text-decoration:none !important}
.imq-logo span{color:#d4b576}
.imq-menu{display:flex;align-items:center;gap:.15rem;flex-wrap:wrap;margin:0;padding:0;list-style:none}
.imq-menu > a,.imq-dd-btn{color:rgba(255,255,255,.7) !important;font-size:.8rem;font-weight:500;padding:.42rem .72rem;border-radius:6px;transition:all .15s;background:none;border:0;font-family:inherit;cursor:pointer;text-decoration:none !important;display:inline-flex;align-items:center;gap:.28rem;line-height:1.2;letter-spacing:0}
.imq-menu > a:hover,.imq-dd-btn:hover{color:#fff !important;background:rgba(255,255,255,.08)}
.imq-menu > a.active,.imq-dd.active > .imq-dd-btn{color:#fff !important;background:rgba(184,146,74,.26);font-weight:600}
.imq-dd{position:relative;display:inline-block}
.imq-dd-menu{display:none;position:absolute;top:100%;left:0;background:#0d2244;border:1px solid rgba(255,255,255,.1);border-radius:8px;padding:.35rem 0;min-width:180px;box-shadow:0 10px 28px rgba(0,0,0,.3);z-index:1001}
.imq-dd:hover .imq-dd-menu,.imq-dd:focus-within .imq-dd-menu,.imq-dd.open .imq-dd-menu{display:block}
.imq-dd-menu a{display:block;padding:.55rem 1rem;color:rgba(255,255,255,.75) !important;font-size:.78rem;text-decoration:none !important;white-space:nowrap;transition:all .12s;font-weight:500}
.imq-dd-menu a:hover{color:#fff !important;background:rgba(184,146,74,.20)}
.imq-dd-menu a.active{color:#fff !important;background:rgba(184,146,74,.26);font-weight:600}
.imq-caret{font-size:.6rem;opacity:.7;margin-top:1px}
.imq-subnav{background:#081832;padding:.45rem 20px;font-family:'Inter','Noto Sans TC',-apple-system,sans-serif}
.imq-subnav-inner{max-width:1140px;margin:0 auto;display:flex;gap:.3rem;flex-wrap:wrap}
.imq-subnav a{color:rgba(255,255,255,.55) !important;font-size:.74rem;font-weight:500;padding:.28rem .6rem;border-radius:5px;text-decoration:none !important}
.imq-subnav a:hover{color:#fff !important;background:rgba(255,255,255,.08)}
.imq-subnav a.active{color:#fff !important;background:rgba(184,146,74,.30);font-weight:600}
@media(min-width:1280px){.imq-nav-inner,.imq-subnav-inner,html body .wrap,html body .container,html body .masthead-inner,html body .crumb,html body .header-inner,html body .hero-inner,html body .cover-inner,html body header.top .inner,html body header.masthead .inner,html body header.site .inner,html body header.dd-head .hrow,html body header.top .hdr-row,html body .imq-foot .in,html body #tw .container,html body #us .container,html body #global .container,html body .lc-wrap,html body .course-nav-inner,html body .mm-hero,html body .mm-table-wrap,html body .mm-lolla-inner,html body .mm-tray-inner,html body .v19-frame{max-width:max(1240px,min(1700px,calc(100% - 48px)))}html body .shell,html body header.site .hdr-inner{max-width:max(1480px,min(1700px,calc(100% - 48px)))}html.imq-wb body{max-width:max(var(--imq-wb0),min(1700px,calc(100% - 48px)))}html.imq-wm body main,html.imq-wm body main.page{max-width:max(var(--imq-wm0),min(1700px,calc(100% - 48px)))}html body .v19-frame{width:auto}html body.v19-dd main.page{min-width:0}}
@media(max-width:768px){
  .imq-nav-root{padding:.55rem 12px}
  .imq-nav-inner{gap:.4rem}
  .imq-menu{width:100%;justify-content:flex-start;gap:.1rem}
  .imq-menu > a,.imq-dd-btn{font-size:.74rem;padding:.32rem .5rem}
  .imq-dd-menu{position:static;display:none;min-width:auto;box-shadow:none;background:rgba(255,255,255,.04);border:none;padding:.1rem 0 .3rem 1rem;margin:.1rem 0}
  .imq-dd.open .imq-dd-menu{display:block}
}
</style>
<header class="imq-nav-root">
  <div class="imq-nav-inner">
    <a class="imq-logo" href="/">InvestMQuest<span>.</span> Research</a>
    <nav class="imq-menu">
      <a href="/">首頁</a>
      <div class="imq-dd">
        <button type="button" class="imq-dd-btn">市場<span class="imq-caret">▾</span></button>
        <div class="imq-dd-menu">
          <a href="/market/">市況主控台</a>
          <a href="/intel/">情報監視器</a>
          <a href="/briefing/">每日簡報</a>
          <a href="/rotation/radar.html">資產輪動雷達</a>
          <a href="/earnings/">財報分析</a>
        </div>
      </div>
      <div class="imq-dd">
        <button type="button" class="imq-dd-btn">總經與籌碼<span class="imq-caret">▾</span></button>
        <div class="imq-dd-menu">
          <a href="/macro/">總經深度報告</a>
          <a href="/macro/db/">總經資料庫</a>
          <a href="/ai-credit/">AI 信用監測</a>
          <a href="/tw-chips/">台股籌碼</a>
          <a href="/kr-chips/">韓股籌碼</a>
          <a href="/etf-dash/?view=overview&tab=countries">全球市場</a>
          <a href="/etf-dash/?view=overview&tab=sectors">產業板塊</a>
        </div>
      </div>
      <div class="imq-dd">
        <button type="button" class="imq-dd-btn">研究<span class="imq-caret">▾</span></button>
        <div class="imq-dd-menu">
          <a href="/t/">研究清單</a>
          <a href="/dd-screener/">DD Screener</a>
          <a href="/canslim/">CAN SLIM 選股</a>
          <a href="/stock-dash/">個股儀表板</a>
          <a href="/etf-dash/">ETF 儀表板</a>
          <a href="/active-etf/">主動式 ETF</a>
          <a href="/id/">產業研究</a>
          <a href="/ideas/">投資想法</a>
        </div>
      </div>
      <a href="/cockpit/" class="active">選股</a>
      <div class="imq-dd">
        <button type="button" class="imq-dd-btn">系統<span class="imq-caret">▾</span></button>
        <div class="imq-dd-menu">
          <a href="/long-track/">系統主控台</a>
          <a href="/backtest/">量化回測</a>
          <a href="/tools/">期貨部位計算機</a>
          <a href="/data.html">公開資料</a>
        </div>
      </div>
      <a href="/flow/">投資流程</a>
      <a href="/simulation/">模擬</a>
      <a href="/mental-models/">心智模型</a>
      <a href="/search.html">搜尋</a>
    </nav>
  </div>
</header>
<script>(function(){document.querySelectorAll('.imq-dd-btn').forEach(function(btn){btn.addEventListener('click',function(e){e.preventDefault();var dd=btn.closest('.imq-dd');document.querySelectorAll('.imq-dd.open').forEach(function(d){if(d!==dd)d.classList.remove('open')});dd.classList.toggle('open')})});document.addEventListener('click',function(e){if(!e.target.closest('.imq-dd'))document.querySelectorAll('.imq-dd.open').forEach(function(d){d.classList.remove('open')})});})();(function(){var h=document.documentElement,b=document.body;if(!b)return;function cap(el){var m=parseFloat(getComputedStyle(el).maxWidth);return m>=600&&m<1700?m:0}var m=cap(b);if(m){h.classList.add('imq-wb');h.style.setProperty('--imq-wb0',m+'px')}var p=document.createElement('main');p.className='page';b.appendChild(p);m=cap(p);if(m){h.classList.add('imq-wm');h.style.setProperty('--imq-wm0',m+'px')}b.removeChild(p)})();</script>""",
}
