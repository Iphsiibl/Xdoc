# xdoc

把 **PDF / 图片 / 音频 / 视频 / Office / 富文本** 忠实转换成文本，让 Agent 直接读取并提取信息。

- **一个入口**：MCP 工具 `read`（stdio）；同时提供同源 CLI `xdoc read`，两者结果一致。
- **一个出口**：Markdown / 纯文本 / JSON 三种格式可选。
- **只转换，不摘要**：金额、日期、编号原样保留；PDF 按页、PPT 按幻灯片、Excel 按工作表、音视频按时间戳给出锚点，便于精确引用。
- **运行期全离线**：不调用任何云服务；OCR / ASR / ffmpeg 均为本地可选插件。

## 三条命令跑通

```bash
uv tool install xdoc-tools
xdoc demo                  # 用内置示例跑一遍：看 xdoc 读出来长什么样（不用准备样本）
xdoc read 你的文件.pdf     # 读自己的文件
xdoc setup                 # 体检 + 打印接给 Agent 的方法（只读，不改你的任何文件）
```

`xdoc demo` 会用随包附带的示例（一个 Markdown + 一个 PDF）把「结构视图」「检索」都演一遍，
示例还会复制到临时目录，你可以直接改着玩。

## 架构

一份内核，两个入口，一个出口 → [架构图（HTML，浏览器直接打开）](docs/diagrams/xdoc-architecture.html)

- **入口**：MCP 工具 `read` 与同源 CLI `xdoc read` 都走 `api.read_document`。
- **内核**：`detect` 判类型 → `converters/*` 忠实解析 → 中间表示 `Document / Section / Block`。
- **出口**：`max_tokens` 预算切分 + `cursor` 续读，渲染成 Markdown / 纯文本 / JSON。
- **解析缓存**：按文件内容 sha256 + 解析选项命中缓存，重复读同一份文件几乎瞬时（实测 2.49s → 0.02s）；缓存键不含页码筛选，所以切页不用重新解析；插件按需进键，装了 ffmpeg 也不会让读过的 PDF、Word 全部失效；PDF 分「基础解析 + OCR 增强」两层存，装完 OCR 插件不用整份重解析（15s → 0.47s）。
- **目录并行**：一个目录里的多个文件用进程池同时解析（实测 7 个 PDF：19.1s → 13.8s）。
- **可选插件**：OCR / ASR / ffmpeg 跑在隔离 venv 里；图片与抽帧落到资产目录。

📖 **完整使用手册**（安装、参数表、输出契约、插件、按任务查、故障排查）→ [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md)
　术语表 → [`GLOSSARY.md`](GLOSSARY.md)　｜　决策记录 → [`docs/adr/`](docs/adr/)

## 安装

```bash
uv tool install xdoc-tools    # 推荐：装一次，之后直接用 xdoc
uvx xdoc-tools read file.pdf  # 不想安装、临时用一次
```

装完先自检：

```bash
xdoc doctor                   # 核心依赖齐全会打印「核心依赖齐全，基础能力可用。」
```

从源码安装（开发者，或想改代码时，在仓库根目录执行）：

```bash
uv tool install --force .
```

可选引擎插件（按需下载、随插随用、可随时卸载）：

```bash
xdoc plugin list              # 查看插件与状态（含实际占用）
xdoc plugin add ocr           # 本地 OCR（RapidOCR / PP-OCRv6，约 280MB）
xdoc plugin add asr           # 本地语音转写·通用（faster-whisper small，约 730MB）
xdoc plugin add asr-zh        # 本地语音转写·中文（FunASR Paraformer-zh，约 3.2GB）
xdoc plugin add media         # ffmpeg（视频抽帧、音频抽取，约 210MB）
xdoc plugin remove ocr        # 卸载（install/download、remove/uninstall 是同义词）
```

插件装上即生效（`ocr`/`asr` 默认 `auto`），卸载即回到纯解析能力。

