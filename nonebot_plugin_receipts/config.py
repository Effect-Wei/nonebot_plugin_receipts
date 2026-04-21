import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def normalize_whitelist_ids(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []

        try:
            value = json.loads(stripped)
        except json.JSONDecodeError:
            return [
                item
                for part in re.split(r"[\s,，]+", stripped)
                if (item := part.strip())
            ]

    if isinstance(value, list | tuple | set | frozenset):
        return [item for entry in value if (item := str(entry).strip())]

    item = str(value).strip()
    return [item] if item else []


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
    receipt_session_timeout_seconds: int = Field(default=120, ge=10, le=3600)
    receipt_feed_lines: int = Field(default=4, ge=0, le=10)
    receipt_enable_cut: bool = True
    receipt_allowed_user_ids: str | list[str] | None = Field(default_factory=list)
    receipt_allowed_group_ids: str | list[str] | None = Field(default_factory=list)

    @field_validator(
        "receipt_allowed_user_ids",
        "receipt_allowed_group_ids",
        mode="before",
    )
    @classmethod
    def normalize_whitelist_ids(cls, value: Any) -> list[str]:
        return normalize_whitelist_ids(value)

    @property
    def allowed_user_ids(self) -> list[str]:
        return normalize_whitelist_ids(self.receipt_allowed_user_ids)

    @property
    def allowed_group_ids(self) -> list[str]:
        return normalize_whitelist_ids(self.receipt_allowed_group_ids)
