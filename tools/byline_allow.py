#!/usr/bin/env python3
"""Narrow author-byline allowlist for Jebb Dykstra (decision 2026-11-05 MT).

Author bylines are approved in every clone room. Operator / provider / agent /
appeal / reviewer / legal lines, meta author tags, JSON-LD publisher and
provider, footers, and llms.txt operator lines must still name SubX, LLC and
must fail if his personal name appears there. Private-contact checks
(jebb emails, j@subx.it, 310-428-9218, Denver registered-agent address) are
unchanged and are not handled here.

Allowed contexts (only):
  1. Visible element whose class token list includes "byline"
     (e.g. <p class="byline"><em>By Jebb Dykstra...</em></p>).
  2. A block whose visible text starts with "By Jebb Dykstra"
     (covers 27chat Story 01-06 co-bylines that omit class="byline").
  3. The exact team co-byline phrase "By Jebb Dykstra, Juno, Vesta and Iris"
     when it appears as that visible byline text (same as 1/2).

"By" is matched with a capital B so mid-sentence "Made by Jebb Dykstra"
(steward-pill titles, prose) is NOT a byline.

Everything else that matches jebb|dykstra (after stripping the
jebbdykstra99/subx-factory repo path) is a hit.
"""
from __future__ import annotations

import re

REPO_PATH = "jebbdykstra99/subx-factory"

# Capital-B "By" only. Optional team co-authors. Names keep their usual casing.
BYLINE_PHRASE = re.compile(
    r"By\s+Jebb\s+Dykstra(?:\s*,\s*Juno\s*,\s*Vesta\s+and\s+Iris)?"
)

BYLINE_EL = re.compile(
    r"<(?P<tag>[a-zA-Z0-9]+)\b([^>]*\bclass\s*=\s*[\"'][^\"']*\bbyline\b[^\"']*[\"'][^>]*)>"
    r"(?P<body>.*?)</(?P=tag)\s*>",
    re.I | re.S,
)

BLOCK = re.compile(
    r"<(?P<tag>p|div|li|h[1-6]|span|em|strong)\b([^>]*)>(?P<body>.*?)</(?P=tag)\s*>",
    re.I | re.S,
)

NAME_HIT = re.compile(r"jebb|dykstra", re.I)
NAME_TOKEN = re.compile(r"Jebb(?:\s+Dykstra)?|Dykstra")

ATTR_OPEN = re.compile(
    r"""\b(?:title|aria-label|alt|content)\s*=\s*(?P<q>["'])(?:(?!(?P=q)).)*$""",
    re.I,
)


