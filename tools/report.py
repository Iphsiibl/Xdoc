"""把 docs/acceptance_results.json 渲染成 docs/ACCEPTANCE.md（可复现的报告）。

用法：uv run python tools/report.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "acceptance_results.json"
OUT = ROOT / "docs" / "ACCEPTANCE.md"


def verdict(ok: bool | None) -> str:
    if ok is None:
        return "—（记录值，非门槛）"
    return "**PASS**" if ok else "**FAIL**"


def main() -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    lines: list[str] = []
    add = lines.append

    add("# xdoc 验收报告")
    add("")
    add("> 由 `tools/acceptance.py` 生成，`tools/report.py` 渲染；数字全部来自真实运行。")
    add("> 运行环境：Windows / AMD Ryzen 7 PRO 5875U (8c16t，无独显，全 CPU) / Python 3.14。")
    add(f"> 每个样本重复 {data.get('runs')} 次取中位数（同时记录离散度）。")
    add("")

    add("## 1. 文本保真（不丢信息）")
    add("")
    add("判据：词级保留率（token_recall）≥ 0.99。参考文本由 pymupdf/python-docx/python-pptx/")
    add("openpyxl/BeautifulSoup 独立抽取，与被测引擎无关。Excel 的日期时间两边统一按 ISO 8601")
    add("比较，避免把格式差异当成丢字。")
    add("")
    add("| 样本 | xdoc token_recall | xdoc shingle | anymd token_recall | xdoc 中位耗时 | anymd 耗时 |")
    add("| --- | --- | --- | --- | --- | --- |")
    for row in data.get("fidelity", []):
        if not row.get("ok"):
            add(f"| {row.get('sample')} | 失败: {row.get('error')} | | | | |")
            continue
        spread = row.get("spread")
        spread_txt = ""
        if spread:
            spread_txt = f"（{spread[0]:.2f}s 抖动）"
        add(f"| {row['sample']} | {row['token_recall']:.4f} | {row['shingle_recall']:.4f} | "
            f"{row.get('anymd_token_recall', '—')} | {row['median_s']:.2f}s{spread_txt} | "
            f"{row.get('anymd_s', '—')} |")
    add("")

    add("## 2. 结构可追溯")
    add("")
    add("判据：锚点数量 == 源文件的页/张/表数量。")
    add("")
    add("| 样本 | 类型 | 期望 | 实际 | 结论 |")
    add("| --- | --- | --- | --- | --- |")
    for row in data.get("traceability", []):
        add(f"| {row.get('sample')} | {row.get('kind')} | {row.get('expected')} | "
            f"{row.get('actual')} | {verdict(row.get('ok'))} |")
    add("")

    add("## 3. OCR")
    add("")
    add("判据：字符级 F1 ≥ 95%。指标用**无序多重集**比较（精确率/召回率/F1）：海报与扫描件")
    add("的阅读顺序本来就不确定，用编辑距离会把「顺序不同」误判成「识别错」。")
    add("候选文本只取文档里的 text 块（OCR 出来的字），不含 section 头、图片说明与资产路径。")
    add("")
    add("| 样本 | 精确率 | 召回率 | F1 | 门槛 | 结论 | 输出片段 |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for row in data.get("ocr", []):
        if not row.get("ok"):
            add(f"| {row.get('sample')} | 失败: {row.get('error')} | | | | | |")
            continue
        add(f"| {row['sample']} | {row.get('char_precision', 0):.4f} | {row.get('char_recall', 0):.4f} | "
            f"{row['char_accuracy']:.4f} | {row['threshold']:.0%} | "
            f"{verdict(row.get('passed'))} | {row.get('output', '')[:80].replace('|', '/')} |")
    add("")

    add("## 4. ASR")
    add("")
    add("判据：中文错字率（CER）≤ 5%；时间戳误差 ≤ 1s（时间戳真值用能量阈值独立测得，")
    add("不依赖 ASR 模型自己的输出）。")
    add("")
    add("| 样本 | CER/词错率 | 门槛 | ASR 起止 | 能量法测得起止 | 起点误差 | 终点误差 | 结论 |")
    add("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in data.get("asr", []):
        if not row.get("ok"):
            add(f"| {row.get('sample')} | 失败: {row.get('error')} | | | | | | |")
            continue
        thr = f"{row['threshold']:.0%}" if row.get("threshold") else "—"
        add(f"| {row['sample']} | {row['cer']:.4f} | {thr} | "
            f"{row.get('asr_start')}–{row.get('asr_end')}s | "
            f"{row.get('vad_start')}–{row.get('vad_end')}s | "
            f"{row.get('start_err_s')}s | {row.get('end_err_s')}s | "
            f"{verdict(row.get('passed') if row.get('threshold') else row.get('passed_ts'))} |")
    for row in data.get("asr", []):
        if row.get("ok") and row.get("transcript"):
            add("")
            add(f"- `{row['sample']}` 转写：{row['transcript']}")
    add("")

    add("## 5. 运行期离线")
    add("")
    add("判据：把 HTTP(S)/ALL_PROXY 全部指向黑洞 127.0.0.1:9，任何运行期联网都会失败或超时；")
    add("在这样的环境下仍能完成转换，即证明不依赖网络。")
    add("")
    add("| 样本 | 结果 | 耗时 | 输出字符 | 备注 |")
    add("| --- | --- | --- | --- | --- |")
    for row in data.get("offline", []):
        add(f"| {row.get('sample')} | {verdict(row.get('ok'))} | {row.get('seconds')}s | "
            f"{row.get('chars')} | {row.get('error', '')} |")
    add("")

    add("## 6. 输出格式可选")
    add("")
    for row in data.get("formats", []):
        add(f"- `{row['sample']}`：markdown={row['lengths'].get('markdown')} 字符，"
            f"text={row['lengths'].get('text')} 字符，json={row['lengths'].get('json')} 字符 → {verdict(row.get('ok'))}")
    add("")

    add("## 7. MCP 工具面")
    add("")
    for row in data.get("mcp", []):
        add(f"- 暴露的工具：{row.get('tools')}（数量 {row.get('count')}）→ {verdict(row.get('ok'))}")
        add("  用户明确要求「单个 MCP 工具」，工具数量必须为 1。")
    add("")

    add("## 8. 长文续读（max_tokens + cursor）")
    add("")
    for row in data.get("budget", []):
        add(f"- `{row['sample']}`：分 {row.get('chunks')} 段读完，累计 {row.get('total_chars')} 字符，"
            f"完整读取 {row.get('full_chars')} 字符，覆盖率 {row.get('coverage')} → {verdict(row.get('ok'))}")
    add("")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"报告写入 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
