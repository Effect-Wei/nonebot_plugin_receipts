from __future__ import annotations

import unittest
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, patch

from nonebot_plugin_receipts.config import Config
from nonebot_plugin_receipts.escpos_backend import (
    NATIVE_CHAR_WIDTH_PX,
    render_hybrid_escpos,
)
from nonebot_plugin_receipts.render_types import ReceiptBlock
from nonebot_plugin_receipts.renderer import render_receipt
from nonebot_plugin_receipts.template import ReceiptTemplate, ReceiptTemplateContext

if TYPE_CHECKING:
    from typing import Any


EXPECTED_DIVIDER_CHARS = 48


class RendererIntegrationTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.template_path = str(
            Path(__file__).resolve().parents[1] / "receipt_template.example.json"
        )
        self.context = ReceiptTemplateContext(sender_name="Tester", sender_id="10001")

    async def test_render_receipt_returns_bytes_in_raster_mode(self) -> None:
        config = Config(
            receipt_render_mode="raster",
            receipt_template_path=self.template_path,
        )

        with patch(
            "nonebot_plugin_receipts.renderer.extract_blocks",
            new=AsyncMock(
                return_value=[ReceiptBlock(kind="text", text="# Title\nBody")]
            ),
        ):
            rendered = await render_receipt(cast("Any", []), config, self.context)

        self.assertIsInstance(rendered, bytes)
        self.assertGreater(len(rendered), 0)

    async def test_render_receipt_returns_bytes_in_hybrid_mode(self) -> None:
        config = Config(
            receipt_render_mode="hybrid",
            receipt_template_path=self.template_path,
        )

        with patch(
            "nonebot_plugin_receipts.renderer.extract_blocks",
            new=AsyncMock(
                return_value=[ReceiptBlock(kind="text", text="## Title\nBody")]
            ),
        ):
            rendered = await render_receipt(cast("Any", []), config, self.context)

        self.assertIsInstance(rendered, bytes)
        self.assertGreater(len(rendered), 0)

    async def test_render_receipt_hybrid_uses_48_char_divider(self) -> None:
        config = Config(
            receipt_render_mode="hybrid",
            receipt_template_path=self.template_path,
            receipt_enable_cut=False,
            receipt_feed_lines=0,
        )

        with patch(
            "nonebot_plugin_receipts.renderer.extract_blocks",
            new=AsyncMock(
                return_value=[ReceiptBlock(kind="text", text="# Title\nBody")]
            ),
        ):
            rendered = await render_receipt(cast("Any", []), config, self.context)

        decoded = rendered.decode("gb18030", errors="ignore")
        divider_lines = [
            line for line in decoded.splitlines() if line and set(line) == {"-"}
        ]
        self.assertEqual(len(divider_lines), 2)
        self.assertTrue(
            all(len(line) == EXPECTED_DIVIDER_CHARS for line in divider_lines)
        )

    def test_hybrid_fixed_native_char_width(self) -> None:
        self.assertEqual(NATIVE_CHAR_WIDTH_PX, 12)

    def test_hybrid_divider_is_not_wrapped(self) -> None:
        config = Config(
            receipt_render_mode="hybrid",
            receipt_template_path=self.template_path,
            receipt_enable_cut=False,
            receipt_feed_lines=0,
        )
        template = ReceiptTemplate(
            margin=16,
            header_enabled=True,
            header_text="Header",
            footer_enabled=True,
            footer_text="Footer",
        )
        rendered = render_hybrid_escpos(
            [ReceiptBlock(kind="text", text="Body")],
            config,
            template,
            self.context,
        )

        decoded = rendered.decode("gb18030", errors="ignore")
        divider_lines = [
            line for line in decoded.splitlines() if line and set(line) == {"-"}
        ]
        self.assertEqual(len(divider_lines), 2)
        self.assertTrue(
            all(len(line) == EXPECTED_DIVIDER_CHARS for line in divider_lines)
        )


if __name__ == "__main__":
    unittest.main()
