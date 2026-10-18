"""/qgm/、/qgm-tw/ 頁頂的一句說明（2026-10-19：頁面不再列在選單，資料照常產生）。

放在英雄區（hero）與主內容（<main>）之間。daily_screener.py 產生 HTML 時呼叫 apply_note()，
所以每週重生的 latest.html 與新的封存頁都帶這一句；財經網站 repo 裡已經產出的 latest.html
也用同一支函式補上（冪等：以標記為界，重跑只會換內容）。

不是歸檔橫幅：這兩頁的資料沒有停更，只是選單入口拿掉了。
"""
from __future__ import annotations

NOTE_TEXT = "本頁不再列在選單；資料仍每週更新，供選股席位的候選母體使用。"
START = "<!--qgm-note-->"
END = "<!--/qgm-note-->"
ANCHOR = '<main class="container"'


def note_html() -> str:
    return (
        f'{START}<div class="container" style="padding-top:1rem">'
        f'<div style="background:#f4f4f5;border:1px solid #d4d4d8;border-left:4px solid #71717a;border-radius:8px;'
        f'color:#3f3f46;padding:.7rem 1rem;font-size:.88rem;line-height:1.7">{NOTE_TEXT}</div></div>{END}\n'
    )


def apply_note(html: str) -> str:
    """把說明放進 HTML（已有則整塊換掉）。找不到插入點時丟 ValueError，不靜默略過。"""
    note = note_html()
    if START in html and END in html:
        a = html.index(START)
        b = html.index(END) + len(END)
        # 標記區塊後面緊接的換行一併換掉，避免重跑累積空行
        if html[b : b + 1] == "\n":
            b += 1
        return html[:a] + note + html[b:]
    i = html.find(ANCHOR)
    if i < 0:
        raise ValueError("找不到 <main class=\"container\"，無法插入頁頂說明")
    return html[:i] + note + html[i:]
