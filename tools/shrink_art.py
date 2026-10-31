"""把 Codex 生成的大图缩小，减少网页加载量。原图另存在 art_source/（不进游戏包）。

用法：python tools/shrink_art.py
"""

import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "src" / "assets" / "art"
SOURCE = ROOT / "art_source"
SIZES = {"customer_": 512, "item_": 384, "shop_bg": 1024}


def main() -> None:
    SOURCE.mkdir(exist_ok=True)
    for f in sorted(ART.glob("*.png")):
        limit = next((v for k, v in SIZES.items() if f.name.startswith(k)), 512)
        im = Image.open(f)
        if max(im.size) <= limit:
            continue
        backup = SOURCE / f.name
        if not backup.exists():
            shutil.copy2(f, backup)
        im.thumbnail((limit, limit), Image.LANCZOS)
        im.save(f, optimize=True)
        print(f"{f.name}: {im.size}, {f.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
