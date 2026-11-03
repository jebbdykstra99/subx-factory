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
