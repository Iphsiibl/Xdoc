# xdoc —— 让 Agent 读懂任意文档的本地转换层

> 目标：一个工具，Agent 就能读 PDF / 图片 / 音频 / 视频 / 富文本 / Excel / PPT / DOCX，
> 运行期完全离线，输出**与原输入几乎完全一样**的文本，格式可选。

## 0. 为什么不是"再找一个现成工具"

调研结论（2026-11-27，GitHub API + npm 实测）：

| 方案 | 结论 |
|---|---|
| `microsoft/markitdown` | README 明写图片描述与语音转写依赖 web 服务 → 与"运行期离线"直接冲突 |
| `SylphxAI/anymd` | 最接近目标（Rust MCP+CLI、`read` 一个工具、page 锚点、token 预算）。但中文 OmniDocBench 默认仅 21.4 分，要拿到好 OCR 得另装 ~2GB doc-VLM；PDF 引用校验在 $29 的 Pro |
| `opendatalab/MinerU` | 中文/扫描件最强，但首跑 ~2GB 模型、依赖重，Windows 装起来不轻 |
| `docling` | 版面/表格强、导出格式全，但体量大 |
| `microsoft/markitdown-mcp` | 官方仓库 404（不存在），GongRzhe Word/PowerPoint MCP 已 archived |

→ 决策：**自建 xdoc（薄壳 + 可插拔引擎）**，用成熟引擎做感知层，自己只写统一契约、编排与质量门。
anymd 不进生产，只当**对照基线**（同一批样本跑同一套指标）。

## 1. 契约（唯一入口 / 唯一出口）

**入口**
- MCP：`read` —— 单个工具，参数化选择格式与引擎。（决策记录见 [`adr/0001`](adr/0001-mcp-single-tool-read.md)）
- CLI：`xdoc read <path> --format markdown`（非 MCP 场景同一实现）；检索另有 `xdoc grep` 子命令，共享同一读取入口。

**出口**（用户 m00048：内容与原输入几乎完全一样，格式可选）
- `format`：`markdown`（默认，保结构）/ `text`（纯文本）/ `json`（结构化，供程序消费）。
- 忠实原则：只转换，不摘要、不改写、不"美化"。金额、日期、编号、代码块原样保留。
- 可追溯锚点：`<!-- page N -->`（PDF）、`<!-- slide N -->`（PPT）、`<!-- sheet: 名称 -->`（Excel）、
  `<!-- t=00:00:12 -->`（音视频时间戳）、图片引用 `![](assets/xxx.png)`。
- 元数据 front-matter：`source / kind / pages / chars / engine / sha256 / truncated / next_cursor`。
- 预算与续读：`max_tokens` 超限即截断并给出 `cursor`，`cursor` 续读。

## 2. 分层与插件（用户 m00048：按需下载、随插随用、可卸载）

- **Tier 1 基础包（零重依赖，pip 装完就能用）**
  PDF / DOCX / PPTX / XLSX / CSV / HTML / Markdown / 纯文本 / 图片元数据
  引擎：pymupdf、python-docx、python-pptx、openpyxl、beautifulsoup4 + markdownify
- **Tier 2 插件（按需下载，CLI 装卸载）**
  - `ocr`：RapidOCR / PP-OCRv5（ONNX，中文，默认）｜ `--ocr vlm` 走 doc-VLM
  - `asr`：FunASR Paraformer-zh（中文默认）｜ faster-whisper（通用）｜ whisper.cpp（极简兜底）
  - `media`：ffmpeg（抽帧、抽音轨）
- 插件管理：`xdoc plugin list | add <name> | remove <name>`，目录 `~/.local/share/xdoc/plugins`，
  模型下载到插件目录，可整体卸载不留残渣。

## 3. 分期

- **P1 骨架**：项目结构、统一 `Document → Sections` 中间表示、markdown/text/json 三种渲染、
  单工具 MCP、CLI、`read` 跑通 Tier 1 全部格式。
- **P2 质量门**：对照样本做忠实度指标（文本型 PDF 提取完整率、DOCX/PPTX/XLSX 结构保真、
  数字/日期原样率），产出 `docs/ACCEPTANCE.md`。
- **P3 插件层**：OCR / ASR / media 插件与下载卸载。
- **P4 收敛**：与 anymd 同指标对比；`uv tool install xdoc-tools` 一条命令装；发 PyPI。

## 4. 验收标准（用户 m00048 的质量诉求，落成可测指标）

