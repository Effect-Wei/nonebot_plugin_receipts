from nonebot import get_plugin_config, on_command
from nonebot.adapters.onebot.v11 import Message, MessageEvent
from nonebot.matcher import Matcher
from nonebot.params import Arg, CommandArg
from nonebot.plugin import PluginMetadata

from .config import Config
from .renderer import ReceiptRenderError, render_receipt
from .spooler import SpoolerClient, SpoolerError
from .template import ReceiptTemplateContext

__plugin_meta__ = PluginMetadata(
    name="小票打印",
    description="将发送给 Bot 的文本和图片消息通过 receipts-spooler 打印",
    usage=(
        "发送 /小票 后附带文本/图片，或单独发送命令后按提示再发送一条要打印的消息。"
    ),
    type="application",
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={},
)

plugin_config = get_plugin_config(Config)

ReceiptPrint = on_command(
    "ticket",
    aliases={"小票", "ticket", "receipt"},
    block=True,
    priority=10,
)


def _has_printable_content(message: Message) -> bool:
    if message.extract_plain_text().strip():
        return True
    return any(segment.type == "image" for segment in message)


def _build_template_context(event: MessageEvent) -> ReceiptTemplateContext:
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


async def _submit_print_job(event: MessageEvent, message: Message) -> str:
    rendered = await render_receipt(
        message,
        plugin_config,
        _build_template_context(event),
    )
    client = SpoolerClient(plugin_config)
    response = await client.push_raw(rendered)
    queue_size = response.get("queue_size")
    if isinstance(queue_size, int):
        return f"打印任务已提交，当前队列长度：{queue_size}"
    return "打印任务已提交到 receipts-spooler。"


@ReceiptPrint.handle()
async def handle_print_command(
    matcher: Matcher, message: Message = CommandArg()
) -> None:
    if _has_printable_content(message):
        matcher.set_arg("receipt_content", message)


@ReceiptPrint.got(
    "receipt_content",
    prompt="请发送一条要打印的消息，支持文本、图片，或两者混合。",
)
async def handle_receipt_content(
    event: MessageEvent,
    receipt_content: Message = Arg("receipt_content"),
) -> None:
    if not _has_printable_content(receipt_content):
        await ReceiptPrint.reject("这条消息里没有可打印的文本或图片，请重新发送。")

    result: str
    try:
        result = await _submit_print_job(event, receipt_content)
    except ReceiptRenderError as exc:
        await ReceiptPrint.finish(f"生成打印内容失败：{exc}")
    except SpoolerError as exc:
        await ReceiptPrint.finish(f"提交到 receipts-spooler 失败：{exc}")

    await ReceiptPrint.finish(result)
