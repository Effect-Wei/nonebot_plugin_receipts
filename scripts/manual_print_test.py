from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nonebot_plugin_receipts.config import Config
from nonebot_plugin_receipts.escpos_backend import (
    image_to_escpos,
    render_hybrid_escpos,
)
from nonebot_plugin_receipts.raster_backend import render_raster_canvas
from nonebot_plugin_receipts.render_types import ReceiptBlock
from nonebot_plugin_receipts.spooler import SpoolerClient, SpoolerError
from nonebot_plugin_receipts.template import ReceiptTemplate, ReceiptTemplateContext
from nonebot_plugin_receipts.text_markup import encode_native_text

MANUAL_PRINT_TEST_FAILED = "Manual print test failed: {message}\n"
MANUAL_PRINT_TEST_SUBMITTED = "Manual print test submitted.\n"
QUEUE_SIZE_TEMPLATE = "Queue size: {queue_size}\n"
RESPONSE_TEMPLATE = "Response: {response}\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manual printer smoke test without starting NoneBot.",
    )
    parser.add_argument(
        "--mode",
        choices=("hybrid", "raster"),
        default=os.getenv("RENDER_MODE", "hybrid"),
        help="Render mode, default from RENDER_MODE or hybrid.",
    )
    parser.add_argument(
        "--text",
        default="# Manual Test\nHello receipt printer\n\\# literal hash",
        help="Text content to print.",
    )
    parser.add_argument(
        "--sender-name",
        default=os.getenv("SENDER_NAME", "LOCAL_TEST"),
        help="Template sender_name.",
    )
    parser.add_argument(
        "--sender-id",
        default=os.getenv("SENDER_ID", "0000"),
        help="Template sender_id.",
    )
    parser.add_argument(
        "--spooler-url",
        default=os.getenv("SPOOLER_URL", "http://127.0.0.1:8000"),
        help="receipts-spooler base URL.",
    )
    parser.add_argument(
        "--spooler-token",
        default=os.getenv("SPOOLER_TOKEN") or None,
        help="Optional X-Spooler-Token.",
    )
    parser.add_argument(
        "--printer-width",
        type=int,
        default=int(os.getenv("PRINTER_WIDTH", "576")),
        help="Printer width in pixels.",
    )
    parser.add_argument(
        "--feed-lines",
        type=int,
        default=int(os.getenv("FEED_LINES", "2")),
        help="Feed lines after printing.",
    )
    parser.add_argument(
        "--cut",
        action="store_true",
        help="Enable cut command (disabled by default in manual tests).",
    )
    parser.add_argument(
        "--divider-only",
        action="store_true",
        help="Send only one divider line for printer validation.",
    )
    parser.add_argument(
        "--divider-chars",
        type=int,
        default=0,
        help="Divider length in characters, default uses printer width / 12.",
    )
    return parser.parse_args()


async def run() -> None:
    args = parse_args()

    config = Config(
        receipts_spooler_url=args.spooler_url,
        receipts_spooler_token=args.spooler_token,
        receipt_render_mode=args.mode,
        receipt_printer_width=args.printer_width,
        receipt_feed_lines=args.feed_lines,
        receipt_enable_cut=args.cut,
    )

    template = ReceiptTemplate(
        header_enabled=True,
        header_text="# Manual Test Header",
        footer_enabled=True,
        footer_text="{sender_name}({sender_id}) @ {timestamp}",
    )
    context = ReceiptTemplateContext(
        sender_name=args.sender_name,
        sender_id=args.sender_id,
    )
    if args.divider_only:
        divider_chars = args.divider_chars or max(1, config.receipt_printer_width // 12)
        payload = b"\x1b@" + encode_native_text(["-" * divider_chars])
        if config.receipt_feed_lines:
            payload += b"\n" * config.receipt_feed_lines
        if config.receipt_enable_cut:
            payload += b"\x1dV\x00"
    else:
        blocks = [ReceiptBlock(kind="text", text=args.text)]
        if args.mode == "hybrid":
            payload = render_hybrid_escpos(blocks, config, template, context)
        else:
            canvas = render_raster_canvas(blocks, config, template, context)
            payload = image_to_escpos(canvas, config)

    try:
        response = await SpoolerClient(config).push_raw(payload)
    except SpoolerError as exc:
        sys.stderr.write(MANUAL_PRINT_TEST_FAILED.format(message=exc))
        raise SystemExit(1) from exc

    sys.stdout.write(MANUAL_PRINT_TEST_SUBMITTED)
    queue_size = response.get("queue_size")
    if isinstance(queue_size, int):
        sys.stdout.write(QUEUE_SIZE_TEMPLATE.format(queue_size=queue_size))
    else:
        sys.stdout.write(RESPONSE_TEMPLATE.format(response=response))


if __name__ == "__main__":
    asyncio.run(run())
