import asyncio
import logging
import re
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .config import settings
from .db import init_db
from .notify import status
from .seo import router as seo_router
from .groups import router as groups_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
WEB = Path(__file__).resolve().parent.parent / "web"


async def _keep_running(name: str, job) -> None:
    """Restarts a background job if it stops with an error (wrong token, network trouble)."""
    while True:
        try:
            status[name] = "starting"
            await job()
            status[name] = "stopped"
        except asyncio.CancelledError:
            raise
        except Exception as error:
            text = f"{type(error).__name__}: {error}".replace(settings.bot_token or "\0", "***")[:300]
            status[name], status[name + "_error"] = "error", text
            logging.getLogger("whotogo").error("%s stopped: %s. Next try in a minute.", name, text)
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    tasks = []
    if settings.run_bot and settings.bot_token:
        from .bot import run_bot
        tasks.append(asyncio.create_task(_keep_running("bot", run_bot)))
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
app.include_router(seo_router)
app.include_router(groups_router)


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/api/diag")
async def diag():
    """Self-check for the first days after launch: states only, no secrets."""
    import re

    import httpx

    token = settings.bot_token
    out = {"bot_token_set": bool(token), "bot_token_shape_ok": bool(re.fullmatch(r"\d{6,12}:[\w-]{30,}", token)),
           "bot": status.get("bot"), "bot_error": status.get("bot_error"), "import": status.get("import"),
           "timepad_token_set": bool(settings.timepad_token), "admins": len(settings.admin_ids),
           "webapp_url": settings.webapp_url}
    try:
        async with httpx.AsyncClient(timeout=6) as client:
            base = settings.telegram_api_base or "https://api.telegram.org"
            out["telegram_via"] = "relay" if settings.telegram_api_base else ("proxy" if settings.telegram_proxy else "direct")
            out["telegram"] = (await client.get(base + "/")).status_code
    except Exception as error:
        out["telegram"] = f"{type(error).__name__}: {error}"[:200]
    if settings.telegram_proxy:
        try:
            import aiohttp
            from aiohttp_socks import ProxyConnector

            async with aiohttp.ClientSession(connector=ProxyConnector.from_url(settings.telegram_proxy),
                                             timeout=aiohttp.ClientTimeout(total=8)) as http:
                async with http.get("https://api.telegram.org/", allow_redirects=False) as response:
                    out["telegram_via_proxy"] = response.status
        except Exception as error:
            out["telegram_via_proxy"] = f"{type(error).__name__}: {error}"[:200]
    return out


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


@app.get("/support", response_class=HTMLResponse)
async def support():
    return _legal("support.html")


@app.get("/terms", response_class=HTMLResponse)
async def terms():
    return _legal("terms.html")


@app.middleware("http")
async def no_stale_pages(request: Request, call_next):
    """Telegram keeps pages for a long time; make it re-check the Mini App files."""
    if request.url.path in ("", "/") and "/tg/" in request.url.query:
        # an ad platform glued its marking (?erid=…) in front of our path: …ru?erid=X/tg/<source>
        found = re.search(r"/tg/([A-Za-z0-9_-]{1,32})", request.url.query)
        if found:
            return RedirectResponse(f"https://t.me/{settings.bot_username}?startapp=src_{found.group(1)}", 302)
    response = await call_next(request)
    if not request.url.path.startswith(("/api/", "/fonts/")):
        response.headers["Cache-Control"] = "no-cache"
    if request.url.path.startswith("/promo/"):  # App Store Connect fetches the promo images from here
        response.headers["Access-Control-Allow-Origin"] = "https://appstoreconnect.apple.com"
    return response


app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
