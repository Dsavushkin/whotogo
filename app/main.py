import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .config import settings
from .db import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
WEB = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    tasks = []
    if settings.run_bot and settings.bot_token:
        from .bot import run_bot
        tasks.append(asyncio.create_task(run_bot()))
    if settings.run_jobs:
        from .jobs import run_jobs
        tasks.append(asyncio.create_task(run_jobs()))
    yield
    for task in tasks:
        task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await task


app = FastAPI(title="Кто идёт", lifespan=lifespan, docs_url="/api/docs" if settings.dev else None, redoc_url=None,
              openapi_url="/api/openapi.json" if settings.dev else None)
app.include_router(router)


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/api/config")
async def config():
    return {"bot": settings.bot_username, "dev": settings.dev}


def _legal(name: str) -> HTMLResponse:
    text = (WEB / "legal" / name).read_text(encoding="utf-8")
    text = text.replace("{{OPERATOR}}", settings.operator_name or "[наименование оператора]")
    text = text.replace("{{EMAIL}}", settings.contact_email or "[электронная почта]")
    return HTMLResponse(text.replace("{{BOT}}", settings.bot_username))


@app.get("/privacy", response_class=HTMLResponse)
async def privacy():
    return _legal("privacy.html")


@app.get("/terms", response_class=HTMLResponse)
async def terms():
    return _legal("terms.html")


@app.middleware("http")
async def no_stale_pages(request: Request, call_next):
    """Telegram keeps pages for a long time; make it re-check the Mini App files."""
    response = await call_next(request)
    if not request.url.path.startswith(("/api/", "/fonts/")):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
