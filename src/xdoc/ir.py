"""中间表示（IR）：所有格式统一落到 Section -> Block 结构。

这样做的原因：渲染器（markdown/text/json）只认 IR，各格式转换器只负责产出 IR，
新增格式或新增输出格式都不需要改对方。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

BlockKind = Literal[
    "heading",
    "text",
    "list_item",
    "quote",
    "code",
    "table",
    "image",
    "note",
]


@dataclass
class Block:
    """一段内容。

    kind 为 "table" 时用 rows（rows[0] 为表头，当 header=True）。
    kind 为 "image" 时用 src（相对 assets 目录的路径）与 text（alt/说明）。
    """

    kind: BlockKind = "text"
    text: str = ""
    level: int = 0
    rows: list[list[str]] = field(default_factory=list)
    header: bool = False
    lang: str | None = None
    src: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Section:
    """带锚点的可追溯单元：PDF 一页 / PPT 一页幻灯片 / Excel 一张表 / 音频一个时间段。"""

    label: str
    anchor: str
    blocks: list[Block] = field(default_factory=list)

    def add(self, block: Block) -> None:
        self.blocks.append(block)

    def extend(self, blocks: list[Block]) -> None:
        self.blocks.extend(blocks)


@dataclass
class Document:
    """一次转换的完整结果。"""

    source: str
    kind: str
    sections: list[Section] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        """纯文本内容（不含锚点标记）。"""
        parts: list[str] = []
        for section in self.sections:
            for block in section.blocks:
                if block.kind == "table":
                    for row in block.rows:
                        parts.append("\t".join(row))
                elif block.kind == "image":
                    if block.text:
                        parts.append(block.text)
                else:
                    parts.append(block.text)
        return "\n".join(p for p in parts if p)

    @property
    def chars(self) -> int:
        return len(self.text)
