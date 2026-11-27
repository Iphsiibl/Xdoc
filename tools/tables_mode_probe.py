"""实验：比较 tables=auto 与 tables=layout 的端到端效果。

对每个 PDF：耗时、字符数、表格数/行数、词级保留率（对比 tools/compare.py 的参考抽取）。
用法：uv run python tools/tables_mode_probe.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from compare import REF, token_recall  # noqa: E402
from xdoc.api import read_with_meta  # noqa: E402
from xdoc.options import ReadOptions  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PDFS = [
    "pdf/en_arxiv_attention.pdf",
    "pdf/en_paper_tracemonkey.pdf",
    "pdf/zh_wiki_microsoft.pdf",
    "pdf/zh_wiki_python.pdf",
]


def main() -> int:
    for rel in PDFS:
        path = ROOT / "samples" / rel
        if not path.exists():
            continue
        reference = REF["pdf"](path)
        print(f"\n=== {rel} ===")
        for mode in ("auto", "layout"):
            started = time.perf_counter()
            text, doc = read_with_meta(path, ReadOptions(format="markdown", tables=mode))
            elapsed = time.perf_counter() - started
            tables = [b for s in doc.sections for b in s.blocks if b.kind == "table"]
            rows = sum(len(b.rows or []) for b in tables)
            print(f"  {mode:7s} {elapsed:6.2f}s chars={len(text):7d} tables={len(tables):3d} rows={rows:4d} "
                  f"token_recall={token_recall(reference, text):.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
