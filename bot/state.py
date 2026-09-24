import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA_DIR, MAX_PRICE
from .filters import Offer
from .scraper import StoreResult

STATE_FILE = Path(DATA_DIR) / "state.json"
ALERTS_FILE = Path(DATA_DIR) / "alerts.json"
STATUS_FILE = Path(DATA_DIR) / "status.json"
MAX_ALERT_HISTORY = 50


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _dump(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def diff_new_deals(results: list[StoreResult]) -> list[Offer]:
    previous = _load(STATE_FILE, {})
    scraped_ok = {r.store.id for r in results if r.error is None or r.offers}
    current = {o.key: o for r in results for o in r.offers}

    new_deals = [
        o
        for o in current.values()
        if o.is_deal
        and (
            not previous.get(o.key, {}).get("is_deal")
            or o.price < previous[o.key].get("price", o.price)
        )
    ]

    kept = {k: v for k, v in previous.items() if k.split("|", 1)[0] not in scraped_ok}
    kept |= {k: asdict(o) | {"is_deal": o.is_deal, "seen_at": _now()} for k, o in current.items()}
    _dump(STATE_FILE, kept)
    return new_deals


def record_alerts(deals: list[Offer]) -> None:
    history = _load(ALERTS_FILE, {"alerts": []})
    stamp = _now()
    history["alerts"] = [asdict(d) | {"detected_at": stamp} for d in deals] + history["alerts"]
    history["alerts"] = history["alerts"][:MAX_ALERT_HISTORY]
    history["last_alert_at"] = stamp if deals else history.get("last_alert_at")
    _dump(ALERTS_FILE, history)


def record_status(results: list[StoreResult]) -> None:
    _dump(
        STATUS_FILE,
        {
            "checked_at": _now(),
            "max_price": MAX_PRICE,
            "stores": {
                r.store.id: {
                    "ok": r.error is None,
                    "error": r.error,
                    "candidates": r.raw_count,
                    "consoles": len(r.offers),
                    "deals": sum(o.is_deal for o in r.offers),
                }
                for r in results
            },
        },
    )
