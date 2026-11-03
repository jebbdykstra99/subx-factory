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
- The pin URL is bare: **no `?v=` or any other query string, and no `#fragment`** (the SHA already busts caches). A pin with a query is drift.
- The pin is a classic `<script>`: **not `type="module"`**. In a module `document.currentScript` is null, so the shell would ignore `data-site` (and run deferred). A module-type pin is drift.
- If a page or the hosting config sets a Content-Security-Policy, its `script-src` (or `default-src` when there is no `script-src`) must allow `https://cdn.jsdelivr.net` or the pin's sha384 hash.
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
| 2d. Modules | a small room extension file through a documented hook (below) | `overrides.modules: [{file, sha256, hooks, load, reason, injects?, imports?}]`; inline code: `overrides.inline: [{page, sha256, reason, injects?, imports?}]`; frames: `overrides.frames: [{page, src or sha256, reason}]` | file must match its sha256; any undeclared local script is drift |
| 3. Fork | a full room `factory.js` pinned to a named base | `fork: true, base, file, sha256, reason, exception` | file must match its sha256; diff size vs base is reported |

Room content (nests, posts, steward copy) and posting rules stay per room in site.json and Firestore, as today. Non-shell room scripts that are not modules (`gate.js`, `takedown.js`, `ref.js`) go in `shell.keep` as `{file, sha256, reason}`. Executable inline `<script>` blocks, `on*=` event handlers and `javascript:` URLs are declared in `overrides.inline` as `{page, sha256, reason}` (sha256 of the exact script text or attribute value; the same hashes a future CSP would list). `<iframe srcdoc>` (sha256 of the srcdoc), `<object>`/`<embed>` and remote `<iframe src>` are declared in `overrides.frames`. A `<meta http-equiv=refresh>` to a remote URL is declared in `overrides.refresh: [{page, url, reason}]` (it still shows as `WARN`). Remote ES module imports are listed in the declaring entry's `imports`.

`index.html` must run the pinned shell. So must every other page that runs room JS: a module, a keep file, any other local script, the Firebase SDK, or declared inline code (inline `<script>`, `on*=` handlers, `javascript:` URLs). A page that is meant to run without the shell is listed in `shell.noShell: ["terms.html", ...]`; `index.html` cannot be listed. Today that is each room's static legal pages (`terms.html`, `privacy.html`, `guidelines.html`, `report.html` loading `takedown.js`), and its `404.html`. Nest bounce pages that are plain redirect stubs (below) need neither. Pages with no script at all need neither.

A noShell page runs without the kill switch and moderation, so it may load **only** `keep` files and declared inline code. A module, the Firebase SDK, any remote script (emoji picker included), an `<iframe>`/`<frame>`/`<object>`/`<embed>`/`srcdoc`, or a keep file that imports modules is drift there. Once any `keep` entry sets `"noShellOk"`, only keep entries with `"noShellOk": true` may load on noShell pages. A noShell page that does run the shell is a `WARN` (remove it from the list). `tools/shell_drift.py --suggest ROOM` prints the inline, frames, keep and noShell entries for a room PR.

### Redirect stubs and `shell.redirects`

A redirect stub is a page whose only job is to send the visitor to a page on the same site, such as a nest bounce page. It needs no `noShell` entry and no inline sha256, but only if it is really that simple:

- Its only code is one classic inline `<script>`. That script is either the `tools/nest_stubs.py` template (only the nest name may differ) or a bare `location.replace('/some/path')` to a path on the same site.
- It has no other script (local, remote or module), no `on*=` handler, no `javascript:` URL, no frame, `<object>` or `<embed>`, no form, no `<base href>` and no preload of a remote script.
- A `<meta http-equiv=refresh>`, if any, stays on the same site.
- It has none of the comment ends described under the drift check.
- `index.html` is never a stub, even when it looks like one. The main page always runs the shell.

List the stubs in `shell.redirects: ["nest/cats.html", ...]` (pages carrying the `nest_stubs.py` marker are checked too). A listed page that fails any rule above is drift, and the message says which rule. Each entry must be a page path inside the room: an entry with `..`, a backslash, `%`-encoding, a scheme such as `https:`, or a leading `//` is drift, as is a page that does not exist.

### Limits on noShell pages

A noShell page has no kill switch, so its declared inline code is limited too:

- Inline code there may not declare `injects` (it may not add scripts at runtime) or remote `imports`.
- Inline code that names a Firebase SDK address (`gstatic.com/firebasejs`, `/__/firebase/`, or a firebase package on an npm CDN) counts as loading the Firebase SDK, which is drift there.
- The same check applies to the text of every keep file loaded on a noShell page. Declaring `injects` on the keep entry does not exempt it.

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
- `WARN`: OK, plus non-blocking notes: `emoji-picker-element@1` loaded without SRI (a mutable range; pin an exact version with `integrity` to clear it), an undeclared remote `<iframe>`/`<frame>`, a declared remote meta refresh, a remote `<link rel=modulepreload|import>` or preload-as-script, a remote CSS `@import` (in `<style>` or a room `.css` file), CSS `url(javascript:)`, or a hosting config file the tool cannot parse.
- `FORK`: declared fork; the diff size against its base is shown.
- `DRIFT`: anything undeclared. That includes:
  - no `shell` block; no live, running shell pin on `index.html`; or a page that loads room JS without a running pin and is not in `shell.noShell`. A pin counts only if its `type` is empty or a classic JavaScript type, it has no `nomodule`, it is not inside `<template>`, `<noscript>`, a raw-text element (`textarea`, `title`, `iframe`, ...) or `<svg>`/`<math>`, the tag has no duplicated attributes, and no CSP on that page blocks it. A pin inside an HTML comment does not count either. A pin inside `<svg><foreignObject>` is **treated as inert** (conservative: some browsers would run it; move it out of the SVG).
  - a `type="module"` pin, or a pin URL with a query (`?v=`) or fragment
  - a CSP that blocks the pin: a `<meta http-equiv="Content-Security-Policy">` on the page, or a header CSP in the room's `_headers`, `firebase.json`, `netlify.toml` or `vercel.json` whose rule matches the page, where `script-src-elem` / `script-src` / `default-src` (first present) allows neither `https://cdn.jsdelivr.net` (host, `*.jsdelivr.net`, `https:` or `*`, with a matching path) nor the pin's `'sha384-…'` hash, or uses `'strict-dynamic'` without the hash. When the pin carries several integrity hashes, a hash-only policy must list all of them (CSP3). `Content-Security-Policy-Report-Only` does not block. A `<meta>` CSP is checked wherever it sits: one placed **after the pin or in `<body>`** is treated as applying, although browsers apply a meta CSP only to later content and ignore one outside `<head>` (a conservative drift; move or fix the tag). **Any other header CSP** (Cloudflare or GitHub Pages settings, a proxy, a `<meta>` injected at runtime, a hosting file the tool cannot read or parse, which is reported as `WARN`) is covered only by the C4 preview check on each room PR.
  - an unpinned or integrity-less shell tag, any host other than `cdn.jsdelivr.net`
  - an undeclared local or remote script (any `src` quoting, `data:`/`blob:` included; an SVG `<script href>` / `xlink:href` is a script source) on any page-like file at any depth (`.html`, `.htm`, `.xhtml`, `.shtml`, `.svg`, `.php`, `.phtml`)
  - a `<meta http-equiv=refresh>` to a `javascript:`/`data:` URL, or to an undeclared remote URL
  - an undeclared or edited inline `<script>`, `on*=` handler or `javascript:` URL (`application/ld+json` and other data blocks are ignored)
  - `<base href>` (it retargets every relative `src`, including declared modules; it cannot be declared)
  - an undeclared `<iframe srcdoc>`, `<object>` or `<embed>`, or a `data:`/`blob:`/`javascript:` frame source. A remote `<iframe src>` that is not declared is `WARN`.
  - a static `import`/`export … from` of a remote or bare specifier not listed in the declaring entry's `imports`, of an undeclared local module (local imports are followed transitively), or of any factory/shell file
  - a module, keep, inline or frames entry without a match (sha256 or src)
  - runtime injection or evaluation (below) without a declared `"injects": "<reason>"`; one that names a factory/shell file is always drift
  - any local `.js` anywhere in the room that is a shell copy (release hash or SubX factory header) and is not the declared fork

**How the check reads pages and URLs.** It reads them the way a browser does, so a trick that fools a simple parser but not a browser does not get through:

- Comment ends. Browsers end an HTML comment at `<!-->`, `<!--->` and `--!>`, and run whatever comes next. Some versions of Python's parser keep reading the comment. Any of the three, anywhere on a page, is drift, whatever Python version runs the check. Write comments as `<!-- ... -->`.
- URLs. Before deciding whether a script `src`, link `href`, frame `src`, import or refresh URL is local or remote, the check decodes HTML entities (once, as the browser does), strips leading and trailing control characters and spaces, removes tabs and line breaks anywhere, and reads `\` as `/`. Anything that then starts with `//` or a scheme is remote. So `/\evil.example/x.js` and `/&#9;/evil.example/x.js` are remote scripts even if a file with that literal name sits in the room. Local paths are also `%`-decoded before the check makes sure they stay inside the room.
- A keep or module entry whose file name contains a space, a control character, a backslash or `%` is drift, because a browser would never request that literal path.

**Injection detection is best-effort.** It is static pattern matching over inline code and every local JS file a page loads or imports: `createElement('script')` or a non-literal `createElement(x)`, `import()`, `importScripts`, `document.write('<script')`, `eval`, `new Function`, `new Worker`/`SharedWorker`, `serviceWorker.register`. Obfuscated code, string building, `fetch` plus indirect evaluation or DOM tricks it does not know can still evade it. It is not a security boundary. What holds is the sha256 pin: every declared module, keep file and inline block is pinned to the bytes a human reviewed, so each one must be read in its room PR, not just hashed.

`--strict` exits 1 on any DRIFT.