def _strip_tags(html: str) -> str:
    t = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    t = re.sub(r"<(script|style)\b.*?</\1\s*>", " ", t, flags=re.I | re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _starts_with_byline(vis: str) -> bool:
    return bool(BYLINE_PHRASE.match(vis))


def _mask(s: str, a: int, b: int) -> str:
    return s[:a] + (" " * (b - a)) + s[b:]


def _in_attr(text: str, pos: int) -> bool:
    win = text[max(0, pos - 120) : pos]
    return ATTR_OPEN.search(win) is not None


def _collect_byline_ranges(text: str, body: str, body_start: int) -> list[tuple[int, int]]:
    ranges = []
    for bm in BYLINE_PHRASE.finditer(body):
        abs_s, abs_e = body_start + bm.start(), body_start + bm.end()
        if _in_attr(text, abs_s):
            continue
        ranges.append((abs_s, abs_e))
        # Also cover any nested markup splits of the same name inside the phrase span.
        for nm in NAME_TOKEN.finditer(body[bm.start() : bm.end()]):
            ranges.append((abs_s + nm.start(), abs_s + nm.end()))
    return ranges


def mask_allowed_bylines(text: str) -> str:
    """Replace allowed byline name spans with spaces. Attributes are never masked."""
    if not text:
        return text
    ranges: list[tuple[int, int]] = []

    for m in BYLINE_EL.finditer(text):
        ranges.extend(_collect_byline_ranges(text, m.group("body"), m.start("body")))

    for m in BLOCK.finditer(text):
        open_tag = text[m.start() : m.start("body")]
        if re.search(r"\bclass\s*=\s*[\"'][^\"']*\bbyline\b", open_tag, re.I):
            continue  # already handled
        vis = _strip_tags(m.group("body"))
        if not _starts_with_byline(vis):
            continue
        ranges.extend(_collect_byline_ranges(text, m.group("body"), m.start("body")))

    out = text
    for a, b in sorted(set(ranges), reverse=True):
        out = _mask(out, a, b)
    return out


def find_name_hits(text: str, *, strip_repo_path: bool = True) -> list[str]:
    """Remaining jebb|dykstra hits after masking allowed bylines."""
    if not text:
        return []
    t = text.replace(REPO_PATH, "") if strip_repo_path else text
    masked = mask_allowed_bylines(t)
    hits = []
    for m in NAME_HIT.finditer(masked):
        lo = max(0, m.start() - 40)
        hi = min(len(masked), m.end() + 40)
        hits.append(masked[lo:hi].replace("\n", " ").strip())
    return hits


def is_clean(text: str, *, allow_reserved_handle_jebb: bool = False) -> bool:
    hits = find_name_hits(text)
    if allow_reserved_handle_jebb:
        kept = []
        for h in hits:
            if re.search(r"\(admin\|moderator\|official\|subx\|jebb\)", h, re.I):
                continue
            kept.append(h)
        hits = kept
    return not hits


def assert_fixture_matrix() -> None:
    assert is_clean('<p class="byline"><em>By Jebb Dykstra, Juno, Vesta and Iris</em></p>')
    assert is_clean('<p class="byline">By Jebb Dykstra</p>')
    assert is_clean("<p><em>By Jebb Dykstra, Juno, Vesta and Iris</em></p>")
    assert is_clean("<p><em>By Jebb Dykstra</em></p>")

    story = (
        '<p><em>By Jebb Dykstra, Juno, Vesta and Iris</em>'
        '<span class="whomark-slot" data-whomark="hybrid" hidden></span> '
        '<span class="post-steward-pill" title="Made by Jebb Dykstra, a person, '
        'with AI agents Juno, Vesta and Iris, run by SubX, LLC.">Human + AI</span></p>'
    )
    assert not is_clean(story), "steward-pill title with Jebb must fail"

    story_ok = story.replace(
        "Made by Jebb Dykstra, a person, with AI agents Juno, Vesta and Iris, run by SubX, LLC.",
        "Human + AI. Operated by SubX, LLC.",
    )
    assert is_clean(story_ok)

    assert not is_clean('<meta name="author" content="Jebb Dykstra, Juno, Vesta and Iris">')
    assert not is_clean('{"publisher": {"@type": "Organization", "name": "Jebb Dykstra"}}')
    assert not is_clean('{"provider": {"name": "Jebb Dykstra"}}')
    assert not is_clean("<p>gaichat.com is operated by Jebb Dykstra.</p>")
    assert not is_clean("<footer>Operator: Jebb Dykstra</footer>")
    assert not is_clean("Operator: Jebb Dykstra\n# llms.txt")
    assert not is_clean("<p>Appeals go to Jebb Dykstra at SubX.</p>")
    assert not is_clean("<p>a human reviewer at Jebb Dykstra</p>")
    assert not is_clean("<p>Contact Jebb Dykstra for help.</p>")
    assert is_clean("https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@abc/factory.js")

    # Mid-sentence lowercase "by" is not a byline
    assert not is_clean("<p>This post was written by Jebb Dykstra overnight.</p>")


if __name__ == "__main__":
    assert_fixture_matrix()
    print("byline_allow: fixture matrix ok")
