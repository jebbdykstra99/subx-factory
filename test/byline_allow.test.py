#!/usr/bin/env python3
"""Author-byline allowlist (decision 2026-11-05): bylines pass; operator/meta/JSON-LD fail."""
import os, re, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import byline_allow as BA  # noqa: E402

fails = []


def ok(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        fails.append(msg)


# ---- built-in fixture matrix ----
try:
    BA.assert_fixture_matrix()
    ok(True, 'assert_fixture_matrix passes')
except AssertionError as e:
    ok(False, 'assert_fixture_matrix: %s' % e)

# ---- PASS: visible bylines ----
PASS = [
    ('class-byline-team', '<p class="byline"><em>By Jebb Dykstra, Juno, Vesta and Iris</em></p>'),
    ('class-byline-solo', '<p class="byline">By Jebb Dykstra</p>'),
    ('class-byline-extra-classes', '<p class="lede byline hero"><em>By Jebb Dykstra</em></p>'),
    ('story-co-byline-em', '<p><em>By Jebb Dykstra, Juno, Vesta and Iris</em></p>'),
    ('story-co-byline-plain', '<p>By Jebb Dykstra, Juno, Vesta and Iris</p>'),
    ('gaichat-about-shape', '<p class="byline"><em>By Jebb Dykstra, Juno, Vesta and Iris</em></p>\n'
                            '<p>Gen AI is operated by <strong>SubX, LLC</strong>.</p>'),
    ('repo-path-only', 'cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@deadbeef/factory.js'),
]
for name, html in PASS:
    ok(BA.is_clean(html), 'PASS %s is clean' % name)

# ---- FAIL: every non-byline context ----
FAIL = [
    ('meta-author', '<meta name="author" content="Jebb Dykstra, Juno, Vesta and Iris">'),
    ('meta-author-solo', '<meta name="author" content="Jebb Dykstra">'),
    ('jsonld-publisher', '{"@type":"Organization","publisher":{"@type":"Organization","name":"Jebb Dykstra"}}'),
    ('jsonld-provider', '{"provider":{"name":"Jebb Dykstra"}}'),
    ('operator-line', '<p>gaichat.com is operated by Jebb Dykstra, a Colorado LLC.</p>'),
    ('footer-operator', '<footer class="legal-footer">Operator: Jebb Dykstra · takedown@subx.it</footer>'),
    ('llms-operator', '# llms.txt\n> Operator: Jebb Dykstra\n'),
    ('reviewer-line', '<p>Appeals go to a human reviewer at Jebb Dykstra via takedown@subx.it.</p>'),
    ('agent-line', '<p>Designated agent: Jebb Dykstra</p>'),
    ('steward-pill-title', '<span class="post-steward-pill" title="Made by Jebb Dykstra, a person, '
                           'with AI agents Juno, Vesta and Iris, run by SubX, LLC.">Human + AI</span>'),
    ('prose-contact', '<p>Contact Jebb Dykstra for help.</p>'),
    ('lowercase-by-prose', '<p>This post was written by Jebb Dykstra overnight.</p>'),
    ('jsonld-author-person', '{"author":{"@type":"Person","name":"Jebb Dykstra"}}'),
]
for name, html in FAIL:
    ok(not BA.is_clean(html), 'FAIL %s is flagged' % name)

# ---- mask leaves forbidden contexts intact for a FORBID-style scan ----
sample = (
    '<p class="byline"><em>By Jebb Dykstra, Juno, Vesta and Iris</em></p>\n'
    '<meta name="author" content="Jebb Dykstra">\n'
    '<p>operated by Jebb Dykstra</p>\n'
)
masked = BA.mask_allowed_bylines(sample)
ok('By Jebb' not in masked and 'class="byline"' in masked, 'mask removes byline phrase, keeps markup')
ok('content="Jebb Dykstra"' in masked, 'mask leaves meta author intact so FORBID still sees it')
ok('operated by Jebb Dykstra' in masked, 'mask leaves operator line intact')
hits = BA.find_name_hits(sample)
ok(len(hits) >= 2 and all('byline' not in h.lower() or 'Jebb' in h or 'jebb' in h.lower() for h in hits),
   'find_name_hits reports meta + operator, not the byline (%s)' % hits)

# ---- wire-check: hub_brand FORBID style after mask ----
FORBID = [re.compile(x, re.I) for x in (
    r'\bjebb(?!dykstra99/subx-factory\b)',
)]
hub_ok = '<p class="byline">By Jebb Dykstra</p><p>Operated by SubX, LLC.</p>'
hub_bad = '<p class="byline">By Jebb Dykstra</p><p>Operated by Jebb Dykstra.</p>'
ok(not [m.group(0) for rx in FORBID for m in rx.finditer(BA.mask_allowed_bylines(hub_ok))],
   'hub FORBID after mask: byline-only page is clean')
ok(any(True for rx in FORBID for m in rx.finditer(BA.mask_allowed_bylines(hub_bad))),
   'hub FORBID after mask: operator line with Jebb still hits')

# ---- file round-trip helper for live / PR scans ----
with tempfile.TemporaryDirectory() as t:
    p = os.path.join(t, 'about.html')
    open(p, 'w').write(PASS[5][1])  # gaichat-about-shape
    body = open(p).read()
    ok(BA.is_clean(body), 'temp about.html with byline + SubX operator is clean')

print('\n%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)
