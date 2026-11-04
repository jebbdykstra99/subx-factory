#!/usr/bin/env python3
"""Spin-up dry run (tools/spinup_render.py): candidates config, modes, exclusions, reserved slugs, rendered site.json,
the non-room drift rule, and the no-write --check. Python stdlib only."""
import copy, json, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import spinup_render as SR, topic_domains, shell_drift  # noqa: E402

fails = []
def ok(c, m):
    print(('ok   ' if c else 'FAIL ') + m)
    if not c:
        fails.append(m)

cfg = json.load(open(SR.CANDIDATES))
brand = json.load(open(os.path.join(ROOT, 'brand', 'brand.json')))
entries, errs = SR.resolve(cfg)
ok(not errs, 'committed candidates resolve with no errors: %s' % errs[:3])
byd = {e['domain']: e for e in entries}

def plus(*cands):
    """A copy of cfg with synthetic candidates appended and the inventory bumped to match."""
    b = copy.deepcopy(cfg)
    b['candidates'] += [dict(c) for c in cands]
    b['source']['inventory'] += len(cands)
    return b

# ---- counts: never invented, every inventory name accounted for, no held name in any form ----
inv = cfg['source']['inventory']
ebr = cfg['excludedByReason']
ok(inv == 151, 'inventory is the 151 names in the plan')
ok(len(cfg['candidates']) + sum(ebr.values()) == inv, 'candidates + excludedByReason = inventory (%d + %d)' % (len(cfg['candidates']), sum(ebr.values())))
ok(len(entries) == 103 and sum(ebr.values()) == 48, 'rendered 103, excluded 48')
modes = {m: sum(1 for e in entries if e['mode'] == m) for m in SR.MODES}
ok(modes == {'room': 0, 'doorway': 94, 'parked': 9}, 'by mode: %s' % modes)
ok(len({c['domain'] for c in cfg['candidates']}) == len(cfg['candidates']), 'no candidate listed twice')
ok('excluded' not in cfg, 'candidates.json has no excluded list')
hexre = re.compile(r'[0-9a-fA-F]{64}')
tracked = subprocess.run(['git', 'ls-files', 'spinup'], cwd=ROOT, capture_output=True, text=True).stdout.split()
spfiles = sorted(set(tracked) | {os.path.relpath(os.path.join(dp, f), ROOT) for dp, dn, fn in os.walk(os.path.join(ROOT, 'spinup'))
                                 if not os.path.relpath(dp, ROOT).startswith(os.path.join('spinup', 'out')) for f in fn})
ok(len(spfiles) >= 3, 'spinup/ files found: %s' % spfiles)
for f in spfiles:
    ok(not hexre.search(open(os.path.join(ROOT, f), encoding='utf-8', errors='replace').read()), 'no 64-hex string in %s' % f)
bad = copy.deepcopy(cfg); bad['note'] = 'a' * 64
ok(any('64-hex' in x for x in SR.resolve(bad)[1]), 'a 64-hex string in candidates.json is refused')
bad = copy.deepcopy(cfg); bad['excluded'] = []
ok(any('may not list excluded' in x for x in SR.resolve(bad)[1]), 'an excluded list in candidates.json is refused')
bad = copy.deepcopy(cfg); bad['excludedByReason'] = dict(ebr, extra=1)
ok(any('source.inventory' in x for x in SR.resolve(bad)[1]), 'counts that do not add up to the inventory are refused')
bad = copy.deepcopy(cfg); bad['excludedByReason'] = {'x': 0}
ok(any('positive count' in x for x in SR.resolve(bad)[1]), 'a zero exclusion count is refused')
# off-repo exclusion list: any candidate on it is refused (synthetic names only; the real list never enters the repo)
with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False) as tf:
    tf.write('# header\nheldexample.com | test reason | test\n\n')
excl = SR.load_exclusions(tf.name)
ok(excl == {'heldexample.com'}, 'exclusion file parser reads domain | reason lines')
bad = plus({'domain': 'heldexample.com'})
ok(any('off-repo exclusion list' in x for x in SR.resolve(bad, exclusions=excl)[1]), 'a candidate on the off-repo exclusion list is refused')
r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'spinup_render.py'), '--check', '--exclusions', tf.name], capture_output=True, text=True)
ok(r.returncode == 0 and 'exclusion list checked (1 names)' in r.stdout, '--check --exclusions passes when no candidate is listed')
os.remove(tf.name)

# ---- modes and defaults ----
ok(cfg['defaults']['mode'] == 'parked', 'defaults.mode is parked')
for c in cfg['candidates']:
    if 'mode' not in c:
        ok(byd[c['domain']]['mode'] == 'parked' and 'topic' not in byd[c['domain']], 'no mode -> parked, no topic: %s' % c['domain'])
