from typing import Literal

from pydantic import BaseModel, Field


class Config(BaseModel):
    receipts_spooler_url: str = "http://127.0.0.1:8000"
    receipts_spooler_token: str | None = None
    receipts_spooler_timeout: float = 5.0
    receipt_image_fetch_timeout: float = 5.0
    receipt_render_mode: Literal["raster", "hybrid"] = "raster"
    receipt_printer_width: int = Field(default=576, ge=128, le=576)
    receipt_template_path: str | None = None
    receipt_font_path: str | None = None
    receipt_font_size: int = Field(default=24, ge=12, le=96)
    receipt_line_spacing: int = Field(default=6, ge=0, le=40)
    receipt_section_gap: int = Field(default=6, ge=0, le=100)
    receipt_feed_lines: int = Field(default=4, ge=0, le=10)
    receipt_enable_cut: bool = True
