"""Telegram bot @whotogo: entry point to the Mini App, notifications and admin commands."""
import logging
from typing import Optional

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import MenuButtonWebApp, Message, WebAppInfo
from sqlalchemy import func, select

from .auth import issue_login_code
from .config import settings
from .db import Session
from .importer import run_import
from .models import Attendance, Event, Match, Report, User, utcnow
from .notify import notifier, open_markup

log = logging.getLogger("whotogo.bot")
router = Router()

WELCOME = (
    "Кто идёт — афиша Москвы и компания на вечер.\n\n"
    "Выберите событие, отметьте «Ищу компанию» и посмотрите, кто ещё идёт. "
    "Чат откроется, только если вы оба нажали «Пойдём вместе». Отказ никто не увидит."
)


def is_admin(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id in settings.admin_ids)


@router.message(CommandStart())
async def start(message: Message, command: CommandObject):
    go = (command.args or "").strip()[:40]
    markup = open_markup(go, "Открыть афишу")
    text = WELCOME if markup else WELCOME + "\n\nПриложение скоро откроется: адрес ещё настраивается."
    await message.answer(text, reply_markup=markup)


@router.message(Command("id"))
async def my_id(message: Message):
    await message.answer(f"Ваш Telegram ID: {message.from_user.id}")


@router.message(Command("login"))
async def login(message: Message):
    """Code for signing in to the app outside Telegram."""
    tg = message.from_user
    async with Session() as session:
        user = (await session.execute(select(User).where(User.tg_id == tg.id))).scalar_one_or_none()
        if user is None:
            user = User(tg_id=tg.id, name=(tg.first_name or "")[:64], username=(tg.username or "")[:64],
                        city=settings.city)
            session.add(user)
            await session.commit()
        if user.is_banned:
            return
        code = await issue_login_code(session, user)
    await message.answer(f"Код для входа в приложение: {code}\nДействует 10 минут. Никому его не сообщайте.")


@router.message(Command("help"))
async def help_(message: Message):
    text = "Откройте афишу кнопкой ниже. Вопросы и жалобы можно написать прямо сюда."
    if is_admin(message):
        text += ("\n\nКоманды администратора:\n/stats — цифры\n/import — обновить афишу\n"
                 "/organizer <tg id> — дать права организатора\n/ban <id> и /unban <id> — блокировка\n"
                 "/hide <id события> — скрыть событие\n/reports — последние жалобы")
    await message.answer(text, reply_markup=open_markup("", "Открыть афишу"))


@router.message(Command("stats"))
async def stats(message: Message):
    if not is_admin(message):
        return
    async with Session() as session:
        count = lambda model, *where: session.scalar(select(func.count()).select_from(model).where(*where))
        users = await count(User)
        ready = await count(User, User.adult_ok)
        events = await count(Event, Event.starts_at >= utcnow(), Event.published)
        looking = await count(Attendance, Attendance.status == "looking")
        marks = await count(Attendance)
        pairs = await count(Match)
    await message.answer(f"Пользователей: {users} (с профилем: {ready})\nБудущих событий: {events}\n"
                         f"Отметок «иду»: {marks}, из них ищут компанию: {looking}\nВзаимных пар: {pairs}")


@router.message(Command("import"))
async def import_(message: Message):
    if not is_admin(message):
        return
    await message.answer("Обновляю афишу…")
    result = await run_import()
    if "error" in result:
        await message.answer(f"Не получилось: {result['error']}")
    else:
        await message.answer(f"Готово. Подходящих событий: {result['seen']}, новых: {result['added']}, "
                             f"обновлено: {result['updated']}")


async def _find_user(session, arg: str) -> Optional[User]:
    arg = arg.strip().lstrip("@")
    if arg.isdigit():
        user = (await session.execute(select(User).where(User.tg_id == int(arg)))).scalar_one_or_none()
        return user or await session.get(User, int(arg))
    return (await session.execute(select(User).where(func.lower(User.username) == arg.lower()))).scalar_one_or_none()


async def _set_flag(message: Message, command: CommandObject, field: str, value: bool, done: str):
    if not is_admin(message):
        return
    async with Session() as session:
        user = await _find_user(session, command.args or "")
        if user is None:
            await message.answer("Не нашёл такого пользователя. Он должен хотя бы раз открыть приложение.")
            return
        setattr(user, field, value)
        await session.commit()
    await message.answer(f"{user.name or user.tg_id}: {done}")
    return user


@router.message(Command("organizer"))
async def organizer(message: Message, command: CommandObject):
    user = await _set_flag(message, command, "is_organizer", True, "теперь организатор")
    if user:
        await notifier.send(user.tg_id, "Вам открыт кабинет организатора: Профиль → Мои события.", "org")


@router.message(Command("ban"))
async def ban(message: Message, command: CommandObject):
    await _set_flag(message, command, "is_banned", True, "заблокирован")


@router.message(Command("unban"))
async def unban(message: Message, command: CommandObject):
    await _set_flag(message, command, "is_banned", False, "разблокирован")


@router.message(Command("hide"))
async def hide(message: Message, command: CommandObject):
    if not is_admin(message):
        return
    arg = (command.args or "").strip()
    async with Session() as session:
        event = await session.get(Event, int(arg)) if arg.isdigit() else None
        if event is None:
            await message.answer("Укажите номер события: /hide 123")
            return
        event.published = False
        await session.commit()
    await message.answer(f"Скрыто: {event.title}")


@router.message(Command("reports"))
async def reports(message: Message):
    if not is_admin(message):
        return
    async with Session() as session:
        rows = (await session.execute(select(Report).order_by(Report.id.desc()).limit(10))).scalars().all()
    lines = [f"#{r.id}: на id {r.target_id} от id {r.reporter_id} — {r.reason[:200]}" for r in rows]
    await message.answer("\n".join(lines) or "Жалоб нет.")


@router.message()
async def anything(message: Message):
    """Free text goes to the admins as a support request."""
    if message.text and not is_admin(message):
        for admin in settings.admin_ids:
            who = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
            await notifier.send(admin, f"Сообщение от {who} (tg {message.from_user.id}):\n{message.text[:1500]}")
        await message.answer("Спасибо, передал команде. Ответим здесь же.",
                             reply_markup=open_markup("", "Открыть афишу"))


async def run_bot() -> None:
    bot = Bot(settings.bot_token)
    notifier.bot = bot
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    try:
        if settings.webapp_url.startswith("https://"):
            await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
                text="Афиша", web_app=WebAppInfo(url=settings.webapp_url + "/")))
        await bot.delete_webhook(drop_pending_updates=False)
        await dispatcher.start_polling(bot, handle_signals=False)
    finally:
        notifier.bot = None
        await bot.session.close()
