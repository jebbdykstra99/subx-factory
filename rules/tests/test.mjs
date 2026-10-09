import { initializeTestEnvironment, assertSucceeds, assertFails } from '@firebase/rules-unit-testing';
import firebase from 'firebase/compat/app';
import 'firebase/compat/firestore';
import fs from 'fs';
const FV = firebase.firestore.FieldValue, TS = firebase.firestore.Timestamp;
const ADMIN = 'o774wL9hUVSi19EkDCgLqQomP8i2';
const env = await initializeTestEnvironment({ projectId: 'demo-subx-guard',
  firestore: { rules: fs.readFileSync(process.env.RULES, 'utf8'), host: '127.0.0.1', port: 8080 } });
const db = (uid, verified = true) => env.authenticatedContext(uid, { email_verified: verified, email: uid + '@x.com' }).firestore();
const utcDay = () => { const d = new Date(); return TS.fromDate(new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()))); };
const base = (uid, site = 'gpchat', extra = {}) => Object.assign({ siteId: site, parentId: null, authorUid: uid, authorName: 'Fan ' + uid,
  authorHandle: 'fan' + uid.toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 10), text: 'Box box box', likes: {}, likeCount: 0, replyCount: 0,
  nestSlug: '', createdAt: FV.serverTimestamp() }, extra);
async function guardedPost(d, uid, data, prev) {
  const b = d.batch(); const ref = d.collection('posts').doc();
  b.set(ref, data);
  const today = utcDay();
  const sameDay = prev && prev.day && prev.day.isEqual(today);
  b.set(d.collection('rateLimits').doc(uid), { lastPostAt: FV.serverTimestamp(), day: today, dayCount: sameDay ? FV.increment(1) : 1 }, { merge: true });
  await b.commit(); return ref;
}
const results = []; let failN = 0;
const STEP1_EXPECTED = ['2 ', '21b ']; // throttle not mandatory until step 3 (guardedSite = [])
async function t(name, p) { try { await p; results.push('PASS ' + name); } catch (e) {
  if (process.env.MODE === 'step1' && STEP1_EXPECTED.some((x) => name.startsWith(x))) { results.push('EXPECTED(step1) ' + name); return; }
  failN++; results.push('FAIL ' + name + ' :: ' + (e.message || e).slice(0, 200)); } }
const seed = async (fn) => env.withSecurityRulesDisabled(async (c) => fn(c.firestore()));

await env.clearFirestore();
await seed(async (s) => { await s.doc('posts/p1').set({ siteId: 'gpchat', authorUid: 'u9', text: 'parent', replyCount: 0, likes: {}, createdAt: TS.now() });
  await s.doc('posts/p27').set({ siteId: '27chat', authorUid: 'u9', text: 'other room', replyCount: 0, likes: {}, createdAt: TS.now() }); });

