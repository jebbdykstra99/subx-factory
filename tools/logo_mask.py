#!/usr/bin/env python3
"""Hub cat mark: one mask file plus the square sizes named in brand.json.

tools/brand_render.py copies those PNGs into hub/site. It does not redraw them.
Replace the files at the configured paths and re-render. No CSS offset.

Dark-tab favicon PNGs are not source files. The renderer paints them from the
alpha already in the square PNGs and from logo.colorDark. The SVG favicon
embeds the 48px pair and switches on prefers-color-scheme.
"""
import base64, os, re, struct, zlib

class LogoError(Exception):
    pass

HEX = re.compile(r'^#[0-9A-Fa-f]{6}$')
MASK_REL = re.compile(r'^brand/assets/[a-z0-9.-]+\.png$')
HREF = re.compile(r'^/assets/brand/[a-z0-9.-]+\.png$')
ICON_KEY = re.compile(r'^icon([1-9][0-9]|[1-9][0-9]{2}|1024)$')
KNOWN = ('mask', 'color', 'colorDark', 'publicMask')
OPTIONAL = ('ogBackground', 'ogImage')
# Squares linked as rel=icon. 256 is the apple touch icon and stays the copied file.
FAVICON_PX = (16, 24, 32, 48, 128)
# Closest approved square to 64px. The SVG embeds this pair. Not a resample.
SVG_EMBED_PX = 48
FAVICON_SVG = '/assets/brand/cat-favicon.svg'


def png_wh(data):
    """Width and height from a PNG IHDR. Does not decode pixels."""
    if len(data) < 24 or data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR':
        raise LogoError('logo file is not a PNG')
    return struct.unpack('>II', data[16:24])


def plan(brand):
    """Return [(repo_rel, public_href, square_px or None)] in copy order.

    The mask master is brand.logo.mask (any PNG size). Each iconN key is a public
    path whose file sits next to the mask and must be N by N pixels.
    """
    logo = brand.get('logo') if isinstance(brand, dict) else None
    if not isinstance(logo, dict):
        raise LogoError('brand.logo must be an object')
    for key in logo:
        if key not in KNOWN and key not in OPTIONAL and not ICON_KEY.fullmatch(key):
            raise LogoError('brand.logo has unknown key %s' % key)
    if 'ogBackground' in logo and not HEX.fullmatch(str(logo['ogBackground'])):
        raise LogoError('brand.logo.ogBackground must be #RRGGBB')
    if 'ogImage' in logo and (not isinstance(logo['ogImage'], str) or not re.fullmatch(r'/[a-z0-9./-]+\.png', logo['ogImage'])):
        raise LogoError('brand.logo.ogImage must be a site png path')
    for key in KNOWN:
        if key not in logo:
            raise LogoError('brand.logo is missing %s' % key)
    if not HEX.fullmatch(str(logo['color'])) or not HEX.fullmatch(str(logo['colorDark'])):
        raise LogoError('brand.logo.color and colorDark must be #RRGGBB')
    mask = logo['mask']
    if not isinstance(mask, str) or not MASK_REL.fullmatch(mask):
        raise LogoError('brand.logo.mask must be a brand/assets/*.png path')
    pub = logo['publicMask']
    if not isinstance(pub, str) or not HREF.fullmatch(pub):
        raise LogoError('brand.logo.publicMask must be an /assets/brand/*.png path')
    folder = os.path.dirname(mask)
    out = [(mask, pub, None)]
    seen = {pub}
    icons = []
    for key, href in logo.items():
        m = ICON_KEY.fullmatch(key)
        if not m:
            continue
        px = int(m.group(1))
        if not isinstance(href, str) or not HREF.fullmatch(href):
            raise LogoError('brand.logo.%s must be an /assets/brand/*.png path' % key)
        if href in seen:
            raise LogoError('brand.logo.%s repeats a public path' % key)
        seen.add(href)
        rel = folder + '/' + os.path.basename(href)
        if not MASK_REL.fullmatch(rel):
            raise LogoError('brand.logo.%s file is not under brand/assets' % key)
        icons.append((rel, href, px))
    if not icons:
        raise LogoError('brand.logo needs icon sizes')
    icons.sort(key=lambda row: row[2])
    return out + icons


def _chunk(tag, payload):
    return struct.pack('>I', len(payload)) + tag + payload + struct.pack('>I', zlib.crc32(tag + payload) & 0xffffffff)


def encode_rgba(w, h, rgba):
    """RGBA bytes to a PNG. Filter None, zlib level 9. Straight alpha, not premultiplied."""
    if len(rgba) != w * h * 4:
        raise LogoError('rgba buffer has the wrong length')
    raw = bytearray()
    stride = w * 4
    for y in range(h):
        raw.append(0)
        raw += rgba[y * stride:(y + 1) * stride]
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)
    return b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', ihdr) + _chunk(b'IDAT', zlib.compress(bytes(raw), 9)) + _chunk(b'IEND', b'')


def dark_href(href):
    """Public path of the dark-tab twin. /assets/brand/cat-16.png -> cat-16-dark.png."""
    if not isinstance(href, str) or not href.endswith('.png') or not HREF.fullmatch(href):
        raise LogoError('dark favicon href must be an /assets/brand/*.png path')
    out = href[:-4] + '-dark.png'
    if out == href or not HREF.fullmatch(out):
        raise LogoError('dark favicon href is not an /assets/brand/*.png path')
    return out


def paint(data, color):
    """Same width, height, and alpha bytes. RGB becomes color. No resample."""
    if not HEX.fullmatch(str(color)):
        raise LogoError('paint color must be #RRGGBB')
    import og_card
    w, h, mode, rgba = og_card.decode_png(data)
    if mode != 'RGBA':
        raise LogoError('logo png must be RGBA')
    r = int(color[1:3], 16)
    g = int(color[3:5], 16)
    b = int(color[5:7], 16)
    out = bytearray(len(rgba))
    for i in range(0, len(rgba), 4):
        out[i] = r
        out[i + 1] = g
        out[i + 2] = b
        out[i + 3] = rgba[i + 3]
    return encode_rgba(w, h, bytes(out))


def favicon_svg(light_png, dark_png, px):
    """SVG icon. Embeds the approved light PNG and the painted dark PNG at px."""
    if png_wh(light_png) != (px, px) or png_wh(dark_png) != (px, px):
        raise LogoError('favicon svg embed must be %dx%d' % (px, px))
    light = base64.b64encode(light_png).decode('ascii')
    dark = base64.b64encode(dark_png).decode('ascii')
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">\n'
        '<style>\n'
        ':root { color-scheme: light dark; }\n'
        '.cat-dark { display: none; }\n'
        '@media (prefers-color-scheme: dark) {\n'
        '  .cat-light { display: none; }\n'
        '  .cat-dark { display: block; }\n'
        '}\n'
        '</style>\n'
        '<image class="cat-light" width="%d" height="%d" href="data:image/png;base64,%s"/>\n'
        '<image class="cat-dark" width="%d" height="%d" href="data:image/png;base64,%s"/>\n'
        '</svg>\n'
    ) % (px, px, px, px, px, px, light, px, px, dark)