bad = plus({'domain': 'unknownexample.com'})
e2, er = SR.resolve(bad)
ok(not er and [x for x in e2 if x['domain'] == 'unknownexample.com'][0]['mode'] == 'parked', 'an unknown domain defaults to parked')
bad = copy.deepcopy(cfg); bad['defaults']['mode'] = 'doorway'
ok(any('defaults.mode must be parked' in x for x in SR.resolve(bad)[1]), 'defaults.mode other than parked is refused')
bad = copy.deepcopy(cfg); bad['defaults']['brand'] = 'SubX'
ok(any('defaults.brand' in x for x in SR.resolve(bad)[1]), 'a literal brand in defaults is refused')
for m, why in (('redirect', 'unknown mode'), ('room', 'room without a live room')):
    bad = plus({'domain': 'unknownexample.com', 'mode': m})
    ok(SR.resolve(bad)[1], 'refused: %s' % why)
bad = plus({'domain': 'unknownexample.com', 'mode': 'doorway'})
ok(any('needs a topic' in x for x in SR.resolve(bad)[1]), 'a doorway without a topic is refused')
live = sorted(topic_domains.room_domains())[0]
bad = plus({'domain': live, 'mode': 'parked'})
ok(any('live room serves it' in x for x in SR.resolve(bad)[1]), 'a live room domain is never a candidate')
bad = plus({'domain': 'Upper.com'})
ok(any('not a lowercase domain' in x for x in SR.resolve(bad)[1]), 'an uppercase domain is refused')
bad = plus({'domain': 'abc.com\n'})
ok(any('not a lowercase domain' in x for x in SR.resolve(bad)[1]), 'a domain with a trailing newline is refused (fullmatch)')
bad = plus(dict(bad['candidates'][0]))
ok(any('listed twice' in x for x in SR.resolve(bad)[1]), 'a duplicate candidate is refused')

# ---- Key 1 edits: awolchat is parked with no topic; ftpchat is a doorway to fight-the-power (owner go 10:02 PM MT) ----
for d in ('awolchat.com',):
    ok(byd[d]['mode'] == 'parked' and 'topic' not in byd[d], 'Key 1: %s is parked with no topic' % d)
    c = [x for x in cfg['candidates'] if x['domain'] == d][0]
    ok('mode' not in c and 'topic' not in c, 'Key 1: %s takes the parked default' % d)
ok(byd['ftpchat.com']['mode'] == 'doorway' and byd['ftpchat.com']['topic'] == 'fight-the-power' and not byd['ftpchat.com'].get('govAgency'),
   'ftpchat is a doorway to fight-the-power, not flagged as an agency')

# ---- government-agency doorways (owner go 2026-11-03): govAgency flag, wave-2 agency topics, brand line ----
import topics_seed  # noqa: E402
AGENCY = {'cfpbchat.com': 'consumer-finance', 'doichat.com': 'public-lands-policy', 'dojchat.com': 'justice-system',
          'epachat.com': 'environment-policy', 'faachat.com': 'aviation-safety', 'fsbchat.com': 'russia-watch',
          'svrchat.com': 'russia-watch', 'treasurychat.com': 'public-finance'}
GOV = 'Not affiliated with, endorsed by, or speaking for any government agency.'
ok(brand.get('nonAffiliationGov') == GOV, 'brand.nonAffiliationGov has the exact text')
flagged = {e['domain']: e['topic'] for e in entries if e.get('govAgency')}
ok(flagged == AGENCY, 'the 8 agency doorways carry govAgency and point at the agreed topics')
ok(byd['interiorchat.com']['mode'] == 'doorway' and byd['interiorchat.com']['topic'] == 'interior-design' and not byd['interiorchat.com'].get('govAgency'),
   'interiorchat is a doorway to interior-design, not flagged as an agency')
ok(all(SR.site_json(byd[d], cfg).get('govAgency') is True for d in AGENCY), 'every agency site.json carries govAgency: true')
ok(not any('govAgency' in SR.site_json(e, cfg) for e in entries if e['domain'] not in AGENCY), 'no other site.json carries govAgency')
s2 = json.load(open(topics_seed.AGENCY_SEED))
ok(not topics_seed.check_agency(s2), 'agency seed passes its check: %s' % topics_seed.check_agency(s2)[:2])
ok(s2['source'] == {'file': 'AGENCY_TOPICS_DRAFT_2026-11-03.md', 'md5': 'e9bf6e557065b100ccaa0b8fb0e51c6e', 'rows': 7}, 'agency seed built from the 7-row draft md5 e9bf6e55')
FTP_DESC = ('Civil rights, protest history and people pushing back on power, from the 1960s to now. '
            'Debate the ideas, not the people. No threats, no doxxing, no calls to violence.')
