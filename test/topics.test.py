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
for s, why in (('los-angeles\n', 'trailing newline'), ('los-angeles\r', 'trailing CR'), ('los-angeles\r\n', 'trailing CRLF'),
               ('\nlos-angeles', 'leading newline'), ('los-angeles ', 'trailing space'), ('l\u043es-angeles', 'Cyrillic o lookalike'),
               ('los\u2010angeles', 'Unicode hyphen lookalike'), ('\uff4c\uff4f\uff53-angeles', 'fullwidth letters'), ('los-angele\u0455', 'Cyrillic s lookalike'),
               ('abc\x00', 'NUL'), ('r\n', 'r + newline')):
    ok(topic_slug.errors(s, words=words), 'slug refused (%s): %r' % (why, s))
ok(topic_slug.SLUG_RE.match('los-angeles\n') is not None and topic_slug.SLUG_RE.fullmatch('los-angeles\n') is None and '$' not in topic_slug.SLUG_RE.pattern,
   'slug regex is used with fullmatch and carries no $ anchor')
r_ = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'topic_slug.py'), 'los-angeles\n'], capture_output=True, text=True)
ok(r_.returncode == 1, 'topic_slug.py CLI refuses a slug with a trailing newline')
PLATFORM = ['x', 'x-com', 'xcom', 'xcorp', 'x-corp', 'twitter', 'grok']
ok(set(PLATFORM) <= words and set(PLATFORM) <= topic_slug.reserved(dict(brand, name='Quillnest', shortName='Quill', primaryDomain='quillnest.example')),
   'reserved: platform names (x, x-com, xcom, xcorp, x-corp, twitter, grok), whatever the brand')
for s in [x for x in PLATFORM if len(x) >= 3]:
    ok(any('reserved' in e for e in topic_slug.errors(s, words=words)), 'reserved platform slug refused: %s' % s)
ok(topic_slug.errors('x', words=words), 'slug refused: x')
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
W = [1]  # approved wave list for these tests (topics/approved_waves.json is empty tonight)
APPR = {'approvedWave': 1, 'approvedBy': 'owner', 'approvedAt': TS.iso(now - timedelta(days=1))}
def atopic(status='hidden', **kw):
    return topic(status, **dict(APPR, **kw))
el = TS.apply(topic(), busy, NOW, W)
ok(el['status'] == 'eligible' and el['activatedAt'] is None, 'hidden -> eligible (not active) at 20 posts / 5 people / 14 days with no approval record')
ok(TS.apply(topic(), busy, NOW)['status'] == 'eligible', 'hidden -> eligible with no approved wave list at all')
ok(TS.apply(atopic(), busy, NOW)['status'] == 'eligible', 'approval record whose wave is not on the approved list -> eligible')
ok(TS.apply(atopic(), busy, NOW, W)['status'] == 'active', 'hidden -> active when the wave was approved ahead of time')
ok(TS.apply(atopic(), busy, NOW, W)['activatedAt'] == NOW, 'activatedAt is set on activation')
ok(TS.apply(atopic('eligible'), busy, NOW, W)['status'] == 'active', 'eligible -> active once the row has a valid approval')
ok(TS.apply(atopic('eligible'), [post('a', 1), post('b', 2), post('c', 3)], NOW, W)['status'] == 'active', 'an approved eligible topic goes active even below the rule (it met it)')
ok(TS.apply(topic('eligible'), busy, NOW, W)['status'] == 'eligible', 'eligible stays eligible while waiting on approval')
ok(TS.apply(topic('eligible'), [post('a', 1), post('b', 2), post('c', 3)], NOW, W)['status'] == 'eligible', 'unapproved eligible with 3 posts in 30 days stays eligible')
ok(TS.apply(topic('eligible'), [post('a', 1), post('b', 2)], NOW, W)['status'] == 'hidden', 'unapproved eligible with < 3 posts in 30 days -> back to hidden')
for k, v, why in (('approvedBy', '', 'empty approvedBy'), ('approvedBy', None, 'no approvedBy'), ('approvedAt', None, 'no approvedAt'),
                  ('approvedAt', TS.iso(now + timedelta(days=1)), 'future approvedAt'), ('approvedAt', '2026-11-03T07:00:00', 'naive approvedAt'),
                  ('approvedAt', 'soon', 'garbage approvedAt'), ('approvedWave', None, 'no approvedWave'), ('approvedWave', True, 'boolean approvedWave'),
                  ('approvedWave', 2, 'wave not on the list')):
    ok(not TS.approved(atopic(**{k: v}), W, NOW) and TS.apply(atopic(**{k: v}), busy, NOW, W)['status'] == 'eligible', 'incomplete approval (%s) is refused: eligible' % why)
