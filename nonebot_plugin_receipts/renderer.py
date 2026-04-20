from __future__ import annotations

import base64
import binascii
import io
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import httpx
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .template import (
    ReceiptTemplate,
    ReceiptTemplateContext,
    ReceiptTemplateError,
    load_receipt_template,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from nonebot.adapters.onebot.v11 import Message

    from .config import Config


MAX_RECEIPT_WIDTH = 576


@dataclass
class ReceiptBlock:
    """A normalized message block used by both render modes."""

    kind: str
    text: str = ""
    image: Image.Image | None = None


@dataclass
class CanvasLayout:
    """Shared layout measurements for raster text rendering."""

    width: int
    margin: int
    content_width: int
    line_height: int
    draw: ImageDraw.ImageDraw
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont


class ReceiptRenderError(RuntimeError):
    """Raised when receipt content cannot be rendered for printing."""

    INVALID_IMAGE_DATA = "图片消息数据格式无效。"
    INACCESSIBLE_IMAGE = "存在无法读取的图片消息，请确认适配器提供了可访问的图片 URL。"
    IMAGE_DECODE_FAILED = "读取图片消息失败。"
    INVALID_LAYOUT = "渲染模板边距过大，导致没有可用的打印宽度。"
    EMPTY_CONTENT = "消息中没有可打印的内容。"

    @classmethod
    def font_load_failed(cls, font_path: str) -> "ReceiptRenderError":
        return cls(f"无法加载字体文件: {font_path}")

    @classmethod
    def unsupported_render_mode(cls, mode: str) -> "ReceiptRenderError":
        return cls(f"不支持的渲染模式: {mode}")


async def render_receipt(
    message: Message,
    config: Config,
    template_context: ReceiptTemplateContext | None = None,
) -> bytes:
    """Render a OneBot message into ESC/POS bytes using the configured mode."""
    try:
        template = load_receipt_template(config)
    except ReceiptTemplateError as exc:
        raise ReceiptRenderError(str(exc)) from exc

    blocks = await _extract_blocks(message, config)
    context = template_context or ReceiptTemplateContext()

    if config.receipt_render_mode == "raster":
        canvas = _render_raster_canvas(
            blocks,
            config,
            template,
            context,
        )
        return _image_to_escpos(canvas, config)

    if config.receipt_render_mode == "hybrid":
        return _render_hybrid_escpos(
            blocks,
            config,
            template,
            context,
        )

    raise ReceiptRenderError.unsupported_render_mode(config.receipt_render_mode)


def _render_raster_canvas(
    blocks: Sequence[ReceiptBlock],
    config: Config,
    template: ReceiptTemplate,
    template_context: ReceiptTemplateContext,
) -> Image.Image:
    """Render all receipt blocks into a single raster canvas."""
    layout = _build_canvas_layout(config, template)

    sections: list[Image.Image] = []
    total_height = layout.margin

    for block in blocks:
        if block.kind == "text" and block.text:
            if section := _build_wrapped_text_section(block.text, layout):
                sections.append(section)
                total_height += section.height
            continue

        if block.kind == "image" and block.image is not None:
            section = _build_image_section(
                block.image,
                layout.width,
                layout.content_width,
                config.receipt_section_gap,
            )
            sections.append(section)
            total_height += section.height

    if not sections:
        raise ReceiptRenderError(ReceiptRenderError.EMPTY_CONTENT)

    footer_text = template.render_footer_text(template_context)
    if footer_text:
        footer = _build_wrapped_text_section(footer_text, layout)
        if footer is not None:
            sections.append(footer)
            total_height += footer.height + layout.margin

    canvas = Image.new("L", (layout.width, total_height), color=255)
    top = layout.margin
    for section in sections:
        canvas.paste(section, (0, top))
        top += section.height

    return canvas


def _render_hybrid_escpos(
    blocks: Sequence[ReceiptBlock],
    config: Config,
    template: ReceiptTemplate,
    template_context: ReceiptTemplateContext,
) -> bytes:
    """Render text natively and images as raster sections in message order."""
    width = min(config.receipt_printer_width, MAX_RECEIPT_WIDTH)
    margin = template.margin
    content_width = width - margin * 2
    if content_width <= 0:
        raise ReceiptRenderError(ReceiptRenderError.INVALID_LAYOUT)

    font = _load_font(config)
    probe = Image.new("L", (width, 10), color=255)
    draw = ImageDraw.Draw(probe)
    avg_char_width = max(1, _measure_text(draw, "AA", font) // 2)
    width_chars = max(1, content_width // avg_char_width)

    chunks: list[bytes] = [b"\x1b@"]

    for block in blocks:
        if block.kind == "text" and block.text:
            lines = _wrap_native_text(block.text, width_chars)
            if lines:
                chunks.append(_encode_native_text(lines))
            continue

        if block.kind == "image" and block.image is not None:
            section = _build_image_section(
                block.image,
                width,
                content_width,
                config.receipt_section_gap,
            )
            chunks.append(_image_to_escpos(section, config, initialize=False))

    footer_text = template.render_footer_text(template_context)
    if footer_text:
        chunks.append(_encode_native_text(_wrap_native_text(footer_text, width_chars)))

    if config.receipt_feed_lines:
        chunks.append(b"\n" * config.receipt_feed_lines)
    if config.receipt_enable_cut:
        chunks.append(b"\x1dV\x00")
    return b"".join(chunks)


def _measure_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> int:
    """Measure text width in pixels using the active PIL font."""
    sample = text or " "
    left, _, right, _ = draw.textbbox((0, 0), sample, font=font)
    return int(right - left)


def _wrap_text(
    text: str,
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    """Wrap raster text using pixel measurements from the active font."""
    return _wrap_by_measure(
        text,
        max_width,
        lambda candidate: _measure_text(draw, candidate, font),
    )


def _wrap_by_measure(
    text: str,
    max_width: int,
    measure: Callable[[str], int],
) -> list[str]:
    """Wrap text by repeatedly measuring candidate lines."""
    wrapped: list[str] = []
    for paragraph in text.splitlines() or [""]:
        if not paragraph:
            wrapped.append("")
            continue

        current = ""
        for char in paragraph:
            candidate = current + char
            if current and measure(candidate) > max_width:
                wrapped.append(current)
                current = char
            else:
                current = candidate
        if current:
            wrapped.append(current)
    return wrapped


def _measure_line_height(
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> int:
    """Estimate a readable line height for the current font."""
    _, top, _, bottom = draw.textbbox((0, 0), "Ag", font=font)
    return max(1, int(bottom - top))


def _flush_text_block(blocks: list[ReceiptBlock], text_buffer: list[str]) -> None:
    """Flush accumulated text into a normalized text block."""
    text = "".join(text_buffer)
    if text:
        blocks.append(ReceiptBlock(kind="text", text=text))
        text_buffer.clear()


async def _fetch_image_bytes(
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


async def _extract_image_block(
    client: httpx.AsyncClient,
    file_value: str,
    url: str,
) -> ReceiptBlock:
    """Normalize one image message segment into a grayscale image block."""
    raw_bytes: bytes | None = None

    if url:
        raw_bytes = await _fetch_image_bytes(client, url)
    elif file_value.startswith("base64://"):
        try:
            raw_bytes = base64.b64decode(
                file_value.removeprefix("base64://"),
                validate=True,
            )
        except binascii.Error as exc:
            raise ReceiptRenderError(ReceiptRenderError.INVALID_IMAGE_DATA) from exc
    elif file_value and urlparse(file_value).scheme in {"http", "https"}:
        raw_bytes = await _fetch_image_bytes(client, file_value)

    if raw_bytes is None:
        raise ReceiptRenderError(ReceiptRenderError.INACCESSIBLE_IMAGE)

    try:
        image = Image.open(io.BytesIO(raw_bytes))
        return ReceiptBlock(kind="image", image=image.convert("L"))
    except OSError as exc:
        raise ReceiptRenderError(ReceiptRenderError.IMAGE_DECODE_FAILED) from exc


async def _extract_blocks(message: Message, config: Config) -> list[ReceiptBlock]:
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

            _flush_text_block(blocks, text_buffer)
            url = str(segment.data.get("url") or "").strip()
            file_value = str(segment.data.get("file") or "").strip()
            blocks.append(await _extract_image_block(client, file_value, url))

        _flush_text_block(blocks, text_buffer)

    return blocks


def _resize_image(image: Image.Image, target_width: int) -> Image.Image:
    """Resize an image to fit the printable width while preserving aspect ratio."""
    if image.width <= target_width:
        return image
    new_height = max(1, int(image.height * (target_width / image.width)))
    return image.resize((target_width, new_height), Image.Resampling.LANCZOS)


def _load_font(config: Config) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load the configured font or fall back to Pillow's default font."""
    if config.receipt_font_path:
        try:
            return ImageFont.truetype(
                config.receipt_font_path,
                size=config.receipt_font_size,
            )
        except OSError as exc:
            raise ReceiptRenderError.font_load_failed(config.receipt_font_path) from exc
    return ImageFont.load_default()


def _build_canvas_layout(config: Config, template: ReceiptTemplate) -> CanvasLayout:
    """Prepare common layout values used by raster text rendering."""
    width = min(config.receipt_printer_width, MAX_RECEIPT_WIDTH)
    margin = template.margin
    content_width = width - margin * 2
    if content_width <= 0:
        raise ReceiptRenderError(ReceiptRenderError.INVALID_LAYOUT)

    font = _load_font(config)
    probe = Image.new("L", (width, 10), color=255)
    draw = ImageDraw.Draw(probe)
    line_height = _measure_line_height(draw, font) + config.receipt_line_spacing
    return CanvasLayout(
        width=width,
        margin=margin,
        content_width=content_width,
        line_height=line_height,
        draw=draw,
        font=font,
    )


def _build_wrapped_text_section(
    text: str,
    layout: CanvasLayout,
) -> Image.Image | None:
    """Render wrapped text into a raster section image."""
    lines = _wrap_text(text, layout.draw, layout.font, layout.content_width)
    if not lines:
        return None

    text_height = max(layout.line_height * len(lines), layout.line_height)
    text_image = Image.new(
        "L",
        (layout.width, text_height + layout.margin),
        color=255,
    )
    text_draw = ImageDraw.Draw(text_image)
    y = 0
    for line in lines:
        text_draw.text((layout.margin, y), line, fill=0, font=layout.font)
        y += layout.line_height
    return text_image


def _build_image_section(
    image: Image.Image,
    width: int,
    content_width: int,
    section_gap: int,
) -> Image.Image:
    """Render one image block into a raster section with gap padding."""
    fitted = _resize_image(image, content_width)
    framed = Image.new(
        "L",
        (width, fitted.height + section_gap),
        color=255,
    )
    offset_x = (width - fitted.width) // 2
    framed.paste(fitted, (offset_x, 0))
    return framed


def _wrap_native_text(text: str, width_chars: int) -> list[str]:
    """Wrap text for native printer output using ASCII=1 and non-ASCII=2 width."""
    return _wrap_by_measure(
        text,
        width_chars,
        lambda candidate: sum(1 if char.isascii() else 2 for char in candidate),
    )


def _encode_native_text(lines: Sequence[str]) -> bytes:
    """Encode wrapped lines using a broad Chinese-compatible printer code page."""
    chunks: list[bytes] = []
    for line in lines:
        chunks.append(line.encode("gb18030", errors="replace"))
        chunks.append(b"\n")
    return b"".join(chunks)


def _image_to_escpos(
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