gov2 = [t for t in s2['topics'] if t.get('govNonAffiliation') is True]
ok(sorted(t['slug'] for t in gov2) == sorted(set(AGENCY.values())), 'agency seed has exactly the 7 agency topics flagged govNonAffiliation')
ok(all(t['status'] == 'hidden' for t in s2['topics']), 'every wave-2 topic is hidden')
ok({d: t['slug'] for t in gov2 for d in t['doorwayDomains']} == AGENCY, 'agency topic doorwayDomains match the flagged doorways')
ftp = [t for t in s2['topics'] if t['slug'] == 'fight-the-power']
ok(len(ftp) == 1 and ftp[0]['title'] == 'Fight the Power' and ftp[0]['description'] == FTP_DESC and ftp[0]['doorwayDomains'] == ['ftpchat.com']
   and 'govNonAffiliation' not in ftp[0] and ftp[0]['status'] == 'hidden', 'fight-the-power: exact title and description, hidden, no gov flag, doorway ftpchat')
ok(s2.get('extraSources') == [{'file': 'FTP_TOPIC_DRAFT_2026-11-03.md', 'md5': '7a8f20c18faf03b3b20c6a1c7e6ffd0a', 'rows': 1}], 'fight-the-power row built from the FTP draft md5 7a8f20c1')
ok(len(s2['topics']) == 8, 'wave-2 seed holds 8 topics (7 agency + fight-the-power)')
PROF2 = {'russia-watch': 'sensitive-18', 'fight-the-power': 'sensitive-18', 'justice-system': 'sensitive-18', 'consumer-finance': 'sensitive-18',
         'environment-policy': 'standard-18', 'aviation-safety': 'standard-18', 'public-lands-policy': 'standard-18', 'public-finance': 'standard-18'}
ok({t['slug']: t['legalProfile'] for t in s2['topics']} == PROF2, 'Key 1 E1: wave-2 legal profiles (4 sensitive-18, 4 standard-18)')
ok({k: v for k, v in json.load(open(os.path.join(ROOT, 'topics', 'wave2_profiles.json')))['legalProfile'].items() if k in PROF2} == PROF2, 'topics/wave2_profiles.json holds the E1 profiles')
w1p = {t['slug']: t.get('legalProfile') for t in json.load(open(os.path.join(ROOT, 'topics', 'seed_wave1.json')))['topics']}
ok(w1p.get('foia-and-intelligence') == 'sensitive-18' and w1p.get('taxes') == 'sensitive-18', 'wave-1 precedent: foia-and-intelligence and taxes are sensitive-18')
b2 = copy.deepcopy(s2); [t.update(legalProfile='standard-18') for t in b2['topics'] if t['slug'] == 'russia-watch']
ok(any('legalProfile must be sensitive-18' in x for x in topics_seed.check_agency(b2)), 'agency seed check refuses russia-watch at standard-18')
b2 = copy.deepcopy(s2); [t.update(legalProfile='sensitive-18') for t in b2['topics'] if t['slug'] == 'public-finance']
ok(any('legalProfile must be standard-18' in x for x in topics_seed.check_agency(b2)), 'agency seed check refuses public-finance at sensitive-18')
b2 = copy.deepcopy(s2); b2['topics'][-1]['govNonAffiliation'] = True
ok(topics_seed.check_agency(b2), 'agency seed check refuses a gov flag on a non-agency row')
b2 = copy.deepcopy(s2); b2['extraSources'][0]['rows'] = 2
ok(topics_seed.check_agency(b2), 'agency seed check refuses an extra-source row count mismatch')
ok(not re.search(r'jebb|denver|\b310[-. ]|peekai|dmca-1|[\u2013\u2014]', json.dumps(s2, ensure_ascii=False).lower()), 'agency seed: no private names, contacts or dashes')
for mut, why in ((lambda t: t.update(govNonAffiliation=False), 'govNonAffiliation false'), (lambda t: t.update(status='active'), 'a non-hidden row'),
                 (lambda t: t.update(posts14d=2), 'non-zero stats'), (lambda t: t.update(slug='interior-design'), 'a wave-1 slug'),
                 (lambda t: t.update(doorwayDomains=['interiorchat.com']), 'a wave-1 doorway'), (lambda t: t.update(title='A \u2014 B'), 'a dash')):
    b2 = copy.deepcopy(s2); mut(b2['topics'][0])
    ok(topics_seed.check_agency(b2), 'agency seed check refuses %s' % why)
if os.path.isfile('/workspace/subx-hub/AGENCY_TOPICS_DRAFT_2026-11-03.md'):
    ok(topics_seed.dump(topics_seed.build_agency('/workspace/subx-hub/AGENCY_TOPICS_DRAFT_2026-11-03.md',
                                                 ['/workspace/subx-hub/FTP_TOPIC_DRAFT_2026-11-03.md'])) == open(topics_seed.AGENCY_SEED).read(),
       'wave-2 seed is what --from-agency-md --from-topic-md builds')
