"""Pool transition event detection and history persistence.

Implements SPEC 6.6 (Transition Event Log) and pool history storage.
"""

import json
from datetime import date
from pathlib import Path


POOL_HISTORY_DIR = Path("data/pool_history")


# ---------------------------------------------------------------------------
# Transition event detection
# ---------------------------------------------------------------------------

def detect_transition(
    prev_pool: str | None,
    current_pool: str | None,
    classifier_details: dict,
) -> dict | None:
    """Detect a pool transition event (SPEC 6.6).

    Args:
        prev_pool: Previous month's pool ('MLB', '3A', or None).
        current_pool: This month's pool.
        classifier_details: Details from determine_current_pool().

    Returns:
        Event dict if a notable transition occurred, None if stable.
    """
    transition_type = classifier_details.get("transition_type", "none")

    # No event for stable / none
    if transition_type in ("stable", "none"):
        return None

    notable = transition_type in ("upgrade", "kickout")

    return {
        "date": date.today().replace(day=1).isoformat(),
        "ticker": None,  # Caller fills this in
        "type": transition_type,
        "from": prev_pool,
        "to": current_pool,
        "reason": classifier_details.get("reason", ""),
        "notable": notable,
    }


# ---------------------------------------------------------------------------
# Pool history persistence (JSON)
# ---------------------------------------------------------------------------

def _history_path(ticker: str) -> Path:
    return POOL_HISTORY_DIR / f"{ticker}.json"


def save_pool_history(
    ticker: str,
    month: str,
    pool: str | None,
    details: dict,
) -> None:
    """Append a monthly pool snapshot to the ticker's history file.

    Path: data/pool_history/{ticker}.json

    Args:
        ticker: Stock symbol.
        month: 'YYYY-MM' format.
        pool: Current pool assignment.
        details: Classifier details for this month.
    """
    POOL_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    path = _history_path(ticker)

    if path.exists():
        data = json.loads(path.read_text())
    else:
        data = {"ticker": ticker, "history": []}

    # Avoid duplicate months
    existing_months = {h["month"] for h in data["history"]}
    if month not in existing_months:
        # Store a serializable subset of details
        entry = {
            "month": month,
            "pool": pool,
            "transition_type": details.get("transition_type"),
            "reason": details.get("reason"),
        }
        data["history"].append(entry)
        # Keep sorted newest-first
        data["history"].sort(key=lambda x: x["month"], reverse=True)

    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def load_pool_history(
    ticker: str, lookback_months: int = 12
) -> list[str | None]:
    """Load past pool assignments for a ticker, oldest → newest.

    Args:
        ticker: Stock symbol.
        lookback_months: How many months to return.

    Returns:
        List of pool strings (oldest first). Empty if no history.
    """
    path = _history_path(ticker)
    if not path.exists():
        return []

    data = json.loads(path.read_text())
    # History is stored newest-first; reverse for oldest-first
    history = list(reversed(data.get("history", [])))
    # Take the last N months
    recent = history[-lookback_months:]
    return [h["pool"] for h in recent]


def generate_monthly_events(
    universe_data: dict[str, dict],
    month: str,
    params: dict,
) -> list[dict]:
    """Generate transition events for an entire universe for one month.

    Args:
        universe_data: {ticker: ticker_data} for all tickers in universe.
        month: 'YYYY-MM' format.
        params: quality_filter block from params.yaml.

    Returns:
        List of event dicts (only non-None transitions).
    """
    from screener.pool_classifier import determine_current_pool

    events = []
    for ticker, td in universe_data.items():
        history = load_pool_history(ticker)
        prev_pool = history[-1] if history else None
        current_pool, details = determine_current_pool(td, history, params)

        event = detect_transition(prev_pool, current_pool, details)
        if event is not None:
            event["ticker"] = ticker
            events.append(event)

        # Save updated history
        save_pool_history(ticker, month, current_pool, details)

    return events
