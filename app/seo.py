"""Plain HTML pages for search engines: one page per event, afisha sections, sitemap and robots.

The Mini App draws everything with JavaScript, which Yandex and Google read poorly. These pages are
rendered on the server, carry their own title, description and schema.org markup, and lead people
into the app («Найти компанию») or to the App Store.
"""
import html
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .api import CATEGORIES, TZ, counts_for, day_bounds
from .config import settings
from .db import get_session
from .models import Event, utcnow

router = APIRouter(include_in_schema=False)
APP_STORE = "https://apps.apple.com/ru/app/id6837698613"

# URL part → (category key, heading, what people search for)
SECTIONS = {
    "muzyka": ("music", "Концерты и музыка", "концерты в Москве"),
    "vecherinki": ("party", "Вечеринки", "вечеринки в Москве"),
    "eda": ("food", "Еда и дегустации", "гастрономические события Москвы"),
    "igry": ("games", "Игры и квизы", "квизы и настольные игры в Москве"),
    "iskusstvo": ("art", "Искусство и выставки", "выставки и арт-события Москвы"),
    "teatr": ("theater", "Театр и стендап", "спектакли и стендап в Москве"),
    "kino": ("cinema", "Кино", "кинопоказы в Москве"),
    "lekcii": ("talk", "Лекции и встречи", "лекции в Москве"),
    "sport": ("sport", "Спорт", "спортивные события и тренировки в Москве"),
    "progulki": ("walk", "Прогулки и экскурсии", "экскурсии и прогулки по Москве"),
    "znakomstva": ("dating", "Знакомства", "вечеринки знакомств в Москве"),
}
DAYS = {
    "segodnya": ("today", "Куда сходить в Москве сегодня", "сегодня"),
    "zavtra": ("tomorrow", "Куда сходить в Москве завтра", "завтра"),
    "vyhodnye": ("weekend", "Куда сходить в Москве на выходных", "на выходных"),
}
SECTION_OF = {key: slug for slug, (key, _, _) in SECTIONS.items()}

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
          "ноября", "декабря"]
WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
TRANSLIT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                    "a b v g d e e zh z i y k l m n o p r s t u f h ts ch sh sch _ y _ e yu ya".split()))
TRANSLIT.update({"ъ": "", "ь": ""})


def slugify(text: str) -> str:
    out = "".join(TRANSLIT.get(ch, ch) for ch in text.lower())
    out = re.sub(r"[^a-z0-9]+", "-", out).strip("-")
    return out[:60].rstrip("-") or "sobytie"


def event_path(event: Event) -> str:
    return f"/e/{event.id}-{slugify(event.title)}"


def site() -> str:
    return (settings.webapp_url or "").rstrip("/")


def local(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc).astimezone(TZ)


def when(event: Event) -> str:
    start = local(event.starts_at)
    text = f"{WEEKDAYS[start.weekday()]}, {start.day} {MONTHS[start.month - 1]}, {start:%H:%M}"
    if event.ends_at and local(event.ends_at).date() != start.date():
        end = local(event.ends_at)
        text += f" — {end.day} {MONTHS[end.month - 1]}"
    return text


def e(text) -> str:
    return html.escape(str(text or ""), quote=True)


def short(text: str, most: int = 160) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= most else text[:most - 1].rsplit(" ", 1)[0] + "…"


