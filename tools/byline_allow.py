#!/usr/bin/env python3
"""Narrow author-byline allowlist for Jebb Dykstra (decision 2026-11-05 MT).

Author bylines are approved in every clone room. Operator / provider / agent /
appeal / reviewer / legal lines, meta author tags, JSON-LD publisher and
provider, footers, attributes, steward-pill titles and llms.txt operator lines
must still name SubX, LLC and must fail if his personal name appears there.
Private-contact checks (jebb emails, j@subx.it, 310-428-9218, Denver
registered-agent address) are unchanged and are not handled here.

What may be masked (Key 1 E1-E4, tightened 2026-11-05):
  * Only visible text nodes. Nothing inside a <...> tag (attributes such as
    title, href, data-author, content) and nothing inside <!--...--> comments,
    <script> or <style> is ever masked.
  * Only inside a qualifying element: p, span, em or strong. Never footer,
    body, section, header, address, div, li or any other element. The
    qualifying element is the outermost element of the unbroken run of
    p/span/em/strong elements that wraps the phrase.
  * That element's visible text must START with the phrase and be at most
    MAX_VISIBLE (80) characters, must not contain a role word (operated,
    reviewer, legal, agent, provider, publisher, appeal, contact, owner...),
    and at most ONE phrase is masked per qualifying element.
  * Every element that holds any part of the phrase must be p/span/em/strong,
    must not be hidden (hidden attribute, aria-hidden, inline display:none or
    visibility:hidden, or class hidden / sr-only / visually-hidden, on the
    element or any ancestor), and if it has a class attribute that attribute must
    contain the exact whitespace-separated token "byline".
  * No ancestor may be footer, address, head, title, a, button, label,
    select, option or textarea.
  * The phrase is "By Jebb Dykstra" or "By Jebb Dykstra, Juno, Vesta and
    Iris" with a capital B and a word boundary after the last name, so
    "Dykstrafoo" and mid-sentence "Made by Jebb Dykstra" never match. Spaces
    in the phrase may be plain whitespace, &nbsp;, &#160; or &#xA0;.

Everything else that matches jebb|dykstra (after stripping the
jebbdykstra99/subx-factory repo path) is a hit.

Not in scope here: F1 (JSON-LD Article author), F2 (spinup_render, spinup and
topics tests that still ban "jebb").
"""
from __future__ import annotations

import re

REPO_PATH = "jebbdykstra99/subx-factory"

MAX_VISIBLE = 80
ALLOWED_TAGS = frozenset({"p", "span", "em", "strong"})
DENY_ANCESTORS = frozenset(
    {"footer", "address", "head", "title", "a", "button", "label", "select", "option", "textarea"}
)
VOID_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
     "param", "source", "track", "wbr"}
)

# Capital-B "By" only, word boundary on both ends (E4).
# Whitespace inside the phrase may also be written as &nbsp;, &#160; or &#xA0; (G3).
_WS = r"(?:\s|&nbsp;|&#160;|&#[xX][aA]0;)"
BYLINE_PHRASE = re.compile(
    r"(?<![\w])By" + _WS + r"+Jebb" + _WS + r"+Dykstra"
    r"(?:" + _WS + r"*," + _WS + r"*Juno" + _WS + r"*," + _WS + r"*Vesta" + _WS + r"+and" + _WS + r"+Iris)?"
    r"(?![\w])"
)

ROLE_WORDS = re.compile(
    r"operat|review|legal|agent|provid|publish|appeal|contact|owner|counsel|"
    r"attorney|registered|takedown|copyright|founder|ceo|llc",
    re.I,
)

NAME_HIT = re.compile(r"jebb|dykstra", re.I)

_ATTRS = r"""(?:[^>"']|"[^"]*"|'[^']*')*"""
TOKEN = re.compile(
    r"(?P<comment><!--.*?(?:-->|\Z))"
    r"|(?P<raw><(?P<rawtag>script|style)\b" + _ATTRS + r">.*?(?:</(?P=rawtag)\s*>|\Z))"
    r"|(?P<decl><[!?]" + _ATTRS + r">)"
    r"|(?P<close></(?P<ctag>[A-Za-z][\w:-]*)\s*>)"
    r"|(?P<open><(?P<otag>[A-Za-z][\w:-]*)(?P<attrs>" + _ATTRS + r")>)",
    re.S | re.I,
)
CLASS_ATTR = re.compile(r"""(?:^|\s)class\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))""", re.I)
# Hidden: the hidden attribute, aria-hidden="true", or inline style display:none /
# visibility:hidden (G1). Class tokens below also count as hidden (G4). Checked on the
# qualifying element, every element holding the phrase, and every ancestor.
HIDDEN_ATTR = re.compile(
    r"""(?:^|\s)(?:hidden(?:\s|=|/|$)|aria-hidden\s*=\s*["']?true"""
    r"""|style\s*=\s*["'][^"']*(?:display\s*:\s*none|visibility\s*:\s*hidden))""",
    re.I,
)
HIDDEN_CLASSES = frozenset({"hidden", "sr-only", "visually-hidden"})


