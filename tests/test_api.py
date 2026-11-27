"""read() 端到端：格式切换、预算截断、续读、错误处理。"""

from __future__ import annotations

import json

import pytest
from conftest import require, sample

from xdoc.api import read, read_document, read_with_meta
from xdoc.errors import XdocError
from xdoc.options import ReadOptions, apply_budget


def test_read_markdown_has_front_matter():
    path = require(sample("docx", "calibre_demo.docx"))
    out = read(path, ReadOptions())
    assert out.startswith("---")
    assert "kind: docx" in out
    assert "source:" in out


def test_read_json_is_valid_json():
    path = require(sample("docx", "calibre_demo.docx"))
    payload = json.loads(read(path, ReadOptions(format="json")))
    assert payload["kind"] == "docx"
    assert payload["sections"]


def test_read_text_format():
    path = require(sample("docx", "calibre_demo.docx"))
    out = read(path, ReadOptions(format="text"))
    assert not out.startswith("---")
    assert "[" in out  # [page 1] 之类的可追溯标记


def test_missing_file_raises_xdoc_error():
    with pytest.raises(XdocError):
        read_document("C:/definitely/not/here.docx", ReadOptions())


def test_directory_raises_xdoc_error(tmp_path):
    with pytest.raises(XdocError):
        read_document(tmp_path, ReadOptions())


def _data_rows(doc) -> list[list[str]]:
    out: list[list[str]] = []
    for section in doc.sections:
        for block in section.blocks:
            if block.kind != "table":
                continue
            rows = block.rows
            if block.header:
                rows = rows[1:]
            out.extend([list(r) for r in rows])
    return out


def test_budget_continuation_never_loses_table_rows():
    """大表格被预算切开时，逐行续读必须一行不丢。"""
    path = require(sample("xlsx", "microsoft_sample.xlsx"))
    original = read_document(path, ReadOptions())
    expected = _data_rows(original)
    assert len(expected) > 100

    chunks = []
    cursor = None
    for _ in range(200):
        doc, cursor = apply_budget(original, 500, cursor)
        chunks.append(doc)
        if not cursor:
            break
    assert cursor is None

    got: list[list[str]] = []
    for chunk in chunks:
        got.extend(_data_rows(chunk))
    assert got == expected


def test_budget_truncation_reports_cursor():
    path = require(sample("xlsx", "microsoft_sample.xlsx"))
    first, first_doc = read_with_meta(path, ReadOptions(format="text", max_tokens=500))
    assert first_doc.meta.get("truncated") is True
    assert first_doc.meta.get("next_cursor")

    second, second_doc = read_with_meta(
        path, ReadOptions(format="text", max_tokens=500, cursor=first_doc.meta["next_cursor"])
    )
    assert second != first
    assert second_doc.meta.get("truncated") is True


def test_front_matter_can_be_disabled():
    path = require(sample("docx", "calibre_demo.docx"))
    out = read(path, ReadOptions(front_matter=False))
    assert not out.startswith("---")
