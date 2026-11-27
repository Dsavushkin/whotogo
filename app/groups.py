"""Companies of 3–5 people: «Соберите мне компанию».

A person who doesn't want to go one-on-one with a stranger asks the service for a company. The waiting
people of one event are put into groups of 3–5 with a shared chat. A newcomer joins an existing group
first, if there is room. Two people are enough only when the event is a few hours away.
"""
import math
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import progress, texts
from .api import SOON, blocked_ids, event_card, require_clean, to_local_iso, user_card
from .auth import current_user
from .db import get_session
from .models import Attendance, Block, Event, Group, GroupMember, GroupMessage, User, utcnow
from .notify import notifier

router = APIRouter(prefix="/api")

SMALLEST, LARGEST = 3, 5
GATHERING_MAX = 10  # «Свой сбор»: the host plus up to nine people


def group_limit(event: Event) -> int:
    """How many people one company of this event takes. A gathering is one company of the size its host chose."""
    if event.source == "user":
        return max(2, min(event.capacity or LARGEST, GATHERING_MAX))
    return LARGEST
PAIR_IS_ENOUGH = timedelta(hours=4)  # close to the start two waiting people get a chat too


def fits(user: User, girls_only: bool, group_girls_only: bool) -> bool:
    """«Только с девушками» people go only into all-women groups; such groups take only women."""
    if girls_only:
        return group_girls_only
    return not group_girls_only or user.gender == "f"


async def blocks_among(session: AsyncSession, ids: set[int]) -> set[tuple[int, int]]:
    if not ids:
        return set()
    rows = await session.execute(select(Block.user_id, Block.target_id).where(
        or_(Block.user_id.in_(ids), Block.target_id.in_(ids))))
    return {pair for a, b in rows for pair in ((a, b), (b, a))}


async def members_of(session: AsyncSession, group_id: int) -> list[User]:
    return list((await session.execute(
        select(User).join(GroupMember, GroupMember.user_id == User.id).where(GroupMember.group_id == group_id)
        .order_by(GroupMember.created_at))).scalars())


async def my_group(session: AsyncSession, user_id: int, event_id: int) -> Optional[Group]:
    return (await session.execute(select(Group).join(GroupMember, GroupMember.group_id == Group.id).where(
        Group.event_id == event_id, GroupMember.user_id == user_id))).scalars().first()


async def assemble(session: AsyncSession, event: Event, now: Optional[datetime] = None) -> int:
    """Puts the waiting people of one event into groups. Returns how many people got a group."""
    now = now or utcnow()
    if event.starts_at <= now + SOON:
        return 0
    groups = list((await session.execute(select(Group).where(Group.event_id == event.id)
                                          .order_by(Group.created_at))).scalars())
    members: dict[int, list[int]] = {g.id: [] for g in groups}
    for group_id, user_id in await session.execute(
            select(GroupMember.group_id, GroupMember.user_id).where(GroupMember.group_id.in_(members or [0]))):
        members[group_id].append(user_id)
    placed = {u for ids in members.values() for u in ids}
    waiting = [(a, u) for a, u in (await session.execute(
        select(Attendance, User).join(User, User.id == Attendance.user_id)
        .where(Attendance.event_id == event.id, Attendance.wants_group.is_(True), Attendance.status == "looking",
               User.is_banned.is_(False)).order_by(Attendance.created_at))).all() if u.id not in placed]
    if not waiting:
        return 0
    largest = group_limit(event)
    blocked = await blocks_among(session, placed | {u.id for _, u in waiting})
    clash = lambda user_id, ids: any((user_id, other) in blocked for other in ids)
    joined: list[tuple[Group, User]] = []
    created: list[Group] = []

    # 1. Room in a group that already exists — the smallest one first.
    rest = []
    for attendance, user in waiting:
        options = [g for g in groups if len(members[g.id]) < largest and fits(user, attendance.girls_only, g.girls_only)
                   and not clash(user.id, members[g.id])]
        if options:
            group = min(options, key=lambda g: len(members[g.id]))
            members[group.id].append(user.id)
            session.add(GroupMember(group_id=group.id, user_id=user.id))
            joined.append((group, user))
        else:
            rest.append((attendance, user))

    # 2. New groups from those still waiting, separately for «только с девушками».
    users = {u.id: u for _, u in rest}
    # A gathering stays one company: the host's. Whoever doesn't fit waits for a free place.
    for girls in (() if event.source == "user" else (True, False)):
        pool = [u.id for a, u in rest if a.girls_only == girls]
        enough = SMALLEST if event.starts_at - now > PAIR_IS_ENOUGH else 2
        if len(pool) < enough:
            continue
        count = max(1, math.ceil(len(pool) / LARGEST))
        buckets: list[list[int]] = [[] for _ in range(count)]
        for user_id in pool:  # round robin, skipping a bucket with someone this person blocked
            for bucket in sorted(buckets, key=len):
                if len(bucket) < LARGEST and not clash(user_id, bucket):
                    bucket.append(user_id)
                    break
        for bucket in buckets:
            if len(bucket) < enough:
                continue
            group = Group(event_id=event.id, girls_only=girls)
            session.add(group)
            await session.flush()
            for user_id in bucket:
                session.add(GroupMember(group_id=group.id, user_id=user_id))
            members[group.id] = bucket
            created.append(group)

    # 3. A captain for each company that has none: someone experienced who agreed to lead.
    everyone: dict[int, User] = {u.id: u for _, u in waiting}
    async def person(user_id: int) -> Optional[User]:
        if user_id not in everyone:
            everyone[user_id] = await session.get(User, user_id)
        return everyone[user_id]

    ready: dict[int, bool] = {}
    for group in created + [g for g, _ in joined]:
        if group.captain_id:
            continue
        for user_id in members[group.id]:
            user = await person(user_id)
            if user and user.captain_ok:
                if user_id not in ready:
                    ready[user_id] = await progress.captain_ready(session, user)
                if ready[user_id]:
                    group.captain_id = user_id
                    break
    await session.commit()

    for group in created:
        people = [await person(i) for i in members[group.id]]
        captain = await person(group.captain_id) if group.captain_id else None
        for user in people:
            others = [p for p in people if p.id != user.id]
            await notifier.send(user.tg_id, texts.group_ready(others, event, group.id, captain, user.id),
                                f"group-{group.id}", button="Открыть чат компании")
    for group, user in joined:
        people = [await person(i) for i in members[group.id]]
        others = [p for p in people if p.id != user.id]
        captain = await person(group.captain_id) if group.captain_id else None
        await notifier.send(user.tg_id, texts.group_ready(others, event, group.id, captain, user.id),
                            f"group-{group.id}", button="Открыть чат компании")
        for other in others:
            await notifier.send(other.tg_id, texts.group_joined(user, event), f"group-{group.id}",
                                throttle_key=f"gj{group.id}", throttle_seconds=1800, button="Открыть чат")
    return sum(len(members[g.id]) for g in created) + len(joined)


