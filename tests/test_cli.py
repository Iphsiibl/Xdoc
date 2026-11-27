"""CLI 行为：read / plugin / doctor / 错误码。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from conftest import require, sample

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(ROOT / "src")
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


def test_plugin_list():
    proc = run("plugin", "list")
    assert proc.returncode == 0, proc.stderr
    for name in ("ocr", "asr", "asr-zh", "media"):
        assert name in proc.stdout


def test_doctor_runs():
    proc = run("doctor")
    assert proc.returncode == 0, proc.stderr
    assert "pymupdf" in proc.stdout
