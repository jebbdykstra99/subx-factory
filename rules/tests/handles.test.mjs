// HANDLES: emulator tests for rules/firestore.rules.hub-signin.proposed.v2.
// Mirrors 27chat PR 53 (824dfbe5) claimHandle: transaction sets handles/{handle} {uid, siteId?}
// and merges users/{uid}.handle. Draft rules only. Does not deploy or publish.
import { initializeTestEnvironment, assertSucceeds, assertFails } from '@firebase/rules-unit-testing';
import firebase from 'firebase/compat/app';
import 'firebase/compat/firestore';
import fs from 'fs';
const FV = firebase.firestore.FieldValue, TS = firebase.firestore.Timestamp;
const ADMIN = 'o774wL9hUVSi19EkDCgLqQomP8i2';
const QTS = TS.fromDate(new Date('2026-11-04T23:15:52.000Z'));
const env = await initializeTestEnvironment({ projectId: 'demo-subx-v2',
  firestore: { rules: fs.readFileSync(process.env.RULES, 'utf8'), host: '127.0.0.1', port: 8080 } });
const db = (uid, verified = true) => env.authenticatedContext(uid, { email_verified: verified, email: uid + '@x.com' }).firestore();
const anon = () => env.unauthenticatedContext().firestore();
const results = []; let failN = 0;
async function t(name, p) { try { await p; results.push('PASS ' + name); } catch (e) { failN++; results.push('FAIL ' + name + ' :: ' + String(e.message || e).slice(0, 240)); } }
const seed = async (fn) => env.withSecurityRulesDisabled(async (c) => fn(c.firestore()));
function claimTx(uid, handle, claim, userPatch) {
  const d = db(uid);
  return d.runTransaction(async (tx) => {
    tx.set(d.doc('handles/' + handle), claim);
    tx.set(d.doc('users/' + uid), userPatch, { merge: true });
  });
}

await env.clearFirestore();

