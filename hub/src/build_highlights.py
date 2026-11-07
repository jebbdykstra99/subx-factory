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
- Also drops (Key 1 edit E1, 2026-11-03) any post whose text contains an em dash (U+2014) or en dash (U+2013), or
  starts with "Seed" (any case). Post text is never edited: a post passes whole or is left out.
  --refilter re-applies these text rules to the existing data/highlights.json without fetching (no new posts).
- Room taglines and rail snippets (2026-11-03): a tagline that fails tagline_rule (the same dash / "Seed" rule, plus
  "pending", "TODO" or "Content DB") ships as "" (the room keeps its name and link; the source copy is never
  rewritten), and a highlight that quotes a failing tagline is dropped. --refilter applies this to data/ too.
- Writes only hub/src/data (no CNAME, no site.json edit: tools/brand_render.py fills site.json rail.outbound from
  rail.json). The per-room report is printed, not saved.
Usage: python3 hub/src/build_highlights.py [--fetch 40] [--max 40] [--no-live-check] | --refilter | --stories-only | --annotate-preview
- Room row preview (no page-load fetch): each suggested room can carry accent (site.json theme.accent), brief (Room Brief
  first outbound line), and preview (the newest published highlight for that room). --annotate-preview fills those on
  data/rooms.json from the public site.json files plus the highlights already on disk. It does not read Firestore.
- Stories (2026-11-04, draft): also writes data/stories.json, the live rooms with Stories on (for the hub's Add story
  picker) and their live public TEXT stories. Steward-only unless --allow-member-stories; photo/clip stories are never
  copied. Stories expire in 24 hours, so this file needs a rebuild cadence (see shell/STORIES.md).

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
    return live_site(domain) is not None

def live_site(domain):
    """The room's public site.json (dict), or None when the room is not reachable."""
    try:
        req = urllib.request.Request('https://%s/site.json' % domain, headers={'user-agent': 'subx-hub-highlights/1'})
        with urllib.request.urlopen(req, timeout=15) as r:
            if r.status != 200: return None
            d = json.loads(r.read().decode('utf-8'))
            return d if isinstance(d, dict) else {}
    except Exception:
        return None

def stories_flag(site):
    """Room Stories on/off as shell v1.2.7 reads it: on unless stories.enabled is false. Rooms on v1.2.6 and older
    only run Stories when stories.enabled is true, so an unset flag counts as off until the room is on v1.2.7."""
    st = (site or {}).get('stories') or {}
    return st.get('enabled') is True

def tier_for(f):
    """WHOMARK tier, same as the factory pill: steward:true or admin-authored -> ai; member -> human. None = drop."""
    if f.get('agentId'): return None            # third-party agents: no approved hub label yet
    if f.get('steward') is True or f.get('authorUid') == ADMIN_UID or f.get('stewardSeed') or f.get('adminSeed') or f.get('seedBatch'):
        return 'ai'
    if isinstance(f.get('authorUid'), str) and f['authorUid']: return 'human'
    return None

DASHES = ('\u2014', '\u2013')   # em dash, en dash

def text_rule(t):
    """Key 1 edit E1: reason a post text is left out, or None. Applied to the full text before clip()."""
    if any(d in t for d in DASHES): return 'dash'
    if t.lstrip().lower().startswith('seed'): return 'seed_prefix'
    return None

TAGLINE_BAD_RE = re.compile(r'pending|content db', re.I)

def tagline_rule(t):
    """Reason a room tagline / rail snippet is left out (shown as no tagline), or None."""
    if not isinstance(t, str) or not t.strip(): return 'empty'
    why = text_rule(t)
    if why: return why
    if TAGLINE_BAD_RE.search(t) or 'TODO' in t: return 'placeholder'
    return None

def safe_tagline(t):
    return t if tagline_rule(t) is None else ''

def bad_taglines(cfg):
    return [r['tagline'] for r in cfg.get('rooms', []) if isinstance(r.get('tagline'), str) and r['tagline'].strip()
            and tagline_rule(r['tagline'])]

def quotes_bad_tagline(text, bad):
    return any(b in text for b in bad)

