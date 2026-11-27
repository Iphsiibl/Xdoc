"""对外主入口：read()。

流程：识别类型 → 转换 →（需要时）OCR 补页 → 预算/续读 → 渲染。
CLI 与 MCP 都调这里，保证两种入口结果一致。
"""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
from pathlib import Path

from .assets import AssetStore
from .converters import convert
from .errors import XdocError
from .ir import Block, Document
from .options import ReadOptions, apply_budget
from .plugins import PluginManager
from .render import render


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ocr_pdf_pages(doc: Document, path: Path, options: ReadOptions, assets: AssetStore) -> None:
    """给没有文本层的 PDF 页补 OCR 文字。"""
    manager = PluginManager(Path(options.plugin_dir) if options.plugin_dir else None)
    if not manager.is_installed("ocr"):
        return
    needs = doc.meta.get("needs_ocr") or []
    if not needs:
        return
    try:
        import pymupdf
    except ImportError:  # pragma: no cover
        return

    tmpdir = Path(tempfile.mkdtemp(prefix="xdoc-ocr-"))
    try:
        pdf = pymupdf.open(str(path))
        image_paths: list[str] = []
        for page_number in needs:
            page = pdf[page_number - 1]
            pix = page.get_pixmap(dpi=200)
            target = tmpdir / f"p{page_number}.png"
            pix.save(str(target))
            image_paths.append(str(target))

        result = manager.run_worker("ocr", {"images": image_paths})
        if result.get("error"):
            raise XdocError(f"OCR 失败: {result['error']}")
        by_index = {item.get("index"): item for item in result.get("results") or []}

        for page_number in needs:
            item = by_index.get(page_number - 1) or {}
            text = (item.get("text") or "").strip()
            section = next((s for s in doc.sections if s.anchor == f"page:{page_number}"), None)
            if section is None:
                continue
            # 去掉"无文本层"的提示块，替换成 OCR 结果
            section.blocks = [b for b in section.blocks if not (b.kind == "note" and "没有文本层" in b.text)]
            if text:
                section.add(Block(kind="text", text=text, meta={"ocr": True, "page": page_number}))
        pdf.close()
        doc.meta["ocr_pages"] = list(needs)
    finally:
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)


def read_document(path: str | Path, options: ReadOptions | None = None) -> Document:
    """把文件读成 Document（未截断）。"""
    options = options or ReadOptions()
    p = Path(path).expanduser()
    if not p.exists():
        raise XdocError(f"文件不存在: {p}")
    if p.is_dir():
        raise XdocError(f"暂不支持目录: {p}（请逐个文件读取）")

    assets = AssetStore(Path(options.assets_dir) if options.assets_dir else None,
                        enabled=options.images != "none")
    doc = convert(p, options, assets)
    doc.source = str(p.resolve())
    doc.meta.setdefault("sha256", file_sha256(p))
    doc.meta.setdefault("bytes", p.stat().st_size)
    doc.meta.setdefault("assets_root", str(assets.root))

    if doc.kind == "pdf" and doc.meta.get("needs_ocr") and options.ocr != "off":
        _ocr_pdf_pages(doc, p, options, assets)

    return doc


def read(path: str | Path, options: ReadOptions | None = None) -> str:
    """主入口：返回渲染后的文本。"""
    options = options or ReadOptions()
    doc = read_document(path, options)
    doc, cursor = apply_budget(doc, options.max_tokens, options.cursor)
    if cursor:
        doc.meta["next_cursor"] = cursor
    else:
        doc.meta.pop("next_cursor", None)
    return render(doc, options.format, front_matter=options.front_matter)


def read_with_meta(path: str | Path, options: ReadOptions | None = None) -> tuple[str, Document]:
    options = options or ReadOptions()
    doc = read_document(path, options)
    doc, cursor = apply_budget(doc, options.max_tokens, options.cursor)
    if cursor:
        doc.meta["next_cursor"] = cursor
    else:
        doc.meta.pop("next_cursor", None)
    return render(doc, options.format, front_matter=options.front_matter), doc
