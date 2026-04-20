from nonebot import on_command
from nonebot.plugin import PluginMetadata

from .command_handlers import register_receipt_handlers
from .config import Config

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

try:
    ReceiptPrint = on_command(
        "ticket",
        aliases={"小票", "ticket", "receipt"},
        block=True,
        priority=10,
    )
except ValueError:
    ReceiptPrint = None

if ReceiptPrint is not None:
    register_receipt_handlers(ReceiptPrint)
