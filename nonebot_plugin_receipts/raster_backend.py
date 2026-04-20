from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import Image, ImageDraw

from .render_types import (
    MAX_RECEIPT_WIDTH,
    CanvasLayout,
    ReceiptBlock,
    ReceiptRenderError,
)
from .render_utils import load_font, measure_line_height, resize_image
from .text_markup import build_raster_render_lines

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .config import Config
    from .template import ReceiptTemplate, ReceiptTemplateContext


def render_raster_canvas(
    blocks: Sequence[ReceiptBlock],
    config: Config,
    template: ReceiptTemplate,
    template_context: ReceiptTemplateContext,
) -> Image.Image:
    """Render all receipt blocks into a single raster canvas."""
    layout = build_canvas_layout(config, template)

    sections: list[Image.Image] = []
    total_height = layout.margin

    header_text = template.render_header_text(template_context)
    total_height += append_raster_text_section(
        sections,
        header_text,
        layout,
        add_divider_after=True,
    )

    body_sections = build_raster_body_sections(
        blocks,
        layout,
        config.receipt_section_gap,
    )
    if not body_sections:
        raise ReceiptRenderError(ReceiptRenderError.EMPTY_CONTENT)

    sections.extend(body_sections)
    total_height += sum(section.height for section in body_sections)

    footer_text = template.render_footer_text(template_context)
    footer_height = append_raster_text_section(
        sections,
        footer_text,
        layout,
        add_divider_before=True,
    )
    if footer_height:
        total_height += footer_height + layout.margin

    canvas = Image.new("L", (layout.width, total_height), color=255)
    top = layout.margin
    for section in sections:
        canvas.paste(section, (0, top))
        top += section.height

    return canvas


def build_canvas_layout(config: Config, template: ReceiptTemplate) -> CanvasLayout:
    """Prepare common layout values used by raster text rendering."""
    width = min(config.receipt_printer_width, MAX_RECEIPT_WIDTH)
    margin = template.margin
    content_width = width - margin * 2
    if content_width <= 0:
        raise ReceiptRenderError(ReceiptRenderError.INVALID_LAYOUT)

    font = load_font(config)
    probe = Image.new("L", (width, 10), color=255)
    draw = ImageDraw.Draw(probe)
    line_height = measure_line_height(draw, font) + config.receipt_line_spacing
    return CanvasLayout(
        width=width,
        margin=margin,
        content_width=content_width,
        section_gap=config.receipt_section_gap,
        font_path=config.receipt_font_path,
        font_size=config.receipt_font_size,
        line_spacing=config.receipt_line_spacing,
        line_height=line_height,
        draw=draw,
        font=font,
    )


def build_wrapped_text_section(
    text: str,
    layout: CanvasLayout,
) -> Image.Image | None:
    """Render wrapped text into a raster section image."""
    render_lines = build_raster_render_lines(text, layout)
    if not render_lines:
        return None

    text_height = sum(
        line.space_before + line.line_height + line.space_after for line in render_lines
    )
    text_image = Image.new(
        "L",
        (layout.width, text_height + layout.margin),
        color=255,
    )
    text_draw = ImageDraw.Draw(text_image)
    y = 0
    for line in render_lines:
        y += line.space_before
        text_draw.text((layout.margin, y), line.text, fill=0, font=line.font)
        y += line.line_height + line.space_after
    return text_image


def append_raster_text_section(
    sections: list[Image.Image],
    text: str,
    layout: CanvasLayout,
    *,
    add_divider_before: bool = False,
    add_divider_after: bool = False,
) -> int:
    """Append a wrapped raster text block and optional divider."""
    if not text:
        return 0

    section = build_wrapped_text_section(text, layout)
    if section is None:
        return 0

    total_height = 0
    if add_divider_before:
        divider = build_divider_section(layout.width, layout.section_gap)
        sections.append(divider)
        total_height += divider.height
    sections.append(section)
    total_height += section.height
    if add_divider_after:
        divider = build_divider_section(layout.width, layout.section_gap)
        sections.append(divider)
        total_height += divider.height
    return total_height


def build_raster_body_sections(
    blocks: Sequence[ReceiptBlock],
    layout: CanvasLayout,
    section_gap: int,
) -> list[Image.Image]:
    """Render message body blocks into raster sections."""
    sections: list[Image.Image] = []
    for block in blocks:
        section = build_raster_body_section(block, layout, section_gap)
        if section is not None:
            sections.append(section)
    return sections


def build_raster_body_section(
    block: ReceiptBlock,
    layout: CanvasLayout,
    section_gap: int,
) -> Image.Image | None:
    """Render a single message block as a raster section."""
    if block.kind == "text" and block.text:
        return build_wrapped_text_section(block.text, layout)
    if block.kind == "image" and block.image is not None:
        return build_image_section(
            block.image,
            layout.width,
            layout.content_width,
            section_gap,
        )
    return None


def build_image_section(
    image: Image.Image,
    width: int,
    content_width: int,
    section_gap: int,
) -> Image.Image:
    """Render one image block into a raster section with gap padding."""
    fitted = resize_image(image, content_width)
    framed = Image.new(
        "L",
        (width, fitted.height + section_gap),
        color=255,
    )
    offset_x = (width - fitted.width) // 2
    framed.paste(fitted, (offset_x, 0))
    return framed


def build_divider_section(width: int, section_gap: int) -> Image.Image:
    """Render a full-width horizontal divider with vertical breathing room."""
    top_gap = max(1, section_gap // 2)
    bottom_gap = max(1, section_gap - top_gap)
    divider = Image.new("L", (width, top_gap + 1 + bottom_gap), color=255)
    draw = ImageDraw.Draw(divider)
    draw.line((0, top_gap, width - 1, top_gap), fill=0, width=1)
    return divider
