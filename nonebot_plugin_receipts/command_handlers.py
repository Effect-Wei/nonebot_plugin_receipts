from __future__ import annotations

from time import monotonic

from nonebot import get_driver, get_plugin_config
from nonebot.adapters.onebot.v11 import Message, MessageEvent  # noqa: TC002
from nonebot.matcher import Matcher  # noqa: TC002
from nonebot.params import Arg, CommandArg

from .config import Config
from .renderer import ReceiptRenderError, render_receipt
from .spooler import SpoolerClient, SpoolerError
from .template import ReceiptTemplateContext

RECEIPT_TIMEOUT_DEADLINE_KEY = "receipt_timeout_deadline"


def register_receipt_handlers(receipt_print: type[Matcher]) -> None:
    """Attach receipt command handlers to the provided matcher."""

    @receipt_print.handle()
    async def handle_print_command(
        matcher: Matcher, message: Message = CommandArg()
    ) -> None:
        if has_printable_content(message):
            matcher.set_arg("receipt_content", message)
            return

        timeout_seconds = get_effective_session_timeout_seconds()
        reset_receipt_timeout_deadline(matcher, timeout_seconds)
        await matcher.send(build_initial_receipt_prompt(timeout_seconds))

    @receipt_print.got(
        "receipt_content",
    )
    async def handle_receipt_content(
        matcher: Matcher,
        event: MessageEvent,
        receipt_content: Message = Arg("receipt_content"),
    ) -> None:
        timeout_seconds = get_effective_session_timeout_seconds()
        if is_receipt_timeout_expired(matcher):
            await receipt_print.finish(build_timeout_receipt_prompt(timeout_seconds))

        if not has_printable_content(receipt_content):
            reset_receipt_timeout_deadline(matcher, timeout_seconds)
            await receipt_print.reject(build_initial_receipt_prompt(timeout_seconds))

        result: str
        try:
            result = await submit_print_job(event, receipt_content)
        except ReceiptRenderError as exc:
            await receipt_print.finish(f"生成打印内容失败：{exc}")
        except SpoolerError as exc:
            await receipt_print.finish(f"提交到 receipts-spooler 失败：{exc}")

        await receipt_print.finish(result)


async def submit_print_job(event: MessageEvent, message: Message) -> str:
    """Render the incoming message and submit it to receipts-spooler."""
    plugin_config = get_runtime_config()
    rendered = await render_receipt(
        message,
        plugin_config,
        build_template_context(event),
    )
    client = SpoolerClient(plugin_config)
    response = await client.push_raw(rendered)
    queue_size = response.get("queue_size")
    if isinstance(queue_size, int):
        return f"打印任务已提交，当前队列长度：{queue_size}"
    return "打印任务已提交到 receipts-spooler。"


def has_printable_content(message: Message) -> bool:
    """Return whether a message contains text or image content."""
    if message.extract_plain_text().strip():
        return True
    return any(segment.type == "image" for segment in message)


def build_template_context(event: MessageEvent) -> ReceiptTemplateContext:
    """Build receipt template metadata from the incoming event."""
    sender = getattr(event, "sender", None)
    sender_name = ""

    if sender is not None:
        sender_name = str(sender.card or sender.nickname or "").strip()

    if not sender_name:
        sender_name = str(getattr(event, "user_id", ""))

    return ReceiptTemplateContext(
        sender_name=sender_name,
        sender_id=str(getattr(event, "user_id", "")),
    )


def get_runtime_config() -> Config:
    """Fetch the current plugin config from the active NoneBot driver."""
    return get_plugin_config(Config)


def get_effective_session_timeout_seconds() -> int:
    """Return the effective wait timeout bounded by NoneBot's session timeout."""
    plugin_timeout = get_runtime_config().receipt_session_timeout_seconds
    driver_timeout = int(get_driver().config.session_expire_timeout.total_seconds())
    safe_driver_timeout = max(1, driver_timeout - 1)
    return max(1, min(plugin_timeout, safe_driver_timeout))


def build_initial_receipt_prompt(timeout_seconds: int) -> str:
    """Build the first prompt shown when waiting for printable content."""
    timeout_text = format_timeout_duration(timeout_seconds)
    return (
        "请发送一条要打印的消息，支持文本、图片，或两者混合。"
        f" 如在 {timeout_text} 内未发送需要打印的内容，将结束本次等待。"
    )


def build_timeout_receipt_prompt(timeout_seconds: int) -> str:
    """Build the prompt shown when the previous wait window has timed out."""
    timeout_text = format_timeout_duration(timeout_seconds)
    return (
        f"等待打印内容已超时（{timeout_text}）。"
        " 本次等待已结束，请重新发送 /小票 开始新的打印流程。"
    )


def format_timeout_duration(timeout_seconds: int) -> str:
    """Format a timeout duration in a user-facing Chinese string."""
    minutes, seconds = divmod(timeout_seconds, 60)
    if minutes and seconds:
        return f"{minutes} 分 {seconds} 秒"
    if minutes:
        return f"{minutes} 分钟"
    return f"{seconds} 秒"


def reset_receipt_timeout_deadline(matcher: Matcher, timeout_seconds: int) -> None:
    """Reset the receipt-content deadline on the current matcher state."""
    matcher.state[RECEIPT_TIMEOUT_DEADLINE_KEY] = monotonic() + timeout_seconds


def is_receipt_timeout_expired(matcher: Matcher) -> bool:
    """Return whether the current receipt-content wait window has expired."""
    deadline = matcher.state.get(RECEIPT_TIMEOUT_DEADLINE_KEY)
    if not isinstance(deadline, int | float):
        return False
    return monotonic() > deadline
