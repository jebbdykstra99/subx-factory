#!/usr/bin/env python3
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'tools'))
from botclass import classify, classify_ai_source, summarize

cases = json.load(open(os.path.join(HERE, 'fixture_cases.json')))
bad = 0
for exp, h in cases:
    got, why = classify(h)
    if got != exp:
        bad += 1
        print('FAIL', exp, got, why, h)

hits = [dict(h, siteId='gpchat') for _, h in cases] + [dict(cases[0][1], siteId='gpchat'), dict(cases[5][1], siteId='gpchat')]
s = summarize(hits)['gpchat']
ok = s['uniqueHumans'] == 5 and s['uniqueBots'] == 14 and s['uniqueUnverified'] == 1 and s['internal'] == 2
if not ok:
    bad += 1
    print('FAIL summary', s)

# Test AI crawler + AI referrer analytics (#2 & #38)
s2 = summarize([
    {'siteId': 'gpchat', 'vid': 'm9x1k2p8q4r7t0', 'ua': 'Mozilla/5.0 Chrome/131.0', 'ref': 'https://chatgpt.com/c/123'},
    {'siteId': 'gpchat', 'vid': 'm9x1k2p8q4r7t0', 'ua': 'Mozilla/5.0 Chrome/131.0'},
    {'siteId': 'gpchat', 'vid': 'botvid12345678', 'ua': 'Mozilla/5.0 (compatible; GPTBot/1.2)'},
    {'siteId': 'gpchat', 'vid': 'botvid99999999', 'ua': 'Mozilla/5.0 (compatible; PerplexityBot/1.0)'},
])['gpchat']
assert s2['aiAgentHits'] == 2 and s2['aiReferrerHits'] == 1, s2
assert s2['aiSources'] == {'gptbot': 1, 'perplexitybot': 1, 'ref:chatgpt.com': 1}, s2
assert classify_ai_source({'ua': 'Mozilla/5.0', 'ref': 'https://www.perplexity.ai/search/foo'}) == ('ai-referrer', 'perplexity.ai')
print(f'botclass: {len(cases)+2-bad}/{len(cases)+2} pass')
sys.exit(1 if bad else 0)
