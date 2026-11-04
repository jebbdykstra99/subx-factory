#!/usr/bin/env python3
"""Stories module (shell v1.2.7) + hub Stories row / composer hand-off: static checks.

- factory.js: Stories default-on (storiesOn reads `enabled !== false`), text-only when the room sets imageUploads:false
  (no image/clip buttons, uploadStoryMedia refuses), and #story / #compose=<text> hand-off from the hub on boot.
- hub: stories.json schema (rooms + live text items only, no media URLs), hub-* markup present, the hub still never writes
  (no Firestore/Auth/fetch-POST in hub.js; CSP connect-src is 'self' plus the pinned sign-in origins), copy does not claim the hub posts.
Run: python3 test/stories_module.test.py
"""
import json, os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
fails = 0; oks = 0
def ok(c, m):
    global fails, oks
    if c: oks += 1; print('ok  ', m)
    else: fails += 1; print('FAIL', m)
def read(*p): return open(os.path.join(ROOT, *p), encoding='utf-8').read()

fx = read('factory', 'factory.js')
ok('return storiesCfg().enabled !== false;' in fx, 'factory.js: Stories default-on (enabled !== false)')
ok("site.imageUploads !== false ? type : 'text'" in fx, 'factory.js: story type falls back to text when imageUploads is false')
ok("var nu = site.imageUploads === false;" in fx and "(nu ? ' only in this room.</p>' : ', a photo, or a short clip.</p><div class=\"stories-composer-types\">" in fx, 'factory.js: text-only story composer copy and no type buttons when imageUploads is false')
ok("'\"></textarea>' + (nu ? '' : '<input class=\"stories-composer-file\"" in fx and "hidden>') + '<div class=\"stories-composer-err\"" in fx, 'factory.js: no file inputs, preview or caption rendered when imageUploads is false (Key 2 F1)')
ok("storiesErr(site.imageUploads === false ? 'Write a short card.' : " in fx, 'factory.js: empty-story error does not offer photo / clip when imageUploads is false')
ok('Lives 24 hours on this room only. Text\' + (nu' in fx, 'factory.js: note reads "Lives 24 hours on this room only. Text only in this room." when uploads are off')
ok(re.search(r"if \(!fbStorage \|\| !storiesOn\(\) \|\| site\.imageUploads === false\) return Promise\.reject", fx) is not None, 'factory.js: uploadStoryMedia refuses when imageUploads is false')
ok("/^#(compose|story)(?:=(.*))?$/.exec(location.hash)" in fx, 'factory.js: boot reads #story / #compose= hand-off from the URL fragment')
ok("if (hand[1] === 'story') openStoriesComposer();" in fx, 'factory.js: #story opens the Stories composer')
ok(re.search(r"restoreCompose\(decodeURIComponent\(hand\[2\] \|\| ''\)\.slice\(0, 280\)\)", fx) is not None, 'factory.js: #compose= text is decoded, clipped to 280 and only placed in the composer (never auto-posted)')
ok(not re.search(r"hand\[2\][^;]*submit|hand\[2\][^;]*addDoc", fx), 'factory.js: hand-off text is never submitted automatically')
ok("requireVerified('add a story')" in fx, 'factory.js: adding a story still needs a verified sign-in')
rel = json.loads(read('FACTORY_RELEASE.json')); rooms = json.loads(read('rooms.json'))
ok(rel['version'] == rooms['version'] == 'v1.2.7', 'release v1.2.7 matches root rooms.json')
sj = json.loads(read('shell', 'v1.2.7', 'SHELL.json'))
ok(sj.get('version') == 'v1.2.7', 'shell/v1.2.7/SHELL.json version')
ok(read('shell', 'v1.2.7', 'factory.js') == fx, 'shell/v1.2.7/factory.js equals factory/factory.js')

