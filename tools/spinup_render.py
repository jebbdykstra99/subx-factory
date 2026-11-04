#!/usr/bin/env python3
"""Spin-up dry run: render one site.json per candidate domain from spinup/candidates.json. CONFIG ONLY, never served.

  python3 tools/spinup_render.py --check [--exclusions FILE]   render into a temp dir, validate, drift --strict, compare plan
  python3 tools/spinup_render.py --out DIR [--exclusions FILE] write DIR/<domain>/site.json (DIR may not be inside the repo,
                                                               except a real, non-symlink spinup/out/, which is git-ignored)
  python3 tools/spinup_render.py --plan [--write]              print (or write) spinup/plan.json, the reviewed summary
  python3 tools/spinup_render.py --redirects [--now ISO]       print the planned doorway edge rules (302 / 301) to stdout

Rules (same site.json fields as topics/site_mode.schema.json; topic_domains.validate_fields is the validator):
  - every candidate gets mode doorway|parked|room; a candidate with no mode takes defaults.mode (parked)
  - a doorway needs a topic slug that passes tools/topic_slug.py (reserved words incl. platform names, fullmatch)
  - mode room only for a domain a live room already serves (hub/src/rooms.json); a live room domain is never a candidate
  - a candidate also in topics/domains.json must keep that file's mode and topic
  - names held for legal or trademark review are NOT in the repo in any form (no name, no hash: a hash of a short
    domain is reversible by guessing). candidates.json carries only excludedByReason counts; the reviewed list lives
    off-repo and, when passed with --exclusions FILE (one "domain | reason" per line), any candidate on it is refused
  - a 64-hex string anywhere in candidates.json is refused (no hashes of held names)
  - a domain label that is a platform word (or that word + "chat") is refused
  - brand is a key into brand/brand.json ("default"); no literal brand name, contact detail or address in output
Doorways would redirect https://<domain>/* to {{brand.primaryDomain}}{{brand.topicPathPrefix}}<slug>/?via=<domain>, 302 while
the topic is not established (hidden, eligible, quiet or not seeded yet) and 301 once active 60 days
(tools/topic_status.py doorway_status). That status is computed, never written into site.json, and nothing here
creates a redirect file, touches DNS, a registrar, a room repo or hub/.
"""
import argparse, json, os, re, subprocess, sys, tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import topic_domains, topic_slug, topic_status  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES = os.path.join(ROOT, 'spinup', 'candidates.json')
PLAN = os.path.join(ROOT, 'spinup', 'plan.json')
OUT_OK = os.path.join(ROOT, 'spinup', 'out')
MODES = ('room', 'doorway', 'parked')
SITE_KEYS = ('domain', 'mode', 'topic', 'brand', 'doorway')
DOMAIN_RE = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+')
HEX64 = re.compile(r'[0-9a-fA-F]{64}')
# hard rules: nothing private may land in a rendered file (the candidate list itself is public registrations)
FORBIDDEN = re.compile(r'jebb|j@subx|@gmail|\(?\b310\)?[-. ]\d{3}[-. ]\d{4}|registered agent|denver,? *co\b|'
                       r'peekai|dmca-?\d', re.I)


def load(p):
    return json.load(open(p, encoding='utf-8'))


def load_exclusions(path):
    """Off-repo list: one 'domain | reason | ...' per line; blank lines and lines without a domain are ignored."""
    out = set()
    if not path:
        return out
    for line in open(path, encoding='utf-8'):
        d = line.split('|')[0].strip().lower()
        if DOMAIN_RE.fullmatch(d):
            out.add(d)
    return out


def brand_literals(brand):
    vals = [brand.get(k) for k in ('name', 'shortName', 'legalEntity', 'primaryDomain', 'takedownEmail',
                                   'contactPhone', 'mailingAddress')]
    return [v.lower() for v in vals if isinstance(v, str) and len(v) >= 4]