await t('1 gpchat member post + throttle batch succeeds', assertSucceeds(guardedPost(db('u1'), 'u1', base('u1'))));
await t('2 gpchat post without throttle doc fails', assertFails(db('u2').collection('posts').add(base('u2'))));
await t('3 second post within 20s fails', assertFails(guardedPost(db('u1'), 'u1', base('u1'), { day: utcDay() })));
await t('4 future createdAt fails (pin-to-top)', assertFails(guardedPost(db('u3'), 'u3', base('u3', 'gpchat', { createdAt: TS.fromDate(new Date('2099-01-01')) }))));
await t('5 forged likeCount fails', assertFails(guardedPost(db('u4'), 'u4', base('u4', 'gpchat', { likeCount: 9999 }))));
await t('6 impersonation handle "admin" fails', assertFails(guardedPost(db('u5'), 'u5', base('u5', 'gpchat', { authorHandle: 'admin' }))));
await t('6c real fan names still ok', assertSucceeds(guardedPost(db('u30'), 'u30', base('u30', 'gpchat', { authorName: 'Badminton Modesto Fan', authorHandle: 'modestofan' }))));
await t('6b impersonation name "gpchat Official" fails', assertFails(guardedPost(db('u5'), 'u5', base('u5', 'gpchat', { authorName: 'gpchat Official' }))));
await t('7 3 links fails', assertFails(guardedPost(db('u6'), 'u6', base('u6', 'gpchat', { text: 'a https://a.com b https://b.com c https://c.com' }))));
await t('7b 2 links ok', assertSucceeds(guardedPost(db('u7'), 'u7', base('u7', 'gpchat', { text: 'a https://a.com b https://b.com' }))));
await t('7c spam shortener fails', assertFails(guardedPost(db('u8'), 'u8', base('u8', 'gpchat', { text: 'win bit.ly/xyz' }))));
await t('7d 281 chars fails', assertFails(guardedPost(db('u10'), 'u10', base('u10', 'gpchat', { text: 'x'.repeat(281) }))));
await t('7e unknown field fails', assertFails(guardedPost(db('u11'), 'u11', base('u11', 'gpchat', { pinned: true }))));
await t('8 27chat legacy client post (no throttle) still works', assertSucceeds(db('u12').collection('posts').add(base('u12', '27chat'))));
await t('9 27chat future createdAt fails', assertFails(db('u13').collection('posts').add(base('u13', '27chat', { createdAt: TS.fromDate(new Date('2099-01-01')) }))));
await t('10 reply same site ok', assertSucceeds(guardedPost(db('u14'), 'u14', base('u14', 'gpchat', { parentId: 'p1' }))));
await t('10b reply to other-site parent fails', assertFails(guardedPost(db('u15'), 'u15', base('u15', 'gpchat', { parentId: 'p27' }))));
await t('10c reply to missing parent fails', assertFails(guardedPost(db('u15'), 'u15', base('u15', 'gpchat', { parentId: 'nope' }))));
await t('11 replyCount bump still works', assertSucceeds(db('u16').doc('posts/p1').update({ replyCount: FV.increment(1) })));
await t('11b like still works', assertSucceeds(db('u16').doc('posts/p1').update({ likes: { u16: true } })));
await t('12 admin deletes member post', assertSucceeds(db(ADMIN).doc('posts/p1').delete()));
await seed(async (s) => s.doc('posts/p2').set({ siteId: 'gpchat', authorUid: 'u9', text: 'x', likes: {}, createdAt: TS.now() }));
await t('12b non-author non-admin delete fails', assertFails(db('u16').doc('posts/p2').delete()));
await t('13 admin backdated steward post still works', assertSucceeds(db(ADMIN).collection('posts').add(base(ADMIN, 'gpchat', { authorName: 'Steward', authorHandle: 'pitwall', createdAt: TS.fromDate(new Date(Date.now() - 60000)), adminSeed: true }))));
await t('14 unverified email fails', assertFails(guardedPost(db('u17', false), 'u17', base('u17'))));
await seed(async (s) => s.doc('rateLimits/u18').set({ lastPostAt: TS.fromDate(new Date(Date.now() - 3600e3)), day: utcDay(), dayCount: 50 }));
await t('15 daily cap 50 blocks 51st', assertFails(guardedPost(db('u18'), 'u18', base('u18'), { day: utcDay() })));
await seed(async (s) => s.doc('rateLimits/u19').set({ lastPostAt: TS.fromDate(new Date(Date.now() - 3600e3)), day: utcDay(), dayCount: 49 }));
await t('15b 50th post ok', assertSucceeds(guardedPost(db('u19'), 'u19', base('u19'), { day: utcDay() })));
await seed(async (s) => s.doc('rateLimits/u20').set({ lastPostAt: TS.fromDate(new Date(Date.now() - 3600e3)), day: TS.fromDate(new Date(Date.now() - 86400e3 * 2)), dayCount: 50 }));
await t('15c new UTC day resets to 1', assertSucceeds(guardedPost(db('u20'), 'u20', base('u20'), { day: TS.fromDate(new Date(0)) })));
await t('16 user cannot delete own rateLimits doc', assertFails(db('u1').doc('rateLimits/u1').delete()));
await t('16b user cannot rewind lastPostAt', assertFails(db('u1').doc('rateLimits/u1').set({ lastPostAt: TS.fromDate(new Date(0)) }, { merge: true })));
await t('17 profile role field rejected', assertFails(db('u21').doc('users/u21').set({ siteId: 'gpchat', displayName: 'x', role: 'admin' })));
await t('17b normal profile ok', assertSucceeds(db('u21').doc('users/u21').set({ siteId: 'gpchat', displayName: 'Fan', provider: 'google', createdAt: FV.serverTimestamp() }, { merge: true })));
await t('18 poll post ok', assertSucceeds(guardedPost(db('u22'), 'u22', base('u22', 'gpchat', { text: 'who wins', poll: { options: ['a', 'b'], votes: {}, duration: 3, endsAt: TS.now() } }))));
await t('18b poll with pre-filled votes fails', assertFails(guardedPost(db('u23'), 'u23', base('u23', 'gpchat', { text: 'who', poll: { options: ['a', 'b'], votes: { x: 1 }, duration: 3, endsAt: TS.now() } }))));
await t('19 report ok', assertSucceeds(db('u24').collection('reports').add({ siteId: 'gpchat', postId: 'p2', targetUid: 'u9', reporterUid: 'u24', reason: 'abuse', createdAt: FV.serverTimestamp() })));
await t('20 memberNests + create ok', assertSucceeds(db('u25').doc('sites/gpchat/memberNests/u25/rooms/my-nest').set({ siteId: 'gpchat', ownerUid: 'u25', slug: 'my-nest', label: 'My nest', nav: true, parent: null, kind: 'user' })));
// DM
const cid = 'gpchat__u26_u27';
await t('21 DM conv + first message with throttle ok', assertSucceeds((async () => { const d = db('u26'); const b = d.batch();
  b.set(d.doc('conversations/' + cid), { siteId: 'gpchat', participants: ['u26', 'u27'] });
  b.set(d.doc('conversations/' + cid + '/messages/m1'), { siteId: 'gpchat', fromUid: 'u26', text: 'hi', createdAt: FV.serverTimestamp() });
  b.set(d.doc('rateLimits/u26'), { lastMsgAt: FV.serverTimestamp() }, { merge: true }); await b.commit(); })()));
