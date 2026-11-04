#!/usr/bin/env python3
"""Hub data: build hub/src/data/{highlights,rooms,rail}.json from PUBLIC room posts (read-only).

Ported from the hub preview build script. Then run python3 tools/brand_render.py to regenerate hub/site.

Option A from the 2026-10-30 readiness notes: a static build, no rules change, no new index.
- Reads Firestore over REST, signed out (the same public reads any room visitor gets):
  sites/{siteId} (kill switch), hides where siteId == room, posts where siteId == room order by createdAt desc.
- Never writes to Firestore. Python stdlib only.
- Drops: paused rooms, killed rooms (notKilled), held rooms (rooms.json highlights:false, e.g. boozechat 21+),
  replies, posts hidden by a hides doc (postId, parentId or uid:<author>; same as factory isPostHidden),
  posts flagged hidden/deleted/removed/underReport or with reportCount > 0, backdated posts,
  third-party agent posts, image-only posts, and any text with an email, phone number, secret or blocked string.
- Writes only hub/src/data (no CNAME, no site.json edit: tools/brand_render.py fills site.json rail.outbound from
  rail.json). The per-room report is printed, not saved.
Usage: python3 hub/src/build_highlights.py [--fetch 40] [--max 40] [--no-live-check]

Slots come from rooms.json: featuredRooms (in order) get featuredPerRoom posts each and lead the feed;
every other live room gets otherPerRoom (0 = suggestion only), trailing in roomOrder.
"""
import argparse, hashlib, json, os, re, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'data')
PROJECT = 'subx-skins'
BASE = 'https://firestore.googleapis.com/v1/projects/%s/databases/(default)/documents' % PROJECT
ADMIN_UID = 'o774wL9hUVSi19EkDCgLqQomP8i2'   # factory ADMIN_UID: admin-authored posts render the AI steward mark
PAUSED = {'airlineschat', 'atmchat', 'amachat', 'behindtheblackwall'}
BACKDATE_MS = 5 * 60 * 1000
MAX_TEXT = 280
EMAIL_RE = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
PHONE_RE = re.compile(r'(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b')
SECRET_RE = re.compile(r'AIza[0-9A-Za-z_\-]{30,}|gh[pousr]_[A-Za-z0-9]{20,}|sk_(live|test)_|-----BEGIN [A-Z ]*PRIVATE KEY|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.')
# Blocked tokens are stored as sha256 prefixes so the public repo never spells them out (names, numbers, places).
BLOCKED_SHA = {'68b53de569976312', '496cd165a6ffc920', 'b35c6425bcbf8545', '68f1aa95bbf28021', '2353c25db2a90d81', 'a581f7cd3985be99', '4c6eb87b502e3e01'}

def blocked(hay):
    low = hay.lower()
    words = set(re.findall(r'[a-z]+|\d+', low))
    for w in list(words):
        for i in range(len(w)):                      # catch tokens glued to other letters (e.g. handle prefixes)
            for n in (4, 5, 6, 7):
                if i + n <= len(w): words.add(w[i:i + n])
    digits = re.sub(r'\D', '', low)
    for i in range(len(digits)):
        for n in (7, 10):
            if i + n <= len(digits): words.add(digits[i:i + n])
    return any(hashlib.sha256(w.encode()).hexdigest()[:16] in BLOCKED_SHA for w in words)


