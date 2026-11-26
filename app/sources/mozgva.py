"""Quiz games of «Мозгва» in Moscow, from the public calendar page (mozgva.com/calendar)."""
import re
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Optional
from zoneinfo import ZoneInfo

import httpx

NAME = "mozgva"
URL = "https://mozgva.com/calendar"
TZ = ZoneInfo("Europe/Moscow")
MONTHS = {"января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6, "июля": 7, "августа": 8,
          "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12}
# Which piece of a game card a text belongs to, by the CSS class of its block.
FIELDS = {"date_m": "date", "game-title": "title", "type": "type", "time": "time", "price": "price",
          "participateBtn": "button", "hide-mobile": "place"}


class CalendarParser(HTMLParser):
    """Collects the cards <div class="itemGame-new2" id="item_<id>">…</div> as dicts of texts."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.games: list = []
        self.depth = 0          # div depth inside the current card, 0 = outside
        self.field: Optional[str] = None
        self.field_tag = ""
        self.skip = 0           # inside the long «Что это?» description

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = (attrs.get("class") or "").split()
        if tag == "div" and "itemGame-new2" in classes:
            self.games.append({"id": (attrs.get("id") or "").replace("item_", "")})
            self.depth = 1
            return
        if not self.depth:
            return
        if tag == "div":
            self.depth += 1
            if self.skip:
                self.skip += 1
            elif "game_description" in classes:
                self.skip = 1
        if self.skip:
            return
        for css, name in FIELDS.items():
            if css in classes and name not in self.games[-1]:
                self.field, self.field_tag = name, tag
                self.games[-1][name] = ""

    def handle_endtag(self, tag):
        if not self.depth:
            return
        if tag == self.field_tag:
            self.field = None
        if tag == "div":
            if self.skip:
                self.skip -= 1
            self.depth -= 1

    def handle_data(self, data):
        if self.depth and self.field and not self.skip:
            self.games[-1][self.field] += data


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def game_date(text: str, today: date) -> Optional[date]:
    """'27 ноября' -> the nearest such date from today on (December's calendar shows January)."""
    m = re.match(r"(\d{1,2})\s+([а-я]+)", norm(text).lower())
    if not m or m.group(2) not in MONTHS:
        return None
    day, month = int(m.group(1)), MONTHS[m.group(2)]
    year = today.year + (1 if month < today.month - 1 else 0)
    try:
        return date(year, month, day)
    except ValueError:
        return None


def to_event(game: dict, today: date) -> Optional[dict]:
    title, kind = norm(game.get("title")), norm(game.get("type"))
    if not title or not game.get("id"):
        return None
    if re.search(r"дет(ск|и)|лет\b|онлайн|домашн", f"{title} {kind}", re.I):
        return None
    if "резерв" in norm(game.get("button")).lower():  # no places left
        return None
    day = game_date(game.get("date", ""), today)
    clock = re.match(r"(\d{1,2}):(\d{2})", norm(game.get("time")))
    if not day or not clock:
        return None
    local = datetime(day.year, day.month, day.day, int(clock.group(1)), int(clock.group(2)), tzinfo=TZ)
    starts = local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    venue = norm(game.get("place"))
    m = re.match(r"(.+?)\s*\((.+)\)\s*$", venue)
    place, street = (m.group(1), m.group(2)) if m else (venue, "")
    price = norm(game.get("price"))
    price = re.sub(r"\s*руб\.?", " ₽", price) + " с человека" if re.search(r"\d", price) else price
    name = title if "мозгв" in title.lower() else f"Мозгва: {title}"
    about = f"{kind}. " if kind else ""
    return {
        "source": NAME, "source_id": str(game["id"])[:64], "title": name[:200],
        "description": (about + "Квиз командами до 9 человек — можно прийти одному и собрать команду здесь. "
                        "Организатор: «Мозгва». Регистрация команды — на сайте организатора.")[:2000],
        "category": "quiz", "starts_at": starts, "ends_at": None, "place": place[:200],
        "address": (f"{street}, Москва" if street else place)[:300], "price": price[:120], "url": URL, "image": "",
    }


def parse(page: str, today: Optional[date] = None) -> list:
    today = today or datetime.now(TZ).date()
    parser = CalendarParser()
    parser.feed(page)
    return [event for event in (to_event(game, today) for game in parser.games) if event]


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
    # The page follows the visitor's city; take it only when it is the Moscow calendar.
    head = page[:5000]
    if "Москв" not in head:
        return []
    return parse(page)
