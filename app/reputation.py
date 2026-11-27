"""Reliability and public profiles.

The fear of going with strangers is that they will not show up. So for every past event where a person
committed to others (was in a company or agreed «Пойдём вместе»), we find out whether they came:
they pressed «Я на месте» at the venue, the organizer checked them in, or someone they went with says so.
The profile shows «Пришёл 5 из 5». Events nobody reported on do not count either way.
"""
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import progress
from .api import CATEGORIES, blocked_ids, current_user, event_card, get_event, to_local_iso, user_card
from .db import get_session
from .models import (Achievement, Attendance, Event, Friend, Group, GroupMember, Match, PresenceVote, User,
                     utcnow)

router = APIRouter(prefix="/api")

CHECKIN_BEFORE = timedelta(hours=1)   # «Я на месте» opens an hour before the start…
CHECKIN_AFTER = timedelta(hours=4)    # …and closes four hours after it
VOTE_DAYS = 7                         # «Кто пришёл?» can be answered for a week
RELIABLE_FROM = 3                     # «Надёжный» badge: at least this many confirmed visits, no misses
HISTORY_LIMIT = 12


async def companions(session: AsyncSession, user_id: int, event_ids: Optional[list] = None) -> dict:
    """{event_id: {other user ids}} — people the user committed to go with: company members and
    mutual «Пойдём вместе» matches."""
    out: dict = {}
    mine = select(GroupMember.group_id).where(GroupMember.user_id == user_id)
    groups = (select(Group.event_id, GroupMember.user_id).join(GroupMember, GroupMember.group_id == Group.id)
              .where(Group.id.in_(mine), GroupMember.user_id != user_id))
    pairs = select(Match.event_id, Match.a_id, Match.b_id).where(
        Match.kind == "together", or_(Match.a_id == user_id, Match.b_id == user_id))
    if event_ids is not None:
        groups = groups.where(Group.event_id.in_(event_ids or [0]))
        pairs = pairs.where(Match.event_id.in_(event_ids or [0]))
    for event_id, other in await session.execute(groups):
        out.setdefault(event_id, set()).add(other)
    for event_id, a, b in await session.execute(pairs):
        out.setdefault(event_id, set()).add(b if a == user_id else a)
    return out


async def reliability(session: AsyncSession, user_ids: list) -> dict:
    """{user_id: {"came": n, "missed": n}} over past committed events."""
    ids = list(dict.fromkeys(user_ids))
    result = {u: {"came": 0, "missed": 0} for u in ids}
    if not ids:
        return result
    past = utcnow() - progress.VISITED_AFTER
    rows = (await session.execute(
        select(Attendance.user_id, Attendance.event_id, Attendance.checked_in)
        .join(Event, Event.id == Attendance.event_id)
        .where(Attendance.user_id.in_(ids), Event.starts_at <= past))).all()
    votes: dict = {}
    for target, event_id, came in await session.execute(
            select(PresenceVote.target_id, PresenceVote.event_id, PresenceVote.came)
            .where(PresenceVote.target_id.in_(ids))):
        votes.setdefault((target, event_id), []).append(came)
    doubtful: dict = {}  # nobody confirmed, someone said «не пришёл»: count only if that person went with them
    for user_id, event_id, checked_in in rows:
        said = votes.get((user_id, event_id), [])
        if checked_in or any(said):
            result[user_id]["came"] += 1
        elif said:
            doubtful.setdefault(user_id, []).append(event_id)
    for user_id, events in doubtful.items():
        committed = await companions(session, user_id, events)
        result[user_id]["missed"] += sum(1 for e in events if e in committed)
    return result


def reliability_card(stats: dict, gender: str = "") -> dict:
    came, missed = stats["came"], stats["missed"]
    verb = "Пришла" if gender == "f" else "Пришёл"
    total = came + missed
    if not total:
        return {"came": 0, "total": 0, "label": "Пока без отметок", "reliable": False}
    return {"came": came, "total": total, "label": f"{verb} {came} из {total}",
            "reliable": came >= RELIABLE_FROM and not missed}


# ---------- «Я на месте» ----------

