"""实验：无框线表格的列对齐区域检测 + 裁剪后用 text 策略抽表。

用途：验证能否在 PDF 里还原"没有画线"的表格（研究论文里很常见）。
步骤：
 1. 取页面 words，按 y 聚成行；
 2. 每行把词按 x 起点聚成列（容差 tol），行内列数 >= min_cols 且列 x 位置稳定 → 该行可能属于表格；
 3. 连续多行（>= min_rows）组成一个候选区域 region；
 4. 用 page.find_tables(strategy="text", use_layout=False, clip=region) 在该区域上抽表；
 5. 打印表格内容，人工/程序判断是否还原正确。

用法：uv run python tools/grid_regions.py <pdf> [page_no ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

TOL = 6.0
MIN_COLS = 3
MIN_ROWS = 2


def _rows(page) -> list[dict]:
    words = page.get_text("words")  # x0,y0,x1,y1,word,block,line,word_no
    rows: list[dict] = []
    for w in sorted(words, key=lambda w: (round(w[1], 1), w[0])):
        placed = False
        for row in rows:
            if abs(row["y"] - w[1]) <= 3.0:
                row["words"].append(w)
                row["y"] = (row["y"] * (len(row["words"]) - 1) + w[1]) / len(row["words"])
                placed = True
                break
        if not placed:
            rows.append({"y": w[1], "words": [w]})
    return rows


def _columns(row: dict) -> list[list]:
    cols: list[list] = []
    for w in sorted(row["words"], key=lambda w: w[0]):
        if cols and abs(cols[-1][0][0] - w[0]) <= TOL:
            cols[-1].append(w)
        else:
            cols.append([w])
    return cols


def _regions(page) -> list[tuple[float, float, float, float]]:
    """返回候选表格区域 (x0, y0, x1, y1)。"""
    regions: list[tuple[float, float, float, float]] = []
    current: list[dict] = []
    for row in _rows(page):
        cols = _columns(row)
        if len(cols) >= MIN_COLS:
            current.append(row)
            continue
        if len(current) >= MIN_ROWS:
            regions.append(_bbox(current))
        current = []
    if len(current) >= MIN_ROWS:
        regions.append(_bbox(current))
    return regions


def _bbox(rows: list[dict]) -> tuple[float, float, float, float]:
    xs0 = [w[0] for r in rows for w in r["words"]]
    ys0 = [w[1] for r in rows for w in r["words"]]
    xs1 = [w[2] for r in rows for w in r["words"]]
    ys1 = [w[3] for r in rows for w in r["words"]]
    return (min(xs0), min(ys0), max(xs1), max(ys1))


def main() -> int:
    path = Path(sys.argv[1])
    pages = [int(p) for p in sys.argv[2:]] or list(range(1, pymupdf.open(path).page_count + 1))
    doc = pymupdf.open(path)
    for pno in pages:
        page = doc[pno - 1]
        regions = _regions(page)
        if not regions:
            continue
        print(f"\n=== page {pno}: {len(regions)} candidate region(s) ===")
        for region in regions:
            print(f"  region={tuple(round(v, 1) for v in region)}")
            try:
                found = page.find_tables(strategy="text", use_layout=False, clip=pymupdf.Rect(region))
            except Exception as exc:
                print(f"    find_tables failed: {exc}")
                continue
            for table in getattr(found, "tables", []) or []:
                data = table.extract()
                rows = [[(c or "").strip() for c in row] for row in (data or [])]
                rows = [r for r in rows if any(r)]
                print(f"    -> {len(rows)} rows")
                for row in rows[:12]:
                    print("       | " + " | ".join(row[:8]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
