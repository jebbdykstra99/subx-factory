# Strict Content-Security-Policy for rooms

The drift check (`tools/shell_drift.py`) is a static guardrail. The CSP is the enforcement layer: it is what a
browser actually obeys, so it also covers the cases the checker cannot see (HTML-like comments in classic scripts,
obfuscated code, a page edited after review). Every HTML page in a room carries one.

## The meta tag

Put this as the **first element in `<head>`**, before any `<script>`, on every `.html` page (stubs and `404.html`
included). Browsers ignore a meta CSP outside `<head>`, and it does not cover scripts that come before it.

```html
<meta http-equiv="Content-Security-Policy" content="script-src 'self' https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@<FULL_MERGE_SHA>/shell/v1.2.6/ https://www.gstatic.com/firebasejs/10.12.2/ https://cdn.jsdelivr.net/npm/emoji-picker-element@1.29.1/ 'sha256-<404.html script>' 'sha256-<redirect stub script>'; object-src 'none'; base-uri 'none'">
```

Fill in:

- `<FULL_MERGE_SHA>`: the same full 40-character commit SHA as the room's pin tag. Before the merge SHA exists, use
  `https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@63e2dca439ee694501942eca91b2b9219bed78d9/factory/`.
  The folder covers `factory.js` and the opt-in files (`factory-rail.js`, ...) of the same release.
- `'sha256-…'`: one hash per distinct inline script on a redirect stub or on `404.html`. These are the only inline
  scripts allowed; everything else lives in a file. Hash = base64 sha256 of the exact text between `<script>` and
  `</script>` (after newline normalization to `\n`). Drop the token when the room has no such script.
- The Firebase folder must match the exact SDK version the pages load.
- Only list hosts the page uses. Add `https://www.google.com/recaptcha/ https://www.gstatic.com/recaptcha/` only
  if the room turns on Firebase App Check with reCAPTCHA.

Not allowed (the checker reports them): `'unsafe-inline'`, `'unsafe-eval'`, `'unsafe-hashes'`, `'wasm-unsafe-eval'`,
`'strict-dynamic'`, nonces (a static page cannot rotate them), `*`, scheme sources (`https:`, `data:`, `blob:`), a
bare `https://cdn.jsdelivr.net`, a repo path without a SHA, a tag, a branch or a short SHA, any version range
(`emoji-picker-element@1/`), any host not listed above, a hash that matches no stub or 404 script, and a policy
without `object-src 'none'` or `base-uri 'none'`. Inline `on*=` handlers and `javascript:` URLs stop working under
this policy; the checker reports any it finds on a page with a strict CSP.

## emoji-picker-element

Two forms are accepted. Either one clears the emoji `WARN`.

1. **Exact-version folder in `script-src`** (as in the tag above):
   ```html
   <script type="module" src="https://cdn.jsdelivr.net/npm/emoji-picker-element@1.29.1/index.js"></script>
   ```
   with `https://cdn.jsdelivr.net/npm/emoji-picker-element@1.29.1/` in `script-src`. The folder, not just
   `index.js`: `index.js` imports `./picker.js` and `./database.js`. SRI on the tag alone does not clear the `WARN`,
   because it cannot cover those imports.
2. **Self-hosted (`'self'`) with SRI**: copy the package files of one exact version into the room (for example
   `vendor/emoji-picker-element/`), declare them in `shell.keep`, and load
   ```html
   <script type="module" src="vendor/emoji-picker-element/index.js" integrity="sha384-…" crossorigin="anonymous"></script>
   ```
   No CDN source is needed in `script-src` then.

The emoji data JSON the picker fetches is `connect-src`, which this policy leaves open.

## Header delivery (the target) vs meta (the fallback)

A meta CSP cannot set `frame-ancestors`, `report-uri` / `report-to` or `sandbox`; browsers ignore them in a meta
tag. So for room mode the target is the same policy sent as an HTTP header by the host (Firebase Hosting
`firebase.json` `hosting.headers`, or `_headers`), with `frame-ancestors 'none'` and a report endpoint added there.
GitHub Pages cannot set headers, so the meta tag is the fallback for rooms served there. The checker accepts either:
a strict meta tag on the page or a strict header rule that matches the page.

```json
{"hosting": {"headers": [{"source": "**", "headers": [{"key": "Content-Security-Policy",
  "value": "script-src 'self' https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@<FULL_MERGE_SHA>/shell/v1.2.6/ https://www.gstatic.com/firebasejs/10.12.2/ https://cdn.jsdelivr.net/npm/emoji-picker-element@1.29.1/; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"}]}]}}
```

## Required by default

`cspRequired` (in `site.json` `shell`, or top level) defaults to `true`: a room without a strict CSP on every HTML
page is `DRIFT`. The 20 rooms that predate the rule are listed in `tools/csp_legacy_rooms.json`; for them a missing
or weak CSP is `WARN`. A room leaves that list in its CSP migration PR, which also sets `"cspRequired": true`.
`cspRequired: false` is `DRIFT` for any room not on the list, so the hub, topic mode and new rooms start strict.