| 指标 | 阈值 | 状态 |
|---|---|---|
| 文本型 PDF 文本提取完整率 | ≥99% | 已校准：5/5 个 PDF 样本词级保留率 = 1.0000 |
| 扫描件 OCR 中文字符准确率 | ≥95% | 已校准：中/英 图片与扫描 PDF 四项 F1 = 1.0000 |
| ASR 中文字错率 / 时间戳误差 | ≤5% / ≤1s | 已校准：中文 CER = 0.0000，误差 0.07s / 0.14s |
| 关键字段（编号/金额/日期）召回 | ≥98% | 以词级保留率覆盖（1.0000） |
| DOCX/PPTX/XLSX 结构保真 | 标题层级/表格行列/单元格值零丢失 | 已校准：锚点数与页/张/表数全等 |
| 普通文档耗时 | <5s（CPU） | 已校准：DOCX/PPTX/XLSX/HTML 均 <1s；大 PDF 6–14s |
| 运行期离线 | 全程无网络调用 | 已校准：代理黑洞下 PDF/OCR/中英文 ASR 全部成功 |

样本来自 `tools/fetch_samples.py`（公开真实文件，含中英混排），来源与 sha256 记在
`samples/manifest.json`，任何结论都可复现。

验收脚本：`tools/acceptance.py`（7 组检查）→ `docs/acceptance_results.json`；
报告 `tools/report.py` → `docs/ACCEPTANCE.md`；对比 `tools/comparison.py` → `docs/COMPARISON.md`。

## 5. 本机约束（实测）

- Windows / AMD Ryzen 7 PRO 5875U 8c/16t / RAM 30.8GB / **无 NVIDIA GPU** → 全部 CPU 推理。
- Python 3.10/3.13 + uv 0.13.7（uv 托管 3.11–3.15）、Node 26、LibreOffice 26.8、pandoc 2.12 可用；
  **ffmpeg、OCR 引擎缺失**（需装）。
- 当前模型 MiniMax-M3.1-Flash **不支持 pdf 输入** → 工具绝不能把原始 PDF 交给模型，
  必须输出文本/Markdown（必要时附页面 PNG）。

## 6. 实现期踩出来的坑（已固化进代码与测试）

- **PDF 表格**：`page.find_tables()` 默认会跑 ONNX 版面模型（≈0.3s/页）→ 一律 `use_layout=False`。
  `strategy="text"` 能发现无框线表格，但会把整页切碎（实测输出 `| v0 := ld sta | te[748] | ...`）；
  `use_layout=True` 能定位论文里的无框线表格（tracemonkey 第 3/8/12 页、arxiv 第 6 页），
  但抽出来的行列会错位合并（arxiv 第 6 页的复杂度对比表变成 2 行、每列 4 个值挤在一起），
  比纯文本更糟 → 都不启用；只还原"有画线"的表格，画线本身就是可靠的结构信息。
  表格单元格里常有多行文字，必须压成一行，否则 Markdown 表格的列对不齐（`_cell_text`）。
- **表格与正文去重**：按"词的多重集"判断表格是否已表达某段正文（缺词比例 ≤5% 才丢原文块），
  再叠加 bbox 覆盖率 ≥0.75；宁可重复也不丢字。字符级比较会误判（arxiv 正文曾整段丢失）。
- **OCR 引擎**：旧 `rapidocr-onnxruntime`（PP-OCRv4）英文不输出空格（"Cleanhandswithsoap..."），
  换 `rapidocr` 3.x（PP-OCRv6）后中英文都正确且快 3–5 倍。
- **FunASR 时间戳**：`timestamp` 是 token 级且不含标点（字数比时间戳多 1），不能直接按字数对齐；
  需要 `_align_stamps`（标点不消耗时间戳、英文单词共用一个时间戳）。
- **FunASR 离线**：`AutoModel(model="paraformer-zh")` 传别名会在离线时去 modelscope hub 查仓库列表
  并重试 4 次 → 必须传本地快照路径（`_local_snapshot`）并 `device="cpu"`。
- **faster-whisper 与 PyAV**：`av>=19` 删了 `metadata_errors` 参数 → 插件依赖钉在 `av>=11,<19`。
- **MCP SDK 2.x**：`mcp.server.fastmcp.FastMCP` 已改名 `mcp.server.mcpserver.MCPServer`
  （1.x/2.x 双兼容写法）。
- **预算切表**：只切文本块会把大表格整块丢掉 → 表格按行切、表头重复、cursor 偏移对表格表示"已消费行数"。
- **测量纪律**：跑基准时不要并行其它重任务，否则 CPU 争用让耗时数字虚高（早前 37s 那批数据就是这么来的）。

## 7. 体验优化轮（2026-11-28，P0+P1）

目标不变：**让「人」和「Agent」用起来更容易**。用真实探针跑了一遍人和 Agent 会撞到的路径
（`tools/ux_probe.py` 走 CLI/API，`tools/mcp_probe.py` 用官方 MCP 客户端连 stdio 服务），
发现四类硬伤，逐条修掉：