async def assemble_upcoming(session: AsyncSession, now: Optional[datetime] = None) -> int:
    """Background pass: events of the next two days where someone still waits for a company."""
    now = now or utcnow()
    ids = [i for (i,) in await session.execute(
        select(Attendance.event_id).join(Event, Event.id == Attendance.event_id)
        .where(Attendance.wants_group.is_(True), Attendance.status == "looking", Event.published,
               Event.starts_at > now + SOON, Event.starts_at < now + timedelta(days=2)).distinct())]
    done = 0
    for event_id in ids:
        event = await session.get(Event, event_id)
        if event:
            done += await assemble(session, event, now)
    return done


async def group_status(session: AsyncSession, me: User, event: Event) -> dict:
    """For the event page: my company, or that I wait for one, and how many others wait."""
    group = await my_group(session, me.id, event.id) if me else None
    hidden = await blocked_ids(session, me) if me else set()
    info: dict = {"group": None, "waiting": False, "waiting_count": 0}
    if event.source == "user":
        info["gathering"] = await gathering_info(session, event, me)
    if group:
        people = [u for u in await members_of(session, group.id) if u.id != me.id and u.id not in hidden]
        info["group"] = {"id": group.id, "size": len(people) + 1, "others": [user_card(u) for u in people],
                         "captain_id": group.captain_id}
        return info
    placed = select(GroupMember.user_id).join(Group, Group.id == GroupMember.group_id).where(Group.event_id == event.id)
    info["waiting_count"] = await session.scalar(select(func.count()).select_from(Attendance).where(
        Attendance.event_id == event.id, Attendance.wants_group.is_(True), Attendance.status == "looking",
        Attendance.user_id.not_in(placed), Attendance.user_id != (me.id if me else 0))) or 0
    if me:
        mine = await session.get(Attendance, (me.id, event.id))
        info["waiting"] = bool(mine and mine.wants_group and mine.status == "looking")
    return info


async def gathering_info(session: AsyncSession, event: Event, me: Optional[User]) -> dict:
    """«Свой сбор»: who gathers and how many places are left in the company."""
    host = await session.get(User, event.organizer_id) if event.organizer_id else None
    group = (await session.execute(select(Group).where(Group.event_id == event.id)
                                   .order_by(Group.created_at))).scalars().first()
    size = await session.scalar(select(func.count()).select_from(GroupMember)
                                .where(GroupMember.group_id == group.id)) if group else 0
    limit = group_limit(event)
    return {"host": user_card(host) if host else None, "mine": bool(me and host and me.id == host.id),
            "size": size or 0, "limit": limit, "left": max(0, limit - (size or 0))}


