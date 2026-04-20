from __future__ import annotations

from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

from .render_types import ReceiptRenderError

if TYPE_CHECKING:
    from .config import Config


def measure_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> int:
    """Measure text width in pixels using the active PIL font."""
    sample = text or " "
    left, _, right, _ = draw.textbbox((0, 0), sample, font=font)
    return int(right - left)


def measure_line_height(
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> int:
    """Estimate a readable line height for the current font."""
    _, top, _, bottom = draw.textbbox((0, 0), "Ag", font=font)
    return max(1, int(bottom - top))


def resize_image(image: Image.Image, target_width: int) -> Image.Image:
    """Resize an image to fit the printable width while preserving aspect ratio."""
    if image.width <= target_width:
        return image
    new_height = max(1, int(image.height * (target_width / image.width)))
    return image.resize((target_width, new_height), Image.Resampling.LANCZOS)


def load_font(config: Config) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
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
