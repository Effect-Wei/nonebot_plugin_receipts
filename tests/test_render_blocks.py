from __future__ import annotations

import base64
import unittest
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from typing import Any

from nonebot_plugin_receipts.config import Config
from nonebot_plugin_receipts.render_blocks import extract_blocks, extract_image_block
from nonebot_plugin_receipts.render_types import ReceiptRenderError


class FakeSegment:
    def __init__(self, segment_type: str, data: dict[str, str]) -> None:
        self.type = segment_type
        self.data = data


class RenderBlocksTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_extract_blocks_merges_text_segments(self) -> None:
        message = [
            FakeSegment("text", {"text": "Hello, "}),
            FakeSegment("text", {"text": "world"}),
        ]

        blocks = await extract_blocks(cast("Any", message), Config())

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].kind, "text")
        self.assertEqual(blocks[0].text, "Hello, world")

    async def test_extract_blocks_preserves_text_image_order(self) -> None:
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x00\x00\x00\x00\x3a\x7e\x9b\x55\x00\x00\x00\x0aIDATx\x9cc`\x00"
            b"\x00\x00\x02\x00\x01\x48\xaf\xa4\x71\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        encoded = base64.b64encode(png_bytes).decode("ascii")
        message = [
            FakeSegment("text", {"text": "A"}),
            FakeSegment("image", {"file": f"base64://{encoded}", "url": ""}),
            FakeSegment("text", {"text": "B"}),
        ]

        blocks = await extract_blocks(cast("Any", message), Config())

        self.assertEqual([block.kind for block in blocks], ["text", "image", "text"])
        self.assertEqual(blocks[0].text, "A")
        self.assertEqual(blocks[2].text, "B")

    async def test_extract_image_block_rejects_invalid_base64(self) -> None:
        with self.assertRaises(ReceiptRenderError) as exc_info:
            await extract_image_block(
                cast("Any", SimpleNamespace()), "base64://@@@", ""
            )

        self.assertEqual(str(exc_info.exception), ReceiptRenderError.INVALID_IMAGE_DATA)

    async def test_extract_image_block_rejects_missing_source(self) -> None:
        with self.assertRaises(ReceiptRenderError) as exc_info:
            await extract_image_block(cast("Any", SimpleNamespace()), "", "")

        self.assertEqual(str(exc_info.exception), ReceiptRenderError.INACCESSIBLE_IMAGE)


if __name__ == "__main__":
    unittest.main()
