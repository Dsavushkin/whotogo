import os
import tempfile

_dir = tempfile.mkdtemp()
os.environ.update(DEV="1", RUN_BOT="0", RUN_JOBS="0", BOT_TOKEN="", ADMIN_IDS="1",
                  DATABASE_URL=os.getenv("TEST_DATABASE_URL", f"sqlite+aiosqlite:///{_dir}/test.db"), TIMEZONE="Europe/Moscow")

import httpx  # noqa: E402
import pytest_asyncio  # noqa: E402

from app.db import Base, Session, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Event, utcnow  # noqa: E402
from app.notify import notifier  # noqa: E402


class Person:
    """A signed-in visitor of the Mini App."""

    def __init__(self, client, tg_id, name):
        self.client, self.headers, self.name, self.id = client, {"X-Dev-User": str(tg_id)}, name, None
        self.tg_id = tg_id

    async def call(self, method, path, **kw):
        return await self.client.request(method, "/api" + path, headers=self.headers, **kw)

    async def ok(self, method, path, **kw):
        response = await self.call(method, path, **kw)
        assert response.status_code == 200, response.text
        return response.json()

    async def join(self):
        me = await self.ok("PUT", "/me", json={"name": self.name, "age": 28, "bio": "", "interests": ["кино"],
                                                "adult_ok": True})
        self.id = me["id"]
        return self


@pytest_asyncio.fixture
async def client():
    await engine.dispose()  # connections belong to the previous test's event loop
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    notifier.sent.clear()
    notifier._last.clear()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await engine.dispose()


@pytest_asyncio.fixture
async def people(client):
    return [await Person(client, 100 + i, name).join() for i, name in enumerate(["Вера", "Аня", "Кирилл"])]


async def add_event(hours=5, title="Винил-вечер", **kw):
    from datetime import timedelta
    async with Session() as session:
        event = Event(title=title, starts_at=utcnow() + timedelta(hours=hours), **{"place": "Лофт", **kw})
        session.add(event)
        await session.commit()
        return event.id
