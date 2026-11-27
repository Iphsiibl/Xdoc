"""ASR worker 的纯函数测试（不加载模型）。"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKER = ROOT / "src" / "xdoc" / "workers" / "asr_worker.py"


def _load_worker():
    spec = importlib.util.spec_from_file_location("xdoc_asr_worker", WORKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


worker = _load_worker()


def test_align_stamps_skips_punctuation():
    """FunASR 的 timestamp 不含标点，文本里的标点不能消耗时间戳。"""
    text = "欢迎大家来体验达摩院推出的语音识别模型。"
    stamps = [[i * 100, i * 100 + 90] for i in range(19)]
    pairs = worker._align_stamps(text, stamps)
    assert len(pairs) == len(text)
    # 19 个字各拿一个时间戳，句号没有
    assert sum(1 for _ch, stamp in pairs if stamp is not None) == 19
    assert pairs[-1][1] is None


def test_align_stamps_treats_ascii_word_as_one_token():
    text = "hello world"
    stamps = [[0, 100], [200, 300]]
    pairs = worker._align_stamps(text, stamps)
    assert pairs[0][1] == [0, 100]
    assert pairs[4][1] == [0, 100]   # hello 共用第一个时间戳
    assert pairs[6][1] == [200, 300]  # world 用第二个


def test_funasr_segments_from_timestamps():
    """中文：19 字 + 1 句号，19 个时间戳 → 一句话，起止时间来自首尾字。"""
    text = "欢迎大家来体验达摩院推出的语音识别模型。"
    stamps = [[880 + i * 200, 880 + i * 200 + 190] for i in range(19)]
    segs = worker._funasr_segments({"text": text, "timestamp": stamps})
    assert len(segs) == 1
    assert segs[0]["text"] == text
    assert segs[0]["start"] == 0.88
    assert abs(segs[0]["end"] - (880 + 18 * 200 + 190) / 1000) < 0.01


def test_funasr_segments_prefers_sentence_info():
    segs = worker._funasr_segments({
        "text": "你好。",
        "sentence_info": [{"text": "你好。", "start": 1200, "end": 3400}],
        "timestamp": [],
    })
    assert segs == [{"start": 1.2, "end": 3.4, "text": "你好。"}]


def test_funasr_segments_without_timestamps_degrades_gracefully():
    segs = worker._funasr_segments({"text": "你好。"})
    assert segs == [{"start": 0.0, "end": 0.0, "text": "你好。"}]


def test_worker_module_is_importable():
    assert callable(worker.main)
    assert sys.modules is not None