class _El:
    __slots__ = ("tag", "attrs", "parent", "open_end", "close_start", "classes", "hidden")

    def __init__(self, tag, attrs, parent, open_end):
        self.tag = tag
        self.attrs = attrs
        self.parent = parent
        self.open_end = open_end
        self.close_start = None
        m = CLASS_ATTR.search(attrs)
        self.classes = None if m is None else (m.group(1) or m.group(2) or m.group(3) or "").split()
        self.hidden = bool(HIDDEN_ATTR.search(attrs)) or bool(
            self.classes and HIDDEN_CLASSES.intersection(c.lower() for c in self.classes))


def _parse(text: str):
    """Return (elements, text_nodes). Text nodes are (start, end) raw spans of
    visible text only; tags, comments, declarations, script and style are skipped."""
    els: list[_El] = []
    texts: list[tuple[int, int]] = []
    stack: list[_El] = []
    pos = 0
    n = len(text)
    while pos < n:
        lt = text.find("<", pos)
        if lt < 0:
            texts.append((pos, n))
            break
        m = TOKEN.match(text, lt)
        if m is None:
            # A lone "<" that does not start a tag is text.
            nxt = text.find("<", lt + 1)
            end = n if nxt < 0 else nxt
            texts.append((pos, end))
            pos = end
            continue
        if lt > pos:
            texts.append((pos, lt))
        if m.group("open"):
            tag = m.group("otag").lower()
            attrs = m.group("attrs") or ""
            if tag not in VOID_TAGS and not attrs.rstrip().endswith("/"):
                el = _El(tag, attrs, stack[-1] if stack else None, m.end())
                els.append(el)
                stack.append(el)
        elif m.group("close"):
            tag = m.group("ctag").lower()
            for i in range(len(stack) - 1, -1, -1):
                if stack[i].tag == tag:
                    stack[i].close_start = m.start()
                    del stack[i:]  # intermediate unclosed elements stay unclosed
                    break
        pos = m.end()
    return els, texts


def _visible(src: str, texts, a: int, b: int):
    """Visible chars between raw offsets a and b as (string, raw positions)."""
    chars: list[str] = []
    raw: list[int] = []
    for s, e in texts:
        if e <= a or s >= b:
            continue
        for i in range(max(s, a), min(e, b)):
            chars.append(src[i])
            raw.append(i)
    return "".join(chars), raw


def _ancestors(el):
    p = el.parent
    while p is not None:
        yield p
        p = p.parent


def _byline_positions(text: str) -> list[int]:
    """Raw offsets of visible chars that belong to an allowed byline phrase."""
    els, texts = _parse(text)
    out: list[int] = []
    for top in els:
        if top.tag not in ALLOWED_TAGS or top.close_start is None:
            continue
        if top.parent is not None and top.parent.tag in ALLOWED_TAGS:
            continue  # not the outermost of its p/span/em/strong run
        if any(a.tag in DENY_ANCESTORS or a.hidden for a in _ancestors(top)):
            continue
        vis, raw = _visible(text, texts, top.open_end, top.close_start)
        lead = len(vis) - len(vis.lstrip())
        body = vis.strip()
        if not body or len(body) > MAX_VISIBLE:
            continue
        m = BYLINE_PHRASE.match(vis, lead)
        if m is None:
            continue
        if ROLE_WORDS.search(vis[m.end():]):
            continue
        span = raw[m.start():m.end()]
        lo, hi = span[0], span[-1]
        inner = [e for e in els if e.open_end >= top.open_end and
                 (e.close_start is None or e.close_start <= top.close_start) and
                 e.open_end <= top.close_start]
        okay = True
        for e in inner:
            if e.close_start is None:
                okay = False  # unclosed markup inside the byline: never mask
                break
            touches = any(e.open_end <= p < e.close_start for p in (lo, hi)) or (
                lo < e.open_end and e.close_start <= hi)
            if not touches:
                continue
            if e.tag not in ALLOWED_TAGS or e.hidden:
                okay = False
                break
            if e.classes is not None and "byline" not in e.classes:
                okay = False
                break
        if okay:
            out.extend(span)  # exactly one phrase per qualifying element
    return out


