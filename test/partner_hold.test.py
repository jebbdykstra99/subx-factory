#!/usr/bin/env python3
"""CLO hold: Millan removed, no USSA outbound href, Sponsored on related cards, one partners page, dark disclosure contrast."""
import json, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
fails = []


def ok(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        fails.append(msg)


def read(p):
    return open(p, encoding='utf-8').read()


def channel(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lum(hexcolor):
    h = hexcolor.lstrip('#')
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def ratio(fg, bg):
    a, b = lum(fg), lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


PARTNER_DIRS = [
    os.path.join(ROOT, 'hub', 'site', 'partners'),
    os.path.join(ROOT, 'hub', 'src', 'partners'),
    os.path.join(ROOT, 'rooms', 'dogacademy-partner'),
]
hits = []
for base in PARTNER_DIRS:
    for dirpath, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fn in files:
            path = os.path.join(dirpath, fn)
            try:
                text = read(path)
            except UnicodeDecodeError:
                continue
            if re.search(r'millan', text, re.I):
                hits.append(os.path.relpath(path, ROOT))
ok(not hits, 'no Millan anywhere under partners/ (%s)' % hits[:6])

href_hits = []
for base in (os.path.join(ROOT, 'hub', 'site'), os.path.join(ROOT, 'hub', 'src'), os.path.join(ROOT, 'rooms')):
    for dirpath, dirs, files in os.walk(base):
        for fn in files:
            if not fn.endswith(('.html', '.json', '.css', '.js', '.py')):
                continue
            path = os.path.join(dirpath, fn)
            text = read(path)
            if re.search(r'href="[^"]*usserviceanimals\.org', text, re.I):
                href_hits.append(os.path.relpath(path, ROOT))
ok(not href_hits, 'no href to usserviceanimals.org anywhere (%s)' % href_hits[:6])

home = read(os.path.join(ROOT, 'hub', 'site', 'partners', 'dogacademy', 'index.html'))
article = read(os.path.join(ROOT, 'hub', 'site', 'partners', 'dogacademy', 'articles', 'calm-steady-presence.html'))
da_name = json.load(open(os.path.join(ROOT, 'rooms', 'dogacademy-partner', 'site.json'), encoding='utf-8'))['displayName']
ok(('Sponsored by %s' % da_name) in home and home.count('>Sponsored<') >= 6, 'room home article cards say Sponsored by the displayName and Sponsored')
cards = re.findall(r'<a class="news-item" href="/partners/dogacademy/articles/[^"]+">.*?</a>', article)
ok(cards and all('>Sponsored<' in c for c in cards), 'each related-article card on an article page has a Sponsored label (%d)' % len(cards))

src_pages = []
for dirpath, dirs, files in os.walk(os.path.join(ROOT, 'hub', 'src')):
    for fn in files:
        if fn == 'partners.html':
            src_pages.append(os.path.join(dirpath, fn))
ok(len(src_pages) == 1, 'one partners.html source (%s)' % src_pages)
sentence = 'Partner staff must identify their affiliation. Fake reviews are prohibited.'
src = read(src_pages[0])
site = read(os.path.join(ROOT, 'hub', 'site', 'partners.html'))
ok(src.count(sentence) == 1 and site.count(sentence) == 1, 'the partners page uses the CLO sentence once')
ok('Fees are flat' not in src and 'Fees are flat' not in site, 'the fee sentence is gone')
ok('Member data is never shared with a brand.' not in site, 'the replaced member-data sentence is gone')

styles = read(os.path.join(ROOT, 'hub', 'src', 'templates', 'styles.css'))
hub_css = read(os.path.join(ROOT, 'hub', 'src', 'templates', 'hub.css'))
room_css = read(os.path.join(ROOT, 'hub', 'src', 'templates', 'partner-room.css'))


def token_block(css, selector):
    m = re.search(re.escape(selector) + r'\s*\{([^}]+)\}', css)
    return m.group(1) if m else ''


def token(block, name):
    m = re.search(r'%s:\s*(#[0-9A-Fa-f]{6})' % name, block)
    return m.group(1) if m else ''


light = token_block(styles, ':root')
dark = token_block(styles, 'html[data-hub-theme="dark"]')
pairs = (
    ('light text on page', token(light, '--text'), token(light, '--bg')),
    ('light text on widget', token(light, '--text'), token(light, '--widget')),
    ('dark text on page', token(dark, '--text'), token(dark, '--bg')),
    ('dark text on widget', token(dark, '--text'), token(dark, '--widget')),
)
for label, fg, bg in pairs:
    ok(fg and bg and ratio(fg, bg) >= 4.5, 'hub %s contrast is at least 4.5:1 (%s on %s = %s)' % (label, fg, bg, None if not (fg and bg) else round(ratio(fg, bg), 2)))
def uses_text(css, selector):
    return re.search(re.escape(selector) + r'[^{]*\{[^}]*color:\s*var\(--text\)', css) is not None


ok(uses_text(hub_css, '.partner-disclosure'), 'partner disclosure uses the hub text token')
ok(uses_text(hub_css, '.sponsored-label'), 'Sponsored label uses the hub text token')
ok(uses_text(room_css, '.partner-disclosure'), 'partner room disclosure uses the hub text token')
ok(uses_text(room_css, '.partner-chip'), 'partner room Sponsored chip uses the hub text token')
ok('@media (prefers-color-scheme' not in styles and '@media (prefers-color-scheme' not in hub_css and '@media (prefers-color-scheme' not in room_css,
   'partner theme does not add a prefers-color-scheme rule the hub home does not use')
page_bg = []
for rel in ('hub/src/templates/partner-room.css',):
    if re.search(r'background\s*:\s*#000(?:000)?\b', read(os.path.join(ROOT, rel))):
        page_bg.append(rel)
home_rules = hub_css.split('body.partner-room-home')[1]
if re.search(r'background\s*:\s*#000(?:000)?\b', home_rules):
    page_bg.append('hub.css partner-room-home')
for rel in ('hub/site/partners/dogacademy/index.html', 'hub/site/partners/usserviceanimals/index.html', 'hub/site/partners.html'):
    html = read(os.path.join(ROOT, rel))
    ok('/theme.js' in html and '/styles.css' in html and '/hub.css' in html, '%s loads the shared hub theme' % rel)
    if re.search(r'background\s*:\s*#000(?:000)?\b', html):
        page_bg.append(rel)
ok(not page_bg, 'partner pages have no hardcoded #000 page background (%s)' % page_bg)

print('\n%d failure(s)' % len(fails))
raise SystemExit(1 if fails else 0)