def page(title: str, description: str, path: str, body: str, *, image: str = "", schema: Optional[dict] = None,
         noindex: bool = False) -> HTMLResponse:
    url = site() + path
    head = [
        f"<title>{e(title)}</title>",
        f'<meta name="description" content="{e(description)}">',
        f'<link rel="canonical" href="{e(url)}">',
        '<meta property="og:type" content="website">', '<meta property="og:site_name" content="Кто идёт">',
        f'<meta property="og:title" content="{e(title)}">',
        f'<meta property="og:description" content="{e(description)}">', f'<meta property="og:url" content="{e(url)}">',
        '<meta name="apple-itunes-app" content="app-id=6837698613">',
    ]
    if image:
        head.append(f'<meta property="og:image" content="{e(image)}">')
    if noindex:
        head.append('<meta name="robots" content="noindex, follow">')
    if schema:
        data = json.dumps(schema, ensure_ascii=False).replace("</", "<\\/")
        head.append(f'<script type="application/ld+json">{data}</script>')
    nav = "".join(f'<a href="/afisha/{slug}">{e(name)}</a>' for slug, (_, name, _) in SECTIONS.items())
    days = "".join(f'<a href="/afisha/{slug}">{e(text.capitalize())}</a>' for slug, (_, _, text) in DAYS.items())
    return HTMLResponse(f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{chr(10).join(head)}
<link rel="stylesheet" href="/seo.css">
</head><body>
<header class="top"><a class="logo" href="/">Кто идёт</a><a class="btn" href="/">Открыть афишу</a></header>
<main>{body}</main>
<footer>
<nav><b>Когда</b><a href="/afisha">Вся неделя</a>{days}</nav>
<nav><b>Что</b>{nav}</nav>
<p>«Кто идёт» — афиша Москвы, где видно, кто ещё идёт. Отметьте «Ищу компанию», и чат откроется при взаимном интересе.
<a href="{APP_STORE}">Приложение для iPhone</a> · <a href="https://t.me/{e(settings.bot_username)}">Telegram</a> ·
<a href="/privacy">Конфиденциальность</a> · <a href="/support">Поддержка</a></p>
</footer>
</body></html>""")


def card(event: Event, looking: int = 0) -> str:
    poster = (f'<img src="{e(event.image)}" alt="" loading="lazy">' if event.image
              else f'<span aria-hidden="true" class="ph p{event.id % 4}">{e(CATEGORIES.get(event.category, "Другое"))}</span>')
    company = f'<span class="tag">Ищут компанию: {looking}</span>' if looking else ""
    return (f'<a class="card" href="{event_path(event)}">{poster}<div><span class="cat">'
            f'{e(CATEGORIES.get(event.category, "Другое"))}</span><h3>{e(event.title)}</h3>'
            f'<p>{e(when(event))}{" · " + e(event.place) if event.place else ""}</p>{company}</div></a>')


def offer(event: Event, url: str) -> Optional[dict]:
    text = (event.price or "").lower()
    if not text:
        return None
    if "бесплат" in text:
        price = "0"
    else:
        found = re.search(r"\d[\d\s]*", text)
        if not found:
            return None
        price = re.sub(r"\s", "", found.group())
    return {"@type": "Offer", "price": price, "priceCurrency": "RUB", "url": event.url or url,
            "availability": "https://schema.org/InStock"}


@router.get("/e/{key}", response_class=HTMLResponse)
async def event_page(key: str, session: AsyncSession = Depends(get_session)):
    found = re.match(r"(\d+)", key)
    event = await session.get(Event, int(found.group(1))) if found else None
    if event is None or not event.published:
        raise HTTPException(404)
    path = event_path(event)
    if "/e/" + key != path:
        return RedirectResponse(path, status_code=301)

    going, looking = (await counts_for(session, [event.id]))[event.id]
    past = (event.ends_at or event.starts_at + timedelta(hours=3)) < utcnow()
    category = CATEGORIES.get(event.category, "Другое")
    section = SECTION_OF.get(event.category)
    start = local(event.starts_at)
    date_words = f"{start.day} {MONTHS[start.month - 1]}"
    title = f"{event.title} — {date_words}, {event.place or 'Москва'}"[:110]
    description = short(f"{date_words} в {start:%H:%M}, {event.place or 'Москва'}. "
                        f"{event.description or category}. Найдите компанию, чтобы пойти вместе.")

    paragraphs = "".join(f"<p>{e(part)}</p>" for part in (event.description or "").split("\n") if part.strip())
    facts = [f"<dt>Когда</dt><dd>{e(when(event))}</dd>"]
    if event.place or event.address:
        facts.append(f"<dt>Где</dt><dd>{e(event.place)}{'<br>' if event.place and event.address else ''}"
                     f"{e(event.address)}</dd>")
    if event.price:
        facts.append(f"<dt>Цена</dt><dd>{e(event.price)}</dd>")
    people = (f"Уже идут: {going}. Ищут компанию: {looking}." if going
              else "Пока никто не отметился — будьте первым, кто ищет компанию.")
    ticket = (f'<a class="btn ghost" href="{e(event.url)}" rel="nofollow noopener" target="_blank">Билеты у организатора</a>'
              if event.url and not past else "")
    action = ('<p class="past">Событие уже прошло.</p>' if past else
              f'<p class="people">{e(people)}</p><div class="actions"><a class="btn" href="/#/event/{event.id}">'
              f'Найти компанию</a>{ticket}</div><p class="hint">В приложении можно отметить «Ищу компанию» и '
              f'посмотреть, кто ещё идёт. Чат открывается, только если интерес взаимный.</p>')

    more_rows = await session.execute(
        select(Event).where(Event.published, Event.city == event.city, Event.id != event.id,
                            Event.category == event.category, Event.starts_at >= utcnow())
        .order_by(Event.starts_at).limit(6))
    more = list(more_rows.scalars())
    more_html = ""
    if more:
        link = f'<a href="/afisha/{section}">все</a>' if section else ""
        more_html = (f'<section><h2>Ещё: {e(category.lower())} {link}</h2><div class="grid">'
                     + "".join(card(x) for x in more) + "</div></section>")

    crumbs = ['<a href="/afisha">Афиша Москвы</a>']
    if section:
        crumbs.append(f'<a href="/afisha/{section}">{e(SECTIONS[section][1])}</a>')
    poster = f'<img class="poster" src="{e(event.image)}" alt="{e(event.title)}">' if event.image else ""
    body = f"""<nav class="crumbs">{" › ".join(crumbs)}</nav>
<article class="event{'' if event.image else ' solo'}">{poster}<div>
<span class="cat">{e(category)}</span><h1>{e(event.title)}</h1>
<dl>{"".join(facts)}</dl>{action}{paragraphs}
</div></article>{more_html}"""

    url = site() + path
    schema = {
        "@context": "https://schema.org", "@type": "Event", "name": event.title, "url": url,
        "startDate": start.isoformat(timespec="minutes"),
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "eventStatus": "https://schema.org/EventScheduled",
        "location": {"@type": "Place", "name": event.place or "Москва",
                     "address": {"@type": "PostalAddress", "streetAddress": event.address or event.place or "",
                                 "addressLocality": "Москва", "addressCountry": "RU"}},
        "description": short(event.description or category, 500),
    }
    if event.ends_at:
        schema["endDate"] = local(event.ends_at).isoformat(timespec="minutes")
    if event.image:
        schema["image"] = [event.image]
    if offer(event, url):
        schema["offers"] = offer(event, url)
    return page(title, description, path, body, image=event.image, schema=schema,
                noindex=past and event.starts_at < utcnow() - timedelta(days=30))


async def listing(session: AsyncSession, path: str, h1: str, title: str, description: str, intro: str,
                  day: str = "week", category: str = "") -> HTMLResponse:
    start, end = day_bounds(day)
    query = select(Event).where(Event.published, Event.city == settings.city, Event.starts_at >= start,
                                Event.starts_at < end)
    if category:
        query = query.where(Event.category == category)
    events = list((await session.execute(query.order_by(Event.starts_at).limit(300))).scalars())
    counts = await counts_for(session, [x.id for x in events])
    if events:
        grid = '<div class="grid">' + "".join(card(x, counts[x.id][1]) for x in events) + "</div>"
    else:
        grid = '<p class="empty">Пока ничего нет — загляните позже: афиша обновляется каждые несколько часов.</p>'
    chips = "".join(f'<a class="chip{" on" if path == "/afisha/" + slug else ""}" href="/afisha/{slug}">'
                    f'{e(text.capitalize())}</a>' for slug, (_, _, text) in DAYS.items())
    chips += "".join(f'<a class="chip{" on" if path == "/afisha/" + slug else ""}" href="/afisha/{slug}">'
                     f'{e(name)}</a>' for slug, (_, name, _) in SECTIONS.items())
    body = (f'<h1>{e(h1)}</h1><p class="lead">{e(intro)}</p><div class="chips">{chips}</div>{grid}')
    return page(title, description, path, body, image=next((x.image for x in events if x.image), ""),
                noindex=not events)


@router.get("/afisha", response_class=HTMLResponse)
async def afisha(session: AsyncSession = Depends(get_session)):
    return await listing(
        session, "/afisha", "Афиша Москвы на неделю",
        "Афиша Москвы на неделю — куда сходить и с кем | Кто идёт",
        "Концерты, вечеринки, квизы, лекции и выставки Москвы на ближайшую неделю. Смотрите, кто ещё идёт, "
        "и находите компанию.",
        "Необычные события Москвы на ближайшие семь дней. На каждом событии видно, кто ищет компанию.")


@router.get("/afisha/{slug}", response_class=HTMLResponse)
async def afisha_section(slug: str, session: AsyncSession = Depends(get_session)):
    if slug in DAYS:
        day, h1, words = DAYS[slug]
        return await listing(
            session, f"/afisha/{slug}", h1, f"{h1} — афиша и компания | Кто идёт",
            f"Куда сходить в Москве {words}: концерты, вечеринки, квизы, лекции. Найдите компанию на вечер.",
            f"События Москвы {words}. Отметьте «Ищу компанию», чтобы пойти не одному.", day=day)
    if slug in SECTIONS:
        key, h1, words = SECTIONS[slug]
        return await listing(
            session, f"/afisha/{slug}", f"{h1} в Москве",
            f"{h1} в Москве на неделю — афиша | Кто идёт",
            f"{words.capitalize()} на ближайшую неделю. Смотрите, кто ещё идёт, и находите компанию.",
            f"{words.capitalize()} на ближайшие семь дней.", category=key)
    raise HTTPException(404)


@router.get("/sitemap.xml")
async def sitemap(session: AsyncSession = Depends(get_session)):
    base = site()
    today = datetime.now(TZ).date().isoformat()
    urls = [(base + "/", today, "daily"), (base + "/afisha", today, "daily")]
    urls += [(f"{base}/afisha/{slug}", today, "daily") for slug in [*DAYS, *SECTIONS]]
    rows = await session.execute(
        select(Event).where(Event.published, Event.starts_at >= utcnow() - timedelta(hours=3))
        .order_by(Event.starts_at).limit(5000))
    for event in rows.scalars():
        changed = (event.created_at or utcnow()).date().isoformat()
        urls.append((base + event_path(event), changed, "weekly"))
    items = "".join(f"<url><loc>{html.escape(loc)}</loc><lastmod>{mod}</lastmod><changefreq>{freq}</changefreq></url>"
                    for loc, mod, freq in urls)
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>')
    return Response(xml, media_type="application/xml")


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots(request: Request):
    """Only the main domain is indexed; the technical address (sslip.io) stays out of search."""
    main_host = urlparse(site()).hostname or ""
    if request.url.hostname != main_host:
        return "User-agent: *\nDisallow: /\n"
    return (f"User-agent: *\nDisallow: /api/\nAllow: /\n\nSitemap: {site()}/sitemap.xml\n")