def mask_allowed_bylines(text: str) -> str:
    """Replace allowed byline phrase chars with spaces. Tags, attributes and
    comments are never masked."""
    if not text:
        return text
    pos = _byline_positions(text)
    if not pos:
        return text
    buf = list(text)
    for i in pos:
        if not buf[i].isspace():
            buf[i] = " "
    return "".join(buf)


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


def is_name_clean(text: str, *, allow_reserved_handle_jebb: bool = False) -> bool:
    """True when no jebb|dykstra remains after masking allowed bylines.
    Name check only: private-contact checks live in the callers."""
    hits = find_name_hits(text)
    if allow_reserved_handle_jebb:
        hits = [h for h in hits if not re.search(r"\(admin\|moderator\|official\|subx\|jebb\)", h, re.I)]
    return not hits


def assert_fixture_matrix() -> None:
    clean = is_name_clean
    assert clean('<p class="byline"><em>By Jebb Dykstra, Juno, Vesta and Iris</em></p>')
    assert clean('<p class="byline">By Jebb Dykstra</p>')
    assert clean("<p><em>By Jebb Dykstra, Juno, Vesta and Iris</em></p>")
    assert clean("<p><em>By Jebb Dykstra</em></p>")

    story = (
        '<p><em>By Jebb Dykstra, Juno, Vesta and Iris</em>'
        '<span class="whomark-slot" data-whomark="hybrid" hidden></span> '
        '<span class="post-steward-pill" title="Made by Jebb Dykstra, a person, '
        'with AI agents Juno, Vesta and Iris, run by SubX, LLC.">Human + AI</span></p>'
    )
    assert not clean(story), "steward-pill title with Jebb must fail"
    story_ok = story.replace(
        "Made by Jebb Dykstra, a person, with AI agents Juno, Vesta and Iris, run by SubX, LLC.",
        "Human + AI. Operated by SubX, LLC.",
    )
    assert clean(story_ok)

    assert not clean('<meta name="author" content="Jebb Dykstra, Juno, Vesta and Iris">')
    assert not clean('{"publisher": {"@type": "Organization", "name": "Jebb Dykstra"}}')
    assert not clean('{"provider": {"name": "Jebb Dykstra"}}')
    assert not clean("<p>gaichat.com is operated by Jebb Dykstra.</p>")
    assert not clean("<footer>Operator: Jebb Dykstra</footer>")
    assert not clean("Operator: Jebb Dykstra\n# llms.txt")
    assert not clean("<p>Appeals go to Jebb Dykstra at SubX.</p>")
    assert not clean("<p>a human reviewer at Jebb Dykstra</p>")
    assert not clean("<p>Contact Jebb Dykstra for help.</p>")
    assert not clean("<p>This post was written by Jebb Dykstra overnight.</p>")
    assert clean("https://cdn.jsdelivr.net/gh/jebbdykstra99/subx-factory@abc/factory.js")

    # Reviewer leaks (Key 1, 2026-11-05): all must fail.
    assert not clean('<footer class="byline">Operated By Jebb Dykstra</footer>')
    assert not clean('<body class="byline"><p>By Jebb Dykstra</p><p>Operator: Jebb Dykstra</p></body>')
    assert not clean('<div class="byline">By Jebb Dykstra</div>')
    assert not clean("<div>By Jebb Dykstra. Reviewer: By Jebb Dykstra</div>")
    assert not clean("<p>By Jebb Dykstra. Reviewer: By Jebb Dykstra</p>")
    assert not clean('<p class="not-byline">By Jebb Dykstra</p>')
    assert not clean('<p class="byline" data-author="Jebb Dykstra">By Jebb Dykstra</p>')
    assert not clean('<p class="byline"><span href="/u/jebb">By Jebb Dykstra</span></p>')
    assert not clean('<p>By Jebb Dykstra <span title="' + "x" * 130 + ' By Jebb Dykstra">i</span></p>')
    assert not clean("<p>By Jebb Dykstra<!-- By Jebb Dykstra --></p>")
    assert not clean("<p>By Jebb Dykstrafoo</p>")
    # Iris G1-G4 (2026-11-05)
    assert not clean('<p class="byline" style="display:none">By Jebb Dykstra</p>')
    assert not clean('<div style="visibility: hidden"><p class="byline">By Jebb Dykstra</p></div>')
    assert not clean('<p class="byline hidden">By Jebb Dykstra</p>')
    assert not clean('<div class="sr-only"><p>By Jebb Dykstra</p></div>')
    assert clean('<p class="byline">By&nbsp;Jebb&#160;Dykstra</p>')


if __name__ == "__main__":
    assert_fixture_matrix()
    print("byline_allow: fixture matrix ok")
