"""格式转换器：每个格式负责把源文件变成统一的 IR（Section -> Block）。"""

from __future__ import annotations

from pathlib import Path

from ..assets import AssetStore
from ..errors import XdocError
from ..options import ReadOptions

__all__ = ["convert", "filter_pages"]


def convert(path: str | Path, options: ReadOptions, assets: AssetStore):
    """把任意支持的文件转换成 Document。

    注意：这里不做页码筛选，也不做结构裁剪——那些在 api.read_document 里统一做，
    这样同一份解析结果可以被缓存复用（切页/取目录不必重新解析文件）。
    """
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
    return doc


def parse_page_spec(spec: str) -> set[int]:
    """解析 "1-5,8" 这样的范围。

    写错就直接报错——静默忽略会让用户以为读到了那几页，其实拿到的是全文或空文档。
    """
    wanted: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, _, end = part.partition("-")
            try:
                start_n = int(start)
                end_n = int(end)
            except ValueError as exc:
                raise XdocError(f"无法解析的页码范围: {part!r}（示例: 1-5,8）") from exc
            if start_n > end_n:
                raise XdocError(f"页码范围顺序反了: {part!r}（示例: 1-5,8）")
            wanted.update(range(start_n, end_n + 1))
        else:
            try:
                wanted.add(int(part))
            except ValueError as exc:
                raise XdocError(f"无法解析的页码: {part!r}（示例: 1-5,8）") from exc
    if not wanted:
        raise XdocError(f"页码范围是空的: {spec!r}（示例: 1-5,8）")
    return wanted


def filter_pages(doc, spec: str, *, strict: bool = True) -> None:
    """按 "1-5,8" 之类的规格筛选章节（页/幻灯片/表）。

    strict=True 时，选不中任何一节就报错（避免"读到了空文档却以为成功"）；
    读目录时传 strict=False，因为不同文件的页数本来就不一样。
    """
    wanted = parse_page_spec(spec)
    total = len(doc.sections)
    doc.sections = [s for i, s in enumerate(doc.sections, start=1) if i in wanted]
    if strict and total and not doc.sections:
        raise XdocError(
            f"指定的范围 {spec!r} 超出文档范围（文档共 {total} 节，可用 1-{total}）"
        )


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
