"""xdoc demo：用内置示例跑一遍，让人半分钟内看到 xdoc 到底能干什么。

示例文件打包在 wheel 里（src/xdoc/examples/），装完 xdoc 就有东西可试，
不用先去别处找样本。
"""

from __future__ import annotations

import shutil
import tempfile
from importlib import resources
from pathlib import Path

from .api import read_with_meta
from .options import ReadOptions, SearchSpec


def example_dir() -> Path:
    """内置示例所在目录。"""
    return Path(str(resources.files("xdoc"))) / "examples"


def example_paths() -> list[Path]:
    """内置示例文件列表。"""
    root = example_dir()
    if not root.exists():  # pragma: no cover - 打包异常时的兜底
        return []
    return [path for path in sorted(root.iterdir()) if path.is_file()]


def _read(path: Path, **kwargs) -> str:
    options = ReadOptions(format="markdown", **kwargs)
    text, _doc = read_with_meta(path, options)
    return text


def run_demo(quiet: bool = False) -> str:
    """跑一遍内置示例，返回要打印给用户的文本。"""
    examples = example_paths()
    if not examples:  # pragma: no cover - 打包异常时的兜底
        return "内置示例缺失（安装可能不完整），请重装：uv tool install --force xdoc-tools"

    # 复制一份到临时目录：用户可以照着改，改完再读，比只读不写更好懂。
    workdir = Path(tempfile.mkdtemp(prefix="xdoc-demo-"))
    for path in examples:
        try:
            shutil.copy2(path, workdir / path.name)
        except OSError:  # pragma: no cover - 复制失败不影响演示
            pass

    out: list[str] = []
    out.append("xdoc demo —— 用内置示例跑一遍（不需要装任何插件）")
    out.append(f"示例已复制到: {workdir}")
    out.append("")

    markdown = next((p for p in examples if p.suffix.lower() == ".md"), None)
    pdf = next((p for p in examples if p.suffix.lower() == ".pdf"), None)

    step = 0
    total = 3
    if markdown is not None:
        step += 1
        out.append(f"[{step}/{total}] 读取示例 Markdown（xdoc read）")
        out.append(_read(markdown))
        out.append("")

    if pdf is not None:
        step += 1
        out.append(f"[{step}/{total}] 读取示例 PDF（xdoc read）")
        out.append(_read(pdf))
        out.append("")

    if markdown is not None:
        step += 1
        out.append(f"[{step}/{total}] 同一份文件的另两种看法：结构视图 + 检索")
        out.append("· 结构视图（xdoc read --outline）：")
        out.append(_read(markdown, outline=True).rstrip())
        out.append("· 检索（xdoc grep \"锚点\"）：")
        out.append(_read(markdown, search=SearchSpec(pattern="锚点", limit=3)).rstrip())
        out.append("")

    out.append("接下来：")
    out.append("  xdoc read <你的文件>    读自己的文件（PDF/DOCX/图片/音频/视频…）")
    out.append("  xdoc setup              体检 + 打印接上 Agent 的方法（只读，不改你的文件）")
    out.append("  xdoc plugin add ocr     读扫描件与图片（可选，约 280MB，装完即可离线用）")
    return "\n".join(out)
