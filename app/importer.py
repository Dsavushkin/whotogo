"""The «parser»: pulls events from outside sources into the afisha."""
import logging

from sqlalchemy import select

from .config import settings
from .db import Session
from .models import Event
from .notify import status
from .sources import mozgva, quizplease, timepad

log = logging.getLogger("whotogo.import")
FIELDS = ("title", "description", "category", "starts_at", "ends_at", "place", "address", "price", "url", "image")


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
    """Timepad (if a token is set) plus the quiz organizers. One failing source does not stop the others."""
    jobs = [("Квиз, плиз", quizplease.fetch()), ("Мозгва", mozgva.fetch())]
    if settings.timepad_token:
        jobs.insert(0, ("Timepad", timepad.fetch(settings.timepad_token, settings.timepad_city,
                                                  settings.import_days_ahead)))
    total = {"added": 0, "updated": 0, "seen": 0}
    errors = []
    for name, job in jobs:
        try:
            items = await job
        except Exception as error:
            log.warning("%s import failed: %s", name, error)
            errors.append(f"{name}: {type(error).__name__}: {error}"[:200])
            continue
        if not items:
            continue
        result = await save_events(items, settings.city)
        log.info("import %s: %s", name, result)
        for key in total:
            total[key] += result[key]
    if errors and not total["seen"]:
        status["import"] = {"error": "; ".join(errors)[:300]}
        return {"error": "; ".join(errors)}
    if errors:
        total["warnings"] = errors
    status["import"] = total
    return total
