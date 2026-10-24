# subx-factory

The single source for every SubX room's `factory.js`. Rooms stay self-contained GitHub Pages repos. This repo **stamps** them by pull request and **checks nightly** that they haven't drifted.

- Release: `v1.2.3`. Core `factory/factory.js` 254,661 B (budget 255,000 B, `tools/check_budget.sh`, CI fails above it), plus three opt-in files (see `FACTORY_RELEASE.json` for sha256):
  - `factory/factory-gp.js` (31,358 B): Watchlist, topic follow, session seeds, F1/OpenF1 rail. Loaded only when site.json turns on `features.watchlist|topicFollow|sessionSeeds` or `rail.kind: f1-calendar` (gpchat only today).
  - `factory/factory-rail.js` (10,231 B): NWS forecast/alerts, NWS CWF, BART BSA live rails. Loaded only for `rail.kind nws-forecast|nws-cwf|bart-bsa` or a rail with `forecastUrl`/`lat`+`lon` (415, 808, samo, bart).
  - `factory/factory-reports.js` (6,535 B): report loop (A9): report status, admin triage, "My reports", `report_update` notifications. Loaded only when site.json turns on `features.reportLoop` (no room yet).
  - Opt-in files load **before** `factory.js` (`<script src="factory-gp.js?v=N"></script>`); `tools/stamp.py` adds/removes the tags and files from the stamped site.json. A room without the file runs neutral core stubs (feature-off behavior; a live rail falls back to the room's fallback cards). `build/split.mjs` generates all four from the single-file build, so `build/rebuild.sh --check` stays byte-reproducible.
- v1.2.2 → v1.2.3: **report loop, A9 pieces 2+3 (2026-10-22)**, opt-in `factory-reports.js` (`features.reportLoop`). Report lifecycle `open → reviewing → actioned | dismissed`. The admin Reports panel gets **Reviewing / Action taken / Dismiss** buttons (Remove post unchanged); each writes `status`, `reviewedBy`, `reviewedAt` (server time), a `history` entry and, for actioned/dismissed, an optional `resolution` note (≤120 chars, prompted). Actioned and dismissed reports leave the queue. Each status change sends the reporter a **`report_update`** notification (`users/{reporter}/notifications`, no postId, text like "We reviewed your report and took action." + note); the bell shows the text and a click opens **My reports**. Signed-in non-admin members get a **My reports** nav entry listing the reports they filed in this room (query `siteId` + `reporterUid`; the rules let a reporter read only their own) with status labels Received / Under review / Action taken / Reviewed, no action. Live rules already accept every write (reports update is admin-only; notification type ≤ 20 chars). The pending NOTIFS_REPORTS rules paste needs `'report_update'` in its type list (addendum kept outside this repo). Without the opt-in a room keeps the v1.2.2 panel (Dismiss only). Core +609 B (stubs, accessors, overlay id). Test: `node test/report-loop.test.js`.
- v1.2.1 → v1.2.2: **notifications and reports write real docs (2026-10-22)**. Every room (not only rooms with `features.notifs`) writes `users/{to}/notifications` for **reply, like, follow** (when `features.following` is on) **and @mention** (handle resolved against authors already loaded in the room feed; at most 5 people per post; the parent author who already gets the reply notif for that post gets no mention notif). Like/follow use fixed doc ids (`like_<postId>_<uid>`, `follow_<uid>`) so unlike/relike can't spam; a repeat is refused by the rules and only logged. No self-notifications. The bell UI is still gated by `features.notifs` (EXCEPTIONS E8). Reports (`reports`, post and story) now carry `status: 'open'`; the admin count treats missing or `open` as open. Report outcome is a toast (it was only written into the compose box, which a page without the composer never shows), and a refused report says to verify email instead of "Post blocked by room guard"; any other failure says "Could not report. Try again." (never the raw error). A report/block gate message is toasted only when the compose error line isn't visible. Live Firestore rules already accept all of these writes; optional hardening paste is outside this repo. Reply notif now goes through the same `sendNotif()` (one entry point per new post). Core +1,534 B. (Numbered v1.2.2 so it doesn't collide with PR #9's v1.3.0.)
- v1.2.0 → v1.2.1: no behavior change. Lean trim, 254,915 → 252,518 B (−2,397 B): shipped comments moved into `build/fold.py`/`build/split.mjs`, dead `likes` read dropped, duplicate `nestSlugNorm` folded into `nestKey` (same body). Token stream identical to v1.2.0 apart from those three code edits. Opt-in files change only in their version banner.
- v1.1.0 → v1.2.0: **accounts gate, re-scoped 2026-10-22 (SubX: anyone can sign up)** (port of gpchat `accountsOpen()`/`applyAccountsGate()`). A room is **closed only** when its site.json says `"accountsOpen": false` (or `"accounts": "closed"`). A missing flag is **open**. `preview: true` is the preview banner only (static index.html markup) and **never** closes sign-ups. Closed rooms hide Register, Create an account, Google and the Google age/date-of-birth boxes (those are hidden only in a closed room); Register/Google refuse; `ensurePublicProfile` (users/{uid}, display name/handle) and `guardedPostWrite` reject; `requireVerified` refuses post/story/like/vote/follow/DM/add-a-room (report and block still work). Admin UID is exempt. `localStorage['subx.steward']='1'` shows the Google button on a closed room for the admin sign-in only; any other uid is signed out. Email sign-in for existing accounts stays. **Every `rooms.json` room must carry an explicit `"accountsOpen": true|false`**; `tools/stamp.py` and `tools/dry_run.py` refuse (exit 2) a room without one, and the stamp writes it into site.json. All 20 rooms are `true` today. Tests: `node test/accounts-gate.test.js`, `node test/accounts-gate.headless.mjs <room-dir>`.
- v1.0.1 → v1.1.0: no behavior change. 289,004 B single file split into core + opt-ins (lean audit 2026-10-22, P0 #2). Headless render of template-stamped gpchat, 415chat, samochat, 27chat matched v1.0.1.
- v1.0.1: a nest view queries its own posts (`siteId` + `nestSlug`, `createdAt` desc, 80 at a time) with an "Older posts in this nest" control. The home feed is still the newest 80 for `siteId`. If the composite index is missing, the nest pages that same `siteId` + `createdAt` query until the page fills, the collection ends, or 4,000 documents are scanned. The index definition is `factory/firestore.indexes.json` — do not deploy that file as the project's full index set.
- Owner: jebbdykstra99. All Actions are free (public repo). No paid services.
- **Rules are never deployed from here.** `rules/` holds proposed rules plus emulator tests, not a copy of what is live (see below). SubX hand-publishes Firestore and Storage rules in the console.

## What v1.0.0 is
T0 master template (hosted Firebase config, rail overlay, nest group headers, nest seat cards, visit pixel) **plus** gpchat's features from PR #31 @ `43a1936` (Watchlist, topic/people follow, notifications, DMs, F1 session seeds and rail merge, and the preview-lift write guards: server time, link and field limits, impersonation checks, `rateLimits` throttle batch, steward label). Rebuild with `build/rebuild.sh` (3-way `git merge-file`, then `build/resolve.py` and the function-level `build/fold.py`). CI checks that the rebuild is byte-identical.

Room differences are **data**, in `site.json`:
| Key | Default | Meaning |
|---|---|---|
| `features.watchlist / following / notifs / topicFollow / sessionSeeds` | all `false` | gpchat-only today (EXCEPTIONS E8) |
| `rail.kind` | `room-brief` | `f1-calendar` = F1 rail (gpchat only); `nws-forecast` / `bart-bsa` = pinned-first; `rail.liveKeep` = samo merge; `rail.productLocation` = NWS CWF office |
| `rail.overlay.enabled` | off | rail interstitial |
| `skin.avatarInitials, bioDefault, profileEmpty, guestHandle, exploreEmpty, seatTag, storiesPlaceholder, regNamePlaceholder, taglineH1, keepBrandTitle` | neutral | room copy that used to be hardcoded in JS |
| `minAge` | 18 | age gate text and check (booze 21; no room goes below 18) |
| `pixel` | on | `false` = no visit beacon (rooms that never had it, until privacy v1.1) |
| `earlyWelcome`, `earlyWelcomeCopy`, `trustBlurb`, `emptyState`, `composePlaceholder` | | as before |
| `redditCrosspost`, `redditSr` | | only 415chat/samochat keep them |

Copy note: many rooms carried stale fallbacks from the 415/311 lineage (avatar "415", bio "Talking about the city.", guest handle "guest415"). The stamp drops them for neutral defaults unless `rooms.json` sets a room-appropriate `skin` value (311, 415, samo, boyfriend, cia, cobra, gp).

## Files
- `factory/factory.js`: the release. Also the template assets `nests.css`, `404.html`, `_redirects`.
- `rooms.json`: the 20 rooms (repo, domain, siteId, cluster, stamp order, status, **accountsOpen (required boolean)**, waitFor, features, skin, sitePatch, keepFiles, allowLoss).
- `EXCEPTIONS.md`: every intended room difference. Mandatory.
- `tools/stamp.py`: stamp one room clone (factory.js, `?v=` bumps, site.json merge, `FACTORY.lock`). It refuses unlisted differences.
- `tools/dry_run.py`: stamp all 20 in temp copies and write the table (`reports/STAMP_DRYRUN.md`).
- `tools/smoke.mjs`: headless load of stamped folders. Read-only; the pixel and Cloud Functions are blocked.
- `test/accounts-gate.headless.mjs [room-dir ...]`: Chrome headless gate check on live gpchat markup (`test/fixtures/gpchat`) and any room dir passed: preview:true with no flag open, preview:true + accountsOpen:true open, accountsOpen:false / accounts:'closed' closed, closed + steward, preview:false + accountsOpen:true open, no flags open, site.json as served. Sign-in and Firestore writes are aborted in the browser.
- `tools/drift_check.py`: live hashes vs `FACTORY.lock` vs the release.
- `.github/workflows/`: `ci.yml` (node --check, eslint, no `AIza`, reproducible rebuild), `drift.yml` (nightly 4:17 AM MT, read-only), `stamp.yml` (manual dispatch only; refuses to run, including room clones, until `rules_step1_live=YES`; then one PR per room on a new branch; **no force-push, never main**).
- `rules/`: proposed Firestore (= gpchat PR #31 final) and Storage rules, baselines, emulator tests. **Not** a source of truth for what is live: `firestore.rules.proposed` is behind the live Firestore rules, and `storage.rules.proposed` matches the live Storage rules as of 2026-10-22 (#6). The live rules are whatever SubX last hand-published in the console.

## Swapping the disclosure mark family
`whoMark(tier, names)` renders the AI-disclosure mark (`human` | `ai` | `hybrid`). **The art is a placeholder** (`marks/placeholder-ring`, ring + H / A / H+A); the family vote is still open. Art and ids are data, so a new family is one command and nothing else: no `factory.js` edit, no per-room edit, no per-room PR.

| File | Role |
|---|---|
| `assets/whomark/sprite.svg` | one sprite, one cached request; a `<symbol>` per tier + `-sm` small variant, `viewBox="0 0 24 24"`, `<title>` each; main stroke `currentColor` (light/dark/mono), one accent `var(--wm-accent)` |
| `assets/whomark/config.json` | tier → `symbolId`, `symbolIdSmall`, `textLabel`, `ariaLabel`, `title`, `plainText` (X/Reddit share text), `ogBadge`, `cornerBadge`; `minSizePx` (hybrid ≥ 16), `labelRequiredAtOrBelowPx` 14, `smallBelowPx` 20 |
| `assets/whomark/whomark.js` | `whoMark(tier, names, {size,label,cls})` → `<span class="wm"><svg role="img" aria-label><title/><use href="sprite.svg?v=<hash>#id"/></svg><span class="wm-label">…</span></span>`; `whoMarkPlain(tier, names)`; `whoMarkBadges(tier)` → `{og, corner}`. Its config block is generated |
| `assets/whomark/og-*.png`, `corner-*.png` | og-card badge (128 px) and image-corner overlay (48 px), rendered from the sprite |
| `build/whomark.py` | validate a family, stamp config into `whomark.js`, render PNGs (`pip install cairosvg`), `--check` |
| `marks/<family>/` | family inputs: `sprite.svg` + `config.json` only. `placeholder-square` is a second placeholder used by the swap tests |

Labels are policy and the validator refuses a family that changes them: human **Human-made**; ai **AI steward · SubX** (title "Operated by SubX using AI tools. Not a real person."); hybrid **Human + AI** (title/aria "Human + AI: <names>", names HTML-escaped). Budgets: sprite.svg ≤ 8,192 B, config.json ≤ 4,096 B, whomark.js ≤ 8,192 B, each PNG ≤ 16,384 B, folder ≤ 65,536 B, and `factory/factory.js` ≤ 255,000 B.

**Rooms.** Off by default. A room opts in with site.json `"whoMark": true`; `tools/stamp.py` then copies `assets/whomark/` into the room and adds `<script src="/assets/whomark/whomark.js?v=<hash>">` before `factory.js` (flag off = tag and folder removed). `factory.js` is **not changed** (0 B; once the accounts gate lands the core has ~20 B of headroom, too little for even a one-line hook). Instead `whomark.js` replaces the factory's AI steward text pill (`stewardPillHtml()`, matched by its "Operated by SubX using AI tools" title) with `whoMark('ai')` as posts render, including posts added later (MutationObserver). The Sample and Steward pills are left alone. Without the flag, or if `whomark.js` did not load, the room shows today's text pill.

**Swap a family (the 3 steps):**
1. Make a folder with the new `sprite.svg` + `config.json` (copy `marks/placeholder-ring/` as the template; keep the labels, change ids, art, accent, badge colours).
2. `./swap-marks.sh marks/<family> --dry-run` — validates and prints the file/size diff; writes and pushes nothing.
3. `./swap-marks.sh marks/<family>` — copies sprite + config into `assets/whomark/`, regenerates `whomark.js` config + PNGs, rebuilds `factory/` (`build/rebuild.sh` → `build/fold.py`), runs every test, commits as Cursor Agent on a new branch, pushes, and opens **one draft PR** here for two-key CLEAR. Never merges. Rooms pick it up on their next normal stamp.

`--no-pr` does step 3 on a local branch without pushing (used to prove the flow). Tests: `node test/whomark.test.js` (3 tiers, escaping, sizes, swap, dry-run, refusal of an incomplete family, the pill upgrade in a fake DOM and in headless Chrome when available) and `python3 build/whomark.py --check`.

```
usage: ./swap-marks.sh <family-dir> [--dry-run] [--no-pr] [--base <ref>] [--branch <name>]

  <family-dir>   folder with exactly the two family inputs: sprite.svg + config.json (e.g. marks/placeholder-square)
  --dry-run      validate + print the diff (files and sizes) against assets/whomark/; writes nothing, pushes nothing
  --no-pr        do the real swap on a new local branch (build, tests, commit) but do not push or open a PR
  --base <ref>   branch point for the swap branch (default: origin/main)
  --branch <n>   branch name (default: cursor/whomark-family-<family>-<YYYYMMDD-HHMM>)

Steps: (1) validate the family: human/ai/hybrid + -sm symbols, every <symbol> parses with viewBox 0 0 24 24 and
<title>, config fields complete, policy labels unchanged, asset byte budgets, factory/factory.js <= 255,000 B;
(2) copy sprite.svg + config.json into assets/whomark/, regenerate whomark.js config + og/corner PNGs, rebuild
factory/ via build/rebuild.sh (build/fold.py), run every test; (3) commit as Cursor Agent on a new branch, push with
the gh credential helper and open ONE draft PR in subx-factory for two-key CLEAR. Never merges, never stamps rooms
(rooms pick the new family up on their next normal stamp). Needs: python3 + cairosvg, node + npm install, gh.
```

## Stamping (SubX)
1. **First publish Firestore rules step 1** (`RULES_PASTE_for_Jebb.txt`). The new factory.js writes `rateLimits` in the same batch as every post. On the old rules, posting breaks.
2. Add the Actions secret `ROOMS_TOKEN`: a fine-grained PAT with access to the room repos only, Contents: write + Pull requests: write.
3. Actions > stamp > Run only after step 1 is published. The workflow refuses to run unless `rules_step1_live=YES`. First run: `rooms=ready`, `dry_run=true`. Then `dry_run=false`.
4. Merge PRs in `rooms.json` order (T0 → L1a → L1b → L3 → L2). After each: `verify_nests.py --live` + `verify/public-check.sh`.
5. Blocked: airlineschat, amachat (userNests migration), popechat (TTS). Waiting: boyfriendchat (PR #8), gpchat (after the Singapore GP, PR #31 merged, rules step 3).
