"""Sends Telegram messages to users. Works as a no-op when the bot is off (tests, local preview)."""
import logging
import time
from typing import Optional

from .config import settings

log = logging.getLogger("whotogo.notify")


def open_markup(go: str = "", text: str = "Открыть"):
    """Inline button that opens the Mini App (needs an https address)."""
    if not settings.webapp_url.startswith("https://"):
        return None
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

    url = settings.webapp_url + "/" + (f"?go={go}" if go else "")
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))]])


class Notifier:
    def __init__(self) -> None:
        self.bot = None
        self.sent: list = []  # (tg_id, text, go) – kept for tests
        self._last: dict = {}

    async def send(self, tg_id: Optional[int], text: str, go: str = "", throttle_key: Optional[str] = None,
                   throttle_seconds: int = 90) -> bool:
        if not tg_id:  # a site user without Telegram: nothing to send yet
            return False
        if throttle_key:
            key, now = (tg_id, throttle_key), time.monotonic()
            if now - self._last.get(key, -1e9) < throttle_seconds:
                return False
            self._last[key] = now
        self.sent.append((tg_id, text, go))
        if self.bot is None:
            return False
        try:
            await self.bot.send_message(tg_id, text, reply_markup=open_markup(go))
            return True
        except Exception as error:  # the person blocked the bot, network hiccup, etc.
            log.warning("message to %s not delivered: %s", tg_id, error)
            return False


notifier = Notifier()

# What the background parts are doing; shown by /api/diag (no secrets here).
status: dict = {"bot": "off", "bot_error": "", "import": None}
