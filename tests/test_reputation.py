from datetime import timedelta

from app.db import Session
from app.models import Attendance, Event, Group, GroupMember, utcnow
from tests.conftest import add_event


async def company(event_id, *persons):
    async with Session() as session:
        group = Group(event_id=event_id)
        session.add(group)
        await session.flush()
        for p in persons:
            session.add(GroupMember(group_id=group.id, user_id=p.id))
        await session.commit()


async def test_checkin_window(people):
    vera, anya, _ = people
    soon = await add_event(hours=0.5)
    later = await add_event(hours=5)
    assert (await vera.call("POST", f"/events/{soon}/checkin")).status_code == 403  # not going
    await vera.ok("POST", f"/events/{soon}/attend", json={"status": "going"})
    event = await vera.ok("GET", f"/events/{soon}")
    assert event["checkin_open"] and not event["checked_in"]
    assert (await vera.ok("POST", f"/events/{soon}/checkin"))["checked_in"]
    assert (await vera.ok("GET", f"/events/{soon}"))["checked_in"]
    await vera.ok("POST", f"/events/{later}/attend", json={"status": "going"})
    assert (await vera.call("POST", f"/events/{later}/checkin")).status_code == 400  # too early


async def test_reliability_and_profile(people):
    vera, anya, kirill = people
    past = await add_event(hours=-20, title="Квиз в пятницу", category="quiz")
    older = await add_event(hours=-50, title="Покерный турнир", category="poker")
    for person in people:
        for event_id in (past, older):
            await person.ok("POST", f"/events/{event_id}/attend", json={"status": "going"})
    await company(past, vera, anya, kirill)
    await company(older, vera, anya)

    assert (await vera.ok("GET", f"/events/{past}/presence"))["people"] and \
        {p["name"] for p in (await vera.ok("GET", f"/events/{past}/presence"))["people"]} == {"Аня", "Кирилл"}
    # Strangers cannot vote on someone they did not go with.
    await vera.ok("POST", f"/events/{older}/presence", json={"votes": {str(kirill.id): False}})
    await vera.ok("POST", f"/events/{past}/presence", json={"votes": {str(anya.id): True, str(kirill.id): False}})
    await vera.ok("POST", f"/events/{older}/presence", json={"votes": {str(anya.id): True}})

    profile = await vera.ok("GET", f"/users/{anya.id}")
    assert profile["reliability"]["label"] == "Пришёл 2 из 2" and not profile["reliability"]["reliable"]
    assert [h["title"] for h in profile["history"]] == ["Квиз в пятницу", "Покерный турнир"]
    assert profile["stats"]["events"] == 2 and profile["met"]
    assert (await vera.ok("GET", f"/users/{kirill.id}"))["reliability"]["label"] == "Пришёл 0 из 1"

    # Kirill hides his history; a later self check-in is not possible after the window, a friend's «пришёл» wins.
    await kirill.ok("PUT", "/me/settings", json={"show_history": False})
    hidden = await vera.ok("GET", f"/users/{kirill.id}")
    assert hidden["history"] == [] and hidden["history_hidden"]
    assert (await kirill.ok("GET", f"/users/{kirill.id}"))["history"]  # he still sees his own
    await anya.ok("POST", f"/events/{past}/presence", json={"votes": {str(kirill.id): True}})
    assert (await vera.ok("GET", f"/users/{kirill.id}"))["reliability"]["label"] == "Пришёл 1 из 1"

    # The people list shows the label too.
    soon = await add_event(hours=30)
    await anya.ok("POST", f"/events/{soon}/attend", json={"status": "looking"})
    listed = (await vera.ok("GET", f"/events/{soon}/people"))["people"][0]
    assert listed["reliability"]["label"] == "Пришёл 2 из 2"


async def test_profile_respects_blocks(people):
    vera, anya, _ = people
    assert (await vera.call("GET", "/users/999999")).status_code == 404
    await vera.ok("POST", f"/users/{anya.id}/report", json={"reason": "spam", "block": True})
    assert (await vera.call("GET", f"/users/{anya.id}")).status_code == 404
