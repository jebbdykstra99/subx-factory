// Headless smoke load of stamped room folders. Read-only: no sign-in, no clicks that write; the visit pixel and
// other Cloud Functions are blocked. Usage: node tools/smoke.mjs <dir-with-room-folders> room1 room2 ...
// Needs puppeteer-core and a local Chrome (CHROME=/usr/bin/google-chrome by default).
import http from 'node:http'; import fs from 'node:fs'; import path from 'node:path';
import puppeteer from 'puppeteer-core';
const [root, ...rooms] = process.argv.slice(2);
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png' };
function serve(dir) {
  return new Promise(res => {
    const s = http.createServer((q, r) => {
      let p = decodeURIComponent(q.url.split('?')[0]); if (p.endsWith('/')) p += 'index.html';
      let f = path.join(dir, p); if (!fs.existsSync(f) && fs.existsSync(f + '.html')) f += '.html';
      if (!fs.existsSync(f)) { r.writeHead(404); return r.end('nf'); }
      r.writeHead(200, { 'content-type': TYPES[path.extname(f)] || 'application/octet-stream' }); fs.createReadStream(f).pipe(r);
    }).listen(0, '127.0.0.1', () => res(s));
  });
}
const browser = await puppeteer.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome', headless: 'new', args: ['--no-sandbox'] });
const results = []; let bad = 0;
for (const room of rooms) {
  const srv = await serve(path.join(root, room)); const url = 'http://127.0.0.1:' + srv.address().port + '/';
  const page = await browser.newPage(); const errs = [], blocked = [];
  await page.setRequestInterception(true);
  page.on('request', q => { const u = q.url(); if (/cloudfunctions\.net|googletagmanager|google-analytics/.test(u)) { blocked.push(u.split('?')[0]); q.abort(); } else q.continue(); });
  page.on('pageerror', e => errs.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error' && !/ERR_FAILED|net::|403|Failed to load resource|app-check|AppCheck|referer|Referer|report-only/i.test(m.text())) errs.push('console: ' + m.text().slice(0, 200)); });
  await page.goto(url, { waitUntil: 'networkidle2', timeout: 45000 }).catch(e => errs.push('goto: ' + e.message));
  await new Promise(r => setTimeout(r, 6000));
  const st = await page.evaluate(() => {
    const vis = id => { const e = document.getElementById(id); return !!(e && !e.hidden && e.offsetParent !== null); };
    return {
      title: document.title,
      brand: (document.querySelector('.brand-title') || {}).textContent || '',
      feedItems: document.querySelectorAll('#thoughts-feed > *').length,
      railCards: document.querySelectorAll('#news-feed > *').length,
      railText: ((document.getElementById('news-feed') || {}).innerText || '').slice(0, 700).replace(/\s+/g, ' '),
      watchlistVisible: vis('watchlist'),
      followBtns: document.querySelectorAll('.topic-follow-btn, [data-topic-follow]').length,
      f1Cards: document.body.innerHTML.includes('Grand Prix') || document.body.innerHTML.includes('Jolpica'),
      noindex: !!document.querySelector('meta[name=robots][content*=noindex]'),
      banner: /preview/i.test((document.querySelector('.preview-banner, #preview-banner, [class*=preview]') || {}).textContent || ''),
      lsKeys: Object.keys(localStorage),
    };
  });
  const ok = !errs.length && st.noindex;
  if (!ok) bad++;
  results.push({ room, ok, ...st, errors: errs, blocked: [...new Set(blocked)] });
  await page.close(); srv.close();
}
await browser.close();
console.log(JSON.stringify(results, null, 2));
process.exit(bad ? 1 : 0);
