"""导出 Godot 网页版到 web/game/，并预压缩（连接程序会自动发 .gz 版本，手机加载快很多）。

用法：python tools/export_web.py
"""

import gzip
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GODOT = Path(r"D:\AI\Godot_v4.7.2-stable_win64.exe\Godot_v4.7.2-stable_win64_console.exe")
OUT = ROOT / "web" / "game"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.iterdir():
        f.unlink()
    subprocess.run([str(GODOT), "--headless", "--path", str(ROOT / "src"), "--import"], check=True)
    subprocess.run([str(GODOT), "--headless", "--path", str(ROOT / "src"),
                    "--export-release", "Web", str(OUT / "index.html")], check=True)
    for f in OUT.iterdir():
        if f.suffix in (".wasm", ".pck", ".js"):
            with open(f, "rb") as src, gzip.open(str(f) + ".gz", "wb", compresslevel=9) as dst:
                shutil.copyfileobj(src, dst)
    for f in sorted(OUT.iterdir()):
        print(f"{f.name:40s} {f.stat().st_size // 1024:>8d} KB")


if __name__ == "__main__":
    main()
