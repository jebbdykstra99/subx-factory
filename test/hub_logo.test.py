#!/usr/bin/env python3
"""Hub cat mark: color comes from brand.json, and the files are the approved lower-nose rasters.

The mask master and the square sizes are copied, not redrawn. A color change is a brand.json edit.
Offline. Temp dirs only.
"""
import hashlib, json, os, re, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import brand_render as BR  # noqa: E402
import logo_mask  # noqa: E402

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

idx = read(os.path.join(SITE, 'index.html'))
ok('alt="SubX"' in idx and 'class="brand-icon"' in idx, 'header logo alt text is SubX')
ok('favicon.svg' not in idx and 'icon32' not in idx, 'home no longer links the old svg favicon')
for key in ('icon16', 'icon24', 'icon32', 'icon48', 'icon128', 'icon256'):
    ok(logo[key] + '?v=' in idx, 'home links %s from brand.json' % key)
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

# New prose has no em or en dash. The README title line is older and is left as it is.
logo_doc = read(os.path.join(ROOT, 'hub', 'README.md')).split('## Logo\n', 1)[1]
ok('## Logo' in read(os.path.join(ROOT, 'hub', 'README.md')) and not re.search(r'[\u2013\u2014]', logo_doc),
   'Logo section has no em or en dash')
for rel in ('tools/logo_mask.py', 'tools/og_card.py', 'test/hub_logo.test.py', 'hub/src/templates/styles.css',
            'hub/src/partials/head.html', 'hub/src/templates/index.html', 'tools/brand_render.py'):
    ok(not re.search(r'[\u2013\u2014]', read(os.path.join(ROOT, rel))), '%s has no em or en dash' % rel)

print('\n%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)
