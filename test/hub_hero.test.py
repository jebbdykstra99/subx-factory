#!/usr/bin/env python3
"""Rotating hero photo (heroImages), static checks for the hub and the factory-hero.js add-on.

Covers: the gpchat photo set in hub/src/rooms.json (9 unflagged photos only, every item fully credited, allowed
licenses only, self-hosted files present and within the weight budget), no room borrowing another room's photos,
the shared hx-core block identical in factory/factory-hero.js and both hub.js copies, the hub CSS block identical
in both index.html copies, z-index 1 or below inside an isolated hero, the fallback (no figure and no class without
photos), the FACTORY_RELEASE.json entry, core factory.js untouched, and no em or en dashes or private contacts.
Python stdlib only."""
import hashlib
import json
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
fails = []


def ok(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        fails.append(msg)


def read(*p):
    with open(os.path.join(ROOT, *p), encoding='utf-8') as f:
        return f.read()


def block(text, start, end):
    i = text.find(start)
    j = text.find(end, i + 1)
    return text[i:j + len(end)] if i >= 0 and j > i else ''


def img_size(path):
    with open(path, 'rb') as f:
        b = f.read()
    if b[:4] == b'RIFF' and b[8:12] == b'WEBP':
        kind = b[12:16]
        if kind == b'VP8 ':
            w, h = struct.unpack('<HH', b[26:30])
            return w & 0x3fff, h & 0x3fff
        if kind == b'VP8L':
            bits = struct.unpack('<I', b[21:25])[0]
            return (bits & 0x3fff) + 1, ((bits >> 14) & 0x3fff) + 1
        if kind == b'VP8X':
            return 1 + int.from_bytes(b[24:27], 'little'), 1 + int.from_bytes(b[27:30], 'little')
    if b[:2] == b'\xff\xd8':
        i = 2
        while i < len(b):
            if b[i] != 0xff:
                i += 1
                continue
            m = b[i + 1]
            if m in (0xc0, 0xc1, 0xc2):
                h, w = struct.unpack('>HH', b[i + 5:i + 9])
                return w, h
            i += 2 + struct.unpack('>H', b[i + 2:i + 4])[0]
    return None


REQ = ('src', 'alt', 'credit', 'license', 'licenseUrl', 'sourceUrl')
LIC = re.compile(r'^(CC0( 1\.0)?|Public Domain( Mark)?( 1\.0)?|PDM( 1\.0)?|CC BY(-SA)?( [0-9]\.[0-9])?( [a-z]{2})?)$', re.I)
HELD = ('gp05-', 'gp11-', 'gp12-')  # Jagermeister livery and identifiable faces: out until Portia clears them
DASH = re.compile('[\u2013\u2014]')
EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}')
PHONE = re.compile(r'\b[0-9]{3}[-. ][0-9]{3}[-. ][0-9]{4}\b')