## 使用

### MCP（推荐给 Agent）

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

Windows 上若客户端不解析 PATH，写绝对路径：`"command": ["C:\\Users\\<你>\\.local\\bin\\xdoc.exe", "serve"]`。

工具参数（每个参数在 schema 里都带说明和取值范围，Agent 能自己判断怎么传）：

| 参数 | 说明 |
| --- | --- |
| `path` | 文件路径，**也可以是目录**（目录里能读的文件会合并成一份） |
| `format` | `markdown`（默认）/ `text` / `json` |
| `max_tokens` | 本次返回的 token 上限，**默认 30000**；传 `0` 表示不限；超出即截断并返回 `next_cursor` |
| `cursor` | 续读游标，把上一步的 `next_cursor` 原样传回 |
| `pages` | 页/幻灯片/表范围，如 `1-5,8` |
| `outline` | 只要结构不要正文（标题 + 锚点），适合先摸清文档再定点读 |
| `grep` / `grep_regex` / `grep_context` / `grep_limit` | 只返回包含关键词的片段（默认字面匹配、忽略大小写） |
| `ocr` / `asr` / `asr_model` / `asr_language` / `asr_punc` / `tables` / `images` / `front_matter` | 感知与渲染开关，取值见下表与手册 |

推荐的省 token 四步法：**`read(path, outline=true)` 看结构 → `read(path, grep="关键词")` 只取命中处 → `read(path, pages="7-9")` 取正文 → `read(path, cursor=…)` 续读**。

仓库自带 Agent 技能 `skills/xdoc-read/SKILL.md`（复制到 `~/.agents/skills/xdoc-read/` 或 `~/.claude/skills/` 即可用），
告诉 Agent 什么时候该用这个工具、怎么按锚点引用原文；装上 MCP 与技能后，Agent 会自动选它。

### CLI

```bash
xdoc demo                                  # 用内置示例跑一遍（不用准备样本）
xdoc setup                                 # 体检 + 打印接给 Agent 的方法（只读）
xdoc read report.pdf                      # Markdown
xdoc read data.xlsx --format json         # 结构化 JSON
xdoc read book.pdf --outline              # 只要结构（标题+锚点），正文先不取
xdoc read book.pdf --max-tokens 8000      # 超长自动截断并给出 next_cursor
xdoc read book.pdf --cursor <next_cursor> # 续读
xdoc read slides.pptx --pages 1-5,8
xdoc read ./docs --outline                # 读整个目录：合并成一份，锚点带文件名
xdoc grep "Transformer" book.pdf          # 检索：只给命中位置与片段
xdoc grep "参考文献" ./docs --context 1    # 在整个目录里检索，带上下文行
xdoc read talk.mp3 --asr-language zh      # 语音转写指定语言（zh / en）
xdoc read talk.mp3 --asr-punc off         # 中文转写不要标点：快 30 秒，字照样准
xdoc read paper.pdf --tables on           # 强制逐页做表格识别（默认 auto：只认有竖线的页）
xdoc read paper.pdf --no-cache            # 跳过解析缓存，强制重新解析
xdoc cache info                           # 看缓存占用
xdoc cache clear                          # 清理解析缓存
xdoc doctor                               # 检查依赖与插件（含修复建议）
```

CLI 默认不限 token（保持既有习惯），需要预算时自己加 `--max-tokens`；MCP 侧默认给 30000 的预算，避免一次把十几万字塞进上下文。
解析与插件安装过程都有进度提示（写在 stderr，`-q` 可关），不会对着一个静默的终端等几分钟。

## 输出契约

```markdown
---
source: /abs/path/report.pdf
kind: pdf
sections: 12
pages: 12
chars: 48123
sha256: ...
---

<!-- page 1 -->
# 1. 引言

正文……

<!-- page 2 -->
| 项目 | 金额 |
| --- | --- |
| 合同 | 1,234.00 |
```

