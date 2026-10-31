"""生成小游戏上架要用的材料，输出到 minigame/上架材料/：

- 软著-源程序.pdf：小游戏源代码，每页 50 行，页眉写软件名称和版本号（不够 60 页就全交，超过就交前 30 + 后 30 页）
- 软著-用户手册.pdf：软件说明书，带截图
- 图标-512.png、图标-144.png：方形图标（平台要求不要自己做圆角）
- 截图/：上架和备案用的游戏截图（需要先在浏览器里跑一遍截图脚本，存在 minigame/build/shots/s*.png）

PDF 用本机的 Edge 无头模式把 HTML 打印出来，不用装别的库。
用法：python tools/build_minigame_docs.py
"""
import html
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
MINI = ROOT / "minigame"
OUT = MINI / "上架材料"
SHOTS = MINI / "build" / "shots"
ART = MINI / "build" / "assets" / "res" / "art"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")

NAME = "待机回收站游戏软件"     # 软著登记的全称；小游戏名“待机回收站”可以省略“游戏软件”后缀
SHORT = "待机回收站"
VERSION = "V1.0"
LINES_PER_PAGE = 50

PAGE_CSS = """
@page { size: A4; margin: 14mm 16mm; }
body { font-family: "Microsoft YaHei", sans-serif; margin: 0; }
.page { page-break-after: always; position: relative; }
.page:last-child { page-break-after: auto; }
.head { display: flex; justify-content: space-between; font-size: 9pt; border-bottom: 1px solid #000;
  padding-bottom: 2px; margin-bottom: 6px; }
"""


def print_pdf(html_path: Path, pdf_path: Path):
    subprocess.run([str(EDGE), "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf_path}", html_path.as_uri()], check=True, capture_output=True)


# ---------------- 源程序 ----------------
def source_lines() -> list:
    files = sorted((MINI / "src").rglob("*.js"))
    files.sort(key=lambda p: (p.name != "main.js", str(p)))   # 入口放最前面
    lines = []
    for f in files:
        rel = f.relative_to(MINI).as_posix()
        lines.append(f"// ===== {rel} =====")
        for line in f.read_text("utf-8").splitlines():
            if line.strip():                                   # 空行不算行数，去掉
                lines.append(line.rstrip())
    return lines


def build_source():
    lines = source_lines()
    pages = [lines[i:i + LINES_PER_PAGE] for i in range(0, len(lines), LINES_PER_PAGE)]
    if len(pages) > 60:                                        # 超过 60 页：前 30 页 + 后 30 页
        pages = pages[:30] + pages[-30:]
    css = PAGE_CSS + """
pre { font-family: Consolas, "Microsoft YaHei", monospace; font-size: 7.6pt; line-height: 1.32; margin: 0;
  white-space: pre-wrap; word-break: break-all; }
"""
    body = []
    for i, p in enumerate(pages, 1):
        body.append(f'<div class="page"><div class="head"><span>{NAME} {VERSION}</span><span>第 {i} 页</span></div>'
                    f'<pre>{html.escape(chr(10).join(p))}</pre></div>')
    src = OUT / "_源程序.html"
    src.write_text(f"<!doctype html><meta charset='utf-8'><style>{css}</style>{''.join(body)}", "utf-8")
    print_pdf(src, OUT / "软著-源程序.pdf")
    src.unlink()
    print(f"源程序：{len(lines)} 行，{len(pages)} 页")


