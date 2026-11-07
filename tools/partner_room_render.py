#!/usr/bin/env python3
"""Render one partner room prototype from its site.json. CONFIG AND PREVIEW ONLY.

Nothing here is deployed, registered, or written into hub/site. The room name is site.json "displayName"
and every visible use of that name is filled from that field.

  python3 tools/partner_room_render.py --check
  python3 tools/partner_room_render.py --out DIR
"""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ROOM = os.path.join(ROOT, 'rooms', 'dogacademy-partner')
SITE = os.path.join(ROOM, 'site.json')
BRAND = os.path.join(ROOT, 'brand', 'brand.json')
WHOMARK = os.path.join(ROOT, 'hub', 'src', 'whomark', 'config.json')

DASH = re.compile(r'[\u2013\u2014]')
PAYS = re.compile(r'\bpays\b', re.I)
PRICE = re.compile(r'\$')
FORBIDDEN = re.compile(
    r'jebb|j@subx\.it|\(?\b310\)?[-. ]\d{3}[-. ]\d{4}|denver|'
    r'puppies-for-sale|psychiatric|esa-training|legally valid|public access|testimonial',
    re.I)
RAIL_URLS = {
    'https://dogacademy.org/in-person-dog-training/private-training',
    'https://dogacademy.org/in-person-dog-training/group-training',
    'https://dogacademy.org/in-person-dog-training/online-training',
    'https://dogacademy.org/courses/puppy-kindergarten',
    'https://dogacademy.org/courses/how-to-stop-your-dog-from-pulling-1',
    'https://dogacademy.org/courses/minimizing-separation-anxiety',
}
OUTCOME = re.compile(r'minimiz|cure|reduc|heal|legally|universal access', re.I)


class RoomError(Exception):
    pass


def load(path):
    return json.load(open(path, encoding='utf-8'))


def strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)


