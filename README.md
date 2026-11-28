# xdoc

把 **PDF / 图片 / 音频 / 视频 / Office / 富文本** 忠实转换成文本，让 Agent 直接读取并提取信息。

- **一个入口**：MCP 工具 `read`（stdio）；同时提供同源 CLI `xdoc read`，两者结果一致。
- **一个出口**：Markdown / 纯文本 / JSON 三种格式可选。
- **只转换，不摘要**：金额、日期、编号原样保留；PDF 按页、PPT 按幻灯片、Excel 按工作表、音视频按时间戳给出锚点，便于精确引用。
- **运行期全离线**：不调用任何云服务；OCR / ASR / ffmpeg 均为本地可选插件。

## 架构

一份内核，两个入口，一个出口 → [架构图（HTML，浏览器直接打开）](docs/diagrams/xdoc-architecture.html)

- **入口**：MCP 工具 `read` 与同源 CLI `xdoc read` 都走 `api.read_document`。
- **内核**：`detect` 判类型 → `converters/*` 忠实解析 → 中间表示 `Document / Section / Block`。
- **出口**：`max_tokens` 预算切分 + `cursor` 续读，渲染成 Markdown / 纯文本 / JSON。
- **可选插件**：OCR / ASR / ffmpeg 跑在隔离 venv 里；图片与抽帧落到资产目录。

📖 **完整使用手册**（安装、参数表、输出契约、插件、按任务查、故障排查）→ [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md)

## 安装

```bash
uv tool install xdoc          # 推荐：装一次，之后直接用 xdoc
uvx xdoc read file.pdf        # 不想安装、临时用一次
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
xdoc plugin list              # 查看插件与状态
xdoc plugin add ocr           # 本地 OCR（RapidOCR / PP-OCRv6，约 60MB）
xdoc plugin add asr           # 本地语音转写·通用（faster-whisper small，约 500MB）
xdoc plugin add asr-zh        # 本地语音转写·中文（FunASR Paraformer-zh，约 2GB）
xdoc plugin add media         # ffmpeg（视频抽帧、音频抽取，约 90MB）
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

工具参数：`path`、`format`（markdown/text/json）、`max_tokens`、`cursor`、`pages`（如 `1-5,8`）、
`ocr`、`asr`、`asr_model`、`images`、`front_matter`。

仓库自带 Agent 技能 `skills/xdoc-read/SKILL.md`（复制到 `~/.agents/skills/xdoc-read/` 或 `~/.claude/skills/` 即可用），
告诉 Agent 什么时候该用这个工具、怎么按锚点引用原文；装上 MCP 与技能后，Agent 会自动选它。

### CLI

```bash
xdoc read report.pdf                      # Markdown
xdoc read data.xlsx --format json         # 结构化 JSON
xdoc read book.pdf --max-tokens 8000      # 超长自动截断并给出 next_cursor
xdoc read book.pdf --cursor <next_cursor> # 续读
xdoc read slides.pptx --pages 1-5,8
xdoc read paper.pdf --tables on           # 强制逐页做表格识别（默认 auto：只认有画线的）
xdoc doctor                               # 检查依赖与插件
```

## 输出契约

```markdown
---
source: /abs/path/report.pdf
kind: pdf
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

- PDF 页锚点 `<!-- page N -->`，PPT `<!-- slide N -->`，Excel `<!-- sheet: 名称 -->`，音视频 `<!-- t=00:00:12 -->`。
- `max_tokens` 截断时，开头的 front-matter 会带 `truncated: true` 与 `next_cursor`。
- `cursor` 坐标始终相对完整文档，可连续续读（表格按行续，文本按字符续）。

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

## 发布证据（0.1.0，2026-11-27）

`uv run python tools/release_check.py` 可重跑；下面是它的实际输出：

| 检查 | 结果 |
| --- | --- |
| 构建 sdist + wheel | PASS（wheel 31 个条目，sdist 173KB） |
| wheel 元数据 name/version/requires-python/license | PASS（xdoc 0.1.0 / >=3.11 / MIT） |
| wheel 含 worker 与转换器代码 | PASS |
| 隔离环境安装（`HOME`/`UV_TOOL_DIR` 全指向临时目录 = 干净机器） | PASS |
| 安装后 `--version` | PASS（xdoc 0.1.0） |
| `xdoc doctor` 绿 | PASS（核心依赖齐全，基础能力可用） |
| 真读一个自造 docx | PASS |
| `xdoc plugin list` 可用 | PASS |
| README 安装命令 = `uv tool install xdoc` | PASS |

证据文件：`docs/release_evidence.json`；发布后用 `uv run python tools/release_check.py --from-index`
从 PyPI 按包名再验一遍真实安装路径。详见 [`docs/RELEASE.md`](docs/RELEASE.md)。

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
- 大 PDF 偏慢：64 页中文维基约 14s（表格识别 + 图片提取占大头）。

## 开发

```bash
uv sync
uv run xdoc doctor
uv run pytest
```

## 样本

`samples/` 下有自动抓取的公开测试样本（`tools/fetch_samples.py`），覆盖中文/英文 PDF、扫描件、
DOCX/PPTX/XLSX、图片、音频、视频、HTML。
