// UNDER-18 FIELD LOCK: emulator tests for rules/firestore.rules.hub-signin.proposed.v2.
// Draft rules only. Does not deploy or publish. Covers merge, update+deleteField, replacement set,
// legacy ageConfirmed:true, queued-only, reason-only, the admin exemption, create, and a normal member.
import { initializeTestEnvironment, assertSucceeds, assertFails } from '@firebase/rules-unit-testing';
import firebase from 'firebase/compat/app';
import 'firebase/compat/firestore';
import fs from 'fs';
const FV = firebase.firestore.FieldValue, TS = firebase.firestore.Timestamp;
const ADMIN = 'o774wL9hUVSi19EkDCgLqQomP8i2';
const QTS = TS.fromDate(new Date('2026-11-04T23:15:52.000Z'));
const OTHER = TS.fromDate(new Date('2026-11-05T00:00:00.000Z'));
const env = await initializeTestEnvironment({ projectId: 'demo-subx-v2',
  firestore: { rules: fs.readFileSync(process.env.RULES, 'utf8'), host: '127.0.0.1', port: 8080 } });
const db = (uid, verified = true) => env.authenticatedContext(uid, { email_verified: verified, email: uid + '@x.com' }).firestore();
const results = []; let failN = 0;
async function t(name, p) { try { await p; results.push('PASS ' + name); } catch (e) { failN++; results.push('FAIL ' + name + ' :: ' + String(e.message || e).slice(0, 240)); } }
const seed = async (fn) => env.withSecurityRulesDisabled(async (c) => fn(c.firestore()));
const user = (uid) => db(uid).doc('users/' + uid);
const post = (uid) => Object.assign({ siteId: '27chat', parentId: null, authorUid: uid, authorName: 'Fan', authorHandle: 'fan1',
  text: 'Box box box', likes: {}, likeCount: 0, replyCount: 0, nestSlug: '', createdAt: FV.serverTimestamp() });

await env.clearFirestore();

// --- normal non-restricted member (regression) ---
await t('N1 signup merge (siteId, displayName, provider, createdAt)', assertSucceeds(user('n1').set({ siteId: 'gpchat', displayName: 'Fan', provider: 'google', createdAt: FV.serverTimestamp() }, { merge: true })));
await t('N2 age attestation (ageConfirmed and ageAttested18 true)', assertSucceeds(user('n1').set({ siteId: 'gpchat', ageConfirmed: true, ageAttested18: true, ageAttestedAt: FV.serverTimestamp() }, { merge: true })));
await t('N3 terms fields', assertSucceeds(user('n1').set({ siteId: 'gpchat', termsVersion: '2026-10-01', termsAcceptedAt: FV.serverTimestamp() }, { merge: true })));
await t('N4 profile edit displayName and bio', assertSucceeds(user('n1').set({ siteId: 'gpchat', displayName: 'Fan Two', bio: 'hello' }, { merge: true })));
await t('N4b profile edit via update()', assertSucceeds(user('n1').update({ bio: 'hello again' })));
await t('N5 hub profile without a handle', assertSucceeds(user('n5').set({ siteId: 'subx', displayName: 'Hub Fan' }, { merge: true })));
await t('N6 profileHidden true then false while not restricted', assertSucceeds((async () => {
  await user('n6').set({ siteId: 'gpchat', displayName: 'Fan', profileHidden: true });
  await user('n6').update({ profileHidden: false });
})()));
await t('N7 ageAttested18 false then true while not restricted', assertSucceeds((async () => {
  await user('n7').set({ siteId: 'gpchat', displayName: 'Fan', ageAttested18: false, ageConfirmed: false });
  await user('n7').update({ ageAttested18: true, ageConfirmed: true });
})()));
await t('N8 replacement set of a normal profile', assertSucceeds(user('n8').set({ siteId: 'gpchat', displayName: 'Fan', provider: 'google' })));
await t('N8b replacement set again', assertSucceeds(user('n8').set({ siteId: 'gpchat', displayName: 'Fan Two', bio: 'hi' })));
await t('N9 27chat post still ok', assertSucceeds(db('n9').collection('posts').add(post('n9'))));
await t('N10 dob still denied', assertFails(user('n10').set({ siteId: 'gpchat', displayName: 'Fan', dob: '2000-01-01' })));
await t('N11 email still denied', assertFails(user('n11').set({ siteId: 'gpchat', displayName: 'Fan', email: 'a@b.com' })));

