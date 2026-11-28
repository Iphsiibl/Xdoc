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
- MCP：`read` —— 单个工具，参数化选择格式与引擎。
- CLI：`xdoc read <path> --format markdown`（非 MCP 场景同一实现）。

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
  数字/日期原样率），产出 `docs/BASELINE.md`。
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
