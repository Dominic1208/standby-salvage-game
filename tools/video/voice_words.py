"""逐字时间戳：给作者的原声录音打上每个字的起止时间，用来对齐字幕和画面。

用法：<GPT-SoVITS venv 的 python> tools/video/voice_words.py <wav> <输出 json>
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, r"D:\AI\tools\audio_asr_deps")
import numpy as np  # noqa: E402
from faster_whisper import WhisperModel  # noqa: E402

cache = Path("D:/AI/tools/audio_asr_models/models--Systran--faster-whisper-small/snapshots")
model_dir = next(p for p in cache.iterdir() if (p / "model.bin").exists())
m = WhisperModel(str(model_dir), device="cpu", compute_type="int8", cpu_threads=4, local_files_only=True)
x = np.frombuffer(subprocess.check_output(["ffmpeg", "-v", "error", "-nostdin", "-i", sys.argv[1], "-ac", "1", "-ar", "16000",
                                           "-f", "f32le", "-"]), dtype=np.float32)
segs, _ = m.transcribe(x, language="zh", beam_size=5, word_timestamps=True,
                       initial_prompt="以下是普通话的句子，带标点。关于AI、Claude、Codex、DeepSeek、代码、待机回收站。")
words = [{"w": w.word, "s": round(w.start, 2), "e": round(w.end, 2)} for s in segs for w in s.words]
Path(sys.argv[2]).write_text(json.dumps(words, ensure_ascii=False), "utf-8")
print(len(words))
