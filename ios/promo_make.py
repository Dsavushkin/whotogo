"""App Store promo images for «Кто идёт»: a headline plus a drawn iPhone screen that mirrors the real app."""
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

FONTS = Path("/home/claude/whotogo/web/fonts")
OUT = Path("/home/claude/promo/out")
OUT.mkdir(parents=True, exist_ok=True)

CSS = f"""
@font-face{{font-family:Manrope;font-weight:200 800;src:url(file://{FONTS}/manrope-cyrillic-wght-normal.woff2) format("woff2");unicode-range:U+0400-045F,U+2116}}
@font-face{{font-family:Manrope;font-weight:200 800;src:url(file://{FONTS}/manrope-latin-wght-normal.woff2) format("woff2");unicode-range:U+0000-00FF,U+2000-206F,U+20BD}}
@font-face{{font-family:Unbounded;font-weight:200 900;src:url(file://{FONTS}/unbounded-cyrillic-wght-normal.woff2) format("woff2");unicode-range:U+0400-045F}}
@font-face{{font-family:Unbounded;font-weight:200 900;src:url(file://{FONTS}/unbounded-latin-wght-normal.woff2) format("woff2");unicode-range:U+0000-00FF,U+2000-206F}}
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{--ground:#F3F4F6;--ink:#0E0E12;--muted:#4A4E5A;--cobalt:#2B4BFF;--cobaltInk:#1B33C4;--lime:#C8F03C;--orange:#FF6A2B;--pink:#FFC2DD;--sky:#BFD0FF;--sun:#FFE08A;--soft:#E6E8ED}}
html,body{{width:440px;height:956px;overflow:hidden}}
body{{font-family:Manrope,sans-serif;font-weight:500;color:var(--ink);-webkit-font-smoothing:antialiased}}
.frame{{position:relative;width:440px;height:956px;overflow:hidden;padding:56px 32px 0}}
.head h1{{font-family:Unbounded,sans-serif;font-weight:800;font-size:33px;line-height:1.12;letter-spacing:-.01em}}
.head p{{margin-top:14px;font-size:18px;font-weight:600;line-height:1.35;opacity:.86}}
.phone{{position:absolute;left:62px;top:258px;width:316px;height:678px;border-radius:52px;background:#0b0b0e;padding:9px;box-shadow:0 30px 60px rgba(0,0,0,.28)}}
.screen{{width:298px;height:660px;border-radius:44px;overflow:hidden;background:var(--ground);position:relative;color:var(--ink)}}
.inner{{width:390px;height:864px;transform:scale(.7641);transform-origin:0 0;position:relative}}
.status{{height:54px;display:flex;align-items:center;justify-content:space-between;padding:0 32px 0 40px;font-weight:700;font-size:16px}}
.status .ic{{display:flex;gap:6px;align-items:center}}
.island{{position:absolute;top:11px;left:50%;transform:translateX(-50%);width:122px;height:35px;border-radius:20px;background:#000}}
.pad{{padding:6px 20px 0}}
.kicker{{font-size:13px;font-weight:700;color:var(--muted)}}
.title{{font-family:Unbounded,sans-serif;font-weight:800;font-size:28px;line-height:1.1}}
.row{{display:flex;gap:8px}}
.chip{{height:44px;padding:0 18px;border-radius:22px;background:#fff;font-size:15px;font-weight:700;display:flex;align-items:center;white-space:nowrap}}
.chip.on{{background:var(--ink);color:#fff}}
.chip.s{{height:36px;padding:0 14px;font-size:13px}}
.badge{{display:inline-block;background:var(--lime);font-size:12px;font-weight:800;padding:6px 10px;border-radius:12px}}
.badge.dim{{background:rgba(14,14,18,.35);color:#fff;font-weight:700}}
.badge.ink{{background:var(--ink);color:#fff}}
.hero{{border-radius:28px;overflow:hidden;background:#fff}}
.poster{{background:var(--cobalt);min-height:196px;padding:18px;display:flex;flex-direction:column;justify-content:space-between;gap:26px;color:#fff}}
.poster h2{{font-family:Unbounded,sans-serif;font-weight:800;font-size:25px;line-height:1.1}}
.between{{display:flex;justify-content:space-between;align-items:center;gap:8px}}
.meta{{padding:14px 18px 16px;display:flex;flex-direction:column;gap:10px}}
.small{{font-size:13px;font-weight:600}}
.muted{{color:var(--muted)}}
.looking{{font-size:13px;font-weight:800;color:var(--cobaltInk)}}
.compact{{background:#fff;border-radius:28px;padding:12px;display:flex;gap:14px;align-items:center}}
.tile{{width:92px;height:92px;border-radius:20px;flex:none;padding:10px;display:flex;align-items:flex-end;font-family:Unbounded,sans-serif;font-weight:800;font-size:12px}}
.compact h3{{font-size:17px;font-weight:800;line-height:1.2}}
.tabbar{{position:absolute;left:0;right:0;bottom:0;height:86px;background:rgba(249,249,250,.96);border-top:1px solid rgba(0,0,0,.08);display:flex;justify-content:space-around;padding-top:8px}}
.tab{{display:flex;flex-direction:column;align-items:center;gap:3px;font-size:10.5px;font-weight:600;color:#8a8d96;width:80px}}
.tab.on{{color:var(--ink)}}
.card{{background:#fff;border-radius:26px;padding:16px;display:flex;flex-direction:column;gap:12px}}
.ava{{display:grid;place-items:center;font-weight:800;flex:none}}
.btn{{height:52px;border-radius:26px;display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:800}}
.tag{{background:var(--ground);border-radius:12px;padding:5px 10px;font-size:12px;font-weight:700}}
.note{{background:var(--lime);border-radius:18px;padding:12px 14px;font-size:14px;font-weight:600;line-height:1.35}}
.fact{{background:#fff;border-radius:20px;padding:12px 14px;flex:1;display:flex;flex-direction:column;gap:2px}}
.navback{{width:44px;height:44px;border-radius:22px;background:rgba(255,255,255,.9);display:grid;place-items:center}}
.bubble{{max-width:78%;padding:10px 14px;font-size:15px;line-height:1.35}}
.in{{align-self:flex-start;background:#fff;border-radius:20px 20px 20px 6px}}
.out{{align-self:flex-end;background:var(--cobalt);color:#fff;border-radius:20px 20px 6px 20px}}
.guest{{background:#fff;border-radius:24px;padding:14px 6px 12px;display:flex;flex-direction:column;align-items:center;gap:8px;border:3px solid transparent;position:relative}}
.guest.on{{border-color:var(--cobalt)}}
.tick{{position:absolute;top:8px;right:8px;width:24px;height:24px;border-radius:12px;background:var(--cobalt);color:#fff;display:grid;place-items:center;font-size:13px;font-weight:800}}
"""