// --- gpchat under-18 merge on a member who already attested (legacy ageConfirmed stays true) ---
await t('G0 attested profile before the gate', assertSucceeds(user('g1').set({ siteId: 'gpchat', displayName: 'Fan', ageConfirmed: true, ageAttested18: true, ageAttestedAt: FV.serverTimestamp() })));
await t('G1 under-18 merge (does not clear ageConfirmed)', assertSucceeds(user('g1').set({
  siteId: 'gpchat', suspended: true, suspendedReason: 'under18', ageAttested18: false, profileHidden: true,
  deletionQueuedAt: FV.serverTimestamp(), notifyUnder18Email: true
}, { merge: true })));
await t('G2 later displayName merge still ok', assertSucceeds(user('g1').set({ siteId: 'gpchat', displayName: 'Fan Two' }, { merge: true })));
await t('G3 repeating ageConfirmed true (unchanged legacy) ok', assertSucceeds(user('g1').set({ siteId: 'gpchat', ageConfirmed: true }, { merge: true })));
await t('G4 ageAttested18 true while suspended fails', assertFails(user('g1').set({ siteId: 'gpchat', ageAttested18: true }, { merge: true })));
await t('G5 retrying the gate with a new deletionQueuedAt fails', assertFails(user('g1').set({
  siteId: 'gpchat', suspended: true, suspendedReason: 'under18', ageAttested18: false, profileHidden: true,
  deletionQueuedAt: FV.serverTimestamp()
}, { merge: true })));
await t('G6 notifyUnder18Email can still change', assertSucceeds(user('g1').set({ siteId: 'gpchat', notifyUnder18Email: false }, { merge: true })));
await t('G7 suspended member post still fails', assertFails(db('g1').collection('posts').add(post('g1'))));
await t('G8 clear suspended still fails', assertFails(user('g1').update({ suspended: false })));

// --- seeded full restriction, fixed queue timestamp ---
await seed(async (s) => s.doc('users/s1').set({
  siteId: 'gpchat', displayName: 'Fan', suspended: true, suspendedReason: 'under18', ageAttested18: false,
  profileHidden: true, deletionQueuedAt: QTS, ageConfirmed: true, notifyUnder18Email: true
}));
await t('S2 merge displayName keeps the queue', assertSucceeds(user('s1').set({ siteId: 'gpchat', displayName: 'Fan Two' }, { merge: true })));
await t('S2b update() displayName ok', assertSucceeds(user('s1').update({ displayName: 'Fan Three' })));
await t('S3 update deleteField deletionQueuedAt fails', assertFails(user('s1').update({ deletionQueuedAt: FV.delete() })));
await t('S4 merge deleteField deletionQueuedAt fails', assertFails(user('s1').set({ deletionQueuedAt: FV.delete() }, { merge: true })));
await t('S5 replacement set omitting deletionQueuedAt fails', assertFails(user('s1').set({
  siteId: 'gpchat', displayName: 'Fan', suspended: true, suspendedReason: 'under18', ageAttested18: false,
  profileHidden: true, ageConfirmed: true
})));
await t('S6 update deletionQueuedAt to a different timestamp fails', assertFails(user('s1').update({ deletionQueuedAt: OTHER })));
await t('S7 replacement set with a different timestamp fails', assertFails(user('s1').set({
  siteId: 'gpchat', displayName: 'Fan', suspended: true, suspendedReason: 'under18', ageAttested18: false,
  profileHidden: true, deletionQueuedAt: OTHER, ageConfirmed: true
})));
await t('S8 update deletionQueuedAt to serverTimestamp fails', assertFails(user('s1').update({ deletionQueuedAt: FV.serverTimestamp() })));
await t('S9 replacement set keeping the exact queue and legacy ageConfirmed ok', assertSucceeds(user('s1').set({
  siteId: 'gpchat', displayName: 'Renamed', suspended: true, suspendedReason: 'under18', ageAttested18: false,
  profileHidden: true, deletionQueuedAt: QTS, ageConfirmed: true
})));
await t('S11 ageAttested18 true fails', assertFails(user('s1').update({ ageAttested18: true })));
await t('S12 change suspendedReason fails', assertFails(user('s1').update({ suspendedReason: 'other' })));
await t('S13 deleteField suspendedReason fails', assertFails(user('s1').update({ suspendedReason: FV.delete() })));
await t('S14 profileHidden false fails', assertFails(user('s1').update({ profileHidden: false })));
await t('S15 deleteField profileHidden fails', assertFails(user('s1').update({ profileHidden: FV.delete() })));
await t('S16 suspended false fails', assertFails(user('s1').update({ suspended: false })));
await t('S17 deleteField suspended fails', assertFails(user('s1').update({ suspended: FV.delete() })));
await t('S18 ageConfirmed true to false is allowed', assertSucceeds(user('s1').update({ ageConfirmed: false })));
await t('S19 ageConfirmed false to true now fails', assertFails(user('s1').update({ ageConfirmed: true })));

