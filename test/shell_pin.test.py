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


def run(d):
    subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'shell_drift.py'), d, '--json', d + '.json'],
                         capture_output=True, text=True)
    return json.load(open(d + '.json'))[0]


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

    # third-party: emoji-picker@1 without SRI is WARN (not OK, not DRIFT); exact version + integrity is clean
    d = room(t, 'emoji_warn', pinned + '<script type="module" src="https://cdn.jsdelivr.net/npm/emoji-picker-element@1/index.js"></script>', {'base': V})
    r = run(d); ok(r['status'] == 'WARN' and r['warnings'], 'emoji-picker-element@1 without SRI = WARN')
    d = room(t, 'emoji_pinned', pinned + '<script type="module" src="https://cdn.jsdelivr.net/npm/emoji-picker-element@1.21.3/index.js" integrity="sha384-x" crossorigin="anonymous"></script>', {'base': V})
    r = run(d); ok(r['status'] == 'OK', 'emoji-picker-element exact version + integrity = OK')

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
    'h8_inertpin': ('DRIFT', 'pin is inert (type=text/plain)', None),
    'h9_templatepin': ('DRIFT', 'pin is inert (inside <template>)', None),
    'h10_evalfetch': ('DRIFT', 'at runtime (', None),
    'h11_obf': ('DRIFT', 'at runtime (createElement(t', None),
    'h12_iframe': ('DRIFT', 'undeclared <a href=javascript:>', 'remote <iframe src=https://evil.example/page.html>'),
    'h13_worker': ('DRIFT', 'at runtime (new Worker(', None),
    'h14_nomodule': ('DRIFT', 'pin is inert (nomodule)', None),
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
    r = run(d); ok(r['status'] == 'DRIFT' and any('inside <noscript>' in x for x in r['findings']), 'pin inside <noscript> = DRIFT')
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
    'k4d_foreignpin': ('DRIFT', 'pin is inert (inside <svg>)', None),
    'k5_css': ('WARN', None, 'CSS @import of remote https://evil.example/x.css'),
    'k6_duppin': ('DRIFT', 'integrity missing or not the SHELL.json value', None),
    'k7_lookalike': ('DRIFT', 'index.html runs no shell', None),
    'k8_cspmeta': ('DRIFT', 'pin is blocked by index.html:1 <meta> CSP', None),
    'k9_pinelsewhere': ('DRIFT', 'index.html runs no shell', None),
    'k10_importmap': ('DRIFT', 'undeclared inline <script>', None),
    'k11_modulepin': ('DRIFT', 'pin has type=module', None),
    'k12_headers': ('DRIFT', 'pin is blocked by _headers header CSP for /*', None),
    'k13_frameset': ('WARN', None, 'remote <frame src=https://evil.example/>'),
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
    s_, f_, w_ = st(d); ok(s_ == 'OK', 'terms.html + nest.html in shell.noShell = OK (%s)' % f_)
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
    ok(st(d)[0] == 'OK', 'declared remote <frame> = OK')

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
    'c3_nonce_ok': ('OK', None, None),
    'c4_nonce_bad': ('DRIFT', 'pin is blocked by', None),
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
# ADV7 more
ok(sorted(ADV7_EXPECT) == sorted(x for x in os.listdir(ADV7) if os.path.isdir(os.path.join(ADV7, x))), 'every adv7 fixture room has an expectation')
for name, needle in sorted(ADV7_EXPECT.items()):
    with tempfile.TemporaryDirectory() as t:
        d = os.path.join(t, name); shutil.copytree(os.path.join(ADV7, name), d)
        r = run(d)
        ok(r['status'] == 'DRIFT' and any(needle in x for x in r['findings']),
           'adv7 %s = DRIFT with "%s" (%s %s)' % (name, needle, r['status'], r['findings']))

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

print('\n%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)
