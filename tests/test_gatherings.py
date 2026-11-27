from datetime import datetime, timedelta

import pytest

from app.notify import notifier
from tests.conftest import Person


def soon(hours=30):
    return (datetime.now() + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M")


@pytest.mark.asyncio
async def test_gathering_flow(client, people):
    vera, anya, kirill = people
    body = {"title": "Квест «Тайна маяка»", "category": "quest", "starts_at": soon(), "place": "Клаустрофобия",
            "address": "Покровка, 1", "need": 1, "price": "≈1 500 ₽ с человека"}
    created = await vera.ok("POST", "/gatherings", json=body)
    event_id = created["id"]
    assert created["gathering"] and created["category"] == "quest"
    assert any("Новый сбор" in text for _, text, _go in notifier.sent)  # admin (tg 1) is told

    # In the afisha, under «Сборы» and under its own category.
    listed = await anya.ok("GET", "/events?day=week&category=sbory")
    assert [e["id"] for e in listed["events"]] == [event_id]
    detail = await anya.ok("GET", f"/events/{event_id}")
    assert detail["gathering"]["host"]["name"] == "Вера" and detail["gathering"]["left"] == 1

    # Anya joins: straight into Vera's company with a chat.
    joined = await anya.ok("POST", f"/events/{event_id}/attend", json={"status": "looking", "group": True})
    assert joined["group"] and joined["group"]["others"][0]["name"] == "Вера"
    # The gathering is full now: Kirill waits, no second company appears.
    third = await kirill.ok("POST", f"/events/{event_id}/attend", json={"status": "looking", "group": True})
    assert third["group"] is None and third["waiting"]
    assert (await anya.ok("GET", f"/events/{event_id}"))["gathering"]["left"] == 0

    # Vera calls it off: it leaves the afisha, Anya hears about it.
    await vera.ok("POST", f"/gatherings/{event_id}/cancel")
    assert not (await anya.ok("GET", "/events?day=week&category=sbory"))["events"]
    assert any("отменён" in text for _, text, _go in notifier.sent)


@pytest.mark.asyncio
async def test_gathering_limits(client, people):
    vera = people[0]
    base = {"title": "Падел 2×2", "category": "sport", "place": "Лужники", "need": 3}
    too_soon = await vera.call("POST", "/gatherings", json={**base, "starts_at": soon(1)})
    assert too_soon.status_code == 400
    for _ in range(3):
        await vera.ok("POST", "/gatherings", json={**base, "starts_at": soon()})
    assert (await vera.call("POST", "/gatherings", json={**base, "starts_at": soon()})).status_code == 429
    guest = Person(client, 999, "Гость")
    assert (await guest.call("POST", "/gatherings", json={**base, "starts_at": soon()})).status_code == 403
