import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from app.api import day_bounds
from app.auth import verify_init_data
from app.jobs import send_after_prompts
from app import texts
from app.notify import notifier
from app.sources.timepad import price_text, short, to_event
from tests.conftest import Person, add_event


async def test_profile_requires_adult_confirmation(client):
    guest = Person(client, 500, "Гость")
    assert (await guest.call("PUT", "/me", json={"name": "Гость", "age": 17, "adult_ok": True})).status_code == 422
    assert (await guest.call("PUT", "/me", json={"name": "Гость", "age": 20, "adult_ok": False})).status_code == 400
    event_id = await add_event()
    assert (await guest.call("POST", f"/events/{event_id}/attend", json={"status": "going"})).status_code == 403
    assert (await client.get("/api/me")).status_code == 401


async def test_together_only_when_mutual(people):
    vera, anya, kirill = people
    event_id = await add_event()
    for person in (anya, kirill):
        await person.ok("POST", f"/events/{event_id}/attend", json={"status": "looking", "note": "Привет"})
    listed = (await vera.ok("GET", f"/events/{event_id}/people"))["people"]
    assert {p["name"] for p in listed} == {"Аня", "Кирилл"} and not any(p["invited"] for p in listed)
    # Аня hears that one more person looks for company there; nothing about who invited whom
    assert [(s[0], s[2]) for s in notifier.sent] == [(anya.tg_id, f"people-{event_id}")] and "Кирилл" in notifier.sent[0][1]
    notifier.sent.clear()

    first = await vera.ok("POST", f"/events/{event_id}/invite/{anya.id}")
    assert first["match_id"] is None and first["other"] is None
    assert notifier.sent == []  # one-sided interest is silent
    assert (await anya.ok("GET", "/matches"))["matches"] == []
    seen_by_anya = (await anya.ok("GET", f"/events/{event_id}/people"))["people"]
    assert all(not p["invited"] and p["match_id"] is None for p in seen_by_anya)  # she cannot tell who tapped

    again = await vera.ok("POST", f"/events/{event_id}/invite/{anya.id}")  # repeat tap changes nothing
    assert again["match_id"] is None

    second = await anya.ok("POST", f"/events/{event_id}/invite/{vera.id}")
    assert second["match_id"] and second["other"]["name"] == "Вера"
    assert [s[0] for s in notifier.sent] == [vera.tg_id] and "Есть с кем пойти" in notifier.sent[0][1]
    assert len((await vera.ok("GET", "/matches"))["matches"]) == 1
    assert (await kirill.ok("GET", "/matches"))["matches"] == []
    assert (await kirill.call("GET", f"/matches/{second['match_id']}")).status_code == 404


async def test_chat_and_block(people):
    vera, anya, _ = people
    event_id = await add_event()
    await anya.ok("POST", f"/events/{event_id}/attend", json={"status": "looking"})
    await vera.ok("POST", f"/events/{event_id}/attend", json={"status": "looking"})
    await vera.ok("POST", f"/events/{event_id}/invite/{anya.id}")
    match_id = (await anya.ok("POST", f"/events/{event_id}/invite/{vera.id}"))["match_id"]
    notifier.sent.clear()

    await vera.ok("POST", f"/matches/{match_id}/messages", json={"text": "Привет!"})
    await vera.ok("POST", f"/matches/{match_id}/messages", json={"text": "Где встретимся?"})
    chat = await anya.ok("GET", f"/matches/{match_id}")
    assert [m["text"] for m in chat["messages"]] == ["Привет!", "Где встретимся?"] and not chat["messages"][0]["mine"]
    assert len([s for s in notifier.sent if s[0] == anya.tg_id]) == 1  # two quick messages -> one push
    newer = await anya.ok("GET", f"/matches/{match_id}", params={"after": chat["messages"][0]["id"]})
    assert len(newer["messages"]) == 1

    await anya.ok("POST", f"/users/{vera.id}/report", json={"reason": "Грубит", "block": True})
    assert any(s[0] == 1 and "Жалоба" in s[1] for s in notifier.sent)  # admin (tg id 1) is told
    assert (await vera.call("POST", f"/matches/{match_id}/messages", json={"text": "Ау"})).status_code == 403
    assert (await vera.ok("GET", "/matches"))["matches"] == []
    assert (await vera.ok("GET", f"/events/{event_id}/people"))["people"] == []


async def test_after_event_marks(people):
    vera, anya, kirill = people
    future = await add_event(hours=5)
    past = await add_event(hours=-20, title="Вчерашний ужин")
    assert (await vera.call("GET", f"/events/{future}/after")).status_code in (400, 403)
    for person in people:
        await person.ok("POST", f"/events/{past}/attend", json={"status": "going"})
    guests = (await vera.ok("GET", f"/events/{past}/after"))["guests"]
    assert {g["name"] for g in guests} == {"Аня", "Кирилл"}

    assert (await vera.ok("POST", f"/events/{past}/after", json={"user_ids": [anya.id, kirill.id]}))["matches"] == []
    assert notifier.sent == []
    result = await anya.ok("POST", f"/events/{past}/after", json={"user_ids": [vera.id]})
    assert len(result["matches"]) == 1 and "взаимно" in notifier.sent[0][1]
    # Vera takes Kirill's mark back; later Kirill marks her -> no pair.
    await vera.ok("POST", f"/events/{past}/after", json={"user_ids": [anya.id]})
    assert (await kirill.ok("POST", f"/events/{past}/after", json={"user_ids": [vera.id]}))["matches"] == []
    assert len((await vera.ok("GET", "/matches"))["matches"]) == 1
    assert [e["title"] for e in (await vera.ok("GET", "/my/events"))["past"]] == ["Вчерашний ужин"]

    notifier.sent.clear()
    assert await send_after_prompts(now_local_hour=3) == 0   # not at night
    assert await send_after_prompts(now_local_hour=11) == 3
    assert await send_after_prompts(now_local_hour=12) == 0  # only once
    assert all(s[2] == f"after-{past}" for s in notifier.sent)


