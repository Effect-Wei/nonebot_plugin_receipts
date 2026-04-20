from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image, ImageDraw, ImageFont

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
    section_gap: int
    font_path: str | None
    font_size: int
    line_spacing: int
    line_height: int
    draw: ImageDraw.ImageDraw
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont
    font_cache: dict[int, ImageFont.FreeTypeFont | ImageFont.ImageFont] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class HybridLayout:
    """Shared layout measurements for hybrid ESC/POS rendering."""

    width: int
    content_width: int
    width_chars: int


@dataclass(frozen=True)
class StyledTextLine:
    """One parsed line of text with optional markdown heading metadata."""

    text: str
    heading_level: int = 0


@dataclass(frozen=True)
class RasterRenderLine:
    """One raster line with resolved font and spacing."""

    text: str
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont
    line_height: int
    space_before: int = 0
    space_after: int = 0


@dataclass(frozen=True)
class NativeTextStyle:
    """ESC/POS text style for one markdown heading level."""

    width_multiplier: int = 1
    height_multiplier: int = 1
    bold: bool = False


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
