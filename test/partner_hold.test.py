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

hub_css = read(os.path.join(ROOT, 'hub', 'src', 'templates', 'hub.css'))
m = re.search(r'html\[data-hub-theme="dark"\] \.partner-disclosure \{ color: (#[0-9A-Fa-f]{6}); \}', hub_css)
ok(m is not None and ratio(m.group(1), '#000000') >= 4.5, 'dark partner-disclosure on #000 is at least 4.5:1 (%s)' % (None if not m else round(ratio(m.group(1), '#000000'), 2)))
block = re.search(r'html\[data-hub-theme="dark"\] body\.partner-room-home \.sponsored-label,.*?\{([^}]+)\}', hub_css, re.S)
color = re.search(r'color:\s*(#[0-9A-Fa-f]{6})', block.group(1)) if block else None
ok(color is not None and ratio(color.group(1), '#000000') >= 4.5, 'dark Sponsored label on #000 is at least 4.5:1')
usa = read(os.path.join(ROOT, 'hub', 'src', 'templates', 'partner-room.css'))
chip = re.search(r'html\[data-hub-theme="dark"\] \.partner-chip \{([^}]+)\}', usa, re.S)
if not chip:
    chip = re.search(r'html\[data-hub-theme="dark"\] \.partner-disclosure,\s*html\[data-hub-theme="dark"\] \.partner-chip \{([^}]+)\}', usa, re.S)
fg = re.search(r'color:\s*(#[0-9A-Fa-f]{6})', chip.group(1)) if chip else None
bg = re.search(r'background:\s*(#[0-9A-Fa-f]{6})', chip.group(1)) if chip else None
ok(fg and bg and ratio(fg.group(1), bg.group(1)) >= 4.5, 'dark partner Sponsored chip contrast is at least 4.5:1')

print('\n%d failure(s)' % len(fails))
raise SystemExit(1 if fails else 0)
