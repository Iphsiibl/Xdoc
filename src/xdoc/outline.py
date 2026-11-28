"""outline 模式：只给结构（标题 + 锚点），不给正文。

用途：面对几百页的文档，先花一次调用看清目录，再按页定点读，比盲读全文省得多。
产出仍然是同一套 IR，所以渲染、预算、续读全都照常工作。
"""

from __future__ import annotations

from .ir import Block, Document, Section
from .render import anchor_text

MAX_SNIPPET = 120
MAX_TOC_ENTRIES = 40
TOC_SNIPPET = 60


def _snippet(section: Section) -> str:
    """没有标题时，用内容首行当提示（让人知道这一节大概讲什么）。"""
    for block in section.blocks:
        if block.kind == "text" and block.text.strip():
            line = next((ln.strip() for ln in block.text.splitlines() if ln.strip()), "")
            if line:
                return line[:MAX_SNIPPET] + ("…" if len(line) > MAX_SNIPPET else "")
        if block.kind == "table" and block.rows:
            row = " | ".join(c for c in block.rows[0] if c)
            return row[:MAX_SNIPPET] + ("…" if len(row) > MAX_SNIPPET else "")
        if block.kind == "list_item" and block.text.strip():
            return block.text.strip()[:MAX_SNIPPET]
    return ""


def section_label(section: Section) -> str:
    """一节的标题：优先用标题，其次用内容开头。"""
    for block in section.blocks:
        if block.kind == "heading" and block.text.strip():
            return block.text.strip()[:TOC_SNIPPET]
    hint = _snippet(section)
    return hint[:TOC_SNIPPET] if hint else ""


def document_title(doc: Document) -> str:
    """整份文档的标题：第一个标题块，没有就用开头第一行。

    读目录时用它给每个文件起个名字（`files` 字段里的 `title`），
    让人一眼看出「这个文件是讲什么的」。
    """
    for section in doc.sections:
        for block in section.blocks:
            if block.kind == "heading" and block.text.strip():
                return block.text.strip()[:TOC_SNIPPET]
    if doc.sections:
        return section_label(doc.sections[0])
    return ""


def build_toc(doc: Document, *, limit: int = MAX_TOC_ENTRIES) -> list[str]:
    """文档地图：每节一行（在哪 + 讲什么），先给结构，再给正文。

    面向 Agent：读完 front-matter 就知道这份文档有什么、该往哪读，
    不用先把全文吞下去再决定。节太多时只给前 limit 条，并说明还剩多少。

    一节里如果有多个标题，就每个标题各占一行（Markdown、Word 常常整篇一节，
    只写一行等于没给地图）；没有标题时用内容开头当提示。
    """
    entries: list[str] = []
    for section in doc.sections:
        where = anchor_text(section)
        if section.file:
            where = f"{section.file} {where}"
        headings = [b.text.strip() for b in section.blocks
                    if b.kind == "heading" and b.text.strip()]
        if headings:
            for heading in headings:
                entries.append(f"{where} · {heading[:TOC_SNIPPET]}")
        else:
            label = section_label(section)
            entries.append(f"{where} · {label}" if label else where)
    if len(entries) > limit:
        rest = len(entries) - limit
        entries = entries[:limit] + [f"… 还有 {rest} 节（用 pages 参数按需读）"]
    return entries


def build_outline(doc: Document) -> Document:
    """把文档压成结构视图：每个锚点只保留标题（没有标题就给首行提示）。"""
    sections: list[Section] = []
    for section in doc.sections:
        blocks = [b for b in section.blocks if b.kind == "heading"]
        if not blocks:
            hint = _snippet(section)
            if hint:
                blocks = [Block(kind="text", text=hint, meta={"outline_hint": True})]
        sections.append(
            Section(label=section.label, anchor=section.anchor, blocks=blocks, file=section.file)
        )
    out = Document(source=doc.source, kind=doc.kind, sections=sections, meta=dict(doc.meta))
    out.meta["outline"] = True
    return out
