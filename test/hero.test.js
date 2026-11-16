// Rotating hero photo add-on (factory/factory-hero.js) in real Chrome.
// Usage: node test/hero.test.js   (CHROME=/usr/bin/google-chrome by default; needs puppeteer-core from devDependencies)
// Serves the repo on 127.0.0.1 with small room fixtures and checks: the fallback adds nothing (no element, no class,
// no CSS), refused items never render, 1 photo shows no dots or pause, the 9-photo set has carousel semantics,
// credits, 32px controls, eager photo 1 at low priority and lazy later photos (photo N+1 only once N is active),
// Next, Pause, the polite announcement after a user action, auto-rotation, and no auto-rotation with reduced motion.
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const CHROME = process.env.CHROME || '/usr/bin/google-chrome';
let fails = 0;
function ok(cond, msg) { console.log((cond ? 'ok   ' : 'FAIL ') + msg); if (!cond) fails++; }

const rooms = JSON.parse(fs.readFileSync(path.join(ROOT, 'hub/src/rooms.json'), 'utf8'));
const set = rooms.rooms.find(r => r.room === 'gpchat').heroImages;
const nine = { interval: 7000, items: set.items.map(it => Object.assign({}, it, {
  src: '/hub/site' + it.src, srcSm: '/hub/site' + it.srcSm, fallback: '/hub/site' + it.fallback })) };
const one = { items: [nine.items[0]] };
const fast = { interval: 4000, items: nine.items };
const bad = { items: [
  Object.assign({}, nine.items[0], { credit: '' }),
  Object.assign({}, nine.items[1], { license: 'CC BY-NC 4.0' }),
  Object.assign({}, nine.items[2], { src: 'https://upload.wikimedia.org/x.jpg' }),
  Object.assign({}, nine.items[3], { license: 'CC BY-ND 2.0' }),
  Object.assign({}, nine.items[4], { sourceUrl: 'javascript:alert(1)' }),
  nine.items[5]
] };
const BAD_ALT = nine.items[5].alt;
const CFG = { none: {}, empty: { items: [] }, one, nine, fast, bad };
const ROOM = (name) => '<!DOCTYPE html><html><head><meta charset="utf-8"><title>fx</title></head><body class="fx">' +
  '<main class="main" style="width:700px"><section class="page active" id="page-thoughts"><nav class="race-strip">Race strip</nav>' +
  '<div class="thoughts-tabs" role="tablist"><button>For You</button></div><div id="compose">Compose</div></section></main>' +
  '<script src="/fx/shell.js" data-site="/fx/' + name + '.json"></script><script src="/factory/factory-hero.js"></script></body></html>';
