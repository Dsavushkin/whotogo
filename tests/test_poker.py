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


MAFIA_PAGE = """<title>Мафия в Москве</title><ul class="event-list"><li class="top" itemscope itemtype="https://schema.org/Event" > <link itemprop="url" href="https://findmafia.ru/event/moskovskaya-mafiya/19928-gorodskaya-mafiya-novichki"> <meta itemprop="startDate" content="2026-11-27T18:50:00+03:00"> <meta itemprop="description" content="Игра"> <div class="info"> <span class = "org">Московская Мафия</span> <h2 class="title"><span itemprop="name">Городская Мафия (Новички)</span></h2> <p class="desc"><span itemprop="location" itemscope itemtype="https://schema.org/Place" class="info-text"> <span itemprop="name"><a class="location-href" href='https://findmafia.ru/location/x' target="_blank">Mos-lounge</a></span> <span itemprop="address" itemscope itemtype="https://schema.org/PostalAddress"> <meta itemprop="streetAddress" content="Комсомольский пр-кт, д 28 "> </span> </span> </p> <p itemprop="offers" itemscope itemtype="https://schema.org/Offer" class="desc"><meta itemprop="priceCurrency" content="RUB"> <meta itemprop="price" content="1200"> <span class="info-text"> 1200 руб./чел.</span></p></div></li>
<li class="top" itemscope itemtype="https://schema.org/Event" > <link itemprop="url" href="https://findmafia.ru/event/x/19929-detskaya"> <meta itemprop="startDate" content="2026-11-28T12:00:00+03:00"><span class = "org">X</span><h2 class="title"><span itemprop="name">Детская мафия</span></h2></li></ul>"""


def test_findmafia_schedule():
    from app.sources import findmafia
    events = findmafia.parse(MAFIA_PAGE, now=datetime(2026, 11, 27, 7, 0))
    assert len(events) == 1
    event = events[0]
    assert event["title"] == "Городская Мафия (Новички) · Московская Мафия" and event["category"] == "mafia"
    assert event["starts_at"] == datetime(2026, 11, 27, 15, 50) and event["source_id"] == "19928"
    assert event["place"] == "Mos-lounge" and event["address"] == "Москва, Комсомольский пр-кт, д 28"
    assert event["price"] == "1 200 ₽ с человека"
    assert findmafia.parse(MAFIA_PAGE, now=datetime(2026, 11, 28, 7, 0)) == []
