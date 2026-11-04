#!/usr/bin/env python3
"""Topic activity rule (TOPIC_ROOMS_PLAN / ACTIVITY_RULE copy) with the per-wave approval gate. Pure functions, Python
stdlib only, no I/O: no runner calls this and nothing writes its output anywhere yet.

Counted post: written by a verified human account that was at least 7 days old when it posted. Steward posts and AI
posts never count, whatever the account says about itself.

Approval: a topic row may carry an approval record (approvedWave, approvedBy, approvedAt). It is valid only when
the row carries no approvalPrereq gate (e.g. "trademark-check": wave approval stays blocked until that check clears
and the field is removed in a reviewed commit), approvedWave is a strict integer >= 1 (not 0 or negative, not bool, float, string, list, dict or None) that is in the approved wave list
(topics/approved_waves.json, one batch approval per wave; only strict-integer entries count), approvedBy is a
non-empty string and approvedAt is a zoned timestamp not in the future. The list is empty tonight. Removing a wave from
the list (or a row losing its record) fails closed: nothing in that wave can be active.

  hidden   -> eligible  meets the active rule (20+ counted posts from 5+ distinct people inside 14 days), no valid approval
  hidden   -> active    meets the active rule and has a valid approval (a wave approved ahead of time)
  eligible -> active    has a valid approval AND still meets the active rule at that moment (a stale approved topic
                        stays eligible, or drops to hidden under the 30-day rule, and is never indexed)
  eligible -> hidden    fewer than 3 counted posts in 30 days while still unapproved
  active   -> quiet     fewer than 3 counted posts in 30 days: back out of search (noindex, out of the sitemap), still
                        open to read and post, badge "Quiet lately. New posts welcome."
  quiet    -> active    meets the active rule again; re-gated by the topic's EXISTING approval (no new wave approval)
  active/quiet -> archived   0 counted posts in 90 days (read-only, noindex, out of the sitemap; nothing is deleted)
  archived -> active    meets the active rule again AND has a FRESH wave approval: approvedAt strictly later than
                        the row's archivedAt (stamped by apply() on entry into archived; nothing else is cleared)
  archived -> eligible  meets the active rule again on the old (pre-archive) approval or none: waits for a fresh
                        wave approval. A row that carries archivedAt keeps needing that fresh approval on every later
                        run (eligible -> active too), so a stale approval never sneaks through one run later.
  no valid approval     an active topic drops to eligible; a quiet or archived topic that meets the active rule goes
                        to eligible, not active. Nothing is indexed without a valid approval.

Quiet vs rested (owner decision, 2026-11-04): a quiet topic returns on its EXISTING approval; a rested (archived) topic
needs a fresh wave approval given after it was archived. Quiet rows never get archivedAt. A topic that went quiet and
then archived is a rested topic. A malformed archivedAt, or an archived row without one (legacy), fails closed.
  hold     -> hold      manual only (never rendered, never changed by this rule)

Only `active` is indexable and sitemap-eligible, and only when the hub itself is not under the hub-wide noindex (lifted
for the go-live on 2026-11-04; no topic is active yet, so the sitemap lists 0 topics). Every other status is
noindex,nofollow.

A doorway domain redirects 302 to the topic until the topic has been active for 60 days since activatedAt, then 301.
activatedAt restarts on every (re)entry into active, so a quiet or archived topic that reopens starts a new 60-day clock.
archivedAt is set on every entry into archived (a later re-archive moves it forward, so an approval from before the new
rest is stale again) and is otherwise left as it is.
"""
from datetime import datetime, timedelta, timezone

STATUSES = ('hidden', 'eligible', 'active', 'quiet', 'archived', 'hold')
APPROVAL_FIELDS = ('approvedWave', 'approvedBy', 'approvedAt')
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


