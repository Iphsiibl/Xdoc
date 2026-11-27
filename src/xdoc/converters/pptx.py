"""PPTX 转换：逐张幻灯片，保留文本层级、表格、图片与备注。"""

from __future__ import annotations

from pathlib import Path

from ..assets import AssetStore
from ..errors import XdocError
from ..ir import Block, Document, Section
from ..options import ReadOptions


def convert(path: Path, options: ReadOptions, assets: AssetStore) -> Document:
    try:
        from pptx import Presentation
    except ImportError as exc:  # pragma: no cover
        raise XdocError("缺少 python-pptx") from exc

    try:
        prs = Presentation(str(path))
    except Exception as exc:
        raise XdocError(f"无法打开 PPTX: {exc}") from exc

    assets.bind(path)
    sections: list[Section] = []
    image_count = 0

    for index, slide in enumerate(prs.slides, start=1):
        section = Section(label=f"slide {index}", anchor=f"slide:{index}")
        title_shape = None
        try:
            title_shape = slide.shapes.title
        except Exception:
            title_shape = None

        shapes = sorted(slide.shapes, key=lambda s: ((s.top or 0), (s.left or 0)))
        for shape in shapes:
            try:
                if shape.has_table:
                    rows = []
                    for row in shape.table.rows:
                        rows.append([cell.text.strip() for cell in row.cells])
                    rows = [r for r in rows if any(c for c in r)]
                    if rows:
                        section.add(Block(kind="table", rows=rows, header=True))
                    continue
                if shape.shape_type is not None and str(shape.shape_type).startswith("PICTURE"):
                    image = shape.image
                    ext = image.ext or "png"
                    rel = assets.save(image.blob, f"slide{index}-{image_count + 1}.{ext}")
                    if rel:
                        image_count += 1
                        section.add(Block(kind="image", src=rel, text=f"幻灯片 {index} 图片"))
                    continue
            except Exception:
                pass

            if getattr(shape, "has_text_frame", False):
                is_title = title_shape is not None and shape == title_shape
                for para in shape.text_frame.paragraphs:
                    text = "".join(run.text for run in para.runs).strip()
                    if not text:
                        continue
                    if is_title:
                        section.add(Block(kind="heading", text=text, level=1))
                    elif para.level and para.level > 0:
                        section.add(Block(kind="list_item", text=text, level=para.level))
                    else:
                        section.add(Block(kind="text", text=text))

        try:
            if slide.has_notes_slide:
                notes = slide.notes_slide.notes_text_frame.text.strip()
                if notes:
                    section.add(Block(kind="note", text=f"备注: {notes}"))
        except Exception:
            pass

        sections.append(section)

    meta = {
        "engine": "python-pptx",
        "slides": len(sections),
        "images_extracted": image_count,
    }
    return Document(source=str(path), kind="pptx", sections=sections, meta=meta)