| 问题（实测） | 修法 | 结果 |
|---|---|---|
| MCP schema 只有 title+type，没说明没枚举，Agent 只能猜参数含义 | 每个参数加 `description`，枚举值用 `Literal` 生成 `enum` | schema 里 12 个参数全部带说明与取值范围 |
| 业务错误被当成成功返回（`is_error=False`，正文写「[xdoc 错误] …」） | 业务错误改抛 SDK 的 `ToolError` | 客户端看到 `isError=true` + 完整原因（如「文件不存在: …」） |
| MCP 默认不限 token：一次 read 把 12.5 万字塞进 128k 上下文（占 98%） | MCP 默认 `max_tokens=30000`，`0` 表示不限；CLI 保持不限 | 单次调用体量可控 |
| 长文档只能全文硬读；坏 cursor 甩 Python traceback | 新增 `outline`（只给标题+锚点）、目录合并读取、解析缓存；`decode_cursor` 抛 `XdocError`，CLI 统一捕获后打印「错误: …」退出码 2 | outline 后 64 页文档 125702 → 5251 字符（4.2%）；重复读 2.49s → 0.02s |

约束照旧：MCP 仍然只暴露 **一个工具 `read`**，新增能力全部做成 `read` 的参数（`outline`、`path` 支持目录）；
CLI 与 MCP 共用 `api.read_document`，输出一致。

MCP SDK 的一个坑：工具异常到 `CallToolResult(is_error=True)` 的转换发生在**协议层**
（`mcp/server/mcpserver/server.py:437-456`），直接调 `server.call_tool()` 只会抛异常——
所以错误语义的测试必须走真实客户端（内存传输即可），否则测不到 Agent 真正看到的东西。

## 8. 减法轮（2026-11-28，清理不需要的文件与代码）

目标：把仓库里「没人要」的东西清掉，让人（读文档、改代码）和 Agent（读仓库、跑工具）
看到的都是有效信息。判定用 **deletion test**：删掉之后复杂度是消失了，还是只是搬到了别处。

### 删掉的文件

- `tools/` 下 6 个一次性探针（`grid_probe` / `grid_regions` / `grid_signal_probe` /
  `layout_probe` / `table_dump` / `tables_mode_probe`）：全仓只在各自 docstring 的「用法：」行出现，
  零引用；它们的结论早已固化进 `src/xdoc/converters/pdf.py` 顶部注释。
- `tools/compare.py` → 拆成 **`tools/ruler.py`**（只留「尺子」：参考文本抽取 + `recall` / `token_recall`）。
  它的 CLI 那半（`run_xdoc` / `run_anymd` / `main`，写 `compare/` 产物）与 `tools/acceptance.py`
  里的同名函数完全重复，而 `compare/` 产物无人读取 → 连目录一起删。
- 本地产物：`dist/`（过期 0.1.0 构建，pyproject 已是 0.1.1）、`compare/`、`__pycache__/`、`.pytest_cache/`。

### 删掉的死代码

| 位置 | 符号 | 原因 |
|---|---|---|
| `src/xdoc/detect.py` | `IMAGE_EXT` / `AUDIO_EXT` / `VIDEO_EXT`、`is_kind()` | 零引用 |
| `src/xdoc/assets.py` | `AssetStore.save_file()` / `copy_dir()` | 零引用（连带 `import shutil`） |
| `src/xdoc/cli.py` | `import json` + `plugin list --json` 分支 | parser 从未注册 `--json`，`main()` 还把它恒置 `False`，分支不可达 |
| `src/xdoc/api.py` | `import subprocess`、`_ocr_pdf_pages()` 的 `assets` 形参 | 未使用 |
| `src/xdoc/converters/` | `epub.py` 的 `import re`、`legacy.py` 的 `import os`、`docx.py` 重复的 `qn` 导入、`html.py` 的 `heading_re` | 未使用 |
| `tools/acceptance.py` | `WS` + 自己的 `norm()` | `norm` 零调用（对比用的是 `ruler.norm`） |

### 顺带修掉的真问题

- `.ogg` 之前映射到并不存在的 kind `opus`（`_handlers()` 里没有这个键），非标准 ogg 会报
  「暂不支持的文件类型: opus」→ 改为 `audio`。
- `PluginManager.run_worker()` 对没有 worker 的插件（如 `media`）会把 worker 路径算成目录本身，
  报错难懂 → 改为明确提示「插件 X 不是 worker 型插件」。
- `ReadOptions.extra`（一个没人写入的 `dict[str, Any]`）→ 换成有类型的 `asr_language: str | None`，
  媒体转换器直接把它传给 faster-whisper。
