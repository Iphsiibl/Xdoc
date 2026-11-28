"""对外主入口：read()。

流程：识别类型 →（查缓存）→ 转换 →（需要时）OCR 补页 → 结构裁剪 → 预算/续读 → 渲染。
CLI 与 MCP 都调这里，保证两种入口结果一致。
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import fields, replace
from pathlib import Path

from .assets import AssetStore
from .cache import cache_key, cache_root, load as cache_load, store as cache_store
from .converters import convert, filter_pages
from .detect import detect_kind
from .errors import XdocError
from .ir import Block, Document, Section
from .options import ReadOptions, apply_budget, notify
from .outline import build_outline, build_toc, document_title
from .plugins import PluginManager
from .render import render
from .search import apply_search

# 目录并行解析的门槛：文件太少时，起进程的开销比省下的时间还大
PARALLEL_MIN_FILES = 2


def _notify(options: ReadOptions, message: str) -> None:
    """进度提示：有回调就报一声，没有就安静干活。"""
    notify(options, message)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ocr_pdf_pages(doc: Document, path: Path, options: ReadOptions) -> None:
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
        _notify(options, f"正在对 {len(needs)} 页做 OCR（可能要几十秒）…")
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


def _relevant_plugins(kind: str, options: ReadOptions) -> list[str]:
    """只有真会影响这类文档的插件，才进缓存键。

    早先进键的是「全部已装插件」：装一个 ffmpeg 就会让所有 PDF、Word 的缓存一起失效，
    你不得不把读过的文件重新解析一遍（64 页的 PDF 要 16 秒）。
    现在按类型和开关算：

    - pdf / image：只有开 OCR 时才看 ocr 插件；
    - audio / video：抽帧、抽音轨、时长都靠 media，转写靠 asr；
    - 其它类型（Word / Excel / PPT / HTML / Markdown…）：不依赖任何插件。
    """
    manager = PluginManager(Path(options.plugin_dir) if options.plugin_dir else None)
    wanted: list[str] = []
    if kind in ("pdf", "image"):
        if options.ocr != "off":
            wanted.append("ocr")
    elif kind in ("audio", "video"):
        wanted.append("media")
        if options.asr != "off":
            wanted.extend(["asr", "asr-zh"])
    return [name for name in wanted if manager.is_installed(name)]


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


def _options_payload(options: ReadOptions) -> dict:
    """给子进程用的选项副本：进度回调带不过去（进程之间不能共享函数）。"""
    return {f.name: getattr(options, f.name) for f in fields(options) if f.name != "on_progress"}


def _read_file_worker(payload: tuple[str, dict]) -> dict:
    """子进程里读一个文件：只回传结果，出错也变成消息（不抛异常）。"""
    path_str, options_dict = payload
    options = ReadOptions(**options_dict)
    try:
        doc = _read_document(path_str, options, strict_pages=False, with_search=False)
    except XdocError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # pragma: no cover - 子进程里的意外错误
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "doc": doc}


def _cached_document(path: Path, options: ReadOptions) -> Document | None:
    """目录并行前的快速检查：这个文件是不是已经在缓存里。

    命中就直接在当前进程读——缓存命中时读整个目录只要零点几秒，
    不能为了「并行」去付几十个子进程的启动钱。
    """
    if not options.use_cache:
        return None
    try:
        kind = detect_kind(path)
        sha = file_sha256(path)
    except OSError:
        return None
    root = cache_root()
    key = cache_key(sha256=sha, kind=kind, options=options,
                    plugins=_relevant_plugins(kind, options))
    doc = cache_load(root, key)
    if doc is None and kind == "pdf" and options.ocr != "off":
        # PDF 有两层缓存：基础层（没做 OCR）可能已经在了。
        # 但这份文档要是还需要 OCR，就得在子进程里补上，这里不能直接用。
        base_key = cache_key(sha256=sha, kind=kind,
                             options=replace(options, ocr="off"), plugins=[])
        base = cache_load(root, base_key)
        if base is None or base.meta.get("needs_ocr"):
            return None
        doc = base
    if doc is None:
        return None
    doc.source = str(path.resolve())
    doc.meta["cache"] = "hit"
    return doc


def _post_process(doc: Document, options: ReadOptions, *, strict_pages: bool,
                  with_search: bool) -> Document:
    """缓存/解析之后统一做的事：切页 → 检索 → 压成结构视图。

    单独抽出来，是因为目录并行时「命中缓存的文件」不走 _read_document，
    但该做的后处理一步都不能少（否则 outline 模式会漏出正文）。
    """
    if options.pages:
        filter_pages(doc, options.pages, strict=strict_pages)
    if options.search and with_search:
        doc = apply_search(doc, options.search)
    elif options.outline:
        doc = build_outline(doc)
    return doc


def _read_collection(root: Path, options: ReadOptions) -> Document:
    """读一个目录：把里面所有能读的文件合成一份文档。

    每个 section 记住自己来自哪个文件（section.file），锚点写成
    `<!-- file:report.pdf page 3 -->`，这样引用时不会张冠李戴。

    文件多的时候并行解析（进程池）：解析是 CPU 密集的，多进程才有效，
    多线程没用——PyMuPDF 不释放 GIL，实测并行 4 个 PDF 快了 1.6 倍。
    """
    files, skipped = _collect_files(root)
    if not files:
        raise XdocError(f"目录里没有可读的文件: {root}")

    docs: dict[Path, Document] = {}
    todo: list[Path] = []
    for path in files:
        cached = _cached_document(path, options)
        if cached is None:
            todo.append(path)
        else:
            docs[path] = _post_process(cached, options, strict_pages=False, with_search=False)

    if len(todo) >= PARALLEL_MIN_FILES and not os.environ.get("XDOC_NO_PARALLEL"):
        _notify(options, f"正在并行解析 {len(todo)} 个文件…")
        payload = _options_payload(options)
        workers = min(len(todo), max(2, (os.cpu_count() or 2)))
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_read_file_worker, (str(p), payload)): p for p in todo}
            for future in as_completed(futures):
                path = futures[future]
                try:
                    result = future.result()
                except Exception as exc:  # pragma: no cover - 子进程崩了
                    result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
                if result.get("ok"):
                    docs[path] = result["doc"]
                else:
                    skipped.append({
                        "file": path.relative_to(root).as_posix(),
                        "error": str(result.get("error") or "未知错误"),
                    })
    else:
        for path in todo:
            try:
                docs[path] = _read_document(path, options, strict_pages=False, with_search=False)
            except XdocError as exc:
                skipped.append({"file": path.relative_to(root).as_posix(), "error": str(exc)})

    sections: list[Section] = []
    files_meta: list[dict] = []
    for path in files:  # 保持文件顺序，输出才稳定
        doc = docs.get(path)
        if doc is None:
            continue
        rel = path.relative_to(root).as_posix()
        for section in doc.sections:
            section.file = rel
            sections.append(section)
        files_meta.append({
            "file": rel,
            "kind": doc.kind,
            "title": document_title(doc),
            "sections": len(doc.sections),
            "chars": doc.chars,
            "cache": doc.meta.get("cache", "miss"),
        })
    skipped.sort(key=lambda item: item["file"])

    if not files_meta:
        detail = "; ".join(f"{item['file']}: {item['error']}" for item in skipped)
        raise XdocError(f"目录里的文件都读不出来: {root}（{detail}）")
    if options.pages and not sections:
        raise XdocError(
            f"指定的页/节范围 {options.pages!r} 在这个目录里的任何文件里都不匹配"
        )

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
    if options.search:
        out = apply_search(out, options.search)
    if options.outline:
        out.meta["outline"] = True
    if skipped:
        out.meta["skipped"] = skipped
    return out


def read_document(path: str | Path, options: ReadOptions | None = None) -> Document:
    """把文件（或整个目录）读成 Document（未截断）。

    对外主入口：CLI 与 MCP 都走这里，保证两种入口结果一致。
    """
    options = options or ReadOptions()
    if options.search and options.outline:
        # 一个看结构、一个找内容，混在一起的结果谁也看不懂——直接说清楚。
        raise XdocError("outline 与 search 不能同时用：一个是看结构，一个是找内容")
    doc = _read_document(path, options, strict_pages=True)
    if not options.outline and not options.search:
        # 先给结构，再给正文：front-matter 里带一张地图，
        # Agent 读完就知道这份文档有什么、在哪一页，不用盲读全文。
        doc.meta["toc"] = build_toc(doc)
    return doc


def _read_document(path: str | Path, options: ReadOptions | None, *, strict_pages: bool,
                   with_search: bool = True) -> Document:
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
    plugins = _relevant_plugins(kind, options)
    key = cache_key(sha256=sha, kind=kind, options=options, plugins=plugins)
    root = cache_root()

    doc = cache_load(root, key) if options.use_cache else None
    if doc is not None:
        doc.source = str(p.resolve())
        doc.meta["sha256"] = sha
        doc.meta["bytes"] = p.stat().st_size
        doc.meta["assets_root"] = str(assets.root)
        doc.meta["cache"] = "hit"
        _notify(options, f"命中解析缓存: {p.name}")
    else:
        doc = _parse_document(p, options, kind, sha, assets, root, key)

    # 页码筛选放在缓存之后：缓存里存的是未筛选的全文，切页不用重新解析
    return _post_process(doc, options, strict_pages=strict_pages, with_search=with_search)


def _parse_document(p: Path, options: ReadOptions, kind: str, sha: str,
                    assets: AssetStore, root: Path, key: str) -> Document:
    """没命中缓存时的解析。

    PDF 走**两层缓存**：基础解析（不含 OCR）与 OCR 增强分开存。
    这样装完 OCR 插件再读同一份 PDF，只需要补 OCR 那一段，
    不用把整份文档重新解析一遍（64 页的 PDF 要 16 秒）。

    其它类型只有一层：它们的解析结果本来就依赖插件，只能整体重做。
    """
    base_options = options
    base_key: str | None = None
    if kind == "pdf" and options.ocr != "off":
        base_options = replace(options, ocr="off")
        base_key = cache_key(sha256=sha, kind=kind, options=base_options, plugins=[])

    doc: Document | None = None
    if base_key is not None and options.use_cache:
        doc = cache_load(root, base_key)

    if doc is None:
        _notify(options, f"正在解析: {p.name}（可能要十几秒）…")
        doc = convert(p, base_options, assets)
        if base_key is not None and options.use_cache:
            cache_store(root, base_key, doc)
        reused = False
    else:
        reused = True

    doc.source = str(p.resolve())
    doc.meta.setdefault("sha256", sha)
    doc.meta.setdefault("bytes", p.stat().st_size)
    doc.meta.setdefault("assets_root", str(assets.root))

    ocr_applied = False
    if doc.kind == "pdf" and doc.meta.get("needs_ocr") and options.ocr != "off":
        _ocr_pdf_pages(doc, p, options)
        ocr_applied = True

    # 基础条目就是最终结果时不必再存一份（PDF 的 OCR 没派上用场就是这种情况）
    if options.use_cache and (base_key is None or ocr_applied):
        cache_store(root, key, doc)
    doc.meta["cache"] = "hit" if reused and not ocr_applied else "miss"
    if reused and not ocr_applied:
        _notify(options, f"命中解析缓存: {p.name}")
    else:
        _notify(options, f"解析完成: {len(doc.sections)} 节 / {doc.chars} 字符")
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
