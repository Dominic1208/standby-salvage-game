"""给解说稿配音：每句一个 mp3，并记下每句时长（字幕和画面都按它对齐）。

用法：python tools/video/tts.py
输出：build_tmp/video/voice/<场景>_<序号>.mp3 和 durations.json
需要联网（微软的中文神经网络语音），只上传解说稿文字。
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import edge_tts

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = ROOT / "build_tmp" / "video" / "voice"


def duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    script = json.loads((HERE / "script.json").read_text("utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    durations = {}
    for scene in script["scenes"]:
        for i, line in enumerate(scene["lines"]):
            path = OUT / f"{scene['id']}_{i:02d}.mp3"
            for attempt in range(6):   # 服务偶尔回 429（请求太多），等一会儿再试
                if path.exists() and path.stat().st_size > 0:
                    break
                try:
                    await edge_tts.Communicate(line, script["voice"], rate=script["rate"]).save(str(path))
                except Exception as exc:
                    path.unlink(missing_ok=True)
                    print(f"  {path.name} 第 {attempt + 1} 次失败：{str(exc)[:60]}，{5 * (attempt + 1)} 秒后重试")
                    await asyncio.sleep(5 * (attempt + 1))
            await asyncio.sleep(0.8)
            durations[path.name] = duration(path)
    (OUT / "durations.json").write_text(json.dumps(durations, ensure_ascii=False, indent=1), "utf-8")
    total = sum(durations.values())
    print(f"{len(durations)} 句，共 {total:.0f} 秒（{total / 60:.1f} 分钟）")


if __name__ == "__main__":
    asyncio.run(main())
