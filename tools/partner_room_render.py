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
    # Rendered contact lines use brand.json so a brand rename reaches every page.
    # The room file is checked against the real brand in test/partner_rooms.test.py.
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
        if 'minimizing-separation-anxiety' in url:
            shown = (c.get('headline') or '') + ' ' + (c.get('snippet') or '')
            if c.get('headline') != 'Home alone practice' or 'anxiety' in shown.lower():
                raise RoomError('the home alone card stays a neutral title with no anxiety outcome')
        urls.append(url)
    if set(urls) != RAIL_URLS or len(urls) != len(set(urls)):
        raise RoomError('Room Brief URLs must be the six ordinary training pages, once each')
    if any('pupp' in u and 'kindergarten' not in u for u in urls):
        raise RoomError('leave puppy sales out of the rail')
    feed = site.get('feed') or []
    kinds = [p.get('kind') for p in feed]
    if not (8 <= len(feed) <= 10):
        raise RoomError('the feed needs 8 to 10 posts')
    if not {'partner', 'staff', 'example', 'steward'} <= set(kinds):
        raise RoomError('the feed needs staff tips, example questions, a partner post, and an AI steward note')
    seats = {p.get('seat') for p in feed}
    if not {n.get('label') for n in nests} <= seats:
        raise RoomError('every explore seat needs a post')
    for p in feed:
        if p.get('kind') == 'partner' and not p.get('href', '').startswith('https://dogacademy.org/'):
            raise RoomError('a partner post links to the sponsor site')
        if p.get('kind') == 'example' and not str(p.get('text') or '').startswith('Example question'):
            raise RoomError('example posts must be marked as examples')
        if re.search(r'\breviews?\b|\btestimonial', p.get('text') or '', re.I):
            raise RoomError('feed posts are not reviews')
    if 'Operated by' in fill(site.get('partnerLine') or '', name):
        raise RoomError('partner line must not repeat the operator line')
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


ROOM_PATH = '/partners/dogacademy/'
ARTICLES = os.path.join(ROOM, 'articles.json')
ARTICLE_DIR = 'partners/dogacademy/articles'
CLAIM = re.compile(r'\b(cure|cures|guarantee|guaranteed|testimonial)\b|\$|\bpays\b', re.I)


def load_articles(path=None):
    path = path or ARTICLES
    data = load(path)
    arts = data.get('articles') or []
    if not (5 <= len(arts) <= 6):
        raise RoomError('the room needs 5 or 6 articles')
    slugs = []
    for a in arts:
        slug = a.get('slug') or ''
        if not re.fullmatch(r'[a-z0-9-]{1,60}', slug):
            raise RoomError('article slug is not a plain path piece')
        slugs.append(slug)
        words = len(' '.join(a.get('paragraphs') or []).split())
        if not (300 <= words <= 500):
            raise RoomError('article %s is %d words; keep the body between 300 and 500' % (slug, words))
        blob = json.dumps(a, ensure_ascii=False)
        if DASH.search(blob) or CLAIM.search(blob):
            raise RoomError('article %s has a dash or a banned claim' % slug)
        if 'qualified trainer' not in blob or 'veterinarian' not in blob:
            raise RoomError('article %s must point aggression or health worries to a trainer or a vet' % slug)
    if len(set(slugs)) != len(slugs):
        raise RoomError('article slugs must be unique')
    # The room name is filled at render time. Article source must not repeat it.
    # Caller passes the current displayName when it knows it.
    if not str(data.get('sourceUrl') or '').startswith('https://www.cesarmillan.com/'):
        raise RoomError('article source must be a public page on his official site')
    for key in ('attribution', 'nonAffiliation', 'sourceLabel'):
        if not str(data.get(key) or '').strip():
            raise RoomError('articles.json is missing %s' % key)
    if 'Not affiliated' not in data['nonAffiliation'] or 'endorsed' not in data['nonAffiliation']:
        raise RoomError('articles need the not affiliated line')
    return data


