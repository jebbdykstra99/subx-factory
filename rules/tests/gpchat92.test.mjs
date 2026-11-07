// gpchat PR 92 (cursor/signin-loop-fix-0d1d) member writes against v2.
// Payloads match factory.js on that branch: email signup, Join acceptance, 18+ attest,
// and the under-18 merge that sets ageConfirmed and ageAttested18 to false.
// Draft rules only. Does not deploy or publish.
import { initializeTestEnvironment, assertSucceeds, assertFails } from '@firebase/rules-unit-testing';
import firebase from 'firebase/compat/app';
import 'firebase/compat/firestore';
import fs from 'fs';
const FV = firebase.firestore.FieldValue, TS = firebase.firestore.Timestamp;
const ATS = TS.fromDate(new Date('2026-11-01T12:00:00.000Z'));
const env = await initializeTestEnvironment({ projectId: 'demo-subx-v2',
  firestore: { rules: fs.readFileSync(process.env.RULES, 'utf8'), host: '127.0.0.1', port: 8080 } });
const db = (uid) => env.authenticatedContext(uid, { email_verified: true, email: uid + '@x.com' }).firestore();
const user = (uid) => db(uid).doc('users/' + uid);
const results = []; let failN = 0;
async function t(name, p) { try { await p; results.push('PASS ' + name); } catch (e) { failN++; results.push('FAIL ' + name + ' :: ' + String(e.message || e).slice(0, 240)); } }
const seed = async (fn) => env.withSecurityRulesDisabled(async (c) => fn(c.firestore()));

await env.clearFirestore();

await t('G92 signup ensurePublicProfile (siteId, displayName, createdAt)', assertSucceeds(user('e1').set({
  siteId: 'gpchat', displayName: 'Fan', createdAt: FV.serverTimestamp()
}, { merge: true })));
await t('G92 Join terms plus age fields on a fresh account', assertSucceeds(user('e1').set({
  siteId: 'gpchat', termsVersion: '1.1', termsAcceptedAt: FV.serverTimestamp(),
  ageConfirmed: true, ageAttested18: true, ageAttestedAt: FV.serverTimestamp()
}, { merge: true })));
await t('G92 google signup profile (provider, createdAt)', assertSucceeds(user('ggl').set({
  siteId: 'gpchat', displayName: 'Fan', provider: 'google', createdAt: FV.serverTimestamp()
}, { merge: true })));
await t('G92 18+ ageOnlyPatch', assertSucceeds(user('a18').set({
  siteId: 'gpchat', displayName: 'Fan', ageConfirmed: true, ageAttested18: true, ageAttestedAt: FV.serverTimestamp()
}, { merge: true })));
await t('G92 under-18 merge on a legacy true profile sets both age fields false', assertSucceeds(user('u18').set({
  siteId: 'gpchat', displayName: 'Fan', ageConfirmed: true, ageAttested18: true, ageAttestedAt: ATS,
  termsVersion: '1.1', termsAcceptedAt: ATS
}).then(() => user('u18').set({
  siteId: 'gpchat', suspended: true, suspendedReason: 'under18', ageAttested18: false, ageConfirmed: false,
  profileHidden: true, deletionQueuedAt: FV.serverTimestamp()
}, { merge: true }))));
await t('G92 that merge left ageAttestedAt in place', assertSucceeds(seed(async (s) => {
  const d = await s.doc('users/u18').get();
  if (!d.exists || !d.data().ageAttestedAt || !d.data().ageAttestedAt.isEqual(ATS)) throw new Error('ageAttestedAt changed');
  if (d.data().ageConfirmed !== false || d.data().ageAttested18 !== false) throw new Error('age flags not false');
})));
await t('G92 a second under-18 merge that rewrites deletionQueuedAt fails', assertFails(user('u18').set({
  siteId: 'gpchat', suspended: true, suspendedReason: 'under18', ageAttested18: false, ageConfirmed: false,
  profileHidden: true, deletionQueuedAt: FV.serverTimestamp()
}, { merge: true })));
await t('G92 18+ patch while already suspended is not sent; the write is denied', assertFails(user('u18').set({
  siteId: 'gpchat', ageConfirmed: true, ageAttested18: true, ageAttestedAt: FV.serverTimestamp()
}, { merge: true })));

console.log(results.join('\n'));
console.log(failN ? `\n${failN} FAILED` : '\nALL PASS');
await env.cleanup();
process.exit(failN ? 1 : 0);
