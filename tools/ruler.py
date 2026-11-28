"""质量尺子：参考文本抽取 + 内容保留率。

尺子（可复现）：
  1. 参考文本 reference：由"最原始"的方式抽取（PDF 用 pymupdf 纯文本、DOCX 用 python-docx、
     PPTX 用 python-pptx、XLSX 用 openpyxl、HTML 用 BeautifulSoup）——它不是"标准答案"，
     但能回答"有没有把原文里的字丢掉"。
  2. 内容保留率 recall：参考文本与候选输出的 8-gram shingle 交集占比（去空白/小写）。
  3. 词级保留率 token_recall：只比词的多重集，忽略顺序。

这个模块只提供"尺子"，不负责跑引擎；跑引擎与出报告在 tools/acceptance.py + tools/report.py。
"""

from __future__ import annotations

import re
from pathlib import Path

WS = re.compile(r"\s+")
NONWORD = re.compile(r"[^0-9a-z\u4e00-\u9fff\u3040-\u30ff%\.\,\:\;\-\+\(\)\[\]/\\#@&*=\"'<>]+")
TOKEN = re.compile(r"[0-9a-z\u4e00-\u9fff]+")


def norm(text: str) -> str:
    text = text.lower()
    text = NONWORD.sub(" ", text)
    return WS.sub(" ", text).strip()


def shingles(text: str, size: int = 8) -> set[str]:
    text = norm(text)
    if len(text) < size:
        return {text} if text else set()
    return {text[i:i + size] for i in range(len(text) - size + 1)}


def recall(reference: str, candidate: str) -> float:
    ref = shingles(reference)
    if not ref:
        return 1.0 if not norm(candidate) else 0.0
    cand = shingles(candidate)
    return len(ref & cand) / len(ref)


def token_recall(reference: str, candidate: str) -> float:
    """词级保留率：忽略顺序，只看"有没有字被弄丢"。

    比 8-gram 保留率更严格也更有意义：表格重排会打散 8-gram，
    但只要一个词都没丢，token_recall 就仍然是 1.0。
    """
    from collections import Counter

    ref = Counter(TOKEN.findall(reference.lower()))
    cand = Counter(TOKEN.findall(candidate.lower()))
    total = sum(ref.values())
    if not total:
        return 1.0
    return sum((ref & cand).values()) / total


# ---------- 参考文本 ----------
def ref_pdf(path: Path) -> str:
    import pymupdf

    doc = pymupdf.open(str(path))
    parts = []
    for page in doc:
        parts.append(page.get_text("text"))
    doc.close()
    return "\n".join(parts)


def ref_docx(path: Path) -> str:
    import docx

    d = docx.Document(str(path))
    parts = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            parts.append(" ".join(c.text for c in row.cells))
    return "\n".join(parts)


def ref_pptx(path: Path) -> str:
    from pptx import Presentation

    prs = Presentation(str(path))
    parts = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                parts.append(shape.text_frame.text)
            if shape.has_table:
                for row in shape.table.rows:
                    parts.append(" ".join(c.text for c in row.cells))
    return "\n".join(parts)


def _cell_text(v) -> str:
    """单元格值 → 文本。日期时间统一用 ISO 8601（和 xdoc 的输出一致），
    否则 '2014-01-01 00:00:00' 与 '2014-01-01T00:00:00' 会被误判成"丢字"。"""
    import datetime as _dt

    if v is None:
        return ""
    if isinstance(v, (_dt.datetime, _dt.date, _dt.time)):
        return v.isoformat()
    return str(v)


def ref_xlsx(path: Path) -> str:
    import openpyxl

    wb = openpyxl.load_workbook(str(path), data_only=True)
    parts = []
    for ws in wb.worksheets:
        parts.append(ws.title)
        for row in ws.iter_rows(values_only=True):
            parts.append(" ".join(_cell_text(v) for v in row))
    return "\n".join(parts)


def ref_html(path: Path) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    return soup.get_text("\n")


def ref_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def ref_audio(path: Path) -> str:
    return ""


def ref_image(path: Path) -> str:
    return ""


REF = {
    "pdf": ref_pdf,
    "docx": ref_docx,
    "pptx": ref_pptx,
    "xlsx": ref_xlsx,
    "html": ref_html,
    "md": ref_text,
    "txt": ref_text,
    "csv": ref_text,
    "wav": ref_audio,
    "flac": ref_audio,
    "mp4": ref_audio,
    "jpg": ref_image,
    "png": ref_image,
}