def check(f, doc, hidden):
    pid = doc['name'].rsplit('/', 1)[-1]
    if f.get('parentId'): return 'reply'
    if pid in hidden or ('uid:' + str(f.get('authorUid'))) in hidden: return 'hidden'
    if f.get('hidden') or f.get('deleted') or f.get('removed') or f.get('underReport') or (f.get('reportCount') or 0) > 0: return 'flagged'
    ct, st = ms(f.get('createdAt') or ''), ms(doc.get('createTime') or '')
    if ct is not None and st is not None and st - ct > BACKDATE_MS: return 'backdated'
    t = f.get('text')
    if not isinstance(t, str) or not t.strip(): return 'no_text'
    why = text_rule(t)
    if why: return why
    if tier_for(f) is None: return 'no_label'
    hay = '\n'.join([t, f.get('authorName') or '', f.get('authorHandle') or ''])
    if EMAIL_RE.search(hay) or SECRET_RE.search(hay): return 'lint'
    if PHONE_RE.search(re.sub(r'https?://\S+', '', hay)): return 'lint'
    if blocked(hay): return 'blocked_string'
    return None

def clip(t):
    t = re.sub(r'\s+\n', '\n', t.strip())
    return t if len(t) <= MAX_TEXT else t[:MAX_TEXT - 1].rstrip() + '…'

ACCENT_RE = re.compile(r'^#[0-9a-fA-F]{6}$')
POST_URL_RE = re.compile(r'^https://[a-z0-9.-]+\.[a-z]{2,}/\?p=[A-Za-z0-9_-]+$', re.I)

def accent_of(site):
    """Room theme accent from its public site.json, or '' when the value is not a 6-digit hex color."""
    theme = (site or {}).get('theme') if isinstance(site, dict) else None
    if not isinstance(theme, dict):
        return ''
    raw = theme.get('accent')
    if isinstance(raw, str) and ACCENT_RE.match(raw.strip()):
        return raw.strip().lower()
    return ''

def brief_line(site):
    """First Room Brief line: the first outbound headline (else snippet) that passes the tagline safety rules."""
    rail = (site or {}).get('rail') if isinstance(site, dict) else None
    cards = rail.get('outbound') if isinstance(rail, dict) else None
    if not isinstance(cards, list):
        return ''
    for card in cards:
        if not isinstance(card, dict):
            continue
        for key in ('headline', 'snippet'):
            raw = card.get(key)
            if not isinstance(raw, str):
                continue
            line = raw.strip().split('\n', 1)[0].strip()
            if not line or tagline_rule(line) is not None:
                continue
            if EMAIL_RE.search(line) or PHONE_RE.search(re.sub(r'https?://\S+', '', line)) or blocked(line):
                continue
            return line
    return ''

def latest_by_room(items):
    """Newest published highlight per room, by createdAt. Ties keep the later item."""
    best = {}
    for it in items or []:
        if not isinstance(it, dict) or not it.get('room'):
            continue
        prev = best.get(it['room'])
        if prev is None or (ms(it.get('createdAt') or '') or 0) >= (ms(prev.get('createdAt') or '') or 0):
            best[it['room']] = it
    return best

def preview_from(it):
    """Compact copy of one highlight for a room row. None when the post cannot be linked safely. Text is not edited."""
    if not isinstance(it, dict):
        return None
    url = it.get('url') if isinstance(it.get('url'), str) else ''
    text = it.get('text') if isinstance(it.get('text'), str) else ''
    if not POST_URL_RE.match(url) or not text.strip() or text_rule(text):
        return None
    tier = it.get('tier') if it.get('tier') in ('ai', 'human', 'hybrid') else ''
    handle = it.get('authorHandle') if isinstance(it.get('authorHandle'), str) else ''
    out = {'url': url, 'handle': handle, 'tier': tier, 'text': text, 'createdAt': it.get('createdAt') or ''}
    names = it.get('names')
    if isinstance(names, str) and names.strip():
        out['names'] = names
    return out

def apply_previews(rooms, items):
    """Set or clear each room's preview from the published highlights. Leaves accent and brief alone."""
    latest = latest_by_room(items)
    for r in rooms or []:
        prev = preview_from(latest.get(r.get('room')))
        if prev:
            r['preview'] = prev
        elif 'preview' in r:
            del r['preview']

