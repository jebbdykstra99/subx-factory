#!/usr/bin/env python3
"""Hub Following / Notifications / Chat (2026-11-04). The hub stays read-only (no sign-in, no database, no writes):
the three nav links are hub-owned (#hub-* hashes, nav-hub-* ids, no data-soon / data-social), so the shell's Soon
painting cannot reach them; hub.js renders the views from the public build-time files; Chat and member
Notifications hand off to https://<room>/#chat and #notifications. The footer says "Topics (soon)" until a rendered
topic is active or quiet. Offline; temp dirs only."""
import json, os, re, shutil, sys, tempfile

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

ok("roomHref(r.domain, frag)" in js and "handoffRows('chat', 'Open Chat')" in js and "handoffRows('notifications', 'Open Notifications')" in js,
   'hub.js: Chat and member Notifications hand off to https://<room>/#chat and #notifications')
ok(re.search(r"/rooms\.json\?v=[0-9a-f]+'\), getJSON\('/highlights\.json\?v=[0-9a-f]+'", js) is not None, 'hub.js: views read the cache-busted rooms.json + highlights.json')
ok("/^#hub-(following|notifications|chat)$/" in js, 'hub.js: routes only the three #hub-* hashes')
ok("new MutationObserver" in js and "observe(thoughts, { attributes: true, attributeFilter: ['class'] })" in js,
   'hub.js: re-shows the hub view when the shell routes the unknown #hub-* hash to home')
ok(not re.search(r"firestore|firebase|fetch\([^)]*method|sendBeacon|XMLHttpRequest|navigator\.sendBeacon|WebSocket", js, re.I), 'hub.js: no database, no POST, no beacon')
ok(all(c in css for c in ('.hub-follow-btn', '.hub-handoff', '.hub-new', '.visually-hidden')), 'hub.css: view styles present')

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
