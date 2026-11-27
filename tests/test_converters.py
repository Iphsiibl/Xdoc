"""各格式转换结果的结构断言（忠实度优先：不丢块、有锚点、表格成 Markdown）。"""

from __future__ import annotations

from conftest import require, sample

from xdoc.api import read_document
from xdoc.options import ReadOptions


def kinds_of(doc):
    return [b.kind for section in doc.sections for b in section.blocks]


def test_docx_keeps_headings_and_tables():
    path = require(sample("docx", "calibre_demo.docx"))
    doc = read_document(path, ReadOptions())
    assert doc.kind == "docx"
    assert doc.sections
    assert "heading" in kinds_of(doc)
    assert "table" in kinds_of(doc)
    assert doc.meta.get("sha256")
    assert doc.meta.get("bytes") == path.stat().st_size


def test_pptx_has_slide_anchors():
    path = require(sample("pptx", "poi_SampleShow.pptx"))
    doc = read_document(path, ReadOptions())
    assert doc.kind == "pptx"
    anchors = [s.anchor for s in doc.sections]
    assert anchors and all(a.startswith("slide:") for a in anchors)
    assert "text" in kinds_of(doc)


def test_xlsx_has_sheet_anchors_and_values():
    path = require(sample("xlsx", "microsoft_sample.xlsx"))
    doc = read_document(path, ReadOptions())
    assert doc.kind == "xlsx"
    anchors = [s.anchor for s in doc.sections]
    assert any(a.startswith("sheet:") for a in anchors)
    tables = [b for s in doc.sections for b in s.blocks if b.kind == "table"]
    assert tables and tables[0].rows


def test_html_headings_and_tables():
    path = require(sample("html", "zh_wikipedia.html"))
    doc = read_document(path, ReadOptions())
    assert doc.kind == "html"
    assert "heading" in kinds_of(doc)
    assert doc.chars > 1000


def test_pdf_pages_have_anchors_and_text():
    path = require(sample("pdf", "en_dummy.pdf"))
    doc = read_document(path, ReadOptions())
    assert doc.kind == "pdf"
    anchors = [s.anchor for s in doc.sections]
    assert anchors == ["page:1"]
    assert "Dummy" in doc.text


def test_pdf_pages_filter():
    path = require(sample("pdf", "zh_wiki_python.pdf"))
    doc = read_document(path, ReadOptions(pages="1-2"))
    assert len(doc.sections) <= 2
    assert all(s.anchor in ("page:1", "page:2") for s in doc.sections)


def test_csv_becomes_table(tmp_path):
    path = tmp_path / "table.csv"
    path.write_text("name,value\nfoo,1\nbar,2\n", encoding="utf-8")
    doc = read_document(path, ReadOptions())
    tables = [b for s in doc.sections for b in s.blocks if b.kind == "table"]
    assert tables
    assert tables[0].rows[0] == ["name", "value"]
    assert tables[0].rows[-1] == ["bar", "2"]


def test_pdf_table_cells_have_no_newlines():
    """PDF 表格单元格里常有多行文字，必须压成一行，否则 Markdown 表格列对不齐。"""
    from xdoc.converters.pdf import _cell_text

    assert _cell_text("a\nb") == "a b"
    assert _cell_text("  x  \n y ") == "x y"
    assert _cell_text(None) == ""

    path = require(sample("pdf", "en_arxiv_attention.pdf"))
    doc = read_document(path, ReadOptions())
    tables = [b for s in doc.sections for b in s.blocks if b.kind == "table"]
    assert tables, "样本里应该有带画线的表格"
    for table in tables:
        for row in table.rows:
            for cell in row:
                assert "\n" not in cell
