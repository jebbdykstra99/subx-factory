#!/usr/bin/env python3
"""Wave-1 topic seed: topics/seed_wave1.json (one row per topic for Firestore collection `topics`, schema topics/schema.json).

  python3 tools/topics_seed.py                      DRY RUN (default): validate the seed and print the writes it WOULD make
  python3 tools/topics_seed.py --check              validate only (CI): schema, slug rules, reserved words, seed invariants
  python3 tools/topics_seed.py --from-csv CSV       rebuild the seed from the wave-1 CSV and compare (add --write to save)
  python3 tools/topics_seed.py --from-agency-md MD   rebuild topics/seed_wave2_agency.json from the agency-topics draft
                                                    (its slug,title,description,doorway_domains block) and compare
                                                    (add --write to save)
  python3 tools/topics_seed.py --apply              REFUSED unless SUBX_TOPICS_APPLY_GO is set; this PR never writes
                                                    Firestore, so even with the variable set it stops before any write

Seed invariants: every topic starts with zero stats and no activatedAt; HOLD topics (topics/wave1_profiles.json "hold")
get status "hold" and stewardOnly true (never rendered); every other topic starts "hidden". Python stdlib only.

Wave-2 agency seed (topics/seed_wave2_agency.json): topics reached by a doorway named after a government agency. Same
row format and invariants (hidden, zero stats, no approval record), plus govNonAffiliation true on every row: the topic
page then shows {{brand.nonAffiliationGov}} under the title and in the footer (hub/src/topic-template.html if:gov).
Its slugs and doorway domains may not repeat wave 1. It is not in hub/src/config.json "topics.seed", so nothing in
hub/site renders from it yet.
"""
import argparse, csv, hashlib, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import topic_schema, topic_slug  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED = os.path.join(ROOT, 'topics', 'seed_wave1.json')
AGENCY_SEED = os.path.join(ROOT, 'topics', 'seed_wave2_agency.json')
SCHEMA = os.path.join(ROOT, 'topics', 'schema.json')
APPROVED = os.path.join(ROOT, 'topics', 'approved_waves.json')
APPROVED_SCHEMA = os.path.join(ROOT, 'topics', 'approved_waves.schema.json')
PROFILES = os.path.join(ROOT, 'topics', 'wave1_profiles.json')
CREATED_AT = '2026-11-03T07:00:00Z'  # 2026-11-03 00:00 MT: fixed so the seed is reproducible
APPLY_ENV = 'SUBX_TOPICS_APPLY_GO'


def load(p):
    return json.load(open(p, encoding='utf-8'))


def build(csv_path, created_at=CREATED_AT):
    raw = open(csv_path, 'rb').read()
    prof = load(PROFILES)
    rows = list(csv.DictReader(raw.decode('utf-8').splitlines()))
    topics = []
    for r in rows:
        slug = r['slug'].strip()
        doors = [d.strip().lower() for d in re.split(r'[;| ]+', r.get('doorway_domains') or '') if d.strip()]
        hold = slug in prof['hold']
        t = {'slug': slug, 'title': r['title'].strip(), 'description': r['description'].strip(),
             'status': 'hold' if hold else 'hidden', 'createdAt': created_at, 'activatedAt': None,
             'posts14d': 0, 'distinctPosters14d': 0, 'posts30d': 0, 'lastCountedPostAt': None,
             'doorwayDomains': doors, 'stewardOnly': hold}
        if slug in prof['legalProfile']:
            t['legalProfile'] = prof['legalProfile'][slug]
        topics.append(t)
    return {'collection': 'topics', 'wave': 1,
            'source': {'file': os.path.basename(csv_path), 'md5': hashlib.md5(raw).hexdigest(), 'rows': len(rows)},
            'generatedBy': 'tools/topics_seed.py --from-csv', 'topics': topics}