ok(TS.approved(atopic(), W, NOW) and not TS.approved(atopic(), [], NOW) and not TS.approved(topic(), W, NOW), 'approved(): needs the full record and a listed wave')
ok(TS.apply(atopic(), busy[:19], NOW, W)['status'] == 'hidden', '19 posts stays hidden')
four = [post('u%d' % (i % 4), i * 0.5) for i in range(25)]
ok(TS.apply(atopic(), four, NOW, W)['status'] == 'hidden', '25 posts by only 4 people stays hidden')
old = [post('u%d' % (i % 5), 14 + i * 0.1) for i in range(20)]
ok(TS.apply(atopic(), old, NOW, W)['status'] == 'hidden', 'posts older than 14 days do not activate')
def mark(**kw):
    return [dict(p, **kw) for p in busy]
ok(TS.apply(atopic(), mark(steward=True), NOW, W)['status'] == 'hidden', 'steward posts never count')
ok(TS.apply(atopic(), mark(ai=True), NOW, W)['status'] == 'hidden', 'AI posts never count')
ok(TS.apply(atopic(), mark(authorVerifiedHuman=False), NOW, W)['status'] == 'hidden', 'unverified accounts never count')
young = [dict(p, authorCreatedAt=TS.iso(TS.parse_ts(p['createdAt']) - timedelta(days=6))) for p in busy]
ok(TS.apply(atopic(), young, NOW, W)['status'] == 'hidden', 'accounts under 7 days old do not count')
aged = [dict(p, authorCreatedAt=TS.iso(TS.parse_ts(p['createdAt']) - timedelta(days=7))) for p in busy]
ok(TS.apply(atopic(), aged, NOW, W)['status'] == 'active', 'accounts exactly 7 days old count')
ok(TS.counts([post('u1', -1)], NOW)['posts14d'] == 0, 'future-dated posts are ignored')
act = atopic('active', activatedAt=TS.iso(now - timedelta(days=40)))
ok(TS.apply(act, [post('a', 1), post('b', 10), post('c', 20)], NOW, W)['status'] == 'active', 'active with 3 posts in 30 days stays active')
ok(TS.apply(act, [post('a', 1), post('b', 10), post('c', 20)], NOW, [])['status'] == 'eligible', 'fails closed: an active topic whose wave is not listed drops to eligible')
ok(TS.apply(act, [post('a', 1), post('b', 10)], NOW, W)['status'] == 'quiet', 'active with < 3 posts in 30 days -> quiet')
q = TS.apply(act, [post('a', 40)], NOW, W)
ok(q['status'] == 'quiet' and TS.robots('quiet', hub_noindex=False) == 'noindex,nofollow' and not TS.sitemap_eligible('quiet', hub_noindex=False),
   'quiet is noindex and out of the sitemap (even once the hub-wide noindex is lifted)')
