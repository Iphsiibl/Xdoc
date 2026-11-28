"""验收脚本：把 Q8 的验收标准逐条变成可复现的检查，并输出证据。

每条标准都对应：
  1) 判定方法（怎么测）
  2) 实测输出（真实数字）
  3) 结论（PASS / FAIL / NOT VERIFIABLE）

用法:
    uv run python tools/acceptance.py            # 全量验收
    uv run python tools/acceptance.py --runs 3   # 每个样本重复 3 次取中位数
    uv run python tools/acceptance.py --quick    # 跳过慢样本

环境:
    Windows / AMD Ryzen 7 PRO 5875U (8c16t, 无独显) / Python 3.14 (项目 venv)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from ruler import REF, recall, token_recall  # noqa: E402
from xdoc.api import read_with_meta  # noqa: E402
from xdoc.options import ReadOptions  # noqa: E402

# ---------------------------------------------------------------- 地面真值
# OCR 真值：人工看图确认（见 docs/ACCEPTANCE.md 里的图）
OCR_TRUTH = {
    "images/zh_easyocr_chinese.jpg": "西 315 愚园路 东 309 W Yuyuan Rd. E",
    "images/en_easyocr_english.png": (
        "Reduce your risk of coronavirus infection: "
        "Clean hands with soap and water or alcohol-based hand rub "
        "Cover nose and mouth when coughing and sneezing with tissue or flexed elbow "
        "Avoid close contact with anyone with cold or flu-like symptoms "
        "Thoroughly cook meat and eggs "
        "No unprotected contact with live wild or farm animals "
        "World Health Organization"
    ),
    "pdf/scanned_zh.pdf": "西 315 愚园路 东 309 W Yuyuan Rd. E",
    "pdf/scanned_en.pdf": (
        "Reduce your risk of coronavirus infection: "
        "Clean hands with soap and water or alcohol-based hand rub "
        "Cover nose and mouth when coughing and sneezing with tissue or flexed elbow "
        "Avoid close contact with anyone with cold or flu-like symptoms "
        "Thoroughly cook meat and eggs "
        "No unprotected contact with live wild or farm animals "
        "World Health Organization"
    ),
}

# ASR 真值：官方样例的原文
ASR_TRUTH = {
    "audio/zh_funasr_example.wav": "欢迎大家来体验达摩院推出的语音识别模型。",
    "audio/en_jfk.flac": (
        "And so, my fellow Americans, ask not what your country can do for you. "
        "Ask not what you can do for your country."
    ),
}

# ---------------------------------------------------------------- 基础工具
CJK = re.compile(r"[\u4e00-\u9fff]")


def levenshtein(a: list[str], b: list[str]) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(reference: str, candidate: str) -> float:
    """字错率：中文按字，英文按词。"""
    if CJK.search(reference):
        ref = list(re.sub(r"\s+", "", reference))
        cand = list(re.sub(r"\s+", "", candidate))
    else:
        ref = reference.lower().split()
        cand = candidate.lower().split()
    if not ref:
        return 0.0 if not cand else 1.0
    return levenshtein(ref, cand) / len(ref)


def multiset_prf(reference: str, candidate: str) -> tuple[float, float, float]:
    """无序的字符/词级 精确率·召回率·F1。

    OCR 的阅读顺序本来就不确定（海报上的文字位置、扫描件的排版），
    用编辑距离衡量会把"顺序不同"误判成"识别错"，所以这里按多重集比较：
    真值里的每个字/词是否都出现在候选里（反之亦然）。
    """
    if CJK.search(reference):
        ref = list(re.sub(r"\s+", "", reference))
        cand = list(re.sub(r"\s+", "", candidate))
    else:
        ref = reference.lower().split()
        cand = candidate.lower().split()
    if not ref and not cand:
        return 1.0, 1.0, 1.0
    from collections import Counter
    rc, cc = Counter(ref), Counter(cand)
    hit = sum((rc & cc).values())
    recall = hit / len(ref) if ref else 0.0
    precision = hit / len(cand) if cand else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def speech_bounds(path: Path) -> tuple[float, float] | None:
    """用能量阈值独立测量语音起止（不依赖 ASR 模型自己的输出）。"""
    ffmpeg = Path.home() / ".local" / "share" / "xdoc" / "plugins" / "media" / "ffmpeg.exe"
    tmp = Path(os.environ.get("TEMP", ".")) / f"xdoc-vad-{path.stem}.wav"
    try:
        if path.suffix.lower() != ".wav":
            subprocess.run(
                [str(ffmpeg), "-y", "-i", str(path), "-ac", "1", "-ar", "16000", str(tmp)],
                capture_output=True, timeout=120, check=True)
            source = tmp
        else:
            source = path
        with wave.open(str(source), "rb") as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            raw = wav.readframes(frames)
        samples = []
        for i in range(0, len(raw) - 1, 2):
            value = int.from_bytes(raw[i:i + 2], "little", signed=True)
            samples.append(value / 32768.0)
        if not samples:
            return None
        win = max(1, rate // 100)  # 10ms
        rms = []
        for start in range(0, len(samples) - win, win):
            chunk = samples[start:start + win]
            rms.append((sum(v * v for v in chunk) / win) ** 0.5)
        peak = max(rms) or 1.0
        thr = peak * 0.1
        voiced = [i for i, v in enumerate(rms) if v >= thr]
        if not voiced:
            return None
        return (voiced[0] * win) / rate, ((voiced[-1] + 1) * win) / rate
    except Exception:
        return None
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------- 引擎运行
def run_xdoc(path: Path, options: ReadOptions | None = None) -> dict:
    started = time.perf_counter()
    try:
        options = options or ReadOptions(format="markdown")
        # 基准要量的是「解析引擎」的耗时，不是缓存命中，所以强制不走缓存。
        options.use_cache = False
        text, doc = read_with_meta(path, options)
        return {
            "ok": True,
            "text": text,
            "doc": doc,
            "elapsed": time.perf_counter() - started,
            "chars": len(text),
            "anchors": (text.count("<!-- page ") + text.count("<!-- slide ")
                        + text.count("<!-- sheet: ") + text.count("<!-- t=")),
            "table_rows": sum(1 for line in text.splitlines() if line.startswith("|")),
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                "elapsed": time.perf_counter() - started}


def run_anymd(path: Path) -> dict:
    started = time.perf_counter()
    npx = None
    from shutil import which
    npx = which("npx") or which("npx.cmd")
    if not npx:
        return {"ok": False, "error": "npx not found", "elapsed": 0.0}
    cmd = ["cmd", "/c", npx, "-y", "@sylphx/anymd", str(path), "--max-tokens", "2000000"]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=900,
                              encoding="utf-8", errors="replace")
        text = proc.stdout
        return {
            "ok": proc.returncode == 0,
            "text": text,
            "elapsed": time.perf_counter() - started,
            "chars": len(text),
            "error": "" if proc.returncode == 0 else (proc.stderr or proc.stdout)[-300:],
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                "elapsed": time.perf_counter() - started}


def timed(fn, path: Path, runs: int) -> dict:
    """重复 runs 次，返回中位数与全部耗时（要看离散度，不看最好成绩）。"""
    times: list[float] = []
    last: dict = {}
    for _ in range(runs):
        last = fn(path)
        if not last.get("ok"):
            break
        times.append(last["elapsed"])
    if not times:
        return last
    times.sort()
    median = times[len(times) // 2]
    return {**last, "elapsed": median, "runs": len(times),
            "spread": (round(times[-1] - times[0], 2), [round(t, 2) for t in times])}


# ---------------------------------------------------------------- 检查项
def check_text_fidelity(runs: int, quick: bool) -> list[dict]:
    rows = []
    targets = []
    for sub in ("pdf", "docx", "pptx", "xlsx", "html"):
        folder = SAMPLES / sub
        if not folder.exists():
            continue
        for p in sorted(folder.iterdir()):
            if p.is_file():
                targets.append(p)
    for path in targets:
        rel = path.relative_to(SAMPLES).as_posix()
        if quick and path.stat().st_size > 3_000_000:
            continue
        ref = REF.get(path.suffix.lower().lstrip("."), lambda _p: "")(path)
        if not ref.strip():
            continue
        res = timed(run_xdoc, path, runs)
        if not res.get("ok"):
            rows.append({"sample": rel, "ok": False, "error": res.get("error")})
            continue
        row = {
            "sample": rel,
            "ok": True,
            "token_recall": round(token_recall(ref, res["text"]), 4),
            "shingle_recall": round(recall(ref, res["text"]), 4),
            "median_s": round(res["elapsed"], 2),
            "spread": res.get("spread"),
            "table_rows": res["table_rows"],
            "anchors": res["anchors"],
        }
        base = run_anymd(path)
        if base.get("ok"):
            row["anymd_token_recall"] = round(token_recall(ref, base["text"]), 4)
            row["anymd_s"] = round(base["elapsed"], 2)
        rows.append(row)
    return rows


def check_traceability() -> list[dict]:
    rows = []
    # PDF: 锚点数应等于页数
    for path in sorted((SAMPLES / "pdf").glob("*.pdf")):
        import pymupdf
        with pymupdf.open(str(path)) as doc:
            pages = doc.page_count
        res = run_xdoc(path)
        anchors = res.get("anchors", 0)
        rows.append({"sample": path.relative_to(SAMPLES).as_posix(), "kind": "pdf",
                     "expected": pages, "actual": anchors,
                     "ok": res.get("ok") and anchors == pages})
    # PPTX: 锚点数应等于幻灯片数
    for path in sorted((SAMPLES / "pptx").glob("*.pptx")):
        from pptx import Presentation
        slides = len(Presentation(str(path)).slides)
        res = run_xdoc(path)
        anchors = res.get("anchors", 0)
        rows.append({"sample": path.relative_to(SAMPLES).as_posix(), "kind": "pptx",
                     "expected": slides, "actual": anchors,
                     "ok": res.get("ok") and anchors == slides})
    # XLSX: 锚点数应等于工作表数
    for path in sorted((SAMPLES / "xlsx").glob("*.xlsx")):
        import openpyxl
        sheets = len(openpyxl.load_workbook(str(path), read_only=True).worksheets)
        res = run_xdoc(path)
        anchors = res.get("anchors", 0)
        rows.append({"sample": path.relative_to(SAMPLES).as_posix(), "kind": "xlsx",
                     "expected": sheets, "actual": anchors,
                     "ok": res.get("ok") and anchors == sheets})
    return rows


def check_ocr() -> list[dict]:
    """OCR 准确率。

    只取文档里的 text 块（OCR 出来的字），不含 section 头、图片说明和
    资产路径——那些是 xdoc 自己的元信息，不是被识别出来的文字。
    指标用无序的多重集 F1：海报/扫描件的阅读顺序本来就不确定。
    """
    rows = []
    for rel, truth in OCR_TRUTH.items():
        path = SAMPLES / rel
        if not path.exists():
            rows.append({"sample": rel, "ok": False, "error": "样本缺失"})
            continue
        res = run_xdoc(path, ReadOptions(format="json"))
        if not res.get("ok"):
            rows.append({"sample": rel, "ok": False, "error": res.get("error")})
            continue
        blocks = [b for s in res["doc"].sections for b in s.blocks if b.kind == "text"]
        hyp = " ".join(b.text for b in blocks)
        precision, recall, f1 = multiset_prf(truth, hyp)
        rows.append({"sample": rel, "ok": True,
                     "char_precision": round(precision, 4),
                     "char_recall": round(recall, 4),
                     "char_accuracy": round(f1, 4),
                     "threshold": 0.95,
                     "passed": f1 >= 0.95,
                     "output": hyp.strip()[:160]})
    return rows


def check_asr() -> list[dict]:
    rows = []
    for rel, truth in ASR_TRUTH.items():
        path = SAMPLES / rel
        if not path.exists():
            rows.append({"sample": rel, "ok": False, "error": "样本缺失"})
            continue
        options = ReadOptions(format="json", asr="zh" if rel.startswith("audio/zh") else "whisper")
        res = run_xdoc(path, options)
        if not res.get("ok"):
            rows.append({"sample": rel, "ok": False, "error": res.get("error")})
            continue
        blocks = [b for s in res["doc"].sections for b in s.blocks if b.kind == "text"]
        hyp = " ".join(b.text for b in blocks)
        hyp = re.sub(r"\[\d\d:\d\d\.\d+\]\s*", "", hyp)
        err = cer(truth, hyp)
        bounds = speech_bounds(path)
        starts = [float(b.meta.get("start", 0)) for b in blocks]
        ends = [float(b.meta.get("end", 0)) for b in blocks]
        row = {"sample": rel, "ok": True,
               "cer": round(err, 4),
               "threshold": 0.05 if rel.startswith("audio/zh") else None,
               "passed": (err <= 0.05) if rel.startswith("audio/zh") else None,
               "segments": len(blocks),
               "asr_start": round(min(starts), 2) if starts else None,
               "asr_end": round(max(ends), 2) if ends else None,
               "transcript": hyp.strip()[:200]}
        if bounds:
            row["vad_start"] = round(bounds[0], 2)
            row["vad_end"] = round(bounds[1], 2)
            if starts:
                row["start_err_s"] = round(abs(min(starts) - bounds[0]), 2)
                row["end_err_s"] = round(abs(max(ends) - bounds[1]), 2)
                row["passed_ts"] = row["start_err_s"] <= 1.0 and row["end_err_s"] <= 1.0
        rows.append(row)
    return rows


def check_offline() -> list[dict]:
    """把代理指向黑洞：任何运行期联网都会失败或超时。"""
    env = dict(os.environ)
    env.update({
        "HTTP_PROXY": "http://127.0.0.1:9",
        "HTTPS_PROXY": "http://127.0.0.1:9",
        "ALL_PROXY": "http://127.0.0.1:9",
        "http_proxy": "http://127.0.0.1:9",
        "https_proxy": "http://127.0.0.1:9",
        "NO_PROXY": "",
        "no_proxy": "",
    })
    targets = [
        ("pdf/zh_wiki_python.pdf", []),
        ("images/zh_easyocr_chinese.jpg", []),
        ("audio/zh_funasr_example.wav", ["--asr", "zh"]),
        ("audio/en_jfk.flac", ["--asr", "whisper"]),
    ]
    rows = []
    for rel, extra in targets:
        path = SAMPLES / rel
        # 必须绕过缓存：命中缓存等于没做转换，证明不了「离线也能转换」。
        cmd = [sys.executable, "-m", "xdoc", "read", str(path), "--format", "text",
               "--no-cache", *extra]
        started = time.perf_counter()
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=600, env=env,
                                  encoding="utf-8", errors="replace")
            ok = proc.returncode == 0 and len(proc.stdout.strip()) > 0
            rows.append({"sample": rel, "ok": ok,
                         "seconds": round(time.perf_counter() - started, 2),
                         "chars": len(proc.stdout),
                         "error": "" if ok else (proc.stderr or proc.stdout)[-300:]})
        except subprocess.TimeoutExpired:
            rows.append({"sample": rel, "ok": False, "error": "timeout（疑似联网等待）",
                         "seconds": 600})
    return rows


def check_formats() -> list[dict]:
    rows = []
    path = SAMPLES / "docx" / "calibre_demo.docx"
    lengths = {}
    for fmt in ("markdown", "text", "json"):
        res = run_xdoc(path, ReadOptions(format=fmt))
        lengths[fmt] = len(res.get("text", "")) if res.get("ok") else 0
    rows.append({"sample": path.relative_to(SAMPLES).as_posix(),
                 "lengths": lengths,
                 "ok": all(v > 0 for v in lengths.values())})
    return rows


def check_mcp_surface() -> list[dict]:
    """MCP 暴露的工具必须只有一个（用户明确要求：单个 MCP 工具）。"""
    script = (
        "import asyncio, json;"
        "from xdoc.mcp_server import build_server;"
        "s = build_server();"
        "tools = asyncio.run(s.list_tools());"
        "print(json.dumps([t.name for t in tools], ensure_ascii=False))"
    )
    try:
        proc = subprocess.run([sys.executable, "-c", script], capture_output=True,
                              timeout=180, encoding="utf-8", errors="replace")
        names = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else []
        return [{"tools": names, "count": len(names), "ok": len(names) == 1}]
    except Exception as exc:
        return [{"ok": False, "error": f"{type(exc).__name__}: {exc}"}]


def check_budget_continuation() -> list[dict]:
    """max_tokens + cursor 续读：不能丢内容，也不能重复卡死。"""
    from xdoc.api import read_with_meta
    path = SAMPLES / "xlsx" / "microsoft_sample.xlsx"
    full, _ = read_with_meta(path, ReadOptions(format="text"))
    rows = []
    cursor = None
    seen: list[str] = []
    for _ in range(60):
        text, doc = read_with_meta(path, ReadOptions(format="text", max_tokens=3000, cursor=cursor))
        seen.append(text)
        cursor = doc.meta.get("next_cursor")
        if not cursor:
            break
    total = sum(len(t) for t in seen)
    rows.append({"sample": path.relative_to(SAMPLES).as_posix(),
                 "chunks": len(seen),
                 "total_chars": total,
                 "full_chars": len(full),
                 "coverage": round(total / max(1, len(full)), 3),
                 "ok": len(seen) > 1 and total >= len(full) * 0.98})
    return rows


# ---------------------------------------------------------------- 主流程
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()

    payload: dict = {"runs": args.runs, "quick": args.quick}
    print("[1/7] 文本保真（xdoc vs anymd）…", flush=True)
    payload["fidelity"] = check_text_fidelity(args.runs, args.quick)
    print("[2/7] 结构可追溯…", flush=True)
    payload["traceability"] = check_traceability()
    print("[3/7] OCR…", flush=True)
    payload["ocr"] = check_ocr()
    print("[4/7] ASR…", flush=True)
    payload["asr"] = check_asr()
    print("[5/7] 运行期离线…", flush=True)
    payload["offline"] = check_offline()
    print("[6/7] 输出格式…", flush=True)
    payload["formats"] = check_formats()
    print("[7/7] MCP 工具面 & 预算续读…", flush=True)
    payload["mcp"] = check_mcp_surface()
    payload["budget"] = check_budget_continuation()

    (ROOT / "docs" / "acceptance_results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2)[:4000])
    print("\n原始数据: docs/acceptance_results.json")
    print("报告: uv run python tools/report.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
