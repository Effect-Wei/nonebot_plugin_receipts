from __future__ import annotations

import re
from typing import TYPE_CHECKING

from PIL import ImageFont

from .render_types import (
    CanvasLayout,
    NativeTextStyle,
    RasterRenderLine,
    StyledTextLine,
)
from .render_utils import measure_line_height, measure_text

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from PIL import ImageDraw


MARKDOWN_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
MIN_RENDER_FONT_SIZE = 12
HEADING_FONT_SCALES = {
    1: 1.8,
    2: 1.55,
    3: 1.35,
    4: 1.2,
    5: 1.1,
}
HEADING_NATIVE_STYLES = {
    1: (2, 2, True),
    2: (2, 1, True),
    3: (1, 2, True),
    4: (1, 1, True),
}


def parse_styled_lines(text: str) -> list[StyledTextLine]:
    """Parse markdown-like headings from plain text."""
    styled_lines: list[StyledTextLine] = []
    for raw_line in text.splitlines() or [""]:
        if raw_line.startswith(r"\#"):
            styled_lines.append(StyledTextLine(text=raw_line[1:]))
            continue

        match = MARKDOWN_HEADING_PATTERN.match(raw_line)
        if match is None:
            styled_lines.append(StyledTextLine(text=raw_line))
            continue

        heading_marks, heading_text = match.groups()
        styled_lines.append(
            StyledTextLine(
                text=heading_text,
                heading_level=min(len(heading_marks), 6),
            )
        )
    return styled_lines


def wrap_text(
    text: str,
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    """Wrap raster text using pixel measurements from the active font."""
    return wrap_by_measure(
        text,
        max_width,
        lambda candidate: measure_text(draw, candidate, font),
    )


def wrap_native_text(text: str, width_chars: int) -> list[str]:
    """Wrap text for native printer output using ASCII=1 and non-ASCII=2 width."""
    return wrap_by_measure(
        text,
        width_chars,
        lambda candidate: sum(1 if char.isascii() else 2 for char in candidate),
    )


def wrap_by_measure(
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


def build_raster_render_lines(
    text: str,
    layout: CanvasLayout,
) -> list[RasterRenderLine]:
    """Expand styled text into wrapped raster render lines."""
    render_lines: list[RasterRenderLine] = []
    for styled_line in parse_styled_lines(text):
        render_lines.extend(build_raster_render_line_group(styled_line, layout))
    return render_lines


def build_raster_render_line_group(
    styled_line: StyledTextLine,
    layout: CanvasLayout,
) -> list[RasterRenderLine]:
    """Render one styled logical line into one or more wrapped raster lines."""
    font = resolve_line_font(layout, styled_line.heading_level)
    line_height = measure_line_height(layout.draw, font) + layout.line_spacing
    wrapped_lines = wrap_text(
        styled_line.text,
        layout.draw,
        font,
        layout.content_width,
    )
    if not wrapped_lines:
        return []

    space_before, space_after = heading_spacing(styled_line.heading_level, layout)
    render_lines: list[RasterRenderLine] = []
    for index, wrapped_line in enumerate(wrapped_lines):
        render_lines.append(
            RasterRenderLine(
                text=wrapped_line,
                font=font,
                line_height=line_height,
                space_before=space_before if index == 0 else 0,
                space_after=space_after if index == len(wrapped_lines) - 1 else 0,
            )
        )
    return render_lines


def resolve_line_font(
    layout: CanvasLayout,
    heading_level: int,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Resolve the font used by one heading level, caching by size."""
    target_size = heading_font_size(layout.font_size, heading_level)
    if target_size == layout.font_size:
        return layout.font

    cached_font = layout.font_cache.get(target_size)
    if cached_font is not None:
        return cached_font

    if not layout.font_path:
        return layout.font

    try:
        cached_font = ImageFont.truetype(layout.font_path, size=target_size)
    except OSError:
        return layout.font

    layout.font_cache[target_size] = cached_font
    return cached_font


def heading_font_size(base_size: int, heading_level: int) -> int:
    """Map markdown heading levels to raster font sizes."""
    scale = HEADING_FONT_SCALES.get(heading_level)
    if scale is None:
        return base_size
    return max(MIN_RENDER_FONT_SIZE, int(base_size * scale))


def heading_spacing(heading_level: int, layout: CanvasLayout) -> tuple[int, int]:
    """Return extra vertical spacing for markdown headings."""
    if heading_level <= 0:
        return (0, 0)
    scale = max(1, 7 - heading_level)
    return (layout.line_spacing * scale, max(1, layout.line_spacing * (scale - 1)))


def encode_native_text(lines: Sequence[str]) -> bytes:
    """Encode wrapped lines using a broad Chinese-compatible printer code page."""
    chunks: list[bytes] = []
    for line in lines:
        chunks.append(line.encode("gb18030", errors="replace"))
        chunks.append(b"\n")
    return b"".join(chunks)


def encode_styled_native_text(
    styled_lines: Sequence[StyledTextLine],
    width_chars: int,
) -> bytes:
    """Encode styled markdown heading text using basic ESC/POS emphasis."""
    chunks: list[bytes] = []
    current_style = NativeTextStyle()

    for styled_line in styled_lines:
        target_style = native_text_style_for_heading(styled_line.heading_level)
        if target_style != current_style:
            chunks.append(encode_native_text_style(target_style))
            current_style = target_style

        lines = wrap_native_text(
            styled_line.text,
            effective_native_width(width_chars, target_style),
        )
        if not lines:
            chunks.append(b"\n")
            continue
        chunks.append(encode_native_text(lines))

    if current_style != NativeTextStyle():
        chunks.append(encode_native_text_style(NativeTextStyle()))
    return b"".join(chunks)


def native_text_style_for_heading(heading_level: int) -> NativeTextStyle:
    """Map markdown heading levels to printable native text styles."""
    style_tuple = HEADING_NATIVE_STYLES.get(heading_level)
    if style_tuple is None:
        return NativeTextStyle()
    width_multiplier, height_multiplier, bold = style_tuple
    return NativeTextStyle(
        width_multiplier=width_multiplier,
        height_multiplier=height_multiplier,
        bold=bold,
    )


def effective_native_width(width_chars: int, style: NativeTextStyle) -> int:
    """Estimate usable character width after ESC/POS text scaling."""
    return max(1, width_chars // max(1, style.width_multiplier))


def encode_native_text_style(style: NativeTextStyle) -> bytes:
    """Encode ESC/POS emphasis for one styled text block."""
    size_byte = (
        ((style.width_multiplier - 1) & 0x07) << 4
        | ((style.height_multiplier - 1) & 0x07)
    )
    return b"".join(
        [
            b"\x1bE" + (b"\x01" if style.bold else b"\x00"),
            b"\x1d!" + bytes((size_byte,)),
        ]
    )
