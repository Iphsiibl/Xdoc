"""音频 / 视频转换。

音频：有 ASR 插件就转写（带时间戳），没有就只给元数据并提示。
视频：ffmpeg 抽音轨 + 抽关键帧，音轨再交给 ASR；关键帧以图片形式交给能看图的模型。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

from ..assets import AssetStore
from ..errors import XdocError
from ..ir import Block, Document, Section
from ..options import ReadOptions
from ..plugins import PluginManager


def _timestamp(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    frac = int(round((seconds - int(seconds)) * 1000))
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}.{frac:03d}"
    return f"{m:02d}:{s:02d}.{frac:03d}"


def _wav_duration(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        return None


def _ffprobe(manager: PluginManager, path: Path) -> dict | None:
    tool = manager.ffmpeg_path("ffprobe")
    if tool is None:
        return None
    cmd = [
        str(tool), "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=120)
        return json.loads(proc.stdout.decode("utf-8", "replace") or "{}")
    except Exception:
        return None


def _extract_audio(manager: PluginManager, path: Path, out_path: Path) -> bool:
    ffmpeg = manager.ffmpeg_path("ffmpeg")
    if ffmpeg is None:
        return False
    cmd = [str(ffmpeg), "-y", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000",
            "-c:a", "pcm_s16le", str(out_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=1800)
        return proc.returncode == 0 and out_path.exists()
    except Exception:
        return False


def _asr_candidates(manager: PluginManager, options: ReadOptions) -> list[tuple[str, str]]:
    """按用户偏好挑可用的 ASR 插件：返回 [(插件名, 后端)]，已过滤掉没装的。"""
    want = (options.asr or "auto").strip().lower()
    if want == "off":
        return []
    if want in ("zh", "funasr", "asr-zh"):
        order = [("asr-zh", "funasr"), ("asr", "faster-whisper")]
    elif want in ("whisper", "faster-whisper", "asr"):
        order = [("asr", "faster-whisper"), ("asr-zh", "funasr")]
    else:  # auto
        order = [("asr", "faster-whisper"), ("asr-zh", "funasr")]
    return [(name, backend) for name, backend in order if manager.is_installed(name)]


def _run_asr(manager: PluginManager, plugin: str, backend: str, audio: Path,
             options: ReadOptions) -> dict:
    payload = {
        "audio": str(audio),
        "model": options.asr_model or "small",
        "language": options.asr_language,
        "backend": backend,
    }
    result = manager.run_worker(plugin, payload)
    if result.get("error"):
        raise XdocError(f"ASR 失败: {result['error']}")
    return result


def _transcribe(manager: PluginManager, audio: Path, options: ReadOptions) -> list[dict]:
    candidates = _asr_candidates(manager, options)
    if not candidates:
        return []
    plugin, backend = candidates[0]
    result = _run_asr(manager, plugin, backend, audio, options)

    language = str(result.get("language") or "")
    want = (options.asr or "auto").strip().lower()
    if want == "auto" and language.startswith("zh"):
        # 自动模式下检测到中文：如果装了中文引擎，再用它转写一遍（中文精度更高）
        zh = next((c for c in candidates if c[0] == "asr-zh"), None)
        if zh and plugin != "asr-zh":
            result = _run_asr(manager, "asr-zh", "funasr", audio, options)
    return result.get("segments") or []


def _segments_to_blocks(segments: list[dict]) -> list[Block]:
    blocks: list[Block] = []
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        start = float(seg.get("start", 0))
        end = float(seg.get("end", start))
        blocks.append(Block(
            kind="text",
            text=f"[{_timestamp(start)}] {text}",
            meta={"start": start, "end": end},
        ))
    return blocks


def convert_audio(path: Path, options: ReadOptions, assets: AssetStore) -> Document:
    manager = PluginManager(Path(options.plugin_dir) if options.plugin_dir else None)
    section = Section(label=path.name, anchor="time:00:00:00")
    meta: dict = {"engine": "builtin"}

    duration = _wav_duration(path)
    if duration is None:
        probe = _ffprobe(manager, path)
        if probe:
            fmt = probe.get("format", {})
            duration = float(fmt.get("duration") or 0) or None
            meta["container"] = fmt.get("format_name")
            streams = probe.get("streams", [])
            if streams:
                meta["codec"] = streams[0].get("codec_name")
                meta["sample_rate"] = streams[0].get("sample_rate")
                meta["channels"] = streams[0].get("channels")
    if duration:
        meta["duration"] = round(duration, 2)

    audio_for_asr = path
    tmpdir = None
    if path.suffix.lower() != ".wav":
        tmpdir = Path(tempfile.mkdtemp(prefix="xdoc-audio-"))
        target = tmpdir / "audio.wav"
        if _extract_audio(manager, path, target):
            audio_for_asr = target
        else:
            audio_for_asr = path

    segments = _transcribe(manager, audio_for_asr, options)
    if segments:
        section.extend(_segments_to_blocks(segments))
        meta["segments"] = len(segments)
        meta["asr"] = "installed plugin"
    else:
        section.add(Block(kind="note", text="（未安装 ASR 插件，只返回元数据；执行 xdoc plugin add asr 可开启转写）"))

    if tmpdir:
        shutil.rmtree(tmpdir, ignore_errors=True)

    meta.setdefault("duration", None)
    return Document(source=str(path), kind="audio", sections=[section], meta=meta)


def _extract_frames(manager: PluginManager, path: Path, assets: AssetStore, duration: float | None,
                    section: Section, max_frames: int = 12) -> int:
    ffmpeg = manager.ffmpeg_path("ffmpeg")
    if ffmpeg is None or not duration:
        return 0
    step = max(1.0, duration / max_frames)
    count = 0
    for index in range(max_frames):
        timestamp = index * step
        if timestamp >= duration:
            break
        filename = f"frame-{_timestamp(timestamp).replace(':', '-')}.png"
        target = assets.root / assets._rel_dir / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        cmd = [str(ffmpeg), "-y", "-ss", f"{timestamp:.2f}", "-i", str(path),
               "-frames:v", "1", str(target)]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=120)
        except Exception:
            continue
        if proc.returncode == 0 and target.exists():
            rel = assets._rel(f"{assets._rel_dir}/{filename}")
            section.add(Block(kind="image", src=rel, text=f"{_timestamp(timestamp)} 关键帧",
                              meta={"timestamp": timestamp}))
            count += 1
    return count


def convert_video(path: Path, options: ReadOptions, assets: AssetStore) -> Document:
    manager = PluginManager(Path(options.plugin_dir) if options.plugin_dir else None)
    assets.bind(path)
    section = Section(label=path.name, anchor="time:00:00:00")
    meta: dict = {"engine": "builtin"}

    probe = _ffprobe(manager, path)
    duration = None
    if probe:
        fmt = probe.get("format", {})
        duration = float(fmt.get("duration") or 0) or None
        meta["container"] = fmt.get("format_name")
        video_streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "video"]
        audio_streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "audio"]
        if video_streams:
            vs = video_streams[0]
            meta["resolution"] = f"{vs.get('width')}x{vs.get('height')}"
            meta["fps"] = vs.get("avg_frame_rate")
        if audio_streams:
            meta["has_audio"] = True
    if duration:
        meta["duration"] = round(duration, 2)

    tmpdir = Path(tempfile.mkdtemp(prefix="xdoc-video-"))
    try:
        audio_path = tmpdir / "audio.wav"
        if _extract_audio(manager, path, audio_path):
            segments = _transcribe(manager, audio_path, options)
            if segments:
                for block in _segments_to_blocks(segments):
                    section.add(block)
                meta["segments"] = len(segments)

        frames = _extract_frames(manager, path, assets, duration, section)
        if frames:
            meta["frames"] = frames
        elif manager.ffmpeg_path("ffmpeg") is None:
            section.add(Block(kind="note", text="（未安装 media 插件，无法抽取关键帧；执行 xdoc plugin add media）"))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    if not section.blocks:
        section.add(Block(kind="note", text="（没有可用内容：缺 media/asr 插件）"))

    return Document(source=str(path), kind="video", sections=[section], meta=meta)