bad = plus({'domain': 'unknownexample.com', 'govAgency': True})
ok(any('only for doorways' in x for x in SR.resolve(bad)[1]), 'govAgency on a parked domain is refused')
bad = plus({'domain': 'unknownexample.com', 'mode': 'doorway', 'topic': 'russia-watch', 'govAgency': 'yes'})
ok(any('must be true' in x for x in SR.resolve(bad)[1]), 'govAgency other than true is refused')
bad = plus({'domain': 'unknownexample.com', 'mode': 'doorway', 'topic': 'interior-design', 'govAgency': True})
ok(any('govNonAffiliation true' in x for x in SR.resolve(bad)[1]), 'govAgency on a doorway whose topic lacks govNonAffiliation is refused')
nob = dict(brand); nob.pop('nonAffiliationGov')
ok(any('needs brand.nonAffiliationGov' in x for x in SR.resolve(cfg, brand=nob)[1]), 'govAgency without the brand key is refused')
ok(SR.plan(entries, cfg)['govAgency'] == sorted(AGENCY), 'plan.json lists the 8 agency doorways')
# ---- released doorways (Juno, 2026-11-03): six names back from the #37 hold, hidden wave-2 rows, trademark-check gate ----
import topic_status  # noqa: E402
REL = {'byobchat.com': 'byob-dining', 'carnavalchat.com': 'carnival-celebrations', 'crunkchat.com': 'crunk-music',
       'praychat.com': 'prayer', 'repentchat.com': 'repentance-and-reflection', 'wokechat.com': 'woke-culture-and-politics'}
ok(all(byd[d]['mode'] == 'doorway' and byd[d]['topic'] == t and not byd[d].get('govAgency') for d, t in REL.items()), 'the six released names are doorways to their topics')
ok(ebr.get('sensitive term (profanity, drugs, other)') == 10 and ebr.get('third-party mark (trademark review)') == 21, 'excludedByReason drops by the six released names')
s3 = json.load(open(topics_seed.RELEASED_SEED))
ok(not topics_seed.check_released(s3), 'released seed passes its check: %s' % topics_seed.check_released(s3)[:2])
ok({d: t['slug'] for t in s3['topics'] for d in t['doorwayDomains']} == REL, 'released seed doorwayDomains match the six doorways')
ok(all(t['status'] == 'hidden' and 'govNonAffiliation' not in t and not any(t.get(k) for k in topic_status.APPROVAL_FIELDS) for t in s3['topics']),
   'released topics are hidden, not agency topics, with no approval record')
ok({t['slug']: t['legalProfile'] for t in s3['topics']} == {'prayer': 'sensitive-18', 'repentance-and-reflection': 'sensitive-18',
   'woke-culture-and-politics': 'sensitive-18', 'carnival-celebrations': 'standard-18', 'crunk-music': 'standard-18', 'byob-dining': 'alcohol-21'},
   'released legal profiles: faith and politics sensitive-18, byob alcohol-21 (like cocktails-and-spirits), the rest standard-18')
ok({t['slug'] for t in s3['topics'] if t.get('approvalPrereq') == 'trademark-check'} == {'carnival-celebrations', 'crunk-music'}, 'trademark-check gate on carnival and crunk only')
allslugs = [t['slug'] for t in topics_seed.all_topics_seed()['topics']]
ok(len(allslugs) == len(set(allslugs)) == 66, 'no slug collides across wave 1, agency and released seeds (66 slugs)')
for mut, why in ((lambda t: t.pop('approvalPrereq', None), 'a gated topic without its gate'), (lambda t: t.update(slug='prayer'), 'a duplicate slug'),
                 (lambda t: t.update(legalProfile='sensitive-18'), 'a wrong profile'), (lambda t: t.update(doorwayDomains=['dojchat.com']), 'an agency doorway')):
    b3 = copy.deepcopy(s3); mut([t for t in b3['topics'] if t['slug'] == 'carnival-celebrations'][0])
    ok(topics_seed.check_released(b3), 'released seed check refuses %s' % why)
b3 = copy.deepcopy(s3); [t.update(approvalPrereq='trademark-check') for t in b3['topics'] if t['slug'] == 'byob-dining']
ok(topics_seed.check_released(b3), 'released seed check refuses a gate on an ungated topic')
NOW = '2026-11-04T05:00:00Z'
rec = {'approvedWave': 2, 'approvedBy': 'owner', 'approvedAt': '2026-11-04T04:00:00Z'}
for t in s3['topics']:
    tt = dict(t, **rec)
    ok(topic_status.approved(tt, [2], NOW) is (t.get('approvalPrereq') is None), 'approval with a valid wave-2 record: %s -> %s' % (t['slug'], t.get('approvalPrereq') is None))
