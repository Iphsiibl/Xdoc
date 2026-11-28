"""读取参数与 token 预算/续读。

续读 cursor 用 base64 编码的 "section:block:charOffset"，对 Agent 来说是不透明字符串，
但我们能精确回到上次停下的位置（且坐标始终相对于完整文档，方便链式续读）。
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Callable

from .errors import XdocError
from .ir import Block, Document, Section


@dataclass
class SearchSpec:
    """一次检索的条件。

    pattern 默认按字面匹配（忽略大小写）；regex=True 时按正则。
    context 是命中行前后各带几行；limit 是最多返回多少条命中。
    """

    pattern: str
    regex: bool = False
    ignore_case: bool = True
    context: int = 0
    limit: int = 50


@dataclass
class ReadOptions:
    """一次 read 的全部可调项。"""

    format: str = "markdown"        # markdown | text | json
    max_tokens: int | None = None   # 超预算即截断并给 next_cursor
    cursor: str | None = None       # 续读位置
    pages: str | None = None        # "1-5,8"（页/幻灯片/表）
    ocr: str = "auto"               # auto | on | off | vlm
    tables: str = "auto"            # auto（版面像表格才识别，快）| on（每页都识别，慢）| off
    asr: str = "auto"               # auto | on | off
    asr_model: str | None = None    # 如 small / base / large-v3
    asr_language: str | None = None   # 语音识别语言（如 zh / en）；None = 自动识别
    images: str = "refs"            # refs | none
    front_matter: bool = True
    assets_dir: str | None = None
    plugin_dir: str | None = None
    outline: bool = False           # True = 只给结构（标题+锚点），不给正文
    use_cache: bool = True          # False = 跳过解析缓存，强制重新解析
    search: SearchSpec | None = None  # 非空 = 只返回命中的位置与片段
    on_progress: Callable[[str], None] | None = None  # 进度回调（CLI 用它写 stderr）


def notify(options: ReadOptions, message: str) -> None:
    """报一声进度：有回调就报，没有就安静干活。"""
    callback = options.on_progress
    if callback is not None:
        callback(message)


def estimate_tokens(text: str) -> int:
    """粗略 token 估算：CJK 约 1 字 1 token，ASCII 约 4 字符 1 token。"""
    if not text:
        return 0
    cjk = 0
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff" or "\u3000" <= ch <= "\u303f" or "\uff00" <= ch <= "\uffef":
            cjk += 1
    other = len(text) - cjk
    return int(cjk + other / 3.6)


def encode_cursor(section: int, block: int, offset: int = 0) -> str:
    raw = f"{section}:{block}:{offset}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[int, int, int]:
    pad = "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(cursor + pad).decode()
        parts = raw.split(":")
        return int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0
    except (binascii.Error, UnicodeDecodeError, ValueError, IndexError) as exc:
        raise XdocError(f"无效的 cursor: {cursor!r}") from exc


def _block_text(block: Block) -> str:
    if block.kind == "table":
        return "\n".join("\t".join(r) for r in block.rows)
    if block.kind == "image":
        return block.text or ""
    return block.text


def _flatten(doc: Document) -> list[tuple[int, int, Block]]:
    items: list[tuple[int, int, Block]] = []
    for si, section in enumerate(doc.sections):
        for bi, block in enumerate(section.blocks):
            items.append((si, bi, block))
    return items


def _rebuild(doc: Document, items: list[tuple[int, int, Block]]) -> Document:
    buckets: dict[int, list[Block]] = {}
    for si, _bi, block in items:
        buckets.setdefault(si, []).append(block)
    sections: list[Section] = []
    for si, section in enumerate(doc.sections):
        blocks = buckets.get(si)
        if blocks is None:
            continue
        sections.append(Section(label=section.label, anchor=section.anchor, blocks=blocks, file=section.file))
    return Document(source=doc.source, kind=doc.kind, sections=sections, meta=dict(doc.meta))


def _table_parts(block: Block) -> tuple[list[list[str]], list[list[str]]]:
    """表格拆成 (表头行, 数据行)。"""
    rows = [list(r) for r in block.rows]
    if not rows:
        return [], []
    if block.header:
        return rows[:1], rows[1:]
    return [], rows


def _slice_table(block: Block, skip_rows: int, take_rows: int | None = None) -> Block:
    """按行切片表格（表头始终保留，方便 Agent 理解列含义）。"""
    header, data = _table_parts(block)
    data = data[skip_rows:]
    if take_rows is not None:
        data = data[:take_rows]
    return _clone_block(block, rows=header + data)


def apply_budget(doc: Document, max_tokens: int | None, cursor: str | None) -> tuple[Document, str | None]:
    """按 cursor 起点切片 + 按 token 预算截断。

    返回 (新文档, next_cursor)。next_cursor 的坐标始终相对于**完整文档**，
    因此可以连续使用：read(cursor=C1) -> C2 -> read(cursor=C2)。

    cursor 的 offset 语义随块类型而变：
    - 文本块：已消费的字符数；
    - 表格块：已消费的数据行数（表头每次都会重复给出）。
    """
    items = _flatten(doc)
    start = (0, 0, 0)
    if cursor:
        start = decode_cursor(cursor)

    # 定位起点
    begin = 0
    for index, (si, bi, _block) in enumerate(items):
        if (si, bi) == (start[0], start[1]):
            begin = index
            break
    else:
        if items:
            begin = len(items)
    offset = start[2] if items else 0
    row_base = 0
    if begin < len(items) and offset:
        si, bi, block = items[begin]
        if block.kind == "text" and offset < len(block.text):
            items[begin] = (si, bi, _clone_block(block, text=block.text[offset:]))
            offset = 0
        elif block.kind == "table":
            items[begin] = (si, bi, _slice_table(block, offset))
            row_base = offset
            offset = 0
        else:
            begin += 1
            offset = 0

    if not max_tokens or max_tokens <= 0:
        return _rebuild(doc, items[begin:]), None

    kept: list[tuple[int, int, Block]] = []
    used = 0
    next_cursor: str | None = None

    for index in range(begin, len(items)):
        si, bi, block = items[index]

        if block.kind == "table":
            cost = estimate_tokens(_block_text(block))
            if used + cost <= max_tokens:
                kept.append((si, bi, block))
                used += cost
                continue
            # 表格太大：按行切，绝不整块丢掉
            _header, data = _table_parts(block)
            acc = 0
            take = 0
            for row in data:
                row_cost = estimate_tokens("\t".join(row))
                if used + acc + row_cost > max_tokens:
                    break
                acc += row_cost
                take += 1
            if take == 0:
                next_cursor = encode_cursor(si, bi, row_base)
                break
            kept.append((si, bi, _slice_table(block, 0, take)))
            used += acc
            next_cursor = encode_cursor(si, bi, row_base + take)
            break

        cost = estimate_tokens(_block_text(block))
        if used + cost <= max_tokens:
            kept.append((si, bi, block))
            used += cost
            continue
        remaining = max_tokens - used
        if remaining > 0 and not kept:
            char_budget = max(1, int(remaining * 3.6))
            text = block.text
            cut = text[:char_budget]
            kept.append((si, bi, _clone_block(block, text=cut)))
            next_cursor = encode_cursor(si, bi, char_budget)
            used = max_tokens
        else:
            next_cursor = encode_cursor(si, bi, 0)
        break

    out = _rebuild(doc, kept)
    if next_cursor:
        out.meta["truncated"] = True
        out.meta["next_cursor"] = next_cursor
    return out, next_cursor


def _clone_block(block: Block, text: str | None = None, rows: list[list[str]] | None = None) -> Block:
    return Block(
        kind=block.kind,
        text=block.text if text is None else text,
        level=block.level,
        rows=block.rows if rows is None else rows,
        header=block.header,
        lang=block.lang,
        src=block.src,
        meta=dict(block.meta),
    )
