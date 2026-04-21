from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import Image, ImageOps

from .raster_backend import build_image_section
from .render_types import (
    MAX_RECEIPT_WIDTH,
    HybridLayout,
    ReceiptBlock,
    ReceiptRenderError,
)
from .text_markup import (
    encode_native_text,
    encode_styled_native_text,
    parse_styled_lines,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .config import Config
    from .template import ReceiptTemplate, ReceiptTemplateContext


NATIVE_CHAR_WIDTH_PX = 12
DIVIDER_BEFORE = "before"
DIVIDER_AFTER = "after"


def render_hybrid_escpos(
    blocks: Sequence[ReceiptBlock],
    config: Config,
    template: ReceiptTemplate,
    template_context: ReceiptTemplateContext,
) -> bytes:
    """Render text natively and images as raster sections in message order."""
    layout = build_hybrid_layout(config, template)
    if layout.content_width <= 0:
        raise ReceiptRenderError(ReceiptRenderError.INVALID_LAYOUT)

    chunks: list[bytes] = [b"\x1b@"]
    divider_width_chars = max(1, layout.width // NATIVE_CHAR_WIDTH_PX)

    header_text = template.render_header_text(template_context)
    append_hybrid_text_section(
        chunks,
        header_text,
        layout.width_chars,
        divider_width_chars,
        divider=DIVIDER_AFTER,
    )

    has_body_content = False
    for block in blocks:
        if block.kind == "text" and block.text:
            styled_lines = parse_styled_lines(block.text)
            if not styled_lines:
                continue
            chunks.append(encode_styled_native_text(styled_lines, layout.width_chars))
            has_body_content = True
            continue

        if block.kind != "image" or block.image is None:
            continue

        section = build_image_section(
            block.image,
            layout.width,
            layout.content_width,
            config.receipt_section_gap,
        )
        chunks.append(image_to_escpos(section, config, initialize=False))
        has_body_content = True

    if not has_body_content:
        raise ReceiptRenderError(ReceiptRenderError.EMPTY_CONTENT)

    footer_text = template.render_footer_text(template_context)
    append_hybrid_text_section(
        chunks,
        footer_text,
        layout.width_chars,
        divider_width_chars,
        divider=DIVIDER_BEFORE,
    )

    if config.receipt_feed_lines:
        chunks.append(b"\n" * config.receipt_feed_lines)
    if config.receipt_enable_cut:
        chunks.append(b"\x1dV\x00")
    return b"".join(chunks)


def build_hybrid_layout(config: Config, template: ReceiptTemplate) -> HybridLayout:
    """Prepare common layout values used by hybrid rendering."""
    width = min(config.receipt_printer_width, MAX_RECEIPT_WIDTH)
    margin = template.margin
    content_width = width - margin * 2

    width_chars = max(1, content_width // NATIVE_CHAR_WIDTH_PX)
    return HybridLayout(
        width=width,
        content_width=content_width,
        width_chars=width_chars,
    )


def append_hybrid_text_section(
    chunks: list[bytes],
    text: str,
    width_chars: int,
    divider_width_chars: int,
    divider: str = "",
) -> None:
    """Append wrapped native text lines and an optional divider."""
    if not text:
        return

    styled_lines = parse_styled_lines(text)
    if not styled_lines:
        return

    if divider == DIVIDER_BEFORE:
        chunks.append(encode_native_text(["-" * divider_width_chars]))
    chunks.append(encode_styled_native_text(styled_lines, width_chars))
    if divider == DIVIDER_AFTER:
        chunks.append(encode_native_text(["-" * divider_width_chars]))


def image_to_escpos(
    image: Image.Image, config: Config, *, initialize: bool = True
) -> bytes:
    """Convert a raster image into ESC/POS raster bit image commands."""
    grayscale = ImageOps.autocontrast(image).convert("L")
    bw = grayscale.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    width, height = bw.size
    width_bytes = (width + 7) // 8
    raster_data = bytearray()

    for y in range(height):
        row_offset = y * width_bytes
        raster_data.extend(b"\x00" * width_bytes)
        for x in range(width):
            if bw.getpixel((x, y)) == 0:
                raster_data[row_offset + (x // 8)] |= 0x80 >> (x % 8)

    chunks: list[bytes] = [b"\x1b@"] if initialize else []
    max_chunk_height = 255
    for start in range(0, height, max_chunk_height):
        chunk_height = min(max_chunk_height, height - start)
        chunk = bytearray()
        for y in range(start, start + chunk_height):
            offset = y * width_bytes
            chunk.extend(raster_data[offset : offset + width_bytes])
        chunks.append(
            b"\x1d\x76\x30\x00"
            + bytes(
                (
                    width_bytes & 0xFF,
                    (width_bytes >> 8) & 0xFF,
                    chunk_height & 0xFF,
                    (chunk_height >> 8) & 0xFF,
                )
            )
            + bytes(chunk)
        )

    if initialize and config.receipt_feed_lines:
        chunks.append(b"\n" * config.receipt_feed_lines)
    if initialize and config.receipt_enable_cut:
        chunks.append(b"\x1dV\x00")
    return b"".join(chunks)
