import asyncio
import http.server
import threading
from functools import partial
from pathlib import Path

import pytest

from bot.config import Store
from bot.filters import is_target_console, parse_prices, variant_of
from bot.scraper import scrape_all


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Consola Xbox Series X 1TB", True),
        ("Xbox Series X Digital Edition Robot White", True),
        ("Consola Xbox Series X + Juego Forza", True),
        ("Control Inalambrico Xbox Series X|S", False),
        ("Consola Xbox Series S 512GB", False),
        ("Xbox Series X 2TB Galaxy Black", False),
        ("Juego Halo Infinite Xbox Series X", False),
        ("Xbox Series X Reacondicionada", False),
        ("FLIGHTSTICK FOR XBOX SERIES X/S", False),
        ("HORI Volante Racing Wheel Overdrive - Xbox Series X - Sniper", False),
        ("Audifonos Turtle Beach Xbox Series X|S", False),
        ("Consola Microsoft Xbox Series X Digital Edition 1TB Blanco", True),
    ],
)
def test_is_target_console(title, expected):
    assert is_target_console(title) is expected


def test_parse_prices_ignores_installments():
    assert parse_prices("$ 719.990 6 cuotas de $119.998") == (719990,)


def test_variant():
    assert variant_of("Xbox Series X Digital Edition").startswith("Digital")
    assert variant_of("Consola Xbox Series X 1TB") == "Estandar 1TB"


@pytest.fixture(scope="module")
def server():
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(Path(__file__).parent))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def test_scrape_fixture(server):
    store = Store("fx", "Fixture", (f"{server}/fixture.html",), extra_wait_ms=0)
    [result] = asyncio.run(scrape_all((store,)))
    assert result.error is None
    offers = {o.url.rsplit("/", 1)[-1]: o for o in result.offers}
    assert set(offers) == {"1", "2", "3", "8", "9", "ld1"}
    assert offers["9"].title == "Consola Xbox Series X 1TB Negra"
    assert offers["1"].price == 719990 and offers["1"].is_deal
    assert not offers["2"].is_deal
    assert not offers["3"].in_stock
    assert offers["8"].price == 829990 and offers["8"].is_deal
    assert offers["ld1"].is_deal and offers["ld1"].variant.startswith("Digital")


def test_state_alerts_only_once(server, tmp_path, monkeypatch):
    import bot.state as state

    monkeypatch.setattr(state, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(state, "ALERTS_FILE", tmp_path / "alerts.json")
    store = Store("fx", "Fixture", (f"{server}/fixture.html",), extra_wait_ms=0)
    results = asyncio.run(scrape_all((store,)))
    first = state.diff_new_deals(results)
    state.record_alerts(first)
    assert len(first) == 4
    assert state.diff_new_deals(results) == []


class FakeSoloTodo:
    def available_products(self, search):
        return {
            90860: "Microsoft Xbox Series X",
            500001: "Microsoft Xbox Series X Digital Edition (Robot White)",
            265618: "Microsoft Xbox Series S 1 TB",
            500002: "Microsoft Xbox Series X 2 TB Galaxy Black Special Edition",
        }

    def entities(self, ids):
        assert set(ids) == {90860, 500001}
        reg = lambda avail, offer, normal: {"is_available": avail, "offer_price": offer, "normal_price": normal}
        new = "https://schema.org/NewCondition"
        return [
            {"store": 9, "product": {"id": 90860}, "external_url": "https://f.cl/1", "condition": new,
             "active_registry": reg(True, "749990.00", "799990.00")},
            {"store": 11, "product": {"id": 500001}, "external_url": "https://p.cl/2", "condition": new,
             "active_registry": reg(True, "949990.00", "949990.00")},
            {"store": 18, "product": {"id": 90860}, "external_url": "https://r.cl/3", "condition": new,
             "active_registry": reg(False, "599990.00", "599990.00")},
            {"store": 260, "product": {"id": 90860}, "external_url": "https://m.cl/4",
             "condition": "https://schema.org/UsedCondition", "active_registry": reg(True, "500000.00", None)},
        ]

    def store_name(self, store_id):
        return {9: "Falabella", 11: "Paris"}.get(store_id, f"Tienda {store_id}")


def test_solotodo_fetch():
    from bot import solotodo

    result = solotodo.fetch(FakeSoloTodo())
    assert result.error is None
    offers = {o.url: o for o in result.offers}
    assert set(offers) == {"https://f.cl/1", "https://p.cl/2"}
    assert offers["https://f.cl/1"].is_deal and offers["https://f.cl/1"].store == "Falabella"
    assert offers["https://f.cl/1"].prices == (749990, 799990)
    assert not offers["https://p.cl/2"].is_deal
    assert offers["https://p.cl/2"].variant.startswith("Digital")


def test_summary_message():
    from bot import solotodo
    from bot.notifiers import summarize

    result = solotodo.fetch(FakeSoloTodo())
    deals = [o for o in result.offers if o.is_deal]
    title, body = summarize([result], deals, 900000)
    assert title == "Revision Xbox: 1 oferta(s) bajo $900.000"
    assert "SoloTodo: ok, 2 consola(s), 1 oferta(s)" in body
    assert "- Falabella $749.990" in body
    title, _ = summarize([result], [], 900000)
    assert title == "Revision Xbox: sin stock bajo $900.000"
