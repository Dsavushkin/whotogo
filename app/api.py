"""HTTP API used by the Mini App (and later by the iPhone app)."""
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import (check_password, current_user, exchange_code, hash_password, maybe_user, new_token,
                   token_hash)
from .config import settings
from .db import get_session
from .interests import INTERESTS, score, why
from .moderation import is_clean
from .models import Attendance, AuthToken, Block, Event, Like, LoginCode, Match, Message, Report, User, utcnow
from .notify import notifier

router = APIRouter(prefix="/api")
TZ = ZoneInfo(settings.timezone)

CATEGORIES = {
    "music": "Музыка", "party": "Вечеринки", "food": "Еда", "games": "Игры", "art": "Искусство",
    "theater": "Театр", "cinema": "Кино", "talk": "Лекции", "sport": "Спорт", "walk": "Прогулки", "dating": "Знакомства",
    "other": "Другое",
}


# ---------- helpers ----------

def to_local_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(TZ).isoformat(timespec="minutes")


def day_bounds(day: str, now: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """UTC-naive [from, to) for «today», «tomorrow», «weekend» or «week» in the city timezone."""
    local_now = (now or datetime.now(timezone.utc)).astimezone(TZ)
    midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    if day == "tomorrow":
        start, end = midnight + timedelta(days=1), midnight + timedelta(days=2)
    elif day == "weekend":
        days_to_sat = (5 - midnight.weekday()) % 7
        if midnight.weekday() == 6:  # Sunday: the weekend is today
            start, end = local_now - timedelta(hours=2), midnight + timedelta(days=1)
        else:
            sat = midnight + timedelta(days=days_to_sat)
            start, end = (max(sat, local_now - timedelta(hours=2)), sat + timedelta(days=2))
    elif day == "week":
        start, end = local_now - timedelta(hours=2), midnight + timedelta(days=8)
    else:  # today; events that began up to two hours ago still count
        start, end = local_now - timedelta(hours=2), midnight + timedelta(days=1)
    as_utc = lambda d: d.astimezone(timezone.utc).replace(tzinfo=None)
    return as_utc(start), as_utc(end)


def user_card(u: User) -> dict:
    return {"id": u.id, "name": u.name or "Гость", "age": u.age, "bio": u.bio, "interests": u.interests or []}


def event_card(e: Event, going: int = 0, looking: int = 0) -> dict:
    return {
        "id": e.id, "title": e.title, "category": e.category, "category_name": CATEGORIES.get(e.category, "Другое"),
        "starts_at": to_local_iso(e.starts_at), "ends_at": to_local_iso(e.ends_at), "place": e.place,
        "address": e.address, "price": e.price, "image": e.image or "", "going": going, "looking": looking,
        "started": e.starts_at <= utcnow(),
    }


async def counts_for(session: AsyncSession, event_ids: list[int]) -> dict[int, tuple[int, int]]:
    if not event_ids:
        return {}
    rows = await session.execute(
        select(Attendance.event_id, Attendance.status, func.count())
        .where(Attendance.event_id.in_(event_ids)).group_by(Attendance.event_id, Attendance.status))
    out: dict[int, list[int]] = {i: [0, 0] for i in event_ids}
    for event_id, status, n in rows:
        out[event_id][0] += n
        if status == "looking":
            out[event_id][1] += n
    return {k: (v[0], v[1]) for k, v in out.items()}


async def blocked_ids(session: AsyncSession, me: User) -> set[int]:
    rows = await session.execute(
        select(Block.user_id, Block.target_id).where(or_(Block.user_id == me.id, Block.target_id == me.id)))
    return {b if a == me.id else a for a, b in rows}


async def get_event(session: AsyncSession, event_id: int) -> Event:
    event = await session.get(Event, event_id)
    if event is None or not event.published:
        raise HTTPException(404, "Событие не найдено")
    return event


def require_adult(me: User) -> None:
    if not me.adult_ok:
        raise HTTPException(403, "Сначала заполните профиль")


async def make_match(session: AsyncSession, me: User, other_id: int, event: Event, kind: str) -> Optional[Match]:
    """Stores my interest; returns a Match if the other person already showed the same interest."""
    exists = await session.execute(select(Like.id).where(
        Like.from_id == me.id, Like.to_id == other_id, Like.event_id == event.id, Like.kind == kind))
    if exists.first() is None:
        session.add(Like(from_id=me.id, to_id=other_id, event_id=event.id, kind=kind))
    back = await session.execute(select(Like.id).where(
        Like.from_id == other_id, Like.to_id == me.id, Like.event_id == event.id, Like.kind == kind))
    if back.first() is None:
        await session.flush()
        return None
    a, b = sorted((me.id, other_id))
    match = (await session.execute(select(Match).where(
        Match.a_id == a, Match.b_id == b, Match.event_id == event.id))).scalar_one_or_none()
    created = match is None
    if created:
        match = Match(a_id=a, b_id=b, event_id=event.id, kind=kind)
        session.add(match)
    await session.flush()
    if created:
        other = await session.get(User, other_id)
        if other:
            text = (f"Идёте вместе: {me.name} тоже хочет пойти с вами на «{event.title}»." if kind == "together"
                    else f"Это взаимно: {me.name} тоже хочет увидеться ещё после «{event.title}».")
            await notifier.send(other.tg_id, text, f"chat-{match.id}")
    return match


# ---------- sign-in outside Telegram ----------

class CodeIn(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


_attempts: dict = {}  # ip -> recent attempt times; guards the 6-digit code against guessing


@router.post("/auth/code")
async def auth_code(body: CodeIn, request: Request, session: AsyncSession = Depends(get_session)):
    key = _limit(request, "code", 8)
    token = await exchange_code(session, body.code)
    if token is None:
        raise HTTPException(400, "Код не подошёл. Получите новый: команда /login в боте.")
    _attempts.pop(key, None)
    return {"token": token}


class AccountIn(BaseModel):
    email: str = Field(min_length=5, max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=200)


def _limit(request: Request, bucket: str, most: int) -> str:
    ip = request.client.host if request.client else "?"
    key, now = f"{bucket}:{ip}", time.monotonic()
    recent = [t for t in _attempts.get(key, []) if now - t < 600]
    if len(recent) >= most:
        raise HTTPException(429, "Слишком много попыток. Попробуйте через 10 минут.")
    _attempts[key] = recent + [now]
    return key


@router.post("/auth/register")
async def auth_register(body: AccountIn, request: Request, session: AsyncSession = Depends(get_session)):
    _limit(request, "register", 6)
    email = body.email.strip().lower()
    if (await session.execute(select(User.id).where(User.email == email))).first():
        raise HTTPException(400, "Эта почта уже зарегистрирована. Войдите с паролем.")
    user = User(email=email, password_hash=await hash_password(body.password), city=settings.city)
    session.add(user)
    await session.commit()
    return {"token": await new_token(session, user.id)}


@router.post("/auth/login")
async def auth_login(body: AccountIn, request: Request, session: AsyncSession = Depends(get_session)):
    key = _limit(request, "login", 10)
    user = (await session.execute(select(User).where(User.email == body.email.strip().lower()))).scalar_one_or_none()
    if user is None or not await check_password(body.password, user.password_hash):
        raise HTTPException(400, "Почта или пароль не подходят.")
    if user.is_banned:
        raise HTTPException(403, "Аккаунт заблокирован")
    _attempts.pop(key, None)
    return {"token": await new_token(session, user.id)}


@router.post("/auth/logout")
async def auth_logout(authorization: str = Header(default=""), me: User = Depends(current_user),
                      session: AsyncSession = Depends(get_session)):
    if authorization.startswith("Bearer "):
        await session.execute(delete(AuthToken).where(AuthToken.token_hash == token_hash(authorization[7:])))
        await session.commit()
    return {"ok": True}


def require_clean(*texts: str) -> None:
    if not all(is_clean(t) for t in texts):
        raise HTTPException(400, "Уберите грубые слова — такое здесь не публикуется.")


# ---------- profile ----------

class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    age: int = Field(ge=18, le=99)
    bio: str = Field(default="", max_length=300)
    interests: list[str] = Field(default_factory=list, max_length=8)
    adult_ok: bool = False


def me_card(me: User) -> dict:
    return {**user_card(me), "name": me.name, "adult_ok": me.adult_ok, "is_organizer": me.is_organizer,
            "is_admin": settings.is_admin(me), "has_telegram": bool(me.tg_id), "nudges": me.nudges}


@router.get("/me")
async def get_me(me: User = Depends(current_user)):
    return me_card(me)


@router.put("/me")
async def put_me(body: ProfileIn, me: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    if not body.adult_ok:
        raise HTTPException(400, "Нужно подтвердить возраст 18+ и согласие с правилами")
    require_clean(body.name, body.bio, *body.interests)
    me = await session.merge(me)
    me.name, me.age, me.bio = body.name.strip(), body.age, body.bio.strip()
    me.interests = [i.strip() for i in body.interests if i.strip() in INTERESTS][:5]
    me.adult_ok = True
    await session.commit()
    return me_card(me)


class SettingsIn(BaseModel):
    nudges: bool


@router.put("/me/settings")
async def put_settings(body: SettingsIn, me: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    me = await session.merge(me)
    me.nudges = body.nudges
    await session.commit()
    return me_card(me)


@router.delete("/me")
async def delete_me(me: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    """Removes the account and everything tied to it."""
    match_ids = [m for (m,) in await session.execute(
        select(Match.id).where(or_(Match.a_id == me.id, Match.b_id == me.id)))]
    if match_ids:
        await session.execute(delete(Message).where(Message.match_id.in_(match_ids)))
        await session.execute(delete(Match).where(Match.id.in_(match_ids)))
    await session.execute(delete(Like).where(or_(Like.from_id == me.id, Like.to_id == me.id)))
    await session.execute(delete(Attendance).where(Attendance.user_id == me.id))
    await session.execute(delete(Block).where(or_(Block.user_id == me.id, Block.target_id == me.id)))
    await session.execute(delete(Report).where(Report.reporter_id == me.id))
    await session.execute(delete(AuthToken).where(AuthToken.user_id == me.id))
    await session.execute(delete(LoginCode).where(LoginCode.user_id == me.id))
    await session.execute(delete(User).where(User.id == me.id))
    await session.commit()
    return {"ok": True}


# ---------- events ----------

@router.get("/events")
async def list_events(day: str = "today", category: str = "", for_me: bool = False,
                      me: Optional[User] = Depends(maybe_user), session: AsyncSession = Depends(get_session)):
    """Open to guests: the afisha is the public face of the site."""
    start, end = day_bounds(day)
    city = me.city if me else settings.city
    query = select(Event).where(Event.published, Event.city == city, Event.starts_at >= start,
                                Event.starts_at < end)
    if category:
        query = query.where(Event.category == category)
    events = list((await session.execute(query.order_by(Event.starts_at).limit(200))).scalars())
    counts = await counts_for(session, [e.id for e in events])
    mine = (me.interests or []) if me else []
    cards = []
    for e in events:
        card = event_card(e, *counts.get(e.id, (0, 0)))
        text = e.title + " " + e.description
        card["why"] = why(e.category, text, mine)[:2]
        card["_score"] = score(e.category, text, mine)
        cards.append(card)
    if for_me and mine:
        # «Для вас»: only fitting events, the best fit first, then where people already look for company.
        cards = [c for c in cards if c["_score"] > 0]
        cards.sort(key=lambda c: (-c["_score"], -c["looking"], c["starts_at"]))
    else:
        # Events where people already look for company go first, then by time.
        cards.sort(key=lambda c: (-c["looking"], c["starts_at"]))
    for c in cards:
        c.pop("_score")
    return {"events": cards, "categories": CATEGORIES, "interests": INTERESTS}


@router.get("/events/{event_id}")
async def event_detail(event_id: int, me: Optional[User] = Depends(maybe_user),
                       session: AsyncSession = Depends(get_session)):
    event = await get_event(session, event_id)
    counts = await counts_for(session, [event.id])
    mine = await session.get(Attendance, (me.id, event.id)) if me else None
    rows = await session.execute(
        select(User).join(Attendance, Attendance.user_id == User.id)
        .where(Attendance.event_id == event.id, User.id != (me.id if me else 0)).limit(5))
    return {**event_card(event, *counts[event.id]), "description": event.description, "url": event.url,
            "source": event.source, "my_status": mine.status if mine else None,
            "my_note": mine.note if mine else "", "faces": [u.name[:1].upper() or "?" for u in rows.scalars()]}


class AttendIn(BaseModel):
    status: str = Field(pattern="^(going|looking|none)$")
    note: str = Field(default="", max_length=200)


@router.post("/events/{event_id}/attend")
async def attend(event_id: int, body: AttendIn, me: User = Depends(current_user),
                 session: AsyncSession = Depends(get_session)):
    require_adult(me)
    require_clean(body.note)
    event = await get_event(session, event_id)
    mine = await session.get(Attendance, (me.id, event.id))
    if body.status == "none":
        if mine:
            await session.delete(mine)
    elif mine:
        mine.status, mine.note = body.status, body.note.strip()
    else:
        session.add(Attendance(user_id=me.id, event_id=event.id, status=body.status, note=body.note.strip()))
    await session.commit()
    return {"my_status": None if body.status == "none" else body.status}


@router.get("/events/{event_id}/people")
async def people(event_id: int, me: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    """People who look for company at this event."""
    require_adult(me)
    event = await get_event(session, event_id)
    hidden = await blocked_ids(session, me)
    rows = await session.execute(
        select(User, Attendance.note).join(Attendance, Attendance.user_id == User.id)
        .where(Attendance.event_id == event.id, Attendance.status == "looking", User.id != me.id,
               User.is_banned.is_(False)).order_by(Attendance.created_at.desc()).limit(100))
    invited = {to for (to,) in await session.execute(select(Like.to_id).where(
        Like.from_id == me.id, Like.event_id == event.id, Like.kind == "together"))}
    matched: dict[int, int] = {}
    for m in (await session.execute(select(Match).where(
            Match.event_id == event.id, or_(Match.a_id == me.id, Match.b_id == me.id)))).scalars():
        matched[m.b_id if m.a_id == me.id else m.a_id] = m.id
    mine = set(me.interests or [])
    found = [{**user_card(u), "note": note, "invited": u.id in invited, "match_id": matched.get(u.id),
              "common": [i for i in (u.interests or []) if i in mine]}
             for u, note in rows if u.id not in hidden]
    found.sort(key=lambda p: -len(p["common"]))  # stable: newest first among equals
    return {"event": event_card(event), "people": found}


@router.post("/events/{event_id}/invite/{user_id}")
async def invite(event_id: int, user_id: int, me: User = Depends(current_user),
                 session: AsyncSession = Depends(get_session)):
    """«Пойдём вместе». The other person learns about it only if they tap the same."""
    require_adult(me)
    event = await get_event(session, event_id)
    if user_id == me.id or user_id in await blocked_ids(session, me):
        raise HTTPException(400, "Нельзя пригласить этого человека")
    theirs = await session.get(Attendance, (user_id, event.id))
    if theirs is None or theirs.status != "looking":
        raise HTTPException(400, "Этот человек больше не ищет компанию")
    if await session.get(Attendance, (me.id, event.id)) is None:
        session.add(Attendance(user_id=me.id, event_id=event.id, status="looking"))
    match = await make_match(session, me, user_id, event, "together")
    await session.commit()
    other = await session.get(User, user_id)
    return {"match_id": match.id if match else None, "other": user_card(other) if match else None,
            "event": event_card(event)}


@router.get("/people")
async def people_feed(me: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    """Everyone who looks for company at upcoming events of the week."""
    require_adult(me)
    start, end = day_bounds("week")
    hidden = await blocked_ids(session, me)
    rows = (await session.execute(
        select(User, Attendance.note, Event).join(Attendance, Attendance.user_id == User.id)
        .join(Event, Event.id == Attendance.event_id)
        .where(Attendance.status == "looking", User.id != me.id, User.is_banned.is_(False), Event.published,
               Event.city == me.city, Event.starts_at >= start, Event.starts_at < end)
        .order_by(Event.starts_at, Attendance.created_at.desc()).limit(150))).all()
    invited = {(to, ev) for to, ev in await session.execute(select(Like.to_id, Like.event_id).where(
        Like.from_id == me.id, Like.kind == "together"))}
    matched = {}
    for m in (await session.execute(select(Match).where(or_(Match.a_id == me.id, Match.b_id == me.id)))).scalars():
        matched[(m.b_id if m.a_id == me.id else m.a_id, m.event_id)] = m.id
    mine = set(me.interests or [])
    return {"people": [
        {**user_card(u), "note": note, "event": event_card(e), "invited": (u.id, e.id) in invited,
         "match_id": matched.get((u.id, e.id)), "common": [i for i in (u.interests or []) if i in mine]}
        for u, note, e in rows if u.id not in hidden]}


@router.get("/my/events")
async def my_events(me: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    """My upcoming events and recent ones where I can still mark guests."""
    now = utcnow()
    rows = (await session.execute(
        select(Event, Attendance.status).join(Attendance, Attendance.event_id == Event.id)
        .where(Attendance.user_id == me.id, Event.starts_at >= now - timedelta(days=4))
        .order_by(Event.starts_at))).all()
    counts = await counts_for(session, [e.id for e, _ in rows])
    upcoming, past = [], []
    for event, status in rows:
        card = {**event_card(event, *counts.get(event.id, (0, 0))), "my_status": status}
        (past if event.starts_at <= now - timedelta(hours=3) else upcoming).append(card)
    return {"upcoming": upcoming, "past": [c for c in reversed(past) if c["going"] >= 2]}


# ---------- after the event ----------

async def attended_event(session: AsyncSession, me: User, event_id: int) -> Event:
    event = await get_event(session, event_id)
    if event.starts_at > utcnow():
        raise HTTPException(400, "Событие ещё не началось")
    if await session.get(Attendance, (me.id, event.id)) is None:
        raise HTTPException(403, "Вы не отмечались на этом событии")
    return event


@router.get("/events/{event_id}/after")
async def after_list(event_id: int, me: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    event = await attended_event(session, me, event_id)
    hidden = await blocked_ids(session, me)
    guests = (await session.execute(
        select(User).join(Attendance, Attendance.user_id == User.id)
        .where(Attendance.event_id == event.id, User.id != me.id, User.is_banned.is_(False)).limit(300))).scalars()
    marked = {to for (to,) in await session.execute(select(Like.to_id).where(
        Like.from_id == me.id, Like.event_id == event.id, Like.kind == "again"))}
    return {"event": event_card(event),
            "guests": [{**user_card(u), "marked": u.id in marked} for u in guests if u.id not in hidden]}


class AfterIn(BaseModel):
    user_ids: list[int] = Field(max_length=300)


@router.post("/events/{event_id}/after")
async def after_mark(event_id: int, body: AfterIn, me: User = Depends(current_user),
                     session: AsyncSession = Depends(get_session)):
    event = await attended_event(session, me, event_id)
    hidden = await blocked_ids(session, me)
    guest_ids = {u for (u,) in await session.execute(
        select(Attendance.user_id).where(Attendance.event_id == event.id))}
    wanted = {u for u in body.user_ids if u in guest_ids and u != me.id and u not in hidden}
    # Marks that were taken back are removed; existing chats stay.
    await session.execute(delete(Like).where(
        Like.from_id == me.id, Like.event_id == event.id, Like.kind == "again", Like.to_id.notin_(wanted or {0})))
    matches = []
    for other_id in wanted:
        match = await make_match(session, me, other_id, event, "again")
        if match:
            matches.append(match.id)
    await session.commit()
    return {"marked": len(wanted), "matches": matches}


# ---------- chats ----------

async def my_match(session: AsyncSession, me: User, match_id: int) -> tuple[Match, User, Event]:
    match = await session.get(Match, match_id)
    if match is None or me.id not in (match.a_id, match.b_id):
        raise HTTPException(404, "Чат не найден")
    other = await session.get(User, match.b_id if match.a_id == me.id else match.a_id)
    event = await session.get(Event, match.event_id)
    return match, other, event


@router.get("/matches")
async def matches(me: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    hidden = await blocked_ids(session, me)
    rows = (await session.execute(select(Match).where(or_(Match.a_id == me.id, Match.b_id == me.id))
                                  .order_by(Match.created_at.desc()).limit(200))).scalars().all()
    out = []
    for m in rows:
        other_id = m.b_id if m.a_id == me.id else m.a_id
        if other_id in hidden:
            continue
        other, event = await session.get(User, other_id), await session.get(Event, m.event_id)
        last = (await session.execute(select(Message).where(Message.match_id == m.id)
                                      .order_by(Message.id.desc()).limit(1))).scalar_one_or_none()
        out.append({"id": m.id, "kind": m.kind, "other": user_card(other), "event": event_card(event),
                    "last": last.text if last else "", "last_mine": bool(last and last.sender_id == me.id),
                    "at": to_local_iso(last.created_at if last else m.created_at)})
    out.sort(key=lambda c: c["at"], reverse=True)
    return {"matches": out}


@router.get("/matches/{match_id}")
async def chat(match_id: int, after: int = 0, me: User = Depends(current_user),
               session: AsyncSession = Depends(get_session)):
    match, other, event = await my_match(session, me, match_id)
    rows = (await session.execute(select(Message).where(Message.match_id == match.id, Message.id > after)
                                  .order_by(Message.id).limit(300))).scalars()
    return {"id": match.id, "kind": match.kind, "other": user_card(other), "event": event_card(event),
            "messages": [{"id": m.id, "mine": m.sender_id == me.id, "text": m.text,
                          "at": to_local_iso(m.created_at)} for m in rows]}


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


@router.post("/matches/{match_id}/messages")
async def send_message(match_id: int, body: MessageIn, me: User = Depends(current_user),
                       session: AsyncSession = Depends(get_session)):
    match, other, _ = await my_match(session, me, match_id)
    if other.id in await blocked_ids(session, me):
        raise HTTPException(403, "Переписка закрыта")
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Пустое сообщение")
    require_clean(text)
    message = Message(match_id=match.id, sender_id=me.id, text=text)
    session.add(message)
    await session.commit()
    await notifier.send(other.tg_id, f"{me.name}: {text[:120]}", f"chat-{match.id}", throttle_key=f"m{match.id}")
    return {"id": message.id, "mine": True, "text": text, "at": to_local_iso(message.created_at)}


# ---------- safety ----------

class ReportIn(BaseModel):
    reason: str = Field(default="", max_length=500)
    block: bool = True


@router.post("/users/{user_id}/report")
async def report(user_id: int, body: ReportIn, me: User = Depends(current_user),
                 session: AsyncSession = Depends(get_session)):
    target = await session.get(User, user_id)
    if target is None or target.id == me.id:
        raise HTTPException(404, "Пользователь не найден")
    if body.reason.strip():
        session.add(Report(reporter_id=me.id, target_id=target.id, reason=body.reason.strip()))
        for admin in settings.admin_ids:
            await notifier.send(admin, f"Жалоба на {target.name} (id {target.id}, tg {target.tg_id}) "
                                       f"от {me.name} (id {me.id}): {body.reason.strip()[:300]}")
    if body.block and await session.get(Block, (me.id, target.id)) is None:
        session.add(Block(user_id=me.id, target_id=target.id))
    await session.commit()
    return {"ok": True}


# ---------- organizer ----------

class EventIn(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(default="", max_length=2000)
    category: str = "other"
    starts_at: datetime  # local time of the city, e.g. 2026-12-05T20:00
    place: str = Field(min_length=2, max_length=120)
    address: str = Field(default="", max_length=200)
    price: str = Field(default="", max_length=60)
    url: str = Field(default="", max_length=300)
    capacity: Optional[int] = Field(default=None, ge=1, le=100000)


def require_organizer(me: User) -> None:
    if not (me.is_organizer or settings.is_admin(me)):
        raise HTTPException(403, "Доступ только для организаторов")


async def my_event(session: AsyncSession, me: User, event_id: int) -> Event:
    require_organizer(me)
    event = await session.get(Event, event_id)
    if event is None or (event.organizer_id != me.id and not settings.is_admin(me)):
        raise HTTPException(404, "Событие не найдено")
    return event


@router.post("/org/events")
async def org_create(body: EventIn, me: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    require_organizer(me)
    require_clean(body.title, body.description, body.place)
    local = body.starts_at if body.starts_at.tzinfo else body.starts_at.replace(tzinfo=TZ)
    starts = local.astimezone(timezone.utc).replace(tzinfo=None)
    if starts < utcnow() - timedelta(hours=1):
        raise HTTPException(400, "Дата события уже прошла")
    if body.url and not body.url.startswith(("https://", "http://")):
        raise HTTPException(400, "Ссылка должна начинаться с https://")
    event = Event(source="org", title=body.title.strip(), description=body.description.strip(),
                  category=body.category if body.category in CATEGORIES else "other", starts_at=starts,
                  place=body.place.strip(), address=body.address.strip(), price=body.price.strip(),
                  url=body.url.strip(), capacity=body.capacity, organizer_id=me.id, city=me.city)
    session.add(event)
    await session.commit()
    return event_card(event)


@router.get("/org/events")
async def org_list(me: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    require_organizer(me)
    events = list((await session.execute(select(Event).where(Event.organizer_id == me.id)
                                         .order_by(Event.starts_at.desc()).limit(100))).scalars())
    counts = await counts_for(session, [e.id for e in events])
    return {"events": [event_card(e, *counts.get(e.id, (0, 0))) for e in events]}


@router.get("/org/events/{event_id}")
async def org_stats(event_id: int, me: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    event = await my_event(session, me, event_id)
    rows = (await session.execute(
        select(User, Attendance).join(Attendance, Attendance.user_id == User.id)
        .where(Attendance.event_id == event.id).order_by(Attendance.created_at))).all()
    pairs = (await session.execute(select(func.count()).select_from(Match).where(Match.event_id == event.id))).scalar()
    return {"event": {**event_card(event), "capacity": event.capacity},
            "going": len(rows), "looking": sum(1 for _, a in rows if a.status == "looking"),
            "checked_in": sum(1 for _, a in rows if a.checked_in),
            "pairs": pairs or 0,  # a number only: who matched with whom stays private
            "guests": [{"id": u.id, "name": u.name, "checked_in": a.checked_in} for u, a in rows]}


@router.post("/org/events/{event_id}/checkin/{user_id}")
async def org_checkin(event_id: int, user_id: int, me: User = Depends(current_user),
                      session: AsyncSession = Depends(get_session)):
    event = await my_event(session, me, event_id)
    guest = await session.get(Attendance, (user_id, event.id))
    if guest is None:
        raise HTTPException(404, "Гость не найден")
    guest.checked_in = not guest.checked_in
    await session.commit()
    return {"checked_in": guest.checked_in}