- PDF 页锚点 `<!-- page N -->`，PPT `<!-- slide N -->`，Excel `<!-- sheet: 名称 -->`，音视频 `<!-- t=00:00:12 -->`，HTML `<!-- section:N -->`，EPUB `<!-- chapter:N -->`。
- 读目录时锚点带文件名：`<!-- file:report.pdf page 3 -->`，front-matter 的 `files` 字段列出每个文件的类型与体量，`skipped` 字段说明哪些文件被跳过、为什么。
- `max_tokens` 截断时，开头的 front-matter 会带 `truncated: true` 与 `next_cursor`。
- `cursor` 坐标始终相对完整文档，可连续续读（表格按行续，文本按字符续）。
- front-matter 里的 `cache: hit|miss` 说明这次用的是解析缓存还是重新解析的。
- 检索时 front-matter 里的 `search:` 给出命中总数与本次返回条数。
- 正常读取时 front-matter 里还有 `toc:`——这份文档的目录（锚点 + 标题），**先扫一眼目录再决定读哪一段**。

## 离线与隐私

运行期不访问网络。所有感知能力（OCR / ASR / 抽帧）都在本地完成；安装插件时才会下载模型与依赖。

验收时把 `HTTP(S)_PROXY` 全部指向黑洞 `127.0.0.1:9`，PDF 解析、图片 OCR、中英文语音转写仍然成功
——说明运行期确实不依赖网络。详见 [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md)。

## 验收证据

| 验收项 | 门槛 | 结果 |
| --- | --- | --- |
| 文本保真（PDF 词级保留率） | ≥ 0.99 | 5/5 个 PDF 样本 = 1.0000 |
| 文本保真（与 anymd 同批对比） | xdoc ≥ anymd | 11 个样本全部持平或更优 |
| 结构可追溯（锚点数 == 页/张/表数） | 全等 | 通过 |
| OCR 字符 F1（中/英、图片/扫描件） | ≥ 0.95 | 通过 |
| 中文 ASR 字错率 | ≤ 0.05 | 0.0000 |
| 时间戳误差（对能量法独立测得的语音起止） | ≤ 1s | 通过 |
| 运行期离线（代理黑洞） | 全部成功 | 通过 |
| MCP 工具数 | = 1 | 1（`read`） |
| 长文续读不丢内容 | 覆盖率 ≥ 1.0 | 通过 |

复现：`uv run python tools/acceptance.py --runs 3` → `docs/acceptance_results.json`，
`uv run python tools/report.py` → `docs/ACCEPTANCE.md`。

## 发布证据（0.1.0 / 0.1.1 已发布到 PyPI；0.2.0 为本版，待发）

已发布：<https://pypi.org/project/xdoc-tools/>（包名 `xdoc-tools`，安装后命令仍是 `xdoc`）

| 版本 | 发布方式 | 复验 |
| --- | --- | --- |
| 0.1.0 | 本机 API token（`uv publish`） | 干净环境从 PyPI 安装 → `--version` → `doctor` 绿 → 真读 docx → `plugin list`，全 PASS |
| 0.1.1 | **CI 自动发布**：推 `v0.1.1` 标签 → `publish.yml` 用 PyPI Trusted Publisher（OIDC）上传，仓库里不存任何 token | 同上（干净环境从 PyPI 安装复验），详见 [`docs/RELEASE.md`](docs/RELEASE.md) |
| 0.2.0（本版） | 同上：推 `v0.2.0` 标签即自动发布 | 本机验收全过；保真指标与 0.1.1 持平 |

0.2.0 相对 0.1.1 的变化（输出契约有变：front-matter 多了 `toc:`）：

