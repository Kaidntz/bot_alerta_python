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
    assert set(offers) == {"1", "2", "3", "8", "ld1"}
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
    assert len(first) == 3
    assert state.diff_new_deals(results) == []
