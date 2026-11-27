"""Mafia game nights of Moscow clubs from FindMafia (findmafia.ru), where clubs publish their schedule and
take sign-ups. The page carries schema.org Event microdata; we read only that and link back to sign up there."""
import html
import re
from datetime import datetime, timezone
from typing import Optional

import httpx

NAME = "findmafia"
URL = "https://findmafia.ru/"
BLOCK = re.compile(r'itemtype="https://schema\.org/Event"(.*?)</li>', re.S)
SKIP = re.compile(r"дет(ск|и)|онлайн|online|подрост|школьн", re.I)


def clean(text) -> str:
    text = re.sub(r"<[^>]+>", " ", str(text or ""))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def pick(pattern: str, block: str) -> str:
    found = re.search(pattern, block, re.S)
    return clean(found.group(1)) if found else ""


def to_event(block: str, now: Optional[datetime] = None) -> Optional[dict]:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    url = pick(r'itemprop="url"\s+href="([^"]+)"', block)
    title = pick(r'itemprop="name">([^<]+)</span>\s*</h2>', block) or pick(r'class="title">(.*?)</h2>', block)
    club = pick(r'class\s*=\s*"org">([^<]+)', block)
    start = pick(r'itemprop="startDate"\s+content="([^"]+)"', block)
    found = re.search(r"/(\d+)-[^/]*$", url)
    if not (url.startswith(URL) and title and start and found) or SKIP.search(title):
        return None
    try:
        starts = datetime.fromisoformat(start).astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None
    if starts <= now:
        return None
    place = pick(r'class="location-href"[^>]*>([^<]+)</a>', block)
    street = pick(r'itemprop="streetAddress"\s+content="([^"]*)"', block)
    price = pick(r'itemprop="price"\s+content="([^"]*)"', block)
    if not re.search(r"мафи|mafia", title, re.I):
        title = f"Мафия: {title}"
    lines = [f"Игровой вечер клуба «{club}»." if club else "Игровой вечер мафии.",
             "Игроков рассаживают за стол по 10–12 человек, можно прийти одному — ведущий объяснит правила.",
             "Запись — на странице игры."]
    try:
        amount = int(float(price))
    except ValueError:
        amount = -1
    return {
        "source": NAME, "source_id": found.group(1)[:64], "title": (f"{title} · {club}" if club else title)[:200],
        "description": " ".join(lines)[:2000], "category": "mafia", "starts_at": starts, "ends_at": None,
        "place": (place or club)[:200], "address": (f"Москва, {street}" if street else "Москва")[:300],
        "price": "Бесплатно" if amount == 0 else (f"{amount:,} ₽ с человека".replace(",", " ") if amount > 0 else ""),
        "url": url[:500], "image": "",
    }


def parse(page: str, now: Optional[datetime] = None) -> list:
    return [event for event in (to_event(block, now) for block in BLOCK.findall(page)) if event]


async def fetch(client: Optional[httpx.AsyncClient] = None) -> list:
    own = client is None
    client = client or httpx.AsyncClient(timeout=30, follow_redirects=True,
                                         headers={"User-Agent": "KtoIdet/1.0 (+https://kompaniyana.ru)"})
    try:
        response = await client.get(URL)
        response.raise_for_status()
        page = response.text
    finally:
        if own:
            await client.aclose()
    if "Москв" not in page[:20000]:
        return []
    return parse(page)
