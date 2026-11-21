"""Demo data for a local preview:  DEV=1 python -m app.seed"""
import asyncio
from datetime import timedelta

from sqlalchemy import select

from .db import Session, init_db
from .models import Attendance, Event, Like, User, utcnow

EVENTS = [
    ("Винил-вечер на крыше", "music", 3, "Лофт на Бауманской", "ул. Бауманская, 11", "1 200 ₽",
     "Диджей ставит пластинки из своей коллекции, гости приносят свои. Небольшой зал, длинный общий стол, "
     "можно прийти одному."),
    ("Ужин с незнакомцами, 8 мест", "food", 2, "Бистро «Сосед»", "Покровка, 20", "2 500 ₽",
     "Восемь человек за одним столом, сет от шефа и карточки с вопросами для разговора."),
    ("Настольные игры в антикафе", "games", 4, "Антикафе «Циферблат»", "Тверская, 12", "400 ₽ / час",
     "Ведущий объяснит правила и соберёт стол. Приходите без компании."),
    ("Квартирник: акустика и чай", "music", 26, "Квартира на Чистых", "Чистопрудный бульвар, 9", "800 ₽",
     "Двадцать гостей, две гитары и самовар."),
    ("Лекция «Как устроен джаз»", "talk", 29, "Библиотека им. Некрасова", "Бауманская, 58/25", "Бесплатно",
     "Час разговора и час живой музыки."),
    ("Забег в парке и кофе после", "sport", 50, "Парк Горького", "Крымский Вал, 9", "Бесплатно",
     "Пять километров в спокойном темпе, потом вместе идём пить кофе."),
    ("Вечер коротких знакомств", "dating", 74, "Бар «Стрелка»", "Берсеневская наб., 14", "1 500 ₽",
     "Двенадцать разговоров по пять минут и свободное общение после."),
    ("Киноклуб: немое кино с тапёром", "cinema", -20, "Кинотеатр «Иллюзион»", "Котельническая наб., 1/15", "600 ₽",
     "Показ с живым сопровождением на фортепиано и обсуждение."),
]
PEOPLE = [
    ("Аня", 27, "Иду первый раз, принесу пластинку. Хочу компанию из 2–3 человек.", ["джаз", "фотография", "настолки"]),
    ("Кирилл", 31, "Недавно переехал в Москву. Ищу, с кем ходить на концерты.", ["инди", "бег", "кино"]),
    ("Даша", 25, "Идём с подругой вдвоём, будем рады ещё паре человек за столом.", ["вино", "театр"]),
    ("Миша", 29, "Люблю настолки и долгие разговоры.", ["настолки", "велосипед"]),
    ("Лера", 26, "Могу показать лучшие кофейни рядом.", ["кофе", "йога"]),
    ("Тимур", 33, "Работаю рядом, зайду после офиса.", ["винил", "готовка"]),
]


async def seed() -> None:
    await init_db()
    async with Session() as session:
        if (await session.execute(select(Event.id).limit(1))).first():
            print("В базе уже есть события — ничего не добавляю.")
            return
        now = utcnow().replace(minute=0, second=0, microsecond=0)
        events = [Event(source="org", title=t, category=c, starts_at=now + timedelta(hours=h), place=p, address=a,
                        price=pr, description=d) for t, c, h, p, a, pr, d in EVENTS]
        people = [User(tg_id=900000 + i, name=n, age=age, bio=bio, interests=tags, adult_ok=True)
                  for i, (n, age, bio, tags) in enumerate(PEOPLE)]
        session.add_all(events + people)
        await session.flush()
        for ei, event in enumerate(events):
            for pi, person in enumerate(people):
                if (ei + pi) % 2 == 0 or ei in (0, 7):
                    session.add(Attendance(user_id=person.id, event_id=event.id, note=person.bio if ei == 0 else "",
                                           status="looking" if (pi + ei) % 3 != 2 else "going"))
        # Аня already wants to go to the first event with the first real visitor (user id will be next).
        session.add(Like(from_id=people[0].id, to_id=len(people) + 1, event_id=events[0].id, kind="together"))
        await session.commit()
    print("Готово: добавлены демо-события и люди.")


if __name__ == "__main__":
    asyncio.run(seed())
