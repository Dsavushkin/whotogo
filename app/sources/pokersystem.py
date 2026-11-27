"""Sport poker tournaments (no money play) of Moscow clubs running on ПокерСистема (pokersystem.ru).

Every club has its own subdomain; its public page loads the schedule from php.php (action tournaments.list)
without signing in. We only show what the club's own page shows to any visitor.
"""
import asyncio
import html
import re
from datetime import datetime, timezone
from typing import Optional

import httpx

NAME = "pokersystem"
API = "https://{slug}.pokersystem.ru/php.php"
SITE = "https://{slug}.pokersystem.ru/"
# Moscow clubs from pokersystem.ru/clubs?city=Москва. Clubs outside Moscow are dropped by address anyway.
CLUBS = (
    "acepokerclub", "kingoftable", "offline", "aurum", "betpoker", "dist", "hroniki", "legacy-poker-club",
    "pokerfaceclub", "river-rat", "troya", "pokerplaymsk", "a2poker", "pokerclub", "sparta", "afk", "pokermsc",
    "lounge-yugo-zapad", "noble-club", "aces", "dopamine", "sova", "t-poker", "karta", "korol-na-stule",
    "stav-tv", "ak-tt", "full-house-89", "fullhouse", "kartel",
)
MOSCOW = re.compile(r"москв|зеленоград", re.I)
DAYS_AHEAD = 21


def clean(text) -> str:
    text = re.sub(r"<[^>]+>", " ", str(text or ""))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def short_address(address: str) -> str:
    """'г. Москва, вн.тер. г. муниципальный округ Таганский, ул. …' -> 'г. Москва, ул. …'."""
    address = re.sub(r"вн\.\s*тер\.[^,]*,\s*", "", clean(address), flags=re.I)
    return re.sub(r",\s*,", ",", address).strip(" ,")


def price_text(value) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return ""
    if amount <= 0:
        return "Бесплатно"
    return f"{int(amount):,} ₽ за участие".replace(",", " ")


def to_event(item: dict, slug: str, now: Optional[datetime] = None) -> Optional[dict]:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    if item.get("status") != "upcoming" or str(item.get("is_hidden")) == "1" or str(item.get("invite_only")) == "1":
        return None
    address = short_address(item.get("address"))
    title = clean(item.get("title"))
    try:
        starts = datetime.fromtimestamp(int(item["ts"]), timezone.utc).replace(tzinfo=None)
    except (KeyError, TypeError, ValueError):
        return None
    if not (title and item.get("id") and MOSCOW.search(address)):
        return None
    if starts <= now or (starts - now).days > DAYS_AHEAD:
        return None
    seats = int(item.get("max_participants") or 0)
    taken = int(item.get("current_participants") or 0) + int(item.get("fake_participants") or 0)
    if seats and taken >= seats:
        return None
    club = clean(item.get("location_title") or item.get("location_name")) or slug
    about = clean(item.get("description"))
    lines = [about[:600]] if about else []
    lines.append("Спортивный покер: играют на фишки, не на деньги. Можно прийти одному — здесь найдётся компания за стол.")
    if seats:
        lines.append(f"Мест: {seats}.")
    lines.append(f"Организатор: {club}. Запись — на странице клуба.")
    if not re.search(r"покер|poker|холдем|омаха|omaha", title, re.I):
        title = f"Покер: {title}"
    return {
        "source": NAME, "source_id": f"{slug}-{item['id']}"[:64], "title": f"{title} · {club}"[:200],
        "description": " ".join(lines)[:2000], "category": "poker", "starts_at": starts, "ends_at": None,
        "place": club[:200], "address": address[:300], "price": price_text(item.get("price_entry")),
        "url": SITE.format(slug=slug)[:500], "image": "",
    }


async def club_events(client: httpx.AsyncClient, slug: str) -> list:
    response = await client.post(API.format(slug=slug), data={"action": "tournaments.list"},
                                 headers={"Referer": SITE.format(slug=slug), "Origin": SITE.format(slug=slug)[:-1]})
    response.raise_for_status()
    data = response.json() or {}
    return [event for event in (to_event(item, slug) for item in data.get("tournaments") or []) if event]


async def fetch(client: Optional[httpx.AsyncClient] = None, clubs=CLUBS) -> list:
    own = client is None
    client = client or httpx.AsyncClient(timeout=20, headers={"User-Agent": "KtoIdet/1.0 (+https://kompaniyana.ru)",
                                                               "Accept": "application/json"})
    out: list = []
    failed = 0
    try:
        for start in range(0, len(clubs), 5):  # a few clubs at a time, gently
            batch = await asyncio.gather(*(club_events(client, slug) for slug in clubs[start:start + 5]),
                                         return_exceptions=True)
            for result in batch:
                if isinstance(result, Exception):
                    failed += 1
                else:
                    out += result
    finally:
        if own:
            await client.aclose()
    if failed == len(clubs):
        raise RuntimeError("no club answered")
    return out
