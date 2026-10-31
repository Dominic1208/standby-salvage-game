"""把解说稿合成讲解视频（1920x1080，30 帧）。

用法：
  python tools/video/tts.py          # 先配音
  python tools/video/make_video.py   # 再合成  →  devlog/video/待机回收站-讲解.mp4

画面用 Pillow 一帧帧画，直接喂给 ffmpeg：手机框截图、大标题、要点、示意图、字幕。
"""

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from tts import voice_name

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
VOICE = ROOT / "build_tmp" / "video" / "voice"
SHOTS = ROOT / "build_tmp" / "video" / "shots"
SCREENS = ROOT / "devlog" / "screens"
OUT_DIR = ROOT / "devlog" / "video"
W, H, FPS = 1920, 1080, 30
GAP = 0.35          # 每句之间的停顿（秒）
SCENE_PAD = 0.6     # 每段结束多停一会
FADE = 0.3          # 画面切换的交叉淡化（秒）

FONT = "C:/Windows/Fonts/msyh.ttc"
FONT_B = "C:/Windows/Fonts/msyhbd.ttc"
MONO = "C:/Windows/Fonts/consola.ttf"
C_NEON, C_PINK, C_TEXT, C_MUTED = (255, 179, 71), (255, 107, 139), (246, 237, 226), (168, 153, 138)
C_PAPER, C_INK = (239, 225, 198), (58, 38, 24)

_fonts = {}


def font(size, bold=False, mono=False):
    key = (size, bold, mono)
    if key not in _fonts:
        path = MONO if mono else (FONT_B if bold else FONT)
        try:
            _fonts[key] = ImageFont.truetype(path, size)
        except OSError:
            _fonts[key] = ImageFont.truetype(FONT, size)
    return _fonts[key]


def load(name):
    for base in (SHOTS, SCREENS):
        for cand in (base / name, base / f"{name}.jpg", base / f"{name}.png"):
            if cand.exists():
                return Image.open(cand).convert("RGB")
    raise SystemExit(f"找不到图片：{name}")


# ---------------- 背景 ----------------
def make_background():
    bg = Image.open(ROOT / "src" / "assets" / "art" / "lounge_bg.png").convert("RGB")
    s = max(W / bg.width, H / bg.height)
    bg = bg.resize((int(bg.width * s), int(bg.height * s)))
    top = (bg.height - H) // 2
    bg = bg.crop(((bg.width - W) // 2, top, (bg.width - W) // 2 + W, top + H))
    bg = bg.filter(ImageFilter.GaussianBlur(18))
    dark = Image.new("RGB", (W, H), (14, 10, 8))
    return Image.blend(bg, dark, 0.78)


BG = None


def text_w(d, s, f):
    return d.textlength(s, font=f)


def wrap(d, s, f, maxw):
    out = []
    for para in s.split("\n"):
        line = ""
        for ch in para:
            # 标点不放在行首：宁可这一行稍微超出一点
            if text_w(d, line + ch, f) > maxw and line and ch not in "，。、；：？！）」』”…":
                out.append(line)
                line = ch
            else:
                line += ch
        out.append(line)
    return out


def phone(img, height):
    """截图放进手机框（圆角 + 黑边 + 阴影），返回 RGBA。"""
    s = height / img.height
    sw, sh = int(img.width * s), height
    shot = img.resize((sw, sh), Image.LANCZOS)
    pad = 14
    fw, fh = sw + pad * 2, sh + pad * 2
    frame = Image.new("RGBA", (fw + 40, fh + 40), (0, 0, 0, 0))
    shadow = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((20, 26, 20 + fw, 26 + fh), 46, fill=(0, 0, 0, 150))
    frame = Image.alpha_composite(frame, shadow.filter(ImageFilter.GaussianBlur(14)))
    d = ImageDraw.Draw(frame)
    d.rounded_rectangle((20, 20, 20 + fw, 20 + fh), 46, fill=(17, 15, 14), outline=(70, 60, 52), width=3)
    mask = Image.new("L", (sw, sh), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, sw, sh), 32, fill=255)
    frame.paste(shot, (20 + pad, 20 + pad), mask)
    return frame


def framed(img, maxw, maxh):
    """横图（电脑截图、美术图）：圆角卡片 + 阴影。"""
    s = min(maxw / img.width, maxh / img.height)
    w, h = int(img.width * s), int(img.height * s)
    pic = img.resize((w, h), Image.LANCZOS)
    out = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((20, 26, 20 + w, 26 + h), 20, fill=(0, 0, 0, 150))
    out = Image.alpha_composite(out, sh.filter(ImageFilter.GaussianBlur(14)))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), 18, fill=255)
    out.paste(pic, (20, 20), mask)
    return out


