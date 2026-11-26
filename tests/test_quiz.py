from app.api import category_keys
from app.sources.timepad import pick_category


def test_quiz_category_from_title():
    assert pick_category([], "Паб-квиз «Мозгобойня» в баре") == "quiz"
    assert pick_category(["Игры"], "Квиз по кино") == "quiz"
    assert pick_category(["Игры"], "Настольные игры в антикафе") == "games"


def test_old_games_filter_keeps_quizzes():
    assert category_keys("games") == ("games", "quiz")
    assert category_keys("quiz") == ("quiz",)


from datetime import date, datetime

from app.sources import mozgva, quizplease

MOZGVA_PAGE = """<html><head><title>Расписание квизов «Мозгва» в Москве</title></head><body>
<div class="itemGame-new2" id="item_9836"> <div class="time_wrap"> <span class="day">Пятница, </span>
<span class="date_m">27 ноября</span> </div> <div class="game-content game_9836 "> <div class="top-content">
<div class="name"> <div class="closing-warning-slot"> </div> <div class="game-title"> Зачетная 1000 День 2 </div> </div>
<div class="type_wrap"> <div class="type"> Классическая </div> <div class="desc_wrap"> <div class="open_description">Что это?</div>
<div class="close_description"> Закрыть</div> <div class="game_description"><p><strong>Длинный</strong> текст</p><div class="time">99:99</div></div>
</div> </div> <div class="place"> <a class="hide-mobile"> Коктейль Холл (Тверская 6с2) </a> <a class="mobile"> Коктейль Холл (Тверская 6с2) </a>
</div> <div class="time">19:00</div> <div class="price">1000 руб.</div> </div> <div class="bottom-content"> <div class="reg_btn">
<a class="roundBtn participateBtn"> Регистрация </a> </div> </div> </div> </div>
<div class="itemGame-new2" id="item_9837"><div class="time_wrap"><span class="date_m">28 ноября</span></div>
<div class="game-content"><div class="game-title">Детская Мозгва</div><div class="type">7-11 лет</div>
<div class="place"><a class="hide-mobile">Ketch Up (Покровка 10с2)</a></div><div class="time">14:30</div>
<div class="price">700 руб.</div><div class="reg_btn"><a class="roundBtn participateBtn">Регистрация</a></div></div></div>
<div class="itemGame-new2" id="item_9838"><div class="time_wrap"><span class="date_m">2 января</span></div>
<div class="game-content"><div class="game-title">Новички 640</div><div class="type">Для новичков</div>
<div class="place"><a class="hide-mobile">Ketch Up (Покровка 10с2)</a></div><div class="time">20:00</div>
<div class="price">1000 руб.</div><div class="reg_btn"><a class="roundBtn participateBtn">В резерв</a></div></div></div>
</body></html>"""


def test_mozgva_calendar():
    events = mozgva.parse(MOZGVA_PAGE, today=date(2026, 11, 26))
    assert len(events) == 1  # the children's game and the full one are skipped
    e = events[0]
    assert e["title"] == "Мозгва: Зачетная 1000 День 2" and e["category"] == "quiz"
    assert e["starts_at"] == datetime(2026, 11, 27, 16, 0)  # 19:00 Moscow
    assert e["place"] == "Коктейль Холл" and e["address"] == "Тверская 6с2, Москва"
    assert e["price"] == "1000 ₽ с человека" and e["source_id"] == "9836"


def test_mozgva_year_turn():
    assert mozgva.game_date("2 января", date(2026, 12, 20)) == date(2027, 1, 2)
    assert mozgva.game_date("30 ноября", date(2026, 11, 26)) == date(2026, 11, 30)


def test_quizplease_game():
    item = {"id": "01a1bf99", "title": "Квиз, плиз!", "date": "26.11.2026 19:00", "status": 0, "game_type": 0,
            "game_number": "1353", "quote": "Игра подойдёт всем.", "max_participants": 9, "current_price": "1000",
            "place": {"title": "Papa's Bar & Grill", "address": "ул. Никольская, 10"},
            "template": {"background_phone": "https://cdn.example/p.png"}}
    e = quizplease.to_event(item)
    assert e["title"] == "Квиз, плиз! #1353" and e["starts_at"] == datetime(2026, 11, 26, 16, 0)
    assert e["price"] == "1 000 ₽ с человека" and e["url"].endswith("/game/01a1bf99")
    assert quizplease.to_event({**item, "status": 1}) is None          # reserve only
    assert quizplease.to_event({**item, "game_type": 1}) is None       # online stream
    themed = quizplease.to_event({**item, "title": "[music party] 100 хитов"})
    assert themed["title"].startswith("Квиз, плиз! [music party]")
