"""Sends Telegram messages to users. Works as a no-op when the bot is off (tests, local preview)."""
import logging
import time
from typing import Optional

from .config import settings

log = logging.getLogger("whotogo.notify")


def markup(buttons: list):
    """Inline keyboard, one button per row. Each item is (text, target): a Mini App screen
    («event-12», «chat-3», "" for the afisha), a web link, or «cb:<data>» for a bot command."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

    rows = []
    for text, target in buttons:
        if target.startswith(("https://", "http://")):
            rows.append([InlineKeyboardButton(text=text, url=target)])
        elif target.startswith("cb:"):
            rows.append([InlineKeyboardButton(text=text, callback_data=target[3:])])
        elif settings.webapp_url.startswith("https://"):
            url = settings.webapp_url + "/" + (f"?go={target}" if target else "")
            rows.append([InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def open_markup(go: str = "", text: str = "Открыть"):
    """A single button that opens the Mini App (needs an https address)."""
    return markup([(text, go)])


def _no_preview():
    try:
        from aiogram.types import LinkPreviewOptions
        return LinkPreviewOptions(is_disabled=True)
    except ImportError:  # aiogram is not installed in some local previews
        return None


NO_PREVIEW = _no_preview()


class Notifier:
    def __init__(self) -> None:
        self.bot = None
        self.sent: list = []  # (tg_id, text, go) – kept for tests
        self._last: dict = {}

    async def send(self, tg_id: Optional[int], text: str, go: str = "", throttle_key: Optional[str] = None,
                   throttle_seconds: int = 90, button: str = "Открыть", buttons: Optional[list] = None) -> bool:
        """Text is HTML: escape whatever people typed (texts.q)."""
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
            await self.bot.send_message(tg_id, text, parse_mode="HTML", link_preview_options=NO_PREVIEW,
                                        reply_markup=markup(buttons if buttons is not None else [(button, go)]))
            return True
        except Exception as error:  # the person blocked the bot, network hiccup, etc.
            log.warning("message to %s not delivered: %s", tg_id, error)
            return False


notifier = Notifier()

# What the background parts are doing; shown by /api/diag (no secrets here).
status: dict = {"bot": "off", "bot_error": "", "import": None}