await seed(async (s) => s.doc('users/s2').set({
  siteId: 'gpchat', displayName: 'Fan', suspended: true, ageAttested18: false, ageConfirmed: false
}));
await t('S20 fill absent reason, profileHidden, and queue on a bare suspension', assertSucceeds(user('s2').set({
  siteId: 'gpchat', suspendedReason: 'under18', profileHidden: true, deletionQueuedAt: QTS
}, { merge: true })));
await t('S21 that filled queue can no longer change', assertFails(user('s2').update({ deletionQueuedAt: OTHER })));
await t('S22 that filled reason can no longer change', assertFails(user('s2').update({ suspendedReason: 'other' })));

// --- queued-only (deletionQueuedAt, suspended not set) ---
await seed(async (s) => s.doc('users/q1').set({
  siteId: 'gpchat', displayName: 'Fan', deletionQueuedAt: QTS, ageConfirmed: false, ageAttested18: false
}));
await t('Q2 queued-only ageConfirmed true fails', assertFails(user('q1').update({ ageConfirmed: true })));
await t('Q3 queued-only ageAttested18 true fails', assertFails(user('q1').update({ ageAttested18: true })));
await t('Q4 queued-only deleteField queue fails', assertFails(user('q1').update({ deletionQueuedAt: FV.delete() })));
await t('Q5 queued-only rewrite queue fails', assertFails(user('q1').update({ deletionQueuedAt: OTHER })));
await t('Q6 queued-only displayName ok', assertSucceeds(user('q1').update({ displayName: 'Fan Two' })));
await t('Q6b queued-only replacement omitting the queue fails', assertFails(user('q1').set({ siteId: 'gpchat', displayName: 'Fan', ageConfirmed: false, ageAttested18: false })));
await seed(async (s) => s.doc('users/q2').set({
  siteId: 'gpchat', displayName: 'Fan', deletionQueuedAt: QTS, ageAttested18: true, ageConfirmed: true
}));
await t('Q7 queued-only legacy ageAttested18 true stays writable', assertSucceeds(user('q2').update({ displayName: 'Fan Two' })));
await t('Q8 queued-only repeating ageConfirmed true ok', assertSucceeds(user('q2').update({ ageConfirmed: true })));
await t('Q9 queued-only cannot clear the queue to unlock age', assertFails(user('q2').update({ deletionQueuedAt: FV.delete(), ageConfirmed: true })));

