"""解析缓存：内容不变就不重复解析。"""

from __future__ import annotations

import pytest

from xdoc.api import read_document
from xdoc.cache import cache_key, cache_root, clear, usage
from xdoc.options import ReadOptions


@pytest.fixture()
def isolated_cache(tmp_path, monkeypatch):
    """把缓存挪到临时目录，别碰用户机器上的真实缓存。"""
    root = tmp_path / "cache"
    monkeypatch.setenv("XDOC_CACHE_DIR", str(root))
    return root


def _md(tmp_path, name: str, body: str):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_second_read_hits_cache(tmp_path, isolated_cache):
    path = _md(tmp_path, "a.md", "# 标题\n\n正文\n")
    first = read_document(path, ReadOptions())
    second = read_document(path, ReadOptions())
    assert first.meta["cache"] == "miss"
    assert second.meta["cache"] == "hit"
    assert second.text == first.text


def test_cached_document_matches_fresh_document(tmp_path, isolated_cache):
    path = _md(tmp_path, "a.md", "# 标题\n\n正文\n\n- 列表\n")
    fresh = read_document(path, ReadOptions(use_cache=False))
    read_document(path, ReadOptions())  # 写缓存
    cached = read_document(path, ReadOptions())
    assert cached.sections[0].blocks[0].kind == fresh.sections[0].blocks[0].kind
    assert cached.text == fresh.text


def test_no_cache_option_forces_reparse(tmp_path, isolated_cache):
    path = _md(tmp_path, "a.md", "# 标题\n\n正文\n")
    read_document(path, ReadOptions())
    again = read_document(path, ReadOptions(use_cache=False))
    assert again.meta["cache"] == "miss"


def test_changed_file_gets_a_new_entry(tmp_path, isolated_cache):
    path = _md(tmp_path, "a.md", "# 标题\n\n正文\n")
    read_document(path, ReadOptions())
    path.write_text("# 标题\n\n换了内容\n", encoding="utf-8")
    doc = read_document(path, ReadOptions())
    assert doc.meta["cache"] == "miss"
    assert "换了内容" in doc.text


def test_cache_key_depends_on_options_and_plugins(tmp_path):
    base = ReadOptions()
    other = ReadOptions(tables="off")
    kwargs = dict(sha256="abc", kind="pdf")
    assert cache_key(**kwargs, options=base, plugins=[]) != cache_key(**kwargs, options=other, plugins=[])
    assert cache_key(**kwargs, options=base, plugins=[]) != cache_key(**kwargs, options=base, plugins=["ocr"])


def test_cache_clear_removes_entries(tmp_path, isolated_cache):
    path = _md(tmp_path, "a.md", "# 标题\n\n正文\n")
    read_document(path, ReadOptions())
    count, _size = usage(cache_root())
    assert count >= 1
    assert clear(cache_root()) >= 1
    assert usage(cache_root()) == (0, 0)


def test_pages_filter_still_applies_on_cache_hit(tmp_path, isolated_cache):
    path = _md(tmp_path, "a.md", "# A\n\n正文A\n")
    read_document(path, ReadOptions())  # 写缓存
    doc = read_document(path, ReadOptions(pages="1"))
    assert doc.meta["cache"] == "hit"
    assert len(doc.sections) == 1
