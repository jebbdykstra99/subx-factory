# hub/ — the brand hub

The hub is rendered from `brand/brand.json` + `hub/src/` into `hub/site/` (committed, so a
deploy needs no build step). Every name, domain, tagline, noun, contact line and the footer
comes from `brand/brand.json`; templates hold `{{brand.*}}` tokens only.

## Render

    python3 tools/brand_render.py           # write hub/site/
    python3 tools/brand_render.py --check   # CI: hub/site/ matches a fresh render
    python3 test/hub_brand.test.py          # CI: pages, CSP, rename test, shell_drift

The rename test renders the hub with a dummy brand and fails if any brand literal is
left outside `brand/brand.json` (allowed: the Firebase project/site ids).

## Logo

The hub mark is the lower-nose SubX cat. `brand/brand.json` `logo.mask` is the one mask master (`brand/assets/cat-mask.png`). The header paints that file as a CSS mask (`mask-image`, `mask-size: cover`, `mask-position: center`) filled with `background-color`. There is no per-page path and no offset for this drawing.

Light color is `logo.color` (`#000000`), written to `--subx-cat-color`. Dark color is `logo.colorDark` (`#e7e9ea`), written to `--subx-cat-color-dark`. `#e7e9ea` is the hub dark theme primary text color (`--text` and `--nav-text` in `styles.css`). It is near white, so the cat matches that text on the black background. For pure white, set `logo.colorDark` to `#ffffff`.

To change a color: edit that one field in `brand/brand.json` and run `python3 tools/brand_render.py`.

Square sizes sit next to the mask and are copied, not redrawn: `cat-16.png`, `cat-24.png`, `cat-32.png`, `cat-48.png`, `cat-128.png`, `cat-256.png`. Their public paths are `logo.icon16` through `logo.icon256`. Favicons use 16, 24, 32, and 48. The apple touch icon is the 256 square, because this set has no 180. A browser tab does not follow the hub theme, so the favicon stays the black raster.

To swap the drawing: replace `logo.mask` and those size files in the same folder, keep the paths, and re-render. Do not add a CSS offset. `cover` plus `center` shows this wide master without letterboxing its empty side margins, and a square file dropped at the same path is shown whole.

## Shell and CSP

- `index.html` runs the shared shell `shell/v1.2.6/factory.js`, self-hosted at
  `/shell/v1.2.6/factory.js` as a hub-only fork (`hub/src/config.json` -> `shell`). The render first
  verifies the pinned file against `config.json` integrity and `shell/v1.2.6/SHELL.json`, then replaces
  only the header comment line that names the source repo with
  ` * Source: SubX shared shell v1.2.6 (hub fork, header only)`, and loads the result with its own new
  SRI. Every other byte is identical. `site.json` declares it (`shell.fork`, EXCEPTIONS.md E21), so
  shell_drift reports `FORK` with 2 diff lines (one line out, one in).
- Sign in (2026-11-04): `site.json` `accountsOpen` is `true`. The shell's own sign-in (left nav / mobile drawer
  `#sidebar-auth`, and the header Sign in / Join button, which only clicks it) signs in the same account the
  rooms use (Firebase project `subx-skins`, `siteId` `subx`). The hub still takes no posts. `index.html` loads the
  Firebase compat SDK (`shell.firebaseVersion`, pinned with SRI) and carries `CSP_AUTH` (`tools/brand_render.py`).
- The other pages (rooms, about, topics, legal, 404) are static and declared in
  `site.json` `shell.noShell` (see `shell/README.md`): the v1.2.6 shell is an app shell
  and needs the app DOM, so it is not loaded on them. They only load files listed in
  `shell.keep`.
- Every static page has the strict meta CSP as the first element of `<head>`:
  `script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; font-src 'self'` (fonts are self-hosted under assets/fonts, OFL 1.1).
  `index.html` has `CSP_AUTH` there instead: the strict policy plus exactly the Firebase Auth, App Check
  (reCAPTCHA v3), Firestore and Google sign-in sources (pinned in `test/hub_brand.test.py`).
  `hub/firebase.json` sends `CSP_AUTH` as a header plus `frame-ancestors 'none'` (browsers enforce header and meta
  together, so static pages stay strict), and `X-Robots-Tag: noindex` on the JSON data files only.
- Rules: `rules/firestore.rules.hub-signin.proposed` (unpublished) lets `siteId` `subx` hold profiles, follows,
  blocks, mutes, follow alerts and DMs; never posts or stories. Test: `cd rules/tests && npm run test:hub`.
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
