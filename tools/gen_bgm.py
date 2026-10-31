"""用本机 ACE-Step 生成游戏背景音乐（纯音乐，可循环）。

用法（用 ACE-Step 自带的 Python 环境）：
  D:\\AI\\tools\\ACE-Step-1.5\\.venv\\Scripts\\python.exe tools\\gen_bgm.py
输出：web/audio/bgm_*.mp3
"""
import json
import os
import shutil
import sys
from pathlib import Path

ENGINE = Path("D:/AI/tools/ACE-Step-1.5")
OUT = Path(__file__).resolve().parent.parent / "web" / "audio"
RAW = Path(__file__).resolve().parent.parent / "art_source" / "bgm_raw"
OUT.mkdir(parents=True, exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ENGINE))
os.environ["ACESTEP_PROJECT_ROOT"] = str(ENGINE)
os.environ["ACESTEP_CHECKPOINTS_DIR"] = str(ENGINE / "checkpoints")
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ["HF_HOME"] = str(ENGINE / "runtime-cache/huggingface")
os.environ["HF_MODULES_CACHE"] = str(ENGINE / "runtime-cache/huggingface/modules")
os.environ["TORCH_HOME"] = str(ENGINE / "runtime-cache/torch")
os.environ["NUMBA_CACHE_DIR"] = str(ENGINE / "runtime-cache/numba")
os.environ["MPLCONFIGDIR"] = str(ENGINE / "runtime-cache/matplotlib")

import torch
from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler
from acestep.inference import GenerationConfig, GenerationParams, generate_music

TRACKS = {
    "bgm_shop": dict(
        caption=("Cozy instrumental lo-fi jazz hop for a late-night second-hand shop game, "
                 "warm Rhodes electric piano chords, soft upright bass, dusty brushed drums, "
                 "gentle vinyl crackle, a little playful glockenspiel melody, relaxed and "
                 "slightly mischievous mood, steady groove, seamless loop, no vocals"),
        bpm=86, key="F major", seed=20261031,
    ),
    "bgm_closing": dict(
        caption=("Short warm instrumental jazz outro for the end of a shopping day in a cozy game, "
                 "mellow piano, soft saxophone, brushed drums, satisfied and a little tired mood, "
                 "gentle ending, no vocals"),
        bpm=72, key="Bb major", seed=20261032,
    ),
}
DURATION = {"bgm_shop": 90.0, "bgm_closing": 30.0}


def main() -> None:
    torch.set_num_threads(8)
    dit = AceStepHandler()
    msg, ok = dit.initialize_service(
        project_root=str(ENGINE), config_path="acestep-v15-turbo", device="cuda",
        use_flash_attention=False, compile_model=False, offload_to_cpu=True,
        offload_dit_to_cpu=True, prefer_source="huggingface", use_mlx_dit=False,
    )
    if not ok:
        raise RuntimeError(msg)
    lm = LLMHandler()
    msg, ok = lm.initialize(
        checkpoint_dir=str(ENGINE / "checkpoints"), lm_model_path="acestep-5Hz-lm-1.7B",
        backend="pt", device="cuda", offload_to_cpu=True,
    )
    if not ok:
        raise RuntimeError(msg)
    for name, t in TRACKS.items():
        params = GenerationParams(
            caption=t["caption"], lyrics="[Instrumental]", instrumental=True,
            bpm=t["bpm"], keyscale=t["key"], timesignature="4", duration=DURATION[name],
            inference_steps=8, seed=t["seed"], thinking=True,
            use_cot_metas=False, use_cot_caption=False, use_cot_lyrics=False, use_cot_language=False,
        )
        config = GenerationConfig(batch_size=1, audio_format="mp3", use_random_seed=False, seeds=[t["seed"]])
        result = generate_music(dit, lm, params, config, save_dir=str(RAW / name))
        if not result.success or not result.audios:
            raise RuntimeError(result.error or result.status_message)
        src = Path(result.audios[0]["path"])
        shutil.copy2(src, OUT / f"{name}{src.suffix}")
        print("BGM", name, OUT / f"{name}{src.suffix}", flush=True)
    (OUT / "bgm_credits.json").write_text(json.dumps(
        {"generator": "ACE-Step 1.5 (local)", "tracks": list(TRACKS)}, ensure_ascii=False), "utf-8")


if __name__ == "__main__":
    main()
