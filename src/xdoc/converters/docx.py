"""DOCX 转换：段落顺序、标题层级、列表、表格、超链接、图片都保留。"""

from __future__ import annotations

import re
from pathlib import Path

from ..assets import AssetStore
from ..errors import XdocError
from ..ir import Block, Document, Section
from ..options import ReadOptions

HEADING_RE = re.compile(r"^(heading|标题)\s*(\d+)$", re.IGNORECASE)
LIST_RE = re.compile(r"(list|列表|项目符号|编号)", re.IGNORECASE)


def _style_name(paragraph) -> str:
    try:
        return paragraph.style.name or ""
    except Exception:
        return ""


def _paragraph_text(paragraph) -> str:
    """取段落文本，尽量带上超链接的 URL（忠实）。"""
    parts: list[str] = []
    try:
        for item in paragraph.iter_inner_content():
            if hasattr(item, "text") and hasattr(item, "url"):
                url = item.url or ""
                parts.append(f"[{item.text}]({url})" if url else item.text)
            else:
                parts.append(item.text)
        return "".join(parts)
    except AttributeError:
        return paragraph.text


def _list_level(paragraph) -> int:
    try:
        pPr = paragraph._p.pPr
        if pPr is not None and pPr.numPr is not None and pPr.numPr.ilvl is not None:
            return int(pPr.numPr.ilvl.val)
    except Exception:
        pass
    try:
        return max(0, int(paragraph.paragraph_format.left_indent.pt // 18))
    except Exception:
        return 0


def _extract_images(paragraph, doc, assets: AssetStore, index: int) -> list[Block]:
    blocks: list[Block] = []
    try:
        from docx.oxml.ns import qn
    except ImportError:  # pragma: no cover
        return blocks
    for blip in paragraph._p.xpath(".//a:blip"):
        r_id = blip.get(qn("r:embed"))
        if not r_id:
            continue
        try:
            part = doc.part.related_parts[r_id]
            ext = part.partname.ext or "png"
            rel = assets.save(part.blob, f"img{index}.{ext}")
        except Exception:
            continue
        if rel:
            blocks.append(Block(kind="image", src=rel, text=f"文档图片 {index}"))
    return blocks


def convert(path: Path, options: ReadOptions, assets: AssetStore) -> Document:
    try:
        import docx
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as exc:  # pragma: no cover
        raise XdocError("缺少 python-docx") from exc

    try:
        doc = docx.Document(str(path))
    except Exception as exc:
        raise XdocError(f"无法打开 DOCX: {exc}") from exc

    assets.bind(path)
    section = Section(label="document", anchor="doc:0")
    image_index = 0
    table_count = 0

    for child in doc.element.body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            paragraph = Paragraph(child, doc)
            text = _paragraph_text(paragraph).strip()
            style = _style_name(paragraph)
            heading = HEADING_RE.match(style.strip())
            if heading and text:
                section.add(Block(kind="heading", text=text, level=int(heading.group(2))))
            elif LIST_RE.search(style) and text:
                section.add(Block(kind="list_item", text=text, level=_list_level(paragraph)))
            elif text:
                section.add(Block(kind="text", text=text))
            for block in _extract_images(paragraph, doc, assets, image_index):
                section.add(block)
                image_index += 1
        elif tag == "tbl":
            table = Table(child, doc)
            rows = []
            for row in table.rows:
                rows.append([cell.text.strip() for cell in row.cells])
            rows = [r for r in rows if any(c for c in r)]
            if rows:
                table_count += 1
                section.add(Block(kind="table", rows=rows, header=True))

    meta = {
        "engine": "python-docx",
        "paragraphs": len(section.blocks),
        "tables": table_count,
    }
    return Document(source=str(path), kind="docx", sections=[section], meta=meta)
