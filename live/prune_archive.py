"""QGM 封存保留規則：每個日期一對檔，只留最近 N 個日期（預設 30）。

背景：QGM 每次執行會把 candidates_YYYY-MM-DD.html 與 snapshot_YYYY-MM-DD.json 推進財經網站 repo 的
docs/qgm/archive/、docs/qgm-tw/archive/。網站（GitHub Pages）逼近 1 GB 上限，2026-10-19 起每個封存目錄只留
最近 30 個日期，更早的檔由 ~/v7-backtest/data/qgm_archive/ 保存（該處由 tools/sync_site_data.py 每天複製、不刪除）。

規則：
- 只認檔名符合 candidates_YYYY-MM-DD.html 或 snapshot_YYYY-MM-DD.json 的檔，其他（index.html 等）一律不動。
- 以檔名裡的日期排序，留最新的 N 個「日期」，同一日期的兩個檔一起留或一起刪。
- 日期不是合法日曆日的檔名不處理（當成不認識的檔，不動）。

用法（workflow 在複製完當天檔案之後、重生 archive/index.html 之前呼叫）：
    python -m live.prune_archive <archive 目錄> [--keep 30] [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

KEEP_DEFAULT = 30

_NAME_RE = re.compile(r"^(?:candidates|snapshot)_(\d{4}-\d{2}-\d{2})\.(?:html|json)$")


def _archive_date(name: str) -> str | None:
    """檔名裡的日期（YYYY-MM-DD）；檔名不符或日期不是合法日曆日回傳 None。"""
    m = _NAME_RE.match(name)
    if not m:
        return None
    try:
        date.fromisoformat(m.group(1))
    except ValueError:
        return None
    return m.group(1)


def prune(archive_dir: str | Path, keep: int = KEEP_DEFAULT, dry_run: bool = False) -> list[Path]:
    """刪除 archive_dir 裡最近 keep 個日期以外的封存檔，回傳被刪（dry_run 時為將刪）的檔案清單。"""
    if keep < 1:
        raise ValueError(f"keep 必須 >= 1，收到 {keep}")
    d = Path(archive_dir)
    if not d.is_dir():
        raise FileNotFoundError(f"找不到封存目錄：{d}")
    by_date: dict[str, list[Path]] = {}
    for p in d.iterdir():
        if not p.is_file():
            continue
        day = _archive_date(p.name)
        if day is not None:
            by_date.setdefault(day, []).append(p)
    old_days = sorted(by_date, reverse=True)[keep:]
    removed = sorted(p for day in old_days for p in by_date[day])
    if not dry_run:
        for p in removed:
            p.unlink()
    return removed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="QGM 封存目錄只留最近 N 個日期")
    ap.add_argument("archive_dir")
    ap.add_argument("--keep", type=int, default=KEEP_DEFAULT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    removed = prune(args.archive_dir, keep=args.keep, dry_run=args.dry_run)
    verb = "將刪除" if args.dry_run else "已刪除"
    print(f"{verb} {len(removed)} 個舊封存檔（保留最近 {args.keep} 個日期）：{args.archive_dir}")
    for p in removed:
        print(f"  - {p.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
