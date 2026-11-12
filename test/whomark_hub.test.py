#!/usr/bin/env python3
"""Hub WHOMARK final-v4.1: config is final (not placeholder), every whomark asset the hub references exists and its bytes
match the final-v4.1 MD5SUMS entry, SVG <title>s are exact, the label rule holds (whomark.js run under node), the
three-tier legend is on About + the topic index + every topic page + the topic template, highlights carry a mark for
every tier, and banned names never ship under hub/. Offline; stdlib + node."""
import hashlib, json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import byline_allow as BYLINE  # noqa: E402
SITE = os.path.join(ROOT, 'hub', 'site')
SRC = os.path.join(ROOT, 'hub', 'src')
WM = os.path.join(SITE, 'assets', 'whomark')
TIERS = ('human', 'ai', 'hybrid')
LABEL = {'human': 'Human-made', 'ai': 'AI-made', 'hybrid': 'Human + AI'}
BOX_BUNDLE = '/workspace/cos/design/marks/final-v4.1'  # design bundle; checked only when present
fails = []


def ok(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        fails.append(msg)


def read(p, mode='r'):
    return open(p, mode, encoding=None if 'b' in mode else 'utf-8').read()


def walk(d):
    for base, _, fs in os.walk(d):
        for f in fs:
            yield os.path.join(base, f)


# ---- config ----
cfg = json.load(open(os.path.join(WM, 'config.json')))
ok(cfg['placeholder'] is False, 'config.json placeholder is false')
ok(cfg['family'] == 'final-v4.1', 'config.json family is final-v4.1 (%s)' % cfg['family'])
ok(cfg['minSizePx'] == {'human': 14, 'ai': 14, 'hybrid': 16}, 'minSizePx human 14 / ai 14 / hybrid 16')
ok(cfg['labelRequiredAtOrBelowPx'] == 14, 'labelRequiredAtOrBelowPx is 14')
ok(set(cfg['tiers']) == set(TIERS) and all(cfg['tiers'][t]['textLabel'] == LABEL[t] for t in TIERS), 'tier labels Human-made / AI-made / Human + AI')
ok(all(cfg['tiers'][t]['title'] == 'WHOMARK: ' + LABEL[t] for t in TIERS), 'config titles are plain "WHOMARK: <label>"')
ok(cfg['tiers']['ai']['stewardLabel'] == 'AI-made · AI steward', 'AI steward label per spec')
ok({t: cfg['tiers'][t]['color'] for t in TIERS} == {'human': '#1E7B34', 'ai': '#000000', 'hybrid': '#9A6700'}, 'palette C light colours')
for t in TIERS:
    ok(cfg['tiers'][t]['ogBadge'] == '/assets/whomark/whomark-%s-lg-color-128px.png' % t, '%s og badge is the set PNG' % t)
    ok(cfg['tiers'][t]['cornerBadge'] == '/assets/whomark/whomark-%s-lg-color-48px.png' % t, '%s corner badge is the set PNG' % t)

# ---- assets: only whomark-* art + config + js, every file in the final-v4.1 manifest with matching bytes ----
manifest = {}
for line in read(os.path.join(SRC, 'whomark', 'MD5SUMS.final-v4.1.txt')).splitlines():
    h, p = line.split(None, 1)
    manifest[os.path.basename(p.strip())] = h
art = sorted(f for f in os.listdir(WM) if f not in ('config.json', 'whomark.js'))
ok(all(f.startswith('whomark-') for f in art), 'every art file name is whomark-* (%s)' % [f for f in art if not f.startswith('whomark-')])
ok(not any(os.path.exists(os.path.join(WM, f)) for f in ('sprite.svg', 'og-ai.png', 'og-human.png', 'og-hybrid.png', 'corner-ai.png', 'corner-human.png', 'corner-hybrid.png')),
   'placeholder sprite + badge PNGs are gone')
ok(sorted(manifest) == art, 'hub art set == manifest (%d files)' % len(art))
for f in art:
    ok(hashlib.md5(read(os.path.join(WM, f), 'rb')).hexdigest() == manifest.get(f), '%s md5 matches final-v4.1 MD5SUMS' % f)
if os.path.isfile(os.path.join(BOX_BUNDLE, 'MD5SUMS.txt')):
    full = {os.path.basename(l.split(None, 1)[1].strip()): l.split()[0] for l in read(os.path.join(BOX_BUNDLE, 'MD5SUMS.txt')).splitlines() if l.strip()}
    ok(all(full.get(f) == h for f, h in manifest.items()), 'repo manifest entries == design bundle MD5SUMS.txt')

# every /assets/whomark/... reference in the hub output (and whomark.js-built names) exists
refs = set()
for p in walk(SITE):
    if p.endswith(('.html', '.js', '.json', '.css')):
        refs |= set(re.findall(r'/assets/whomark/([A-Za-z0-9._-]+)', read(p)))
built = {'whomark-%s-%s-color.svg' % (t, s) for t in TIERS for s in ('s14', 's16', 'lg')}
built |= {'whomark-%s-lg-color-%s.png' % (t, s) for t in TIERS for s in ('128px', '48px')}
refs = {r for r in refs if '.' in r} | built
missing = sorted(r for r in refs if not os.path.isfile(os.path.join(WM, r)))
ok(not missing, 'every referenced whomark asset exists (%d refs; missing %s)' % (len(refs), missing))
unused = sorted(set(art) - refs)
ok(not unused, 'no unreferenced whomark art ships (%s)' % unused)

# ---- SVG titles exact, no ™ in titles ----
for f in art:
    if f.endswith('.svg'):
        t = re.findall(r'<title>(.*?)</title>', read(os.path.join(WM, f)))
        tier = f.split('-')[1]
        ok(t == ['WHOMARK: ' + LABEL[tier]], '%s <title> is exactly "WHOMARK: %s" (%s)' % (f, LABEL[tier], t))

# ---- whomark.js: label rule + sizes + titles, run under node ----
JS = r'''
const fs = require('fs'), vm = require('vm');
const ctx = { globalThis: {} }; ctx.window = ctx.globalThis;
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), ctx);
const g = ctx.window, out = {};
for (const t of ['human', 'ai', 'hybrid']) for (const s of [8, 12, 14, 15, 16, 20, 24, 48]) out[t + s] = g.whoMark(t, t === 'hybrid' ? ['Ana', 'Bo'] : null, { size: s, label: false });
out.steward = g.whoMark('ai', null, { steward: true });
out.bad = g.whoMark('robot');
out.cfg = g.whoMarkConfig();
out.badges = g.whoMarkBadges('hybrid');
out.plain = g.whoMarkPlain('hybrid', ['Ana']);
console.log(JSON.stringify(out));
'''
r = subprocess.run(['node', '-e', JS, os.path.join(WM, 'whomark.js')], capture_output=True, text=True)
ok(r.returncode == 0, 'whomark.js runs under node (%s)' % r.stderr.strip()[:200])
o = json.loads(r.stdout) if r.returncode == 0 else {}
if o:
    jc = o['cfg']
    ok(jc['family'] == cfg['family'] and jc['placeholder'] is False and jc['minSizePx'] == cfg['minSizePx']
       and jc['labelRequiredAtOrBelowPx'] == cfg['labelRequiredAtOrBelowPx']
       and all(jc['tiers'][t]['textLabel'] == cfg['tiers'][t]['textLabel'] and jc['tiers'][t]['title'] == cfg['tiers'][t]['title'] for t in TIERS),
       'whomark.js config == config.json')
    for k, h in o.items():
        if k in ('cfg', 'bad', 'badges', 'plain', 'steward'):
            continue
        t, s = re.match(r'([a-z]+)(\d+)', k).groups(); s = int(s)
        px = int(re.search(r'width="(\d+)"', h).group(1))
        lab = re.search(r'<span class="whomark-label"[^>]*>([^<]*)</span>', h)
        ok(lab is not None and lab.group(1) == LABEL[t], '%s @%dpx: visible label "%s" always shown (label:false ignored)' % (t, s, LABEL[t]))
        ok(px >= cfg['minSizePx'][t], '%s @%dpx renders %dpx >= tier minimum' % (t, s, px))
        if px <= cfg['labelRequiredAtOrBelowPx']:
            ok(lab is not None, '%s at %dpx (<= 14) carries the text label' % (t, px))
        f = re.search(r'whomark-%s-(s14|s16|lg)-color\.svg' % t, h).group(1)
        ok((px == 14 and f == 's14') or (px == 16 and f == 's16') or (px >= 24 and f == 'lg'), '%s @%dpx uses the snapped file for its size (%s @ %dpx)' % (t, s, f, px))
        ok(('aria-label="WHOMARK: %s' % LABEL[t]) in h and '™' not in h, '%s: aria-label is plain "WHOMARK: %s", no ™' % (t, LABEL[t]))
    ok('AI-made · AI steward' in o['steward'], 'steward mark label "AI-made · AI steward"')
    ok(o['bad'] == '', 'unknown tier renders nothing')
    ok(o['badges'] == {'og': cfg['tiers']['hybrid']['ogBadge'], 'corner': cfg['tiers']['hybrid']['cornerBadge']}, 'whoMarkBadges = config og/corner')
    ok(o['plain'] == 'Human + AI: Ana', 'plain-text fallback')
js = read(os.path.join(WM, 'whomark.js'))
ok('style=' not in js and 'createElement(\'style\')' not in js and 'textContent' not in js, 'whomark.js injects no inline styles (strict CSP)')

# ---- legend: About, topic index, every topic page, the topic template ----
brand = json.load(open(os.path.join(ROOT, 'brand', 'brand.json')))
tdir = os.path.join(SITE, brand['topicPathPrefix'].strip('/'))
pages = ['about.html'] + [os.path.relpath(p, SITE) for p in walk(tdir) if p.endswith('.html')]
ok(len(pages) >= 50, 'legend pages: about + topic index + topic pages (%d)' % len(pages))
for p in pages:
    h = read(os.path.join(SITE, p))
    m = re.search(r'<table class="hub-legend">(.*?)</table>', h, re.S)
    rows = re.findall(r'<tr><th scope="row">(.*?)</th>', m.group(1)) if m else []
    tiers = [re.search(r'whomark--(human|ai|hybrid)', x).group(1) if re.search(r'whomark--(human|ai|hybrid)', x) else None for x in rows]
    labs = [re.sub(r'<[^>]+>', '', x) for x in rows]
    imgs = all(re.search(r'<img src="/assets/whomark/whomark-%s-s16-color\.svg\?v=[0-9a-f]{10}" width="16" height="16"' % t, x) for t, x in zip(tiers, rows)) if rows else False
    ok(tiers == list(TIERS) and labs == [LABEL[t] for t in TIERS] and imgs, '%s: three-tier legend with marks + labels' % p)
    ok(('<caption>%s labels</caption>' % brand['disclosureMark']) in h, '%s: legend caption uses {{brand.disclosureMark}}' % p)
ok('{{> legend}}' in read(os.path.join(SRC, 'topic-template.html')), 'topic template includes the legend partial')
ok('{{> legend}}' in read(os.path.join(SRC, 'templates', 'about.html')), 'About template includes the legend partial')
ok('placeholder art' not in read(os.path.join(SITE, 'about.html')), 'About no longer says the marks are placeholder art')

# ---- highlights: every tier gets a mark; home + topic pages load whomark.js ----
hj = read(os.path.join(SITE, 'hub.js'))
ok(all(('data-whomark="%s"' % t) in hj for t in TIERS) and 'tierHtml(it.tier, it.names)' in hj, 'hub.js: every highlight tier renders a [data-whomark] mark')
for p in ['index.html', 'about.html'] + pages:
    ok(re.search(r'<script src="/assets/whomark/whomark\.js\?v=[0-9a-f]{10}"', read(os.path.join(SITE, p))) is not None, '%s loads self-hosted whomark.js' % p)
hl = json.load(open(os.path.join(SITE, 'highlights.json')))
ok(all(it.get('tier') in TIERS for it in hl.get('items', [])), 'every highlight has a known tier (so every card shows a mark)')

# ---- banned names: PEEKAI (any case), VokaDots, private details ----
BANNED = re.compile(r'peek\s*-?\s*ai|voka\s*-?\s*dots', re.I)
# Denver is a legitimate topic slug (/t/denver/); only a Denver street
# address (registered-agent form: number + street, Denver, CO / 802xx) is private.
DENVER_ADDR = re.compile(
    r'\b\d{1,6}\s+(?:[NSEW]\.?\s+)?[A-Za-z0-9.\' ]{1,40}?\b'
    r'(?:St|Street|Ave|Avenue|Blvd|Boulevard|Rd|Road|Dr|Drive|Way|Pl|Place|Ct|Court|Ln|Lane|Pkwy|Parkway)\b'
    r'[^\n]{0,60}?\bDenver\b,?\s*(?:CO|Colo\.?|Colorado)\b(?:\s*802\d\d)?'
    r'|\bDenver,?\s*(?:CO|Colorado)\s+802\d\d\b', re.I)
def banned(t):
    return BANNED.search(t) or DENVER_ADDR.search(t)
hits = []
# the self-hosted shell (hub/site/shell/<base>/factory.js) is the hub-only fork of shell/<base>/factory.js (EXCEPTIONS.md E21):
# one header line differs; its upstream code keeps the functional reserved-handle regex "jebb". hub_brand.test.py pins it.
SELF_SHELL = os.path.abspath(os.path.join(ROOT, 'hub', 'site', 'shell'))
_hub_cfg = json.load(open(os.path.join(ROOT, 'hub', 'src', 'config.json')))
ok(_hub_cfg['shell']['base'] == 'v1.2.10', 'hub is pinned to shell v1.2.10')
ok(os.path.isfile(os.path.join(SELF_SHELL, 'v1.2.10', 'factory.js')), 'hub/site/shell/v1.2.10/factory.js exists')
ok(os.path.isfile(os.path.join(SELF_SHELL, 'v1.2.10', 'factory-signin.js')), 'hub/site/shell/v1.2.10/factory-signin.js exists (lazy sign-in companion)')
ok(not os.path.isdir(os.path.join(SELF_SHELL, 'v1.2.9')), 'previous hub shell v1.2.9 is no longer hosted')
ok(not os.path.isdir(os.path.join(SELF_SHELL, 'v1.2.6')), 'previous hub shell v1.2.6 is no longer hosted')
for p in list(walk(os.path.join(ROOT, 'hub'))) + [os.path.join(SRC, 'topic-template.html')]:
    if os.path.abspath(p).startswith(SELF_SHELL + os.sep):
        fl = read(p, 'rb').split(b'\n')
        pl = read(os.path.join(ROOT, os.path.relpath(p, os.path.join(ROOT, 'hub', 'site'))), 'rb').split(b'\n')
        dl = [i for i in range(len(pl)) if len(fl) != len(pl) or fl[i] != pl[i]]
        ft = b'\n'.join(fl).decode('utf-8')
        jebbs = re.findall(r'jebb\w*|dykstra', ft, re.I)
        # factory.js keeps the reserved-handle regex "jebb"; factory-signin.js has no handle list,
        # so after the header swap it has no jebb or dykstra at all.
        want_jebb = (jebbs == ['jebb']) if os.path.basename(p) == 'factory.js' else (jebbs == [])
        ok(len(dl) == 1 and fl[dl[0]].startswith(b' * Source: SubX shared shell') and not banned(ft)
           and want_jebb,
           '%s: hub fork of the shared shell (one header line), no repo path or private string besides the reserved-handle regex (jebb=%s)' % (os.path.relpath(p, ROOT), jebbs))
        continue
    b = read(p, 'rb')
    try:
        t = b.decode('utf-8')
    except UnicodeDecodeError:
        t = b.decode('latin-1')
    t2 = t.replace('jebbdykstra99/subx-factory', '')
    # Decision 2026-11-05: mask allowed author bylines before the jebb|dykstra ban.
    t2 = BYLINE.mask_allowed_bylines(t2)
    if banned(t) or re.search(r'jebb|dykstra', t2, re.I):
        hits.append(os.path.relpath(p, ROOT))
ok(not hits, 'no PEEKAI / VokaDots / private name or Denver street address under hub/ or the topic template (%s)' % hits)
# the check itself catches them
ok(not banned('/t/denver/') and not banned('Denver') and not banned('denver'), 'bare "denver" slug/word passes')
ok(banned('1234 Example St, Suite 100, Denver, CO 80202') and banned('55 N. Main Street Denver Colorado') and banned('Denver, CO 80203'), 'Denver street-address pattern is blocked')
ok(BANNED.search('PeekAI') and BANNED.search('vokadots') and BANNED.search('PEEKAI'), 'banned-name grep matches any case')
# Decision 2026-11-05: byline allowlist sides
ok(BYLINE.is_name_clean('<p class="byline">By Jebb Dykstra</p>'), 'whomark_hub byline allowlist: byline passes')
ok(not BYLINE.is_name_clean('<meta name="author" content="Jebb Dykstra">'), 'whomark_hub byline allowlist: meta author fails')
ok(not BYLINE.is_name_clean('{"publisher":{"name":"Jebb Dykstra"}}'), 'whomark_hub byline allowlist: JSON-LD publisher fails')

if fails:
    print('FAILED %d: %s' % (len(fails), fails[:5]))
    sys.exit(1)
print('whomark_hub: all checks passed')
