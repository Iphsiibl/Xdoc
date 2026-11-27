"""格式转换器：每个格式负责把源文件变成统一的 IR（Section -> Block）。"""

from __future__ import annotations

from pathlib import Path

from ..assets import AssetStore
from ..errors import XdocError
from ..options import ReadOptions

__all__ = ["convert", "filter_pages"]


def convert(path: str | Path, options: ReadOptions, assets: AssetStore):
    """把任意支持的文件转换成 Document。"""
    from ..detect import detect_kind

    p = Path(path)
    kind = detect_kind(p)
    handler = _handlers().get(kind)
    if handler is None:
        raise XdocError(f"暂不支持的文件类型: {kind}（{p.suffix or '无扩展名'}）")
    # 统一绑定资源子目录，避免各转换器漏调导致图片落到工作目录或路径为空
    assets.bind(p)
    doc = handler(p, options, assets)
    doc.meta.setdefault("engine", kind)
    if options.pages:
        filter_pages(doc, options.pages)
    return doc


def filter_pages(doc, spec: str) -> None:
    """按 "1-5,8" 之类的规格筛选章节（页/幻灯片/表）。"""
    wanted: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, _, end = part.partition("-")
            try:
                wanted.update(range(int(start), int(end) + 1))
            except ValueError:
                continue
        else:
            try:
                wanted.add(int(part))
            except ValueError:
                continue
    if not wanted:
        return
    doc.sections = [s for i, s in enumerate(doc.sections, start=1) if i in wanted]


def _handlers():
    from . import csv as csv_mod
    from . import docx as docx_mod
    from . import epub as epub_mod
    from . import html as html_mod
    from . import image as image_mod
    from . import legacy as legacy_mod
    from . import media as media_mod
    from . import pdf as pdf_mod
    from . import pptx as pptx_mod
    from . import text as text_mod
    from . import xlsx as xlsx_mod

    return {
        "pdf": pdf_mod.convert,
        "docx": docx_mod.convert,
        "pptx": pptx_mod.convert,
        "xlsx": xlsx_mod.convert,
        "html": html_mod.convert,
        "markdown": text_mod.convert_markdown,
        "text": text_mod.convert_text,
        "csv": csv_mod.convert,
        "epub": epub_mod.convert,
        "image": image_mod.convert,
        "audio": media_mod.convert_audio,
        "video": media_mod.convert_video,
        "doc_legacy": legacy_mod.convert_doc,
        "ppt_legacy": legacy_mod.convert_ppt,
        "xls_legacy": legacy_mod.convert_xls,
    }
