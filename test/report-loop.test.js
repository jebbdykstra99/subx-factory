// node test/report-loop.test.js — v1.2.3 (A9 pieces 2+3): report status + triage, "My reports", report_update notif.
// Installs the shipped factory-reports.js against a fake core / DOM / Firestore and checks the core stubs.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert';
const rd = (f) => fs.readFileSync(new URL('../factory/' + f, import.meta.url), 'utf8');
const core = rd('factory.js');
const plug = rd('factory-reports.js');
function fnSrc(src, name) {
  const i = src.indexOf('  function ' + name + '(');
  assert.ok(i >= 0, name + ' missing');
  return src.slice(i, src.indexOf('\n  }\n', i) + 4);
}
const J = (x) => JSON.parse(JSON.stringify(x));
const ADMIN = 'o774wL9hUVSi19EkDCgLqQomP8i2';

// ---- core without the opt-in: v1.2.2 admin row (Dismiss only), no My reports
const c0 = { PLUGIN: {} };
vm.createContext(c0);
vm.runInContext(fnSrc(core, 'escapeHtml') + fnSrc(core, 'reportTriage') + fnSrc(core, 'syncMyReports'), c0);
assert.strictEqual(c0.reportTriage({ id: 'r<1' }), '<button type="button" class="post-action" data-report-dismiss="r&lt;1">Dismiss</button>');
assert.strictEqual(c0.syncMyReports(), undefined);
assert.ok(core.includes("return r.status !== 'dismissed' && r.status !== 'actioned'; }).slice(0, 50);"), 'actioned leaves the queue');
assert.ok(core.includes("    syncMyReports();\n    var nav = document.querySelector('#sidebar nav ul');\n    var link = document.getElementById('nav-reports');"), 'My reports synced with the admin entry');
assert.ok(core.includes("'reports-overlay', 'myreports-overlay'].forEach("), 'My reports overlay closes with the others');
assert.ok(core.includes('        reportTriage(r) +\n'), 'admin row uses reportTriage');
assert.ok(Buffer.byteLength(core) <= 255000, 'core budget');

// ---- fake DOM
const els = {};
let clickHandler = null;
function mkEl(tag) {
  const e = { tag, id: '', className: '', innerHTML: '', children: [], parentNode: null,
    classList: { s: new Set(), add(c) { this.s.add(c); }, remove(...c) { c.forEach((x) => this.s.delete(x)); }, contains(c) { return this.s.has(c); } },
    appendChild(ch) { ch.parentNode = e; e.children.push(ch); const m = /id="([^"]+)"/.exec(ch.innerHTML); if (m) els[m[1]] = { parentNode: ch }; if (ch.id) els[ch.id] = ch; return ch; },
    remove() { const p = e.parentNode; if (p) p.children = p.children.filter((x) => x !== e); Object.keys(els).forEach((k) => { if (els[k] === e || els[k].parentNode === e) delete els[k]; }); } };
  return e;
}
const navUl = mkEl('ul');
const document = {
  body: mkEl('body'),
  querySelector: (q) => (q === '#sidebar nav ul' ? navUl : null),
  getElementById: (id) => {
    if (els[id]) return els[id];
    if (id === 'myreports-list' && els['myreports-overlay']) return (els['myreports-list'] = mkEl('div'));
    return null;
  },
  createElement: mkEl,
  addEventListener: (t, fn) => { assert.strictEqual(t, 'click'); assert.ok(!clickHandler, 'wired once'); clickHandler = fn; }
};
function target(attrs) { // element matching closest() by attribute selectors
  return { closest: (sel) => {
    const m = /^\[([a-z-]+)(?:="([^"]+)")?\]$/.exec(sel);
    if (m) return (m[1] in attrs && (m[2] === undefined || attrs[m[1]] === m[2])) ? { getAttribute: (k) => attrs[k] } : null;
    return attrs.id && sel === '#' + attrs.id ? {} : null;
  } };
}
const click = (attrs) => clickHandler({ target: target(attrs), preventDefault() {} });

