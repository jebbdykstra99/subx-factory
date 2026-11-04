# Strict Content-Security-Policy for rooms

The drift check (`tools/shell_drift.py`) is a static guardrail. The CSP is the enforcement layer: it is what a
browser actually obeys, so it also covers the cases the checker cannot see (HTML-like comments in classic scripts,
obfuscated code, a page edited after review). Every HTML page in a room carries one.

## The meta tag

Put this as the **first element in `<head>`** on every `.html` page (stubs and `404.html` included). Only
`<!DOCTYPE>`, `<html>`, `<head>`, `<meta charset>`, comments and whitespace may come before it; the checker reports
anything else (a `<title>`, `<link>`, `<base>`, `<div>`, text or a `<script>`), because a browser may then close
`<head>` early and put the meta in `<body>`, where it is ignored, or apply it only to what follows. Write
`http-equiv="Content-Security-Policy"` exactly (any case, no spaces around it: browsers do not trim it). A meta tag
carries **one** policy, so it must not contain a comma; in a header a comma separates policies, in a meta it just
becomes part of a source list.

```html
<meta http-equiv="Content-Security-Policy" content="script-src 'self' https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@<FULL_MERGE_SHA>/shell/v1.2.6/ https://www.gstatic.com/firebasejs/10.12.2/ https://cdn.jsdelivr.net/npm/emoji-picker-element@1.29.1/ 'sha256-<404.html script>' 'sha256-<redirect stub script>'; object-src 'none'; base-uri 'none'">
```

Fill in:

- `<FULL_MERGE_SHA>`: the same full 40-character commit SHA as the page's own pin tag, and the same
  `/shell/v<base>/` folder. Before the merge SHA exists, use
  `https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@63e2dca439ee694501942eca91b2b9219bed78d9/factory/`
  (only on a page whose pin uses that `/factory/` path). The folder covers `factory.js` and the opt-in files
  (`factory-rail.js`, ...) of the same release. List no other subx-factory source: another SHA, another version
  folder or the repo root at the pin SHA is `DRIFT` (any of them would let other files from the repo run).
- `'sha256-…'`: one hash per distinct inline script on a redirect stub or on `404.html`. These are the only inline
  scripts allowed; everything else lives in a file. Hash = base64 sha256 of the exact text between `<script>` and
  `</script>` (after newline normalization to `\n`). Drop the token when the room has no such script.
- The Firebase folder must match the exact SDK version the pages load.
- Only list hosts the page uses. For Firebase App Check with reCAPTCHA, set `"recaptcha": true` in `site.json`
  `shell` (default `false`) and add exactly `https://www.google.com/recaptcha/api.js` (or
  `https://www.google.com/recaptcha/enterprise.js`) and `https://www.gstatic.com/recaptcha/releases/`. Nothing
  wider: the rest of `/recaptcha/` on both hosts serves a public AngularJS gadget that turns injected markup into
  script execution. Without the opt-in these sources are `DRIFT`.
- For Firebase Auth Google sign-in (the popup loads Google's gapi loader), set `"googleSignIn": true` in `site.json`
  `shell` (default `false`) and add exactly `https://apis.google.com/js/api.js` and
  `https://apis.google.com/_/scs/abc-static/` (the gapi iframes module). Never the bare `https://apis.google.com`
  host or another folder on it: it is a known CSP-bypass host (JSONP). Without the opt-in these sources are `DRIFT`
  (shell_drift rule C2g).

Not allowed (the checker reports them): `'unsafe-inline'`, `'unsafe-eval'`, `'unsafe-hashes'`, `'wasm-unsafe-eval'`,
`'strict-dynamic'`, nonces (a static page cannot rotate them), `*`, scheme sources (`https:`, `data:`, `blob:`), a
bare `https://cdn.jsdelivr.net`, a repo path without a SHA, a tag, a branch or a short SHA, any version range
(`emoji-picker-element@1/`), any host not listed above, a hash that matches no stub or 404 script, a `worker-src` or
`child-src` with `*`, a scheme or a wildcard host, and a policy without `object-src 'none'` or `base-uri 'none'`. Inline `on*=` handlers and `javascript:` URLs stop working under
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
  "value": "script-src 'self' https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@<FULL_MERGE_SHA>/shell/v1.2.6/ https://www.gstatic.com/firebasejs/10.12.2/ https://cdn.jsdelivr.net/npm/emoji-picker-element@1.29.1/ 'sha256-<404.html script>' 'sha256-<redirect stub script>'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"}]}]}}
```

A `**` header also covers the redirect stubs and `404.html`, so it carries their hashes, as the meta tag does
(drop a token when the room has no such script). A header and a meta on the same page both apply, and the browser
enforces both.

## Hosting redirects and rewrites

After a redirect, CSP checks only the new URL's origin, not its path. So a same-origin URL (`'self'`) that redirects
to `cdn.jsdelivr.net` would let **any** jsDelivr file run despite the exact pin folder. A redirect or rewrite to
another origin is `DRIFT`: `firebase.json` `hosting.redirects` / `hosting.rewrites`, `_redirects`, `netlify.toml`
`[[redirects]]`, `vercel.json` `redirects` / `rewrites`, and a `Location` or `Refresh` header in `_headers`.
Same-origin rules (the `/*  /index.html  200` nest fallback) are fine.

## Required by default

`cspRequired` (in `site.json` `shell`, or top level) defaults to `true`: a room without a strict CSP on every HTML
page is `DRIFT`. The 20 rooms that predate the rule are listed in `tools/csp_legacy_rooms.json`; for them a missing
or weak CSP is `WARN`. A room leaves that list in its CSP migration PR, which also sets `"cspRequired": true`.
`cspRequired: false` is `DRIFT` for any room not on the list, so the hub, topic mode and new rooms start strict.
