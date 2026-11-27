"""PDF 转换：文本层 + 表格还原 + 标题层级识别 + 图片提取。

原则：忠实优先。文本按原始行保留，表格还原为 Markdown 表格，
无文本层的页面标记出来（交给 OCR 插件补），不做任何摘要。

性能要点（实测于本机 CPU，Ryzen 7 5875U，无 GPU）：
  * `page.get_text("dict")` 一次即可还原纯文本，不要再调 `get_text("text")`（省 ~1/3 时间）。
  * `page.find_tables()` 默认会跑 ONNX 版面模型：64 页 37s；显式 `use_layout=False`
    只要 12s，而且检出的表格更多（9 vs 6）→ 一律关掉版面模型。
  * 表格识别只在"页面上确实有画线"时才做：无框线表格本来就识别不出来，
    画线统计是几乎零成本的精确门控（实测召回 100%）。
"""

from __future__ import annotations

import collections
import re
import statistics
from pathlib import Path

from ..assets import AssetStore
from ..errors import XdocError
from ..ir import Block, Document, Section
from ..options import ReadOptions

_WORD = re.compile(r"[0-9a-z\u4e00-\u9fff]+")


def _cell_text(cell) -> str:
    """表格单元格：把换行压成空格。

    PDF 表格单元格里常常有多行文字；直接输出会破坏 Markdown 表格的列对齐
    （`|` 分隔的行数和列数对不上）。
    """
    return " ".join((cell or "").split())


def _span_size(span: dict) -> float:
    return float(span.get("size") or 0)


def _body_size(page_dict: dict) -> float:
    sizes: list[tuple[float, int]] = []
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                txt = span.get("text", "")
                if txt.strip():
                    sizes.append((_span_size(span), len(txt)))
    if not sizes:
        return 0.0
    weighted: list[float] = []
    for size, count in sizes:
        weighted.extend([size] * count)
    return statistics.median(weighted)


def _heading_level(size: float, body: float) -> int:
    if not body or size < body * 1.15:
        return 0
    if size >= body * 1.9:
        return 1
    if size >= body * 1.45:
        return 2
    return 3


def _block_lines(block: dict) -> list[str]:
    lines: list[str] = []
    for line in block.get("lines", []):
        text = "".join(span.get("text", "") for span in line.get("spans", []))
        lines.append(text.rstrip())
    return lines


def _page_plain_text(page_dict: dict) -> str:
    """从 get_text("dict") 的结果还原纯文本（省一次 get_text 调用）。"""
    parts: list[str] = []
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = "".join(span.get("text", "") for span in line.get("spans", []))
            if text.strip():
                parts.append(text.rstrip())
    return "\n".join(parts)


def _ruling_stats(page) -> tuple[int, int]:
    """统计页面上的水平线/垂直线数量（表格边框）。

    用于"这一页有没有可能存在表格"的精确门控：lines_strict 策略要求真实画线，
    没有画线的页面跑 find_tables 也不会有结果，跳过即可。
    """
    horizontal = vertical = 0
    try:
        drawings = page.get_cdrawings()
    except Exception:
        return 0, 0
    for drawing in drawings:
        for item in drawing.get("items", ()) or ():
            kind = item[0]
            if kind == "l":
                p1, p2 = item[1], item[2]
                x1, y1 = getattr(p1, "x", None), getattr(p1, "y", None)
                x2, y2 = getattr(p2, "x", None), getattr(p2, "y", None)
                if x1 is None:
                    x1, y1 = p1[0], p1[1]
                    x2, y2 = p2[0], p2[1]
                dx, dy = abs(x1 - x2), abs(y1 - y2)
                if dy <= 1.5 and dx >= 12:
                    horizontal += 1
                elif dx <= 1.5 and dy >= 6:
                    vertical += 1
            elif kind == "re":
                rect = item[1]
                try:
                    width = abs(rect.x1 - rect.x0)
                    height = abs(rect.y1 - rect.y0)
                except AttributeError:
                    values = [v for v in rect if isinstance(v, (int, float))]
                    if len(values) != 4:
                        continue
                    width, height = abs(values[2] - values[0]), abs(values[3] - values[1])
                if width >= 12 and height <= 2.5:
                    horizontal += 1
                elif height >= 6 and width <= 2.5:
                    vertical += 1
    return horizontal, vertical


def _find_tables(page) -> list:
    """抽表：只跑画线策略（lines_strict），显式关闭 ONNX 版面模型。

    不用版面模型（use_layout=True）是有原因的：它虽然能认出"无框线表格"，
    但抽出来的行/列会错位合并（实测 arxiv 第 6 页的复杂度对比表会变成 2 行、
    每列把 4 个值挤在一起），比纯文本更糟；strategy="text" 更会把整页切碎。
    所以这里只还原"有画线"的表格——画线本身就是可靠的结构信息，
    没有画线的表格保留完整文字（词级保留率仍是 1.0）。
    """
    try:
        found = page.find_tables(use_layout=False)
    except TypeError:  # 老版本 pymupdf 没有 use_layout 参数
        try:
            found = page.find_tables()
        except Exception:
            return []
    except Exception:
        return []
    return list(getattr(found, "tables", []) or [])


def _table_blocks(page, options: ReadOptions) -> tuple[list[Block], list[tuple[tuple, str]]]:
    """返回 (表格块, [(bbox, 表格文本)])。"""
    blocks: list[Block] = []
    boxes: list[tuple[tuple, str]] = []
    for table in _find_tables(page):
        try:
            data = table.extract()
        except Exception:
            continue
        if not data:
            continue
        rows = [[_cell_text(cell) for cell in row] for row in data]
        rows = [r for r in rows if any(c for c in r)]
        if not rows:
            continue
        blocks.append(Block(kind="table", rows=rows, header=True,
                            meta={"bbox": list(table.bbox) if table.bbox else None}))
        if table.bbox:
            flat = "".join("".join(row) for row in rows)
            boxes.append((tuple(table.bbox), flat))
    return blocks, boxes


