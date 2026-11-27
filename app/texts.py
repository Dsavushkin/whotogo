"""Everything the bot says to people: profile texts, welcome and notifications.

Messages go out with parse_mode=HTML, so anything a person typed (names, titles, chat text)
passes through `q()` first.
"""
import html
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import settings

APP_STORE = "https://apps.apple.com/ru/app/id6837698613"
TZ = ZoneInfo(settings.timezone)
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября",
          "ноября", "декабря"]
WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

# ---------- bot profile (set automatically at start) ----------
NAME = "Кто идёт — компания на вечер"
SHORT_DESCRIPTION = "Афиша Москвы, где видно, кто ещё идёт. Найдите компанию на концерт, квиз или выставку."
DESCRIPTION = (
    "Кто идёт — афиша необычных событий Москвы и компания на вечер.\n\n"
    "🎟 Концерты, вечеринки, квизы, лекции и выставки — каждый день новые\n"
    "🙋 Отметьте «Ищу компанию» и посмотрите, кто ещё идёт\n"
    "🤝 Чат откроется, только если вы оба нажали «Пойдём вместе». Отказ никто не увидит\n"
    "🔔 Напомню о событии и подскажу, куда сходить на выходных\n\n"
    "Нажмите «Старт», чтобы открыть афишу."
)
COMMANDS = [
    ("start", "Открыть афишу"),
    ("today", "Куда сходить сегодня"),
    ("weekend", "Куда сходить на выходных"),
    ("login", "Код для входа в приложение"),
    ("remind", "Включить напоминания"),
    ("quiet", "Выключить напоминания"),
    ("help", "Помощь и связь с командой"),
]


def q(text) -> str:
    return html.escape(str(text or ""), quote=False)


def local(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc).astimezone(TZ)


def when(dt: datetime, now: datetime | None = None) -> str:
    """«сегодня в 19:00», «завтра в 19:00» or «сб, 29 ноября, 19:00»."""
    start = local(dt)
    today = (now or datetime.now(timezone.utc)).astimezone(TZ).date()
    if start.date() == today:
        return f"сегодня в {start:%H:%M}"
    if start.date() == today + timedelta(days=1):
        return f"завтра в {start:%H:%M}"
    return f"{WEEKDAYS[start.weekday()]}, {start.day} {MONTHS[start.month - 1]}, {start:%H:%M}"


def who(user) -> str:
    return q(user.name or "Гость") + (f", {user.age}" if getattr(user, "age", None) else "")


# ---------- conversation ----------
WELCOME = (
    "<b>Привет! Это «Кто идёт»</b> — афиша Москвы, где видно, кто ещё идёт.\n\n"
    "Как это работает:\n"
    "1. Выберите событие в афише\n"
    "2. Нажмите «Ищу компанию»\n"
    "3. Отметьте тех, с кем хотели бы пойти. Если это взаимно — откроется чат\n\n"
    "Отказ никто не увидит. Я напишу, когда найдётся пара, и напомню о событии в день встречи."
)
WELCOME_NO_APP = "\n\nАфиша скоро откроется: адрес сайта ещё настраивается."
HELP = (
    "<b>Что я умею</b>\n"
    "/today — куда сходить сегодня\n"
    "/weekend — куда сходить на выходных\n"
    "/login — код для входа в приложение на iPhone или на сайте\n"
    "/quiet и /remind — выключить и включить напоминания перед выходными\n\n"
    "Вопрос, идея или жалоба? Напишите прямо сюда — передам команде, ответим в этом чате."
)
SUPPORT_THANKS = "Спасибо! Передал команде — ответим здесь же."
LOGIN_CODE = "Код для входа: <code>{code}</code>\nДействует 10 минут. Никому его не сообщайте."
NUDGES_OFF = "Хорошо, больше не буду напоминать перед выходными.\nВключить снова: /remind"
NUDGES_ON = "Готово! В четверг, пятницу и субботу подскажу, куда сходить, если на выходные ещё нет планов."
ORGANIZER_ON = ("<b>Вам открыт кабинет организатора</b>\n"
                "Добавляйте свои события и отмечайте гостей на входе: Профиль → Мои события.")
NOTHING_FOUND = "Пока ничего подходящего — загляните в афишу чуть позже: она обновляется каждые несколько часов."


AD_POST = (
    "Не с кем сходить на концерт, квиз или выставку? 🙋\n\n"
    "<b>«Кто идёт»</b> — афиша Москвы, где видно, кто ещё собирается на событие. Отмечаешь «Ищу компанию», "
    "смотришь, кто идёт, и жмёшь «Пойдём вместе». Чат откроется, только если это взаимно — отказ никто не увидит.\n\n"
    "🎟 Концерты, вечеринки, квизы, лекции, прогулки — каждый день\n"
    "⏰ Напомним в день события\n"
    "🆓 Бесплатно\n\n"
    "👉 <a href=\"https://t.me/{bot}?startapp=src_{source}\">Открыть афишу</a>"
)


