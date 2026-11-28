# xdoc 使用手册

> 把 **PDF / 图片 / 音频 / 视频 / Office / 富文本** 忠实转成文本，让 Agent（或你自己）直接读、直接引用。
>
> 本手册覆盖：安装自检 → CLI 与 MCP 两种用法 → 输出契约 → 插件 → 按任务查 → 故障排查 → 性能与限制。
> 想看证据（验收数据、与 anymd 的对比）见 [`ACCEPTANCE.md`](ACCEPTANCE.md) 与 [`COMPARISON.md`](COMPARISON.md)。

---

## 0. 30 秒上手

```bash
uv tool install xdoc-tools    # 装一次
xdoc demo                 # 用内置示例跑一遍（不用准备样本）
xdoc doctor                 # 自检：应打印「核心依赖齐全，基础能力可用。」
xdoc read report.pdf        # 读一个 PDF，输出 Markdown
xdoc setup                  # 体检 + 打印接给 Agent 的方法（只读，不改你的文件）
```

给 Agent 用：把 xdoc 注册成 MCP 服务（见 [§2.2](#22-mcp给-agent)），Agent 就会多出一个 `read` 工具。

---

## 1. 安装与自检

### 1.1 三种装法

| 场景 | 命令 | 说明 |
| --- | --- | --- |
| 长期用（推荐） | `uv tool install xdoc-tools` | 装到 `~/.local/bin/xdoc.exe`（Windows）/ `~/.local/bin/xdoc` |
| 临时用一次 | `uvx xdoc-tools read file.pdf` | 不想安装，uv 会临时拉起 |
| 从源码（开发者） | 仓库根目录执行 `uv sync` 后 `uv run xdoc …`；或 `uv tool install --force .` | `uv tool install --force .` 会覆盖已装的 xdoc |

> `uv` 没有的话：`pip install uv`，或从 <https://docs.astral.sh/uv/getting-started/installation/> 取对应平台的安装命令。

### 1.2 自检：`xdoc doctor`

```bash
xdoc doctor
```

输出分四段：

| 段 | 内容 | 缺失怎么办 |
| --- | --- | --- |
| **核心依赖** | `pymupdf`(PDF)、`docx`(DOCX)、`pptx`(PPTX)、`openpyxl`(XLSX)、`bs4`(HTML)、`markdownify`(HTML→MD)、`mcp`(MCP 服务) | 全部随包安装；若显示 `[缺失]`，重装一次 xdoc。**核心依赖有缺失时 doctor 返回 exit 1** |
| **外部工具（可选）** | LibreOffice（旧版 `.doc/.ppt/.xls`）、ffmpeg（视频抽帧） | 缺失只影响对应格式，不影响其它能力 |
| **插件（可选）** | `ocr` / `asr` / `asr-zh` / `media` 的安装状态 | 按需安装，见 [§4](#4-插件按需下载随插随用可卸载) |
| **解析缓存** | 缓存目录、条目数与占用 | 太大就 `xdoc cache clear`（见 [§3.7](#37-解析缓存重复读几乎瞬时)） |

结尾会明确告诉你结论：`核心依赖齐全，基础能力可用。`

### 1.3 Windows 注意事项

- **中文输出**：已内置修复（自动切 UTF-8 控制台代码页 + 流编码降级），中文文档直接输出不会崩。若终端仍显示异常，用 `-o out.md` 写文件再打开。
- **PATH**：`uv tool install` 装到 `%USERPROFILE%\.local\bin`。如果 MCP 客户端不解析 PATH，配置里写绝对路径（见 §2.2）。
- **旧版 Office**：需要本机装 LibreOffice，`doctor` 会告诉你路径；它不在 PATH 也没关系，xdoc 会自己找。

### 1.4 第一次用：`xdoc demo` 与 `xdoc setup`

| 命令 | 做什么 | 会不会改你的文件 |
| --- | --- | --- |
| `xdoc demo` | 用随包附带的示例（一个 Markdown + 一个 PDF）跑一遍：全文、结构视图（`--outline`）、检索三种看法都演给你看；示例会复制到临时目录，你可以直接改着玩 | 不会（只写临时目录） |
| `xdoc setup` | 体检（依赖、插件、缓存、命令是否可用）+ 打印接给 Agent 的方法：Claude Code 一行命令、Claude Desktop 的配置路径与 JSON 片段 | **不会**（只打印，不写任何配置文件） |

`xdoc setup` 故意只打印：MCP 配置要写进 Claude 自己的配置文件，那一步由你决定。

---

## 2. 两种用法

CLI 与 MCP **共用同一个内核**（`api.read_document`），同一个文件两种入口输出内容一致。

### 2.1 CLI

```bash
xdoc read <path> [选项]
xdoc grep <pattern> <path> [选项]   # 检索：只给出命中的位置与片段
xdoc plugin list | add <name> | remove <name>
xdoc cache info | clear          # 解析缓存：看占用 / 清空
xdoc demo                       # 用内置示例跑一遍（Markdown + PDF）
xdoc setup                      # 体检 + 打印接给 Agent 的方法（只读）
xdoc doctor
xdoc serve                     # 以 stdio 方式启动 MCP 服务
xdoc --version
```

`xdoc read` 的全部选项：

| 选项 | 取值 | 默认 | 说明 |
| --- | --- | --- | --- |
| `--format` | `markdown` / `text` / `json` | `markdown` | 输出格式 |
| `--max-tokens` | 整数 | 不限 | token 预算；超出即截断，并在 front-matter 给出 `next_cursor`（`0` = 不限） |
| `--cursor` | 字符串 | 无 | 续读游标（接上一次的 `next_cursor`） |
| `--pages` | `1-5,8` | 全部 | 按序号筛选章节：PDF 页 / PPT 幻灯片 / Excel 的**第 N 个表格块**（Excel 不是工作表）；越界会报错而不是静默返回空 |
| `--outline` | 开关 | 关 | 只输出结构（标题 + 锚点），不要正文；适合先看目录再定点读 |
| `--ocr` | `auto` / `on` / `off` / `vlm` | `auto` | OCR 开关（需装 `ocr` 插件）。`vlm` 目前与 `on` 等效（本地 doc-VLM 未接入） |
| `--asr` | `auto` / `on` / `off` / `zh` / `whisper` | `auto` | `zh`=中文 FunASR；`whisper`=通用 faster-whisper；`auto`=自动挑引擎（详见 §4.3） |
| `--asr-model` | 如 `small` / `large-v3` | 不传=引擎默认 | 不传时 `asr` 用 `small`；`asr-zh` 用 Paraformer-zh |
| `--asr-language` | 如 `zh` / `en` | 不传=自动识别 | 语音转写的语言（中文音频写 `zh` 更稳） |
| `--tables` | `auto` / `on` / `off` | `auto` | PDF 表格识别：`auto`=只对有画线的页识别（快）；`on`=逐页识别（慢）；`off`=不识别 |
| `--no-images` | 开关 | 关 | 不提取内嵌图片（更快、更小输出） |
| `--no-front-matter` | 开关 | 关 | 不输出元数据头（只对 `markdown` 有意义，`text`/`json` 本来就没有 front-matter） |
| `--no-cache` | 开关 | 关 | 跳过解析缓存，强制重新解析 |
| `-q, --quiet` | 开关 | 关 | 不显示进度提示（进度写在 stderr，不影响 stdout 的正文） |
| `-o, --output` | 文件路径 | 标准输出 | 写文件而不是打印 |

`path` 可以是**目录**：会把目录里所有能读的文件合并成一份文档（锚点带文件名，见 §3.2）。

`xdoc grep` 的选项（在 `xdoc read` 的选项之外多这几个）：

| 选项 | 取值 | 默认 | 说明 |
| --- | --- | --- | --- |
| `--regex` | 开关 | 关 | 把检索词当**正则表达式**；写错会明确报错 |
| `--case-sensitive` | 开关 | 关 | 区分大小写（默认忽略） |
| `--context` | 整数 | `0` | 命中行前后各带几行上下文 |
| `--limit` | 整数 | `50` | 最多返回多少条命中（stderr 会报出命中总数） |

退出码：`0` 成功；`2` 业务错误（stderr 打印 `错误: …`）；`1` 其它异常；`130` Ctrl+C（会打印「已取消」）。

常用例子：

```bash
xdoc read report.pdf                          # Markdown
xdoc read data.xlsx --format json             # 结构化 JSON
xdoc read book.pdf --outline                  # 只要结构（标题+锚点），先不取正文
xdoc read book.pdf --max-tokens 8000          # 超长自动截断，给出 next_cursor
xdoc read book.pdf --cursor <next_cursor>     # 续读
xdoc read slides.pptx --pages 1-5,8           # 只看第 1–5 页和第 8 页
xdoc read ./docs --outline                   # 读整个目录：合并成一份
xdoc read paper.pdf --tables on               # 强制逐页表格识别
xdoc read scan.pdf --ocr on                   # 强制 OCR（扫描件）
xdoc read talk.mp3 --asr zh --asr-model small # 中文转写
xdoc read talk.mp3 --asr-language zh           # 指定转写语言
xdoc grep "Transformer" paper.pdf             # 只找命中位置，不给全文
xdoc grep "参考文献" ./docs --context 1        # 在整个目录里检索，带上下文行
xdoc demo                                      # 用内置示例跑一遍
xdoc setup                                     # 打印接给 Agent 的方法
```

### 2.2 MCP（给 Agent）

xdoc 只暴露**一个工具** `read`（用户明确要求的「一个入口」）。

**OpenCode / Claude Desktop / Cursor 通用形状**（键名按你的客户端调整）：

```jsonc
{
  "mcp": {
    "servers": {
      "xdoc": {
        "type": "local",
        "command": ["xdoc", "serve"]
      }
    }
  }
}
```

Windows 上客户端不解析 PATH 时写绝对路径：

```jsonc
"command": ["C:\\Users\\<你的用户名>\\.local\\bin\\xdoc.exe", "serve"]
```

`read` 工具的参数（每个参数在 schema 里都带 `description` 和取值枚举，Agent 不需要猜）：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `path` | string | **必填** | 文件路径，**也可以是目录**（目录里能读的文件会合并成一份） |
| `format` | string | `markdown` | `markdown` / `text` / `json` |
| `max_tokens` | int | `30000` | 本次返回的 token 上限；**`0` 表示不限**；超出即截断并返回 `next_cursor` |
| `cursor` | string? | 无 | 续读游标 |
| `pages` | string? | 无 | 如 `1-5,8` |
| `outline` | bool | `false` | 只要结构不要正文（标题 + 锚点） |
| `grep` | string? | 无 | 只返回包含这个词的片段（默认按字面匹配、忽略大小写） |
| `grep_regex` | bool | `false` | `grep` 按正则解释 |
| `grep_context` | int | `0` | 命中行前后各带几行上下文 |
| `grep_limit` | int | `50` | 最多返回多少条命中 |
| `ocr` | string | `auto` | `auto` / `on` / `off` / `vlm` |
| `asr` | string | `auto` | `auto` / `on` / `off` / `zh` / `whisper` |
| `asr_model` | string? | 无 | 模型名；不传时 `asr` 用 `small`、`asr-zh` 用 Paraformer-zh |
| `asr_language` | string? | 无 | 语音转写语言，如 `zh` / `en`；省略则自动识别 |
| `tables` | string | `auto` | `auto` / `on` / `off` |
| `images` | string | `refs` | `refs`=图片抽到资产目录并在正文给路径；`none`=不抽 |
| `front_matter` | bool | `true` | 是否带元数据头 |

> MCP 版比 CLI 多一个 `images` 参数；CLI 里用 `--no-images` 等价。
> MCP 侧**没有**缓存开关（服务端始终用缓存，缓存对读的结果没有影响）；CLI 侧有 `--no-cache`。
> **MCP 默认 `max_tokens=30000`**：一次读十几万字会占满模型上下文，所以默认给预算；确实要全文时传 `max_tokens=0`。CLI 默认不限，保持既有习惯。
> **出错时工具返回 `isError=true`**，正文里写明原因（例如「文件不存在: …」），不会被当成正常结果。
> 工具描述里已经写清「只转换，不摘要」、省 token 的三步用法与插件缺失时的安装命令，Agent 会照着做。

**省 token 的推荐顺序**：

1. `read(path, outline=true)` —— 只要结构（标题 + 锚点），几十行就能看清整份文档；
2. `read(path, pages="7-9")` —— 按锚点定位到真正要的那几页；
3. `read(path, grep="关键词")` —— 只取命中处的片段（整篇里只有几处相关时最省）；
4. `read(path, cursor="…")` —— 内容仍太长时按游标续读。

**让 Agent 主动用它**：仓库自带 `skills/xdoc-read/SKILL.md`，复制到 `~/.agents/skills/xdoc-read/`（或 `~/.claude/skills/`）即可；它告诉 Agent 什么时候该用这个工具、怎么按锚点引用原文。

---

## 3. 输出契约

xdoc 的价值不在「能读」，在**读出来的东西可核对、可引用**。三件事保证这点：

### 3.1 front-matter 元数据头

```markdown
---
source: C:\Users\me\docs\report.pdf
kind: pdf
sections: 12
chars: 48123
engine: pymupdf 2.2
pages: 12
tables_mode: auto
sha256: 3df79d34…（原文件指纹）
bytes: 13264
assets_root: C:\Users\me\.local\share\xdoc\assets
---
```

| 字段 | 含义 |
| --- | --- |
| `source` | 原文件绝对路径 |
| `kind` | 识别出的类型（`pdf` / `docx` / `xlsx` / `audio` / `video` / `collection` …） |
| `sections` / `chars` | 章节数与字符数 |
| `engine` | 实际使用的转换器（`pymupdf 2.2`、`python-docx`、`python-pptx`、`openpyxl`、`collection`、`builtin`…） |
| `sha256` / `bytes` | 原文件指纹与大小，便于确认「读的是哪一份」 |
| `assets_root` | 图片 / 抽帧的落盘目录 |
| `cache` | `hit` = 用了解析缓存；`miss` = 这次重新解析的 |
| 类型专属 | PDF 有 `pages`；Excel 有 `sheets`；音视频有 `duration` / `fps` |
| OCR | **只有图片 OCR** 的块带 `meta.avg_score`（置信度）；扫描 PDF 的 OCR 结果没有置信度 |
| 读目录时 | `file_count`（读到几个文件）、`files`（每个文件的类型与体量）、`skipped`（哪些文件被跳过、为什么） |
| `outline` 模式 | `outline: true`，表示这次只给结构 |
| 检索时 | `search:` 给出 `pattern` / `total`（命中总数）/ `returned`（本次返回）/ `truncated`（是否被 limit 截断） |
| 截断时 | `truncated: true` 与 `next_cursor` 会出现在这里 |

用 `--no-front-matter` 或 `front_matter=false` 可关闭（只对 `markdown` 有效；`text` / `json` 本身就没有 front-matter）。

### 3.2 锚点（引用的坐标系）

| 来源 | 锚点 |
| --- | --- |
| PDF | `<!-- page 3 -->` |
| PPT | `<!-- slide 2 -->` |
| Excel | `<!-- sheet: 销售明细 -->` |
| 音频 / 视频 | `<!-- t=00:00:00 -->`（整段一个锚点；每条转写自带 `[00:00.880]` 时间戳前缀） |
| DOCX / Markdown / 纯文本 | `<!-- doc:0 -->`（整篇一个章节） |
| HTML | `<!-- section:0 -->`（按 h1/h2 切段） |
| EPUB | `<!-- chapter:0 -->`（按章切分） |
| 图片 | `<!-- image:0 -->` |
| 读目录时 | `<!-- file:report.pdf page 3 -->`（前面多一段文件名，JSON 里是 `file` 字段） |

锚点同时出现在 Markdown 与 JSON 里（JSON 中是 `anchor` 字段，值为 `page:3` / `slide:2` / `sheet:销售明细` / `doc:0` / `section:0` / `chapter:0` / `time:00:00:00` 这种原始形式；Markdown 里的 `t=00:00:00` 是它的展示形式）。

有了锚点，Agent 的回答可以精确到「第 3 页」「第 2 张幻灯片」「第 12 秒」，而不是含糊的「第几部分」。

### 3.3 三种输出格式

- **`markdown`（默认）**：保留标题层级、列表、表格（标准 Markdown 表格）、图片（`![alt](绝对路径)`）、引用、代码块。适合直接喂给模型。
- **`text`**：纯文本，不带 Markdown 语法。适合 `grep`、做 diff、或嵌入检索流程。
- **`json`**：结构化输出，便于程序处理（下面是真实输出片段）：

```json
{
  "source": "C:\\Users\\me\\docs\\calibre_demo.docx",
  "kind": "docx",
  "meta": {
    "engine": "python-docx",
    "paragraphs": 92,
    "tables": 5,
    "sha256": "269329fc…",
    "bytes": 1311881,
    "assets_root": "C:\\Users\\me\\.local\\share\\xdoc\\assets",
    "truncated": true,
    "next_cursor": "MDoxMDow"
  },
  "chars": 1348,
  "sections": [
    {
      "label": "document",
      "anchor": "doc:0",
      "blocks": [
        { "kind": "text", "text": "Demonstration of DOCX support in calibre" },
        { "kind": "heading", "text": "Text Formatting", "level": 1 },
        { "kind": "table", "header": true, "rows": [["项目", "金额"], ["合同", "1,234.00"]] },
        { "kind": "image", "text": "插图", "src": "C:\\…\\assets\\calibre_demo-9f2\\p1-img1.jpeg" }
      ]
    }
  ]
}
```

`kind` 常见取值：`heading` / `text` / `list_item` / `table` / `image` / `quote` / `code` / `note`。

`kind: "code"` 的块如果源文件里写了语言标注（Markdown 的 ` ```python `），会多一个 `"lang": "python"` 字段。

### 3.4 截断与续读（长文档必读）

给 `max_tokens` 后，xdoc 会**截断而不是硬塞**，并在 front-matter 给出续读游标：

```bash
xdoc read book.pdf --max-tokens 8000
# ---
# truncated: true
# next_cursor: eyJzZWN0aW9uIjoyLCJibG9jayI6Nywib2Zmc2V0IjoxMjM0fQ
# ---
```

把 `next_cursor` 原样传回去继续读：

```bash
xdoc read book.pdf --max-tokens 8000 --cursor eyJzZWN0aW9uIjoy…
```

规则（实测覆盖长文不丢内容）：

- **坐标始终相对完整文档**，所以可以链式续读：`read(cursor=C1) → C2 → read(cursor=C2)`；
- **文本按字符续，表格按行续**（表头每次重复给出，方便 Agent 始终看得懂列的含义）；
- 表格**不会被整块丢掉**——预算不够就按行切；
- token 估算口径：中文约 1 字 1 token，英文/数字约 3.6 字符 1 token（估算用于切片，不用于计费）。

### 3.5 先看结构：outline 模式

长文档最省 token 的做法不是加预算，而是**先不看正文**：

```bash
xdoc read zh_wiki_python.pdf --outline
# ---
# outline: true
# ---
# <!-- page 1 -->
# # Python（简介）
# <!-- page 2 -->
# # 发展历史
```

每个章节只保留标题（没有标题的章节保留正文首行当提示）与锚点，正文一律不给。
实测 64 页中文维基：全文 125702 字符 → outline 5251 字符（**4.2%**）。
看完结构再用 `--pages` 精确取正文，或用 `--cursor` 续读。

MCP 侧对应参数 `outline=true`（`read(path, outline=true)`）。

### 3.6 读目录：一次拿一批文件

```bash
xdoc read ./docs --outline
```

- 目录里所有能读的文件（PDF/Office/HTML/文本/图片/音视频…）合并成**一份**文档；
- 锚点带文件名：`<!-- file:report.pdf page 3 -->`，不会张冠李戴；
- front-matter 给出 `file_count`、`files`（每个文件的类型、章节数、字符数、是否命中缓存）；
- 认不出的格式、隐藏文件、临时文件（`~$…`）会被跳过，并在 `skipped` 字段里说明原因——不会静默消失；
- 目录里一个可读文件都没有时，报错「目录里没有可读的文件」。

> `--pages` 在目录模式下对**每个文件分别生效**（如 `--pages 1-2` = 每个文件的前两页）；token 预算与 `cursor` 则作用在合并后的整份文档上。

### 3.7 解析缓存（重复读几乎瞬时）

第一次读某个文件会解析并把结果缓存起来，之后同样的读法直接命中：

```bash
xdoc read paper.pdf --tables on     # 第一次：解析（约 2.5s）
xdoc read paper.pdf --tables on     # 第二次：命中缓存（约 0.02s）
xdoc cache info                     # 看缓存目录、条目数、占用
xdoc cache clear                    # 清空
```

- 缓存键 = **文件内容 sha256** + 影响解析结果的选项（`tables` / `ocr` / `asr` / `images` …）+ xdoc 版本 + 已装插件清单。文件改了或选项变了就自动重新解析，不会读到过期结果。
- **页码筛选（`--pages`）不参与缓存键**：缓存里存的是未筛选的全文，切页不需要重新解析。
- **检索也不参与缓存键**：缓存里存的是全文，换个词检索不用重新解析。
- 缓存目录：`~/.local/share/xdoc/cache`（可用环境变量 `XDOC_CACHE_DIR` 改）；`--no-cache` 可跳过缓存。
- front-matter 的 `cache: hit|miss` 说明这次走的是缓存还是重新解析。

### 3.8 检索：只取命中处，不给全文

```bash
xdoc grep "Transformer" paper.pdf --context 1
xdoc grep "参考文献" ./docs --limit 20
xdoc grep "def .*\\(" code.py --regex
```

输出只包含命中的片段（按原文顺序、按章节分组），并保留锚点：

```markdown
---
kind: pdf
search: {"pattern":"Transformer","regex":false,"ignore_case":true,"context":1,"total":2,"returned":2,"truncated":false}
---
<!-- page 24 -->
## 注意力机制
Transformer 的核心是自注意力……
```

（`search` 是一整行的 JSON，YAML 也认；`total` 是命中总数，`returned` 是本次返回条数。）

- 默认按**字面**匹配、**忽略大小写**；`--regex` 按正则，`--case-sensitive` 区分大小写；
- `--context N` 让命中行前后各带 N 行；`--limit N` 限制返回条数（front-matter 里的 `total` 始终是命中总数）；
- 行号 = 该章节正文里的第几行（Markdown / 纯文本里是第 N 个**非空**行——转换器本来就不保留空行）；
- 目录模式下在**所有能读的文件**里检索，命中会标出来自哪个文件（`<!-- file:xxx.pdf page 3 -->`）；
- 检索与 `outline` 互斥（一个看结构、一个找内容），同时用会报错；
- 没有命中时给一段说明而不是空白输出。

MCP 侧对应参数：`read(path, grep="关键词")`、`grep_regex` / `grep_context` / `grep_limit`。

### 3.9 类型识别：看内容，不看扩展名

xdoc 先看**文件内容**（magic bytes、zip 内部结构），再看扩展名：

- 改错了扩展名的文件照样能读对（`report.pdf` 其实是 docx → 按 docx 读）；
- 任何 UTF-8 文本文件都能当纯文本读（`.json` / `.yaml` / `.py` 等）；
- `.doc` / `.ppt` / `.xls` 会先经 LibreOffice 转成现代格式再读，所以读出来的 `kind` 是 `docx` / `pptx` / `xlsx`；
- 完全认不出的二进制会被跳过（在目录模式下列进 `skipped`），单文件模式则报「暂不支持的文件类型」。

---

## 4. 插件（按需下载、随插随用、可卸载）

基础能力（解析 PDF/Office/HTML/文本）**零重依赖**，随包就能用。以下插件是可选增强：装上即生效，卸载即回到基础能力。

| 插件 | 作用 | 体积（实测） | 什么时候需要 |
| --- | --- | --- | --- |
| `ocr` | 本地 OCR（RapidOCR / PP-OCRv6，中英文，CPU） | 约 280MB | 扫描 PDF、截图、照片、含图文字的 PDF |
| `asr` | 通用语音转写（faster-whisper small） | 约 730MB | 英文、多语种录音 |
| `asr-zh` | 中文语音转写（FunASR Paraformer-zh） | 约 3.2GB | 中文录音、会议、访谈 |
| `media` | ffmpeg / ffprobe | 约 210MB | 视频抽帧、音频抽取 |

```bash
xdoc plugin list              # 看状态（含每个插件的实际占用）
xdoc plugin add ocr           # 安装（install / download 是同义词）
xdoc plugin remove ocr        # 卸载（uninstall 是同义词）
```

- 插件装在 `~/.local/share/xdoc/plugins/<name>/`：Python 插件含独立 `venv/` 与 `models/`，`media` 含 `ffmpeg.exe` / `ffprobe.exe`。**每个插件在自己的隔离 venv 里跑**，不会污染 xdoc 本体。
- **运行期不联网**：模型只在安装时下载一次，之后离线可用（验收时把 `HTTP(S)_PROXY` 指向黑洞仍能正常 OCR/转写）。
- 插件是 worker 子进程：主进程只传文件路径与 JSON，不加载模型。
- **安装过程有输出**：依赖下载、模型预下载的进度实时打印在 stderr，不会对着一个静默的终端等几分钟。
- `xdoc plugin list` 与 `xdoc doctor` 会显示**实际占用**（磁盘上的真实体积），可以拿它和上表的估计值对照。

### 4.1 `asr` 的 auto 是怎么挑引擎的

| `--asr` | 行为 |
| --- | --- |
| `auto`（默认） | 优先 `asr`（faster-whisper）；若它识别出是中文、且装了 `asr-zh`，则**用中文引擎再转写一遍**（中文精度更高） |
| `zh` | 直接用 `asr-zh`（FunASR），没装就回落 `asr` |
| `whisper` | 直接用 `asr`（faster-whisper） |
| `off` | 不转写，只给媒体元信息 |

---

## 5. 按任务查

### 5.1 文本型 PDF（含表格）

```bash
xdoc read paper.pdf
```

- 页级锚点 `<!-- page N -->`，标题按字号推断层级，**有画线的表格**还原成 Markdown 表格。
- 只关心几页：`xdoc read paper.pdf --pages 1-5,8`
- 表格没识别出来（页面上没有画线）：`xdoc read paper.pdf --tables on`（更慢，会逐页按画线识别）。

### 5.2 扫描 PDF / 图片（OCR）

```bash
xdoc plugin add ocr        # 一次性
xdoc read scan.pdf         # 无文本层的页会自动 OCR
xdoc read photo.jpg
```

- 扫描 PDF 会逐页以 200dpi 栅格化后 OCR，识别结果替换掉「本页没有文本层」的提示。
- **图片** OCR 的置信度写在识别块的 `meta.avg_score` 里（用 `--format json` 可见）；扫描 PDF 的 OCR 结果**没有**置信度（PDF 侧只给文字）。
- 极小字号（<8pt）可能识别不全 —— 这是 200dpi + 小模型的边界。

### 5.3 音频

```bash
xdoc plugin add asr         # 或 asr-zh
xdoc read talk.mp3                     # auto
xdoc read talk.mp3 --asr zh            # 强制中文引擎
xdoc read talk.mp3 --asr-model large-v3
```

输出形如（真实输出）：

```markdown
---
kind: audio
duration: 5.55
segments: 1
asr: installed plugin
---

<!-- t=00:00:00 -->
[00:00.880] 欢迎大家来体验达摩院推出的语音识别模型。
```

- 时间戳来自模型本身（中文用逐字时间戳对齐），实测误差 ≤ 1s。
- 中文首调要加载约 1GB 模型（CPU），单次 30–60s；之后很快。
- 没装插件时不会报错，只给媒体元信息（时长、编码）。

### 5.4 视频

```bash
xdoc plugin add media        # ffmpeg
xdoc read movie.mp4
```

- 输出音轨转写（带时间戳锚点）+ **关键帧 PNG**（**总共最多 12 帧**，均匀分布在整段时长上，落在资产目录，正文里给绝对路径）。模型可以直接看这些帧做画面理解。

真实输出（`--asr off` 时只有帧，装了 ASR 插件则前面还有转写段落）：

```markdown
---
kind: video
container: mov,mp4,m4a,3gp,3g2,mj2
resolution: 640x360
duration: 60.1
frames: 12
---

<!-- t=00:00:00 -->
![00:00.000 关键帧](C:\Users\me\.local\share\xdoc\assets\big_buck_bunny-ee6cd16ac9\frame-00-00.000.png)
![00:05.008 关键帧](C:\Users\me\.local\share\xdoc\assets\big_buck_bunny-ee6cd16ac9\frame-00-05.008.png)
```

### 5.5 Excel（尤其大表）

```bash
xdoc read data.xlsx                  # Markdown 表格
xdoc read data.xlsx --format json    # 结构化
xdoc read data.xlsx --pages 1-3      # 只看前 3 个表格块（Excel 的「节」是表格，不是工作表）
```

- 日期时间按 **ISO 8601** 输出（`2014-01-01T00:00:00`），避免地区格式歧义。
- 单元格公式：优先输出缓存的计算值，没有缓存值时保留公式原文。
- 表很大时配合 `--max-tokens` + `--cursor` 按行续读（表头每次重复）。

真实输出（`microsoft_sample.xlsx`，11216 个单元格）：

```markdown
---
kind: xlsx
sheets: 1
cells: 11216
---

<!-- sheet: Sheet1 -->
| Segment | Country | Product | … | Date | … |
| --- | --- | --- | --- | --- | --- |
| Government | Canada | Carretera | … | 2014-01-01T00:00:00 | … |
```

### 5.6 PPT

```bash
xdoc read deck.pptx                  # 全部
xdoc read deck.pptx --pages 1-5,8    # 指定幻灯片
```

每张幻灯片一个 `<!-- slide N -->` 锚点；演讲者备注也会带出来（渲染成 `> [!NOTE] 备注: …`）。

真实输出：

```markdown
---
kind: pptx
slides: 2
---

<!-- slide 1 -->
# Title of the first slide
Subtitle of the first slide
> [!NOTE] 备注: I am the notes of the first slide

<!-- slide 2 -->
# This is the second slide
```

### 5.7 旧版 Office（`.doc` / `.ppt` / `.xls`）

```bash
xdoc read old.doc
```

需要本机 LibreOffice（`xdoc doctor` 会检查）。转换在临时目录完成，不动原文件。

### 5.8 HTML / Markdown / 纯文本 / CSV / EPUB

```bash
xdoc read page.html
xdoc read notes.md
xdoc read data.csv
xdoc read book.epub
```

- HTML 会剥掉 script/style/form 等非正文节点，按 h1/h2/h3 切分结构（锚点是 `<!-- section:N -->`）。
- CSV 自动猜分隔符（逗号/分号/制表符），输出 Markdown 表格。
- EPUB 按 spine 顺序逐章输出（锚点是 `<!-- chapter:N -->`）。

---

## 6. 给 Agent 用时的要点

1. **别把原始 PDF 丢给内置 reader**。很多模型不支持 pdf 输入，直接传会失败；必须先转成文本/Markdown。
2. **先 read，再引用**。输出里的 `<!-- page N -->` 锚点就是引用坐标，回答时带上它。
3. **长文档先 `outline=true`**：几十行看清结构，再按 `--pages`/`pages` 取正文，别一上来就全文。
4. **只关心某个词就用 `grep`**：只返回命中处的片段，比全文省一个数量级的 token。
5. **看到 `truncated: true` 就续读**：把 `next_cursor` 传回去，直到没有 `next_cursor` 为止（一次对话里可以串好几轮）。
6. **一次要一批文件就传目录**：目录会合并成一份文档，锚点带文件名（`<!-- file:report.pdf page 3 -->`）。
7. **需要 OCR / 转写 / 抽帧时先装插件**。没装时工具会明确告诉你 `xdoc plugin add ocr` 之类命令，别自己猜。
8. **想要精确结构就用 `format=json`**，想要好读的文本就用 `markdown`。
9. **出错时工具返回 `isError=true`**，正文里写明原因（如「文件不存在: …」）；按提示改路径重试即可，别把错误当内容继续用。
10. 细节见 `skills/xdoc-read/SKILL.md`。

---

## 7. 故障排查

| 现象 | 原因 | 解决 |
| --- | --- | --- |
| `错误: 暂不支持的文件类型: xxx` | 类型不在支持矩阵（见 §9） | 换格式，或先转成 PDF/文本 |
| `错误: 目录里没有可读的文件: …` | 目录里全是认不出的格式 | 换目录；或先转成 PDF/文本 |
| `错误: 文件不存在: …` | 路径错 | 用绝对路径 |
| `错误: 无效的 cursor: …` | 游标被改写了 | 原样传回上一步的 `next_cursor`；不要自己拼 |
| `错误: 指定的范围 '999' 超出文档范围（文档共 64 节，可用 1-64）` | `--pages` 越界 | 改成范围内的页码 |
| `错误: 无法解析的页码 'abc'（示例: 1-5,8）` | `--pages` 写法不对 | 用 `1-5,8` 这种写法 |
| `错误: 未知插件: xxx（可用: …）` | 插件名拼错 | 用 `xdoc plugin list` 里的名字 |
| `错误: outline 与 search 不能同时用` | 同时要结构和内容 | 先 outline 定位，再按页/按词取正文 |
| `错误: 指定的页/节范围 … 在这个目录里的任何文件里都不匹配` | 目录里没有这么长的文件 | 放宽 `--pages`，或单独读某个文件 |
| 正文里出现「（图片内容需要 OCR 插件…）」 | 没装 `ocr` | `xdoc plugin add ocr` |
| 扫描 PDF 每页都是「没有文本层」 | 没装 `ocr` | 同上；装好后自动 OCR |
| 音频只有时长没有文字 | 没装 `asr` / `asr-zh` | 装插件；中文装 `asr-zh` |
| 视频只有元信息、没有帧 | 没装 `media` | `xdoc plugin add media` |
| `.doc` 读取报错 | 没装 LibreOffice | 装 LibreOffice（`doctor` 会检查） |
| Windows 终端中文显示异常 | 终端本身不支持 UTF-8 | 用 `-o out.md` 写文件；xdoc 内部已做编码兜底，不会崩 |
| 大 PDF 很慢 | 表格识别 + 图片提取占大头 | `--pages` 缩小范围、`--tables off`、`--no-images`；同一文件第二次读会命中缓存 |
| 中文 ASR 第一次特别慢 | 加载 1GB 模型（CPU） | 正常现象，之后同一进程很快 |
| `xdoc doctor` 报核心依赖 `[缺失]` | 安装损坏 | 重新 `uv tool install --force xdoc-tools`（包名是 `xdoc-tools`，命令仍是 `xdoc`） |
| 插件装完仍提示缺失 | 装到了别的目录 | `xdoc plugin list` 看状态；重装该插件 |

---

## 8. 性能参考（本机实测，中位数）

机器：AMD Ryzen 7 PRO 5875U（8c/16t，无独显，纯 CPU）。同一批真实样本，指标 = **词级保留率**（相对原始文本，1.0 = 一字不差）。

| 样本 | xdoc 词级保留率 | xdoc 耗时 | anymd 词级保留率 | anymd 耗时 |
| --- | --- | --- | --- | --- |
| `pdf/en_arxiv_attention.pdf`（15 页） | **1.0000** | 2.18s | 0.9836 | 2.56s |
| `pdf/zh_wiki_python.pdf`（64 页中文） | **1.0000** | 14.11s | 0.9012 | 2.8s |
| `pdf/zh_wiki_microsoft.pdf` | **1.0000** | — | 0.8768 | 3.43s |
| `pdf/en_paper_tracemonkey.pdf` | **1.0000** | — | 0.9607 | 2.56s |
| `xlsx/microsoft_sample.xlsx` | **1.0000** | 0.25s | 0.8552 | 1.71s |
| `html/zh_wikipedia.html` | 0.9927 | 0.84s | 0.9115 | — |
| `docx/calibre_demo.docx` | **1.0000** | 0.1s | 0.9816 | 1.8s |

要点：

- **中文 PDF 是分水岭**：xdoc 词级保留率 1.0，anymd 会掉字（8-gram 口径下 0.74 vs 0.96）。
- xdoc 的 PDF 慢在**表格识别与图片提取**；只要文字的话 `--tables off --no-images` 会快很多。
- 完整数据：`docs/ACCEPTANCE.md`、`docs/COMPARISON.md`。

---

## 9. 支持矩阵与已知限制

### 9.1 支持的文件类型

| 类型 | 扩展名 | 输出 |
| --- | --- | --- |
| PDF（文本型） | `.pdf` | 按页锚点 + 标题层级 + 有画线的表格 |
| PDF（扫描件） | `.pdf` | 同上，无文本层的页自动 OCR（需 `ocr` 插件） |
| Word | `.docx` / `.docm` / `.dotx` | 标题 / 列表 / 表格 / 超链接 / 内嵌图片 |
| Word（旧） | `.doc` | 需 LibreOffice；读出来的 `kind` 是 `docx` |
| PowerPoint | `.pptx` / `.pptm` / `.potx` / `.ppt` | 按幻灯片锚点 + 表格 + 备注（旧 `.ppt` 需 LibreOffice） |
| Excel | `.xlsx` / `.xlsm` / `.xltx` | 按工作表锚点 + Markdown 表格；`.xls` 需 LibreOffice |
| 表格 | `.csv` / `.tsv` | 自动猜分隔符 → Markdown 表格 |
| 网页 | `.html` / `.htm` / `.xhtml` | 去噪后按标题切段 |
| Markdown / 纯文本 | `.md` / `.markdown` / `.txt` / `.log` | 原样保留结构 |
| EPUB | `.epub` | 按章节顺序 |
| 图片 | `.jpg` / `.jpeg` / `.png` / `.webp` / `.gif` / `.bmp` / `.tif` / `.tiff` | OCR 文字 + 尺寸等元信息（需 `ocr` 插件） |
| 音频 | `.wav` / `.mp3` / `.m4a` / `.flac` / `.aac` / `.ogg` / `.opus` | 转写 + 时间戳（需 `asr` / `asr-zh` 插件） |
| 视频 | `.mp4` / `.mov` / `.mkv` / `.avi` / `.webm` / `.m4v` | 转写 + 关键帧 PNG（需 `media` + ASR 插件） |

> 识别**以内容为准**（magic bytes / zip 结构），扩展名只是线索：改错扩展名的文件照样读得对；任何 UTF-8 文本文件都能当纯文本读（详见 §3.9）。

### 9.2 已知限制

- **PDF 无框线表格不会还原成表格**（文字完整保留，词级保留率仍 1.0）。三条路都实测过并被否决：`strategy="text"` 会把整页切碎；`use_layout=True`（ONNX 版面模型）能找到但行列错位合并；廉价「列对齐」门控在双栏/维基页上几乎每页命中。
- **Excel 日期时间按 ISO 8601 输出**。
- **中文 ASR 首调 30–60s**（CPU 加载 1GB 模型）。
- **扫描 PDF 固定 200dpi 栅格化**，极小字号（<8pt）可能识别不全。
- **旧版 Office 依赖本机 LibreOffice**。
- **大 PDF 偏慢**（64 页中文维基首次解析约 14s；命中缓存后约 0.02s）。
- **暂不支持 URL**、暂不支持 `.xlsb` / `.odt` 等其它格式。

---

## 10. 复现与证据

```bash
uv run python tools/acceptance.py --runs 3   # 跑完整验收 → docs/acceptance_results.json
uv run python tools/report.py                # → docs/ACCEPTANCE.md
uv run python tools/comparison.py            # → docs/COMPARISON.md
uv run python tools/release_check.py         # 发布自检（隔离环境安装 + doctor 绿）
uv run --extra dev pytest                    # 单元测试
```

- 架构说明与图：[`docs/diagrams/xdoc-architecture.html`](diagrams/xdoc-architecture.html)
- 术语表：[`GLOSSARY.md`](../GLOSSARY.md)
- 决策记录：[`docs/adr/`](adr/)
- 计划与踩坑记录：[`PLAN.md`](PLAN.md)
- 发布说明：[`RELEASE.md`](RELEASE.md)