ok(TS.rendered('quiet') and not TS.read_only('quiet') and q['stewardOnly'] is False, 'quiet stays rendered and open to post')
ok(TS.badge('quiet') == 'Quiet lately. New posts welcome.' and TS.badge('active') is None, 'quiet badge text kept')
qt = atopic('quiet', activatedAt=act['activatedAt'])
ok(TS.apply(qt, [post('a', 1), post('b', 2), post('c', 3)], NOW, W)['status'] == 'quiet', 'quiet does NOT reopen at 3 posts in 30 days (needs the active rule)')
rq = TS.apply(qt, busy, NOW, W)
ok(rq['status'] == 'active' and rq['activatedAt'] == NOW, 'quiet -> active on the active rule, re-gated by the existing approval (new 60-day clock)')
ok(TS.apply(dict(qt, approvedAt=TS.iso(now - timedelta(days=300))), busy, NOW, W)['status'] == 'active', 'reopening needs no new wave approval (old approval still valid)')
ok(TS.apply(topic('quiet', activatedAt=act['activatedAt']), busy, NOW, W)['status'] == 'eligible', 'quiet with no approval record reopens only as eligible')
ar = TS.apply(act, [post('a', 91)], NOW, W)
ok(ar['status'] == 'archived' and ar['stewardOnly'] is True and TS.read_only('archived'), 'active with 0 posts in 90 days -> archived, read-only')
ok(TS.apply(qt, [], NOW, W)['status'] == 'archived', 'quiet with no counted posts ever -> archived')
ok(TS.apply(act, [post('a', 89)], NOW, W)['status'] == 'quiet', 'a post 89 days ago keeps it out of archive')
ok(TS.robots('archived', hub_noindex=False) == 'noindex,nofollow' and not TS.sitemap_eligible('archived', hub_noindex=False), 'archived: noindex, out of the sitemap')
re_ = TS.apply(atopic('archived', activatedAt=act['activatedAt'], stewardOnly=True), busy, NOW, W)
ok(re_['status'] == 'active' and re_['stewardOnly'] is False and re_['activatedAt'] == NOW, 'archived auto-reopens on the active rule with its existing approval (new activatedAt)')
ok(TS.apply(topic('archived', activatedAt=act['activatedAt'], stewardOnly=True), busy, NOW, W)['status'] == 'eligible', 'archived without approval reopens only as eligible')
ok(TS.apply(atopic('archived', stewardOnly=True), [post('a', 1)], NOW, W)['status'] == 'archived', 'archived stays archived below the active rule')
ok(TS.apply(atopic('hold', stewardOnly=True), busy, NOW, W)['status'] == 'hold', 'hold is manual: the rule never changes it')
ok(TS.apply(topic(), [], NOW, W)['status'] == 'hidden', 'hidden with nothing stays hidden (never archived)')
src = atopic(); TS.apply(src, busy, NOW, W)
ok(src == atopic(), 'apply() is pure: input row untouched')
ok([s for s in TS.STATUSES if TS.robots(s, hub_noindex=False) == 'index,follow'] == ['active'], 'only active is indexable once the hub-wide noindex is lifted')
ok([s for s in TS.STATUSES if TS.sitemap_eligible(s, hub_noindex=False)] == ['active'], 'only active is sitemap-eligible once the hub-wide noindex is lifted')
ok(all(TS.robots(s) == 'noindex,nofollow' for s in TS.STATUSES), 'hub-wide noindex covers every status')
ok(not any(TS.sitemap_eligible(s) for s in TS.STATUSES), 'hub-wide noindex: no topic is sitemap-eligible tonight')
ok(not TS.rendered('hold') and all(TS.rendered(s) for s in ('hidden', 'eligible', 'active', 'quiet', 'archived')), 'only hold is never rendered')
ok(TS.doorway_status(topic(), NOW) == 302 and TS.doorway_status(topic('eligible'), NOW) == 302, 'doorway: 302 while hidden or eligible')
ok(TS.doorway_status(topic('active', activatedAt=TS.iso(now - timedelta(days=59))), NOW) == 302, 'doorway: 302 at 59 days active')
ok(TS.doorway_status(topic('active', activatedAt=TS.iso(now - timedelta(days=60))), NOW) == 301, 'doorway: 301 after 60 days active')
ok(TS.doorway_status(topic('quiet', activatedAt=TS.iso(now - timedelta(days=200))), NOW) == 302, 'doorway: quiet falls back to 302')
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
ok(list(TS.STATUSES) == ['hidden', 'eligible', 'active', 'quiet', 'archived', 'hold'], 'statuses include eligible')
ok(not topic_schema.validate(dict(by['dogs'], **APPR), sch) and not topic_schema.validate(dict(by['dogs'], approvedWave=None, approvedBy=None, approvedAt=None), sch),
   'schema: optional approval record (approvedWave, approvedBy, approvedAt), null allowed')
