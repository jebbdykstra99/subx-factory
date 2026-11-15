#!/usr/bin/env python3
"""Featured room rotation on the hub home (2026-11-15), static and simulated checks.

Covers: config.json home.featured_rotation (explicit alphabetical allowlist of live public rooms, epoch, pin null by
default, the "Featured today" label), every date in full cycles simulated in Python and in node against the shipped
hub.js pick (hourly instants across both 2026-11-01 and 2027-03-14 US Mountain Time DST changes, switching at local
midnight), every allowlisted room appearing once per cycle, no paused, held, 21+, or Agent Room ever appearing, Also
featured being the next two rooms, the pin overriding the date, the built cards (one per room, one shown, type cards
for rooms without photos, white text at AA or better on both gradient stops, no #1D9BF0, no dashes, no inline script),
and the photo carousel only under the exact featured room. Python stdlib plus node."""
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'hub', 'src'))
import build_highlights as B  # noqa: E402

fails = []
DASH = re.compile('[\u2013\u2014]')
NEVER = {'airlineschat', 'amachat', 'atmchat', 'behindtheblackwall', 'boyfriendchat', 'boozechat', 'agentroom', 'grokchat'}


def ok(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        fails.append(msg)


def read(*p):
    with open(os.path.join(ROOT, *p), encoding='utf-8') as f:
        return f.read()


cfg_home = json.loads(read('hub', 'src', 'config.json'))['home']
fr = cfg_home.get('featured_rotation') or {}
allow = fr.get('rooms') or []
src = {r['room']: r for r in json.loads(read('hub', 'src', 'rooms.json'))['rooms']}

# ---- config ----
ok(len(allow) >= 3 and allow == sorted(allow) and len(set(allow)) == len(allow), 'allowlist is explicit, unique, alphabetical (%d rooms)' % len(allow))
ok(not (set(allow) & NEVER) and not any('grok' in r or 'agent' in r for r in allow), 'allowlist has no paused, held, 21+, or Agent Room entry')
ok(all(src.get(r, {}).get('status') == 'live' and src[r].get('highlights') is True and not src[r].get('hold') for r in allow),
   'every allowlisted room is live, public, and unheld in hub/src/rooms.json')
PIN = fr.get('pin', 'missing')
ok(PIN is None, 'pin is present and null (the Sunday rule replaces a one-time pin)')
WD = fr.get('weekday_featured')
ok(WD == {'sun': 'popechat'}, 'weekday_featured gives popechat every Sunday (decided 2026-11-15 3:53 PM MT)')
ok('weekday_featured' in cfg_home.get('_doc', '') and 'Sunday' in cfg_home.get('_doc', ''), 'config _doc explains the weekday rule')
ok(fr.get('timezone') == 'US/Mountain' and re.match(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}$', fr.get('epoch', '')) is not None, 'epoch is a date, timezone is US/Mountain')
ok(fr.get('label') == 'A {{brand.name}} room · Featured today', 'label is "A {brand} room · Featured today"')
ok(not DASH.search(json.dumps(fr, ensure_ascii=False)) and not DASH.search(cfg_home.get('_doc', '')), 'no em or en dash in the rotation config or its doc')
ok('kill switch' in cfg_home.get('_doc', '') and 'featured_rotation' in cfg_home.get('_doc', ''), 'config _doc explains the rotation and the kill-switch limit')

# The pick never needs a tz database (build_highlights.mountain_date is the US rule; hub.js uses Intl, then the same
# rule). When a zone database is available (system, or the tzdata package that ci.yml installs), cross-check the rule.
try:
    from zoneinfo import ZoneInfo
    _mt = ZoneInfo('US/Mountain')
except Exception:
    _mt = None
if _mt is not None:
    _t, _bad = datetime(2026, 1, 1, tzinfo=timezone.utc), 0
    while _t < datetime(2029, 1, 1, tzinfo=timezone.utc):
        _bad += B.mountain_date(_t) != _t.astimezone(_mt).date()
        _t += timedelta(minutes=30)
    ok(_bad == 0, 'US Mountain rule = zoneinfo US/Mountain at every half hour, 2026 to 2028 (%d mismatches)' % _bad)
else:
    print('skip zoneinfo US/Mountain cross-check (no zone database; the pick does not need one)')

rot = B.feat_rooms()
order = [c['room'] for c in rot['rooms']]
ok(order == allow and not rot['skipped'], 'every allowlisted room is in hub/src/data/rooms.json, so the rotation is the whole allowlist')
N = len(order)
epoch = date.fromisoformat(fr['epoch'])

# ---- Python pick over full cycles ----
def py_pick(d, pin=None, weekday=WD):
    return B.feat_pick(order, fr['epoch'], d.isoformat(), pin, weekday)


for start in (epoch, date(2026, 10, 20), date(2027, 3, 1)):
    days = [start + timedelta(days=k) for k in range(N * 7 // 6 + 7)]
    rr = [py_pick(d)[0] for d in days if d.weekday() != 6][:N]
    ok(sorted(rr) == order, 'one full round-robin cycle from %s (Sundays skipped) shows every allowlisted room exactly once' % start)
    ok(sorted(py_pick(start + timedelta(days=k), weekday={})[0] for k in range(N)) == order, 'with no weekday rule, %d consecutive days from %s show every room once' % (N, start))
sundays = [epoch + timedelta(days=k) for k in range(-7, 7 * N + 7) if (epoch + timedelta(days=k)).weekday() == 6]
ok(len(sundays) >= N and all(py_pick(d)[0] == 'popechat' for d in sundays), 'every Sunday across a full cycle (%d Sundays) is popechat' % len(sundays))
ok(all(py_pick(d)[1] == [order[(order.index('popechat') + 1) % N], order[(order.index('popechat') + 2) % N]] for d in sundays), 'on Sundays, Also featured is the next two after popechat')
ok(py_pick(date(2026, 11, 16))[0] == '27chat' == order[0], 'Monday 2026-11-16 (the epoch) is still 27chat')
ok(py_pick(date(2026, 11, 15))[0] == 'popechat', 'today, Sunday 2026-11-15, shows popechat')
ok(py_pick(date(2026, 11, 14))[0] == order[-1], 'the Saturday before the epoch wraps to the last room')
rr_all = [py_pick(epoch + timedelta(days=k))[0] for k in range(7 * N) if (epoch + timedelta(days=k)).weekday() != 6]
ok(all(rr_all.count(r) == 6 for r in order), 'over 14 weeks every room gets exactly 6 round-robin days (none is stuck on Sunday)')
ok(all(py_pick(d, 'gaichat')[0] == 'gaichat' for d in sundays), 'pin beats the Sunday rule (gaichat on every Sunday when pinned)')
good_also = True
for k in range(-N, 3 * N):
    room, also = py_pick(epoch + timedelta(days=k))
    i = order.index(room)
    good_also &= also == [order[(i + 1) % N], order[(i + 2) % N]] and room not in also and not (set(also) | {room}) & NEVER
ok(good_also, 'Also featured is always the next two rooms in order, never the featured room, never an excluded room')
ok(all(py_pick(epoch + timedelta(days=k), 'gaichat')[0] == 'gaichat' for k in range(2 * N)), 'pin overrides the date (gaichat every day)')
gi = order.index('gaichat') if 'gaichat' in order else 0
ok(py_pick(epoch, 'gaichat')[1] == [order[(gi + 1) % N], order[(gi + 2) % N]], 'pinned: Also featured is the next two after the pin')
ok(py_pick(epoch, 'boyfriendchat')[0] == order[0], 'a pin that is not on the allowlist is ignored')

# ---- the shipped hub.js pick, run in node, hourly across both DST changes ----
js = read('hub', 'site', 'hub.js')
blk = B.FEAT_START and js[js.find('/* featured-rotation:start'):js.find('/* featured-rotation:end */')]
ok(len(blk) > 400 and 'Math.random' not in blk and 'setInterval' not in blk and 'setTimeout' not in blk, 'hub.js carries the pick block, with no randomness and no timer')
instants = []
for a, b in ((datetime(2026, 10, 25, tzinfo=timezone.utc), datetime(2026, 11, 12, tzinfo=timezone.utc)),
             (datetime(2027, 3, 8, tzinfo=timezone.utc), datetime(2027, 3, 24, tzinfo=timezone.utc))):
    t = a
    while t < b:
        instants.append(t)
        t += timedelta(minutes=30)
# both sides of local midnight on DST days and plain days (MDT midnight = 06:00Z, MST midnight = 07:00Z)
for s in ('2026-10-31T05:59:59Z', '2026-10-31T06:00:00Z', '2026-11-01T05:59:59Z', '2026-11-01T06:00:00Z', '2026-11-02T06:59:59Z',
          '2026-11-02T07:00:00Z', '2027-03-14T06:59:59Z', '2027-03-14T07:00:00Z', '2027-03-15T05:59:59Z', '2027-03-15T06:00:00Z'):
    instants.append(datetime.fromisoformat(s.replace('Z', '+00:00')))
harness = blk + '\n' + (
    'var order = %s, epoch = %s, ts = %s, wd = %s, pins = [null, "gaichat"], out = [];\n'
    'for (var p = 0; p < pins.length; p++) for (var k = 0; k < ts.length; k++) { var r = featPick(order, epoch, new Date(ts[k]), "US/Mountain", pins[p], wd); out.push(r.room + "|" + r.also.join(",")); }\n'
    'process.stdout.write(JSON.stringify(out));\n') % (json.dumps(order), json.dumps(fr['epoch']), json.dumps([int(t.timestamp() * 1000) for t in instants]), json.dumps(WD))
try:
    res = subprocess.run(['node', '-e', harness], capture_output=True, text=True, timeout=60)
    got = json.loads(res.stdout) if res.returncode == 0 else None
except FileNotFoundError:
    got = None
ok(got is not None, 'node runs the shipped pick block (%s)' % ('' if got is not None else res.stderr[:200]))
if got is not None:
    want = []
    for pin in (None, 'gaichat'):
        for t in instants:
            room, also = py_pick(B.mountain_date(t), pin)
            want.append(room + '|' + ','.join(also))
    bad = [(instants[k % len(instants)].isoformat(), got[k], want[k]) for k in range(len(want)) if got[k] != want[k]]
    ok(not bad, 'hub.js pick = Python pick by Mountain Time calendar date at %d instants, both DST changes, pin on and off %s' % (len(want), bad[:3]))
    fb = subprocess.run(['node', '-e', blk + '\nvar ts=%s,r=[];for(var k=0;k<ts.length;k++){r.push(featYmd(new Date(ts[k]),"No/SuchZone").join("-"));}process.stdout.write(JSON.stringify(r));'
                        % json.dumps([int(t.timestamp() * 1000) for t in instants])], capture_output=True, text=True)
    fbw = ['%d-%d-%d' % (d.year, d.month, d.day) for d in (B.mountain_date(t) for t in instants)]
    ok(fb.returncode == 0 and json.loads(fb.stdout) == fbw, 'hub.js fallback without an Intl time zone uses the US Mountain rule and matches at every instant')
    ok(all(g.split('|')[0] in order and not set(g.replace('|', ',').split(',')) & NEVER for g in got), 'node never picks an excluded room')
    mid = [got[len(instants) - 10 + k].split('|')[0] for k in range(10)]
    ok(mid[0] != mid[1] and mid[2] != mid[3] and mid[4] != mid[5] and mid[6] != mid[7] and mid[8] != mid[9],
       'the card changes exactly at midnight US Mountain Time, in MDT and MST and on both DST days')

# ---- built page ----
home = read('hub', 'site', 'index.html')
sec = home[home.find('<!-- featured-rotation:start'):home.find('<!-- featured-rotation:end -->')]
ok(bool(sec) and 'data-feat-order="%s"' % ' '.join(order) in sec and 'data-feat-epoch="%s"' % fr['epoch'] in sec
   and 'data-feat-tz="US/Mountain"' in sec and 'data-feat-pin=""' in sec and 'data-feat-weekday="sun:popechat"' in sec,
   'built hero carries the order, epoch, timezone, empty pin, and the Sunday rule')
cards = re.findall(r'<div class="hub-feat( is-type)?" data-feat="([a-z0-9-]+)"( style="--feat-a:(#[0-9a-f]{6});--feat-b:(#[0-9a-f]{6})")?( hidden)?>', sec)
sets = re.findall(r'<div class="hub-also-set" data-feat="([a-z0-9-]+)"( hidden)?>(.*?)</div></div>(?=\s*<div class="hub-also-set|\s*</div>)', sec, re.S)
ok([c[1] for c in cards] == order, 'one hero card per allowlisted room, in order')
shown = [c[1] for c in cards if not c[5]]
dflt = re.search(r'data-feat-default="([a-z0-9-]+)"', sec)
ok(len(shown) == 1 and dflt is not None and shown[0] == dflt.group(1), 'exactly one card is shown without JavaScript: the build date default (%s)' % shown)
if got is not None:
    sun_ms = [int(datetime(d.year, d.month, d.day, 19, tzinfo=timezone.utc).timestamp() * 1000) for d in sundays]
    hp = subprocess.run(['node', '-e', blk + '\nvar o=%s,ts=%s,r=[];for(var k=0;k<ts.length;k++){r.push(featPick(o,%s,new Date(ts[k]),"US/Mountain",null,%s).room+"/"+featPick(o,%s,new Date(ts[k]),"US/Mountain","gaichat",%s).room);}process.stdout.write(JSON.stringify(r));'
                        % (json.dumps(order), json.dumps(sun_ms), json.dumps(fr['epoch']), json.dumps(WD), json.dumps(fr['epoch']), json.dumps(WD))], capture_output=True, text=True)
    ok(hp.returncode == 0 and set(json.loads(hp.stdout)) == {'popechat/gaichat'}, 'hub.js: every Sunday is popechat, and a pin beats the Sunday rule')
    mon = subprocess.run(['node', '-e', blk + '\nprocess.stdout.write(featPick(%s,%s,new Date(Date.UTC(2026,10,16,19)),"US/Mountain",null,%s).room+" "+featPick(%s,%s,new Date(Date.UTC(2026,10,15,19)),"US/Mountain",null,%s).room);'
                         % (json.dumps(order), json.dumps(fr['epoch']), json.dumps(WD), json.dumps(order), json.dumps(fr['epoch']), json.dumps(WD))], capture_output=True, text=True)
    ok(mon.stdout == '27chat popechat', 'hub.js: Monday 2026-11-16 is 27chat and today, Sunday 2026-11-15, is popechat (%r)' % mon.stdout)
ok([s[0] for s in sets] == order and [s[0] for s in sets if not s[1]] == shown, 'one Also featured set per room; the default set matches the default card')
for s in sets:
    names = re.findall(r'class="hub-also-name">([^<]+)<', s[2])
    i = order.index(s[0])
    ok(names == [order[(i + 1) % N], order[(i + 2) % N]], 'Also featured under %s is the next two rooms %s' % (s[0], names))
if dflt:
    bd = next(epoch + timedelta(days=k) for k in range(-7, 7 * N) if py_pick(epoch + timedelta(days=k))[0] == dflt.group(1))
    ok(B.feat_block(rot, bd.isoformat()) in read('hub', 'src', 'templates', 'index.html'),
       'templates/index.html block is exactly what build_highlights.py --featured writes')
for c in cards:
    photos = bool(src[c[1]].get('heroImages'))
    ok(bool(c[0]) != photos, '%s: %s' % (c[1], 'photo card (no type card)' if photos else 'room-colored type card'))
    if c[0]:
        a, b = c[3], c[4]
        ok(B.contrast(a, '#ffffff') >= 4.5 and B.contrast(b, '#ffffff') >= 4.5 and B.contrast(a, '#ffffff') >= 7.0,
           '%s: white text passes AA on both stops (%.1f:1, %.1f:1), same in light and dark' % (c[1], B.contrast(a, '#ffffff'), B.contrast(b, '#ffffff')))
ok(B.contrast('#0f1419', '#ffffff') >= 7.0, 'type card Open button: #0f1419 on #fff')
ok(len(re.findall(r'<p class="hub-feat-brief">', sec)) == sum(1 for c in cards if c[0]), 'every type card has one Room Brief line')
ok(sec.count('A SubX room · Featured today') == N and 'room · featured<' not in sec, 'every card is labeled "A SubX room · Featured today"')
ok('1d9bf0' not in sec.lower() and not DASH.search(sec), 'no #1D9BF0 and no em or en dash in the hero cards')
ok(not re.search(r'<script\b', sec) and '<img' not in sec, 'no inline script (strict CSP) and no images in the cards (photos stay in hub.js)')
ok(not any(('data-feat="%s"' % r) in sec or ('>%s<' % r) in sec for r in NEVER), 'no excluded room is anywhere in the hero')
ok('id="hub-hero" hidden' not in home and 'class="hero-primary"' in sec and 'id="hub-also-list"' in sec, 'hero is in the page at load (no wait for a fetch)')

# ---- carousel only under the exact featured room ----
for p in (('hub', 'src', 'templates', 'hub.js'), ('hub', 'site', 'hub.js')):
    j = read(*p)
    ok("if (hero && hero.room !== heroId) hero = null;" in j and "if (featPicked && featPicked.room) return featPicked.room;" in j,
       '/'.join(p) + ': photos and highlights follow the shown card only (no fallback room)')
ok(sorted(r for r in order if src[r].get('heroImages')) == ['gpchat', 'popechat'], 'only gpchat and popechat have photos, so a carousel starts only on their days')
core = js[js.find('/* hx-core:start'):js.find('/* hx-core:end */')]
pub = {r['room']: r for r in json.loads(read('hub', 'site', 'rooms.json'))['rooms']}
hv = subprocess.run(['node', '-e', core + '\nvar v=hxValidate(%s);process.stdout.write(JSON.stringify([v.items.map(function(i){return "Photo: "+i.credit+" \\u00b7 "+i.license;}), v.refused.length]));'
                     % json.dumps(pub['popechat']['heroImages'])], capture_output=True, text=True)
hvo = json.loads(hv.stdout) if hv.returncode == 0 else None
ok(hvo == [['Photo: Jebulon \u00b7 CC0', 'Photo: Alvesgaspar \u00b7 CC BY-SA 4.0', 'Photo: David Iliff \u00b7 CC BY-SA 3.0'], 0],
   'hub.js accepts all 3 popechat photos and their credit lines read "Photo: {credit} \u00b7 {license}" (%s %s)' % (hvo, hv.stderr[:200]))

# ---- adapted-photo note on the credit line (2026-11-15): the two BY-SA photos are crops ----
pc_items = pub['popechat']['heroImages']['items']
lines = ['Photo: %s \u00b7 %s%s' % (it['credit'], it['license'], (' \u00b7 ' + it['modified']) if it.get('modified') else '') for it in pc_items]
ok(lines == ['Photo: Jebulon \u00b7 CC0', 'Photo: Alvesgaspar \u00b7 CC BY-SA 4.0 \u00b7 cropped', 'Photo: David Iliff \u00b7 CC BY-SA 3.0 \u00b7 cropped'],
   'credit lines: both CC BY-SA photos end in "cropped", Jebulon CC0 has no suffix (%s)' % lines)
ok([it['licenseUrl'] for it in pc_items] == ['https://creativecommons.org/publicdomain/zero/1.0/', 'https://creativecommons.org/licenses/by-sa/4.0/', 'https://creativecommons.org/licenses/by-sa/3.0/']
   and all(it['sourceUrl'].startswith('https://commons.wikimedia.org/wiki/File:') for it in pc_items), 'popechat license links go to each deed; credits link to the Commons file page')
for p in (('hub', 'src', 'templates', 'hub.js'), ('hub', 'site', 'hub.js')):
    j = read(*p)
    fnm = j[j.find('function hxModified('):j.find('function hxModified(') + 1200]
    ok("hxModified(fig, room.heroImages.items);" in j and "' \\u00b7 ' + m" in fnm and "'hx-mod'" in fnm and 'insertBefore(note, lic.nextSibling)' in fnm,
       '/'.join(p) + ': the "modified" note is drawn right after the license link, following the active slide')
ok(not re.search('\u00a9|all rights reserved', json.dumps(pub['popechat']['heroImages'], ensure_ascii=False), re.I), 'no copyright claim or all rights reserved on the popechat photos')
ok(not re.search(r'endors|official|approved by|holy see|on behalf of', ' '.join(it['alt'] for it in pc_items), re.I), 'popechat alt text names places only, no endorsement wording')

# ---- CI ----
ok('python3 test/hub_featured_rotation.test.py' in read('.github', 'workflows', 'ci.yml'), 'ci.yml runs this test')

print('\n%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)
