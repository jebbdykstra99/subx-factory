#!/usr/bin/env python3
"""Nightly drift check (read-only, no token needed). For every room in rooms.json:
  live https://<domain>/factory.js and /styles.css sha256  vs  the room repo's FACTORY.lock (raw.githubusercontent.com, main)
  and vs this repo's factory/factory.js (the release). Opt-in files (factory-gp.js, factory-rail.js, factory-reports.js) get the same
  live-vs-lock-vs-release check for every room whose FACTORY.lock lists them.
States: OK, DRIFT (live != lock), STALE (lock != release: stamp PR not merged yet), UNSTAMPED (no FACTORY.lock yet),
ERROR (fetch failed, e.g. btb cert). Exit 1 on any DRIFT, or on ERROR for rooms without driftIgnore ["https"].
Usage: python3 tools/drift_check.py [--out report.md]"""
import argparse, hashlib, json, os, sys, time, urllib.request, ssl
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def get(url):
    req = urllib.request.Request(url + ('&' if '?' in url else '?') + 'drift=' + str(int(time.time())), headers={'User-Agent': 'subx-factory-drift/1', 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(req, timeout=20) as r: return r.read()
def h(b): return hashlib.sha256(b).hexdigest()
ap = argparse.ArgumentParser(); ap.add_argument('--out'); a = ap.parse_args()
cfg = json.load(open(os.path.join(ROOT, 'rooms.json')))
release = h(open(os.path.join(ROOT, 'factory/factory.js'), 'rb').read())
OPTIN = ('factory-gp.js', 'factory-rail.js', 'factory-reports.js')
release_optin = {f: h(open(os.path.join(ROOT, 'factory', f), 'rb').read()) for f in OPTIN if os.path.exists(os.path.join(ROOT, 'factory', f))}
rows, fail = [], False
for e in sorted(cfg['rooms'], key=lambda e: e['order']):
    st, note = 'OK', []
    try: lock = json.loads(get('https://raw.githubusercontent.com/%s/main/FACTORY.lock' % e['repo']))
    except Exception: lock = None
    try:
        fj = h(get('https://%s/factory.js' % e['domain'])); sc = h(get('https://%s/styles.css' % e['domain']))
    except Exception as ex:
        rows.append((e['room'], 'ERROR', '-', '-', str(ex)[:80])); 
        if 'https' not in e.get('driftIgnore', []): fail = True
        continue
    if not lock: st = 'UNSTAMPED'; note.append('no FACTORY.lock yet')
    else:
        if fj != lock['files']['factory.js']: st = 'DRIFT'; note.append('factory.js live != lock')
        if sc != lock['files'].get('styles.css', sc): st = 'DRIFT'; note.append('styles.css live != lock')
        for f in OPTIN:
            if f not in lock['files']: continue
            try: live_o = h(get('https://%s/%s' % (e['domain'], f)))
            except Exception as ex: st = 'DRIFT'; note.append('%s not served (%s)' % (f, str(ex)[:40])); continue
            if live_o != lock['files'][f]: st = 'DRIFT'; note.append('%s live != lock' % f)
            elif st == 'OK' and lock['files'][f] != release_optin.get(f): st = 'STALE'; note.append('%s lock != release' % f)
        if st == 'OK' and lock['files']['factory.js'] != release: st = 'STALE'; note.append('lock is %s, release is %s' % (lock.get('version'), cfg['version']))
    if st == 'DRIFT': fail = True
    rows.append((e['room'], st, fj[:12], sc[:12], '; '.join(note)))
md = ['# Drift check %s' % time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime()), '', 'Release `%s` factory.js `%s`' % (cfg['version'], release[:12]), '',
      '| Room | State | live factory.js | live styles.css | Note |', '|---|---|---|---|---|'] + ['| %s | %s | `%s` | `%s` | %s |' % r for r in rows]
out = '\n'.join(md) + '\n'; print(out)
if a.out: open(a.out, 'w').write(out)
if os.environ.get('GITHUB_STEP_SUMMARY'): open(os.environ['GITHUB_STEP_SUMMARY'], 'a').write(out)
sys.exit(1 if fail else 0)
