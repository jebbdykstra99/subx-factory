import fs from 'fs';
import os from 'os';
import path from 'path';
import vm from 'vm';
import assert from 'assert';
import crypto from 'crypto';
import { execFileSync, spawnSync } from 'child_process';
import { fileURLToPath } from 'url';

/*
 * whoMark: disclosure mark component (assets/whomark/). Run: node test/whomark.test.js
 *  1. whoMark / whoMarkPlain / whoMarkBadges for human, ai, hybrid (aria-label, <title>, sprite <use>, label, escaping)
 *  2. swap: build the other placeholder family into a temp dir, output changes, whomark.js logic is untouched
 *  3. ./swap-marks.sh --dry-run writes nothing; an incomplete family is refused
 *  4. factory.js is untouched (0 B): whomark.js upgrades the factory's AI steward text pill; no script = text pill.
 *     Plus a real-Chrome check when puppeteer-core + Chrome are available (CHROME=/usr/bin/google-chrome default).
 */
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const A = path.join(root, 'assets', 'whomark');
const BEGIN = '/* @whomark-config */', END = '/* @whomark-config-end */';
let pass = 0;
function ok(name, fn) { fn(); pass++; console.log('ok', name); }
function load(file) {
  const ctx = { globalThis: null };
  ctx.globalThis = ctx;
  vm.runInNewContext(fs.readFileSync(file, 'utf8'), ctx, { filename: file });
  return ctx;
}
function hashDir(d) {
  const h = crypto.createHash('sha256');
  for (const f of fs.readdirSync(d).sort()) h.update(f + '\0').update(fs.readFileSync(path.join(d, f)));
  return h.digest('hex');
}
const hasCairo = spawnSync('python3', ['-c', 'import cairosvg']).status === 0;
const W = load(path.join(A, 'whomark.js'));
const cfg = W.whoMarkConfig();
// The swap fixture is whichever placeholder family is NOT active (so the test still means something after a swap).
const OTHER = cfg.family === 'placeholder-square' ? 'marks/placeholder-ring' : 'marks/placeholder-square';
const OTHER_NAME = OTHER.split('/')[1];

ok('config is embedded and complete', () => {
  assert.equal(cfg.sprite, '/assets/whomark/sprite.svg');
  assert.match(cfg.version, /^[0-9a-f]{10}$/);
  for (const t of ['human', 'ai', 'hybrid']) for (const f of ['symbolId', 'symbolIdSmall', 'textLabel', 'ariaLabel', 'title', 'plainText', 'ogBadge', 'cornerBadge']) assert.ok(cfg.tiers[t][f], t + '.' + f);
  assert.ok(cfg.minSizePx.hybrid >= 16);
});

const LABEL = { human: 'Human-made', ai: 'AI steward · SubX', hybrid: 'Human + AI' };
ok('whoMark: 3 tiers render accessible sprite marks', () => {
  for (const t of ['human', 'ai', 'hybrid']) {
    const h = W.whoMark(t, t === 'hybrid' ? ['Jebb'] : undefined, { size: 24 });
    assert.match(h, /<svg class="wm-svg" role="img" aria-label="[^"]+"/, t);
    assert.match(h, /<title>[^<]+<\/title>/, t);
    assert.ok(h.includes('<use href="/assets/whomark/sprite.svg?v=' + cfg.version + '#' + cfg.tiers[t].symbolId + '"></use>'), t);
    assert.ok(h.includes('<span class="wm-label" aria-hidden="true">' + LABEL[t] + '</span>'), t);
    assert.ok(!/<path|<circle|<rect|<g\b/.test(h), t + ': rooms reference symbol ids only, never inline art');
  }
  assert.ok(W.whoMark('ai').includes('aria-label="AI steward · SubX"'));
  assert.ok(W.whoMark('ai').includes('title="Operated by SubX using AI tools. Not a real person."'));
  assert.ok(W.whoMark('hybrid', ['Ana', 'Bo']).includes('aria-label="Human + AI: Ana, Bo"'));
  assert.ok(W.whoMark('hybrid', 'Ana').includes('<title>Human + AI: Ana</title>'));
  assert.ok(W.whoMark('hybrid').includes('aria-label="Human + AI"'), 'no names -> no dangling colon');
  assert.equal(W.whoMark('robot'), '');
  assert.equal(W.whoMark('__proto__'), '');
});

