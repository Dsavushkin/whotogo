import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from app.api import day_bounds
from app.auth import verify_init_data
from app.jobs import send_after_prompts
from app.notify import notifier
from app.sources.timepad import price_text, to_event
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
    assert [s[0] for s in notifier.sent] == [vera.tg_id] and "Идёте вместе" in notifier.sent[0][1]
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
    quiet = await add_event(hours=1, title="Тихий вечер")
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
    assert (start, end) == (datetime(2026, 11, 20, 14, 0), datetime(2026, 11, 20, 21, 0))
    assert day_bounds("tomorrow", friday_evening) == (datetime(2026, 11, 20, 21, 0), datetime(2026, 11, 21, 21, 0))
    assert day_bounds("weekend", friday_evening) == (datetime(2026, 11, 20, 21, 0), datetime(2026, 11, 22, 21, 0))
    sunday = datetime(2026, 11, 22, 9, 0, tzinfo=timezone.utc)
    assert day_bounds("weekend", sunday) == (datetime(2026, 11, 22, 7, 0), datetime(2026, 11, 22, 21, 0))


def test_timepad_mapping():
    item = {"id": 777, "name": "Винил-вечер &amp; джаз", "starts_at": "2026-11-21T20:00:00+0300",
            "ends_at": "2026-11-21T23:00:00+0300", "url": "https://x.timepad.ru/event/777/",
            "description_short": "<p>Приносите   пластинки</p>", "categories": [{"id": 1, "name": "Концерты"}],
            "location": {"city": "Москва", "address": "Бауманская, 11"}, "organization": {"name": "Лофт"},
            "registration_data": {"price_min": 500, "price_max": 1500}, "age_limit": "18"}
    event = to_event(item)
    assert event["title"] == "Винил-вечер & джаз" and event["category"] == "music"
    assert event["starts_at"] == datetime(2026, 11, 21, 17, 0) and event["price"] == "от 500 ₽"
    assert event["description"] == "Приносите пластинки" and event["source_id"] == "777"
    assert to_event({**item, "categories": [{"name": "Для детей"}]}) is None
    assert to_event({**item, "location": {"city": "Без города"}}) is None
    assert to_event({**item, "name": "Вебинар по продажам"}) is None
    assert price_text({"price_min": 0, "price_max": 0}) == "Бесплатно" and price_text(None) == ""
    assert price_text({"price_min": 1200, "price_max": 1200}) == "1 200 ₽"
