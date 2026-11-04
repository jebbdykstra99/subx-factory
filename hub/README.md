# hub/ — the brand hub (preview)

The hub is rendered from `brand/brand.json` + `hub/src/` into `hub/site/` (committed, so a
deploy needs no build step). Every name, domain, tagline, noun, contact line and the footer
comes from `brand/brand.json`; templates hold `{{brand.*}}` tokens only.

## Render

    python3 tools/brand_render.py           # write hub/site/
    python3 tools/brand_render.py --check   # CI: hub/site/ matches a fresh render
    python3 test/hub_brand.test.py          # CI: pages, CSP, rename test, shell_drift

The rename test renders the hub with a dummy brand and fails if any brand literal is
left outside `brand/brand.json` (allowed: the repo path in the shell pin, the Firebase
project/site ids).

## Shell and CSP

- `index.html` runs the shared shell `shell/v1.2.6/factory.js`, pinned to a full commit
  SHA on jsDelivr with SRI (`hub/src/config.json` -> `shell`).
- The other pages (rooms, about, topics, legal, 404) are static and declared in
  `site.json` `shell.noShell` (see `shell/README.md`): the v1.2.6 shell is an app shell
  and needs the app DOM, so it is not loaded on them. They only load files listed in
  `shell.keep`.
- Every page has the strict meta CSP as the first element of `<head>`:
  `script-src 'self' <pin folder>/; object-src 'none'; base-uri 'none'; font-src 'self'` (fonts are self-hosted under assets/fonts, OFL 1.1).
  `hub/firebase.json` sends the same policy as a header plus `frame-ancestors 'none'`,
  and `X-Robots-Tag: noindex, nofollow`.
- Check: `python3 tools/shell_drift.py hub/site --csp-legacy <file> --strict`.

## Data

`hub/src/build_highlights.py` refreshes `hub/src/data/` (highlights, rooms, rail) from
the public read-only room data; then re-render. It writes nothing else.

## Preview deploy (never live)

    cd hub && firebase hosting:channel:deploy hub-shell --expires 7d --project subx-skins

The preview banner and `noindex,nofollow` stay on every page; topics are not seeded.
