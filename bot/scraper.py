import asyncio
import logging
import os
import re
from pathlib import Path
from dataclasses import dataclass, field

from playwright.async_api import Browser, async_playwright

from .config import CONCURRENCY, LINK_PATTERN, NAV_TIMEOUT_MS, Store
from .filters import Offer, to_offer

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

EXTRACT_JS = """
(pattern) => {
  const match = new RegExp(pattern, 'i');
  const hasPrice = /\\$\\s?\\d{1,3}(?:[.\\s]\\d{3})+/;
  const noise = /^(utm_|tracking|position|search_layout|type$|sid$|polycard|reco|searchVariation)/i;
  const cleanUrl = (href) => {
    const u = new URL(href, location.href);
    u.hash = '';
    [...u.searchParams.keys()].filter((k) => noise.test(k)).forEach((k) => u.searchParams.delete(k));
    return u.href;
  };
  const headingSel = 'h1,h2,h3,h4,[class*="title" i],[class*="name" i],[class*="nombre" i],[class*="description" i]';
  const titleOf = (a) => [
    ...[...a.querySelectorAll(headingSel)].map((h) => h.innerText),
    a.querySelector('img')?.alt, a.title, a.getAttribute('aria-label'), a.innerText,
  ].map((t) => (t ?? '').trim()).find((t) => match.test(t) && !/\\$\\s?\\d/.test(t)) ?? '';
  const cardOf = (a) => {
    let node = a;
    for (let i = 0; i < 10 && node.parentElement; i++) {
      if (hasPrice.test(node.innerText ?? '')) return node;
      node = node.parentElement;
    }
    return null;
  };
  const byUrl = new Map();
  for (const a of document.querySelectorAll('a[href]')) {
    const title = titleOf(a);
    if (!title) continue;
    const card = cardOf(a);
    if (!card || (card.innerText ?? '').length > 2500) continue;
    const url = cleanUrl(a.href);
    const prev = byUrl.get(url);
    if (!prev || title.length < prev.title.length) byUrl.set(url, { url, title, text: card.innerText });
  }
  const ld = [...document.querySelectorAll('script[type="application/ld+json"]')]
    .flatMap((s) => { try { return [JSON.parse(s.textContent)].flat(); } catch { return []; } })
    .flatMap((n) => n?.['@graph'] ?? n?.itemListElement?.map((i) => i.item ?? i) ?? [n])
    .filter((n) => n?.['@type'] === 'Product' && match.test(n.name ?? ''));
  for (const p of ld) {
    const offer = [p.offers].flat()[0] ?? {};
    const url = cleanUrl(p.url ?? offer.url ?? location.href);
    if (byUrl.has(url)) continue;
    const price = offer.price ?? offer.lowPrice;
    const stock = /OutOfStock|SoldOut/i.test(offer.availability ?? '') ? ' agotado' : '';
    if (price) byUrl.set(url, { url, title: p.name, text: `$${Number(price).toLocaleString('es-CL')}${stock}` });
  }
  return [...byUrl.values()];
}
"""

DIAG_JS = """
() => ({
  title: document.title,
  url: location.href,
  links: document.querySelectorAll('a[href]').length,
  mentions: (document.body?.innerText.match(/series\\s*x/gi) ?? []).length,
  snippet: (document.body?.innerText ?? '').replace(/\\s+/g, ' ').slice(0, 300),
})
"""

DEBUG = os.getenv("DEBUG_DUMP") == "1"
DEBUG_DIR = Path("debug")


@dataclass
class StoreResult:
    store: Store
    offers: list[Offer] = field(default_factory=list)
    raw_count: int = 0
    error: str | None = None
    diagnostics: list[dict] = field(default_factory=list)


async def _scrape_url(browser: Browser, store: Store, url: str) -> tuple[list[dict], dict]:
    context = await browser.new_context(
        user_agent=USER_AGENT,
        locale="es-CL",
        timezone_id="America/Santiago",
        viewport={"width": 1366, "height": 900},
        extra_http_headers=store.headers,
    )
    try:
        page = await context.new_page()
        await page.route("**/*.{png,jpg,jpeg,webp,gif,svg,woff,woff2,mp4}", lambda r: r.abort())
        await page.goto(url, wait_until="commit", timeout=NAV_TIMEOUT_MS)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT_MS)
        except Exception:
            pass
        if store.wait_selector:
            await page.wait_for_selector(store.wait_selector, timeout=NAV_TIMEOUT_MS)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        for _ in range(3):
            await page.mouse.wheel(0, 2500)
            await page.wait_for_timeout(600)
        await page.wait_for_timeout(store.extra_wait_ms)
        raws = await page.evaluate(EXTRACT_JS, LINK_PATTERN)
        diag = await page.evaluate(DIAG_JS)
        if DEBUG:
            DEBUG_DIR.mkdir(exist_ok=True)
            name = f"{store.id}-{store.urls.index(url)}"
            await page.screenshot(path=DEBUG_DIR / f"{name}.png", full_page=False)
            (DEBUG_DIR / f"{name}.html").write_text(await page.content(), encoding="utf-8")
        return raws, diag
    finally:
        await context.close()


def _identity(offer) -> tuple:
    return re.sub(r"\W+", " ", offer.title.lower()).strip(), offer.price


async def _scrape_store(browser: Browser, store: Store, sem: asyncio.Semaphore) -> StoreResult:
    result = StoreResult(store)
    async with sem:
        for url in store.urls:
            try:
                raws, diag = await _scrape_url(browser, store, url)
            except Exception as exc:
                result.error = f"{type(exc).__name__}: {str(exc).splitlines()[0][:200]}"
                log.warning("%s fallo en %s: %s", store.name, url, result.error)
                continue
            result.raw_count += len(raws)
            result.diagnostics.append(diag)
            seen = {_identity(o) for o in result.offers}
            for offer in filter(None, (to_offer(store.id, store.name, r) for r in raws)):
                if _identity(offer) not in seen:
                    seen.add(_identity(offer))
                    result.offers.append(offer)
    log.info("%s: %d candidatos, %d consolas", store.name, result.raw_count, len(result.offers))
    return result


async def scrape_all(stores: tuple[Store, ...]) -> list[StoreResult]:
    sem = asyncio.Semaphore(CONCURRENCY)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True, args=["--disable-blink-features=AutomationControlled"]
        )
        try:
            return await asyncio.gather(*(_scrape_store(browser, s, sem) for s in stores))
        finally:
            await browser.close()