@router.post("/events/{event_id}/checkin")
async def checkin(event_id: int, me: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    event = await get_event(session, event_id)
    mark = await session.get(Attendance, (me.id, event.id))
    if mark is None:
        raise HTTPException(403, "Сначала отметьте, что идёте на событие")
    now = utcnow()
    if not event.starts_at - CHECKIN_BEFORE <= now <= event.starts_at + CHECKIN_AFTER:
        raise HTTPException(400, "Отметиться можно за час до начала и до конца вечера")
    mark.checked_in = True
    await session.commit()
    return {"checked_in": True}


def checkin_state(event: Event, mark: Optional[Attendance]) -> dict:
    now = utcnow()
    return {"checked_in": bool(mark and mark.checked_in),
            "checkin_open": bool(mark) and event.starts_at - CHECKIN_BEFORE <= now <= event.starts_at + CHECKIN_AFTER}


# ---------- «Кто пришёл?» ----------

async def vote_window(session: AsyncSession, me: User, event_id: int) -> tuple[Event, set]:
    event = await get_event(session, event_id)
    if not event.starts_at <= utcnow() <= event.starts_at + timedelta(days=VOTE_DAYS):
        raise HTTPException(400, "Отметить, кто пришёл, можно в течение недели после события")
    others = (await companions(session, me.id, [event.id])).get(event.id, set())
    others -= await blocked_ids(session, me)
    return event, others


@router.get("/events/{event_id}/presence")
async def presence_list(event_id: int, me: User = Depends(current_user),
                        session: AsyncSession = Depends(get_session)):
    event = await get_event(session, event_id)
    if not event.starts_at <= utcnow() <= event.starts_at + timedelta(days=VOTE_DAYS):
        return {"people": []}
    _, others = await vote_window(session, me, event_id)
    users = (await session.execute(select(User).where(User.id.in_(others or {0}), User.is_banned.is_(False)))).scalars()
    said = {t: c for t, c in await session.execute(select(PresenceVote.target_id, PresenceVote.came).where(
        PresenceVote.voter_id == me.id, PresenceVote.event_id == event.id))}
    return {"people": [{**user_card(u), "came": said.get(u.id)} for u in users]}


class PresenceIn(BaseModel):
    votes: dict[int, Optional[bool]] = Field(max_length=50)  # user id -> came / didn't / take back (None)


@router.post("/events/{event_id}/presence")
async def presence_mark(event_id: int, body: PresenceIn, me: User = Depends(current_user),
                        session: AsyncSession = Depends(get_session)):
    event, others = await vote_window(session, me, event_id)
    saved = 0
    for target, came in body.votes.items():
        if target not in others:
            continue
        await session.execute(delete(PresenceVote).where(
            PresenceVote.voter_id == me.id, PresenceVote.target_id == target, PresenceVote.event_id == event.id))
        if came is not None:
            session.add(PresenceVote(voter_id=me.id, target_id=target, event_id=event.id, came=came))
            saved += 1
    await session.commit()
    return {"saved": saved}


# ---------- public profile ----------

@router.get("/users/{user_id}")
async def profile(user_id: int, me: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    user = await session.get(User, user_id)
    if user is None or user.is_banned or not user.adult_ok or user_id in await blocked_ids(session, me):
        raise HTTPException(404, "Профиль не найден")
    values = await progress.counts(session, user.id)
    earned = {code for (code,) in await session.execute(
        select(Achievement.code).where(Achievement.user_id == user.id))}
    board = [a for a in progress.board(values) if a["level"] and a["code"] in earned] or \
        [a for a in progress.board(values) if a["level"]]
    history = []
    if user.show_history or user.id == me.id:
        rows = (await session.execute(
            select(Event).join(Attendance, Attendance.event_id == Event.id)
            .where(Attendance.user_id == user.id, Event.published,
                   Event.starts_at <= utcnow() - progress.VISITED_AFTER)
            .order_by(Event.starts_at.desc()).limit(HISTORY_LIMIT))).scalars()
        history = [{"id": e.id, "title": e.title, "starts_at": to_local_iso(e.starts_at),
                    "category": e.category, "category_name": CATEGORIES.get(e.category, "Другое")} for e in rows]
    together = await session.scalar(
        select(Attendance.event_id).where(Attendance.user_id == me.id, Attendance.event_id.in_(
            select(Attendance.event_id).where(Attendance.user_id == user.id))).limit(1)) if user.id != me.id else None
    is_friend = bool(await session.get(Friend, (me.id, user.id)))
    return {
        **user_card(user), "me": user.id == me.id, "since": to_local_iso(user.created_at),
        "reliability": reliability_card((await reliability(session, [user.id]))[user.id], user.gender),
        "stats": {"events": values["events"], "companies": values["companies"], "genres": values["explorer"]},
        "captain": user.captain_ok, "friend": is_friend, "met": bool(together),
        "achievements": board, "history": history, "history_hidden": not user.show_history,
    }
