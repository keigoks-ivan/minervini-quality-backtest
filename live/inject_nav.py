"""Insert the canonical InvestMQuest site header into an HTML file.

Used by .github/workflows/daily_screener_{us,tw}.yml for the workflow-built
stub pages (/qgm{,-tw}/index.html redirect + archive/index.html listing), so
they carry the same header as the daily_screener.py reports. The block comes
from live/site_nav_block.py (synced from financial-analysis-bot/scripts/
site_nav.py — do not edit by hand) and is inserted right after <body>,
separated by a single newline — exactly mirroring site_nav.py's injector.

Usage: python -m live.inject_nav <file.html> <us|tw>
"""

import sys
from pathlib import Path

from live.site_nav_block import NAV_BLOCKS


def inject(path: str, market: str) -> None:
    p = Path(path)
    html = p.read_text(encoding="utf-8")
    nav = NAV_BLOCKS[market]
    if nav in html:
        return  # already injected (idempotent)
    marker = "<body>"
    i = html.index(marker) + len(marker)
    p.write_text(html[:i] + "\n" + nav + html[i:], encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[2] not in NAV_BLOCKS:
        sys.exit("usage: python -m live.inject_nav <file.html> <us|tw>")
    inject(sys.argv[1], sys.argv[2])
