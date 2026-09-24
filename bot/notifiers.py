import logging
import os
from abc import ABC, abstractmethod

import requests

from .filters import Offer

log = logging.getLogger(__name__)


def clp(value: int) -> str:
    return f"${value:,.0f}".replace(",", ".")


def format_offer(o: Offer) -> str:
    return f"{o.store} | {o.variant} | {clp(o.price)}\n{o.title}\n{o.url}"


class Notifier(ABC):
    @classmethod
    @abstractmethod
    def from_env(cls) -> "Notifier | None": ...

    @abstractmethod
    def send(self, title: str, body: str, url: str | None = None, priority: str = "high") -> None: ...


class NtfyNotifier(Notifier):
    def __init__(self, topic: str, server: str):
        self.endpoint = f"{server.rstrip('/')}/{topic}"

    @classmethod
    def from_env(cls):
        topic = os.getenv("NTFY_TOPIC")
        return cls(topic, os.getenv("NTFY_SERVER", "https://ntfy.sh")) if topic else None

    def send(self, title, body, url=None, priority="high"):
        headers = {"Title": title, "Priority": priority, "Tags": "video_game"}
        if url:
            headers["Click"] = url
        requests.post(self.endpoint, data=body.encode(), headers=headers, timeout=15).raise_for_status()


class TelegramNotifier(Notifier):
    def __init__(self, token: str, chat_id: str):
        self.endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id = chat_id

    @classmethod
    def from_env(cls):
        token, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
        return cls(token, chat) if token and chat else None

    def send(self, title, body, url=None, priority="high"):
        payload = {
            "chat_id": self.chat_id,
            "text": f"{title}\n\n{body}",
            "disable_web_page_preview": True,
            "disable_notification": priority in ("min", "low"),
        }
        requests.post(self.endpoint, json=payload, timeout=15).raise_for_status()


NOTIFIERS: tuple[type[Notifier], ...] = (NtfyNotifier, TelegramNotifier)


def configured() -> list[Notifier]:
    return [n for n in (cls.from_env() for cls in NOTIFIERS) if n]


def _dispatch(title: str, body: str, url: str | None = None, priority: str = "high") -> None:
    targets = configured()
    if not targets:
        log.info("Sin notificadores push configurados")
    for target in targets:
        try:
            target.send(title, body, url, priority)
        except Exception as exc:
            log.error("%s fallo: %s", type(target).__name__, exc)


def broadcast(deals: list[Offer]) -> None:
    for deal in sorted(deals, key=lambda d: d.price):
        _dispatch(f"Xbox Series X en stock: {clp(deal.price)}", format_offer(deal), deal.url)


def summarize(results, deals: list[Offer], max_price: int) -> tuple[str, str]:
    title = (
        f"Revision Xbox: {len(deals)} oferta(s) bajo {clp(max_price)}"
        if deals
        else f"Revision Xbox: sin stock bajo {clp(max_price)}"
    )
    lines = [
        f"{r.store.name}: {'error' if r.error and not r.offers else 'ok'}, "
        f"{len(r.offers)} consola(s), {sum(o.is_deal for o in r.offers)} oferta(s)"
        for r in results
    ]
    lines += [f"- {d.store} {clp(d.price)} {d.variant}" for d in sorted(deals, key=lambda d: d.price)]
    return title, "\n".join(lines)


def send_summary(results, deals: list[Offer], max_price: int) -> None:
    title, body = summarize(results, deals, max_price)
    _dispatch(title, body, priority="high" if deals else os.getenv("SUMMARY_PRIORITY", "default"))