def head_and_points(canvas, x, y, maxw, head, points):
    d = ImageDraw.Draw(canvas)
    fh = font(58, True)
    for line in wrap(d, head, fh, maxw):
        d.text((x, y), line, font=fh, fill=C_NEON)
        y += 80
    y += 30
    fp = font(40)
    for p in points or []:
        lines = wrap(d, p, fp, maxw - 44)
        d.ellipse((x, y + 20, x + 16, y + 36), fill=C_PINK)
        for i, l in enumerate(lines):
            d.text((x + 40, y), l, font=fp, fill=C_TEXT)
            y += 58
        y += 18
    return y


def place_phones(canvas, names, area):
    """在 area=(x0,y0,x1,y1) 里横排 1~3 部手机，竖图进手机框，横图进卡片。"""
    x0, y0, x1, y1 = area
    imgs = [load(n) for n in names]
    items = []
    for im in imgs:
        if im.width / im.height > 0.75:   # 横图
            items.append(framed(im, (x1 - x0) / len(imgs) - 20, y1 - y0 - 40))
        else:
            items.append(phone(im, int(min(y1 - y0 - 40, 820 if len(imgs) < 3 else 740))))
    total = sum(i.width for i in items) - 30 * (len(items) - 1)
    if total > x1 - x0:   # 太宽就缩小
        k = (x1 - x0) / total
        items = [i.resize((int(i.width * k), int(i.height * k)), Image.LANCZOS) for i in items]
        total = x1 - x0
    x = x0 + (x1 - x0 - total) / 2
    for it in items:
        canvas.alpha_composite(it, (int(x), int(y0 + (y1 - y0 - it.height) / 2)))
        x += it.width - 30


