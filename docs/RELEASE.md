# xdoc 发布记录（0.1.0 / 0.1.1）

日期：2026-11-28（发布日）
包名：`xdoc-tools`（PyPI，MIT）—— 命令仍是 `xdoc`
一句话：把 PDF / 图片 / 音频 / 视频 / Office / 富文本忠实转成文本，让 Agent 直接读；本地、离线、单 MCP 工具。

> **为什么叫 `xdoc-tools`**：PyPI 拒绝 `xdoc` 这个名字（`The name 'xdoc' isn't allowed`）——
> 它与已存在的 `xdocx` / `xdocs` 太相似，触发防抢注规则。`xdoc-tools`（PyPI 上显示为 XdocTools）
> 可用；**安装后的命令不变，仍是 `xdoc`**。

---

## 已发布记录（2026-11-28）

| 项 | 值 |
| --- | --- |
| 包名 | `xdoc-tools`（PyPI 上显示为 XdocTools） |
| 版本 | 0.1.0（本机 token 发布）、**0.1.1（CI 自动发布，见下节）** |
| 项目页 | <https://pypi.org/project/xdoc-tools/> |
| 安装 | `uv tool install xdoc-tools`（装完命令仍是 `xdoc`） |
| wheel | `xdoc_tools-0.1.0-py3-none-any.whl`（55039 B，sha256 `05e455d928188b9c3962a925c969feee873bd6d6d6a86e54cf471d0678b20525`） |
| sdist | `xdoc_tools-0.1.0.tar.gz`（197193 B，sha256 `9add9e884d8e4cebdea949b6e3f7f9dda564ab5678abeba1e66a13e5c7c510db`） |
| 发布方式 | 0.1.0 = 本机 API token（`uv publish`）；0.1.1 = **CI 用 Trusted Publisher（OIDC）自动发布**，仓库里不存任何 token |
| 发布后复验 | `uv run python tools/release_check.py --from-index` → 干净环境从 PyPI 安装、`--version`、`doctor` 绿、真读 docx、`plugin list`、README 命令一致，**全 PASS** |

## 0.1.1 —— CI 自动发布（PyPI Trusted Publisher / OIDC）

| 项 | 值 |
| --- | --- |
| 触发方式 | `git tag v0.1.1 && git push origin v0.1.1` → GitHub Actions `publish.yml` 自动跑完并上传 |
| workflow run | `46112053578`（event=push, ref=v0.1.1, conclusion=**success**） |
| wheel | `xdoc_tools-0.1.1-py3-none-any.whl`（54426 B，sha256 `63c6b8431a2f4b66839eb068245eada042dde5467a53773df0be8db71e7dbdc3`） |
| sdist | `xdoc_tools-0.1.1.tar.gz`（197656 B，sha256 `647d881cce470bf45a671a1b52a1cf249c96d7dc33fe304459683706fcdf4243`） |
| PyPI 侧配置 | 项目 `xdoc-tools` → Manage current publishers → GitHub / `Iphsiibl/Xdoc` / `publish.yml` / environment `pypi`（已激活） |
| 凭据 | 仓库里没有 token；上传用的是 GitHub OIDC token 换来的 PyPI 短期 token（`pypi.org/_/oidc/mint-token`） |
| 发布后复验 | `uv run python tools/release_check.py --from-index` → 6/6 PASS（干净环境装到 **0.1.1** → `--version` → `doctor` 绿 → 真读 docx → `plugin list` → README 命令一致） |

**以后发版只要三步**（不用碰 token）：

```bash
# 1) 改版本号：pyproject.toml 的 version + src/xdoc/__init__.py 的 __version__，然后 uv lock
# 2) 跑一遍自检
uv run --extra dev pytest
uv run python tools/release_check.py
# 3) 打标签推上去，CI 自己发
git commit -am "release: 0.1.2" && git push origin main
git tag v0.1.2 && git push origin v0.1.2
```


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
| 9 | README 安装命令 | PASS — README 主命令为 `uv tool install xdoc-tools`，与包名一致 |

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

### 3.1 CI 现状（已实测，非推测）

| 工作流 | 运行 | 结果 |
| --- | --- | --- |
| CI（ubuntu-latest + windows-latest） | CI #5，commit `260ae69` | **Success**（2 个 job 全绿，30s） |
| Publish | Publish #4，commit `260ae69` | 跑测试 ✅、发布前自检 ✅、**「发布到 PyPI」❌ exit code 2** |

Publish 唯一的失败点是最后一步的 OIDC 取 token：GitHub Actions 侧的日志结论是
`error: Failed to obtain token for trusted publishing / cause: No OIDC token discovered`
（`uv publish` 对这种错误返回 exit code 2）——说明 PyPI 侧还没登记 Trusted Publisher。
在此之前，`uv run pytest` 与 `uv run python tools/release_check.py` 在 CI 里都已通过，
即「干净机器可安装 + doctor 绿 + README 命令一致」这条 done 标准已由 CI 独立验证。

