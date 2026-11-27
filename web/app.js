/* Кто идёт — Telegram Mini App. One file, no build step. */
(() => {
'use strict';

const tg = window.Telegram && window.Telegram.WebApp;
const params = new URLSearchParams(location.search);
const $app = document.getElementById('app');
const $sheet = document.getElementById('sheet');
const $toast = document.getElementById('toast');
const state = { me: null, guest: false, dev: false, bot: 'whotogobot', day: 'today', category: '', timer: null, token: 0, authMode: 'login', girls: false };
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
/** Inline style with the event poster; a dark veil keeps white text readable. */
const bg = (url, plain) => {
  if (!/^https:\/\/[^\s"'()]+$/.test(url || '')) return '';
  return ` style="background-image:${plain ? '' : 'linear-gradient(rgba(14,14,18,.2),rgba(14,14,18,.78)),'}url('${esc(url)}')"`;
};
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

/** Small marks on an afisha card: friends who go and the group-ticket offer. */
const extras = (e) => (e.friends || e.group_deal || e.gathering ? `<span class="marks">${e.gathering ? '<span class="mark gather">👋 Сбор участника</span>' : ''}${e.friends ? `<span class="mark friends">👋 ${e.friends} ${plural(e.friends, 'друг', 'друга', 'друзей')}</span>` : ''}${e.group_deal ? `<span class="mark deal">🎟 ${esc(e.group_deal)}</span>` : ''}</span>` : '');

const localDay = () => new Date().toDateString();
const CAT_ICON = { quiz: '🧠', poker: '♠️', mafia: '🎭', quest: '🗝' };
screens.afisha = async () => {
  // Late evening nothing is left today: open tomorrow and hide «Сегодня» until the date changes.
  if (state.noToday && state.noToday !== localDay()) state.noToday = '';
  if (state.noToday && state.day === 'today') state.day = 'tomorrow';
  let data = await api('GET', `/events?day=${state.day}${state.category ? '&category=' + state.category : ''}`);
  if (state.day === 'today' && !data.events.length) {
    const all = state.category ? await api('GET', '/events?day=today') : data;
    if (!all.events.length) {
      state.noToday = localDay();
      state.day = 'tomorrow';
      data = await api('GET', `/events?day=tomorrow${state.category ? '&category=' + state.category : ''}`);
    }
  }
  const titles = { today: 'Куда сегодня?', tomorrow: 'Куда завтра?', weekend: 'Куда на выходных?', week: 'Куда на неделе?' };
  const dayChip = (id, label) => `<button class="chip" data-day="${id}" aria-pressed="${state.day === id}">${label}</button>`;
  const catChip = (id, label) => `<button class="chip small" data-category="${id}" aria-pressed="${state.category === id}">${label}</button>`;
  // The big card on top goes to an event with a poster, if one is near the start of the list.
  const lead = data.events.slice(0, 12).findIndex((e) => e.image && e.looking === (data.events[0] || {}).looking);
  if (lead > 0) data.events.unshift(data.events.splice(lead, 1)[0]);
  const cards = data.events.map((e, i) => (i === 0 ? `
    <button class="hero" data-go="event/${e.id}">
      <div class="poster p0${e.image ? ' photo' : ''}"${bg(e.image)}>
        <div class="between"><span class="badge">${when(e.starts_at)}</span><span class="badge dim">${esc(e.category_name)}</span></div>
        <h2 class="display">${esc(e.title)}</h2>
      </div>
      <div class="meta">
        <p class="small semi muted">${esc([e.place, e.price].filter(Boolean).join(' · '))}</p>
        <div class="between"><span class="small semi">${e.going ? goingText(e.going) : 'Станьте первым гостем'}</span>
        ${e.looking ? `<span class="looking">${lookingText(e.looking)}</span>` : ''}</div>
        ${extras(e)}
      </div>
    </button>` : `
    <button class="compact" data-go="event/${e.id}">
      ${e.image ? `<span class="tile photo"${bg(e.image, true)} role="img" aria-label="${esc(e.category_name)}"></span>` : `<span class="tile display p${1 + (e.id % 5)}">${esc(e.category_name)}</span>`}
      <span class="col">
        <span class="tiny strong muted">${when(e.starts_at)}${e.price ? ' · ' + esc(e.price) : ''}</span>
        <h2>${esc(e.title)}</h2>
        ${e.looking ? `<span class="looking">${lookingText(e.looking)}</span>` : `<span class="small semi muted clip">${esc(e.place)}</span>`}
        ${extras(e)}
      </span>
    </button>`)).join('');
  return `<div class="screen with-nav">
    <header class="head">
      <div class="between"><div class="col" style="gap:2px"><span class="kicker">Москва</span><h1 class="display">${titles[state.day]}</h1></div>
        ${state.me ? '<button class="chip small invite-chip" data-invite-friends>👋 Позвать друга</button>' : '<button class="chip" data-go="auth" style="background:var(--ink);color:#fff">Войти</button>'}</div>
      ${state.me ? '' : '<p class="note">Афиша Москвы и компания на вечер. Отметьте «Ищу компанию» на событии и посмотрите, кто ещё идёт.</p>'}
      <div class="chips">${state.noToday ? '' : dayChip('today', 'Сегодня')}${dayChip('tomorrow', 'Завтра')}${dayChip('weekend', 'Выходные')}${dayChip('week', 'Неделя')}</div>
      <div class="chips">${catChip('', 'Всё')}${catChip(data.gatherings || 'sbory', '👋 Сборы')}${Object.entries(data.categories).filter(([id]) => id !== 'other').map(([id, label]) => catChip(id, (CAT_ICON[id] ? CAT_ICON[id] + ' ' : '') + label)).join('')}</div>
      <button class="btn white small gather-btn" data-go="${state.me ? 'gather' : 'auth'}">＋ Свой сбор: квест, падел, покер…</button>
    </header>
    <main class="body">${cards || (state.category === 'sbory'
      ? empty('Сборов пока нет', 'Соберите компанию сами: квест, падел, волейбол, покер — всё, куда не пойдёшь один.', `<button class="btn ink small" data-go="${state.me ? 'gather' : 'auth'}">＋ Свой сбор</button>`)
      : empty('Пока пусто', 'На эти даты событий нет. Посмотрите другие дни.', '<button class="btn ink small" data-day="week">Вся неделя</button>'))}</main>
    ${nav('')}</div>`;
};

function gatheringCard(e) {
  const g = e.gathering;
  const host = g.host ? `<span class="line">${ava(g.host, 's')}<span class="small semi">Собирает ${esc(g.host.name)}${g.host.age ? ', ' + g.host.age : ''}</span></span>` : '';
  const places = g.left ? `Свободно ${g.left} ${plural(g.left, 'место', 'места', 'мест')} из ${g.limit - 1}` : 'Мест пока нет — можно встать в очередь';
  return `<div class="card company gather">
    <span class="kicker">👋 Свой сбор</span>
    ${host}
    <span class="small semi">${places}. Присоединитесь — откроется общий чат с организатором сбора.</span>
    ${e.waiting ? '<span class="looking">Вы в очереди — сообщим, если место освободится</span>' : `<button class="btn ink small" data-company="${e.id}">${g.left ? 'Присоединиться' : 'Встать в очередь'}</button>`}</div>`;
}

function companyCard(e) {
  if (e.gathering && !e.group) return gatheringCard(e);
  const quiz = e.category === 'quiz';
  const what = quiz ? 'команду' : 'компанию';
  const faces = (list) => `<span class="faces">${list.slice(0, 4).map((p) => ava(p, 's')).join('')}</span>`;
  if (e.group) {
    const names = e.group.others.map((p) => esc(p.name)).join(', ');
    return `<button class="card company ready" data-go="group/${e.group.id}">
      <span class="between"><span class="kicker">👥 Ваша ${quiz ? 'команда' : 'компания'}</span><span class="badge ink">${e.group.size} ${plural(e.group.size, 'человек', 'человека', 'человек')}</span></span>
      <span class="line">${faces(e.group.others)}<span class="small semi clip">Вы${names ? ', ' + names : ''}</span></span>
      ${e.group.captain_id ? `<span class="small semi">⭐ ${e.group.captain_id === state.me.id ? (quiz ? 'Вы капитан команды' : 'Вы капитан компании') : 'Капитан: ' + esc((e.group.others.find((p) => p.id === e.group.captain_id) || {}).name || '')}</span>` : ''}
      ${e.group_deal ? `<span class="mark deal">🎟 ${esc(e.group_deal)} — промокод в чате</span>` : ''}
      <span class="btn lime small">Открыть чат ${quiz ? 'команды' : 'компании'}</span></button>`;
  }
  if (e.started) return '';
  if (e.waiting) {
    return `<div class="card company">
      <span class="kicker">👥 Собираем ${what}</span>
      <span class="semi">${e.waiting_count ? `Кроме вас ждут ещё ${e.waiting_count}. ` : ''}Как только наберётся 3 человека, откроем общий чат и пришлём уведомление.</span>
      <span class="tiny semi muted">Ближе к началу хватит и двоих.</span>
      <button class="btn text small danger" data-company-stop="${e.id}">Не собирать</button></div>`;
  }
  if (quiz) {
    return `<div class="card company quiz">
    <span class="kicker">🧠 Команда на квиз</span>
    <span class="strong" style="font-size:18px">Не с кем играть?</span>
    <span class="small semi">Соберём команду из 3–5 человек, которые тоже идут на эту игру, и откроем общий чат: придумаете название и договоритесь о встрече.</span>
    ${e.group_deal ? `<span class="mark deal">🎟 Командам — ${esc(e.group_deal)}</span>` : ''}
    ${e.waiting_count ? `<span class="looking">Уже ждут: ${e.waiting_count}</span>` : ''}
    <button class="btn ink small" data-company="${e.id}">Соберите мне команду</button></div>`;
  }
  return `<div class="card company">
    <span class="kicker">👥 Компания на вечер</span>
    <span class="strong" style="font-size:18px">Не хочется вдвоём с незнакомцем?</span>
    <span class="small semi">Соберём компанию из 3–5 человек, которые тоже идут, и откроем общий чат. С компанией проще и не похоже на свидание.</span>
    ${e.group_deal ? `<span class="mark deal">🎟 Компании — ${esc(e.group_deal)}</span>` : ''}
    ${e.waiting_count ? `<span class="looking">Уже ждут: ${e.waiting_count}</span>` : ''}
    <button class="btn ink small" data-company="${e.id}">Соберите мне компанию</button></div>`;
}

screens.event = async (id) => {
  const e = await api('GET', '/events/' + id);
  state.event = e;
  const mine = e.my_status;
  const footer = e.started
    ? (mine ? `<button class="btn ink" data-go="after/${e.id}">С кем хочется увидеться ещё?</button>` : '')
    : e.gathering
      ? (e.group ? `<button class="btn lime" data-go="group/${e.group.id}">Открыть чат сбора</button>`
        : e.waiting ? '' : `<button class="btn ink" data-company="${e.id}">${e.gathering.left ? 'Присоединиться' : 'Встать в очередь'}</button>`)
    : `<button class="btn ${mine === 'going' ? 'lime' : 'soft'}" data-attend="${mine === 'going' ? 'none' : 'going'}">${mine === 'going' ? ICON.check + ' Иду' : 'Иду'}</button>
       <button class="btn ${mine === 'looking' ? 'lime' : 'ink'}" data-looking>${mine === 'looking' ? ICON.check + ' Ищу компанию' : 'Ищу компанию'}</button>`;
  return `<div class="screen" style="padding-top:0">
    <div class="event-top p0${e.image ? ' photo' : ''}"${bg(e.image)}>
      <div class="between">${backBtn('ghost')}<span class="badge dim">${esc(e.category_name)}</span></div>
      <div><span class="badge">${when(e.starts_at)}</span><h1 class="display">${esc(e.title)}</h1></div>
    </div>
    <main class="body" style="padding-top:16px">
      <div class="facts">
        <div class="fact"><span class="tiny strong muted">Где</span><span class="semi">${esc(e.place || 'Уточняется')}</span>${e.address ? `<span class="small muted">${esc(e.address)}</span>` : ''}</div>
        <div class="fact"><span class="tiny strong muted">${e.gathering ? 'Стоимость' : 'Билет'}</span><span class="semi">${esc(e.price || (e.gathering ? 'Договоритесь в чате' : 'На сайте события'))}</span></div>
      </div>
      ${e.description ? `<p>${esc(e.description)}</p>` : ''}
      ${e.friends && e.friends.length ? `<div class="card friends-going"><span class="line"><span class="faces">${e.friends.slice(0, 4).map((p) => ava(p, 's')).join('')}</span><span class="small semi">👋 ${e.friends.length === 1 ? esc(e.friends[0].name) + ' тоже идёт' : 'Идут ваши друзья: ' + e.friends.map((p) => esc(p.name)).join(', ')}</span></span></div>` : ''}
      ${companyCard(e)}
      <button class="card" data-go="event/${e.id}/people">
        <span class="between"><h2 class="strong" style="font-size:17px">Кто идёт</h2><span class="looking">${e.going ? 'Все ' + e.going : ''}</span></span>
        <span class="line">${e.faces.length ? `<span class="faces">${e.faces.map((f, i) => `<span class="ava s c${i % 6}">${esc(f)}</span>`).join('')}</span>` : ''}
        <span class="small semi">${e.looking ? e.looking + ' ' + plural(e.looking, 'человек ищет', 'человека ищут', 'человек ищут') + ', с кем пойти' : 'Пока никто не ищет компанию. Будьте первым.'}</span></span>
      </button>
      ${e.started ? '' : '<button class="btn white small" data-share>Позвать друга</button>'}
      ${e.url ? `<button class="btn white small" data-link="${esc(e.url)}">Билеты и подробности</button>` : ''}
      ${e.source === 'timepad' ? '<p class="tiny muted">Источник: Timepad</p>' : ''}
      ${e.gathering ? '<p class="tiny muted">Сбор создал участник «Кто идёт». Встречайтесь в людных местах и не переводите деньги незнакомым заранее.</p>' : ''}
      ${e.gathering && e.gathering.mine && !e.started ? `<button class="btn text small danger" data-gather-cancel="${e.id}">Отменить сбор</button>` : ''}
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
      <div class="col"><h2 class="strong" style="font-size:18px">${who(p)}</h2>${p.girls_only ? '<span class="badge girls">👭 только с девушками</span>' : ''}${(p.note || p.bio) ? `<p class="small">${esc(p.note || p.bio)}</p>` : ''}</div>
    </div>
    ${p.interests.length ? `<div class="tags">${p.interests.map((t) => `<span class="tag">${esc(t)}</span>`).join('')}</div>` : ''}
    ${button}
    <button class="btn text quiet" data-report="${p.id}">Пожаловаться</button>
  </article>`;
}
const RULE = '<p class="note">Чат откроется, только если вы оба нажали «Пойдём вместе». Отказ никто не увидит.</p>';
const isGirl = () => state.me && state.me.gender === 'f';
const girlsQuery = () => (isGirl() && state.girls ? '?girls=1' : '');
const girlsChip = () => (isGirl() ? `<div class="chips" style="margin:0;padding:0"><button class="chip small" data-girls aria-pressed="${state.girls}">👭 Только девушки</button></div>` : '');

screens.eventPeople = async (id) => {
  const data = await api('GET', `/events/${id}/people` + girlsQuery());
  return `<div class="screen">
    <header class="head"><div class="line" style="gap:12px">${backBtn()}
      <div class="col" style="gap:2px"><span class="kicker clip">${esc(data.event.title)} · ${when(data.event.starts_at, false).toLowerCase()}</span><h1 class="display" style="font-size:24px">Ищут компанию</h1></div></div>
      ${RULE}${girlsChip()}</header>
    <main class="body">${data.people.map((p) => personCard(p, id)).join('') || empty('Пока никого', 'Отметьте «Ищу компанию» на странице события, и другие гости увидят вас здесь.')}</main></div>`;
};

screens.people = async () => {
  const data = await api('GET', '/people' + girlsQuery());
  const cards = data.people.map((p) => personCard(p, p.event.id,
    `<button class="line small semi muted" data-go="event/${p.event.id}" style="text-align:left"><span class="badge ink">${when(p.event.starts_at)}</span><span class="clip">${esc(p.event.title)}</span></button>`)).join('');
  return `<div class="screen with-nav">
    <header class="head"><div class="col" style="gap:2px"><span class="kicker">На этой неделе</span><h1 class="display">Ищут компанию</h1></div>${RULE}${girlsChip()}</header>
    <main class="body">${cards || empty('Пока никого', 'Выберите событие в афише и отметьте «Ищу компанию» — так вас найдут. Или позовите друга.', '<button class="btn ink small" data-go="">Открыть афишу</button><button class="btn soft small" data-invite-friends>👋 Позвать друга</button>')}
      ${cards ? '<button class="card invite-card" data-invite-friends><span class="strong">👋 Не нашли с кем пойти?</span><span class="small semi">Позовите друга — ссылка откроет приложение</span></button>' : ''}</main>
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
  const [data, mine, companies] = await Promise.all([api('GET', '/matches'), api('GET', '/my/events'), api('GET', '/groups')]);
  const groups = companies.groups.map((g) => `<button class="compact" data-go="group/${g.id}" style="border-radius:24px">
    <span class="group-ava">${g.others.slice(0, 3).map((p) => ava(p, 's')).join('') || ava({ name: '👥', id: 0 }, 'l')}</span>
    <span class="col" style="flex:1;min-width:0"><span class="between"><span class="strong clip" style="font-size:17px">👥 ${esc(g.event.title)}</span><span class="tiny semi muted">${when(g.at, false)}</span></span>
    <span class="small semi muted clip">${g.last ? (g.last_from ? esc(g.last_from) + ': ' : '') + esc(g.last) : 'Компания: вы, ' + g.others.map((p) => esc(p.name)).join(', ')}</span></span></button>`).join('');
  const prompts = mine.past.map((e) => `<button class="card" data-go="after/${e.id}" style="background:var(--lime)">
    <span class="tiny strong">${when(e.starts_at, false)} · ${esc(e.title)}</span><span class="strong" style="font-size:17px">С кем хочется увидеться ещё?</span></button>`).join('');
  const rows = data.matches.map((m) => `<button class="compact" data-go="chat/${m.id}" style="border-radius:24px">${ava(m.other, 'l')}
    <span class="col" style="flex:1"><span class="between"><span class="strong" style="font-size:17px">${esc(m.other.name)}</span><span class="tiny semi muted">${when(m.at, false)}</span></span>
    <span class="small semi muted clip">${m.last ? (m.last_mine ? 'Вы: ' : '') + esc(m.last) : esc(m.event.title)}</span></span></button>`).join('');
  return `<div class="screen with-nav"><header class="head"><h1 class="display">Чаты</h1></header>
    <main class="body">${prompts}${groups}${rows || (prompts || groups ? '' : empty('Чатов пока нет', 'Чат открывается, когда вы и другой гость оба нажали «Пойдём вместе».', '<button class="btn ink small" data-go="people">Кто ищет компанию</button>'))}</main>${nav('chats')}</div>`;
};

const bubble = (m) => `<p class="msg ${m.mine ? 'out' : 'in'}" data-id="${m.id}">${!m.mine && m.from ? `<b class="from">${esc(m.from)}${state.chat && state.chat.group && state.chat.group.captain_id === m.from_id ? ' ⭐' : ''}</b>` : ''}${esc(m.text)}</p>`;
screens.chat = async (id) => {
  const c = await api('GET', '/matches/' + id);
  state.chat = { id, base: '/matches/', last: c.messages.length ? c.messages[c.messages.length - 1].id : 0, other: c.other };
  const timer = state.timer = setInterval(async () => {
    if (!state.chat || state.chat.id !== id || state.chat.base !== '/matches/') return clearInterval(timer);
    try {
      const fresh = await api('GET', `/matches/${id}?after=${state.chat.last}`);
      addMessages(fresh.messages);
    } catch (e) { /* next tick will retry */ }
  }, 4000);
  const ice = c.icebreaker ? c.icebreaker.split('\n').filter((l) => l.startsWith('— ')).map((l) => l.slice(2)) : [];
  const quick = c.messages.length ? '' : `<div class="chips" style="margin:0">${[...ice, 'Привет! Где встретимся?', 'У входа за 15 минут до начала'].map((t) => `<button class="chip small" data-quick="${esc(t)}">${esc(t)}</button>`).join('')}</div>`;
  return `<div class="screen" style="padding-top:0">
    <header class="chat-head">
      <div class="line" style="gap:12px">${backBtn('soft')}${ava(c.other, 'm')}
        <div class="col" style="gap:0;flex:1"><h1 class="strong" style="font-size:18px">${esc(c.other.name)}</h1><span class="small semi muted">${c.kind === 'again' ? 'взаимная отметка после вечера' : 'идёте вместе ' + when(c.event.starts_at, false).toLowerCase()}</span></div>
        <button class="round soft" data-report="${c.other.id}" aria-label="Пожаловаться или скрыть">${ICON.more}</button></div>
      <button class="chat-event" data-go="event/${c.event.id}" style="text-align:left"><span class="small strong">${esc(c.event.title)}</span><span class="small semi muted">${when(c.event.starts_at)}${c.event.place ? ' · ' + esc(c.event.place) : ''}</span></button>
    </header>
    <main class="msgs" id="msgs"><p class="sys">${c.kind === 'again' ? 'Чат открылся, потому что вы отметили друг друга после вечера' : 'Чат открылся, потому что вы оба захотели пойти вместе'}</p>${c.icebreaker ? `<p class="sys ice">💡 ${esc(c.icebreaker).replace(/\n/g, '<br>')}</p>` : ''}${c.messages.map(bubble).join('')}</main>
    <div class="compose">${quick}<form id="send"><label style="flex:1"><span hidden>Сообщение</span><input class="input round-input" name="text" placeholder="Сообщение" autocomplete="off" maxlength="1000" enterkeyhint="send"></label>
      <button class="round" style="background:var(--ink);color:#fff;width:52px;height:52px;border-radius:26px" aria-label="Отправить">${ICON.send}</button></form></div></div>`;
};
screens.group = async (id) => {
  const c = await api('GET', '/groups/' + id);
  state.chat = { id, base: '/groups/', last: c.messages.length ? c.messages[c.messages.length - 1].id : 0, group: c };
  const timer = state.timer = setInterval(async () => {
    if (!state.chat || state.chat.id !== id || state.chat.base !== '/groups/') return clearInterval(timer);
    try {
      const fresh = await api('GET', `/groups/${id}?after=${state.chat.last}`);
      addMessages(fresh.messages);
    } catch (e) { /* next tick will retry */ }
  }, 4000);
  const ice = c.icebreaker.split('\n').filter((l) => l.startsWith('— ')).map((l) => l.slice(2));
  const quick = c.messages.length ? '' : `<div class="chips" style="margin:0">${['Всем привет! 👋', ...ice, 'Встречаемся у входа за 15 минут?'].map((t) => `<button class="chip small" data-quick="${esc(t)}">${esc(t)}</button>`).join('')}</div>`;
  const size = c.others.length + 1;
  return `<div class="screen" style="padding-top:0">
    <header class="chat-head">
      <div class="line" style="gap:12px">${backBtn('soft')}<span class="faces">${c.others.slice(0, 3).map((p) => ava(p, 's')).join('')}</span>
        <div class="col" style="gap:0;flex:1;min-width:0"><h1 class="strong clip" style="font-size:18px">Компания из ${size}</h1><span class="small semi muted clip">Вы, ${c.others.map((p) => esc(p.name)).join(', ') || 'пока больше никого'}</span></div>
        <button class="round soft" data-group-menu="${c.id}" aria-label="Участники">${ICON.more}</button></div>
      <button class="chat-event" data-go="event/${c.event.id}" style="text-align:left"><span class="small strong">${esc(c.event.title)}</span><span class="small semi muted">${when(c.event.starts_at)}${c.event.place ? ' · ' + esc(c.event.place) : ''}</span></button>
    </header>
    <main class="msgs" id="msgs"><p class="sys">Мы собрали компанию из тех, кто тоже идёт${c.girls_only ? ' — только девушки' : ''}. Договоритесь, где встретиться</p>${c.captain_id ? `<p class="sys">⭐ ${c.captain_id === state.me.id ? 'Вы капитан: предложите место встречи и познакомьте всех' : 'Капитан компании — ' + esc((c.others.find((p) => p.id === c.captain_id) || {}).name || '') + ': встретит всех у входа'}</p>` : ''}${c.promo ? `<div class="sys deal-box"><span>🎟 <b>Скидка для вашей компании:</b> ${esc(c.deal)}</span><button class="chip small" data-copy="${esc(c.promo)}">Промокод ${esc(c.promo)} · скопировать</button></div>` : ''}<p class="sys ice">💡 ${esc(c.icebreaker).replace(/\n/g, '<br>')}</p>${c.messages.map(bubble).join('')}</main>
    <div class="compose">${quick}<form id="send"><label style="flex:1"><span hidden>Сообщение</span><input class="input round-input" name="text" placeholder="Сообщение компании" autocomplete="off" maxlength="1000" enterkeyhint="send"></label>
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
  const sent = await act(() => api('POST', `${state.chat.base}${state.chat.id}/messages`, { text }));
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
      <div class="field"><span>Пол</span><div class="tags">${[['f', 'Девушка'], ['m', 'Парень'], ['', 'Не указывать']].map(([v, t]) => `<button type="button" class="chip small" data-gender="${v}" aria-pressed="${(me.gender || '') === v}">${t}</button>`).join('')}</div>
        <span class="tiny semi muted">Девушки могут искать компанию только среди девушек</span></div>
      <label class="field"><span>О себе</span><textarea class="input" name="bio" maxlength="300" placeholder="Что любите, с кем хотите пойти">${esc(me.bio)}</textarea></label>
      <div class="field"><span>Интересы, до пяти</span><div class="tags">${INTERESTS.map((t) => `<button type="button" class="chip small" data-interest aria-pressed="${chosen.has(t)}">${t}</button>`).join('')}</div></div>
      ${first ? '<label class="check"><input type="checkbox" name="adult"><span>Мне есть 18 лет. Принимаю <a href="/terms" target="_blank">пользовательское соглашение</a> и <a href="/privacy" target="_blank">политику конфиденциальности</a>.</span></label>' : ''}
      <p class="error" id="error" role="alert" hidden></p>
      <div style="flex:1"></div>
      <button class="btn ink">${first ? 'Открыть афишу' : 'Сохранить'}</button>
    </form></div>`;
}
screens.profileEdit = async () => profileForm(false);

function achTile(a) {
  const pct = a.next ? Math.min(100, Math.round((a.value / a.next) * 100)) : 100;
  return `<button class="ach${a.level ? ' got' : ''}" data-ach="${a.code}"><span class="ach-emoji">${a.emoji}</span>
    <span class="tiny strong clip">${esc(a.title)}</span><span class="ach-stars">${'★'.repeat(a.level)}${'☆'.repeat(a.levels - a.level)}</span>
    <span class="bar"><i style="width:${pct}%"></i></span></button>`;
}
function achievementSheet(code) {
  const a = (state.progress || { achievements: [] }).achievements.find((x) => x.code === code);
  if (!a) return;
  return sheet(`<div class="col" style="align-items:center;text-align:center;gap:6px"><span style="font-size:56px">${a.emoji}</span>
      <h2 class="strong">${esc(a.level ? a.title : 'Ещё не открыто')}</h2>
      <p class="small muted">${a.next ? `${a.value} из ${a.next} ${esc(a.unit)} до «${esc(a.next_title)}»` : `Высший уровень — ${a.value} ${esc(a.unit)}`}</p></div>
    <div class="rows">${a.steps.map((s) => `<div class="rowline" style="cursor:default"><span style="font-size:20px">${s.done ? '★' : '☆'}</span><span class="semi" style="flex:1">${esc(s.title)}</span><span class="small semi muted">от ${s.need}</span></div>`).join('')}</div>
    <p class="small muted">${esc(a.hint)}</p>
    ${a.level ? `<button class="btn ink" data-ach-share="${a.code}">Поделиться</button>` : ''}
    <button class="btn text" data-close>Закрыть</button>`);
}
function shareAchievement(code) {
  const a = (state.progress || { achievements: [] }).achievements.find((x) => x.code === code);
  if (!a || !a.level) return;
  const inv = state.progress.invite;
  const text = `${a.emoji} Моё достижение в «Кто идёт» — «${a.title}». Хожу на события в Москве с новыми людьми, присоединяйся`;
  const picture = location.origin + `/ach/${a.code}-${a.level}.jpg`;
  if (inTelegram && tg.shareToStory) {
    try { closeSheet(); return tg.shareToStory(picture, { text: text + ' ' + inv.link }); } catch (err) { /* old client: share a link */ }
  }
  closeSheet();
  return shareLink(inv.link, inv.web_link, text);
}

screens.achievements = async () => {
  const p = state.progress = await api('GET', '/me/progress');
  const got = p.achievements.filter((a) => a.level).length;
  return `<div class="screen"><header class="head"><div>${backBtn()}</div><span class="kicker">Открыто ${got} из ${p.achievements.length}</span><h1 class="display">Достижения</h1></header>
    <main class="body"><div class="ach-grid">${p.achievements.map(achTile).join('')}</div>
    <p class="small muted" style="text-align:center">Нажмите на достижение, чтобы посмотреть уровни и поделиться в сторис.</p></main></div>`;
};

screens.friends = async () => {
  const f = state.invite = await api('GET', '/friends');
  const list = f.friends.map((p) => `<div class="rowline" style="cursor:default">${ava(p, 'm')}<span class="semi" style="flex:1">${who(p)}</span><button class="btn text small quiet" data-unfriend="${p.id}">Убрать</button></div>`).join('');
  const going = f.going.map((g) => `<button class="rowline" data-go="event/${g.event.id}">${ava(g.friend, 'm')}<span class="col" style="gap:0;flex:1;min-width:0"><span class="semi clip">${esc(g.friend.name)} · ${esc(g.event.title)}</span><span class="small semi muted">${when(g.event.starts_at)}</span></span></button>`).join('');
  return `<div class="screen"><header class="head"><div>${backBtn()}</div><h1 class="display">Друзья</h1>
      <p class="muted">Друзья видят, куда вы идёте, и могут позвать вас в свою компанию. Добавить друга — отправить ему свою ссылку.</p></header>
    <main class="body">
      <button class="btn ink" data-invite-friends>Позвать друзей</button>
      ${going ? `<section class="card"><h2 class="strong" style="font-size:17px">Куда идут друзья</h2><div class="rows">${going}</div></section>` : ''}
      <section class="card"><h2 class="strong" style="font-size:17px">${f.friends.length ? 'Ваши друзья · ' + f.friends.length : 'Пока никого'}</h2>${list ? `<div class="rows">${list}</div>` : '<p class="small muted">Отправьте ссылку другу — как только он откроет её, вы станете друзьями.</p>'}</section>
    </main></div>`;
};

screens.profile = async () => {
  const me = state.me;
  const [mine, p] = await Promise.all([api('GET', '/my/events'), api('GET', '/me/progress')]);
  state.progress = p;
  const got = p.achievements.filter((a) => a.level);
  const top = [...got, ...p.achievements.filter((a) => !a.level)].slice(0, 4);
  const cap = p.captain;
  const captainCard = cap.ready
    ? `<section class="card"><label class="check"><input type="checkbox" data-captain ${cap.on ? 'checked' : ''}><span><b>⭐ Быть капитаном компаний</b><br><span class="small muted">Вы уже бывали на встречах. Капитан встречает компанию у входа и знакомит всех — так новичкам спокойнее.</span></span></label></section>`
    : `<section class="card"><span class="strong">⭐ Капитан компании</span><span class="small muted">Станет доступно после ${cap.need} событий. Сейчас: ${cap.events} из ${cap.need}.</span><span class="bar"><i style="width:${Math.round((cap.events / cap.need) * 100)}%"></i></span></section>`;
  const events = mine.upcoming.map((e) => `<button class="rowline" data-go="event/${e.id}"><span class="col" style="gap:0;flex:1"><span class="strong clip">${esc(e.title)}</span><span class="small semi muted">${when(e.starts_at)} · ${e.my_status === 'looking' ? 'ищу компанию' : 'иду'}</span></span></button>`).join('');
  return `<div class="screen with-nav"><header class="head"><h1 class="display">Профиль</h1></header>
    <main class="body">
      <section class="card"><div class="line" style="gap:14px">${ava(me, 'l')}<div class="col" style="gap:2px"><h2 class="strong" style="font-size:20px">${who(me)}</h2>${me.bio ? `<p class="small">${esc(me.bio)}</p>` : ''}</div></div>
        ${me.interests.length ? `<div class="tags">${me.interests.map((t) => `<span class="tag">${esc(t)}</span>`).join('')}</div>` : ''}
        <button class="btn soft small" data-go="profile/edit">Изменить</button></section>
      <button class="card invite-card" data-invite-friends><span class="strong" style="font-size:18px">👋 Позвать друга</span><span class="small semi">Отправьте ссылку на «Кто идёт» — ходить вместе веселее. Друг появится у вас в друзьях, а вы получите достижение.</span></button>
      <section class="card"><span class="between"><h2 class="strong" style="font-size:17px">Достижения · ${got.length} из ${p.achievements.length}</h2><button class="btn text small" data-go="achievements" style="width:auto;padding:0">Все</button></span>
        <div class="ach-grid">${top.map(achTile).join('')}</div></section>
      <button class="card" data-go="friends" style="gap:4px"><span class="strong" style="font-size:17px">👋 Друзья →</span><span class="small semi muted">Позвать друзей и посмотреть, кто куда идёт</span></button>
      ${captainCard}
      ${me.has_telegram ? `<section class="card"><label class="check"><input type="checkbox" data-nudges ${me.nudges ? 'checked' : ''}><span><b>Напоминать перед выходными</b><br><span class="small muted">Пишем в бот в четверг, пятницу и субботу, если на выходные ничего не отмечено.</span></span></label></section>` : ''}
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

screens.gatherNew = async () => {
  const cats = (await api('GET', '/events?day=today')).categories;
  const order = ['quest', 'sport', 'poker', 'mafia', 'games', 'quiz', 'food', 'music', 'party', 'walk', 'art', 'cinema', 'theater', 'talk', 'other'];
  const options = order.filter((id) => cats[id]).map((id) => `<option value="${id}"${id === 'quest' ? ' selected' : ''}>${(CAT_ICON[id] ? CAT_ICON[id] + ' ' : '') + cats[id]}</option>`).join('');
  return `<div class="screen"><header class="head"><div>${backBtn()}</div><span class="kicker">👋 Свой сбор</span><h1 class="display" style="font-size:26px">Соберите компанию</h1>
      <p class="note">Квест на пятерых, падел два на два, волейбол, покер, поход в кино — всё, куда не хочется идти одному. Сбор появится в афише, откликнувшиеся попадут к вам в общий чат.</p></header>
    <form class="body" id="gather" novalidate>
      <label class="field"><span>Что делаем</span><input class="input" name="title" required maxlength="100" placeholder="Квест «Тайна маяка» на Покровке"></label>
      <label class="field"><span>Тип</span><select class="input" name="category">${options}</select></label>
      <label class="field"><span>Когда</span><input class="input" name="starts_at" type="datetime-local" required></label>
      <label class="field"><span>Где</span><input class="input" name="place" required maxlength="120" placeholder="Название места"></label>
      <label class="field"><span>Адрес</span><input class="input" name="address" maxlength="200" placeholder="Улица, дом, метро"></label>
      <label class="field"><span>Сколько человек ищете</span><input class="input" name="need" type="number" inputmode="numeric" min="1" max="9" value="3" required></label>
      <label class="field"><span>Стоимость</span><input class="input" name="price" maxlength="60" placeholder="≈1 500 ₽ с человека, делим поровну"></label>
      <label class="field"><span>Пара слов</span><textarea class="input" name="description" maxlength="800" placeholder="Уровень, что взять с собой, где встречаемся"></textarea></label>
      <p class="error" id="error" role="alert" hidden></p>
      <button class="btn ink">Опубликовать сбор</button>
      <p class="tiny muted">Сбор увидят все в афише. Нельзя: реклама, продажа, азартные игры на деньги.</p>
    </form></div>`;
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
        <div class="stat"><b>${s.companies}</b><span>${plural(s.companies, 'компания собралась', 'компании собрались', 'компаний собрались')}</span></div>
      </div>
      <form class="card" id="deal" data-event="${id}" style="gap:10px"><h2 class="strong" style="font-size:16px">🎟 Групповые билеты</h2>
        <p class="small" style="color:#A9ADBA">Скидка для компаний, которые мы собираем на ваше событие. Условие видно в афише, промокод — только участникам компании.</p>
        <label class="field"><span>Условие</span><input class="input" name="group_deal" maxlength="120" value="${esc(s.event.group_deal)}" placeholder="−20% для компании от 3 человек"></label>
        <label class="field"><span>Промокод</span><input class="input" name="group_promo" maxlength="40" value="${esc(s.event.group_promo || '')}" placeholder="KTOIDET20"></label>
        <button class="btn lime small">Сохранить</button></form>
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
    if (state.me && state.me.adult_ok && !state.inviteDone) { state.inviteDone = true; useInvite(); }
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
    else if (a === 'group') html = await screens.group(b);
    else if (a === 'achievements') html = await screens.achievements();
    else if (a === 'friends') html = await screens.friends();
    else if (a === 'profile') html = b === 'edit' ? await screens.profileEdit() : await screens.profile();
    else if (a === 'gather') html = await screens.gatherNew();
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
  if (a === 'chat' || a === 'group') window.scrollTo(0, document.body.scrollHeight); else window.scrollTo(0, 0);
}

// ---------- actions ----------
function formError(text) { const el = document.getElementById('error'); if (el) { el.textContent = text; el.hidden = !text; } }

function adSource() {
  try {
    const fromUrl = new URLSearchParams(location.search).get('utm_source');
    if (fromUrl && !localStorage.getItem('src')) localStorage.setItem('src', fromUrl.slice(0, 32));
    return localStorage.getItem('src') || '';
  } catch (err) { return ''; }
}
adSource();

async function shareLink(tgLink, webLink, text) {
  if (inTelegram && tg.openTelegramLink) {
    return tg.openTelegramLink('https://t.me/share/url?url=' + encodeURIComponent(tgLink) + '&text=' + encodeURIComponent(text));
  }
  if (navigator.share) { try { await navigator.share({ text, url: webLink }); } catch (err) { /* closed */ } return; }
  try { await navigator.clipboard.writeText(text + ' ' + webLink); toast('Ссылка скопирована'); } catch (err) { toast(webLink); }
}

async function joinCompany(e, girlsOnly) {
  const res = await act(() => api('POST', `/events/${e.id}/attend`, { status: 'looking', note: e.my_note || '', group: true, girls_only: girlsOnly }));
  if (!res) return;
  haptic();
  if (res.group) return go('group/' + res.group.id);
  toast(e.gathering ? 'Мест пока нет — сообщим, если освободится' : 'Собираем компанию — пришлём уведомление');
  render();
}

/** «Позвать друга»: a personal link to the app. The friend lands in Telegram, the iPhone app or the site
 * and becomes a friend after signing in. */
async function inviteFriend() {
  if (!state.me) { state.returnTo = route().join('/'); return go('auth'); }
  const f = state.invite || (state.invite = await act(() => api('GET', '/friends')));
  if (!f) return;
  haptic();
  return shareLink(f.link, f.web_link, 'Я нахожу компанию на концерты, квизы и выставки в «Кто идёт». Присоединяйся — пойдём вместе');
}

async function shareEvent(e) {
  if (!e) return;
  const text = `Пойдёшь со мной на «${e.title}»? ${when(e.starts_at, true)}`;
  if (state.me) {
    const inv = await act(() => api('GET', `/events/${e.id}/invite`));
    if (inv) return shareLink(inv.link, inv.web_link, text);
  }
  if (inTelegram && tg.openTelegramLink) {
    const link = `https://t.me/${state.bot}?startapp=event-${e.id}`;
    return tg.openTelegramLink('https://t.me/share/url?url=' + encodeURIComponent(link) + '&text=' + encodeURIComponent(text));
  }
  const url = location.origin + '/e/' + e.id;
  if (navigator.share) { try { await navigator.share({ title: e.title, text, url }); } catch (err) { /* closed */ } return; }
  try { await navigator.clipboard.writeText(text + ' ' + url); toast('Ссылка скопирована'); } catch (err) { toast(url); }
}

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
  if ('share' in d) return shareEvent(state.event);
  if (d.company) {
    if (!state.me) { state.returnTo = route().join('/'); return go('auth'); }
    const e = state.event;
    if (e.gathering) return joinCompany(e, false);
    if (isGirl()) {
      const what = e.category === 'quiz' ? 'команду' : 'компанию';
      return sheet(`<h2 class="strong">Соберём ${what}</h2><p class="muted">Найдём 2–4 человек, которые тоже идут, и откроем общий чат.</p>
        <label class="check"><input type="checkbox" id="company-girls" ${e.my_girls_only ? 'checked' : ''}><span>👭 Только девушки</span></label>
        <button class="btn ink" data-company-go="${e.id}">Соберите мне ${what}</button><button class="btn text" data-close>Отмена</button>`);
    }
    return joinCompany(e, false);
  }
  if (d.gatherCancel) {
    return sheet(`<h2 class="strong">Отменить сбор?</h2><p class="muted">Сбор пропадёт из афиши, участникам придёт сообщение.</p>
      <button class="btn ink" data-gather-cancel-go="${d.gatherCancel}">Отменить сбор</button><button class="btn text" data-close>Не отменять</button>`);
  }
  if (d.gatherCancelGo) {
    closeSheet();
    if (await act(() => api('POST', `/gatherings/${d.gatherCancelGo}/cancel`))) { toast('Сбор отменён'); return go(''); }
    return;
  }
  if (d.companyGo) { const only = document.getElementById('company-girls'); closeSheet(); return joinCompany(state.event, !!(only && only.checked)); }
  if (d.companyStop) {
    if (await act(() => api('POST', `/events/${d.companyStop}/attend`, { status: 'looking', note: state.event.my_note || '', group: false }))) render();
    return;
  }
  if (d.groupMenu) {
    const g = state.chat && state.chat.group;
    if (!g) return;
    return sheet(`<h2 class="strong">Компания</h2>
      ${g.full ? '' : `<button class="btn ink" data-group-invite="${g.id}">Позвать друга в компанию</button>`}
      ${g.others.map((p) => `<div class="between">${ava(p, 'm')}<span class="semi" style="flex:1;margin-left:12px">${who(p)}${g.captain_id === p.id ? ' ⭐' : ''}</span><button class="btn text small quiet" data-report="${p.id}">Пожаловаться</button></div>`).join('')}
      <button class="btn text danger" data-group-leave="${g.id}">Выйти из компании</button><button class="btn text" data-close>Закрыть</button>`);
  }
  if (d.groupLeave) {
    if (await act(() => api('POST', `/groups/${d.groupLeave}/leave`))) { closeSheet(); toast('Вы вышли из компании'); go('chats'); }
    return;
  }
  if (d.groupInvite) {
    const inv = await act(() => api('GET', `/groups/${d.groupInvite}/invite`));
    if (!inv) return;
    const e = state.chat && state.chat.group && state.chat.group.event;
    closeSheet();
    return shareLink(inv.link, inv.web_link, `Пойдём со мной${e ? ` на «${e.title}», ${when(e.starts_at, true).toLowerCase()}` : ''}? У нас уже собралась компания`);
  }
  if (d.copy) {
    try { await navigator.clipboard.writeText(d.copy); toast('Скопировано'); } catch (err) { toast(d.copy); }
    return;
  }
  if ('inviteFriends' in d) return inviteFriend();
  if (d.unfriend) {
    if (await act(() => api('DELETE', '/friends/' + d.unfriend))) render();
    return;
  }
  if (d.ach) return achievementSheet(d.ach);
  if (d.achShare) return shareAchievement(d.achShare);
  if ('gender' in d) {
    document.querySelectorAll('[data-gender]').forEach((b) => b.setAttribute('aria-pressed', String(b === el)));
    return;
  }
  if ('girls' in d) { state.girls = !state.girls; return render(); }
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
      ${isGirl() ? `<label class="check"><input type="checkbox" id="girls-only" ${e.my_girls_only ? 'checked' : ''}><span>👭 Только с девушками — меня увидят и позовут только девушки</span></label>` : ''}
      <button class="btn ink" data-looking-save="${e.id}">${e.my_status === 'looking' ? 'Сохранить' : 'Показать меня гостям'}</button>
      ${e.my_status === 'looking' ? `<button class="btn text danger" data-looking-stop="${e.id}">Больше не ищу</button>` : '<button class="btn text" data-close>Отмена</button>'}`);
  }
  if (d.lookingSave) {
    const note = document.getElementById('note').value;
    const only = document.getElementById('girls-only');
    if (await act(() => api('POST', `/events/${d.lookingSave}/attend`, { status: 'looking', note, girls_only: !!(only && only.checked) }))) { haptic(); closeSheet(); go(`event/${d.lookingSave}/people`); }
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

document.addEventListener('change', async (event) => {
  if (event.target.matches('[data-captain]')) {
    const on = event.target.checked;
    const me = await act(() => api('PUT', '/me/settings', { captain_ok: on }));
    if (me) { state.me = me; toast(on ? 'Теперь вы можете стать капитаном компании' : 'Капитанство выключено'); } else event.target.checked = !on;
    return;
  }
  if (!event.target.matches('[data-nudges]')) return;
  const on = event.target.checked;
  const me = await act(() => api('PUT', '/me/settings', { nudges: on }));
  if (me) { state.me = me; toast(on ? 'Будем напоминать перед выходными' : 'Напоминания выключены'); } else event.target.checked = !on;
});

document.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.target, f = new FormData(form);
  if (form.id === 'deal') {
    const body = { group_deal: String(f.get('group_deal')).trim(), group_promo: String(f.get('group_promo')).trim() };
    if (body.group_deal && !body.group_promo) return toast('Добавьте промокод');
    if (await act(() => api('PUT', `/org/events/${form.dataset.event}/deal`, body))) toast(body.group_deal ? 'Скидка включена' : 'Скидка выключена');
    return;
  }
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
      const answer = await api('POST', signup ? '/auth/register' : '/auth/login', { email, password, source: adSource() });
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
    const picked = form.querySelector('[data-gender][aria-pressed=true]');
    const gender = picked ? picked.dataset.gender : '';
    try {
      state.me = await api('PUT', '/me', { name: String(f.get('name')).trim(), age, bio: String(f.get('bio')), interests, gender, adult_ok: true });
    } catch (e) { return formError(e.message); }
    if (first) return render();
    toast('Сохранено');
    return back();
  }
  if (form.id === 'gather') {
    const body = Object.fromEntries([...f.entries()].map(([k, v]) => [k, String(v).trim()]));
    if (body.title.length < 3) return formError('Напишите, что делаем.');
    if (!body.starts_at) return formError('Укажите дату и время.');
    if (body.place.length < 2) return formError('Укажите место.');
    body.need = Number(body.need);
    if (!body.need || body.need < 1 || body.need > 9) return formError('Ищите от 1 до 9 человек.');
    try {
      const created = await api('POST', '/gatherings', body);
      history.replaceState(null, '', '#/event/' + created.id);
      toast('Сбор в афише');
      return render();
    } catch (e) { return formError(e.message); }
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
  // «Квизы» link for organizers and ads: t.me/<bot>?startapp=quiz or ?go=quiz — afisha of quizzes for the week.
  if (target === 'quiz') { state.category = 'quiz'; state.day = 'week'; return ''; }
  const m = /^(chat|after|event|match|people|group)-(\d+)$/.exec(target);
  if (m) return m[1] === 'people' ? `event/${m[2]}/people` : `${m[1]}/${m[2]}`;
  const invited = /^fr_[a-z0-9]{4,16}(?:_g\d+)?_e(\d+)$/i.exec(target);
  if (invited) return `event/${invited[1]}`;
  return ['org', 'achievements', 'friends'].includes(target) ? target : '';
}
/** A friend's invite (t.me/<bot>?startapp=fr_<code>[_g<company>] or ?fr=<code>&g=<company>): kept until signed in. */
function keepInvite() {
  const sp = (tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param) || '';
  const m = /^fr_([a-z0-9]{4,16})(?:_g(\d+))?(?:_e(\d+))?$/i.exec(sp);
  const code = m ? m[1] : params.get('fr'), group = m ? m[2] : params.get('g');
  if (code) { try { localStorage.setItem('invite', JSON.stringify({ code, group: group ? Number(group) : null })); } catch (e) { /* private mode */ } }
}
keepInvite();
async function useInvite() {
  let invite;
  try { invite = JSON.parse(localStorage.getItem('invite') || 'null'); localStorage.removeItem('invite'); } catch (e) { return; }
  if (!invite) return;
  try {
    const res = await api('POST', '/friends/accept', invite);
    if (res.group_id) { toast('Вы в компании друга'); return go('group/' + res.group_id); }
    if (res.friend && res.new) toast(`${res.friend.name} теперь у вас в друзьях`);
  } catch (e) { /* stale link */ }
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
