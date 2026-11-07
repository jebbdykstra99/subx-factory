// Rooms tab preview. Home reuses the highlights.json fetch the feed already started. The rooms directory
// (no feed) does not fetch highlights.json; it uses the preview copied onto rooms.json at build time.
// A partner room with enabled not true stays out of the list.
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

function boot(opts) {
  const calls = [];
  function el(id) {
    return { id, innerHTML: '', textContent: '', hidden: false, attrs: {},
      classList: { contains() { return false; }, toggle() {}, add() {}, remove() {} },
      getAttribute(k) { return this.attrs[k] == null ? null : this.attrs[k]; }, setAttribute(k, v) { this.attrs[k] = String(v); },
      hasAttribute(k) { return k in this.attrs; }, removeAttribute(k) { delete this.attrs[k]; }, focus() {} };
  }
  const ids = ['hub-feed', 'hub-rooms'].filter(id => opts[id]);
  const els = {}; ids.forEach(id => { els[id] = el(id); });
  const store = {};
  const localStorage = { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
  const sandbox = {
    console, JSON, Date, Promise, Object, Array, String, Math, isFinite, RegExp, setTimeout: f => f(),
    location: { hash: '' }, navigator: {},
    fetch: p => {
      calls.push(String(p));
      const body = /highlights\.json/.test(p) ? opts.highlights : /rooms\.json/.test(p) ? opts.rooms : { items: [], rooms: [] };
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
    },
    document: {
      getElementById: i => els[i] || null,
      querySelectorAll: () => [],
      querySelector: () => null,
      addEventListener() {}
    }
  };
  sandbox.window = { localStorage, history: { replaceState() {} }, addEventListener() {} };
  sandbox.localStorage = localStorage;
  vm.createContext(sandbox);
  vm.runInContext(js, sandbox);
  return { els, calls };
}

const tick = () => new Promise(r => setImmediate(r));
const newest = {};
hl.items.forEach(it => {
  const t = Date.parse(it.createdAt);
  if (!newest[it.room] || t >= Date.parse(newest[it.room].createdAt)) newest[it.room] = it;
});
const partner = { room: 'partnerdemo', name: 'Partner Demo', domain: 'partnerdemo.example', tagline: 'Should stay hidden.', partner: true, enabled: false, accent: '#112233', brief: 'Hidden brief' };
const tagOnly = { room: 'tagonly', name: 'tagonly', domain: 'tagonly.example', tagline: 'Only the tagline.', featured: false, notifs: false };
const bare = { room: 'bare', name: 'bare', domain: 'bare.example', tagline: '', featured: false, notifs: false };
const roomsPlus = { rooms: rooms.rooms.concat([partner, tagOnly, bare]) };
const newer = { room: 'gpchat', domain: 'gpchat.com', url: 'https://gpchat.com/?p=NEWERPOST1', text: 'Newer porch note for the row.', authorHandle: 'newerhandle', tier: 'human', createdAt: '2099-01-01T00:00:00.000Z', postId: 'NEWERPOST1', featured: true };

(async () => {
  const home = boot({ 'hub-feed': true, 'hub-rooms': true, rooms: roomsPlus, highlights: { items: hl.items.concat([newer]) } });
  await tick(); await tick();
  const html = home.els['hub-rooms'].innerHTML;
  const hlCalls = home.calls.filter(u => /highlights\.json/.test(u));
  const roomCalls = home.calls.filter(u => /rooms\.json/.test(u));
  ok(hlCalls.length === 1 && roomCalls.length === 1, 'home: highlights.json is fetched once and shared with the Rooms tab (' + home.calls.join(' ') + ')');
  ok(html.indexOf('partnerdemo') === -1 && html.indexOf('Hidden brief') === -1, 'partner room with enabled not true is not listed');
  ok(html.indexOf('https://gpchat.com/?p=NEWERPOST1') !== -1 && html.indexOf('@newerhandle') !== -1 && html.indexOf('Human-made') !== -1,
    'home: the Rooms tab uses the newest highlight from highlights.json');
  ok(/aria-label="Latest post in gpchat by @newerhandle, Human-made, /.test(html), 'preview link aria-label names the room, handle, and label');
  ok(html.indexOf('style="background:#e10600"') !== -1, 'gpchat preview uses the room accent');
  const quiet = html.split('hub-room-card').filter(part => part.indexOf('>808chat<') !== -1)[0] || '';
  ok(quiet.indexOf('is-quiet') !== -1 && quiet.indexOf('https://808chat.com/') !== -1 && quiet.indexOf('NWS HFO') !== -1,
    '808chat has no highlight, so the preview is the Room Brief line');
  ok(html.indexOf('Only the tagline.') !== -1 && html.indexOf('>bare<') !== -1, 'tagline fallback and a bare room both render');
  const bareCard = html.split('hub-room-card').filter(part => part.indexOf('>bare<') !== -1)[0] || '';
  ok(bareCard.indexOf('hub-room-peek') === -1, 'a room with no highlight, brief, or tagline has no empty preview box');
  ok((html.match(/class="hub-room-peek(?: |")/g) || []).length === rooms.rooms.length + 1, 'one preview per listed room plus the tagline-only room');

  const dir = boot({ 'hub-rooms': true, rooms: roomsPlus, highlights: { items: [] } });
  await tick(); await tick();
  const dhtml = dir.els['hub-rooms'].innerHTML;
  ok(!dir.calls.some(u => /highlights\.json/.test(u)) && dir.calls.some(u => /rooms\.json/.test(u)),
    'rooms directory does not fetch highlights.json (' + dir.calls.join(' ') + ')');
  ok(dhtml.indexOf('@pitwall') !== -1 && dhtml.indexOf(newest.gpchat.url) !== -1 && dhtml.indexOf('AI-made · AI steward') !== -1,
    'rooms directory uses the build-time preview (handle, post, AI steward label)');
  ok(dhtml.indexOf('NWS HFO') !== -1, 'rooms directory quiet row still shows the Room Brief');
  console.log('\n' + fails + ' failure(s)');
  process.exit(fails ? 1 : 0);
})();
