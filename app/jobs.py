"""Background work: refresh the afisha and ask guests the morning after an event."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from typing import Optional

from sqlalchemy import func, or_, select

from . import groups, texts
from .config import settings
from .db import Session
from .importer import run_import
from .models import Attendance, Block, Event, Match, User, utcnow
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
                await notifier.send(user.tg_id, texts.after_event(event), f"after-{event.id}", button="Отметить")
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
        text = texts.weekend_nudge(rule[2], picks)
        buttons = texts.picks_buttons(picks) + [("Вся афиша", "")]
        for person in people:
            person.last_nudge_at = now_utc
            await notifier.send(person.tg_id, text, buttons=buttons)
            sent += 1
        await session.commit()
    return sent


async def send_day_reminders(now: Optional[datetime] = None) -> int:
    """On the day of the event, 2–5 hours before the start (and not at night): «Сегодня в 19:00 — …»."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(tzinfo=None)
    sent = 0
    async with Session() as session:
        rows = (await session.execute(
            select(Attendance, Event, User).join(Event, Event.id == Attendance.event_id)
            .join(User, User.id == Attendance.user_id)
            .where(Attendance.reminded.is_(False), Event.published, User.tg_id.is_not(None),
                   User.is_banned.is_(False), Event.starts_at > now + timedelta(hours=2),
                   Event.starts_at <= now + timedelta(hours=5)).limit(1000))).all()
        looking_counts: dict = {}
        for attendance, event, user in rows:
            start = texts.local(event.starts_at)
            if start.date() != texts.local(now).date() or not 9 <= texts.local(now).hour < 22:
                continue
            attendance.reminded = True
            pairs = (await session.execute(select(Match).where(
                Match.event_id == event.id, Match.kind == "together",
                or_(Match.a_id == user.id, Match.b_id == user.id)))).scalars().all()
            blocked = {b if a == user.id else a for a, b in await session.execute(
                select(Block.user_id, Block.target_id).where(or_(Block.user_id == user.id, Block.target_id == user.id)))}
            chats = []
            for m in pairs:
                partner = await session.get(User, m.b_id if m.a_id == user.id else m.a_id)
                if partner and partner.id not in blocked and not partner.is_banned:
                    chats.append((m, partner))
            partners = [p for _, p in chats]
            group = await groups.my_group(session, user.id, event.id)
            if group:
                company = [p for p in await groups.members_of(session, group.id)
                           if p.id != user.id and p.id not in blocked and not p.is_banned]
                partners = company + [p for p in partners if p not in company]
            if event.id not in looking_counts:
                looking_counts[event.id] = await session.scalar(select(func.count()).select_from(Attendance).where(
                    Attendance.event_id == event.id, Attendance.status == "looking"))
            others = looking_counts[event.id] - (attendance.status == "looking")
            text = texts.day_reminder(event, partners, others, attendance.status)
            if group:
                buttons = [("Чат компании", f"group-{group.id}")]
            elif chats:
                buttons = [("Открыть чат", f"chat-{chats[0][0].id}")]
            elif attendance.status == "looking":
                buttons = [("Кто ищет компанию", f"people-{event.id}")]
            else:
                buttons = [("Открыть событие", f"event-{event.id}")]
            await notifier.send(user.tg_id, text, buttons=buttons)
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
            await send_day_reminders()
            async with Session() as session:
                await groups.assemble_upcoming(session)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("background job failed")
        await asyncio.sleep(600)