def approved(topic, approved_waves, now):
    """True when the row's approval record is complete, its wave is on the approved wave list and, for a row that has
    rested (archivedAt set, or status archived), approvedAt is strictly later than archivedAt."""
    if topic.get('approvalPrereq') is not None:  # an open prerequisite (e.g. trademark-check) blocks approval outright
        return False
    wave, by, at = (topic.get(k) for k in APPROVAL_FIELDS)
    # strict int only: bool is an int subclass, 1.0 == 1, and a list/dict wave must not raise
    if type(wave) is not int or wave < 1 or not any(type(w) is int and w == wave for w in (approved_waves or ())):
        return False
    if not isinstance(by, str) or not by.strip():
        return False
    try:
        at = parse_ts(at)
    except (TypeError, ValueError):
        return False
    if at is None or at > parse_ts(now):
        return False
    # Rested topics need a fresh approval: once a row has been archived, only an approval given strictly after
    # archivedAt counts. A malformed archivedAt, or an archived row that lacks one, fails closed.
    if topic.get('archivedAt') is not None or topic.get('status') == 'archived':
        try:
            rested = parse_ts(topic.get('archivedAt'))
        except (TypeError, ValueError):
            return False
        if rested is None or at <= rested:
            return False
    return True


def next_status(status, stats, now, is_approved=False, last_counted=None):
    """The status a topic should have now. stats: output of counts() (posts90d optional: derived from lastCountedPostAt).
    is_approved: approved(topic, approved_waves, now)."""
    if status not in STATUSES:
        raise ValueError('unknown status %r' % (status,))
    if status == 'hold':
        return 'hold'
    rule = meets_active(stats)
    if status in ('hidden', 'eligible'):
        if is_approved and rule:  # the bar is re-checked at the moment of activation, approval alone is not enough
            return 'active'
        if rule:
            return 'eligible'
        if status == 'eligible' and stats['posts30d'] < QUIET_POSTS:
            return 'hidden'
        return status
    if status in ('quiet', 'archived') and rule:
        return 'active' if is_approved else 'eligible'
    if status == 'archived':
        return 'archived'
    now = parse_ts(now)
    last = parse_ts(stats.get('lastCountedPostAt', last_counted))
    p90 = stats.get('posts90d')
    if p90 == 0 or last is None or now - last >= timedelta(days=ARCHIVE_DAYS):
        return 'archived'
    if stats['posts30d'] < QUIET_POSTS:
        return 'quiet'
    if status == 'active' and not is_approved:
        return 'eligible'
    return 'active' if status == 'active' else 'quiet'


def apply(topic, posts, now, approved_waves=()):
    """Return a NEW topic row (input untouched) with fresh stats, status, activatedAt, archivedAt and stewardOnly."""
    stats = counts(posts, now)
    out = dict(topic)
    old = topic['status']
    new = next_status(old, stats, now, approved(topic, approved_waves, now))
    for k in ('posts14d', 'distinctPosters14d', 'posts30d', 'lastCountedPostAt'):
        out[k] = stats[k]
    out['status'] = new
    if new == 'active' and old != 'active':
        out['activatedAt'] = iso(parse_ts(now))  # a (re)opening starts a new 60-day clock
    if new == 'archived' and old != 'archived':
        out['archivedAt'] = iso(parse_ts(now))  # rest starts: only an approval given after this counts again
    elif old == 'archived' and topic.get('archivedAt') is None:
        out['archivedAt'] = iso(parse_ts(now))  # legacy archived row with no stamp: stamp it so the old approval stays stale
    out['stewardOnly'] = new in ('archived', 'hold')
    return out


def robots(status, hub_noindex=True):
    if hub_noindex or status != 'active':
        return NOINDEX
    return INDEX


def sitemap_eligible(status, hub_noindex=True):
    return (not hub_noindex) and status == 'active'


def rendered(status):
    return status != 'hold'


def read_only(status):
    return status in ('archived', 'hold')


def badge(status):
    return QUIET_BADGE if status == 'quiet' else None


def doorway_status(topic, now):
    """HTTP status a doorway domain should answer with: 302 until the topic has been active 60 days, then 301."""
    if topic['status'] == 'active':
        since = parse_ts(topic.get('activatedAt'))
        if since is not None and parse_ts(now) - since >= timedelta(days=PERMANENT_AFTER_DAYS):
            return 301
    return 302
