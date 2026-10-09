#!/usr/bin/env python3
"""Per-room stamp dry-run. Copies each room clone to a temp dir, stamps the copy, reports git diff size.
  python3 tools/dry_run.py --rooms-dir DIR [--out reports/STAMP_DRYRUN.md] [--keep OUTDIR]
DIR holds one clone per room (folder name = room). Nothing is pushed; the clones are not modified."""
import argparse, json, os, shutil, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); sys.path.insert(0, HERE)
import stamp as S
ap = argparse.ArgumentParser(); ap.add_argument('--rooms-dir', required=True); ap.add_argument('--out'); ap.add_argument('--keep')
a = ap.parse_args()
cfg = json.load(open(os.path.join(ROOT, 'rooms.json')))
release = {'factory': open(os.path.join(ROOT, 'factory/factory.js'), 'rb').read(), 'version': cfg['version']}
rows = []
for e in sorted(cfg['rooms'], key=lambda e: e['order']):
    src = os.path.join(a.rooms_dir, e['room'])
    tmp = os.path.join(a.keep, e['room']) if a.keep else tempfile.mkdtemp()
    if os.path.exists(tmp): shutil.rmtree(tmp)
    shutil.copytree(src, tmp, symlinks=True)
    rep, files = S.stamp(e, release, tmp, dry=True)
    # always write into the temp copy so the diff size is measurable even for blocked rooms
    fjs, idx, site_raw, lock = files
    open(os.path.join(tmp, 'factory.js'), 'wb').write(fjs); open(os.path.join(tmp, 'index.html'), 'w').write(idx)
    if site_raw: open(os.path.join(tmp, 'site.json'), 'w').write(site_raw)
    open(os.path.join(tmp, 'FACTORY.lock'), 'w').write(json.dumps(lock, indent=2) + '\n')
    subprocess.run(['git', '-C', tmp, 'add', '-A'], check=True)
    ns = subprocess.run(['git', '-C', tmp, 'diff', '--cached', '--numstat'], capture_output=True, text=True).stdout.strip().splitlines()
    per = {l.split('\t')[2]: (l.split('\t')[0], l.split('\t')[1]) for l in ns}
    tot_a = sum(int(x[0]) for x in per.values() if x[0].isdigit()); tot_d = sum(int(x[1]) for x in per.values() if x[1].isdigit())
    rep['diff'] = per; rep['diff_total'] = '+%d/-%d' % (tot_a, tot_d)
    rows.append(rep)
    if not a.keep: shutil.rmtree(tmp)
STANDARD = ('hosted config replaces', 'write guards:', 'rail overlay code new (dormant')
WAIT = {e['room']: e.get('waitFor', []) for e in cfg['rooms']}
def room_risks(r): return [x for x in r['risks'] if not x.startswith(STANDARD)]
def cell(r):
    if not r['ok']: return 'BLOCKED'
    if WAIT.get(r['room']): return 'WAIT'
    return 'RISKY' if room_risks(r) else 'CLEAN'
md = ['| # | Room | Cluster | Result | factory.js | site.json | index.html | Blockers / risky diffs | Cleanup (separate PR) |', '|---|---|---|---|---|---|---|---|---|']
for i, r in enumerate(rows, 1):
    d = r['diff']; f = lambda k: ('+%s/-%s' % d[k]) if k in d else '0'
    why = '; '.join(['**' + b + '**' for b in r['blockers']] + (['wait: ' + '; '.join(WAIT[r['room']])] if r['ok'] and WAIT.get(r['room']) else []) + room_risks(r) + [c for c in r['changes'] if not c.startswith(('localStorage', 'Reddit'))])
    md.append('| %d | %s | %s | %s | %s | %s | %s | %s | %s |' % (i, r['room'], r['cluster'], cell(r), f('factory.js'), f('site.json'), f('index.html'), why.replace('|', '/'), ', '.join(r['cleanup']) or '-'))
head = ('Every stamp also carries the STANDARD changes: write guards (posts/DMs batch rateLimits, so Firestore rules step 1 must be live first), '
        'hosted Firebase config instead of the inline AIza key (16 rooms), dormant rail-overlay code, localStorage keys -> subx.user/subx.likes with a one-time migration, '
        'and the Reddit lock (redditCrosspost:false, redditSr dropped; 415chat/samochat keep theirs).\n'
        'CLEAN = no room-specific risk; RISKY = needs a look; WAIT = ready but gated on another change; BLOCKED = the stamp refuses.\n\n')
out = head + '\n'.join(md) + '\n'
if a.out: open(a.out, 'w').write(out); json.dump(rows, open(a.out.rsplit('.', 1)[0] + '.json', 'w'), indent=2)
print(out)
