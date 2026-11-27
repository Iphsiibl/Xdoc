"""HTML / 富文本转换：按标题切段，结构化为 Markdown。"""

from __future__ import annotations

import re
from pathlib import Path

from ..assets import AssetStore
from ..errors import XdocError
from ..ir import Block, Document, Section
from ..options import ReadOptions

DROP_TAGS = ["script", "style", "noscript", "iframe", "svg", "canvas", "form"]


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "big5", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def convert(path: Path, options: ReadOptions, assets: AssetStore) -> Document:
    try:
        from bs4 import BeautifulSoup
        from markdownify import markdownify
    except ImportError as exc:  # pragma: no cover
        raise XdocError("缺少 beautifulsoup4 / markdownify") from exc

    raw = _decode(path.read_bytes())
    soup = BeautifulSoup(raw, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else None
    for tag in soup(DROP_TAGS):
        tag.decompose()

    body = soup.body or soup
    sections: list[Section] = []
    current = Section(label=title or "document", anchor="section:0")
    sections.append(current)

    heading_re = re.compile(r"^#{1,6}\s+(.*)$")
    for node in body.find_all(["h1", "h2", "h3", "p", "ul", "ol", "pre", "table", "blockquote"], recursive=True):
        if node.name in ("h1", "h2", "h3"):
            text = node.get_text(" ", strip=True)
            if not text:
                continue
            level = int(node.name[1])
            if level <= 2 and current.blocks:
                current = Section(label=text, anchor=f"section:{len(sections)}")
                sections.append(current)
            current.add(Block(kind="heading", text=text, level=level))
        elif node.name == "table":
            rows = []
            for tr in node.find_all("tr"):
                cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
                if any(cells):
                    rows.append(cells)
            if rows:
                current.add(Block(kind="table", rows=rows, header=True))
        elif node.name in ("ul", "ol"):
            for li in node.find_all("li", recursive=False):
                text = li.get_text(" ", strip=True)
                if text:
                    current.add(Block(kind="list_item", text=text))
        elif node.name == "pre":
            text = node.get_text("\n", strip=False).strip()
            if text:
                current.add(Block(kind="code", text=text))
        elif node.name == "blockquote":
            text = node.get_text(" ", strip=True)
            if text:
                current.add(Block(kind="quote", text=text))
        else:  # p
            text = node.get_text(" ", strip=True)
            if text:
                current.add(Block(kind="text", text=text))

    if not any(s.blocks for s in sections):
        # 兜底：整页转 Markdown
        md = markdownify(str(body), heading_style="ATX", bullets="-")
        sections[0].add(Block(kind="text", text=md.strip()))

    meta = {"engine": "beautifulsoup4+markdownify", "title": title}
    return Document(source=str(path), kind="html", sections=sections, meta=meta)
