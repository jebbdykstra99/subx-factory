#!/usr/bin/env python3
"""Partner rooms: one displayName field, a flagged hub slot, and the room prototype."""
import json, os, re, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'hub', 'src'))
import brand_render as BR  # noqa: E402
import partner_room_render as PR  # noqa: E402
import build_highlights as BH  # noqa: E402

fails = []


def ok(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        fails.append(msg)


def read(p):
    return open(p, encoding='utf-8').read()


SITE_PATH = os.path.join(ROOT, 'rooms', 'dogacademy-partner', 'site.json')
HUB_ROOMS = os.path.join(ROOT, 'hub', 'src', 'rooms.json')
site = json.load(open(SITE_PATH, encoding='utf-8'))
name = site['displayName']
hub = json.load(open(HUB_ROOMS, encoding='utf-8'))
entry = hub['partnerRooms'][0]

brand = json.load(open(os.path.join(ROOT, 'brand', 'brand.json'), encoding='utf-8'))
ok(site.get('operator') == brand['legalEntity'] and site.get('takedownEmail') == brand['takedownEmail'] and site.get('contactPhone') == brand['contactPhone'],
   'room file contacts match brand.json')
ok(entry['enabled'] is False, 'partner entry is flagged off')
ok(entry['displayName'] == '@rooms/%s/site.json#displayName' % entry['room'], 'hub displayName references the room site.json field')
ok(entry['sponsor'] == '@displayName' and entry['disclosure'] == 'Sponsored by {{displayName}}', 'sponsor and disclosure fill from displayName')
ok(name not in read(HUB_ROOMS), 'hub/src/rooms.json does not copy the room name')
ok(entry['room'] not in hub['featuredRooms'] and entry['room'] not in hub['roomOrder']
   and entry['room'] not in {r['room'] for r in hub['rooms']}, 'partner room stays out of featuredRooms, roomOrder, and the organic list')
BH.assert_partners_not_ranked(hub)
bad = json.loads(json.dumps(hub))
bad['featuredRooms'] = list(bad['featuredRooms']) + [entry['room']]
try:
    BH.assert_partners_not_ranked(bad)
    ok(False, 'a partner id in featuredRooms is refused')
except SystemExit:
    ok(True, 'a partner id in featuredRooms is refused')
try:
    BR.shown_partners([{'enabled': False}, {'enabled': False}, {'enabled': False}], True)
    ok(False, 'widget cap is 2')
except BR.RenderError:
    ok(True, 'widget cap is 2')

# The name string may appear only as displayName in the room site.json.
skip_ext = {'.png', '.woff2', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.pdf'}
hits = []
for dirpath, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', '__pycache__')]
    for fn in files:
        if os.path.splitext(fn)[1].lower() in skip_ext:
            continue
        path = os.path.join(dirpath, fn)
        rel = os.path.relpath(path, ROOT).replace(os.sep, '/')
        try:
            text = read(path)
        except UnicodeDecodeError:
            continue
        if rel == 'rooms/dogacademy-partner/site.json':
            text = text.replace(json.dumps(name, ensure_ascii=False), '""', 1)
        if rel.startswith('hub/site/partners/dogacademy/'):
            continue
        if name in text:
            hits.append(rel)
ok(not hits, 'displayName is not hardcoded anywhere else (%s)' % hits[:8])

pages = PR.render(SITE_PATH)
joined = '\n'.join(pages.values())
ok(name in pages['index.html'] and pages['index.html'].count('<title>%s</title>' % name) == 1, 'room title renders displayName')
ok('property="og:title" content="%s"' % name in pages['index.html'], 'room og:title renders displayName')
ok('<h1>%s</h1>' % name in pages['index.html'], 'room header renders displayName')
ok(('Sponsored by %s' % name) in pages['index.html'] and pages['index.html'].count('class="partner-disclosure"') >= 2, 'room and partner posts show the sponsor line')
ok('class="sidebar"' in pages['index.html'] and 'class="room-banner"' in pages['index.html'] and 'class="room-avatar"' in pages['index.html'] and 'id="room-feed"' in pages['index.html'], 'room home uses the shell: nav, banner, avatar, feed')
ok('<h2>Room</h2>' not in pages['index.html'] and pages['index.html'].count('Operated by ') == 1, 'no empty Room heading and one operator line')
ok('id="articles"' in pages['index.html'] and pages['index.html'].count('class="news-item-headline"') >= 6, 'articles show as cards')
ok('Home alone practice' in pages['index.html'] and 'Separation anxiety course' not in pages['index.html'], 'home alone card title is neutral')
ok(pages['index.html'].count('>Sponsored<') >= 7, 'product cards and the partner post are labeled Sponsored')
ok(('%s staff' % name) in pages['index.html'] and ('%s staff' % name) in pages['llms.txt'], 'staff label renders from displayName')
ok('color: #000000' in pages['index.html'] and 'AI-made' in pages['index.html'], 'AI label stays AI-made at #000000')
ok('Do not post diagnoses.' in pages['guidelines.html'], 'guidelines tell members not to post diagnoses')
ok('SubX, LLC' in pages['index.html'] and 'takedown@subx.it' in pages['index.html'] and '+1-650-539-5005' in pages['index.html'], 'operator and public contacts are on the room')
ok('https://TBD' not in joined and '$' not in joined, 'no TBD url and no prices')
ok('puppies-for-sale' not in joined and 'psychiatric' not in joined.lower() and 'esa-training' not in joined.lower(), 'no puppy sales, PSD, or ESA course')
ok(not re.search(r'[\u2013\u2014]|\bpays\b|testimonial', joined, re.I), 'room output has no en or em dash, no "pays", no testimonial')
ok(all(u in pages['index.html'] for u in PR.RAIL_URLS), 'rail links the six training pages')
for label in ('Puppy start', 'Leash and walks', 'Barking and reactivity', 'Home alone', 'Tricks and enrichment', 'Breed corner'):
    ok(label in pages['index.html'], 'explore seat %s' % label)

alt = 'North Paw'
with tempfile.TemporaryDirectory() as t:
    room = os.path.join(t, 'rooms', 'dogacademy-partner')
    os.makedirs(room)
    swapped = json.loads(json.dumps(site))
    swapped['displayName'] = alt
    json.dump(swapped, open(os.path.join(room, 'site.json'), 'w'))
    alt_pages = PR.render(os.path.join(room, 'site.json'))
    blob = '\n'.join(alt_pages.values())
    ok(name not in blob and alt in alt_pages['index.html'] and ('<title>%s</title>' % alt) in alt_pages['index.html']
       and ('Sponsored by %s' % alt) in alt_pages['index.html'] and ('%s staff' % alt) in alt_pages['llms.txt']
       and ('Guidelines, %s' % alt) in alt_pages['guidelines.html'],
       'one displayName edit renames the room header, title, meta, posts, guidelines, and llms.txt')
    hub_out = os.path.join(t, 'hub')
    BR.render(out=hub_out, preview_partners=True, rooms_root=os.path.join(t, 'rooms'))
    idx = read(os.path.join(hub_out, 'index.html'))
    part = read(os.path.join(hub_out, 'partners.html'))
    ok('id="partner-rooms"' in idx and ('>%s</span>' % alt) in idx and ('Sponsored by %s' % alt) in idx
       and 'Why am I seeing this?' in idx and name not in idx, 'preview hub widget renders the swapped name')
    ok(alt in part and ('<title>%s, Why am I seeing this?' % alt) in part and name not in part
       and 'property="og:title" content="%s, Why am I seeing this?' % alt in part, 'partners page title, meta, and og follow displayName')
    ok(idx.index('id="news-feed"') < idx.index('id="partner-rooms"'), 'partner widget is under Suggested rooms')
    artp = read(os.path.join(hub_out, 'partners', 'dogacademy', 'articles', 'calm-steady-presence.html'))
    ok(('%s staff' % alt) in artp and name not in artp and 'Not affiliated with or endorsed by Cesar Millan.' in artp
       and 'rel="noopener"' in artp and 'https://www.cesarmillan.com/about' in artp,
       'article byline follows displayName and names the public source without an endorsement')

live = BR.render(out=os.path.join(tempfile.mkdtemp(), 'live'))
live_idx = read(os.path.join(live.out, 'index.html'))
live_part = read(os.path.join(live.out, 'partners.html'))
ok('id="partner-rooms"' not in live_idx and name not in live_idx and name not in live_part, 'flag off: hub home does not show the room')
room_home = read(os.path.join(live.out, 'partners', 'dogacademy', 'index.html'))
ok('class="room-banner"' in room_home and 'class="sidebar"' in room_home and name in room_home and 'noindex,nofollow' in room_home,
   'flag off still publishes the noindex room home')
ok(PR.load_articles() and len(PR.load_articles()['articles']) == 6, 'six original articles')
for line in ('Partner rooms are sponsored by the named company.',
             'SubX, LLC runs the rooms. Moderation stays with SubX, LLC.',
             'A brand cannot edit or remove member posts.',
             'Member data is never shared with a brand.',
             'There are no fake reviews.'):
    ok(line in live_part, 'partners page: %s' % line[:48])
ok(not re.search(r'\bpays\b', live_part, re.I), 'partners page does not say the brand pays')
ok('Fees are flat' not in live_part, 'partners page does not state a fee')
ok('labeled Sponsored' in live_part, 'partners page keeps the Sponsored label')
css = read(os.path.join(ROOT, 'hub', 'src', 'templates', 'hub.css'))
ok('#eff3f4' in css and '#536471' in css and '.partner-disclosure' in css and 'font-size: 15px' in css
   and 'body.hub-home:has(.partner-rooms) .right-panel' in css and 'position: static' in css,
   'widget uses #eff3f4 and a 15px #536471 disclosure, and follows organic rooms on a narrow screen')
rc = __import__('subprocess').run([sys.executable, os.path.join(ROOT, 'tools', 'brand_render.py'), '--preview-partners'], capture_output=True, text=True)
ok(rc.returncode == 2, 'preview flag refuses to write the live hub/site')

print('\n%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)