ok(topic_schema.validate(dict(by['dogs'], approvedWave=0), sch) and topic_schema.validate(dict(by['dogs'], approvedWave='1'), sch)
   and topic_schema.validate(dict(by['dogs'], approvedBy=''), sch) and topic_schema.validate(dict(by['dogs'], approvedAt='later'), sch),
   'schema rejects a bad approval record')
ok(not any(k in t for t in seed['topics'] for k in TS.APPROVAL_FIELDS), 'seed rows carry no approval record')
bad = json.loads(json.dumps(seed)); bad['topics'][0].update(APPR)
ok(topics_seed.check(bad), 'seed check refuses a seed row with an approval record')
aw = json.load(open(os.path.join(ROOT, 'topics', 'approved_waves.json')))
aws = json.load(open(os.path.join(ROOT, 'topics', 'approved_waves.schema.json')))
ok(aw['approvedWaves'] == [] and not topic_schema.validate(aw, aws), 'approved_waves.json: valid and empty tonight (no wave approved)')
ok(topic_schema.validate({'approvedWaves': ['1']}, aws) and topic_schema.validate({'approvedWaves': [1, 1]}, aws) and topic_schema.validate({}, aws),
   'approved_waves schema rejects non-integer, duplicate or missing waves')
ok(not any(TS.approved(dict(t, **APPR), aw['approvedWaves'], NOW) for t in seed['topics']), 'tonight no seed topic could pass the approval gate')
ok(topic_schema.validate('dogs\n', {'type': 'string', 'pattern': '^[a-z]+$'}) and not topic_schema.validate('dogs', {'type': 'string', 'pattern': '^[a-z]+$'}),
   'schema pattern: $ means end of string (ECMA), so a trailing newline is refused')
ok(topic_schema.validate(dict(by['dogs'], slug='dogs\n'), sch) and topic_schema.validate(dict(by['dogs'], createdAt='2026-11-03T07:00:00Z\n'), sch),
   'schema refuses a slug or date-time with a trailing newline')
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

# ---- activity copy matches the quiet rule (Key 2 follow-up) ----
QUIET = 'A topic with fewer than 3 counted posts in 30 days goes quiet: it stays open, leaves search, and returns once it clears the bar again.'
for f in ('about.html', os.path.join('t', 'index.html')):
    h = open(os.path.join(ROOT, 'hub', 'site', f), encoding='utf-8').read()
    ok(QUIET in h and 'rests: it stays readable, leaves search' not in h and 'One that goes 90 days without a counted post rests: it stays readable and reopens on its own' in h,
       'copy (%s): quiet leaves search; 90-day rest line no longer implies quiet topics stay in search' % f)
tt = open(os.path.join(ROOT, 'hub', 'src', 'topic-template.html'), encoding='utf-8').read()
ok('It can show up in search once 20 or more posts' in tt and 'It shows up in search once' not in tt, 'copy (topic template): meeting the bar no longer promises search (approval gate)')
ok(not re.search(r'stays (indexed|in search|listed)', open(os.path.join(ROOT, 'hub', 'src', 'templates', 'topics.html'), encoding='utf-8').read() + tt),
   'copy: nothing says a quiet topic stays in search')

print('\n%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)
