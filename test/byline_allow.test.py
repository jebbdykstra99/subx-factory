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
    ('span-byline', '<div class="meta"><span class="byline">By Jebb Dykstra</span></div>'),
    ('strong-byline', '<header><strong>By Jebb Dykstra</strong></header>'),
    ('byline-with-date', '<p class="byline"><em>By Jebb Dykstra</em> · Nov 5, 2026</p>'),
    ('byline-split-markup', '<p class="byline">By <strong>Jebb Dykstra</strong></p>'),
    ('27chat-story-shape-subx-pill', '<p><em>By Jebb Dykstra, Juno, Vesta and Iris</em>'
        '<span class="whomark-slot" data-whomark="hybrid" hidden></span> '
        '<span class="post-steward-pill" title="Human + AI. Operated by SubX, LLC.">Human + AI</span></p>'),
]
for name, html in PASS:
    ok(BA.is_name_clean(html), 'PASS %s is clean' % name)

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
    # Key 1 reviewer leaks (2026-11-05): each passed the first allowlist and must fail.
    ('footer-class-byline-operated', '<footer class="byline">Operated By Jebb Dykstra</footer>'),
    ('body-class-byline-page', '<body class="byline"><p>By Jebb Dykstra</p><p>Operator: Jebb Dykstra</p></body>'),
    ('body-class-byline-bare', '<body class="byline">By Jebb Dykstra</body>'),
    ('div-starts-with-byline-masks-reviewer', '<div><p>By Jebb Dykstra</p> Reviewer: By Jebb Dykstra</div>'),
    ('div-byline-then-reviewer', '<div>By Jebb Dykstra. Reviewer: By Jebb Dykstra</div>'),
    ('p-byline-then-reviewer', '<p>By Jebb Dykstra. Reviewer: By Jebb Dykstra</p>'),
    ('p-two-em-bylines', '<p><em>By Jebb Dykstra</em> Reviewer: <em>By Jebb Dykstra</em></p>'),
    ('div-class-byline', '<div class="byline">By Jebb Dykstra</div>'),
    ('section-class-byline', '<section class="byline">By Jebb Dykstra</section>'),
    ('header-class-byline', '<header class="byline">By Jebb Dykstra</header>'),
    ('address-class-byline', '<address class="byline">By Jebb Dykstra</address>'),
    ('li-class-byline', '<li class="byline">By Jebb Dykstra</li>'),
    ('footer-p-byline', '<footer><p class="byline">By Jebb Dykstra</p></footer>'),
    ('class-not-byline', '<p class="not-byline">By Jebb Dykstra</p>'),
    ('class-byline-suffix', '<p class="byline-x">By Jebb Dykstra</p>'),
    ('inner-class-not-byline', '<p class="byline"><em class="not-byline">By Jebb Dykstra</em></p>'),
    ('data-author-attr', '<p class="byline" data-author="Jebb Dykstra">By Jebb Dykstra</p>'),
    ('href-attr', '<p class="byline"><a href="/u/jebb-dykstra">By Jebb Dykstra</a></p>'),
    ('href-attr-span', '<p class="byline">By Jebb Dykstra <span data-href="https://x.com/jebbdykstra">x</span></p>'),
    ('title-over-120', '<p>By Jebb Dykstra <span title="' + 'x' * 130 + ' By Jebb Dykstra">i</span></p>'),
    ('title-attr-byline-only', '<span class="byline" title="By Jebb Dykstra">By SubX</span>'),
    ('title-element', '<title>By Jebb Dykstra</title>'),
    ('html-comment', '<p>By Jebb Dykstra<!-- By Jebb Dykstra --></p>'),
    ('html-comment-only', '<!-- <p class="byline">By Jebb Dykstra</p> -->'),
    ('dykstrafoo', '<p>By Jebb Dykstrafoo</p>'),
    ('co-byline-no-boundary', '<p>By Jebb Dykstra, Juno, Vesta and IrisDykstra</p>'),
    ('over-80-visible', '<p class="byline">By Jebb Dykstra, ' + 'with notes ' * 8 + '</p>'),
    ('byline-plus-role', '<p class="byline">By Jebb Dykstra, operator of SubX</p>'),
    ('hidden-byline-span', '<span class="byline" hidden>By Jebb Dykstra</span>'),
    ('script-byline', '<script>document.write("<p>By Jebb Dykstra</p>")</script>'),
    ('llms-markdown-byline', '# By Jebb Dykstra, Juno, Vesta and Iris\n'),
]
for name, html in FAIL:
    ok(not BA.is_name_clean(html), 'FAIL %s is flagged' % name)

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
    ok(BA.is_name_clean(body), 'temp about.html with byline + SubX operator is clean')

# ---- live room shapes (offline copies of gaichat about.html line, 27chat story) ----
GAICHAT_LINE = '    <p class="byline"><em>By Jebb Dykstra, Juno, Vesta and Iris</em></p>'
ok(BA.is_name_clean(GAICHAT_LINE), 'gaichat about.html byline line (p.byline > em) is clean')
ok('Jebb' not in BA.mask_allowed_bylines(GAICHAT_LINE) and '<p class="byline"><em>' in BA.mask_allowed_bylines(GAICHAT_LINE),
   'mask only blanks visible phrase chars, markup kept byte-for-byte')
ok(len(BA.mask_allowed_bylines(GAICHAT_LINE)) == len(GAICHAT_LINE), 'mask keeps offsets (same length)')

# ---- E4 word boundary on the co-byline: only the solo phrase is masked ----
m_iris = BA.mask_allowed_bylines('<p>By Jebb Dykstra, Juno, Vesta and Irisfoo</p>')
ok('Juno, Vesta and Irisfoo' in m_iris and 'Jebb' not in m_iris, 'co-byline needs a word boundary after Iris (solo phrase masked only)')

# ---- one phrase per element: second phrase always left visible ----
two = '<p>By Jebb Dykstra. By Jebb Dykstra</p>'
ok(BA.mask_allowed_bylines(two).count('Jebb') == 1, 'at most one phrase masked per qualifying element')

print('\n%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)