async def test_feed_counts_and_people_feed(people):
    vera, anya, kirill = people
    quiet = await add_event(hours=3, title="Тихий вечер")
    await add_event(hours=0.5, title="Уже начинается")  # less than an hour left: hidden
    busy = await add_event(hours=2, title="Шумный вечер", category="party")
    await anya.ok("POST", f"/events/{busy}/attend", json={"status": "looking"})
    await kirill.ok("POST", f"/events/{busy}/attend", json={"status": "going"})
    events = (await vera.ok("GET", "/events", params={"day": "week"}))["events"]
    assert [e["title"] for e in events] == ["Шумный вечер", "Тихий вечер"]
    assert (events[0]["going"], events[0]["looking"]) == (2, 1)
    assert [e["id"] for e in (await vera.ok("GET", "/events", params={"day": "week", "category": "party"}))["events"]] == [busy]
    feed = (await vera.ok("GET", "/people"))["people"]
    assert [(p["name"], p["event"]["id"]) for p in feed] == [("Аня", busy)]
    await anya.ok("POST", f"/events/{busy}/attend", json={"status": "none"})
    assert (await vera.ok("GET", "/people"))["people"] == []
    assert (await vera.call("POST", f"/events/{busy}/invite/{anya.id}")).status_code == 400
    detail = await kirill.ok("GET", f"/events/{busy}")
    assert detail["my_status"] == "going" and detail["going"] == 1 and quiet


