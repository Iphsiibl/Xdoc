"""实验：use_layout=True（ONNX 版面模型）能否还原"无框线表格"。

对比每个 PDF：
  - lines_strict + use_layout=False（当前默认）
  - default（use_layout=True，走版面模型）
输出每页检出的表格数/行数与总耗时。
用法：uv run python tools/layout_probe.py
"""
from __future__ import annotations

import time
from pathlib import Path

import pymupdf

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "pdf"


def _probe(page, **kwargs) -> tuple[int, int]:
    try:
        found = page.find_tables(**kwargs)
    except Exception as exc:
        print(f"    failed: {exc}")
        return (0, 0)
    tables = list(getattr(found, "tables", []) or [])
    rows = 0
    for table in tables:
        try:
            data = table.extract()
        except Exception:
            continue
        rows += sum(1 for row in (data or []) if any((c or "").strip() for c in row))
    return (len(tables), rows)


def main() -> int:
    for path in sorted(SAMPLES.glob("*.pdf")):
        doc = pymupdf.open(path)
        if doc.page_count > 20:
            continue
        print(f"\n=== {path.name} ({doc.page_count} pages) ===")
        for label, kwargs in (("no-layout", {"use_layout": False}), ("layout", {"use_layout": True})):
            started = time.perf_counter()
            per_page = []
            for page in doc:
                per_page.append(_probe(page, **kwargs))
            elapsed = time.perf_counter() - started
            total_rows = sum(r for _t, r in per_page)
            pages_with = [i + 1 for i, (t, _r) in enumerate(per_page) if t]
            print(f"  {label:9s} tables={sum(t for t, _ in per_page)} rows={total_rows} "
                  f"time={elapsed:.2f}s pages_with_tables={pages_with}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
