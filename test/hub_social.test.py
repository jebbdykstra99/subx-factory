#!/usr/bin/env python3
"""Hub Following / Notifications / Chat (2026-11-04). The hub stays read-only (no sign-in, no database, no writes):
the three nav links are hub-owned (#hub-* hashes, nav-hub-* ids, no data-soon / data-social), so the shell's Soon
painting cannot reach them; hub.js renders the views from the public build-time files; Chat and member
Notifications hand off to https://<room>/#chat and #notifications. The footer says "Topics (soon)" until a rendered
topic is active or quiet. Offline; temp dirs only."""
import json, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import brand_render as BR  # noqa: E402

fails = []


def ok(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        fails.append(msg)


def read(*p):
    return open(os.path.join(ROOT, *p), encoding='utf-8').read()


idx = read('hub', 'site', 'index.html'); js = read('hub', 'site', 'hub.js'); css = read('hub', 'site', 'hub.css')
nav = idx.split('<nav', 1)[1].split('</nav>', 1)[0] if '<nav' in idx else idx
for v in ('following', 'notifications', 'chat'):
    m = re.search(r'<a [^>]*data-hub-view="%s"[^>]*>' % v, idx)
    ok(m is not None and 'href="#hub-%s"' % v in m.group(0) and 'id="nav-hub-%s"' % v in m.group(0), 'nav: %s is a hub-owned link (#hub-%s)' % (v, v))
    ok(m is not None and 'data-soon' not in m.group(0) and 'data-social' not in m.group(0), 'nav: %s carries no data-soon / data-social' % v)
    ok('id="nav-%s"' % v not in idx, 'index.html: no #nav-%s for the shell to paint Soon on' % v)
ok('id="notif-badge"' not in idx and 'id="hub-notif-badge"' in idx, 'nav: the notifications badge is hub-owned')
ok(not re.search(r'nav-soon|>\s*Soon\s*<', nav), 'nav: no Soon label in the left nav markup')
for pid in ('page-hub-following', 'page-hub-notifications', 'page-hub-chat', 'hub-following-feed', 'hub-follow-list',
            'hub-notif-feed', 'hub-notif-rooms', 'hub-chat-rooms'):
    ok('id="%s"' % pid in idx, 'index.html: #%s present' % pid)
ok(re.search(r'class="page hub-view" id="page-hub-following"', idx) is not None, 'index.html: hub views are .page sections')
vis = re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style)\b.*?</\1>', '', idx, flags=re.S))
ok('saved in this browser only' in vis and 'the hub sends them nowhere' in vis, 'Following copy: follows stay in the browser')
ok('The hub does not read or store your messages.' in vis, 'Chat copy: the hub does not read or store messages')
ok('Read-only' in idx, 'footer still says Read-only')

ok("listedHref(r.domain, frag)" in js and "handoffRows('chat', 'Open Chat')" in js and "handoffRows('notifications', 'Open Notifications')" in js,
   'hub.js: Chat and member Notifications hand off to https://<room>/#chat and #notifications')
ok(re.search(r"/rooms\.json\?v=[0-9a-f]+'\), getJSON\('/highlights\.json\?v=[0-9a-f]+'", js) is not None, 'hub.js: views read the cache-busted rooms.json + highlights.json')
ok("/^#hub-(following|notifications|chat)$/" in js, 'hub.js: routes only the three #hub-* hashes')
ok("new MutationObserver" in js and "observe(thoughts, { attributes: true, attributeFilter: ['class'] })" in js,
   'hub.js: re-shows the hub view when the shell routes the unknown #hub-* hash to home')
ok(not re.search(r"firestore|firebase|fetch\([^)]*method|sendBeacon|XMLHttpRequest|navigator\.sendBeacon|WebSocket", js, re.I), 'hub.js: no database, no POST, no beacon')
ok(all(c in css for c in ('.hub-follow-btn', '.hub-handoff', '.hub-new', '.visually-hidden')), 'hub.css: view styles present')

# outbound links: only the exact rooms.json domains (behaviour checked in test/hub_social_dom.test.js)
ok("hubDomains[String(r.domain).toLowerCase()] = true" in js and "items.map(listedCard)" in js and "var c = listedCard(it)" in js
   and "var url = listedHref(r.domain, '')" in js and "roomHref(r.domain, frag)" not in js,
   'hub.js: Following rows, feeds, and Chat / Notifications hand-offs go only to domains listed in rooms.json')