def picks_text(title: str, picks: list) -> str:
    """Numbered list of events; buttons with the same numbers open each one."""
    lines = [f"<b>{q(title)}</b>", ""]
    for n, (event, going, looking) in enumerate(picks, 1):
        extra = f" · 🙋 {looking} ищут компанию" if looking else (f" · идут {going}" if going else "")
        place = f", {q(event.place)}" if event.place else ""
        lines.append(f"{n}. <b>{q(event.title)}</b>\n    {when(event.starts_at)}{place}{extra}")
    return "\n".join(lines)


def picks_buttons(picks: list) -> list:
    return [(f"{n}. {event.title}"[:60], f"event-{event.id}") for n, (event, _, _) in enumerate(picks, 1)]


# ---------- icebreakers: two questions to start the chat ----------

ICEBREAKERS = {
    "poker": ["Давно играешь или впервые за столом?", "Холдем — твоя игра или есть любимая другая?",
              "Встретимся у входа минут за 15 до регистрации?", "Кто последним вылетит — угощает остальных чаем?"],
    "mafia": ["Ты чаще мирный или мафия?", "Как ты вычисляешь, кто врёт?", "Первый раз играешь в клубе?",
              "Договоримся не сдавать друг друга в первую ночь? 😄"],
    "quest": ["Страшные квесты — да или нет?", "Ты решаешь головоломки или ищешь предметы?",
              "Как поделим стоимость — поровну?", "Где встречаемся перед началом?"],
    "quiz": ["Как назовём команду?", "В какой теме ты эксперт: кино, история, музыка?",
             "Ты капитан или тот, кто знает ответ на один вопрос, но точно?", "Играем на победу или ради веселья?"],
    "music": ["Какую песню ждёшь больше всего?", "Лучший концерт, на котором ты был?",
              "Что сейчас слушаешь по дороге?", "Танцуешь или стоишь у бара?"],
    "party": ["Под какую песню точно выйдешь танцевать?", "Ты больше «до утра» или «до метро»?",
              "Лучшая вечеринка в твоей жизни — где это было?", "Что пьёшь, чтобы взять тебе тоже?"],
    "food": ["Какое блюдо попробуешь первым?", "Лучшее место в Москве, где ты ел?",
             "Готовишь сам или только пробуешь?", "Сладкое или острое?"],
    "games": ["Ты играешь на победу или ради веселья?", "Любимая настолка или квиз?",
              "В какой теме ты эксперт?", "Как назовём команду?"],
    "art": ["Какая выставка последней зацепила?", "Ты читаешь подписи к картинам или просто смотришь?",
            "Любимый художник или музей?", "Куда пойдём после — кофе или прогулка?"],
    "theater": ["Последний спектакль, который запомнился?", "Ты читал пьесу заранее?",
                "Партер или балкон?", "Обсудим в антракте или после?"],
    "cinema": ["Последний фильм, который зацепил?", "Попкорн сладкий или солёный?",
               "Какой фильм пересматриваешь много раз?", "Ты остаёшься на титры?"],
    "talk": ["Что хочешь узнать на этой лекции?", "О чём ты мог бы прочитать лекцию сам?",
             "Последняя книга или подкаст, который понравился?", "Задашь вопрос лектору?"],
    "sport": ["За кого болеешь или чем занимаешься?", "Самый крутой матч, который ты видел?",
              "Утренние тренировки — это про тебя?", "Чем отметим победу?"],
    "walk": ["Любимое место в Москве для прогулок?", "Где выпьем кофе по пути?",
             "Ты больше город или парк?", "Какой район хочешь открыть?"],
}
ICEBREAKERS_ANY = ["Что тебя зацепило в этом событии?", "Как обычно проводишь выходные?",
                   "Куда в Москве ты бы сводил друга, который приехал впервые?", "Где встретимся — у входа?"]


def icebreaker_questions(event, seed: int = 0) -> list[str]:
    """Two questions picked by the event's category; `seed` (the chat id) keeps the pair stable."""
    pool = ICEBREAKERS.get(getattr(event, "category", ""), ICEBREAKERS_ANY)
    first = seed % len(pool)
    return [pool[first], pool[(first + 1) % len(pool)]]


def icebreaker_plain(event, seed: int = 0, group: bool = False) -> str:
    first, second = icebreaker_questions(event, seed)
    return f"Вы {'все' if group else 'оба'} идёте на «{event.title}». Чтобы начать разговор:\n— {first}\n— {second}"


# ---------- notifications ----------

def match_together(other, event, seed: int = 0) -> str:
    first, _ = icebreaker_questions(event, seed)
    return (f"🤝 <b>Есть с кем пойти!</b>\n{who(other)} тоже хочет пойти с вами на «{q(event.title)}» "
            f"({when(event.starts_at)}).\n\nНапишите первым и договоритесь, где встретиться.\n"
            f"<i>Можно начать с вопроса: {q(first)}</i>")


def names_list(users) -> str:
    names = [q(u.name or "Гость") for u in users]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " и " + names[-1]


