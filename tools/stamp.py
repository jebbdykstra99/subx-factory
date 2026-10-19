#!/usr/bin/env python3
"""Stamp one room repo with the current factory release.

  python3 tools/stamp.py --room 27chat --repo-dir /path/to/27chat [--dry-run] [--json out.json] [--force-blocked]

Writes (inside --repo-dir, never pushes, never touches git history):
  factory.js            = factory/factory.js (identical bytes in every room)
  index.html            = factory.js?v=N+1, and site.json?v=M+1 (preload + every data-site) when site.json changes
  site.json             = deep-merge of rooms.json features / skin / sitePatch (room copy moves out of JS)
  FACTORY.lock          = release version + sha256 of factory.js and the room-pinned styles.css

Refuses (exit 2) when:
  - the room is status "blocked" in rooms.json (unless --force-blocked, for dry-runs only),
  - site.json siteId differs from rooms.json,
  - the room's current factory.js has functions the release lacks and they are not listed in rooms.json allowLoss
    (that is the "unlisted difference" lock; record it in EXCEPTIONS.md + rooms.json first),
  - the room has an extra .js file that is not in keepFiles (e.g. a new gate.js).
Exit 0 = stamped (or would stamp, with --dry-run). The report lists risky diffs for the PR body.
"""
import argparse, hashlib, json, os, re, shutil, subprocess, sys, tempfile, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from fnsplit import split

def sha(b): return hashlib.sha256(b).hexdigest()
def rd(p): return open(p, 'rb').read()
def fns(src): return [k for k, _ in split(src) if not k.startswith('#')]
DEAD = ['app.js', 'firestore.rules', 'storage.rules', 'firebase.indexes.json', 'RULES.md', 'nest_stubs.py']

def deep_merge(dst, src):
    for k, v in src.items():
        if k == '_dropKeys': continue
        if isinstance(v, dict) and isinstance(dst.get(k), dict): deep_merge(dst[k], v)
        else: dst[k] = v
    for k in src.get('_dropKeys', []): dst.pop(k, None)

