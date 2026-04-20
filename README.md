# nonebot_plugin_receipts

一个面向 NoneBot2 的独立插件，用来把发送给 Bot 的文本和图片消息转成 ESC/POS 原始打印数据，再投递给 [`receipts-spooler`](https://github.com/Effect-Wei/receipts-spooler)。

当前实现面向 OneBot v11 适配器，适合 QQ 机器人消息场景。

## 功能

- 提供 `ticket`、`小票`、`receipt` 指令，三者互为别名
- 支持命令后直接附带文本和图片
- 如果命令后没有内容，会继续追问下一条消息
- 将文本和图片合成为一张热敏小票图，再编码为 ESC/POS 栅格打印命令
- 通过 `receipts-spooler` 的 `/api/v1/task/push_raw` 接口提交打印任务

## 安装

```powershell
cd nonebot_plugin_receipts
pip install -e .
```

然后在你的 NoneBot2 项目中加载插件：

```python
nonebot.load_plugin("nonebot_plugin_receipts")
```

## 配置

插件通过 NoneBot 全局配置读取以下环境变量：

| 变量                          | 默认值                  | 说明                                  |
| ----------------------------- | ----------------------- | ------------------------------------- |
| `RECEIPTS_SPOOLER_URL`        | `http://127.0.0.1:8000` | `receipts-spooler` 服务地址           |
| `RECEIPTS_SPOOLER_TOKEN`      | 空                      | 对应 `X-Spooler-Token`                |
| `RECEIPTS_SPOOLER_TIMEOUT`    | `5.0`                   | 调用 spooler 的 HTTP 超时             |
| `RECEIPT_IMAGE_FETCH_TIMEOUT` | `5.0`                   | 下载图片消息内容时的 HTTP 超时        |
| `RECEIPT_RENDER_MODE`         | `raster`                | 渲染模式，可选 `raster`/`hybrid`      |
| `RECEIPT_PRINTER_WIDTH`       | `576`                   | 小票像素宽度，最大 `576`              |
| `RECEIPT_TEMPLATE_PATH`       | 空                      | 可选，指向渲染模板 JSON 文件          |
| `RECEIPT_FONT_PATH`           | 空                      | 可选，建议配置支持中文的 TTF/OTF 字体 |
| `RECEIPT_FONT_SIZE`           | `24`                    | 文本字号                              |
| `RECEIPT_LINE_SPACING`        | `6`                     | 文本行距                              |
| `RECEIPT_SECTION_GAP`         | `6`                     | 文本和图片之间的垂直间距              |
| `RECEIPT_SESSION_TIMEOUT_SECONDS` | `120`               | 等待用户补发打印内容的超时时间（秒）   |
| `RECEIPT_FEED_LINES`          | `4`                     | 打印后走纸行数                        |
| `RECEIPT_ENABLE_CUT`          | `true`                  | 是否附加切纸命令                      |

### 渲染模式

- `raster`：把文本和图片一起渲染成整张位图，再输出 ESC/POS 栅格数据，兼容性最好。
- `hybrid`：文本走打印机原生字符输出，图片仍走位图，能减少大量文字被渲染成图片。

`hybrid` 模式下，中文是否正常输出取决于打印机对中英文字符集的支持情况。

### 渲染模板

如果你想单独调整小票布局，可以配置 `RECEIPT_TEMPLATE_PATH` 指向一个 JSON 文件。项目根目录里附带了一个示例文件 [`receipt_template.example.json`](receipt_template.example.json)。

支持的模板字段：

| 字段                           | 默认值                                     | 说明                   |
| ------------------------------ | ------------------------------------------ | ---------------------- |
| `margin`                       | `16`                                       | 左右和顶部内边距       |
| `header_enabled`               | `false`                                    | 是否渲染页眉           |
| `header_text`                  | `{sender_name}({sender_id})`               | 页眉文字模板           |
| `footer_enabled`               | `true`                                     | 是否渲染页脚           |
| `footer_text`                  | `{sender_name}({sender_id}) @ {timestamp}` | 页脚文字模板           |
| `footer_timestamp_format`      | `%Y-%m-%d %H:%M:%S`                        | 时间格式               |
| `footer_timezone_offset_hours` | `8`                                        | 页脚时间使用的时区偏移 |

`header_text` 和 `footer_text` 都支持这些占位符：

- `{timestamp}`
- `{sender_name}`
- `{sender_id}`

当 `header` 存在时，会在页眉和正文之间绘制一条全宽横线；当 `footer` 存在时，会在正文和页脚之间再绘制一条全宽横线。

示例：

```json
{
  "margin": 24,
  "header_enabled": true,
  "header_text": "来自 {sender_name}({sender_id})",
  "footer_enabled": true,
  "footer_text": "{sender_name}({sender_id}) 打印于 {timestamp}",
  "footer_timestamp_format": "%Y/%m/%d %H:%M",
  "footer_timezone_offset_hours": 8
}
```

## 使用

直接在命令后附带内容：

```text
/小票 今晚睡大觉
```

或者：

1. 发送 `/小票`
2. 按提示继续发送一条包含文本、图片或两者混合的消息

插件会把纯文本和图片消息段一起打印，并在提交成功后回复当前队列长度。

如果命令后没有直接附带内容，插件会提示用户继续发送，并明确说明多久后超时。  
如果用户在该时间窗口后才继续回复，插件会提示“已超时”，并直接结束本次等待；此时需要重新发送 `/小票` 开始新的打印流程。

`RECEIPT_SESSION_TIMEOUT_SECONDS` 的实际生效时间不会超过 NoneBot 全局 `SESSION_EXPIRE_TIMEOUT`，建议两者保持一致或让前者更小。

文本里支持类似 Markdown 的多级标题语法：

- `# 一级标题`
- `## 二级标题`
- `### 三级标题`
- 一直到 `###### 六级标题`

在 `raster` 模式下会使用更大的字号和额外留白；在 `hybrid` 模式下会尽量映射为 ESC/POS 的加粗和放大文本。  
如果需要打印以 `#` 开头的普通文本，可以写成 `\# 普通文本`。

## 注意事项

- 如果你需要打印中文，最好配置 `RECEIPT_FONT_PATH` 指向支持中文的字体文件。
- 图片消息需要 OneBot 事件中带有可访问的 `url`，或消息段 `file` 为 `base64://...` / `http(s)://...`。
- 本插件不会直接连接打印机，只负责把任务提交到 `receipts-spooler`。