def build_agency(md_path, created_at=CREATED_AT):
    """Wave-2 agency seed from the agency-topics draft: the CSV block that starts with its slug,title,... header."""
    raw = open(md_path, 'rb').read()
    lines = raw.decode('utf-8').splitlines()
    i = next(n for n, ln in enumerate(lines) if ln.strip() == 'slug,title,description,doorway_domains')
    block = []
    for ln in lines[i:]:
        if not ln.strip():
            break
        block.append(ln)
    topics = []
    for r in csv.DictReader(block):
        doors = [d.strip().lower() for d in re.split(r'[;|, ]+', r.get('doorway_domains') or '') if d.strip()]
        topics.append({'slug': r['slug'].strip(), 'title': r['title'].strip(), 'description': r['description'].strip(),
                       'status': 'hidden', 'createdAt': created_at, 'activatedAt': None,
                       'posts14d': 0, 'distinctPosters14d': 0, 'posts30d': 0, 'lastCountedPostAt': None,
                       'doorwayDomains': doors, 'stewardOnly': False, 'legalProfile': 'standard-18',
                       'govNonAffiliation': True})
    return {'collection': 'topics', 'wave': 2,
            'source': {'file': os.path.basename(md_path), 'md5': hashlib.md5(raw).hexdigest(), 'rows': len(topics)},
            'generatedBy': 'tools/topics_seed.py --from-agency-md', 'topics': topics}


def check_agency(seed2, seed1=None, brand=None):
    """Wave-2 agency seed: schema, slug rules, hidden, zero stats, no approval, govNonAffiliation, no overlap with wave 1."""
    seed1 = seed1 if seed1 is not None else load(SEED)
    sch = load(SCHEMA)
    words = topic_slug.reserved(brand)
    e = []
    if seed2.get('collection') != 'topics' or seed2.get('wave') != 2:
        e.append('agency seed must be collection "topics", wave 2')
    s1 = {t['slug'] for t in seed1['topics']}
    d1 = {d for t in seed1['topics'] for d in t['doorwayDomains']}
    seen, doors = set(), {}
    for t in seed2.get('topics', []):
        w = 'agency topic %s' % t.get('slug')
        e += ['%s: %s' % (w, x) for x in topic_schema.validate(t, sch)]
        e += ['%s: %s' % (w, x) for x in topic_slug.errors(t.get('slug'), words=words)]
        if t.get('slug') in seen or t.get('slug') in s1:
            e.append('%s: duplicate slug (or already in wave 1)' % w)
        seen.add(t.get('slug'))
        for d in t.get('doorwayDomains', []):
            if d in doors or d in d1:
                e.append('%s: doorway %s already belongs to another topic' % (w, d))
            doors[d] = t.get('slug')
        if not t.get('doorwayDomains'):
            e.append('%s: an agency topic is reached by at least one doorway' % w)
        if t.get('status') != 'hidden' or t.get('stewardOnly') is not False:
            e.append('%s: an agency seed row starts hidden with stewardOnly false' % w)
        if any(t.get(k) for k in ('posts14d', 'distinctPosters14d', 'posts30d')) or t.get('activatedAt') or t.get('lastCountedPostAt'):
            e.append('%s: a seed row must start with zero stats' % w)
        if any(t.get(k) is not None for k in ('approvedWave', 'approvedBy', 'approvedAt')):
            e.append('%s: a seed row must not carry an approval record' % w)
        if t.get('govNonAffiliation') is not True:
            e.append('%s: govNonAffiliation must be true (page shows brand.nonAffiliationGov)' % w)
        if re.search('[\u2013\u2014]', t.get('title', '') + t.get('description', '')):
            e.append('%s: no dashes in title or description' % w)
    if seed2.get('source', {}).get('rows') != len(seed2.get('topics', [])):
        e.append('agency seed row count does not match source rows')
    return e


def all_topics_seed():
    """Wave 1 plus the wave-2 agency rows (if the file exists), as one seed dict for lookups."""
    s = load(SEED)
    if os.path.exists(AGENCY_SEED):
        s = dict(s, topics=s['topics'] + load(AGENCY_SEED)['topics'])
    return s


def dump(seed):
    return json.dumps(seed, indent=2, ensure_ascii=False) + '\n'