await t('H1 signed-out get fails', assertFails(anon().doc('handles/fan1').get()));
await t('H2 signed-in get of a missing handle ok', assertSucceeds(db('h1').doc('handles/missing').get()));
await t('H3 claim {uid, siteId:27chat} ok', assertSucceeds(db('h1').doc('handles/fan1').set({ uid: 'h1', siteId: '27chat' })));
await t('H4 owner reads the claim', assertSucceeds(db('h1').doc('handles/fan1').get()));
await t('H5 another signed-in user reads the claim', assertSucceeds(db('h2').doc('handles/fan1').get()));
await t('H5b signed-in list ok', assertSucceeds(db('h2').collection('handles').limit(5).get()));
await t('H5c signed-out list fails', assertFails(anon().collection('handles').limit(5).get()));
await t('H6 duplicate claim by the owner fails', assertFails(db('h1').doc('handles/fan1').set({ uid: 'h1', siteId: '27chat' })));
await t('H6b merge update of the owner claim fails', assertFails(db('h1').doc('handles/fan1').set({ siteId: 'gpchat' }, { merge: true })));
await t('H7 another uid cannot claim the same handle', assertFails(db('h2').doc('handles/fan1').set({ uid: 'h2', siteId: '27chat' })));
await t('H7b another uid cannot overwrite the claim with the owner uid', assertFails(db('h2').doc('handles/fan1').set({ uid: 'h1', siteId: '27chat' })));
await t('H8 another uid claims a different handle', assertSucceeds(db('h2').doc('handles/fan2').set({ uid: 'h2', siteId: 'gpchat' })));
await t('H9 claim with only uid (siteId omitted) ok', assertSucceeds(db('h3').doc('handles/fan3').set({ uid: 'h3' })));
await t('H10 extra key fails', assertFails(db('h3').doc('handles/fanx').set({ uid: 'h3', siteId: '27chat', handle: 'fanx' })));
await t('H11 missing uid fails', assertFails(db('h3').doc('handles/fany').set({ siteId: '27chat' })));
await t('H12 uid mismatch fails', assertFails(db('h3').doc('handles/fanz').set({ uid: 'h1', siteId: '27chat' })));
await t('H13 unknown siteId fails', assertFails(db('h3').doc('handles/fanbad').set({ uid: 'h3', siteId: 'not-a-room' })));
await t('H14 signed-out create fails', assertFails(anon().doc('handles/anon1').set({ uid: 'anon' })));
for (const reserved of ['admin', 'moderator', 'official', 'subx', 'jebb', 'jebb1', 'admin1', 'subxfan']) {
  await t('H15 reserved ' + reserved + ' fails for a member', assertFails(db('h4').doc('handles/' + reserved).set({ uid: 'h4', siteId: '27chat' })));
}
await t('H16 exact blocklist mod fails', assertFails(db('h4').doc('handles/mod').set({ uid: 'h4' })));
await t('H17 leetspeak adm1n fails', assertFails(db('h4').doc('handles/adm1n').set({ uid: 'h4' })));
await t('H18 uppercase fails', assertFails(db('h4').doc('handles/Bad').set({ uid: 'h4' })));
await t('H19 length 16 fails', assertFails(db('h4').doc('handles/' + 'a'.repeat(16)).set({ uid: 'h4' })));
await t('H20 length 15 ok', assertSucceeds(db('h4').doc('handles/' + 'a'.repeat(15)).set({ uid: 'h4', siteId: '27chat' })));
await t('H21 underscore ok', assertSucceeds(db('h4').doc('handles/fan_ok').set({ uid: 'h4' })));
await t('H22 j32b is not a reserved prefix; a member can claim it', assertSucceeds(db('h5').doc('handles/j32b').set({ uid: 'h5', siteId: '27chat' })));
await t('H23 admin cannot take j32b once it is claimed', assertFails(db(ADMIN).doc('handles/j32b').set({ uid: ADMIN, siteId: '27chat' })));
await t('H24 admin claims reserved jebb', assertSucceeds(db(ADMIN).doc('handles/jebb').set({ uid: ADMIN, siteId: '27chat' })));
await t('H25 admin claims reserved subx, moderator, official, adminfan', assertSucceeds((async () => {
  await db(ADMIN).doc('handles/subx').set({ uid: ADMIN });
  await db(ADMIN).doc('handles/moderator').set({ uid: ADMIN, siteId: '27chat' });
  await db(ADMIN).doc('handles/official').set({ uid: ADMIN, siteId: 'gpchat' });
  await db(ADMIN).doc('handles/adminfan').set({ uid: ADMIN, siteId: '27chat' });
})()));
await t('H26 admin still cannot claim exact-blocklist mod', assertFails(db(ADMIN).doc('handles/mod').set({ uid: ADMIN })));
await t('H27 owner delete ok', assertSucceeds(db('h2').doc('handles/fan2').delete()));
await t('H28 other uid delete fails', assertFails(db('h2').doc('handles/fan1').delete()));
await t('H29 admin cannot delete another uid claim', assertFails(db(ADMIN).doc('handles/fan1').delete()));
await t('H30 after owner delete, another uid can claim it', assertSucceeds(db('h6').doc('handles/fan2').set({ uid: 'h6', siteId: '27chat' })));

