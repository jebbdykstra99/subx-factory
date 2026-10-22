// node test/notifs-reports.test.js — v1.2.2: notifications + reports write real docs in every room.
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
const parents = {};
const fakeDb = {
  collection: (c1) => ({ doc: (d1) => ({
    get: () => Promise.resolve({ exists: !!parents[d1], data: () => parents[d1] }),
    collection: (c2) => ({
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
vm.runInContext('function liveUid(){return me;} function isEmailVerified(){return verified;} function findPost(id){return livePosts.filter(function(p){return p.id===id;})[0]||null;}\n' +
  fnSrc('sendNotif') + '\n' + fnSrc('writeMentionNotifs') + '\n' + fnSrc('writeReplyNotif'), ctx);
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
// cap: at most 5 distinct people per post, even with more handles (and repeats) in the text
ctx.livePosts = 'abcdefg'.split('').map((c) => ({ authorUid: 'u_' + c, handle: 'h' + c }));
writes.length = 0;
ctx.writeMentionNotifs('@ha @hb @ha @hc @hd @he @hf @hg', 'post10');
assert.deepStrictEqual(J(writes.map((w) => w.p.toUid)), ['u_a', 'u_b', 'u_c', 'u_d', 'u_e']);
// dedupe vs reply: parent author mentioned in a reply gets the reply notif only (parent loaded locally)
ctx.livePosts = [{ id: 'par1', authorUid: 'uB', handle: 'bee' }, { id: 'x', authorUid: 'uC', handle: 'cee' }];
writes.length = 0;
ctx.writeReplyNotif('par1', 'thanks @bee and @cee', 'reply1');
assert.deepStrictEqual(J(writes.map((w) => [w.p.toUid, w.p.type, w.p.postId])), [['uB', 'reply', 'par1'], ['uC', 'mention', 'reply1']]);
// a top-level post (no parent) still sends mentions
writes.length = 0;
ctx.writeReplyNotif(null, 'yo @bee', 'top1');
assert.deepStrictEqual(J(writes.map((w) => [w.p.toUid, w.p.type, w.p.postId])), [['uB', 'mention', 'top1']]);
// unverified: nothing
ctx.verified = false; writes.length = 0; ctx.writeReplyNotif('par1', '@cee', 'r2'); ctx.verified = true;
assert.strictEqual(writes.length, 0);
// dedupe vs reply when the parent is not loaded (author fetched from Firestore), then the async tail checks
parents.par2 = { authorUid: 'uC' };
writes.length = 0;
ctx.writeReplyNotif('par2', 'cc @cee @bee', 'reply2');
await new Promise((r) => setTimeout(r, 10));
assert.deepStrictEqual(J(writes.map((w) => [w.p.toUid, w.p.type, w.p.postId])), [['uC', 'reply', 'par2'], ['uB', 'mention', 'reply2']]);
// call sites
assert.ok(src.includes('writeReplyNotif(parentId, text, ref && ref.id);'), 'one notif entry point per new post');
assert.ok(!/writeReplyNotif\(parentId, text\);/.test(src), 'old reply-only call removed');
assert.ok(!/notifsOn\(\)[^\n]*!parentId/.test(src), 'reply notif no longer gated on features.notifs');
assert.ok(src.includes("sendNotif(post.authorUid, 'like', postId, '', 'like_' + postId + '_' + uid)"), 'like call site');
assert.ok(src.includes("if (!on) sendNotif(target, 'follow', '', '', 'follow_' + me);"), 'follow call site');
const reportAdds = src.split("collection('reports').add({").slice(1).map((s) => s.slice(0, s.indexOf('})')));
assert.strictEqual(reportAdds.length, 2);
reportAdds.forEach((b) => assert.ok(b.includes("status: 'open'"), 'report status open'));
assert.ok(!src.includes("composeErr('Reported. Thanks.')"), 'report outcome is a toast');
console.log('notifs-reports: like/follow/mention/reply write in every room; mentions capped at 5, no mention when the reply notif covers it; reports carry status open');
