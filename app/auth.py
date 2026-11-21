"""Sign-in with Telegram Mini App init data."""
from typing import Optional
import asyncio
import hashlib
import hmac
import json
import secrets
import time
from datetime import timedelta
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import get_session
from .models import AuthToken, LoginCode, User, utcnow


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
    if authorization.startswith("Bearer "):
        row = await session.get(AuthToken, token_hash(authorization[7:]))
        user = await session.get(User, row.user_id) if row else None
        if user is None:
            raise HTTPException(401, "Войдите заново")
        if user.is_banned:
            raise HTTPException(403, "Аккаунт заблокирован")
        return user
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


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def issue_login_code(session: AsyncSession, user: User, minutes: int = 10) -> str:
    """A fresh 6-digit code for the user; older codes of the same user stop working."""
    await session.execute(delete(LoginCode).where(
        (LoginCode.user_id == user.id) | (LoginCode.expires_at < utcnow())))
    while True:
        code = f"{secrets.randbelow(10 ** 6):06d}"
        if await session.get(LoginCode, code) is None:
            break
    session.add(LoginCode(code=code, user_id=user.id, expires_at=utcnow() + timedelta(minutes=minutes)))
    await session.commit()
    return code


async def exchange_code(session: AsyncSession, code: str) -> Optional[str]:
    """Code -> long-lived token (None if the code is wrong or expired). A code works once."""
    row = await session.get(LoginCode, code)
    if row is None or row.expires_at < utcnow():
        return None
    token = secrets.token_urlsafe(32)
    session.add(AuthToken(token_hash=token_hash(token), user_id=row.user_id))
    await session.delete(row)
    await session.commit()
    return token


async def new_token(session: AsyncSession, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    session.add(AuthToken(token_hash=token_hash(token), user_id=user_id))
    await session.commit()
    return token


def _scrypt(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)


async def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = await asyncio.to_thread(_scrypt, password, salt)
    return f"scrypt${salt.hex()}${digest.hex()}"


async def check_password(password: str, stored: str) -> bool:
    try:
        kind, salt, digest = stored.split("$")
        if kind != "scrypt":
            return False
        fresh = await asyncio.to_thread(_scrypt, password, bytes.fromhex(salt))
    except ValueError:
        return False
    return hmac.compare_digest(fresh.hex(), digest)


async def maybe_user(
    authorization: str = Header(default=""),
    x_dev_user: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
) -> Optional[User]:
    """The signed-in user, or None for a guest who only looks at the afisha."""
    if not authorization and not (settings.dev and x_dev_user):
        return None
    try:
        return await current_user(authorization, x_dev_user, session)
    except HTTPException:
        return None
