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

    r = run(room(t, 'kept', '<script src="gate.js?v=1"></script>' + pinned, {'base': V, 'keep': ['gate.js']}, {'gate.js': b''}))
    ok(r['status'] == 'OK', 'room file in shell.keep (gate.js) = OK')

    pre = 'https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@%s/factory/factory.js' % m['sourceCommit']
    r = run(room(t, 'premerge', '<script src="%s" integrity="%s" crossorigin="anonymous"></script>' % (pre, INTEG), {'base': V}))
    ok(r['status'] == 'OK', 'pre-merge factory/ path at SHELL.json sourceCommit = OK (%s)' % r['findings'])
    other = pre.replace(m['sourceCommit'], '1' * 40)
    r = run(room(t, 'premerge2', '<script src="%s" integrity="%s" crossorigin="anonymous"></script>' % (other, INTEG), {'base': V}))
    ok(r['status'] == 'DRIFT', 'factory/ path at any other commit = DRIFT')

print('\n%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)
