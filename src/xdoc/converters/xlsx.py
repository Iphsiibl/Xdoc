"""XLSX 转换：逐工作表，空行切分成多张表，单元格值原样保留（含日期/数字格式）。"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from ..assets import AssetStore
from ..errors import XdocError
from ..ir import Block, Document, Section
from ..options import ReadOptions


def _fmt(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()
    if isinstance(value, float):
        if value == int(value) and abs(value) < 1e15:
            return str(int(value))
        return repr(value)
    return str(value)


def _col_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def convert(path: Path, options: ReadOptions, assets: AssetStore) -> Document:
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover
        raise XdocError("缺少 openpyxl") from exc

    try:
        wb = openpyxl.load_workbook(str(path), data_only=False, read_only=False)
    except Exception as exc:
        raise XdocError(f"无法打开 XLSX: {exc}") from exc

    try:
        wb_values = openpyxl.load_workbook(str(path), data_only=True, read_only=False)
    except Exception:
        wb_values = None

    sections: list[Section] = []
    total_cells = 0

    for ws in wb.worksheets:
        value_ws = wb_values[ws.title] if wb_values is not None else None
        rows_data: list[list[str]] = []
        row_numbers: list[int] = []
        for r_idx, row in enumerate(ws.iter_rows(values_only=False), start=1):
            values: list[str] = []
            non_empty = False
            for cell in row:
                raw = cell.value
                if isinstance(raw, str) and raw.startswith("=") and value_ws is not None:
                    cached = value_ws.cell(row=cell.row, column=cell.column).value
                    if cached is not None:
                        raw = cached
                text = _fmt(raw)
                if text:
                    non_empty = True
                values.append(text)
            if non_empty:
                rows_data.append(values)
                row_numbers.append(r_idx)
            else:
                if rows_data:
                    sections.append(_section_for(ws.title, rows_data, row_numbers))
                    total_cells += sum(len(r) for r in rows_data)
                    rows_data, row_numbers = [], []
        if rows_data:
            sections.append(_section_for(ws.title, rows_data, row_numbers))
            total_cells += sum(len(r) for r in rows_data)

    meta = {
        "engine": "openpyxl",
        "sheets": len(wb.sheetnames),
        "cells": total_cells,
    }
    wb.close()
    if wb_values is not None:
        wb_values.close()
    return Document(source=str(path), kind="xlsx", sections=sections, meta=meta)


def _section_for(title: str, rows: list[list[str]], row_numbers: list[int]) -> Section:
    start_row = row_numbers[0]
    end_row = row_numbers[-1]
    width = max((len(r) for r in rows), default=1)
    section = Section(
        label=f"{title} (行 {start_row}-{end_row})",
        anchor=f"sheet:{title}",
    )
    section.add(Block(kind="table", rows=rows, header=True,
                      meta={"range": f"A{start_row}:{_col_letter(width - 1)}{end_row}"}))
    return section
