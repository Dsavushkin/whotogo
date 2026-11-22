"""Friends (through the personal invite link), achievements and the story picture for an achievement."""
import io
import secrets
from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import progress, texts
from .api import SOON, blocked_ids, day_bounds, event_card, user_card
from .auth import current_user
from .cards import ASSETS, BLUE, INK, LIME, SKY, WHITE, fit, font
from .config import settings
from .db import get_session
from .groups import LARGEST, fits, members_of, my_group
from .models import Attendance, Event, Friend, Group, GroupMember, User, utcnow
from .notify import notifier

router = APIRouter(prefix="/api")
pictures = APIRouter(include_in_schema=False)


async def invite_code(session: AsyncSession, me: User) -> str:
    if not me.invite_code:
        while True:
            code = secrets.token_hex(4)
            if (await session.execute(select(User.id).where(User.invite_code == code))).first() is None:
                break
        me = await session.merge(me)
        me.invite_code = code
        await session.commit()
    return me.invite_code


def invite_links(code: str, group_id: Optional[int] = None) -> dict:
    tail = f"_g{group_id}" if group_id else ""
    web = f"{settings.webapp_url}/?fr={code}" + (f"&g={group_id}" if group_id else "")
    return {"link": f"https://t.me/{settings.bot_username}?startapp=fr_{code}{tail}", "web_link": web}


async def friend_ids(session: AsyncSession, user_id: int) -> set[int]:
    return {i for (i,) in await session.execute(select(Friend.friend_id).where(Friend.user_id == user_id))}


async def friends_at(session: AsyncSession, me: Optional[User], event_ids: list[int]) -> dict[int, list[User]]:
    """Which of my friends marked each of these events."""
    if not me or not event_ids:
        return {}
    ids = await friend_ids(session, me.id)
    if not ids:
        return {}
    out: dict[int, list[User]] = {}
    for event_id, user in await session.execute(
            select(Attendance.event_id, User).join(User, User.id == Attendance.user_id)
            .where(Attendance.event_id.in_(event_ids), Attendance.user_id.in_(ids), User.is_banned.is_(False))):
        out.setdefault(event_id, []).append(user)
    return out


# ---------- friends ----------