# hub
st = json.loads(read('hub', 'site', 'stories.json'))
ok(set(st) >= {'version', 'generated', 'ttlHours', 'membersShown', 'rooms', 'items'} and st['ttlHours'] == 24, 'stories.json: top-level schema')
listed = {r['room'] for r in json.loads(read('hub', 'site', 'rooms.json'))['rooms']}
ok(all(r['room'] in listed and isinstance(r['stories'], bool) for r in st['rooms']), 'stories.json: rooms are hub-listed rooms with a boolean stories flag')
ITEM = {'room', 'roomName', 'domain', 'storyId', 'text', 'authorName', 'tier', 'createdAt', 'expiresAt'}
ok(all(set(i) == ITEM for i in st['items']), 'stories.json: items carry only the public text fields (no media URLs)')
ok(not re.search(r'mediaUrl|posterUrl|firebasestorage', json.dumps(st)), 'stories.json: no media URLs')
ok(st['membersShown'] is False, 'stories.json: steward-only by default')
cfg = json.loads(read('hub', 'src', 'config.json'))
ok('stories.json' in cfg['data'], 'hub config: stories.json is a data file')
idx = read('hub', 'site', 'index.html'); js = read('hub', 'site', 'hub.js'); css = read('hub', 'site', 'hub.css')
for idn in ('hub-stories-row', 'hub-story-add', 'hub-compose-text', 'hub-compose-room', 'hub-compose-go', 'hub-story-pick', 'hub-story-view'):
    ok('id="%s"' % idn in idx, 'index.html: #%s present' % idn)
ok('class="stories-tray' not in idx.split('hub-stories')[0][-200:], 'index.html: hub row does not reuse the hidden .stories-tray class')
ok('.hub-story' in css and '.hub-compose' in css, 'hub.css: hub-story / hub-compose styles')
ok(re.search(r"/stories\.json\?v=[0-9a-f]+", js) is not None, 'hub.js: stories.json is cache-busted')
ok("'compose=' + encodeURIComponent(text)" in js and "roomHref(r.domain, 'story')" in js, 'hub.js: hand-off goes to https://<room>/#compose= and #story')
ok(not re.search(r"firestore|firebase|method:\s*'POST'|sendBeacon|XMLHttpRequest|sessionStorage|document\.cookie|indexedDB", js, re.I), 'hub.js: no writes, no Firebase, no cookies or session storage')
# 2026-11-04 (hub Following): the ONE browser-storage use is the follows key (test/hub_storage_guard.py, which also
# refuses bracket access, built names, and other indirect routes to storage)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hub_storage_guard  # noqa: E402
probs = hub_storage_guard.problems(js)
ok(not probs, 'hub.js: storage only via window.localStorage get/setItem(HUB_STORE = hub.follows.v1), no indirect access (%s)' % probs)
csp = re.search(r"connect-src ([^;\"]+)", read('hub', 'firebase.json') if os.path.exists(os.path.join(ROOT, 'hub', 'firebase.json')) else idx)
# HUB SIGN-IN (2026-11-04): connect-src adds only the Firebase Auth / App Check / Firestore origins the shell's
# sign-in needs (pinned in test/hub_brand.test.py); hub.js itself still writes nothing (checked above).
HUB_CONNECT = "'self' https://subx-skins.web.app https://identitytoolkit.googleapis.com https://securetoken.googleapis.com https://firestore.googleapis.com https://content-firebaseappcheck.googleapis.com https://www.google.com/recaptcha/"
ok(csp is None or csp.group(1).strip() == HUB_CONNECT, "hub CSP connect-src is 'self' plus only the pinned sign-in origins")
vis = re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style)\b.*?</\1>', '', idx, flags=re.S))
ok('The hub does not save or send your text: it opens that room and copies your words so you can paste them there.' in vis, 'index.html: composer note (Key 1 E1 wording)')
ok('<!--' not in idx.split('id="hub-stories"')[0][-400:] and 'STORIES.md' not in idx, 'index.html: no internal note comment before the Stories row')
ok('source' not in st, 'stories.json: no internal source note')
ok('data/' not in json.dumps(json.loads(read('hub', 'site', 'site.json')).get('stories')), 'hub site.json: no internal data/ path note')
ok(not re.search(r'post(ed)? (here|on the hub|from the hub) (now|today)|your post is live', vis, re.I), 'index.html: no claim that the hub posts')
hs = json.loads(read('hub', 'site', 'site.json'))
ok(hs.get('stories', {}).get('enabled') is False and hs.get('accountsOpen') is True, 'hub site.json: hub runs no Stories of its own; accounts open for sign-in only (HUB SIGN-IN)')
print('\n%d ok, %d fail' % (oks, fails))
sys.exit(1 if fails else 0)
