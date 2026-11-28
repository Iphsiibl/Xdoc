"""outline 模式：只给结构，不给正文。"""

from __future__ import annotations

from xdoc.api import read, read_document
from xdoc.options import ReadOptions


def _md(tmp_path, name: str, body: str):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_outline_keeps_headings_and_drops_body(tmp_path):
    path = _md(tmp_path, "a.md", "# 一级标题\n\n正文一\n\n## 二级标题\n\n正文二\n")
    doc = read_document(path, ReadOptions(outline=True))
    texts = [b.text for s in doc.sections for b in s.blocks]
    assert "一级标题" in texts
    assert "二级标题" in texts
    assert "正文一" not in texts
    assert "正文二" not in texts
    assert doc.meta["outline"] is True


def test_outline_without_heading_shows_first_line_hint(tmp_path):
    path = _md(tmp_path, "a.txt", "这是一段没有标题的正文，用来提示内容。\n第二行\n")
    doc = read_document(path, ReadOptions(outline=True))
    blocks = [b for s in doc.sections for b in s.blocks]
    assert len(blocks) == 1
    assert "没有标题的正文" in blocks[0].text
    assert blocks[0].meta.get("outline_hint") is True


def test_outline_keeps_anchors(tmp_path):
    path = _md(tmp_path, "a.md", "# 标题\n\n正文\n")
    out = read(path, ReadOptions(outline=True))
    assert "<!-- doc:0 -->" in out
    assert "outline: true" in out
    assert "正文" not in out


def test_outline_is_much_shorter_than_full_read(tmp_path):
    body = "# 标题\n\n" + ("很多字。" * 200)
    path = _md(tmp_path, "a.md", body)
    full = _body(read(path, ReadOptions()))
    thin = _body(read(path, ReadOptions(outline=True)))
    assert len(thin) < len(full) / 5


def _body(text: str) -> str:
    """去掉 front-matter，只比较正文。"""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2]
    return text
