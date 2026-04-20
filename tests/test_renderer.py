from __future__ import annotations

import unittest
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, patch

from nonebot_plugin_receipts.config import Config
from nonebot_plugin_receipts.render_types import ReceiptBlock
from nonebot_plugin_receipts.renderer import render_receipt
from nonebot_plugin_receipts.template import ReceiptTemplateContext

if TYPE_CHECKING:
    from typing import Any


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


if __name__ == "__main__":
    unittest.main()
