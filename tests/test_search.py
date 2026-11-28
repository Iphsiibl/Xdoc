"""检索：命中定位、分组、上下文、限制、正则、跨文件。"""

from __future__ import annotations

from pathlib import Path

import pytest

from xdoc.api import read_document, read_with_meta
from xdoc.errors import XdocError
from xdoc.options import ReadOptions, SearchSpec


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _search(path: Path, **kwargs):
    options = ReadOptions(search=SearchSpec(**kwargs))
    return read_document(path, options)


def test_search_finds_line_and_keeps_anchor(tmp_path):
    path = _write(tmp_path, "a.md", "# 标题\n\nTransformer 很强大\n\n结束\n")
    doc = _search(path, pattern="transformer")
    assert doc.meta["search"]["total"] == 1
    assert len(doc.sections) == 1
    assert doc.sections[0].anchor == "doc:0"
    assert "Transformer 很强大" in doc.text
    # 行号 = 该节正文里的第几行（块按顺序拼接，空行不计入）
    assert doc.sections[0].blocks[0].meta["line"] == 2


def test_search_is_case_insensitive_by_default(tmp_path):
    path = _write(tmp_path, "a.md", "Transformer\n")
    assert _search(path, pattern="transformer").meta["search"]["total"] == 1
    strict = _search(path, pattern="transformer", ignore_case=False)
    assert strict.meta["search"]["total"] == 0


def test_search_regex_mode_and_invalid_regex(tmp_path):
    path = _write(tmp_path, "a.md", "alpha1\nbeta2\n")
    doc = _search(path, pattern=r"[a-z]+\d", regex=True)
    assert doc.meta["search"]["total"] == 2
    with pytest.raises(XdocError):
        _search(path, pattern="[unclosed", regex=True)


def test_search_limit_truncates_and_reports_total(tmp_path):
    path = _write(tmp_path, "a.md", "".join(f"hit {i}\n" for i in range(5)))
    doc = _search(path, pattern="hit", limit=2)
    assert doc.meta["search"]["total"] == 5
    assert doc.meta["search"]["returned"] == 2
    assert doc.meta["search"]["truncated"] is True


def test_search_context_adds_neighbouring_lines(tmp_path):
    path = _write(tmp_path, "a.md", "第一行\n第二行\n目标行\n第四行\n第五行\n")
    doc = _search(path, pattern="目标行", context=1)
    text = doc.sections[0].blocks[0].text
    assert "第二行" in text and "第四行" in text


def test_search_groups_hits_of_one_section(tmp_path):
    path = _write(tmp_path, "a.html", "<h1>甲</h1><p>关键词</p><p>又见关键词</p>")
    doc = _search(path, pattern="关键词")
    assert len(doc.sections) == 1
    assert len(doc.sections[0].blocks) == 2
    assert doc.sections[0].anchor == "section:0"


def test_search_across_directory_marks_source_file(tmp_path):
    _write(tmp_path, "a.md", "共享关键词在这里\n")
    _write(tmp_path, "b.md", "别处也有共享关键词\n")
    doc = _search(tmp_path, pattern="共享关键词")
    assert doc.kind == "collection"
    assert doc.meta["search"]["total"] == 2
    files = {section.file for section in doc.sections}
    assert files == {"a.md", "b.md"}


def test_search_conflicts_with_outline(tmp_path):
    path = _write(tmp_path, "a.md", "# 标题\n\n内容\n")
    options = ReadOptions(outline=True, search=SearchSpec(pattern="内容"))
    with pytest.raises(XdocError):
        read_document(path, options)


def test_search_conflicts_with_outline_for_a_directory(tmp_path):
    # 目录也要报同一个错，而不是悄悄合并两种结果
    _write(tmp_path, "a.md", "# 标题\n\n内容\n")
    options = ReadOptions(outline=True, search=SearchSpec(pattern="内容"))
    with pytest.raises(XdocError):
        read_document(tmp_path, options)


def test_search_reuses_cache_and_does_not_poison_it(tmp_path):
    path = _write(tmp_path, "a.md", "alpha\nbeta\n")
    cache_dir = tmp_path / "cache"
    import os

    os.environ["XDOC_CACHE_DIR"] = str(cache_dir)
    try:
        first = _search(path, pattern="alpha")
        assert first.meta["cache"] == "miss"
        second = _search(path, pattern="beta")
        assert second.meta["cache"] == "hit"      # 换个词不用重新解析
        assert second.meta["search"]["total"] == 1
        assert "beta" in second.text
    finally:
        os.environ.pop("XDOC_CACHE_DIR", None)


def test_search_without_match_says_so(tmp_path):
    path = _write(tmp_path, "a.md", "内容\n")
    text, doc = read_with_meta(path, ReadOptions(search=SearchSpec(pattern="根本没有")))
    assert doc.meta["search"]["total"] == 0
    assert "没有找到" in text


def test_search_empty_pattern_is_an_error(tmp_path):
    path = _write(tmp_path, "a.md", "内容\n")
    with pytest.raises(XdocError):
        _search(path, pattern="")
