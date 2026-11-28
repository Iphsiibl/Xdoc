"""检索：在已解析的文档里按行查找，返回命中位置与原文片段。

为什么单独一层：
- Agent 读长文档的真实动作是「先定位，再定点读」，而不是把全文塞进上下文；
- 检索发生在「解析之后、渲染之前」，所以命中结果与正文共用同一套锚点、
  预算与续读逻辑——命中位置可以直接被引用（<!-- page 12 -->）；
- 检索不吃解析缓存：缓存里存的是全文，检索只是全文之上的一个视图，
  换个关键词不用重新解析文件。

行号约定：行号相对「所在 section 的正文」，从 1 开始。
section 的正文 = 该 section 各 block 的文本按顺序拼接（表格按行，图片按说明文字）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import XdocError
from .ir import Block, Document, Section
from .options import SearchSpec

__all__ = ["Match", "apply_search", "compile_pattern", "find_matches"]


@dataclass(frozen=True)
class Match:
    """一处命中。"""

    file: str | None      # 读目录时标明来自哪个文件
    anchor: str           # 命中所在 section 的锚点（如 page:12）
    label: str            # 命中所在 section 的标题
    line: int             # 行号（相对所在 section，从 1 开始）
    text: str             # 命中的那一行原文
    before: tuple[str, ...] = ()
    after: tuple[str, ...] = ()


def compile_pattern(spec: SearchSpec) -> re.Pattern[str]:
    """把检索条件编译成正则。默认按字面匹配（忽略大小写），避免正则元字符误伤。"""
    if not spec.pattern:
        raise XdocError("检索词不能为空")
    flags = re.IGNORECASE if spec.ignore_case else 0
    if spec.regex:
        try:
            return re.compile(spec.pattern, flags)
        except re.error as exc:
            raise XdocError(f"正则表达式无效: {spec.pattern!r}（{exc}）") from exc
    return re.compile(re.escape(spec.pattern), flags)


def _block_lines(block: Block) -> list[str]:
    """一个 block 拆成若干「行」。"""
    if block.kind == "table":
        return [" | ".join(row) for row in block.rows]
    if block.kind == "image":
        return [block.text] if block.text else []
    text = block.text or ""
    return text.splitlines()


def _section_lines(section: Section) -> list[str]:
    """section 的正文行：各 block 的文本按顺序拼接（块之间不补空行）。"""
    lines: list[str] = []
    for block in section.blocks:
        lines.extend(_block_lines(block))
    return lines


def find_matches(doc: Document, spec: SearchSpec) -> list[Match]:
    """找出文档里所有命中（不受 limit 限制，limit 在 apply_search 里生效）。"""
    pattern = compile_pattern(spec)
    context = max(0, int(spec.context))
    matches: list[Match] = []
    for section in doc.sections:
        lines = _section_lines(section)
        for index, line in enumerate(lines):
            if not pattern.search(line):
                continue
            before = tuple(lines[max(0, index - context):index]) if context else ()
            after = tuple(lines[index + 1:index + 1 + context]) if context else ()
            matches.append(Match(
                file=section.file,
                anchor=section.anchor,
                label=section.label,
                line=index + 1,
                text=line,
                before=before,
                after=after,
            ))
    return matches


def apply_search(doc: Document, spec: SearchSpec) -> Document:
    """把命中结果做成一份新文档。

    同一个位置（同一页/同一节）里的多处命中合成一节：锚点只出现一次，
    便于引用（<!-- page 24 --> 就是第 24 页）。每处命中一个块，
    命中的那一行就在块中间（它一定含检索词，Agent 一眼能认出来）。
    """
    matches = find_matches(doc, spec)
    limit = max(1, int(spec.limit))
    shown = matches[:limit]

    groups: dict[tuple[str | None, str], list[Match]] = {}
    for match in shown:
        groups.setdefault((match.file, match.anchor), []).append(match)

    sections: list[Section] = []
    for (file, anchor), group in groups.items():
        blocks = [
            Block(
                kind="text",
                text="\n".join([*hit.before, hit.text, *hit.after]),
                meta={"line": hit.line, "match": hit.text},
            )
            for hit in group
        ]
        lines = ",".join(str(hit.line) for hit in group)
        sections.append(Section(
            label=f"{group[0].label} · L{lines}",
            anchor=anchor,
            blocks=blocks,
            file=file,
        ))
    if not sections:
        # 一条没命中也要说清楚，别让调用方以为读失败了
        sections.append(Section(
            label="检索结果",
            anchor="search:0",
            blocks=[Block(kind="note", text=f"没有找到包含 “{spec.pattern}” 的内容")],
        ))

    meta = dict(doc.meta)
    meta["search"] = {
        "pattern": spec.pattern,
        "regex": spec.regex,
        "ignore_case": spec.ignore_case,
        "context": spec.context,
        "total": len(matches),
        "returned": len(shown),
        "truncated": len(matches) > len(shown),
    }
    return Document(source=doc.source, kind=doc.kind, sections=sections, meta=meta)
