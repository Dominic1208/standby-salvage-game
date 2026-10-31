"""把参考录音转成带时间的文字（选参考片段、核对文字用）。只在本机跑。

用法：<GPT-SoVITS venv 的 python> tools/video/voice_asr.py <wav>
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, r"D:\AI\tools\audio_asr_deps")
import numpy as np  # noqa: E402
from faster_whisper import WhisperModel  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
cache = Path("D:/AI/tools/audio_asr_models/models--Systran--faster-whisper-small/snapshots")
model_dir = next(p for p in cache.iterdir() if (p / "model.bin").exists())
m = WhisperModel(str(model_dir), device="cpu", compute_type="int8", cpu_threads=4, local_files_only=True)
x = np.frombuffer(subprocess.check_output(["ffmpeg", "-v", "error", "-nostdin", "-i", sys.argv[1], "-ac", "1", "-ar", "16000",
                                           "-f", "f32le", "-"]), dtype=np.float32)
segs, _ = m.transcribe(x, language="zh", beam_size=5, initial_prompt="以下是普通话的句子，带标点。")
for s in segs:
    print(f"{s.start:6.2f} - {s.end:6.2f}  {s.text}")
