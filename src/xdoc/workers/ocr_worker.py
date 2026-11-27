"""OCR worker（运行在 ocr 插件自己的 venv 里）。

输入 JSON（stdin）：
    {"images": ["path/to/page1.png", ...], "lang": "ch"}
输出 JSON（stdout）：
    {"results": [{"index": 0, "text": "...", "lines": [{"text": "...", "score": 0.99, "box": [...]}]}]}

引擎：
  * 首选 `rapidocr`（PP-OCRv6 ONNX 模型，英文能正确输出空格）；
  * 回落 `rapidocr_onnxruntime`（旧版 PP-OCRv4，仅在没有新包时使用）。
"""
from __future__ import annotations

import json
import sys


def _load_engine():
    try:
        from rapidocr import RapidOCR  # type: ignore

        return "v3", RapidOCR()
    except ImportError:
        pass
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore

        return "legacy", RapidOCR()
    except ImportError as exc:
        raise RuntimeError(f"缺少 OCR 引擎（安装 rapidocr 或 rapidocr-onnxruntime）: {exc}")


def _lines_from_output(api: str, outcome) -> list[dict]:
    lines: list[dict] = []
    if outcome is None:
        return lines

    if api == "v3":
        txts = list(getattr(outcome, "txts", None) or ())
        scores = list(getattr(outcome, "scores", None) or ())
        boxes = getattr(outcome, "boxes", None)
        for index, text in enumerate(txts):
            score = float(scores[index]) if index < len(scores) else 0.0
            box = None
            if boxes is not None:
                try:
                    box = [[float(p[0]), float(p[1])] for p in boxes[index]]
                except (IndexError, TypeError, ValueError):
                    box = None
            lines.append({"text": str(text), "score": score, "box": box})
        return lines

    for item in outcome:
        try:
            box, text, score = item[0], item[1], item[2]
        except (IndexError, TypeError):
            continue
        lines.append({"text": str(text), "score": float(score), "box": box})
    return lines


def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    images = payload.get("images") or []
    if not images:
        print(json.dumps({"results": []}, ensure_ascii=False))
        return 0

    try:
        api, engine = _load_engine()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1

    results = []
    for index, path in enumerate(images):
        try:
            outcome = engine(path)
            if api == "legacy":
                outcome = outcome[0]
        except Exception as exc:  # pragma: no cover
            results.append({"index": index, "text": "", "error": str(exc)})
            continue
        lines = _lines_from_output(api, outcome)
        text = "\n".join(line["text"] for line in lines)
        avg = round(sum(line["score"] for line in lines) / len(lines), 4) if lines else 0.0
        results.append({"index": index, "text": text, "lines": lines, "avg_score": avg})
    print(json.dumps({"results": results}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