def _text_represented(block_text: str, table_text: str, tolerance: float = 0.05) -> bool:
    """判断文本块的内容是否已经被表格单元格完整表达。

    按"词"做多重集比较（忽略顺序与空白）：如果块里的词几乎都能在表格文本里找到，
    说明表格已经包含这段内容，可以丢掉原始文本块（避免重复）；
    如果缺了一部分（表格抽取时丢了字，或表格 bbox 误吞了正文），
    就保留原始文本块，宁可重复也不丢字。
    """
    words = _WORD.findall(block_text.lower())
    if not words:
        return True
    pool = collections.Counter(_WORD.findall(table_text.lower()))
    missing = 0
    for word in words:
        if pool[word] > 0:
            pool[word] -= 1
        else:
            missing += 1
    return missing / len(words) <= tolerance


def _covered_ratio(bbox, boxes: list[tuple]) -> float:
    """文本块被表格 bbox 覆盖的比例（0~1）。

    只有覆盖比例够高才丢掉原始文本块（表格里已经有一份），
    避免表格 bbox 画得偏大时把整段正文一起吞掉。
    """
    if not bbox or not boxes:
        return 0.0
    x0, y0, x1, y1 = bbox
    area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    if area <= 0:
        return 0.0
    covered = 0.0
    for bx0, by0, bx1, by1 in boxes:
        ix0, iy0 = max(x0, bx0), max(y0, by0)
        ix1, iy1 = min(x1, bx1), min(y1, by1)
        if ix1 > ix0 and iy1 > iy0:
            covered += (ix1 - ix0) * (iy1 - iy0)
    return min(1.0, covered / area)


def convert(path: Path, options: ReadOptions, assets: AssetStore) -> Document:
    try:
        import pymupdf
    except ImportError as exc:  # pragma: no cover
        raise XdocError("缺少 pymupdf，请先安装 xdoc 的基础依赖") from exc

    try:
        doc = pymupdf.open(path)
    except Exception as exc:
        raise XdocError(f"无法打开 PDF: {exc}") from exc

    needs_ocr: list[int] = []
    image_count = 0
    table_count = 0
    sections: list[Section] = []
    mode = getattr(options, "tables", "auto")
    if mode not in ("off", "auto", "on"):
        mode = "auto"

    for page_index, page in enumerate(doc):
        page_number = page_index + 1
        section = Section(label=f"page {page_number}", anchor=f"page:{page_number}")
        page_dict = page.get_text("dict")
        body = _body_size(page_dict)

        table_blocks: list[Block] = []
        table_boxes: list[tuple[tuple, str]] = []
        if mode != "off":
            horizontal, vertical = _ruling_stats(page)
            if mode == "on" or horizontal or vertical:
                table_blocks, table_boxes = _table_blocks(page, options)
                table_count += len(table_blocks)

        items: list[tuple[float, str, object]] = []
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            bbox = block.get("bbox")
            text = "\n".join(_block_lines(block)).strip("\n")
            if not text.strip():
                continue
            if bbox:
                covering = [tbl_text for box, tbl_text in table_boxes
                            if _covered_ratio(bbox, [box]) >= 0.75]
                if covering and _text_represented(text, "".join(covering)):
                    continue  # 这段文字已经以表格单元格的形态输出了
            items.append((bbox[1], "text", (block, text)))

        for block in table_blocks:
            bbox = block.meta.get("bbox")
            top = float(bbox[1]) if bbox else 0.0
            items.append((top, "table", block))

        items.sort(key=lambda item: item[0])

        for _, kind, payload in items:
            if kind == "table":
                section.add(payload)  # type: ignore[arg-type]
                continue
            block_dict, text = payload  # type: ignore[misc]
            size = max((_span_size(s) for line in block_dict.get("lines", [])
                         for s in line.get("spans", []) if s.get("text", "").strip()), default=0.0)
            level = _heading_level(size, body)
            if level:
                section.add(Block(kind="heading", text=text.strip(), level=level))
            else:
                section.add(Block(kind="text", text=text))

        if not _page_plain_text(page_dict).strip():
            needs_ocr.append(page_number)
            section.add(Block(kind="note", text="（本页没有文本层，需要 OCR 才能读取内容）"))

        if options.images == "refs":
            for img_index, img in enumerate(page.get_images(full=True), start=1):
                xref = img[0]
                try:
                    data = doc.extract_image(xref)
                except Exception:
                    continue
                ext = data.get("ext", "png")
                rel = assets.save(data["image"], f"p{page_number}-img{img_index}.{ext}")
                if rel:
                    section.add(Block(kind="image", src=rel, text=f"第 {page_number} 页图片 {img_index}"))
                    image_count += 1

        sections.append(section)

    meta = {
        "engine": f"pymupdf {getattr(pymupdf, '__version__', '')}".strip(),
        "pages": doc.page_count,
        "tables_mode": mode,
    }
    if table_count:
        meta["tables"] = table_count
    if needs_ocr:
        meta["needs_ocr"] = needs_ocr
        meta["ocr_hint"] = "部分页面无文本层，用 xdoc plugin add ocr 安装后重读"
    if image_count:
        meta["images_extracted"] = image_count
    doc.close()

    return Document(source=str(path), kind="pdf", sections=sections, meta=meta)
