"""用作者自己的声音给解说稿配音（GPT-SoVITS，本机离线，零样本：只用一段参考录音，不训练）。

用法：
  <GPT-SoVITS venv python> tools/video/voice_clone.py            # 全部配音
  <GPT-SoVITS venv python> tools/video/voice_clone.py --try 3    # 只念前 3 句试听
输出和 tts.py 一样放在 build_tmp/video/voice/，并更新 durations.json，make_video.py 直接能用。

借用 NightPlay 项目里已经装好的 GPT-SoVITS 运行环境和官方通用预训练模型（v2）；
不读、不改那个项目的训练成果和配置。跑之前检查它的显卡占用锁，跑完释放。
"""
import json
import os
import subprocess
import sys
import time
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
from tts import voice_name  # noqa: E402

GSV = Path("D:/AI/NightPlay/voice/GPT-SoVITS/source")
LOCK = Path("D:/AI/NightPlay/voice/gpu-owner.json")
PRE = GSV / "GPT_SoVITS" / "pretrained_models"
VOICE_DIR = ROOT / "build_tmp" / "video" / "voice"
REF_DIR = ROOT / "build_tmp" / "video" / "myvoice"
REF_MAIN = (REF_DIR / "ref_main.wav", "大家好，我做了个小游戏，叫待机回收站。")
REF_AUX = [REF_DIR / "ref_aux.wav"]
# 生成后的处理：不再整体拉响度（会把停顿里的底噪一起放大），只轻度降噪、停顿处压低、稍微提一点清晰度
POST_FX = ("afftdn=nr=10:nf=-50,agate=threshold=0.012:ratio=4:attack=5:release=180,"
           "equalizer=f=3500:t=q:w=1.2:g=2.5,treble=g=2:f=7000,alimiter=limit=0.9")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    script = json.loads((HERE / "script.json").read_text("utf-8"))
    if not script["voice"].startswith("clone:"):
        raise SystemExit('script.json 的 voice 要写成 "clone:名字" 才会用自己的声音')
    only = int(sys.argv[sys.argv.index("--try") + 1]) if "--try" in sys.argv else None
    lines = []
    for sc in script["scenes"]:
        for i, line in enumerate(sc["lines"]):
            line = line.replace("{name}", script["name"])
            lines.append((sc["id"], i, line))
    if only:
        lines = lines[:only]

    cpu = "--cpu" in sys.argv   # 显卡被别的任务（比如 NightPlay 训练）占着时，用 CPU 慢慢念，不抢显卡
    if not cpu:
        if LOCK.exists():
            raise SystemExit(f"显卡正被别的任务占用（{LOCK}），等它跑完再试，或者加 --cpu")
        LOCK.write_text(json.dumps({"owner": "standby_salvage_video_voice", "pid": os.getpid(),
                                    "started_ms": int(time.time() * 1000)}), "utf-8")
    try:
        os.chdir(GSV)
        sys.path[:0] = [str(GSV / "GPT_SoVITS"), str(GSV)]
        os.environ.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "version": "v2",
                           "CUDA_VISIBLE_DEVICES": "" if cpu else "0", "TOKENIZERS_PARALLELISM": "false"})
        # 稿子是中文夹少量英文（AI、App、GitHub），交给官方的中英混合处理；分段器缺依赖时退回整句中文
        try:
            import text.LangSegmenter as _seg  # noqa: F401
        except Exception:
            seg = types.ModuleType("text.LangSegmenter")

            import re

            class S:
                @staticmethod
                def getTexts(t, default_lang=""):
                    # 连续的英文字母（AI、GitHub、Claude…）按英文念，其余按中文念
                    out = []
                    for part in re.split(r"([A-Za-z][A-Za-z\-]*)", t):
                        if part:
                            out.append({"lang": "en" if re.fullmatch(r"[A-Za-z][A-Za-z\-]*", part) else "zh", "text": part})
                    return out
            seg.LangSegmenter = S
            sys.modules["text.LangSegmenter"] = seg
        import numpy as np
        import soundfile as sf
        from TTS_infer_pack.TTS import TTS, TTS_Config
        tts = TTS(TTS_Config({"custom": {
            "device": "cpu" if cpu else "cuda", "is_half": False, "version": "v2",
            "t2s_weights_path": str(PRE / "gsv-v2final-pretrained" / "s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt"),
            "vits_weights_path": str(PRE / "gsv-v2final-pretrained" / "s2G2333k.pth"),
            "cnhuhbert_base_path": str(PRE / "chinese-hubert-base"),
            "bert_base_path": str(PRE / "chinese-roberta-wwm-ext-large")}}))
        VOICE_DIR.mkdir(parents=True, exist_ok=True)
        dur_file = VOICE_DIR / "durations.json"
        durations = json.loads(dur_file.read_text("utf-8")) if dur_file.exists() else {}
        for n, (sid, i, line) in enumerate(lines):
            out = VOICE_DIR / voice_name(sid, i, line, script["voice"])
            if out.exists():
                durations[out.name] = durations.get(out.name) or len(sf.read(out)[0]) / sf.info(out).samplerate
                continue
            chars = sum(1 for c in line if "\u4e00" <= c <= "\u9fff")
            expect = chars * 0.19
            best = None
            for k in range(3):   # 偶尔会提前收尾（念不完），短得离谱就换个种子重来
                r = list(tts.run({
                    "text": line, "text_lang": "zh", "ref_audio_path": str(REF_MAIN[0]), "prompt_text": REF_MAIN[1],
                    "prompt_lang": "zh", "aux_ref_audio_paths": [str(p) for p in REF_AUX], "text_split_method": "cut5",
                    "batch_size": 1, "top_k": 15, "top_p": 1, "temperature": 1.0, "seed": 20261031 + n * 10 + k,
                    "speed_factor": 1.0, "parallel_infer": False, "return_fragment": False, "streaming_mode": False}))
                sr, a = r[-1]
                a = np.asarray(a)
                sec = len(a) / sr
                if best is None or sec > best[2]:
                    best = (sr, a, sec)
                if sec >= expect * 0.6:
                    break
            sr, a, sec = best
            wav = out.with_suffix(".wav")
            sf.write(wav, a, sr, subtype="PCM_16")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-af", POST_FX,
                            "-ar", "44100", "-b:a", "192k", str(out)], check=True)
            wav.unlink()
            durations[out.name] = float(subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                capture_output=True, text=True).stdout)
            print(f"[{n + 1}/{len(lines)}] {sec:5.1f}s  {line[:30]}")
        dur_file.write_text(json.dumps(durations, ensure_ascii=False, indent=1), "utf-8")
    finally:
        if LOCK.exists() and json.loads(LOCK.read_text("utf-8")).get("pid") == os.getpid():
            LOCK.unlink()


if __name__ == "__main__":
    main()