g = dict([t for t in s3['topics'] if t['slug'] == 'crunk-music'][0], **rec)
st = dict(posts14d=25, distinctPosters14d=6, posts30d=25)
ok(topic_status.next_status('hidden', st, NOW, topic_status.approved(g, [2], NOW)) == 'eligible', 'a gated topic that meets the bar stays eligible (never active)')
g.pop('approvalPrereq')
ok(topic_status.approved(g, [2], NOW) is True, 'removing approvalPrereq (after the trademark check) lets the approval count')
ok(topic_status.approved(dict(g, approvalPrereq=''), [2], NOW) is False, 'any non-null approvalPrereq still blocks')
# topic page rendering: the agency topic shows the line under the title and in the footer; wave-1 pages do not
import brand_render  # noqa: E402
with tempfile.TemporaryDirectory() as tr:
    R = brand_render.Renderer(os.path.join(ROOT, 'hub', 'src'), os.path.join(ROOT, 'brand', 'brand.json'), os.path.join(tr, 'o'))
    if R is not None and hasattr(R, 'run'):
        R.run()
        for t in gov2:
            html = R.render_topic(t)
            h1 = html.index('<h1>'); g = html.find(brand_render.html_attr(GOV)); ft = html.rfind('<footer')
            ok(g > h1 and 'class="topic-gov" data-gov="title"' in html[h1:html.index('</header>')]
               and 'legal-footer-gov' in html[ft:] and html.count(brand_render.html_attr(GOV)) == 2 and '<!--' not in html,
               'topic page %s shows nonAffiliationGov under the title and in the footer' % t['slug'])
        hf = R.render_topic(ftp[0])
        ok(brand_render.html_attr(GOV) not in hf and 'topic-gov' not in hf and 'Fight the Power' in hf, 'fight-the-power page renders with no government line')
        for t in s2['topics']:
            ht = R.render_topic(t)
            ok((R.ctx['brand']['notAdvice'] in ht) == (PROF2[t['slug']] == 'sensitive-18') and '21+ only.' not in ht,
               'topic page %s legal-profile lines match %s' % (t['slug'], PROF2[t['slug']]))
        w1p0 = json.load(open(os.path.join(ROOT, 'topics', 'seed_wave1.json')))['topics']
        ok([t['legalProfile'] for t in w1p0 if t['slug'] == 'cocktails-and-spirits'] == ['alcohol-21'], 'wave-1 precedent: cocktails-and-spirits is alcohol-21')
        for t in s3['topics']:
            hr = R.render_topic(t)
            ok(('21+ only.' in hr) == (t['legalProfile'] == 'alcohol-21') and (R.ctx['brand']['notAdvice'] in hr) == (t['legalProfile'] != 'standard-18')
               and brand_render.html_attr(GOV) not in hr, 'released topic page %s legal-profile lines match %s' % (t['slug'], t['legalProfile']))
        w1 = json.load(open(os.path.join(ROOT, 'topics', 'seed_wave1.json')))['topics']
        hw = R.render_topic([t for t in w1 if t['slug'] == 'interior-design'][0])
        ok(brand_render.html_attr(GOV) not in hw and 'topic-gov' not in hw, 'a wave-1 page (interior-design) has no government line')
        try:
            R.ctx['brand'] = dict(R.ctx['brand']); R.ctx['brand'].pop('nonAffiliationGov')
            R.render_topic(s2['topics'][0]); ok(False, 'render refuses a gov topic without brand.nonAffiliationGov')
        except brand_render.RenderError:
            ok(True, 'render refuses a gov topic without brand.nonAffiliationGov')
    else:
        ok(False, 'brand_render.Renderer with run() not found')
ok('{{brand.nonAffiliationGov}}' in open(os.path.join(ROOT, 'spinup', 'README.md')).read(), 'README documents the {{brand.nonAffiliationGov}} rule')

# ---- reserved slugs (fullmatch) and platform-word labels ----
for s in ('x', 'x-com', 'xcom', 'xcorp', 'x-corp', 'twitter', 'grok', 'subx', 'admin', 'grok\n', 'Twitter'):
    bad = plus({'domain': 'unknownexample.com', 'mode': 'doorway', 'topic': s})
    ok(SR.resolve(bad)[1], 'reserved or malformed doorway slug refused: %r' % s)
for s in ('grokking-tips', 'twitter-history', 'x-files-fans'):
    bad = plus({'domain': 'unknownexample.com', 'mode': 'doorway', 'topic': s})
    ok(not SR.resolve(bad)[1], 'slug that only contains a reserved word is fine (fullmatch): %s' % s)
for d in ('twitterchat.com', 'xcorp.com', 'grok.net', 'x-com.us'):
    bad = plus({'domain': d})
    ok(any('platform word' in x for x in SR.resolve(bad)[1]), 'platform-word domain label refused: %s' % d)
