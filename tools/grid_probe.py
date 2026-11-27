"""实验脚本：能否用"文字列对齐"廉价发现无框线表格页。

背景：
  - PDF 的 find_tables() 只认"框线"（lines_strict），无框线表格要靠版面模型或 text 策略，
    两者都慢（0.3~1s/页）或会把整页切碎。
  - 已在用的"画线门控"（h>=1|v>=1）召回 100%，但在 Wikipedia 这类每页都有分隔线的文档上
    误选率高（62/64 页），白白跑 find_tables。

问题：有没有比 find_tables 便宜、又能覆盖无框线表格的页级门控？

用法：uv run python tools/grid_probe.py [pdf...]
"""
from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples" / "pdf"

# 页面里确实有表格（find_tables 任一策略检出非空 rows）的页
TRUTH = {
    "zh_wiki_python.pdf": [2, 9, 13, 14, 19, 28],
    "en_paper_tracemonkey.pdf": [3, 8, 12],
    "zh_wiki_microsoft.pdf": [2, 4],
    "en_arxiv_attention.pdf": [6, 8, 9, 10, 13, 14, 15],
}


def column_score(words, tol: float = 12.0) -> tuple[int, int]:
    """返回 (列数, 至少含 3 列的行数)。

    做法：把所有词的 x 起点做一维聚类（容差 tol），得到"列"；
    再统计每行里命中列心的词数，>=3 的行算一行表格行。
    """
    if not words:
        return 0, 0
    rows: dict[int, list[float]] = {}
    for x0, y0, _x1, _y1, _w, *_ in words:
        rows.setdefault(int((y0) // 4), []).append(x0)
    starts = sorted(x for xs in rows.values() for x in xs)
    cols: list[float] = []
    for x in starts:
        if not cols or x - cols[-1] > tol:
            cols.append(x)
    if len(cols) < 3:
        return len(cols), 0
    table_rows = 0
    for xs in rows.values():
        hits = 0
        for x in xs:
            if any(abs(x - c) <= tol for c in cols):
                hits += 1
        if hits >= 3:
            table_rows += 1
    return len(cols), table_rows


def main() -> int:
    targets = sys.argv[1:] or sorted(SAMPLES.glob("*.pdf"))
    for name in targets:
        path = Path(name) if Path(name).is_absolute() else SAMPLES / name
        if not path.exists():
            print(f"!! {path} 不存在")
            continue
        truth = set(TRUTH.get(path.name, []))
        doc = pymupdf.open(str(path))
        sel: list[int] = []
        detail: list[str] = []
        for index, page in enumerate(doc, start=1):
            words = page.get_text("words")
            cols, trows = column_score(words)
            hit = trows >= 2 and cols >= 3
            if hit:
                sel.append(index)
            if index in truth or hit:
                detail.append(f"p{index}: cols={cols} trows={trows} truth={index in truth}")
        doc.close()
        tp = len(set(sel) & truth)
        fn = len(truth - set(sel))
        print(f"\n=== {path.name}  页数={len(sel)} 选中页={sel}")
        print(f"    truth={sorted(truth)}  tp={tp} fn={fn} fp={len(sel) - tp}")
        for line in detail:
            print("   ", line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
