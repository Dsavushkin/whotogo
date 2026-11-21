"""Background work: refresh the afisha and ask guests the morning after an event."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from typing import Optional

from sqlalchemy import func, or_, select

from .config import settings
from .db import Session
from .importer import run_import
from .models import Attendance, Event, User, utcnow
from .notify import notifier

log = logging.getLogger("whotogo.jobs")


async def send_after_prompts(now_local_hour: int = -1) -> int:
    """«С кем хочется увидеться ещё?» – once per guest, 12–48 hours after the start, in daytime."""
    hour = now_local_hour if now_local_hour >= 0 else datetime.now(timezone.utc).astimezone(
        ZoneInfo(settings.timezone)).hour
    if not 10 <= hour < 21:
        return 0
    now, sent = utcnow(), 0
    async with Session() as session:
        rows = (await session.execute(
            select(Attendance, Event, User).join(Event, Event.id == Attendance.event_id)
            .join(User, User.id == Attendance.user_id)
            .where(Attendance.after_prompted.is_(False), Event.starts_at <= now - timedelta(hours=12),
                   Event.starts_at >= now - timedelta(hours=48)).limit(500))).all()
        guests: dict = {}
        for attendance, event, user in rows:
            if event.id not in guests:
                guests[event.id] = await session.scalar(
                    select(func.count()).select_from(Attendance).where(Attendance.event_id == event.id))
            attendance.after_prompted = True
            if guests[event.id] >= 2 and not user.is_banned:
                await notifier.send(user.tg_id, f"Как прошло «{event.title}»? С кем хочется увидеться ещё? "
                                    "Отметьте гостей: человек узнает об этом, только если отметит вас в ответ.",
                                    f"after-{event.id}")
                sent += 1
        await session.commit()
    return sent


WEEKDAY_NUDGES = {
    # weekday: (from hour, to hour, title)
    3: (17, 20, "Планы на выходные уже есть?"),
    4: (17, 20, "Пятница! Куда идёте вечером?"),
    5: (11, 14, "Суббота — куда сходить сегодня?"),
}


async def pick_events(session, start: datetime, end: datetime, limit: int = 3) -> list:
    """The most wanted events of the period: where people already look for company, then where they go."""
    from .api import counts_for
    events = list((await session.execute(
        select(Event).where(Event.published, Event.city == settings.city, Event.starts_at >= start,
                            Event.starts_at < end).order_by(Event.starts_at).limit(300))).scalars())
    counts = await counts_for(session, [e.id for e in events])
    events.sort(key=lambda e: (-counts.get(e.id, (0, 0))[1], -counts.get(e.id, (0, 0))[0], not e.image, e.starts_at))
    return [(e, *counts.get(e.id, (0, 0))) for e in events[:limit]]


async def send_weekend_nudges(now: Optional[datetime] = None) -> int:
    """Thursday to Saturday: one reminder a day to people who have nothing planned until Sunday night."""
    tz = ZoneInfo(settings.timezone)
    local = (now or datetime.now(timezone.utc)).astimezone(tz)
    rule = WEEKDAY_NUDGES.get(local.weekday())
    if not rule or not rule[0] <= local.hour < rule[1]:
        return 0
    to_utc = lambda d: d.astimezone(timezone.utc).replace(tzinfo=None)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    now_utc, today_utc = to_utc(local), to_utc(midnight)
    weekend_end = to_utc(midnight + timedelta(days=7 - midnight.weekday()))  # Monday 00:00
    sent = 0
    async with Session() as session:
        busy = {u for (u,) in await session.execute(
            select(Attendance.user_id).join(Event, Event.id == Attendance.event_id)
            .where(Event.starts_at >= now_utc - timedelta(hours=3), Event.starts_at < weekend_end))}
        people = (await session.execute(select(User).where(
            User.tg_id.is_not(None), User.adult_ok, User.is_banned.is_(False), User.nudges,
            or_(User.last_nudge_at.is_(None), User.last_nudge_at < today_utc)))).scalars().all()
        people = [p for p in people if p.id not in busy]
        if not people:
            return 0
        picks = await pick_events(session, now_utc + timedelta(minutes=30), to_utc(midnight + timedelta(days=1)))
        if len(picks) < 3:
            more = await pick_events(session, to_utc(midnight + timedelta(days=1)), weekend_end, 3 - len(picks))
            picks += more
        lines = []
        for event, going, looking in picks:
            start = event.starts_at.replace(tzinfo=timezone.utc).astimezone(tz)
            when = start.strftime("%H:%M") if start.date() == local.date() else start.strftime("%d.%m, %H:%M")
            extra = f", {looking} ищут компанию" if looking else ""
            lines.append(f"• {event.title} — {when}{extra}")
        text = rule[2]
        if lines:
            text += "\n\nЧто выбирают:\n" + "\n".join(lines)
        text += "\n\nОтметьте «Ищу компанию» — и найдётся, с кем пойти.\nНе присылать такие напоминания: /quiet"
        for person in people:
            person.last_nudge_at = now_utc
            await notifier.send(person.tg_id, text, "")
            sent += 1
        await session.commit()
    return sent


async def run_jobs() -> None:
    last_import = None  # the first import runs right after the start
    loop = asyncio.get_running_loop()
    while True:
        try:
            if settings.timepad_token and (
                    last_import is None or loop.time() - last_import > settings.import_every_hours * 3600):
                last_import = loop.time()
                await run_import()
            await send_after_prompts()
            await send_weekend_nudges()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("background job failed")
        await asyncio.sleep(600)
