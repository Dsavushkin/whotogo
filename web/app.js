/* Кто идёт — Telegram Mini App. One file, no build step. */
(() => {
'use strict';

const tg = window.Telegram && window.Telegram.WebApp;
const params = new URLSearchParams(location.search);
const $app = document.getElementById('app');
const $sheet = document.getElementById('sheet');
const $toast = document.getElementById('toast');
const state = { me: null, guest: false, dev: false, bot: 'whotogo', day: 'today', category: '', timer: null, token: 0, authMode: 'login' };
const inTelegram = !!(tg && tg.initData);
const store = {
  get token() { try { return localStorage.getItem('token') || ''; } catch (e) { return ''; } },
  set token(value) { try { value ? localStorage.setItem('token', value) : localStorage.removeItem('token'); } catch (e) { /* private mode */ } },
};

// ---------- helpers ----------
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const plural = (n, one, few, many) => {
  const a = Math.abs(n) % 100, b = a % 10;
  return a > 10 && a < 20 ? many : b === 1 ? one : b > 1 && b < 5 ? few : many;
};
const ICON = {
  back: '<svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg>',
  check: '<svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  send: '<svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>',
  more: '<svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>',
  pin: '<svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21s7-6.2 7-11.5a7 7 0 0 0-14 0C5 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/></svg>',
};
const MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const WEEKDAYS = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];
const cityDay = (shift) => new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Moscow' }).format(new Date(Date.now() + (shift || 0) * 864e5));

/** "2026-11-21T20:00+03:00" -> "Сегодня · 20:00" (the string is already in city time). */
function when(iso, withTime) {
  if (!iso) return '';
  const day = iso.slice(0, 10), time = iso.slice(11, 16);
  let label;
  if (day === cityDay(0)) label = 'Сегодня';
  else if (day === cityDay(1)) label = 'Завтра';
  else if (day === cityDay(-1)) label = 'Вчера';
  else {
    const [y, m, d] = day.split('-').map(Number);
    label = WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()] + ', ' + d + ' ' + MONTHS[m - 1];
  }
  return withTime === false ? label : label + ' · ' + time;
}
const ava = (person, size) => `<span class="ava ${size || ''} c${(person.id || 0) % 6}" aria-hidden="true">${esc((person.name || '?').trim().charAt(0).toUpperCase())}</span>`;
const who = (p) => esc(p.name) + (p.age ? ', ' + p.age : '');
const lookingText = (n) => n + ' ' + plural(n, 'ищет компанию', 'ищут компанию', 'ищут компанию');
const goingText = (n) => n + ' ' + plural(n, 'идёт', 'идут', 'идут');

function toast(text) {
  $toast.textContent = text;
  $toast.hidden = false;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => { $toast.hidden = true; }, 3200);
}
function haptic(kind) { try { tg && tg.HapticFeedback && tg.HapticFeedback.notificationOccurred(kind || 'success'); } catch (e) { /* old client */ } }

function sheet(html) {
  $sheet.innerHTML = `<div class="sheet" role="dialog" aria-modal="true">${html}</div>`;
  $sheet.hidden = false;
  const first = $sheet.querySelector('textarea, input, button');
  if (first) first.focus({ preventScroll: true });
}
function closeSheet() { $sheet.hidden = true; $sheet.innerHTML = ''; }
$sheet.addEventListener('click', (e) => { if (e.target === $sheet) closeSheet(); });

// ---------- server ----------
async function api(method, path, body) {
  const headers = { 'Content-Type': 'application/json' };
  if (inTelegram) headers.Authorization = 'tma ' + tg.initData;
  else if (store.token) headers.Authorization = 'Bearer ' + store.token;
  else if (state.dev && params.get('dev')) headers['X-Dev-User'] = params.get('dev');
  let response;
  try {
    response = await fetch('/api' + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  } catch (e) {
    throw new Error('Нет связи. Проверьте интернет и попробуйте ещё раз.');
  }
  if (response.status === 401) { const error = new Error('auth'); error.auth = true; throw error; }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(typeof detail === 'string' ? detail : 'Проверьте, что всё заполнено верно.');
  }
  return data;
}
const act = async (fn) => { try { return await fn(); } catch (e) { toast(e.message); return null; } };

