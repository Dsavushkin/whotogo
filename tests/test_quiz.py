from app.api import category_keys
from app.sources.timepad import pick_category


def test_quiz_category_from_title():
    assert pick_category([], "Паб-квиз «Мозгобойня» в баре") == "quiz"
    assert pick_category(["Игры"], "Квиз по кино") == "quiz"
    assert pick_category(["Игры"], "Настольные игры в антикафе") == "games"


def test_old_games_filter_keeps_quizzes():
    assert category_keys("games") == ("games", "quiz")
    assert category_keys("quiz") == ("quiz",)
