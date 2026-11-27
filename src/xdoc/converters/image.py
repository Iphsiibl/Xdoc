"""图片转换：元数据 + （装了 OCR 插件就）文字识别。

识别结果保留行结构，并给出识别置信度，便于判断是否可信。
"""

from __future__ import annotations

from pathlib import Path

from ..assets import AssetStore
from ..errors import XdocError
from ..ir import Block, Document, Section
from ..options import ReadOptions
from ..plugins import PluginManager


def _dimensions(path: Path) -> tuple[int | None, int | None]:
    try:
        import pymupdf

        doc = pymupdf.open(str(path))
        page = doc[0]
        rect = page.rect
        doc.close()
        return int(rect.width), int(rect.height)
    except Exception:
        pass
    try:
        from PIL import Image  # type: ignore

        with Image.open(path) as img:
            return img.width, img.height
    except Exception:
        return None, None


def convert(path: Path, options: ReadOptions, assets: AssetStore) -> Document:
    assets.bind(path)
    section = Section(label=path.name, anchor="image:0")
    meta: dict = {"engine": "builtin"}

    width, height = _dimensions(path)
    if width and height:
        meta["width"] = width
        meta["height"] = height
    meta["bytes"] = path.stat().st_size
    meta["format"] = path.suffix.lstrip(".").lower()

    manager = PluginManager(Path(options.plugin_dir) if options.plugin_dir else None)
    ocr_results: list[dict] = []
    if options.ocr != "off" and manager.is_installed("ocr"):
        payload = {"images": [str(path)]}
        result = manager.run_worker("ocr", payload)
        if result.get("error"):
            raise XdocError(f"OCR 失败: {result['error']}")
        ocr_results = result.get("results") or []

    if ocr_results:
        for item in ocr_results:
            text = (item.get("text") or "").strip()
            if not text:
                continue
            scores = [float(line.get("score", 0)) for line in item.get("lines", [])]
            section.add(Block(kind="text", text=text, meta={
                "ocr": True,
                "avg_score": round(sum(scores) / len(scores), 4) if scores else None,
            }))
        meta["ocr"] = "installed plugin"
    else:
        section.add(Block(kind="note", text="（图片内容需要 OCR 插件：xdoc plugin add ocr）"))

    return Document(source=str(path), kind="image", sections=[section], meta=meta)