# ---------------- 用户手册 ----------------
MANUAL = [
    ("一、软件概述", [
        f"{SHORT}是一款运行在微信、抖音小游戏平台上的经营模拟游戏。玩家经营一家“什么都收”的回收站：顾客上门卖二手物品，"
        "玩家通过检查物品线索、质疑顾客讲的来历、出价砍价来决定是否收购；每天打烊时把收来的货卖给收购商，赚取差价并按期偿还贷款。",
        "玩家还可以派店里的员工出门探险，员工按真实时间回来，带回冒险故事和包裹，包裹里可以开出现金、情报和收藏品。"
        "赚到的钱可以用来升级店铺、给员工换造型、收集图鉴、解锁成就。",
        "本软件为单机游戏，不需要注册登录，不收集任何个人信息，存档只保存在玩家手机本地。"]),
    ("二、运行环境", [
        "硬件：安卓或苹果智能手机，屏幕竖屏。",
        "软件：微信（小游戏）或抖音（小游戏）最新版本。",
        "开发语言：JavaScript；画面使用 Canvas 2D 绘制。代码约 2000 行。"]),
    ("三、启动", [
        f"在微信或抖音中搜索“{SHORT}”，点开即可进入。启动页显示游戏名称和《健康游戏忠告》，点击屏幕进入游戏。"
        "第一次进入时会显示四页新手引导，介绍开店、验货、派员工、还贷款等基本玩法。"],
        ["s01_启动页", "s02_新手引导"]),
    ("四、大本营（主界面）", [
        "进入游戏后是大本营。店里的员工会在房间里走动；外出回来的员工会在吧台前排队等你听汇报。",
        "顶部显示天数、现金、口碑和下一次还贷时间；下面一排按钮依次是：员工、升级、抽造型、图鉴、成就、设置。",
        "点击画面下方的吧台即可开门营业。"],
        ["s03_大本营"]),
    ("五、员工与探险", [
        "点“员工”打开员工列表，可以查看每位员工的状态，招募新员工。",
        "点“派出门”选择目的地：门口转转、楼下跳蚤市场、大学城毕业季、城郊旧货仓库、海边码头、深夜拍卖会、深山老宅。"
        "越远的地方用时越长，带回的包裹越好；部分目的地需要经营到一定天数才解锁。",
        "员工按真实时间回来，关闭游戏也照常计时。回来后点员工即可听他讲这次的冒险经历，有时还会遇到需要你决定的小选择，"
        "最后收下他带回的包裹。"],
        ["s04_员工", "s05_派员工出门", "s06_员工汇报"]),
    ("六、营业：收货与砍价", [
        "开门后顾客会带着物品上门，并讲述物品的来历。画面中部的“回收单”显示物品名称、类别、市场参考价和顾客要价。",
        "点“检查××”可以查看物品的一处细节（每次检查消耗营业时间）。有的顾客会撒谎：如果检查发现的细节和顾客说的来历对不上，"
        "就点“质疑来历”揭穿他，被揭穿的顾客只能按真实价值出售。质疑诚实的顾客会让他不高兴。",
        "下方的收银机用来出价：可以用“−”“+”调整，也可以直接按要价的三成、五成、七成、九成出价，然后点“出价”。"
        "顾客会接受、还价或者离开。也可以“按要价收”或“不收了”。"],
        ["s07_收货", "s08_揭穿骗子", "s09_成交"]),
    ("七、打烊结算与还贷", [
        "营业时间用完后自动打烊：仓库里的货卖给收购商，符合“今日订单”类别的货可以多卖钱；会漏液的问题货可能弄坏别的货。",
        "第 3 天和第 7 天需要偿还贷款，钱不够店就会被收走；撑过 7 天即获胜。无论输赢，员工、升级、收藏品和成就都会保留。"],
        ["s10_打烊结算"]),
    ("八、包裹与收藏图鉴", [
        "员工带回的包裹可以在大本营右上角点开。包裹里可能有现金、情报（下次检查物品不耗时间）、口碑或收藏品。",
        "收藏品共有近千件，分为几十个系列，可在“图鉴”中按系列查看收集进度。"],
        ["s11_拆包裹", "s14_收藏图鉴"]),
    ("九、店铺升级、员工造型与成就", [
        "“升级”中可以用现金购买放大镜、霓虹招牌、防水保险柜等八种永久升级，每种最多三级。",
        "“抽造型”中可以用游戏内现金抽取员工造型，页面上公示各稀有度的概率；抽到的造型可以给任何员工换上。"
        "本游戏没有任何付费功能，抽造型只消耗游戏内的现金。",
        "“成就”记录玩家的游戏里程碑，共三十余项。"],
        ["s12_店铺升级", "s13_抽造型", "s15_成就"]),
    ("十、设置", [
        "可以调整音乐和音效的音量，重新查看新手引导，查看游戏介绍和隐私说明。"],
        ["s16_设置"]),
]


