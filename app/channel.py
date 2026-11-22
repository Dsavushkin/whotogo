"""Posts to the project's Telegram channel «Куда сходить в Москве».

The channel is connected by adding the bot as an administrator (an admin of the project must do it);
the bot remembers the channel and posts on schedule:
  · every day at 11:00 — «Куда сходить сегодня»;
  · Thursday at 19:00 — «Куда сходить на выходных».
Buttons in channels cannot open a Mini App directly, so links use t.me/<bot>?startapp=event-<id>.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from . import texts
from .config import settings
from .db import Session
from .models import Event, Setting

log = logging.getLogger("whotogo.channel")

# weekday (None = every day): (hour, kind)
SCHEDULE = [(None, 11, "today"), (3, 19, "weekend")]
TITLES = {"today": "Куда сходить сегодня", "weekend": "Куда сходить на выходных"}


async def get_setting(key: str) -> str:
    async with Session() as session:
        row = await session.get(Setting, key)
        return row.value if row else ""


async def set_setting(key: str, value: str) -> None:
    async with Session() as session:
        row = await session.get(Setting, key)
        if row is None:
            session.add(Setting(key=key, value=value))
        else:
            row.value = value
        await session.commit()


def app_link(target: str = "") -> str:
    return f"https://t.me/{settings.bot_username}?startapp" + (f"={target}" if target else "")


async def channel_picks(kind: str, now: Optional[datetime] = None, most: int = 6) -> list:
    """Evening events first, people looking for company, with posters, at most two per category."""
    from .api import counts_for, day_bounds
    start, end = day_bounds(kind, now)
    if kind == "today":
        start = max(start, (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(tzinfo=None)
                    + timedelta(hours=1))
    async with Session() as session:
        events = list((await session.execute(
            select(Event).where(Event.published, Event.city == settings.city, Event.starts_at >= start,
                                Event.starts_at < end).order_by(Event.starts_at).limit(400))).scalars())
        counts = await counts_for(session, [e.id for e in events])

    def score(event: Event) -> float:
        going, looking = counts.get(event.id, (0, 0))
        hour = texts.local(event.starts_at).hour
        return (looking * 5 + going * 2 + (3 if event.image else 0) + (2 if 17 <= hour <= 22 else 0)
                + (1 if 12 <= hour < 17 else 0))

    picked, per_category = [], {}
    for event in sorted(events, key=lambda e: (-score(e), e.starts_at)):
        if per_category.get(event.category, 0) >= 2:
            continue
        per_category[event.category] = per_category.get(event.category, 0) + 1
        picked.append((event, *counts.get(event.id, (0, 0))))
        if len(picked) >= most:
            break
    return sorted(picked, key=lambda p: p[0].starts_at)


def post_text(kind: str, picks: list, now: Optional[datetime] = None) -> str:
    local_now = (now or datetime.now(timezone.utc)).astimezone(texts.TZ)
    head = TITLES[kind]
    if kind == "today":
        head += f", {local_now.day} {texts.MONTHS[local_now.month - 1]}"
    lines = [f"<b>{head}</b>", ""]
    for event, going, looking in picks:
        start = texts.local(event.starts_at)
        time = f"{start:%H:%M}" if kind == "today" else f"{texts.WEEKDAYS[start.weekday()]} {start:%H:%M}"
        place = f" · {texts.q(event.place)}" if event.place else ""
        extra = f"\n    🙋 {looking} ищут компанию" if looking else ""
        lines.append(f"▪️ <b>{time}</b> <a href=\"{app_link(f'event-{event.id}')}\">{texts.q(event.title)}</a>"
                     f"{place}{extra}")
    lines += ["", "Не с кем пойти? Откройте событие и нажмите «Ищу компанию» — увидите, кто ещё идёт."]
    return "\n".join(lines)


async def post(bot, kind: str, now: Optional[datetime] = None) -> bool:
    channel = await get_setting("channel")
    if not channel:
        return False
    picks = await channel_picks(kind, now)
    if len(picks) < 3:
        return False
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from .notify import NO_PREVIEW
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Найти компанию", url=app_link())],
        [InlineKeyboardButton(text="Вся афиша", url=settings.webapp_url.rstrip("/") + "/afisha")],
    ])
    text = post_text(kind, picks, now)
    poster = next((e.image for e, _, _ in picks if e.image), "")
    if poster and len(text) <= 1000:
        try:
            await bot.send_photo(channel, poster, caption=text, parse_mode="HTML", reply_markup=keyboard)
            return True
        except Exception as error:  # the poster could not be fetched: post as text
            log.warning("channel photo failed: %s", error)
    await bot.send_message(channel, text, parse_mode="HTML", reply_markup=keyboard, link_preview_options=NO_PREVIEW)
    return True


async def run_schedule(bot, now: Optional[datetime] = None) -> list:
    """Called every few minutes; posts what is due and has not been posted today."""
    local_now = (now or datetime.now(timezone.utc)).astimezone(texts.TZ)
    done = []
    for weekday, hour, kind in SCHEDULE:
        if weekday is not None and local_now.weekday() != weekday:
            continue
        if not hour <= local_now.hour < hour + 2:
            continue
        key = f"posted:{kind}:{local_now.date().isoformat()}"
        if await get_setting(key):
            continue
        try:
            if await post(bot, kind, now):
                await set_setting(key, "1")
                done.append(kind)
        except Exception as error:
            log.warning("channel post %s failed: %s", kind, error)
    return done
