"""Telegram bot @whotogo: entry point to the Mini App, notifications and admin commands."""
import asyncio
import logging
import re
from pathlib import Path
from typing import Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (BotCommand, CallbackQuery, ChatMemberUpdated, FSInputFile, InputProfilePhotoStatic,
                           MenuButtonWebApp, Message, WebAppInfo)
from sqlalchemy import func, select

from . import channel, texts
from .auth import issue_login_code
from .config import settings
from .db import Session
from .importer import run_import
from .models import Attendance, Event, Match, Report, User, utcnow
from .notify import NO_PREVIEW, markup, notifier, status

log = logging.getLogger("whotogo.bot")
router = Router()
AVATAR = Path(__file__).resolve().parent.parent / "web" / "brand" / "bot-avatar.jpg"
SUPPORT_TAG = re.compile(r"\(tg (\d+)\)")


async def reply(message: Message, text: str, buttons: Optional[list] = None):
    await message.answer(text, parse_mode="HTML", reply_markup=markup(buttons) if buttons else None,
                         link_preview_options=NO_PREVIEW)


def start_buttons() -> list:
    return [("Открыть афишу", ""), ("Куда сходить сегодня", "cb:today"), ("Приложение для iPhone", texts.APP_STORE)]


def is_admin(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id in settings.admin_ids)


@router.message(CommandStart())
async def start(message: Message, command: CommandObject):
    go = (command.args or "").strip()[:40]
    if go == "login":  # opened from the iPhone app: send the sign-in code right away
        return await login(message)
    if go:  # a link to a particular screen: open it straight away
        return await reply(message, "Открываю 👇", [("Открыть", go)])
    has_app = settings.webapp_url.startswith("https://")
    await reply(message, texts.WELCOME + ("" if has_app else texts.WELCOME_NO_APP), start_buttons())


async def picks_for(day: str) -> tuple[str, list]:
    from .api import day_bounds
    from .jobs import pick_events
    start, end = day_bounds(day)
    async with Session() as session:
        picks = await pick_events(session, start, end, 5)
    title = {"today": "Куда сходить сегодня", "weekend": "Куда сходить на выходных"}[day]
    return title, picks


async def send_picks(message: Message, day: str) -> None:
    title, picks = await picks_for(day)
    if not picks:
        return await reply(message, texts.NOTHING_FOUND, [("Открыть афишу", "")])
    await reply(message, texts.picks_text(title, picks) + "\n\nОткройте событие и отметьте «Ищу компанию».",
                texts.picks_buttons(picks) + [("Вся афиша", "")])


@router.message(Command("today"))
async def today(message: Message):
    await send_picks(message, "today")


@router.message(Command("weekend"))
async def weekend(message: Message):
    await send_picks(message, "weekend")


@router.callback_query(F.data.in_({"today", "weekend"}))
async def picks_button(callback: CallbackQuery):
    await callback.answer()
    await send_picks(callback.message, callback.data)


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
    await reply(message, texts.LOGIN_CODE.format(code=code))


async def _set_nudges(message: Message, value: bool) -> None:
    async with Session() as session:
        user = (await session.execute(select(User).where(User.tg_id == message.from_user.id))).scalar_one_or_none()
        if user:
            user.nudges = value
            await session.commit()
    await reply(message, texts.NUDGES_ON if value else texts.NUDGES_OFF)


@router.message(Command("quiet"))
async def quiet(message: Message):
    await _set_nudges(message, False)


@router.message(Command("remind"))
async def remind(message: Message):
    await _set_nudges(message, True)


@router.message(Command("help"))
async def help_(message: Message):
    text = texts.HELP
    if is_admin(message):
        text += ("\n\n<b>Для администратора</b>\n/stats — цифры\n/import — обновить афишу\n"
                 "/organizer &lt;tg id&gt; — дать права организатора\n/ban &lt;id&gt; и /unban &lt;id&gt; — блокировка\n"
                 "/hide &lt;id события&gt; — скрыть событие\n/reports — последние жалобы\n"
                 "/post today | weekend — опубликовать подборку в канал\n"
                 "Ответить пользователю: ответьте (reply) на его пересланное сообщение.")
    await reply(message, text, [("Открыть афишу", "")])


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
        await notifier.send(user.tg_id, texts.ORGANIZER_ON, "org", button="Мои события")


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
    lines = [f"#{r.id}: на id {r.target_id} от id {r.reporter_id} — {texts.q(r.reason[:200])}" for r in rows]
    await reply(message, "\n".join(lines) or "Жалоб нет.")


