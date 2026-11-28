"""旧版 Office 格式（.doc/.ppt/.xls）转换。

本机装有 LibreOffice，用无头模式先转成现代格式，再走标准转换器。
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from ..assets import AssetStore
from ..errors import XdocError
from ..ir import Document
from ..options import ReadOptions

CANDIDATES = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/usr/bin/soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
]


def find_soffice() -> str | None:
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    for candidate in CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def _convert_to(path: Path, target_ext: str) -> Path:
    soffice = find_soffice()
    if soffice is None:
        raise XdocError("未找到 LibreOffice，无法转换旧版 Office 文件（可用 xdoc plugin add ... 或安装 LibreOffice）")
    outdir = Path(tempfile.mkdtemp(prefix="xdoc-legacy-"))
    profile = outdir / "profile"
    cmd = [
        soffice, "--headless", "--norestore", "--invisible",
        f"-env:UserInstallation=file:///{profile.as_posix()}",
        "--convert-to", target_ext, "--outdir", str(outdir), str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=300)
    except Exception as exc:
        raise XdocError(f"LibreOffice 转换失败: {exc}") from exc
    produced = list(outdir.glob(f"*.{target_ext.split(':')[0]}"))
    if not produced:
        detail = proc.stderr.decode("utf-8", "replace")[-400:]
        raise XdocError(f"LibreOffice 未产出文件: {detail}")
    return produced[0]


def _convert_legacy(path: Path, target: str, options: ReadOptions, assets: AssetStore) -> Document:
    from . import convert as dispatch

    converted = _convert_to(path, target)
    try:
        doc = dispatch(converted, options, assets)
    finally:
        shutil.rmtree(converted.parent, ignore_errors=True)
    doc.source = str(path)
    doc.meta["converted_via"] = "LibreOffice"
    return doc


def convert_doc(path: Path, options: ReadOptions, assets: AssetStore) -> Document:
    return _convert_legacy(path, "docx", options, assets)


def convert_ppt(path: Path, options: ReadOptions, assets: AssetStore) -> Document:
    return _convert_legacy(path, "pptx", options, assets)


def convert_xls(path: Path, options: ReadOptions, assets: AssetStore) -> Document:
    return _convert_legacy(path, "xlsx", options, assets)
