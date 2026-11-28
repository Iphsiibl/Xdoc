"""outline 模式：只给结构（标题 + 锚点），不给正文。

用途：面对几百页的文档，先花一次调用看清目录，再按页定点读，比盲读全文省得多。
产出仍然是同一套 IR，所以渲染、预算、续读全都照常工作。
"""

from __future__ import annotations

from .ir import Block, Document, Section

MAX_SNIPPET = 120


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
