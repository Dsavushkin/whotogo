"""Sign-in with Telegram Mini App init data."""
from typing import Optional
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import get_session
from .models import User


def verify_init_data(init_data: str, bot_token: str, max_age: int, now: Optional[float] = None) -> Optional[dict]:
    """Returns the Telegram user dict if the signature is valid and fresh, else None."""
    if not init_data or not bot_token:
        return None
    pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    received = pairs.pop("hash", "")
    if not received:
        return None
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        return None
    try:
        auth_date = int(pairs.get("auth_date", "0"))
        user = json.loads(pairs.get("user", ""))
    except (ValueError, json.JSONDecodeError):
        return None
    if (now or time.time()) - auth_date > max_age:
        return None
    return user if isinstance(user, dict) and "id" in user else None


async def current_user(
    authorization: str = Header(default=""),
    x_dev_user: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
) -> User:
    tg: Optional[dict] = None
    if authorization.startswith("tma "):
        tg = verify_init_data(authorization[4:], settings.bot_token, settings.init_data_max_age)
    elif settings.dev and x_dev_user:
        # "12345" or "12345:Name" – local development and tests only.
        tg_id, _, name = x_dev_user.partition(":")
        if tg_id.isdigit():
            tg = {"id": int(tg_id), "first_name": name or f"User {tg_id}"}
    if not tg:
        raise HTTPException(401, "Откройте приложение через Telegram")

    user = (await session.execute(select(User).where(User.tg_id == int(tg["id"])))).scalar_one_or_none()
    if user is None:
        user = User(tg_id=int(tg["id"]), name=str(tg.get("first_name", ""))[:64],
                    username=str(tg.get("username", ""))[:64], city=settings.city)
        session.add(user)
        await session.commit()
    elif tg.get("username") and tg["username"] != user.username:
        user.username = str(tg["username"])[:64]
        await session.commit()
    if user.is_banned:
        raise HTTPException(403, "Аккаунт заблокирован")
    return user
