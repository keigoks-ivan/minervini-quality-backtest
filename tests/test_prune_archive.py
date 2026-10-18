"""QGM 封存保留規則（live/prune_archive.py）：每個封存目錄只留最近 N 個日期。"""

from datetime import date, timedelta
from pathlib import Path

import pytest

from live.prune_archive import KEEP_DEFAULT, main, prune


def _make_archive(d: Path, days: list[str], extra: tuple[str, ...] = ("index.html",)) -> None:
    for day in days:
        (d / f"candidates_{day}.html").write_text("<html></html>")
        (d / f"snapshot_{day}.json").write_text("{}")
    for name in extra:
        (d / name).write_text("keep me")


def _days(n: int, start: date = date(2026, 1, 1)) -> list[str]:
    return [(start + timedelta(days=i)).isoformat() for i in range(n)]


def test_default_keep_is_30():
    assert KEEP_DEFAULT == 30


def test_keeps_latest_30_dates_and_deletes_older_pairs(tmp_path):
    days = _days(45)
    _make_archive(tmp_path, days)
    removed = prune(tmp_path)
    assert len(removed) == 2 * 15
    left = sorted(p.name for p in tmp_path.iterdir())
    kept_days = days[-30:]
    expected = sorted(
        [f"candidates_{d}.html" for d in kept_days] + [f"snapshot_{d}.json" for d in kept_days] + ["index.html"]
    )
    assert left == expected


def test_same_date_pair_stays_together(tmp_path):
    # 第 30 與第 31 新的日期的兩個檔都要整對處理，不會留一半
    days = _days(31)
    _make_archive(tmp_path, days)
    prune(tmp_path)
    assert not (tmp_path / f"candidates_{days[0]}.html").exists()
    assert not (tmp_path / f"snapshot_{days[0]}.json").exists()
    assert (tmp_path / f"candidates_{days[1]}.html").exists()
    assert (tmp_path / f"snapshot_{days[1]}.json").exists()


def test_fewer_than_keep_deletes_nothing(tmp_path):
    _make_archive(tmp_path, _days(12))
    assert prune(tmp_path) == []
    assert len(list(tmp_path.iterdir())) == 12 * 2 + 1


def test_exactly_keep_deletes_nothing(tmp_path):
    _make_archive(tmp_path, _days(30))
    assert prune(tmp_path) == []


def test_incomplete_pair_still_counts_as_one_date(tmp_path):
    # 某天只有 html、沒有 json（或相反）也算一個日期，不能因為缺檔多留一天
    days = _days(32)
    for d in days:
        (tmp_path / f"candidates_{d}.html").write_text("x")
    (tmp_path / f"snapshot_{days[-1]}.json").write_text("{}")
    prune(tmp_path)
    left_days = {p.name.split("_")[1].split(".")[0] for p in tmp_path.iterdir()}
    assert left_days == set(days[-30:])


def test_unknown_names_are_never_touched(tmp_path):
    days = _days(40)
    _make_archive(tmp_path, days, extra=("index.html", "README.md", "candidates_latest.html",
                                         "snapshot_2026-13-45.json", "candidates_2026-02-30.html", "notes.txt"))
    prune(tmp_path)
    for name in ("index.html", "README.md", "candidates_latest.html", "snapshot_2026-13-45.json",
                 "candidates_2026-02-30.html", "notes.txt"):
        assert (tmp_path / name).exists(), name


def test_subdirectories_are_ignored(tmp_path):
    _make_archive(tmp_path, _days(35))
    sub = tmp_path / "candidates_2025-01-01.html"  # 名字像封存檔的目錄
    sub.mkdir()
    prune(tmp_path)
    assert sub.is_dir()


def test_rerun_is_idempotent(tmp_path):
    _make_archive(tmp_path, _days(50))
    prune(tmp_path)
    before = sorted(p.name for p in tmp_path.iterdir())
    assert prune(tmp_path) == []
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_dry_run_deletes_nothing_but_reports(tmp_path):
    _make_archive(tmp_path, _days(40))
    removed = prune(tmp_path, dry_run=True)
    assert len(removed) == 20
    assert all(p.exists() for p in removed)


def test_custom_keep(tmp_path):
    _make_archive(tmp_path, _days(10))
    prune(tmp_path, keep=3)
    assert len([p for p in tmp_path.iterdir() if p.name.startswith("snapshot_")]) == 3


def test_invalid_keep_and_missing_dir(tmp_path):
    with pytest.raises(ValueError):
        prune(tmp_path, keep=0)
    with pytest.raises(FileNotFoundError):
        prune(tmp_path / "nope")


def test_cli(tmp_path, capsys):
    _make_archive(tmp_path, _days(33))
    assert main([str(tmp_path), "--keep", "30"]) == 0
    out = capsys.readouterr().out
    assert "已刪除 6 個" in out
    assert not (tmp_path / "snapshot_2026-01-01.json").exists()


def test_both_workflows_call_prune_after_copy_and_before_index():
    root = Path(__file__).resolve().parent.parent
    call = 'python -m live.prune_archive "$DEST/archive" --keep 30'
    for name, dest in (("daily_screener_us.yml", "docs/qgm"), ("daily_screener_tw.yml", "docs/qgm-tw")):
        text = (root / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert text.count(call) == 1, name
        copied = text.index('cp "$SRC/snapshot_${TODAY}.json"')
        index_regen = text.index("<title>QGM")  # archive/index.html 重生的起點
        assert copied < text.index(call) < index_regen, name
        # 刪除要被 git add 帶進 commit（git add <目錄> 會 stage 目錄內的刪除）
        assert f"git add {dest}/" in text, name