r = subprocess.run(['node', os.path.join(ROOT, 'test', 'hub_social_dom.test.js')], capture_output=True, text=True)
ok(r.returncode == 0, 'hub_social_dom.test.js (fake DOM): links stay on rooms.json domains, only hub.follows.v1 stored (%s)'
   % (r.stdout.strip().splitlines()[-1:] if r.returncode == 0 else r.stdout + r.stderr))

# storage: the one key, no indirect access (shared guard with stories_module)
sys.path.insert(0, os.path.join(ROOT, 'test'))
import hub_storage_guard  # noqa: E402
probs = hub_storage_guard.problems(js)
ok(not probs, 'hub.js: storage only via window.localStorage get/setItem(HUB_STORE), no bracket or indirect access (%s)' % probs)

# privacy page: the hub follows paragraph (Key 2 C1), in the source and in the built page
def norm(h):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', h)).strip()
brand = json.load(open(os.path.join(ROOT, 'brand', 'brand.json')))
src_p = read('hub', 'src', 'templates', 'privacy.html'); site_p = read('hub', 'site', 'privacy.html')
for name, page, dom, ent in (('src', src_p, '{{brand.primaryDomain}}', '{{brand.legalEntity}}'),
                             ('site', site_p, brand['primaryDomain'], brand['legalEntity'])):
    m = re.search(r'<p id="hub-follows-storage">(.*?)</p>', page, re.S)
    t = norm(m.group(1)) if m else ''
    ok(m is not None and page.count('id="hub-follows-storage"') == 1, 'privacy (%s): one hub follows paragraph' % name)
    want = ("Hub follows: when you follow rooms on %s, the list of rooms you follow and a list of the highlights you have "
            "already seen are kept only in your browser's local storage as hub.follows.v1. They are not sent to %s or anyone "
            "else. Clearing your browser data removes them. You can also unfollow rooms at any time." % (dom, ent))
    ok(t == want, 'privacy (%s): paragraph is the Key 1 P1 text, exactly (%r)' % (name, t))
    ok('<code>hub.follows.v1</code>' in m.group(1) and 'kept only in your browser' in t and 'They are not sent to %s or anyone else.' % ent in t
       and 'Clearing your browser data removes them.' in t and 'You can also unfollow rooms at any time.' in t,
       'privacy (%s): pins the key, browser only, not sent, how to clear, unfollow' % name)
    ok('the time you last opened Notifications' not in t, 'privacy (%s): describes what is stored now (seen highlight ids, not a time)' % name)
    ok(not re.search(r'[\u2010-\u2015]| - ', t), 'privacy (%s): no dashes in the paragraph' % name)
    ok('hub.follows.v1' == hub_storage_guard.KEY and ("var HUB_STORE = '%s';" % hub_storage_guard.KEY) in js,
       'privacy (%s): the key named on the page is the key hub.js uses' % name)
ok(site_p.find('id="hub-follows-storage"') > site_p.find('Cookies / local storage'), 'privacy: paragraph follows the information list')

# Key 1 E1: no Soon left on the hub nav or tabs; the shell's Soon overlays are gone; its old hashes go to the hub views
main = idx.split('<main', 1)[1].split('</main>', 1)[0] if '<main' in idx else idx
tabs = re.findall(r'<button[^>]*class="thoughts-tab[^"]*"[^>]*>.*?</button>', idx, re.S)
ok(tabs and not [x for x in tabs if re.search(r'soon', x, re.I)], 'E1: no tab says Soon (%d tabs)' % len(tabs))
ok('data-thoughts-tab="following"' not in idx, 'E1: the shell For You "Following" tab is not on the hub')
ok(not re.search(r'tab-soon|>\s*Soon\s*<|Chat: Soon', idx), 'E1: no Soon label anywhere in hub index.html')
ok(all(('id="%s"' % x) not in idx for x in ('chat-overlay', 'chat-new-btn', 'chat-placeholder', 'chat-send-btn', 'notif-mark-read')), 'E1: shell Chat / Notifications Soon overlays removed')
stub = re.search(r'<div class="notif-overlay" id="notif-overlay"[^>]*>(.*?)</div>\s*</div>', idx, re.S)
ok(stub is not None and ' hidden' in stub.group(0).split('>', 1)[0] and 'id="notif-back"' in stub.group(1) and not re.search(r'soon', stub.group(0), re.I),
   'E1: only a hidden, Soon free notif-overlay stub stays (the shell wires notif-back at start)')
