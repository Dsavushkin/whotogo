"""Picture for channel posts: heading, date and the top events with their posters (1080×1350)."""
import asyncio
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageOps

from . import texts
from .config import settings
from .api import CATEGORIES

ASSETS = Path(__file__).resolve().parent / "assets"
W, H = 1080, 1350
BLUE, INK, LIME, ORANGE, PINK, SKY, WHITE = "#2B4BFF", "#0E0E12", "#C8F03C", "#FF6A2B", "#FFC2DD", "#BFD0FF", "#FFFFFF"
MUTED = "#5B6070"
DAYS_FULL = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(ASSETS / name), size)


def fit(draw: ImageDraw.ImageDraw, text: str, fnt, width: int, lines: int) -> list[str]:
    """Word-wraps text into at most `lines` lines, the last one ending with … if cut."""
    words, out, line = text.split(), [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=fnt) <= width:
            line = trial
            continue
        if line:
            out.append(line)
        line = word
        if len(out) == lines:
            break
    if line and len(out) < lines:
        out.append(line)
    if len(out) == lines and " ".join(out) != " ".join(words):
        last = out[-1]
        while last and draw.textlength(last + "…", font=fnt) > width:
            last = last[:-1].rstrip()
        out[-1] = last + "…"
    return out


async def fetch_posters(urls: list[str]) -> list[Optional[Image.Image]]:
    import httpx

    async def one(client, url):
        if not url:
            return None
        try:
            response = await client.get(url)
            response.raise_for_status()
            return Image.open(io.BytesIO(response.content)).convert("RGB")
        except Exception:
            return None

    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        return list(await asyncio.gather(*(one(client, u) for u in urls)))


def rounded(img: Image.Image, size: int, radius: int) -> Image.Image:
    img = ImageOps.fit(img, (size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size, size), radius, fill=255)
    out = Image.new("RGBA", (size, size))
    out.paste(img, (0, 0), mask)
    return out


def render(kind: str, picks: list, posters: list, now: Optional[datetime] = None) -> bytes:
    local_now = (now or datetime.now(timezone.utc)).astimezone(texts.TZ)
    weekend = kind == "weekend"
    ground, accent = (INK, LIME) if weekend else (BLUE, LIME)
    img = Image.new("RGB", (W, H), ground)
    draw = ImageDraw.Draw(img)

    logo = Image.open(ASSETS / "logo.png").convert("RGBA")
    logo = logo.resize((int(logo.width * 52 / logo.height), 52), Image.LANCZOS)
    img.paste(logo, (64, 60), logo)
    draw.text((64 + logo.width + 18, 66), "Кто идёт", font=font("Manrope_800ExtraBold.ttf", 34), fill=WHITE)

    head = font("Unbounded_800ExtraBold.ttf", 80)
    draw.text((60, 140), "Куда сходить", font=head, fill=WHITE)
    draw.text((60, 232), "на выходных" if weekend else "сегодня", font=head, fill=accent)

    if weekend:
        label = "суббота и воскресенье"
    else:
        label = f"{DAYS_FULL[local_now.weekday()]}, {local_now.day} {texts.MONTHS[local_now.month - 1]}"
    chip = font("Manrope_800ExtraBold.ttf", 30)
    width = draw.textlength(label, font=chip)
    draw.rounded_rectangle((64, 346, 64 + width + 48, 346 + 58), 29, fill=WHITE)
    draw.text((88, 357), label, font=chip, fill=INK)

    title_font, place_font = font("Manrope_800ExtraBold.ttf", 32), font("Manrope_700Bold.ttf", 24)
    time_font = font("Manrope_800ExtraBold.ttf", 26)
    top, row_h, gap, thumb = 434, 200, 14, 168
    colors = [ORANGE, LIME, PINK, SKY]
    for n, ((event, going, looking), poster) in enumerate(zip(picks[:4], posters[:4])):
        y = top + n * (row_h + gap)
        draw.rounded_rectangle((48, y, W - 48, y + row_h), 32, fill=WHITE)
        tx, ty = 64 + 16, y + 16
        if poster is not None:
            card = rounded(poster, thumb, 24)
            img.paste(card, (tx, ty), card)
        else:
            draw.rounded_rectangle((tx, ty, tx + thumb, ty + thumb), 24, fill=colors[n % 4])
            name = CATEGORIES.get(event.category, "Другое")
            small = font("Manrope_800ExtraBold.ttf", 24)
            draw.text((tx + 16, ty + thumb - 44), name, font=small, fill=INK)
        x = tx + thumb + 28
        start = texts.local(event.starts_at)
        when = f"{texts.WEEKDAYS[start.weekday()]} {start:%H:%M}" if weekend else f"{start:%H:%M}"
        tw = draw.textlength(when, font=time_font)
        draw.rounded_rectangle((x, ty + 2, x + tw + 28, ty + 44), 21, fill=LIME if not weekend else ORANGE)
        draw.text((x + 14, ty + 7), when, font=time_font, fill=INK)
        if looking:
            note = f"{looking} ищут компанию"
            draw.text((x + tw + 44, ty + 9), note, font=font("Manrope_800ExtraBold.ttf", 24), fill=BLUE)
        lines = fit(draw, event.title, title_font, W - 48 - 28 - x, 2)
        for i, line in enumerate(lines):
            draw.text((x, ty + 54 + i * 40), line, font=title_font, fill=INK)
        if event.place:
            place = fit(draw, event.place, place_font, W - 48 - 28 - x, 1)[0]
            draw.text((x, ty + 58 + len(lines) * 40), place, font=place_font, fill=MUTED)

    footer = font("Manrope_800ExtraBold.ttf", 30)
    draw.text((64, H - 66), "Найди компанию на вечер →", font=footer, fill=WHITE)
    handle = "@" + settings.bot_username
    draw.text((W - 64 - draw.textlength(handle, font=footer), H - 66), handle, font=footer, fill=accent)

    out = io.BytesIO()
    img.save(out, "JPEG", quality=90, optimize=True)
    return out.getvalue()
