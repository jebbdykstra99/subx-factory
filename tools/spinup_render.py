#!/usr/bin/env python3
"""Spin-up dry run: render one site.json per candidate domain from spinup/candidates.json. CONFIG ONLY, never served.

  python3 tools/spinup_render.py --check                 render into a temp dir, validate, drift --strict, compare plan
  python3 tools/spinup_render.py --out DIR               write DIR/<domain>/site.json (DIR may not be in hub/ or the repo,
                                                         except the git-ignored spinup/out/)
  python3 tools/spinup_render.py --plan [--write]        print (or write) spinup/plan.json, the reviewed summary
  python3 tools/spinup_render.py --redirects [--now ISO] print the planned doorway edge rules (302 / 301) to stdout

Rules (same site.json fields as topics/site_mode.schema.json; topic_domains.validate_fields is the validator):
  - every candidate gets mode doorway|parked|room; a candidate with no mode takes defaults.mode (parked)
  - a doorway needs a topic slug that passes tools/topic_slug.py (reserved words incl. platform names, fullmatch)
  - mode room only for a domain a live room already serves (hub/src/rooms.json); a live room domain is never a candidate
  - a candidate also in topics/domains.json must keep that file's mode and topic
  - excluded domains (holds, brand reserves, possible personal names) are listed by sha256 only and may not be candidates;
    a domain label that is a platform word (or that word + "chat") is refused
  - brand is a key into brand/brand.json ("default"); no literal brand name, contact detail or address in output
Doorways would redirect https://<domain>/* to {{brand.primaryDomain}}{{brand.topicPathPrefix}}<slug>/?via=<domain>, 302 while
the topic is not established (hidden, eligible, quiet or not seeded yet) and 301 once active 60 days
(tools/topic_status.py doorway_status). That status is computed, never written into site.json, and nothing here
creates a redirect file, touches DNS, a registrar, a room repo or hub/.
"""
import argparse, hashlib, json, os, re, subprocess, sys, tempfile
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
# hard rules: nothing private or barred may land in a rendered file (the domain list itself is public registrations)
FORBIDDEN = re.compile(r'jebb|j@subx|@gmail|\(?\b310\)?[-. ]\d{3}[-. ]\d{4}|registered agent|denver,? *co\b|'
                       r'peekai|vokadots|vocadots|dmca-?\d', re.I)


def load(p):
    return json.load(open(p, encoding='utf-8'))