def esc(s):
    return (s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;'))


def fill(text, name):
    return text.replace('{{displayName}}', name)


def initials(name):
    parts = re.findall(r'[A-Za-z0-9]+', name or '')
    if not parts:
        return '?'
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def validate(site, brand, whomark):
    name = site.get('displayName')
    if not isinstance(name, str) or not name.strip() or name != name.strip():
        raise RoomError('displayName must be a single non-empty line')
    if name.endswith(' room') or 'chat' in name.lower():
        raise RoomError('displayName must be the company name, not a chat-style name or a "room" suffix')
    raw = json.dumps(site, ensure_ascii=False)
    rest = raw.replace(json.dumps(name, ensure_ascii=False), '""', 1)
    if name in rest:
        raise RoomError('displayName is copied somewhere besides that one field')
    for s in strings(site):
        if DASH.search(s):
            raise RoomError('en or em dash in room copy: %r' % s[:80])
        if PAYS.search(s):
            raise RoomError('room copy must not say the brand pays: %r' % s[:80])
        if FORBIDDEN.search(s):
            raise RoomError('forbidden copy in room config: %r' % s[:80])
    if site.get('siteId') != 'dogacademy-partner':
        raise RoomError('siteId must be dogacademy-partner')
    if site.get('domain') != 'TBD':
        raise RoomError('domain must stay TBD until a name clears trademark review')
    if site.get('operator') != brand['legalEntity'] or site.get('takedownEmail') != brand['takedownEmail'] or site.get('contactPhone') != brand['contactPhone']:
        raise RoomError('operator, takedown email, and phone must match brand.json')
    if '3019' in raw or 'Ocean Park' in raw or '90405' in raw:
        raise RoomError('room config must not carry a street address')
    sh = site.get('shell') or {}
    if sh.get('base') != 'v1.2.6' or sh.get('fork') is not False or sh.get('cspRequired') is not True:
        raise RoomError('shell must pin v1.2.6 with fork false and cspRequired true')
    if 'guidelines.html' not in (sh.get('noShell') or []):
        raise RoomError('guidelines.html must be a noShell legal page')
    nests = site.get('nests') or []
    if not (1 <= len(nests) <= 6):
        raise RoomError('explore seats (nests) must be 1 to 6')
    rail = site.get('rail') or {}
    if rail.get('kind') != 'room-brief':
        raise RoomError('rail.kind must be room-brief')
    cards = rail.get('outbound') or []
    if not (1 <= len(cards) <= 6):
        raise RoomError('Room Brief is capped at 6 cards')
    if int(rail.get('maxCards') or 0) > 6 or int(rail.get('maxCards') or 0) < len(cards):
        raise RoomError('rail.maxCards must cover the cards and stay at or under 6')
    urls = []
    for c in cards:
        if c.get('tag') != 'Sponsored':
            raise RoomError('each Room Brief card is labeled Sponsored')
        if PRICE.search(c.get('headline', '') + c.get('snippet', '')):
            raise RoomError('Room Brief cards show no prices')
        if OUTCOME.search(c.get('headline', '') + ' ' + c.get('snippet', '')):
            raise RoomError('Room Brief card makes an outcome or legal claim: %r' % c.get('headline'))
        url = c.get('url') or ''
        if not url.startswith('https://dogacademy.org/'):
            raise RoomError('Room Brief links stay on dogacademy.org')
        urls.append(url)
    if set(urls) != RAIL_URLS or len(urls) != len(set(urls)):
        raise RoomError('Room Brief URLs must be the six ordinary training pages, once each')
    if any('pupp' in u and 'kindergarten' not in u for u in urls):
        raise RoomError('leave puppy sales out of the rail')
    feed = site.get('feed') or []
    kinds = [p.get('kind') for p in feed]
    if 'partner' not in kinds or 'staff' not in kinds:
        raise RoomError('the feed needs a staff post and a partner post')
    for p in feed:
        if p.get('kind') == 'partner' and not p.get('href', '').startswith('https://dogacademy.org/'):
            raise RoomError('a partner post links to the sponsor site')
        if re.search(r'\breviews?\b|\btestimonial', p.get('text') or '', re.I):
            raise RoomError('feed posts are not reviews')
    if '{{displayName}}' not in (site.get('partnerLine') or '') or '{{displayName}}' not in (site.get('staffLabel') or '') or '{{displayName}}' not in (site.get('disclosure') or ''):
        raise RoomError('partner line, staff label, and disclosure must fill from {{displayName}}')
    if not any('diagnos' in g.lower() for g in site.get('guidelines') or []):
        raise RoomError('guidelines must tell members not to post diagnoses')
    ai = (whomark.get('tiers') or {}).get('ai') or {}
    if ai.get('color') != '#000000' or ai.get('textLabel') != 'AI-made' or 'AI steward' not in (ai.get('stewardLabel') or ''):
        raise RoomError('WHOMARK AI label text and #000000 color are unchanged')
    human = (whomark.get('tiers') or {}).get('human') or {}
    if human.get('textLabel') != 'Human-made':
        raise RoomError('WHOMARK human label is unchanged')
    return name


CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0; background: #fff; color: #0f1419;
  font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
a { color: #0f1419; }
.wrap { display: grid; grid-template-columns: minmax(0, 1fr) 320px; grid-template-areas: "head rail" "feed rail"; min-height: 100vh; }
header { grid-area: head; padding: 1.15rem 1.3rem 0.4rem; }
main { grid-area: feed; padding: 0.2rem 1.3rem 2rem; }
.rail { grid-area: rail; padding: 1rem 1rem 2rem; border-left: 1px solid #eff3f4; }
h1 { font-size: 22px; line-height: 1.25; margin: 0 0 0.25rem; }
.tagline { margin: 0; font-size: 15px; color: #536471; }
.disclosure { display: block; margin: 0.55rem 0 0; font-size: 15px; line-height: 1.4; font-weight: 700; color: #536471; }
.partner-line, .contacts { margin: 0.45rem 0 0; font-size: 15px; line-height: 1.45; }
.seats { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.75rem 0 0.2rem; }
.seat { border: 1px solid #cfd9de; border-radius: 999px; padding: 0.22rem 0.7rem; font-size: 15px; background: #fff; }
.rail h2 { font-size: 17px; margin: 0 0 0.45rem; }
.rail-box { background: #eff3f4; border: 1px solid #eff3f4; border-radius: 16px; overflow: hidden; }
.card { display: block; padding: 0.65rem 0.9rem; text-decoration: none; border-bottom: 1px solid #fff; }
.card:hover { background: #e7eced; }
.sponsored-label, .staff-label { display: inline-block; font-size: 15px; font-weight: 700; color: #0f1419; }
.card h3 { font-size: 15px; margin: 0.12rem 0; }
.card p, .post p { margin: 0.15rem 0 0; font-size: 15px; }
.rail-note { margin: 0.45rem 0 0; font-size: 15px; color: #536471; }
.post { display: flex; gap: 0.7rem; padding: 0.75rem 0; border-bottom: 1px solid #eff3f4; }
.avatar { width: 42px; height: 42px; border-radius: 50%; background: #2f3336; color: #e7e9ea;
  display: flex; align-items: center; justify-content: center; font-weight: 700; flex: none; }
.wm { font-size: 15px; font-weight: 700; margin-left: 0.35rem; }
.wm-ai { color: #000000; }
.wm-human { color: #1E7B34; }
.foot { margin-top: 1rem; font-size: 15px; color: #536471; }
.rules { padding: 1.2rem 1.3rem 2rem; max-width: 40rem; }
.rules li { margin: 0.35rem 0; }
@media (max-width: 800px) {
  .wrap { display: block; }
  .rail { border-left: 0; }
}
"""


def render_pages(site, brand, whomark):
    name = validate(site, brand, whomark)
    ai = whomark['tiers']['ai']
    human = whomark['tiers']['human']
    disclosure = fill(site['disclosure'], name)
    staff = fill(site['staffLabel'], name)
    partner_line = fill(site['partnerLine'], name)
    seats = ''.join('<span class="seat">%s</span>' % esc(n['label']) for n in site['nests'])
    cards = []
    for c in site['rail']['outbound']:
        cards.append(
            '<a class="card" href="%s"><span class="sponsored-label">Sponsored</span>'
            '<h3>%s</h3><p>%s</p>'
            '<span class="disclosure">%s</span></a>'
            % (esc(c['url']), esc(c['headline']), esc(c['snippet']), esc(disclosure)))
    posts = []
    for p in site['feed']:
        if p['whomark'] == 'ai':
            mark = '<span class="wm wm-ai">%s</span>' % esc(ai['stewardLabel'])
        else:
            mark = '<span class="wm wm-human">%s</span>' % esc(human['textLabel'])
        if p['kind'] == 'staff':
            who = '<span class="staff-label">%s</span>' % esc(staff)
        elif p['kind'] == 'partner':
            who = '<span class="sponsored-label">Sponsored</span>'
        else:
            who = '<span class="staff-label">AI steward</span>'
        extra = ''
        if p['kind'] == 'partner':
            extra = '<a href="%s">%s</a>' % (esc(p['href']), esc(p['href']))
            extra = '<p>%s</p><span class="disclosure">%s</span>' % (extra, esc(disclosure))
        posts.append(
            '<article class="post"><div class="avatar" aria-hidden="true">%s</div><div>'
            '<div>%s%s</div><p>%s</p>%s</div></article>'
            % (esc(initials(name if p['kind'] != 'steward' else 'AI')), who, mark, esc(p['text']), extra))
    contacts = 'Operated by %s. <a href="mailto:%s">%s</a>. %s.' % (
        esc(site['operator']), esc(site['takedownEmail']), esc(site['takedownEmail']), esc(site['contactPhone']))
    index = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>%s</title>
<meta name="description" content="%s %s">
<meta property="og:title" content="%s">
<meta property="og:description" content="%s">
<style>%s</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>%s</h1>
  <p class="tagline">%s</p>
  <span class="disclosure">%s</span>
  <p class="partner-line">%s</p>
  <p class="contacts">%s</p>
  <div class="seats" aria-label="Explore seats">%s</div>
  <p class="foot"><a href="guidelines.html">Room guidelines</a></p>
</header>
<aside class="rail" aria-label="Room Brief">
  <h2>Room Brief</h2>
  <div class="rail-box">%s</div>
  <p class="rail-note">%s</p>
</aside>
<main>
  <h2>Room</h2>
  %s
</main>
</div>
</body>
</html>
""" % (
        esc(name), esc(site['tagline']), esc(disclosure), esc(name), esc(site['tagline']), CSS,
        esc(name), esc(site['tagline']), esc(disclosure), esc(partner_line), contacts, seats,
        ''.join(cards), esc(site['rail']['footer']), ''.join(posts))
    rules = ''.join('<li>%s</li>' % esc(g) for g in site['guidelines'])
    guidelines = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Guidelines, %s</title>
<meta name="description" content="Room guidelines for %s. Do not post diagnoses.">
<meta property="og:title" content="Guidelines, %s">
<meta property="og:description" content="Room guidelines for %s.">
<style>%s</style>
</head>
<body>
<article class="rules">
  <h1>Guidelines for %s</h1>
  <span class="disclosure">%s</span>
  <ul>%s</ul>
  <p class="contacts">%s</p>
  <p><a href="index.html">Back to %s</a></p>
</article>
</body>
</html>
""" % (esc(name), esc(name), esc(name), esc(name), CSS, esc(name), esc(disclosure), rules, contacts, esc(name))
    llms = """# %s

> %s (%s) is a community room operated by %s.

## Disclosure
- The room says: %s
- Promotional product cards and partner posts are labeled Sponsored.
- Staff posts are labeled %s.
- WHOMARK labels stay %s, %s, and %s. The AI label color is %s.
- WHOMARK labels do not replace the sponsor line on the room or on a partner post.

## Contact
- Operator: %s
- Notices / takedown: %s
- Phone: %s

Domain: TBD. This file is a room prototype. It grants no license to copy content.
""" % (
        name, name, site['tagline'], site['operator'], disclosure, staff,
        human['textLabel'], ai['textLabel'], whomark['tiers']['hybrid']['textLabel'], ai['color'],
        site['operator'], site['takedownEmail'], site['contactPhone'])
    return {'index.html': index, 'guidelines.html': guidelines, 'llms.txt': llms}


def render(site_path=None, out=None, brand_path=None, whomark_path=None):
    site_path = site_path or SITE
    brand = load(brand_path or BRAND)
    whomark = load(whomark_path or WHOMARK)
    site = load(site_path)
    pages = render_pages(site, brand, whomark)
    if out:
        os.makedirs(out, exist_ok=True)
        for rel, text in pages.items():
            with open(os.path.join(out, rel), 'w', encoding='utf-8') as fh:
                fh.write(text)
    return pages


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--out')
    ap.add_argument('--site')
    a = ap.parse_args(argv)
    try:
        pages = render(a.site, None if a.check and not a.out else a.out)
    except RoomError as e:
        print('partner_room_render: %s' % e, file=sys.stderr)
        return 2
    if a.check:
        print('partner_room_render --check: room config ok (%s)' % ', '.join(sorted(pages)))
    elif a.out:
        print('rendered %s' % a.out)
    else:
        print('partner_room_render: pass --out DIR or --check', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
