from datetime import datetime

from app.sources import pokersystem

NOW = datetime(2026, 11, 27, 7, 0)  # naive UTC
ADDRESS = "г. Москва, вн.тер. г. муниципальный округ Таганский, ул. Сергия Радонежского, д. 9, стр. 5"


def item(**over):
    base = {"id": 225, "title": "OMAHA 4-CARD", "status": "upcoming", "ts": 1795784400,  # 2026-11-27 13:00 UTC
            "price_entry": "500", "current_participants": "4", "max_participants": "54", "is_hidden": 0,
            "invite_only": 0, "address": ADDRESS, "location_title": "Ace Poker Club",
            "description": "ОМАХА • 4 КАРТЫ\nПоздняя регистрация до 18:10"}
    base.update(over)
    return base


def test_tournament_to_event():
    event = pokersystem.to_event(item(), "acepokerclub", now=NOW)
    assert event["category"] == "poker" and event["source_id"] == "acepokerclub-225"
    assert event["title"] == "OMAHA 4-CARD · AcePokerClub" and event["place"] == "AcePokerClub"
    assert event["starts_at"] == datetime(2026, 11, 27, 13, 0)
    assert event["price"] == "500 ₽ за участие"
    assert event["address"] == "г. Москва, ул. Сергия Радонежского, д. 9, стр. 5"
    assert event["url"] == "https://acepokerclub.pokersystem.ru/"
    assert "не на деньги" in event["description"]


def test_free_and_generic_titles():
    event = pokersystem.to_event(item(title="FREEROLL", price_entry=0), "acepokerclub", now=NOW)
    assert event["price"] == "Бесплатно" and event["title"].startswith("Покер: FREEROLL")


def test_skips_what_a_newcomer_cannot_join():
    skip = [item(ts=1785340800),                     # old «upcoming» left in July
            item(status="finished"), item(is_hidden=1), item(invite_only="1"),
            item(current_participants=54),            # full
            item(address="г Омск, ул Ленина, 1"),     # not Moscow
            item(ts=1795784400 + 40 * 86400)]         # too far ahead
    assert [pokersystem.to_event(x, "acepokerclub", now=NOW) for x in skip] == [None] * len(skip)


async def test_poker_seo_pages(client):
    from tests.conftest import add_event
    await add_event(hours=30, title="CLASSIC · Ace Poker Club", category="poker", place="Ace Poker Club")
    await add_event(hours=50, title="FREEROLL · Аурум", category="poker", place="Аурум")
    section = (await client.get("/afisha/poker")).text
    assert "FAQPage" in section and "ItemList" in section and "Спортивный покер" in section
    assert '/afisha/poker/ace-poker-club' in section and "noindex" not in section
    club = await client.get("/afisha/poker/ace-poker-club")
    assert club.status_code == 200 and "Ace Poker Club: расписание турниров по покеру" in club.text
    assert "Аурум" not in club.text.split("<main>")[1].split("<footer>")[0]
    assert (await client.get("/afisha/poker/nobody")).status_code == 404
    assert "/afisha/poker/aurum" in (await client.get("/sitemap.xml")).text


async def test_indexnow_key_file(client):
    from app import indexnow
    assert (await client.get(f"/{indexnow.KEY}.txt")).text == indexnow.KEY
    assert await indexnow.submit(["/afisha"]) == 0  # never pings from dev/tests
