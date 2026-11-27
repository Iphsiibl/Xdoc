"""纯文本 / Markdown 转换。

Markdown 不做重排：按行识别标题/列表/代码块，其余按段落保留。
"""

from __future__ import annotations

import re
from pathlib import Path

from ..assets import AssetStore
from ..ir import Block, Document, Section
from ..options import ReadOptions

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")


def decode_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8", "gb18030", "big5", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def convert_text(path: Path, options: ReadOptions, assets: AssetStore) -> Document:
    text = decode_text(path)
    section = Section(label="text", anchor="doc:0")
    section.add(Block(kind="text", text=text.rstrip("\n")))
    meta = {"engine": "builtin", "lines": text.count("\n") + 1}
    return Document(source=str(path), kind="text", sections=[section], meta=meta)


def convert_markdown(path: Path, options: ReadOptions, assets: AssetStore) -> Document:
    text = decode_text(path)
    section = Section(label="markdown", anchor="doc:0")
    in_code = False
    code_lines: list[str] = []
    for line in text.splitlines():
        if line.strip().startswith("```"):
            if in_code:
                section.add(Block(kind="code", text="\n".join(code_lines)))
                code_lines = []
            in_code = not in_code
            continue
        if in_code:
            code_lines.append(line)
            continue
        heading = HEADING_RE.match(line)
        if heading:
            section.add(Block(kind="heading", text=heading.group(2).strip(),
                              level=len(heading.group(1))))
            continue
        item = LIST_RE.match(line)
        if item:
            indent = len(item.group(1)) // 2
            section.add(Block(kind="list_item", text=item.group(3).strip(), level=indent))
            continue
        if not line.strip():
            continue
        section.add(Block(kind="text", text=line))
    if code_lines:
        section.add(Block(kind="code", text="\n".join(code_lines)))

    meta = {"engine": "builtin", "headings": sum(1 for b in section.blocks if b.kind == "heading")}
    return Document(source=str(path), kind="markdown", sections=[section], meta=meta)
