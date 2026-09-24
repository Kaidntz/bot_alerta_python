import argparse
import asyncio
import logging

from .config import MAX_PRICE, active_stores
from .notifiers import broadcast, clp, format_offer
from .scraper import scrape_all
from .state import diff_new_deals, record_alerts, record_status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor de stock Xbox Series X")
    parser.add_argument("--debug", action="store_true", help="Muestra todas las consolas detectadas")
    parser.add_argument("--dry-run", action="store_true", help="No guarda estado ni notifica")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    results = asyncio.run(scrape_all(active_stores()))

    if args.debug:
        for r in results:
            print(f"\n== {r.store.name} ({r.raw_count} candidatos) {r.error or ''}")
            for o in r.offers:
                flag = "OFERTA" if o.is_deal else ("stock" if o.in_stock else "agotado")
                print(f"  [{flag}] {clp(o.price)} {o.title} -> {o.url}")

    deals = [o for r in results for o in r.offers if o.is_deal]
    print(f"\nOfertas en stock bajo {clp(MAX_PRICE)}: {len(deals)}")
    for d in sorted(deals, key=lambda d: d.price):
        print(format_offer(d), end="\n\n")

    if args.dry_run:
        return 0

    new_deals = diff_new_deals(results)
    record_status(results)
    record_alerts(new_deals)
    if new_deals:
        broadcast(new_deals)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
