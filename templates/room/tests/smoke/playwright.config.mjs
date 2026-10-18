// Shared SubX room smoke config (synced from subx-factory templates/room/tests/smoke).
// Serves the room's repo root as static files and runs smoke.spec.mjs against it.
// Env: SMOKE_ROOT (dir to serve, default: repo root two levels up), SMOKE_PORT (default 4173),
//      SMOKE_BASE_URL (test a running server instead, e.g. a preview; skips the local server),
//      SMOKE_CHROME (path to a local Chrome instead of Playwright's bundled Chromium).
import { defineConfig } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(process.env.SMOKE_ROOT || path.join(here, '..', '..'));
const port = Number(process.env.SMOKE_PORT || 4173);
const baseURL = process.env.SMOKE_BASE_URL || `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: here,
  testMatch: /smoke\.spec\.mjs$/,
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['github']] : 'list',
  use: {
    baseURL,
    viewport: { width: 1280, height: 900 },
    launchOptions: process.env.SMOKE_CHROME ? { executablePath: process.env.SMOKE_CHROME } : {},
  },
  webServer: process.env.SMOKE_BASE_URL ? undefined : {
    command: `python3 -m http.server ${port} --bind 127.0.0.1 --directory "${root}"`,
    url: `http://127.0.0.1:${port}/`,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
