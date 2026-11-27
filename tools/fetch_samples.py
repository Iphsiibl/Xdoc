#!/usr/bin/env python3
"""抓取公开的真实测试样本到 samples/，供 xdoc 与 anymd 等实现做同一批对比。

用法:
    python tools/fetch_samples.py            # 缺文件才下载
    python tools/fetch_samples.py --force    # 全部重下

设计约束:
- 只用标准库，避免污染项目依赖。
- 每个样本在 manifest 里登记来源 URL 与类型，方便复现与溯源。
- 下载后校验 magic bytes，避免拿到 HTML 错误页当样本。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) xdoc-sample-fetcher/0.1"

# (相对路径, 来源 URL, 期望 magic 前缀(小写 hex，可为空), 备注)
MANIFEST: list[tuple[str, str, str, str]] = [
    ("docx/calibre_demo.docx",
     "https://calibre-ebook.com/downloads/demos/demo.docx",
     "504b0304", "Calibre 官方演示 Word（真实排版，含图片/表格/标题）"),
    ("pptx/poi_SampleShow.pptx",
     "https://raw.githubusercontent.com/apache/poi/trunk/test-data/slideshow/SampleShow.pptx",
     "504b0304", "Apache POI 官方测试 PPTX"),
    ("pptx/pythonpptx_test.pptx",
     "https://raw.githubusercontent.com/scanny/python-pptx/master/features/steps/test_files/test.pptx",
     "504b0304", "python-pptx 项目测试 PPTX"),
    ("xlsx/microsoft_sample.xlsx",
     "https://go.microsoft.com/fwlink/?LinkID=521962",
     "504b0304", "微软官方 Excel 示例（财务表）"),
    ("pdf/en_dummy.pdf",
     "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
     "25504446", "W3C 最小文本型 PDF"),
    ("pdf/en_paper_tracemonkey.pdf",
     "https://raw.githubusercontent.com/mozilla/pdf.js/master/web/compressed.tracemonkey-pldi-09.pdf",
     "25504446", "真实学术论文（多栏排版，英文）"),
    ("pdf/en_arxiv_attention.pdf",
     "https://arxiv.org/pdf/1706.03762",
     "25504446", "arXiv 真实论文（双栏，中英混排含公式）"),
    ("pdf/zh_wiki_microsoft.pdf",
     "https://zh.wikipedia.org/api/rest_v1/page/pdf/Microsoft",
     "25504446", "中文维基真实 PDF（中文文本层）"),
    ("pdf/zh_wiki_python.pdf",
     "https://zh.wikipedia.org/api/rest_v1/page/pdf/Python",
     "25504446", "中文维基真实 PDF（中文文本层）"),
    ("images/zh_easyocr_chinese.jpg",
     "https://raw.githubusercontent.com/JaidedAI/EasyOCR/master/examples/chinese.jpg",
     "ffd8ff", "EasyOCR 官方中文示例图"),
    ("images/en_easyocr_english.png",
     "https://raw.githubusercontent.com/JaidedAI/EasyOCR/master/examples/english.png",
     "89504e47", "EasyOCR 官方英文示例图"),
    ("images/en_tessdoc_eurotext.png",
     "https://raw.githubusercontent.com/tesseract-ocr/tessdoc/main/images/eurotext.png",
     "89504e47", "tessdoc 官方文本行图（OCR 基准常用）"),
    ("audio/zh_funasr_example.wav",
     "https://isv-data.oss-cn-hangzhou.aliyuncs.com/ics/MaaS/ASR/test_audio/asr_example_zh.wav",
     "52494646", "FunASR 官方中文朗读示例（真实人声）"),
    ("audio/en_jfk.flac",
     "https://raw.githubusercontent.com/openai/whisper/main/tests/jfk.flac",
     "664c6141", "whisper 官方英文示例（已知台词）"),
    ("video/big_buck_bunny.mp4",
     "https://raw.githubusercontent.com/mediaelement/mediaelement-files/master/big_buck_bunny.mp4",
     "", "真实视频样本（画面+音轨）"),
]

HTML_PAGES = [
    ("html/zh_wikipedia.html", "https://zh.wikipedia.org/wiki/Python", "中文富文本网页"),
    ("html/en_wikipedia.html", "https://en.wikipedia.org/wiki/Markdown", "英文富文本网页"),
]


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    SAMPLES.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    failures = 0

    for rel, url, magic, note in MANIFEST:
        dest = SAMPLES / rel
        if dest.exists() and not args.force:
            data = dest.read_bytes()
            got = "cached"
        else:
            try:
                data = fetch(url)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                got = "downloaded"
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                print(f"FAIL {rel}: {exc}", file=sys.stderr)
                records.append({"path": rel, "source": url, "status": "failed",
                                "error": str(exc), "note": note})
                failures += 1
                continue

        ok = (not magic) or data[: len(magic) // 2].hex().lower() == magic
        records.append({
            "path": rel,
            "source": url,
            "status": got,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "magic_ok": ok,
            "note": note,
        })
        flag = "ok " if ok else "BAD"
        print(f"{flag} {rel:42s} {len(data):>9,} B  {got}")

    for rel, url, note in HTML_PAGES:
        dest = SAMPLES / rel
        if dest.exists() and not args.force:
            got = "cached"
        else:
            try:
                data = fetch(url)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                got = "downloaded"
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                print(f"FAIL {rel}: {exc}", file=sys.stderr)
                records.append({"path": rel, "source": url, "status": "failed",
                                "error": str(exc), "note": note})
                failures += 1
                continue
        records.append({
            "path": rel,
            "source": url,
            "status": got,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "magic_ok": True,
            "note": note,
        })
        print(f"ok  {rel:42s} {len(data):>9,} B  {got}")

    manifest_path = SAMPLES / "manifest.json"
    manifest_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nmanifest -> {manifest_path}  ({len(records)} entries, {failures} failed)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
