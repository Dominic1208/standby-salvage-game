"""把电脑版的图片和声音压成小游戏用的尺寸，输出到 minigame/build/assets/。

微信小游戏：首包 ≤ 4MB，全部分包加起来 ≤ 30MB。所以：
- 首包只放音效（audio/sfx_*.mp3）；
- 图片和背景音乐放进分包 res/（res/art/*.png|jpg、res/audio/bgm_*.mp3），启动后再加载。
图片用到哪些，从 minigame/build/data/*.json（清理过的数据）里的 art / look 字段自动收集。

用法：python tools/build_minigame_assets.py
"""
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "src" / "assets" / "art"
AUDIO = ROOT / "web" / "audio"
OUT = ROOT / "minigame" / "build" / "assets"

# 小游戏版的员工造型 adv_01..22 = 电脑版的这些立绘（顺序和 meta.json 的抽卡表一致）
SKIN_SOURCES = ([f"claude_{i}" for i in range(1, 7)] + [f"codex_{i}" for i in range(1, 7)]
                + [f"deepseek_{i}" for i in range(1, 7)] + [f"special_{i}" for i in range(1, 5)])
BACKGROUNDS = {"lounge_bg": 900, "shop_bg": 900}      # 背景：存 jpg，宽度
CHARACTER_H = 520                                     # 顾客、员工立绘的高度
ICON = 256                                            # 货物、类别图标
COLLECTIBLE = 320                                     # 收藏品图、包裹图


def collect_art() -> set:
    names = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("art", "look") and isinstance(v, str):
                    names.add(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    # 读清理过的小游戏数据（先跑 build_minigame_data.py），删掉的顾客和收藏品的图就不打包
    for f in ["catalog", "customers", "gifts", "meta", "staff"]:
        walk(json.loads((ROOT / "minigame" / "build" / "data" / f"{f}.json").read_text("utf-8")))
    return names | {"lounge_bg", "shop_bg", "gift_small", "gift_big", "gift_weird"}


def source_of(name: str) -> Path:
    if name.startswith("adv_"):
        return ART / f"{SKIN_SOURCES[int(name[4:]) - 1]}.png"
    return ART / f"{name}.png"


def save_png(im: Image.Image, path: Path):
    """256 色带透明的 PNG，体积大约是原图的四分之一。"""
    im = im.convert("RGBA")
    q = im.quantize(colors=256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.FLOYDSTEINBERG)
    q.save(path, optimize=True)


def shrink(im: Image.Image, max_w=None, max_h=None) -> Image.Image:
    s = 1.0
    if max_w:
        s = min(s, max_w / im.width)
    if max_h:
        s = min(s, max_h / im.height)
    return im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS) if s < 1 else im


def build_art(names: set):
    out = OUT / "res" / "art"
    if out.exists():   # 清掉上次的，免得删掉的图还留在包里
        for f in out.iterdir():
            f.unlink()
    out.mkdir(parents=True, exist_ok=True)
    total = 0
    for name in sorted(names):
        src = source_of(name)
        if not src.exists():
            print("  缺图：", name)
            continue
        im = Image.open(src)
        if name in BACKGROUNDS:
            dst = out / f"{name}.jpg"
            shrink(im.convert("RGB"), max_w=BACKGROUNDS[name]).save(dst, quality=82, optimize=True, progressive=True)
        else:
            dst = out / f"{name}.png"
            if name.startswith(("customer_", "adv_")):
                im = shrink(im, max_h=CHARACTER_H)
            elif name.startswith(("col_", "gift_")):
                im = shrink(im, max_w=COLLECTIBLE, max_h=COLLECTIBLE)
            else:
                im = shrink(im, max_w=ICON, max_h=ICON)
            save_png(im, dst)
        total += dst.stat().st_size
    print(f"图片 {len(names)} 张，{total / 1024 / 1024:.1f} MB")


def build_audio():
    sfx_dir = OUT / "audio"
    bgm_dir = OUT / "res" / "audio"
    sfx_dir.mkdir(parents=True, exist_ok=True)
    bgm_dir.mkdir(parents=True, exist_ok=True)
    total = {"sfx": 0, "bgm": 0}
    for src in sorted(AUDIO.iterdir()):
        if src.suffix not in (".wav", ".mp3"):
            continue
        is_bgm = src.stem.startswith("bgm_")
        dst = (bgm_dir if is_bgm else sfx_dir) / f"{src.stem}.mp3"
        rate = "64k" if is_bgm else "48k"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-ac", "1", "-ar", "44100", "-b:a", rate, str(dst)],
                       check=True)
        total["bgm" if is_bgm else "sfx"] += dst.stat().st_size
    print(f"音效 {total['sfx'] / 1024:.0f} KB（首包），背景音乐 {total['bgm'] / 1024 / 1024:.1f} MB（分包）")


def build_share():
    """转发卡片图（5:4，放首包根目录）：用抖音横封面缩一下。"""
    src = ROOT / "devlog" / "video" / "抖音横封面-4比3.jpg"
    if not src.exists():
        return
    im = Image.open(src).convert("RGB")
    w, h = im.size
    ch = round(w * 4 / 5)
    im = im.crop((0, (h - ch) // 2, w, (h - ch) // 2 + ch)).resize((500, 400), Image.LANCZOS)
    OUT.mkdir(parents=True, exist_ok=True)
    im.save(OUT / "share.jpg", quality=85)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    build_share()
    build_art(collect_art())
    build_audio()


if __name__ == "__main__":
    main()
