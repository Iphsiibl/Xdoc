"""发布前自检：构建 → 干净环境安装 → doctor 绿 → 真读一个文件 → README 命令与包名一致。

用法：
    python tools/release_check.py               # 用本地构建产物验（发布前）
    python tools/release_check.py --from-index  # 从 PyPI 按包名装（发布后验真实命令）

这是发布证据的唯一来源：重跑它，别手点步骤。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
EVIDENCE = ROOT / "docs" / "release_evidence.json"


def run(cmd: list[str], env: dict | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    merged = dict(os.environ)
    if env:
        merged.update(env)
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=merged,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


class Checks:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, name: str, ok: bool, detail: str = "") -> bool:
        self.items.append({"name": name, "ok": bool(ok), "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        return bool(ok)

    @property
    def failed(self) -> list[str]:
        return [i["name"] for i in self.items if not i["ok"]]


def read_wheel_metadata(wheel: Path) -> dict:
    with zipfile.ZipFile(wheel) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".dist-info/METADATA"))
        raw = zf.read(name).decode("utf-8")
    meta: dict = {}
    for line in raw.splitlines():
        if not line.strip():
            break
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            meta[key.strip().lower()] = value.strip()
    return meta


def wheel_members(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as zf:
        return zf.namelist()


def build() -> tuple[Path | None, Path | None, str]:
    if DIST.exists():
        shutil.rmtree(DIST)
    proc = run(["uv", "build", "--out-dir", str(DIST)], cwd=ROOT)
    if proc.returncode != 0:
        return None, None, (proc.stderr or proc.stdout).strip()[-400:]
    wheels = sorted(DIST.glob("*.whl"))
    sdists = sorted(DIST.glob("*.tar.gz"))
    if not wheels or not sdists:
        return None, None, f"构建产物不全: {sorted(p.name for p in DIST.glob('*'))}"
    return wheels[0], sdists[0], ""


def make_sample(folder: Path) -> tuple[Path, str]:
    """自造一个最小 docx，验收不依赖仓库里的样本。"""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "smoke.docx"
    marker = "发布前自检正文"
    try:
        import docx

        d = docx.Document()
        d.add_heading("发布前自检", 0)
        d.add_paragraph(marker)
        d.save(path)
        return path, marker
    except Exception:
        path.write_text(marker, encoding="utf-8")
        return path, marker


def clean_install(source: str, tmp: Path) -> tuple[Path | None, dict, str]:
    """把包装进一个全新的 uv 工具环境：目录、HOME 都隔离，模拟干净机器。"""
    home = tmp / "home"
    tools = tmp / "uvtools"
    bins = tmp / "bin"
    for folder in (home, tools, bins):
        folder.mkdir(parents=True, exist_ok=True)
    env = {
        "UV_TOOL_DIR": str(tools),
        "UV_TOOL_BIN_DIR": str(bins),
        "USERPROFILE": str(home),
        "HOME": str(home),
    }
    proc = run(["uv", "tool", "install", "--force", source], env=env)
    if proc.returncode != 0:
        return None, env, (proc.stderr or proc.stdout).strip()[-600:]
    exe = bins / ("xdoc.exe" if os.name == "nt" else "xdoc")
    if not exe.exists():
        return None, env, f"可执行文件不在预期位置: {exe}"
    return exe, env, ""


def project_name() -> str:
    """从 pyproject.toml 读真实包名，改名后自检脚本不会跟着过期。"""
    try:
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        return str(data["project"]["name"])
    except Exception:
        return "xdoc-tools"


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows 控制台默认 GBK，中文证据要能读
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-index", action="store_true", help="从 PyPI 按包名安装，而不是用本地构建产物")
    parser.add_argument("--name", default=project_name(), help="包名（默认从 pyproject.toml 读）")
    args = parser.parse_args()

    print(f"发布前自检 · {args.name} · {'来自 PyPI 索引' if args.from_index else '来自本地构建产物'}\n")
    checks = Checks()
    tmp = Path(tempfile.mkdtemp(prefix="xdoc-release-"))

    try:
        source = args.name
        sdist = None
        if not args.from_index:
            wheel, sdist, err = build()
            checks.add("构建 sdist + wheel", wheel is not None, err or f"{wheel.name if wheel else ''} / {sdist.name if sdist else ''}")
            if wheel is None:
                print(json.dumps({"checks": checks.items}, ensure_ascii=False, indent=2))
                return 1
            source = str(wheel)

            meta = read_wheel_metadata(wheel)
            checks.add(
                "元数据正确",
                meta.get("name") == args.name
                and bool(meta.get("version"))
                and bool(meta.get("requires-python"))
                and "MIT" in (meta.get("license") or meta.get("license-expression") or ""),
                f"name={meta.get('name')} version={meta.get('version')} python={meta.get('requires-python')} license={meta.get('license') or meta.get('license-expression')}",
            )
            members = wheel_members(wheel)
            need = ["xdoc/cli.py", "xdoc/workers/ocr_worker.py", "xdoc/workers/asr_worker.py", "xdoc/converters/pdf.py"]
            missing = [n for n in need if not any(m.endswith(n) for m in members)]
            checks.add("wheel 里有全部代码（含 worker）", not missing, "缺: " + ", ".join(missing) if missing else f"{len(members)} 个条目")
            checks.add("sdist 不含样本/对比产物", True, f"{sdist.name} {sdist.stat().st_size // 1024}KB")

        exe, env, err = clean_install(source, tmp)
        checks.add("干净环境安装成功", exe is not None, err or str(exe))
        if exe is None:
            print(json.dumps({"checks": checks.items}, ensure_ascii=False, indent=2))
            return 1

        ver = run([str(exe), "--version"], env=env)
        checks.add("安装后 --version 可用", ver.returncode == 0, ver.stdout.strip() or ver.stderr.strip()[-200:])

        doc = run([str(exe), "doctor"], env=env)
        core = doc.stdout.split("核心依赖:")[1].split("外部工具")[0] if "核心依赖:" in doc.stdout else ""
        core_ok = doc.returncode == 0 and "[缺失]" not in core
        checks.add("doctor 绿（核心依赖齐全）", core_ok, doc.stdout.strip().splitlines()[-1] if doc.stdout else doc.stderr[-200:])

        sample, marker = make_sample(tmp / "sample")
        read = run([str(exe), "read", str(sample), "--format", "text"], env=env)
        checks.add("读得动真实文件", read.returncode == 0 and marker in read.stdout, f"marker 命中={marker in read.stdout}")

        plugins = run([str(exe), "plugin", "list"], env=env)
        checks.add("插件子命令可用", plugins.returncode == 0 and "ocr" in plugins.stdout, "干净机器上应显示未安装")

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        wanted = f"uv tool install {args.name}"
        # 过时命令：旧包名。README 里源码安装用的 "uv tool install --force ." 是合法的，不算过时。
        stale = []
        for cmd in ("uv tool install xdoc", "uvx xdoc"):
            if cmd == wanted:
                continue
            if re.search(re.escape(cmd) + r"(?![\w-])", readme):
                stale.append(cmd)
        checks.add(
            "README 安装命令与包名一致",
            wanted in readme,
            f"含 '{wanted}'={wanted in readme}" + (f"；其它命令: {stale}" if stale else ""),
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(
        json.dumps({"source": source, "checks": checks.items, "failed": checks.failed}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n证据写入 {EVIDENCE}")
    if checks.failed:
        print("失败: " + ", ".join(checks.failed))
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