// ---------- navigation ----------
const ROOT = ['', 'people', 'chats', 'profile'];
const route = () => location.hash.replace(/^#\/?/, '').split('/').filter(Boolean);
const go = (path) => { location.hash = '#/' + path; };
const back = () => (history.length > 1 ? history.back() : go(''));

function nav(active) {
  const item = (path, label) => `<button data-go="${path}" ${path === active ? 'aria-current="page"' : ''}>${label}</button>`;
  return `<nav class="nav" aria-label="Разделы">${item('', 'Афиша')}${item('people', 'Люди')}${item('chats', 'Чаты')}${item('profile', 'Профиль')}</nav>`;
}
const backBtn = (cls) => `<button class="round ${cls || ''}" data-back aria-label="Назад">${ICON.back}</button>`;
const empty = (title, text, action) => `<div class="empty"><h2 class="strong">${title}</h2><p class="muted">${text}</p>${action || ''}</div>`;

// ---------- screens ----------
const screens = {};

screens.afisha = async () => {
  const data = await api('GET', `/events?day=${state.day}${state.category ? '&category=' + state.category : ''}`);
  const titles = { today: 'Куда сегодня?', tomorrow: 'Куда завтра?', weekend: 'Куда на выходных?', week: 'Куда на неделе?' };
  const dayChip = (id, label) => `<button class="chip" data-day="${id}" aria-pressed="${state.day === id}">${label}</button>`;
  const catChip = (id, label) => `<button class="chip small" data-category="${id}" aria-pressed="${state.category === id}">${label}</button>`;
  const cards = data.events.map((e, i) => (i === 0 ? `
    <button class="hero" data-go="event/${e.id}">
      <div class="poster p0">
        <div class="between"><span class="badge">${when(e.starts_at)}</span><span class="badge dim">${esc(e.category_name)}</span></div>
        <h2 class="display">${esc(e.title)}</h2>
      </div>
      <div class="meta">
        <p class="small semi muted">${esc([e.place, e.price].filter(Boolean).join(' · '))}</p>
        <div class="between"><span class="small semi">${e.going ? goingText(e.going) : 'Станьте первым гостем'}</span>
        ${e.looking ? `<span class="looking">${lookingText(e.looking)}</span>` : ''}</div>
      </div>
    </button>` : `
    <button class="compact" data-go="event/${e.id}">
      <span class="tile display p${1 + (e.id % 5)}">${esc(e.category_name)}</span>
      <span class="col">
        <span class="tiny strong muted">${when(e.starts_at)}${e.price ? ' · ' + esc(e.price) : ''}</span>
        <h2>${esc(e.title)}</h2>
        ${e.looking ? `<span class="looking">${lookingText(e.looking)}</span>` : `<span class="small semi muted clip">${esc(e.place)}</span>`}
      </span>
    </button>`)).join('');
  return `<div class="screen with-nav">
    <header class="head">
      <div class="between"><div class="col" style="gap:2px"><span class="kicker">Москва</span><h1 class="display">${titles[state.day]}</h1></div>
        ${state.me ? '' : '<button class="chip" data-go="auth" style="background:var(--ink);color:#fff">Войти</button>'}</div>
      ${state.me ? '' : '<p class="note">Афиша Москвы и компания на вечер. Отметьте «Ищу компанию» на событии и посмотрите, кто ещё идёт.</p>'}
      <div class="chips">${dayChip('today', 'Сегодня')}${dayChip('tomorrow', 'Завтра')}${dayChip('weekend', 'Выходные')}${dayChip('week', 'Неделя')}</div>
      <div class="chips">${catChip('', 'Всё')}${Object.entries(data.categories).filter(([id]) => id !== 'other').map(([id, label]) => catChip(id, label)).join('')}</div>
    </header>
    <main class="body">${cards || empty('Пока пусто', 'На эти даты событий нет. Посмотрите другие дни.', '<button class="btn ink small" data-day="week">Вся неделя</button>')}</main>
    ${nav('')}</div>`;
};

screens.event = async (id) => {
  const e = await api('GET', '/events/' + id);
  state.event = e;
  const mine = e.my_status;
  const footer = e.started
    ? (mine ? `<button class="btn ink" data-go="after/${e.id}">С кем хочется увидеться ещё?</button>` : '')
    : `<button class="btn ${mine === 'going' ? 'lime' : 'soft'}" data-attend="${mine === 'going' ? 'none' : 'going'}">${mine === 'going' ? ICON.check + ' Иду' : 'Иду'}</button>
       <button class="btn ${mine === 'looking' ? 'lime' : 'ink'}" data-looking>${mine === 'looking' ? ICON.check + ' Ищу компанию' : 'Ищу компанию'}</button>`;
  return `<div class="screen" style="padding-top:0">
    <div class="event-top p0">
      <div class="between">${backBtn('ghost')}<span class="badge dim">${esc(e.category_name)}</span></div>
      <div><span class="badge">${when(e.starts_at)}</span><h1 class="display">${esc(e.title)}</h1></div>
    </div>
    <main class="body" style="padding-top:16px">
      <div class="facts">
        <div class="fact"><span class="tiny strong muted">Где</span><span class="semi">${esc(e.place || 'Уточняется')}</span>${e.address ? `<span class="small muted">${esc(e.address)}</span>` : ''}</div>
        <div class="fact"><span class="tiny strong muted">Билет</span><span class="semi">${esc(e.price || 'На сайте события')}</span></div>
      </div>
      ${e.description ? `<p>${esc(e.description)}</p>` : ''}
      <button class="card" data-go="event/${e.id}/people">
        <span class="between"><h2 class="strong" style="font-size:17px">Кто идёт</h2><span class="looking">${e.going ? 'Все ' + e.going : ''}</span></span>
        <span class="line">${e.faces.length ? `<span class="faces">${e.faces.map((f, i) => `<span class="ava s c${i % 6}">${esc(f)}</span>`).join('')}</span>` : ''}
        <span class="small semi">${e.looking ? e.looking + ' ' + plural(e.looking, 'человек ищет', 'человека ищут', 'человек ищут') + ', с кем пойти' : 'Пока никто не ищет компанию. Будьте первым.'}</span></span>
      </button>
      ${e.url ? `<button class="btn white small" data-link="${esc(e.url)}">Билеты и подробности</button>` : ''}
      ${e.source === 'timepad' ? '<p class="tiny muted">Источник: Timepad</p>' : ''}
    </main>
    ${footer ? `<footer class="foot row">${footer}</footer>` : ''}</div>`;
};

function personCard(p, eventId, eventLine) {
  const button = p.match_id
    ? `<button class="btn lime small" data-go="chat/${p.match_id}">Открыть чат</button>`
    : p.invited
      ? `<button class="btn soft small" disabled>${ICON.check} Вы предложили</button>`
      : `<button class="btn blue small" data-invite="${p.id}" data-event="${eventId}">Пойдём вместе</button>`;
  return `<article class="card">
    ${eventLine || ''}
    <div class="line" style="align-items:flex-start;gap:12px">${ava(p, 'l')}
      <div class="col"><h2 class="strong" style="font-size:18px">${who(p)}</h2>${(p.note || p.bio) ? `<p class="small">${esc(p.note || p.bio)}</p>` : ''}</div>
    </div>
    ${p.interests.length ? `<div class="tags">${p.interests.map((t) => `<span class="tag">${esc(t)}</span>`).join('')}</div>` : ''}
    ${button}
    <button class="btn text quiet" data-report="${p.id}">Пожаловаться</button>
  </article>`;
}
const RULE = '<p class="note">Чат откроется, только если вы оба нажали «Пойдём вместе». Отказ никто не увидит.</p>';

screens.eventPeople = async (id) => {
  const data = await api('GET', `/events/${id}/people`);
  return `<div class="screen">
    <header class="head"><div class="line" style="gap:12px">${backBtn()}
      <div class="col" style="gap:2px"><span class="kicker clip">${esc(data.event.title)} · ${when(data.event.starts_at, false).toLowerCase()}</span><h1 class="display" style="font-size:24px">Ищут компанию</h1></div></div>
      ${RULE}</header>
    <main class="body">${data.people.map((p) => personCard(p, id)).join('') || empty('Пока никого', 'Отметьте «Ищу компанию» на странице события, и другие гости увидят вас здесь.')}</main></div>`;
};

screens.people = async () => {
  const data = await api('GET', '/people');
  const cards = data.people.map((p) => personCard(p, p.event.id,
    `<button class="line small semi muted" data-go="event/${p.event.id}" style="text-align:left"><span class="badge ink">${when(p.event.starts_at)}</span><span class="clip">${esc(p.event.title)}</span></button>`)).join('');
  return `<div class="screen with-nav">
    <header class="head"><div class="col" style="gap:2px"><span class="kicker">На этой неделе</span><h1 class="display">Ищут компанию</h1></div>${RULE}</header>
    <main class="body">${cards || empty('Пока никого', 'Выберите событие в афише и отметьте «Ищу компанию» — так вас найдут.', '<button class="btn ink small" data-go="">Открыть афишу</button>')}</main>
    ${nav('people')}</div>`;
};

screens.match = async (id) => {
  const m = await api('GET', '/matches/' + id);
  const again = m.kind === 'again';
  return `<div class="screen accent">
    <div class="head">${backBtn('ghost')}</div>
    <main class="body" style="justify-content:center;gap:28px">
      <div class="line" style="justify-content:center;gap:0">${ava(state.me.id % 6 === m.other.id % 6 ? { name: state.me.name, id: state.me.id + 1 } : state.me, 'xl')}<span style="margin-left:-18px">${ava(m.other, 'xl')}</span></div>
      <div class="col" style="gap:10px;text-align:center"><h1 class="display" style="font-size:34px">${again ? 'Это взаимно' : 'Идёте вместе'}</h1>
      <p style="font-size:17px;font-weight:600">${esc(m.other.name)} ${again ? 'тоже хочет увидеться ещё.' : 'тоже хочет пойти с вами.'}<br>${again ? 'Напишите первым.' : 'Договоритесь, где встретиться.'}</p></div>
      <div style="background:rgba(14,14,18,.28);border-radius:22px;padding:14px;display:flex;gap:12px;align-items:center">
        <span class="round" style="border-radius:16px;color:var(--ink)">${ICON.pin}</span>
        <div class="col" style="gap:2px"><span class="strong">${esc(m.event.title)}</span><span class="small semi">${when(m.event.starts_at)}${m.event.place ? ' · ' + esc(m.event.place) : ''}</span></div>
      </div>
    </main>
    <footer class="foot"><button class="btn lime" data-replace="chat/${m.id}">Открыть чат</button><button class="btn text" data-go="">Позже</button></footer></div>`;
};

screens.after = async (id) => {
  const data = await api('GET', `/events/${id}/after`);
  const picked = data.guests.filter((g) => g.marked).length;
  return `<div class="screen">
    <header class="head" style="gap:10px"><div class="line" style="gap:12px">${backBtn()}<span class="badge ink clip">${when(data.event.starts_at, false)} · ${esc(data.event.title)}</span></div>
      <h1 class="display" style="font-size:26px">С кем хочется увидеться ещё?</h1>
      <p class="muted">Отметьте гостей вечера. Человек узнает об этом, только если отметит вас в ответ.</p></header>
    <main class="body">${data.guests.length ? `<div class="guests">${data.guests.map((g) => `
      <button class="guest" data-guest="${g.id}" aria-pressed="${g.marked}">${ava(g, 'l')}<span class="small strong clip" style="max-width:100%">${esc(g.name)}</span><span class="tick">${ICON.check}</span></button>`).join('')}</div>`
      : empty('Гостей пока нет', 'Отметки появятся, когда на событии отметится кто-то ещё.')}</main>
    ${data.guests.length ? `<footer class="foot"><p class="small semi muted" style="text-align:center" id="picked" data-total="${data.guests.length}">Выбрано: ${picked} из ${data.guests.length}</p>
      <button class="btn ink" data-after="${id}">Готово</button><button class="btn text muted" data-after="${id}" data-nobody>Никого не отмечать</button></footer>` : ''}</div>`;
};

screens.chats = async () => {
  const [data, mine] = await Promise.all([api('GET', '/matches'), api('GET', '/my/events')]);
  const prompts = mine.past.map((e) => `<button class="card" data-go="after/${e.id}" style="background:var(--lime)">
    <span class="tiny strong">${when(e.starts_at, false)} · ${esc(e.title)}</span><span class="strong" style="font-size:17px">С кем хочется увидеться ещё?</span></button>`).join('');
  const rows = data.matches.map((m) => `<button class="compact" data-go="chat/${m.id}" style="border-radius:24px">${ava(m.other, 'l')}
    <span class="col" style="flex:1"><span class="between"><span class="strong" style="font-size:17px">${esc(m.other.name)}</span><span class="tiny semi muted">${when(m.at, false)}</span></span>
    <span class="small semi muted clip">${m.last ? (m.last_mine ? 'Вы: ' : '') + esc(m.last) : esc(m.event.title)}</span></span></button>`).join('');
  return `<div class="screen with-nav"><header class="head"><h1 class="display">Чаты</h1></header>
    <main class="body">${prompts}${rows || (prompts ? '' : empty('Чатов пока нет', 'Чат открывается, когда вы и другой гость оба нажали «Пойдём вместе».', '<button class="btn ink small" data-go="people">Кто ищет компанию</button>'))}</main>${nav('chats')}</div>`;
};

const bubble = (m) => `<p class="msg ${m.mine ? 'out' : 'in'}" data-id="${m.id}">${esc(m.text)}</p>`;
screens.chat = async (id) => {
  const c = await api('GET', '/matches/' + id);
  state.chat = { id, last: c.messages.length ? c.messages[c.messages.length - 1].id : 0, other: c.other };
  const timer = state.timer = setInterval(async () => {
    if (!state.chat || state.chat.id !== id) return clearInterval(timer);
    try {
      const fresh = await api('GET', `/matches/${id}?after=${state.chat.last}`);
      addMessages(fresh.messages);
    } catch (e) { /* next tick will retry */ }
  }, 4000);
  const quick = c.messages.length ? '' : `<div class="chips" style="margin:0">${['Привет! Где встретимся?', 'У входа за 15 минут до начала', 'Я уже внутри'].map((t) => `<button class="chip small" data-quick="${esc(t)}">${esc(t)}</button>`).join('')}</div>`;
  return `<div class="screen" style="padding-top:0">
    <header class="chat-head">
      <div class="line" style="gap:12px">${backBtn('soft')}${ava(c.other, 'm')}
        <div class="col" style="gap:0;flex:1"><h1 class="strong" style="font-size:18px">${esc(c.other.name)}</h1><span class="small semi muted">${c.kind === 'again' ? 'взаимная отметка после вечера' : 'идёте вместе ' + when(c.event.starts_at, false).toLowerCase()}</span></div>
        <button class="round soft" data-report="${c.other.id}" aria-label="Пожаловаться или скрыть">${ICON.more}</button></div>
      <button class="chat-event" data-go="event/${c.event.id}" style="text-align:left"><span class="small strong">${esc(c.event.title)}</span><span class="small semi muted">${when(c.event.starts_at)}${c.event.place ? ' · ' + esc(c.event.place) : ''}</span></button>
    </header>
    <main class="msgs" id="msgs"><p class="sys">${c.kind === 'again' ? 'Чат открылся, потому что вы отметили друг друга после вечера' : 'Чат открылся, потому что вы оба захотели пойти вместе'}</p>${c.messages.map(bubble).join('')}</main>
    <div class="compose">${quick}<form id="send"><label style="flex:1"><span hidden>Сообщение</span><input class="input round-input" name="text" placeholder="Сообщение" autocomplete="off" maxlength="1000" enterkeyhint="send"></label>
      <button class="round" style="background:var(--ink);color:#fff;width:52px;height:52px;border-radius:26px" aria-label="Отправить">${ICON.send}</button></form></div></div>`;
};
function addMessages(list) {
  const box = document.getElementById('msgs');
  if (!box || !state.chat) return;
  list.forEach((m) => {
    if (m.id > state.chat.last) { box.insertAdjacentHTML('beforeend', bubble(m)); state.chat.last = m.id; }
  });
  if (list.length) window.scrollTo(0, document.body.scrollHeight);
}
async function sendMessage(text) {
  text = text.trim();
  if (!text || !state.chat) return;
  const sent = await act(() => api('POST', `/matches/${state.chat.id}/messages`, { text }));
  if (sent) { addMessages([sent]); const quick = document.querySelector('.compose .chips'); if (quick) quick.remove(); }
}

screens.auth = () => {
  const signup = state.authMode === 'signup';
  return `<div class="screen">
    <header class="head"><div>${backBtn()}</div><span class="kicker">Кто идёт · афиша и компания на вечер</span>
      <h1 class="display">${signup ? 'Новый аккаунт' : 'Вход'}</h1>
      <p class="muted">${signup ? 'Нужен, чтобы отмечаться на событиях и писать тем, с кем интерес взаимный.' : 'Войдите, чтобы отмечаться на событиях и видеть, кто ищет компанию.'}</p></header>
    <form class="body" id="auth" novalidate>
      <label class="field"><span>Почта</span><input class="input" name="email" type="email" inputmode="email" autocomplete="email" autocapitalize="none" required placeholder="you@example.com"></label>
      <label class="field"><span>Пароль</span><input class="input" name="password" type="password" autocomplete="${signup ? 'new-password' : 'current-password'}" required minlength="8" placeholder="${signup ? 'Не короче 8 символов' : 'Ваш пароль'}"></label>
      <p class="error" id="error" role="alert" hidden></p>
      <button class="btn ink">${signup ? 'Создать аккаунт' : 'Войти'}</button>
      <button type="button" class="btn text" data-auth-mode="${signup ? 'login' : 'signup'}">${signup ? 'У меня уже есть аккаунт' : 'Создать аккаунт'}</button>
      ${signup ? '<p class="small muted" style="text-align:center">Создавая аккаунт, вы принимаете <a href="/terms" target="_blank">соглашение</a> и <a href="/privacy" target="_blank">политику конфиденциальности</a>.</p>' : `<p class="small muted" style="text-align:center">Забыли пароль? Напишите нам, поможем: <a href="/privacy" target="_blank">контакты</a>.</p>`}
    </form></div>`;
};

const INTERESTS = ['музыка', 'кино', 'театр', 'настолки', 'бары', 'еда', 'вино', 'прогулки', 'спорт', 'бег', 'йога', 'танцы', 'искусство', 'книги', 'путешествия', 'фотография', 'стендап', 'наука', 'языки', 'игры'];
function profileForm(first) {
  const me = state.me, tgUser = (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) || {};
  const chosen = new Set(me.interests || []);
  return `<div class="screen">
    <header class="head">${first ? '<span class="kicker">Кто идёт · афиша и компания на вечер</span>' : `<div>${backBtn()}</div>`}
      <h1 class="display">${first ? 'Пара слов о вас' : 'Профиль'}</h1>
      ${first ? '<p class="muted">Это увидят гости событий, когда вы ищете компанию. Фото не нужно.</p>' : ''}</header>
    <form class="body" id="profile" novalidate>
      <label class="field"><span>Имя</span><input class="input" name="name" required maxlength="40" value="${esc(me.adult_ok ? me.name : (me.name && !/^User /.test(me.name) ? me.name : tgUser.first_name || ''))}" autocomplete="given-name"></label>
      <label class="field"><span>Возраст</span><input class="input" name="age" type="number" inputmode="numeric" min="18" max="99" required value="${me.age || ''}" placeholder="Например, 27"></label>
      <label class="field"><span>О себе</span><textarea class="input" name="bio" maxlength="300" placeholder="Что любите, с кем хотите пойти">${esc(me.bio)}</textarea></label>
      <div class="field"><span>Интересы, до пяти</span><div class="tags">${INTERESTS.map((t) => `<button type="button" class="chip small" data-interest aria-pressed="${chosen.has(t)}">${t}</button>`).join('')}</div></div>
      ${first ? '<label class="check"><input type="checkbox" name="adult"><span>Мне есть 18 лет. Принимаю <a href="/terms" target="_blank">пользовательское соглашение</a> и <a href="/privacy" target="_blank">политику конфиденциальности</a>.</span></label>' : ''}
      <p class="error" id="error" role="alert" hidden></p>
      <div style="flex:1"></div>
      <button class="btn ink">${first ? 'Открыть афишу' : 'Сохранить'}</button>
    </form></div>`;
}
screens.profileEdit = async () => profileForm(false);

screens.profile = async () => {
  const me = state.me, mine = await api('GET', '/my/events');
  const events = mine.upcoming.map((e) => `<button class="rowline" data-go="event/${e.id}"><span class="col" style="gap:0;flex:1"><span class="strong clip">${esc(e.title)}</span><span class="small semi muted">${when(e.starts_at)} · ${e.my_status === 'looking' ? 'ищу компанию' : 'иду'}</span></span></button>`).join('');
  return `<div class="screen with-nav"><header class="head"><h1 class="display">Профиль</h1></header>
    <main class="body">
      <section class="card"><div class="line" style="gap:14px">${ava(me, 'l')}<div class="col" style="gap:2px"><h2 class="strong" style="font-size:20px">${who(me)}</h2>${me.bio ? `<p class="small">${esc(me.bio)}</p>` : ''}</div></div>
        ${me.interests.length ? `<div class="tags">${me.interests.map((t) => `<span class="tag">${esc(t)}</span>`).join('')}</div>` : ''}
        <button class="btn soft small" data-go="profile/edit">Изменить</button></section>
      <section class="card"><h2 class="strong" style="font-size:17px">Мои события</h2>${events ? `<div class="rows">${events}</div>` : '<p class="small muted">Отметьте «Иду» или «Ищу компанию» на событии, и оно появится здесь.</p>'}</section>
      ${me.is_organizer || me.is_admin
        ? '<button class="btn ink small" data-go="org">Кабинет организатора</button>'
        : `<section class="card"><h2 class="strong" style="font-size:17px">Проводите вечера?</h2><p class="small muted">Добавьте своё событие в афишу и узнайте, сколько гостей нашли компанию. Напишите боту, подключим кабинет.</p><button class="btn soft small" data-tg="https://t.me/${state.bot}">Написать</button></section>`}
      <p class="small" style="text-align:center"><a href="/terms" target="_blank">Соглашение</a> · <a href="/privacy" target="_blank">Конфиденциальность</a></p>
      ${inTelegram ? '' : '<button class="btn text small" data-logout>Выйти</button>'}
      <button class="btn text small danger" data-delete>Удалить аккаунт</button>
    </main>${nav('profile')}</div>`;
};

screens.org = async () => {
  const data = await api('GET', '/org/events');
  const rows = data.events.map((e) => `<button class="card" data-go="org/${e.id}"><span class="tiny strong" style="color:#A9ADBA">${when(e.starts_at)}</span><span class="strong" style="font-size:17px">${esc(e.title)}</span>
    <span class="small semi" style="color:var(--lime)">${goingText(e.going)} · ${lookingText(e.looking)}</span></button>`).join('');
  return `<div class="screen dark"><header class="head"><div>${backBtn('ghost')}</div><span class="kicker">Кабинет организатора</span><h1 class="display" style="font-size:24px">Мои события</h1></header>
    <main class="body">${rows || empty('Событий пока нет', '<span style="color:#A9ADBA">Добавьте первое — оно сразу появится в афише.</span>')}</main>
    <footer class="foot"><button class="btn blue" data-go="org/new">Новое событие</button></footer></div>`;
};

screens.orgNew = async () => {
  const cats = (await api('GET', '/events?day=today')).categories;
  return `<div class="screen dark"><header class="head"><div>${backBtn('ghost')}</div><h1 class="display" style="font-size:24px">Новое событие</h1></header>
    <form class="body" id="event" novalidate>
      <label class="field"><span>Название</span><input class="input" name="title" required maxlength="120" placeholder="Винил-вечер на крыше"></label>
      <label class="field"><span>Дата и время</span><input class="input" name="starts_at" type="datetime-local" required></label>
      <label class="field"><span>Формат</span><select class="input" name="category">${Object.entries(cats).map(([id, label]) => `<option value="${id}">${label}</option>`).join('')}</select></label>
      <label class="field"><span>Место</span><input class="input" name="place" required maxlength="120" placeholder="Лофт на Бауманской"></label>
      <label class="field"><span>Адрес</span><input class="input" name="address" maxlength="200" placeholder="Улица, дом"></label>
      <label class="field"><span>Цена</span><input class="input" name="price" maxlength="60" placeholder="1 200 ₽ или Бесплатно"></label>
      <label class="field"><span>Ссылка на билеты</span><input class="input" name="url" type="url" maxlength="300" placeholder="https://"></label>
      <label class="field"><span>Сколько мест</span><input class="input" name="capacity" type="number" inputmode="numeric" min="1" placeholder="Необязательно"></label>
      <label class="field"><span>Описание</span><textarea class="input" name="description" maxlength="2000" placeholder="Что будет, для кого, можно ли прийти одному"></textarea></label>
      <p class="error" id="error" role="alert" hidden></p>
      <button class="btn blue">Опубликовать</button>
    </form></div>`;
};

screens.orgEvent = async (id) => {
  const s = await api('GET', '/org/events/' + id);
  const guests = s.guests.map((g) => `<button class="rowline" data-checkin="${g.id}" data-event="${id}" aria-pressed="${g.checked_in}">${ava(g, 'm')}<span class="semi" style="flex:1">${esc(g.name)}</span><span class="small semi" style="color:${g.checked_in ? 'var(--lime)' : '#A9ADBA'}">${g.checked_in ? 'на месте' : 'ждём'}</span></button>`).join('');
  return `<div class="screen dark"><header class="head" style="gap:6px"><div>${backBtn('ghost')}</div><span class="kicker">Кабинет организатора</span><h1 class="display" style="font-size:24px">${esc(s.event.title)}</h1><span class="small semi" style="color:#A9ADBA">${when(s.event.starts_at)}${s.event.place ? ' · ' + esc(s.event.place) : ''}</span></header>
    <main class="body">
      <div class="stats">
        <div class="stat"><b>${s.going}</b><span>${plural(s.going, 'гость отметился', 'гостя отметились', 'гостей отметились')}${s.event.capacity ? ' из ' + s.event.capacity : ''}</span></div>
        <div class="stat"><b>${s.checked_in}</b><span>уже на месте</span></div>
        <div class="stat"><b>${s.looking}</b><span>искали компанию</span></div>
        <div class="stat lime"><b>${s.pairs}</b><span>${plural(s.pairs, 'пара договорилась', 'пары договорились', 'пар договорились')}</span></div>
      </div>
      <section class="card"><h2 class="strong" style="font-size:16px">Гости</h2>${guests ? `<div class="rows">${guests}</div>` : '<p class="small" style="color:#A9ADBA">Пока никто не отметился. Нажмите на гостя, когда он придёт.</p>'}</section>
      <p class="small" style="color:#A9ADBA">На следующий день гости получат вопрос «С кем хочется увидеться ещё?». Вы увидите только число взаимных отметок, без имён.</p>
    </main></div>`;
};

// ---------- render ----------
async function render() {
  clearInterval(state.timer);
  state.chat = null;
  if (route()[0] === 'match') $toast.hidden = true;
  closeSheet();
  const token = ++state.token;
  const [a, b, c] = route();
  if (tg && tg.BackButton && inTelegram) { try { ROOT.includes(a || '') && !b ? tg.BackButton.hide() : tg.BackButton.show(); } catch (e) { /* old client */ } }
  let html;
  try {
    if (!state.me && !state.guest) {
      try { state.me = await api('GET', '/me'); } catch (e) {
        if (!e.auth) throw e;
        store.token = '';
        state.guest = true;
      }
    }
    const open = !a || (a === 'event' && !c);  // pages a guest may see
    if (!state.me && a === 'auth') html = screens.auth();
    else if (!state.me && !open) { state.returnTo = [a, b, c].filter(Boolean).join('/'); history.replaceState(null, '', '#/auth'); html = screens.auth(); }
    else if (state.me && a === 'auth') { history.replaceState(null, '', '#/'); html = await screens.afisha(); }
    else if (state.me && !state.me.adult_ok) html = profileForm(true);
    else if (!a) html = await screens.afisha();
    else if (a === 'event' && c === 'people') html = await screens.eventPeople(b);
    else if (a === 'event') html = await screens.event(b);
    else if (a === 'people') html = await screens.people();
    else if (a === 'match') html = await screens.match(b);
    else if (a === 'after') html = await screens.after(b);
    else if (a === 'chats') html = await screens.chats();
    else if (a === 'chat') html = await screens.chat(b);
    else if (a === 'profile') html = b === 'edit' ? await screens.profileEdit() : await screens.profile();
    else if (a === 'org') html = b === 'new' ? await screens.orgNew() : b ? await screens.orgEvent(b) : await screens.org();
    else html = await screens.afisha();
  } catch (e) {
    if (e.auth) { store.token = ''; state.me = null; state.guest = true; }
    html = e.auth
      ? screens.auth()
      : `<div class="screen"><main class="body" style="justify-content:center">${empty('Не получилось загрузить', esc(e.message), '<button class="btn ink small" data-reload>Повторить</button><button class="btn text small" data-go="">На главную</button>')}</main></div>`;
  }
  if (token !== state.token) return;
  $app.innerHTML = html;
  if (a === 'chat') window.scrollTo(0, document.body.scrollHeight); else window.scrollTo(0, 0);
}

// ---------- actions ----------
function formError(text) { const el = document.getElementById('error'); if (el) { el.textContent = text; el.hidden = !text; } }

function reportSheet(userId) {
  sheet(`<h2 class="strong">Пожаловаться</h2><p class="muted">Этот человек больше не увидит вас, а вы — его. Жалобу прочитает команда.</p>
    <label class="field"><span>Что случилось</span><textarea class="input" id="reason" maxlength="500" placeholder="Необязательно"></textarea></label>
    <button class="btn ink" data-report-send="${userId}">Скрыть и пожаловаться</button><button class="btn text" data-close>Отмена</button>`);
}

document.addEventListener('click', async (event) => {
  const el = event.target.closest('button, a.btn');
  if (!el) return;
  const d = el.dataset;
  if ('back' in d) return back();
  if ('close' in d) return closeSheet();
  if ('reload' in d) return render();
  if (d.go === 'auth') state.returnTo = route().join('/');
  if ('go' in d) return route().join('/') === d.go ? render() : go(d.go);
  if ('replace' in d) { history.replaceState(null, '', '#/' + d.replace); return render(); }
  if (d.day) { state.day = d.day; return render(); }
  if ('category' in d) { state.category = d.category; return render(); }
  if (d.link) return tg && tg.openLink ? tg.openLink(d.link) : window.open(d.link, '_blank', 'noopener');
  if (d.tg) return tg && tg.openTelegramLink ? tg.openTelegramLink(d.tg) : window.open(d.tg, '_blank', 'noopener');
  if ('interest' in d) {
    const on = el.getAttribute('aria-pressed') === 'true';
    if (!on && document.querySelectorAll('[data-interest][aria-pressed=true]').length >= 5) return toast('Можно выбрать до пяти');
    return el.setAttribute('aria-pressed', String(!on));
  }
  if (d.authMode) { state.authMode = d.authMode; return render(); }
  if ('logout' in d) {
    await act(() => api('POST', '/auth/logout'));
    store.token = ''; state.me = null; state.guest = true;
    history.replaceState(null, '', '#/');
    return render();
  }
  if ((d.attend || 'looking' in d) && !state.me) { state.returnTo = route().join('/'); return go('auth'); }
  if (d.attend) {
    const id = route()[1];
    if (await act(() => api('POST', `/events/${id}/attend`, { status: d.attend }))) { if (d.attend !== 'none') haptic(); render(); }
    return;
  }
  if ('looking' in d) {
    const e = state.event;
    return sheet(`<h2 class="strong">Ищу компанию</h2><p class="muted">Вас увидят гости этого события. Напишите пару слов — так проще откликнуться.</p>
      <label class="field"><span>Сообщение гостям</span><textarea class="input" id="note" maxlength="200" placeholder="Иду первый раз, хочу компанию из 2–3 человек">${esc(e.my_note)}</textarea></label>
      <button class="btn ink" data-looking-save="${e.id}">${e.my_status === 'looking' ? 'Сохранить' : 'Показать меня гостям'}</button>
      ${e.my_status === 'looking' ? `<button class="btn text danger" data-looking-stop="${e.id}">Больше не ищу</button>` : '<button class="btn text" data-close>Отмена</button>'}`);
  }
  if (d.lookingSave) {
    const note = document.getElementById('note').value;
    if (await act(() => api('POST', `/events/${d.lookingSave}/attend`, { status: 'looking', note }))) { haptic(); closeSheet(); go(`event/${d.lookingSave}/people`); }
    return;
  }
  if (d.lookingStop) {
    if (await act(() => api('POST', `/events/${d.lookingStop}/attend`, { status: 'going' }))) render();
    return;
  }
  if (d.invite) {
    el.disabled = true;
    const result = await act(() => api('POST', `/events/${d.event}/invite/${d.invite}`));
    if (!result) { el.disabled = false; return; }
    if (result.match_id) { haptic(); return go('match/' + result.match_id); }
    el.className = 'btn soft small';
    el.innerHTML = ICON.check + ' Вы предложили';
    return toast('Если это взаимно, откроется чат');
  }
  if (d.guest) {
    el.setAttribute('aria-pressed', String(el.getAttribute('aria-pressed') !== 'true'));
    const picked = document.getElementById('picked');
    if (picked) picked.textContent = `Выбрано: ${document.querySelectorAll('[data-guest][aria-pressed=true]').length} из ${picked.dataset.total}`;
    return;
  }
  if (d.after) {
    const ids = 'nobody' in d ? [] : [...document.querySelectorAll('[data-guest][aria-pressed=true]')].map((g) => Number(g.dataset.guest));
    const result = await act(() => api('POST', `/events/${d.after}/after`, { user_ids: ids }));
    if (!result) return;
    if (result.matches.length) { haptic(); history.replaceState(null, '', '#/match/' + result.matches[0]); return render(); }
    toast(ids.length ? 'Сохранено. Если отметка взаимная, придёт сообщение.' : 'Хорошо, никого не отмечаем');
    history.replaceState(null, '', '#/chats');
    return render();
  }
  if (d.quick) return sendMessage(d.quick);
  if (d.report) return reportSheet(d.report);
  if (d.reportSend) {
    const reason = document.getElementById('reason').value;
    if (await act(() => api('POST', `/users/${d.reportSend}/report`, { reason, block: true }))) {
      closeSheet(); toast('Скрыли. Спасибо, что сообщили.');
      route()[0] === 'chat' ? go('chats') : render();
    }
    return;
  }
  if (d.checkin) {
    if (await act(() => api('POST', `/org/events/${d.event}/checkin/${d.checkin}`))) render();
    return;
  }
  if ('delete' in d) {
    return sheet(`<h2 class="strong">Удалить аккаунт?</h2><p class="muted">Профиль, отметки и переписка удалятся без возможности восстановления.</p>
      <button class="btn ink" data-delete-yes>Удалить всё</button><button class="btn text" data-close>Отмена</button>`);
  }
  if ('deleteYes' in d) {
    if (await act(() => api('DELETE', '/me'))) { store.token = ''; state.me = null; state.guest = !inTelegram; closeSheet(); history.replaceState(null, '', '#/'); render(); }
  }
});

document.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.target, f = new FormData(form);
  if (form.id === 'send') {
    const text = String(f.get('text'));
    form.reset();
    return sendMessage(text);
  }
  if (form.id === 'auth') {
    const email = String(f.get('email')).trim(), password = String(f.get('password'));
    const signup = state.authMode === 'signup';
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return formError('Проверьте адрес почты.');
    if (password.length < 8) return formError(signup ? 'Пароль должен быть не короче 8 символов.' : 'Почта или пароль не подходят.');
    try {
      const answer = await api('POST', signup ? '/auth/register' : '/auth/login', { email, password });
      store.token = answer.token;
    } catch (e) { return formError(e.auth ? 'Почта или пароль не подходят.' : e.message); }
    state.me = null; state.guest = false;
    history.replaceState(null, '', '#/' + (state.returnTo && state.returnTo !== 'auth' ? state.returnTo : ''));
    state.returnTo = '';
    return render();
  }
  if (form.id === 'profile') {
    const first = !state.me.adult_ok, age = Number(f.get('age'));
    if (!String(f.get('name')).trim()) return formError('Напишите, как вас зовут.');
    if (!age || age < 18) return formError('Сервис только для тех, кому есть 18 лет.');
    if (age > 99) return formError('Проверьте возраст.');
    if (first && !f.get('adult')) return formError('Подтвердите возраст и согласие с правилами.');
    const interests = [...form.querySelectorAll('[data-interest][aria-pressed=true]')].map((b) => b.textContent);
    try {
      state.me = await api('PUT', '/me', { name: String(f.get('name')).trim(), age, bio: String(f.get('bio')), interests, adult_ok: true });
    } catch (e) { return formError(e.message); }
    if (first) return render();
    toast('Сохранено');
    return back();
  }
  if (form.id === 'event') {
    const body = Object.fromEntries([...f.entries()].map(([k, v]) => [k, String(v).trim()]));
    if (body.title.length < 3) return formError('Добавьте название.');
    if (!body.starts_at) return formError('Укажите дату и время.');
    if (body.place.length < 2) return formError('Укажите место.');
    body.capacity = body.capacity ? Number(body.capacity) : null;
    try {
      const created = await api('POST', '/org/events', body);
      history.replaceState(null, '', '#/org/' + created.id);
      toast('Событие в афише');
      return render();
    } catch (e) { return formError(e.message); }
  }
});

// ---------- start ----------
function deepLink() {
  const target = params.get('go') || (tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param) || '';
  const m = /^(chat|after|event|match)-(\d+)$/.exec(target);
  if (m) return `${m[1]}/${m[2]}`;
  return target === 'org' ? 'org' : '';
}
async function start() {
  if (tg) {
    try {
      tg.ready(); tg.expand();
      tg.setHeaderColor && tg.setHeaderColor('#F3F4F6');
      tg.setBackgroundColor && tg.setBackgroundColor('#F3F4F6');
      tg.BackButton && tg.BackButton.onClick(back);
      tg.disableVerticalSwipes && tg.disableVerticalSwipes();
    } catch (e) { /* older Telegram */ }
  }
  try { const config = await (await fetch('/api/config')).json(); state.bot = config.bot || state.bot; state.dev = !!config.dev; } catch (e) { /* default */ }
  const target = deepLink();
  if (target && !location.hash) {
    history.replaceState(null, '', '#/');
    location.hash = '#/' + target;  // keeps the afisha underneath for «назад»
    window.addEventListener('hashchange', render);
    return;  // the hash change draws the screen
  }
  window.addEventListener('hashchange', render);
  render();
}
start();
})();
