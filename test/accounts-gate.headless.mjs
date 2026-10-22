// Headless check of the accounts gate on real room pages. Never creates an account: every sign-in request
// (Identity Toolkit, securetoken, accounts.google.com, the Firebase /__/auth handler) and every Firestore write
// is aborted in the browser; the test only records whether a signUp was attempted.
// Usage: node test/accounts-gate.headless.mjs [room-dir ...]   (CHROME=/usr/bin/google-chrome, FACTORY=alt factory.js)
//   Always runs test/fixtures/gpchat (live gpchat.com markup with its static #cv-accounts-closed note), then
//   each room dir given (index.html + site.json, e.g. a fresh copy of boyfriendchat.com).
import http from 'node:http'; import fs from 'node:fs'; import path from 'node:path';
import puppeteer from 'puppeteer-core';
const core = fs.readFileSync(process.env.FACTORY || new URL('../factory/factory.js', import.meta.url));
const dirs = [new URL('./fixtures/gpchat', import.meta.url).pathname, ...process.argv.slice(2)];
const SIGNIN = /identitytoolkit|securetoken|accounts\.google\.com|\/__\/auth\//;
const variant = (base, patch, drop) => { const s = Object.assign({}, base, patch); (drop || []).forEach(k => delete s[k]); return s; };
const browser = await puppeteer.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome', headless: 'new', args: ['--no-sandbox'] });
let bad = 0;
for (const dir of dirs) {
  const room = path.basename(dir); const base = JSON.parse(fs.readFileSync(path.join(dir, 'site.json'), 'utf8'));
  const cases = [
    ['preview:true', variant(base, { preview: true, accountsOpen: true }), 'closed'],
    ['accountsOpen missing', variant(base, {}, ['accountsOpen', 'preview']), 'closed'],
    ['closed + subx.steward=1', variant(base, { preview: true }), 'steward'],
    ['accountsOpen:true, preview:false', variant(base, { accountsOpen: true, preview: false }), 'open']
  ];
  if (room === 'gpchat') cases.push(['live site.json as served (accountsOpen:true)', base, 'open']);
  for (const [name, site, want] of cases) {
    const srv = await new Promise(res => { const s = http.createServer((q, r) => {
      const p = q.url.split('?')[0];
      if (p === '/factory.js') { r.writeHead(200, { 'content-type': 'text/javascript' }); return r.end(core); }
      if (p === '/site.json') { r.writeHead(200, { 'content-type': 'application/json' }); return r.end(JSON.stringify(site)); }
      const f = path.join(dir, p === '/' ? 'index.html' : path.normalize(p).replace(/^[/\\]+/, ''));
      if (f.startsWith(dir) && fs.existsSync(f) && fs.statSync(f).isFile()) {
        r.writeHead(200, { 'content-type': f.endsWith('.html') ? 'text/html' : f.endsWith('.css') ? 'text/css' : 'application/octet-stream' });
        return r.end(fs.readFileSync(f)); }
      r.writeHead(404); r.end('nf'); }).listen(0, '127.0.0.1', () => res(s)); });
    const page = await browser.newPage(); const signup = []; const signin = [];
    if (want === 'steward') await page.evaluateOnNewDocument(() => { try { localStorage.setItem('subx.steward', '1'); } catch (e) {} });
    await page.setRequestInterception(true);
    page.on('request', q => { const u = q.url();
      if (SIGNIN.test(u) || (/firestore\.googleapis/.test(u) && q.method() !== 'GET')) {
        signin.push(u.split('?')[0].replace(/^https?:\/\/([^/]+)\/(?:v1\/)?([^/]*).*$/, '$1/$2')); if (/signUp/.test(u)) signup.push(u.split('?')[0]); return q.abort(); }
      if (/cloudfunctions\.net|googletagmanager|google-analytics/.test(u)) return q.abort();
      q.continue(); });
    await page.goto('http://127.0.0.1:' + srv.address().port + '/', { waitUntil: 'networkidle2', timeout: 45000 }).catch(() => {});
    await new Promise(r => setTimeout(r, 5000));
    const st = await page.evaluate(async () => {
      const shown = sel => { const e = document.querySelector(sel); return !!(e && getComputedStyle(e).display !== 'none' && !e.hidden); };
      const out = { closedClass: document.documentElement.classList.contains('acc-closed'),
        gateCss: !!document.getElementById('acc-gate-css'), notes: document.querySelectorAll('#cv-accounts-closed').length,
        registerTab: shown('[data-tab="register"]'), google: shown('#cv-google-login'), googleAge: shown('label[for="cv-google-age"]'),
        note: shown('#cv-accounts-closed') ? document.getElementById('cv-accounts-closed').textContent : null };
      document.getElementById('cv-reg-email').value = 'gate-test@example.invalid';
      document.getElementById('cv-reg-pw').value = 'not-a-real-pw-123';
      document.getElementById('cv-reg-age').checked = true;
      document.getElementById('cv-reg-btn').click();
      await new Promise(r => setTimeout(r, 2500));
      out.regErr = document.getElementById('cv-reg-err').textContent;
      return out; });
    st.signupAttempted = signup.length > 0; st.blocked = [...new Set(signin)];
    const closedUi = st.closedClass && st.gateCss && st.notes === 1 && !st.registerTab && !!st.note && /not open yet/.test(st.note) &&
      !st.signupAttempted && /not open/.test(st.regErr);
    const ok = want === 'open' ? (!st.closedClass && !st.gateCss && st.registerTab && st.google && !st.note && st.signupAttempted)
      : want === 'steward' ? (closedUi && st.google)
      : (closedUi && !st.google && !st.googleAge);
    if (!ok) bad++;
    console.log((ok ? 'PASS ' : 'FAIL ') + room + ' ' + name + ' -> ' + JSON.stringify(st));
    await page.close(); srv.close();
  }
}
await browser.close();
process.exit(bad ? 1 : 0);
