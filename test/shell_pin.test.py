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
    'e_dynamic': 'injects a script at runtime',
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

print('\n%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)