def annotate_preview():
    """Fill accent, brief, and preview on data/rooms.json. Public site.json reads only. No Firestore."""
    rp = os.path.join(DATA, 'rooms.json')
    rd = json.load(open(rp, encoding='utf-8'))
    hl = json.load(open(os.path.join(DATA, 'highlights.json'), encoding='utf-8'))
    for r in rd.get('rooms') or []:
        site = live_site(r.get('domain'))
        accent, brief = accent_of(site), brief_line(site)
        if accent:
            r['accent'] = accent
        elif 'accent' in r:
            del r['accent']
        if brief:
            r['brief'] = brief
        elif 'brief' in r:
            del r['brief']
        if site is None:
            print('annotate-preview: %s site.json unreachable' % r.get('room'))
    apply_previews(rd.get('rooms') or [], hl.get('items') or [])
    json.dump(rd, open(rp, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    n_prev = sum(1 for r in rd['rooms'] if r.get('preview'))
    print('annotate-preview: %d rooms, %d with a highlight preview (wrote %s)' % (len(rd['rooms']), n_prev, rp))
    return 0

def write_rail(suggest):
    # Right rail (factory rail.outbound cards): suggested live rooms, merged into site.json by tools/brand_render.py.
    rail = [{'tag': 'Featured room' if s['featured'] else 'Room', 'headline': s['name'], 'snippet': safe_tagline(s['tagline']),
             'meta': s['domain'], 'url': 'https://%s/' % s['domain']} for s in suggest]
    with open(os.path.join(DATA, 'rail.json'), 'w') as fh:
        json.dump(rail, fh, indent=1, ensure_ascii=False); fh.write('\n')

def refilter():
    cfg = json.load(open(os.path.join(HERE, 'rooms.json'), encoding='utf-8'))
    assert_partners_not_ranked(cfg)
    bad = bad_taglines(cfg)
    rp = os.path.join(DATA, 'rooms.json')
    rd = json.load(open(rp, encoding='utf-8'))
    cleared = [r['room'] for r in rd['rooms'] if r.get('tagline') and tagline_rule(r['tagline'])]
    for r in rd['rooms']: r['tagline'] = safe_tagline(r.get('tagline'))
    write_rail(rd['rooms'])
    print('refilter: taglines cleared: %s' % (', '.join(cleared) or '-'))
    p = os.path.join(DATA, 'highlights.json')
    d = json.load(open(p, encoding='utf-8'))
    keep, drop = [], []
    for it in d['items']:
        (drop if text_rule(it['text']) or quotes_bad_tagline(it['text'], bad) else keep).append(it)
    counts = {}
    for it in keep: counts[it['room']] = counts.get(it['room'], 0) + 1
    d['items'], d['counts'] = keep, counts
    apply_previews(rd['rooms'], keep)
    json.dump(rd, open(rp, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    json.dump(d, open(p, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print('refilter: kept %d, dropped %d (%s)' % (len(keep), len(drop), ', '.join('%s/%s' % (i['room'], i['postId']) for i in drop) or '-'))
    return 0

STORY_TYPES_SHOWN = {'text'}   # no photo/clip on the hub: no remote media, nothing to moderate twice

def story_check(f, doc, sid, now_ms, allow_members):
    """Reason a story is left out of hub/src/data/stories.json, or None. Same safety bar as highlights."""
    if f.get('siteId') != sid: return 'wrong_site'
    e = f.get('expiresAt')
    exp = ms(e) if isinstance(e, str) else (float(e) if isinstance(e, (int, float)) and not isinstance(e, bool) else None)
    if exp is None or exp <= now_ms: return 'expired'
    if f.get('type') not in STORY_TYPES_SHOWN: return 'media'
    if f.get('hidden') or f.get('deleted') or f.get('removed') or f.get('underReport') or (f.get('reportCount') or 0) > 0: return 'flagged'
    ct, st = ms(f.get('createdAt') or ''), ms(doc.get('createTime') or '')
    if ct is not None and st is not None and st - ct > BACKDATE_MS: return 'backdated'
    t = f.get('text')
    if not isinstance(t, str) or not t.strip(): return 'no_text'
    why = text_rule(t)
    if why: return why
    tier = tier_for(f)
    if tier is None: return 'no_label'
    if tier != 'ai' and not allow_members: return 'member_story_held'
    hay = '\n'.join([t, f.get('authorName') or '', f.get('authorHandle') or ''])
    if EMAIL_RE.search(hay) or SECRET_RE.search(hay): return 'lint'
    if PHONE_RE.search(re.sub(r'https?://\S+', '', hay)): return 'lint'
    if blocked(hay): return 'blocked_string'
    return None

def build_stories(cfg, no_live_check=False, allow_members=False):
    """hub/src/data/stories.json: which live rooms run Stories (for the hub's Add story picker) and their live public
    text stories (steward-only by default). Stories expire after 24 hours; the hub page also drops expired items on
    the client, so a stale build never shows an old story. Public reads only (stories allow read for factory sites)."""
    now_ms = time.time() * 1000
    rooms, items, report = [], [], {}
    for r in sorted(cfg['rooms'], key=lambda r: r['room']):
        sid, room = r['siteId'], r['room']
        rep = report.setdefault(room, {'fetched': 0, 'kept': 0, 'dropped': {}})
        if room in PAUSED or r.get('status') != 'live':
            rep['skipped'] = 'paused'; continue
        if not r.get('suggest'):
            rep['skipped'] = 'not listed on the hub (%s)' % (r.get('hold') or 'suggest off'); continue
        site = {} if no_live_check else live_site(r['domain'])
        if site is None:
            rep['skipped'] = 'not live'; continue
        try:
            if site_killed(sid):
                rep['skipped'] = 'killed'; continue
        except Exception as e:
            rep['skipped'] = 'kill check failed: %s' % e; continue
        on = stories_flag(site)
        rooms.append({'room': room, 'name': r['name'], 'domain': r['domain'], 'stories': on})
        if not on:
            rep['skipped'] = 'stories off'; continue
        try:
            docs = run_query('stories', sid, order=False, limit=50)
        except Exception as e:
            rep['error'] = str(e); continue
        for doc in docs:
            rep['fetched'] += 1
            f = {k: val(v) for k, v in (doc.get('fields') or {}).items()}
            why = story_check(f, doc, sid, now_ms, allow_members)
            if why: rep['dropped'][why] = rep['dropped'].get(why, 0) + 1; continue
            items.append({'room': room, 'roomName': r['name'], 'domain': r['domain'], 'storyId': doc['name'].rsplit('/', 1)[-1],
                          'text': clip(f['text']), 'authorName': f.get('authorName') or '', 'tier': tier_for(f),
                          'createdAt': doc.get('createTime'), 'expiresAt': f.get('expiresAt')})
            rep['kept'] += 1
        time.sleep(0.2)
    items.sort(key=lambda it: it.get('createdAt') or '', reverse=True)
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    json.dump({'version': 1, 'generated': now,
               'ttlHours': 24, 'membersShown': bool(allow_members), 'rooms': rooms, 'items': items},
              open(os.path.join(DATA, 'stories.json'), 'w'), indent=1, ensure_ascii=False)
    print('stories: %d live items; %d live rooms, %d with Stories on (wrote %s)' % (len(items), len(rooms), sum(1 for x in rooms if x['stories']), DATA))
    for room, rep in report.items():
        print('  %-20s kept %-2s fetched %-3s %s %s' % (room, rep.get('kept'), rep.get('fetched'), rep.get('skipped', ''), rep.get('dropped') or ''))
    return 0

def assert_partners_not_ranked(cfg):
    """Partner rooms stay out of the organic list. featuredRooms and roomOrder are visitor rank, not a sponsor slot."""
    ids = set()
    for p in cfg.get('partnerRooms') or []:
        if isinstance(p, dict) and isinstance(p.get('room'), str):
            ids.add(p['room'])
    organic = {r.get('room') for r in cfg.get('rooms') or [] if isinstance(r, dict)}
    featured = set(cfg.get('featuredRooms') or [])
    order = set(cfg.get('roomOrder') or [])
    bad = ids & (organic | featured | order)
    if bad:
        raise SystemExit('partner rooms must stay out of the organic rooms list, featuredRooms, and roomOrder: %s' % ', '.join(sorted(bad)))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fetch', type=int, default=40)
    ap.add_argument('--max', type=int, default=40)
    ap.add_argument('--no-live-check', action='store_true')
    ap.add_argument('--allow-unverified-members', action='store_true', help='include member posts even when hides cannot be read (not recommended)')
    ap.add_argument('--refilter', action='store_true', help='re-apply text_rule to data/highlights.json only (no fetch)')
    ap.add_argument('--annotate-preview', action='store_true', help='fill room accent, brief, and highlight preview from public site.json plus data/highlights.json (no Firestore)')
    ap.add_argument('--stories-only', action='store_true', help='rebuild data/stories.json only (highlights untouched)')
    ap.add_argument('--allow-member-stories', action='store_true', help='include member text stories (decision pending; default steward-only)')
    a = ap.parse_args()
    if a.annotate_preview:
        return annotate_preview()
    if a.refilter:
        return refilter()

    cfg = json.load(open(os.path.join(HERE, 'rooms.json')))
    assert_partners_not_ranked(cfg)
    if a.stories_only:
        return build_stories(cfg, a.no_live_check, a.allow_member_stories)
    featured = [x for x in cfg.get('featuredRooms', [])]
    f_per, o_per = int(cfg.get('featuredPerRoom', 6)), int(cfg.get('otherPerRoom', 1))
    order = featured + [x for x in cfg.get('roomOrder', []) if x not in featured]
    rank = {x: i for i, x in enumerate(order)}
    rooms = sorted(cfg['rooms'], key=lambda r: (rank.get(r['room'], 999), r['room']))
    report, picked, suggest = {}, {}, []
    bad = bad_taglines(cfg)
    for r in rooms:
        sid, room = r['siteId'], r['room']
        rep = report.setdefault(room, {'siteId': sid, 'fetched': 0, 'kept': 0, 'dropped': {}})
        if room in PAUSED or r.get('status') != 'live':
            rep['skipped'] = 'paused'; continue
        site_doc = None if a.no_live_check else live_site(r['domain'])
        live = True if a.no_live_check else site_doc is not None
        if not live:
            rep['skipped'] = 'not live (site.json unreachable)'; continue
        try:
            if site_killed(sid):
                rep['skipped'] = 'killed (sites/%s.killed)' % sid; continue
        except Exception as e:
            rep['skipped'] = 'kill check failed: %s' % e; continue
        if r.get('suggest'):
            # notifs (2026-11-04, hub Notifications): the room's own site.json turns member Notifications on
            # (features.notifs true); the hub shows an "Open Notifications" link only for those rooms
            notifs = isinstance(site_doc, dict) and isinstance(site_doc.get('features'), dict) and site_doc['features'].get('notifs') is True
            entry = {'room': room, 'name': r['name'], 'domain': r['domain'], 'tagline': safe_tagline(r.get('tagline')), 'featured': room in featured,
                     'notifs': notifs}
            accent, brief = accent_of(site_doc), brief_line(site_doc)
            if accent: entry['accent'] = accent
            if brief: entry['brief'] = brief
            suggest.append(entry)
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
            if not why and quotes_bad_tagline(f['text'], bad): why = 'quotes_bad_tagline'
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
    apply_previews(suggest, items)
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    counts = {}
    for it in items: counts[it['room']] = counts.get(it['room'], 0) + 1
    json.dump({'version': 1, 'generated': now, 'source': 'Firestore REST, public reads only (posts, hides, sites)',
               'featuredRooms': featured, 'featuredPerRoom': f_per, 'otherPerRoom': o_per, 'counts': counts, 'items': items},
              open(os.path.join(DATA, 'highlights.json'), 'w'), indent=1, ensure_ascii=False)
    json.dump({'version': 1, 'generated': now, 'rooms': suggest},
              open(os.path.join(DATA, 'rooms.json'), 'w'), indent=1, ensure_ascii=False)
    write_rail(suggest)
    build_stories(cfg, a.no_live_check, a.allow_member_stories)
    print('highlights: %d items from %d rooms; suggested rooms: %d (wrote %s)' % (len(items), len(counts), len(suggest), DATA))
    for room, rep in report.items():
        print('  %-20s kept %-2s fetched %-3s %s %s' % (room, rep.get('kept'), rep.get('fetched'), rep.get('skipped', ''), rep.get('dropped') or ''))
    return 0

if __name__ == '__main__':
    sys.exit(main())
