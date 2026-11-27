"""«Свой сбор»: a participant gathers a company for something that has no afisha page.

A quest room for five, padel for four, volleyball, a poker evening — the host says what, when, where and
how many people are needed. The gathering shows in the afisha («Сборы»); whoever presses «Присоединиться»
gets into the host's company with a shared chat, until the places run out. Admins see each new gathering
in the bot and can hide it with /hide.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import texts
from .api import CATEGORIES, TZ, event_card, require_adult, require_clean
from .auth import current_user
from .config import settings
from .db import get_session
from .groups import GATHERING_MAX, gathering_info, members_of
from .models import Attendance, Event, Group, GroupMember, User, utcnow
from .notify import notifier

router = APIRouter(prefix="/api")

ACTIVE_LIMIT = 3            # upcoming gatherings of one person at a time
DAILY_LIMIT = 3             # new gatherings of one person in 24 hours
EARLIEST = timedelta(hours=2)
LATEST = timedelta(days=30)


class GatheringIn(BaseModel):
    title: str = Field(min_length=3, max_length=100)        # «Квест „Пила“ на Бауманской»
    category: str = "other"
    starts_at: str                                           # local time, 2026-12-05T19:00
    place: str = Field(min_length=2, max_length=120)
    address: str = Field(default="", max_length=200)
    need: int = Field(ge=1, le=GATHERING_MAX - 1)          # how many people the host looks for
    price: str = Field(default="", max_length=60)           # «≈1 500 ₽ с человека, делим поровну»
    description: str = Field(default="", max_length=800)
    url: str = Field(default="", max_length=300)


@router.post("/gatherings")
async def create(body: GatheringIn, me: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    require_adult(me)
    require_clean(body.title, body.place, body.address, body.price, body.description)
    if me.is_banned:
        raise HTTPException(403, "Создание сборов недоступно")
    try:
        local = datetime.fromisoformat(body.starts_at.strip())
    except ValueError:
        raise HTTPException(400, "Проверьте дату и время")
    local = local if local.tzinfo else local.replace(tzinfo=TZ)
    starts = local.astimezone(timezone.utc).replace(tzinfo=None)
    now = utcnow()
    if starts < now + EARLIEST:
        raise HTTPException(400, "Сбор можно создать минимум за 2 часа до начала")
    if starts > now + LATEST:
        raise HTTPException(400, "Сбор можно создать не дальше чем на месяц вперёд")
    if body.url and not body.url.startswith(("https://", "http://")):
        raise HTTPException(400, "Ссылка должна начинаться с https://")
    active = await session.scalar(select(func.count()).select_from(Event).where(
        Event.source == "user", Event.organizer_id == me.id, Event.published, Event.starts_at > now)) or 0
    recent = await session.scalar(select(func.count()).select_from(Event).where(
        Event.source == "user", Event.organizer_id == me.id, Event.created_at > now - timedelta(days=1))) or 0
    if active >= ACTIVE_LIMIT or recent >= DAILY_LIMIT:
        raise HTTPException(429, f"Можно вести не больше {ACTIVE_LIMIT} сборов одновременно")

    event = Event(source="user", title=body.title.strip(), description=body.description.strip(),
                  category=body.category if body.category in CATEGORIES else "other", starts_at=starts,
                  place=body.place.strip(), address=body.address.strip(), price=body.price.strip(),
                  url=body.url.strip(), capacity=body.need + 1, organizer_id=me.id, city=me.city)
    session.add(event)
    await session.flush()
    event.source_id = str(event.id)
    group = Group(event_id=event.id, captain_id=me.id)
    session.add(group)
    await session.flush()
    session.add(GroupMember(group_id=group.id, user_id=me.id))
    session.add(Attendance(user_id=me.id, event_id=event.id, status="looking", wants_group=True,
                           note="Собираю компанию"))
    await session.commit()

    for admin in settings.admin_ids:
        await notifier.send(admin, texts.new_gathering(me, event), f"event-{event.id}", button="Посмотреть")
    return {**event_card(event), "group_id": group.id}


@router.post("/gatherings/{event_id}/cancel")
async def cancel(event_id: int, me: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    """The host calls the gathering off: it leaves the afisha, the company gets a message."""
    event = await session.get(Event, event_id)
    if event is None or event.source != "user" or (event.organizer_id != me.id and not settings.is_admin(me)):
        raise HTTPException(404, "Сбор не найден")
    event.published = False
    group = (await session.execute(select(Group).where(Group.event_id == event.id))).scalars().first()
    people = [u for u in await members_of(session, group.id) if u.id != me.id] if group else []
    await session.execute(delete(Attendance).where(Attendance.event_id == event.id))
    await session.commit()
    for user in people:
        await notifier.send(user.tg_id, texts.gathering_cancelled(event), "", button="Афиша")
    return {"ok": True}


@router.get("/gatherings/{event_id}")
async def info(event_id: int, me: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    event = await session.get(Event, event_id)
    if event is None or event.source != "user":
        raise HTTPException(404, "Сбор не найден")
    return await gathering_info(session, event, me)