STATUS = """<div class="island"></div><div class="status"><span>9:41</span><span class="ic">
<svg width="18" height="12" viewBox="0 0 18 12"><rect x="0" y="8" width="3" height="4" rx="1" fill="currentColor"/><rect x="5" y="5.5" width="3" height="6.5" rx="1" fill="currentColor"/><rect x="10" y="3" width="3" height="9" rx="1" fill="currentColor"/><rect x="15" y="0" width="3" height="12" rx="1" fill="currentColor"/></svg>
<svg width="16" height="12" viewBox="0 0 16 12"><path d="M8 11.5 5.6 9a3.4 3.4 0 0 1 4.8 0zM3.5 7a6.4 6.4 0 0 1 9 0l1.4-1.4a8.4 8.4 0 0 0-11.8 0zM.6 4.1a10.6 10.6 0 0 1 14.8 0L16 3.5A11.5 11.5 0 0 0 0 3.5z" fill="currentColor"/></svg>
<svg width="27" height="13" viewBox="0 0 27 13"><rect x=".5" y=".5" width="23" height="12" rx="3.5" fill="none" stroke="currentColor" opacity=".4"/><rect x="2" y="2" width="20" height="9" rx="2" fill="currentColor"/><rect x="24.5" y="4.5" width="2" height="4" rx="1" fill="currentColor" opacity=".4"/></svg>
</span></div>"""

ICONS = {
    "Афиша": '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3.5" y="5" width="17" height="15.5" rx="3"/><path d="M3.5 9.5h17M8 3v4M16 3v4"/></svg>',
    "Люди": '<svg width="28" height="26" viewBox="0 0 26 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="9" cy="8" r="3.6"/><path d="M2.5 20c.6-3.8 3.2-5.8 6.5-5.8s5.9 2 6.5 5.8"/><circle cx="18" cy="8.5" r="3"/><path d="M17 14.3c3 .1 5.4 2 6 5.7"/></svg>',
    "Чаты": '<svg width="28" height="26" viewBox="0 0 26 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 5.5a3 3 0 0 1 3-3h8a3 3 0 0 1 3 3v5a3 3 0 0 1-3 3H9l-4 3v-3.2A3 3 0 0 1 3 10.5z"/><path d="M19.5 8.5h.5a3 3 0 0 1 3 3v4.5a3 3 0 0 1-2 2.8V21l-3.2-2.5H13a3 3 0 0 1-2.6-1.5"/></svg>',
    "Профиль": '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9.5"/><circle cx="12" cy="10" r="3.2"/><path d="M5.8 18.6c1.3-2.3 3.5-3.6 6.2-3.6s4.9 1.3 6.2 3.6"/></svg>',
}


