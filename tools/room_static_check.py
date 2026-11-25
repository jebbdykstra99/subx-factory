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
DASH_ENTITY_RE = re.compile(r'&(?:[nN][dD]ash|[mM][dD]ash);|&#(?:8210|8211|8212|8213|x201[2-5X]|X201[2-5]);', re.I)
GROK_WORD_RE = re.compile(r'(?<![A-Za-z0-9])Grok(?![A-Za-z0-9])')
EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
PHONE_RE = re.compile(r'(?<!\d)(?:\+?1[\s.\-]*)?(?:\(?\d{3}\)?[\s.\-]*)\d{3}[\s.\-]*\d{4}(?!\d)')
DENVER_RE = re.compile(r'\bDenver\b.{0,40}\b(?:CO|Colorado)\b|\b(?:CO|Colorado)\b.{0,40}\bDenver\b|\b802\d{2}\b', re.I)
NOINDEX_META_RE = re.compile(r'<meta\b[^>]*\brobots\b[^>]*>', re.I)
PREVIEW_WORD_RE = re.compile(r'\bPreview\b')
BANNER_BLOCK_RE = re.compile(
    r'<([A-Za-z][A-Za-z0-9]*)\b[^>]*class=["\'][^"\']*preview-banner[^"\']*["\'][^>]*>(.*?)</\1>',
    re.I | re.S,
)
# sha256 of known private emails (lowercase) and phone digit forms. Not the values.
PRIVATE_EMAIL_HASHES = {
    '67780f8474807c9cebdc1f89fa17a4dc8c7c29fa8a9036f34ed378dc0214b267',
    '4e5fa5feb3efc43eb6526cedf6a2036afbc25862a581cae8d5cfd7acbbe8a1ee',
}
# Operator mailbox allowed only on start.html / /start (hash only; value is never printed).
START_ONLY_EMAIL_HASHES = {
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
    """Lexical relative path for messages (does not follow symlinks)."""
    try:
        return p.relative_to(root).as_posix()
    except ValueError:
        return p.name


def lexical_inside(room: Path, p: Path) -> bool:
    try:
        relp = p.relative_to(room)
    except ValueError:
        return False
    return '..' not in relp.parts


def target_escapes(target: str) -> bool:
    """True if a room-relative target is absolute or climbs out with .."""
    if not target:
        return True
    if target.startswith('/') or target.startswith('\\'):
        return True
    if len(target) >= 2 and target[1] == ':':
        return True
    parts = Path(target).parts
    return '..' in parts or parts[:1] == ('..',)


def safe_under_room(room: Path, p: Path) -> bool:
    """True if p is a real (non-symlink) file whose resolve() stays in room."""
    if p.is_symlink():
        return False
    if not p.exists() or not p.is_file():
        return False
    try:
        p.resolve().relative_to(room.resolve())
    except (ValueError, OSError):
        return False
    return True


def walk_room(room: Path) -> tuple[list[Path], list[str]]:
    """Safe walk: no follow-symlinks. Returns (files, path-error messages)."""
    files: list[Path] = []
    errors: list[str] = []
    room_r = room.resolve()
    for dirpath, dirnames, filenames in os.walk(room, followlinks=False):
        dp = Path(dirpath)
        if any(part in SKIP_DIR_NAMES for part in dp.parts):
            dirnames[:] = []
            continue
        for d in list(dirnames):
            child = dp / d
            if d in SKIP_DIR_NAMES:
                dirnames.remove(d)
                continue
            if child.is_symlink():
                errors.append('symlink directory rejected: %s' % rel(room, child))
                dirnames.remove(d)
        for fn in filenames:
            child = dp / fn
            if child.is_symlink():
                errors.append('symlink rejected: %s' % rel(room, child))
                continue
            if not child.is_file():
                continue
            try:
                child.resolve().relative_to(room_r)
            except (ValueError, OSError):
                errors.append('path escapes the room root: %s' % rel(room, child))
                continue
            files.append(child)
    return files, errors


def iter_files(room: Path, *, ext: set[str] | None = None, names: set[str] | None = None,
               path_errors: list[str] | None = None):
    files, errors = walk_room(room)
    if path_errors is not None:
        path_errors.extend(errors)
    for p in files:
        if names and p.name in names:
            yield p
            continue
        if ext and p.suffix.lower() in ext:
            yield p


def public_copy_files(room: Path, path_errors: list[str] | None = None):
    for p in iter_files(room, ext=PUBLIC_COPY_EXT, names=PUBLIC_COPY_NAMES, path_errors=path_errors):
        if p.name == 'FACTORY.lock':
            continue
        yield p


def text_scan_files(room: Path, path_errors: list[str] | None = None):
    for p in iter_files(room, ext=TEXT_SCAN_EXT, path_errors=path_errors):
        yield p


def html_files(room: Path, path_errors: list[str] | None = None) -> list[Path]:
    return sorted(
        p for p in iter_files(room, ext={'.html'}, path_errors=path_errors)
    )


def is_start_path(room: Path, p: Path) -> bool:
    r = rel(room, p).lower()
    return r in {'start.html', 'start'} or r.endswith('/start.html') or r == 'start/index.html'


def page_rel(room: Path, p: Path) -> str:
    return rel(room, p)


def banner_text(html: str) -> list[str]:
    """Visible text of each .preview-banner element, including child tags."""
    out = []
    for _tag, inner in BANNER_BLOCK_RE.findall(html):
        text = re.sub(r'<[^>]+>', '', inner)
        text = re.sub(r'\s+', ' ', text).strip()
        out.append(text)
    return out


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


def _add_host(hosts: set[str], raw: str) -> None:
    d = (raw or '').strip().lower()
    d = d.split('://', 1)[-1].split('/', 1)[0]
    if not d:
        return
    hosts.add(d)
    if d.startswith('www.'):
        hosts.add(d[4:])
    else:
        hosts.add('www.' + d)


def room_hosts(room: Path, site: dict | None, factory: Path | None = None) -> set[str]:
    """Internal hosts from CNAME, site.json domain, and rooms.json only. Never sitemap locs."""
    hosts: set[str] = set()
    cname = room / 'CNAME'
    if cname.is_file() and not cname.is_symlink() and safe_under_room(room, cname):
        line = cname.read_text(encoding='utf-8', errors='replace').strip().splitlines()
        if line:
            _add_host(hosts, line[0])
    if site and isinstance(site.get('domain'), str) and site['domain']:
        _add_host(hosts, site['domain'])
    if factory is not None and isinstance(site, dict) and isinstance(site.get('siteId'), str):
        domain = rooms_domain(factory, site['siteId'])
        if domain:
            _add_host(hosts, domain)
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
    if parsed.scheme and parsed.scheme not in ('http', 'https', ''):
        return 'external'
    if parsed.scheme in ('http', 'https'):
        host = (parsed.netloc or '').lower()
        if host not in hosts:
            return 'external'
        path = parsed.path
    else:
        path = parsed.path if parsed.scheme == '' else parsed.path
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


def normalize_pretty(room: Path, target: str) -> str:
    """Map pretty paths (/oahu, /) to name.html when that file exists in the room."""
    if not target or target == 'external':
        return target
    if target_escapes(target):
        return target
    if not Path(target).suffix and safe_under_room(room, room / (target + '.html')):
        return (target + '.html')
    return target


def resolve_local(room: Path, target: str) -> bool:
    if not target or target == 'external' or target_escapes(target):
        return False
    cand = room / target
    if cand.is_symlink():
        return False
    if safe_under_room(room, cand):
        return True
    if not Path(target).suffix:
        return resolve_local(room, target + '.html')
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

    walk_files, walk_errs = walk_room(room)
    for e in walk_errs:
        err('path', e)

    hosts = room_hosts(room, site if isinstance(site, dict) else None, factory)

    # 1. HTML structure and internal links (all .html under the room, not only the root)
    html_pages = sorted(p for p in walk_files if p.suffix.lower() == '.html')
    if not html_pages:
        err('html', 'no *.html files in the room')
    for p in html_pages:
        rname = page_rel(room, p)
        text = p.read_text(encoding='utf-8', errors='replace')
        parser = PageParser()
        try:
            parser.feed(text)
            parser.close()
        except Exception as e:
            err('html', '%s: parse error: %s' % (rname, e))
            continue
        for e in parser.parse_errors:
            err('html', '%s: %s' % (rname, e))
        if not parser.has_doctype and not text.lstrip().lower().startswith('<!doctype'):
            err('html', '%s: missing doctype' % rname)
        if parser.dup_ids:
            err('html', '%s: duplicate id(s): %s' % (rname, ', '.join(parser.dup_ids)))
        for kind, url, tag in parser.refs:
            target = local_target(url, hosts)
            if target is None or target == 'external':
                continue
            if target_escapes(target):
                err('path', '%s: internal %s on <%s> escapes the room root' % (rname, kind, tag))
                continue
            if not resolve_local(room, target):
                err('links', '%s: broken internal %s on <%s>: %s (resolved %s)' % (rname, kind, tag, url, target))

    if isinstance(site, dict):
        for jpath, val in walk_local_paths(site):
            rel_path = val.split('?', 1)[0].lstrip('/')
            if not rel_path:
                continue
            if target_escapes(rel_path):
                err('path', 'site.json %s path escapes the room root' % jpath)
                continue
            if not resolve_local(room, rel_path):
                err('links', 'site.json %s path missing: %s' % (jpath, val))

    # 2. Sitemap + robots (lifted rooms)
    sm_path = room / 'sitemap.xml'
    indexable: list[str] = []
    noindex_pages: list[str] = []
    for p in html_pages:
        rname = page_rel(room, p)
        text = p.read_text(encoding='utf-8', errors='replace')
        if has_noindex(text):
            noindex_pages.append(rname)
        else:
            indexable.append(rname)

    if expect_indexable:
        if not sm_path.is_file() or sm_path.is_symlink():
            if not any(f.code == 'path' and 'sitemap.xml' in f.msg for f in findings):
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
                raw_loc = loc.strip()
                t = local_target(raw_loc, hosts)
                if t is None or t == 'external':
                    err('sitemap', 'sitemap <loc> is not this room: %s' % raw_loc)
                    continue
                if target_escapes(t):
                    err('path', 'sitemap <loc> escapes the room root: %s' % raw_loc)
                    continue
                t = normalize_pretty(room, t)
                if not resolve_local(room, t):
                    err('sitemap', 'sitemap <loc> is missing in the room: %s' % raw_loc)
                    continue
                sm_paths.add(t)
        for name in indexable:
            if name not in sm_paths:
                err('sitemap', 'indexable page missing from sitemap.xml: %s' % name)
        robots_path = room / 'robots.txt'
        if not robots_path.is_file() or robots_path.is_symlink():
            if not robots_path.is_file():
                err('robots', 'robots.txt is missing')
        else:
            rules = parse_robots_star(robots_path.read_text(encoding='utf-8', errors='replace'))
            allows = [v for k, v in rules if k == 'allow']
            disallows = [v for k, v in rules if k == 'disallow']
            if '/' not in allows:
                err('robots', 'robots.txt User-agent: * group must include Allow: /')
            # Empty Disallow: means allow all; only Disallow: / is a blanket deny.
            if '/' in disallows:
                err('robots', 'robots.txt User-agent: * group must not blanket-Disallow: /')

    # 3. typography + Grok (public copy only; skip stamped shell)
    skip_copy = {'FACTORY.lock'}
    for p in walk_files:
        if p.name in skip_copy:
            continue
        if p.suffix.lower() not in PUBLIC_COPY_EXT and p.name not in PUBLIC_COPY_NAMES:
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
    for p in walk_files:
        if p.suffix.lower() not in TEXT_SCAN_EXT:
            continue
        text = p.read_text(encoding='utf-8', errors='replace')
        rname = rel(room, p)
        for i, line in enumerate(text.splitlines(), 1):
            for em in EMAIL_RE.findall(line):
                digest = sha256_text(em.lower())
                if digest in PRIVATE_EMAIL_HASHES:
                    err('pii', '%s:%d: private email' % (rname, i))
                elif digest in START_ONLY_EMAIL_HASHES and not is_start_path(room, p):
                    err('pii', '%s:%d: operator email is only allowed on /start' % (rname, i))
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
            if Path(name).name not in allowed_noindex:
                err('noindex', '%s has a noindex robots meta; only 404.html and report.html may' % name)
        for name in ('404.html', 'report.html'):
            root_page = room / name
            if safe_under_room(room, root_page) and name not in noindex_pages:
                err('noindex', '%s must keep noindex, nofollow' % name)
        for p in html_pages:
            rname = page_rel(room, p)
            text = p.read_text(encoding='utf-8', errors='replace')
            banners = banner_text(text)
            for body in banners:
                if re.search(r'Preview only', body, re.I):
                    err('banner', '%s preview-banner says Preview only' % rname)
                elif body and not body.startswith('Beta:'):
                    err('banner', '%s preview-banner must start with Beta:' % rname)
            for i, line in enumerate(text.splitlines(), 1):
                if not PREVIEW_WORD_RE.search(line):
                    continue
                stripped = line.strip()
                if re.search(r'class=["\'][^"\']*preview', stripped, re.I) and not re.search(r'>\s*[^<]*Preview', stripped):
                    if not PREVIEW_WORD_RE.search(re.sub(r'\b(?:class|id)=["\'][^"\']*["\']', '', stripped)):
                        continue
                if PREVIEW_WORD_RE.search(stripped):
                    without_attrs = re.sub(r'\b(?:class|id|href|src)=["\'][^"\']*["\']', '', stripped)
                    if PREVIEW_WORD_RE.search(without_attrs):
                        err('banner', '%s:%d: leftover Preview copy' % (rname, i))

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
                if target_escapes(fn):
                    err('path', 'FACTORY.lock path escapes the room root')
                    continue
                rp = room / fn
                if rp.is_symlink():
                    err('path', 'FACTORY.lock path is a symlink: %s' % fn)
                    continue
                if not safe_under_room(room, rp):
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
