#!/usr/bin/env python3
"""Topic activity rule (TOPIC_ROOMS_PLAN / ACTIVITY_RULE copy). Pure functions, Python stdlib only, no I/O.

Counted post: written by a verified human account that was at least 7 days old when it posted. Steward posts and AI
posts never count, whatever the account says about itself.

  hidden   -> active    20+ counted posts from 5+ distinct people inside 14 days (the "active rule")
  active   -> quiet     fewer than 3 counted posts in 30 days (stays indexed, badge "Quiet lately. New posts welcome.")
  quiet    -> active    3+ counted posts in 30 days again
  active/quiet -> archived   0 counted posts in 90 days (read-only, noindex, out of the sitemap; nothing is deleted)
  archived -> active    meets the active rule again (auto-reopen)
  hold     -> hold      manual only (never rendered, never changed by this rule)

Hidden and archived (and hold) topics are noindex,nofollow. Only active and quiet topics are sitemap-eligible, and only
when the hub itself is not under the hub-wide noindex (it is tonight, so the sitemap lists 0 topics).

A doorway domain redirects 302 to the topic while the topic is not established, and 301 once the topic has been active
(active or quiet) for 60 days since activatedAt.
"""
from datetime import datetime, timedelta, timezone

STATUSES = ('hidden', 'active', 'quiet', 'archived', 'hold')
ACTIVE_POSTS, ACTIVE_PEOPLE, ACTIVE_DAYS = 20, 5, 14
QUIET_POSTS, QUIET_DAYS = 3, 30
ARCHIVE_DAYS = 90
MIN_ACCOUNT_AGE_DAYS = 7
PERMANENT_AFTER_DAYS = 60
QUIET_BADGE = 'Quiet lately. New posts welcome.'
NOINDEX = 'noindex,nofollow'
INDEX = 'index,follow'


def parse_ts(v):
    """ISO-8601 string (Z or offset) or datetime -> aware datetime in UTC; None stays None."""
    if v is None or v == '':
        return None
    if isinstance(v, datetime):
        dt = v
    else:
        s = str(v)
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        raise ValueError('timestamp without a zone: %r' % (v,))
    return dt.astimezone(timezone.utc)


def iso(dt):
    return None if dt is None else dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def is_counted(post):
    """post: {createdAt, authorUid, authorVerifiedHuman: bool, authorCreatedAt, steward: bool, ai: bool}."""
    if post.get('steward') or post.get('ai') or post.get('authorIsSteward') or post.get('authorIsAi'):
        return False
    if post.get('authorVerifiedHuman') is not True:
        return False
    if not post.get('authorUid'):
        return False
    made, born = parse_ts(post.get('createdAt')), parse_ts(post.get('authorCreatedAt'))
    if made is None or born is None:
        return False
    return made - born >= timedelta(days=MIN_ACCOUNT_AGE_DAYS)


def counts(posts, now):
    """Counted-post stats for the schema fields (posts14d, distinctPosters14d, posts30d, posts90d, lastCountedPostAt)."""
    now = parse_ts(now)
    counted = [p for p in posts if is_counted(p) and parse_ts(p['createdAt']) <= now]
    def within(days):
        return [p for p in counted if now - parse_ts(p['createdAt']) < timedelta(days=days)]
    w14 = within(ACTIVE_DAYS)
    last = max((parse_ts(p['createdAt']) for p in counted), default=None)
    return {'posts14d': len(w14), 'distinctPosters14d': len({p['authorUid'] for p in w14}),
            'posts30d': len(within(QUIET_DAYS)), 'posts90d': len(within(ARCHIVE_DAYS)), 'lastCountedPostAt': iso(last)}


def meets_active(stats):
    return stats['posts14d'] >= ACTIVE_POSTS and stats['distinctPosters14d'] >= ACTIVE_PEOPLE


def next_status(status, stats, now, last_counted=None):
    """The status a topic should have now. stats: output of counts() (posts90d optional: derived from lastCountedPostAt)."""
    if status not in STATUSES:
        raise ValueError('unknown status %r' % (status,))
    if status == 'hold':
        return 'hold'
    if meets_active(stats):
        return 'quiet' if status == 'quiet' and stats['posts30d'] < QUIET_POSTS else 'active'
    if status in ('hidden', 'archived'):
        return status
    now = parse_ts(now)
    last = parse_ts(stats.get('lastCountedPostAt', last_counted))
    p90 = stats.get('posts90d')
    if p90 == 0 or last is None or now - last >= timedelta(days=ARCHIVE_DAYS):
        return 'archived'
    if stats['posts30d'] < QUIET_POSTS:
        return 'quiet'
    return 'active'


def apply(topic, posts, now):
    """Return a NEW topic row (input untouched) with fresh stats, status, activatedAt and stewardOnly."""
    stats = counts(posts, now)
    out = dict(topic)
    old = topic['status']
    new = next_status(old, stats, now)
    for k in ('posts14d', 'distinctPosters14d', 'posts30d', 'lastCountedPostAt'):
        out[k] = stats[k]
    out['status'] = new
    if new in ('active', 'quiet') and old not in ('active', 'quiet'):
        out['activatedAt'] = iso(parse_ts(now))  # a reopen starts a new 60-day clock
    out['stewardOnly'] = new in ('archived', 'hold')
    return out


def robots(status, hub_noindex=True):
    if hub_noindex or status not in ('active', 'quiet'):
        return NOINDEX
    return INDEX


def sitemap_eligible(status, hub_noindex=True):
    return (not hub_noindex) and status in ('active', 'quiet')


def rendered(status):
    return status != 'hold'


def read_only(status):
    return status in ('archived', 'hold')


def badge(status):
    return QUIET_BADGE if status == 'quiet' else None


def doorway_status(topic, now):
    """HTTP status a doorway domain should answer with: 302 until the topic has been active 60 days, then 301."""
    if topic['status'] in ('active', 'quiet'):
        since = parse_ts(topic.get('activatedAt'))
        if since is not None and parse_ts(now) - since >= timedelta(days=PERMANENT_AFTER_DAYS):
            return 301
    return 302