// --- reason-only (suspendedReason under18, no suspended, no queue) ---
await seed(async (s) => s.doc('users/r1').set({
  siteId: 'gpchat', displayName: 'Fan', suspendedReason: 'under18', ageConfirmed: false, ageAttested18: false
}));
await t('R2 reason-only ageConfirmed true fails', assertFails(user('r1').update({ ageConfirmed: true })));
await t('R3 reason-only ageAttested18 true fails', assertFails(user('r1').update({ ageAttested18: true })));
await t('R4 reason-only change reason fails', assertFails(user('r1').update({ suspendedReason: 'other' })));
await t('R5 reason-only deleteField reason fails', assertFails(user('r1').update({ suspendedReason: FV.delete() })));
await t('R6 reason-only displayName ok', assertSucceeds(user('r1').update({ displayName: 'Fan Two' })));
await t('R7 reason-only may add a queue timestamp', assertSucceeds(user('r1').update({ deletionQueuedAt: QTS })));
await t('R8 that queue is then fixed', assertFails(user('r1').update({ deletionQueuedAt: FV.delete() })));

// --- create ---
await t('C1 create under-18 gate without ageConfirmed ok', assertSucceeds(user('c1').set({
  siteId: 'gpchat', displayName: 'Fan', suspended: true, suspendedReason: 'under18', ageAttested18: false,
  profileHidden: true, deletionQueuedAt: FV.serverTimestamp()
})));
await t('C2 create suspended with ageConfirmed true fails', assertFails(user('c2').set({
  siteId: 'gpchat', displayName: 'Fan', suspended: true, suspendedReason: 'under18', ageAttested18: false,
  ageConfirmed: true, deletionQueuedAt: FV.serverTimestamp()
})));
await t('C3 create suspended with ageAttested18 true fails', assertFails(user('c3').set({
  siteId: 'gpchat', displayName: 'Fan', suspended: true, ageAttested18: true
})));
await t('C4 create queued-only with ageConfirmed true fails', assertFails(user('c4').set({
  siteId: 'gpchat', displayName: 'Fan', deletionQueuedAt: FV.serverTimestamp(), ageConfirmed: true
})));
await t('C5 create queued-only with ageAttested18 true fails', assertFails(user('c5').set({
  siteId: 'gpchat', displayName: 'Fan', deletionQueuedAt: FV.serverTimestamp(), ageAttested18: true
})));
await t('C6 create reason-only with ageConfirmed true fails', assertFails(user('c6').set({
  siteId: 'gpchat', displayName: 'Fan', suspendedReason: 'under18', ageConfirmed: true
})));
await t('C7 create normal profile with both age fields true ok', assertSucceeds(user('c7').set({
  siteId: 'gpchat', displayName: 'Fan', ageConfirmed: true, ageAttested18: true, ageAttestedAt: FV.serverTimestamp()
})));
await t('C8 create with suspended and ageConfirmed true in one write fails', assertFails(user('c8').set({
  siteId: '27chat', displayName: 'Fan', suspended: true, ageConfirmed: true, ageAttested18: false
})));

// --- admin exemption is the existing suspendOk isAdmin() short-circuit, on the admin's own doc ---
await seed(async (s) => s.doc('users/' + ADMIN).set({
  siteId: 'gpchat', displayName: 'Steward', suspended: true, suspendedReason: 'under18', ageAttested18: false,
  profileHidden: true, deletionQueuedAt: QTS, ageConfirmed: false
}));
await t('A1 admin can clear queue, reason, profileHidden, and suspension on their own doc', assertSucceeds(db(ADMIN).doc('users/' + ADMIN).update({
  deletionQueuedAt: FV.delete(), suspended: false, suspendedReason: 'lifted', profileHidden: false,
  ageConfirmed: true, ageAttested18: true
})));
await t('A2 admin still cannot write another user doc', assertFails(db(ADMIN).doc('users/s1').update({ suspended: false, deletionQueuedAt: FV.delete() })));
await t('A3 a member still cannot lift their own seeded restriction', assertFails(user('q1').update({ deletionQueuedAt: FV.delete(), ageConfirmed: true })));

console.log(results.join('\n'));
console.log(failN ? `\n${failN} FAILED` : '\nALL PASS');
await env.cleanup();
process.exit(failN ? 1 : 0);
