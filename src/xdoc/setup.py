"""xdoc setup：体检 + 告诉用户怎么把 xdoc 接给 Agent。

只读：不碰用户的任何文件，只说清楚「该改哪儿、贴什么、为什么」。
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from . import __version__

# 核心依赖：(import 名, 负责的能力)
CORE_DEPENDENCIES = [
    ("pymupdf", "PDF"),
    ("docx", "DOCX"),
    ("pptx", "PPTX"),
    ("openpyxl", "XLSX"),
    ("bs4", "HTML"),
    ("markdownify", "HTML->Markdown"),
    ("mcp", "MCP 服务"),
]


def missing_dependencies() -> list[str]:
    """没装的核心依赖（缺了基础能力就不完整）。"""
    import importlib

    missing: list[str] = []
    for module, _label in CORE_DEPENDENCIES:
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(module)
    return missing


def server_command() -> tuple[str, list[str]]:
    """MCP 服务器怎么启动：优先用 PATH 上的 xdoc，否则退回当前解释器。"""
    exe = shutil.which("xdoc")
    if exe:
        return exe, ["serve"]
    return sys.executable, ["-m", "xdoc.cli", "serve"]


def claude_code_command() -> str:
    """Claude Code 里接入 xdoc 的一条命令。"""
    command, args = server_command()
    return "claude mcp add xdoc -- " + " ".join([command, *args])


def claude_desktop_config_path() -> Path:
    """Claude Desktop 的 MCP 配置文件位置。"""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "Claude" / "claude_desktop_config.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def claude_desktop_snippet() -> str:
    """要贴进 Claude Desktop 配置里的那段（只打印，不写文件）。"""
    command, args = server_command()
    payload = {"mcpServers": {"xdoc": {"command": command, "args": args}}}
    return json.dumps(payload, ensure_ascii=False, indent=2)


def setup_report() -> str:
    """生成 setup 的输出文本。"""
    from .plugins import PluginManager

    out: list[str] = []
    out.append(f"xdoc setup —— 体检 + 把 Agent 接上（只读，不会改你的任何文件）")
    out.append("")

    out.append("[环境]")
    out.append(f"  xdoc 版本: {__version__}")
    out.append(f"  python:    {sys.executable}")
    exe = shutil.which("xdoc")
    if exe:
        out.append(f"  命令可用:  {exe}")
    else:
        out.append("  命令不可用: 当前 shell 里敲 xdoc 找不到命令")
        out.append(f"              可执行文件在: {Path(sys.executable).parent}")
        out.append("              把它加进 PATH，或直接用 python -m xdoc.cli")
    missing = missing_dependencies()
    if missing:
        out.append(f"  核心依赖:  缺 {', '.join(missing)}（重装：uv tool install --force xdoc-tools）")
    else:
        out.append("  核心依赖:  齐全")

    manager = PluginManager()
    plugins = manager.list()
    installed = [item["name"] for item in plugins if item["installed"]]
    out.append(f"  插件:      已装 {', '.join(installed) if installed else '（还没装，可选）'}")

    out.append("")
    out.append("[接给 Agent（MCP）]")
    out.append("  Claude Code —— 复制这一行执行：")
    out.append(f"    {claude_code_command()}")
    out.append("")
    out.append("  Claude Desktop —— 打开这个文件：")
    config = claude_desktop_config_path()
    exists = "（已存在，贴进去即可）" if config.exists() else "（还没有这个文件，建一个也行）"
    out.append(f"    {config}  {exists}")
    out.append("  把下面这段加到它的 mcpServers 里（已有的其它服务器别删）：")
    for line in claude_desktop_snippet().splitlines():
        out.append(f"    {line}")

    out.append("")
    out.append("[下一步]")
    out.append("  1. xdoc demo             先看看 xdoc 读出来长什么样")
    out.append("  2. xdoc read <你的文件>   读自己的文件")
    out.append("  3. xdoc plugin add ocr    读扫描件与图片（可选，装完即可离线用）")
    out.append("")
    out.append("提示: xdoc setup 只打印，不写文件；改配置这一步由你自己决定。")
    return "\n".join(out)
