#!/usr/bin/env python3
"""Link-preview image for the hub. Python stdlib at render time.

Colors, the cat, the name, and the tagline come from brand/brand.json.
Glyph shapes are baked masks in tools/og_font.png and tools/og_font.json.
Those files are a derived subset of Inter. See tools/og_font.NOTICE.md and
tools/OFL-Inter.txt. Rebuild the masks with: python3 tools/og_card.py --bake
brand_render calls build() and writes logo.ogImage (hub/site/og.png).
"""
import json, os, struct, zlib

WIDTH = 1200
HEIGHT = 630
HERE = os.path.dirname(os.path.abspath(__file__))
FONT_PNG = os.path.join(HERE, 'og_font.png')
FONT_JSON = os.path.join(HERE, 'og_font.json')
BOLD_PX = 92
REGULAR_PX = 36
CAT_MAX = 500
# Inter files used only by --bake. The committed masks do not need them.
BOLD_TTF = '/usr/share/fonts/truetype/macos/Inter-Bold.ttf'
REGULAR_TTF = '/usr/share/fonts/truetype/macos/Inter-Regular.ttf'


class CardError(Exception):
    pass


def _hex(s):
    s = str(s).lstrip('#')
    if len(s) != 6:
        raise CardError('color must be #RRGGBB')
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def decode_png(data):
    """Return (w, h, mode, bytes). mode is 'L' or 'RGBA'."""
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise CardError('not a png')
    pos = 8
    w = h = color = None
    idat = b''
    while pos < len(data):
        ln = struct.unpack('>I', data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if typ == b'IHDR':
            w, h, bit, color = struct.unpack('>IIBB', chunk[:10])
            if bit != 8 or color not in (0, 2, 4, 6):
                raise CardError('png must be 8-bit gray or RGB')
        elif typ == b'IDAT':
            idat += chunk
        elif typ == b'IEND':
            break
    ch = {0: 1, 2: 3, 4: 2, 6: 4}[color]
    raw = zlib.decompress(idat)
    stride = w * ch
    i = 0
    prev = bytearray(stride)
    out = bytearray()
    for _y in range(h):
        f = raw[i]
        i += 1
        row = bytearray(raw[i:i + stride])
        i += stride
        if f == 1:
            for x in range(stride):
                left = row[x - ch] if x >= ch else 0
                row[x] = (row[x] + left) & 255
        elif f == 2:
            for x in range(stride):
                row[x] = (row[x] + prev[x]) & 255
        elif f == 3:
            for x in range(stride):
                left = row[x - ch] if x >= ch else 0
                row[x] = (row[x] + ((left + prev[x]) // 2)) & 255
        elif f == 4:
            for x in range(stride):
                a = row[x - ch] if x >= ch else 0
                b = prev[x]
                c = prev[x - ch] if x >= ch else 0
                row[x] = (row[x] + _paeth(a, b, c)) & 255
        elif f != 0:
            raise CardError('bad png filter')
        prev = row
        if color == 0:
            out += row
        elif color == 2:
            for x in range(w):
                r, g, b = row[x * 3:x * 3 + 3]
                out += bytes((r, g, b, 255))
        elif color == 4:
            for x in range(w):
                yv, a = row[x * 2:x * 2 + 2]
                out += bytes((yv, yv, yv, a))
        else:
            out += row
    mode = 'L' if color == 0 else 'RGBA'
    return w, h, mode, bytes(out)


def encode_png(w, h, rgb):
    """RGB bytes to a PNG. Filter None, zlib level 9."""
    raw = bytearray()
    stride = w * 3
    for y in range(h):
        raw.append(0)
        raw += rgb[y * stride:(y + 1) * stride]

    def chunk(tag, payload):
        return struct.pack('>I', len(payload)) + tag + payload + struct.pack('>I', zlib.crc32(tag + payload) & 0xffffffff)

    ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', zlib.compress(bytes(raw), 9)) + chunk(b'IEND', b'')


def _resize_rgba(src, sw, sh, dw, dh):
    """Area-average downsample. Integer coverage, deterministic."""
    out = bytearray(dw * dh * 4)
    for y in range(dh):
        y0 = y * sh / dh
        y1 = (y + 1) * sh / dh
        iy0 = int(y0)
        iy1 = min(sh, int(y1) + (0 if y1 == int(y1) else 1))
        for x in range(dw):
            x0 = x * sw / dw
            x1 = (x + 1) * sw / dw
            ix0 = int(x0)
            ix1 = min(sw, int(x1) + (0 if x1 == int(x1) else 1))
            ar = ag = ab = aa = tot = 0.0
            for iy in range(iy0, iy1):
                row_c = min(y1, iy + 1) - max(y0, iy)
                if row_c <= 0:
                    continue
                base = (iy * sw) * 4
                for ix in range(ix0, ix1):
                    col_c = min(x1, ix + 1) - max(x0, ix)
                    if col_c <= 0:
                        continue
                    cov = row_c * col_c
                    i = base + ix * 4
                    a = src[i + 3] / 255.0
                    ar += src[i] * a * cov
                    ag += src[i + 1] * a * cov
                    ab += src[i + 2] * a * cov
                    aa += a * cov
                    tot += cov
            o = (y * dw + x) * 4
            if tot <= 0 or aa <= 0:
                continue
            a8 = int(aa / tot * 255 + 0.5)
            if a8 <= 0:
                continue
            if a8 > 255:
                a8 = 255
            out[o] = min(255, int(ar / aa + 0.5))
            out[o + 1] = min(255, int(ag / aa + 0.5))
            out[o + 2] = min(255, int(ab / aa + 0.5))
            out[o + 3] = a8
    return bytes(out)


def _fit_cat(rgba, sw, sh, side):
    """Crop to the opaque bounds and fit inside a square of `side` without stretching."""
    minx, miny, maxx, maxy = sw, sh, -1, -1
    for y in range(sh):
        row = y * sw * 4
        for x in range(sw):
            if rgba[row + x * 4 + 3] > 8:
                if x < minx:
                    minx = x
                if x > maxx:
                    maxx = x
                if y < miny:
                    miny = y
                if y > maxy:
                    maxy = y
    if maxx < 0:
        raise CardError('cat mask has no pixels')
    cw, ch = maxx - minx + 1, maxy - miny + 1
    cropped = bytearray(cw * ch * 4)
    for y in range(ch):
        src = ((miny + y) * sw + minx) * 4
        cropped[y * cw * 4:(y + 1) * cw * 4] = rgba[src:src + cw * 4]
    scale = side / max(cw, ch)
    dw = max(1, int(round(cw * scale)))
    dh = max(1, int(round(ch * scale)))
    if dw == cw and dh == ch:
        fitted = bytes(cropped)
    else:
        fitted = _resize_rgba(bytes(cropped), cw, ch, dw, dh)
    return dw, dh, fitted


def _load_font():
    if not os.path.isfile(FONT_PNG) or not os.path.isfile(FONT_JSON):
        raise CardError('glyph masks are missing; run python3 tools/og_card.py --bake')
    meta = json.load(open(FONT_JSON, encoding='utf-8'))
    w, h, mode, data = decode_png(open(FONT_PNG, 'rb').read())
    if mode != 'L':
        raise CardError('glyph mask png must be gray')
    meta['_px'] = (w, h, data)
    return meta


def _measure(style, text, font):
    glyphs = font[style]['glyphs']
    kern = font[style]['kern']
    width = 0
    prev = None
    for ch in text:
        if ch not in glyphs:
            raise CardError('share image has no glyph for %r' % ch)
        if prev:
            width += kern.get(prev + ch, 0)
        width += glyphs[ch]['adv']
        prev = ch
    return width


def _blit_text(rgb, canvas_w, canvas_h, ink, style, text, x, y, font):
    glyphs = font[style]['glyphs']
    kern = font[style]['kern']
    fw, _fh, mask = font['_px']
    pen = x
    prev = None
    ir, ig, ib = ink
    for ch in text:
        g = glyphs[ch]
        if prev:
            pen += kern.get(prev + ch, 0)
        if g['w'] and g['h']:
            dx, dy = pen + g['bx'], y + g['by']
            for row in range(g['h']):
                yy = dy + row
                if yy < 0 or yy >= canvas_h:
                    continue
                src = (g['ay'] + row) * fw + g['ax']
                dst = (yy * canvas_w + dx) * 3
                line = mask[src:src + g['w']]
                for col, a in enumerate(line):
                    if a == 0:
                        continue
                    xx = dx + col
                    if xx < 0 or xx >= canvas_w:
                        continue
                    o = dst + col * 3
                    inv = 255 - a
                    rgb[o] = (rgb[o] * inv + ir * a + 127) // 255
                    rgb[o + 1] = (rgb[o + 1] * inv + ig * a + 127) // 255
                    rgb[o + 2] = (rgb[o + 2] * inv + ib * a + 127) // 255
        pen += g['adv']
        prev = ch


def _blit_cat(rgb, canvas_w, canvas_h, ink, bg_unused, cat, cw, ch, x, y):
    ir, ig, ib = ink
    del bg_unused
    for row in range(ch):
        yy = y + row
        if yy < 0 or yy >= canvas_h:
            continue
        for col in range(cw):
            xx = x + col
            if xx < 0 or xx >= canvas_w:
                continue
            i = (row * cw + col) * 4
            a = cat[i + 3]
            if a == 0:
                continue
            o = (yy * canvas_w + xx) * 3
            inv = 255 - a
            rgb[o] = (rgb[o] * inv + ir * a + 127) // 255
            rgb[o + 1] = (rgb[o + 1] * inv + ig * a + 127) // 255
            rgb[o + 2] = (rgb[o + 2] * inv + ib * a + 127) // 255


def build(brand, mask_bytes):
    """Return a 1200x630 RGB PNG. name, tagline, cat color, and background come from brand."""
    logo = brand.get('logo') or {}
    name = str(brand.get('name') or '')
    tag = str(brand.get('tagline') or '')
    if not name or not tag:
        raise CardError('brand name and tagline are required for the share image')
    ink = _hex(logo.get('color') or '#000000')
    bg = _hex(logo.get('ogBackground') or '#ffffff')
    _w, _h, mode, rgba = decode_png(mask_bytes)
    if mode != 'RGBA':
        raise CardError('cat mask must be an RGBA png')
    cw, ch, cat = _fit_cat(rgba, _w, _h, CAT_MAX)
    font = _load_font()
    name_w = _measure('bold', name, font)
    tag_w = _measure('regular', tag, font)
    text_w = max(name_w, tag_w)
    gap = 64
    margin = 72
    lock_w = cw + gap + text_w
    left = max(margin, (WIDTH - lock_w) // 2)
    if left + lock_w > WIDTH - 24:
        left = margin
    cat_x = left
    cat_y = (HEIGHT - ch) // 2
    text_x = cat_x + cw + gap
    name_h = font['bold']['height']
    tag_h = font['regular']['height']
    block_h = name_h + 18 + tag_h
    visual_top = (HEIGHT - block_h) // 2
    name_y = visual_top - font['bold']['top']
    tag_y = visual_top + name_h + 18 - font['regular']['top']
    row = bytes((bg[0], bg[1], bg[2])) * WIDTH
    rgb = bytearray(row * HEIGHT)
    _blit_cat(rgb, WIDTH, HEIGHT, ink, bg, cat, cw, ch, cat_x, cat_y)
    _blit_text(rgb, WIDTH, HEIGHT, ink, 'bold', name, text_x, name_y, font)
    _blit_text(rgb, WIDTH, HEIGHT, ink, 'regular', tag, text_x, tag_y, font)
    png = encode_png(WIDTH, HEIGHT, bytes(rgb))
    if len(png) > 300 * 1024:
        raise CardError('share image is %d bytes, over 300KB' % len(png))
    return png


def _bake():
    from PIL import Image, ImageDraw, ImageFont
    chars = [chr(c) for c in range(32, 127)]

    def pack(font, size):
        glyphs = {}
        kern = {}
        tiles = []
        for ch in chars:
            im = Image.new('L', (size * 3, size * 3), 0)
            draw = ImageDraw.Draw(im)
            origin = (size, size)
            draw.text(origin, ch, font=font, fill=255)
            box = im.getbbox()
            if box is None or ch == ' ':
                adv = int(round(font.getlength(ch)))
                glyphs[ch] = {'ax': 0, 'ay': 0, 'w': 0, 'h': 0, 'adv': adv, 'bx': 0, 'by': 0}
                continue
            tile = im.crop(box)
            tiles.append((ch, tile))
            glyphs[ch] = {
                'w': tile.width, 'h': tile.height,
                'adv': int(round(font.getlength(ch))),
                'bx': box[0] - origin[0], 'by': box[1] - origin[1],
            }
        # pair kerning, stored only when it changes the rounded width
        for a in chars:
            for b in chars:
                delta = int(round(font.getlength(a + b) - font.getlength(a) - font.getlength(b)))
                if delta:
                    kern[a + b] = delta
        # pack tiles left to right, one row
        x = 0
        height = 1
        for ch, tile in tiles:
            glyphs[ch]['ax'] = x
            glyphs[ch]['ay'] = 0
            x += tile.width
            height = max(height, tile.height)
        sheet = Image.new('L', (max(1, x), height), 0)
        for ch, tile in tiles:
            sheet.paste(tile, (glyphs[ch]['ax'], 0))
        inked = [g for g in glyphs.values() if g['h']]
        top = min((g['by'] for g in inked), default=0)
        bot = max((g['by'] + g['h'] for g in inked), default=size)
        return {'height': bot - top, 'top': top, 'glyphs': glyphs, 'kern': kern, 'sheet': sheet}

    bold = pack(ImageFont.truetype(BOLD_TTF, BOLD_PX), BOLD_PX)
    regular = pack(ImageFont.truetype(REGULAR_TTF, REGULAR_PX), REGULAR_PX)
    gap = 2
    atlas = Image.new('L', (max(bold['sheet'].width, regular['sheet'].width), bold['sheet'].height + gap + regular['sheet'].height), 0)
    atlas.paste(bold['sheet'], (0, 0))
    atlas.paste(regular['sheet'], (0, bold['sheet'].height + gap))
    for g in regular['glyphs'].values():
        if g['h']:
            g['ay'] += bold['sheet'].height + gap
    meta = {
        'bold': {'height': bold['height'], 'top': bold['top'], 'glyphs': bold['glyphs'], 'kern': bold['kern']},
        'regular': {'height': regular['height'], 'top': regular['top'], 'glyphs': regular['glyphs'], 'kern': regular['kern']},
    }
    atlas.save(FONT_PNG)
    json.dump(meta, open(FONT_JSON, 'w', encoding='utf-8'), separators=(',', ':'))
    print('baked %s (%d bytes) and %s' % (FONT_PNG, os.path.getsize(FONT_PNG), FONT_JSON))


def main(argv=None):
    import sys
    argv = argv if argv is not None else sys.argv[1:]
    if argv == ['--bake']:
        _bake()
        return 0
    root = os.path.dirname(HERE)
    brand = json.load(open(os.path.join(root, 'brand', 'brand.json'), encoding='utf-8'))
    mask = open(os.path.join(root, brand['logo']['mask']), 'rb').read()
    png = build(brand, mask)
    out = os.path.join(root, 'hub', 'site', brand['logo'].get('ogImage', '/og.png').lstrip('/'))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, 'wb').write(png)
    print('wrote %s (%d bytes)' % (out, len(png)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
