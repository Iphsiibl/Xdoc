"""输出格式：markdown（默认）/ text（纯文本）/ json。

三种格式都从同一份 IR 渲染，保证内容一致，只有排版不同。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .errors import XdocError
from .ir import Block, Document, Section

FORMATS = ("markdown", "text", "json")

# 锚点正文模板（不含注释包装，由 _anchor_line 统一加 `<!-- ... -->`）
_ANCHOR_STYLE = {
    "page": "page {n}",
    "slide": "slide {n}",
    "sheet": "sheet: {name}",
    "time": "t={t}",
}


_PLAIN = re.compile(r"^[^\s:#\"'\[\]{}&*!|>%@`,\\][^#]*$")


def _yaml_scalar(value: Any) -> str:
    """渲染成 YAML 标量：简单值不加引号，含特殊字符才加引号。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == "":
        return '""'
    if _PLAIN.match(text) and not text.endswith(" ") and not re.search(r":\s", text):
        return text
    return json.dumps(text, ensure_ascii=False)


def _front_matter(doc: Document) -> str:
    lines = ["---"]
    meta: dict[str, Any] = {
        "source": doc.source,
        "kind": doc.kind,
        "sections": len(doc.sections),
        "chars": doc.chars,
    }
    meta.update(doc.meta)
    for key, value in meta.items():
        if value is None:
            continue
        if isinstance(value, dict):
            # 字典用 JSON 流式写法（YAML 的 flow mapping，JSON 是它的子集）
            rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        elif isinstance(value, (list, tuple)):
            if any(isinstance(item, dict) for item in value):
                # 列表里带结构（如目录模式的 files）就用 JSON 流式写法，YAML 也能解析
                rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            else:
                rendered = "[" + ", ".join(_yaml_scalar(v) for v in value) + "]"
        else:
            rendered = _yaml_scalar(value)
        lines.append(f"{key}: {rendered}")
    lines.append("---")
    return "\n".join(lines)


def _anchor_text(section: Section) -> str:
    """锚点正文，例如 page 3 / sheet: 汇总 / t=00:00:12。"""
    kind, _, value = section.anchor.partition(":")
    template = _ANCHOR_STYLE.get(kind)
    if template is None:
        return section.anchor
    return template.format(n=value, name=value, t=value)


def _anchor_line(section: Section) -> str:
    text = _anchor_text(section)
    if section.file:
        # 目录模式：标明这一节来自哪个文件
        return f"<!-- file:{section.file} {text} -->"
    return f"<!-- {text} -->"


def _table_rows(block: Block) -> list[str]:
    rows = [list(r) for r in block.rows]
    if not rows:
        return []
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(c.replace("|", "\\|") for c in rows[0]) + " |"]
    if block.header and len(rows) > 1:
        out.append("| " + " | ".join("---" for _ in rows[0]) + " |")
        out.extend("| " + " | ".join(c.replace("|", "\\|") for c in r) + " |" for r in rows[1:])
    else:
        out.extend("| " + " | ".join(c.replace("|", "\\|") for c in r) + " |" for r in rows[1:])
    return out


def _resolve_src(src: str | None, assets_root: str | None) -> str:
    """图片路径给 Agent 必须是能直接打开的绝对路径。"""
    if not src:
        return ""
    if assets_root and not Path(src).is_absolute():
        return str(Path(assets_root) / src)
    return src


def _render_block_md(block: Block, assets_root: str | None = None) -> list[str]:
    if block.kind == "heading":
        level = max(1, min(block.level or 1, 6))
        return ["#" * level + " " + block.text]
    if block.kind == "list_item":
        indent = "  " * max(0, block.level)
        return [f"{indent}- {block.text}"]
    if block.kind == "quote":
        return ["> " + line for line in block.text.splitlines() or [""]]
    if block.kind == "code":
        fence = "```"
        return [f"{fence}{block.lang or ''}", block.text, fence]
    if block.kind == "table":
        return _table_rows(block)
    if block.kind == "image":
        alt = block.text or ""
        return [f"![{alt}]({_resolve_src(block.src, assets_root)})"]
    if block.kind == "note":
        return [f"> [!NOTE] {block.text}"]
    return block.text.splitlines() or [""]


def render_markdown(doc: Document, *, front_matter: bool = True) -> str:
    out: list[str] = []
    assets_root = doc.meta.get("assets_root")
    if front_matter:
        out.append(_front_matter(doc))
        out.append("")
    for section in doc.sections:
        out.append(_anchor_line(section))
        for block in section.blocks:
            out.extend(_render_block_md(block, assets_root))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def render_text(doc: Document) -> str:
    """纯文本：保留可追溯标记，但不用 Markdown 语法。"""
    out: list[str] = []
    assets_root = doc.meta.get("assets_root")
    for section in doc.sections:
        label = section.label
        if section.file:
            label = f"{section.file} · {label}"
        out.append(f"[{label}]")
        for block in section.blocks:
            if block.kind == "table":
                for row in block.rows:
                    out.append("\t".join(row))
            elif block.kind == "image":
                if block.text:
                    out.append(f"[图片] {block.text}")
                if block.src:
                    out.append(f"  ({_resolve_src(block.src, assets_root)})")
            elif block.kind == "code":
                out.append(block.text)
            elif block.kind == "heading":
                out.append(block.text)
            elif block.kind == "list_item":
                out.append("- " + block.text)
            elif block.kind == "quote":
                out.append(block.text)
            else:
                out.append(block.text)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def _block_to_dict(block: Block, assets_root: str | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {"kind": block.kind, "text": block.text}
    if block.level:
        data["level"] = block.level
    if block.kind == "table":
        data["rows"] = block.rows
        data["header"] = block.header
    if block.src:
        data["src"] = _resolve_src(block.src, assets_root)
    if block.lang:
        data["lang"] = block.lang
    if block.meta:
        data["meta"] = block.meta
    return data


def render_json(doc: Document) -> str:
    assets_root = doc.meta.get("assets_root")
    sections = []
    for section in doc.sections:
        item = {
            "label": section.label,
            "anchor": section.anchor,
            "blocks": [_block_to_dict(b, assets_root) for b in section.blocks],
        }
        if section.file:
            item["file"] = section.file
        sections.append(item)
    payload = {
        "source": doc.source,
        "kind": doc.kind,
        "meta": doc.meta,
        "chars": doc.chars,
        "sections": sections,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def render(doc: Document, fmt: str = "markdown", *, front_matter: bool = True) -> str:
    if fmt == "markdown":
        return render_markdown(doc, front_matter=front_matter)
    if fmt == "text":
        return render_text(doc)
    if fmt == "json":
        return render_json(doc)
    raise XdocError(f"未知输出格式: {fmt}（可用: {', '.join(FORMATS)}）")
