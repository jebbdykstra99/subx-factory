// HUB SIGN-IN (2026-11-04): emulator tests for rules/firestore.rules.hub-signin.proposed.
// The hub (siteId 'subx') may hold accounts, follows, blocks, mutes and DMs; never posts, stories, reports or nests.
import { initializeTestEnvironment, assertSucceeds, assertFails } from '@firebase/rules-unit-testing';
import firebase from 'firebase/compat/app';
import 'firebase/compat/firestore';
import fs from 'fs';
const FV = firebase.firestore.FieldValue, TS = firebase.firestore.Timestamp;
const env = await initializeTestEnvironment({ projectId: 'demo-subx-hub',
  firestore: { rules: fs.readFileSync(process.env.RULES, 'utf8'), host: '127.0.0.1', port: 8080 } });
const HUB = process.env.MODE !== 'live';  // MODE=live: the same suite against the live rules, where hub writes must fail
const db = (uid, verified = true) => env.authenticatedContext(uid, { email_verified: verified, email: uid + '@x.com' }).firestore();
const anon = () => env.unauthenticatedContext().firestore();
const results = []; let failN = 0;
async function t(name, p) { try { await p; results.push('PASS ' + name); } catch (e) { failN++; results.push('FAIL ' + name + ' :: ' + String(e.message || e).slice(0, 200)); } }
const hub = (p) => (HUB ? assertSucceeds(p) : assertFails(p));
await env.clearFirestore();
await env.withSecurityRulesDisabled(async (c) => { const s = c.firestore();
  await s.doc('posts/p1').set({ siteId: 'gpchat', authorUid: 'u9', text: 'parent', replyCount: 0, likes: {}, createdAt: TS.now() }); });

// accounts: the shell's ensurePublicProfile write ({ siteId, displayName }, merge)
await t('H1 hub profile create (siteId subx, displayName)', hub(db('h1').doc('users/h1').set({ siteId: 'subx', displayName: 'Hub Fan' }, { merge: true })));
await t('H1b hub profile update (handle)', hub(db('h1').doc('users/h1').set({ siteId: 'subx', handle: 'hubfan' }, { merge: true })));
await t('H1c own profile read', assertSucceeds(db('h1').doc('users/h1').get()));
await t('H2 hub profile for another uid fails', assertFails(db('h1').doc('users/h2').set({ siteId: 'subx', displayName: 'X' })));
await t('H3 hub profile with email field fails', assertFails(db('h3').doc('users/h3').set({ siteId: 'subx', email: 'a@b.com' })));
await t('H4 hub profile with role/admin fails', assertFails(db('h4').doc('users/h4').set({ siteId: 'subx', admin: true })));
await t('H5 hub profile impersonation handle fails', assertFails(db('h5').doc('users/h5').set({ siteId: 'subx', handle: 'admin' })));
await t('H6 unknown siteId profile still fails', assertFails(db('h6').doc('users/h6').set({ siteId: 'subxx', displayName: 'X' })));
await t('H7 signed-out profile write fails', assertFails(anon().doc('users/h7').set({ siteId: 'subx' })));
await t('H7b hub profile dob field fails', assertFails(db('h7').doc('users/h7').set({ siteId: 'subx', dob: '2000-01-01' })));
// follows / blocks / mutes
await t('H8 hub follow ok', hub(db('h1').doc('users/h1/following/h2').set({ siteId: 'subx', targetUid: 'h2', createdAt: FV.serverTimestamp() })));
await t('H8b hub self-follow fails', assertFails(db('h1').doc('users/h1/following/h1').set({ siteId: 'subx', targetUid: 'h1' })));
await t('H8c hub follow unverified email fails', assertFails(db('h1', false).doc('users/h1/following/h3').set({ siteId: 'subx', targetUid: 'h3' })));
await t('H9 hub block ok', hub(db('h1').doc('users/h1/blocks/h4').set({ siteId: 'subx', blockerUid: 'h1', targetUid: 'h4' })));
await t('H10 hub mute ok', hub(db('h1').doc('users/h1/mutes/h5').set({ siteId: 'subx', muterUid: 'h1', targetUid: 'h5' })));
// notifications: hub may only send follow alerts
await t('H11 hub follow notification ok', hub(db('h1').doc('users/h2/notifications/n1').set({ toUid: 'h2', fromUid: 'h1', type: 'follow', siteId: 'subx', read: false, createdAt: FV.serverTimestamp() })));
await t('H11b hub like notification fails', assertFails(db('h1').doc('users/h2/notifications/n2').set({ toUid: 'h2', fromUid: 'h1', type: 'like', siteId: 'subx', postId: 'p1', read: false, createdAt: FV.serverTimestamp() })));
await t('H11c hub reply notification fails', assertFails(db('h1').doc('users/h2/notifications/n3').set({ toUid: 'h2', fromUid: 'h1', type: 'reply', siteId: 'subx', read: false, createdAt: FV.serverTimestamp() })));
// DMs
const cid = 'subx__h1_h2';
await t('H12 hub DM conversation + first message ok', hub((async () => { const d = db('h1'); const b = d.batch();
  b.set(d.doc('conversations/' + cid), { siteId: 'subx', participants: ['h1', 'h2'] });
  b.set(d.doc('conversations/' + cid + '/messages/m1'), { siteId: 'subx', fromUid: 'h1', text: 'hi', createdAt: FV.serverTimestamp() });
  await b.commit(); })()));
