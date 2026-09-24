import re
from dataclasses import dataclass

from .config import MAX_PRICE, MIN_PLAUSIBLE_PRICE

SERIES_X = re.compile(r"xbox\s*series\s*x(?![a-z])", re.I)
ALWAYS_EXCLUDE = re.compile(
    r"series\s*s\b|galaxy|2\s*tb|usad[oa]|reacondicionad|seminuev|open\s*box|caja\s*da[nñ]ada|repuesto",
    re.I,
)
ACCESSORY = re.compile(
    r"control|joystick|mando|juego|game\b|cable|disco|ssd|expansi|soporte|funda|skin|vinilo|sticker|"
    r"cargador|bater[ií]a|aud[ií]fono|headset|base\b|ventilador|cooler|stand|protector|compatible|"
    r"tarjeta|gift|suscripci|game\s*pass|carcasa|mochila|bolso|estuche",
    re.I,
)
CONSOLE = re.compile(r"consola", re.I)
DIGITAL = re.compile(r"digital|all[\s-]*digital|sin\s*lector", re.I)
OUT_OF_STOCK = re.compile(
    r"agotad[oa]|sin\s*stock|no\s*disponible|fuera\s*de\s*stock|pr[oó]ximamente|av[ií]same|"
    r"notif[ií]came|sin\s*unidades|stock\s*:\s*0",
    re.I,
)
PRICE = re.compile(r"\$\s?(\d{1,3}(?:[.\s]\d{3})+)")


@dataclass(frozen=True)
class Offer:
    store_id: str
    store: str
    title: str
    url: str
    price: int
    prices: tuple[int, ...]
    variant: str
    in_stock: bool

    @property
    def key(self) -> str:
        return f"{self.store_id}|{self.url}"

    @property
    def is_deal(self) -> bool:
        return self.in_stock and self.price < MAX_PRICE


def parse_prices(text: str) -> tuple[int, ...]:
    values = {int(re.sub(r"\D", "", m)) for m in PRICE.findall(text)}
    return tuple(sorted(v for v in values if v >= MIN_PLAUSIBLE_PRICE))


def is_target_console(title: str) -> bool:
    if not SERIES_X.search(title) or ALWAYS_EXCLUDE.search(title):
        return False
    return bool(CONSOLE.search(title)) or not ACCESSORY.search(title)


def variant_of(title: str) -> str:
    return "Digital Edition (blanca)" if DIGITAL.search(title) else "Estandar 1TB"


def to_offer(store_id: str, store: str, raw: dict) -> Offer | None:
    title = " ".join(raw.get("title", "").split())
    if not is_target_console(title):
        return None
    prices = parse_prices(raw.get("text", ""))
    if not prices:
        return None
    return Offer(
        store_id=store_id,
        store=store,
        title=title,
        url=raw["url"],
        price=prices[0],
        prices=prices,
        variant=variant_of(title),
        in_stock=not OUT_OF_STOCK.search(raw.get("text", "")),
    )
