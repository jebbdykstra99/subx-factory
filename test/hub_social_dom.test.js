// Runs the built hub/site/hub.js against a tiny fake DOM (no browser, offline) and checks that the Following,
// Notifications and Chat views only link to the exact domains listed in hub/site/rooms.json, that a highlight
// pointing anywhere else is dropped, that member Notifications are offered only for rooms with notifs true
// (Key 1 E2), that following a room starts the badge at 0 and New means a highlight id not seen yet (Key 1 E3),
// that the shell's #following / #notifications / #chat hashes go to the hub views (Key 1 E1), and that the only
// storage written is the hub.follows.v1 key.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
const SITE = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'hub', 'site');
const js = fs.readFileSync(path.join(SITE, 'hub.js'), 'utf8');
const rooms = JSON.parse(fs.readFileSync(path.join(SITE, 'rooms.json'), 'utf8'));
const hl = JSON.parse(fs.readFileSync(path.join(SITE, 'highlights.json'), 'utf8'));
let fails = 0;
function ok(c, m) { console.log((c ? 'ok   ' : 'FAIL ') + m); if (!c) fails++; }

// follow the room with the most highlights, so a first follow would have shown 9+ under the old createdAt rule
const per = {}; hl.items.forEach(it => { per[it.room] = (per[it.room] || 0) + 1; });
const first = rooms.rooms.slice().sort((a, b) => (per[b.room] || 0) - (per[a.room] || 0))[0];
const evil = [
  { room: first.room, postId: 'evil1', roomName: first.name, domain: 'evil.example', url: 'https://evil.example/?p=abc', text: 'x', authorName: 'x', tier: 'ai', createdAt: '2099-01-01T00:00:00Z' },
  { room: first.room, postId: 'evil2', roomName: first.name, domain: first.domain, url: 'https://evil.example/?p=abd', text: 'y', authorName: 'y', tier: 'ai', createdAt: '2099-01-01T00:00:00Z' },
  { room: first.room, postId: 'evil3', roomName: first.name, domain: 'evil.example', url: 'https://' + first.domain + '/?p=abe', text: 'z', authorName: 'z', tier: 'ai', createdAt: '2099-01-01T00:00:00Z' }
];
const roomsPlus = { rooms: rooms.rooms.concat([{ room: 'evil', name: 'evil', domain: 'not a domain', tagline: '', notifs: true }]) };

function boot(store, items, hash) {
  function el(id) {
    const cls = new Set();
    return { id, innerHTML: '', textContent: '', hidden: false, attrs: {},
      classList: { contains: c => cls.has(c), toggle: (c, on) => { if (on === undefined) on = !cls.has(c); on ? cls.add(c) : cls.delete(c); }, add: c => cls.add(c), remove: c => cls.delete(c) },
      getAttribute(k) { return this.attrs[k] == null ? null : this.attrs[k]; }, setAttribute(k, v) { this.attrs[k] = String(v); },
      hasAttribute(k) { return k in this.attrs; }, removeAttribute(k) { delete this.attrs[k]; }, focus() {} };
  }
  const ids = ['page-hub-following', 'page-hub-notifications', 'page-hub-chat', 'page-thoughts', 'hub-following-feed', 'hub-follow-list',
    'hub-notif-feed', 'hub-notif-rooms', 'hub-chat-rooms', 'hub-notif-badge', 'notif-overlay'];
  const els = {}; ids.forEach(i => { els[i] = el(i); });
  const pages = ['page-hub-following', 'page-hub-notifications', 'page-hub-chat', 'page-thoughts'].map(i => els[i]);
  const writes = [], values = [];
  const localStorage = { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { writes.push(k); values.push(String(v)); store[k] = String(v); } };
  const loc = { hash };
  const listeners = {};
  const sandbox = {
    console, JSON, Date, Promise, Object, Array, String, Math, isFinite, RegExp, setTimeout: f => f(),
    location: loc, navigator: {},
    fetch: p => Promise.resolve({ ok: true, json: () => Promise.resolve(/rooms\.json/.test(p) ? roomsPlus : /highlights\.json/.test(p) ? { items } : { items: [], rooms: [] }) }),
    document: {
      getElementById: i => els[i] || null,
      querySelectorAll: s => (s === '.page' ? pages : []),
      querySelector: () => null,
      addEventListener: (t, f) => { (listeners['d' + t] = listeners['d' + t] || []).push(f); }
    }
  };
  sandbox.window = { localStorage, history: { replaceState: (a, b, h) => { loc.hash = h; } },
    addEventListener: (t, f) => { (listeners['w' + t] = listeners['w' + t] || []).push(f); } };
  sandbox.localStorage = localStorage;
  vm.createContext(sandbox);
  vm.runInContext(js, sandbox);
  const go = h => { loc.hash = h; listeners.whashchange.forEach(f => f()); };
  const click = room => listeners.dclick[listeners.dclick.length - 1]({ target: { closest: s => (s === '[data-follow-room]' ? { getAttribute: () => room } : null) } });
  return { els, loc, go, click, writes, values };
}

