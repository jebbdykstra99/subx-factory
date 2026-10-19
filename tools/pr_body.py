#!/usr/bin/env python3
"""Render a stamp report JSON as a PR body."""
import json, sys
r = json.load(open(sys.argv[1]))
print('Stamped by **subx-factory** (one identical `factory.js` for every room; room differences live in `site.json`).\n')
print('**Merge only after Firestore rules step 1 is published** (the new factory.js writes `rateLimits` with every post).\n')
for title, key in (('Risky diffs', 'risks'), ('Other changes', 'changes'), ('Cleanup left for a separate PR', 'cleanup')):
    if r.get(key): print('### %s\n' % title + '\n'.join('- ' + x for x in r[key]) + '\n')
print('After merge: `verify_nests.py --live` and `verify/public-check.sh` for this room. Rollback = revert this PR.')
