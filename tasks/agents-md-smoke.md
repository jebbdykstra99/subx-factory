Task (repo {{owner}}/{{repo}}): add a room-specific AGENTS.md, the shared SubX Playwright smoke test, and a CI workflow.

1. Copy subx-factory `templates/room/` into the repo root: `tests/smoke/{package.json,playwright.config.mjs,smoke.spec.mjs}` and `.github/workflows/smoke.yml`. Do not edit them per room.
2. Write `AGENTS.md` at the repo root (`python3 tools/room_agents_md.py <clone>` in subx-factory renders it): what the repo is, siteId, deploy path (GitHub Pages from main), the locks (noindex + banner held until Jebb lifts; no gate.js unless location is core; nests mandatory; public phone +1-650-539-5005 only), and how to run tests.
3. Run the smoke test (`cd tests/smoke && npm install && npx playwright install chromium && npm test`).
4. Open one PR. Do not merge. Do not touch factory.js, site.json, index.html, noindex, robots.txt, the banner, rules, DNS or Pages settings.
