# hub/ — the brand hub

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
  and `X-Robots-Tag: noindex` on the JSON data files only.
- Check: `python3 tools/shell_drift.py hub/site --csp-legacy <file> --strict`.

## Disclosure mark

The hub ships the final-v4.1 mark art from `hub/src/whomark/` (config, `whomark.js`, `whomark-*` SVG/PNG files;
`MD5SUMS.final-v4.1.txt` pins their bytes), vendored to `assets/whomark/`. The shared `assets/whomark/` used by rooms
is unchanged. Check: `python3 test/whomark_hub.test.py`.

## Data

`hub/src/build_highlights.py` refreshes `hub/src/data/` (highlights, rooms, rail) from
the public read-only room data; then re-render. It writes nothing else.

## Indexing (go-live 2026-11-04)

`hub/src/config.json` `topics.hubNoindex` is `false`: the hub pages (home, rooms, about, terms, privacy, guidelines,
report) render `index,follow` with a canonical `https://<brand.primaryDomain>/...` link and are listed in
`sitemap.xml`; robots.txt allows search crawling (named AI crawlers and training bots stay disallowed) and names the
sitemap. The 404 page and the topic index keep `noindex,nofollow` (their `pages` entry sets `robots`). Topic pages
keep the hide-until-active rule from `tools/topic_status.py`: only an `active` topic is indexable or in the sitemap;
hidden, eligible, quiet and archived topics stay `noindex,nofollow`. There is no preview banner.
Rollback: set `hubNoindex` to `true` and re-render (every page noindex,nofollow, empty sitemap).

## Deploy

`hub/firebase.json` deploys to the hosting target `hub`, which `hub/.firebaserc` maps to the dedicated site
`subx-hub` in project `subx-skins`. Never point the hub at the `subx-skins` site: its live channel is the SubX
Master console.

    cd hub && firebase hosting:channel:deploy golive --only hub --expires 7d --project subx-skins   # preview (Firebase adds noindex on channels)
    cd hub && firebase deploy --only hosting:hub --project subx-skins                              # production (live channel of subx-hub)

### WHOMARK spec §7 deviation

The hub is light-only, so it ships no dark (`color-dark`) or mono files, and it ships 9 of the 36 final-v4.1 SVGs (only those referenced: `whomark-{human,ai,hybrid}-{s14,s16,lg}-color.svg`) plus the referenced og/corner PNGs.