async def leave_group(session: AsyncSession, user_id: int, event_id: int) -> None:
    group = await my_group(session, user_id, event_id)
    if group:
        if group.captain_id == user_id:
            group.captain_id = None
        await session.execute(delete(GroupMember).where(GroupMember.group_id == group.id,
                                                        GroupMember.user_id == user_id))


# ---------- API ----------

async def member_group(session: AsyncSession, me: User, group_id: int) -> tuple[Group, Event]:
    group = await session.get(Group, group_id)
    if group is None or await session.get(GroupMember, (group_id, me.id)) is None:
        raise HTTPException(404, "Чат не найден")
    return group, await session.get(Event, group.event_id)


@router.get("/groups")
async def groups_list(me: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Group).join(GroupMember, GroupMember.group_id == Group.id)
                                  .where(GroupMember.user_id == me.id).order_by(Group.created_at.desc())
                                  .limit(50))).scalars().all()
    hidden = await blocked_ids(session, me)
    out = []
    for group in rows:
        event = await session.get(Event, group.event_id)
        people = [u for u in await members_of(session, group.id) if u.id != me.id]
        last = (await session.execute(select(GroupMessage).where(GroupMessage.group_id == group.id,
                                                                 GroupMessage.sender_id.not_in(hidden or {0}))
                                      .order_by(GroupMessage.id.desc()).limit(1))).scalar_one_or_none()
        sender = None
        if last and last.sender_id != me.id:
            sender = next((u.name for u in people if u.id == last.sender_id), None)
        out.append({"id": group.id, "event": event_card(event), "others": [user_card(u) for u in people],
                    "last": last.text if last else "", "last_from": "Вы" if last and last.sender_id == me.id else sender,
                    "at": to_local_iso(last.created_at if last else group.created_at)})
    out.sort(key=lambda c: c["at"], reverse=True)
    return {"groups": out}


@router.get("/groups/{group_id}")
async def group_chat(group_id: int, after: int = 0, me: User = Depends(current_user),
                     session: AsyncSession = Depends(get_session)):
    group, event = await member_group(session, me, group_id)
    hidden = await blocked_ids(session, me)
    people = await members_of(session, group.id)
    names = {u.id: u.name or "Гость" for u in people}
    rows = (await session.execute(select(GroupMessage).where(GroupMessage.group_id == group.id, GroupMessage.id > after)
                                  .order_by(GroupMessage.id).limit(300))).scalars()
    return {"id": group.id, "event": event_card(event), "girls_only": group.girls_only,
            "captain_id": group.captain_id if group.captain_id in names else None,
            "deal": event.group_deal, "promo": event.group_promo, "full": len(people) >= group_limit(event),
            "others": [user_card(u) for u in people if u.id != me.id],
            "icebreaker": texts.icebreaker_plain(event, group.id, group=True),
            "messages": [{"id": m.id, "mine": m.sender_id == me.id, "from": names.get(m.sender_id, "Гость"),
                          "from_id": m.sender_id, "text": m.text, "at": to_local_iso(m.created_at)}
                         for m in rows if m.sender_id not in hidden]}


class GroupMessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


@router.post("/groups/{group_id}/messages")
async def group_send(group_id: int, body: GroupMessageIn, me: User = Depends(current_user),
                     session: AsyncSession = Depends(get_session)):
    group, event = await member_group(session, me, group_id)
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Пустое сообщение")
    require_clean(text)
    message = GroupMessage(group_id=group.id, sender_id=me.id, text=text)
    session.add(message)
    await session.commit()
    hidden = await blocked_ids(session, me)
    for other in await members_of(session, group.id):
        if other.id != me.id and other.id not in hidden:
            await notifier.send(other.tg_id, texts.group_message(me, text, event), f"group-{group.id}",
                                throttle_key=f"g{group.id}", button="Ответить")
    return {"id": message.id, "mine": True, "from": me.name, "from_id": me.id, "text": text,
            "at": to_local_iso(message.created_at)}


@router.post("/groups/{group_id}/leave")
async def group_leave(group_id: int, me: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    group, event = await member_group(session, me, group_id)
    await session.execute(delete(GroupMember).where(GroupMember.group_id == group.id, GroupMember.user_id == me.id))
    if group.captain_id == me.id:
        group.captain_id = None
    mine = await session.get(Attendance, (me.id, event.id))
    if mine:
        mine.wants_group = False
    await session.commit()
    return {"ok": True}