def build_manual():
    css = PAGE_CSS + """
h1 { font-size: 20pt; text-align: center; margin: 30mm 0 6mm; }
.sub { text-align: center; font-size: 11pt; color: #444; }
h2 { font-size: 13pt; margin: 4mm 0 2mm; }
p { font-size: 10.5pt; line-height: 1.75; text-indent: 2em; margin: 0 0 2mm; }
.shots { display: flex; gap: 6mm; justify-content: center; margin: 3mm 0; }
.shots figure { margin: 0; text-align: center; font-size: 9pt; color: #333; }
.shots img { height: 105mm; border: 1px solid #999; }
"""
    tmp = OUT / "_img"     # 截图先缩小成 jpg，免得 PDF 太大（登记系统对文件大小有限制）
    tmp.mkdir(exist_ok=True)
    for f in SHOTS.glob("s*.png"):
        Image.open(f).convert("RGB").resize((540, 1170), Image.LANCZOS).save(tmp / f"{f.stem}.jpg", quality=82)
    pages = [f'<div class="page"><h1>{NAME}<br>用户手册</h1><div class="sub">版本 {VERSION}</div></div>']
    n = 1
    for title, paras, *shots in MANUAL:
        names = shots[0] if shots else []
        imgs = "".join(f'<figure><img src="{(tmp / (s + ".jpg")).as_uri()}"><figcaption>图：{s.split("_", 1)[1]}</figcaption></figure>'
                       for s in names if (tmp / (s + ".jpg")).exists())
        n += 1
        pages.append(f'<div class="page"><div class="head"><span>{NAME} {VERSION}</span><span>第 {n} 页</span></div>'
                     f'<h2>{title}</h2>{"".join(f"<p>{html.escape(p)}</p>" for p in paras)}'
                     f'{f"<div class=shots>{imgs}</div>" if imgs else ""}</div>')
    src = OUT / "_用户手册.html"
    src.write_text(f"<!doctype html><meta charset='utf-8'><style>{css}</style>{''.join(pages)}", "utf-8")
    print_pdf(src, OUT / "软著-用户手册.pdf")
    src.unlink()
    shutil.rmtree(tmp)
    print(f"用户手册：{n} 页")


# ---------------- 图标和截图 ----------------
def build_icon():
    size = 512
    im = Image.new("RGB", (size, size))
    d = ImageDraw.Draw(im)
    for y in range(size):   # 暖色渐变底
        t = y / size
        d.line([(0, y), (size, y)], fill=(int(70 + 40 * (1 - t)), int(38 + 20 * (1 - t)), int(24 + 6 * (1 - t))))
    chest = Image.open(ART / "gift_big.png").convert("RGBA")
    k = 400 / max(chest.size)
    chest = chest.resize((round(chest.width * k), round(chest.height * k)), Image.LANCZOS)
    im.paste(chest, ((size - chest.width) // 2, (size - chest.height) // 2 + 10), chest)
    im.save(OUT / "图标-512.png")
    im.resize((144, 144), Image.LANCZOS).save(OUT / "图标-144.png")


STORE_SHOTS = ["s01_启动页", "s03_大本营", "s07_收货", "s08_揭穿骗子", "s06_员工汇报", "s13_抽造型", "s14_收藏图鉴"]


def copy_shots():
    dst = OUT / "截图"
    dst.mkdir(exist_ok=True)
    for i, s in enumerate(STORE_SHOTS, 1):
        src = SHOTS / f"{s}.png"
        if src.exists():
            Image.open(src).convert("RGB").save(dst / f"{i:02d}-{s.split('_', 1)[1]}.jpg", quality=90)
    print(f"截图：{len(list(dst.glob('*.jpg')))} 张")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    build_source()
    build_manual()
    build_icon()
    copy_shots()


if __name__ == "__main__":
    main()