ok('whoMark: sizes (small variant, hybrid >= 16px, 14px always labelled)', () => {
  assert.ok(W.whoMark('ai', null, { size: 16 }).includes('#' + cfg.tiers.ai.symbolIdSmall + '"'));
  assert.ok(W.whoMark('ai', null, { size: 32 }).includes('#' + cfg.tiers.ai.symbolId + '"'));
  assert.ok(W.whoMark('hybrid', null, { size: 12 }).includes('width="16" height="16"'));
  const h14 = W.whoMark('human', null, { size: 14, label: false });
  assert.ok(h14.includes('width="14"') && h14.includes('wm-label'), '14px keeps the visible label');
  assert.ok(!W.whoMark('human', null, { size: 24, label: false }).includes('wm-label'));
});

ok('whoMark: names and options are escaped (no HTML injection)', () => {
  const evil = ['<img src=x onerror=alert(1)>', '"><script>alert(2)</script>', "O'Neil & co"];
  const h = W.whoMark('hybrid', evil, { cls: '" onmouseover="x' });
  const tags = new Set([...h.matchAll(/<\/?([a-zA-Z]+)/g)].map((m) => m[1]));
  assert.deepEqual([...tags].sort(), ['span', 'svg', 'title', 'use'], 'no injected elements');
  const attrs = new Set([...h.matchAll(/\s([a-zA-Z-]+)="[^"]*"/g)].map((m) => m[1]));
  for (const a of attrs) assert.ok(['class', 'title', 'data-wm-family', 'role', 'aria-label', 'width', 'height', 'viewBox', 'focusable', 'href', 'aria-hidden'].includes(a), 'injected attribute ' + a);
  assert.ok(h.includes('&lt;img src=x onerror=alert(1)&gt;') && h.includes('&quot;&gt;&lt;script&gt;') && h.includes('O&#39;Neil &amp; co'));
  assert.ok(W.whoMark('hybrid', 'a\nb\u0000c').includes('Human + AI: a b c'));
});

ok('whoMarkPlain + whoMarkBadges', () => {
  assert.equal(W.whoMarkPlain('human'), 'Human-made');
  assert.equal(W.whoMarkPlain('ai'), 'AI steward · SubX');
  assert.equal(W.whoMarkPlain('hybrid'), 'Human + AI');
  assert.equal(W.whoMarkPlain('hybrid', ['Ana', ' Bo\n']), 'Human + AI: Ana, Bo');
  assert.equal(W.whoMarkPlain('nope'), '');
  for (const t of ['human', 'ai', 'hybrid']) {
    const b = W.whoMarkBadges(t);
    for (const p of [b.og, b.corner]) {
      assert.match(p, /^\/assets\/whomark\/[a-z0-9-]+\.png$/);
      assert.ok(fs.existsSync(path.join(root, p)), p + ' exists');
    }
  }
  assert.equal(W.whoMarkBadges('nope'), null);
});

ok('assets/whomark is in sync with its sprite + config (build/whomark.py --check)', () => {
  execFileSync('python3', ['build/whomark.py', '--check'].concat(hasCairo ? [] : ['--no-png']), { cwd: root, stdio: 'pipe' });
});

ok('swap: a second family changes the output with no other edits', () => {
  const before = hashDir(A);
  const out = fs.mkdtempSync(path.join(os.tmpdir(), 'wm-swap-'));
  execFileSync('python3', ['build/whomark.py', '--src', OTHER, '--out', out].concat(hasCairo ? [] : ['--no-png']), { cwd: root, stdio: 'pipe' });
  const B = load(path.join(out, 'whomark.js'));
  const cb = B.whoMarkConfig();
  assert.equal(cb.family, OTHER_NAME);
  assert.notEqual(cb.version, cfg.version);
  for (const t of ['human', 'ai', 'hybrid']) {
    const a = W.whoMark(t, ['Ana']), b = B.whoMark(t, ['Ana']);
    assert.notEqual(a, b, t);
    assert.ok(b.includes('#' + cb.tiers[t].symbolIdSmall + '"') && b.includes('?v=' + cb.version), t);
    assert.equal(W.whoMarkPlain(t, ['Ana']), B.whoMarkPlain(t, ['Ana']), 'disclosure copy is policy, unchanged by a swap');
  }
  const strip = (s) => s.slice(0, s.indexOf(BEGIN)) + s.slice(s.indexOf(END));
  assert.equal(strip(fs.readFileSync(path.join(out, 'whomark.js'), 'utf8')), strip(fs.readFileSync(path.join(A, 'whomark.js'), 'utf8')), 'only the config block differs');
  const spriteB = fs.readFileSync(path.join(out, 'sprite.svg'), 'utf8');
  for (const t of ['human', 'ai', 'hybrid']) assert.ok(spriteB.includes('id="' + cb.tiers[t].symbolId + '"'));
  assert.equal(hashDir(A), before, 'building elsewhere leaves assets/whomark alone');
  fs.rmSync(out, { recursive: true, force: true });
});

ok('swap-marks.sh --dry-run validates, prints the diff, writes nothing', () => {
  const before = hashDir(A);
  const git0 = execFileSync('git', ['status', '--porcelain'], { cwd: root }).toString();
  const r = spawnSync('./swap-marks.sh', [OTHER, '--dry-run'], { cwd: root });
  assert.equal(r.status, 0, r.stderr.toString());
  const o = r.stdout.toString();
  assert.match(o, /valid family/);
  assert.match(o, /changed\s+sprite\.svg/);
  assert.match(o, /file\(s\) would change/);
  assert.equal(hashDir(A), before);
  assert.equal(execFileSync('git', ['status', '--porcelain'], { cwd: root }).toString(), git0);
});

ok('an incomplete family is refused', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'wm-bad-'));
  let s = fs.readFileSync(path.join(root, 'marks/placeholder-square/sprite.svg'), 'utf8');
  s = s.replace(/<symbol id="wmsq-hybrid-sm"[\s\S]*?<\/symbol>/, '').replace('<symbol id="wmsq-ai" viewBox="0 0 24 24">\n    <title>AI steward</title>', '<symbol id="wmsq-ai" viewBox="0 0 32 32">');
  fs.writeFileSync(path.join(d, 'sprite.svg'), s);
  const c = JSON.parse(fs.readFileSync(path.join(root, 'marks/placeholder-square/config.json'), 'utf8'));
  delete c.tiers.human.plainText; c.minSizePx.hybrid = 12; c.tiers.ai.textLabel = 'Bot';
  fs.writeFileSync(path.join(d, 'config.json'), JSON.stringify(c));
  const r = spawnSync('python3', ['build/whomark.py', '--validate', d], { cwd: root });
  const e = r.stderr.toString();
  assert.equal(r.status, 1);
  for (const m of ['wmsq-hybrid-sm', 'viewBox', 'no <title>', 'human.plainText', 'hybrid 12 < 16', 'policy label']) assert.ok(e.includes(m), m + ' in ' + e);
  const r2 = spawnSync('./swap-marks.sh', [d, '--dry-run'], { cwd: root });
  assert.notEqual(r2.status, 0);
  fs.rmSync(d, { recursive: true, force: true });
});

