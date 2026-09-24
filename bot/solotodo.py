import logging
from concurrent.futures import ThreadPoolExecutor

import requests

from .config import Store
from .filters import ALWAYS_EXCLUDE, SERIES_X, Offer, variant_of
from .scraper import StoreResult

log = logging.getLogger(__name__)

API = "https://publicapi.solotodo.com"
CONSOLES_CATEGORY = 33
CHILE = 1
NEW_CONDITION = "https://schema.org/NewCondition"
SEARCHES = ("xbox series x", "xbox series x digital")
SOURCE = Store("solotodo", "SoloTodo", (API,))


class SoloTodoClient:
    def __init__(self, session: requests.Session | None = None, timeout: int = 20):
        self.http = session or requests.Session()
        self.http.headers["User-Agent"] = "xbox-stock-bot/1.0"
        self.timeout = timeout
        self._store_names: dict[int, str] = {}

    def _get(self, path: str, params=None) -> dict:
        response = self.http.get(f"{API}{path}", params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def available_products(self, search: str) -> dict[int, str]:
        data = self._get(
            f"/categories/{CONSOLES_CATEGORY}/browse/",
            {"search": search, "countries": CHILE},
        )
        return {
            entry["product"]["id"]: entry["product"]["name"]
            for bucket in data.get("results", [])
            for entry in bucket.get("product_entries", [])
        }

    def entities(self, product_ids: list[int]) -> list[dict]:
        if not product_ids:
            return []
        data = self._get("/products/available_entities/", [("ids", i) for i in product_ids])
        return [e for r in data.get("results", []) for e in r.get("entities", [])]

    def store_name(self, store_id: int) -> str:
        if store_id not in self._store_names:
            try:
                self._store_names[store_id] = self._get(f"/stores/{store_id}/")["name"]
            except requests.RequestException:
                self._store_names[store_id] = f"Tienda {store_id}"
        return self._store_names[store_id]


def is_series_x_console(name: str) -> bool:
    return bool(SERIES_X.search(name)) and not ALWAYS_EXCLUDE.search(name)


def to_offer(entity: dict, product_name: str, store: str) -> Offer | None:
    registry = entity.get("active_registry") or {}
    if not registry.get("is_available") or entity.get("condition") != NEW_CONDITION:
        return None
    prices = tuple(
        sorted({int(float(registry[k])) for k in ("offer_price", "normal_price") if registry.get(k)})
    )
    if not prices:
        return None
    return Offer(
        store_id=SOURCE.id,
        store=store,
        title=product_name,
        url=entity["external_url"],
        price=prices[0],
        prices=prices,
        variant=variant_of(f"{product_name} {entity.get('name', '')}"),
        in_stock=True,
    )


def fetch(client: SoloTodoClient | None = None) -> StoreResult:
    client = client or SoloTodoClient()
    result = StoreResult(SOURCE)
    try:
        products = {
            pid: name
            for search in SEARCHES
            for pid, name in client.available_products(search).items()
            if is_series_x_console(name)
        }
        entities = client.entities(list(products))
        store_ids = {e["store"] for e in entities}
        with ThreadPoolExecutor(max_workers=6) as pool:
            names = dict(zip(store_ids, pool.map(client.store_name, store_ids)))
        result.raw_count = len(entities)
        result.offers = [
            o
            for e in entities
            if (o := to_offer(e, products[e["product"]["id"]], names[e["store"]]))
        ]
        result.diagnostics.append({"products": products, "entities": len(entities)})
    except requests.RequestException as exc:
        result.error = f"{type(exc).__name__}: {str(exc)[:200]}"
        log.warning("SoloTodo fallo: %s", result.error)
    log.info("SoloTodo: %d publicaciones, %d consolas disponibles", result.raw_count, len(result.offers))
    return result