def tabbar(active):
    items = "".join(f'<div class="tab{" on" if k == active else ""}">{v}<span>{k}</span></div>' for k, v in ICONS.items())
    return f'<div class="tabbar">{items}</div>'


def ava(letter, bg, size=56, fg="#0E0E12", radius=None):
    r = radius if radius is not None else size * 0.4
    return (f'<span class="ava" style="width:{size}px;height:{size}px;border-radius:{r}px;background:{bg};'
            f'color:{fg};font-size:{size*0.4:.0f}px">{letter}</span>')


BACK = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#0E0E12" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg>'


def screen_afisha():
    return STATUS + f"""<div class="pad" style="display:flex;flex-direction:column;gap:14px">
<div><div class="kicker">Москва</div><div class="title">Куда сегодня?</div></div>
<div class="row"><span class="chip on">Сегодня</span><span class="chip">Завтра</span><span class="chip">Выходные</span><span class="chip">Неделя</span></div>
<div class="row"><span class="chip s on">Всё</span><span class="chip s">Музыка</span><span class="chip s">Вечеринки</span><span class="chip s">Еда</span><span class="chip s">Игры</span></div>
<div class="hero"><div class="poster"><div class="between"><span class="badge" style="color:#0E0E12">Сегодня · 20:00</span><span class="badge dim">Музыка</span></div>
<h2>Винил-вечер на крыше</h2></div>
<div class="meta"><span class="small muted">Лофт на Бауманской · 1 200 ₽</span><div class="between"><span class="small" style="font-weight:700">12 идут</span><span class="looking">5 ищут компанию</span></div></div></div>
<div class="compact"><span class="tile" style="background:var(--lime)">Еда</span><div style="display:flex;flex-direction:column;gap:6px"><span class="small muted" style="font-weight:800;font-size:12px">Сегодня · 19:30 · 2 500 ₽</span><h3>Ужин с незнакомцами, 8 мест</h3><span class="looking">3 ищут компанию</span></div></div>
<div class="compact"><span class="tile" style="background:var(--pink)">Игры</span><div style="display:flex;flex-direction:column;gap:6px"><span class="small muted" style="font-weight:800;font-size:12px">Сегодня · 19:00 · 400 ₽</span><h3>Настольные игры в антикафе</h3><span class="looking">2 ищут компанию</span></div></div>
</div>{tabbar("Афиша")}"""


def screen_event():
    return f"""<div style="background:var(--cobalt);padding:54px 20px 22px;border-radius:0 0 32px 32px;color:#fff;position:relative">
<div class="island"></div><div class="status" style="position:absolute;top:0;left:0;right:0;color:#fff">{STATUS.split('<div class="status">')[1].split('</div>')[0]}</div>
<div class="between" style="margin-top:6px"><span class="navback">{BACK}</span><span class="badge dim">Музыка</span></div>
<div style="margin-top:48px"><span class="badge" style="color:#0E0E12">Сегодня · 20:00</span>
<div style="font-family:Unbounded;font-weight:800;font-size:29px;line-height:1.1;margin-top:10px">Винил-вечер на крыше</div></div></div>
<div class="pad" style="padding-top:16px;display:flex;flex-direction:column;gap:14px">
<div class="row" style="gap:10px"><div class="fact"><span class="muted" style="font-size:12px;font-weight:800">Где</span><span style="font-weight:700;font-size:15px">Лофт на Бауманской</span><span class="small muted">ул. Бауманская, 11</span></div>
<div class="fact"><span class="muted" style="font-size:12px;font-weight:800">Билет</span><span style="font-weight:700;font-size:15px">1 200 ₽</span></div></div>
<p style="font-size:15px;line-height:1.4">Диджей ставит пластинки из своей коллекции, гости приносят свои. Небольшой зал и общий стол — можно прийти одному.</p>
<div class="card"><div class="between"><span style="font-size:17px;font-weight:800">Кто идёт</span><span class="looking" style="font-size:14px">Все 12</span></div>
<div class="row" style="align-items:center"><span style="display:flex">{''.join(ava(l, c, 30, radius=15).replace('class="ava"', 'class="ava" style2') for l, c in [])}</span>
<span style="display:flex">{''.join(f'<span class="ava" style="width:32px;height:32px;border-radius:16px;background:{c};font-size:13px;border:2px solid #fff;margin-left:{0 if i == 0 else -10}px">{l}</span>' for i, (l, c) in enumerate([("А", "#FF6A2B"), ("К", "#C8F03C"), ("Д", "#FFC2DD"), ("М", "#BFD0FF")]))}</span>
<span class="small" style="font-weight:600">5 человек ищут, с кем пойти</span></div></div>
</div>
<div style="position:absolute;left:0;right:0;bottom:0;padding:12px 20px 34px;background:var(--ground);display:flex;gap:8px">
<span class="btn" style="flex:1;background:var(--soft);height:58px;border-radius:29px">Иду</span>
<span class="btn" style="flex:1;background:var(--ink);color:#fff;height:58px;border-radius:29px">Ищу компанию</span></div>"""