await t('H31 users.handle without a claim fails', assertFails(db('p1').doc('users/p1').set({ siteId: '27chat', displayName: 'Fan', handle: 'noclaim' })));
await t('H32 signup, age attestation, and profile edit without a handle still ok', assertSucceeds((async () => {
  const u = db('p2').doc('users/p2');
  await u.set({ siteId: '27chat', displayName: 'Fan', provider: 'google', createdAt: FV.serverTimestamp() }, { merge: true });
  await u.set({ siteId: '27chat', ageConfirmed: true, ageAttested18: true, ageAttestedAt: FV.serverTimestamp(), termsVersion: '2026-10-01', termsAcceptedAt: FV.serverTimestamp() }, { merge: true });
  await u.set({ siteId: '27chat', displayName: 'Fan Two', bio: 'hello' }, { merge: true });
})()));
await t('H33 transaction claims the handle and sets users.handle', assertSucceeds(claimTx('p3', 'p3fan', { uid: 'p3', siteId: '27chat' }, {
  siteId: '27chat', displayName: 'Fan', handle: 'p3fan', ageConfirmed: true, ageAttested18: true, ageAttestedAt: FV.serverTimestamp()
})));
await t('H34 set users.handle after the claim already exists', assertSucceeds((async () => {
  await db('p4').doc('handles/p4fan').set({ uid: 'p4', siteId: 'gpchat' });
  await db('p4').doc('users/p4').set({ siteId: 'gpchat', displayName: 'Fan', handle: 'p4fan' }, { merge: true });
})()));
await t('H35 users.handle set to someone else\'s claim fails', assertFails(db('p4').doc('users/p4').set({ siteId: 'gpchat', handle: 'fan1' }, { merge: true })));
await t('H36 transaction that claims A but sets users.handle B fails', assertFails(claimTx('p5', 'handlea', { uid: 'p5', siteId: '27chat' }, { siteId: '27chat', handle: 'handleb' })));
await seed(async (s) => s.doc('users/p6').set({ siteId: 'gpchat', displayName: 'Legacy', handle: 'oldfan' }));
await t('H37 unchanged legacy handle without a claim stays writable', assertSucceeds(db('p6').doc('users/p6').set({ siteId: 'gpchat', displayName: 'Legacy Two', handle: 'oldfan' }, { merge: true })));
await t('H38 displayName merge that leaves the legacy handle in place ok', assertSucceeds(db('p6').doc('users/p6').set({ siteId: 'gpchat', bio: 'still here' }, { merge: true })));
await t('H39 changing the legacy handle without a new claim fails', assertFails(db('p6').doc('users/p6').set({ siteId: 'gpchat', handle: 'newfan' }, { merge: true })));
await t('H40 changing the legacy handle in the claim transaction ok', assertSucceeds(claimTx('p6', 'newfan', { uid: 'p6', siteId: 'gpchat' }, { siteId: 'gpchat', handle: 'newfan' })));
await t('H41 hub profile handle with a subx claim ok', assertSucceeds(claimTx('p7', 'hubfan', { uid: 'p7', siteId: 'subx' }, { siteId: 'subx', displayName: 'Hub Fan', handle: 'hubfan' })));
await t('H42 member cannot set a reserved users.handle', assertFails(claimTx('p8', 'jebb', { uid: 'p8', siteId: '27chat' }, { siteId: '27chat', handle: 'jebb' })));
await t('H43 admin claims reserved prefix jebbroom and sets users.handle in one transaction', assertSucceeds(claimTx(ADMIN, 'jebbroom', { uid: ADMIN, siteId: '27chat' }, { siteId: '27chat', displayName: 'Room Owner', handle: 'jebbroom' })));
await t('H44 admin sets users.handle to the already-claimed jebb', assertSucceeds(db(ADMIN).doc('users/' + ADMIN).set({ siteId: '27chat', handle: 'jebb' }, { merge: true })));

await seed(async (s) => s.doc('users/p9').set({
  siteId: 'gpchat', displayName: 'Fan', suspended: true, suspendedReason: 'under18', ageAttested18: false,
  profileHidden: true, deletionQueuedAt: QTS, ageConfirmed: true
}));
await t('H45 restricted member can still claim a handle and set it', assertSucceeds(claimTx('p9', 'u18fan', { uid: 'p9', siteId: 'gpchat' }, { siteId: 'gpchat', handle: 'u18fan' })));
await t('H46 that claim did not clear the queue', assertSucceeds(db('p9').doc('users/p9').update({ displayName: 'Fan Two' })));
await t('H47 restricted member still cannot drop the queue', assertFails(db('p9').doc('users/p9').update({ deletionQueuedAt: FV.delete() })));

console.log(results.join('\n'));
console.log(failN ? `\n${failN} FAILED` : '\nALL PASS');
await env.cleanup();
process.exit(failN ? 1 : 0);
