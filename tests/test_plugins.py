"""插件管理：体积口径、ffmpeg 安装后的清理、未知插件的中文提示。"""

from __future__ import annotations

from pathlib import Path

import pytest

from xdoc.errors import PluginError
from xdoc.plugins import PLUGINS, PluginManager, _collect_ffmpeg_tools


def _fake_ffmpeg_tree(directory: Path) -> None:
    """造一个和官方压缩包一样的目录结构。"""
    root = directory / "ffmpeg-9.1-essentials_build"
    (root / "bin").mkdir(parents=True)
    (root / "doc").mkdir()
    for name in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe"):
        (root / "bin" / name).write_bytes(b"x" * 1024)
    (root / "doc" / "ffmpeg.html").write_text("doc", encoding="utf-8")


def test_ffmpeg_install_keeps_only_two_binaries(tmp_path):
    _fake_ffmpeg_tree(tmp_path)
    _collect_ffmpeg_tools(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ffmpeg.exe", "ffprobe.exe"]
    assert not (tmp_path / "ffmpeg-9.1-essentials_build").exists()


def test_plugin_list_reports_real_size(tmp_path):
    manager = PluginManager(tmp_path)
    for spec in PLUGINS.values():
        directory = manager.plugin_dir(spec.name)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "blob.bin").write_bytes(b"0" * (2 * 1024 * 1024))
        manager.marker(spec.name).write_text("{}", encoding="utf-8")

    items = {item["name"]: item for item in manager.list()}
    assert items["ocr"]["installed"] is True
    assert items["ocr"]["size_mb"] > 0
    assert items["ocr"]["approx_size"]


def test_unknown_plugin_error_lists_available_plugins(tmp_path):
    manager = PluginManager(tmp_path)
    with pytest.raises(PluginError) as excinfo:
        manager.install("nope")
    message = str(excinfo.value)
    assert "未知插件: nope" in message
    assert "ocr" in message

    with pytest.raises(PluginError) as excinfo:
        manager.uninstall("nope")
    assert "ocr" in str(excinfo.value)
