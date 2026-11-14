// Featured articles pilot (Nov 14 2026): factory-featured.js pure helpers + factory.js hook guards.
import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const CORE_JS = fs.readFileSync(path.join(ROOT, 'factory', 'factory.js'), 'utf8');
const ADDON_JS = fs.readFileSync(path.join(ROOT, 'factory', 'factory-featured.js'), 'utf8');
// The add-on is a classic browser script; run it the way a page would, plus a CommonJS-style module slot.
const sandbox = { module: { exports: {} }, URLSearchParams, Date };
vm.runInNewContext(ADDON_JS, sandbox);
const F = sandbox.module.exports;

const NOW = Date.UTC(2026, 10, 14, 15, 0, 0);
const DAY = 86400000;
const LONG = 'Snake of the Day: the Black Mamba\n\nWho: one of Africa\'s best known snakes.\n\nWhere: savanna.';
const cfg = F.cfgOf({ featured: { featuredDays: 3, handles: ['namecheck', '@IdDesk'], articleMinChars: 600, maxPinned: 2 } });

function post(id, o) {
  return Object.assign({ id: id, text: 'short note', handle: 'namecheck', steward: true, ms: NOW - DAY, parentId: null }, o || {});
}

test('cfgOf reads site.json featured block with safe defaults', () => {
  assert.strictEqual(cfg.days, 3);
  assert.deepStrictEqual([...cfg.handles], ['namecheck', 'iddesk']);
  assert.strictEqual(cfg.maxPinned, 2);
  const d = F.cfgOf({});
  assert.strictEqual(d.days, 3);
  assert.strictEqual(d.minChars, 600);
  assert.strictEqual(d.label, 'Our articles');
});

test('paragraph split and Show more eligibility', () => {
  assert.strictEqual(F.firstParagraph(LONG), 'Snake of the Day: the Black Mamba');
  assert.strictEqual(F.paragraphs(LONG).length, 3);
  assert.strictEqual(F.isLong(LONG), true);
  assert.strictEqual(F.isLong('one paragraph only\nwith a line break'), false);
  assert.strictEqual(F.isLong('trailing gap\n\n   \n'), false);
  assert.strictEqual(F.isLong('a\r\n\r\nb'), true);
});

test('ours = steward flag AND listed handle; users with a steward handle do not count', () => {
  assert.strictEqual(F.isOurs(post('a'), cfg), true);
  assert.strictEqual(F.isOurs(post('b', { handle: 'IDDESK' }), cfg), true);
  assert.strictEqual(F.isOurs(post('c', { handle: 'randomfan' }), cfg), false);
  assert.strictEqual(F.isOurs(post('d', { steward: false }), cfg), false);
  assert.strictEqual(F.isOurs(post('e', { parentId: 'a' }), cfg), false);
});

test('articles are long or multi-paragraph steward posts, newest first', () => {
  const posts = [
    post('short'),
    post('old', { text: LONG, ms: NOW - 10 * DAY }),
    post('new', { text: LONG, ms: NOW - 1000 }),
    post('big', { text: 'x'.repeat(700), ms: NOW - 2 * DAY })
  ];
  assert.deepStrictEqual([...F.ourArticles(posts, cfg).map((p) => p.id)], ['new', 'big', 'old']);
});

test('featured window expires automatically and is capped', () => {
  const posts = [
    post('a1', { text: LONG, ms: NOW - 1000 }),
    post('a2', { text: LONG, ms: NOW - 2 * DAY }),
    post('a3', { text: LONG, ms: NOW - 2.5 * DAY }),
    post('stale', { text: LONG, ms: NOW - 4 * DAY })
  ];
  assert.deepStrictEqual([...F.featuredIds(posts, cfg, NOW)], ['a1', 'a2']);
  assert.deepStrictEqual([...F.featuredIds(posts, cfg, NOW + 5 * DAY)], []);
  const off = F.cfgOf({ featured: { featuredDays: 0, handles: ['namecheck'] } });
  assert.deepStrictEqual([...F.featuredIds(posts, off, NOW)], []);
});

test('images: https only', () => {
  assert.ok(F.safeImageUrl('https://upload.wikimedia.org/a.jpg'));
  assert.strictEqual(F.safeImageUrl('http://example.com/a.jpg'), '');
  assert.strictEqual(F.safeImageUrl('javascript:alert(1)'), '');
  assert.strictEqual(F.safeImageUrl('data:image/png;base64,AAA'), '');
  assert.strictEqual(F.safeImageUrl('https://x.test/a.jpg" onerror="x'), '');
  assert.strictEqual(F.safeImageUrl(null), '');
});

test('titles and permalinks', () => {
  assert.strictEqual(F.titleOf(LONG), 'Snake of the Day: the Black Mamba');
  assert.ok(F.titleOf('word '.repeat(60), 40).length <= 40);
  assert.strictEqual(F.permalink('LWRc xj&"'), '/?p=LWRc%20xj%26%22');
});

test('add-on never writes user text with innerHTML and has no en or em dashes', () => {
  assert.ok(!/innerHTML/.test(ADDON_JS));
  assert.ok(!/[\u2013\u2014]/.test(ADDON_JS));
  assert.ok(!/grok/i.test(ADDON_JS));
});

test('factory.js stays under the byte cap and carries the lazy hooks', () => {
  const bytes = Buffer.byteLength(CORE_JS, 'utf8');
  assert.ok(bytes <= 255000, 'factory.js is ' + bytes + ' B');
  assert.ok(CORE_JS.includes("if(site.featured)addon('factory-featured').onload="));
  assert.ok(CORE_JS.includes('PLUGIN.feat&&PLUGIN.feat(el);'));
  assert.ok(CORE_JS.includes('PLUGIN.feat&&PLUGIN.feat();'));
  assert.ok(CORE_JS.includes("if (/^https:/i.test(post.imageUrl))"));
  assert.ok(CORE_JS.includes("var s = addon('factory-signin');"));
});

test('install returns a feat hook', () => {
  const api = F.install({ site: { featured: {} }, topLevelPosts: () => [] });
  assert.strictEqual(typeof api.feat, 'function');
});
