#!/usr/bin/env python3
"""Spin-up dry run (tools/spinup_render.py): candidates config, modes, exclusions, reserved slugs, rendered site.json,
the non-room drift rule, and the no-write --check. Python stdlib only."""
import copy, json, os, re, subprocess, sys, tempfile

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

# ---- counts: never invented, every inventory name accounted for ----
inv = cfg['source']['inventory']
ok(inv == 151, 'inventory is the 151 names in the plan')
ok(len(cfg['candidates']) + len(cfg['excluded']) == inv, 'candidates + excluded = inventory (%d + %d)' % (len(cfg['candidates']), len(cfg['excluded'])))
ok(len(entries) == 112 and len(cfg['excluded']) == 39, 'rendered 112, excluded 39')
modes = {m: sum(1 for e in entries if e['mode'] == m) for m in SR.MODES}
ok(modes == {'room': 0, 'doorway': 98, 'parked': 14}, 'by mode: %s' % modes)
ok(len({c['domain'] for c in cfg['candidates']}) == len(cfg['candidates']), 'no candidate listed twice')

# ---- exclusions: by sha256 only, never by name; an excluded domain can't come back ----
txt = open(SR.CANDIDATES).read().lower()
for name in ('muskchat', 'grokchat', 'kardashianchat', 'mournchat', 'lockechat', 'holmeschat', 'luzchat', 'dots.com'):
    ok(name not in txt, 'excluded name not written in candidates.json: %s' % name)
for d in ('grokchat.com', 'muskchat.com', 'mournchat.com', 'lockechat.com'):
    ok(SR.sha(d) in {x['sha256'] for x in cfg['excluded']}, 'excluded by hash: %s' % d)
    bad = copy.deepcopy(cfg)
    bad['candidates'].append({'domain': d, 'mode': 'parked'})
    _, e = SR.resolve(bad)
    ok(any('excluded' in x for x in e), 'excluded domain re-added as a candidate is refused: %s' % d)
reasons = {x['reason'] for x in cfg['excluded']}
ok(all(r.startswith('hold: ') for r in reasons), 'every exclusion has a hold reason')
bad = copy.deepcopy(cfg); bad['excluded'].append({'sha256': 'nothex', 'reason': 'x'})
ok(any('needs a sha256' in x for x in SR.resolve(bad)[1]), 'a malformed exclusion is refused')
bad = copy.deepcopy(cfg); bad['excluded'].append({'sha256': '0' * 64, 'reason': ' '})
ok(any('needs a sha256' in x for x in SR.resolve(bad)[1]), 'an exclusion without a reason is refused')

# ---- modes and defaults ----
ok(cfg['defaults']['mode'] == 'parked', 'defaults.mode is parked')
for c in cfg['candidates']:
    if 'mode' not in c:
        ok(byd[c['domain']]['mode'] == 'parked' and 'topic' not in byd[c['domain']], 'no mode -> parked, no topic: %s' % c['domain'])
bad = copy.deepcopy(cfg); bad['candidates'].append({'domain': 'unknownexample.com'})
e2, er = SR.resolve(bad)
ok(not er and [x for x in e2 if x['domain'] == 'unknownexample.com'][0]['mode'] == 'parked', 'an unknown domain defaults to parked')
bad = copy.deepcopy(cfg); bad['defaults']['mode'] = 'doorway'
ok(any('defaults.mode must be parked' in x for x in SR.resolve(bad)[1]), 'defaults.mode other than parked is refused')
bad = copy.deepcopy(cfg); bad['defaults']['brand'] = 'SubX'
ok(any('defaults.brand' in x for x in SR.resolve(bad)[1]), 'a literal brand in defaults is refused')
for m, why in (('redirect', 'unknown mode'), ('room', 'room without a live room')):
    bad = copy.deepcopy(cfg); bad['candidates'].append({'domain': 'unknownexample.com', 'mode': m})
    ok(SR.resolve(bad)[1], 'refused: %s' % why)
bad = copy.deepcopy(cfg); bad['candidates'].append({'domain': 'unknownexample.com', 'mode': 'doorway'})
ok(any('needs a topic' in x for x in SR.resolve(bad)[1]), 'a doorway without a topic is refused')
live = sorted(topic_domains.room_domains())[0]
bad = copy.deepcopy(cfg); bad['candidates'].append({'domain': live, 'mode': 'parked'})
ok(any('live room serves it' in x for x in SR.resolve(bad)[1]), 'a live room domain is never a candidate')
bad = copy.deepcopy(cfg); bad['candidates'].append({'domain': 'Upper.com'})
ok(any('not a lowercase domain' in x for x in SR.resolve(bad)[1]), 'an uppercase domain is refused')
bad = copy.deepcopy(cfg); bad['candidates'].append({'domain': 'abc.com\n'})
ok(any('not a lowercase domain' in x for x in SR.resolve(bad)[1]), 'a domain with a trailing newline is refused (fullmatch)')
bad = copy.deepcopy(cfg); bad['candidates'].append(dict(bad['candidates'][0]))
ok(any('listed twice' in x for x in SR.resolve(bad)[1]), 'a duplicate candidate is refused')

# ---- reserved slugs (fullmatch) and platform-word labels ----
for s in ('x', 'x-com', 'xcom', 'xcorp', 'x-corp', 'twitter', 'grok', 'subx', 'admin', 'grok\n', 'Twitter'):
    bad = copy.deepcopy(cfg); bad['candidates'].append({'domain': 'unknownexample.com', 'mode': 'doorway', 'topic': s})
    ok(SR.resolve(bad)[1], 'reserved or malformed doorway slug refused: %r' % s)