def seeker(letter, bg, name, text, tags, button):
    tag_html = "".join(f'<span class="tag">{t}</span>' for t in tags)
    return f"""<div class="card"><div class="row" style="gap:12px;align-items:flex-start">{ava(letter, bg)}
<div style="display:flex;flex-direction:column;gap:6px"><span style="font-size:18px;font-weight:800">{name}</span><span style="font-size:14px;line-height:1.35">{text}</span></div></div>
<div class="row" style="flex-wrap:wrap;gap:6px">{tag_html}</div>{button}
<span class="muted" style="font-size:12px;font-weight:600;text-align:center">Пожаловаться</span></div>"""


def screen_people():
    blue = '<span class="btn" style="background:var(--cobalt);color:#fff">Пойдём вместе</span>'
    done = '<span class="btn" style="background:var(--soft);color:var(--muted)">✓ Вы предложили</span>'
    return STATUS + f"""<div class="pad" style="display:flex;flex-direction:column;gap:14px">
<div class="row" style="gap:12px;align-items:center"><span class="navback" style="background:#fff">{BACK}</span>
<div><div class="kicker">Винил-вечер на крыше · сегодня</div><div class="title" style="font-size:24px">Ищут компанию</div></div></div>
<div class="note">Чат откроется, только если вы оба нажали «Пойдём вместе». Отказ никто не увидит.</div>
{seeker("А", "#FF6A2B", "Аня, 27", "Иду первый раз, принесу пару пластинок. Хочу компанию из 2–3 человек.", ["джаз", "фотография", "настолки"], blue)}
{seeker("К", "#C8F03C", "Кирилл, 31", "Недавно переехал в Москву, ищу, с кем ходить на концерты.", ["инди", "бег", "кино"], done)}
</div>"""


def screen_match():
    return f"""<div style="position:absolute;inset:0;background:var(--cobalt);color:#fff">
<div class="island"></div><div class="status" style="color:#fff">{STATUS.split('<div class="status">')[1].split('</div>')[0]}</div>
<div style="padding:4px 20px"><span style="font-size:16px;font-weight:600">Закрыть</span></div>
<div style="display:flex;flex-direction:column;align-items:center;gap:28px;padding:110px 20px 0">
<div class="row" style="gap:0">{ava("В", "#FFE08A", 112)}<span style="margin-left:-18px">{ava("А", "#FF6A2B", 112)}</span></div>
<div style="text-align:center"><div style="font-family:Unbounded;font-weight:800;font-size:34px">Идёте вместе</div>
<p style="margin-top:10px;font-size:17px;font-weight:600;line-height:1.4">Аня тоже хочет пойти с вами.<br>Договоритесь, где встретиться.</p></div>
<div style="align-self:stretch;background:rgba(14,14,18,.28);border-radius:22px;padding:14px">
<div style="font-weight:800;font-size:15px">Винил-вечер на крыше</div><div style="font-size:14px;font-weight:600">Сегодня · 20:00 · Лофт на Бауманской</div></div></div>
<div style="position:absolute;left:20px;right:20px;bottom:40px;display:flex;flex-direction:column;gap:6px">
<span class="btn" style="background:var(--lime);color:var(--ink);height:58px;border-radius:29px">Открыть чат</span>
<span class="btn" style="color:#fff;height:48px">Позже</span></div></div>"""


