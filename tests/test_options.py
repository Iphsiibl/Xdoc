"""token 估算、cursor 编解码、预算截断与续读。"""

from __future__ import annotations

import pytest

from xdoc.ir import Block, Document, Section
from xdoc.options import (
    ReadOptions,
    apply_budget,
    decode_cursor,
    encode_cursor,
    estimate_tokens,
)


def make_doc() -> Document:
    return Document(
        source="mem",
        kind="text",
        sections=[
            Section(
                label="page 1",
                anchor="page:1",
                blocks=[
                    Block(kind="text", text="x" * 100),
                    Block(kind="text", text="y" * 100),
                    Block(kind="text", text="z" * 100),
                ],
            )
        ],
    )


def test_estimate_tokens_cjk_and_ascii():
    assert estimate_tokens("中文测试") == 4
    assert estimate_tokens("a" * 36) == 10
    assert estimate_tokens("") == 0


def test_cursor_roundtrip():
    cursor = encode_cursor(2, 5, 17)
    assert decode_cursor(cursor) == (2, 5, 17)


def test_cursor_rejects_garbage():
    with pytest.raises(ValueError):
        decode_cursor("not-a-cursor!!")


def test_apply_budget_without_limit_keeps_everything():
    doc, cursor = apply_budget(make_doc(), None, None)
    assert cursor is None
    assert sum(len(b.text) for b in doc.sections[0].blocks) == 300


def test_apply_budget_truncates_and_reports_cursor():
    doc, cursor = apply_budget(make_doc(), 10, None)
    assert cursor is not None
    assert doc.meta["truncated"] is True
    assert doc.meta["next_cursor"] == cursor
    assert len(doc.sections[0].blocks) == 1
    assert 0 < len(doc.sections[0].blocks[0].text) < 100


def test_continuation_covers_the_whole_document_without_gap():
    doc = make_doc()
    first, cursor = apply_budget(doc, 10, None)
    assert cursor is not None
    second, cursor2 = apply_budget(doc, None, cursor)
    assert cursor2 is None

    joined = "".join(b.text for b in first.sections[0].blocks) + "".join(
        b.text for b in second.sections[0].blocks
    )
    assert joined == "x" * 100 + "y" * 100 + "z" * 100


def test_read_options_defaults():
    options = ReadOptions()
    assert options.format == "markdown"
    assert options.ocr == "auto"
    assert options.tables == "auto"
    assert options.asr == "auto"
    assert options.images == "refs"
    assert options.front_matter is True
