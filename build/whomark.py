#!/usr/bin/env python3
"""whoMark assets: validate a mark family, stamp its config into whomark.js, render og/corner badge PNGs.

  python3 build/whomark.py --validate <family-dir>          # exit 1 + reasons if the family is not swappable
  python3 build/whomark.py [--src <family-dir>] [--out DIR]  # build (default --src/--out = assets/whomark)
  python3 build/whomark.py --check                           # assets/whomark is in sync with its sprite + config
  add --no-png to skip PNG rendering (CI without cairosvg); PNGs need `pip install cairosvg`.

A family dir holds exactly two inputs: sprite.svg and config.json (see marks/placeholder-ring/).
Everything else in assets/whomark/ (whomark.js config block, og-*.png, corner-*.png) is generated."""
import argparse, hashlib, json, os, re, shutil, sys, tempfile
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, 'assets', 'whomark')
SVGNS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', SVGNS)
TIERS = ('human', 'ai', 'hybrid')
TIER_FIELDS = ('symbolId', 'symbolIdSmall', 'textLabel', 'ariaLabel', 'title', 'plainText', 'ogBadge', 'cornerBadge')
# Disclosure copy is policy, not art: a family swap may not change it.
LABELS = {'human': 'Human-made', 'ai': 'AI steward · SubX', 'hybrid': 'Human + AI'}
# Byte budgets (stated in README "Swapping the disclosure mark family").
BUDGET = {'sprite.svg': 8192, 'config.json': 4096, 'whomark.js': 8192, 'png': 16384, 'total': 65536}
CORE_BUDGET = 255000
BEGIN, END = '/* @whomark-config */', '/* @whomark-config-end */'

def q(tag): return '{%s}%s' % (SVGNS, tag)

def load_family(d):
    sp, cp = os.path.join(d, 'sprite.svg'), os.path.join(d, 'config.json')
    return open(sp, 'rb').read(), json.load(open(cp, encoding='utf-8'))

def symbols(sprite_bytes):
    root = ET.fromstring(sprite_bytes)
    return root, {s.get('id'): s for s in root.iter(q('symbol'))}

