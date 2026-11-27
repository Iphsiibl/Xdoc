"""ASR worker（运行在 asr 插件自己的 venv 里）。

输入 JSON（stdin）：
    {"audio": "path/to.wav", "model": "small", "language": "zh", "backend": "faster-whisper"}
输出 JSON（stdout）：
    {"segments": [{"start": 0.0, "end": 2.4, "text": "..."}], "language": "zh", "model": "small"}
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _MODELSCOPE_CACHE_HINT() -> str:
    return os.environ.get("MODELSCOPE_CACHE") or "(未设置 MODELSCOPE_CACHE)"


def _local_snapshot(repo_id: str) -> str | None:
    """在 modelscope 缓存里找已下载的模型快照目录。

    缓存布局：``<MODELSCOPE_CACHE>/models/<repo_id 以 -- 代替 />/snapshots/<revision>/``
    """
    cache = os.environ.get("MODELSCOPE_CACHE")
    if not cache:
        return None
    base = Path(cache) / "models" / repo_id.replace("/", "--") / "snapshots"
    if not base.is_dir():
        return None
    snaps = sorted((p for p in base.iterdir() if p.is_dir()), key=lambda p: p.name)
    return str(snaps[-1]) if snaps else None


def _transcribe_faster_whisper(audio: str, model: str, language: str | None) -> dict:
    from faster_whisper import WhisperModel

    engine = WhisperModel(model, device="cpu", compute_type="int8")
    segments, info = engine.transcribe(
        audio,
        language=language,
        vad_filter=True,
        beam_size=5,
        condition_on_previous_text=False,
    )
    out = []
    for seg in segments:
        text = (seg.text or "").strip()
        if text:
            out.append({"start": round(float(seg.start), 2), "end": round(float(seg.end), 2), "text": text})
    return {"segments": out, "language": getattr(info, "language", language), "model": model}


_PUNCT = "，。！？；、,.!?;:：…"


def _align_stamps(text: str, stamps: list) -> list[tuple[str, list | None]]:
    """把 FunASR 的 token 级时间戳对齐到字符。

    FunASR 的 timestamp 是"每个 token 一项"：中文按字、英文按词，
    且**不含标点**（实测 text 20 字 vs timestamp 19 项，差的就是句号）。
    所以这里按同样的规则切 token：CJK 逐字一个，连续 ASCII 字母/数字
    （一个单词）共用一个，标点不消耗时间戳。
    """
    pairs: list[tuple[str, list | None]] = []
    i, s, n = 0, 0, len(text)
    while i < n:
        ch = text[i]
        if ch in _PUNCT or ch.isspace():
            # 标点与空白都不是 FunASR 的 token，不消耗时间戳
            pairs.append((ch, None))
            i += 1
            continue
        if ch.isascii() and (ch.isalnum() or ch in "'-"):
            j = i
            while j < n and text[j] not in _PUNCT and text[j].isascii() and (
                text[j].isalnum() or text[j] in "'-"
            ):
                j += 1
            stamp = stamps[s] if s < len(stamps) else None
            s += 1
            for k in range(i, j):
                pairs.append((text[k], stamp))
            i = j
            continue
        stamp = stamps[s] if s < len(stamps) else None
        s += 1
        pairs.append((ch, stamp))
        i += 1
    return pairs


def _funasr_segments(item: dict) -> list[dict]:
    """FunASR 的输出有两种形态，都要还原成"带起止时间的句子"。

    1. 有 sentence_info：直接用（毫秒）。
    2. 只有 text + timestamp（token 级时间戳，毫秒）：按标点切句，
       句首 token 的时间为 start、句末 token 的时间为 end。
    """
    sentences = item.get("sentence_info") or []
    out: list[dict] = []
    for sent in sentences:
        text = (sent.get("text") or "").strip()
        if text:
            out.append({
                "start": round(float(sent.get("start", 0)) / 1000, 2),
                "end": round(float(sent.get("end", 0)) / 1000, 2),
                "text": text,
            })
    if out:
        return out

    text = (item.get("text") or "").strip()
    stamps = item.get("timestamp") or []
    if text and stamps:
        buf: list[str] = []
        seg_start: int | None = None
        seg_end: int | None = None
        for ch, stamp in _align_stamps(text, stamps):
            if stamp is not None:
                st, en = int(stamp[0]), int(stamp[1])
                seg_start = st if seg_start is None else seg_start
                seg_end = en
            buf.append(ch)
            if ch in _PUNCT:
                if seg_start is not None and seg_end is not None:
                    out.append({"start": round(seg_start / 1000, 2),
                                "end": round(seg_end / 1000, 2),
                                "text": "".join(buf).strip()})
                buf, seg_start, seg_end = [], None, None
        if buf and seg_start is not None and seg_end is not None:
            out.append({"start": round(seg_start / 1000, 2),
                        "end": round(seg_end / 1000, 2),
                        "text": "".join(buf).strip()})
        if out:
            return out

    if text:
        return [{"start": 0.0, "end": 0.0, "text": text}]
    return []


def _transcribe_funasr(audio: str, model: str, language: str | None) -> dict:
    from funasr import AutoModel

    # 关键：FunASR 的 AutoModel 传别名（"paraformer-zh"）会去 modelscope hub
    # 查仓库列表——运行期必须离线，所以优先传本地已下载的快照目录。
    asr_path = _local_snapshot("iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch")
    vad_path = _local_snapshot("iic/speech_fsmn_vad_zh-cn-16k-common-pytorch")
    punc_path = _local_snapshot("iic/punc_ct-transformer_cn-en-common-vocab471067-large")
    if not asr_path:
        raise RuntimeError(
            "本地没有 paraformer-zh 模型快照（%s），请先运行 `xdoc plugin add asr-zh`" % _MODELSCOPE_CACHE_HINT())

    engine = AutoModel(model=asr_path, vad_model=vad_path or "fsmn-vad",
                       punc_model=punc_path or "ct-punc", device="cpu",
                       disable_pbar=True, disable_log=True)
    result = engine.generate(input=audio, batch_size_s=300)
    out: list[dict] = []
    for item in (result or []):
        out.extend(_funasr_segments(item))
    return {"segments": out, "language": "zh", "model": model}


def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    audio = payload.get("audio")
    model = payload.get("model") or "small"
    language = payload.get("language")
    backend = payload.get("backend") or "faster-whisper"
    if not audio:
        print(json.dumps({"error": "缺少 audio 路径"}, ensure_ascii=False))
        return 1
    try:
        if backend == "funasr":
            result = _transcribe_funasr(audio, model, language)
        else:
            result = _transcribe_faster_whisper(audio, model, language)
    except Exception as exc:  # pragma: no cover
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
