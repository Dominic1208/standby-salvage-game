"""把 Noto Sans SC 裁剪成游戏用的小字体：常用 3755 个汉字 + 源码和数据里出现的所有字符。

用法：python tools/build_font.py <NotoSansSC-Regular.otf 路径>
输出：src/assets/fonts/ui.otf
字体许可：SIL Open Font License 1.1（Noto CJK，可随项目开源分发）。
"""

import sys
from pathlib import Path

from fontTools import subset

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "assets" / "fonts" / "ui.otf"


def gb2312_level1() -> str:
    chars = []
    for hi in range(0xB0, 0xD8):
        for lo in range(0xA1, 0xFF):
            try:
                chars.append(bytes([hi, lo]).decode("gb2312"))
            except UnicodeDecodeError:
                pass
    return "".join(chars)


def project_chars() -> str:
    text = []
    for pattern in ("*.gd", "data/*.json"):
        for f in (ROOT / "src").glob(pattern):
            text.append(f.read_text("utf-8"))
    return "".join(text)


def main() -> None:
    src = sys.argv[1]
    chars = set(gb2312_level1()) | set(project_chars())
    chars |= set(chr(c) for c in range(0x20, 0x7F))
    chars |= set("，。！？：；“”‘’（）《》【】、…—·￥¥＋－％")
    opts = subset.Options()
    opts.layout_features = ["*"]
    font = subset.load_font(src, opts)
    sub = subset.Subsetter(opts)
    sub.populate(text="".join(sorted(chars)))
    sub.subset(font)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    subset.save_font(font, str(OUT), opts)
    print(f"{OUT}  {OUT.stat().st_size // 1024} KB, {len(chars)} chars")


if __name__ == "__main__":
    main()