def validate(d):
    errs = []
    for f in ('sprite.svg', 'config.json'):
        p = os.path.join(d, f)
        if not os.path.isfile(p): errs.append('missing %s' % f); continue
        if os.path.getsize(p) > BUDGET[f]: errs.append('%s is %d B > budget %d B' % (f, os.path.getsize(p), BUDGET[f]))
    if errs: return errs
    try: sprite, cfg = load_family(d)
    except Exception as e: return ['cannot read family: %s' % e]
    try: root, syms = symbols(sprite)
    except ET.ParseError as e: return ['sprite.svg does not parse: %s' % e]
    if root.tag != q('svg'): errs.append('sprite.svg root is not <svg xmlns="%s">' % SVGNS)
    txt = sprite.decode('utf-8', 'replace')
    if re.search(r'<script|\son\w+\s*=|<foreignObject|(?:xlink:)?href\s*=\s*["\'](?!#)', txt, re.I):
        errs.append('sprite.svg has script, event handlers, foreignObject or external hrefs')
    if 'currentColor' not in txt: errs.append('sprite.svg never uses currentColor (main stroke must follow text colour)')
    accents = set(re.findall(r'var\((--[\w-]+)', txt))
    if len(accents) > 1: errs.append('sprite.svg uses %d CSS variables %s; exactly one accent is allowed' % (len(accents), sorted(accents)))
    if accents and cfg.get('accentVar') not in accents: errs.append('accentVar %r is not the variable the sprite uses %s' % (cfg.get('accentVar'), sorted(accents)))
    for sid, s in syms.items():
        if s.get('viewBox', '').split() != ['0', '0', '24', '24']: errs.append('symbol %s viewBox %r != "0 0 24 24"' % (sid, s.get('viewBox')))
        t = s.find(q('title'))
        if t is None or not (t.text or '').strip(): errs.append('symbol %s has no <title>' % sid)
    for k in ('family', 'sprite', 'accentVar', 'accentDefault', 'defaultSizePx', 'smallBelowPx', 'minSizePx', 'labelRequiredAtOrBelowPx', 'badges', 'tiers'):
        if k not in cfg: errs.append('config.json missing %s' % k)
    if any(e.startswith('config.json missing') for e in errs): return errs
    if cfg['sprite'] != '/assets/whomark/sprite.svg': errs.append('config sprite must be /assets/whomark/sprite.svg (rooms serve it from there)')
    mins = cfg['minSizePx']
    if not isinstance(mins, dict) or any(not isinstance(mins.get(t), int) for t in TIERS): errs.append('minSizePx needs an integer per tier')
    elif mins['hybrid'] < 16: errs.append('minSizePx.hybrid %s < 16' % mins['hybrid'])
    elif min(mins.values()) < 14: errs.append('minSizePx below 14')
    if cfg['labelRequiredAtOrBelowPx'] < 14: errs.append('labelRequiredAtOrBelowPx must be >= 14 (14px marks always carry the text label)')
    for b in ('og', 'corner'):
        if not isinstance(cfg['badges'].get(b), dict) or not all(k in cfg['badges'][b] for k in ('px', 'bg', 'fg')): errs.append('badges.%s needs px, bg, fg' % b)
    for t in TIERS:
        tc = cfg['tiers'].get(t)
        if not isinstance(tc, dict): errs.append('config tiers.%s missing' % t); continue
        for f in TIER_FIELDS:
            if not isinstance(tc.get(f), str) or not tc[f]: errs.append('tiers.%s.%s missing' % (t, f))
        for f in ('symbolId', 'symbolIdSmall'):
            if tc.get(f) and tc[f] not in syms: errs.append('tiers.%s.%s %r is not a <symbol> in sprite.svg' % (t, f, tc[f]))
        if tc.get('textLabel') != LABELS[t]: errs.append('tiers.%s.textLabel %r != policy label %r' % (t, tc.get('textLabel'), LABELS[t]))
        for f in ('ogBadge', 'cornerBadge'):
            if tc.get(f) and not re.match(r'^/assets/whomark/[a-z0-9-]+\.png$', tc[f]): errs.append('tiers.%s.%s must be /assets/whomark/<name>.png' % (t, f))
    if '{names}' not in cfg['tiers'].get('hybrid', {}).get('title', ''): errs.append('tiers.hybrid.title must contain {names} ("Human + AI: {names}")')
    fj = os.path.join(ROOT, 'factory', 'factory.js')
    if os.path.getsize(fj) > CORE_BUDGET: errs.append('factory/factory.js %d B > %d B' % (os.path.getsize(fj), CORE_BUDGET))
    return errs

def embed_config(cfg, sprite):
    c = {k: v for k, v in cfg.items() if k not in ('note', 'badges')}
    c['version'] = hashlib.sha256(sprite).hexdigest()[:10]
    return json.dumps(c, ensure_ascii=False, separators=(',', ':'), sort_keys=True)

def stamp_js(js, cfg, sprite):
    i, j = js.index(BEGIN) + len(BEGIN), js.index(END)
    return js[:i] + embed_config(cfg, sprite) + js[j:]

def badge_svg(sprite, cfg, sid, kind):
    _, syms = symbols(sprite)
    b = cfg['badges'][kind]; px = b['px']
    inner = ''.join(ET.tostring(ch, encoding='unicode') for ch in syms[sid] if ch.tag != q('title'))
    inner = inner.replace('currentColor', b['fg'])
    inner = re.sub(r'var\(\s*--[\w-]+\s*(?:,\s*([^)]+))?\)', lambda m: (m.group(1) or cfg['accentDefault']).strip(), inner)
    inner = re.sub(r'\sxmlns(?::\w+)?="[^"]*"', '', inner)
    bg = ('<rect width="24" height="24" rx="5" fill="%s"/>' % b['bg']) if kind == 'og' else ('<circle cx="12" cy="12" r="12" fill="%s" fill-opacity="0.88"/>' % b['bg'])
    pad = 0.18 if kind == 'og' else 0.14
    s = 1 - 2 * pad
    return ('<svg xmlns="%s" width="%d" height="%d" viewBox="0 0 24 24">%s<g transform="translate(%.2f %.2f) scale(%.3f)">%s</g></svg>'
            % (SVGNS, px, px, bg, 24 * pad, 24 * pad, s, inner))