def article_rel(slug):
    return '%s/%s.html' % (ARTICLE_DIR, slug)


def room_page_rels():
    data = load_articles()
    return ['partners/dogacademy/index.html'] + [article_rel(a['slug']) for a in data['articles']]


def fragments(site, brand, whomark):
    """Escaped room pieces. The visible name always comes from displayName."""
    name = validate(site, brand, whomark)
    ai = whomark['tiers']['ai']
    human = whomark['tiers']['human']
    disclosure = fill(site['disclosure'], name)
    staff = fill(site['staffLabel'], name)
    partner_line = fill(site['partnerLine'], name)
    cards = []
    for c in site['rail']['outbound']:
        cards.append(
            '<a class="news-item" href="%s"><div class="sponsored-label">Sponsored</div>'
            '<div class="news-item-headline">%s</div><div class="news-item-snippet">%s</div>'
            '<div class="partner-disclosure">%s</div></a>'
            % (esc(c['url']), esc(c['headline']), esc(c['snippet']), esc(disclosure)))
    posts = []
    first_seat = {}
    for i, p in enumerate(site['feed']):
        if p.get('seat') and p['seat'] not in first_seat:
            first_seat[p['seat']] = 'post-%d' % (i + 1)
    for i, p in enumerate(site['feed']):
        if p.get('whomark') == 'ai':
            mark = '<span class="wm wm-ai">%s</span>' % esc(ai['stewardLabel'])
            who_initials = 'AI'
        else:
            mark = '<span class="wm wm-human">%s</span>' % esc(human['textLabel'])
            who_initials = initials(name)
        if p['kind'] == 'staff':
            who = '<span class="staff-label">%s</span>' % esc(staff)
        elif p['kind'] == 'partner':
            who = '<span class="sponsored-label">Sponsored</span>'
        elif p['kind'] == 'example':
            who = '<span class="example-label">Example</span>'
        else:
            who = '<span class="staff-label">AI steward</span>'
        seat = ('<span class="seat-pill">%s</span>' % esc(p['seat'])) if p.get('seat') else ''
        extra = ''
        if p['kind'] == 'partner':
            extra = '<p><a href="%s">%s</a></p><span class="partner-disclosure">%s</span>' % (
                esc(p['href']), esc(p['href']), esc(disclosure))
        posts.append(
            '<article class="post" id="post-%d"><div class="post-avatar" style="background:#2f3336" aria-hidden="true">%s</div>'
            '<div class="post-body"><div class="post-meta">%s%s%s</div><p class="post-text">%s</p>%s</div></article>'
            % (i + 1, who_initials, who, mark, seat, esc(p['text']), extra))
    seats = ''.join(
        '<a class="room-seat" href="#%s">%s</a>' % (first_seat.get(n['label'], 'room-feed'), esc(n['label']))
        for n in site['nests'])
    pack = load_articles()
    if name in json.dumps(pack, ensure_ascii=False):
        raise RoomError('articles must not hardcode the room name')
    article_bits = []
    feed_bits = []
    for a in pack['articles']:
        href = '/' + article_rel(a['slug'])
        article_bits.append(
            '<a class="news-item" href="%s"><div class="staff-label">%s</div>'
            '<div class="news-item-headline">%s</div><div class="news-item-snippet">%s</div></a>'
            % (esc(href), esc(staff), esc(a['title']), esc(a['dek'])))
        feed_bits.append(
            '<article class="post"><div class="post-avatar" style="background:#2f3336" aria-hidden="true">%s</div>'
            '<div class="post-body"><div class="post-meta"><span class="staff-label">%s</span>'
            '<span class="wm wm-human">%s</span></div>'
            '<p class="post-text"><a href="%s">%s</a></p><p class="post-text">%s</p>'
            '<span class="partner-disclosure">%s</span></div></article>'
            % (esc(initials(name)), esc(staff), esc(human['textLabel']), esc(href), esc(a['title']), esc(a['dek']), esc(disclosure)))
    rules = ''.join('<li>%s</li>' % esc(g) for g in site['guidelines'])
    contacts = 'Operated by %s. <a href="mailto:%s">%s</a>. %s.' % (
        esc(brand['legalEntity']), esc(brand['takedownEmail']), esc(brand['takedownEmail']), esc(brand['contactPhone']))
    return {
        'name': name,
        'disclosure': disclosure,
        'staff': staff,
        'partner_line': partner_line,
        'seats': seats,
        'cards': ''.join(cards),
        'posts': ''.join(feed_bits) + ''.join(posts),
        'article_section': ''.join(article_bits),
        'rules': rules,
        'article_pack': pack,
        'contacts': contacts,
        'initials': initials(name),
        'tagline': site['tagline'],
        'rail_footer': site['rail']['footer'],
        'ai_label': ai['stewardLabel'],
        'ai_text': ai['textLabel'],
        'ai_color': ai['color'],
        'human_label': human['textLabel'],
        'hybrid_label': whomark['tiers']['hybrid']['textLabel'],
        'operator': brand['legalEntity'],
        'email': brand['takedownEmail'],
        'phone': brand['contactPhone'],
    }


