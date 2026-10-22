import fs from 'fs';
import path from 'path';
import assert from 'assert';
import { fileURLToPath } from 'url';
import { spawnSync } from 'child_process';

/*
 * Accounts gate, re-scoped 2026-10-22 (Jebb: anyone can sign up). Closed ONLY when site.json says accountsOpen:false
 * or accounts:'closed'. A missing flag is open; preview:true is the banner only and never closes sign-ups.
 * Also checks every write path still carries its guard, every rooms.json room has an explicit boolean accountsOpen,
 * and tools/stamp.py refuses a room without one. Run: node test/accounts-gate.test.js
 */
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const src = fs.readFileSync(path.join(root, 'factory', 'factory.js'), 'utf8');
const m = src.match(/  function accountsOpen\(\) \{[\s\S]*?\n  \}\n/);
assert.ok(m, 'accountsOpen() missing from factory/factory.js');
const open = site => new Function('site', m[0] + 'return accountsOpen();')(site);

const cases = [
  [{ siteId: 'gpchat', preview: true }, true, 'gpchat preview:true, no accounts flag is open'],
  [{ siteId: 'boyfriend', preview: true }, true, 'preview:true, no flag is open (banner only)'],
  [{ siteId: 'x', preview: true, accountsOpen: true }, true, 'preview:true + accountsOpen:true is open'],
  [{ siteId: 'x', accountsOpen: true, preview: false }, true, 'preview:false + accountsOpen:true is open'],
  [{ siteId: 'buffettchat' }, true, 'accountsOpen missing is open'],
  [null, true, 'no site.json is open'],
  [{ siteId: 'gpchat', accountsOpen: true }, true, 'gpchat shape is open'],
  [{ siteId: 'x', accountsOpen: false }, false, 'accountsOpen:false is closed'],
  [{ siteId: 'x', accountsOpen: false, preview: true }, false, 'accountsOpen:false + preview:true is closed'],
  [{ siteId: 'x', accounts: 'closed' }, false, "accounts:'closed' is closed"],
  [{ siteId: 'x', accounts: 'closed', accountsOpen: true }, false, "accounts:'closed' wins over accountsOpen:true"]
];
for (const [site, want, msg] of cases) assert.strictEqual(open(site), want, msg);
assert.ok(!/site\.preview/.test(src), 'preview must not be read by factory.js (banner only, static markup)');

// Juno: no room may open by omission. Every rooms.json room carries an explicit boolean; stamp.py refuses one without it.
const rooms = JSON.parse(fs.readFileSync(path.join(root, 'rooms.json'), 'utf8')).rooms;
for (const r of rooms) assert.strictEqual(typeof r.accountsOpen, 'boolean', 'rooms.json ' + r.room + ' needs an explicit accountsOpen');
const py = "import sys; sys.path.insert(0, 'tools'); import stamp as S\n" +
  "for v in (None, 'true', 1):\n" +
  "  e = {'room': 'newroom'}\n" +
  "  if v is not None: e['accountsOpen'] = v\n" +
  "  try: S.require_accounts_open(e); sys.exit('accepted %r' % (v,))\n" +
  "  except S.AccountsOpenMissing as x: assert 'accountsOpen' in str(x)\n" +
  "assert S.require_accounts_open({'room': 'r', 'accountsOpen': False}) is False\n";
const r = spawnSync('python3', ['-c', py], { cwd: root, encoding: 'utf8' });
assert.strictEqual(r.status, 0, 'stamp.py must refuse a room without an explicit boolean accountsOpen: ' + r.stderr + r.stdout);

const guards = [
  ["ensurePublicProfile", "if (!accountsOpen() && user.uid !== ADMIN_UID) return Promise.reject(new Error(ACC_CLOSED));"],
  ["guardedPostWrite", "if (!accountsOpen() && doc.authorUid !== ADMIN_UID) return Promise.reject(new Error(ACC_CLOSED));"],
  ["requireVerified", "if (!accountsOpen() && !isAdminUser() && action !== 'report' && action !== 'block') {"],
  ["register", "if (!accountsOpen()) { err.textContent = ACC_CLOSED;"],
  ["google click", "if (!accountsOpen() && !document.documentElement.classList.contains('acc-stew'))"],
  ["finishGoogle", "if (u && !accountsOpen() && u.uid !== ADMIN_UID) return fbAuth.signOut().then("],
  ["redirect", "if (u && !accountsOpen() && u.uid !== ADMIN_UID) return fbAuth.signOut();"],
  ["boot", "wireEvents();\n    applyAccountsGate();"],
  ["static note hidden when open", "if (n) n.style.display = o ? 'none' : '';"],
  ["once-guard on style id", "if (o || document.getElementById('acc-gate-css')) return;"],
  ["style id", "st.id = 'acc-gate-css';"],
  ["no duplicate note", "if (n || !p) return;"]
];
for (const [name, s] of guards) assert.strictEqual(src.split(s).length - 1, 1, 'guard missing or duplicated: ' + name);
assert.ok(!/document\.getElementById\('cv-accounts-closed'\)\) return/.test(src), 'gate must not short-circuit on the static note');

// Share menu (gpchat PR #73): x.com Web Intent and neutral labels in every factory output.
for (const f of ['factory.js', 'factory-gp.js', 'factory-rail.js']) {
  const t = fs.readFileSync(path.join(root, 'factory', f), 'utf8');
  for (const bad of ['twitter.com/intent/tweet', 'Post on X', 'Post on Reddit']) assert.ok(!t.includes(bad), f + ' still has ' + bad);
}
for (const s of ["'https://x.com/intent/post?text='", '>Share to x.com</button>', '>Share to Reddit</button>']) assert.strictEqual(src.split(s).length - 1, 1, 'share menu missing: ' + s);
console.log('accounts-gate: ok (' + guards.length + ' guards, ' + cases.length + ' cases, ' + rooms.length + ' rooms explicit, stamp refuses missing, share menu)');