// ---- fake core + Firestore
const updates = [], notifs = [], toasts = [], queries = [];
let promptAnswer = '';
let me = ADMIN, live = true;
let reportDocs = [];
const fbDb = { collection: (c) => {
  const q = { wh: [], where(f, op, v) { this.wh.push([f, op, v]); return this; },
    get() { queries.push([c, J(this.wh)]); return Promise.resolve({ docs: reportDocs.map((d) => ({ id: d.id, data: () => d })) }); },
    doc: (id) => ({ update: (p) => { updates.push([c + '/' + id, p]); return Promise.resolve(); } }) };
  return q;
} };
const coreApi = {
  liveUid: () => me, isLiveUser: () => live, escapeHtml: (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'),
  closeSocialOverlays: () => {}, findPost: (id) => (id === 'p1' ? { text: 'spam   post' } : null),
  notifWhen: (ms) => (ms ? '2h' : ''), tsMillis: (t) => (t && t.ms) || 0, toast: (m) => toasts.push(m),
  sendNotif: (to, type, postId, text) => notifs.push({ to, type, postId, text }),
  get ADMIN_UID() { return ADMIN; }, get SITE_ID() { return 'airlineschat'; }, get fbDb() { return fbDb; }
};
const win = { prompt: () => promptAnswer };
const ctx = { window: win, document, console, Date, setTimeout: (f) => f(),
  firebase: { firestore: { FieldValue: { serverTimestamp: () => 'TS', arrayUnion: (x) => ({ arrayUnion: x }) } } } };
vm.createContext(ctx);
vm.runInContext(plug, ctx);
const api = ctx.window.__subxPlugins[0](coreApi);
assert.deepStrictEqual(Object.keys(api).sort(), ['reportTriage', 'syncMyReports']);

// admin triage row
const row = api.reportTriage({ id: 'r1', reporterUid: 'uR', status: 'open' });
assert.ok(row.startsWith('<p>Received</p>'));
for (const s of ['reviewing', 'actioned', 'dismissed']) assert.ok(row.includes('data-report-status="' + s + '" data-report-id="r1" data-report-uid="uR"'), s);
assert.ok(!api.reportTriage({ id: 'r1', reporterUid: 'uR', status: 'reviewing' }).includes('data-report-status="reviewing"'), 'no Reviewing button once reviewing');
assert.ok(api.reportTriage({ id: '"x', reporterUid: 'u', status: '<b>' }).includes('&lt;b&gt;'), 'escaped');

// admin: wire + no My reports entry for the admin
api.syncMyReports();
assert.ok(clickHandler, 'listener wired');
assert.strictEqual(navUl.children.length, 0);

// actioned with a note -> audit fields, resolution, report_update notif to the reporter
promptAnswer = '  Removed   the post.  ';
click({ 'data-report-status': 'actioned', 'data-report-id': 'r1', 'data-report-uid': 'uR' });
await new Promise((r) => setImmediate(r));
assert.deepStrictEqual(J(updates[0][0]), 'reports/r1');
const p = updates[0][1];
assert.strictEqual(p.status, 'actioned'); assert.strictEqual(p.reviewedBy, ADMIN); assert.strictEqual(p.reviewedAt, 'TS');
assert.strictEqual(p.resolution, 'Removed the post.');
assert.deepStrictEqual(Object.keys(p.history.arrayUnion).sort(), ['by', 'ms', 'status']);
assert.deepStrictEqual(notifs[0], { to: 'uR', type: 'report_update', postId: '', text: 'We reviewed your report and took action. Removed the post.' });
assert.ok(toasts[0] === 'Report: Action taken');
// reviewing: no prompt, no resolution
win.prompt = () => { throw new Error('no prompt for reviewing'); };
click({ 'data-report-status': 'reviewing', 'data-report-id': 'r2', 'data-report-uid': 'uR' });
await new Promise((r) => setImmediate(r));
assert.strictEqual(updates[1][1].status, 'reviewing'); assert.ok(!('resolution' in updates[1][1]));
assert.strictEqual(notifs[1].text, 'Your report is under review.');
win.prompt = () => promptAnswer;
// prompt cancelled -> nothing; bogus status -> nothing; 'open' -> nothing; non-admin -> nothing
promptAnswer = null;
click({ 'data-report-status': 'dismissed', 'data-report-id': 'r3', 'data-report-uid': 'uR' });
promptAnswer = '';
click({ 'data-report-status': 'deleted', 'data-report-id': 'r3', 'data-report-uid': 'uR' });
click({ 'data-report-status': 'open', 'data-report-id': 'r3', 'data-report-uid': 'uR' });
me = 'uR';
click({ 'data-report-status': 'dismissed', 'data-report-id': 'r3', 'data-report-uid': 'uR' });
await new Promise((r) => setImmediate(r));
assert.strictEqual(updates.length, 2); assert.strictEqual(notifs.length, 2);
// notif text always fits sendNotif (180) and the rules (280)
assert.ok('We reviewed your report. No action was needed. '.length + 120 <= 180);

// reporter: My reports entry, query scoped to me + this room (rules: reporter reads own only)
api.syncMyReports();
assert.strictEqual(navUl.children.length, 1);
assert.ok(navUl.children[0].innerHTML.includes('id="nav-myreports" data-myreports="1"'));
api.syncMyReports();
assert.strictEqual(navUl.children.length, 1, 'no duplicate entry');
reportDocs = [
  { id: 'a', postId: 'p1', status: 'actioned', resolution: 'Removed <spam>', createdAt: { ms: 1 } },
  { id: 'b', postId: 'gone', createdAt: { ms: 2 } }
];
click({ 'data-myreports': '1' });
await new Promise((r) => setImmediate(r));
assert.deepStrictEqual(queries[0], ['reports', [['siteId', '==', 'airlineschat'], ['reporterUid', '==', 'uR']]]);
const html = els['myreports-list'].innerHTML;
assert.ok(html.indexOf('(post no longer shown)') < html.indexOf('spam post'), 'newest first');
assert.ok(html.includes('<strong>Received</strong>') && html.includes('<strong>Action taken</strong>') && html.includes('Removed &lt;spam&gt;'));
// a report_update notif opens My reports
click({ 'data-notif-type': 'report_update', 'data-notif-id': 'n1' });
await new Promise((r) => setImmediate(r));
assert.strictEqual(queries.length, 2);
// signed out -> entry removed
live = false; api.syncMyReports();
assert.strictEqual(navUl.children.length, 0);

// report_update payload fits the NOTIFS_REPORTS paste (hasOnly keys) and the live rule (type <= 20)
const sctx = { fbDb: { collection: () => ({ doc: () => ({ collection: () => ({ add: (x) => { sctx.out = x; return Promise.resolve(); } }) }) }) },
  SITE_ID: 'airlineschat', console, firebase: { firestore: { FieldValue: { serverTimestamp: () => 'TS' } } } };
vm.createContext(sctx);
vm.runInContext('function liveUid(){return "' + ADMIN + '";} function isEmailVerified(){return true;}\n' + fnSrc(core, 'sendNotif'), sctx);
sctx.sendNotif('uR', 'report_update', '', 'We reviewed your report and took action.');
const allowed = ['toUid', 'fromUid', 'type', 'siteId', 'postId', 'read', 'text', 'createdAt'];
assert.ok(Object.keys(sctx.out).every((k) => allowed.includes(k)), Object.keys(sctx.out).join());
assert.ok('report_update'.length <= 20);
console.log('report-loop: triage writes status/reviewedBy/reviewedAt/history(+resolution) and notifies the reporter; My reports scoped to me+room; core stubs keep v1.2.2 behavior; core ' + Buffer.byteLength(core) + ' B');