if (HUB) {
  await t('H12b participant reads hub DM', assertSucceeds(db('h2').doc('conversations/' + cid + '/messages/m1').get()));
  await t('H12c non-participant cannot read hub DM', assertFails(db('h3').doc('conversations/' + cid + '/messages/m1').get()));
  await t('H12d message siteId must match conversation', assertFails(db('h1').doc('conversations/' + cid + '/messages/m2').set({ siteId: 'gpchat', fromUid: 'h1', text: 'x', createdAt: FV.serverTimestamp() })));
}
// never on the hub: posts, stories, reports, bookmarks, nests
await t('H13 hub post fails', assertFails(db('h1').collection('posts').add({ siteId: 'subx', parentId: null, authorUid: 'h1', authorName: 'Hub Fan', authorHandle: 'hubfan', text: 'hello', likes: {}, likeCount: 0, replyCount: 0, nestSlug: '', createdAt: FV.serverTimestamp() })));
await t('H14 hub story fails', assertFails(db('h1').collection('stories').add({ siteId: 'subx', authorUid: 'h1', authorName: 'Hub Fan', text: 'x', createdAt: TS.now(), expiresAt: TS.fromDate(new Date(Date.now() + 864e5)) })));
await t('H15 hub report fails', assertFails(db('h1').collection('reports').add({ siteId: 'subx', postId: 'p1', targetUid: 'u9', reporterUid: 'h1', reason: 'abuse', createdAt: FV.serverTimestamp() })));
await t('H16 hub bookmark fails', assertFails(db('h1').doc('users/h1/bookmarks/p1').set({ siteId: 'subx', uid: 'h1', postId: 'p1' })));
await t('H17 hub memberNest fails', assertFails(db('h1').doc('sites/subx/memberNests/h1/rooms/n').set({ siteId: 'subx', ownerUid: 'h1', slug: 'n', label: 'N', nav: true, parent: null, kind: 'user' })));
// rooms unchanged
await t('H18 room profile (gpchat) still ok', assertSucceeds(db('r1').doc('users/r1').set({ siteId: 'gpchat', displayName: 'Room Fan' }, { merge: true })));
await t('H18b room follow still ok', assertSucceeds(db('r1').doc('users/r1/following/r2').set({ siteId: 'gpchat', targetUid: 'r2' })));
console.log(results.join('\n')); console.log(failN ? `\n${failN} FAILED` : '\nALL PASS');
await env.cleanup(); process.exit(failN ? 1 : 0);