bad = plus({'domain': 'twitterfans.com'})
ok(not SR.resolve(bad)[1], 'a label that only contains a platform word is fine: twitterfans.com')

# ---- consistency with topics/domains.json and the HOLD rule ----
existing = {x['domain']: x for x in json.load(open(topic_domains.DOMAINS))['domains']}
over = [e for e in entries if e['domain'] in existing]
ok(over and all(existing[e['domain']]['mode'] == e['mode'] and existing[e['domain']].get('topic') == e.get('topic') for e in over),
   'every candidate also in topics/domains.json keeps its mode and topic (%d overlap)' % len(over))
ok(byd['marineschat.com']['topic'] == 'military-life', 'marineschat follows topics/domains.json (military-life)')
bad = copy.deepcopy(cfg)
for c in bad['candidates']:
    if c['domain'] == 'awwchat.com':
        c['topic'] = 'dogs'
ok(any('topics/domains.json has' in x for x in SR.resolve(bad)[1]), 'a topic that disagrees with topics/domains.json is refused')
bad = plus({'domain': 'unknownexample.com', 'mode': 'doorway', 'topic': 'grief'})
ok(any('HOLD topic' in x for x in SR.resolve(bad)[1]), 'a doorway to a HOLD topic is refused')

# ---- rendered site.json ----
with tempfile.TemporaryDirectory() as tmp:
    dirs, e = SR.render(entries, tmp, cfg)
    ok(not e and len(dirs) == 103, 'render writes 103 site.json files with no errors')
    files = sorted(os.listdir(tmp))
    ok(files == sorted(byd), 'one dir per rendered domain, nothing else')
    sj = [json.load(open(os.path.join(d, 'site.json'))) for d in dirs]
    ok(all(set(s) <= set(SR.SITE_KEYS) for s in sj), 'site.json carries only domain/mode/topic/brand/doorway/govAgency')
    ok(all(s['brand'] == 'default' for s in sj), 'brand is the brand.json key "default"')
    ok(all(not topic_domains.validate_fields(s, 'x') for s in sj), 'every site.json passes topic_domains.validate_fields')
    ok(all('status' not in (s.get('doorway') or {}) for s in sj), 'no stored doorway status (302/301 is computed)')
    ok(all(('doorway' in s) == (s['mode'] == 'doorway') for s in sj), 'doorway settings only on doorways')
    blob = ''.join(open(os.path.join(d, 'site.json')).read() for d in dirs)
    ok(not SR.FORBIDDEN.search(blob), 'no private or barred string in the output')
    ok(not any(l in blob.lower() for l in SR.brand_literals(brand)), 'no literal brand string in the output')
    ok(not SR.drift(dirs), 'rendered dirs pass shell_drift --strict')
    vr = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'topic_domains.py'), '--validate-site'] +
                        [os.path.join(d, 'site.json') for d in dirs], capture_output=True, text=True)
    ok(vr.returncode == 0, 'rendered files pass topic_domains --validate-site')
    # drift rule for non-room dirs
    d0 = dirs[0]
    ok(shell_drift.check_nonroom(d0, 'a', json.load(open(os.path.join(d0, 'site.json'))))['status'] == 'OK', 'non-room dir with only site.json is OK')
    open(os.path.join(d0, 'index.html'), 'w').write('<p>hi</p>')
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'shell_drift.py'), d0, '--strict'], capture_output=True, text=True)
    ok(r.returncode == 1 and 'serves no files' in r.stdout, 'a doorway/parked dir with a page is DRIFT')
    os.remove(os.path.join(d0, 'index.html'))
    # P1: exactly site.json and nothing else
    def p1(setup, why):
        d1 = os.path.join(tmp, '_p1')
        os.makedirs(d1)
        shutil.copy(os.path.join(d0, 'site.json'), os.path.join(d1, 'site.json'))
        setup(d1)
        st = shell_drift.check_nonroom(d1, 'a', json.load(open(os.path.join(d1, 'site.json'))))['status']
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'shell_drift.py'), d1, '--strict'], capture_output=True, text=True)
        ok(st == 'DRIFT' and r.returncode == 1 and '| DRIFT |' in r.stdout, 'P1: %s is DRIFT' % why)
        shutil.rmtree(d1)
    p1(lambda d: os.mkdir(os.path.join(d, 'empty')), 'an empty subdirectory')
    p1(lambda d: os.mkdir(os.path.join(d, '.git')), 'a .git directory')
    p1(lambda d: os.makedirs(os.path.join(d, 'a', 'b')), 'nested empty subdirectories')
    p1(lambda d: open(os.path.join(d, '.htaccess'), 'w').write('x'), 'a dot-file')
    p1(lambda d: open(os.path.join(d, 'robots.txt'), 'w').write('x'), 'any other file')
    p1(lambda d: os.symlink('/etc/hostname', os.path.join(d, 'link')), 'a symlink beside site.json')
    p1(lambda d: os.symlink(tmp, os.path.join(d, 'dirlink')), 'a symlink to a directory')
    def swap(d):
        real = os.path.join(tmp, '_real_site.json')
        os.replace(os.path.join(d, 'site.json'), real)
        os.symlink(real, os.path.join(d, 'site.json'))
    p1(swap, 'site.json as a symlink')
    # list-valued (and other non-object) site.json: DRIFT, no exception
    for val, why in (([], 'an empty list'), ([{'mode': 'doorway'}], 'a list'), ('doorway', 'a string'), (7, 'a number'), (None, 'null')):
        d2 = os.path.join(tmp, '_list')
        os.makedirs(d2)
        open(os.path.join(d2, 'site.json'), 'w').write(json.dumps(val))
        try:
            res = shell_drift.check(d2, shell_drift.load_manifests() if hasattr(shell_drift, 'load_manifests') else None)
            okc = res['status'] == 'DRIFT' and any('JSON object' in x for x in res['findings'])
        except Exception as ex:  # noqa: BLE001
            okc = False
            print('     exception: %r' % ex)
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'shell_drift.py'), d2, '--strict'], capture_output=True, text=True)
        ok(okc and r.returncode == 1 and 'Traceback' not in r.stderr and '| DRIFT |' in r.stdout,
           'site.json that is %s is DRIFT with no exception' % why)
        shutil.rmtree(d2)
    ag = [d for d in dirs if os.path.basename(d) == 'dojchat.com'][0]
    ok(shell_drift.check_nonroom(ag, 'a', json.load(open(os.path.join(ag, 'site.json'))))['status'] == 'OK', 'drift allows govAgency on a doorway')
    s = dict(json.load(open(os.path.join(ag, 'site.json')))); s['mode'] = 'parked'; s.pop('doorway'); s.pop('topic')
    ok(shell_drift.check_nonroom(ag, 'a', s)['status'] == 'DRIFT', 'drift refuses govAgency on a parked dir')
    for extra, why in (({'shell': {'base': 'v1'}}, 'shell block'), ({'mode': 'portal'}, 'unknown mode'), ({'name': 'Z'}, 'room key'), ({'govAgency': 1}, 'govAgency not true')):
        s = dict(json.load(open(os.path.join(d0, 'site.json')))); s.update(extra)
        ok(shell_drift.check_nonroom(d0, 'a', s)['status'] == 'DRIFT', 'non-room site.json with %s is DRIFT' % why)
    inside = os.path.join(ROOT, 'hub', 'spinup-test')
    _, e = SR.render(entries[:1], inside, cfg)
    ok(e and not os.path.exists(inside), 'render refuses an out dir in hub/ and writes nothing')
    _, e = SR.render(entries[:1], os.path.join(ROOT, 'topics', 'x'), cfg)
    ok(e and not os.path.exists(os.path.join(ROOT, 'topics', 'x')), 'render refuses an out dir elsewhere in the repo')