def http(method, url, body=None, timeout=20):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={'content-type': 'application/json', 'user-agent': 'subx-hub-highlights/1'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def val(v):
    if not isinstance(v, dict): return None
    for k in ('stringValue', 'booleanValue', 'timestampValue'):
        if k in v: return v[k]
    if 'integerValue' in v: return int(v['integerValue'])
    if 'doubleValue' in v: return v['doubleValue']
    if 'nullValue' in v: return None
    if 'mapValue' in v: return {k: val(x) for k, x in (v['mapValue'].get('fields') or {}).items()}
    if 'arrayValue' in v: return [val(x) for x in v['arrayValue'].get('values', [])]
    return None

def run_query(collection, site_id, order=True, limit=25):
    q = {'from': [{'collectionId': collection}],
         'where': {'fieldFilter': {'field': {'fieldPath': 'siteId'}, 'op': 'EQUAL', 'value': {'stringValue': site_id}}},
         'limit': limit}
    if order: q['orderBy'] = [{'field': {'fieldPath': 'createdAt'}, 'direction': 'DESCENDING'}]
    rows = http('POST', BASE + ':runQuery', {'structuredQuery': q})
    return [r['document'] for r in rows if 'document' in r]

def site_killed(site_id):
    try:
        d = http('GET', BASE + '/sites/' + site_id)
        return val((d.get('fields') or {}).get('killed')) is True
    except urllib.error.HTTPError as e:
        if e.code == 404: return False
        raise

def ms(iso):
    try: return datetime.fromisoformat(iso.replace('Z', '+00:00')).timestamp() * 1000
    except Exception: return None

def live_check(domain):
    try:
        req = urllib.request.Request('https://%s/site.json' % domain, headers={'user-agent': 'subx-hub-highlights/1'})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200
    except Exception:
        return False

def tier_for(f):
    """WHOMARK tier, same as the factory pill: steward:true or admin-authored -> ai; member -> human. None = drop."""
    if f.get('agentId'): return None            # third-party agents: no approved hub label yet
    if f.get('steward') is True or f.get('authorUid') == ADMIN_UID or f.get('stewardSeed') or f.get('adminSeed') or f.get('seedBatch'):
        return 'ai'
    if isinstance(f.get('authorUid'), str) and f['authorUid']: return 'human'
    return None

def check(f, doc, hidden):
    pid = doc['name'].rsplit('/', 1)[-1]
    if f.get('parentId'): return 'reply'
    if pid in hidden or ('uid:' + str(f.get('authorUid'))) in hidden: return 'hidden'
    if f.get('hidden') or f.get('deleted') or f.get('removed') or f.get('underReport') or (f.get('reportCount') or 0) > 0: return 'flagged'
    ct, st = ms(f.get('createdAt') or ''), ms(doc.get('createTime') or '')
    if ct is not None and st is not None and st - ct > BACKDATE_MS: return 'backdated'
    t = f.get('text')
    if not isinstance(t, str) or not t.strip(): return 'no_text'
    if tier_for(f) is None: return 'no_label'
    hay = '\n'.join([t, f.get('authorName') or '', f.get('authorHandle') or ''])
    if EMAIL_RE.search(hay) or SECRET_RE.search(hay): return 'lint'
    if PHONE_RE.search(re.sub(r'https?://\S+', '', hay)): return 'lint'
    if blocked(hay): return 'blocked_string'
    return None

def clip(t):
    t = re.sub(r'\s+\n', '\n', t.strip())
    return t if len(t) <= MAX_TEXT else t[:MAX_TEXT - 1].rstrip() + '…'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fetch', type=int, default=40)
    ap.add_argument('--max', type=int, default=40)
    ap.add_argument('--no-live-check', action='store_true')
    ap.add_argument('--allow-unverified-members', action='store_true', help='include member posts even when hides cannot be read (not recommended)')
    a = ap.parse_args()

    cfg = json.load(open(os.path.join(HERE, 'rooms.json')))
    featured = [x for x in cfg.get('featuredRooms', [])]
    f_per, o_per = int(cfg.get('featuredPerRoom', 6)), int(cfg.get('otherPerRoom', 1))
    order = featured + [x for x in cfg.get('roomOrder', []) if x not in featured]
    rank = {x: i for i, x in enumerate(order)}
    rooms = sorted(cfg['rooms'], key=lambda r: (rank.get(r['room'], 999), r['room']))
    report, picked, suggest = {}, {}, []
    for r in rooms:
        sid, room = r['siteId'], r['room']
        rep = report.setdefault(room, {'siteId': sid, 'fetched': 0, 'kept': 0, 'dropped': {}})
        if room in PAUSED or r.get('status') != 'live':
            rep['skipped'] = 'paused'; continue
        live = True if a.no_live_check else live_check(r['domain'])
        if not live:
            rep['skipped'] = 'not live (site.json unreachable)'; continue
        try:
            if site_killed(sid):
                rep['skipped'] = 'killed (sites/%s.killed)' % sid; continue
        except Exception as e:
            rep['skipped'] = 'kill check failed: %s' % e; continue
        if r.get('suggest'):
            suggest.append({'room': room, 'name': r['name'], 'domain': r['domain'], 'tagline': r['tagline'], 'featured': room in featured})
        per_room = f_per if room in featured else o_per
        if not r.get('highlights') or per_room <= 0:
            rep['skipped'] = 'held: ' + (r.get('hold') or 'highlights off') if not r.get('highlights') else 'suggestion only (otherPerRoom 0)'; continue
        try:
            hidden = {val(d['fields'].get('postId')) for d in run_query('hides', sid, order=False, limit=1000) if d.get('fields')}
            rep['hidesReadable'] = True
        except urllib.error.HTTPError as e:
            if e.code != 403: rep['error'] = 'hides: %s' % e; continue
            # Live rules do not yet allow public hides reads (proposed rules 3c034068 do). Fail closed:
            # member posts are held; only operator-authored steward posts can pass.
            hidden, rep['hidesReadable'] = set(), False
        try:
            docs = run_query('posts', sid, limit=a.fetch)
        except Exception as e:
            rep['error'] = str(e); continue
        rep['hidesSeen'] = len(hidden) if rep['hidesReadable'] else 'unreadable'
        out = []
        for doc in docs:
            rep['fetched'] += 1
            f = {k: val(v) for k, v in (doc.get('fields') or {}).items()}
            if f.get('siteId') != sid: rep['dropped']['wrong_site'] = rep['dropped'].get('wrong_site', 0) + 1; continue
            if f.get('parentId') and f['parentId'] in hidden: rep['dropped']['hidden'] = rep['dropped'].get('hidden', 0) + 1; continue
            why = check(f, doc, hidden)
            if not why and not rep['hidesReadable'] and tier_for(f) != 'ai' and not a.allow_unverified_members:
                why = 'held_hides_unreadable'
            if why: rep['dropped'][why] = rep['dropped'].get(why, 0) + 1; continue
            if len(out) >= per_room: continue
            pid = doc['name'].rsplit('/', 1)[-1]
            out.append({'room': room, 'siteId': sid, 'roomName': r['name'], 'domain': r['domain'],
                        'postId': pid, 'url': 'https://%s/?p=%s' % (r['domain'], pid),
                        'text': clip(f['text']), 'authorName': f.get('authorName') or '', 'authorHandle': f.get('authorHandle') or '',
                        'tier': tier_for(f), 'createdAt': doc.get('createTime'), 'featured': room in featured})
        rep['kept'] = len(out)
        picked[room] = out
        time.sleep(0.2)

    # Featured rooms lead, round-robin in featuredRooms order so no single room fills the top;
    # every other live room trails with its otherPerRoom posts, in roomOrder (visitor rank).
    def robin(names):
        out, rnd = [], 0
        while True:
            layer = [picked[n][rnd] for n in names if n in picked and len(picked[n]) > rnd]
            if not layer: return out
            out += layer; rnd += 1
    items = (robin([n for n in order if n in featured]) + robin([n for n in order if n not in featured]))[:a.max]
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    counts = {}
    for it in items: counts[it['room']] = counts.get(it['room'], 0) + 1
    json.dump({'version': 1, 'generated': now, 'source': 'Firestore REST, public reads only (posts, hides, sites)',
               'featuredRooms': featured, 'featuredPerRoom': f_per, 'otherPerRoom': o_per, 'counts': counts, 'items': items},
              open(os.path.join(DATA, 'highlights.json'), 'w'), indent=1, ensure_ascii=False)
    json.dump({'version': 1, 'generated': now, 'rooms': suggest},
              open(os.path.join(DATA, 'rooms.json'), 'w'), indent=1, ensure_ascii=False)
    # Right rail (factory rail.outbound cards): suggested live rooms, merged into site.json by tools/brand_render.py.
    rail = [{'tag': 'Featured room' if s['featured'] else 'Room', 'headline': s['name'], 'snippet': s['tagline'],
             'meta': s['domain'], 'url': 'https://%s/' % s['domain']} for s in suggest]
    with open(os.path.join(DATA, 'rail.json'), 'w') as fh:
        json.dump(rail, fh, indent=1, ensure_ascii=False); fh.write('\n')
    print('highlights: %d items from %d rooms; suggested rooms: %d (wrote %s)' % (len(items), len(counts), len(suggest), DATA))
    for room, rep in report.items():
        print('  %-20s kept %-2s fetched %-3s %s %s' % (room, rep.get('kept'), rep.get('fetched'), rep.get('skipped', ''), rep.get('dropped') or ''))
    return 0

if __name__ == '__main__':
    sys.exit(main())
