#!/usr/bin/env python3
"""Hub cat mark: color comes from brand.json, and the files are the approved lower-nose rasters.

The mask master and the square sizes are copied, not redrawn. A color change is a brand.json edit.
Offline. Temp dirs only.
"""
import base64, hashlib, json, os, re, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import brand_render as BR  # noqa: E402
import logo_mask  # noqa: E402
import og_card  # noqa: E402

BRAND = os.path.join(ROOT, 'brand', 'brand.json')
SITE = os.path.join(ROOT, 'hub', 'site')
fails = []

# Approved lower-nose proposed-black files. Not the earlier seven-colour export.
EXPECT = {
    'brand/assets/cat-mask.png': '45acca35be1357ea672f34fed35994e20446d6b62deb3de32444ca559a4ac661',
    'brand/assets/cat-16.png': '81a2abfdde74be24ddc449d00021f41bf4c4bffb39c2a89cd34b7cb029a86762',
    'brand/assets/cat-24.png': 'c8cc77a5e517bcb9e7bd9ee5e90a4928d1b01281810267de5d461c977714581c',
    'brand/assets/cat-32.png': '1105a6aa15b1f7f593d6a6ba97017b1ddfcadcd2ab5ade0e484dff40080f1ba2',
    'brand/assets/cat-48.png': '2e7a6ea55aa8aff2c5164c4b18dca1f9c30cc69e23ee6ee3c5208263cc0583ef',
    'brand/assets/cat-128.png': '3dd8be7994ccfd961e082af8309b376cb606ab933a78608864d2a4c37cd8e0b5',
    'brand/assets/cat-256.png': 'f4b692783efc10a35f41f67d4c46ac7ea50b0a3b8eac252df90ab26d35624c64',
}