@router.get("/friends")
async def friends(me: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    code = await invite_code(session, me)
    ids = await friend_ids(session, me.id)
    people = list((await session.execute(select(User).where(User.id.in_(ids or {0}), User.is_banned.is_(False))
                                          .order_by(User.name))).scalars())
    start, end = day_bounds("week")
    going = (await session.execute(
        select(User, Event).join(Attendance, Attendance.user_id == User.id).join(Event, Event.id == Attendance.event_id)
        .where(Attendance.user_id.in_(ids or {0}), Event.published, Event.starts_at >= start, Event.starts_at < end,
               User.is_banned.is_(False)).order_by(Event.starts_at).limit(60))).all()
    return {**invite_links(code), "friends": [user_card(u) for u in people],
            "going": [{"friend": user_card(u), "event": event_card(e)} for u, e in going]}


class AcceptIn(BaseModel):
    code: str = Field(min_length=4, max_length=16)
    group: Optional[int] = None


@router.post("/friends/accept")
async def accept(body: AcceptIn, me: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    """Opened a friend's invite link: become friends, and join their company if the link was for one."""
    inviter = (await session.execute(select(User).where(User.invite_code == body.code))).scalar_one_or_none()
    if inviter is None or inviter.is_banned:
        raise HTTPException(404, "Приглашение не найдено")
    if inviter.id == me.id:
        return {"friend": None, "group_id": None, "new": False}
    if inviter.id in await blocked_ids(session, me):
        return {"friend": None, "group_id": None, "new": False}
    new = await session.get(Friend, (me.id, inviter.id)) is None
    if new:
        session.add_all([Friend(user_id=me.id, friend_id=inviter.id), Friend(user_id=inviter.id, friend_id=me.id)])
        await session.commit()
        await notifier.send(inviter.tg_id, texts.new_friend(me), "friends", button="Друзья")
        await progress.award(session, inviter)
        await progress.award(session, me)
    group_id = await join_friends_group(session, me, inviter, body.group) if body.group else None
    return {"friend": user_card(inviter), "group_id": group_id, "new": new}


async def join_friends_group(session: AsyncSession, me: User, inviter: User, group_id: int) -> Optional[int]:
    group = await session.get(Group, group_id)
    if group is None or await session.get(GroupMember, (group.id, inviter.id)) is None or not me.adult_ok:
        return None
    if await session.get(GroupMember, (group.id, me.id)):
        return group.id
    event = await session.get(Event, group.event_id)
    if event is None or event.starts_at <= utcnow() + SOON or await my_group(session, me.id, event.id):
        return None
    people = await members_of(session, group.id)
    hidden = await blocked_ids(session, me)
    if len(people) >= LARGEST or any(p.id in hidden for p in people) or not fits(me, False, group.girls_only):
        return None
    mine = await session.get(Attendance, (me.id, event.id))
    if mine:
        mine.status, mine.wants_group = "looking", True
    else:
        session.add(Attendance(user_id=me.id, event_id=event.id, status="looking", wants_group=True))
    session.add(GroupMember(group_id=group.id, user_id=me.id))
    await session.commit()
    for other in people:
        await notifier.send(other.tg_id, texts.group_joined(me, event), f"group-{group.id}",
                            throttle_key=f"gj{group.id}", throttle_seconds=1800, button="Открыть чат")
    return group.id


@router.get("/groups/{group_id}/invite")
async def group_invite(group_id: int, me: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    """Link that brings a friend straight into my company."""
    if await session.get(GroupMember, (group_id, me.id)) is None:
        raise HTTPException(404, "Чат не найден")
    return invite_links(await invite_code(session, me), group_id)


@router.delete("/friends/{user_id}")
async def unfriend(user_id: int, me: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    await session.execute(delete(Friend).where(
        ((Friend.user_id == me.id) & (Friend.friend_id == user_id)) | ((Friend.user_id == user_id) & (Friend.friend_id == me.id))))
    await session.commit()
    return {"ok": True}


# ---------- achievements ----------

@router.get("/me/progress")
async def my_progress(me: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    values = await progress.counts(session, me.id)
    await progress.award(session, me, notify=False)  # quietly catch up, the screen shows them anyway
    return {"achievements": progress.board(values),
            "captain": {"ready": await progress.captain_ready(session, me), "on": me.captain_ok,
                        "events": values["events"], "need": progress.CAPTAIN_AFTER},
            "invite": invite_links(await invite_code(session, me))}


# ---------- story picture ----------

STORY_W, STORY_H = 1080, 1920
COLORS = {"events": BLUE, "companies": "#FF6A2B", "captain": "#FFB800", "explorer": "#16A37F", "friends": "#E0457B",
          "again": "#8A5CFF", "night": "#1C1C24", "culture": "#B8336A"}


@lru_cache(maxsize=64)
def story_picture(code: str, level: int) -> bytes:
    kind = progress.BY_CODE[code]
    accent = COLORS.get(code, BLUE)
    img = Image.new("RGB", (STORY_W, STORY_H), accent)
    draw = ImageDraw.Draw(img)
    # Medal: rings and the level's stars.
    cx, cy, r = STORY_W // 2, 760, 300
    draw.ellipse((cx - r - 40, cy - r - 40, cx + r + 40, cy + r + 40), fill=LIME)
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=INK)
    big = font("Unbounded_800ExtraBold.ttf", 230)
    need = str(kind.levels[level - 1])
    draw.text((cx, cy - 30), need, font=big, fill=WHITE, anchor="mm")
    unit = font("Manrope_800ExtraBold.ttf", 44)
    for i, line in enumerate(fit(draw, kind.name, unit, 2 * r - 120, 2)):
        draw.text((cx, cy + 130 + i * 52), line, font=unit, fill=SKY, anchor="mm")
    stars = len(kind.levels)
    for i in range(stars):
        x = cx + (i - (stars - 1) / 2) * 90
        star(draw, x, cy + r + 120, 34, LIME if i < level else INK)
    # Text.
    kicker = font("Manrope_800ExtraBold.ttf", 52)
    draw.text((cx, 250), "НОВОЕ ДОСТИЖЕНИЕ", font=kicker, fill=WHITE, anchor="mm")
    title = font("Unbounded_800ExtraBold.ttf", 96)
    lines = fit(draw, kind.titles[level - 1], title, STORY_W - 140, 2)
    y = 1330
    for line in lines:
        draw.text((cx, y), line, font=title, fill=WHITE, anchor="mm")
        y += 118
    hint = font("Manrope_700Bold.ttf", 46)
    for line in fit(draw, "Хожу на события в Москве с новыми людьми", hint, STORY_W - 200, 2):
        draw.text((cx, y + 20), line, font=hint, fill=WHITE, anchor="mm")
        y += 58
    # Footer.
    try:
        logo = Image.open(ASSETS / "logo.png").convert("RGBA")
        logo.thumbnail((120, 120))
        img.paste(logo, (cx - 300, STORY_H - 230), logo)
    except Exception:
        pass
    foot = font("Unbounded_800ExtraBold.ttf", 54)
    draw.text((cx - 160, STORY_H - 205), "Кто идёт", font=foot, fill=WHITE)
    draw.text((cx - 160, STORY_H - 135), "kompaniyana.ru", font=font("Manrope_800ExtraBold.ttf", 40), fill=LIME)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=90)
    return out.getvalue()


def star(draw: ImageDraw.ImageDraw, x: float, y: float, r: float, color) -> None:
    import math
    points = []
    for i in range(10):
        angle = math.pi / 2 + i * math.pi / 5
        radius = r if i % 2 == 0 else r * 0.45
        points.append((x + radius * math.cos(angle), y - radius * math.sin(angle)))
    draw.polygon(points, fill=color)


@pictures.get("/ach/{code}-{level}.jpg")
async def achievement_picture(code: str, level: int):
    kind = progress.BY_CODE.get(code)
    if kind is None or not 1 <= level <= len(kind.levels):
        raise HTTPException(404)
    return Response(story_picture(code, level), media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"})
