// Headless check of the accounts gate on a real room page. Never creates an account: every Identity Toolkit
// and Firestore write request is aborted in the browser; the test only records whether one was attempted.
// Usage: node test/accounts-gate.headless.mjs <room-dir-with-index.html-and-site.json>   (CHROME=/usr/bin/google-chrome)
import http from 'node:http'; import fs from 'node:fs'; import path from 'node:path';
import puppeteer from 'puppeteer-core';
const dir = process.argv[2]; const core = fs.readFileSync(new URL('../factory/factory.js', import.meta.url));
const base = JSON.parse(fs.readFileSync(path.join(dir, 'site.json'), 'utf8'));
const cases = [
  ['preview:true', Object.assign({}, base, { preview: true, accountsOpen: true }), false],
  ['accountsOpen missing', (() => { const s = Object.assign({}, base); delete s.accountsOpen; delete s.preview; return s; })(), false],
  ['accountsOpen:true, preview:false', Object.assign({}, base, { accountsOpen: true, preview: false }), true]
];
const browser = await puppeteer.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome', headless: 'new', args: ['--no-sandbox'] });
let bad = 0;
for (const [name, site, wantOpen] of cases) {
  const srv = await new Promise(res => { const s = http.createServer((q, r) => {
    const p = q.url.split('?')[0];
    if (p === '/' || p === '/index.html') { r.writeHead(200, { 'content-type': 'text/html' }); return r.end(fs.readFileSync(path.join(dir, 'index.html'))); }
    if (p === '/factory.js') { r.writeHead(200, { 'content-type': 'text/javascript' }); return r.end(core); }
    if (p === '/site.json') { r.writeHead(200, { 'content-type': 'application/json' }); return r.end(JSON.stringify(site)); }
    r.writeHead(404); r.end('nf'); }).listen(0, '127.0.0.1', () => res(s)); });
  const page = await browser.newPage(); const signup = [];
  await page.setRequestInterception(true);
  page.on('request', q => { const u = q.url();
    if (/identitytoolkit|securetoken/.test(u) || (/firestore\.googleapis/.test(u) && q.method() !== 'GET')) { if (/signUp|accounts:/.test(u)) signup.push(u.split('?')[0]); return q.abort(); }
    if (/cloudfunctions\.net|googletagmanager|google-analytics/.test(u)) return q.abort();
    q.continue(); });
  await page.goto('http://127.0.0.1:' + srv.address().port + '/', { waitUntil: 'networkidle2', timeout: 45000 }).catch(() => {});
  await new Promise(r => setTimeout(r, 5000));
  const st = await page.evaluate(async () => {
    const shown = sel => { const e = document.querySelector(sel); return !!(e && getComputedStyle(e).display !== 'none' && !e.hidden); };
    const out = { closedClass: document.documentElement.classList.contains('acc-closed'),
      registerTab: shown('[data-tab="register"]'), google: shown('#cv-google-login'), googleAge: shown('label[for="cv-google-age"]'),
      note: shown('#cv-accounts-closed') ? document.getElementById('cv-accounts-closed').textContent : null };
    document.getElementById('cv-reg-email').value = 'gate-test@example.invalid';
    document.getElementById('cv-reg-pw').value = 'not-a-real-pw-123';
    document.getElementById('cv-reg-age').checked = true;
    document.getElementById('cv-reg-btn').click();
    await new Promise(r => setTimeout(r, 2500));
    out.regErr = document.getElementById('cv-reg-err').textContent;
    return out; });
  st.signupAttempted = signup.length > 0;
  const ok = wantOpen
    ? (!st.closedClass && st.registerTab && st.google && !st.note && st.signupAttempted)
    : (st.closedClass && !st.registerTab && !st.google && !st.googleAge && !!st.note && !st.signupAttempted && /not open/.test(st.regErr));
  if (!ok) bad++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + ' -> ' + JSON.stringify(st));
  await page.close(); srv.close();
}
await browser.close();
process.exit(bad ? 1 : 0);
