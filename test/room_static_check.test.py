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

finally:
    shutil.rmtree(td, ignore_errors=True)


print('%d fail(s)' % len(fails))
if fails:
    for m in fails:
        print('  -', m)
    sys.exit(1)
print('all tests passed')
sys.exit(0)
