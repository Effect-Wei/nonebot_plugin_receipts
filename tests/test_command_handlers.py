from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock, patch

from nonebot.exception import FinishedException

from nonebot_plugin_receipts.command_handlers import (
    RECEIPT_TIMEOUT_DEADLINE_KEY,
    build_initial_receipt_prompt,
    build_timeout_receipt_prompt,
    format_timeout_duration,
    get_effective_session_timeout_seconds,
    get_event_group_id,
    get_event_user_id,
    is_receipt_submission_allowed,
    is_receipt_timeout_expired,
    register_receipt_handlers,
    reset_receipt_timeout_deadline,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


class DummyMatcher:
    def __init__(self) -> None:
        self.state: dict[str, float] = {}


class DummyMessage:
    def __init__(self, text: str = "", segments: list[Any] | None = None) -> None:
        self._text = text
        self._segments = segments or []

    def extract_plain_text(self) -> str:
        return self._text

    def __iter__(self):  # noqa: ANN204
        return iter(self._segments)


class StubReceiptPrint:
    handle_handler: "Callable[..., Awaitable[Any]] | None" = None
    got_handler: "Callable[..., Awaitable[Any]] | None" = None

    @classmethod
    def handle(cls):  # noqa: ANN206
        def decorator(func: Any) -> Any:
            cls.handle_handler = func
            return func

        return decorator

    @classmethod
    def got(cls, *_args: Any, **_kwargs: Any):  # noqa: ANN206
        def decorator(func: Any) -> Any:
            cls.got_handler = func
            return func

        return decorator

    @classmethod
    async def finish(cls, message: str) -> None:
        raise RuntimeError(message)

    @classmethod
    async def reject(cls, message: str) -> None:
        raise ValueError(message)


def require_handle_handler() -> "Callable[..., Awaitable[Any]]":
    assert StubReceiptPrint.handle_handler is not None
    return StubReceiptPrint.handle_handler


def require_got_handler() -> "Callable[..., Awaitable[Any]]":
    assert StubReceiptPrint.got_handler is not None
    return StubReceiptPrint.got_handler


async def call_registered_handler(
    handler: "Callable[..., Awaitable[Any]]", *args: Any
) -> Any:
    return await handler(*args)


class DummyDriverConfig:
    def __init__(self, seconds: int) -> None:
        self._seconds = seconds

    @property
    def session_expire_timeout(self):  # noqa: ANN201
        from datetime import timedelta

        return timedelta(seconds=self._seconds)


class DummyDriver:
    def __init__(self, seconds: int) -> None:
        self.config = DummyDriverConfig(seconds)


class DummyPluginConfig:
    def __init__(
        self,
        seconds: int,
        allowed_user_ids: list[str] | None = None,
        allowed_group_ids: list[str] | None = None,
    ) -> None:
        self.receipt_session_timeout_seconds = seconds
        self.receipt_allowed_user_ids = allowed_user_ids or []
        self.receipt_allowed_group_ids = allowed_group_ids or []

    @property
    def allowed_user_ids(self) -> list[str]:
        return self.receipt_allowed_user_ids

    @property
    def allowed_group_ids(self) -> list[str]:
        return self.receipt_allowed_group_ids


class CommandHandlersTestCase(unittest.TestCase):
    def setUp(self) -> None:
        StubReceiptPrint.handle_handler = None
        StubReceiptPrint.got_handler = None
        register_receipt_handlers(cast("Any", StubReceiptPrint))

    def test_format_timeout_duration(self) -> None:
        self.assertEqual(format_timeout_duration(45), "45 秒")
        self.assertEqual(format_timeout_duration(120), "2 分钟")
        self.assertEqual(format_timeout_duration(125), "2 分 5 秒")

    def test_build_prompts_include_timeout_text(self) -> None:
        self.assertIn("2 分钟", build_initial_receipt_prompt(120))
        self.assertIn("已超时", build_timeout_receipt_prompt(120))
        self.assertIn("/小票", build_timeout_receipt_prompt(120))

    def test_get_effective_session_timeout_seconds_uses_minimum(self) -> None:
        with (
            patch(
                "nonebot_plugin_receipts.command_handlers.get_runtime_config",
                return_value=DummyPluginConfig(180),
            ),
            patch(
                "nonebot_plugin_receipts.command_handlers.get_driver",
                return_value=DummyDriver(120),
            ),
        ):
            self.assertEqual(get_effective_session_timeout_seconds(), 119)

    def test_reset_and_check_timeout_deadline(self) -> None:
        matcher = DummyMatcher()

        reset_receipt_timeout_deadline(cast("Any", matcher), 30)
        self.assertIn(RECEIPT_TIMEOUT_DEADLINE_KEY, matcher.state)
        self.assertFalse(is_receipt_timeout_expired(cast("Any", matcher)))

        matcher.state[RECEIPT_TIMEOUT_DEADLINE_KEY] = 0
        self.assertTrue(is_receipt_timeout_expired(cast("Any", matcher)))

    def test_get_event_ids(self) -> None:
        private_event = SimpleNamespace(user_id=123456)
        group_event = SimpleNamespace(user_id=123456, group_id=654321)

        self.assertEqual(get_event_user_id(cast("Any", private_event)), "123456")
        self.assertEqual(get_event_group_id(cast("Any", private_event)), "")
        self.assertEqual(get_event_group_id(cast("Any", group_event)), "654321")

    def test_submission_allowed_when_whitelist_empty(self) -> None:
        event = SimpleNamespace(user_id=123456, group_id=654321)

        with patch(
            "nonebot_plugin_receipts.command_handlers.get_runtime_config",
            return_value=DummyPluginConfig(120),
        ):
            self.assertTrue(is_receipt_submission_allowed(cast("Any", event)))

    def test_submission_allowed_for_whitelisted_user(self) -> None:
        event = SimpleNamespace(user_id=123456)

        with patch(
            "nonebot_plugin_receipts.command_handlers.get_runtime_config",
            return_value=DummyPluginConfig(120, allowed_user_ids=["123456"]),
        ):
            self.assertTrue(is_receipt_submission_allowed(cast("Any", event)))

    def test_submission_allowed_for_whitelisted_group(self) -> None:
        event = SimpleNamespace(user_id=111111, group_id=654321)

        with patch(
            "nonebot_plugin_receipts.command_handlers.get_runtime_config",
            return_value=DummyPluginConfig(120, allowed_group_ids=["654321"]),
        ):
            self.assertTrue(is_receipt_submission_allowed(cast("Any", event)))

    def test_submission_denied_for_non_whitelisted_sender(self) -> None:
        event = SimpleNamespace(user_id=111111, group_id=222222)

        with patch(
            "nonebot_plugin_receipts.command_handlers.get_runtime_config",
            return_value=DummyPluginConfig(
                120,
                allowed_user_ids=["123456"],
                allowed_group_ids=["654321"],
            ),
        ):
            self.assertFalse(is_receipt_submission_allowed(cast("Any", event)))


class CommandHandlerFlowTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        StubReceiptPrint.handle_handler = None
        StubReceiptPrint.got_handler = None
        register_receipt_handlers(cast("Any", StubReceiptPrint))

    async def test_handle_print_command_announces_timeout_when_content_missing(
        self,
    ) -> None:
        matcher = SimpleNamespace(state={}, send=AsyncMock(), set_arg=AsyncMock())
        event = SimpleNamespace(user_id=123456)
        message = DummyMessage()

        with (
            patch(
                "nonebot_plugin_receipts.command_handlers.get_effective_session_timeout_seconds",
                return_value=119,
            ),
            patch(
                "nonebot_plugin_receipts.command_handlers.get_runtime_config",
                return_value=DummyPluginConfig(120),
            ),
        ):
            await call_registered_handler(
                require_handle_handler(), matcher, event, message
            )

        matcher.send.assert_awaited_once()
        prompt = matcher.send.await_args.args[0]
        self.assertIn("1 分 59 秒", prompt)
        self.assertIn(RECEIPT_TIMEOUT_DEADLINE_KEY, matcher.state)

    async def test_handle_print_command_ignores_non_whitelisted_sender(self) -> None:
        matcher = SimpleNamespace(state={}, send=AsyncMock(), set_arg=AsyncMock())
        event = SimpleNamespace(user_id=111111, group_id=222222)
        message = DummyMessage(text="hello")

        with (
            self.assertRaises(FinishedException),
            patch(
                "nonebot_plugin_receipts.command_handlers.get_runtime_config",
                return_value=DummyPluginConfig(
                    120,
                    allowed_user_ids=["123456"],
                    allowed_group_ids=["654321"],
                ),
            ),
        ):
            await call_registered_handler(
                require_handle_handler(), matcher, event, message
            )

        matcher.send.assert_not_awaited()
        matcher.set_arg.assert_not_awaited()

    async def test_handle_receipt_content_finishes_when_timeout_expired(self) -> None:
        matcher = DummyMatcher()
        matcher.state[RECEIPT_TIMEOUT_DEADLINE_KEY] = 0
        event = SimpleNamespace(user_id=123456)
        receipt_content = DummyMessage(text="late")

        with (
            self.assertRaises(RuntimeError) as exc_info,
            patch(
                "nonebot_plugin_receipts.command_handlers.get_effective_session_timeout_seconds",
                return_value=119,
            ),
            patch(
                "nonebot_plugin_receipts.command_handlers.get_runtime_config",
                return_value=DummyPluginConfig(120),
            ),
        ):
            await call_registered_handler(
                require_got_handler(), matcher, event, receipt_content
            )

        self.assertIn("已超时", str(exc_info.exception))
        self.assertIn("/小票", str(exc_info.exception))

    async def test_handle_receipt_content_ignores_non_whitelisted_sender(self) -> None:
        matcher = DummyMatcher()
        event = SimpleNamespace(user_id=111111, group_id=222222)
        receipt_content = DummyMessage(text="late")

        with (
            self.assertRaises(FinishedException),
            patch(
                "nonebot_plugin_receipts.command_handlers.get_runtime_config",
                return_value=DummyPluginConfig(
                    120,
                    allowed_user_ids=["123456"],
                    allowed_group_ids=["654321"],
                ),
            ),
        ):
            await call_registered_handler(
                require_got_handler(), matcher, event, receipt_content
            )


if __name__ == "__main__":
    unittest.main()
