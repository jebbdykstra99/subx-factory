#!/usr/bin/env python3
"""Topic layer: slug rules + reserved words, the activity rule (tools/topic_status.py), the wave-1 seed and schema,
the hybrid domain config, and the --apply refusal. Python stdlib only."""
import json, os, re, subprocess, sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import topic_schema, topic_slug, topic_status as TS, topics_seed, topic_domains  # noqa: E402

fails = []
def ok(c, m):
    print(('ok   ' if c else 'FAIL ') + m)
    if not c:
        fails.append(m)

brand = json.load(open(os.path.join(ROOT, 'brand', 'brand.json')))
words = topic_slug.reserved(brand)

# ---- slugs ----
for s in ('grand-prix-racing', 'abc', 'a1-b2', 'x' * 48):
    ok(not topic_slug.errors(s, words=words), 'slug ok: %s' % s[:20])
for s, why in (('ab', 'too short'), ('x' * 49, 'too long'), ('Grand-Prix', 'uppercase'), ('a--b', 'double hyphen'), ('-abc', 'leading hyphen'),
               ('abc-', 'trailing hyphen'), ('a_b_c', 'underscore'), ('r/pics', 'r/ prefix'), ('r-pics', 'r- prefix'), ('reddit-fans', 'Reddit text'),
               ('askreddit', 'Reddit text inside'), ('café', 'non-ascii')):
    ok(topic_slug.errors(s, words=words), 'slug refused (%s): %s' % (why, s[:20]))
SYSTEM = ['t', 'c', 'u', 'p', 'n', 'api', 'admin', 'auth', 'login', 'signup', 'settings', 'search', 'explore', 'home', 'feed', 'new', 'hot', 'top',
          'following', 'notifications', 'chat', 'profile', 'news', 'watchlist', 'stories', 'thoughts', 'static', 'assets', 'shell', 'cdn', 'sitemap',
          'robots', 'llms', 'status', 'console']
LEGAL = ['about', 'terms', 'privacy', 'legal', 'takedown', 'report', 'abuse', 'security', 'support', 'official', 'verified', 'staff', 'mod',
         'moderator', 'steward']
ok(set(SYSTEM) <= words and set(LEGAL) <= words, 'reserved: every system path and brand/legal word from the brief')
for s in [x for x in SYSTEM + LEGAL if len(x) >= 3]:
    ok(any('reserved' in e for e in topic_slug.errors(s, words=words)), 'reserved slug refused: %s' % s)
ok({'subx', 'subx-it', 'subx-official', 'official-subx'} <= words, 'reserved: brand words generated from brand.json')
alt = dict(brand, name='Quillnest', shortName='Quill', primaryDomain='quillnest.example', legalEntity='Quillnest Labs, Inc.', aliases=['Q Nest'])
w2 = topic_slug.reserved(alt)
ok({'quillnest', 'quill', 'quillnest-labs', 'q-nest', 'quillnest-official'} <= w2 and 'subx' not in w2, 'reserved: brand words follow a rename (and brand.aliases)')

# ---- activity rule ----
NOW = '2026-11-04T04:00:00Z'
now = TS.parse_ts(NOW)
def post(uid, days_ago, **kw):
    p = {'authorUid': uid, 'createdAt': TS.iso(now - timedelta(days=days_ago)), 'authorVerifiedHuman': True,
         'authorCreatedAt': TS.iso(now - timedelta(days=days_ago + 30))}
    p.update(kw)
    return p
def topic(status='hidden', **kw):
    t = {'slug': 'tide-pools', 'title': 'T', 'description': 'd', 'status': status, 'createdAt': NOW, 'activatedAt': None, 'posts14d': 0,
         'distinctPosters14d': 0, 'posts30d': 0, 'lastCountedPostAt': None, 'doorwayDomains': [], 'stewardOnly': False}
    t.update(kw)
    return t
