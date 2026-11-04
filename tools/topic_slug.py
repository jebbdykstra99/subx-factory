#!/usr/bin/env python3
"""Topic slug validator. A slug is the path segment in <brand.topicPathPrefix><slug>/ (e.g. /t/grand-prix-racing/).

Rules: lowercase ASCII a-z, 0-9 and single hyphens (the whole string: no trailing newline, CR or Unicode lookalike); 3-48 chars; starts and ends with a letter or digit; no "r/"-style
prefix and no Reddit text; not a reserved word. Reserved = topics/reserved.json "system" + "legal" + "platform" + brand words generated
from brand/brand.json (name, shortName, legalEntity first word, primaryDomain labels, and each of those + "-official").

Usage: python3 tools/topic_slug.py SLUG [SLUG ...]   (exit 1 if any is refused)
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLUG_RE = re.compile(r'[a-z0-9](?:[a-z0-9]|-(?=[a-z0-9])){2,47}')  # always fullmatch(): '$' would accept 'abc\n'
REDDIT_RE = re.compile(r'^(r|u)-|reddit|subreddit|^r\Z')


def _word(s):
    return re.sub(r'[^a-z0-9]+', '-', str(s).lower()).strip('-')


def reserved(brand=None, path=None):
    if brand is None:
        brand = json.load(open(os.path.join(ROOT, 'brand', 'brand.json'), encoding='utf-8'))
    r = json.load(open(path or os.path.join(ROOT, 'topics', 'reserved.json'), encoding='utf-8'))
    words = set(r['system']) | set(r['legal']) | set(r.get('platform', []))
    names = {_word(brand.get('name', '')), _word(brand.get('shortName', '')), _word(str(brand.get('legalEntity', '')).split(',')[0])}
    names |= {_word(x) for x in brand.get('aliases', [])}
    dom = str(brand.get('primaryDomain', ''))
    names |= {_word(dom)} | {_word(x) for x in dom.split('.')[:-1]}
    names.discard('')
    words |= names | {n + '-official' for n in names} | {'official-' + n for n in names}
    return words


def errors(slug, brand=None, words=None):
    e = []
    if not isinstance(slug, str):
        return ['slug must be a string']
    if not slug.isascii() or not SLUG_RE.fullmatch(slug):
        e.append('slug %r must be 3-48 chars of a-z, 0-9 and single inner hyphens' % slug)
    if REDDIT_RE.search(slug) or '/' in slug:
        e.append('slug %r looks like a Reddit path or names Reddit' % slug)
    if slug in (words if words is not None else reserved(brand)):
        e.append('slug %r is reserved' % slug)
    return e


def main(argv):
    words = reserved()
    bad = 0
    for s in argv:
        e = errors(s, words=words)
        print('%s: %s' % (s, '; '.join(e) if e else 'ok'))
        bad += bool(e)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
