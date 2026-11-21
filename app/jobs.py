"""Background work: refresh the afisha and ask guests the morning after an event."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from .config import settings
from .db import Session
from .importer import run_import
from .models import Attendance, Event, User, utcnow
from .notify import notifier

log = logging.getLogger("whotogo.jobs")


async def send_after_prompts(now_local_hour: int = -1) -> int:
    """«С кем хочется увидеться ещё?» – once per guest, 12–48 hours after the start, in daytime."""
    hour = now_local_hour if now_local_hour >= 0 else datetime.now(timezone.utc).astimezone(
        ZoneInfo(settings.timezone)).hour
    if not 10 <= hour < 21:
        return 0
    now, sent = utcnow(), 0
    async with Session() as session:
        rows = (await session.execute(
            select(Attendance, Event, User).join(Event, Event.id == Attendance.event_id)
            .join(User, User.id == Attendance.user_id)
            .where(Attendance.after_prompted.is_(False), Event.starts_at <= now - timedelta(hours=12),
                   Event.starts_at >= now - timedelta(hours=48)).limit(500))).all()
        guests: dict = {}
        for attendance, event, user in rows:
            if event.id not in guests:
                guests[event.id] = await session.scalar(
                    select(func.count()).select_from(Attendance).where(Attendance.event_id == event.id))
            attendance.after_prompted = True
            if guests[event.id] >= 2 and not user.is_banned:
                await notifier.send(user.tg_id, f"Как прошло «{event.title}»? С кем хочется увидеться ещё? "
                                    "Отметьте гостей: человек узнает об этом, только если отметит вас в ответ.",
                                    f"after-{event.id}")
                sent += 1
        await session.commit()
    return sent


async def run_jobs() -> None:
    last_import = 0.0
    loop = asyncio.get_running_loop()
    while True:
        try:
            if settings.timepad_token and loop.time() - last_import > settings.import_every_hours * 3600:
                last_import = loop.time()
                await run_import()
            await send_after_prompts()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("background job failed")
        await asyncio.sleep(600)