def check(seed, brand=None):
    e = []
    sch = load(SCHEMA)
    words = topic_slug.reserved(brand)
    prof = load(PROFILES)
    if seed.get('collection') != 'topics':
        e.append('seed collection must be "topics"')
    seen, doors = set(), {}
    for t in seed.get('topics', []):
        w = 'topic %s' % t.get('slug')
        e += ['%s: %s' % (w, x) for x in topic_schema.validate(t, sch)]
        e += ['%s: %s' % (w, x) for x in topic_slug.errors(t.get('slug'), words=words)]
        if t.get('slug') in seen:
            e.append('%s: duplicate slug' % w)
        seen.add(t.get('slug'))
        for d in t.get('doorwayDomains', []):
            if d in doors:
                e.append('%s: doorway %s already belongs to %s' % (w, d, doors[d]))
            doors[d] = t.get('slug')
        want = 'hold' if t.get('slug') in prof['hold'] else 'hidden'
        if t.get('status') != want:
            e.append('%s: a wave-1 seed row must start %s (got %s)' % (w, want, t.get('status')))
        if any(t.get(k) for k in ('posts14d', 'distinctPosters14d', 'posts30d')) or t.get('activatedAt') or t.get('lastCountedPostAt'):
            e.append('%s: a seed row must start with zero stats' % w)
        if any(t.get(k) is not None for k in ('approvedWave', 'approvedBy', 'approvedAt')):
            e.append('%s: a seed row must not carry an approval record' % w)
        if t.get('stewardOnly') is not (want == 'hold'):
            e.append('%s: stewardOnly must be %s' % (w, want == 'hold'))
    for h in prof['hold']:
        if h not in seen:
            e.append('HOLD topic %s is not in the seed' % h)
    aw = load(APPROVED)
    e += ['approved_waves.json: %s' % x for x in topic_schema.validate(aw, load(APPROVED_SCHEMA))]
    if seed.get('source', {}).get('rows') != len(seed.get('topics', [])):
        e.append('seed row count does not match source rows')
    return e


def summary(seed):
    st = {}
    for t in seed['topics']:
        st[t['status']] = st.get(t['status'], 0) + 1
    return st


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--from-csv')
    ap.add_argument('--from-agency-md')
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args(argv)
    if a.apply:
        if not os.environ.get(APPLY_ENV):
            print('REFUSED: --apply needs %s set (and an explicit owner go). Nothing written.' % APPLY_ENV, file=sys.stderr)
            return 3
        print('REFUSED: this tool has no Firestore writer in this PR; the seed is applied by a separately reviewed '
              'migration. Nothing written.', file=sys.stderr)
        return 4
    if a.from_csv:
        seed = build(a.from_csv)
        cur = open(SEED, encoding='utf-8').read() if os.path.exists(SEED) else ''
        if a.write:
            open(SEED, 'w', encoding='utf-8').write(dump(seed))
            print('wrote %s (%d topics: %s)' % (os.path.relpath(SEED, ROOT), len(seed['topics']), summary(seed)))
        elif cur != dump(seed):
            print('DIFF: %s is not what %s builds' % (os.path.relpath(SEED, ROOT), a.from_csv), file=sys.stderr)
            return 1
        else:
            print('seed matches %s (md5 %s)' % (a.from_csv, seed['source']['md5']))
    if a.from_agency_md:
        s2 = build_agency(a.from_agency_md)
        cur = open(AGENCY_SEED, encoding='utf-8').read() if os.path.exists(AGENCY_SEED) else ''
        if a.write:
            open(AGENCY_SEED, 'w', encoding='utf-8').write(dump(s2))
            print('wrote %s (%d topics)' % (os.path.relpath(AGENCY_SEED, ROOT), len(s2['topics'])))
        elif cur != dump(s2):
            print('DIFF: %s is not what %s builds' % (os.path.relpath(AGENCY_SEED, ROOT), a.from_agency_md), file=sys.stderr)
            return 1
        else:
            print('agency seed matches %s (md5 %s)' % (a.from_agency_md, s2['source']['md5']))
    seed = load(SEED)
    errs = check(seed)
    if os.path.exists(AGENCY_SEED):
        s2 = load(AGENCY_SEED)
        errs += check_agency(s2, seed)
        if not errs:
            print('agency seed OK: %d topics %s, source md5 %s' % (len(s2['topics']), summary(s2), s2['source']['md5']))
    if errs:
        print('\n'.join('FAIL ' + x for x in errs), file=sys.stderr)
        return 1
    print('seed OK: %d topics %s, source md5 %s' % (len(seed['topics']), summary(seed), seed['source']['md5']))
    if not a.check and not a.from_csv:
        print('DRY RUN (no Firestore access, nothing written). Would create-if-absent in collection "%s":' % seed['collection'])
        for t in seed['topics']:
            print('  topics/%s  status=%s  doorways=%s' % (t['slug'], t['status'], ','.join(t['doorwayDomains']) or '-'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