src_rooms = json.loads(read('hub', 'src', 'rooms.json'))
by_room = {r['room']: r for r in src_rooms['rooms']}
gp = by_room.get('gpchat', {}).get('heroImages')
ok(isinstance(gp, dict) and isinstance(gp.get('items'), list), 'hub/src/rooms.json: gpchat has a heroImages block')
items = (gp or {}).get('items', [])
ok(len(items) == 9, 'gpchat heroImages: exactly the 9 unflagged photos (%d)' % len(items))
ok((gp or {}).get('interval') == 7000, 'gpchat heroImages: 7 second interval')
ok(not any(h in json.dumps(gp) for h in HELD), 'gpchat heroImages: photos 5, 11 and 12 stay out pending Portia')
for n, it in enumerate(items):
    tag = 'gpchat item %d' % (n + 1)
    ok(all(isinstance(it.get(k), str) and it[k].strip() for k in REQ), tag + ': src, alt, credit, license, licenseUrl, sourceUrl all set')
    ok(bool(LIC.match(it.get('license', ''))) and not re.search(r'\b(NC|ND)\b', it.get('license', '')), tag + ': allowed license (%s)' % it.get('license'))
    ok(it.get('licenseUrl', '').startswith('https://creativecommons.org/'), tag + ': license links to creativecommons.org')
    ok(it.get('sourceUrl', '').startswith('https://commons.wikimedia.org/wiki/File:'), tag + ': credit links to the Commons file page')
    ok(len(it.get('alt', '')) >= 40, tag + ': real alt text')
    ok(re.match(r'^[0-9]{1,3}% [0-9]{1,3}%$', it.get('focal', '')) is not None, tag + ': focal point set')
    ok(it.get('w') == 1200 and it.get('h') == 800, tag + ': width and height set (1200x800)')
    for key, size, budget in (('src', (1200, 800), 100 * 1024), ('srcSm', (600, 400), 35 * 1024), ('fallback', (1200, 800), 170 * 1024)):
        u = it.get(key, '')
        ok(u.startswith('/assets/hero/gpchat/') and '..' not in u, tag + ': %s is self-hosted under /assets/hero/gpchat/' % key)
        f = os.path.join(ROOT, 'hub', 'site', u.lstrip('/'))
        ok(os.path.isfile(f), tag + ': %s exists in hub/site' % key)
        if os.path.isfile(f):
            ok(img_size(f) == size, tag + ': %s is %dx%d' % (key, size[0], size[1]))
            ok(os.path.getsize(f) <= budget, tag + ': %s within %d KB' % (key, budget // 1024))
        if key == 'src':
            jpg = u.replace('-1200.webp', '-600.jpg')
            ok(os.path.isfile(os.path.join(ROOT, 'hub', 'site', jpg.lstrip('/'))), tag + ': 600px JPEG exists')
    ok(not DASH.search(json.dumps(it, ensure_ascii=False)), tag + ': no em or en dash')

hero_dir = os.path.join(ROOT, 'hub', 'site', 'assets', 'hero', 'gpchat')
files = sorted(os.listdir(hero_dir)) if os.path.isdir(hero_dir) else []
ok(len(files) == 36 and not any(f.startswith(HELD) for f in files), 'hub/site/assets/hero/gpchat: 36 files, none of the held photos')

for room, r in by_room.items():
    hi = r.get('heroImages')
    if not hi:
        continue
    srcs = [it.get(k, '') for it in hi.get('items', []) for k in ('src', 'srcSm', 'fallback') if it.get(k)]
    ok(all(s.startswith('/assets/hero/%s/' % room) for s in srcs), '%s: heroImages use only its own /assets/hero/%s/ photos' % (room, room))
ok(sorted(k for k, r in by_room.items() if r.get('heroImages')) == ['gpchat'], 'only gpchat has photos today; every other room keeps the fallback')

addon = read('factory', 'factory-hero.js')
core = block(addon, '/* hx-core:start', '/* hx-core:end */')
ok(len(core) > 2000, 'factory-hero.js carries the hx-core block')
for p in (('hub', 'src', 'templates', 'hub.js'), ('hub', 'site', 'hub.js')):
    ok(block(read(*p), '/* hx-core:start', '/* hx-core:end */') == core, '/'.join(p) + ': hx-core block is identical to factory-hero.js')
for p in (('hub', 'src', 'templates', 'hub.js'), ('hub', 'site', 'hub.js')):
    js = read(*p)
    fn = block(js, 'function paintHeroPhotos(room)', "heroEl.classList.add('hx-on');\n  }")
    ok(bool(fn), '/'.join(p) + ': paintHeroPhotos is present')
    ok("paintHeroPhotos(hero && design === 'hero-room' ? hero : null);" in js, '/'.join(p) + ': the hero paints only the featured room\'s photos')
    ok('room.heroImages' in fn and not re.search(r'rooms?\[|findRoom|list\.', fn), '/'.join(p) + ': photos come only from the featured room entry, never another room')
    ok("heroEl.classList.remove('hx-on')" in fn and 'removeChild(old)' in fn, '/'.join(p) + ': no photos means no figure and no class')
ok(block(read('hub', 'src', 'templates', 'hub.js'), 'function paintHeroPhotos(room)', "heroEl.classList.add('hx-on');\n  }") ==
   block(read('hub', 'site', 'hub.js'), 'function paintHeroPhotos(room)', "heroEl.classList.add('hx-on');\n  }"), 'paintHeroPhotos is the same in the template and the built hub.js')

css_t = block(read('hub', 'src', 'templates', 'index.html'), '/* Rotating hero photo', '\n  </style>')
css_s = block(read('hub', 'site', 'index.html'), '/* Rotating hero photo', '\n  </style>')
ok(bool(css_t) and css_t == css_s, 'index.html: the hero photo CSS is identical in the template and the built copy')
ok('max-content minmax(240px, 1fr) 230px' in css_t and '@container hxhero (min-width: 760px)' in css_t, 'desktop A: photo card in the middle column from a 760px hero content width, Also featured keeps 230px')
ok('aspect-ratio: 16 / 6; max-height: 200px' in css_t, 'desktop A below 760px: 16:6 banner capped at 200px under the title row')
ok('aspect-ratio: 16 / 9; margin: 0 -16px 16px' in css_t, 'phone C: 16:9 photo edge to edge above the title')
ok('.hub-hero.hx-on { isolation: isolate;' in css_t, 'the hero is isolated when the photo is on')
ok(all(cls in css_t for cls in ('.hx-on', '.hx-hub')) and not re.search(r'\.hero-split\s*\{[^}]*grid-template-columns: max-content', css_t.split('.hx-on')[0]),
   'every hero photo layout rule is keyed on .hx-on or .hx-hub (fallback changes nothing)')
zs = [int(z) for z in re.findall(r'z-index:\s*(-?[0-9]+)', core + css_t + block(addon, 'var HX_CSS_ROOM', ';\n'))]
ok(zs and max(zs) <= 1, 'photo layers never go above z-index 1 (%s); the search panel (410) and scrim (400) stay on top' % zs)
for txt, name in ((core, 'hx-core'), (css_t, 'hub CSS'), (addon, 'factory-hero.js')):
    ok(not DASH.search(txt), name + ': no em or en dash in new copy')
    ok(not EMAIL.search(txt) and not PHONE.search(txt), name + ': no email address or phone number')
ok("'Photo: '" in core and "' \\u00b7 '" in core and 'font:500 11px' in core and 'rgba(0,0,0,.62)' in core and 'overflow-wrap:anywhere' in core
   and 'text-overflow' not in core and 'nowrap' not in core, 'credit: "Photo: {credit} \u00b7 {license}" at 11px in a 62% black capsule, wraps, never truncated')
ok('.hx-next,.hx-pause{width:32px;height:32px' in core, 'Pause and Next buttons are 32px')
ok("'aria-roledescription': 'carousel'" in core and "'aria-roledescription': 'slide'" in core and "'aria-live': 'polite'" in core and "'aria-hidden': 'true'" in core,
   'ARIA carousel semantics: carousel group, slide groups, polite live region, decorative dots')
ok("fetchpriority', 'low'" in core and "loading: n === 0 ? 'eager' : 'lazy'" in core, 'photo 1 eager at low priority, the rest lazy')
ok('transition:opacity 700ms' in core and 'prefers-reduced-motion' in core, '0.7 second fade, none with reduced motion')

rel = json.loads(read('FACTORY_RELEASE.json'))
hero_rel = rel.get('optIn', {}).get('factory-hero.js', {})
raw = open(os.path.join(ROOT, 'factory', 'factory-hero.js'), 'rb').read()
ok(hero_rel.get('sha256') == hashlib.sha256(raw).hexdigest() and hero_rel.get('bytes') == len(raw), 'FACTORY_RELEASE.json optIn factory-hero.js sha256 and bytes match the file')
core_js = open(os.path.join(ROOT, 'factory', 'factory.js'), 'rb').read()
ok(hashlib.sha256(core_js).hexdigest() == rel['factory.js']['sha256'] and len(core_js) == rel['factory.js']['bytes'] <= rel['coreBudgetBytes'],
   'core factory.js is unchanged (%d B, budget %d B)' % (len(core_js), rel['coreBudgetBytes']))
ok('factory-hero' not in core_js.decode('utf-8', 'replace'), 'core factory.js does not reference the add-on')

print('\n%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)
