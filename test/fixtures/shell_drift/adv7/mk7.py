# Review fixes for PR #31 (Key 2 at 7aa0716): comment ends, URL normalization, redirects paths, keep Firebase,
# index.html is never a stub. Run from this folder: python3 mk7.py
import sys; sys.path.insert(0, '../adv4')
exec(open('../adv4/mk4.py').read().split('# noShell')[0])
EV = 'https://evil.example/x.js'
EVS = '<script src="%s"></script>' % EV
STUB = "<html><head><script>location.replace('/')</script>%s</head></html>"
R = {'redirects': ['go.html']}
NS = {'noShell': ['terms.html'], 'keep': [keep('takedown.js', TD)]}
NSP = '<html><head><script src="takedown.js"></script>%s</head></html>'
# B1-B3: comment ends browsers honour (<!-->, <!--->, --!>) on a stub, on the pinned index.html and on a noShell page
for i, c in enumerate(['<!-->%s-->', '<!-- x --!>%s -->', '<!--->%s-->']):
    mk('k%d_stub_comment' % i, PIN, R, None, {'go.html': STUB % (c % EVS)})
    mk('k%d_index_comment' % i, PIN + (c % EVS))
    mk('k%d_noshell_comment' % i, PIN, NS, {'takedown.js': TD}, {'terms.html': NSP % (c % EVS)})
# B4: a script src browsers read as //evil.example (backslash, entity-encoded tab), even with a keep file at that literal
# path. The keep files themselves (named with a backslash / a tab) are written by the test at run time, not committed.
BS = '/* looks local */\n'
mk('n0_src_backslash_keep', '<script src="/\\evil.example/x.js"></script>' + PIN, {'keep': [keep('\\evil.example/x.js', BS)]})
mk('n1_src_tab_entity_keep', '<script src="/&#9;/evil.example/x.js"></script>' + PIN, {'keep': [keep('\t/evil.example/x.js', BS)]})
mk('n2_src_newline', '<script src="/\n/evil.example/x.js"></script>' + PIN)
mk('n3_import_backslash', PIN, {'overrides': {'modules': [keep('lib/m.js', "import '/\\\\evil.example/x.js';")]}},
   {'lib/m.js': "import '/\\\\evil.example/x.js';"}, {'about.html': '<html>%s<script type="module" src="lib/m.js"></script></html>' % PIN})
# B5: meta refresh off the origin on ordinary (non-stub) pages
for i, u in enumerate(['/\\evil.example/', '/&#9;/evil.example/', '\\\\evil.example/', ' &#10;//evil.example/']):
    mk('r%d_refresh' % i, PIN, None, None, {'go.html': '<html><head><meta http-equiv="refresh" content="0;url=%s"></head></html>' % u})
# B6: shell.redirects entries must name a page inside the room
for i, x in enumerate(['../outside.html', '/../outside.html', 'nest\\go.html', 'https://evil.example/go.html', '%2e%2e/outside.html',
                       '//evil.example/go.html', 'nest/../../outside.html']):
    mk('d%d_redirects_outside' % i, PIN, {'redirects': [x]}, {'nest/go.html': STUB % ''})
# B7: a keep file loaded on a noShell page may not name the Firebase SDK (even with "injects" declared)
for i, body in enumerate(["import('https://www.gstatic.com/firebasejs/10.0.0/firebase-app.js');\n",
                          "var s=document.createElement('script');s.src='/__/firebase/init.js';document.head.appendChild(s);\n",
                          "/* https://cdn.jsdelivr.net/npm/firebase@10/firebase-app.js */\n"]):
    e = keep('takedown.js', body); e['injects'] = 'loader'
    mk('f%d_noshell_keep_firebase' % i, PIN, {'noShell': ['terms.html'], 'keep': [e]}, {'takedown.js': body}, {'terms.html': NSP % ''})
# Review nit: index.html is never a redirect stub, even when it is shaped exactly like one
mk('i0_index_bare_stub', "<script>location.replace('/')</script>", None, None, {'about.html': '<html><head>%s</head></html>' % PIN})
