import fs from 'fs';
import path from 'path';
import assert from 'assert';
import { fileURLToPath } from 'url';

/*
 * Growth console: every post written through guardedPostWrite() carries authorType.
 * Admin UID (steward seeds / AI personas) -> 'steward'; any other uid -> 'human'.
 * Runs the real guardedPostWrite from factory/factory.js against a stub Firestore and checks the written doc.
 * Run: node test/authortype.test.js
 */
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const src = fs.readFileSync(path.join(root, 'factory', 'factory.js'), 'utf8');
const m = src.match(/  function guardedPostWrite\(doc\) \{[\s\S]*?\n  \}\n/);
assert.ok(m, 'guardedPostWrite() missing from factory/factory.js');
assert.strictEqual(src.split("doc.authorType = doc.authorUid === ADMIN_UID ? 'steward' : 'human';").length - 1, 1,
  'authorType line missing or duplicated');

const ADMIN = 'o774wL9hUVSi19EkDCgLqQomP8i2';
function harness() {
  const writes = [];
  const ref = { id: 'p1', set: d => { writes.push({ kind: 'set', d: d }); return Promise.resolve(); } };
  const fbDb = {
    collection: c => ({ doc: () => (c === 'posts' ? ref : { id: 'rl' }) }),
    batch: () => {
      const ops = [];
      return { set: (r, d) => ops.push({ r: r, d: d }), commit: () => { ops.forEach(o => { if (o.r === ref) writes.push({ kind: 'batch', d: o.d }); }); return Promise.resolve(); } };
    }
  };
  const firebase = { firestore: { FieldValue: { serverTimestamp: () => 'ST', increment: n => n } } };
  const fn = new Function('ADMIN_UID', 'fbDb', 'firebase', 'accountsOpen', 'ACC_CLOSED',
    'var guardState = { sending: false, rate: null };' +
    'function postGuardMessage() { return ""; } function notePostCommitted() {}' +
    'function utcMidnightTs() { return 0; } function rateDayEqual() { return false; }' +
    'function isPermDenied() { return false; } function nearUtcMidnight() { return false; } function otherDayOffset() { return 0; }' +
    m[0] + 'return guardedPostWrite;');
  return { writes: writes, write: fn(ADMIN, fbDb, firebase, () => true, 'closed') };
}

const cases = [
  [{ authorUid: 'member1', text: 'hi' }, 'human', 'batch'],
  [{ authorUid: ADMIN, text: 'seed', steward: true }, 'steward', 'set'],
  [{ authorUid: ADMIN, text: 'admin post' }, 'steward', 'set'],
  [{ authorUid: 'member2', text: 'spoof', authorType: 'steward' }, 'human', 'batch']
];
for (const [doc, want, kind] of cases) {
  const h = harness();
  await h.write(Object.assign({}, doc));
  assert.strictEqual(h.writes.length, 1, 'one post write');
  assert.strictEqual(h.writes[0].kind, kind, 'write path for ' + doc.authorUid);
  assert.strictEqual(h.writes[0].d.authorType, want, doc.text + ' -> ' + want);
}
console.log('authortype: ok (' + cases.length + ' cases)');
