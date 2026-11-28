"""CLI 行为：read / plugin / doctor / 错误码。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import require, sample

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(ROOT / "src")
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "xdoc", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=str(ROOT),
    )


def test_read_markdown():
    path = require(sample("docx", "calibre_demo.docx"))
    proc = run("read", str(path))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("---")
    assert "kind: docx" in proc.stdout


def test_read_json_format():
    path = require(sample("docx", "calibre_demo.docx"))
    proc = run("read", str(path), "--format", "json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["kind"] == "docx"


def test_read_output_file(tmp_path):
    path = require(sample("docx", "calibre_demo.docx"))
    out = tmp_path / "out.md"
    proc = run("read", str(path), "-o", str(out))
    assert proc.returncode == 0, proc.stderr
    assert out.exists()
    assert "kind: docx" in out.read_text(encoding="utf-8")


def test_missing_file_returns_2():
    proc = run("read", "C:/definitely/not/here.docx")
    assert proc.returncode == 2
    assert "错误" in proc.stderr


def test_invalid_cursor_returns_2_without_traceback():
    """坏 cursor 必须是人话错误，不是 Python 堆栈。"""
    path = require(sample("pdf", "en_dummy.pdf"))
    proc = run("read", str(path), "--cursor", "!!!bad!!!")
    assert proc.returncode == 2
    assert "无效的 cursor" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_read_outline_flag(tmp_path):
    docx = pytest.importorskip("docx")
    path = tmp_path / "outline.docx"
    document = docx.Document()
    document.add_heading("第一章", 0)
    document.add_paragraph("正文内容很长，" * 50)
    document.save(path)

    env_extra = {"XDOC_CACHE_DIR": str(tmp_path / "cache")}
    full = run("read", str(path), env_extra=env_extra)
    brief = run("read", str(path), "--outline", env_extra=env_extra)
    assert brief.returncode == 0, brief.stderr
    assert "outline: true" in brief.stdout
    assert "第一章" in brief.stdout
    assert len(brief.stdout) < len(full.stdout)


def test_read_directory_merges_files(tmp_path):
    (tmp_path / "a.md").write_text("# 甲\n\n内容甲\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# 乙\n\n内容乙\n", encoding="utf-8")
    proc = run("read", str(tmp_path), env_extra={"XDOC_CACHE_DIR": str(tmp_path / "cache")})
    assert proc.returncode == 0, proc.stderr
    assert "kind: collection" in proc.stdout
    assert "file_count: 2" in proc.stdout
    assert "内容甲" in proc.stdout and "内容乙" in proc.stdout
    assert "file:a.md" in proc.stdout


def test_cache_commands(tmp_path):
    cache_dir = tmp_path / "cache"
    env_extra = {"XDOC_CACHE_DIR": str(cache_dir)}
    info = run("cache", "info", env_extra=env_extra)
    assert info.returncode == 0, info.stderr
    assert "缓存目录" in info.stdout
    assert str(cache_dir) in info.stdout
    clear = run("cache", "clear", env_extra=env_extra)
    assert clear.returncode == 0, clear.stderr
    assert "已清理解析缓存" in clear.stdout


def test_plugin_list():
    proc = run("plugin", "list")
    assert proc.returncode == 0, proc.stderr
    for name in ("ocr", "asr", "asr-zh", "media"):
        assert name in proc.stdout


def test_doctor_runs():
    proc = run("doctor")
    assert proc.returncode == 0, proc.stderr
    assert "pymupdf" in proc.stdout


def test_read_survives_non_utf8_console_encoding(tmp_path):
    """控制台代码页不是 UTF-8 时也不能崩。

    Windows 上 PYTHONIOENCODING=cp1252 时，旧版会直接抛 UnicodeEncodeError。
    """
    docx = pytest.importorskip("docx")
    path = tmp_path / "中文文档.docx"
    document = docx.Document()
    document.add_heading("中文标题", 0)
    document.add_paragraph("正文内容，带中文标点：你好，世界。")
    document.save(path)

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "cp1252"
    env["PYTHONPATH"] = str(ROOT / "src")
    proc = subprocess.run(
        [sys.executable, "-m", "xdoc", "read", str(path), "--format", "text"],
        capture_output=True,
        env=env,
        cwd=str(ROOT),
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    out = proc.stdout.decode("utf-8", "replace")
    assert "中文标题" in out
    assert "你好，世界。" in out