busy = [post('u%d' % (i % 5), i * 0.5) for i in range(20)]  # 20 posts, 5 people, inside 10 days
ok(TS.counts(busy, NOW)['posts14d'] == 20 and TS.counts(busy, NOW)['distinctPosters14d'] == 5, 'counts: 20 posts by 5 people in 14 days')
ok(TS.apply(topic(), busy, NOW)['status'] == 'active', 'hidden -> active at 20 posts / 5 people / 14 days')
ok(TS.apply(topic(), busy, NOW)['activatedAt'] == NOW, 'activatedAt is set on activation')
ok(TS.apply(topic(), busy[:19], NOW)['status'] == 'hidden', '19 posts stays hidden')
four = [post('u%d' % (i % 4), i * 0.5) for i in range(25)]
ok(TS.apply(topic(), four, NOW)['status'] == 'hidden', '25 posts by only 4 people stays hidden')
old = [post('u%d' % (i % 5), 14 + i * 0.1) for i in range(20)]
ok(TS.apply(topic(), old, NOW)['status'] == 'hidden', 'posts older than 14 days do not activate')
def mark(**kw):
    return [dict(p, **kw) for p in busy]
ok(TS.apply(topic(), mark(steward=True), NOW)['status'] == 'hidden', 'steward posts never count')
ok(TS.apply(topic(), mark(ai=True), NOW)['status'] == 'hidden', 'AI posts never count')
ok(TS.apply(topic(), mark(authorVerifiedHuman=False), NOW)['status'] == 'hidden', 'unverified accounts never count')
young = [dict(p, authorCreatedAt=TS.iso(TS.parse_ts(p['createdAt']) - timedelta(days=6))) for p in busy]
ok(TS.apply(topic(), young, NOW)['status'] == 'hidden', 'accounts under 7 days old do not count')
aged = [dict(p, authorCreatedAt=TS.iso(TS.parse_ts(p['createdAt']) - timedelta(days=7))) for p in busy]
ok(TS.apply(topic(), aged, NOW)['status'] == 'active', 'accounts exactly 7 days old count')
ok(TS.counts([post('u1', -1)], NOW)['posts14d'] == 0, 'future-dated posts are ignored')
act = topic('active', activatedAt=TS.iso(now - timedelta(days=40)))
ok(TS.apply(act, [post('a', 1), post('b', 10), post('c', 20)], NOW)['status'] == 'active', 'active with 3 posts in 30 days stays active')
ok(TS.apply(act, [post('a', 1), post('b', 10)], NOW)['status'] == 'quiet', 'active with < 3 posts in 30 days -> quiet')
q = TS.apply(act, [post('a', 40)], NOW)
ok(q['status'] == 'quiet' and TS.robots('quiet', hub_noindex=False) == 'index,follow' and TS.sitemap_eligible('quiet', hub_noindex=False),
   'quiet stays indexed and in the sitemap (once the hub-wide noindex is lifted)')
