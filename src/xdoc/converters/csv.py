"""CSV / TSV 转换。"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from ..assets import AssetStore
from ..ir import Block, Document, Section
from ..options import ReadOptions
from .text import decode_text


def convert(path: Path, options: ReadOptions, assets: AssetStore) -> Document:
    text = decode_text(path)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel_tab if path.suffix.lower() == ".tsv" else csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [[cell.strip() for cell in row] for row in reader]
    rows = [r for r in rows if any(c for c in r)]

    section = Section(label=path.name, anchor="doc:0")
    if rows:
        section.add(Block(kind="table", rows=rows, header=True))
    meta = {"engine": "builtin-csv", "rows": len(rows),
            "delimiter": dialect.delimiter}
    return Document(source=str(path), kind="csv", sections=[section], meta=meta)