def resolve(cfg=None, seed=None, rooms=None, existing=None, brand=None, exclusions=None, raw=None):
    """Return (entries, errors). entries: [{domain, mode, topic?, ownership?}] sorted by domain."""
    if cfg is None:
        raw = open(CANDIDATES, encoding='utf-8').read()
        cfg = json.loads(raw)
    raw = raw if raw is not None else json.dumps(cfg)
    seed = seed if seed is not None else load(topic_domains.SEED)
    rooms = rooms if rooms is not None else topic_domains.room_domains()
    existing = existing if existing is not None else {x['domain']: x for x in load(topic_domains.DOMAINS)['domains']}
    brand = brand if brand is not None else load(topic_domains.BRANDS['default'])
    exclusions = exclusions or set()
    words = topic_slug.reserved(brand)
    platform = set(load(os.path.join(ROOT, 'topics', 'reserved.json')).get('platform', []))
    defaults = cfg.get('defaults') or {}
    dmode = defaults.get('mode', 'parked')
    e, out, seen = [], [], set()
    if HEX64.search(raw):
        e.append('candidates.json carries a 64-hex string; held names may not appear in any form (no hashes)')
    if 'excluded' in cfg:
        e.append('candidates.json may not list excluded names; record only excludedByReason counts')
    if dmode != 'parked':
        e.append('defaults.mode must be parked (unknown domains are parked), not %r' % (dmode,))
    if defaults.get('brand', 'default') != 'default':
        e.append('defaults.brand must be "default" (a key into brand/brand.json)')
    ebr = cfg.get('excludedByReason', {})
    if not isinstance(ebr, dict) or not all(isinstance(k, str) and k.strip() and type(v) is int and v > 0 for k, v in ebr.items()):
        e.append('excludedByReason must map a reason to a positive count')
        ebr = {}
    inv = (cfg.get('source') or {}).get('inventory')
    if type(inv) is not int or inv != len(cfg.get('candidates', [])) + sum(ebr.values()):
        e.append('source.inventory (%r) must equal candidates (%d) + excludedByReason (%d)'
                 % (inv, len(cfg.get('candidates', [])), sum(ebr.values())))
    for c in cfg.get('candidates', []):
        d = c.get('domain') if isinstance(c, dict) else None
        if not isinstance(d, str) or not d.isascii() or not DOMAIN_RE.fullmatch(d):
            e.append('candidate domain %r is not a lowercase domain' % (d,))
            continue
        w = 'candidate %s' % d
        if d in seen:
            e.append('%s: listed twice' % w)
        seen.add(d)
        if d in exclusions:
            e.append('%s: on the off-repo exclusion list; remove it from candidates' % w)
            continue
        label = d.split('.')[0]
        if label in platform or (label.endswith('chat') and label[:-4] in platform):
            e.append('%s: label names a platform word; it may not be spun up' % w)
            continue
        mode = c.get('mode', dmode)
        if mode not in MODES:
            e.append('%s: mode %r is not room|doorway|parked' % (w, mode))
            continue
        topic = c.get('topic')
        if mode == 'doorway':
            if not topic:
                e.append('%s: a doorway needs a topic slug' % w)
                continue
            se = topic_slug.errors(topic, words=words)
            if se:
                e.append('%s: %s' % (w, '; '.join(se)))
                continue
        if topic is not None and mode != 'doorway' and not isinstance(topic, str):
            e.append('%s: topic must be a slug' % w)
            continue
        if mode == 'room' and d not in rooms:
            e.append('%s: mode room but no live room serves it' % w)
        if mode != 'room' and d in rooms:
            e.append('%s: a live room serves it; live rooms are not spin-up candidates' % w)
        old = existing.get(d)
        if old and (old['mode'] != mode or old.get('topic') != topic):
            e.append('%s: topics/domains.json has %s/%s, candidates say %s/%s' % (w, old['mode'], old.get('topic'), mode, topic))
        ent = {'domain': d, 'mode': mode}
        if topic:
            ent['topic'] = topic
        if c.get('ownership'):
            ent['ownership'] = c['ownership']
        out.append(ent)
    topics = {t['slug']: t for t in seed['topics']}
    for ent in out:
        t = topics.get(ent.get('topic'))
        if ent['mode'] == 'doorway' and t is not None and t['status'] == 'hold':
            e.append('candidate %s: doorway to a HOLD topic; park or exclude it' % ent['domain'])
    out.sort(key=lambda x: x['domain'])
    return out, e


