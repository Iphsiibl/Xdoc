"""文件类型识别：扩展名 + magic bytes（不信扩展名）。

Zip 家族（docx/pptx/xlsx/epub）都靠读 zip 内部结构判定，避免扩展名撒谎。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

EXT_KINDS = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".docm": "docx",
    ".dotx": "docx",
    ".doc": "doc_legacy",
    ".pptx": "pptx",
    ".pptm": "pptx",
    ".potx": "pptx",
    ".ppt": "ppt_legacy",
    ".xlsx": "xlsx",
    ".xlsm": "xlsx",
    ".xltx": "xlsx",
    ".xls": "xls_legacy",
    ".csv": "csv",
    ".tsv": "csv",
    ".html": "html",
    ".htm": "html",
    ".xhtml": "html",
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".log": "text",
    ".epub": "epub",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".gif": "image",
    ".bmp": "image",
    ".tif": "image",
    ".tiff": "image",
    ".wav": "audio",
    ".mp3": "audio",
    ".m4a": "audio",
    ".flac": "audio",
    ".aac": "audio",
    ".ogg": "opus",
    ".opus": "audio",
    ".mp4": "video",
    ".mov": "video",
    ".mkv": "video",
    ".avi": "video",
    ".webm": "video",
    ".m4v": "video",
}

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg", ".opus"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


def _zip_kind(path: Path) -> str | None:
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
    except (zipfile.BadZipFile, OSError):
        return None
    if "word/document.xml" in names:
        return "docx"
    if "ppt/presentation.xml" in names:
        return "pptx"
    if "xl/workbook.xml" in names:
        return "xlsx"
    if "mimetype" in names:
        try:
            with zipfile.ZipFile(path) as zf:
                if zf.read("mimetype").decode("ascii", "ignore").strip() == "application/epub+zip":
                    return "epub"
        except (KeyError, OSError, UnicodeDecodeError):
            pass
    return None


def detect_kind(path: str | Path) -> str:
    """返回 kind 标识：pdf/docx/pptx/xlsx/html/markdown/text/csv/epub/image/audio/video/... 。

    判定顺序：magic bytes → zip 内部结构 → 扩展名。
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在: {p}")

    with p.open("rb") as fh:
        head = fh.read(8)

    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"\x89PNG") or head[:2] == b"\xff\xd8" or head[:6] in (b"GIF87a", b"GIF89a"):
        return "image"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image"
    if head[:2] == b"BM":
        return "image"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "image"
    if head[:4] == b"OggS":
        return "audio"
    if head[:4] == b"fLaC":
        return "audio"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio"
    if head[:3] == b"ID3" or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio"
    if head[4:8] == b"ftyp":
        return "video"

    if head[:2] == b"PK":
        kind = _zip_kind(p)
        if kind:
            return kind

    ext = p.suffix.lower()
    kind = EXT_KINDS.get(ext)
    if kind:
        return kind

    # 兜底：按内容猜文本类
    try:
        p.read_text(encoding="utf-8")[:2048]
    except (UnicodeDecodeError, OSError):
        pass
    else:
        return "text"
    return "unknown"


def is_kind(kind: str, group: str) -> bool:
    return {
        "image": kind == "image",
        "audio": kind in ("audio", "opus"),
        "video": kind == "video",
        "office": kind in ("docx", "pptx", "xlsx", "doc_legacy", "ppt_legacy", "xls_legacy"),
    }[group]
