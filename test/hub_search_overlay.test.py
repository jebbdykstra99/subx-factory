#!/usr/bin/env python3
"""Search rooms field on the subx.it hub hero (option 2).

Offline checks on the approved files: the field sits above the featured
room in both index.html copies, the overlay is a modal dialog, hub.js
loads rooms.json and handles Escape, and the new CSS rules do not use
#1D9BF0.
"""
from __future__ import annotations

import re
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_COPIES = (
    ROOT / "hub/src/templates/index.html",
    ROOT / "hub/site/index.html",
)
JS_COPIES = (
    ROOT / "hub/src/templates/hub.js",
    ROOT / "hub/site/hub.js",
)
CSS_COPIES = (
    ROOT / "hub/src/templates/hub.css",
    ROOT / "hub/site/hub.css",
)
CSS_MARKER = "/* Search rooms field on the hero"
ACCENT = re.compile(r"#1[Dd]9[Bb][Ff]0")


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


class _IndexScan(HTMLParser):
    """Collect start-tag events with a running source position."""

    def __init__(self, raw: str) -> None:
        super().__init__(convert_charrefs=True)
        self.raw = raw
        self.events: list[tuple[int, str, dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {k: (v or "") for k, v in attrs}
        self.events.append((self.getpos()[0], tag, ad))


def parse_index(path: Path) -> _IndexScan:
    raw = path.read_text(encoding="utf-8")
    parser = _IndexScan(raw)
    parser.feed(raw)
    parser.close()
    return parser


class HubSearchOverlayTest(unittest.TestCase):
    def test_field_exists_above_the_hero_in_both_index_copies(self) -> None:
        for path in INDEX_COPIES:
            with self.subTest(file=rel(path)):
                raw = path.read_text(encoding="utf-8")
                hero = raw.find('id="hub-hero"')
                self.assertNotEqual(hero, -1, f"{rel(path)} is missing #hub-hero")
                # Visible closed fields and their "Search rooms" label sit
                # earlier in the document than the featured room.
                center = raw.find("hub-search-closed-center")
                phone = raw.find("hub-search-closed-hero")
                self.assertNotEqual(center, -1, f"{rel(path)} is missing the center-column field")
                self.assertNotEqual(phone, -1, f"{rel(path)} is missing the phone field")
                self.assertLess(center, hero, f"{rel(path)}: center field must sit above the hero")
                self.assertLess(phone, hero, f"{rel(path)}: phone field must sit above the hero")
                # The closed controls actually say "Search rooms".
                window = raw[min(center, phone):hero]
                self.assertGreaterEqual(window.count("Search rooms"), 2, f"{rel(path)}: Search rooms label missing above the hero")

    def test_overlay_has_dialog_attributes(self) -> None:
        for path in INDEX_COPIES:
            with self.subTest(file=rel(path)):
                scan = parse_index(path)
                dialogs = [
                    ev for ev in scan.events
                    if ev[1] == "div"
                    and ev[2].get("role") == "dialog"
                    and ev[2].get("id") in {"hub-search-popover", "hub-search-sheet"}
                ]
                ids = {ev[2].get("id") for ev in dialogs}
                self.assertEqual(
                    ids,
                    {"hub-search-popover", "hub-search-sheet"},
                    f"{rel(path)}: expected both search dialogs, got {ids}",
                )
                for _line, _tag, ad in dialogs:
                    self.assertEqual(ad.get("aria-modal"), "true", f"{rel(path)} #{ad.get('id')} missing aria-modal")
                    self.assertEqual(ad.get("aria-label"), "Search rooms", f"{rel(path)} #{ad.get('id')} missing aria-label")
                # Scrim and Done are how the overlay closes, besides Escape.
                raw = path.read_text(encoding="utf-8")
                self.assertIn("hub-search-scrim", raw)
                self.assertIn("data-hub-search-close", raw)
                self.assertIn(">Done</button>", raw)

    def test_hub_js_loads_rooms_json_and_handles_escape(self) -> None:
        rooms_re = re.compile(r"getJSON\(\s*(?:'\{\{asset:/rooms\.json\}\}'|'/rooms\.json(?:\?v=[0-9a-f]+)?'|\"[^\"]*rooms\.json[^\"]*\")\s*\)")
        escape_re = re.compile(r"e\.key\s*===\s*['\"]Escape['\"]")
        for path in JS_COPIES:
            with self.subTest(file=rel(path)):
                raw = path.read_text(encoding="utf-8")
                self.assertIn("initHubSearch", raw, f"{rel(path)} is missing initHubSearch")
                self.assertRegex(raw, rooms_re, f"{rel(path)} does not load rooms.json")
                # The search block itself (not an earlier handler) handles Escape.
                block_start = raw.find("function initHubSearch")
                self.assertGreater(block_start, -1)
                block = raw[block_start:]
                self.assertRegex(block, escape_re, f"{rel(path)} search block does not handle Escape")
                self.assertIn("sidebar-search-btn", block)

    def test_new_css_rules_do_not_use_accent_hex(self) -> None:
        for path in CSS_COPIES:
            with self.subTest(file=rel(path)):
                raw = path.read_text(encoding="utf-8")
                self.assertIn(CSS_MARKER, raw, f"{rel(path)} is missing the new search CSS block")
                new_rules = raw[raw.index(CSS_MARKER):]
                hits = ACCENT.findall(new_rules)
                self.assertEqual(hits, [], f"{rel(path)} new CSS rules contain #1D9BF0: {hits}")
                # Search rules are the ones that mention hub-search.
                for m in re.finditer(r"[^{}]*hub-search[^{]*\{[^}]*\}", new_rules, re.I):
                    self.assertIsNone(ACCENT.search(m.group(0)), m.group(0)[:80])


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(HubSearchOverlayTest)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
