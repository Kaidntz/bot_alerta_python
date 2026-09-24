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
    def send(self, title: str, body: str, url: str | None = None) -> None: ...


class NtfyNotifier(Notifier):
    def __init__(self, topic: str, server: str):
        self.endpoint = f"{server.rstrip('/')}/{topic}"

    @classmethod
    def from_env(cls):
        topic = os.getenv("NTFY_TOPIC")
        return cls(topic, os.getenv("NTFY_SERVER", "https://ntfy.sh")) if topic else None

    def send(self, title, body, url=None):
        headers = {"Title": title, "Priority": "high", "Tags": "video_game"}
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

    def send(self, title, body, url=None):
        payload = {"chat_id": self.chat_id, "text": f"{title}\n\n{body}", "disable_web_page_preview": True}
        requests.post(self.endpoint, json=payload, timeout=15).raise_for_status()


NOTIFIERS: tuple[type[Notifier], ...] = (NtfyNotifier, TelegramNotifier)


def configured() -> list[Notifier]:
    return [n for n in (cls.from_env() for cls in NOTIFIERS) if n]


def broadcast(deals: list[Offer]) -> None:
    targets = configured()
    if not targets:
        log.info("Sin notificadores push configurados; solo se registra en data/alerts.json")
        return
    for deal in sorted(deals, key=lambda d: d.price):
        title = f"Xbox Series X en stock: {clp(deal.price)}"
        for target in targets:
            try:
                target.send(title, format_offer(deal), deal.url)
            except Exception as exc:
                log.error("%s fallo: %s", type(target).__name__, exc)