def ok(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        fails.append(msg)


def read(p):
    return open(p, encoding='utf-8').read()


brand = json.load(open(BRAND, encoding='utf-8'))
logo = brand['logo']
ok(logo['color'] == '#000000' and logo['colorDark'] == '#ffffff',
   'logo.color is #000000 and logo.colorDark is #ffffff')
ok(logo['mask'] == 'brand/assets/cat-mask.png' and logo['publicMask'] == '/assets/brand/cat-mask.png',
   'one mask path in brand.json')
ok(list(logo) == ['mask', 'color', 'colorDark', 'publicMask', 'icon16', 'icon24', 'icon32', 'icon48', 'icon128', 'icon256', 'ogBackground', 'ogImage'],
   'logo keys are the mask, two colors, the size paths, and the share image')

names = sorted(os.listdir(os.path.join(ROOT, 'brand', 'assets')))
ok(names == sorted(os.path.basename(p) for p in EXPECT), 'brand/assets holds only the mask and the six sizes (%s)' % names)
ok(not any(n.startswith(('current-', 'proposed-')) or 'white' in n for n in names),
   'brand/assets has no current-* or white raster')

for rel, digest in EXPECT.items():
    data = open(os.path.join(ROOT, rel), 'rb').read()
    ok(hashlib.sha256(data).hexdigest() == digest, '%s is the approved lower-nose file' % rel)

pairs = logo_mask.plan(brand)
ok(pairs[0][0] == logo['mask'] and pairs[0][2] is None, 'plan copies the mask master first, with no forced square size')
ok([px for _, _, px in pairs if px] == [16, 24, 32, 48, 128, 256], 'plan lists the configured square sizes')

for rel, href, px in pairs:
    repo = open(os.path.join(ROOT, rel), 'rb').read()
    site = open(os.path.join(SITE, href.lstrip('/')), 'rb').read()
    w, h = logo_mask.png_wh(repo)
    ok(repo == site, '%s is a byte copy of %s' % (href, rel))
    if px is None:
        ok((w, h) == (1168, 784), 'mask master is the 1168x784 source, not the old 512 square')
    else:
        ok((w, h) == (px, px), '%s is %dx%d' % (rel, px, px))

css = read(os.path.join(SITE, 'styles.css'))
ok('--subx-cat-color: #000000;' in css and '--subx-cat-color-dark: #ffffff;' in css,
   'rendered CSS variables are the brand.json colors')
block = css.split('.brand-icon {', 1)[1].split('}', 1)[0]
ok('var(--subx-cat-color)' in block and 'mask-size: cover' in block and 'mask-position: center' in block,
   'the mark is a mask filled from --subx-cat-color, cover and center only')
ok('var(--subx-cat-color-dark)' in css.split('html[data-hub-theme="dark"] .brand-icon {', 1)[1].split('}', 1)[0],
   'dark mode fills the same mask from --subx-cat-color-dark')
ok('object-position' not in block and 'translate' not in block and 'drop-shadow' not in block
   and not re.search(r'mask-position:\s*[0-9]', block) and 'outline' not in block,
   'no drawing offset, outline, or drop shadow on the mark')
ok(logo['publicMask'] + '?v=' in block, 'the mask URL is the configured public path')

def rgba_of(data):
    w, h, mode, rgba = og_card.decode_png(data)
    return w, h, mode, rgba


def alpha_of(rgba):
    return bytes(rgba[i + 3] for i in range(0, len(rgba), 4))


idx = read(os.path.join(SITE, 'index.html'))
ok('alt="SubX"' in idx and 'class="brand-icon"' in idx, 'header logo alt text is SubX')
ok('href="/favicon.svg' not in idx and 'href="favicon.svg' not in idx and 'icon32' not in idx,
   'home does not link the old root favicon.svg')
icons = re.findall(r'<link rel="(?:icon|apple-touch-icon)"[^>]*>', idx)
ok(icons and icons[0].startswith('<link rel="icon" type="image/svg+xml"')
   and '/assets/brand/cat-favicon.svg?v=' in icons[0] and 'media=' not in icons[0],
   'the svg icon link is first and has no media attribute')
for key in ('icon16', 'icon24', 'icon32', 'icon48', 'icon128', 'icon256'):
    ok(logo[key] + '?v=' in idx, 'home links %s from brand.json' % key)
for px in logo_mask.FAVICON_PX:
    light = '/assets/brand/cat-%d.png?v=' % px
    dark_name = '/assets/brand/cat-%d-dark.png' % px
    ok(light in idx, 'home links the black %d favicon' % px)
    dark_links = [t for t in icons if dark_name in t]
    ok(len(dark_links) == 1 and 'media="(prefers-color-scheme: dark)"' in dark_links[0]
       and 'sizes="%dx%d"' % (px, px) in dark_links[0] and 'type="image/png"' in dark_links[0],
       'home links the dark-tab %d favicon with a dark media query' % px)
    src = open(os.path.join(ROOT, 'brand', 'assets', 'cat-%d.png' % px), 'rb').read()
    dark = open(os.path.join(SITE, dark_name.lstrip('/')), 'rb').read()
    sw, sh, smode, srgba = rgba_of(src)
    dw, dh, dmode, drgba = rgba_of(dark)
    ok((sw, sh) == (dw, dh) == (px, px) and smode == dmode == 'RGBA' and alpha_of(srgba) == alpha_of(drgba),
       'cat-%d-dark.png keeps the approved size and alpha' % px)
    ok(all(drgba[i:i + 3] == b'\xff\xff\xff' for i in range(0, len(drgba), 4)),
       'cat-%d-dark.png RGB is logo.colorDark' % px)
    ok(dark != src, 'cat-%d-dark.png is not a copy of the black file' % px)
ok(not os.path.isfile(os.path.join(SITE, 'assets', 'brand', 'cat-256-dark.png')),
   'no dark apple-touch raster is written')
apple = [t for t in icons if 'apple-touch-icon' in t]
ok(len(apple) == 1 and 'cat-256.png?v=' in apple[0] and 'media=' not in apple[0] and 'cat-256-dark' not in idx,
   'apple touch icon stays the black 256 with no media query')
svg = read(os.path.join(SITE, 'assets', 'brand', 'cat-favicon.svg'))
b48 = open(os.path.join(ROOT, 'brand', 'assets', 'cat-48.png'), 'rb').read()
d48 = open(os.path.join(SITE, 'assets', 'brand', 'cat-48-dark.png'), 'rb').read()
ok('prefers-color-scheme: dark' in svg and 'color-scheme: light dark' in svg
   and '.cat-light' in svg and '.cat-dark' in svg,
   'svg switches the embedded cats with prefers-color-scheme')
ok(base64.b64encode(b48).decode('ascii') in svg and base64.b64encode(d48).decode('ascii') in svg,
   'svg embeds the approved 48px black png and the painted dark png')
ok('#ffffff' not in svg and '#000000' not in svg and 'SubX' not in svg,
   'svg does not hardcode the cat colors or the brand name')
ok(logo_mask.SVG_EMBED_PX == 48 and 'width="48"' in svg and 'height="48"' in svg,
   'svg embed is the 48px square, the closest approved size to 64')
mask_src = open(os.path.join(ROOT, 'brand', 'assets', 'cat-mask.png'), 'rb').read()
_mw, _mh, _mm, mask_rgba = rgba_of(mask_src)
ok(_mm == 'RGBA' and alpha_of(mask_rgba), 'mask master alpha is the approved RGBA file')
page_miss = []
for base, _, names_ in os.walk(SITE):
    for name in names_:
        if not name.endswith('.html'):
            continue
        text = read(os.path.join(base, name))
        rel = os.path.relpath(os.path.join(base, name), SITE)
        if '/assets/brand/cat-favicon.svg?v=' not in text or 'media="(prefers-color-scheme: dark)"' not in text:
            page_miss.append(rel)
        if 'cat-256-dark' in text:
            page_miss.append(rel + ':dark256')
ok(not page_miss, 'every rendered page links the svg and a dark-tab png (%s)' % page_miss[:4])
py_src = read(os.path.join(ROOT, 'tools', 'logo_mask.py'))
ok('#ffffff' not in py_src and '#000000' not in py_src, 'logo_mask.py does not hardcode the cat colors')
ok("logo['colorDark']" in read(os.path.join(ROOT, 'tools', 'brand_render.py')),
   'the renderer reads the dark favicon color from brand.json')
desc = re.search(r'<meta name="description" content="([^"]*)">', idx)
ok(desc is not None and desc.group(1).strip() != '', 'index.html has a meta description')
og = re.search(r'<meta property="og:image" content="([^"]+)">', idx)
ok(og is not None and og.group(1) == 'https://%s%s' % (brand['primaryDomain'], logo['ogImage']),
   'index.html og:image is the absolute share image (%s)' % (og.group(1) if og else None))
ok('<meta name="twitter:card" content="summary_large_image">' in idx, 'index.html twitter:card is summary_large_image')
og_path = logo['ogImage'].lstrip('/')
og_file = os.path.join(SITE, og_path)
ok(os.path.isfile(og_file), 'og image file exists')
og_bytes = open(og_file, 'rb').read()
ok(logo_mask.png_wh(og_bytes) == (1200, 630), 'og image is 1200x630')
ok(len(og_bytes) <= 300 * 1024, 'og image is under 300KB (%d)' % len(og_bytes))
# partner pages keep their own og:title and stay noindex; the share image is added
part = read(os.path.join(SITE, 'partners.html'))
ok(part.count('property="og:title"') == 1 and 'Why am I seeing this?' in part, 'partners.html keeps one og:title')
ok('<meta name="robots" content="noindex,nofollow">' in part and 'property="og:image"' in part,
   'partners.html stays noindex and gains og:image')
room = read(os.path.join(SITE, 'partners/usserviceanimals/index.html'))
ok(room.count('property="og:title"') == 1 and '<meta name="robots" content="noindex,nofollow">' in room,
   'partner room keeps one og:title and stays noindex')
ok('property="og:image"' in room, 'partner room gains og:image')

# A color edit in brand.json is the only change the CSS needs.
dummy = json.loads(json.dumps(brand))
dummy['logo']['color'] = '#123456'
dummy['logo']['colorDark'] = '#abcdef'
with tempfile.TemporaryDirectory() as t:
    bp = os.path.join(t, 'brand.json')
    json.dump(dummy, open(bp, 'w', encoding='utf-8'))
    out = os.path.join(t, 'site')
    BR.render(brand=bp, out=out)
    css2 = read(os.path.join(out, 'styles.css'))
    ok('--subx-cat-color: #123456;' in css2 and '--subx-cat-color-dark: #abcdef;' in css2,
       'a brand.json color edit changes the rendered variables')
    ok('--subx-cat-color: #000000;' not in css2 and '--subx-cat-color-dark: #ffffff;' not in css2,
       'the previous cat colors are not left hardcoded')
    copied = open(os.path.join(out, 'assets', 'brand', 'cat-mask.png'), 'rb').read()
    ok(copied == open(os.path.join(ROOT, logo['mask']), 'rb').read(),
       'a color edit does not rewrite the mask file')
    black48 = open(os.path.join(out, 'assets', 'brand', 'cat-48.png'), 'rb').read()
    ok(black48 == b48, 'a color edit does not rewrite the approved black favicon')
    painted = open(os.path.join(out, 'assets', 'brand', 'cat-48-dark.png'), 'rb').read()
    pw, ph, pmode, prgba = rgba_of(painted)
    ok((pw, ph) == (48, 48) and pmode == 'RGBA' and alpha_of(prgba) == alpha_of(rgba_of(b48)[3])
       and all(prgba[i:i + 3] == bytes.fromhex('abcdef') for i in range(0, len(prgba), 4)),
       'a colorDark edit repaints the dark favicon and keeps the approved alpha')
    svg2 = read(os.path.join(out, 'assets', 'brand', 'cat-favicon.svg'))
    ok(base64.b64encode(b48).decode('ascii') in svg2 and base64.b64encode(painted).decode('ascii') in svg2,
       'the svg embed follows the colorDark edit and still uses the approved black png')
    ok(base64.b64encode(d48).decode('ascii') not in svg2, 'the previous white embed is not left in the svg')
    idx2 = read(os.path.join(out, 'index.html'))
    ok('/assets/brand/cat-favicon.svg?v=' in idx2 and 'cat-48-dark.png?v=' in idx2
       and 'media="(prefers-color-scheme: dark)"' in idx2,
       'a color edit still emits the svg link and the dark-tab png links')

# New prose has no em or en dash. The README title line is older and is left as it is.
logo_doc = read(os.path.join(ROOT, 'hub', 'README.md')).split('## Logo\n', 1)[1]
ok('## Logo' in read(os.path.join(ROOT, 'hub', 'README.md')) and not re.search(r'[\u2013\u2014]', logo_doc),
   'Logo section has no em or en dash')
for rel in ('tools/logo_mask.py', 'tools/og_card.py', 'test/hub_logo.test.py', 'hub/src/templates/styles.css',
            'hub/src/partials/head.html', 'hub/src/templates/index.html', 'tools/brand_render.py'):
    ok(not re.search(r'[\u2013\u2014]', read(os.path.join(ROOT, rel))), '%s has no em or en dash' % rel)

print('\n%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)
