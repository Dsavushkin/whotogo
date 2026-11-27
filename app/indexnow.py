"""IndexNow: tells Yandex (and Bing) about new pages right away instead of waiting for the crawler.
The key is public by design — search engines check it at /<key>.txt on our domain."""
import logging
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from .config import settings

log = logging.getLogger("whotogo.indexnow")
KEY = "c4f1a8e27b9d4e5fa03b6d81e2c7f590"
ENDPOINT = "https://yandex.com/indexnow"
router = APIRouter(include_in_schema=False)


@router.get(f"/{KEY}.txt", response_class=PlainTextResponse)
async def key_file():
    return KEY


async def submit(paths: list) -> int:
    """Best effort; never raises. Returns how many URLs were sent."""
    base = (settings.webapp_url or "").rstrip("/")
    host = urlparse(base).hostname or ""
    if settings.dev or not paths or not host or host.endswith("sslip.io"):
        return 0
    urls = [base + path for path in dict.fromkeys(paths)][:10000]
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(ENDPOINT, json={"host": host, "key": KEY,
                                                         "keyLocation": f"{base}/{KEY}.txt", "urlList": urls})
        log.info("indexnow %s urls -> %s", len(urls), response.status_code)
    except Exception as error:  # search engines being down is not our problem
        log.warning("indexnow failed: %s", error)
        return 0
    return len(urls)