def screen_chat():
    return STATUS + f"""<div style="text-align:center;font-size:17px;font-weight:700;margin-top:-4px">Аня</div>
<div style="padding:14px 16px;display:flex;flex-direction:column;gap:8px">
<div style="background:#fff;border-radius:18px;padding:10px 14px"><div style="font-weight:800;font-size:14px">Винил-вечер на крыше</div><div class="small muted">Сегодня · 20:00 · Лофт на Бауманской</div></div>
<div class="muted" style="font-size:12px;font-weight:600;text-align:center;padding:6px 40px">Чат открылся, потому что вы оба захотели пойти вместе</div>
<div class="bubble out">Привет! Тоже иду первый раз. Где встретимся?</div>
<div class="bubble in">Привет! Давай у входа за 15 минут до начала?</div>
<div class="bubble out">Договорились. Я в жёлтом шарфе</div>
<div class="bubble in">Отлично, возьму пару пластинок — послушаем</div></div>
<div style="position:absolute;left:0;right:0;bottom:0;padding:8px 16px 34px;display:flex;gap:8px;background:var(--ground)">
<span style="flex:1;height:52px;border-radius:26px;background:#fff;display:flex;align-items:center;padding:0 16px;font-weight:600;color:#9a9da6">Сообщение</span>
<span style="width:52px;height:52px;border-radius:26px;background:var(--ink);display:grid;place-items:center"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round"><path d="M12 19V5M6 11l6-6 6 6"/></svg></span></div>"""


def screen_after():
    guests = [("А", "#FF6A2B", "Аня", True), ("К", "#C8F03C", "Кирилл", False), ("Д", "#FFC2DD", "Даша", True),
              ("М", "#BFD0FF", "Миша", False), ("Л", "#FFE08A", "Лера", False), ("Т", "#0E0E12", "Тимур", False)]
    tiles = "".join(f'<div class="guest{" on" if on else ""}">{ava(l, c, 56, "#fff" if c == "#0E0E12" else "#0E0E12")}'
                    f'<span style="font-size:13px;font-weight:800">{n}</span>{"<span class=tick>✓</span>" if on else ""}</div>'
                    for l, c, n, on in guests)
    return STATUS + f"""<div class="pad" style="display:flex;flex-direction:column;gap:12px">
<div class="row" style="gap:12px;align-items:center"><span class="navback" style="background:#fff">{BACK}</span><span class="badge ink">Вчера · Винил-вечер на крыше</span></div>
<div class="title" style="font-size:26px">С кем хочется увидеться ещё?</div>
<p class="muted" style="font-size:15px;line-height:1.4">Отметьте гостей вечера. Человек узнает об этом, только если отметит вас в ответ.</p>
<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px">{tiles}</div></div>
<div style="position:absolute;left:0;right:0;bottom:0;padding:12px 20px 34px;display:flex;flex-direction:column;gap:6px;align-items:center">
<span class="muted" style="font-size:13px;font-weight:700">Выбрано: 2 из 6</span>
<span class="btn" style="align-self:stretch;background:var(--ink);color:#fff;height:58px;border-radius:29px">Готово</span></div>"""


SLIDES = [
    ("1", "#2B4BFF", "#fff", "Афиша Москвы на каждый день", "Концерты, лекции, ужины, прогулки и вечеринки", screen_afisha),
    ("2", "#C8F03C", "#0E0E12", "Отметьте «Ищу компанию»", "Гости события увидят, что вы ищете, с кем пойти", screen_event),
    ("3", "#0E0E12", "#fff", "Посмотрите, кто ещё идёт", "Без свайпов — вас знакомит общее событие", screen_people),
    ("4", "#FF6A2B", "#0E0E12", "Чат — только при взаимном интересе", "Отказ никто не увидит", screen_match),
    ("5", "#2B4BFF", "#fff", "Договоритесь о встрече", "Где встретиться и во сколько", screen_chat),
    ("6", "#C8F03C", "#0E0E12", "Увидьтесь снова после вечера", "Отметьте, с кем хочется продолжить", screen_after),
]


def page(bg, fg, title, sub, screen):
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>
<div class="frame" style="background:{bg};color:{fg}"><div class="head"><h1>{title}</h1><p>{sub}</p></div>
<div class="phone"><div class="screen"><div class="inner">{screen()}</div></div></div></div></body></html>"""


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox", "--allow-file-access-from-files"])
        ctx = await browser.new_context(viewport={"width": 440, "height": 956}, device_scale_factor=3)
        pg = await ctx.new_page()
        for name, bg, fg, title, sub, screen in SLIDES:
            html = OUT / f"{name}.html"
            html.write_text(page(bg, fg, title, sub, screen), encoding="utf-8")
            await pg.goto(f"file://{html}")
            await pg.evaluate("document.fonts.ready")
            await pg.wait_for_timeout(300)
            await pg.screenshot(path=str(OUT / f"{name}.png"))
        await browser.close()


asyncio.run(main())
