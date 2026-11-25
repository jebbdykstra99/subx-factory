#!/usr/bin/env python3
"""Unit tests for tools/room_static_check.py. Fixtures live in a temp dir only."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import room_static_check as RSC  # noqa: E402

fails = []


def ok(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        fails.append(msg)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def site_json(**over):
    data = {
        'siteId': 'testroom',
        'name': 'testroom',
        'tagline': 'A test room. Local, not brochure.',
        'minAge': 18,
        'accountsOpen': True,
        'stories': {'enabled': False},
        'features': {},
        'pixel': False,
        'redditCrosspost': False,
    }
    data.update(over)
    return data


def page(title, body, *, noindex=False, banner=None):
    robots = '  <meta name="robots" content="noindex, nofollow">\n' if noindex else ''
    ban = ''
    if banner is not None:
        ban = '  <div class="preview-banner" role="status">%s</div>\n' % banner
    return (
        '<!DOCTYPE html>\n<html lang="en"><head>\n'
        '  <meta charset="utf-8">\n'
        '  <title>%s</title>\n'
        '%s'
        '  <link rel="icon" href="favicon.svg">\n'
        '</head><body>\n'
        '%s'
        '  %s\n'
        '  <a href="terms.html">Terms</a>\n'
        '  <a href="privacy.html">Privacy</a>\n'
        '  <a href="report.html">Report</a>\n'
        '  <a href="about.html">About</a>\n'
        '  <a href="guidelines.html">Guidelines</a>\n'
        '</body></html>\n'
    ) % (title, robots, ban, body)


def write_good_room(root: str, *, factory_js: bytes | None = None, extra_html: dict | None = None,
                    sitemap_pages=None, robots=None, site_over=None, lock_files=None,
                    include_404=True, include_report=True) -> str:
    room = os.path.join(root, 'room')
    os.makedirs(room, exist_ok=True)
    pages = {
        'index.html': page('testroom', '<p>Home.</p>', banner='Beta: early and a bit unfinished. Not a brochure.'),
        'about.html': page('About', '<p>About this room. Hawaiʻi is spelled with an ʻokina.</p>',
                           banner='Beta: early and a bit unfinished. Not a brochure.'),
        'terms.html': page('Terms', '<p>Terms of Service.</p>'),
        'privacy.html': page('Privacy', '<p>Privacy Policy.</p>'),
        'guidelines.html': page('Guidelines', '<p>Guidelines.</p>'),
    }
    if include_404:
        pages['404.html'] = page('Not found', '<p>Not found.</p>', noindex=True)
    if include_report:
        pages['report.html'] = page('Report', '<p>Report a problem.</p>', noindex=True)
    if extra_html:
        pages.update(extra_html)
    for name, html in pages.items():
        with open(os.path.join(room, name), 'w', encoding='utf-8') as f:
            f.write(html)
    indexable = [n for n in pages if n not in ('404.html', 'report.html')]
    if sitemap_pages is None:
        sitemap_pages = indexable
    locs = []
    for n in sitemap_pages:
        if n == 'index.html':
            locs.append('https://testroom.example/')
        else:
            locs.append('https://testroom.example/%s' % n)
    sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for loc in locs:
        sm += '  <url><loc>%s</loc></url>\n' % loc
    sm += '</urlset>\n'
    with open(os.path.join(room, 'sitemap.xml'), 'w', encoding='utf-8') as f:
        f.write(sm)
    robots_txt = robots or (
        'User-agent: *\nAllow: /\nDisallow: /preview-lift/\n\n'
        'User-agent: GPTBot\nDisallow: /\n'
    )
    with open(os.path.join(room, 'robots.txt'), 'w', encoding='utf-8') as f:
        f.write(robots_txt)
    with open(os.path.join(room, 'site.json'), 'w', encoding='utf-8') as f:
        json.dump(site_json(**(site_over or {})), f, indent=2)
        f.write('\n')
    with open(os.path.join(room, 'CNAME'), 'w', encoding='utf-8') as f:
        f.write('testroom.example\n')
    with open(os.path.join(room, 'favicon.svg'), 'w', encoding='utf-8') as f:
        f.write('<svg xmlns="http://www.w3.org/2000/svg"></svg>\n')
    with open(os.path.join(room, 'llms.txt'), 'w', encoding='utf-8') as f:
        f.write('# testroom\n\n> A test room. Public beta, open to search indexing.\n')
    blob = factory_js if factory_js is not None else b'/* test factory.js */\n'
    with open(os.path.join(room, 'factory.js'), 'wb') as f:
        f.write(blob)
    files = {'factory.js': sha256_bytes(blob)}
    if lock_files:
        files.update(lock_files)
    lock = {
        'factory': 'jebbdykstra99/subx-factory',
        'version': 'v1.2.10',
        'room': 'testroom',
        'siteId': 'testroom',
        'files': files,
    }
    with open(os.path.join(room, 'FACTORY.lock'), 'w', encoding='utf-8') as f:
        json.dump(lock, f, indent=2)
        f.write('\n')
    return room


def run(room, **kw):
    kwargs = dict(expect_indexable=True, fail_on_stale=False, core_budget_bytes=255000, print_report=False)
    kwargs.update(kw)
    return RSC.run_check(room, ROOT, **kwargs)


def codes(findings, level=None):
    return [(f.level, f.code, f.msg) for f in findings if level is None or f.level == level]


def has_error(findings, code, substr=None):
    for f in findings:
        if f.level == 'error' and f.code == code and (substr is None or substr in f.msg):
            return True
    return False


def has_stale(findings, substr=None):
    for f in findings:
        if f.level == 'stale' and (substr is None or substr in f.msg):
            return True
    return False


td = tempfile.mkdtemp(prefix='room-static-check-')
try:
    # ---- good room ----
    room = write_good_room(td)
    rc, findings = run(room)
    errors = [f for f in findings if f.level == 'error']
    ok(rc == 0, 'good room exits 0 (got %s)' % rc)
    ok(not errors, 'good room has no errors: %s' % errors)
    ok(has_stale(findings, 'factory.js lock does not match'),
       'good room (tiny factory.js) is STALE vs this factory release')

    # Hawaiian okina in about.html must not trip the dash check
    ok(not has_error(findings, 'copy'), 'Hawaiian okina is not flagged as a dash')

    # STALE becomes a failure only when requested
    rc_s, findings_s = run(room, fail_on_stale=True)
    ok(rc_s == 1, 'fail_on_stale true exits 1 on STALE (got %s)' % rc_s)

    # ---- dash ----
    ddir = os.path.join(td, 'dash')
    shutil.copytree(room, ddir)
    about = os.path.join(ddir, 'about.html')
    with open(about, encoding='utf-8') as f:
        txt = f.read()
    with open(about, 'w', encoding='utf-8') as f:
        f.write(txt.replace('About this room.', 'About this room\u2014more.'))
    rc, findings = run(ddir)
    ok(rc == 1 and has_error(findings, 'copy', 'en or em dash'),
       'em dash in about.html fails the copy check')

    # entity dash
    edir = os.path.join(td, 'entity-dash')
    shutil.copytree(room, edir)
    about = os.path.join(edir, 'about.html')
    with open(about, encoding='utf-8') as f:
        txt = f.read()
    with open(about, 'w', encoding='utf-8') as f:
        f.write(txt.replace('About this room.', 'About this room&mdash;more.'))
    rc, findings = run(edir)
    ok(rc == 1 and has_error(findings, 'copy', 'en or em dash'),
       'mdash entity in about.html fails the copy check')

    # ---- Grok ----
    gdir = os.path.join(td, 'grok')
    shutil.copytree(room, gdir)
    about = os.path.join(gdir, 'about.html')
    with open(about, encoding='utf-8') as f:
        txt = f.read()
    with open(about, 'w', encoding='utf-8') as f:
        f.write(txt.replace('About this room.', 'About this room. Grok is not allowed.'))
    rc, findings = run(gdir)
    ok(rc == 1 and has_error(findings, 'copy', 'Grok'),
       'word Grok in about.html fails the copy check')

    # ---- PII via canary hashes (no real contacts in this file) ----
    saved_email = set(RSC.PRIVATE_EMAIL_HASHES)
    saved_phone = set(RSC.PRIVATE_PHONE_HASHES)
    canary_email = 'canary@example.invalid'
    canary_phone = '9995550100'
    RSC.PRIVATE_EMAIL_HASHES = set(saved_email) | {RSC.sha256_text(canary_email)}
    RSC.PRIVATE_PHONE_HASHES = set(saved_phone) | {RSC.sha256_text(canary_phone)}
    try:
        pdir = os.path.join(td, 'pii-email')
        shutil.copytree(room, pdir)
        with open(os.path.join(pdir, 'about.html'), encoding='utf-8') as f:
            txt = f.read()
        with open(os.path.join(pdir, 'about.html'), 'w', encoding='utf-8') as f:
            f.write(txt.replace('About this room.', 'Contact %s please.' % canary_email))
        rc, findings = run(pdir)
        ok(rc == 1 and has_error(findings, 'pii', 'private email'),
           'canary email is reported as private email (value not required in the message)')
        ok(all(canary_email not in f.msg for f in findings),
           'PII finding does not include the email value')

        pdir2 = os.path.join(td, 'pii-phone')
        shutil.copytree(room, pdir2)
        with open(os.path.join(pdir2, 'llms.txt'), 'a', encoding='utf-8') as f:
            f.write('call 999-555-0100\n')
        rc, findings = run(pdir2)
        ok(rc == 1 and has_error(findings, 'pii', 'private phone'),
           'canary phone is reported as private phone')

        pdir3 = os.path.join(td, 'pii-denver')
        shutil.copytree(room, pdir3)
        with open(os.path.join(pdir3, 'about.html'), encoding='utf-8') as f:
            txt = f.read()
        with open(os.path.join(pdir3, 'about.html'), 'w', encoding='utf-8') as f:
            f.write(txt.replace('About this room.', 'Mailed from Denver, CO 80202.'))
        rc, findings = run(pdir3)
        ok(rc == 1 and has_error(findings, 'pii', 'Denver address pattern'),
           'Denver, CO ZIP pattern fails the PII check')
    finally:
        RSC.PRIVATE_EMAIL_HASHES = saved_email
        RSC.PRIVATE_PHONE_HASHES = saved_phone

    # ---- missing sitemap entry ----
    sdir = os.path.join(td, 'sitemap')
    room2 = write_good_room(sdir, extra_html={'maui.html': page('Maui', '<p>Maui page.</p>')},
                            sitemap_pages=['index.html', 'about.html', 'terms.html', 'privacy.html', 'guidelines.html'])
    rc, findings = run(room2)
    ok(rc == 1 and has_error(findings, 'sitemap', 'maui.html'),
       'indexable maui.html missing from sitemap.xml fails')

    # ---- noindex mismatch ----
    ndir = os.path.join(td, 'noindex')
    shutil.copytree(room, ndir)
    about = os.path.join(ndir, 'about.html')
    with open(about, encoding='utf-8') as f:
        txt = f.read()
    with open(about, 'w', encoding='utf-8') as f:
        f.write(txt.replace('<title>About</title>', '<meta name="robots" content="noindex, nofollow">\n  <title>About</title>'))
    rc, findings = run(ndir)
    ok(rc == 1 and has_error(findings, 'noindex', 'about.html'),
       'noindex on about.html fails for a lifted room')

    # 404 without noindex
    n4 = os.path.join(td, 'noindex-404')
    shutil.copytree(room, n4)
    p404 = os.path.join(n4, '404.html')
    with open(p404, encoding='utf-8') as f:
        txt = f.read()
    with open(p404, 'w', encoding='utf-8') as f:
        f.write(txt.replace('  <meta name="robots" content="noindex, nofollow">\n', ''))
    rc, findings = run(n4)
    ok(rc == 1 and has_error(findings, 'noindex', '404.html must keep noindex'),
       '404.html without noindex fails for a lifted room')

    # ---- leftover Preview copy / Preview only banner ----
    bdir = os.path.join(td, 'banner')
    shutil.copytree(room, bdir)
    index = os.path.join(bdir, 'index.html')
    with open(index, encoding='utf-8') as f:
        txt = f.read()
    with open(index, 'w', encoding='utf-8') as f:
        f.write(txt.replace('Beta: early and a bit unfinished. Not a brochure.', 'Preview only.'))
    rc, findings = run(bdir)
    ok(rc == 1 and has_error(findings, 'banner', 'Preview only'),
       'Preview only banner fails')

    # ---- over-budget factory.js ----
    bud = os.path.join(td, 'budget')
    blob = b'x' * 120
    room_b = write_good_room(bud, factory_js=blob)
    rc, findings = run(room_b, core_budget_bytes=100)
    ok(rc == 1 and has_error(findings, 'budget'),
       'factory.js over a 100 B budget fails')

    # under budget passes the budget check (STALE still a warning)
    rc, findings = run(room_b, core_budget_bytes=1000)
    ok(rc == 0 and not has_error(findings, 'budget'),
       'factory.js under a 1000 B budget does not fail the budget check')

    # ---- schema: redditCrosspost true ----
    rdir = os.path.join(td, 'reddit')
    room_r = write_good_room(rdir, site_over={'redditCrosspost': True})
    rc, findings = run(room_r)
    ok(rc == 1 and has_error(findings, 'site.json', 'redditCrosspost'),
       'redditCrosspost true fails the schema')

    # minAge 17
    adir = os.path.join(td, 'age')
    room_a = write_good_room(adir, site_over={'minAge': 17})
    rc, findings = run(room_a)
    ok(rc == 1 and has_error(findings, 'site.json', 'minAge'),
       'minAge 17 fails the schema')

    # ---- lock drift ----
    ldir = os.path.join(td, 'lock')
    shutil.copytree(room, ldir)
    with open(os.path.join(ldir, 'factory.js'), 'ab') as f:
        f.write(b'\n/* edited */\n')
    rc, findings = run(ldir)
    ok(rc == 1 and has_error(findings, 'lock', 'local DRIFT'),
       'edited factory.js that no longer matches FACTORY.lock fails as local DRIFT')

    # ---- broken internal link ----
    kdir = os.path.join(td, 'broken')
    shutil.copytree(room, kdir)
    with open(os.path.join(kdir, 'about.html'), encoding='utf-8') as f:
        txt = f.read()
    with open(os.path.join(kdir, 'about.html'), 'w', encoding='utf-8') as f:
        f.write(txt.replace('<a href="terms.html">Terms</a>', '<a href="missing-page.html">Terms</a>'))
    rc, findings = run(kdir)
    ok(rc == 1 and has_error(findings, 'links', 'missing-page.html'),
       'broken internal link fails')

    # pretty URL /about resolves to about.html (via same-host canonical)
    pdir = os.path.join(td, 'pretty')
    shutil.copytree(room, pdir)
    with open(os.path.join(pdir, 'index.html'), encoding='utf-8') as f:
        txt = f.read()
    with open(os.path.join(pdir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(txt.replace('<a href="about.html">About</a>', '<a href="https://testroom.example/about">About</a>'))
    rc, findings = run(pdir)
    ok(rc == 0 and not has_error(findings, 'links'),
       'same-host pretty URL /about resolves to about.html')

    # ---- robots blanket disallow ----
    rob = os.path.join(td, 'robots')
    room_rob = write_good_room(rob, robots='User-agent: *\nDisallow: /\n')
    rc, findings = run(room_rob)
    ok(rc == 1 and has_error(findings, 'robots', 'blanket-Disallow'),
       'robots.txt blanket Disallow: / fails for a lifted room')

    # preview rooms skip sitemap/robots/noindex lifted rules
    rc, findings = run(room_rob, expect_indexable=False)
    ok(rc == 0 or not has_error(findings, 'robots'),
       'expect_indexable false does not fail a preview robots Disallow: /')

    # ---- N1: wrong-host sitemap loc does not join the host set or count as coverage ----
    n1 = os.path.join(td, 'sitemap-wrong-host')
    room_n1 = write_good_room(
        n1,
        extra_html={'oahu.html': page('Oahu', '<p>Oahu page.</p>')},
        sitemap_pages=['index.html', 'about.html', 'terms.html', 'privacy.html', 'guidelines.html'],
    )
    with open(os.path.join(room_n1, 'sitemap.xml'), 'w', encoding='utf-8') as f:
        f.write(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            '  <url><loc>https://testroom.example/</loc></url>\n'
            '  <url><loc>https://testroom.example/about.html</loc></url>\n'
            '  <url><loc>https://testroom.example/terms.html</loc></url>\n'
            '  <url><loc>https://testroom.example/privacy.html</loc></url>\n'
            '  <url><loc>https://testroom.example/guidelines.html</loc></url>\n'
            '  <url><loc>https://evil.example/oahu</loc></url>\n'
            '</urlset>\n'
        )
    rc, findings = run(room_n1)
    ok(has_error(findings, 'sitemap', 'not this room') and has_error(findings, 'sitemap', 'oahu.html'),
       'wrong-host sitemap loc fails and does not count as coverage for oahu.html')

    # ---- N6: pretty sitemap /oahu covers oahu.html ----
    n6 = os.path.join(td, 'sitemap-pretty')
    room_n6 = write_good_room(
        n6,
        extra_html={'oahu.html': page('Oahu', '<p>Oahu page.</p>')},
        sitemap_pages=['index.html', 'about.html', 'terms.html', 'privacy.html', 'guidelines.html'],
    )
    with open(os.path.join(room_n6, 'sitemap.xml'), 'w', encoding='utf-8') as f:
        f.write(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            '  <url><loc>https://testroom.example/</loc></url>\n'
            '  <url><loc>https://testroom.example/about.html</loc></url>\n'
            '  <url><loc>https://testroom.example/terms.html</loc></url>\n'
            '  <url><loc>https://testroom.example/privacy.html</loc></url>\n'
            '  <url><loc>https://testroom.example/guidelines.html</loc></url>\n'
            '  <url><loc>https://testroom.example/oahu</loc></url>\n'
            '</urlset>\n'
        )
    rc, findings = run(room_n6)
    ok(rc == 0 and not has_error(findings, 'sitemap'),
       'pretty sitemap path /oahu is normalized to oahu.html for coverage')

    # ---- Aegis N1 / Juno N2: start-only operator mailbox ----
    op_email = 'j' + '@' + 'subx.it'
    st_ok = os.path.join(td, 'start-ok')
    shutil.copytree(room, st_ok)
    start_html = page('Start', '<p>Contact the operator at %s.</p>' % op_email)
    with open(os.path.join(st_ok, 'start.html'), 'w', encoding='utf-8') as f:
        f.write(start_html)
    with open(os.path.join(st_ok, 'sitemap.xml'), encoding='utf-8') as f:
        sm = f.read()
    with open(os.path.join(st_ok, 'sitemap.xml'), 'w', encoding='utf-8') as f:
        f.write(sm.replace('</urlset>', '  <url><loc>https://testroom.example/start.html</loc></url>\n</urlset>'))
    rc, findings = run(st_ok)
    ok(rc == 0 and not has_error(findings, 'pii'),
       'operator email on start.html is allowed')
    ok(all(op_email not in f.msg for f in findings),
       'start-page finding messages do not include the operator email value')

    st_bad = os.path.join(td, 'start-elsewhere')
    shutil.copytree(room, st_bad)
    with open(os.path.join(st_bad, 'about.html'), encoding='utf-8') as f:
        txt = f.read()
    with open(os.path.join(st_bad, 'about.html'), 'w', encoding='utf-8') as f:
        f.write(txt.replace('About this room.', 'Contact %s please.' % op_email))
    rc, findings = run(st_bad)
    ok(rc == 1 and has_error(findings, 'pii', 'only allowed on /start'),
       'operator email outside start.html fails')
    ok(all(op_email not in f.msg for f in findings),
       'off-start PII finding does not include the operator email value')

    # ---- Aegis N3: reject symlinks and paths that escape the room ----
    outside = os.path.join(td, 'outside-secret.html')
    with open(outside, 'w', encoding='utf-8') as f:
        f.write('<!DOCTYPE html><html><body>secret \u2014 dash</body></html>\n')
    syn = os.path.join(td, 'symlink')
    shutil.copytree(room, syn)
    os.symlink(outside, os.path.join(syn, 'leaked.html'))
    rc, findings = run(syn)
    ok(has_error(findings, 'path', 'symlink rejected'),
       'a file symlink in the room is rejected')
    ok(not has_error(findings, 'copy'),
       'symlink target contents are not scanned as public copy')

    esc = os.path.join(td, 'href-escape')
    shutil.copytree(room, esc)
    with open(os.path.join(esc, 'about.html'), encoding='utf-8') as f:
        txt = f.read()
    with open(os.path.join(esc, 'about.html'), 'w', encoding='utf-8') as f:
        f.write(txt.replace('<a href="terms.html">Terms</a>', '<a href="../outside-secret.html">Terms</a>'))
    rc, findings = run(esc)
    ok(rc == 1 and has_error(findings, 'path', 'escapes the room root'),
       'href that climbs out of the room root fails')

    lck = os.path.join(td, 'lock-escape')
    shutil.copytree(room, lck)
    with open(os.path.join(lck, 'FACTORY.lock'), encoding='utf-8') as f:
        lock = json.load(f)
    lock['files']['../outside-secret.html'] = '0' * 64
    with open(os.path.join(lck, 'FACTORY.lock'), 'w', encoding='utf-8') as f:
        json.dump(lock, f)
        f.write('\n')
    rc, findings = run(lck)
    ok(rc == 1 and has_error(findings, 'path', 'FACTORY.lock path escapes'),
       'FACTORY.lock path with .. is rejected')

    # ---- Juno N4: nested HTML is checked ----
    nest = os.path.join(td, 'nested')
    shutil.copytree(room, nest)
    os.makedirs(os.path.join(nest, 'stories'), exist_ok=True)
    with open(os.path.join(nest, 'stories', 'talk.html'), 'w', encoding='utf-8') as f:
        f.write(page('Talk', '<p>Nested talk.</p>'))
    rc, findings = run(nest)
    ok(rc == 1 and has_error(findings, 'sitemap', 'stories/talk.html'),
       'nested indexable stories/talk.html is required in the sitemap')

    # ---- Juno N7: decimal dash entities, wrapped banner, empty Disallow ----
    ent = os.path.join(td, 'entity-8210')
    shutil.copytree(room, ent)
    with open(os.path.join(ent, 'about.html'), encoding='utf-8') as f:
        txt = f.read()
    with open(os.path.join(ent, 'about.html'), 'w', encoding='utf-8') as f:
        f.write(txt.replace('About this room.', 'About this room&#8210;more.'))
    rc, findings = run(ent)
    ok(rc == 1 and has_error(findings, 'copy', 'en or em dash'),
       'decimal entity &#8210; (U+2012) fails the copy check')

    ent2 = os.path.join(td, 'entity-8213')
    shutil.copytree(room, ent2)
    with open(os.path.join(ent2, 'about.html'), encoding='utf-8') as f:
        txt = f.read()
    with open(os.path.join(ent2, 'about.html'), 'w', encoding='utf-8') as f:
        f.write(txt.replace('About this room.', 'About this room&#8213;more.'))
    rc, findings = run(ent2)
    ok(rc == 1 and has_error(findings, 'copy', 'en or em dash'),
       'decimal entity &#8213; (U+2015) fails the copy check')

    wrap = os.path.join(td, 'banner-wrap')
    shutil.copytree(room, wrap)
    with open(os.path.join(wrap, 'index.html'), encoding='utf-8') as f:
        txt = f.read()
    with open(os.path.join(wrap, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(txt.replace(
            '>Beta: early and a bit unfinished. Not a brochure.</div>',
            '><span>Beta: early and a bit unfinished. Not a brochure.</span></div>',
        ))
    rc, findings = run(wrap)
    ok(rc == 0 and not has_error(findings, 'banner'),
       'Beta banner text wrapped in a child element still passes')

    wrap_bad = os.path.join(td, 'banner-wrap-preview')
    shutil.copytree(room, wrap_bad)
    with open(os.path.join(wrap_bad, 'index.html'), encoding='utf-8') as f:
        txt = f.read()
    with open(os.path.join(wrap_bad, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(txt.replace(
            '>Beta: early and a bit unfinished. Not a brochure.</div>',
            '><span>Preview only.</span></div>',
        ))
    rc, findings = run(wrap_bad)
    ok(rc == 1 and has_error(findings, 'banner', 'Preview only'),
       'Preview only banner text wrapped in a child element fails')

    empty_d = os.path.join(td, 'robots-empty-disallow')
    room_ed = write_good_room(empty_d, robots='User-agent: *\nAllow: /\nDisallow:\n')
    rc, findings = run(room_ed)
    ok(rc == 0 and not has_error(findings, 'robots'),
       'empty Disallow: is not a blanket disallow')

    # ---- room-root /start only (Aegis / Juno LOW) ----
    room_p = RSC.Path(room)
    ok(RSC.is_start_path(room_p, room_p / 'start.html'),
       'is_start_path accepts room-root start.html')
    ok(RSC.is_start_path(room_p, room_p / 'start'),
       'is_start_path accepts room-root start')
    ok(RSC.is_start_path(room_p, room_p / 'start' / 'index.html'),
       'is_start_path accepts room-root start/index.html')
    ok(not RSC.is_start_path(room_p, room_p / 'stories' / 'start.html'),
       'is_start_path rejects nested stories/start.html')
    ok(not RSC.is_start_path(room_p, room_p / 'legal' / 'start.html'),
       'is_start_path rejects nested legal/start.html')
    ok(not RSC.is_start_path(room_p, room_p / 'start-anything.html'),
       'is_start_path rejects start-anything.html')

    st_nested = os.path.join(td, 'start-nested')
    shutil.copytree(room, st_nested)
    os.makedirs(os.path.join(st_nested, 'stories'), exist_ok=True)
    with open(os.path.join(st_nested, 'stories', 'start.html'), 'w', encoding='utf-8') as f:
        f.write(page('Nested start', '<p>Contact the operator at %s.</p>' % op_email))
    rc, findings = run(st_nested)
    ok(rc == 1 and has_error(findings, 'pii', 'only allowed on /start'),
       'operator email on nested stories/start.html fails')
    ok(all(op_email not in f.msg for f in findings),
       'nested start finding messages do not include the operator email value')

    st_idx = os.path.join(td, 'start-index')
    shutil.copytree(room, st_idx)
    os.makedirs(os.path.join(st_idx, 'start'), exist_ok=True)
    with open(os.path.join(st_idx, 'start', 'index.html'), 'w', encoding='utf-8') as f:
        f.write(page('Start', '<p>Contact the operator at %s.</p>' % op_email))
    with open(os.path.join(st_idx, 'sitemap.xml'), encoding='utf-8') as f:
        sm = f.read()
    with open(os.path.join(st_idx, 'sitemap.xml'), 'w', encoding='utf-8') as f:
        f.write(sm.replace('</urlset>', '  <url><loc>https://testroom.example/start/index.html</loc></url>\n</urlset>'))
    rc, findings = run(st_idx)
    ok(not has_error(findings, 'pii'),
       'operator email on room-root start/index.html is allowed')
    ok(all(op_email not in f.msg for f in findings),
       'start/index.html finding messages do not include the operator email value')

    # ---- well-known named reads reject symlinks and do not print outside paths ----
    marker = 'outside-secret-wellknown'
    outside_dir = os.path.join(td, marker)
    os.makedirs(outside_dir, exist_ok=True)
    outside_site = os.path.join(outside_dir, 'leaked-site.json')
    with open(outside_site, 'w', encoding='utf-8') as f:
        f.write('{"dash": "this file uses an em dash: \u2014"}\n')
    outside_cname = os.path.join(outside_dir, 'leaked-CNAME')
    with open(outside_cname, 'w', encoding='utf-8') as f:
        f.write('evil.example\n')
    outside_js = os.path.join(outside_dir, 'leaked-factory.js')
    with open(outside_js, 'wb') as f:
        f.write(b'/* outside factory.js */\n')
    outside_lock = os.path.join(outside_dir, 'leaked-FACTORY.lock')
    with open(outside_lock, 'w', encoding='utf-8') as f:
        f.write('{"files": {}}\n')

    def no_outside(findings, label):
        msgs = ' | '.join(f.msg for f in findings)
        ok(marker not in msgs and 'leaked-site.json' not in msgs and 'leaked-CNAME' not in msgs
           and 'leaked-factory.js' not in msgs and 'leaked-FACTORY.lock' not in msgs,
           '%s findings do not print the outside path' % label)

    syn_site = os.path.join(td, 'symlink-site')
    shutil.copytree(room, syn_site)
    os.remove(os.path.join(syn_site, 'site.json'))
    os.symlink(outside_site, os.path.join(syn_site, 'site.json'))
    rc, findings = run(syn_site)
    ok(has_error(findings, 'path', 'site.json is a symlink'),
       'direct read of site.json rejects a symlink')
    no_outside(findings, 'site.json symlink')

    syn_cn = os.path.join(td, 'symlink-cname')
    shutil.copytree(room, syn_cn)
    os.remove(os.path.join(syn_cn, 'CNAME'))
    os.symlink(outside_cname, os.path.join(syn_cn, 'CNAME'))
    rc, findings = run(syn_cn)
    ok(has_error(findings, 'path', 'CNAME is a symlink'),
       'direct read of CNAME rejects a symlink')
    no_outside(findings, 'CNAME symlink')

    syn_js = os.path.join(td, 'symlink-factory-js')
    shutil.copytree(room, syn_js)
    os.remove(os.path.join(syn_js, 'factory.js'))
    os.symlink(outside_js, os.path.join(syn_js, 'factory.js'))
    rc, findings = run(syn_js)
    ok(has_error(findings, 'path', 'factory.js is a symlink'),
       'direct read of factory.js rejects a symlink')
    ok(not any(marker in f.msg or 'leaked-factory.js' in f.msg for f in findings),
       'budget step does not print an outside factory.js path')
    no_outside(findings, 'factory.js symlink')

    syn_lock = os.path.join(td, 'symlink-lock')
    shutil.copytree(room, syn_lock)
    os.remove(os.path.join(syn_lock, 'FACTORY.lock'))
    os.symlink(outside_lock, os.path.join(syn_lock, 'FACTORY.lock'))
    rc, findings = run(syn_lock)
    ok(has_error(findings, 'path', 'FACTORY.lock is a symlink'),
       'direct read of FACTORY.lock rejects a symlink')
    no_outside(findings, 'FACTORY.lock symlink')

    outside_tax = os.path.join(outside_dir, 'leaked-taxonomy.json')
    with open(outside_tax, 'w', encoding='utf-8') as f:
        f.write('{not valid json, leaked-taxonomy}\n')
    syn_tax = os.path.join(td, 'symlink-taxonomy')
    shutil.copytree(room, syn_tax)
    os.symlink(outside_tax, os.path.join(syn_tax, 'taxonomy.json'))
    rc, findings = run(syn_tax)
    ok(has_error(findings, 'path', 'taxonomy.json is a symlink'),
       'direct read of taxonomy.json rejects a symlink')
    ok(not has_error(findings, 'taxonomy.json', 'not valid JSON'),
       'taxonomy.json symlink target is not parsed as JSON')
    no_outside(findings, 'taxonomy.json symlink')
    ok(all('leaked-taxonomy' not in f.msg for f in findings),
       'taxonomy.json symlink findings do not include leaked target text')

    # ---- budget check with relative --room / --factory (the CI layout) ----
    rel_root = os.path.join(td, 'ci-layout')
    os.makedirs(rel_root)
    write_good_room(rel_root)
    old_cwd = os.getcwd()
    try:
        os.chdir(rel_root)
        rc, findings = RSC.run_check('room', os.path.relpath(ROOT, rel_root),
                                     expect_indexable=True, fail_on_stale=False,
                                     core_budget_bytes=255000, print_report=False)
    finally:
        os.chdir(old_cwd)
    ok(not has_error(findings, 'budget'),
       'budget check works when --room and --factory are relative paths (got %s)' %
       [f.msg for f in findings if f.code == 'budget'])
    ok(not any('No such file' in f.msg or 'factoryfactory.js' in f.msg for f in findings),
       'budget notes do not mangle a relative check_budget.sh path')

    # ---- reusable workflow checkout contract ----
    wf = os.path.join(ROOT, '.github', 'workflows', 'room-static-check.yml')
    with open(wf, encoding='utf-8') as f:
        wf_text = f.read()
    ok('${{ github.action_repository }}' not in wf_text,
       'workflow does not use github.action_repository')
    ok('${{ github.action_ref }}' not in wf_text,
       'workflow does not use github.action_ref')
    ok('repository: jebbdykstra99/subx-factory' in wf_text,
       'factory checkout hardcodes jebbdykstra99/subx-factory')
    ok('factory_ref:' in wf_text,
       'workflow_call accepts factory_ref')
    ok('${{ job.workflow_sha }}' in wf_text,
       'resolve step uses job.workflow_sha')
    ok('${{ github.job_workflow_sha }}' not in wf_text,
       'resolve step does not use github.job_workflow_sha')
    ok('[0-9a-fA-F]{40}' in wf_text,
       'resolve step requires a 40-char SHA')
    ok('steps.factory_sha.outputs.sha' in wf_text,
       'factory checkout uses the resolved SHA')

finally:
    shutil.rmtree(td, ignore_errors=True)


print('%d fail(s)' % len(fails))
if fails:
    for m in fails:
        print('  -', m)
    sys.exit(1)
print('all tests passed')
sys.exit(0)
