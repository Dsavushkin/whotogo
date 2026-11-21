"""Tables. All datetimes are stored as naive UTC."""
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    # Telegram users have tg_id, site users have email; one of the two is always set.
    tg_id: Mapped[Optional[int]] = mapped_column(BigInteger, unique=True, index=True, nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(120), unique=True, index=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(200), default="")
    username: Mapped[str] = mapped_column(String(64), default="")
    name: Mapped[str] = mapped_column(String(64), default="")
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bio: Mapped[str] = mapped_column(String(300), default="")
    interests: Mapped[list] = mapped_column(JSON, default=list)
    city: Mapped[str] = mapped_column(String(16), default="msk")
    # The person confirmed they are 18+ and accepted the terms.
    adult_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    is_organizer: Mapped[bool] = mapped_column(Boolean, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("source", "source_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(16), default="org")  # "kudago" | "org"
    source_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(32), default="other", index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    place: Mapped[str] = mapped_column(String(200), default="")
    address: Mapped[str] = mapped_column(String(300), default="")
    price: Mapped[str] = mapped_column(String(120), default="")
    url: Mapped[str] = mapped_column(String(500), default="")
    image: Mapped[str] = mapped_column(String(500), default="")  # poster from the organizer, may be empty
    city: Mapped[str] = mapped_column(String(16), default="msk", index=True)
    capacity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    organizer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Attendance(Base):
    __tablename__ = "attendance"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), primary_key=True, index=True)
    status: Mapped[str] = mapped_column(String(16))  # "going" | "looking"
    note: Mapped[str] = mapped_column(String(200), default="")
    checked_in: Mapped[bool] = mapped_column(Boolean, default=False)
    after_prompted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Like(Base):
    """One-sided interest. Nobody sees it until it is mutual."""
    __tablename__ = "likes"
    __table_args__ = (UniqueConstraint("from_id", "to_id", "event_id", "kind"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    from_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    to_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # "together" (before) | "again" (after)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Match(Base):
    """Mutual interest for one event; opens a chat. a_id < b_id."""
    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("a_id", "b_id", "event_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    a_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    b_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Block(Base):
    __tablename__ = "blocks"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    target_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class LoginCode(Base):
    """One-time code from the bot (/login) to sign in outside Telegram, e.g. in the iPhone app."""
    __tablename__ = "login_codes"
    code: Mapped[str] = mapped_column(String(6), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class AuthToken(Base):
    """A signed-in device. Only the SHA-256 of the token is stored."""
    __tablename__ = "auth_tokens"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
