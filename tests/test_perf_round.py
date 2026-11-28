"""这一轮的性能改造：渐进式目录（toc）、目录并行解析、PDF 表格门控、ASR 标点开关。

这些改动都碰了「什么时候才做重活」，所以测试的重点是：
**结果不能变**（门控不能漏表、并行不能少文件、目录不能变样），
以及**新的开关要真的生效**。
"""

from __future__ import annotations

import os

import pytest

from xdoc.api import read_document
from xdoc.converters.media import _asr_payload
from xdoc.options import ReadOptions


def _md(tmp_path, name: str, body: str):
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


# ---------------------------------------------------------------- 渐进式目录
def test_toc_lists_sections_with_anchors(tmp_path):
    path = _md(tmp_path, "a.md", "# 第一章\n\n正文一\n\n## 第二章\n\n正文二\n")
    doc = read_document(path, ReadOptions())
    toc = doc.meta["toc"]
    assert isinstance(toc, list) and toc
    joined = "\n".join(toc)
    assert "第一章" in joined and "第二章" in joined
    assert "doc:0" in joined


def test_toc_is_absent_in_outline_and_search_mode(tmp_path):
    path = _md(tmp_path, "a.md", "# 标题\n\n正文\n")
    assert "toc" not in read_document(path, ReadOptions(outline=True)).meta
    from xdoc.options import SearchSpec

    searched = read_document(path, ReadOptions(search=SearchSpec(pattern="正文")))
    assert "toc" not in searched.meta


def test_toc_is_capped(tmp_path):
    body = "\n\n".join(f"## 第 {i} 节" for i in range(80))
    path = _md(tmp_path, "a.md", body + "\n")
    toc = read_document(path, ReadOptions()).meta["toc"]
    assert len(toc) <= 41  # 40 条 + 一行「还有 N 节」


# ---------------------------------------------------------------- 目录并行
def test_parallel_directory_read_matches_serial(tmp_path, monkeypatch):
    for i in range(3):
        _md(tmp_path, f"f{i}.md", f"# 文件 {i}\n\n内容 {i}\n")
    monkeypatch.setenv("XDOC_NO_PARALLEL", "1")
    serial = read_document(tmp_path, ReadOptions())
    monkeypatch.delenv("XDOC_NO_PARALLEL")
    parallel = read_document(tmp_path, ReadOptions())
    assert serial.meta["file_count"] == 3
    assert parallel.meta["file_count"] == serial.meta["file_count"] == 3
    assert [f["file"] for f in parallel.meta["files"]] == [f["file"] for f in serial.meta["files"]]
    assert [f["title"] for f in parallel.meta["files"]] == [f["title"] for f in serial.meta["files"]]
    assert "内容 2" in parallel.text and "内容 2" in serial.text


# ---------------------------------------------------------------- PDF 表格门控
def test_pdf_with_ruled_table_is_still_extracted(tmp_path):
    """表格门控改成「只看竖线」后，有线的表格必须照样认出来。"""
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((60, 80), "Invoice", fontsize=14)
    rows, cols = 3, 2
    left, top, w, h = 60.0, 120.0, 240.0, 120.0
    for r in range(rows + 1):
        y = top + r * h / rows
        page.draw_line(pymupdf.Point(left, y), pymupdf.Point(left + w, y))
    for c in range(cols + 1):
        x = left + c * w / cols
        page.draw_line(pymupdf.Point(x, top), pymupdf.Point(x, top + h))
    page.insert_text((70, 150), "Item")
    page.insert_text((190, 150), "Amount")
    page.insert_text((70, 190), "Contract")
    page.insert_text((190, 190), "1234.00")
    path = tmp_path / "table.pdf"
    doc.save(str(path))
    doc.close()

    out = read_document(path, ReadOptions())
    tables = [b for s in out.sections for b in s.blocks if b.kind == "table"]
    assert tables, "有画线的表格应该被认出来"
    text = out.text
    assert "Item" in text and "1234.00" in text


# ---------------------------------------------------------------- ASR 标点
def test_asr_punc_auto_is_off_in_auto_mode_and_on_when_engine_named():
    auto = ReadOptions(asr="auto", asr_punc="auto")
    assert _asr_payload("funasr", "/tmp/a.wav", auto)["punc"] is False
    named = ReadOptions(asr="zh", asr_punc="auto")
    assert _asr_payload("funasr", "/tmp/a.wav", named)["punc"] is True
    assert _asr_payload("funasr", "/tmp/a.wav", ReadOptions(asr_punc="on"))["punc"] is True
    assert _asr_payload("funasr", "/tmp/a.wav", ReadOptions(asr_punc="off"))["punc"] is False


def test_asr_punc_changes_cache_key():
    from xdoc.cache import cache_key

    def key(punc: str) -> str:
        return cache_key(sha256="abc", kind="audio",
                         options=ReadOptions(asr_punc=punc), plugins=())

    assert key("on") != key("off")
    # 非音视频类型的键不受影响
    assert cache_key(sha256="abc", kind="pdf",
                     options=ReadOptions(asr_punc="on"), plugins=()) == cache_key(
        sha256="abc", kind="pdf", options=ReadOptions(asr_punc="off"), plugins=())


def test_cjk_words_are_joined_without_punctuation_model():
    """没有标点模型时引擎输出「欢 迎 大 家」，我们要自己拼回去。"""
    from xdoc.workers.asr_worker import _join_cjk

    assert _join_cjk("欢 迎 大 家 来 体 验") == "欢迎大家来体验"
    assert _join_cjk("hello world") == "hello world"
    # 汉字之间的空格去掉；汉字与英文之间的空格留着
    assert _join_cjk("你好 world 朋友") == "你好 world 朋友"
    assert _join_cjk("你 好 world") == "你好 world"


def test_no_parallel_env_is_respected(tmp_path):
    """XDOC_NO_PARALLEL=1 时也要能正常读目录。"""
    _md(tmp_path, "a.md", "# 甲\n\n内容\n")
    os.environ["XDOC_NO_PARALLEL"] = "1"
    try:
        doc = read_document(tmp_path, ReadOptions())
    finally:
        os.environ.pop("XDOC_NO_PARALLEL", None)
    assert doc.meta["file_count"] == 1