await t('21b DM message without throttle fails', assertFails(db('u26').doc('conversations/' + cid + '/messages/m2').set({ siteId: 'gpchat', fromUid: 'u26', text: 'hi again', createdAt: FV.serverTimestamp() })));

// ===== CLO #5/#6/#7 + allowlist (added 2026-10-08 evening) =====
await seed(async (s) => { await s.doc('users/u40').set({ siteId: 'gpchat', displayName: 'Private Fan', provider: 'google' }); });
await t('30 other member GET users/{uid} denied (privacy)', assertFails(db('u41').doc('users/u40').get()));
await t('30b unauthenticated GET users/{uid} denied', assertFails(env.unauthenticatedContext().firestore().doc('users/u40').get()));
await t('30c owner GET own users doc ok', assertSucceeds(db('u40').doc('users/u40').get()));
await t('30d steward/admin GET users doc ok', assertSucceeds(db(ADMIN).doc('users/u40').get()));
await t('30e member list users denied', assertFails(db('u41').collection('users').where('siteId', '==', 'gpchat').get()));
await t('30f admin DM picker list users ok', assertSucceeds(db(ADMIN).collection('users').where('siteId', '==', 'gpchat').limit(80).get()));
await t('31 write email into users doc denied', assertFails(db('u42').doc('users/u42').set({ siteId: 'gpchat', displayName: 'x', email: 'u42@x.com' })));
await t('31b write phone into users doc denied', assertFails(db('u42').doc('users/u42').set({ siteId: 'gpchat', displayName: 'x', phone: '+15555550100' })));
await t('31c own following/notifications reads ok', assertSucceeds(Promise.all([db('u40').collection('users/u40/following').get(), db('u40').collection('users/u40/notifications').get()])));
await t('31d other user notifications read denied', assertFails(db('u41').collection('users/u40/notifications').get()));
await t('32 report alert notif to Jebb ok', assertSucceeds(db('u43').collection('users/' + ADMIN + '/notifications').add({ toUid: ADMIN, fromUid: 'u43', type: 'report', siteId: 'gpchat', postId: 'p2', read: false, text: 'Reported post p2', createdAt: FV.serverTimestamp() })));
await t('32b report-type notif to a non-admin denied', assertFails(db('u43').collection('users/u40/notifications').add({ toUid: 'u40', fromUid: 'u43', type: 'report', siteId: 'gpchat', read: false, createdAt: FV.serverTimestamp() })));
await t('32c reply notif (legacy shape) still ok', assertSucceeds(db('u43').collection('users/u40/notifications').add({ toUid: 'u40', fromUid: 'u43', type: 'reply', siteId: 'gpchat', postId: 'p2', read: false, text: 'nice', createdAt: FV.serverTimestamp() })));
await t('33 member sets steward:true denied', assertFails(guardedPost(db('u44'), 'u44', base('u44', 'gpchat', { steward: true }))));
await t('33b member steward:false ok', assertSucceeds(guardedPost(db('u45'), 'u45', base('u45', 'gpchat', { steward: false }))));
await t('33c admin steward:true post ok', assertSucceeds(db(ADMIN).collection('posts').add(base(ADMIN, 'gpchat', { authorName: 'Pit Wall', authorHandle: 'pitwall', steward: true }))));
for (const sid of ['booze', 'buffet', 'boyfriend', 'cia', 'cobra', '311chat', 'airlineschat', 'amachat', 'atmchat', 'behindtheblackwall']) {
  await t('34 allowlist: legacy post on ' + sid + ' ok', assertSucceeds(db('a' + sid).collection('posts').add(base('a' + sid, sid))));
}
await t('34b unknown siteId denied', assertFails(db('u46').collection('posts').add(base('u46', 'notaroom'))));
console.log(results.join('\n')); console.log(failN ? `\n${failN} FAILED` : '\nALL PASS');
await env.cleanup(); process.exit(failN ? 1 : 0);