### 3.2 之后怎么发：CI 自动发布（已打通，仓库里不存任何 token）

**PyPI 侧的 Trusted Publisher 已激活**（2026-11-28 在
<https://pypi.org/manage/project/xdoc-tools/settings/publishing/> 添加，页面上 "Manage current publishers"
现在能看到这一条）：

| 字段 | 值 |
| --- | --- |
| Provider | GitHub |
| Owner | `Iphsiibl` |
| Repository name | `Xdoc` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

之后发版只有两步：

```bash
# 1. 改版本号：pyproject.toml 里 version = "0.1.1"（跟着 uv lock）
# 2. 打标签推上去
git tag v0.1.1 && git push origin v0.1.1
```

`.github/workflows/publish.yml` 收到 `v*` 标签后依次：跑测试 → 跑发布前自检 →
查这一版是否已在 PyPI（版本号从 `pyproject.toml` 取，不是 ref 名，所以手动触发也准）→
**换 OIDC token 自检** → `uv publish --trusted-publishing always`。

也可以手动触发：Actions → Publish → Run workflow，confirm 填 `xdoc-tools`。
此时若当前版本已在 PyPI，上传那步会自动跳过，只跑测试与自检。

#### 踩过的坑：为什么不能单独建一个「自检」工作流

最初的方案是另开一个 `trusted-publisher-check.yml` 只换 token 不上传，结果实测报：

```
HTTP 422 {"errors":[{"code":"invalid-publisher","description":"valid token, but no corresponding publisher (Publisher with matching claims was not found)"}],"message":"Token request failed"}
```

原因不是 publisher 没配好，而是 **OIDC token 的 claims 里带的是「发起这次请求的工作流文件名」**：
publisher 登记的是 `publish.yml`，自检工作流却是 `trusted-publisher-check.yml`，文件名对不上，
PyPI 匹配不到任何 publisher（报错里的 `valid token` 说明 GitHub 侧 claims 全对）。
结论：「换 token 自检」这一步必须待在 `publish.yml` 里面 —— 现已如此，那个独立自检工作流已删除。

#### 踩过的坑：残留的 pending publisher 会把整个发布链卡死

把 publisher 加到 `xdoc-tools` 项目下、并把工作流名对齐之后，换 token 还是报 422，但这次是**另一个错**：

```
HTTP 422 {"errors":[{"code":"invalid-payload","description":"The name 'XdocTools' is too similar to an existing project. ..."}],"message":"Token request failed"}
```

根因：账号里还留着一条**早先登记的 pending publisher**，项目名写的是 `XdocTools`
（规范化后是 `xdoctools`，和我们真正发布的 `xdoc-tools` **不是同一个项目名**）。
pending publisher 的语义是「项目不存在时替我创建它」，于是 PyPI 先匹配到它 → 试图创建项目
`XdocTools` → 撞上防抢注规则（`xdoc` 当初也是被这条规则拒的）→ 整个换 token 失败。

修法（1 分钟）：打开 <https://pypi.org/manage/account/publishing/>，
在 **Pending publishers** 里把那条 `XdocTools` 的 **Remove** 点掉。
删完后 "No pending publishers are currently configured."，
只留下 "Projects with active publishers → xdoc-tools" 这条，换 token 立刻就通。

> 教训：PyPI 的 pending publisher 与同名项目不是一回事 —— pending 是「按名字预登记」，
> 只有名字**规范化后完全相同**才会自动转成该项目的 publisher。

### 3.3 备用：本机用 API token 发布（万一 CI 坏了）

需要 PyPI API token（**用户侧凭据，助手不代管、不落盘**）：

```bash
# 方式 B1：当前 shell 里临时设置，token 不进命令历史以外的任何地方
$env:UV_PUBLISH_TOKEN = "pypi-xxxxxxxx"   # PowerShell
uv publish

# 方式 B2：交互式输入用户名与 token
uv publish --username <你的用户名>
```

token 申请：https://pypi.org/manage/account/token/ （scope 勾 `pypi` 上传）。

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
- 公开仓库地址已补进 `pyproject.toml` 的 `[project.urls]`（Repository/Issues = https://github.com/Iphsiibl/Xdoc）。
- CI 里踩过的坑（都已修并复跑通过）：`astral-sh/setup-uv` 没有 `v10` 主标签（要写精确版本 `v10.4.0`）；
  windows-latest 的默认 shell 是 pwsh，不支持 bash heredoc（冒烟测试已改成 `tools/smoke_cli.py`）；
  Windows 控制台代码页非 UTF-8 会让中文输出抛 `UnicodeEncodeError`（`cli.py` 里 `_setup_console()` 处理）。