def sha(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def brand_literals(brand):
    vals = [brand.get(k) for k in ('name', 'shortName', 'legalEntity', 'primaryDomain', 'takedownEmail',
                                   'contactPhone', 'mailingAddress')]
    return [v.lower() for v in vals if isinstance(v, str) and len(v) >= 4]


def resolve(cfg=None, seed=None, rooms=None, existing=None, brand=None):
    """Return (entries, errors). entries: [{domain, mode, topic?, ownership?}] sorted by domain."""
    cfg = cfg if cfg is not None else load(CANDIDATES)
    seed = seed if seed is not None else load(topic_domains.SEED)
    rooms = rooms if rooms is not None else topic_domains.room_domains()
    existing = existing if existing is not None else {x['domain']: x for x in load(topic_domains.DOMAINS)['domains']}
    brand = brand if brand is not None else load(topic_domains.BRANDS['default'])
    words = topic_slug.reserved(brand)
    platform = set(load(os.path.join(ROOT, 'topics', 'reserved.json')).get('platform', []))
    defaults = cfg.get('defaults') or {}
    dmode = defaults.get('mode', 'parked')
    e, out, seen = [], [], set()
    if dmode != 'parked':
        e.append('defaults.mode must be parked (unknown domains are parked), not %r' % (dmode,))
    if defaults.get('brand', 'default') != 'default':
        e.append('defaults.brand must be "default" (a key into brand/brand.json)')
    excl = {}
    for x in cfg.get('excluded', []):
        h = x.get('sha256') if isinstance(x, dict) else None
        if not (isinstance(h, str) and re.fullmatch(r'[0-9a-f]{64}', h)) or not str(x.get('reason', '')).strip():
            e.append('excluded entry needs a sha256 and a reason: %r' % (x,))
            continue
        excl[h] = x['reason']
    for c in cfg.get('candidates', []):
        d = c.get('domain') if isinstance(c, dict) else None
        if not isinstance(d, str) or not d.isascii() or not DOMAIN_RE.fullmatch(d):
            e.append('candidate domain %r is not a lowercase domain' % (d,))
            continue
        w = 'candidate %s' % d
        if d in seen:
            e.append('%s: listed twice' % w)
        seen.add(d)
        if sha(d) in excl:
            e.append('%s: excluded (%s); remove it from candidates' % (w, excl[sha(d)]))
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
        r['siteJsonSha256'] = sha(dump(site_json(ent, cfg)))
        rows.append(r)
    reasons = {}
    for x in cfg.get('excluded', []):
        reasons[x['reason']] = reasons.get(x['reason'], 0) + 1
    return {'notes': 'DRY RUN PLAN (generated by tools/spinup_render.py --plan --write). Not served. One row per rendered '
                     'site.json; doorway status (302/301) is computed at serve time by tools/topic_status.py doorway_status.',
            'inventory': (cfg.get('source') or {}).get('inventory'),
            'rendered': len(rows), 'excluded': len(cfg.get('excluded', [])), 'byMode': counts,
            'doorwaysNeedingTopicRow': sum(1 for r in rows if r.get('topicSeeded') is False),
            'excludedByReason': dict(sorted(reasons.items())), 'domains': rows}


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


def out_dir_ok(out):
    real = os.path.realpath(out)
    root = os.path.realpath(ROOT)
    if real == root or real.startswith(os.path.join(root, '')):
        ok = os.path.realpath(OUT_OK)
        return real == ok or real.startswith(os.path.join(ok, ''))
    return True


def render(entries, out, cfg=None, brand=None):
    """Write out/<domain>/site.json; return the list of room dirs and the errors."""
    brand = brand if brand is not None else load(topic_domains.BRANDS['default'])
    if not out_dir_ok(out):
        return [], ['--out %s is inside the repo (or hub/); use spinup/out/ or a dir outside the repo' % out]
    dirs, e = [], []
    for ent in entries:
        d = os.path.join(out, ent['domain'])
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, 'site.json')
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


def check():
    cfg = load(CANDIDATES)
    entries, e = resolve(cfg)
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
    a = ap.parse_args(argv)
    if a.plan:
        entries, e = resolve()
        if e:
            print('\n'.join('FAIL ' + x for x in e), file=sys.stderr)
            return 1
        text = dump(plan(entries))
        if a.write:
            open(PLAN, 'w', encoding='utf-8').write(text)
            print('wrote spinup/plan.json')
        else:
            sys.stdout.write(text)
        return 0
    if a.redirects:
        entries, e = resolve()
        if e:
            print('\n'.join('FAIL ' + x for x in e), file=sys.stderr)
            return 1
        now = a.now or datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        print('# PLAN ONLY (not served): spin-up doorway edge rules at %s' % now)
        print('\n'.join(redirects(entries, now)))
        return 0
    if a.out:
        entries, e = resolve()
        if not e:
            dirs, e = render(entries, a.out)
            e += drift(dirs)
        if e:
            print('\n'.join('FAIL ' + x for x in e), file=sys.stderr)
            return 1
        print('rendered %d site.json files into %s (dry run, not served)' % (len(entries), a.out))
        return 0
    entries, p, e = check()
    if e:
        print('\n'.join('FAIL ' + x for x in e), file=sys.stderr)
        return 1
    print('spin-up dry run OK: %d rendered of %s inventory, %d excluded, by mode %s, %d doorways need a topic row; '
          'drift --strict and --validate-site clean, nothing written'
          % (p['rendered'], p['inventory'], p['excluded'], p['byMode'], p['doorwaysNeedingTopicRow']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