def stamp(entry, release, repo, dry):
    rep = {'room': entry['room'], 'cluster': entry['cluster'], 'status': entry['status'], 'blockers': [], 'risks': [], 'cleanup': [], 'changes': []}
    old_js = rd(os.path.join(repo, 'factory.js')).decode()
    rel_js = release['factory'].decode()
    site_p = os.path.join(repo, 'site.json'); site_raw = rd(site_p).decode(); site = json.loads(site_raw)
    if site.get('siteId') != entry['siteId']:
        rep['blockers'].append('siteId mismatch: site.json %r vs rooms.json %r' % (site.get('siteId'), entry['siteId']))
    rel_fns = set(fns(rel_js)); lost = [f for f in fns(old_js) if f not in rel_fns]
    unl = [f for f in lost if f not in entry.get('allowLoss', [])]
    if unl: rep['blockers'].append('%d room-only functions would be deleted (not in allowLoss): %s' % (len(unl), ', '.join(unl[:12]) + (' …' if len(unl) > 12 else '')))
    if entry['status'] == 'blocked': rep['blockers'].insert(0, 'rooms.json status blocked: ' + '; '.join(entry.get('waitFor', [])))
    extra_js = sorted(f for f in os.listdir(repo) if f.endswith('.js') and f not in ('factory.js', 'app.js'))
    for f in extra_js:
        if f not in entry.get('keepFiles', []): rep['blockers'].append('unlisted extra file %s (add to keepFiles + EXCEPTIONS.md)' % f)
    rep['cleanup'] = [f for f in DEAD if os.path.exists(os.path.join(repo, f))]
    # risky diffs (user-visible)
    if 'AIza' in old_js: rep['risks'].append('hosted config replaces inline AIza key (runtime fetch of subx-skins.web.app/firebase-web-config.json)')
    if 'function sendPixel' not in old_js and entry['sitePatch'].get('pixel') is not False: rep['risks'].append('visit pixel NEW for this room')
    if 'function overlayCfg' not in old_js:
        rep['risks'].append('rail overlay code new' + (' and ENABLED by site.json' if (site.get('rail') or {}).get('overlay', {}).get('enabled') else ' (dormant: rail.overlay not enabled)'))
    if 'rateLimits' not in old_js: rep['risks'].append('write guards: posts/DMs now batch rateLimits; requires Firestore rules step 1 published BEFORE merge')
    if '.user\'' in old_js or 'LS_USER' in old_js: rep['changes'].append('localStorage keys -> subx.user/subx.likes (one-time migration from legacy keys)')
    if any(entry['features'].values()): rep['risks'].append('features ON: ' + ', '.join(k for k, v in entry['features'].items() if v))
    if lost and not unl: rep['changes'].append('allowLoss: ' + ', '.join(lost))
    # site.json patch
    new_site = json.loads(site_raw)
    patch = dict(entry.get('sitePatch', {}))
    if entry.get('features'): patch['features'] = entry['features']
    if entry.get('skin'): patch['skin'] = entry['skin']
    deep_merge(new_site, patch)
    if new_site.get('minAge') != site.get('minAge'): rep['risks'].append('minAge %s -> %s' % (site.get('minAge'), new_site.get('minAge')))
    if ('redditSr' in site) != ('redditSr' in new_site) or site.get('redditCrosspost') != new_site.get('redditCrosspost'): rep['changes'].append('Reddit flags: redditCrosspost:false, redditSr dropped (README lock R8)')
    site_changed = new_site != site
    indent = 2
    new_site_raw = json.dumps(new_site, indent=indent, ensure_ascii=False) + ('\n' if site_raw.endswith('\n') else '')
    # index.html cache-busts
    idx_p = os.path.join(repo, 'index.html'); idx = rd(idx_p).decode()
    m = re.search(r'factory\.js\?v=(\d+)', idx)
    if not m: rep['blockers'].append('index.html has no factory.js?v=N'); fv = None
    else:
        fv = int(m.group(1)) + 1; idx = re.sub(r'factory\.js\?v=\d+', 'factory.js?v=%d' % fv, idx)
    if site_changed:
        sm = re.search(r'site\.json\?v=(\d+)', idx)
        if sm: idx = re.sub(r'site\.json\?v=\d+', 'site.json?v=%d' % (int(sm.group(1)) + 1), idx)
    for needed in ('firebase-app-check-compat', 'firebase-storage-compat'):
        if needed not in idx: rep['blockers'].append('index.html lacks %s script' % needed)
    styles = rd(os.path.join(repo, 'styles.css')) if os.path.exists(os.path.join(repo, 'styles.css')) else b''
    lock = {'factory': 'jebbdykstra99/subx-factory', 'version': release['version'], 'room': entry['room'], 'siteId': entry['siteId'],
            'files': {'factory.js': sha(release['factory']), 'styles.css': sha(styles)},
            'keepFiles': entry.get('keepFiles', []), 'exceptions': 'see subx-factory EXCEPTIONS.md',
            'stampedAt': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
    rep['ok'] = not rep['blockers']
    if not dry and rep['ok']:
        open(os.path.join(repo, 'factory.js'), 'wb').write(release['factory'])
        open(idx_p, 'w').write(idx)
        if site_changed: open(site_p, 'w').write(new_site_raw)
        open(os.path.join(repo, 'FACTORY.lock'), 'w').write(json.dumps(lock, indent=2) + '\n')
    rep['factory_v'] = fv
    return rep, (release['factory'], idx, new_site_raw if site_changed else None, lock)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--room', required=True); ap.add_argument('--repo-dir', required=True)
    ap.add_argument('--dry-run', action='store_true'); ap.add_argument('--force-blocked', action='store_true')
    ap.add_argument('--json')
    a = ap.parse_args()
    cfg = json.load(open(os.path.join(ROOT, 'rooms.json')))
    entry = next((e for e in cfg['rooms'] if e['room'] == a.room), None)
    if not entry: sys.exit('room not in rooms.json: ' + a.room)
    release = {'factory': rd(os.path.join(ROOT, 'factory', 'factory.js')), 'version': cfg['version']}
    if a.force_blocked and not a.dry_run: sys.exit('--force-blocked is for --dry-run only')
    rep, _ = stamp(entry, release, a.repo_dir, a.dry_run)
    if a.force_blocked and entry['status'] == 'blocked': pass
    if a.json: json.dump(rep, open(a.json, 'w'), indent=2)
    print(json.dumps(rep, indent=2))
    sys.exit(0 if rep['ok'] else 2)

if __name__ == '__main__':
    main()
