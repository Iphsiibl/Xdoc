# xdoc 0.1.0 发布记录

日期：2026-11-27
包名：`xdoc`（PyPI，MIT）
一句话：把 PDF / 图片 / 音频 / 视频 / Office / 富文本忠实转成文本，让 Agent 直接读；本地、离线、单 MCP 工具。

---

## 1. 发布前自检（`tools/release_check.py`）

证据文件：`docs/release_evidence.json`（由脚本生成，可随时重跑）

| # | 检查 | 实测结果 |
| --- | --- | --- |
| 1 | 构建 sdist + wheel | PASS — `xdoc-0.1.0-py3-none-any.whl`（31 个条目）、`xdoc-0.1.0.tar.gz`（173KB） |
| 2 | wheel 元数据 | PASS — name=`xdoc`、version=`0.1.0`、requires-python=`>=3.11`、license=`MIT` |
| 3 | wheel 含全部代码 | PASS — 含 `xdoc/cli.py`、`xdoc/workers/ocr_worker.py`、`xdoc/workers/asr_worker.py`、`xdoc/converters/pdf.py` |
| 4 | 干净环境安装 | PASS — `HOME`/`USERPROFILE`/`UV_TOOL_DIR`/`UV_TOOL_BIN_DIR` 全部指向临时目录，可执行文件落在临时目录内（不借用本机已有安装） |
| 5 | `--version` | PASS — `xdoc 0.1.0` |
| 6 | `xdoc doctor` 绿 | PASS — 核心依赖段无 `[缺失]`，结尾「核心依赖齐全，基础能力可用。」，退出码 0 |
| 7 | 真读文件 | PASS — 自造 docx 被读出并命中正文标记 |
| 8 | `xdoc plugin list` | PASS — 干净机器上正确显示 4 个插件均未安装 |
| 9 | README 安装命令 | PASS — README 主命令为 `uv tool install xdoc`，与包名一致 |

复现：

```bash
uv run python tools/release_check.py            # 发布前：验本地构建产物
uv run python tools/release_check.py --from-index # 发布后：从 PyPI 按包名验真实安装
```

## 2. 功能验收（`tools/acceptance.py --runs 3`，3 次取中位数）

证据文件：`docs/acceptance_results.json` → `docs/ACCEPTANCE.md`、`docs/COMPARISON.md`

- 文本保真：5/5 个 PDF 样本**词级保留率 = 1.0000**（不丢字，只换格式）。
- 同批对比 anymd：11 个样本 xdoc **8 胜 3 平 0 负**；差距最大的是中文 PDF（xdoc 0.96 vs anymd 0.74）。
- 结构可追溯：10/10 通过（锚点数 == 页数/张数/表数）。
- OCR：4/4 样本（中文图、英文图、中文扫描 PDF、英文扫描 PDF）精确率/召回率/F1 = **1.0000**。
- ASR：中文字错率 **0.0000**；英文词错率 0.0435；时间戳误差 0.07–0.33s（门槛 ≤1s）。
- 运行期离线：把 `HTTP(S)_PROXY` 指向黑洞后，PDF 解析、图片 OCR、中英文语音转写 **4/4 仍成功**。
- 输出格式：markdown / text / json 三种都非空且内容一致。
- MCP 工具面：**只有 1 个工具 `read`**（符合「一个入口」）。
- 长文续读：xlsx 分 8 段读完，累计 84137 字符 vs 完整 82919（覆盖率 1.015，不丢内容）。

## 3. 上传

两条路，任选一条。

### A. CI 自动发布（推荐，无需在本机保存密钥）

仓库已带 `.github/workflows/publish.yml`：推送 `v*` 标签或手动触发 → 跑测试 → 跑发布前自检 →
`uv publish --trusted-publishing always`（PyPI OIDC，仓库里不存任何 token）。

一次性配置（在 https://pypi.org/manage/project/xdoc/settings/publishing/ 添加 Trusted Publisher）：

- Provider：`GitHub`
- Repository：`Iphsiibl/Xdoc`
- Workflow name：`publish.yml`
- Environment name：`pypi`

然后 `git tag v0.1.0 && git push origin v0.1.0` 即可。

### B. 本机用 API token 发布（一步到位）

需要 PyPI API token（**用户侧凭据，助手不代管、不落盘**）：

```bash
# 方式 B1：当前 shell 里临时设置，token 不进命令历史以外的任何地方
$env:UV_PUBLISH_TOKEN = "pypi-xxxxxxxx"   # PowerShell
uv publish

# 方式 B2：交互式输入用户名与 token
uv publish --username <你的用户名>
```

token 申请：https://pypi.org/manage/account/token/ （scope 勾 `pypi` 上传）。
若同名 `xdoc` 已被占用（当前未被占用），改版本号或换名。

上传后按 done 标准复验：

```bash
uv run python tools/release_check.py --from-index
```

## 4. 已知限制（诚实版）

- **PDF 无框线表格不会还原成表格**（正文文字仍完整保留，词级保留率 1.0）。实测三条路都不划算：
  `strategy="text"` 会把整页切碎；`use_layout=True`（ONNX 版面模型）能找到论文里的无框线表格，
  但行列错位合并（arXiv 论文第 6 页的复杂度对比表会挤成 2 行），比纯文本更糟；廉价「列对齐」门控在
  维基/双栏论文上几乎每页命中、没有选择性。因此只还原**有画线**的表格。
- Excel 日期时间按 ISO 8601 输出（`2014-01-01T00:00:00`），避免地区格式歧义。
- 中文 ASR 首次调用要加载约 1GB 模型（CPU），单次 30–60s。
- 扫描 PDF 按 200dpi 栅格化后 OCR，极小字号（<8pt）可能识别不全。
- 旧版 `.doc/.ppt/.xls` 依赖本机 LibreOffice（`xdoc doctor` 会检查）。
- 大 PDF 偏慢：64 页中文维基约 14s（表格识别 + 图片提取占大头）。

## 5. 后续可做

- 打包成一条命令注册到所有 MCP 客户端（吸收 anymd 的 `setup` 思路）。
- 把 MinerU / docling 做成同级插件，给愿意装 2GB 依赖的人更强的版面与表格还原。
- 公开仓库地址补进 `pyproject.toml` 的 `[project.urls]`（有仓库后一行即可）。
