from __future__ import annotations

import base64
import binascii
import io
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import httpx
from PIL import Image

from .render_types import ReceiptBlock, ReceiptRenderError

if TYPE_CHECKING:
    from nonebot.adapters.onebot.v11 import Message

    from .config import Config


async def extract_blocks(message: Message, config: Config) -> list[ReceiptBlock]:
    """Convert a mixed OneBot message into ordered text and image blocks."""
    blocks: list[ReceiptBlock] = []
    async with httpx.AsyncClient(timeout=config.receipt_image_fetch_timeout) as client:
        text_buffer: list[str] = []

        for segment in message:
            if segment.type == "text":
                text_buffer.append(str(segment.data.get("text") or ""))
                continue

            if segment.type != "image":
                continue

            flush_text_block(blocks, text_buffer)
            url = str(segment.data.get("url") or "").strip()
            file_value = str(segment.data.get("file") or "").strip()
            blocks.append(await extract_image_block(client, file_value, url))

        flush_text_block(blocks, text_buffer)

    return blocks


async def extract_image_block(
    client: httpx.AsyncClient,
    file_value: str,
    url: str,
) -> ReceiptBlock:
    """Normalize one image message segment into a grayscale image block."""
    raw_bytes: bytes | None = None

    if url:
        raw_bytes = await fetch_image_bytes(client, url)
    elif file_value.startswith("base64://"):
        try:
            raw_bytes = base64.b64decode(
                file_value.removeprefix("base64://"),
                validate=True,
            )
        except binascii.Error as exc:
            raise ReceiptRenderError(ReceiptRenderError.INVALID_IMAGE_DATA) from exc
    elif file_value and urlparse(file_value).scheme in {"http", "https"}:
        raw_bytes = await fetch_image_bytes(client, file_value)

    if raw_bytes is None:
        raise ReceiptRenderError(ReceiptRenderError.INACCESSIBLE_IMAGE)

    try:
        image = Image.open(io.BytesIO(raw_bytes))
        return ReceiptBlock(kind="image", image=image.convert("L"))
    except OSError as exc:
        raise ReceiptRenderError(ReceiptRenderError.IMAGE_DECODE_FAILED) from exc


async def fetch_image_bytes(
    client: httpx.AsyncClient,
    url: str,
) -> bytes:
    """Download image bytes from a remote URL."""
    try:
        response = await client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ReceiptRenderError(ReceiptRenderError.INACCESSIBLE_IMAGE) from exc
    return response.content


def flush_text_block(blocks: list[ReceiptBlock], text_buffer: list[str]) -> None:
    """Flush accumulated text into a normalized text block."""
    text = "".join(text_buffer)
    if text:
        blocks.append(ReceiptBlock(kind="text", text=text))
        text_buffer.clear()
