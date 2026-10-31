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


def patch_secure_context_check(html: Path) -> None:
    """单线程导出不需要 HTTPS，但 Godot 启动页仍会检查“安全上下文”。

    局域网 http 地址（手机试玩）会因此报错，这里只去掉这一项，其余检查保留。
    """
    text = html.read_text("utf-8")
    old = "const missing = Engine.getMissingFeatures({\n\t\tthreads: GODOT_THREADS_ENABLED,\n\t});"
    new = ("const missing = Engine.getMissingFeatures({\n\t\tthreads: GODOT_THREADS_ENABLED,\n\t})"
           ".filter((m) => GODOT_THREADS_ENABLED || !m.startsWith('Secure Context'));")
    if old not in text:
        raise SystemExit("index.html 结构变了，找不到安全上下文检查，请检查 Godot 版本")
    text = text.replace(old, new)
    # iPhone 上手指拖动会让整页跟着滑、回弹，按钮点起来卡、还会误触：把页面钉住，滑动交给游戏自己处理
    lock = ("<style>html,body{position:fixed;inset:0;overflow:hidden;overscroll-behavior:none;"
            "touch-action:none;-webkit-user-select:none;user-select:none}</style>")
    text = text.replace("</head>", lock + "</head>", 1)
    html.write_text(text, "utf-8")


STAFF_OUT = ROOT / "web" / "staff"
STAFF_PREFIXES = ("staff_", "claude_", "codex_", "deepseek_", "special_")


def copy_staff_portraits() -> None:
    """员工立绘给网页外壳的对话框用（员工推门来找你时显示）。"""
    from PIL import Image
    STAFF_OUT.mkdir(parents=True, exist_ok=True)
    for f in (ROOT / "src" / "assets" / "art").glob("*.png"):
        if f.name.startswith(STAFF_PREFIXES):
            im = Image.open(f)
            im.thumbnail((360, 480))
            im.save(STAFF_OUT / f.name, optimize=True)


def main() -> None:
    copy_staff_portraits()
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.iterdir():
        f.unlink()
    subprocess.run([str(GODOT), "--headless", "--path", str(ROOT / "src"), "--import"], check=True)
    subprocess.run([str(GODOT), "--headless", "--path", str(ROOT / "src"),
                    "--export-release", "Web", str(OUT / "index.html")], check=True)
    patch_secure_context_check(OUT / "index.html")
    for f in OUT.iterdir():
        if f.suffix in (".wasm", ".pck", ".js"):
            with open(f, "rb") as src, gzip.open(str(f) + ".gz", "wb", compresslevel=9) as dst:
                shutil.copyfileobj(src, dst)
    for f in sorted(OUT.iterdir()):
        print(f"{f.name:40s} {f.stat().st_size // 1024:>8d} KB")


if __name__ == "__main__":
    main()
