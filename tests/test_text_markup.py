from __future__ import annotations

import unittest

from nonebot_plugin_receipts.render_types import NativeTextStyle
from nonebot_plugin_receipts.text_markup import (
    effective_native_width,
    encode_styled_native_text,
    native_text_style_for_heading,
    parse_styled_lines,
    wrap_native_text,
)


class TextMarkupTestCase(unittest.TestCase):
    def test_parse_styled_lines_supports_headings_and_escape(self) -> None:
        lines = parse_styled_lines("# Title\n\\# Literal\nplain")

        self.assertEqual(lines[0].heading_level, 1)
        self.assertEqual(lines[0].text, "Title")
        self.assertEqual(lines[1].heading_level, 0)
        self.assertEqual(lines[1].text, "# Literal")
        self.assertEqual(lines[2].heading_level, 0)
        self.assertEqual(lines[2].text, "plain")

    def test_parse_styled_lines_preserves_blank_lines(self) -> None:
        lines = parse_styled_lines("first\n\nsecond")

        self.assertEqual([line.text for line in lines], ["first", "", "second"])
        self.assertEqual([line.heading_level for line in lines], [0, 0, 0])

    def test_parse_styled_lines_caps_heading_level_at_six(self) -> None:
        lines = parse_styled_lines("###### six\n####### seven")

        self.assertEqual(lines[0].heading_level, 6)
        self.assertEqual(lines[1].heading_level, 0)
        self.assertEqual(lines[1].text, "####### seven")

    def test_wrap_native_text_counts_non_ascii_as_double_width(self) -> None:
        wrapped = wrap_native_text("A中B国", 4)
        self.assertEqual(wrapped, ["A中B", "国"])

    def test_native_text_style_mapping(self) -> None:
        self.assertEqual(
            native_text_style_for_heading(1),
            NativeTextStyle(width_multiplier=2, height_multiplier=2, bold=True),
        )
        self.assertEqual(
            native_text_style_for_heading(4),
            NativeTextStyle(width_multiplier=1, height_multiplier=1, bold=True),
        )
        self.assertEqual(
            native_text_style_for_heading(6),
            NativeTextStyle(),
        )

    def test_effective_native_width_respects_width_multiplier(self) -> None:
        style = NativeTextStyle(width_multiplier=2, height_multiplier=1, bold=True)
        self.assertEqual(effective_native_width(32, style), 16)

    def test_encode_styled_native_text_emits_style_commands(self) -> None:
        encoded = encode_styled_native_text(parse_styled_lines("# Title\nBody"), 32)

        self.assertIn(b"\x1bE\x01", encoded)
        self.assertIn(b"\x1d!\x11", encoded)
        self.assertIn(b"\x1bE\x00", encoded)
        self.assertIn(b"Title", encoded)
        self.assertIn(b"Body", encoded)


if __name__ == "__main__":
    unittest.main()
