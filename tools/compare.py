"""质量对比脚本：xdoc vs anymd，用同一批真实样本 + 同一把尺子。

尺子（可复现）：
  1. 参考文本 reference：由"最原始"的方式抽取（PDF 用 pymupdf 纯文本、DOCX 用 python-docx、
     PPTX 用 python-pptx、XLSX 用 openpyxl、HTML 用 BeautifulSoup）——它不是"标准答案"，
     但能回答"有没有把原文里的字丢掉"。
  2. 内容保留率 recall：参考文本与候选输出的 8-gram shingle 交集占比（去空白/小写）。
  3. 结构指标：表格行数、锚点数、图片数、字数、耗时。

用法：
    uv run python tools/compare.py            # 跑全部样本
    uv run python tools/compare.py --only pdf # 只跑某类
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
OUT = ROOT / "compare"

sys.path.insert(0, str(ROOT / "src"))

from xdoc.api import read_with_meta  # noqa: E402
from xdoc.options import ReadOptions  # noqa: E402

WS = re.compile(r"\s+")
NONWORD = re.compile(r"[^0-9a-z\u4e00-\u9fff\u3040-\u30ff%\.\,\:\;\-\+\(\)\[\]/\\#@&*=\"'<>]+")


def norm(text: str) -> str:
    text = text.lower()
    text = NONWORD.sub(" ", text)
    return WS.sub(" ", text).strip()


def shingles(text: str, size: int = 8) -> set[str]:
    text = norm(text)
    if len(text) < size:
        return {text} if text else set()
    return {text[i:i + size] for i in range(len(text) - size + 1)}


def recall(reference: str, candidate: str) -> float:
    ref = shingles(reference)
    if not ref:
        return 1.0 if not norm(candidate) else 0.0
    cand = shingles(candidate)
    return len(ref & cand) / len(ref)


TOKEN = re.compile(r"[0-9a-z\u4e00-\u9fff]+")


def token_recall(reference: str, candidate: str) -> float:
    """词级保留率：忽略顺序，只看"有没有字被弄丢"。

    比 8-gram 保留率更严格也更有意义：表格重排会打散 8-gram，
    但只要一个词都没丢，token_recall 就仍然是 1.0。
    """
    from collections import Counter

    ref = Counter(TOKEN.findall(reference.lower()))
    cand = Counter(TOKEN.findall(candidate.lower()))
    total = sum(ref.values())
    if not total:
        return 1.0
    return sum((ref & cand).values()) / total


# ---------- 参考文本 ----------
def ref_pdf(path: Path) -> str:
    import pymupdf

    doc = pymupdf.open(str(path))
    parts = []
    for page in doc:
        parts.append(page.get_text("text"))
    doc.close()
    return "\n".join(parts)


def ref_docx(path: Path) -> str:
    import docx

    d = docx.Document(str(path))
    parts = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            parts.append(" ".join(c.text for c in row.cells))
    return "\n".join(parts)


def ref_pptx(path: Path) -> str:
    from pptx import Presentation

    prs = Presentation(str(path))
    parts = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                parts.append(shape.text_frame.text)
            if shape.has_table:
                for row in shape.table.rows:
                    parts.append(" ".join(c.text for c in row.cells))
    return "\n".join(parts)


def _cell_text(v) -> str:
    """单元格值 → 文本。日期时间统一用 ISO 8601（和 xdoc 的输出一致），
    否则 '2014-01-01 00:00:00' 与 '2014-01-01T00:00:00' 会被误判成"丢字"。"""
    import datetime as _dt

    if v is None:
        return ""
    if isinstance(v, (_dt.datetime, _dt.date, _dt.time)):
        return v.isoformat()
    return str(v)


def ref_xlsx(path: Path) -> str:
    import openpyxl

    wb = openpyxl.load_workbook(str(path), data_only=True)
    parts = []
    for ws in wb.worksheets:
        parts.append(ws.title)
        for row in ws.iter_rows(values_only=True):
            parts.append(" ".join(_cell_text(v) for v in row))
    return "\n".join(parts)


def ref_html(path: Path) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    return soup.get_text("\n")


def ref_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def ref_audio(path: Path) -> str:
    return ""


def ref_image(path: Path) -> str:
    return ""


REF = {
    "pdf": ref_pdf,
    "docx": ref_docx,
    "pptx": ref_pptx,
    "xlsx": ref_xlsx,
    "html": ref_html,
    "md": ref_text,
    "txt": ref_text,
    "csv": ref_text,
    "wav": ref_audio,
    "flac": ref_audio,
    "mp4": ref_audio,
    "jpg": ref_image,
    "png": ref_image,
}


# ---------- 候选引擎 ----------
def run_xdoc(path: Path) -> dict:
    started = time.perf_counter()
    try:
        text, doc = read_with_meta(path, ReadOptions(format="markdown"))
        elapsed = time.perf_counter() - started
        return {
            "ok": True,
            "text": text,
            "elapsed": round(elapsed, 2),
            "chars": len(text),
            "anchors": text.count("<!-- page ") + text.count("<!-- slide ")
            + text.count("<!-- sheet: ") + text.count("<!-- t="),
            "table_rows": len([l for l in text.splitlines() if l.startswith("|")]),
            "images": text.count("![image]"),
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                "elapsed": round(time.perf_counter() - started, 2)}


def run_anymd(path: Path) -> dict:
    started = time.perf_counter()
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        return {"ok": False, "error": "npx not found", "elapsed": 0}
    # Windows 下 .cmd 需要经由 cmd /c 执行
    cmd = ["cmd", "/c", npx, "-y", "@sylphx/anymd", str(path), "--max-tokens", "2000000"]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=600, encoding="utf-8", errors="replace")
        elapsed = time.perf_counter() - started
        if proc.returncode != 0:
            return {"ok": False, "error": (proc.stderr or proc.stdout)[-500:],
                    "elapsed": round(elapsed, 2)}
        text = proc.stdout
        return {
            "ok": True,
            "text": text,
            "elapsed": round(elapsed, 2),
            "chars": len(text),
            "anchors": text.count("<!-- page ") + text.count("<!-- slide ")
            + text.count("<!-- sheet: ") + text.count("<!-- t="),
            "table_rows": len([l for l in text.splitlines() if l.startswith("|")]),
            "images": text.count("![image]"),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "elapsed": round(time.perf_counter() - started, 2)}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                "elapsed": round(time.perf_counter() - started, 2)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="只跑某类（pdf/docx/pptx/...）")
    ap.add_argument("--engine", default="both", choices=["xdoc", "anymd", "both"])
    ap.add_argument("--out", default="compare")
    args = ap.parse_args()

    out_root = ROOT / args.out
    results = []
    samples = sorted(p for p in SAMPLES.rglob("*") if p.is_file() and p.suffix.lower() != ".json")
    for path in samples:
        kind = path.suffix.lower().lstrip(".")
        if args.only and kind != args.only:
            continue
        print(f"=== {path.relative_to(ROOT)}", flush=True)
        row = {"sample": str(path.relative_to(ROOT)), "kind": kind,
               "bytes": path.stat().st_size}
        reference = ""
        if kind in REF:
            try:
                reference = REF[kind](path)
            except Exception as exc:
                row["ref_error"] = f"{type(exc).__name__}: {exc}"

        for engine in (["xdoc", "anymd"] if args.engine == "both" else [args.engine]):
            res = run_xdoc(path) if engine == "xdoc" else run_anymd(path)
            name = path.relative_to(SAMPLES).as_posix().replace("/", "__")
            target = out_root / engine / f"{name}.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            if res.get("ok"):
                target.write_text(res["text"], encoding="utf-8")
            row[engine] = {k: v for k, v in res.items() if k != "text"}
            if res.get("ok") and reference:
                row[engine]["recall"] = round(recall(reference, res["text"]), 4)
                row[engine]["token_recall"] = round(token_recall(reference, res["text"]), 4)
            print(f"    {engine:6s} ok={res.get('ok')} elapsed={res.get('elapsed')}s "
                  f"chars={res.get('chars')} recall={row[engine].get('recall')} "
                  f"token={row[engine].get('token_recall')} "
                  f"{'' if res.get('ok') else res.get('error')}", flush=True)
        results.append(row)

    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果写入 {out_root / 'results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
