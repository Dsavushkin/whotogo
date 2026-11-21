"""The «parser»: pulls events from outside sources into the afisha."""
import logging

from sqlalchemy import select

from .config import settings
from .db import Session
from .models import Event
from .sources import timepad

log = logging.getLogger("whotogo.import")
FIELDS = ("title", "description", "category", "starts_at", "ends_at", "place", "address", "price", "url")


async def save_events(items: list, city: str) -> dict:
    """Adds new events and refreshes known ones. Hidden events stay hidden."""
    added = updated = 0
    async with Session() as session:
        known = {}
        ids = [item["source_id"] for item in items]
        for start in range(0, len(ids), 500):
            rows = await session.execute(select(Event).where(
                Event.source == items[0]["source"], Event.source_id.in_(ids[start:start + 500])))
            known.update({event.source_id: event for event in rows.scalars()})
        for item in items:
            event = known.get(item["source_id"])
            if event is None:
                event = known[item["source_id"]] = Event(city=city, **item)
                session.add(event)
                added += 1
            else:
                changed = False
                for field in FIELDS:
                    if getattr(event, field) != item[field]:
                        setattr(event, field, item[field])
                        changed = True
                updated += changed
        await session.commit()
    return {"added": added, "updated": updated, "seen": len(items)}


async def run_import() -> dict:
    if not settings.timepad_token:
        return {"error": "Не задан TIMEPAD_TOKEN"}
    try:
        items = await timepad.fetch(settings.timepad_token, settings.timepad_city, settings.import_days_ahead)
    except Exception as error:
        log.warning("timepad import failed: %s", error)
        return {"error": f"Timepad: {error}"}
    result = await save_events(items, settings.city)
    log.info("import done: %s", result)
    return result
