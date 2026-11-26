"""Quiz games of «Квиз, плиз!» in Moscow, from the public schedule the site itself uses (quizplease.ru/schedule)."""
import html
import re
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import httpx

NAME = "quizplease"
API = "https://api.quizplease.ru/api/games/schedule/{city}"
SITE = "https://quizplease.ru/game/{id}"
MOSCOW_ID = 4
TZ = ZoneInfo("Europe/Moscow")
# 0 — registration open, 2 — open, closes soon; 1 — no places, reserve only (useless for a new team).
OPEN_STATUSES = (0, 2)
ONLINE_TYPE = 1  # streams «везде, где есть интернет»


def clean(text: Optional[str]) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def parse_time(value: str) -> Optional[datetime]:
    """'26.11.2026 19:00' Moscow time -> naive UTC."""
    try:
        local = datetime.strptime(value.strip(), "%d.%m.%Y %H:%M").replace(tzinfo=TZ)
    except (AttributeError, ValueError):
        return None
    return local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def to_event(item: dict) -> Optional[dict]:
    if item.get("status") not in OPEN_STATUSES or item.get("game_type") == ONLINE_TYPE:
        return None
    place = item.get("place") or {}
    address = clean(place.get("address_ru") or place.get("address"))
    starts = parse_time(item.get("date") or "")
    title = clean(item.get("title"))
    if not (address and starts and title and item.get("id")):
        return None
    if re.search(r"онлайн|стрим|дет(ск|и)", title, re.I):
        return None
    number = clean(str(item.get("game_number") or ""))
    full_title = f"Квиз, плиз! {title}" if "квиз" not in title.lower() and "плиз" not in title.lower() else title
    if number and "#" not in full_title:
        full_title += f" #{number}"
    about = clean(item.get("quote")) or clean(item.get("description"))
    size = item.get("max_participants")
    lines = [about[:600]] if about else []
    if size:
        lines.append(f"Команды до {size} человек — можно прийти одному и собрать команду здесь.")
    lines.append("Организатор: «Квиз, плиз!». Регистрация команды — на сайте организатора.")
    price = item.get("current_price") or item.get("price")
    template = item.get("template") or {}
    image = str(template.get("background_phone") or template.get("background_pc") or "")
    return {
        "source": NAME, "source_id": str(item["id"])[:64], "title": full_title[:200],
        "description": " ".join(lines)[:2000], "category": "quiz", "starts_at": starts, "ends_at": None,
        "place": clean(place.get("title"))[:200] or address[:48], "address": address[:300],
        "price": f"{int(float(price)):,} ₽ с человека".replace(",", " ") if price else "",
        "url": SITE.format(id=item["id"])[:500], "image": image[:500] if image.startswith("https://") else "",
    }


async def fetch(client: Optional[httpx.AsyncClient] = None, city_id: int = MOSCOW_ID) -> list:
    own = client is None
    client = client or httpx.AsyncClient(timeout=30, headers={"User-Agent": "KtoIdet/1.0 (+https://kompaniyana.ru)",
                                                               "Accept": "application/json",
                                                               "Referer": "https://quizplease.ru/schedule"})
    params = [("per_page", 100), ("order", "date")] + [("statuses[]", s) for s in (0, 1, 2, 3, 5)]
    out: list = []
    try:
        for page in range(1, 6):
            response = await client.get(API.format(city=city_id), params=params + [("page", page)])
            response.raise_for_status()
            data = (response.json() or {}).get("data") or {}
            out += filter(None, map(to_event, data.get("data") or []))
            if page >= int((data.get("pagination") or {}).get("total_pages") or 1):
                break
    finally:
        if own:
            await client.aclose()
    return out
