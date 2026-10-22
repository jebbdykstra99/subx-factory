// node test/notifs-reports.test.js — v1.3.0: notifications + reports write real docs in every room.
// Runs the shipped sendNotif/writeMentionNotifs bodies against a fake Firestore and checks the call sites.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert';
const src = fs.readFileSync(new URL('../factory/factory.js', import.meta.url), 'utf8');
function fnSrc(name) {
  const i = src.indexOf('  function ' + name + '(');
  assert.ok(i > 0, name + ' missing');
  const j = src.indexOf('\n  }\n', i);
  return src.slice(i, j + 4);
}
const writes = [];
const J = (x) => JSON.parse(JSON.stringify(x));
const fakeDb = {
  collection: (c1) => ({ doc: (d1) => ({ collection: (c2) => ({
    add: (p) => { writes.push({ path: [c1, d1, c2].join('/'), id: null, p }); return Promise.resolve(); },
    doc: (id) => ({ set: (p) => { writes.push({ path: [c1, d1, c2].join('/'), id, p }); return Promise.resolve(); } })
  }) }) })
};
const ctx = {
  fbDb: fakeDb, SITE_ID: 'gpchat', me: 'uA', verified: true, livePosts: [],
  console,
  firebase: { firestore: { FieldValue: { serverTimestamp: () => 'TS' } } }
};
vm.createContext(ctx);
vm.runInContext('function liveUid(){return me;} function isEmailVerified(){return verified;}\n' +
  fnSrc('sendNotif') + '\n' + fnSrc('writeMentionNotifs'), ctx);
// like / follow use fixed ids, reply-shaped payload, no self notif
ctx.sendNotif('uB', 'like', 'p1', '', 'like_p1_uA');
ctx.sendNotif('uB', 'follow', '', '', 'follow_uA');
ctx.sendNotif('uA', 'like', 'p1', '', 'like_p1_uA');
ctx.verified = false; ctx.sendNotif('uB', 'like', 'p9', '', 'x'); ctx.verified = true;
assert.strictEqual(writes.length, 2);
assert.deepStrictEqual(J(writes[0]), { path: 'users/uB/notifications', id: 'like_p1_uA', p: { toUid: 'uB', fromUid: 'uA', type: 'like', siteId: 'gpchat', read: false, createdAt: 'TS', postId: 'p1' } });
assert.deepStrictEqual(J(writes[1].p), { toUid: 'uB', fromUid: 'uA', type: 'follow', siteId: 'gpchat', read: false, createdAt: 'TS' });
// mentions: resolve handles from the loaded feed, once per person, never self
ctx.livePosts = [{ authorUid: 'uB', handle: 'Bee' }, { authorUid: 'uB', handle: 'bee' }, { authorUid: 'uA', handle: 'me' }, { authorUid: 'uC', handle: 'cee_1' }];
writes.length = 0;
ctx.writeMentionNotifs('hi @bee and @BEE and @me and @cee_1 and @nobody', 'post9');
assert.deepStrictEqual(J(writes.map((w) => [w.path, w.p.type, w.p.postId])), [['users/uB/notifications', 'mention', 'post9'], ['users/uC/notifications', 'mention', 'post9']]);
// call sites
assert.ok(/if \(!me \|\| !fbDb \|\| !isEmailVerified\(\) \|\| !parentId\) return;/.test(src), 'reply notif no longer gated on features.notifs');
assert.ok(src.includes("sendNotif(post.authorUid, 'like', postId, '', 'like_' + postId + '_' + uid)"), 'like call site');
assert.ok(src.includes("if (!on) sendNotif(target, 'follow', '', '', 'follow_' + me);"), 'follow call site');
assert.ok(src.includes('writeMentionNotifs(text, ref && ref.id);'), 'mention call site');
const reportAdds = src.split("collection('reports').add({").slice(1).map((s) => s.slice(0, s.indexOf('})')));
assert.strictEqual(reportAdds.length, 2);
reportAdds.forEach((b) => assert.ok(b.includes("status: 'open'"), 'report status open'));
assert.ok(!src.includes("composeErr('Reported. Thanks.')"), 'report outcome is a toast');
console.log('notifs-reports: like/follow/mention/reply write in every room; reports carry status open');
