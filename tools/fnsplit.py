import re, sys, json, hashlib
def split(src):
    """Split an IIFE factory.js into top-level 2-space-indented chunks keyed by function name.
    Returns list of (key, text). Non-function chunks are keyed '#N'."""
    lines = src.split('\n')
    out = []; cur = []; key = None; n = 0
    i = 0
    fn = re.compile(r'^  (?:async )?function\s+([A-Za-z0-9_$]+)\s*\(')
    while i < len(lines):
        L = lines[i]
        m = fn.match(L)
        if m:
            if cur: out.append((key or '#%d' % n, '\n'.join(cur))); n += 1; cur = []
            key = m.group(1); body = [L]
            if not L.rstrip().endswith('}') or L.strip().endswith('{'):
                i += 1
                while i < len(lines):
                    body.append(lines[i])
                    if lines[i] == '  }' or lines[i].startswith('  }') and not lines[i].startswith('   '):
                        break
                    i += 1
            out.append((key, '\n'.join(body))); key = None
            i += 1; continue
        cur.append(L); i += 1
    if cur: out.append(('#%d' % n, '\n'.join(cur)))
    return out
if __name__ == '__main__':
    a = split(open(sys.argv[1]).read())
    print(len(a), sum(1 for k, _ in a if not k.startswith('#')))
