from __future__ import annotations

from typing import TYPE_CHECKING

from .escpos_backend import image_to_escpos, render_hybrid_escpos
from .raster_backend import render_raster_canvas
from .render_blocks import extract_blocks
from .render_types import ReceiptRenderError
from .template import (
    ReceiptTemplateContext,
    ReceiptTemplateError,
    load_receipt_template,
)

if TYPE_CHECKING:
    from nonebot.adapters.onebot.v11 import Message

    from .config import Config


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

    blocks = await extract_blocks(message, config)
    context = template_context or ReceiptTemplateContext()

    if config.receipt_render_mode == "raster":
        canvas = render_raster_canvas(
            blocks,
            config,
            template,
            context,
        )
        return image_to_escpos(canvas, config)

    if config.receipt_render_mode == "hybrid":
        return render_hybrid_escpos(
            blocks,
            config,
            template,
            context,
        )

    raise ReceiptRenderError.unsupported_render_mode(config.receipt_render_mode)
