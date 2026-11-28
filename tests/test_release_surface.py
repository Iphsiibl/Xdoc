"""发布面自检：README 说的话必须和代码/元数据一致（发布前必跑）。

这是「README install section matches the real command」这条 done 标准的自动化守卫。
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from xdoc import __version__
from xdoc.plugins import PLUGINS

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
META = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
PROJECT = META["project"]


def test_readme_install_command_uses_the_real_package_name():
    name = PROJECT["name"]
    assert f"uv tool install {name}" in README, f"README 缺少真实安装命令 uv tool install {name}"


def test_readme_has_no_wrong_install_paths():
    for wrong in ("pipx install xdoc", "pip install xdoc", "conda install xdoc"):
        assert wrong not in README, f"README 出现未经支持的安装方式: {wrong}"


def test_readme_mentions_every_plugin():
    for name in PLUGINS:
        assert name in README, f"README 没写插件 {name}"


def test_readme_version_matches_package():
    assert PROJECT["version"] == __version__
    assert __version__ in README, "README 里找不到当前版本号（发布证据段落应含版本）"


def test_readme_shows_doctor_selfcheck():
    assert "xdoc doctor" in README


def test_project_metadata_is_publishable():
    assert PROJECT["license"] == "MIT"
    assert META["project"].get("license-files") == ["LICENSE"]
    assert (ROOT / "LICENSE").exists()
    assert PROJECT["requires-python"] == ">=3.11"
    assert PROJECT["readme"] == "README.md"
    # sdist 里不该塞可再生成的样本
    exclude = META["tool"]["hatch"]["build"]["targets"]["sdist"]["exclude"]
    assert "/samples" in exclude


def test_wheel_includes_worker_code():
    """worker 是插件运行的关键路径，不能被构建配置漏掉。"""
    targets = META["tool"]["hatch"]["build"]["targets"]
    assert targets["wheel"]["packages"] == ["src/xdoc"]
    for worker in ("ocr_worker.py", "asr_worker.py"):
        assert (ROOT / "src" / "xdoc" / "workers" / worker).exists()
