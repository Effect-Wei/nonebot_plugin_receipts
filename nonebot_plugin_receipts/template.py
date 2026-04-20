from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, ValidationError

if TYPE_CHECKING:
    from .config import Config


class ReceiptTemplateContext(BaseModel):
    sender_name: str = ""
    sender_id: str = ""


class ReceiptTemplate(BaseModel):
    """Layout template for receipt rendering."""

    margin: int = Field(default=16, ge=0, le=64)
    footer_enabled: bool = True
    footer_text: str = "{sender_name}({sender_id}) @ {timestamp}"
    footer_timestamp_format: str = "%Y-%m-%d %H:%M:%S"
    footer_timezone_offset_hours: int = Field(default=8, ge=-12, le=14)

    def render_footer_text(self, context: ReceiptTemplateContext) -> str:
        if not self.footer_enabled:
            return ""

        timestamp = datetime.now(
            timezone(timedelta(hours=self.footer_timezone_offset_hours))
        ).strftime(self.footer_timestamp_format)
        try:
            return self.footer_text.format(
                timestamp=timestamp,
                sender_name=context.sender_name,
                sender_id=context.sender_id,
            )
        except (KeyError, ValueError) as exc:
            raise ReceiptTemplateError(
                ReceiptTemplateError.INVALID_FOOTER_TEXT
            ) from exc


class ReceiptTemplateError(RuntimeError):
    """Raised when a receipt template cannot be loaded."""

    INVALID_FOOTER_TEXT = (
        "渲染模板 footer_text 不合法，只能使用"
        " {timestamp}、{sender_name}、{sender_id} 占位符。"
    )

    @classmethod
    def read_failed(cls, path: str) -> "ReceiptTemplateError":
        return cls(f"无法读取渲染模板文件: {path}")

    @classmethod
    def invalid_json(cls, path: str) -> "ReceiptTemplateError":
        return cls(f"渲染模板文件不是合法的 JSON: {path}")

    @classmethod
    def invalid_data(cls, path: str) -> "ReceiptTemplateError":
        return cls(f"渲染模板配置无效: {path}")


def load_receipt_template(config: Config) -> ReceiptTemplate:
    if not config.receipt_template_path:
        return ReceiptTemplate()

    path = Path(config.receipt_template_path)
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReceiptTemplateError.read_failed(str(path)) from exc

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ReceiptTemplateError.invalid_json(str(path)) from exc

    if not isinstance(data, dict):
        raise ReceiptTemplateError.invalid_data(str(path))

    try:
        return ReceiptTemplate.model_validate(data)
    except ValidationError as exc:
        raise ReceiptTemplateError.invalid_data(str(path)) from exc
