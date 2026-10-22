import fs from 'fs';
import path from 'path';
import assert from 'assert';
import { fileURLToPath } from 'url';

/*
 * Accounts gate (fail closed). Open only when site.json accountsOpen === true and preview !== true.
 * Also checks every write path still carries its guard. Run: node test/accounts-gate.test.js
 */
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const src = fs.readFileSync(path.join(root, 'factory', 'factory.js'), 'utf8');
const m = src.match(/  function accountsOpen\(\) \{[\s\S]*?\n  \}\n/);
assert.ok(m, 'accountsOpen() missing from factory/factory.js');
const open = site => new Function('site', m[0] + 'return accountsOpen();')(site);

assert.strictEqual(open({ siteId: 'boyfriend', preview: true }), false, 'preview:true is closed');
assert.strictEqual(open({ siteId: 'buffettchat' }), false, 'accountsOpen missing is closed');
assert.strictEqual(open({ siteId: 'x', accountsOpen: 'true' }), false, 'accountsOpen must be boolean true');
assert.strictEqual(open({ siteId: 'x', accountsOpen: true, preview: true }), false, 'preview:true wins over accountsOpen:true');
assert.strictEqual(open({ siteId: 'x', accountsOpen: false }), false, 'accountsOpen:false is closed');
assert.strictEqual(open(null), false, 'no site.json is closed');
assert.strictEqual(open({ siteId: 'gpchat', accountsOpen: true }), true, 'gpchat shape is open');
assert.strictEqual(open({ siteId: 'x', accountsOpen: true, preview: false }), true, 'accountsOpen:true + preview:false is open');

const guards = [
  ["ensurePublicProfile", "if (!accountsOpen() && user.uid !== ADMIN_UID) return Promise.reject(new Error(ACC_CLOSED));"],
  ["guardedPostWrite", "if (!accountsOpen() && doc.authorUid !== ADMIN_UID) return Promise.reject(new Error(ACC_CLOSED));"],
  ["requireVerified", "if (!accountsOpen() && !isAdminUser() && action !== 'report' && action !== 'block') {"],
  ["register", "if (!accountsOpen()) { err.textContent = ACC_CLOSED;"],
  ["google click", "if (!accountsOpen() && !document.documentElement.classList.contains('acc-stew'))"],
  ["finishGoogle", "if (u && !accountsOpen() && u.uid !== ADMIN_UID) return fbAuth.signOut().then("],
  ["redirect", "if (u && !accountsOpen() && u.uid !== ADMIN_UID) return fbAuth.signOut();"],
  ["boot", "wireEvents();\n    applyAccountsGate();"]
];
for (const [name, s] of guards) assert.strictEqual(src.split(s).length - 1, 1, 'guard missing or duplicated: ' + name);
console.log('accounts-gate: ok (' + guards.length + ' guards, 8 cases)');
