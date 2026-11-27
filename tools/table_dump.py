"""实验：对比 no-layout 与 layout 两种模式抽出的表格内容质量。

用法：uv run python tools/table_dump.py <pdf> <page_no> [no-layout|layout]
"""
from __future__ import annotations

import sys
from pathlib import Path

import pymupdf


def main() -> int:
    path = Path(sys.argv[1])
    pno = int(sys.argv[2])
    mode = sys.argv[3] if len(sys.argv) > 3 else "layout"
    kwargs = {"use_layout": mode == "layout"}
    doc = pymupdf.open(path)
    page = doc[pno - 1]
    found = page.find_tables(**kwargs)
    for table in getattr(found, "tables", []) or []:
        data = table.extract()
        rows = [[(c or "").strip() for c in row] for row in (data or [])]
        rows = [r for r in rows if any(r)]
        print(f"--- table bbox={tuple(round(v,1) for v in table.bbox)} rows={len(rows)} "
              f"cols={max((len(r) for r in rows), default=0)}")
        for row in rows[:15]:
            print("  | " + " | ".join(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
