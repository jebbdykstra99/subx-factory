// Storage rules tests (local emulator only, demo-* project; never touches prod).
// Run: npm run test:storage            (proposed: all 20 rooms upload)
//      npm run test:storage:baseline   (box copy of deployed rules: 311chat + wave four denied)
import { initializeTestEnvironment, assertSucceeds, assertFails } from '@firebase/rules-unit-testing';
import fs from 'fs';
const BASELINE = process.env.MODE === 'baseline';
const env = await initializeTestEnvironment({ projectId: 'demo-subx-storage',
  storage: { rules: fs.readFileSync(process.env.RULES, 'utf8'), host: '127.0.0.1', port: 9199 } });
const st = (uid, verified = true) => env.authenticatedContext(uid, { email_verified: verified, email: uid + '@x.com' }).storage();
const bytes = (n) => new Uint8Array(n);
const MB = 1024 * 1024;
// Real siteIds from each room's site.json (20 rooms).
const OLD = ['gpchat', '27chat', 'bartchat', 'popechat', 'samochat', '415chat', 'buffettchat', 'buffet', 'booze', 'boyfriend',
  'cia', 'cobra', 'gaichat', 'recruitchat', '808chat'];
const NEW = ['311chat', 'airlineschat', 'amachat', 'atmchat', 'behindtheblackwall'];
const results = []; let failN = 0;
async function t(name, p) { try { await p; results.push('PASS ' + name); } catch (e) { failN++; results.push('FAIL ' + name + ' :: ' + String(e.message || e).slice(0, 160)); } }
const up = (s, path, n, type) => s.ref(path).put(bytes(n), { contentType: type });

for (const sid of OLD) await t(`post image ${sid} ok`, assertSucceeds(up(st('u1'), `posts/${sid}/u1/1.jpg`, 1000, 'image/jpeg')));
for (const sid of NEW) {
  const p = up(st('u1'), `posts/${sid}/u1/1.jpg`, 1000, 'image/jpeg');
  await t(`post image ${sid} ${BASELINE ? 'DENIED (baseline gap)' : 'ok'}`, BASELINE ? assertFails(p) : assertSucceeds(p));
  const s2 = up(st('u1'), `stories/${sid}/u1/s1.mp4`, 1000, 'video/mp4');
  await t(`story video ${sid} ${BASELINE ? 'DENIED (baseline gap)' : 'ok'}`, BASELINE ? assertFails(s2) : assertSucceeds(s2));
}
for (const sid of [...OLD, ...NEW]) {
  await t(`${sid}: 5 MB post image denied`, assertFails(up(st('u2'), `posts/${sid}/u2/big.jpg`, 5 * MB, 'image/jpeg')));
  await t(`${sid}: non-image post denied`, assertFails(up(st('u2'), `posts/${sid}/u2/x.html`, 100, 'text/html')));
  await t(`${sid}: upload into another uid folder denied`, assertFails(up(st('u2'), `posts/${sid}/u3/1.jpg`, 100, 'image/png')));
  await t(`${sid}: unverified email post image denied`, assertFails(up(st('u4', false), `posts/${sid}/u4/1.jpg`, 100, 'image/png')));
  await t(`${sid}: signed-out upload denied`, assertFails(env.unauthenticatedContext().storage().ref(`posts/${sid}/u5/1.jpg`).put(bytes(10), { contentType: 'image/png' })));
  await t(`${sid}: 8 MB story denied`, assertFails(up(st('u2'), `stories/${sid}/u2/big.mp4`, 8 * MB, 'video/mp4')));
}
await t('unknown room denied', assertFails(up(st('u1'), 'posts/notarealsite/u1/1.jpg', 100, 'image/png')));
await t('short alias "atm" not in storage list (rooms upload with full siteId)', assertFails(up(st('u1'), 'posts/atm/u1/1.jpg', 100, 'image/png')));
await t('public read of a post image ok', assertSucceeds(env.unauthenticatedContext().storage().ref(`posts/gpchat/u1/1.jpg`).getMetadata()));
console.log(results.join('\n'));
console.log(`\n${results.length - failN}/${results.length} pass (${BASELINE ? 'BASELINE' : 'PROPOSED'})`);
await env.cleanup();
process.exit(failN ? 1 : 0);
