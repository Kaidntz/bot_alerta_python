import os
from dataclasses import dataclass, field

MAX_PRICE = int(os.getenv("MAX_PRICE", "900000"))
MIN_PLAUSIBLE_PRICE = 200000
CONCURRENCY = int(os.getenv("CONCURRENCY", "3"))
NAV_TIMEOUT_MS = 60000
DATA_DIR = os.getenv("DATA_DIR", "data")

LINK_PATTERN = r"series\s*x"


@dataclass(frozen=True)
class Store:
    id: str
    name: str
    urls: tuple[str, ...]
    wait_selector: str | None = None
    extra_wait_ms: int = 2500
    headers: dict = field(default_factory=dict)


STORES: tuple[Store, ...] = (
    Store("falabella", "Falabella", ("https://www.falabella.com/falabella-cl/search?Ntt=xbox+series+x",)),
    Store("paris", "Paris", ("https://www.paris.cl/search?q=xbox%20series%20x",)),
    Store("ripley", "Ripley", ("https://simple.ripley.cl/search/xbox%20series%20x",)),
    Store("lider", "Lider", ("https://www.lider.cl/search?q=xbox%20series%20x",)),
    Store("microplay", "Microplay", ("https://www.microplay.cl/busqueda/?q=xbox+series+x",)),
    Store("weplay", "Weplay", ("https://www.weplay.cl/catalogsearch/result/?q=xbox+series+x",)),
    Store("pcfactory", "PC Factory", ("https://www.pcfactory.cl/buscar?valor=xbox%20series%20x",)),
    Store("spdigital", "SP Digital", ("https://www.spdigital.cl/search?q=xbox%20series%20x",)),
    Store(
        "mercadolibre",
        "Mercado Libre",
        (
            "https://listado.mercadolibre.cl/consola-xbox-series-x",
            "https://listado.mercadolibre.cl/xbox-series-x-digital-edition",
        ),
    ),
)

ENABLED = {s.strip() for s in os.getenv("STORES", "").split(",") if s.strip()}


def active_stores() -> tuple[Store, ...]:
    return tuple(s for s in STORES if not ENABLED or s.id in ENABLED)