- `Block.lang` 之前永远是 `None`（没有任何转换器写它）→ Markdown 转换器现在会读出 ``` 后的语言标注
  （` ```python ` 不再退化成 ` ``` `），字段不再是空壳。

一个没动的地方：`api.read()` 只被测试和探针调用，CLI/MCP 走的都是 `read_with_meta`——
但它是文档里承诺的对外主入口，删了会破坏库使用者的导入路径，所以保留。

## 9. 检索轮（2026-11-28，Agent 侧的「找得到」）

目标：让人和 Agent 在**长文档里找东西**这件事上不再靠全文硬读。
两轮审计（Agent 侧走 MCP/技能路径，人侧走 CLI 真实命令）给出的结论一致：
问题不是「功能少」，而是**没反馈 + 静默失败 + 只能整篇读**。

### 修掉的三个真 bug（都是「静默」或「崩」）

| 问题（实测） | 修法 | 结果 |
|---|---|---|
| `xdoc --help` 在非中文 Windows 上直接崩：`UnicodeEncodeError: 'charmap' codec can't encode character '\u628a'` | `_setup_console()` 提到 `parse_args()` **之前**（`serve` 子命令除外，它走 stdio 不碰标准流） | exit 0，不再崩 |
| `--pages 999` 越界：exit 0、输出 front-matter 后什么都没有 | 页码解析统一走 `parse_page_spec()`，越界/格式错/顺序反了都抛 `XdocError` | exit 2 + 「指定的范围 '999' 超出文档范围（文档共 64 节，可用 1-64）」 |
| `xdoc plugin add 不存在的插件`：英文 argparse 报错 + 中文乱码 | 去掉 `choices=sorted(PLUGINS)`，让 `plugins.py` 里写好的中文提示可达 | exit 2 + 「未知插件: nosuch（可用: ocr, asr, asr-zh, media）」 |

### 检索（grep）

- `src/xdoc/search.py`：`find_matches()` 定位、`apply_search()` 把命中处拼成一份新文档。
  命中以节为单位聚合，锚点不变（`<!-- page 24 -->`），块上带 `meta.line`（该节第几行）与
  `meta.match`（命中原文）；front-matter 里的 `search:` 给出**命中总数**与本次返回条数。
- 行号语义：**块文本按顺序拼接、块间不补空行**，所以 Markdown 里就是第 N 个非空行
  （转换器本身就是一行一个块）。补空行反而会和真实文件行号错位。
- MCP 侧仍是**一个工具 `read`**，检索做成它的 4 个参数：`grep` / `grep_regex` / `grep_context` / `grep_limit`；
  CLI 侧新增 `xdoc grep` 子命令。两者共享 `api.read_document`，输出契约一致。
- `outline` 与 `search` 互斥：一个是看结构，一个是找内容，同时用会明确报错。
- 目录检索在**合并之后**做（否则每个文件先检索会把 meta 冲掉）；页码筛选仍按文件分别生效。

### 反馈（让人愿意等）

- 解析、OCR、ASR、抽帧、抽音轨、LibreOffice 转换、安装插件、下载 ffmpeg：全程有进度提示（stderr，`-q` 可关）。
- 插件体积改成**实测值**（ocr ≈280MB / asr ≈730MB / asr-zh ≈3.2GB / media ≈210MB），
  `plugin list` 与 `doctor` 额外显示**磁盘实际占用**。
- ffmpeg 插件装完只留 `ffmpeg.exe` + `ffprobe.exe`，删掉解压出来的整棵冗余树（省约 330MB）。
- `xdoc doctor` 从「体检报告」改成「修复指南」：缺什么给什么命令（含 `xdoc plugin add media`、
  `uv tool install --force xdoc-tools`），并检查 `xdoc` 命令本身在不在 PATH。

### 文档纠错（输出契约漂移）

审计出 4 条中危漂移（HTML 锚点是 `section:N` 不是 `doc:0`；JSON 里音视频 anchor 是 `time:00:00:00`；
视频关键帧是「总共最多 12 帧」不是「每 12 秒一帧」；OCR `avg_score` 只有图片 OCR 有），
加 15 条低危（`--pages` 对 Excel 是「第 N 个表格块」、EPUB 锚点 `chapter:N`、`asr_model` 默认 None、
识别看内容不看扩展名、front-matter 只对 markdown 生效等），全部同步到 README / USER_GUIDE / SKILL。

### 还没做

- `xdoc setup`（一键装依赖 + 配好 MCP）、`xdoc demo`（自带样例，不依赖 samples/）。
- `ReadOptions.asr_language` 有类型了但还没暴露到 CLI/MCP（属加法，单独一轮）。
