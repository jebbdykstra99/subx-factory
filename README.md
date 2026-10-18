# subx-factory

The single source for every SubX room's `factory.js`. Rooms stay self-contained GitHub Pages repos. This repo **stamps** them by pull request and **checks nightly** that they haven't drifted.

- Release: `v1.0.1`. `factory/factory.js` sha256 `5db3afa90854…` (289,004 B; see `FACTORY_RELEASE.json`).
- v1.0.1: a nest view queries its own posts (`siteId` + `nestSlug`, `createdAt` desc, 80 at a time) with an "Older posts in this nest" control. The home feed is still the newest 80 for `siteId`. If the composite index is missing, the nest pages that same `siteId` + `createdAt` query until the page fills, the collection ends, or 4,000 documents are scanned. The index definition is `factory/firestore.indexes.json` — do not deploy that file as the project's full index set.
- Owner: jebbdykstra99. All Actions are free (public repo). No paid services.
- **Rules are never deployed from here.** `rules/` is a reference copy plus emulator tests. Jebb hand-publishes Firestore and Storage rules in the console.

## What v1.0.0 is
T0 master template (hosted Firebase config, rail overlay, nest group headers, nest seat cards, visit pixel) **plus** gpchat's features from PR #31 @ `43a1936` (Watchlist, topic/people follow, notifications, DMs, F1 session seeds and rail merge, and the preview-lift write guards: server time, link and field limits, impersonation checks, `rateLimits` throttle batch, steward label). Rebuild with `build/rebuild.sh` (3-way `git merge-file`, then `build/resolve.py` and the function-level `build/fold.py`). CI checks that the rebuild is byte-identical.

Room differences are **data**, in `site.json`:
| Key | Default | Meaning |
|---|---|---|
| `features.watchlist / following / notifs / topicFollow / sessionSeeds` | all `false` | gpchat-only today (EXCEPTIONS E8) |
| `rail.kind` | `room-brief` | `f1-calendar` = F1 rail (gpchat only); `nws-forecast` / `bart-bsa` = pinned-first; `rail.liveKeep` = samo merge; `rail.productLocation` = NWS CWF office |
| `rail.overlay.enabled` | off | rail interstitial |
| `skin.avatarInitials, bioDefault, profileEmpty, guestHandle, exploreEmpty, seatTag, storiesPlaceholder, regNamePlaceholder, taglineH1, keepBrandTitle` | neutral | room copy that used to be hardcoded in JS |
| `minAge` | 13 | age gate text and check (booze 21, boyfriend 18) |
| `pixel` | on | `false` = no visit beacon (rooms that never had it, until privacy v1.1) |
| `earlyWelcome`, `earlyWelcomeCopy`, `trustBlurb`, `emptyState`, `composePlaceholder` | | as before |
| `redditCrosspost`, `redditSr` | | only 415chat/samochat keep them |

Copy note: many rooms carried stale fallbacks from the 415/311 lineage (avatar "415", bio "Talking about the city.", guest handle "guest415"). The stamp drops them for neutral defaults unless `rooms.json` sets a room-appropriate `skin` value (311, 415, samo, boyfriend, cia, cobra, gp).

## Files
- `factory/factory.js`: the release. Also the template assets `nests.css`, `404.html`, `_redirects`.
- `rooms.json`: the 20 rooms (repo, domain, siteId, cluster, stamp order, status, waitFor, features, skin, sitePatch, keepFiles, allowLoss).
- `EXCEPTIONS.md`: every intended room difference. Mandatory.
- `tools/stamp.py`: stamp one room clone (factory.js, `?v=` bumps, site.json merge, `FACTORY.lock`). It refuses unlisted differences.
- `tools/dry_run.py`: stamp all 20 in temp copies and write the table (`reports/STAMP_DRYRUN.md`).
- `tools/smoke.mjs`: headless load of stamped folders. Read-only; the pixel and Cloud Functions are blocked.
- `tools/drift_check.py`: live hashes vs `FACTORY.lock` vs the release.
- `templates/room/`: shared Playwright smoke test + PR workflow synced into every room; `tools/room_agents_md.py` renders each room's `AGENTS.md`. See `templates/README.md`.
- `.github/workflows/`: `room-smoke.yml` (shared smoke test on 3 pilot rooms, as-is and locally stamped, on every PR), `ci.yml` (node --check, eslint, no `AIza`, reproducible rebuild), `drift.yml` (nightly 4:17 AM MT, read-only), `stamp.yml` (manual dispatch only; refuses to run, including room clones, until `rules_step1_live=YES`; then one PR per room on a new branch; **no force-push, never main**).
- `rules/`: proposed Firestore (= gpchat PR #31 final) and Storage rules, baselines, emulator tests. Reference only.

## Stamping (Jebb)
1. **First publish Firestore rules step 1** (`RULES_PASTE_for_Jebb.txt`). The new factory.js writes `rateLimits` in the same batch as every post. On the old rules, posting breaks.
2. Add the Actions secret `ROOMS_TOKEN`: a fine-grained PAT with access to the room repos only, Contents: write + Pull requests: write.
3. Actions > stamp > Run only after step 1 is published. The workflow refuses to run unless `rules_step1_live=YES`. First run: `rooms=ready`, `dry_run=true`. Then `dry_run=false`.
4. Merge PRs in `rooms.json` order (T0 → L1a → L1b → L3 → L2). After each: `verify_nests.py --live` + `verify/public-check.sh`.
5. Blocked: airlineschat, amachat (userNests migration), popechat (TTS). Waiting: boyfriendchat (PR #8), gpchat (after the Singapore GP, PR #31 merged, rules step 3).
