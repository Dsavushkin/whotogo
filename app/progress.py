"""What a person has done in the service: events, companies, friends. Drives achievements and captains."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import texts
from .models import Achievement, Attendance, Event, Friend, Group, GroupMember, Match, Report, User, utcnow
from .notify import notifier

# An event counts as visited three hours after its start.
VISITED_AFTER = timedelta(hours=3)
CAPTAIN_AFTER = 3  # visited events before one can lead companies


@dataclass(frozen=True)
class Kind:
    code: str
    emoji: str
    name: str  # what is counted, for the progress line
    levels: tuple[int, ...]
    titles: tuple[str, ...]
    hint: str  # how to get it


KINDS = [
    Kind("events", "🎟", "событий", (1, 5, 15, 30), ("Первый выход", "Завсегдатай", "Светский лев", "Легенда Москвы"),
         "Сходите на событие, отмеченное в «Кто идёт»"),
    Kind("companies", "👥", "компаний", (1, 3, 10), ("Своя компания", "Душа компании", "Собиратель"),
         "Сходите на событие с компанией, которую мы собрали"),
    Kind("captain", "⭐", "компаний под вашим началом", (1, 5), ("Капитан", "Адмирал"),
         "Станьте капитаном компании — после трёх событий это можно включить в профиле"),
    Kind("explorer", "🧭", "разных жанров", (3, 6, 9), ("Любопытный", "Исследователь", "Всё попробовал"),
         "Ходите на разное: концерты, театр, квизы, лекции"),
    Kind("friends", "🤝", "друзей", (1, 5, 15), ("Привёл друга", "Свой круг", "Центр притяжения"),
         "Позовите друзей по своей ссылке"),
    Kind("again", "✨", "взаимных «увидимся ещё»", (1, 5), ("Новое знакомство", "Обаяние"),
         "После события отметьте, с кем хотите увидеться ещё"),
    Kind("night", "🌙", "вечеринок", (3,), ("Ночная жизнь",), "Сходите на три вечеринки"),
    Kind("culture", "🎭", "спектаклей, выставок и лекций", (5,), ("Культурная программа",),
         "Театр, выставки и лекции — пять раз"),
]
BY_CODE = {k.code: k for k in KINDS}


async def counts(session: AsyncSession, user_id: int, now: Optional[datetime] = None) -> dict[str, int]:
    now = now or utcnow()
    visited = (select(Event.id, Event.category).join(Attendance, Attendance.event_id == Event.id)
               .where(Attendance.user_id == user_id, Event.starts_at <= now - VISITED_AFTER))
    rows = (await session.execute(visited)).all()
    categories = [c for _, c in rows]
    past_groups = (select(Group.id, Group.captain_id).join(GroupMember, GroupMember.group_id == Group.id)
                   .join(Event, Event.id == Group.event_id)
                   .where(GroupMember.user_id == user_id, Event.starts_at <= now - VISITED_AFTER))
    groups = (await session.execute(past_groups)).all()
    friends = await session.scalar(select(func.count()).select_from(Friend).where(Friend.user_id == user_id))
    again = await session.scalar(select(func.count()).select_from(Match).where(
        Match.kind == "again", or_(Match.a_id == user_id, Match.b_id == user_id)))
    return {
        "events": len(rows),
        "companies": len(groups),
        "captain": sum(1 for _, captain in groups if captain == user_id),
        "explorer": len({c for c in categories if c and c != "other"}),
        "friends": friends or 0,
        "again": again or 0,
        "night": categories.count("party"),
        "culture": sum(1 for c in categories if c in ("theater", "art", "talk")),
    }


async def captain_ready(session: AsyncSession, user: User) -> bool:
    """Leads companies only someone who has been to a few events and has no complaints."""
    if user.is_banned:
        return False
    complaints = await session.scalar(select(func.count()).select_from(Report).where(Report.target_id == user.id))
    return not complaints and (await counts(session, user.id))["events"] >= CAPTAIN_AFTER


def level_of(kind: Kind, value: int) -> int:
    return sum(1 for need in kind.levels if value >= need)


def board(values: dict[str, int]) -> list[dict]:
    """All achievements with the reached level and the way to the next one."""
    out = []
    for kind in KINDS:
        value, level = values.get(kind.code, 0), level_of(kind, values.get(kind.code, 0))
        nxt = kind.levels[level] if level < len(kind.levels) else None
        out.append({
            "code": kind.code, "emoji": kind.emoji, "level": level, "levels": len(kind.levels),
            "title": kind.titles[level - 1] if level else kind.titles[0], "value": value, "next": nxt,
            "next_title": kind.titles[level] if nxt else None, "unit": kind.name, "hint": kind.hint,
            "steps": [{"need": need, "title": title, "done": value >= need} for need, title in zip(kind.levels, kind.titles)],
        })
    return out


async def award(session: AsyncSession, user: User, notify: bool = True) -> list[str]:
    """Stores newly reached levels and tells the person about the best new one. Returns new codes."""
    values = await counts(session, user.id)
    have = {c for (c,) in await session.execute(select(Achievement.code).where(Achievement.user_id == user.id))}
    fresh = []
    for kind in KINDS:
        for level in range(1, level_of(kind, values[kind.code]) + 1):
            code = f"{kind.code}:{level}"
            if code not in have:
                session.add(Achievement(user_id=user.id, code=code))
                fresh.append(code)
    if not fresh:
        return []
    await session.commit()
    if notify:
        # Several at once (the first run) → one message about the highest of them.
        kind_code, level = max(fresh, key=lambda c: (int(c.split(":")[1]), c)).split(":")
        kind = BY_CODE[kind_code]
        await notifier.send(user.tg_id, texts.achievement(kind, int(level), values[kind_code], len(fresh)),
                            "achievements", button="Мои достижения")
    return fresh


async def award_recent(session: AsyncSession, now: Optional[datetime] = None) -> int:
    """Background pass: people whose events ended recently or who got friends today."""
    now = now or utcnow()
    ids = {i for (i,) in await session.execute(
        select(Attendance.user_id).join(Event, Event.id == Attendance.event_id)
        .where(Event.starts_at <= now - VISITED_AFTER, Event.starts_at > now - VISITED_AFTER - timedelta(days=2)))}
    ids |= {i for (i,) in await session.execute(select(Friend.user_id).where(Friend.created_at > now - timedelta(days=1)))}
    done = 0
    for user_id in ids:
        user = await session.get(User, user_id)
        if user and not user.is_banned:
            done += len(await award(session, user))
    return done
