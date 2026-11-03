# Shared pinned shell

One `factory.js` for every room, served from this repo, pinned by commit SHA and checked with SRI. Rooms stop carrying their own copy. A room differs from the shell only through **declared** layers in its `site.json`; anything undeclared is drift.

Status: proposal (draft PR). No room loads from here yet. Nothing is deployed by this folder.

## What is served

`shell/vX.Y.Z/` holds byte-identical copies of `factory/` at that release, plus `SHELL.json` (bytes, sha256, SRI sha384, source commit). A folder is **never edited** after it merges; a shell change is a new folder. `test/shell_pin.test.py` fails CI if a file stops matching its `SHELL.json`, or if the folder for the current `FACTORY_RELEASE.json` version differs from `factory/`.

Host: **jsDelivr's GitHub mirror** of this public repo. No new service, no account, no cost, no deploy step: every room already loads `emoji-picker-element` from `cdn.jsdelivr.net`. A URL with a full 40-character commit SHA is served `cache-control: public, max-age=31536000, immutable`, `content-type: application/javascript`, `access-control-allow-origin: *` (checked 2026-11-02 on `factory/factory.js@63e2dca`, bytes = sha256 `53765ec2…`).

## The room include

```html
<script src="https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@<FULL_MERGE_SHA>/shell/v1.2.6/factory.js"
        integrity="sha384-P1qjkeL0BmNyUksLCAUJJ0Lws2AX1bx7hdOGxVHEbHjXQsof63F7DxNAZQbDXFpY"
        crossorigin="anonymous"
        data-site="site.json?v=N"></script>
```

- Pin rule: full commit SHA only. Never `@main`, a branch, `@latest`, or a semver range (those are mutable and break SRI). `tools/shell_drift.py` reports anything else as drift.
- `integrity` comes from `shell/<version>/SHELL.json`. `crossorigin="anonymous"` is required for SRI on a cross-origin script.
- `data-site` stays on the tag. The shell reads it from `document.currentScript` and fetches `site.json` relative to the **page**, so config, `localStorage`, Firebase Auth domains and App Check stay per room origin.
- Opt-in files (`factory-gp.js`, `factory-rail.js`, `factory-reports.js`) load the same way, **before** `factory.js`, each with its own `integrity`.
- Before the merge SHA exists, the same bytes are at `@63e2dca439ee694501942eca91b2b9219bed78d9/factory/factory.js` with the same `integrity` (SRI is content-based). The drift check accepts that path only at the `sourceCommit` in `SHELL.json`.

## Release, cache, rollback

- Release: new `shell/vX.Y.Z/` folder in one subx-factory PR (the only code review). Each room then gets a generated two-line change (URL + integrity) in `index.html` and `site.json shell.base`; no code in room PRs.
- Cache: SHA URLs are immutable, so there is nothing to purge. The room's `index.html` decides which bytes run.
- Rollback: point the room's tag back at the previous SHA + integrity. Old SHA URLs keep working.
- If jsDelivr fails to serve, the SRI check fails, or the file is blocked, the room shell does not run (same failure as a broken local copy today). There is **no failover**: one `<script>` tag loads one URL, and no fallback loader exists. `window.subxKill` and site.json `kill` live inside the shell, so they only act when the shell loads.

## Guest state on migration

localStorage follows the page origin, not the script origin, so moving the shell to jsDelivr does not move or reset room storage. What changes is which keys the shell uses:

- v1.2.6 uses `subx.user` / `subx.likes`. At start (factory.js L10-18) it copies the first `<name>.user` / `<name>.likes` key on the origin into `subx.user` / `subx.likes` when those are empty. Old keys are left in place.
- Rooms already on `subx.user` (the v1.2.5, v1.0.1-based and e1e27433 shells) keep the same key: no change.
- Rooms on `415chat.user` (gpchat) or `311chat.user` (airlineschat, amachat) have the guest profile copied to `subx.user` on first load: kept.
- Likes: guests cannot like in any shell ("Guest cannot like"); likes are per signed-in uid in Firestore. Older shells load a local likes map that v1.2.6 does not read, so nothing visible is lost.
- Not carried over: room-only keys that v1.2.6 does not know. Today that is gpchat's `subx.ageBlock.<site>` (under-18 block time) and `subx.joinAttested.<site>` (sessionStorage). gpchat stays a declared fork until its age gate is ported, so these are kept.
- Session-scoped keys (`subx.hit.*`, `subx.authLand`, `subx.restorePath`) are per tab and have the same names in every shell.

Each room PR still verifies this on a preview (sign in, guest name, reload) before merge.

## Per-room overrides (first-class)

Order of preference. Use the first layer that can express the difference.