async def test_organizer_cabinet(people, client):
    vera, anya, _ = people
    body = {"title": "Квартирник", "starts_at": (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT20:00"),
            "place": "Квартира на Чистых", "category": "music", "price": "800 ₽", "capacity": 20}
    assert (await vera.call("POST", "/org/events", json=body)).status_code == 403
    admin = await Person(client, 1, "Админ").join()
    event = await admin.ok("POST", "/org/events", json=body)
    assert event["starts_at"].endswith("T20:00+03:00")
    await anya.ok("POST", f"/events/{event['id']}/attend", json={"status": "looking"})
    await vera.ok("POST", f"/events/{event['id']}/attend", json={"status": "looking"})
    await vera.ok("POST", f"/events/{event['id']}/invite/{anya.id}")
    await anya.ok("POST", f"/events/{event['id']}/invite/{vera.id}")
    assert (await admin.ok("POST", f"/org/events/{event['id']}/checkin/{anya.id}"))["checked_in"] is True
    stats = await admin.ok("GET", f"/org/events/{event['id']}")
    assert (stats["going"], stats["looking"], stats["checked_in"], stats["pairs"]) == (2, 2, 1, 1)
    assert (await vera.call("GET", f"/org/events/{event['id']}")).status_code == 403


async def test_delete_account(people):
    vera, anya, _ = people
    event_id = await add_event()
    await anya.ok("POST", f"/events/{event_id}/attend", json={"status": "looking"})
    await vera.ok("POST", f"/events/{event_id}/invite/{anya.id}")
    await anya.ok("POST", f"/events/{event_id}/invite/{vera.id}")
    await anya.ok("DELETE", "/me")
    assert (await vera.ok("GET", "/matches"))["matches"] == []
    assert (await vera.ok("GET", f"/events/{event_id}"))["going"] == 1
    assert (await anya.ok("GET", "/me"))["adult_ok"] is False  # a fresh empty account


def test_telegram_signature():
    token = "123456:TEST"
    def sign(fields):
        check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
        secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        return urlencode({**fields, "hash": hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()})
    fields = {"auth_date": str(int(time.time())), "query_id": "AAE", "user": json.dumps({"id": 42, "first_name": "Вера"})}
    assert verify_init_data(sign(fields), token, 3600)["id"] == 42
    assert verify_init_data(sign(fields), "999:OTHER", 3600) is None
    assert verify_init_data(sign(fields).replace("42", "43"), token, 3600) is None
    assert verify_init_data(sign({**fields, "auth_date": str(int(time.time()) - 7200)}), token, 3600) is None
    assert verify_init_data("", token, 3600) is None


def test_day_bounds():
    friday_evening = datetime(2026, 11, 20, 16, 0, tzinfo=timezone.utc)  # 19:00 in Moscow
    start, end = day_bounds("today", friday_evening)
    assert (start, end) == (datetime(2026, 11, 20, 17, 0), datetime(2026, 11, 20, 21, 0))
    assert day_bounds("tomorrow", friday_evening) == (datetime(2026, 11, 20, 21, 0), datetime(2026, 11, 21, 21, 0))
    assert day_bounds("weekend", friday_evening) == (datetime(2026, 11, 20, 21, 0), datetime(2026, 11, 22, 21, 0))
    sunday = datetime(2026, 11, 22, 9, 0, tzinfo=timezone.utc)
    assert day_bounds("weekend", sunday) == (datetime(2026, 11, 22, 10, 0), datetime(2026, 11, 22, 21, 0))


def test_timepad_mapping():
    item = {"id": 777, "name": "Винил-вечер &quot;Chill&quot; &amp; джаз", "starts_at": "2026-11-21T20:00:00+0300",
            "ends_at": "2026-11-21T23:00:00+0300", "url": "https://x.timepad.ru/event/777/",
            "description_short": "<p>Приносите   пластинки</p>", "categories": [{"id": 1, "name": "Концерты"}],
            "location": {"city": "Москва", "address": "Николоямская ул. 1, Библиотека иностранной литературы, "
                         "центральный вход, Культурный центр «Франкотека», 2 этаж"},
            "organization": {"name": "Лофт"}, "age_limit": "18",
            "poster_image": {"default_url": "https://ucare.timepad.ru/abc/-/crop/1672x940/0,0/-/preview/308x600/-/format/jpeg/p.jpg",
                             "uploadcare_url": "//ucare.timepad.ru/abc/"},
            "registration_data": {"price_min": 500, "price_max": 1500, "is_registration_open": True}}
    event = to_event(item)
    assert event["title"] == 'Винил-вечер "Chill" & джаз' and event["category"] == "music"
    assert event["starts_at"] == datetime(2026, 11, 21, 17, 0) and event["price"] == "от 500 ₽"
    assert event["description"] == "Приносите пластинки Организатор: Лофт." and event["source_id"] == "777"
    assert event["place"] == "Николоямская ул. 1"
    assert event["image"] == "https://ucare.timepad.ru/abc/-/crop/1672x940/0,0/-/preview/960x960/-/format/jpeg/p.jpg"
    assert to_event({**item, "poster_image": None})["image"] == ""
    assert short("Место встречи: м. Китай-город, 10 выход, налево через пешеходный переход у памятника Кириллу "
                 "и Мефодию. Администратор с табличкой.") == "м. Китай-город, 10 выход"
    assert short("Покровка, 20") == "Покровка, 20" and len(short("Очень " * 30)) <= 49
    assert to_event({**item, "categories": [{"name": "Экскурсии и путешествия"}], "name": "Бункер"})["category"] == "walk"
    assert to_event({**item, "categories": [{"name": "Для детей"}]}) is None
    assert to_event({**item, "age_limit": "6"}) is None
    assert to_event({**item, "location": {"city": "Без города"}}) is None
    assert to_event({**item, "name": "Вебинар по продажам"}) is None
    assert to_event({**item, "name": "Квест-экскурсия (без гида)"}) is None
    assert to_event({**item, "ends_at": "2026-11-30T23:00:00+0300"}) is None
    assert to_event({**item, "registration_data": {"is_registration_open": False}}) is None
    assert price_text({"price_min": 0, "price_max": 0}) == "Бесплатно" and price_text(None) == ""
    assert price_text({"price_min": 1200, "price_max": 1200}) == "1 200 ₽"


async def test_import_adds_then_updates(client):
    import httpx
    from app.importer import save_events
    from app.sources import timepad

    def page(request):
        skip = int(request.url.params["skip"])
        assert request.headers["authorization"] == "Bearer T" and request.url.params["cities"] == "Москва"
        make = lambda i, hour: {"id": i, "name": f"Вечер {i % 3}", "starts_at": f"2026-11-21T{hour}:00:00+0300",
                                "location": {"address": "Покровка, 20"}, "age_limit": "16", "categories": []}
        values = [make(skip + i, 18 + i % 2) for i in range(100 if skip == 0 else 4)]
        return httpx.Response(200, json={"total": 104, "values": values})

    async with httpx.AsyncClient(transport=httpx.MockTransport(page)) as http:
        items = await timepad.fetch("T", "Москва", 7, client=http)
    assert len(items) == 3  # same title on the same day is kept once
    assert await save_events(items, "msk") == {"added": 3, "updated": 0, "seen": 3}
    items[0]["price"] = "Бесплатно"
    assert await save_events(items, "msk") == {"added": 0, "updated": 1, "seen": 3}


async def test_sign_in_with_code_from_bot(people, client):
    from sqlalchemy import select, update
    from app import api
    from app.auth import issue_login_code
    from app.db import Session
    from app.models import LoginCode, User

    vera = people[0]
    api._attempts.clear()
    async with Session() as session:
        user = (await session.execute(select(User).where(User.id == vera.id))).scalar_one()
        old = await issue_login_code(session, user)
        code = await issue_login_code(session, user)
    post = lambda c: client.post("/api/auth/code", json={"code": c})
    assert (await post(old)).status_code == 400 or old == code  # a newer code replaces the older one
    token = (await post(code)).json()["token"]
    assert (await post(code)).status_code == 400  # works once
    bearer = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/api/me", headers=bearer)).json()["name"] == "Вера"
    assert (await client.get("/api/me", headers={"Authorization": "Bearer nope"})).status_code == 401

    async with Session() as session:
        expired = await issue_login_code(session, user)
        await session.execute(update(LoginCode).values(expires_at=api.utcnow() - api.timedelta(minutes=1)))
        await session.commit()
    assert (await post(expired)).status_code == 400

    assert (await client.post("/api/auth/logout", headers=bearer)).status_code == 200
    assert (await client.get("/api/me", headers=bearer)).status_code == 401
    codes = [(await post("000000")).status_code for _ in range(9)]
    assert codes[-1] == 429 and 400 in codes  # guessing is cut off
    api._attempts.clear()


async def test_site_account_and_public_afisha(client):
    from app import api
    api._attempts.clear()
    event_id = await add_event(title="Открытый вечер")
    # A guest sees the afisha and the event page, nothing more.
    assert [e["title"] for e in (await client.get("/api/events", params={"day": "week"})).json()["events"]] == ["Открытый вечер"]
    assert (await client.get(f"/api/events/{event_id}")).json()["my_status"] is None
    assert (await client.get("/api/people")).status_code == 401
    assert (await client.post(f"/api/events/{event_id}/attend", json={"status": "going"})).status_code == 401

    account = {"email": "Vera@Example.com", "password": "correct horse"}
    assert (await client.post("/api/auth/register", json={"email": "bad", "password": "correct horse"})).status_code == 422
    assert (await client.post("/api/auth/register", json={**account, "password": "short"})).status_code == 422
    token = (await client.post("/api/auth/register", json=account)).json()["token"]
    assert (await client.post("/api/auth/register", json=account)).status_code == 400  # taken
    bearer = {"Authorization": f"Bearer {token}"}
    me = (await client.get("/api/me", headers=bearer)).json()
    assert me["adult_ok"] is False and me["has_telegram"] is False
    await client.put("/api/me", headers=bearer, json={"name": "Вера", "age": 28, "adult_ok": True})
    assert (await client.post(f"/api/events/{event_id}/attend", headers=bearer, json={"status": "looking"})).status_code == 200

    assert (await client.post("/api/auth/login", json={**account, "password": "wrong password"})).status_code == 400
    again = (await client.post("/api/auth/login", json={"email": "vera@example.com", "password": "correct horse"})).json()["token"]
    assert again != token and (await client.get("/api/me", headers={"Authorization": f"Bearer {again}"})).json()["name"] == "Вера"

    # A match with a Telegram user: only the Telegram side gets a bot message, nothing breaks for the site user.
    anya = await Person(client, 300, "Аня").join()
    await anya.ok("POST", f"/events/{event_id}/attend", json={"status": "looking"})
    await anya.ok("POST", f"/events/{event_id}/invite/{me['id']}")
    notifier.sent.clear()
    matched = (await client.post(f"/api/events/{event_id}/invite/{anya.id}", headers=bearer)).json()
    assert matched["match_id"] and [s[0] for s in notifier.sent] == [anya.tg_id]
    await anya.ok("POST", f"/matches/{matched['match_id']}/messages", json={"text": "Привет"})
    assert len(notifier.sent) == 1
    api._attempts.clear()


def test_moderation_filter():
    from app.moderation import is_clean
    for ok in ["Привет! Где встретимся?", "Иду на концерт, ребята", "Застрахуй себя от скуки — шучу", "Ребус", "Хлебушек",
               "Небо", "Требую кофе", "Сабля", "Колбаса", "мандарин", "Скребок", "", "Hello, Scunthorpe"]:
        assert is_clean(ok), ok
    for bad in ["иди на х.у.й", "Пиздец", "ёбаный", "ебать", "БЛЯДЬ", "бля", "мудак", "fuck you", "х у й"]:
        assert not is_clean(bad), bad


async def test_obscene_message_is_rejected(people):
    vera, anya, _ = people
    event_id = await add_event()
    await anya.ok("POST", f"/events/{event_id}/attend", json={"status": "looking"})
    assert (await vera.call("POST", f"/events/{event_id}/attend", json={"status": "looking", "note": "все мудаки"})).status_code == 400
    await vera.ok("POST", f"/events/{event_id}/attend", json={"status": "looking"})
    await vera.ok("POST", f"/events/{event_id}/invite/{anya.id}")
    match_id = (await anya.ok("POST", f"/events/{event_id}/invite/{vera.id}"))["match_id"]
    assert (await vera.call("POST", f"/matches/{match_id}/messages", json={"text": "ну ты и пиздабол"})).status_code == 400
    await vera.ok("POST", f"/matches/{match_id}/messages", json={"text": "Привет!"})


async def test_weekend_nudges(people, client):
    from datetime import datetime, timedelta, timezone
    from app.db import Session
    from app.jobs import send_weekend_nudges
    from app.models import User
    vera, anya, kirill = people
    friday_evening = datetime(2026, 11, 27, 15, 30, tzinfo=timezone.utc)  # 18:30 in Moscow
    async with Session() as session:
        from app.models import Event
        busy_event = Event(title="Квартирник", starts_at=datetime(2026, 11, 28, 17, 0), place="Чистые пруды")
        tonight = Event(title="Винил-вечер", starts_at=datetime(2026, 11, 27, 17, 0), place="Лофт")
        session.add_all([busy_event, tonight])
        await session.commit()
        busy_id, tonight_id = busy_event.id, tonight.id
    await vera.ok("POST", f"/events/{busy_id}/attend", json={"status": "going"})  # has weekend plans
    await anya.ok("PUT", "/me/settings", json={"nudges": False})                  # turned reminders off
    notifier.sent.clear()

    assert await send_weekend_nudges(datetime(2026, 11, 26, 9, 0, tzinfo=timezone.utc)) == 0   # Thursday morning
    assert await send_weekend_nudges(datetime(2026, 11, 24, 15, 30, tzinfo=timezone.utc)) == 0  # Tuesday
    assert await send_weekend_nudges(friday_evening) == 1
    assert notifier.sent[0][0] == kirill.tg_id and "Пятница" in notifier.sent[0][1] and "Винил-вечер" in notifier.sent[0][1]
    assert await send_weekend_nudges(friday_evening + timedelta(hours=1)) == 0   # once a day
    assert await send_weekend_nudges(friday_evening + timedelta(hours=17)) == 1  # Saturday 11:30 again
    assert (await kirill.ok("GET", "/me"))["nudges"] is True and (await anya.ok("GET", "/me"))["nudges"] is False


async def test_seo_pages(client):
    from tests.conftest import add_event
    event_id = await add_event(hours=30, title="Джаз в «Синей птице»", category="music", price="от 1 500 ₽",
                               address="Малая Дмитровка, 23/15", description="Квартет\nи гости")
    from app.seo import slugify
    assert slugify("Джаз в «Синей птице»") == "dzhaz-v-siney-ptitse"

    moved = await client.get(f"/e/{event_id}", follow_redirects=False)
    assert moved.status_code == 301 and moved.headers["location"] == f"/e/{event_id}-dzhaz-v-siney-ptitse"
    page = await client.get(moved.headers["location"])
    assert page.status_code == 200
    text = page.text
    assert "<h1>Джаз в «Синей птице»</h1>" in text and '"@type": "Event"' in text and '"price": "1500"' in text
    assert f'href="/#/event/{event_id}"' in text and "noindex" not in text
    assert (await client.get("/e/99999")).status_code == 404

    assert "Джаз" in (await client.get("/afisha/muzyka")).text
    assert "Джаз" in (await client.get("/afisha")).text
    assert (await client.get("/afisha/nepoyatno")).status_code == 404

    sitemap = (await client.get("/sitemap.xml")).text
    assert f"/e/{event_id}-dzhaz-v-siney-ptitse</loc>" in sitemap and "/afisha/vyhodnye</loc>" in sitemap
    assert (await client.get("/robots.txt")).text == "User-agent: *\nDisallow: /\n"  # test host ≠ main domain


async def test_day_reminders(people):
    from datetime import datetime, timedelta, timezone
    from app.jobs import send_day_reminders
    vera, anya, kirill = people
    now = datetime(2026, 11, 20, 12, 0, tzinfo=timezone(timedelta(hours=3)))  # Friday, noon in Moscow
    starts = (now + timedelta(hours=7)).astimezone(timezone.utc).replace(tzinfo=None)  # 19:00
    from app.db import Session
    from app.models import Event
    async with Session() as session:
        event = Event(title="Квиз <Мозгобойня>", starts_at=starts, place="Бар «Ровесник»")
        session.add(event)
        await session.commit()
    for person in (vera, anya, kirill):
        await person.ok("POST", f"/events/{event.id}/attend", json={"status": "looking"})
    await vera.ok("POST", f"/events/{event.id}/invite/{anya.id}")
    match_id = (await anya.ok("POST", f"/events/{event.id}/invite/{vera.id}"))["match_id"]
    notifier.sent.clear()

    assert await send_day_reminders(now) == 0  # 7 hours before: too early
    assert await send_day_reminders(now + timedelta(hours=3)) == 3  # 15:00
    sent = {s[0]: s for s in notifier.sent}
    assert "Сегодня в 19:00" in sent[vera.tg_id][1] and "Квиз &lt;Мозгобойня&gt;" in sent[vera.tg_id][1]
    assert "Идёте вместе с: Аня" in sent[vera.tg_id][1]
    assert "ищут ещё 2" in sent[kirill.tg_id][1]
    assert await send_day_reminders(now + timedelta(hours=4)) == 0  # once per event
    assert match_id


async def test_channel_posts(client):
    from datetime import datetime, timedelta, timezone
    from app import channel
    from app.db import Session
    from app.models import Event
    now = datetime(2026, 11, 20, 11, 5, tzinfo=timezone(timedelta(hours=3)))  # Friday 11:05 Moscow
    base = now.astimezone(timezone.utc).replace(tzinfo=None)
    async with Session() as session:
        for i, (title, category, hours) in enumerate([("Утренняя экскурсия", "walk", 1), ("Джаз <вечер>", "music", 8),
                                                     ("Квиз", "games", 9), ("Лекция", "talk", 7),
                                                     ("Ещё квиз", "games", 9), ("Третий квиз", "games", 10)]):
            session.add(Event(title=title, category=category, starts_at=base + timedelta(hours=hours), place="Бар",
                              image="https://img/x.jpg" if i == 1 else ""))
        await session.commit()

    class FakeBot:
        def __init__(self):
            self.sent = []

        async def send_photo(self, chat, photo, **kw):
            self.sent.append(("photo", chat, kw["caption"]))

        async def send_message(self, chat, text, **kw):
            self.sent.append(("text", chat, text))

    bot = FakeBot()
    assert await channel.run_schedule(bot, now) == []  # no channel yet
    await channel.set_setting("channel", "-100123")
    assert await channel.run_schedule(bot, now) == ["today"]
    kind, chat, text = bot.sent[0]
    assert kind == "photo" and chat == "-100123" and "Куда сходить сегодня, 20 ноября" in text
    assert "Джаз &lt;вечер&gt;" in text and "startapp=event-" in text and text.count("квиз") + text.count("Квиз") == 2
    assert await channel.run_schedule(bot, now + timedelta(minutes=10)) == []  # once a day


async def test_ad_sources(client):
    from app.auth import clean_source, start_source
    assert clean_source("src_vk-1") == "vk-1" and clean_source("tg<script>") == "tgscript"
    assert start_source("query_id=1&start_param=src_tgchan1&auth_date=1") == "tgchan1"
    assert start_source("start_param=event-5") == ""
    token = (await client.post("/api/auth/register", json={"email": "ad@ex.ru", "password": "secret123",
                                                          "source": "vk_ads"})).json()["token"]
    from app.db import Session
    from app.models import User
    from sqlalchemy import select
    async with Session() as session:
        assert (await session.execute(select(User.source).where(User.email == "ad@ex.ru"))).scalar() == "vk_ads"
    assert token


async def test_app_store_link(client):
    iphone = {"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)"}
    first = await client.get("/app?c=vk_ios", headers=iphone, follow_redirects=False)
    assert first.status_code == 302 and first.headers["location"].endswith("pt=127051032&mt=8&ct=vk_ios")
    await client.get("/app?c=vk_ios", headers=iphone, follow_redirects=False)
    android = await client.get("/app?c=vk_ios", headers={"user-agent": "Mozilla/5.0 (Linux; Android 14)"},
                               follow_redirects=False)
    assert android.headers["location"] == "/?utm_source=vk_ios"
    from app.channel import get_setting
    assert await get_setting("clicks:vk_ios") == "2"


async def test_telegram_ad_link(client):
    moved = await client.get("/tg?s=tg_chtets&erid=2W5zFHWBHsG", follow_redirects=False)
    assert moved.status_code == 302 and moved.headers["location"] == "https://t.me/whotogobot?startapp=src_tg_chtets"


async def test_telegram_ad_link_survives_marking(client):
    for url in ("/tg/tg_telega", "/tg/tg_telega?erid=2W5zFHWBHsG", "/?erid=2W5zFHWBHsG/tg/tg_telega"):
        moved = await client.get(url, follow_redirects=False)
        assert moved.headers["location"] == "https://t.me/whotogobot?startapp=src_tg_telega", url


async def test_girls_only(people):
    vera, anya, kirill = people
    for person, gender in ((vera, "f"), (anya, "f"), (kirill, "m")):
        await person.ok("PUT", "/me", json={"name": person.name, "age": 28, "gender": gender, "adult_ok": True})
    event = await add_event(category="music")
    saved = await vera.ok("POST", f"/events/{event}/attend", json={"status": "looking", "girls_only": True})
    assert saved["girls_only"] is True
    # A man does not see her and cannot invite her; a woman can.
    assert (await kirill.ok("GET", f"/events/{event}/people"))["people"] == []
    assert (await kirill.ok("GET", "/people"))["people"] == []
    assert (await kirill.call("POST", f"/events/{event}/invite/{vera.id}")).status_code == 400
    seen = (await anya.ok("GET", f"/events/{event}/people"))["people"]
    assert [p["name"] for p in seen] == ["Вера"] and seen[0]["girls_only"] is True
    # A man cannot turn the option on for himself.
    assert (await kirill.ok("POST", f"/events/{event}/attend", json={"status": "looking", "girls_only": True}))["girls_only"] is False
    # «Только девушки» filter hides men.
    assert [p["name"] for p in (await anya.ok("GET", "/people", params={"girls": 1}))["people"]] == ["Вера"]
    assert {p["name"] for p in (await anya.ok("GET", "/people"))["people"]} == {"Вера", "Кирилл"}
    # Changing gender away from «девушка» drops the option.
    await vera.ok("PUT", "/me", json={"name": "Вера", "age": 28, "gender": "", "adult_ok": True})
    assert [p["name"] for p in (await kirill.ok("GET", f"/events/{event}/people"))["people"]] == ["Вера"]


async def test_icebreaker(people):
    vera, anya, _ = people
    event = await add_event(category="cinema")
    await vera.ok("POST", f"/events/{event}/attend", json={"status": "looking"})
    await anya.ok("POST", f"/events/{event}/invite/{vera.id}")
    match = (await vera.ok("POST", f"/events/{event}/invite/{anya.id}"))["match_id"]
    chat = await vera.ok("GET", f"/matches/{match}")
    lines = [line[2:] for line in chat["icebreaker"].split("\n") if line.startswith("— ")]
    assert len(lines) == 2 and all(q in texts.ICEBREAKERS["cinema"] for q in lines)
    assert "Можно начать с вопроса" in notifier.sent[-1][1]


async def crowd(client, names, start=300):
    return [await Person(client, start + i, name).join() for i, name in enumerate(names)]


async def test_groups(client):
    a, b, c, d, e = await crowd(client, ["Аня", "Боря", "Вика", "Гоша", "Даша"])
    event = await add_event(hours=10, category="music")
    want = {"status": "looking", "group": True}
    first = await a.ok("POST", f"/events/{event}/attend", json=want)
    assert first["waiting"] is True and first["group"] is None
    await b.ok("POST", f"/events/{event}/attend", json=want)
    assert notifier.sent == [] or all("Компания собрана" not in s[1] for s in notifier.sent)
    third = await c.ok("POST", f"/events/{event}/attend", json=want)
    assert third["group"]["size"] == 3
    ready = [s for s in notifier.sent if "Компания собрана" in s[1]]
    assert len(ready) == 3 and {s[2] for s in ready} == {f"group-{third['group']['id']}"}
    group = third["group"]["id"]

    # A newcomer joins the existing company; the others hear about it.
    notifier.sent.clear()
    fourth = await d.ok("POST", f"/events/{event}/attend", json=want)
    assert fourth["group"]["id"] == group and fourth["group"]["size"] == 4
    assert sum("присоединяется" in s[1] for s in notifier.sent) == 3

    # Shared chat with an icebreaker; the others get the message.
    chat = await a.ok("GET", f"/groups/{group}")
    assert len(chat["others"]) == 3 and chat["icebreaker"]
    notifier.sent.clear()
    await a.ok("POST", f"/groups/{group}/messages", json={"text": "Привет всем! Встречаемся у входа?"})
    assert len(notifier.sent) == 3
    seen = await b.ok("GET", f"/groups/{group}")
    assert seen["messages"][0]["from"] == "Аня" and not seen["messages"][0]["mine"]
    assert (await b.ok("GET", "/groups"))["groups"][0]["last_from"] == "Аня"
    assert (await e.call("GET", f"/groups/{group}")).status_code == 404  # not a member

    # The event page shows the company; leaving drops the wish too.
    page = await a.ok("GET", f"/events/{event}")
    assert page["group"]["size"] == 4
    await d.ok("POST", f"/groups/{group}/leave")
    page = await d.ok("GET", f"/events/{event}")
    assert page["group"] is None and page["waiting"] is False
    # «Иду» without company also leaves the group.
    await c.ok("POST", f"/events/{event}/attend", json={"status": "going"})
    assert len((await a.ok("GET", f"/groups/{group}"))["others"]) == 1


async def test_groups_respect_girls_only_and_blocks(client):
    people = await crowd(client, ["Ира", "Катя", "Лена", "Миша", "Нина", "Олег"])
    ira, katya, lena, misha, nina, oleg = people
    for person, gender in zip(people, "fffmfm"):
        await person.ok("PUT", "/me", json={"name": person.name, "age": 28, "gender": gender, "adult_ok": True})
    await oleg.ok("POST", f"/users/{nina.id}/report", json={"block": True})
    event = await add_event(hours=10)
    for girl in (ira, katya, lena):
        await girl.ok("POST", f"/events/{event}/attend", json={"status": "looking", "group": True, "girls_only": True})
    girls = (await ira.ok("GET", f"/events/{event}"))["group"]
    assert girls and {p["name"] for p in girls["others"]} == {"Катя", "Лена"}
    # Миша can't join the girls' company; with Нина and Олег (who blocked each other) no company of 3 is possible.
    for person in (misha, nina, oleg):
        await person.ok("POST", f"/events/{event}/attend", json={"status": "looking", "group": True})
    assert (await misha.ok("GET", f"/events/{event}"))["group"] is None
    assert (await misha.ok("GET", f"/events/{event}"))["waiting"] is True


async def test_pair_is_enough_close_to_start(client):
    from app.db import Session
    from app.groups import assemble_upcoming
    a, b = await crowd(client, ["Петя", "Рита"])
    event = await add_event(hours=3)
    for person in (a, b):
        await person.ok("POST", f"/events/{event}/attend", json={"status": "looking", "group": True})
    assert (await a.ok("GET", f"/events/{event}"))["group"]["size"] == 2
    late = await add_event(hours=0.5)
    assert (await a.call("POST", f"/events/{late}/attend", json={"status": "looking", "group": True})).status_code == 200
    async with Session() as session:
        assert await assemble_upcoming(session) == 0


async def visited(person, count, category="music"):
    """Marks `count` past events for a person (as if they went)."""
    for _ in range(count):
        event = await add_event(hours=-5, category=category)
        async with __import__("app.db", fromlist=["Session"]).Session() as session:
            from app.models import Attendance
            session.add(Attendance(user_id=person.id, event_id=event, status="going"))
            await session.commit()


async def test_captain(client):
    a, b, c = await crowd(client, ["Капитан", "Боря", "Вика"])
    assert (await a.call("PUT", "/me/settings", json={"captain_ok": True})).status_code == 400  # too early
    await visited(a, 3)
    info = await a.ok("GET", "/me/progress")
    assert info["captain"]["ready"] is True
    assert (await a.ok("PUT", "/me/settings", json={"captain_ok": True}))["captain_ok"] is True
    event = await add_event(hours=10)
    for person in (b, a, c):
        await person.ok("POST", f"/events/{event}/attend", json={"status": "looking", "group": True})
    page = await b.ok("GET", f"/events/{event}")
    assert page["group"]["captain_id"] == a.id
    ready = {s[0]: s[1] for s in notifier.sent if "Компания собрана" in s[1]}
    assert "Вы капитан" in ready[a.tg_id] and "Капитан компании — Капитан" in ready[b.tg_id]
    assert (await c.ok("GET", f"/groups/{page['group']['id']}"))["captain_id"] == a.id


async def test_friends_and_company_invite(client):
    a, b, c, d = await crowd(client, ["Аня", "Боря", "Вика", "Гоша"])
    link = (await a.ok("GET", "/friends"))["link"]
    code = link.split("fr_")[1]
    res = await b.ok("POST", "/friends/accept", json={"code": code})
    assert res["new"] is True and res["friend"]["name"] == "Аня"
    assert any("теперь у вас в друзьях" in s[1] for s in notifier.sent if s[0] == a.tg_id)
    assert [f["name"] for f in (await a.ok("GET", "/friends"))["friends"]] == ["Боря"]
    # Where friends go: the afisha shows it.
    event = await add_event(hours=10)
    await b.ok("POST", f"/events/{event}/attend", json={"status": "going"})
    assert (await a.ok("GET", "/events", params={"day": "week"}))["events"][0]["friends"] == 1
    assert [f["name"] for f in (await a.ok("GET", f"/events/{event}"))["friends"]] == ["Боря"]
    assert (await a.ok("GET", "/friends"))["going"][0]["event"]["id"] == event
    # Invite a friend straight into my company.
    for person in (a, c, d):
        await person.ok("POST", f"/events/{event}/attend", json={"status": "looking", "group": True})
    group = (await a.ok("GET", f"/events/{event}"))["group"]["id"]
    invite = (await a.ok("GET", f"/groups/{group}/invite"))["link"]
    assert invite.endswith(f"_g{group}")
    joined = await b.ok("POST", "/friends/accept", json={"code": code, "group": group})
    assert joined["group_id"] == group and joined["new"] is False
    assert len((await a.ok("GET", f"/groups/{group}"))["others"]) == 3
    # Achievement for the friend.
    assert any(a_["code"] == "friends" and a_["level"] == 1 for a_ in (await a.ok("GET", "/me/progress"))["achievements"])


async def test_achievements(client):
    from app.db import Session
    from app.progress import award_recent
    (a,) = await crowd(client, ["Аня"])
    await visited(a, 5, category="party")
    async with Session() as session:
        assert await award_recent(session) == 3  # events 1 and 5, night 3
    note = [s for s in notifier.sent if s[0] == a.tg_id and "Новое достижение" in s[1]]
    assert len(note) == 1 and "Завсегдатай" in note[0][1] and note[0][2] == "achievements"
    async with Session() as session:
        assert await award_recent(session) == 0  # only once
    board = {x["code"]: x for x in (await a.ok("GET", "/me/progress"))["achievements"]}
    assert board["events"]["level"] == 2 and board["events"]["next"] == 15 and board["night"]["level"] == 1
    picture = await client.get("/ach/events-2.jpg")
    assert picture.status_code == 200 and picture.headers["content-type"] == "image/jpeg"
    assert (await client.get("/ach/events-9.jpg")).status_code == 404


async def test_group_deal(client):
    a, b, c = await crowd(client, ["Аня", "Боря", "Вика"])
    admin = await Person(client, 1, "Админ").join()
    event = await add_event(hours=10)
    await admin.ok("PUT", f"/org/events/{event}/deal", json={"group_deal": "−20% для компании", "group_promo": "KTO20"})
    assert (await a.ok("GET", "/events", params={"day": "week"}))["events"][0]["group_deal"] == "−20% для компании"
    assert (await a.call("PUT", f"/org/events/{event}/deal", json={"group_deal": "x"})).status_code == 403
    for person in (a, b, c):
        await person.ok("POST", f"/events/{event}/attend", json={"status": "looking", "group": True})
    assert any("Скидка для компании" in s[1] for s in notifier.sent)
    group = (await a.ok("GET", f"/events/{event}"))["group"]["id"]
    chat = await a.ok("GET", f"/groups/{group}")
    assert chat["promo"] == "KTO20" and chat["deal"] == "−20% для компании"


async def test_invite_link_page(client):
    a, b = await crowd(client, ["Аня", "Боря"])
    event = await add_event(hours=10, title="Квиз в Депо")
    links = await a.ok("GET", f"/events/{event}/invite")
    code = links["link"].split("fr_")[1].split("_")[0]
    assert links["link"].endswith(f"_e{event}") and links["web_link"].endswith(f"/i/{code}?e={event}")
    iphone = await client.get(f"/i/{code}", params={"e": event}, headers={"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0)"})
    assert iphone.status_code == 302 and iphone.headers["location"].startswith("https://apps.apple.com/") \
        and iphone.headers["location"].endswith("ct=invite")
    android = await client.get(f"/i/{code}", params={"e": event}, headers={"user-agent": "Mozilla/5.0 (Linux; Android 14)"})
    assert android.status_code == 302 and android.headers["location"] == f"/?fr={code}&go=event-{event}"
    landing = await client.get(f"/i/{code}", params={"e": event}, headers={"user-agent": "TelegramBot (like TwitterBot)"})
    assert landing.status_code == 200 and "Аня зовёт тебя" in landing.text and "Квиз в Депо" in landing.text
    assert f"startapp=fr_{code}_e{event}" in landing.text and "apps.apple.com" in landing.text
    general = (await a.ok("GET", "/friends"))["web_link"]
    assert general.endswith(f"/i/{code}")
    assert (await b.ok("POST", "/friends/accept", json={"code": code}))["new"] is True
