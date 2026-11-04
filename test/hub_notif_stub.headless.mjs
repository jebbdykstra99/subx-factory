// Headless Chrome check of Juno Key 2 C1 on the built hub (hub/site): the shell v1.2.6 openNotif() adds .active to the
// hidden #notif-overlay stub on #notifications. Loading the legacy /#notifications link, and switching the hash to
// #notifications, must leave the stub not displayed, keep focus out of any aria-hidden element, and show the hub
// Notifications view. Offline: only 127.0.0.1 is served; every other request is aborted.
// Usage: node test/hub_notif_stub.headless.mjs   (CHROME=/usr/bin/google-chrome default)
import http from 'node:http'; import fs from 'node:fs'; import path from 'node:path';
import { fileURLToPath } from 'node:url';
import puppeteer from 'puppeteer-core';
const SITE = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'hub', 'site');
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.css': 'text/css', '.svg': 'image/svg+xml', '.txt': 'text/plain' };
const srv = http.createServer((req, res) => {
  let p = decodeURIComponent(req.url.split('?')[0]); if (p.endsWith('/')) p += 'index.html';
  const f = path.join(SITE, path.normalize(p));
  if (!f.startsWith(SITE) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { 'content-type': TYPES[path.extname(f)] || 'application/octet-stream' }); res.end(fs.readFileSync(f));
});
await new Promise(r => srv.listen(0, '127.0.0.1', r));
const base = 'http://127.0.0.1:' + srv.address().port;
let fails = 0;
const ok = (c, m) => { console.log((c ? 'ok   ' : 'FAIL ') + m); if (!c) fails++; };
const wait = ms => new Promise(r => setTimeout(r, ms));
const browser = await puppeteer.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome', headless: 'new', args: ['--no-sandbox'] });
try {
  const pg = await browser.newPage(); await pg.setViewport({ width: 1280, height: 900 });
  await pg.setRequestInterception(true);
  pg.on('request', r => (r.url().startsWith(base) ? r.continue() : r.abort()));
  const state = () => pg.evaluate(() => {
    const o = document.getElementById('notif-overlay'), a = document.activeElement;
    const page = document.getElementById('page-hub-notifications');
    return { hash: location.hash, overlay: o ? getComputedStyle(o).display : 'missing', active: !!(o && o.classList.contains('active')),
      focusHidden: !!(a && a.closest && a.closest('[aria-hidden="true"]')), focusId: a ? a.id || a.tagName : '',
      view: !!(page && page.classList.contains('active') && getComputedStyle(page).display !== 'none' && page.getBoundingClientRect().height > 0) };
  });
  const check = (s, how) => {
    ok(s.overlay === 'none', how + ': the notif-overlay stub is not displayed (display ' + s.overlay + ', .active ' + s.active + ')');
    ok(!s.focusHidden, how + ': focus is not in an aria-hidden element (focus ' + s.focusId + ')');
    ok(s.hash === '#hub-notifications' && s.view, how + ': the hub Notifications view shows (hash ' + s.hash + ')');
  };
  await pg.goto(base + '/#notifications', { waitUntil: 'networkidle0' }); await wait(800);
  check(await state(), 'load /#notifications');
  await pg.evaluate(() => { location.hash = '#hub-following'; }); await wait(400);
  await pg.evaluate(() => { location.hash = '#notifications'; }); await wait(800);
  check(await state(), 'hash change to #notifications');
  await pg.evaluate(() => { location.hash = '#home'; }); await wait(400);
  await pg.evaluate(() => { location.hash = '#notifications'; }); await wait(800);
  check(await state(), 'hash change #home to #notifications');
} finally { await browser.close(); srv.close(); }
console.log('\n' + fails + ' failure(s)');
process.exit(fails ? 1 : 0);
