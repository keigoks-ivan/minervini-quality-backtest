"""/qgm/、/qgm-tw/ 頁頂說明（live/archive_note.py）。"""

from pathlib import Path

import pytest

from live.archive_note import ANCHOR, END, NOTE_TEXT, NOTE_TEXT_TW, START, apply_note, note_html

PAGE = (
    '<html><body>\n<header>nav</header>\n<section class="hero"><h1>QGM</h1></section>\n\n'
    '<main class="container" style="flex:1"><p>內容</p></main>\n</body></html>\n'
)


def test_note_text_is_the_agreed_sentence():
    assert NOTE_TEXT == "本頁不再列在選單；資料仍每週更新，供選股席位的候選母體使用。"


def test_inserted_once_between_hero_and_main():
    out = apply_note(PAGE)
    assert out.count(START) == 1 and out.count(END) == 1 and out.count(NOTE_TEXT) == 1
    assert out.index("</section>") < out.index(START) < out.index(ANCHOR)
    # 其他內容原封不動
    assert out.replace(note_html(), "") == PAGE


def test_apply_is_idempotent():
    once = apply_note(PAGE)
    assert apply_note(once) == once
    assert apply_note(apply_note(once)) == once


def test_existing_block_is_replaced_not_duplicated():
    stale = PAGE.replace(ANCHOR, f"{START}<div>舊說明</div>{END}\n{ANCHOR}", 1)
    out = apply_note(stale)
    assert "舊說明" not in out and out.count(START) == 1 and out.count(NOTE_TEXT) == 1


def test_missing_anchor_raises():
    with pytest.raises(ValueError):
        apply_note("<html><body><p>沒有主內容區</p></body></html>")


def test_no_archive_banner_wording():
    # 這兩頁沒有停更，不能出現「已歸檔」「停止更新」
    assert "歸檔" not in note_html() and "停止更新" not in note_html()


def test_daily_screener_applies_note_after_nav_injection():
    src = (Path(__file__).resolve().parent.parent / "live" / "daily_screener.py").read_text(encoding="utf-8")
    assert "from live.archive_note import apply_note" in src
    assert src.index('"__IMQ_NAV__"') < src.index("html = apply_note(html, market)") < src.index("html_path.write_text(html)")


def test_tw_page_uses_tw_text():
    out = apply_note(PAGE, "tw")
    assert NOTE_TEXT_TW in out and NOTE_TEXT not in out
    assert apply_note(out, "tw") == out
