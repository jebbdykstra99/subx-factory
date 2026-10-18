// Shared SubX room smoke test (synced from subx-factory templates/room/tests/smoke). Read-only:
// no sign-in, no writes. The visit pixel, Cloud Functions and analytics are blocked so CI never
// counts as a visit or calls a function.
//
// Checks: home loads; the Nests nav and its "+" (add a nested room) are visible; no "Dummy feed"
// text on the page; <meta name="robots"> carries noindex unless the room is lifted.
// "Lifted" = site.json "preview" is false, or SMOKE_LIFTED=1. Only Jebb lifts a room.
import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(process.env.SMOKE_ROOT || path.join(here, '..', '..'));
let site = {};
try { site = JSON.parse(fs.readFileSync(path.join(root, 'site.json'), 'utf8')); } catch { /* checked below */ }
const lifted = process.env.SMOKE_LIFTED === '1' || site.preview === false;
const BLOCK = /cloudfunctions\.net|run\.app\/.*(visit|pixel)|googletagmanager\.com|google-analytics\.com/i;

test.beforeEach(async ({ page }) => {
  await page.route(BLOCK, route => route.abort());
});

test('site.json parses', () => {
  expect(fs.existsSync(path.join(root, 'site.json')), 'site.json at repo root').toBeTruthy();
  expect(site.siteId, 'site.json siteId').toBeTruthy();
});

test('home loads with nests, "+", no dummy feed, noindex unless lifted', async ({ page }) => {
  const pageErrors = [];
  page.on('pageerror', e => pageErrors.push(e.message));

  const resp = await page.goto('/', { waitUntil: 'domcontentloaded' });
  expect(resp && resp.ok(), 'GET / returns 2xx').toBeTruthy();
  await expect(page).toHaveTitle(/\S/);

  // Nests are mandatory in every room: the "Nests" nav group, at least one nest link, and the "+".
  await expect(page.locator('.nav-nests-label').first()).toBeVisible({ timeout: 20_000 });
  expect(await page.locator('a[data-nest]').count(), 'at least one nest link').toBeGreaterThan(0);
  // T0 factory: #nav-nest-add. airlineschat/amachat fork (EXCEPTIONS E7, "+" store on userNests): .nav-nests-add.
  const plus = page.locator('#nav-nest-add, .nav-nests-add[data-nest-add]').first();
  await expect(plus).toBeVisible();
  await expect(plus).toHaveText('+');

  // Placeholder feed copy must never ship.
  const text = await page.locator('body').innerText();
  expect(text, 'no "Dummy feed" text').not.toMatch(/dummy\s*feed/i);

  // Preview lock: noindex stays until Jebb lifts the room.
  const robots = await page.locator('meta[name="robots"]').evaluateAll(els => els.map(e => e.getAttribute('content') || '').join(' '));
  if (lifted) {
    test.info().annotations.push({ type: 'lifted', description: 'room is lifted: noindex not required' });
  } else {
    expect(robots, 'meta robots noindex (preview lock)').toMatch(/noindex/i);
  }

  if (pageErrors.length) test.info().annotations.push({ type: 'pageerror', description: pageErrors.join(' | ').slice(0, 500) });
});
