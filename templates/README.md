# templates/

## `room/`: files synced verbatim into every room repo
Everything under `templates/room/` is copied byte-for-byte into a room's repo root by
`tools/fanout.py --mode sync` (or by hand). Do not put docs in `room/`; they would ship to every room.

| Path in room | What |
|---|---|
| `tests/smoke/smoke.spec.mjs` | Playwright smoke test: Home loads; Nests nav + `+` visible; no `Dummy feed` text; `<meta name="robots">` has `noindex` unless the room is lifted (`site.json preview: false`, or `SMOKE_LIFTED=1`). Read-only: blocks Cloud Functions, the visit pixel and analytics |
| `tests/smoke/playwright.config.mjs` | Serves the repo root with `python3 -m http.server` on 127.0.0.1:4173. `SMOKE_BASE_URL` targets a running copy instead; `SMOKE_CHROME` uses a local Chrome |
| `tests/smoke/package.json` | Pins `@playwright/test` |
| `.github/workflows/smoke.yml` | Runs the smoke test on every PR (free Actions minutes on public repos). No secrets |

`AGENTS.md` is **not** a template file: it is room-specific and rendered by `tools/room_agents_md.py`
from the room's `site.json`, `rooms.json` and `EXCEPTIONS.md` (repo, siteId, deploy path, locks, how to test).

## Run it locally
```bash
cd templates/room/tests/smoke && npm install
SMOKE_ROOT=/path/to/cobrachat SMOKE_CHROME=/usr/bin/google-chrome npm test
python3 tools/room_agents_md.py /path/to/cobrachat > /tmp/AGENTS.md
```

## CI here
`.github/workflows/room-smoke.yml` runs the shared test on every subx-factory PR against three pilot rooms
(cobrachat, buffetchat, ciachat), both as they are on `main` and stamped locally with the PR's `factory.js`,
so a template change that would hide nests or the `+`, drop noindex, or ship placeholder copy fails before any stamp.