ok("var LEGACY = { '#following': '#hub-following', '#notifications': '#hub-notifications', '#chat': '#hub-chat' };" in js,
   "E1: #following, #notifications and #chat land on the hub views")
# Key 1 E2: member Notifications only for rooms that have them; copy
src_rooms_d = json.load(open(os.path.join(ROOT, 'hub', 'src', 'data', 'rooms.json'), encoding='utf-8'))
site_rooms_d = json.load(open(os.path.join(ROOT, 'hub', 'site', 'rooms.json'), encoding='utf-8'))
ok(all(isinstance(x.get('notifs'), bool) for x in src_rooms_d['rooms'] + site_rooms_d['rooms']), 'E2: every rooms.json entry says notifs true or false')
nf = {x['room']: x['notifs'] for x in site_rooms_d['rooms']}
ok(all(nf.get(x) is False for x in ('gpchat', 'popechat', '311chat') if x in nf), 'E2: gpchat, popechat, 311chat ship notifs false (no member Notifications there)')
ok("frag !== 'notifications' || hubNotifs[r.room] === true" in js, 'E2: hub.js lists Open Notifications only for notifs rooms')
ok("'notifs': notifs" in read('hub', 'src', 'build_highlights.py') and "site_doc['features'].get('notifs') is True" in read('hub', 'src', 'build_highlights.py'),
   'E2: build_highlights sets notifs from the room site.json features.notifs')
ok("Rooms with Notifications turned on show replies, mentions, and follows from members there, under that room's sign-in." in vis,
   'E2: Notifications copy (rooms with Notifications turned on)')
ok('Direct messages, and in most rooms replies and mentions, live in each room under its sign-in; the hub links you there.' in vis,
   'E2: What is coming copy (DMs, and in most rooms replies and mentions)')
# Key 1 E3: freshness copy; New by seen ids; baseline on follow
ok('New highlights from rooms you follow since you last looked. Highlights update when the hub is rebuilt, not in real time.' in vis, 'E3: Notifications freshness copy')
ok('Date.now()' not in js.split("var HUB_STORE")[1] and 'msOf(it.createdAt) > since' not in js, 'E3: New is not createdAt vs Date.now()')
ok('hub.rooms.push(room); markSeen(room);' in js, 'E3: following a room marks its current highlights seen (badge starts at 0)')
# Key 1 E4: error copy
ok('This did not load. Try again later, or open a room from <a href="/rooms.html">Rooms</a>.' in js, 'E4: load error copy')
# Key 1 N1: llms.txt Live line
llms = read('hub', 'site', 'llms.txt')
ok(re.search(r"^- Live: .*following rooms and new-highlight notifications on the hub, saved only in your browser; links to each room's Chat\.$", llms, re.M) is not None,
   'N1: llms.txt Live line names Following, Notifications and Chat')
new_copy = ["Rooms with Notifications turned on", "Direct messages, and in most rooms", "Highlights update when the hub is rebuilt", "This did not load."]
ok(not [c for c in new_copy if re.search(r'[\u2010-\u2015]', c)], 'new copy: no dashes')

# footer Topics label follows topic status
r = BR.Renderer(os.path.join(ROOT, 'hub', 'src'), os.path.join(ROOT, 'brand', 'brand.json'), tempfile.mkdtemp())
ok(r.ctx['topicsNav']['soon'] == ' (soon)', 'footer: no active topic today, label keeps "(soon)"')
ok('>Topics (soon)</a>' in idx, 'index.html: footer shows Topics (soon) today')
with tempfile.TemporaryDirectory() as t:
    src = os.path.join(t, 'src'); shutil.copytree(os.path.join(ROOT, 'hub', 'src'), src)
    cfg = json.load(open(os.path.join(src, 'config.json')))
    seed = json.load(open(os.path.join(ROOT, cfg['topics']['seed'])))
    first = next(x for x in seed['topics'] if x['status'] == 'hidden')
    first['status'] = 'active'
    sp = os.path.join(t, 'seed.json'); json.dump(seed, open(sp, 'w'))
    cfg['topics']['seed'] = sp; json.dump(cfg, open(os.path.join(src, 'config.json'), 'w'))
    r2 = BR.Renderer(src, os.path.join(ROOT, 'brand', 'brand.json'), os.path.join(t, 'out'))
    ok(r2.ctx['topicsNav']['soon'] == '', 'footer: one active topic drops "(soon)"')

print('\n%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)
