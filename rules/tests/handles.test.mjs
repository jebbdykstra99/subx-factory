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
const pair = (uid, handle, site = '27chat', claimExtra = {}) => claimTx(uid, handle,
  Object.assign({ uid, siteId: site }, claimExtra),
  { siteId: site, displayName: 'Fan', handle });

await env.clearFirestore();

await t('H1 signed-out get fails', assertFails(anon().doc('handles/fan1').get()));
await t('H2 signed-in get of a missing handle ok', assertSucceeds(db('h1').doc('handles/missing').get()));
await t('H3 claim paired with users.handle ok', assertSucceeds(pair('h1', 'fan1')));
await t('H3b orphan claim without users.handle fails', assertFails(db('h1').doc('handles/orphan1').set({ uid: 'h1', siteId: '27chat' })));
await t('H4 owner reads the claim', assertSucceeds(db('h1').doc('handles/fan1').get()));
await t('H5 another signed-in user reads the claim', assertSucceeds(db('h2').doc('handles/fan1').get()));
await t('H5b signed-in list fails', assertFails(db('h2').collection('handles').limit(5).get()));
await t('H5d admin list fails', assertFails(db(ADMIN).collection('handles').limit(5).get()));
await t('H5c signed-out list fails', assertFails(anon().collection('handles').limit(5).get()));
await t('H6 duplicate claim by the owner fails', assertFails(pair('h1', 'fan1')));
await t('H6b merge update of the owner claim fails', assertFails(db('h1').doc('handles/fan1').set({ siteId: 'gpchat' }, { merge: true })));
await t('H7 another uid cannot claim the same handle', assertFails(pair('h2', 'fan1')));
await t('H7b another uid cannot overwrite the claim with the owner uid', assertFails(db('h2').doc('handles/fan1').set({ uid: 'h1', siteId: '27chat' })));
await t('H8 another uid claims a different handle', assertSucceeds(pair('h2', 'fan2', 'gpchat')));
await t('H9 claim body with only uid ok when users.handle matches', assertSucceeds(claimTx('h3', 'fan3', { uid: 'h3' }, { siteId: '27chat', displayName: 'Fan', handle: 'fan3' })));
await t('H10 extra key fails', assertFails(claimTx('h3', 'fanx', { uid: 'h3', siteId: '27chat', handle: 'fanx' }, { siteId: '27chat', handle: 'fanx' })));
await t('H11 missing uid fails', assertFails(claimTx('h3', 'fany', { siteId: '27chat' }, { siteId: '27chat', handle: 'fany' })));
await t('H12 uid mismatch fails', assertFails(claimTx('h3', 'fanz', { uid: 'h1', siteId: '27chat' }, { siteId: '27chat', handle: 'fanz' })));
await t('H13 unknown siteId fails', assertFails(claimTx('h3', 'fanbad', { uid: 'h3', siteId: 'not-a-room' }, { siteId: '27chat', handle: 'fanbad' })));
await t('H14 signed-out create fails', assertFails(anon().doc('handles/anon1').set({ uid: 'anon' })));
for (const reserved of ['admin', 'moderator', 'official', 'subx', 'support', 'takedown', 'jebb', 'jebb1', 'admin1', 'subxfan', 'j32b']) {
  await t('H15 reserved ' + reserved + ' fails for a member', assertFails(pair('h4', reserved)));
}
await t('H16 exact blocklist mod fails', assertFails(pair('h4', 'mod')));
await t('H17 leetspeak adm1n fails', assertFails(pair('h4', 'adm1n')));
await t('H18 uppercase fails', assertFails(pair('h4', 'Bad')));
await t('H19 length 16 fails', assertFails(pair('h4', 'a'.repeat(16))));
await t('H20 length 15 ok', assertSucceeds(pair('h4', 'a'.repeat(15))));
await t('H21 underscore ok', assertSucceeds(pair('h21', 'fan_ok')));
await t('H22 j32b is denied to a member even in the claim transaction', assertFails(pair('h5', 'j32b')));
await t('H23 j32b is denied to ADMIN_UID', assertFails(pair(ADMIN, 'j32b')));
await t('H24 admin cannot client-claim jebb', assertFails(pair(ADMIN, 'jebb')));
await t('H25 admin cannot client-claim subx, support, takedown, or adminfan', assertFails((async () => {
  await pair(ADMIN, 'subx');
  await pair(ADMIN, 'support');
  await pair(ADMIN, 'takedown');
  await pair(ADMIN, 'adminfan');
})()));
await t('H26 admin can claim an ordinary handle', assertSucceeds(pair(ADMIN, 'roomfan')));
await t('H27 stale delete while users.handle still matches fails', assertFails(db('h2').doc('handles/fan2').delete()));
await t('H28 other uid delete fails', assertFails(db('h1').doc('handles/fan2').delete()));
await t('H29 admin cannot delete another uid claim', assertFails(db(ADMIN).doc('handles/fan1').delete()));
await t('H30 release: delete the claim and clear users.handle', assertSucceeds((async () => {
  const d = db('h2');
  await d.runTransaction(async (tx) => {
    tx.delete(d.doc('handles/fan2'));
    tx.set(d.doc('users/h2'), { handle: FV.delete() }, { merge: true });
  });
})()));
await t('H30b another uid reclaims the released handle', assertSucceeds(pair('h6', 'fan2', '27chat')));

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
await t('H34 repeating the same handle after the claim exists ok', assertSucceeds((async () => {
  await pair('p4', 'p4fan', 'gpchat');
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
await t('H43 admin cannot claim reserved prefix jebbroom', assertFails(pair(ADMIN, 'jebbroom')));
await t('H44 admin cannot set users.handle j32b without a client claim', assertFails(db(ADMIN).doc('users/' + ADMIN).set({ siteId: '27chat', handle: 'j32b' }, { merge: true })));
await t('K1 swap: new claim, delete the old claim, point users.handle at the new id', assertSucceeds((async () => {
  const d = db('p4');
  await d.runTransaction(async (tx) => {
    tx.delete(d.doc('handles/p4fan'));
    tx.set(d.doc('handles/p4new'), { uid: 'p4', siteId: 'gpchat' });
    tx.set(d.doc('users/p4'), { siteId: 'gpchat', handle: 'p4new' }, { merge: true });
  });
})()));
await t('K2 swap without deleting the old claim fails', assertFails((async () => {
  const d = db('p4');
  await d.runTransaction(async (tx) => {
    tx.set(d.doc('handles/p4alt'), { uid: 'p4', siteId: 'gpchat' });
    tx.set(d.doc('users/p4'), { siteId: 'gpchat', handle: 'p4alt' }, { merge: true });
  });
})()));
await t('K3 release after the swap', assertSucceeds((async () => {
  const d = db('p4');
  await d.runTransaction(async (tx) => {
    tx.delete(d.doc('handles/p4new'));
    tx.set(d.doc('users/p4'), { handle: FV.delete() }, { merge: true });
  });
})()));
await t('K4 reclaim of the released handle by another uid', assertSucceeds(pair('p4b', 'p4new', 'gpchat')));

await seed(async (s) => s.doc('users/p9').set({
  siteId: 'gpchat', displayName: 'Fan', suspended: true, suspendedReason: 'under18', ageAttested18: false,
  profileHidden: true, deletionQueuedAt: QTS, ageConfirmed: true
}));
await t('H45 suspended and profileHidden member cannot claim or set a handle', assertFails(claimTx('p9', 'u18fan', { uid: 'p9', siteId: 'gpchat' }, { siteId: 'gpchat', handle: 'u18fan' })));
await t('H45b suspended member cannot create the claim doc alone', assertFails(db('p9').doc('handles/u18fan').set({ uid: 'p9', siteId: 'gpchat' })));
await seed(async (s) => s.doc('users/p10').set({ siteId: 'gpchat', displayName: 'Fan', profileHidden: true }));
await t('H45c profileHidden without suspended cannot claim', assertFails(pair('p10', 'hidfan')));
await t('H45d profileHidden member can still edit displayName', assertSucceeds(db('p10').doc('users/p10').set({ siteId: 'gpchat', displayName: 'Hidden Fan' }, { merge: true })));
await seed(async (s) => s.doc('users/p11').set({ siteId: 'gpchat', displayName: 'Fan', suspended: true, ageAttested18: false }));
await t('H45e suspended without profileHidden cannot change users.handle', assertFails(pair('p11', 'susfan')));
await t('H46 suspended member can still edit displayName', assertSucceeds(db('p9').doc('users/p9').update({ displayName: 'Fan Two' })));
await t('H47 restricted member still cannot drop the queue', assertFails(db('p9').doc('users/p9').update({ deletionQueuedAt: FV.delete() })));

console.log(results.join('\n'));
console.log(failN ? `\n${failN} FAILED` : '\nALL PASS');
await env.cleanup();
process.exit(failN ? 1 : 0);
