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


# ---------- notifications ----------

def match_together(other, event) -> str:
    return (f"🤝 <b>Есть пара!</b>\n{who(other)} тоже хочет пойти с вами на «{q(event.title)}» "
            f"({when(event.starts_at)}).\n\nНапишите первым и договоритесь, где встретиться.")


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
            "Отметьте, с кем хочется увидеться ещё. Человек узнает об этом, только если отметит вас в ответ.")


def day_reminder(event, partners: list, looking: int, status: str) -> str:
    start = local(event.starts_at)
    place = ", ".join(x for x in (event.place, event.address) if x)
    head = f"⏰ <b>Сегодня в {start:%H:%M}</b> — «{q(event.title)}»"
    if place:
        head += f"\n📍 {q(place)}"
    if partners:
        names = ", ".join(q(p.name or "Гость") for p in partners)
        return f"{head}\n\nИдёте вместе с: {names}. Договоритесь, где встретиться."
    if status == "looking" and looking:
        return f"{head}\n\nКомпанию ищут ещё {looking} — посмотрите, с кем можно пойти."
    if status == "looking":
        return f"{head}\n\nПока вы первый, кто ищет компанию. Позовите друга — или загляните ближе к вечеру."
    return head + "\n\nХорошего вечера!"


def weekend_nudge(title: str, picks: list) -> str:
    text = picks_text(title, picks) if picks else f"<b>{q(title)}</b>"
    return (text + "\n\nОтметьте «Ищу компанию» — и найдётся, с кем пойти."
            "\n<i>Не присылать такие напоминания: /quiet</i>")