def site_json(ent, cfg=None):
    cfg = cfg if cfg is not None else load(CANDIDATES)
    d = cfg.get('defaults') or {}
    s = {'domain': ent['domain'], 'mode': ent['mode']}
    if ent.get('topic'):
        s['topic'] = ent['topic']
    s['brand'] = d.get('brand', 'default')
    if ent['mode'] == 'doorway':
        s['doorway'] = dict(d.get('doorway') or {'style': 'redirect', 'keepQuery': False})
    return s


def dump(o):
    return json.dumps(o, indent=2, ensure_ascii=True) + '\n'


def plan(entries, cfg=None, seed=None):
    cfg = cfg if cfg is not None else load(CANDIDATES)
    seed = seed if seed is not None else load(topic_domains.SEED)
    seeded = {t['slug'] for t in seed['topics']}
    counts = {m: 0 for m in MODES}
    rows = []
    for ent in entries:
        counts[ent['mode']] += 1
        r = {'domain': ent['domain'], 'mode': ent['mode']}
        if ent.get('topic'):
            r['topic'] = ent['topic']
            if ent['mode'] == 'doorway':
                r['topicSeeded'] = ent['topic'] in seeded
        if ent.get('ownership'):
            r['ownership'] = ent['ownership']
        rows.append(r)
    ebr = cfg.get('excludedByReason', {})
    return {'notes': 'DRY RUN PLAN (generated by tools/spinup_render.py --plan --write). Not served. One row per rendered '
                     'site.json; doorway status (302/301) is computed at serve time by tools/topic_status.py doorway_status. '
                     'Excluded names are not listed (counts by reason only).',
            'inventory': (cfg.get('source') or {}).get('inventory'),
            'rendered': len(rows), 'excluded': sum(ebr.values()), 'byMode': counts,
            'doorwaysNeedingTopicRow': sum(1 for r in rows if r.get('topicSeeded') is False),
            'excludedByReason': dict(sorted(ebr.items())), 'domains': rows}


def output_errors(path, text, brand):
    e = []
    m = FORBIDDEN.search(text)
    if m:
        e.append('%s: forbidden string %r' % (path, m.group(0)))
    low = text.lower()
    for lit in brand_literals(brand):
        if lit in low:
            e.append('%s: literal brand string %r (use the brand key)' % (path, lit))
    return e


def _inside(path, base):
    return path == base or path.startswith(os.path.join(base, ''))


def out_dir_ok(out):
    """P2: resolve with realpath. Outside the repo is fine. A path that is (or resolves) inside the repo must resolve
    under a real, non-symlink spinup/out/ (spinup/ itself not a symlink either)."""
    real = os.path.realpath(out)
    root = os.path.realpath(ROOT)
    lexical = os.path.abspath(out)
    if not _inside(real, root) and not _inside(lexical, os.path.abspath(ROOT)) and not _inside(lexical, root):
        return True
    for p in (os.path.join(ROOT, 'spinup'), OUT_OK):
        if os.path.islink(p):
            return False
    return _inside(real, os.path.join(root, 'spinup', 'out'))


def render(entries, out, cfg=None, brand=None):
    """Write out/<domain>/site.json; return the list of room dirs and the errors."""
    brand = brand if brand is not None else load(topic_domains.BRANDS['default'])
    if not out_dir_ok(out):
        return [], ['--out %s resolves inside the repo (or hub/); use a real spinup/out/ or a dir outside the repo' % out]
    dirs, e = [], []
    base = os.path.realpath(out)
    for ent in entries:
        d = os.path.join(out, ent['domain'])
        if os.path.islink(d) or (os.path.exists(d) and not os.path.isdir(d)):
            e.append('%s exists and is not a plain dir' % d)
            continue
        os.makedirs(d, exist_ok=True)
        if os.path.dirname(os.path.realpath(d)) != base:
            e.append('%s resolves outside %s' % (d, out))
            continue
        p = os.path.join(d, 'site.json')
        if os.path.islink(p):
            e.append('%s is a symlink' % p)
            continue
        s = site_json(ent, cfg)
        text = dump(s)
        e += topic_domains.validate_fields(s, p)
        e += output_errors(p, text, brand)
        open(p, 'w', encoding='utf-8').write(text)
        dirs.append(d)
    return dirs, e