const SRC = fs.readFileSync(path.join(root, 'factory', 'factory.js'), 'utf8');
const TEXT = '<span class="post-steward-pill" title="Operated by SubX using AI tools. Not a real person.">AI steward · SubX</span>';
ok('factory.js untouched; the AI steward pill whomark.js upgrades is still the factory text pill', () => {
  assert.ok(!/whoMark/.test(SRC), 'no whoMark code in factory.js');
  const i = SRC.indexOf('  function stewardPillHtml(post) {');
  const fn = SRC.slice(i, SRC.indexOf('\n  }\n', i) + 4);
  const out = vm.runInNewContext(fn + '\nstewardPillHtml(post);', { isSessionSeedPost: () => false, post: { steward: true } });
  assert.equal(out, TEXT, 'factory AI pill changed: update PILL in assets/whomark/whomark.js');
});
ok('whoMarkUpgrade swaps only the AI pill (fake DOM)', () => {
  const el = (cls, title) => ({ cls, title, parentNode: {}, outerHTML: null,
    matches(sel) { return sel.startsWith('.post-steward-pill[title^="Operated by SubX') && this.cls === 'post-steward-pill' && /^Operated by SubX using AI tools/.test(this.title || ''); } });
  const ai = el('post-steward-pill', 'Operated by SubX using AI tools. Not a real person.'), sample = el('post-steward-pill', ''), stew = el('post-steward-pill', '');
  const all = [ai, sample, stew];
  const rootEl = { matches: () => false, querySelectorAll: (sel) => all.filter((e) => e.matches(sel)) };
  assert.equal(W.whoMarkUpgrade(rootEl), 1);
  assert.equal(ai.outerHTML, W.whoMark('ai', null, { cls: 'post-steward-pill-wm' }));
  assert.equal(sample.outerHTML, null); assert.equal(stew.outerHTML, null);
  assert.equal(W.whoMarkUpgrade(null), 0);
});


