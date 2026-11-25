#!/usr/bin/env python3
"""Static clone-room checker for the shared room-static-check workflow.

Stdlib only. Local files only (no live fetch, no tokens). A thin caller in a
room repo pins this workflow to a subx-factory SHA and runs it against the
room checkout.

Checks: HTML structure and internal links; sitemap coverage and robots Allow
for lifted rooms; site.json schema (redditCrosspost must be false); typography
(no en/em dashes, no word Grok) in public copy; private-contact hashes (values
never printed); noindex/banner vs expect_indexable; factory.js byte budget via
tools/check_budget.sh; FACTORY.lock sha256 vs the room tree and vs this
factory release (STALE is a warning unless --fail-on-stale).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

PUBLIC_COPY_EXT = {'.html', '.txt', '.xml', '.json'}
PUBLIC_COPY_NAMES = {'llms.txt', 'robots.txt', 'sitemap.xml', 'site.json', 'taxonomy.json'}
TEXT_SCAN_EXT = {'.html', '.txt', '.xml', '.json', '.js', '.css', '.md'}
SKIP_DIR_NAMES = {'.git', 'node_modules', '__pycache__'}
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}
DASH_RE = re.compile(r'[\u2012\u2013\u2014\u2015]')
DASH_ENTITY_RE = re.compile(r'&(?:[nN][dD]ash|[mM][dD]ash);|&#(?:8211|8212|x201[2-5X]|X201[2-5]);', re.I)
GROK_WORD_RE = re.compile(r'(?<![A-Za-z0-9])Grok(?![A-Za-z0-9])')
EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
PHONE_RE = re.compile(r'(?<!\d)(?:\+?1[\s.\-]*)?(?:\(?\d{3}\)?[\s.\-]*)\d{3}[\s.\-]*\d{4}(?!\d)')
DENVER_RE = re.compile(r'\bDenver\b.{0,40}\b(?:CO|Colorado)\b|\b(?:CO|Colorado)\b.{0,40}\bDenver\b|\b802\d{2}\b', re.I)
NOINDEX_META_RE = re.compile(r'<meta\b[^>]*\brobots\b[^>]*>', re.I)
PREVIEW_WORD_RE = re.compile(r'\bPreview\b')
BANNER_RE = re.compile(r'class=["\'][^"\']*preview-banner[^"\']*["\'][^>]*>([^<]*)', re.I)
# sha256 of known private emails (lowercase) and phone digit forms. Not the values.
PRIVATE_EMAIL_HASHES = {
    '67780f8474807c9cebdc1f89fa17a4dc8c7c29fa8a9036f34ed378dc0214b267',
    '4e5fa5feb3efc43eb6526cedf6a2036afbc25862a581cae8d5cfd7acbbe8a1ee',
    '35105d77a479aace5aa5f2d685ee60fa64b813016b6f1668d762e4d680ef5b80',
}
PRIVATE_PHONE_HASHES = {
    'a581f7cd3985be994e0e03db59c7877728c75bf0d0e741e6ccf2fe490a486d7f',
    'db2eb141f529992d56d16434db65f96cc89ffb654ea367d9024054d49ba56803',
}

DEFAULT_BUDGET = 255000


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def parse_bool(s: str) -> bool:
    v = str(s).strip().lower()
    if v in ('1', 'true', 'yes', 'y'):
        return True
    if v in ('0', 'false', 'no', 'n'):
        return False
    raise argparse.ArgumentTypeError('expected true or false, got %r' % s)


class Finding:
    def __init__(self, level: str, code: str, msg: str):
        self.level = level  # error | stale | note
        self.code = code
        self.msg = msg

    def __repr__(self) -> str:
        return '%s %s: %s' % (self.level.upper(), self.code, self.msg)


def rel(root: Path, p: Path) -> str:
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(p)


def iter_files(room: Path, *, ext: set[str] | None = None, names: set[str] | None = None):
    for p in room.rglob('*'):
        if not p.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in p.parts):
            continue
        if names and p.name in names:
            yield p
            continue
        if ext and p.suffix.lower() in ext:
            yield p


def public_copy_files(room: Path):
    for p in iter_files(room, ext=PUBLIC_COPY_EXT, names=PUBLIC_COPY_NAMES):
        # FACTORY.lock is not public copy
        if p.name == 'FACTORY.lock':
            continue
        yield p


def text_scan_files(room: Path):
    for p in iter_files(room, ext=TEXT_SCAN_EXT):
        yield p


# ---- schema (subset of JSON Schema draft 2020-12 used by room_site.schema.json) ----

def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def validate_schema(instance: Any, schema: dict, path: str = '$') -> list[str]:
    errs: list[str] = []
    typ = schema.get('type')
    if typ == 'object':
        if not isinstance(instance, dict):
            return ['%s: expected object, got %s' % (path, type(instance).__name__)]
        for key in schema.get('required', []):
            if key not in instance:
                errs.append('%s: missing required property %s' % (path, key))
        props = schema.get('properties') or {}
        for key, val in instance.items():
            if key in props:
                errs.extend(validate_schema(val, props[key], '%s.%s' % (path, key)))
            elif schema.get('additionalProperties') is False:
                errs.append('%s: additional property %s is not allowed' % (path, key))
        return errs
    if typ == 'string':
        if not isinstance(instance, str):
            return ['%s: expected string, got %s' % (path, type(instance).__name__)]
        if 'minLength' in schema and len(instance) < schema['minLength']:
            errs.append('%s: string shorter than minLength %s' % (path, schema['minLength']))
        if 'const' in schema and instance != schema['const']:
            errs.append('%s: expected %r' % (path, schema['const']))
        return errs
    if typ == 'integer':
        if not _is_int(instance):
            return ['%s: expected integer, got %s' % (path, type(instance).__name__)]
        if 'minimum' in schema and instance < schema['minimum']:
            errs.append('%s: %s is below minimum %s' % (path, instance, schema['minimum']))
        if 'const' in schema and instance != schema['const']:
            errs.append('%s: expected %r' % (path, schema['const']))
        return errs
    if typ == 'boolean':
        if not isinstance(instance, bool):
            return ['%s: expected boolean, got %s' % (path, type(instance).__name__)]
        if 'const' in schema and instance != schema['const']:
            errs.append('%s: expected %s' % (path, 'true' if schema['const'] else 'false'))
        return errs
    if typ == 'array':
        if not isinstance(instance, list):
            return ['%s: expected array, got %s' % (path, type(instance).__name__)]
        return errs
    if typ == 'number':
        if isinstance(instance, bool) or not isinstance(instance, (int, float)):
            return ['%s: expected number, got %s' % (path, type(instance).__name__)]
        return errs
    if 'const' in schema and instance != schema['const']:
        errs.append('%s: expected %r' % (path, schema['const']))
    return errs


# ---- HTML ----

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.has_doctype = False
        self.stack: list[str] = []
        self.ids_seen: set[str] = set()
        self.dup_ids: list[str] = []
        self.refs: list[tuple[str, str, str]] = []  # kind, url, tag
        self.parse_errors: list[str] = []

    def error(self, message):  # html.parser API
        self.parse_errors.append(message)

    def handle_decl(self, decl):
        if decl.lower().startswith('doctype'):
            self.has_doctype = True

    def handle_starttag(self, tag, attrs):
        ad = {k: (v if v is not None else '') for k, v in attrs}
        if tag not in VOID:
            self.stack.append(tag)
        ident = ad.get('id') or ''
        if ident:
            if ident in self.ids_seen:
                self.dup_ids.append(ident)
            self.ids_seen.add(ident)
        for key in ('href', 'src', 'action', 'poster', 'data-src'):
            if key in ad and ad[key]:
                self.refs.append((key, ad[key], tag))
        if 'srcset' in ad and ad['srcset']:
            for part in ad['srcset'].split(','):
                u = part.strip().split(' ')[0]
                if u:
                    self.refs.append(('srcset', u, tag))

    def handle_endtag(self, tag):
        if tag in self.stack:
            while self.stack:
                t = self.stack.pop()
                if t == tag:
                    break

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.stack and self.stack[-1] == tag and tag not in VOID:
            self.stack.pop()


def room_hosts(room: Path, site: dict | None) -> set[str]:
    hosts: set[str] = set()
    cname = room / 'CNAME'
    if cname.is_file():
        host = cname.read_text(encoding='utf-8', errors='replace').strip().splitlines()
        host = host[0].strip().lower() if host else ''
        if host:
            hosts.add(host)
            if host.startswith('www.'):
                hosts.add(host[4:])
            else:
                hosts.add('www.' + host)
    if site and isinstance(site.get('domain'), str) and site['domain']:
        d = site['domain'].strip().lower()
        d = d.split('://', 1)[-1].split('/', 1)[0]
        if d:
            hosts.add(d)
    sm = room / 'sitemap.xml'
    if sm.is_file():
        for loc in re.findall(r'<loc>\s*([^<]+)\s*</loc>', sm.read_text(encoding='utf-8', errors='replace')):
            net = urlparse(loc.strip()).netloc.lower()
            if net:
                hosts.add(net)
    return hosts


def local_target(url: str, hosts: set[str]) -> str | None:
    """Return a room-relative path, 'external', or None (skip)."""
    if not url or url.startswith(('#', 'mailto:', 'tel:', 'javascript:', 'data:')):
        return None
    raw = url.strip()
    if raw.startswith('//'):
        parsed = urlparse('https:' + raw)
    else:
        parsed = urlparse(raw)
    if parsed.scheme in ('http', 'https'):
        host = (parsed.netloc or '').lower()
        if host not in hosts:
            return 'external'
        path = parsed.path
    else:
        path = parsed.path if parsed.scheme == '' else parsed.path
        # bare relative path: urlparse('about.html') puts it in path
        if not path:
            path = raw.split('?', 1)[0].split('#', 1)[0]
    path = unquote(path.split('?')[0].split('#')[0])
    if path == '' or path == '/':
        return 'index.html'
    if path.startswith('/'):
        path = path[1:]
    if path.endswith('/'):
        path = path + 'index.html'
    return path


def resolve_local(room: Path, target: str) -> bool:
    if (room / target).is_file():
        return True
    # Cloudflare / Pages pretty URL: /oahu -> oahu.html
    if not Path(target).suffix and (room / (target + '.html')).is_file():
        return True
    return False


def has_noindex(html: str) -> bool:
    for tag in NOINDEX_META_RE.findall(html):
        if re.search(r'noindex', tag, re.I):
            return True
    return False


def parse_robots_star(text: str) -> list[str]:
    """Return directives (Allow/Disallow values not needed) for the User-agent: * group.

    Groups are separated by a blank line or a new User-agent after rules started.
    Consecutive User-agent lines share one rule block.
    """
    lines = text.splitlines()
    groups: list[tuple[list[str], list[tuple[str, str]]]] = []
    agents: list[str] = []
    rules: list[tuple[str, str]] = []
    saw_rule = False

    def flush():
        nonlocal agents, rules, saw_rule
        if agents or rules:
            groups.append((agents, rules))
        agents, rules, saw_rule = [], [], False

    for raw in lines:
        line = raw.split('#', 1)[0].strip()
        if not line:
            if saw_rule:
                flush()
            continue
        if line.lower().startswith('user-agent:'):
            val = line.split(':', 1)[1].strip()
            if saw_rule:
                flush()
            agents.append(val)
            continue
        if line.lower().startswith('sitemap:'):
            continue
        if ':' in line:
            k, v = line.split(':', 1)
            rules.append((k.strip().lower(), v.strip()))
            saw_rule = True
    flush()
    out: list[tuple[str, str]] = []
    for ag, ru in groups:
        if any(a.strip() == '*' for a in ag):
            out.extend(ru)
            break
    return out


# ---- site.json local paths ----

ASSET_SUFFIX = ('.jpg', '.jpeg', '.png', '.webp', '.svg', '.js', '.css', '.html', '.json', '.mp3', '.gif', '.ico')


def walk_local_paths(obj: Any, path: str = '$'):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk_local_paths(v, '%s.%s' % (path, k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk_local_paths(v, '%s[%d]' % (path, i))
    elif isinstance(obj, str):
        s = obj.strip()
        if s.startswith('http://') or s.startswith('https://') or s.startswith('//') or s.startswith('data:'):
            return
        looks = s.startswith('/') or s.startswith('assets/') or s.lower().endswith(ASSET_SUFFIX)
        if looks and ('/' in s or s.lower().endswith(ASSET_SUFFIX)):
            yield path, s


# ---- lock / release ----

def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def rooms_domain(factory: Path, site_id: str | None) -> str | None:
    rooms_path = factory / 'rooms.json'
    if not rooms_path.is_file() or not site_id:
        return None
    try:
        cfg = load_json(rooms_path)
    except Exception:
        return None
    for e in cfg.get('rooms') or []:
        if e.get('siteId') == site_id or e.get('room') == site_id:
            return (e.get('domain') or '').strip() or None
    return None


# ---- main check ----

def collect(room: Path, factory: Path, *, expect_indexable: bool, fail_on_stale: bool,
            core_budget_bytes: int, schema: dict) -> list[Finding]:
    findings: list[Finding] = []

    def err(code: str, msg: str):
        findings.append(Finding('error', code, msg))

    def stale(code: str, msg: str):
        findings.append(Finding('stale', code, msg))

    def note(code: str, msg: str):
        findings.append(Finding('note', code, msg))

    if not room.is_dir():
        err('room', 'room path is not a directory: %s' % room)
        return findings
    if not factory.is_dir():
        err('factory', 'factory path is not a directory: %s' % factory)
        return findings

    site = None
    site_path = room / 'site.json'
    if not site_path.is_file():
        err('site.json', 'site.json is missing')
    else:
        try:
            site = load_json(site_path)
        except Exception as e:
            err('site.json', 'site.json is not valid JSON: %s' % e)
            site = None
        else:
            if not isinstance(site, dict):
                err('site.json', 'site.json root must be an object')
                site = None
            else:
                for e in validate_schema(site, schema):
                    err('site.json', e)

    tax = room / 'taxonomy.json'
    if tax.is_file():
        try:
            load_json(tax)
        except Exception as e:
            err('taxonomy.json', 'taxonomy.json is not valid JSON: %s' % e)

    cname_path = room / 'CNAME'
    cname_val = ''
    if cname_path.is_file():
        cname_val = cname_path.read_text(encoding='utf-8', errors='replace').strip().splitlines()
        cname_val = cname_val[0].strip() if cname_val else ''
        if not cname_val:
            err('cname', 'CNAME is empty')
        else:
            site_id = (site or {}).get('siteId') if isinstance(site, dict) else None
            domain = rooms_domain(factory, site_id if isinstance(site_id, str) else None)
            if domain and cname_val.lower() != domain.lower():
                err('cname', 'CNAME %s does not match rooms.json domain %s' % (cname_val, domain))

    hosts = room_hosts(room, site if isinstance(site, dict) else None)

    # 1. HTML structure and internal links
    html_files = sorted(p for p in room.glob('*.html') if p.is_file())
    if not html_files:
        err('html', 'no *.html files in the room root')
    for p in html_files:
        text = p.read_text(encoding='utf-8', errors='replace')
        parser = PageParser()
        try:
            parser.feed(text)
            parser.close()
        except Exception as e:
            err('html', '%s: parse error: %s' % (p.name, e))
            continue
        for e in parser.parse_errors:
            err('html', '%s: %s' % (p.name, e))
        if not parser.has_doctype and not text.lstrip().lower().startswith('<!doctype'):
            err('html', '%s: missing doctype' % p.name)
        if parser.dup_ids:
            err('html', '%s: duplicate id(s): %s' % (p.name, ', '.join(parser.dup_ids)))
        for kind, url, tag in parser.refs:
            target = local_target(url, hosts)
            if target is None or target == 'external':
                continue
            if not resolve_local(room, target):
                err('links', '%s: broken internal %s on <%s>: %s (resolved %s)' % (p.name, kind, tag, url, target))

    if isinstance(site, dict):
        for jpath, val in walk_local_paths(site):
            rel_path = val.split('?', 1)[0].lstrip('/')
            if not rel_path:
                continue
            if not resolve_local(room, rel_path):
                err('links', 'site.json %s path missing: %s' % (jpath, val))

    # 2. Sitemap + robots (lifted rooms)
    sm_path = room / 'sitemap.xml'
    indexable: list[str] = []
    noindex_pages: list[str] = []
    for p in html_files:
        text = p.read_text(encoding='utf-8', errors='replace')
        if has_noindex(text):
            noindex_pages.append(p.name)
        else:
            indexable.append(p.name)

    if expect_indexable:
        if not sm_path.is_file():
            err('sitemap', 'sitemap.xml is missing')
            sm_paths: set[str] = set()
        else:
            sm_text = sm_path.read_text(encoding='utf-8', errors='replace')
            sm_paths = set()
            locs = re.findall(r'<loc>\s*([^<]+)\s*</loc>', sm_text)
            if not locs:
                err('sitemap', 'sitemap.xml has no <loc> entries')
            for loc in locs:
                t = local_target(loc.strip(), hosts)
                if t is None or t == 'external':
                    err('sitemap', 'sitemap <loc> is not this room: %s' % loc.strip())
                    continue
                if not resolve_local(room, t):
                    err('sitemap', 'sitemap <loc> is missing in the room: %s' % loc.strip())
                sm_paths.add(t)
        for name in indexable:
            if name not in sm_paths:
                err('sitemap', 'indexable page missing from sitemap.xml: %s' % name)
        robots_path = room / 'robots.txt'
        if not robots_path.is_file():
            err('robots', 'robots.txt is missing')
        else:
            rules = parse_robots_star(robots_path.read_text(encoding='utf-8', errors='replace'))
            allows = [v for k, v in rules if k == 'allow']
            disallows = [v for k, v in rules if k == 'disallow']
            if not any(v in ('/', '') or v == '/' for v in allows) and not any(v == '/' for v in allows):
                # Allow: / is required
                if '/' not in allows:
                    err('robots', 'robots.txt User-agent: * group must include Allow: /')
            if '/' in disallows or '' in disallows:
                err('robots', 'robots.txt User-agent: * group must not blanket-Disallow: /')

    # 3. typography + Grok (public copy only; skip stamped shell)
    skip_copy = {'FACTORY.lock'}
    for p in public_copy_files(room):
        if p.name in skip_copy:
            continue
        if p.name.startswith('factory') and p.suffix == '.js':
            continue
        if p.name == 'styles.css':
            continue
        text = p.read_text(encoding='utf-8', errors='replace')
        rname = rel(room, p)
        for i, line in enumerate(text.splitlines(), 1):
            if DASH_RE.search(line) or DASH_ENTITY_RE.search(line):
                err('copy', '%s:%d: en or em dash (or entity) in public copy' % (rname, i))
            if GROK_WORD_RE.search(line):
                err('copy', '%s:%d: word Grok in public copy' % (rname, i))

    # 4. private contacts (public copy and other room text, including JS)
    for p in text_scan_files(room):
        text = p.read_text(encoding='utf-8', errors='replace')
        rname = rel(room, p)
        for i, line in enumerate(text.splitlines(), 1):
            for em in EMAIL_RE.findall(line):
                if sha256_text(em.lower()) in PRIVATE_EMAIL_HASHES:
                    err('pii', '%s:%d: private email' % (rname, i))
            for m in PHONE_RE.finditer(line):
                digits = re.sub(r'\D', '', m.group(0))
                forms = {digits}
                if len(digits) == 11 and digits.startswith('1'):
                    forms.add(digits[1:])
                if any(sha256_text(d) in PRIVATE_PHONE_HASHES for d in forms):
                    err('pii', '%s:%d: private phone' % (rname, i))
            if DENVER_RE.search(line):
                err('pii', '%s:%d: Denver address pattern' % (rname, i))

    # 5. noindex / banner
    if expect_indexable:
        allowed_noindex = {'404.html', 'report.html'}
        for name in noindex_pages:
            if name not in allowed_noindex:
                err('noindex', '%s has a noindex robots meta; only 404.html and report.html may' % name)
        for name in ('404.html', 'report.html'):
            if (room / name).is_file() and name not in noindex_pages:
                err('noindex', '%s must keep noindex, nofollow' % name)
        for p in html_files:
            text = p.read_text(encoding='utf-8', errors='replace')
            banners = BANNER_RE.findall(text)
            for b in banners:
                body = b.strip()
                if re.search(r'Preview only', body, re.I):
                    err('banner', '%s preview-banner says Preview only' % p.name)
                elif body and not body.startswith('Beta:'):
                    err('banner', '%s preview-banner must start with Beta:' % p.name)
            # leftover visible Preview copy; class names and /preview-lift/ are ok
            for i, line in enumerate(text.splitlines(), 1):
                if not PREVIEW_WORD_RE.search(line):
                    continue
                stripped = line.strip()
                if re.search(r'class=["\'][^"\']*preview', stripped, re.I) and not re.search(r'>\s*[^<]*Preview', stripped):
                    # class/id only (preview-banner, compose-image-preview) with no Preview text
                    if not PREVIEW_WORD_RE.search(re.sub(r'\b(?:class|id)=["\'][^"\']*["\']', '', stripped)):
                        continue
                if PREVIEW_WORD_RE.search(stripped):
                    # still a Preview word outside attr values?
                    without_attrs = re.sub(r'\b(?:class|id|href|src)=["\'][^"\']*["\']', '', stripped)
                    if PREVIEW_WORD_RE.search(without_attrs):
                        err('banner', '%s:%d: leftover Preview copy' % (p.name, i))
        robots_path = room / 'robots.txt'
        # /preview-lift/ leftover Disallow is allowed; do not flag

    # 6. factory.js budget
    core = room / 'factory.js'
    budget_sh = factory / 'tools' / 'check_budget.sh'
    if not core.is_file():
        err('budget', 'factory.js is missing')
    elif not budget_sh.is_file():
        err('budget', 'tools/check_budget.sh is missing in the factory checkout')
    else:
        env = os.environ.copy()
        env['CORE_BUDGET_BYTES'] = str(int(core_budget_bytes))
        try:
            proc = subprocess.run(
                ['bash', str(budget_sh), str(core.resolve()), str(int(core_budget_bytes))],
                cwd=str(factory),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as e:
            err('budget', 'check_budget.sh failed to run: %s' % e)
        else:
            out = (proc.stdout or '') + (proc.stderr or '')
            for line in out.splitlines():
                note('budget', line)
            if proc.returncode != 0:
                err('budget', 'factory.js exceeds budget %s B' % int(core_budget_bytes))

    # 7. FACTORY.lock vs room and vs this release
    lock_path = room / 'FACTORY.lock'
    lock = None
    if not lock_path.is_file():
        err('lock', 'FACTORY.lock is missing')
    else:
        try:
            lock = load_json(lock_path)
        except Exception as e:
            err('lock', 'FACTORY.lock is not valid JSON: %s' % e)
            lock = None
        if lock is not None and not isinstance(lock, dict):
            err('lock', 'FACTORY.lock root must be an object')
            lock = None
        files = (lock or {}).get('files') if isinstance(lock, dict) else None
        if lock is not None and not isinstance(files, dict):
            err('lock', 'FACTORY.lock is missing a files object')
            files = None
        if isinstance(files, dict):
            for fn, expected in files.items():
                if not isinstance(fn, str) or not fn:
                    err('lock', 'FACTORY.lock has a bad files key')
                    continue
                rp = room / fn
                if not rp.is_file():
                    err('lock', 'FACTORY.lock lists %s but the file is missing in the room' % fn)
                    continue
                got = sha256_bytes(rp.read_bytes())
                if not isinstance(expected, str) or got != expected:
                    err('lock', '%s sha256 does not match FACTORY.lock (local DRIFT)' % fn)

    # release compare: factory.js + opt-in factory-*.js that exist on this SHA
    release_js = factory / 'factory' / 'factory.js'
    release_json = factory / 'FACTORY_RELEASE.json'
    release_sha = None
    if release_js.is_file():
        release_sha = sha256_bytes(release_js.read_bytes())
    if release_json.is_file():
        try:
            relj = load_json(release_json)
            rec = relj.get('factory.js') if isinstance(relj, dict) else None
            rec_sha = rec.get('sha256') if isinstance(rec, dict) else None
            if isinstance(rec_sha, str) and release_sha and rec_sha != release_sha:
                note('release', 'FACTORY_RELEASE.json factory.js sha256 does not match factory/factory.js on this SHA')
            if isinstance(rec_sha, str) and not release_sha:
                release_sha = rec_sha
        except Exception as e:
            note('release', 'FACTORY_RELEASE.json could not be read: %s' % e)

    lock_files = (lock or {}).get('files') if isinstance(lock, dict) else None
    if isinstance(lock_files, dict) and release_sha:
        fj = lock_files.get('factory.js')
        if isinstance(fj, str) and fj != release_sha:
            stale('stale', 'factory.js lock does not match this factory release')
        for fn, expected in lock_files.items():
            if not isinstance(fn, str) or not fn.startswith('factory-') or not fn.endswith('.js'):
                continue
            fp = factory / 'factory' / fn
            if not fp.is_file():
                stale('stale', '%s is in the room lock but not on this factory release' % fn)
                continue
            rel_sha = sha256_bytes(fp.read_bytes())
            if isinstance(expected, str) and expected != rel_sha:
                stale('stale', '%s lock does not match this factory release' % fn)
        # styles.css is a room skin; do not compare to hub styles

    _ = fail_on_stale  # used by report() / run_check()
    return findings


def report(findings: list[Finding], *, fail_on_stale: bool) -> int:
    errors = [f for f in findings if f.level == 'error']
    stales = [f for f in findings if f.level == 'stale']
    notes = [f for f in findings if f.level == 'note']
    for f in findings:
        print(f)
    print('---')
    print('%d error(s), %d stale, %d note(s)' % (len(errors), len(stales), len(notes)))
    if errors:
        return 1
    if stales and fail_on_stale:
        print('failing on STALE because --fail-on-stale is true')
        return 1
    if stales:
        print('STALE is a warning only (--fail-on-stale is false)')
    return 0


def default_schema_path() -> Path:
    return Path(__file__).resolve().parent / 'room_site.schema.json'


def run_check(room: str | Path, factory: str | Path, *, expect_indexable: bool = True,
              fail_on_stale: bool = False, core_budget_bytes: int = DEFAULT_BUDGET,
              schema_path: str | Path | None = None, print_report: bool = True) -> tuple[int, list[Finding]]:
    room_p = Path(room)
    factory_p = Path(factory)
    sp = Path(schema_path) if schema_path else default_schema_path()
    if not sp.is_file():
        findings = [Finding('error', 'schema', 'schema file is missing: %s' % sp)]
        rc = report(findings, fail_on_stale=fail_on_stale) if print_report else 1
        return rc, findings
    try:
        schema = load_json(sp)
    except Exception as e:
        findings = [Finding('error', 'schema', 'schema is not valid JSON: %s' % e)]
        rc = report(findings, fail_on_stale=fail_on_stale) if print_report else 1
        return rc, findings
    findings = collect(room_p, factory_p, expect_indexable=expect_indexable, fail_on_stale=fail_on_stale,
                       core_budget_bytes=int(core_budget_bytes), schema=schema)
    rc = report(findings, fail_on_stale=fail_on_stale) if print_report else (
        1 if any(f.level == 'error' for f in findings) or (fail_on_stale and any(f.level == 'stale' for f in findings)) else 0
    )
    return rc, findings


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description='Static clone-room checker (local files only).')
    ap.add_argument('--room', required=True, help='path to the room checkout')
    ap.add_argument('--factory', required=True, help='path to the subx-factory checkout')
    ap.add_argument('--expect-indexable', type=parse_bool, default=True,
                    help='true for a lifted room (default true)')
    ap.add_argument('--fail-on-stale', type=parse_bool, default=False,
                    help='true to fail when the lock is STALE vs this release (default false)')
    ap.add_argument('--core-budget-bytes', type=int, default=DEFAULT_BUDGET)
    ap.add_argument('--schema', default=None, help='override path to room_site.schema.json')
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rc, _ = run_check(args.room, args.factory, expect_indexable=args.expect_indexable,
                      fail_on_stale=args.fail_on_stale, core_budget_bytes=args.core_budget_bytes,
                      schema_path=args.schema)
    return rc


if __name__ == '__main__':
    sys.exit(main())
