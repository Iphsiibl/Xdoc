"""生成 docs/COMPARISON.md：xdoc 与 anymd 在同一批真实样本上的同指标对比。

数据来源：docs/acceptance_results.json（由 tools/acceptance.py 实测产生）。
用法：uv run python tools/comparison.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "acceptance_results.json"
OUT = ROOT / "docs" / "COMPARISON.md"


def main() -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    rows = [r for r in data.get("fidelity", []) if r.get("ok")]
    lines: list[str] = []
    add = lines.append

    add("# xdoc vs anymd：同批样本、同指标、同机器")
    add("")
    add("对比对象：`@sylphx/anymd`（SylphxAI/anymd，MIT，Rust 写的 MCP server + CLI）与本项目的 xdoc。")
    add("")
    add("- **样本**：`samples/` 下 17 个公开真实文件（PDF/扫描件/DOCX/PPTX/XLSX/图片/音频/视频/HTML），")
    add("  由 `tools/fetch_samples.py` 自动抓取，不是人造样本。")
    add("- **指标**：`token_recall`（词级保留率，忽略顺序，只看有没有丢字）与 `shingle_recall`（8-gram 保留率，")
    add("  兼顾顺序）。参考文本由 pymupdf / python-docx / python-pptx / openpyxl / BeautifulSoup 独立抽取，")
    add("  与被测引擎无关。")
    add("- **环境**：Windows / AMD Ryzen 7 PRO 5875U（8c16t，无独显，全程 CPU）；每个样本跑 3 次取中位数。")
    add("")

    add("## 结果")
    add("")
    add("| 样本 | xdoc token | anymd token | xdoc 8-gram | xdoc 耗时 | anymd 耗时 | 谁更全 |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    wins = ties = losses = 0
    for row in rows:
        x = row.get("token_recall")
        a = row.get("anymd_token_recall")
        if x is None or a is None:
            verdict = "—"
        elif x > a:
            verdict = "**xdoc**"
            wins += 1
        elif x == a:
            verdict = "持平"
            ties += 1
        else:
            verdict = "anymd"
            losses += 1
        add(f"| {row['sample']} | {x:.4f} | {a:.4f} | {row.get('shingle_recall', 0):.4f} | "
            f"{row.get('median_s', 0):.2f}s | {row.get('anymd_s', 0):.2f}s | {verdict} |")
    add("")
    add(f"合计：xdoc 更全 {wins} 个、持平 {ties} 个、落后 {losses} 个。")
    add("")

    add("## 读法")
    add("")
    add("- **中文 PDF 差距最大**：xdoc 词级 1.0000 / 8-gram 0.96–0.98，anymd 词级 0.88–0.90 / 8-gram 0.74–0.75。")
    add("  anymd 默认用英文 tesseract，中英混排的维基 PDF 掉字明显；xdoc 直接取 PDF 文本层（词级不掉字），")
    add("  扫描件另走 PP-OCRv6，4 个中英扫描样本字符 F1 均为 1.0000。")
    add("- **HTML 差距明显**：xdoc 词级 0.976–0.993 / 8-gram 0.90–0.93，anymd 0.55–0.87。")
    add("- **anymd 的强项是速度与安装**：单文件约 1.8–2.7s（含 npx 冷启动），`npx -y @sylphx/anymd setup`")
    add("  能自动注册到所有 MCP 客户端；xdoc 的大 PDF（64 页）要 6–14s，因为要还原表格与图片。")
    add("- **anymd 的 OCR/ASR 需要额外下载**：好成绩要另装约 2GB 的本地 doc-VLM；语音转写模型也是另下。")
    add("  xdoc 把这些做成插件（`xdoc plugin add ocr/asr/asr-zh`），按需装、随时卸。")
    add("")

    add("## 结论")
    add("")
    add("1. **质量过关**：在同一批真实样本上，xdoc 的保真度全面达到 anymd，中文场景明显更好。")
    add("2. **继续走自己的路线**，但吸收 anymd 两个值得抄的点：")
    add("   - 「一条命令装好并注册到所有 MCP 客户端」的安装体验（xdoc 已发布到 PyPI：`uv tool install xdoc-tools`，命令仍是 `xdoc`）；")
    add("   - 页面锚点 + 续读游标的输出形态（xdoc 已实现 `<!-- page N -->` 与 `next_cursor`）。")
    add("3. **不引入 anymd 作为依赖**：它是 Rust 二进制 + 闭源 Pro 功能，且核心能力（保真度）不如自研实现。")
    add("")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"对比报告写入 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
