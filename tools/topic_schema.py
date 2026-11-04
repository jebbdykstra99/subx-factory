#!/usr/bin/env python3
"""A tiny JSON Schema subset validator (stdlib only) for topics/*.schema.json files: type (incl. lists, null), enum,
required, properties, additionalProperties false, pattern, minLength/maxLength, minimum, items, uniqueItems and
format date-time (ISO-8601 with Z or an offset)."""
import re
from datetime import datetime

TYPES = {'string': str, 'integer': int, 'boolean': bool, 'object': dict, 'array': list, 'null': type(None)}


def _is(v, t):
    if t == 'integer':
        return isinstance(v, int) and not isinstance(v, bool)
    return isinstance(v, TYPES[t])


def _dt(s):
    if not re.fullmatch(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(Z|[+-]\d\d:\d\d)$', s):
        return False
    try:
        datetime.fromisoformat(s[:-1] + '+00:00' if s.endswith('Z') else s)
        return True
    except ValueError:
        return False


def _pattern(p):
    """JSON Schema patterns are ECMA-262: '$' (no m flag) means end of string. Python's '$' also matches before a
    trailing newline, so rewrite every unescaped '$' outside a character class to '\\Z'."""
    out, i, cls = [], 0, False
    while i < len(p):
        c = p[i]
        if c == '\\':
            out.append(p[i:i + 2]); i += 2; continue
        if cls:
            cls = c != ']'
        elif c == '[':
            cls = True
        elif c == '$':
            c = '\\Z'
        out.append(c); i += 1
    return re.compile(''.join(out))


def validate(v, sch, where='$'):
    e = []
    if 'enum' in sch and v not in sch['enum']:
        return ['%s: %r not in %s' % (where, v, sch['enum'])]
    if 'type' in sch:
        ts = sch['type'] if isinstance(sch['type'], list) else [sch['type']]
        if not any(_is(v, t) for t in ts):
            return ['%s: expected %s' % (where, '/'.join(ts))]
    if isinstance(v, str):
        if 'pattern' in sch and not _pattern(sch['pattern']).search(v):
            e.append('%s: %r does not match %s' % (where, v, sch['pattern']))
        if len(v) < sch.get('minLength', 0) or len(v) > sch.get('maxLength', 10 ** 9):
            e.append('%s: length %d out of range' % (where, len(v)))
        if sch.get('format') == 'date-time' and not _dt(v):
            e.append('%s: %r is not an ISO-8601 date-time with a zone' % (where, v))
    if _is(v, 'integer') and 'minimum' in sch and v < sch['minimum']:
        e.append('%s: %r < %r' % (where, v, sch['minimum']))
    if isinstance(v, list):
        if sch.get('uniqueItems') and len({repr(x) for x in v}) != len(v):
            e.append('%s: items not unique' % where)
        for i, x in enumerate(v):
            e += validate(x, sch.get('items', {}), '%s[%d]' % (where, i))
    if isinstance(v, dict):
        for k in sch.get('required', []):
            if k not in v:
                e.append('%s: missing %s' % (where, k))
        props = sch.get('properties', {})
        for k, x in v.items():
            if k in props:
                e += validate(x, props[k], '%s.%s' % (where, k))
            elif sch.get('additionalProperties') is False:
                e.append('%s: unknown field %s' % (where, k))
    return e
