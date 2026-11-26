"""OneTap Connect (the iOS proxy client): its support form sends messages to the admins in the bot."""
import time
from html import escape

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .config import settings
from .notify import notifier

router = APIRouter(prefix="/api/onetap", include_in_schema=False)
recent: dict[str, float] = {}


class SupportIn(BaseModel):
    contact: str = Field(min_length=3, max_length=120)
    text: str = Field(min_length=2, max_length=2000)


@router.post("/support")
async def support(body: SupportIn, request: Request):
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0]
    now = time.monotonic()
    if now - recent.get(ip, -1e9) < 60:
        raise HTTPException(429, "Подождите минуту")
    recent[ip] = now
    text = f"🛟 <b>OneTap Connect — поддержка</b>\nКонтакт: {escape(body.contact)}\n\n{escape(body.text)}"
    for admin in settings.admin_ids:
        await notifier.send(admin, text, button="Открыть")
    return {"ok": True}
