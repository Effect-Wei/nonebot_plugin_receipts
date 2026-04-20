import base64
import json
from typing import Any

import httpx

from .config import Config


class SpoolerError(RuntimeError):
    INVALID_RESPONSE = "receipts-spooler 返回了不可识别的响应。"


class SpoolerClient:
    def __init__(self, config: Config) -> None:
        self._config = config

    async def push_raw(self, payload: bytes) -> dict[str, Any]:
        url = self._config.receipts_spooler_url.rstrip("/")
        headers: dict[str, str] = {}
        if self._config.receipts_spooler_token:
            headers["X-Spooler-Token"] = self._config.receipts_spooler_token

        body = {
            "data_type": "escpos_base64",
            "payload": base64.b64encode(payload).decode("ascii"),
        }

        try:
            async with httpx.AsyncClient(
                timeout=self._config.receipts_spooler_timeout
            ) as client:
                response = await client.post(
                    f"{url}/api/v1/task/push_raw",
                    json=body,
                    headers=headers,
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text.strip() or str(exc)
            raise SpoolerError(detail) from exc
        except httpx.HTTPError as exc:
            raise SpoolerError(str(exc)) from exc

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise SpoolerError(SpoolerError.INVALID_RESPONSE) from exc
        if not isinstance(data, dict):
            raise SpoolerError(SpoolerError.INVALID_RESPONSE)
        return data
