"""解析缓存：同一份文件不重复解析。

为什么要它：
- Agent 的典型动作是「先看结构 → 再定点读页」，同一份 PDF 会被反复解析；
- 64 页中文 PDF 解析一次要 6 秒以上，每次续读都从头再来一遍，非常难受。

缓存键 = 文件内容 sha256 + 影响解析结果的选项 + 工具版本 + 已装插件清单。
内容变了键就变，旧条目自动作废，所以缓存目录可以放心攒，不会读到过期内容。
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable

from . import __version__
from .ir import Block, Document, Section

CACHE_VERSION = 1
MAX_ENTRY_BYTES = 64 * 1024 * 1024


def cache_root() -> Path:
    """缓存根目录（可用 XDOC_CACHE_DIR 覆盖）。"""
    override = os.environ.get("XDOC_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local" / "share" / "xdoc" / "cache"


def cache_key(*, sha256: str, kind: str, options: Any, plugins: Iterable[str]) -> str:
    """算出缓存键：内容 + 解析相关选项 + 工具版本 + 插件清单。"""
    payload = {
        "v": CACHE_VERSION,
        "xdoc": __version__,
        "sha": sha256,
        "kind": kind,
        "tables": getattr(options, "tables", None),
        "ocr": getattr(options, "ocr", None),
        "asr": getattr(options, "asr", None),
        "asr_model": getattr(options, "asr_model", None),
        # 转写语言会改变结果，必须进键；只对音视频有意义，其它类型的键保持不变
        "asr_language": (getattr(options, "asr_language", None)
                         if kind in ("audio", "video") else None),
        # 有没有标点模型也会改变转写文本（有标点的版本多一整套标点）
        "asr_punc": (getattr(options, "asr_punc", "on")
                     if kind in ("audio", "video") else None),
        "images": getattr(options, "images", None),
        "assets": str(getattr(options, "assets_dir", None) or ""),
        "plugins": sorted(plugins),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def document_to_dict(doc: Document) -> dict[str, Any]:
    """Document → 可 JSON 化的 dict（保持与 IR 一一对应）。"""
    return {
        "source": doc.source,
        "kind": doc.kind,
        "meta": doc.meta,
        "sections": [
            {
                "label": section.label,
                "anchor": section.anchor,
                "file": section.file,
                "blocks": [
                    {
                        "kind": block.kind,
                        "text": block.text,
                        "level": block.level,
                        "rows": block.rows,
                        "header": block.header,
                        "lang": block.lang,
                        "src": block.src,
                        "meta": block.meta,
                    }
                    for block in section.blocks
                ],
            }
            for section in doc.sections
        ],
    }


def document_from_dict(data: dict[str, Any]) -> Document:
    """dict → Document（document_to_dict 的逆操作）。"""
    sections: list[Section] = []
    for raw in data.get("sections") or []:
        blocks = [
            Block(
                kind=raw_block.get("kind", "text"),
                text=raw_block.get("text", ""),
                level=raw_block.get("level", 0),
                rows=[list(row) for row in (raw_block.get("rows") or [])],
                header=bool(raw_block.get("header", False)),
                lang=raw_block.get("lang"),
                src=raw_block.get("src"),
                meta=dict(raw_block.get("meta") or {}),
            )
            for raw_block in (raw.get("blocks") or [])
        ]
        sections.append(
            Section(
                label=raw.get("label", ""),
                anchor=raw.get("anchor", ""),
                blocks=blocks,
                file=raw.get("file"),
            )
        )
    return Document(
        source=data.get("source", ""),
        kind=data.get("kind", ""),
        sections=sections,
        meta=dict(data.get("meta") or {}),
    )


def entry_path(root: Path, key: str) -> Path:
    return Path(root) / key[:2] / f"{key}.json"


def _assets_intact(doc: Document) -> bool:
    """缓存里的图片路径必须还在，否则宁可当作没命中。"""
    assets_root = doc.meta.get("assets_root")
    if not assets_root:
        return True
    for section in doc.sections:
        for block in section.blocks:
            src = block.src
            if block.kind == "image" and src and not Path(assets_root, src).exists():
                return False
    return True


def load(root: Path, key: str) -> Document | None:
    """命中返回 Document，未命中或条目损坏返回 None。"""
    path = entry_path(root, key)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    try:
        doc = document_from_dict(data)
    except (TypeError, ValueError, AttributeError):
        return None
    if not _assets_intact(doc):
        return None
    return doc


def store(root: Path, key: str, doc: Document) -> bool:
    """写入缓存条目，成功返回 True。"""
    try:
        payload = json.dumps(document_to_dict(doc), ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return False
    if len(payload.encode("utf-8")) > MAX_ENTRY_BYTES:
        return False
    path = entry_path(root, key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)
    except OSError:
        return False
    return True


def clear(root: Path | None = None) -> int:
    """清空缓存，返回被删除的条目数。

    只删缓存条目本身，不整目录删——万一 XDOC_CACHE_DIR 指到别处，
    也不该把别人的目录连根拔掉。
    """
    root = Path(root) if root else cache_root()
    if not root.exists():
        return 0
    count = 0
    for path in list(root.rglob("*.json")):
        try:
            path.unlink()
            count += 1
        except OSError:
            pass
    return count


def usage(root: Path | None = None) -> tuple[int, int]:
    """返回 (条目数, 占用字节数)。"""
    root = Path(root) if root else cache_root()
    if not root.exists():
        return 0, 0
    count = 0
    size = 0
    for path in root.rglob("*.json"):
        count += 1
        try:
            size += path.stat().st_size
        except OSError:
            pass
    return count, size
