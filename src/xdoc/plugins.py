"""插件管理：可选引擎（OCR / ASR / ffmpeg）按需下载安装，可随时卸载。

插件是"装了就能用"的独立环境：
- Python 插件：各自一个 venv + 自己的依赖 + 自己的模型，互不影响。
- 二进制插件（如 ffmpeg）：解压到插件目录，不写系统 PATH。

Base 包本身保持轻量，卸载插件后不留残渣（整个目录删掉即可）。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .errors import PluginError

PACKAGE_ROOT = Path(__file__).resolve().parent
WORKERS_DIR = PACKAGE_ROOT / "workers"


@dataclass(frozen=True)
class PluginSpec:
    name: str
    title: str
    description: str
    deps: tuple[str, ...] = ()
    worker: str | None = None
    kind: str = "python"          # python | binary
    approx_size: str = ""
    warmup: str | None = None     # 安装后执行的一段 Python，用来把模型下载到插件目录
    index_url: str | None = None  # 依赖走哪个源（CPU 版 torch 用官方 CPU 源，避免 2GB+ CUDA 包）


PLUGINS: dict[str, PluginSpec] = {
    "ocr": PluginSpec(
        name="ocr",
        title="OCR 文字识别",
        description="扫描件/图片转文字（PP-OCRv6 ONNX 模型，纯 CPU，中英文）",
        deps=("rapidocr>=3.0", "onnxruntime>=1.16"),
        worker="ocr_worker.py",
        approx_size="约 60MB（模型随包装好，运行期不联网）",
    ),
    "asr": PluginSpec(
        name="asr",
        title="语音转写（通用）",
        description="音频/视频转文字，带时间戳（faster-whisper，多语言）",
        deps=("faster-whisper>=1.0", "av>=11,<19"),
        worker="asr_worker.py",
        approx_size="约 500MB（含 small 模型，安装时下载）",
        warmup=(
            "from faster_whisper import WhisperModel\n"
            "WhisperModel('small', device='cpu', compute_type='int8')\n"
        ),
    ),
    "asr-zh": PluginSpec(
        name="asr-zh",
        title="语音转写（中文）",
        description="中文/中英混说转写（FunASR Paraformer-zh），带时间戳并自动恢复标点",
        deps=("funasr>=1.1.0", "modelscope>=1.13.0", "torch>=2.2", "torchaudio>=2.2"),
        worker="asr_worker.py",
        approx_size="约 2GB（含 torch 与 Paraformer-zh 模型，安装时下载）",
        index_url="https://download.pytorch.org/whl/cpu",
        warmup=(
            "from funasr import AutoModel\n"
            "AutoModel(model='paraformer-zh', vad_model='fsmn-vad', "
            "punc_model='ct-punc', disable_update=True)\n"
        ),
    ),
    "media": PluginSpec(
        name="media",
        title="音视频处理 (ffmpeg/ffprobe)",
        description="抽音频轨、抽关键帧、读取时长/编码信息",
        kind="binary",
        approx_size="约 90MB",
    ),
}

FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"


def default_plugin_root() -> Path:
    return Path.home() / ".local" / "share" / "xdoc" / "plugins"


class PluginManager:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else default_plugin_root()
        self.root.mkdir(parents=True, exist_ok=True)

    # ---------- 目录 ----------
    def plugin_dir(self, name: str) -> Path:
        return self.root / name

    def venv_python(self, name: str) -> Path:
        base = self.plugin_dir(name) / "venv"
        if os.name == "nt":
            return base / "Scripts" / "python.exe"
        return base / "bin" / "python"

    def marker(self, name: str) -> Path:
        return self.plugin_dir(name) / ".installed"

    def is_installed(self, name: str) -> bool:
        return self.marker(name).exists()

    def list(self) -> list[dict]:
        out: list[dict] = []
        for spec in PLUGINS.values():
            info = {
                "name": spec.name,
                "title": spec.title,
                "description": spec.description,
                "kind": spec.kind,
                "installed": self.is_installed(spec.name),
                "approx_size": spec.approx_size,
            }
            if spec.name == "media":
                info["ffmpeg"] = str(self.ffmpeg_path()) if self.ffmpeg_path() else None
            out.append(info)
        return out

    # ---------- 安装 / 卸载 ----------
    def install(self, name: str) -> dict:
        spec = PLUGINS.get(name)
        if spec is None:
            raise PluginError(f"未知插件: {name}（可用: {', '.join(PLUGINS)}）")
        if self.is_installed(name):
            return {"plugin": name, "status": "already-installed"}

        directory = self.plugin_dir(name)
        directory.mkdir(parents=True, exist_ok=True)

        if spec.kind == "binary":
            self._install_ffmpeg(directory)
        else:
            self._install_python_plugin(spec, directory)

        self.marker(name).write_text(
            json.dumps({"name": name, "installed_at": _now(), "deps": list(spec.deps)}),
            encoding="utf-8",
        )
        return {"plugin": name, "status": "installed", "dir": str(directory)}

    def _install_python_plugin(self, spec: PluginSpec, directory: Path) -> None:
        venv_dir = directory / "venv"
        uv = shutil.which("uv")
        try:
            if uv:
                subprocess.run([uv, "venv", str(venv_dir), "--python", "3.12"],
                               check=True, capture_output=True)
                pip_cmd = [uv, "pip", "install", "--python", str(self.venv_python(spec.name))]
                if spec.index_url:
                    pip_cmd += ["--index-url", spec.index_url,
                                "--extra-index-url", "https://pypi.org/simple"]
                subprocess.run(pip_cmd + list(spec.deps), check=True, capture_output=True)
            else:
                subprocess.run([sys.executable, "-m", "venv", str(venv_dir)],
                               check=True, capture_output=True)
                subprocess.run([str(self.venv_python(spec.name)), "-m", "pip", "install", *spec.deps],
                               check=True, capture_output=True)
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or b"").decode("utf-8", "replace")[-800:]
            raise PluginError(f"安装 {spec.name} 失败: {detail}") from exc

        if spec.worker:
            source = WORKERS_DIR / spec.worker
            if not source.exists():
                raise PluginError(f"缺少 worker 脚本: {source}")
            shutil.copy2(source, directory / spec.worker)

        if spec.warmup:
            # 模型在安装期下载到插件目录里，运行期完全离线
            env = self._plugin_env(spec.name)
            try:
                subprocess.run([str(self.venv_python(spec.name)), "-c", spec.warmup],
                               check=True, capture_output=True, env=env)
            except subprocess.CalledProcessError as exc:
                detail = (exc.stderr or b"").decode("utf-8", "replace")[-800:]
                raise PluginError(f"{spec.name} 模型预下载失败: {detail}") from exc

    def _install_ffmpeg(self, directory: Path) -> None:
        import urllib.request
        import zipfile

        archive = directory / "ffmpeg.zip"
        try:
            request = urllib.request.Request(
                FFMPEG_URL, headers={"User-Agent": "xdoc-plugin-installer/0.1"}
            )
            with urllib.request.urlopen(request, timeout=600) as resp, archive.open("wb") as out:
                shutil.copyfileobj(resp, out)
        except Exception as exc:
            raise PluginError(f"下载 ffmpeg 失败: {exc}") from exc

        with zipfile.ZipFile(archive) as zf:
            zf.extractall(directory)
        archive.unlink(missing_ok=True)
        # 解压出来的目录结构是 ffmpeg-<version>-essentials/bin/
        for candidate in directory.glob("*/bin/ffmpeg.exe"):
            for tool in ("ffmpeg.exe", "ffprobe.exe"):
                src = candidate.parent / tool
                if src.exists():
                    shutil.copy2(src, directory / tool)

    def uninstall(self, name: str) -> dict:
        if name not in PLUGINS:
            raise PluginError(f"未知插件: {name}")
        directory = self.plugin_dir(name)
        existed = directory.exists()
        if existed:
            shutil.rmtree(directory, ignore_errors=True)
        return {"plugin": name, "status": "uninstalled" if existed else "not-installed"}

    # ---------- 使用 ----------
    def _plugin_env(self, name: str) -> dict[str, str]:
        """插件运行/安装时的环境变量：模型缓存指向插件目录（卸载即彻底删除）。

        运行期强制离线：模型已经在安装期下载好，转写时不允许再去连模型仓库。
        """
        env = dict(os.environ)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        models = self.plugin_dir(name) / "models"
        env["MODELSCOPE_CACHE"] = str(models)
        env["HF_HOME"] = str(models)
        env["XDOC_PLUGIN_DIR"] = str(self.plugin_dir(name))
        env["MODELSCOPE_OFFLINE"] = "1"
        env["HF_HUB_OFFLINE"] = "1"
        env["TRANSFORMERS_OFFLINE"] = "1"
        return env

    def ffmpeg_path(self, tool: str = "ffmpeg") -> Path | None:
        local = self.plugin_dir("media") / (f"{tool}.exe" if os.name == "nt" else tool)
        if local.exists():
            return local
        found = shutil.which(tool)
        return Path(found) if found else None

    def run_worker(self, name: str, payload: dict, *, timeout: int = 1800) -> dict:
        spec = PLUGINS.get(name)
        if spec is None:
            raise PluginError(f"未知插件: {name}")
        if not self.is_installed(name):
            raise PluginError(f"插件 {name} 未安装，先执行: xdoc plugin add {name}")
        python = self.venv_python(name)
        # 优先用包里的 worker（永远是最新版本），插件目录里的副本只作备份
        worker = WORKERS_DIR / (spec.worker or "")
        if not worker.exists():
            worker = self.plugin_dir(name) / (spec.worker or "")
        if not worker.exists():
            raise PluginError(f"插件 {name} 的 worker 缺失: {worker}")

        env = self._plugin_env(name)
        try:
            proc = subprocess.run(
                [str(python), str(worker)],
                input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                capture_output=True,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise PluginError(f"插件 {name} 执行超时（>{timeout}s）") from exc

        stdout = proc.stdout.decode("utf-8", "replace").strip()
        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", "replace")[-1200:].strip()
            detail = stderr
            if stdout:
                try:
                    payload = json.loads(stdout.splitlines()[-1])
                    if isinstance(payload, dict) and payload.get("error"):
                        detail = f"{payload['error']}\n{stderr}".strip()
                except (json.JSONDecodeError, IndexError):
                    detail = f"{stdout[-600:]}\n{stderr}".strip()
            raise PluginError(f"插件 {name} 执行失败（exit {proc.returncode}）: {detail}")
        try:
            return json.loads(stdout.splitlines()[-1]) if stdout else {}
        except json.JSONDecodeError as exc:
            raise PluginError(f"插件 {name} 返回无法解析的结果: {stdout[:400]}") from exc


def _now() -> str:
    import datetime as _dt

    return _dt.datetime.now().isoformat(timespec="seconds")