- `xdoc grep` 检索（CLI 与 MCP 共用），`read` 的 `grep*` 参数；
- 读目录时**并行解析**，front-matter 的 `files` 多了 `title`；
- 正常读取时 front-matter 多一张 `toc:` 目录（先看结构再读正文）；
- PDF 表格识别改成「只对有竖线的页做」，64 页 PDF 从 13.8s 降到 4.6s，输出逐字节相同；
- 缓存与插件解耦：装 OCR 插件不再让读过的 PDF 全部重解析（15s → 0.47s）；
- 中文转写并行 + 标点可选：13 秒的中文音频从 66s 降到 24.7s；
- `xdoc demo` / `xdoc setup` 打通首次上手；`xdoc doctor` 给出可执行的修复建议。

`uv run python tools/release_check.py` 可重跑；下面是 0.1.0 时的实际输出：

| 检查 | 结果 |
| --- | --- |
| 构建 sdist + wheel | PASS（wheel 31 个条目，sdist 173KB） |
| wheel 元数据 name/version/requires-python/license | PASS（xdoc-tools 0.1.0 / >=3.11 / MIT） |
| wheel 含 worker 与转换器代码 | PASS |
| 隔离环境安装（`HOME`/`UV_TOOL_DIR` 全指向临时目录 = 干净机器） | PASS |
| 安装后 `--version` | PASS（xdoc 0.1.0） |
| `xdoc doctor` 绿 | PASS（核心依赖齐全，基础能力可用） |
| 真读一个自造 docx | PASS |
| `xdoc plugin list` 可用 | PASS |
| README 安装命令 = `uv tool install xdoc-tools` | PASS |

证据文件：`docs/release_evidence.json`；发布后用 `uv run python tools/release_check.py --from-index`
从 PyPI 按包名再验一遍真实安装路径（已验：干净环境从 PyPI 安装 → `--version` → `doctor` 绿 → 真读 docx → `plugin list`，全 PASS）。
详见 [`docs/RELEASE.md`](docs/RELEASE.md)。

CI 侧也已独立跑通同一套自检：GitHub Actions 的 CI 工作流在 ubuntu-latest + windows-latest 上全绿，
Publish 工作流里的「跑测试」与「发布前自检（干净环境安装 + doctor 绿 + README 一致）」两步均通过。

## 已知限制

- **PDF 无框线表格不会被还原成表格**（正文文字仍完整保留，词级保留率 1.0）。
  实测过三条路都不划算：
  - `find_tables(strategy="text")` 会把整页切成碎片（`| v0 := ld sta | te[748] | ...`）；
  - `find_tables(use_layout=True)`（ONNX 版面模型）能找到论文里的无框线表格，
    但抽出来的行列会错位合并——arXiv「Attention Is All You Need」第 6 页那张
    复杂度对比表会变成 2 行、每列把 4 个值挤在一起，比纯文本更糟；
  - "列对齐"这种廉价门控在维基/双栏论文上几乎每页都命中，没有选择性。

  画线本身就是可靠的结构信息，所以只还原**有画线**的表格；无框线表格保留完整文字。
  将来若要更强的表格结构，可以把 MinerU / docling 做成同级插件（重依赖，按需装）。
- **Excel 日期时间按 ISO 8601 输出**（`2014-01-01T00:00:00`），避免地区格式歧义。
- **中文 ASR 首次调用需加载约 1GB 模型**（CPU），单次约 30–60s；之后同一进程内很快。
- **扫描 PDF 逐页以 200dpi 栅格化后 OCR**，极小字号（<8pt）可能识别不全。
- 旧版 `.doc/.ppt/.xls` 依赖本机 LibreOffice（`xdoc doctor` 会检查）。
- 大 PDF 偏慢：64 页中文维基首次解析约 14s（表格识别 + 图片提取占大头）；解析结果进缓存后，第二次读约 0.02s。

## 开发

```bash
uv sync
uv run xdoc doctor
uv run --extra dev pytest
```

## 样本

`samples/` 下有自动抓取的公开测试样本（`tools/fetch_samples.py`），覆盖中文/英文 PDF、扫描件、
DOCX/PPTX/XLSX、图片、音频、视频、HTML。
