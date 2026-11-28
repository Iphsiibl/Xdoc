"""读目录：把目录里能读的文件合成一份文档。"""

from __future__ import annotations

import pytest

from xdoc.api import read, read_document
from xdoc.errors import XdocError
from xdoc.options import ReadOptions


def _md(path, body: str):
    path.write_text(body, encoding="utf-8")
    return path


def test_directory_merges_files(tmp_path):
    _md(tmp_path / "a.md", "# 标题 A\n\n正文 A\n")
    _md(tmp_path / "b.md", "# 标题 B\n\n正文 B\n")
    doc = read_document(tmp_path, ReadOptions())
    assert doc.kind == "collection"
    assert doc.meta["file_count"] == 2
    assert {s.file for s in doc.sections} == {"a.md", "b.md"}


def test_directory_output_marks_source_file(tmp_path):
    _md(tmp_path / "a.md", "# 标题 A\n\n正文 A\n")
    out = read(tmp_path, ReadOptions())
    assert "<!-- file:a.md doc:0 -->" in out
    assert "file_count: 1" in out


def test_empty_directory_raises_xdoc_error(tmp_path):
    with pytest.raises(XdocError):
        read_document(tmp_path, ReadOptions())


def test_unreadable_file_is_skipped_not_fatal(tmp_path):
    _md(tmp_path / "a.md", "# 标题 A\n\n正文 A\n")
    # 非法 UTF-8 字节：既不是已知格式，也解不出文本，应该被跳过而不是整个失败
    (tmp_path / "binary.bin").write_bytes(b"\xff\xfe\x00\x81binary")
    doc = read_document(tmp_path, ReadOptions())
    assert doc.meta["file_count"] == 1
    assert doc.meta["skipped"]


def test_directory_json_has_file_field(tmp_path):
    import json

    _md(tmp_path / "a.md", "# 标题 A\n\n正文 A\n")
    payload = json.loads(read(tmp_path, ReadOptions(format="json")))
    assert payload["kind"] == "collection"
    assert payload["sections"][0]["file"] == "a.md"


def test_directory_outline_merges_structures(tmp_path):
    _md(tmp_path / "a.md", "# 标题 A\n\n正文 A\n")
    _md(tmp_path / "b.md", "# 标题 B\n\n正文 B\n")
    doc = read_document(tmp_path, ReadOptions(outline=True))
    texts = [b.text for s in doc.sections for b in s.blocks]
    assert "标题 A" in texts
    assert "标题 B" in texts
    assert "正文 A" not in texts
