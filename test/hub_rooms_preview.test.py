#!/usr/bin/env python3
"""Rooms tab preview: accent and Room Brief come from each room site.json via build_highlights.py,
the newest highlight is the one highlights.json already published, and the rendered hub reuses that
data. No partner room is listed while its flag is off. Offline except the render check."""
import json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'hub', 'src'))
import build_highlights as BH  # noqa: E402

fails = []


def ok(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        fails.append(msg)


def read(*p):
    return open(os.path.join(ROOT, *p), encoding='utf-8').read()


site = {'theme': {'accent': '  #AABBCC '}, 'rail': {'title': 'Room Brief', 'outbound': [
    {'headline': 'Race day \u2014 skip', 'snippet': 'also \u2013 skip'},
    {'headline': 'Seed: not this', 'snippet': 'Plain fallback line'},
    {'headline': 'First safe line', 'snippet': 'later'}]}}
ok(BH.accent_of(site) == '#aabbcc', 'accent_of keeps a 6-digit hex and lowercases it')
ok(BH.accent_of({'theme': {'accent': 'red'}}) == '' and BH.accent_of({}) == '', 'accent_of drops a non-hex accent')
ok(BH.brief_line(site) == 'Plain fallback line', 'brief_line skips a dash headline and a Seed headline, then keeps that card snippet')
ok(BH.brief_line({'rail': {'outbound': [{'headline': 'Email me user@example.com', 'snippet': 'Kept snippet'}]}}) == 'Kept snippet',
   'brief_line skips a line with an email')
ok(BH.preview_from({'url': 'https://gpchat.com/?p=Ab1', 'text': 'Hello there', 'authorHandle': 'pit', 'tier': 'ai', 'createdAt': '2026-11-02T00:00:00Z'})
   == {'url': 'https://gpchat.com/?p=Ab1', 'handle': 'pit', 'tier': 'ai', 'text': 'Hello there', 'createdAt': '2026-11-02T00:00:00Z'},
   'preview_from copies the post and does not edit the text')
ok(BH.preview_from({'url': 'http://gpchat.com/?p=Ab1', 'text': 'Hello', 'tier': 'ai'}) is None, 'preview_from refuses a non-https post url')
ok(BH.preview_from({'url': 'https://gpchat.com/?p=Ab1', 'text': 'Seed hello', 'tier': 'ai'}) is None, 'preview_from refuses a Seed post')
items = [{'room': 'a', 'createdAt': '2026-11-01T00:00:00Z', 'url': 'https://a.example/?p=old', 'text': 'old', 'tier': 'ai', 'authorHandle': 'old'},
         {'room': 'a', 'createdAt': '2026-11-02T00:00:00Z', 'url': 'https://a.example/?p=new', 'text': 'new', 'tier': 'human', 'authorHandle': 'new'}]
ok(BH.latest_by_room(items)['a']['text'] == 'new', 'latest_by_room keeps the newest highlight')

src_rooms = json.load(open(os.path.join(ROOT, 'hub', 'src', 'data', 'rooms.json'), encoding='utf-8'))
src_hl = json.load(open(os.path.join(ROOT, 'hub', 'src', 'data', 'highlights.json'), encoding='utf-8'))
latest = BH.latest_by_room(src_hl['items'])
ok(all(re.fullmatch(r'#[0-9a-f]{6}', r.get('accent', '')) for r in src_rooms['rooms']), 'every listed room has a 6-digit accent')
ok(all(r.get('brief') and BH.tagline_rule(r['brief']) is None and not re.search(r'[\u2013\u2014]', r['brief']) for r in src_rooms['rooms']),
   'every listed room has a Room Brief line with no em or en dash')
ok(all('partner' not in r and r.get('enabled') is not False for r in src_rooms['rooms']), 'listed rooms are not partner entries')
for r in src_rooms['rooms']:
    want = BH.preview_from(latest.get(r['room']))
    ok(r.get('preview') == want, '%s preview matches the newest published highlight' % r['room'])
ok(not any(r.get('preview') for r in src_rooms['rooms'] if r['room'] == '808chat'), '808chat has no highlight preview')
ok(any(r['room'] == '808chat' and r.get('brief') for r in src_rooms['rooms']), '808chat falls back to a Room Brief line')

src_js = read('hub', 'src', 'templates', 'hub.js')
chunk = src_js.split('function labelText', 1)[1].split('function getJSON', 1)[0]
ok('function labelText' in src_js and not re.search(r'[\u2013\u2014]', chunk), 'new room peek copy has no em or en dash')
ok("(r.tagline ? '<p>' + esc(r.tagline) + '</p>' : '')" in src_js, 'a room with no tagline still renders no empty tagline line')
ok("jsonCache['{{asset:/highlights.json}}']" in src_js and "!(r.partner === true && r.enabled !== true)" in src_js,
   'the Rooms tab reuses a highlights fetch already in flight, and a partner room stays hidden while enabled is not true')
css = read('hub', 'src', 'templates', 'hub.css')
ok('flex: 0 1 40%' in css and 'max-width: 320px' in css and 'box-shadow: none' in css, 'desktop preview is about 40% wide, max 320px, no shadow')
ok('@media (max-width: 480px)' in css and '.hub-room-peek-line' in css and '-webkit-line-clamp: 2' in css,
   'narrow widths collapse the preview to one muted line, and the desktop snippet clamps to two lines')
ok('var(--text-light)' in css and 'var(--text-muted)' in css and '#536471' in read('hub', 'src', 'templates', 'styles.css'),
   'secondary text uses the hub tokens, #536471 on the light canvas')

r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'brand_render.py'), '--check'], capture_output=True, text=True)
ok(r.returncode == 0, 'brand_render --check (%s%s)' % (r.stdout.strip(), r.stderr.strip()))
site_rooms = json.load(open(os.path.join(ROOT, 'hub', 'site', 'rooms.json'), encoding='utf-8'))
ok(site_rooms == src_rooms, 'rendered rooms.json matches hub/src/data/rooms.json')
dom = subprocess.run(['node', os.path.join(ROOT, 'test', 'hub_rooms_preview_dom.test.js')], capture_output=True, text=True)
ok(dom.returncode == 0, 'hub_rooms_preview_dom.test.js (%s)' % ((dom.stdout + dom.stderr).strip().splitlines()[-1:] or [dom.stderr]))
if dom.returncode != 0:
    print(dom.stdout)
    print(dom.stderr)

print('\n%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)
