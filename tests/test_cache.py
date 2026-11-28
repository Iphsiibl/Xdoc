"""解析缓存：内容不变就不重复解析。"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import require, sample
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


def test_cache_key_separates_asr_language():
    """转写语言会改变结果，键必须跟着变（否则换个语言读到旧语言的转写）。"""
    zh = cache_key(sha256="x", kind="audio", options=ReadOptions(asr_language="zh"), plugins=[])
    en = cache_key(sha256="x", kind="audio", options=ReadOptions(asr_language="en"), plugins=[])
    assert zh != en
    # 非音视频不受影响，键保持稳定（不然所有文件的缓存会一次性作废）
    assert (cache_key(sha256="x", kind="pdf", options=ReadOptions(asr_language="zh"), plugins=[])
            == cache_key(sha256="x", kind="pdf", options=ReadOptions(asr_language="en"), plugins=[]))


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


def _fake_plugin(plugin_dir: Path, name: str) -> None:
    """装一个「假插件」：只放标记文件，用来测缓存键跟插件的关系。"""
    (plugin_dir / name).mkdir(parents=True, exist_ok=True)
    (plugin_dir / name / ".installed").write_text("", encoding="utf-8")


def test_unrelated_plugin_does_not_invalidate_cache(tmp_path, isolated_cache):
    """装一个跟文档无关的插件，不该逼你把文档重新解析一遍。"""
    plugin_dir = tmp_path / "plugins"
    path = _md(tmp_path, "a.md", "# 标题\n\n正文\n")
    options = ReadOptions(plugin_dir=str(plugin_dir))

    first = read_document(path, options)
    assert first.meta["cache"] == "miss"

    _fake_plugin(plugin_dir, "media")   # 装了 ffmpeg
    again = read_document(path, options)
    assert again.meta["cache"] == "hit"
    assert again.text == first.text


def test_pdf_base_parse_is_reused_after_installing_ocr(tmp_path, isolated_cache, monkeypatch):
    """PDF 分两层缓存：装 OCR 插件后不用把整份 PDF 重新解析。"""
    pdf = require(sample("pdf", "en_dummy.pdf"))
    plugin_dir = tmp_path / "plugins"
    options = ReadOptions(plugin_dir=str(plugin_dir))

    calls: list[str] = []
    import xdoc.api as api

    real_convert = api.convert

    def counting_convert(path, opts, assets):
        calls.append(str(path))
        return real_convert(path, opts, assets)

    monkeypatch.setattr(api, "convert", counting_convert)

    read_document(pdf, options)
    assert len(calls) == 1

    _fake_plugin(plugin_dir, "ocr")     # 装了 OCR
    doc = read_document(pdf, options)
    assert len(calls) == 1, "装了 OCR 之后不该重新解析 PDF"
    assert doc.meta["cache"] == "hit"
