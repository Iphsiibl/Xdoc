"""EPUB 转换：按 spine 顺序逐章转 Markdown。"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from ..assets import AssetStore
from ..errors import XdocError
from ..ir import Block, Document, Section
from ..options import ReadOptions


def convert(path: Path, options: ReadOptions, assets: AssetStore) -> Document:
    try:
        from bs4 import BeautifulSoup
        from markdownify import markdownify
    except ImportError as exc:  # pragma: no cover
        raise XdocError("缺少 beautifulsoup4 / markdownify") from exc

    try:
        zf = zipfile.ZipFile(path)
    except Exception as exc:
        raise XdocError(f"无法打开 EPUB: {exc}") from exc

    try:
        container = ET.fromstring(zf.read("META-INF/container.xml"))
    except Exception as exc:
        raise XdocError(f"EPUB 缺少 container.xml: {exc}") from exc

    opf_path = ""
    for rootfile in container.iter():
        if rootfile.tag.endswith("rootfile"):
            opf_path = rootfile.attrib.get("full-path", "")
            break
    if not opf_path:
        raise XdocError("EPUB 结构异常：找不到 OPF 文件")

    base = Path(opf_path).parent
    opf = ET.fromstring(zf.read(opf_path))
    manifest: dict[str, str] = {}
    for item in opf.iter():
        if item.tag.endswith("item"):
            manifest[item.attrib.get("id", "")] = item.attrib.get("href", "")

    sections: list[Section] = []
    for index, spine in enumerate(opf.iter()):
        if not spine.tag.endswith("itemref"):
            continue
        href = manifest.get(spine.attrib.get("idref", ""), "")
        if not href:
            continue
        item_path = (base / href).as_posix().lstrip("./")
        try:
            raw = zf.read(item_path).decode("utf-8", "replace")
        except KeyError:
            continue
        soup = BeautifulSoup(raw, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else f"第 {index + 1} 章"
        md = markdownify(str(soup.body or soup), heading_style="ATX", bullets="-")
        section = Section(label=title, anchor=f"chapter:{index + 1}")
        section.add(Block(kind="text", text=md.strip()))
        sections.append(section)

    meta = {"engine": "builtin-epub", "chapters": len(sections)}
    return Document(source=str(path), kind="epub", sections=sections, meta=meta)
