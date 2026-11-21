"""Events from the official Timepad API (https://dev.timepad.ru). Needs a free personal token."""
import asyncio
import html
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

API = "https://api.timepad.ru/v1/events"
NAME = "timepad"

# Our category <- words met in Timepad category names or event titles.
CATEGORY_WORDS = [
    ("dating", ("знакомств", "свидани", "speed dating", "быстрые свидания")),
    ("games", ("игр", "квиз", "квест", "мафи", "настол")),
    ("party", ("вечеринк", "party", "тусовк", "дискотек", "рейв")),
    ("music", ("концерт", "музык", "джаз", "dj", "винил")),
    ("food", ("еда", "гастро", "ужин", "дегустац", "кулинар", "вино", "бранч")),
    ("theater", ("театр", "спектакл", "стендап", "stand up", "импров")),
    ("cinema", ("кино", "фильм")),
    ("sport", ("спорт", "бег", "йог", "танц", "фитнес")),
    ("walk", ("экскурс", "прогулк", "путешеств")),
    ("art", ("искусств", "выставк", "культур", "хобби", "творч", "мастер-класс", "рисован", "керамик")),
    ("talk", ("лекци", "наука", "психолог", "язык", "образован", "встреча", "разговорн", "книг")),
]
# Not for «компания на вечер».
SKIP_WORDS = ("для детей", "детск", "бизнес", "ит и интернет", "вебинар", "онлайн", "конференц", "форум",
              "курс ", "тренинг", "образование за рубежом", "хакатон", "без гида", "гражданск", "выставк")


def clean(text: Optional[str]) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def pick_category(names: list, title: str) -> str:
    hay = " ".join(names + [title]).lower()
    for slug, words in CATEGORY_WORDS:
        if any(w in hay for w in words):
            return slug
    return "other"


def price_text(reg: Optional[dict]) -> str:
    reg = reg or {}
    low, high = reg.get("price_min"), reg.get("price_max")
    if low is None and high is None:
        return ""
    low, high = int(low or 0), int(high or 0)
    fmt = lambda n: f"{n:,}".replace(",", " ")
    if high == 0:
        return "Бесплатно"
    if low == high:
        return f"{fmt(high)} ₽"
    return f"от {fmt(low)} ₽" if low else f"до {fmt(high)} ₽"


def parse_time(value: Optional[str]) -> Optional[datetime]:
    """'2026-11-21T19:00:00+0300' -> naive UTC."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z").astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None


def to_event(item: dict) -> Optional[dict]:
    """Maps one Timepad event to our fields; None if it does not fit."""
    title = clean(item.get("name"))
    starts = parse_time(item.get("starts_at"))
    if not title or not starts:
        return None
    names = [clean(c.get("name")) for c in item.get("categories") or []]
    hay = " ".join(names + [title]).lower()
    if any(w in hay for w in SKIP_WORDS):
        return None
    age = str(item.get("age_limit") or "")
    if age.isdigit() and int(age) < 12:  # family and children's events
        return None
    ends = parse_time(item.get("ends_at"))
    if ends and ends - starts > timedelta(hours=8):  # exhibitions and other all-day things
        return None
    if (item.get("registration_data") or {}).get("is_registration_open") is False:
        return None
    address = clean((item.get("location") or {}).get("address"))
    if not address:  # no venue: most likely an online event
        return None
    organization = item.get("organization") or {}
    organizer = clean(organization.get("name"))
    description = clean(item.get("description_short"))
    if organizer:
        description = (description + " " if description else "") + f"Организатор: {organizer}."
    return {
        "source": NAME, "source_id": str(item.get("id")), "title": title[:200], "description": description[:2000],
        "category": pick_category(names, title), "starts_at": starts, "ends_at": ends,
        "place": short(address), "address": address[:300],
        "price": price_text(item.get("registration_data")), "url": str(item.get("url") or "")[:500],
    }


def short(address: str, limit: int = 48) -> str:
    """A long «how to find us» text -> something that fits a card."""
    text = re.sub(r"^(место встречи|адрес|сбор)\s*[:—-]\s*", "", address, flags=re.I)
    text = re.split(r"[;(]| - | — |(?<=[а-яёa-z]{3})\.\s+(?=[А-ЯЁA-Z«])", text)[0].strip(" ,.")
    parts, head = [p.strip() for p in text.split(",") if p.strip()], ""
    for part in parts:
        if head and len(head) + len(part) + 2 > limit:
            break
        head = f"{head}, {part}" if head else part
    if len(head) > limit:
        head = head[:limit].rsplit(" ", 1)[0].rstrip(" ,") + "…"
    return head or address[:limit]


async def fetch(token: str, city: str, days_ahead: int, client: Optional[httpx.AsyncClient] = None) -> list:
    """All suitable public events of the city for the next days."""
    now = datetime.now(timezone.utc)
    params = {
        "limit": 100, "skip": 0, "cities": city, "sort": "+starts_at",
        "starts_at_min": now.strftime("%Y-%m-%dT%H:%M:%S+0000"),
        "starts_at_max": (now + timedelta(days=days_ahead)).strftime("%Y-%m-%dT%H:%M:%S+0000"),
        "fields": "location,description_short,categories,organization,registration_data,age_limit,ends_at",
        "access_statuses": "public", "moderation_statuses": "featured,shown",
    }
    own = client is None
    client = client or httpx.AsyncClient(timeout=30)
    out: list = []
    try:
        seen = set()
        while params["skip"] < 8000:
            response = await client.get(API, params=params, headers={"Authorization": f"Bearer {token}"})
            response.raise_for_status()
            values = response.json().get("values") or []
            for event in filter(None, map(to_event, values)):
                key = (event["title"], event["starts_at"].date())  # repeated sessions of one day -> the first
                if key not in seen:
                    seen.add(key)
                    out.append(event)
            if len(values) < params["limit"]:
                break
            params["skip"] += params["limit"]
            await asyncio.sleep(0.25)
    finally:
        if own:
            await client.aclose()
    return out