| Layer | What goes here | Declared in site.json `shell` | Drift check |
|---|---|---|---|
| 1. Config | `features`, `skin`, `rail`, `nests`, `minAge`, `imageUploads`, `stories`, `pixel`, `accountsOpen`, `redditCrosspost` … (see top-level README table) | not needed: config is the default | none |
| 2a. Theme | room `styles.css`, CSS variables, icons, og images, assets | `overrides.theme: ["styles.css", "assets/…"]` | files must exist |
| 2b. Copy | room strings: site.json keys (`skin.*`, `tagline`, `trustBlurb`, `emptyState` …) or a copy file | `overrides.copy: ["site.json:skin", "copy.json"]` | files must exist |
| 2c. Legal | Terms, Privacy, DMCA, age-gate markup, footer, report page. **Per room and never changed by a shell release** | `overrides.legal: ["terms.html", "privacy.html", "index.html#age-gate"]` | files must exist; listed so nobody "fixes" them into the shell |
| 2d. Modules | a small room extension file through a documented hook (below) | `overrides.modules: [{file, sha256, hooks, load, reason, injects?}]`; inline scripts: `overrides.inline: [{page, sha256, reason}]` | file must match its sha256; any undeclared local script is drift |
| 3. Fork | a full room `factory.js` pinned to a named base | `fork: true, base, file, sha256, reason, exception` | file must match its sha256; diff size vs base is reported |

Room content (nests, posts, steward copy) and posting rules stay per room in site.json and Firestore, as today. Non-shell room scripts that are not modules (`gate.js`, `takedown.js`, `ref.js`) go in `shell.keep` as `{file, sha256, reason}`. Executable inline `<script>` blocks are declared in `overrides.inline` as `{page, sha256, reason}` (sha256 of the exact script text; the same hashes a future CSP would list). `tools/shell_drift.py --suggest ROOM` prints these entries for a room PR.

Example: `site.shell.example.json`.

### Documented hooks (modules)

v1.2.6 has one code hook: **`window.__subxPlugins`** (the contract `factory-gp.js` / `factory-rail.js` / `factory-reports.js` already use). A module loads **before** the pinned shell and pushes an installer; the shell calls it once with `core` (helpers and live getters such as `site`, `SITE_ID`, `fbDb`, `toast`, `renderFeed`, `sendNotif`) and merges the returned object into its plugin slots:

`addToWatchlist, removeFromWatchlist, renderWatchlist, renderTopicFeed, renderFollowBtn, toggleTopicFollow, syncTopicFollowButtons, sessionSeedPosts, mergeF1Rail, fetchF1Cards, fetchNwsCards, fetchCwfCards, fetchBartCards, reportTriage, syncMyReports`.

A module may fill those slots and call `core` helpers; it cannot replace other shell functions. Example: `extension.example.js`.

A module loaded **after** the shell can only work on the DOM (the `assets/whomark/whomark.js` pattern: MutationObserver on rendered posts). v1.2.6 has no post-boot code hook, and the core has 69 B of budget headroom. A `SubX.onReady(fn)` hook is proposed for the next shell release (separate keyed PR), not added here, so the pinned bytes stay exactly v1.2.6.

If a difference fits none of the hooks, it is a fork (layer 3) until the shell grows a hook or a site.json flag for it.

### Forks

A fork is allowed, never silent: `shell.fork: true` with `base` (a `shell/` version), `file`, `sha256`, `reason` and an `EXCEPTIONS.md` row id. The drift check reports the fork's diff size against its base, so the debt stays visible. Any edit to the forked file without updating `sha256` is drift.

## Drift check

```
python3 tools/shell_drift.py ../room1 ../room2 [--md out.md] [--json out.json] [--strict]
```

Read-only. Status per room:

- `OK`: pinned shell + only declared overrides.
- `WARN`: OK, plus non-blocking notes. Today that is `emoji-picker-element@1` loaded without SRI (a mutable range); pin an exact version with `integrity` to clear it.
- `FORK`: declared fork; the diff size against its base is shown.
- `DRIFT`: anything undeclared. That includes:
  - no `shell` block, or no pinned shell `<script>` on any page (for example a pin inside an HTML comment)
  - an unpinned or integrity-less shell tag, any host other than `cdn.jsdelivr.net`
  - an undeclared local or remote script (quoted, single-quoted or unquoted `src`), on any `*.html` at any depth
  - an undeclared or edited inline `<script>` (`application/ld+json` and other data blocks are ignored)
  - a module, keep or inline entry without a matching sha256
  - runtime script injection (`createElement('script')`, `import()`, `importScripts`, `document.write('<script')`) in inline or loaded room JS without a declared `"injects": "<reason>"`; injection that names a factory/shell file is always drift
  - any local `.js` anywhere in the room that is a shell copy (release hash or SubX factory header) and is not the declared fork

`--strict` exits 1 on any DRIFT.