ok(SR.out_dir_ok(os.path.join(ROOT, 'spinup', 'out')) and SR.out_dir_ok(os.path.join(ROOT, 'spinup', 'out', 'a')),
   'spinup/out/ (git-ignored) is allowed')
# P2: realpath; a path that only looks like spinup/out but resolves elsewhere in the repo is refused
ok(not SR.out_dir_ok(os.path.join(ROOT, 'spinup', 'out', '..', '..', 'hub')), 'spinup/out/../../hub is refused (realpath)')
ok(not SR.out_dir_ok(os.path.join(ROOT, 'spinup')), 'spinup/ itself is refused')
ok(not SR.out_dir_ok(ROOT), 'the repo root is refused')
with tempfile.TemporaryDirectory() as t2:
    ok(SR.out_dir_ok(os.path.join(t2, 'o')), 'a dir outside the repo is allowed')
    ln = os.path.join(t2, 'to-hub')
    os.symlink(os.path.join(ROOT, 'hub'), ln)
    ok(not SR.out_dir_ok(ln) and SR.render(entries[:1], ln, cfg)[1], 'a symlink outside the repo that points into hub/ is refused')
out_ok = os.path.join(ROOT, 'spinup', 'out')
if not os.path.lexists(out_ok):
    with tempfile.TemporaryDirectory() as t3:
        os.symlink(t3, out_ok)
        try:
            ok(not SR.out_dir_ok(out_ok) and not SR.out_dir_ok(os.path.join(out_ok, 'a')), 'P2: a symlinked spinup/out is refused')
            _, e = SR.render(entries[:1], out_ok, cfg)
            ok(e and not os.listdir(t3), 'P2: render into a symlinked spinup/out is refused and writes nothing')
        finally:
            os.remove(out_ok)
    os.symlink(os.path.join(ROOT, 'hub'), out_ok)
    try:
        ok(not SR.out_dir_ok(out_ok), 'P2: spinup/out symlinked into hub/ is refused')
    finally:
        os.remove(out_ok)