ok('whoMarkUpgrade upgrades declarative [data-whomark] badges (human, ai, hybrid) and ignores unknown tiers', () => {
  const decl = (tier, names, size, label, cls) => ({
    parentNode: {}, outerHTML: null,
    matches(sel) { return sel === '[data-whomark]'; },
    getAttribute(k) {
      return ({ 'data-whomark': tier, 'data-whomark-names': names, 'data-whomark-size': size, 'data-whomark-label': label, 'data-whomark-class': cls })[k] ?? null;
    }
  });
  const h1 = decl('hybrid', 'Jebb Dykstra, Juno, Vesta and Iris', '16', null, 'story-byline-wm');
  const h2 = decl('human', null, '24', 'false', null);
  const bad = decl('unknown-tier', null, null, null, null);
  const rootEl = { matches: () => false, querySelectorAll: (sel) => sel === '[data-whomark]' ? [h1, h2, bad] : [] };
  assert.equal(W.whoMarkUpgrade(rootEl), 2);
  assert.equal(h1.outerHTML, W.whoMark('hybrid', 'Jebb Dykstra, Juno, Vesta and Iris', { size: '16', label: true, cls: 'story-byline-wm' }));
  assert.equal(h2.outerHTML, W.whoMark('human', null, { size: '24', label: false, cls: null }));
  assert.equal(bad.outerHTML, null);
});

ok('Mark R5 (final-v2) candidate families validate and dry-run cleanly', () => {
  for (const fam of ['marks/mark-r5', 'marks/mark-r5-arms-d', 'marks/mark-r5-arms-w']) {
    const r = spawnSync('python3', ['build/whomark.py', '--validate', fam], { cwd: root });
    assert.equal(r.status, 0, fam + ': ' + r.stderr.toString());
    const r2 = spawnSync('./swap-marks.sh', [fam, '--dry-run'], { cwd: root });
    assert.equal(r2.status, 0, fam + ' dry-run: ' + r2.stderr.toString());
  }
});

let puppeteer = null;
const CHROME = process.env.CHROME || '/usr/bin/google-chrome';
try { if (fs.existsSync(CHROME)) puppeteer = (await import('puppeteer-core')).default; } catch { puppeteer = null; }
if (puppeteer) {
  const b = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] });
  try {
    const page = await b.newPage();
    const pills = TEXT + '<span class="post-steward-pill">Sample</span><span class="post-steward-pill">Steward</span>';
    const js = fs.readFileSync(path.join(A, 'whomark.js'), 'utf8');
    await page.setContent('<!doctype html><html><head><script>' + js + '</script></head><body><div id="feed">' + pills + '</div></body></html>');
    await page.evaluate((h) => { const d = document.createElement('article'); d.innerHTML = h; document.getElementById('feed').appendChild(d); }, pills);
    await new Promise((r) => setTimeout(r, 50));
    const r = await page.evaluate(() => ({ wm: document.querySelectorAll('.wm.wm-ai.post-steward-pill-wm svg[role=img][aria-label]').length,
      text: document.querySelectorAll('.post-steward-pill[title]').length, other: document.querySelectorAll('.post-steward-pill').length }));
    assert.deepEqual(r, { wm: 2, text: 0, other: 4 }, 'Chrome: initial + later-rendered AI pills upgraded, Sample/Steward untouched');
    await page.setContent('<!doctype html><body>' + pills + '</body>');
    assert.equal(await page.evaluate(() => document.querySelectorAll('.post-steward-pill[title]').length), 1, 'no whomark.js -> text pill');
    pass++; console.log('ok Chrome: AI pill upgraded on render (incl. later posts); no script = text pill');
  } finally { await b.close(); }
} else console.log('skip Chrome check (no puppeteer-core/Chrome)');

console.log('whomark: ' + pass + ' passed');