def body_html(fr):
    """X-style room shell: left nav, banner and avatar, centered feed, right rail. No empty band above the feed."""
    e = esc
    return '''<button class="hamburger" id="hamburger" aria-label="Open navigation" aria-controls="sidebar" aria-expanded="false"><span></span><span></span><span></span></button>
<aside class="sidebar" id="sidebar">
  <div class="sidebar-brand">
    <a href="%s" class="brand-mark" aria-label="%s home"><span class="room-nav-avatar" aria-hidden="true">%s</span></a>
    <div class="brand-title">%s</div>
    <div class="brand-sub">%s</div>
  </div>
  <nav aria-label="Room">
    <ul>
      <li><a class="nav-social-link active" href="%s">Home</a></li>
      <li><a class="nav-social-link" href="%s#seats">Explore</a></li>
      <li><a class="nav-social-link" href="%s#articles">Articles</a></li>
      <li><a class="nav-social-link" href="%s#guidelines">Guidelines</a></li>
      <li><a class="nav-social-link" href="/">Hub</a></li>
    </ul>
    <button type="button" class="hub-theme-toggle" id="hub-theme-toggle" aria-pressed="false">Lights out</button>
    <div class="nav-legal"><a href="/terms.html">Terms</a> <a href="/privacy.html">Privacy</a> <a href="/report.html">Report</a> <a href="/about.html">About</a></div>
  </nav>
</aside>
<main class="main">
  <div class="room-banner" role="img" aria-label="Room banner"></div>
  <div class="room-id">
    <div class="room-avatar" aria-hidden="true">%s</div>
    <div>
      <h1>%s</h1>
      <p class="room-tagline">%s</p>
    </div>
  </div>
  <div class="room-meta">
    <span class="partner-disclosure">%s</span>
    <p class="partner-line">%s</p>
    <p class="contacts">%s</p>
  </div>
  <div class="room-seats" id="seats">%s</div>
  <section class="room-articles" id="articles">
    <h2>Articles</h2>
    <div class="right-panel-body article-list">%s</div>
  </section>
  <div class="room-feed" id="room-feed">%s</div>
  <section class="room-guidelines" id="guidelines">
    <h2>Room guidelines</h2>
    <ul>%s</ul>
  </section>
</main>
<aside class="right-panel" id="right-panel" aria-label="Room Brief">
  <div class="right-panel-header">
    <div class="right-panel-kicker">In the room</div>
    <div class="right-panel-title">Room Brief</div>
  </div>
  <div class="right-panel-body" id="room-rail">%s</div>
  <div class="right-panel-footer"><p>%s</p></div>
</aside>''' % (
        ROOM_PATH, e(fr['name']), e(fr['initials']), e(fr['name']), e(fr['tagline']),
        ROOM_PATH, ROOM_PATH, ROOM_PATH,
        ROOM_PATH, e(fr['initials']), e(fr['name']), e(fr['tagline']),
        e(fr['disclosure']), e(fr['partner_line']), fr['contacts'],
        fr['seats'], fr['article_section'], fr['posts'], fr['rules'], fr['cards'], e(fr['rail_footer']))