# ---------------- 各种画面 ----------------
def render(frame, chapter):
    c = BG.convert("RGBA").copy()
    d = ImageDraw.Draw(c)
    lay = frame["layout"]
    if lay == "title":
        if frame.get("phones"):
            place_phones(c, frame["phones"], (1180, 60, 1840, 900))
        d.text((140, 330), frame["title"], font=font(150, True), fill=C_PINK)
        for i, line in enumerate(wrap(d, frame.get("sub", ""), font(50), 960)):
            d.text((146, 560 + i * 72), line, font=font(50), fill=C_TEXT)
    elif lay == "phones":
        n = len(frame["phones"])
        right = 1040 if n == 1 else 1180 if n == 2 else 1260
        place_phones(c, frame["phones"], (60, 50, right, 900))
        head_and_points(c, right + 40, 170, W - right - 120, frame.get("head", ""), frame.get("points"))
    elif lay == "image":
        im = framed(load(frame["image"]), 1640, 760)
        c.alpha_composite(im, ((W - im.width) // 2, 200))
        d.text((W / 2, 120), frame["head"], font=font(56, True), fill=C_NEON, anchor="mm")
    elif lay == "compare":
        d.text((W / 2, 110), frame["head"], font=font(62, True), fill=C_NEON, anchor="mm")
        a, b = load(frame["left"]), load(frame["right"])
        wide = a.width / a.height > 2 and b.width / b.height > 2
        if wide:   # 两张横长图：上下排
            ia, ib = framed(a, 1400, 220), framed(b, 1400, 400)
            c.alpha_composite(ia, ((W - ia.width) // 2, 170))
            d.text((W / 2, 170 + ia.height + 14), frame["left_label"], font=font(38), fill=C_MUTED, anchor="mm")
            c.alpha_composite(ib, ((W - ib.width) // 2, 450))
            d.text((W / 2, 450 + ib.height + 14), frame["right_label"], font=font(40, True), fill=C_TEXT, anchor="mm")
        else:
            for k, (im, label) in enumerate(((a, frame["left_label"]), (b, frame["right_label"]))):
                cx = W / 4 + k * W / 2
                it = phone(im, 580) if im.width / im.height <= 0.75 else framed(im, 760, 600)
                c.alpha_composite(it, (int(cx - it.width / 2), 170))
                d.text((cx, 170 + it.height + 18), label, font=font(42, True), fill=C_TEXT if k else C_MUTED, anchor="mm")
            d.text((W / 2, 500), "→", font=font(110, True), fill=C_NEON, anchor="mm")
    elif lay == "diagram":
        d.text((W / 2, 170), frame["head"], font=font(70, True), fill=C_NEON, anchor="mm")
        boxes = frame["boxes"]
        bw, bh, gap = 440, 260, (W - 3 * 440 - 160) / 2
        for i, label in enumerate(boxes):
            x = 80 + i * (bw + gap)
            d.rounded_rectangle((x, 380, x + bw, 380 + bh), 28, fill=(43, 32, 25), outline=C_NEON, width=3)
            lines = label.split("\n")
            d.text((x + bw / 2, 380 + bh / 2 - 30), lines[0], font=font(50, True), fill=C_TEXT, anchor="mm")
            for j, l in enumerate(lines[1:]):
                d.text((x + bw / 2, 380 + bh / 2 + 40 + j * 46), l, font=font(32), fill=C_MUTED, anchor="mm")
            if i < len(boxes) - 1:
                ax = x + bw + gap / 2
                for j, l in enumerate(frame["arrows"][i].split("\n")):
                    d.text((ax, 470 + j * 70), l, font=font(36, True), fill=C_PINK, anchor="mm")
    elif lay == "card":
        d.text((W / 2, 200 if frame.get("code") or frame.get("big") else 500), frame["head"], font=font(70, True),
               fill=C_NEON, anchor="mm")
        y = 330
        if frame.get("big"):
            d.text((W / 2, y + 40), frame["big"], font=font(84, True), fill=C_TEXT, anchor="mm")
            y += 150
        if frame.get("code"):
            lines = frame["code"].split("\n")
            fcode = font(56 if len(lines) <= 4 else 50)
            lh = 84 if len(lines) <= 4 else 72
            cw = max(text_w(d, l, fcode) for l in lines) + 140
            ch = len(lines) * lh + 90
            x = (W - cw) / 2
            d.rounded_rectangle((x, y, x + cw, y + ch), 28, fill=(22, 18, 15), outline=(90, 74, 62), width=3)
            for i, l in enumerate(lines):
                d.text((x + 70, y + 45 + i * lh), l, font=fcode, fill=C_TEXT)
    # 章节标签 + 角标
    if chapter:
        f = font(30, True)
        tw = text_w(d, chapter, f)
        d.rounded_rectangle((W - tw - 90, 34, W - 40, 88), 27, fill=(0, 0, 0, 140), outline=C_NEON, width=2)
        d.text((W - 65 - tw, 44), chapter, font=f, fill=C_NEON)
    d.text((44, 40), "待机回收站", font=font(30, True), fill=C_PINK)
    return c.convert("RGB")


def subtitle(img, s):
    d = ImageDraw.Draw(img, "RGBA")
    f = font(46, True)
    lines = wrap(d, s, f, 1640)
    y = H - 60 - len(lines) * 62
    d.rectangle((0, y - 24, W, H), fill=(0, 0, 0, 120))
    for l in lines:
        d.text((W / 2, y), l, font=f, fill=(255, 255, 255), anchor="mt", stroke_width=5, stroke_fill=(0, 0, 0))
        y += 62
    return img


def main():
    global BG
    sys.stdout.reconfigure(encoding="utf-8")
    script = json.loads((HERE / "script.json").read_text("utf-8"))
    durations = json.loads((VOICE / "durations.json").read_text("utf-8"))
    BG = make_background()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 时间线：每句一段 [开始, 结束]，画面、字幕、配音
    segs, t = [], 0.4
    for sc in script["scenes"]:
        last = None
        for i, line in enumerate(sc["lines"]):
            fr = sc["frames"][i]
            fr = last if fr == "same" else fr
            voice = VOICE / voice_name(sc["id"], i, line.replace("{name}", script["name"]), script["voice"])
            dur = durations[voice.name] + GAP + (SCENE_PAD if i == len(sc["lines"]) - 1 else 0)
            line = line.replace("{name}", script["name"])
            segs.append({"start": t, "end": t + dur, "frame": fr, "chapter": sc.get("chapter", ""), "text": line,
                         "voice": voice, "new": fr is not last})
            last = fr
            t += dur
    total = t + 1.0
    print(f"共 {len(segs)} 句，{total:.0f} 秒")

    # 每个不同的画面只画一次
    cache = {}
    for s in segs:
        key = id(s["frame"])
        if key not in cache:
            cache[key] = render(s["frame"], s["chapter"])
        s["img"] = cache[key]
    print(f"画面 {len(cache)} 张，开始逐帧合成…")

    silent = OUT_DIR / "_video.mp4"
    if "--audio-only" in sys.argv and silent.exists():
        mux(segs, total, silent)
        return
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
                             "-crf", "20", "-pix_fmt", "yuv420p", str(silent)], stdin=subprocess.PIPE)
    n_frames = int(total * FPS)
    si = 0
    for fi in range(n_frames):
        tt = fi / FPS
        while si < len(segs) - 1 and tt >= segs[si + 1]["start"]:
            si += 1
        s = segs[si] if tt >= segs[0]["start"] else segs[0]
        # 同一画面连续多句：从这组的第一句开始慢慢推近
        g0 = si
        while g0 > 0 and not segs[g0]["new"]:
            g0 -= 1
        g1 = si
        while g1 < len(segs) - 1 and not segs[g1 + 1]["new"]:
            g1 += 1
        k = (tt - segs[g0]["start"]) / max(0.1, segs[g1]["end"] - segs[g0]["start"])
        zoom = 1.0 + 0.04 * min(1.0, max(0.0, k))
        img = s["img"]
        cw, ch = W / zoom, H / zoom
        frame = img.crop(((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2)).resize((W, H), Image.BILINEAR)
        # 换画面时交叉淡化
        if s["new"] and si > 0 and tt - s["start"] < FADE:
            prev = segs[si - 1]["img"].resize((W, H))
            frame = Image.blend(prev, frame, (tt - s["start"]) / FADE)
        if tt < 0.4:
            frame = Image.blend(Image.new("RGB", (W, H)), frame, tt / 0.4)
        if tt > total - 0.8:
            frame = Image.blend(frame, Image.new("RGB", (W, H)), min(1, (tt - (total - 0.8)) / 0.8))
        if s["start"] <= tt < s["end"] - 0.05:
            frame = subtitle(frame.copy(), s["text"])
        proc.stdin.write(frame.tobytes())
        if fi % (FPS * 30) == 0:
            print(f"  {tt:.0f} / {total:.0f} 秒")
    proc.stdin.close()
    proc.wait()
    mux(segs, total, silent)


def mux(segs, total, silent):
    # 声音：每句配音按时间放好 + 背景音乐（压低）+ 开头开门声
    inputs, filters = [], []
    for i, s in enumerate(segs):
        inputs += ["-i", str(s["voice"])]
        ms = int((s["start"] + 0.1) * 1000)
        filters.append(f"[{i + 1}:a]adelay={ms}|{ms},volume=1.3[v{i}]")   # 第 0 路输入是画面
    n = len(segs)
    bgm = ROOT / "web" / "audio" / "bgm_shop.mp3"
    door = ROOT / "web" / "audio" / "sfx_door.wav"
    inputs += ["-stream_loop", "-1", "-i", str(bgm), "-i", str(door)]
    filters.append(f"[{n + 1}:a]volume=0.10,atrim=0:{total:.2f},afade=t=out:st={total - 2:.2f}:d=2[bgm]")
    filters.append(f"[{n + 2}:a]adelay=200|200,volume=0.6[door]")
    mix = "".join(f"[v{i}]" for i in range(n)) + "[bgm][door]"
    filters.append(f"{mix}amix=inputs={n + 2}:normalize=0,alimiter=limit=0.89,atrim=0:{total:.2f}[a]")
    out = OUT_DIR / "待机回收站-讲解.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), *inputs,
                    "-filter_complex", ";".join(filters), "-map", "0:v", "-map", "[a]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)], check=True)
    if "--keep" not in sys.argv:
        silent.unlink()
    print(f"完成：{out}  ({out.stat().st_size // 1024 // 1024} MB)")


if __name__ == "__main__":
    main()