const tick = () => new Promise(r => setImmediate(r));
const hrefs = h => (h.match(/href="([^"]*)"/g) || []).map(x => x.slice(6, -1));
const allowed = new Set(rooms.rooms.map(r => r.domain.toLowerCase()));
const notifRooms = rooms.rooms.filter(r => r.notifs === true), quiet = rooms.rooms.filter(r => r.notifs !== true);
function onlyListed(h, frag) {
  return hrefs(h).every(u => { const m = /^https:\/\/([^/]+)\/(.*)$/.exec(u); return m && allowed.has(m[1]) && (m[2] === (frag ? '#' + frag : '')); });
}
const badge = b => (b.hidden ? '' : b.textContent);
(async () => {
  const store = {};
  const a = boot(store, hl.items.concat(evil), '#hub-following');
  await tick(); await tick();
  ok((per[first.room] || 0) >= 2, 'fixture: ' + first.room + ' has ' + (per[first.room] || 0) + ' highlights to start from');
  a.click(first.room);
  const f = a.els['hub-following-feed'].innerHTML, fl = a.els['hub-follow-list'].innerHTML;
  ok(f.indexOf('class="hub-card"') !== -1, 'Following: followed room shows highlights');
  ok(!/evil\.example/.test(f), 'Following: a highlight whose url or domain is not in rooms.json is dropped');
  ok(onlyListed(fl, ''), 'Following: room rows link only to rooms.json domains');
  ok(!/not a domain/.test(fl), 'Following: a room with a bad domain is not listed');
  ok(badge(a.els['hub-notif-badge']) === '' && a.els['hub-notif-badge'].hidden === true, 'E3: first follow sets a baseline, badge stays at 0 (not 9+)');
  a.go('#hub-notifications');
  const n = a.els['hub-notif-feed'].innerHTML, nr = a.els['hub-notif-rooms'].innerHTML;
  ok(!/evil\.example/.test(n), 'Notifications: no off-list highlight');
  ok(!/hub-new/.test(n), 'E3: nothing is marked New right after the first follow');
  ok(onlyListed(nr, 'notifications'), 'Notifications: hand-offs go only to https://<rooms.json domain>/#notifications');
  ok(hrefs(nr).length === notifRooms.length && notifRooms.every(r => hrefs(nr).indexOf('https://' + r.domain + '/#notifications') !== -1),
    'E2: one Open Notifications hand-off per room with notifs true (' + notifRooms.length + ')');
  ok(quiet.length > 0 && quiet.every(r => nr.indexOf(r.domain) === -1), 'E2: no notifications link for ' + quiet.map(r => r.room).join(', '));
  a.go('#hub-chat');
  const c = a.els['hub-chat-rooms'].innerHTML;
  ok(onlyListed(c, 'chat') && hrefs(c).length === rooms.rooms.length, 'Chat: hand-offs go only to https://<rooms.json domain>/#chat, one per listed room');
  ok(a.writes.length > 0 && a.writes.every(k => k === 'hub.follows.v1'), 'storage: only hub.follows.v1 is written');
  const saved = JSON.parse(store['hub.follows.v1']);
  ok(JSON.stringify(Object.keys(saved).sort()) === '["rooms","seen"]' && saved.rooms[0] === first.room &&
    Array.isArray(saved.seen) && saved.seen.every(x => typeof x === 'string' && x.indexOf(first.room + '/') === 0),
  'storage: holds only the followed rooms and the seen highlight ids');

  // after a rebuild one new highlight appears for the followed room: badge 1, marked New once, then seen
  const fresh = Object.assign({}, hl.items.find(it => it.room === first.room), { postId: 'freshPost1', url: 'https://' + first.domain + '/?p=freshPost1', createdAt: '2000-01-01T00:00:00Z' });
  const b = boot(store, hl.items.concat([fresh]), '#hub-following');
  await tick(); await tick();
  ok(badge(b.els['hub-notif-badge']) === '1', 'E3: a highlight id not seen yet counts once, even with an old createdAt (badge ' + JSON.stringify(badge(b.els['hub-notif-badge'])) + ')');
  b.go('#hub-notifications');
  ok((b.els['hub-notif-feed'].innerHTML.match(/hub-new/g) || []).length === 1, 'E3: exactly that highlight is marked New');
  b.go('#hub-following');
  ok(badge(b.els['hub-notif-badge']) === '', 'E3: opening Notifications marks it seen');

  // an older save kept a time in seen: rebased on load, no 9+
  const old = { 'hub.follows.v1': JSON.stringify({ rooms: [first.room], seen: 0 }) };
  const d = boot(old, hl.items, '#hub-following');
  await tick(); await tick();
  ok(badge(d.els['hub-notif-badge']) === '' && Array.isArray(JSON.parse(old['hub.follows.v1']).seen), 'E3: an older time based save starts at 0 too');

  // E1: the shell's own hashes go to the hub views
  for (const [from, to] of [['#following', '#hub-following'], ['#notifications', '#hub-notifications'], ['#chat', '#hub-chat']]) {
    const e = boot({}, hl.items, from);
    ok(e.loc.hash === to, 'E1: ' + from + ' opens ' + to + ' on load');
    e.go('#home'); e.go(from);
    ok(e.loc.hash === to, 'E1: ' + from + ' opens ' + to + ' on hash change');
  }
  // Key 2 C1: the shell's openNotif() adds .active to the hidden stub; the hub drops it on load and on every hash change
  const st = boot({}, hl.items, '#hub-following');
  st.els['notif-overlay'].classList.add('active'); st.go('#notifications');
  ok(!st.els['notif-overlay'].classList.contains('active') && st.loc.hash === '#hub-notifications', 'C1: #notifications drops .active from the notif-overlay stub');
  st.els['notif-overlay'].classList.add('active'); st.go('#hub-notifications');
  ok(!st.els['notif-overlay'].classList.contains('active'), 'C1: .active added after the hash change is dropped too');

  // Iris: hub.follows.v1 holds only rooms and seen ids. Old saves (a seen time, a lastOpened time, a version, anything
  // else) are rewritten to exactly those two fields on the next write; every write is checked against this list.
  const ALLOWED = '["rooms","seen"]';
  const keysOf = v => JSON.stringify(Object.keys(JSON.parse(v)).sort());
  const legacy = { 'hub.follows.v1': JSON.stringify({ rooms: [first.room], seen: 1730000000000, lastOpened: 1730000000000, v: 1, extra: 'x' }) };
  const m = boot(legacy, hl.items, '#hub-following');
  await tick(); await tick();
  const mig = JSON.parse(legacy['hub.follows.v1']);
  ok(keysOf(legacy['hub.follows.v1']) === ALLOWED && Array.isArray(mig.seen) && mig.seen.every(x => typeof x === 'string' && /^[a-z0-9-]+\/[A-Za-z0-9_-]+$/.test(x)) &&
    !/1730000000000|lastOpened/.test(legacy['hub.follows.v1']), 'storage: an old save with seen/lastOpened times and a version is rewritten to rooms + seen ids only');
  const legacy2 = { 'hub.follows.v1': JSON.stringify({ rooms: [], lastOpened: 1730000000000, v: 1 }) };
  const m2 = boot(legacy2, hl.items, '#hub-following');
  await tick(); await tick(); m2.click(first.room); m2.click(first.room); m2.click(quiet[0].room);
  ok(keysOf(legacy2['hub.follows.v1']) === ALLOWED && !/lastOpened|1730000000000|"v"/.test(legacy2['hub.follows.v1']), 'storage: lastOpened and v are dropped on the next write');
  const every = [a, b, d, m, m2].reduce((acc, x) => acc.concat(x.values), []);
  ok(every.length > 0 && every.every(v => keysOf(v) === ALLOWED && JSON.parse(v).rooms.every(r => typeof r === 'string') && JSON.parse(v).seen.every(x => typeof x === 'string')),
    'storage: every write (' + every.length + ') has exactly the fields rooms (room ids) and seen (highlight ids)');
  console.log('\n' + fails + ' failure(s)');
  process.exit(fails ? 1 : 0);
})();