def group_ready(others, event, seed: int = 0, captain=None, me_id: int = 0) -> str:
    first, _ = icebreaker_questions(event, seed)
    total = len(others) + 1
    return (f"👥 <b>Компания собрана!</b>\nНа «{q(event.title)}» ({when(event.starts_at)}) вас {total}: "
            f"вы, {names_list(others)}.\n\nПоздоровайтесь в общем чате и договоритесь, где встретиться.\n"
            f"<i>Можно начать с вопроса: {q(first)}</i>{captain_line(captain, me_id)}{deal_line(event)}")


def captain_line(captain, me_id: int) -> str:
    if captain is None:
        return ""
    if captain.id == me_id:
        return ("\n\n⭐ <b>Вы капитан этой компании.</b> Предложите место встречи, встретьте всех у входа "
                "и познакомьте друг с другом — дальше всё пойдёт само.")
    return f"\n\n⭐ Капитан компании — {q(captain.name or 'Гость')}: опытный участник, встретит всех у входа."


def deal_line(event) -> str:
    if not getattr(event, "group_deal", ""):
        return ""
    text = f"\n\n🎟 <b>Скидка для компании:</b> {q(event.group_deal)}"
    if getattr(event, "group_promo", ""):
        text += f". Промокод — в чате компании"
    return text


def achievement(kind, level: int, value: int, fresh: int = 1) -> str:
    title = kind.titles[level - 1]
    text = f"🏆 <b>Новое достижение: {kind.emoji} {q(title)}</b>\nУ вас уже {value} {kind.name}."
    if level < len(kind.levels):
        text += f"\nСледующий уровень — «{q(kind.titles[level])}» за {kind.levels[level]}."
    if fresh > 1:
        text += f"\n\nВсего открыто сразу: {fresh}. Загляните в профиль."
    return text


def new_friend(friend) -> str:
    return f"🤝 <b>{q(friend.name or 'Гость')}</b> теперь у вас в друзьях. Вы будете видеть, куда друг друга идёте."


def group_joined(newcomer, event) -> str:
    return f"👋 К вашей компании на «{q(event.title)}» присоединяется {who(newcomer)}. Поздоровайтесь!"


def group_message(sender, text: str, event) -> str:
    text = text if len(text) <= 300 else text[:299] + "…"
    return f"👥 <b>{q(sender.name or 'Гость')}</b> · {q(event.title)}\n{q(text)}"


def match_again(other, event) -> str:
    return (f"✨ <b>Это взаимно</b>\n{who(other)} тоже хочет увидеться ещё после «{q(event.title)}». "
            "Чат открыт — напишите первым.")


def chat_message(sender, text: str) -> str:
    text = text if len(text) <= 300 else text[:299] + "…"
    return f"💬 <b>{q(sender.name or 'Гость')}</b>\n{q(text)}"


def new_companion(other, event) -> str:
    return (f"🙋 На «{q(event.title)}» ({when(event.starts_at)}) тоже ищут компанию: {who(other)}.\n"
            "Загляните — вдруг это ваш человек.")


def after_event(event) -> str:
    return (f"👋 Как прошло «{q(event.title)}»?\n"
            "Отметьте, кто из вашей компании пришёл, и с кем хочется увидеться ещё. "
            "Человек узнает о «увидимся ещё», только если отметит вас в ответ.")


def day_reminder(event, partners: list, looking: int, status: str) -> str:
    start = local(event.starts_at)
    place = ", ".join(x for x in (event.place, event.address) if x)
    head = f"⏰ <b>Сегодня в {start:%H:%M}</b> — «{q(event.title)}»"
    if place:
        head += f"\n📍 {q(place)}"
    if partners:
        names = ", ".join(q(p.name or "Гость") for p in partners)
        _, second = icebreaker_questions(event, event.id)
        return (f"{head}\n\nИдёте вместе с: {names}. Договоритесь, где встретиться."
                f"\n\n💡 <i>О чём поговорить: {q(second)}</i>")
    if status == "looking" and looking:
        return f"{head}\n\nКомпанию ищут ещё {looking} — посмотрите, с кем можно пойти."
    if status == "looking":
        return f"{head}\n\nПока вы первый, кто ищет компанию. Позовите друга — или загляните ближе к вечеру."
    return head + "\n\nХорошего вечера!"


def weekend_nudge(title: str, picks: list) -> str:
    text = picks_text(title, picks) if picks else f"<b>{q(title)}</b>"
    return (text + "\n\nОтметьте «Ищу компанию» — и найдётся, с кем пойти."
            "\n<i>Не присылать такие напоминания: /quiet</i>")


def new_gathering(host, event) -> str:
    """For admins: a participant created «Свой сбор». /hide removes it from the afisha."""
    return (f"🆕 Новый сбор #{event.id} от {who(host)}:\n<b>{q(event.title)}</b>, {when(event.starts_at)}, "
            f"{q(event.place)}\nнужно ещё {max(0, (event.capacity or 1) - 1)}\n\nСкрыть: /hide {event.id}")


def gathering_cancelled(event) -> str:
    return (f"😔 Сбор «{q(event.title)}» ({when(event.starts_at)}) отменён организатором.\n"
            "Загляните в афишу — там есть и другие сборы.")
