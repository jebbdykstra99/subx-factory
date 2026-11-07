#!/usr/bin/env python3
"""Hub cat mark: one mask file plus the square sizes named in brand.json.

tools/brand_render.py copies those PNGs into hub/site. It does not redraw them.
Replace the files at the configured paths and re-render. No CSS offset.
"""
import os, re, struct

class LogoError(Exception):
    pass

HEX = re.compile(r'^#[0-9A-Fa-f]{6}$')
MASK_REL = re.compile(r'^brand/assets/[a-z0-9.-]+\.png$')
HREF = re.compile(r'^/assets/brand/[a-z0-9.-]+\.png$')
ICON_KEY = re.compile(r'^icon([1-9][0-9]|[1-9][0-9]{2}|1024)$')
KNOWN = ('mask', 'color', 'colorDark', 'publicMask')
OPTIONAL = ('ogBackground', 'ogImage')


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
