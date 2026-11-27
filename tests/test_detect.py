"""文件类型识别。"""

from __future__ import annotations

from conftest import require, sample

from xdoc.detect import detect_kind


def test_detect_text_and_csv(tmp_path):
    md = tmp_path / "a.md"
    md.write_text("# 标题\n", encoding="utf-8")
    assert detect_kind(md) in ("markdown", "text")

    csv_file = tmp_path / "b.csv"
    csv_file.write_text("a,b\n1,2\n", encoding="utf-8")
    assert detect_kind(csv_file) == "csv"


def test_detect_binary_by_magic(tmp_path):
    png = tmp_path / "c.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    assert detect_kind(png) == "image"

    wav = tmp_path / "d.wav"
    wav.write_bytes(b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 16)
    assert detect_kind(wav) == "audio"


def test_detect_office_by_zip_layout(tmp_path):
    import zipfile

    docx = tmp_path / "e.docx"
    with zipfile.ZipFile(docx, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", "<document/>")
    assert detect_kind(docx) == "docx"

    pptx = tmp_path / "f.pptx"
    with zipfile.ZipFile(pptx, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("ppt/presentation.xml", "<p/>")
    assert detect_kind(pptx) == "pptx"

    xlsx = tmp_path / "g.xlsx"
    with zipfile.ZipFile(xlsx, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("xl/workbook.xml", "<workbook/>")
    assert detect_kind(xlsx) == "xlsx"


def test_detect_real_samples():
    cases = {
        sample("docx", "calibre_demo.docx"): "docx",
        sample("pptx", "poi_SampleShow.pptx"): "pptx",
        sample("xlsx", "microsoft_sample.xlsx"): "xlsx",
        sample("pdf", "en_dummy.pdf"): "pdf",
        sample("images", "zh_easyocr_chinese.jpg"): "image",
        sample("audio", "zh_funasr_example.wav"): "audio",
        sample("video", "big_buck_bunny.mp4"): "video",
        sample("html", "zh_wikipedia.html"): "html",
    }
    for path, expected in cases.items():
        require(path)
        assert detect_kind(path) == expected