const TYPES = { '.js': 'text/javascript', '.webp': 'image/webp', '.jpg': 'image/jpeg', '.json': 'application/json', '.html': 'text/html' };
const server = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://x');
  let m;
  if ((m = u.pathname.match(/^\/fx\/room-([a-z]+)\.html$/))) { res.writeHead(200, { 'content-type': 'text/html' }); return res.end(ROOM(m[1])); }
  if ((m = u.pathname.match(/^\/fx\/([a-z]+)\.json$/)) && CFG[m[1]]) {
    res.writeHead(200, { 'content-type': 'application/json' });
    return res.end(JSON.stringify(Object.assign({ siteId: 'gpchat', name: 'gpchat' }, m[1] === 'none' ? {} : { heroImages: CFG[m[1]] })));
  }
  if (u.pathname === '/fx/shell.js') { res.writeHead(200, { 'content-type': 'text/javascript' }); return res.end('/* stands in for factory.js */'); }
  const f = path.join(ROOT, decodeURIComponent(u.pathname));
  if (!f.startsWith(ROOT) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'content-type': TYPES[path.extname(f)] || 'application/octet-stream' });
  fs.createReadStream(f).pipe(res);
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const BASE = 'http://127.0.0.1:' + server.address().port;
const puppeteer = (await import('puppeteer-core')).default;
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] });
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function open(name, { reduce = false, width = 1280 } = {}) {
  const p = await browser.newPage();
  await p.setViewport({ width, height: 900 });
  await p.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: reduce ? 'reduce' : 'no-preference' }]);
  const photos = []; const warns = [];
  p.on('request', (r) => { if (/\/assets\/hero\//.test(r.url())) photos.push(r.url().split('/').pop()); });
  p.on('console', (m) => { if (m.type() === 'warn' || m.type() === 'warning') warns.push(m.text()); });
  await p.mouse.move(5, 890);
  await p.goto(BASE + '/fx/room-' + name + '.html', { waitUntil: 'networkidle0' });
  await sleep(300);
  return { p, photos, warns };
}
const BEFORE = '<nav class="race-strip">Race strip</nav><div class="thoughts-tabs" role="tablist"><button>For You</button></div><div id="compose">Compose</div>';

for (const name of ['none', 'empty']) {
  const { p } = await open(name);
  const s = await p.evaluate(() => ({ hx: document.querySelectorAll('.hx').length, style: !!document.getElementById('hx-style'),
    html: document.getElementById('page-thoughts').innerHTML, body: document.body.className, sec: document.getElementById('page-thoughts').className }));
  ok(s.hx === 0 && !s.style, name + ': no figure and no injected CSS');
  ok(s.html === BEFORE && s.body === 'fx' && s.sec === 'page active', name + ': center column, classes and layout exactly as before');
  await p.close();
}

{
  const { p, warns } = await open('bad');
  const s = await p.evaluate(() => ({ n: document.querySelectorAll('.hx-slide').length, alt: document.querySelector('.hx-slide img') && document.querySelector('.hx-slide img').alt,
    ctrl: !!document.querySelector('.hx-ctrl') }));
  ok(s.n === 1 && s.alt === BAD_ALT, 'bad: only the one fully credited, allowed item renders');
  ok(warns.some(w => /heroImages: refused/.test(w)), 'bad: refusals are logged');
  await p.close();
}

{
  const { p } = await open('one');
  const s = await p.evaluate(() => ({ n: document.querySelectorAll('.hx-slide').length, ctrl: !!document.querySelector('.hx-ctrl'),
    dots: document.querySelectorAll('.hx-dot').length, pause: !!document.querySelector('.hx-pause'), credit: (document.querySelector('.hx-credit') || {}).textContent }));
  ok(s.n === 1 && !s.ctrl && !s.pause && s.dots === 0, 'one photo: shown without dots or pause');
  ok(s.credit === 'Photo: Mark McArdle \u00b7 CC BY-SA 2.0', 'one photo: credit still shown');
  await p.close();
}

{
  const { p, photos } = await open('nine');
  const s = await p.evaluate(() => {
    const f = document.querySelector('.hx'); const sl = [...f.querySelectorAll('.hx-slide')];
    const img = (k) => sl[k].querySelector('img'); const src = (k) => sl[k].querySelector('source');
    const r = (sel) => { const b = f.querySelector(sel).getBoundingClientRect(); return [Math.round(b.width), Math.round(b.height)]; };
    const page = document.getElementById('page-thoughts');
    return {
      role: f.getAttribute('role'), rd: f.getAttribute('aria-roledescription'), label: f.getAttribute('aria-label'), n: sl.length,
      slide0: [sl[0].getAttribute('role'), sl[0].getAttribute('aria-roledescription'), sl[0].getAttribute('aria-label'), sl[0].getAttribute('aria-hidden')],
      hidden1: sl[1].getAttribute('aria-hidden'),
      img0: [img(0).getAttribute('loading'), img(0).getAttribute('fetchpriority'), img(0).getAttribute('decoding'), img(0).getAttribute('width'), img(0).getAttribute('height'), img(0).style.objectPosition, !!img(0).getAttribute('src')],
      src0: src(0) && [src(0).type, src(0).getAttribute('srcset'), src(0).getAttribute('sizes')],
      img1: [img(1).getAttribute('loading'), !!img(1).getAttribute('src')],
      later: sl.slice(2).map((s, k) => !!img(k + 2).getAttribute('src') || !!(src(k + 2) && src(k + 2).getAttribute('srcset'))),
      alts: sl.map((s, k) => img(k).alt.length > 30),
      credit: f.querySelector('.hx-credit').textContent,
      authorHref: f.querySelector('.hx-author').getAttribute('href'), licHref: f.querySelector('.hx-lic').getAttribute('href'),
      font: getComputedStyle(f.querySelector('.hx-credit')).fontSize, capsule: getComputedStyle(f.querySelector('.hx-credit')).backgroundColor,
      dotsHidden: f.querySelector('.hx-dots').getAttribute('aria-hidden'), next: r('.hx-next'), pause: r('.hx-pause'),
      live: [f.querySelector('.hx-sr').getAttribute('aria-live'), f.querySelector('.hx-sr').textContent],
      order: [...page.children].map(e => e.className.split(' ')[0]), z: getComputedStyle(f.querySelector('.hx-slide.is-active')).zIndex
    };
  });
  ok(s.role === 'group' && s.rd === 'carousel' && s.label === 'gpchat photos' && s.n === 9, 'nine: figure role group, carousel, "gpchat photos", 9 slides');
  ok(s.slide0.join('|') === 'group|slide|1 of 9|' && s.hidden1 === 'true', 'nine: slides are labeled groups; inactive slides are aria-hidden');
  ok(s.img0.join('|') === 'eager|low|async|1200|800|50% 50%|true', 'nine: photo 1 eager, fetchpriority low, async, width/height and focal set');
  ok(s.src0 && s.src0[0] === 'image/webp' && /-1200\.webp 1200w, .*-600\.webp 600w$/.test(s.src0[1]) && s.src0[2] === '(min-width:1000px) 760px, 100vw', 'nine: <picture> with a WebP source (1200w, 600w) and a JPEG fallback');
  ok(s.img1[0] === 'lazy' && s.img1[1], 'nine: photo 2 is lazy and primed once photo 1 is active');
  ok(s.later.every(x => !x), 'nine: photos 3 to 9 have no src yet');
  ok(s.alts.every(Boolean), 'nine: every photo has real alt text');
  ok(s.credit === 'Photo: Mark McArdle \u00b7 CC BY-SA 2.0' && /commons\.wikimedia\.org\/wiki\/File:/.test(s.authorHref) && /creativecommons\.org\/licenses\/by-sa\/2\.0\//.test(s.licHref), 'nine: credit names the author (file page) and license (license page)');
  ok(s.font === '11px' && s.capsule === 'rgba(0, 0, 0, 0.62)', 'nine: credit is 11px in a 62% black capsule');
  ok(s.dotsHidden === 'true' && s.next.join('x') === '32x32' && s.pause.join('x') === '32x32', 'nine: decorative dots; Next and Pause are 32x32');
  ok(s.live[0] === 'polite' && s.live[1] === '', 'nine: polite live region stays silent until the user acts');
  ok(s.order.join(',') === 'race-strip,hx,thoughts-tabs,', 'nine: slot sits above the For You tabs and the composer, under the room brief strip');
  ok(Number(s.z) <= 1, 'nine: photo layer z-index stays at 1 or below');
  ok(!photos.some(f => /gp0[3-9]|gp10/.test(f)), 'nine: no request for photos 3 to 9 at load (' + photos.join(', ') + ')');
  await p.click('.hx-next');
  await sleep(200);
  const t = await p.evaluate(() => { const sl = [...document.querySelectorAll('.hx-slide')]; return { active: sl.findIndex(s => s.classList.contains('is-active')),
    hidden0: sl[0].getAttribute('aria-hidden'), live: document.querySelector('.hx-sr').textContent, primed: !!sl[2].querySelector('img').getAttribute('src'),
    credit: document.querySelector('.hx-credit').textContent, dot: [...document.querySelectorAll('.hx-dot')].findIndex(d => d.classList.contains('is-active')) }; });
  ok(t.active === 1 && t.hidden0 === 'true' && t.dot === 1, 'Next: photo 2 active, photo 1 aria-hidden, dot follows');
  ok(t.live === 'Photo 2 of 9', 'Next: announces "Photo 2 of 9"');
  ok(t.primed, 'Next: photo 3 gets its src only now');
  ok(t.credit === 'Photo: Eustace Bagge \u00b7 CC BY-SA 4.0', 'Next: credit follows the photo');
  await p.click('.hx-pause');
  const u = await p.evaluate(() => [document.querySelector('.hx-pause').getAttribute('aria-pressed'), document.querySelector('.hx-pause').getAttribute('aria-label')]);
  ok(u.join('|') === 'true|Play photos', 'Pause: aria-pressed true, label Play photos');
  await p.close();
}

{
  const { p } = await open('nine');
  const expected = [
    'Photo: Mark McArdle \u00b7 CC BY-SA 2.0',
    'Photo: Eustace Bagge \u00b7 CC BY-SA 4.0',
    'Photo: Chris Peeters \u00b7 CC0',
    'Photo: In Vitrio \u00b7 CC BY-SA 4.0 \u00b7 cropped',
    'Photo: Lothar Spurzem \u00b7 CC BY-SA 2.0 de \u00b7 cropped',
    'Photo: Paul Perreijn \u00b7 CC BY 2.0 \u00b7 cropped'
  ];
  for (let n = 0; n < expected.length; n++) {
    if (n) { await p.click('.hx-next'); await sleep(200); }
    const c = await p.evaluate(() => document.querySelector('.hx-credit').textContent);
    ok(c === expected[n], 'cropped note: photo ' + (n + 1) + ' credit is ' + expected[n]);
  }
  await p.close();
}

{
  const { p } = await open('fast');
  const fade = await p.evaluate(() => getComputedStyle(document.querySelector('.hx-slide')).transitionDuration);
  await sleep(4700);
  const a = await p.evaluate(() => [...document.querySelectorAll('.hx-slide')].findIndex(s => s.classList.contains('is-active')));
  ok(a === 1, 'auto-rotation: moves to photo 2 after the interval');
  ok(fade === '0.7s', 'auto-rotation: 0.7 second crossfade');
  await p.close();
}

{
  const { p } = await open('fast', { reduce: true });
  const s = await p.evaluate(() => ({ pause: document.querySelector('.hx-pause').hidden, fade: getComputedStyle(document.querySelector('.hx-slide')).transitionDuration }));
  await sleep(4700);
  const a = await p.evaluate(() => [...document.querySelectorAll('.hx-slide')].findIndex(s => s.classList.contains('is-active')));
  ok(s.pause && a === 0 && s.fade === '0s', 'reduced motion: no auto-rotation, no crossfade, no pause button');
  await p.click('.hx-next');
  const b = await p.evaluate(() => [...document.querySelectorAll('.hx-slide')].findIndex(s => s.classList.contains('is-active')));
  ok(b === 1, 'reduced motion: Next still works');
  await p.close();
}

{
  const p = await browser.newPage();
  await p.goto(BASE + '/fx/room-none.html', { waitUntil: 'networkidle0' });
  const v = await p.evaluate(() => { const L = window.SubxHero.licenseOk; return [L('CC0'), L('CC0 1.0'), L('Public Domain Mark 1.0'), L('CC BY 2.0'), L('CC BY-SA 2.0 de'), L('CC BY-SA 4.0'),
    !L('CC BY-NC 4.0'), !L('CC BY-ND 2.0'), !L('CC BY-NC-SA 3.0'), !L('All rights reserved'), !L('')]; });
  ok(v.every(Boolean), 'licenses: CC0, PDM, CC BY, CC BY-SA allowed; NC, ND and anything else refused');
  const h = await p.evaluate(() => { const r = window.SubxHero.validate({ items: [{ src: '//cdn.example.com/a.webp', alt: 'a', credit: 'b', license: 'CC0', licenseUrl: 'https://creativecommons.org/publicdomain/zero/1.0/', sourceUrl: 'https://commons.wikimedia.org/wiki/File:a.jpg' }] }); return r.items.length === 0 && r.refused.length === 1; });
  ok(h, 'validate: a protocol-relative (hotlinked) src is refused');
  await p.close();
}

await browser.close();
server.close();
console.log('\n' + fails + ' failure(s)');
process.exit(fails ? 1 : 0);