else:
    ok(not os.path.islink(out_ok), 'existing spinup/out is a real dir (symlink tests skipped)')
ok('spinup/out/' in open(os.path.join(ROOT, '.gitignore')).read().split('\n'), 'spinup/out/ is git-ignored')

# ---- forbidden-string guard catches the hard-rule items ----
for bad_s in ('owner@gmail.com', '(310) 555-0100', '310-555-0100', 'registered agent', 'Denver, CO', 'PEEKAI', 'DMCA-1'):
    ok(SR.output_errors('f', bad_s, brand), 'guard catches %r' % bad_s)
ok(not SR.output_errors('f', '{"domain": "310chat.com", "topic": "denver"}', brand), 'domain/city names alone are not flagged')
ok(SR.output_errors('f', 'Visit ' + brand['name'], brand), 'guard catches a literal brand name')

# ---- redirects: config only, 302 while hidden or unseeded, 301 after 60 days active ----
lines = SR.redirects(entries, '2026-11-03T00:00:00Z')
dl = [l for l in lines if not l.startswith('#')]
ok(len(dl) == 94 and all(l.endswith(' 302') for l in dl), 'every doorway plans 302 today (no topic active 60 days)')
ok(all('{{brand.primaryDomain}}{{brand.topicPathPrefix}}' in l for l in dl), 'redirect targets use brand placeholders')
seed = {'topics': [{'slug': 'seattle', 'status': 'active', 'activatedAt': '2026-08-01T00:00:00Z', 'doorwayDomains': []}]}
one = [e for e in entries if e['domain'] == '206chat.com']
ok(SR.redirects(one, '2026-11-03T00:00:00Z', seed)[0].endswith(' 301'), 'active 60+ days -> 301')
ok(SR.redirects(one, '2026-09-01T00:00:00Z', seed)[0].endswith(' 302'), 'active < 60 days -> 302')
seed['topics'][0]['status'] = 'hidden'
ok(SR.redirects(one, '2027-11-03T00:00:00Z', seed)[0].endswith(' 302'), 'hidden -> 302')

# ---- off-repo list (box only, if present): none of its names is in any tracked file ----
BOX = os.environ.get('SPINUP_EXCLUSIONS', '/workspace/subx-hub/from-vesta/SPINUP_EXCLUSIONS_2026-11-03.txt')
if os.path.isfile(BOX):
    held = SR.load_exclusions(BOX)
    blob = ''
    for f in subprocess.run(['git', 'ls-files', 'spinup', 'tools/spinup_render.py', 'test/spinup.test.py', 'tools/shell_drift.py'],
                            cwd=ROOT, capture_output=True, text=True).stdout.split():
        blob += open(os.path.join(ROOT, f), encoding='utf-8', errors='replace').read().lower()
    tok = lambda k: re.search(r'(?<![a-z0-9-])%s(?![a-z0-9-])' % re.escape(k), blob)  # whole names, not substrings
    hit = sorted(h for h in held if tok(h) or tok(h.split('.')[0]))
    ok(not hit, 'no off-repo held name in spinup files (%d names checked, %d hit)' % (len(held), len(hit)))
    ok(not (held & set(byd)), 'no held name is a candidate')
else:
    print('skip off-repo exclusion list (not on this machine)')

# ---- plan.json and --check write nothing ----
p = SR.plan(entries, cfg)
ok(open(SR.PLAN).read() == SR.dump(p), 'spinup/plan.json is current')
ok(all(set(r) <= {'domain', 'mode', 'topic', 'topicSeeded', 'ownership', 'govAgency'} for r in p['domains']), 'plan rows carry no hash')
ok(p['byMode'] == modes and p['rendered'] == 103 and p['excluded'] == 48 and p['excludedByReason'] == ebr, 'plan counts match')
before = subprocess.run(['git', 'status', '--porcelain', '--ignored'], cwd=ROOT, capture_output=True, text=True).stdout
r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'spinup_render.py'), '--check'], capture_output=True, text=True)
after = subprocess.run(['git', 'status', '--porcelain', '--ignored'], cwd=ROOT, capture_output=True, text=True).stdout
ok(r.returncode == 0 and 'nothing written' in r.stdout, '--check passes: %s' % (r.stdout.strip() or r.stderr.strip())[:200])
ok(before == after, '--check writes nothing in the repo')

print('\n%d failed' % len(fails) if fails else '\nall spinup tests ok')
sys.exit(1 if fails else 0)
