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
    header_enabled: bool = False
    header_text: str = "{sender_name}({sender_id})"
    footer_enabled: bool = True
    footer_text: str = "{sender_name}({sender_id}) @ {timestamp}"
    footer_timestamp_format: str = "%Y-%m-%d %H:%M:%S"
    footer_timezone_offset_hours: int = Field(default=8, ge=-12, le=14)

    def render_header_text(self, context: ReceiptTemplateContext) -> str:
        return self._render_section_text(
            enabled=self.header_enabled,
            template_text=self.header_text,
            context=context,
            error_message=ReceiptTemplateError.INVALID_HEADER_TEXT,
        )

    def render_footer_text(self, context: ReceiptTemplateContext) -> str:
        return self._render_section_text(
            enabled=self.footer_enabled,
            template_text=self.footer_text,
            context=context,
            error_message=ReceiptTemplateError.INVALID_FOOTER_TEXT,
        )

    def _render_section_text(
        self,
        *,
        enabled: bool,
        template_text: str,
        context: ReceiptTemplateContext,
        error_message: str,
    ) -> str:
        if not enabled:
            return ""

        timestamp = self._render_timestamp()
        try:
            return template_text.format(
                timestamp=timestamp,
                sender_name=context.sender_name,
                sender_id=context.sender_id,
            )
        except (KeyError, ValueError) as exc:
            raise ReceiptTemplateError(error_message) from exc

    def _render_timestamp(self) -> str:
        return datetime.now(
            timezone(timedelta(hours=self.footer_timezone_offset_hours))
        ).strftime(self.footer_timestamp_format)


class ReceiptTemplateError(RuntimeError):
    """Raised when a receipt template cannot be loaded."""

    INVALID_HEADER_TEXT = (
        "渲染模板 header_text 不合法，只能使用"
        " {timestamp}、{sender_name}、{sender_id} 占位符。"
    )
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