def drift(dirs):
    if not dirs:
        return []
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'shell_drift.py')] + dirs + ['--strict'],
                       capture_output=True, text=True)
    if r.returncode != 0:
        bad = [ln for ln in r.stdout.splitlines() if '| DRIFT |' in ln] or [r.stderr.strip() or 'drift failed']
        return ['drift --strict: ' + b for b in bad]
    return []


def check(exclusions=None):
    raw = open(CANDIDATES, encoding='utf-8').read()
    cfg = json.loads(raw)
    entries, e = resolve(cfg, exclusions=exclusions, raw=raw)
    with tempfile.TemporaryDirectory(prefix='spinup-dryrun-') as tmp:
        dirs, e2 = render(entries, tmp, cfg)
        e += e2
        if not e:
            e += drift(dirs)
            vr = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'topic_domains.py'), '--validate-site'] +
                                [os.path.join(x, 'site.json') for x in dirs], capture_output=True, text=True)
            if vr.returncode != 0:
                e.append('topic_domains --validate-site: ' + vr.stdout.strip())
    p = plan(entries, cfg)
    if not os.path.isfile(PLAN) or open(PLAN, encoding='utf-8').read() != dump(p):
        e.append('spinup/plan.json is not what --plan generates (run --plan --write)')
    elif HEX64.search(open(PLAN, encoding='utf-8').read()):
        e.append('spinup/plan.json carries a 64-hex string')
    return entries, p, e


def redirects(entries, now, seed=None):
    seed = seed if seed is not None else load(topic_domains.SEED)
    topics = {t['slug']: t for t in seed['topics']}
    lines = []
    for ent in entries:
        if ent['mode'] != 'doorway':
            lines.append('# %s: mode %s, no redirect' % (ent['domain'], ent['mode']))
            continue
        t = topics.get(ent['topic'], {'status': 'hidden'})  # not seeded yet = hidden: 302
        lines.append('https://%s/*  https://{{brand.primaryDomain}}{{brand.topicPathPrefix}}%s/?via=%s  %d'
                     % (ent['domain'], ent['topic'], ent['domain'], topic_status.doorway_status(t, now)))
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--out')
    ap.add_argument('--plan', action='store_true')
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--redirects', action='store_true')
    ap.add_argument('--now')
    ap.add_argument('--exclusions', help='off-repo exclusion list (never committed)')
    a = ap.parse_args(argv)
    excl = load_exclusions(a.exclusions)
    if a.plan or a.redirects:
        entries, e = resolve(exclusions=excl)
        if e:
            print('\n'.join('FAIL ' + x for x in e), file=sys.stderr)
            return 1
        if a.plan:
            text = dump(plan(entries))
            if a.write:
                open(PLAN, 'w', encoding='utf-8').write(text)
                print('wrote spinup/plan.json')
            else:
                sys.stdout.write(text)
            return 0
        now = a.now or datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        print('# PLAN ONLY (not served): spin-up doorway edge rules at %s' % now)
        print('\n'.join(redirects(entries, now)))
        return 0
    if a.out:
        entries, e = resolve(exclusions=excl)
        if not e:
            dirs, e = render(entries, a.out)
            e += drift(dirs)
        if e:
            print('\n'.join('FAIL ' + x for x in e), file=sys.stderr)
            return 1
        print('rendered %d site.json files into %s (dry run, not served)' % (len(entries), a.out))
        return 0
    entries, p, e = check(excl)
    if e:
        print('\n'.join('FAIL ' + x for x in e), file=sys.stderr)
        return 1
    print('spin-up dry run OK: %d rendered of %s inventory, %d excluded, by mode %s, %d doorways need a topic row; '
          'drift --strict and --validate-site clean%s, nothing written'
          % (p['rendered'], p['inventory'], p['excluded'], p['byMode'], p['doorwaysNeedingTopicRow'],
             ', exclusion list checked (%d names)' % len(excl) if excl else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