for s in ('grokking-tips', 'twitter-history', 'x-files-fans'):
    bad = copy.deepcopy(cfg); bad['candidates'].append({'domain': 'unknownexample.com', 'mode': 'doorway', 'topic': s})
    ok(not SR.resolve(bad)[1], 'slug that only contains a reserved word is fine (fullmatch): %s' % s)
for d in ('twitterchat.com', 'xcorp.com', 'grokchat.net', 'x-com.us'):
    bad = copy.deepcopy(cfg); bad['candidates'].append({'domain': d})
    ok(any('platform word' in x or 'excluded' in x for x in SR.resolve(bad)[1]), 'platform-word domain label refused: %s' % d)
bad = copy.deepcopy(cfg); bad['candidates'].append({'domain': 'twitterfans.com'})
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
bad = copy.deepcopy(cfg); bad['candidates'].append({'domain': 'unknownexample.com', 'mode': 'doorway', 'topic': 'grief'})
ok(any('HOLD topic' in x for x in SR.resolve(bad)[1]), 'a doorway to a HOLD topic is refused')

# ---- rendered site.json ----
with tempfile.TemporaryDirectory() as tmp:
    dirs, e = SR.render(entries, tmp, cfg)
    ok(not e and len(dirs) == 112, 'render writes 112 site.json files with no errors')
    files = sorted(os.listdir(tmp))
    ok(files == sorted(byd), 'one dir per rendered domain, nothing else')
    sj = [json.load(open(os.path.join(d, 'site.json'))) for d in dirs]
    ok(all(set(s) <= set(SR.SITE_KEYS) for s in sj), 'site.json carries only domain/mode/topic/brand/doorway')
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
    for extra, why in (({'shell': {'base': 'v1'}}, 'shell block'), ({'mode': 'portal'}, 'unknown mode'), ({'name': 'Z'}, 'room key')):
        s = dict(json.load(open(os.path.join(d0, 'site.json')))); s.update(extra)
        ok(shell_drift.check_nonroom(d0, 'a', s)['status'] == 'DRIFT', 'non-room site.json with %s is DRIFT' % why)
    inside = os.path.join(ROOT, 'hub', 'spinup-test')
    _, e = SR.render(entries[:1], inside, cfg)
    ok(e and not os.path.exists(inside), 'render refuses an out dir in hub/ and writes nothing')
    _, e = SR.render(entries[:1], os.path.join(ROOT, 'topics', 'x'), cfg)
    ok(e and not os.path.exists(os.path.join(ROOT, 'topics', 'x')), 'render refuses an out dir elsewhere in the repo')
ok(SR.out_dir_ok(os.path.join(ROOT, 'spinup', 'out')) and SR.out_dir_ok(os.path.join(ROOT, 'spinup', 'out', 'a')),
   'spinup/out/ (git-ignored) is allowed')
ok('spinup/out/' in open(os.path.join(ROOT, '.gitignore')).read().split('\n'), 'spinup/out/ is git-ignored')

# ---- forbidden-string guard catches the hard-rule items ----
for bad_s in ('owner@gmail.com', '(310) 555-0100', '310-555-0100', 'registered agent', 'Denver, CO', 'PEEKAI', 'VokaDots', 'DMCA-1'):
    ok(SR.output_errors('f', bad_s, brand), 'guard catches %r' % bad_s)
ok(not SR.output_errors('f', '{"domain": "310chat.com", "topic": "denver"}', brand), 'domain/city names alone are not flagged')
ok(SR.output_errors('f', 'Visit ' + brand['name'], brand), 'guard catches a literal brand name')

# ---- redirects: config only, 302 while hidden or unseeded, 301 after 60 days active ----
lines = SR.redirects(entries, '2026-11-03T00:00:00Z')
dl = [l for l in lines if not l.startswith('#')]
ok(len(dl) == 98 and all(l.endswith(' 302') for l in dl), 'every doorway plans 302 today (no topic active 60 days)')
ok(all('{{brand.primaryDomain}}{{brand.topicPathPrefix}}' in l for l in dl), 'redirect targets use brand placeholders')
seed = {'topics': [{'slug': 'seattle', 'status': 'active', 'activatedAt': '2026-08-01T00:00:00Z', 'doorwayDomains': []}]}
one = [e for e in entries if e['domain'] == '206chat.com']
ok(SR.redirects(one, '2026-11-03T00:00:00Z', seed)[0].endswith(' 301'), 'active 60+ days -> 301')
ok(SR.redirects(one, '2026-09-01T00:00:00Z', seed)[0].endswith(' 302'), 'active < 60 days -> 302')
seed['topics'][0]['status'] = 'hidden'
ok(SR.redirects(one, '2027-11-03T00:00:00Z', seed)[0].endswith(' 302'), 'hidden -> 302')

# ---- plan.json and --check write nothing ----
p = SR.plan(entries, cfg)
ok(open(SR.PLAN).read() == SR.dump(p), 'spinup/plan.json is current')
ok(p['byMode'] == modes and p['rendered'] == 112 and p['excluded'] == 39, 'plan counts match')
before = subprocess.run(['git', 'status', '--porcelain', '--ignored'], cwd=ROOT, capture_output=True, text=True).stdout
r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'spinup_render.py'), '--check'], capture_output=True, text=True)
after = subprocess.run(['git', 'status', '--porcelain', '--ignored'], cwd=ROOT, capture_output=True, text=True).stdout
ok(r.returncode == 0 and 'nothing written' in r.stdout, '--check passes: %s' % (r.stdout.strip() or r.stderr.strip())[:200])
ok(before == after, '--check writes nothing in the repo')

print('\n%d failed' % len(fails) if fails else '\nall spinup tests ok')
sys.exit(1 if fails else 0)