@router.my_chat_member()
async def added_to_channel(update: ChatMemberUpdated):
    """A project admin makes the bot an administrator of a channel: the bot starts posting there."""
    if update.chat.type != "channel" or not update.from_user or update.from_user.id not in settings.admin_ids:
        return
    status_now = update.new_chat_member.status
    title = texts.q(update.chat.title or update.chat.username or update.chat.id)
    if status_now == "administrator":
        await channel.set_setting("channel", str(update.chat.id))
        await notifier.send(update.from_user.id,
                            f"📣 Канал «{title}» подключён. Буду публиковать подборки каждый день в 11:00 и "
                            "в четверг в 19:00. Опубликовать сейчас: /post", buttons=[])
    elif status_now in ("left", "kicked") and await channel.get_setting("channel") == str(update.chat.id):
        await channel.set_setting("channel", "")
        await notifier.send(update.from_user.id, f"Канал «{title}» отключён.", buttons=[])


@router.message(Command("post"))
async def post_now(message: Message, command: CommandObject):
    if not is_admin(message):
        return
    kind = (command.args or "today").strip()
    if kind not in channel.TITLES:
        return await message.answer("Так: /post today или /post weekend")
    if not await channel.get_setting("channel"):
        return await message.answer("Канал не подключён: добавьте бота администратором канала.")
    done = await channel.post(message.bot, kind)
    await message.answer("Опубликовано." if done else "Не опубликовал: подходящих событий меньше трёх.")


async def channel_loop(bot: Bot) -> None:
    while True:
        try:
            await channel.run_schedule(bot)
        except Exception as error:
            log.warning("channel schedule failed: %s", error)
        await asyncio.sleep(300)


@router.message()
async def anything(message: Message):
    """Free text goes to the admins as a support request; an admin answers by replying to it."""
    if not message.text:
        return
    if is_admin(message):
        original = message.reply_to_message
        found = SUPPORT_TAG.search((original.text or "") if original else "")
        if found:
            await notifier.send(int(found.group(1)), f"💬 <b>Ответ команды «Кто идёт»</b>\n{texts.q(message.text)}",
                                buttons=[])
            await message.answer("Отправлено.")
        return
    who = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
    for admin in settings.admin_ids:
        await notifier.send(admin, f"✉️ {texts.q(who)} (tg {message.from_user.id}):\n{texts.q(message.text[:1500])}"
                                   "\n\n<i>Ответьте на это сообщение, чтобы написать человеку.</i>", buttons=[])
    await reply(message, texts.SUPPORT_THANKS, [("Открыть афишу", "")])


dispatcher = Dispatcher()
dispatcher.include_router(router)


def make_bot() -> Bot:
    session = None
    if settings.telegram_api_base:
        from aiogram.client.session.aiohttp import AiohttpSession
        from aiogram.client.telegram import TelegramAPIServer
        session = AiohttpSession(api=TelegramAPIServer.from_base(settings.telegram_api_base))
    elif settings.telegram_proxy:
        from aiogram.client.session.aiohttp import AiohttpSession
        session = AiohttpSession(proxy=settings.telegram_proxy)
    return Bot(settings.bot_token, session=session)


async def set_up_profile(bot: Bot, bot_id: int) -> None:
    """Name, descriptions, command menu and avatar. Each is changed only when it differs."""
    steps = [
        ("commands", lambda: bot.set_my_commands([BotCommand(command=c, description=d) for c, d in texts.COMMANDS])),
    ]
    try:
        if (await bot.get_my_name()).name != texts.NAME:
            steps.append(("name", lambda: bot.set_my_name(texts.NAME)))
        if (await bot.get_my_description()).description != texts.DESCRIPTION:
            steps.append(("description", lambda: bot.set_my_description(texts.DESCRIPTION)))
        if (await bot.get_my_short_description()).short_description != texts.SHORT_DESCRIPTION:
            steps.append(("short description", lambda: bot.set_my_short_description(texts.SHORT_DESCRIPTION)))
        if AVATAR.exists() and (await bot.get_user_profile_photos(bot_id, limit=1)).total_count == 0:
            steps.append(("avatar", lambda: bot.set_my_profile_photo(
                InputProfilePhotoStatic(photo=FSInputFile(AVATAR)))))
    except Exception as error:
        log.warning("bot profile check failed: %s", error)
    for name, step in steps:
        try:
            await step()
        except Exception as error:  # Telegram limits how often a name can change; try again next start
            log.warning("bot %s not updated: %s", name, error)


async def run_bot() -> None:
    bot = make_bot()
    try:
        me = await bot.get_me(request_timeout=15)
        notifier.bot = bot
        status["bot"], status["bot_error"] = f"polling as @{me.username}", ""
        settings.bot_username = me.username or settings.bot_username  # the real name, whatever .env says
        if settings.webapp_url.startswith("https://"):
            await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
                text="Афиша", web_app=WebAppInfo(url=settings.webapp_url + "/")))
        await set_up_profile(bot, me.id)
        await bot.delete_webhook(drop_pending_updates=False)
        poster = asyncio.create_task(channel_loop(bot))
        try:
            await dispatcher.start_polling(bot, handle_signals=False)
        finally:
            poster.cancel()
    finally:
        notifier.bot = None
        await bot.session.close()
