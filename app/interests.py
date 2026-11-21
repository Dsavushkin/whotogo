"""Interests (and subcultures) → which events fit a person. Shared by the afisha, people lists and reminders."""
from typing import Iterable

# The list people pick from (apps and site show it in this order).
INTERESTS = [
    "музыка", "техно", "хип-хоп", "рок", "джаз", "кино", "театр", "стендап", "настолки", "игры", "бары", "еда",
    "вино", "прогулки", "путешествия", "спорт", "бег", "йога", "танцы", "скейт", "велосипед", "скалолазание",
    "искусство", "фотография", "книги", "наука", "языки", "аниме",
]

# interest → (event categories, words in the title or description)
RULES = {
    "музыка": ({"music"}, ("концерт", "музык", "dj", "диджей", "винил", "квартирник")),
    "техно": ({"party"}, ("техно", "techno", "рейв", "rave", "house", "электрон")),
    "хип-хоп": (set(), ("хип-хоп", "hip-hop", "hip hop", "рэп", "rap", "баттл")),
    "рок": (set(), ("рок", "rock", "панк", "punk", "метал", "metal", "гранж")),
    "джаз": (set(), ("джаз", "jazz", "блюз", "blues", "свинг")),
    "кино": ({"cinema"}, ("кино", "фильм", "показ", "кинопоказ")),
    "театр": ({"theater"}, ("спектакл", "театр", "постановк")),
    "стендап": (set(), ("стендап", "stand-up", "stand up", "комеди", "импров", "open mic", "открытый микрофон")),
    "настолки": (set(), ("настол", "мафи", "board game")),
    "игры": ({"games"}, ("игр", "квиз", "квест", "мафи")),
    "бары": ({"party"}, ("бар", "коктейл", "паб", "pub")),
    "еда": ({"food"}, ("гастро", "ужин", "кулинар", "бранч", "дегустац", "мастер-класс по", "кухн")),
    "вино": (set(), ("вин", "дегустац", "сомелье")),
    "прогулки": ({"walk"}, ("прогулк", "экскурс")),
    "путешествия": ({"walk"}, ("путешеств", "экскурс", "поход")),
    "спорт": ({"sport"}, ("спорт", "трениров", "фитнес", "футбол", "волейбол", "падел")),
    "бег": (set(), ("бег", "забег", "пробеж", "run")),
    "йога": (set(), ("йог", "медитац", "растяжк")),
    "танцы": (set(), ("танц", "сальса", "бачата", "хастл", "свинг", "dance")),
    "скейт": (set(), ("скейт", "skate", "лонгборд")),
    "велосипед": (set(), ("вело", "bike", "байк")),
    "скалолазание": (set(), ("скалолаз", "боулдеринг", "скалодром", "climbing")),
    "искусство": ({"art"}, ("выставк", "искусств", "галере", "музей", "живопис", "художник")),
    "фотография": (set(), ("фото", "photo")),
    "книги": ({"talk"}, ("книг", "литератур", "чтени", "поэз", "писател")),
    "наука": ({"talk"}, ("лекци", "наук", "научн", "астроном", "истори")),
    "языки": (set(), ("язык", "english", "разговорн", "speaking", "language")),
    "аниме": (set(), ("аниме", "anime", "косплей", "cosplay", "манга")),
}


def why(category: str, text: str, interests: Iterable[str]) -> list:
    """The person's interests this event fits, strongest first (word matches beat category matches)."""
    text = text.lower()
    strong, weak = [], []
    for interest in interests:
        cats, words = RULES.get(interest, (set(), ()))
        if any(w in text for w in words):
            strong.append(interest)
        elif category in cats:
            weak.append(interest)
    return strong + weak


def score(category: str, text: str, interests: Iterable[str]) -> int:
    text = text.lower()
    total = 0
    for interest in interests:
        cats, words = RULES.get(interest, (set(), ()))
        total += 2 if any(w in text for w in words) else (1 if category in cats else 0)
    return total