ok(TS.badge('quiet') == 'Quiet lately. New posts welcome.' and TS.badge('active') is None, 'quiet badge text')
ok(TS.apply(topic('quiet', activatedAt=act['activatedAt']), [post('a', 1), post('b', 2), post('c', 3)], NOW)['status'] == 'active', 'quiet -> active at 3 posts in 30 days')
ar = TS.apply(act, [post('a', 91)], NOW)
ok(ar['status'] == 'archived' and ar['stewardOnly'] is True and TS.read_only('archived'), 'active with 0 posts in 90 days -> archived, read-only')
ok(TS.apply(topic('quiet', activatedAt=act['activatedAt']), [], NOW)['status'] == 'archived', 'quiet with no counted posts ever -> archived')
ok(TS.apply(act, [post('a', 89)], NOW)['status'] == 'quiet', 'a post 89 days ago keeps it out of archive')
ok(TS.robots('archived', hub_noindex=False) == 'noindex,nofollow' and not TS.sitemap_eligible('archived', hub_noindex=False), 'archived: noindex, out of the sitemap')
re_ = TS.apply(topic('archived', activatedAt=act['activatedAt'], stewardOnly=True), busy, NOW)
ok(re_['status'] == 'active' and re_['stewardOnly'] is False and re_['activatedAt'] == NOW, 'archived auto-reopens on the active rule (new activatedAt)')
ok(TS.apply(topic('archived', stewardOnly=True), [post('a', 1)], NOW)['status'] == 'archived', 'archived stays archived below the active rule')
ok(TS.apply(topic('hold', stewardOnly=True), busy, NOW)['status'] == 'hold', 'hold is manual: the rule never changes it')
ok(TS.apply(topic(), [], NOW)['status'] == 'hidden', 'hidden with nothing stays hidden (never archived)')
src = topic(); TS.apply(src, busy, NOW)
ok(src == topic(), 'apply() is pure: input row untouched')
ok(TS.robots('hidden', hub_noindex=False) == 'noindex,nofollow' and all(TS.robots(s) == 'noindex,nofollow' for s in TS.STATUSES), 'hidden noindex,nofollow; hub-wide noindex covers every status')
ok(not any(TS.sitemap_eligible(s) for s in TS.STATUSES), 'hub-wide noindex: no topic is sitemap-eligible tonight')
ok(not TS.rendered('hold') and all(TS.rendered(s) for s in ('hidden', 'active', 'quiet', 'archived')), 'only hold is never rendered')
ok(TS.doorway_status(topic(), NOW) == 302, 'doorway: 302 while hidden')
ok(TS.doorway_status(topic('active', activatedAt=TS.iso(now - timedelta(days=59))), NOW) == 302, 'doorway: 302 at 59 days active')
ok(TS.doorway_status(topic('active', activatedAt=TS.iso(now - timedelta(days=60))), NOW) == 301, 'doorway: 301 after 60 days active')
ok(TS.doorway_status(topic('archived', activatedAt=TS.iso(now - timedelta(days=200))), NOW) == 302, 'doorway: archived falls back to 302')
try:
    TS.parse_ts('2026-11-04T04:00:00'); ok(False, 'naive timestamps are refused')
except ValueError:
    ok(True, 'naive timestamps are refused')

# ---- seed + schema ----
seed = json.load(open(os.path.join(ROOT, 'topics', 'seed_wave1.json')))
sch = json.load(open(os.path.join(ROOT, 'topics', 'schema.json')))
ok(not topics_seed.check(seed), 'seed passes schema, slug, reserved and seed invariants (%s)' % topics_seed.check(seed)[:2])
ok(seed['source']['md5'] == '0954c611f47ddbd3417b1557e94fd489' and seed['source']['rows'] == 52, 'seed built from topics_wave1.csv md5 0954c611...')
ok(topics_seed.summary(seed) == {'hidden': 51, 'hold': 1}, 'seed: 51 hidden + 1 hold')
by = {t['slug']: t for t in seed['topics']}
ok(by['grief']['status'] == 'hold' and by['grief']['stewardOnly'] is True, 'grief is HOLD')
ok(by['air-travel']['status'] == 'hidden' and by['cash-and-atms']['status'] == 'hidden', 'air-travel and cash-and-atms are hidden')
ok(set(sch['required']) == {'slug', 'title', 'description', 'status', 'createdAt', 'activatedAt', 'posts14d', 'distinctPosters14d', 'posts30d',
                             'lastCountedPostAt', 'doorwayDomains', 'stewardOnly'} and sch['properties']['status']['enum'] == list(TS.STATUSES),
   'schema: the briefed fields and statuses')
ok(topic_schema.validate(dict(by['dogs'], status='live'), sch) and topic_schema.validate(dict(by['dogs'], posts14d=-1), sch)
   and topic_schema.validate(dict(by['dogs'], extra=1), sch) and topic_schema.validate(dict(by['dogs'], createdAt='yesterday'), sch),
   'schema validator rejects bad status, negative counts, unknown fields, bad dates')