def build(src, out, png=True):
    sprite, cfg = load_family(src)
    os.makedirs(out, exist_ok=True)
    for f in ('sprite.svg', 'config.json'):
        if os.path.abspath(os.path.join(src, f)) != os.path.abspath(os.path.join(out, f)): shutil.copyfile(os.path.join(src, f), os.path.join(out, f))
    tpl = open(os.path.join(ASSETS, 'whomark.js'), encoding='utf-8').read()
    open(os.path.join(out, 'whomark.js'), 'w', encoding='utf-8').write(stamp_js(tpl, cfg, sprite))
    wanted = set()
    for t in TIERS:
        for f, kind, key in (('ogBadge', 'og', 'symbolId'), ('cornerBadge', 'corner', 'symbolIdSmall')):
            name = os.path.basename(cfg['tiers'][t][f]); wanted.add(name)
            if png:
                import cairosvg
                cairosvg.svg2png(bytestring=badge_svg(sprite, cfg, cfg['tiers'][t][key], kind).encode(), write_to=os.path.join(out, name))
    if png:  # drop badge PNGs the new config no longer names
        for f in os.listdir(out):
            if f.endswith('.png') and f not in wanted: os.remove(os.path.join(out, f))
    return sizes(out)

def sizes(d):
    rows = {f: os.path.getsize(os.path.join(d, f)) for f in sorted(os.listdir(d)) if os.path.isfile(os.path.join(d, f))}
    over = [f for f, b in rows.items() if b > BUDGET.get(f, BUDGET['png'] if f.endswith('.png') else BUDGET['total'])]
    if sum(rows.values()) > BUDGET['total']: over.append('total %d B' % sum(rows.values()))
    return rows, over

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--validate', metavar='FAMILY_DIR'); ap.add_argument('--src', default=ASSETS); ap.add_argument('--out', default=ASSETS)
    ap.add_argument('--check', action='store_true'); ap.add_argument('--no-png', action='store_true')
    a = ap.parse_args()
    if a.validate:
        errs = validate(a.validate)
        for e in errs: print('INVALID: ' + e, file=sys.stderr)
        if not errs: print('valid family: %s' % a.validate)
        sys.exit(1 if errs else 0)
    png = not a.no_png
    if png:
        try: import cairosvg  # noqa: F401
        except ImportError:
            if a.check: png = False; print('whomark: cairosvg not installed, PNGs not compared')
            else: sys.exit('whomark: PNG rendering needs cairosvg (pip install cairosvg), or pass --no-png')
    errs = validate(a.src)
    if errs: sys.exit('whomark: invalid family %s:\n  ' % a.src + '\n  '.join(errs))
    if a.check:
        tmp = tempfile.mkdtemp()
        try:
            build(ASSETS, tmp, png)
            bad = [f for f in os.listdir(tmp) if (png or not f.endswith('.png')) and open(os.path.join(tmp, f), 'rb').read() != open(os.path.join(ASSETS, f), 'rb').read()]
        finally: shutil.rmtree(tmp)
        if bad: sys.exit('whomark: assets/whomark out of sync (run python3 build/whomark.py): ' + ', '.join(sorted(bad)))
        print('whomark: assets/whomark in sync'); return
    rows, over = build(a.src, a.out, png)
    for f, b in rows.items(): print('%-20s %7d B' % (f, b))
    print('%-20s %7d B (budget %d B)' % ('total', sum(rows.values()), BUDGET['total']))
    if over: sys.exit('whomark: over budget: ' + ', '.join(over))

if __name__ == '__main__':
    main()
