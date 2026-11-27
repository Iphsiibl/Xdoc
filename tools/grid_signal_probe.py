"""实验：找一个"便宜且准"的表格页信号，用来决定要不要跑版面模型。

候选信号（每页独立计算）：
  - grid_cols(page)：把词按 y 聚行、按 x 起点聚列，某行有 >= MIN_COLS 列且
    该行各"格"（列起点之间的文本）的中位长度 <= MAX_CELL 字 → 该行像表格行；
  - grid_rows(page)：像表格行的行数 >= MIN_ROWS → 该页"像有表格"。

输出每个 PDF 每页的信号值，和 pages_with_signal 列表。
用法：uv run python tools/grid_signal_probe.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

MIN_COLS = 3
MIN_ROWS = 2
MAX_CELL = 60
TOL = 6.0


def _page_rows(page) -> list[list[tuple[float, float, str]]]:
    """返回每行 [(x0, x1, word)]。"""
    words = page.get_text("words")
    rows: list[list] = []
    buckets: list[dict] = []
    for w in sorted(words, key=lambda w: (round(w[1], 1), w[0])):
        placed = False
        for b in buckets:
            if abs(b["y"] - w[1]) <= 3.0:
                b["words"].append((w[0], w[2], w[4]))
                placed = True
                break
        if not placed:
            buckets.append({"y": w[1], "words": [(w[0], w[2], w[4])]})
    for b in buckets:
        rows.append(sorted(b["words"]))
    return rows


def _row_is_table_like(words: list[tuple[float, float, str]]) -> bool:
    if len(words) < MIN_COLS:
        return False
    # 聚列：列起点相差 <= TOL 视为同一列
    cols: list[list[tuple[float, float, str]]] = []
    for w in words:
        if cols and abs(cols[-1][0][0] - w[0]) <= TOL:
            cols[-1].append(w)
        else:
            cols.append([w])
    if len(cols) < MIN_COLS:
        return False
    # 每列的文本长度（列内词拼接）
    lengths = sorted(len(" ".join(x[2] for x in col)) for col in cols)
    median = lengths[len(lengths) // 2]
    return median <= MAX_CELL


def grid_rows(page) -> int:
    return sum(1 for row in _page_rows(page) if _row_is_table_like(row))


def main() -> int:
    root = Path(__file__).resolve().parent.parent / "samples" / "pdf"
    for path in sorted(root.glob("*.pdf")):
        doc = pymupdf.open(path)
        pages = [i + 1 for i, page in enumerate(doc) if grid_rows(page) >= MIN_ROWS]
        print(f"{path.name:32s} pages={doc.page_count:3d} signal_pages={pages}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