bad = json.loads(json.dumps(seed)); bad['topics'][0]['posts14d'] = 3
ok(topics_seed.check(bad), 'seed check refuses non-zero starting stats')
bad = json.loads(json.dumps(seed)); bad['topics'][0]['slug'] = 'login'
ok(topics_seed.check(bad), 'seed check refuses a reserved slug')
bad = json.loads(json.dumps(seed)); by2 = {t['slug']: t for t in bad['topics']}; by2['grief']['status'] = 'hidden'
ok(topics_seed.check(bad), 'seed check refuses grief out of HOLD')
txt = json.dumps(seed).lower()
ok(not re.search(r'jebb|denver|\b310[-. ]|peekai|vokadots|dmca-1084331|[\u2013\u2014]', txt), 'seed: no private names, contacts or dashes')

def run(args, env=None):
    e = dict(os.environ); e.pop(topics_seed.APPLY_ENV, None); e.update(env or {})
    return subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'topics_seed.py')] + args, capture_output=True, text=True, env=e)
r = run([])
ok(r.returncode == 0 and 'DRY RUN' in r.stdout and 'nothing written' in r.stdout, 'topics_seed.py defaults to a dry run')
r = run(['--apply'])
ok(r.returncode == 3 and 'REFUSED' in r.stderr, '--apply refused without SUBX_TOPICS_APPLY_GO')
r = run(['--apply'], {topics_seed.APPLY_ENV: '1'})
ok(r.returncode == 4 and 'Nothing written' in r.stderr, '--apply still writes nothing with the variable set (no writer in this PR)')
code = ''.join(open(os.path.join(ROOT, 'tools', f)).read() for f in ('topics_seed.py', 'topic_status.py', 'topic_domains.py', 'topic_slug.py'))
ok(not re.search(r'firebase_admin|google\.cloud|firestore\.client|requests\.|urllib\.request|http\.client', code), 'topic tools import no Firestore / network client')

# ---- hybrid domain config ----
cfg = json.load(open(os.path.join(ROOT, 'topics', 'domains.json')))
ok(not topic_domains.check(cfg, seed), 'domains.json valid against seed, rooms and schema (%s)' % topic_domains.check(cfg, seed)[:2])
modes = {x['domain']: x['mode'] for x in cfg['domains']}
rooms = topic_domains.room_domains()
ok(all(modes[d] == 'room' for d in modes if d in rooms), 'every domain a live room serves stays mode room')
ok(modes['mournchat.com'] == 'parked', 'the HOLD topic doorway (mournchat.com) is parked')
ok(sum(1 for m in modes.values() if m == 'doorway') == 27 and sum(1 for m in modes.values() if m == 'room') == 18, '27 doorways, 18 rooms, 1 parked')
lines = topic_domains.redirects(NOW, cfg, seed)
ok('https://213chat.com/*  https://subx.it/t/los-angeles/?via=213chat.com  302' in lines and not any(l.endswith(' 301') for l in lines), 'redirect plan: 302 for every doorway tonight')
bad = json.loads(json.dumps(cfg)); [x.update(mode='doorway') for x in bad['domains'] if x['domain'] == 'gpchat.com']
ok(any('live room' in e for e in topic_domains.check(bad, seed)), 'turning a live room into a doorway is refused')
ok(topic_domains.validate_fields({'mode': 'doorway'}, 'x') and topic_domains.validate_fields({'mode': 'banana'}, 'x')
   and topic_domains.validate_fields({'mode': 'doorway', 'topic': 'dogs', 'doorway': {'status': 301}}, 'x')
   and not topic_domains.validate_fields({'name': 'Room', 'shell': {}}, 'x'), 'site.json hybrid fields: optional, validated, status never stored')
ok(not os.path.exists(os.path.join(ROOT, 'hub', 'site', '_redirects')) and '"redirects"' not in open(os.path.join(ROOT, 'hub', 'firebase.json')).read(),
   'no live redirect files or hosting redirects')

print('\n%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)