def article_html(fr, article):
    """Same shell as the room home, with one article in the center column."""
    e = esc
    pack = fr['article_pack']
    paras = ''.join('<p>%s</p>' % e(p) for p in article['paragraphs'])
    href = '/' + article_rel(article['slug'])
    others = ''.join(
        '<a class="news-item" href="/%s"><div class="news-item-headline">%s</div></a>'
        % (article_rel(a['slug']), e(a['title'])) for a in pack['articles'])
    credit = (
        '<p class="article-byline"><span class="staff-label">%s</span> <span class="wm wm-human">%s</span></p>'
        '<p class="partner-disclosure">%s</p>'
        '<p class="article-credit">%s</p>'
        '<p><a href="%s" rel="noopener">%s</a></p>'
        '<p class="article-credit">%s</p>'
        % (e(fr['staff']), e(fr['human_label']), e(fr['disclosure']),
           e(pack['attribution']), e(pack['sourceUrl']), e(pack['sourceLabel']), e(pack['nonAffiliation'])))
    main = '''<div class="room-banner" role="img" aria-label="Room banner"></div>
  <div class="room-id">
    <div class="room-avatar" aria-hidden="true">%s</div>
    <div><p class="room-tagline"><a href="%s">%s</a></p><h1>%s</h1></div>
  </div>
  <article class="article-body">%s%s</article>''' % (
        e(fr['initials']), ROOM_PATH, e(fr['name']), e(article['title']), credit, paras)
    # Reuse the home shell's nav by swapping the main and rail of a fresh home and... build directly.
    home = body_html(fr)
    start = home.find('<main class="main">')
    end = home.find('</main>')
    page = home[:start] + '<main class="main">\n  ' + main + '\n</main>' + home[end + len('</main>'):]
    page = re.sub(
        r'(<div class="right-panel-body" id="room-rail">).*?(</div>\s*<div class="right-panel-footer">)',
        lambda m: m.group(1) + others + m.group(2),
        page, count=1, flags=re.S)
    page = page.replace('<div class="right-panel-title">Room Brief</div>', '<div class="right-panel-title">Articles</div>', 1)
    page = page.replace('Room Brief links open the sponsor site. Not a news ingest.', 'More from this room.', 1)
    page = page.replace('nav-social-link active', 'nav-social-link', 1)
    return page


def render_pages(site, brand, whomark):
    fr = fragments(site, brand, whomark)
    name = fr['name']
    body = body_html(fr)
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
<link rel="stylesheet" href="/styles.css">
<link rel="stylesheet" href="/nests.css">
<link rel="stylesheet" href="/hub.css">
<style>.wm-ai { color: #000000; }</style>
</head>
<body class="partner-room-home">
%s
</body>
</html>
""" % (esc(name), esc(fr['tagline']), esc(fr['disclosure']), esc(name), esc(fr['tagline']), body)
    guidelines = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="robots" content="noindex,nofollow">
<title>Guidelines, %s</title>
</head>
<body class="partner-room-home">
<h1>Guidelines for %s</h1>
<span class="partner-disclosure">%s</span>
<ul>%s</ul>
<p class="contacts">%s</p>
<p><a href="index.html">Back to %s</a></p>
</body>
</html>
""" % (esc(name), esc(name), esc(fr['disclosure']), fr['rules'], fr['contacts'], esc(name))
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
        name, name, fr['tagline'], fr['operator'], fr['disclosure'], fr['staff'],
        fr['human_label'], fr['ai_text'], fr['hybrid_label'], fr['ai_color'],
        fr['operator'], fr['email'], fr['phone'])
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
