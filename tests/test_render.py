"""三种输出格式的渲染。"""

from __future__ import annotations

import json

from xdoc.errors import XdocError
from xdoc.ir import Block, Document, Section
from xdoc.render import render


def make_doc() -> Document:
    return Document(
        source="C:/tmp/demo.pdf",
        kind="pdf",
        sections=[
            Section(
                label="page 1",
                anchor="page:1",
                blocks=[
                    Block(kind="heading", text="标题一", level=1),
                    Block(kind="text", text="正文内容"),
                    Block(kind="table", header=True, rows=[["列 A", "列 B"], ["1", "2"]]),
                    Block(kind="image", text="示意图", src="C:/tmp/a.png"),
                    Block(kind="note", text="注意"),
                ],
            )
        ],
        meta={"pages": 1},
    )


def test_markdown_contains_anchor_and_all_blocks():
    out = render(make_doc(), "markdown")
    assert out.startswith("---")
    assert "<!-- page 1 -->" in out
    assert "# 标题一" in out
    assert "正文内容" in out
    assert "| 列 A | 列 B |" in out
    assert "| --- | --- |" in out
    assert "![示意图](C:/tmp/a.png)" in out
    assert "> [!NOTE] 注意" in out


def test_markdown_without_front_matter():
    out = render(make_doc(), "markdown", front_matter=False)
    assert not out.startswith("---")
    assert "<!-- page 1 -->" in out


def test_text_format_keeps_traceability():
    out = render(make_doc(), "text")
    assert "[page 1]" in out
    assert "列 A\t列 B" in out
    assert "[图片] 示意图" in out
    assert "#" not in out


def test_json_format_roundtrip():
    payload = json.loads(render(make_doc(), "json"))
    assert payload["kind"] == "pdf"
    assert payload["source"] == "C:/tmp/demo.pdf"
    assert payload["sections"][0]["anchor"] == "page:1"
    kinds = [b["kind"] for b in payload["sections"][0]["blocks"]]
    assert kinds == ["heading", "text", "table", "image", "note"]
    table = payload["sections"][0]["blocks"][2]
    assert table["rows"] == [["列 A", "列 B"], ["1", "2"]]
    assert table["header"] is True


def test_unknown_format_raises():
    try:
        render(make_doc(), "yaml")
    except XdocError as exc:
        assert "yaml" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("未知格式应当报错")
