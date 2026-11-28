"""对外主入口：read()。

流程：识别类型 →（查缓存）→ 转换 →（需要时）OCR 补页 → 结构裁剪 → 预算/续读 → 渲染。
CLI 与 MCP 都调这里，保证两种入口结果一致。
"""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
from pathlib import Path

from .assets import AssetStore
from .cache import cache_key, cache_root, load as cache_load, store as cache_store
from .converters import convert, filter_pages
from .detect import detect_kind
from .errors import XdocError
from .ir import Block, Document, Section
from .options import ReadOptions, apply_budget
from .outline import build_outline
from .plugins import PLUGINS, PluginManager
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


def _installed_plugins(options: ReadOptions) -> list[str]:
    """已装插件清单：装没装会影响解析结果，必须进缓存键。"""
    manager = PluginManager(Path(options.plugin_dir) if options.plugin_dir else None)
    return [name for name in PLUGINS if manager.is_installed(name)]


def _collect_files(root: Path) -> tuple[list[Path], list[dict]]:
    """收集目录里能读的文件（跳过隐藏文件、临时文件与认不出的二进制）。

    返回 (可读文件列表, 跳过清单)；跳过的文件也要报告出来，
    否则用户会以为「目录里就这几个文件」。
    """
    found: list[Path] = []
    skipped: list[dict] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        name = path.name
        rel = path.relative_to(root).as_posix()
        if name.startswith(".") or name.startswith("~$"):
            skipped.append({"file": rel, "error": "隐藏文件或临时文件"})
            continue
        try:
            kind = detect_kind(path)
        except (OSError, FileNotFoundError) as exc:
            skipped.append({"file": rel, "error": f"无法识别: {exc}"})
            continue
        if kind == "unknown":
            skipped.append({"file": rel, "error": "认不出的文件格式"})
            continue
        found.append(path)
    return found, skipped


def _read_collection(root: Path, options: ReadOptions) -> Document:
    """读一个目录：把里面所有能读的文件合成一份文档。

    每个 section 记住自己来自哪个文件（section.file），锚点写成
    `<!-- file:report.pdf page 3 -->`，这样引用时不会张冠李戴。
    """
    files, skipped = _collect_files(root)
    if not files:
        raise XdocError(f"目录里没有可读的文件: {root}")

    sections: list[Section] = []
    files_meta: list[dict] = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        try:
            doc = read_document(path, options)
        except XdocError as exc:
            skipped.append({"file": rel, "error": str(exc)})
            continue
        for section in doc.sections:
            section.file = rel
            sections.append(section)
        files_meta.append({
            "file": rel,
            "kind": doc.kind,
            "sections": len(doc.sections),
            "chars": doc.chars,
            "cache": doc.meta.get("cache", "miss"),
        })

    if not files_meta:
        detail = "; ".join(f"{item['file']}: {item['error']}" for item in skipped)
        raise XdocError(f"目录里的文件都读不出来: {root}（{detail}）")

    out = Document(
        source=str(root.resolve()),
        kind="collection",
        sections=sections,
        meta={
            "engine": "collection",
            "file_count": len(files_meta),
            "files": files_meta,
        },
    )
    if options.outline:
        out.meta["outline"] = True
    if skipped:
        out.meta["skipped"] = skipped
    return out


def read_document(path: str | Path, options: ReadOptions | None = None) -> Document:
    """把文件（或整个目录）读成 Document（未截断）。"""
    options = options or ReadOptions()
    p = Path(path).expanduser()
    if not p.exists():
        raise XdocError(f"文件不存在: {p}")
    if p.is_dir():
        return _read_collection(p, options)

    assets = AssetStore(Path(options.assets_dir) if options.assets_dir else None,
                        enabled=options.images != "none")
    kind = detect_kind(p)
    sha = file_sha256(p)
    key = cache_key(sha256=sha, kind=kind, options=options, plugins=_installed_plugins(options))
    root = cache_root()

    doc = cache_load(root, key) if options.use_cache else None
    if doc is not None:
        doc.source = str(p.resolve())
        doc.meta["sha256"] = sha
        doc.meta["bytes"] = p.stat().st_size
        doc.meta["assets_root"] = str(assets.root)
        doc.meta["cache"] = "hit"
    else:
        doc = convert(p, options, assets)
        doc.source = str(p.resolve())
        doc.meta.setdefault("sha256", sha)
        doc.meta.setdefault("bytes", p.stat().st_size)
        doc.meta.setdefault("assets_root", str(assets.root))

        if doc.kind == "pdf" and doc.meta.get("needs_ocr") and options.ocr != "off":
            _ocr_pdf_pages(doc, p, options, assets)

        doc.meta["cache"] = "miss"
        if options.use_cache:
            cache_store(root, key, doc)

    # 页码筛选放在缓存之后：缓存里存的是未筛选的全文，切页不用重新解析
    if options.pages:
        filter_pages(doc, options.pages)
    if options.outline:
        doc = build_outline(doc)
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
