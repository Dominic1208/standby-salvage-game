"""把解说稿合成讲解视频（横版 1920x1080；加 --vertical 出竖版 1080x1920，发抖音/视频号用；30 帧）。

用法：
  python tools/video/tts.py          # 先配音
  python tools/video/make_video.py   # 再合成  →  devlog/video/待机回收站-讲解.mp4

画面用 Pillow 一帧帧画，直接喂给 ffmpeg：手机框截图、大标题、要点、示意图、字幕。
layout 为 clip 的画面放实机录屏（src/dev/demo.gd 用 Godot Movie Maker 录的，片段起点在 clips.txt）。
"""

import json
import re
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
GAME = ROOT / "build_tmp" / "video" / "game"     # 实机录屏 demo.avi + clips.txt
OUT_DIR = ROOT / "devlog" / "video"
W, H, FPS = 1920, 1080, 30
VERTICAL = "--vertical" in sys.argv
if VERTICAL:
    W, H = 1080, 1920
GAP = 0.35          # 每句之间的停顿（秒）
SCENE_PAD = 0.6     # 每段结束多停一会
FADE = 0.3          # 画面切换的交叉淡化（秒）
VOICE_GAIN = 1.3    # 配音音量（真人原声已经修过音、响度够了，脚本里会设成 1.0）

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
        # 英文单词（Claude、GitHub…）整个当一个单位，不在中间断开
        for ch in re.findall(r"[A-Za-z0-9.\-]+|.", para):
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
    if VERTICAL:
        return render_v(frame)
    c = BG.convert("RGBA").copy()
    d = ImageDraw.Draw(c)
    lay = frame["layout"]
    if lay == "title":
        if frame.get("phones"):
            place_phones(c, frame["phones"], (1180, 60, 1840, 900))
        d.text((140, 330), frame["title"], font=font(150, True), fill=C_PINK)
        for i, line in enumerate(wrap(d, frame.get("sub", ""), font(50), 960)):
            d.text((146, 560 + i * 72), line, font=font(50), fill=C_TEXT)
    elif lay == "clip":
        frame["_slot"] = place_clip(c, (60, 50, 1040, 900))
        head_and_points(c, 1080, 170, W - 1080 - 120, frame.get("head", ""), frame.get("points"))
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


# ---------------- 实机录屏 ----------------
def place_clip(canvas, area):
    """在 area 里放一个空手机框，返回录屏要贴进去的位置 (x, y, w, h, mask)。"""
    x0, y0, x1, y1 = area
    vw, vh = CLIP_SIZE
    h = int(min(y1 - y0 - 40, (x1 - x0 - 68) * vh / vw))
    sw = int(h * vw / vh) // 2 * 2
    ph = phone(Image.new("RGB", (sw, h)), h)
    px, py = int(x0 + (x1 - x0 - ph.width) / 2), int(y0 + (y1 - y0 - ph.height) / 2)
    canvas.alpha_composite(ph, (px, py))
    mask = Image.new("L", (sw, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, sw, h), 32, fill=255)
    return (px + 34, py + 34, sw, h, mask)


CLIP_SIZE = (640, 1386)
CLIP_AT = {}


def load_clips():
    global CLIP_SIZE
    for line in (GAME / "clips.txt").read_text("utf-8").splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] == "CLIP":
            CLIP_AT[parts[1]] = float(parts[2])
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", str(GAME / "demo.avi")], capture_output=True, text=True).stdout
    CLIP_SIZE = tuple(int(v) for v in out.strip().split(","))


class ClipReader:
    """按顺序从 demo.avi 读一段，缩放到手机框里的大小。读到头就停在最后一帧。"""

    def __init__(self, start, w, h):
        self.w, self.h, self.n, self.last = w, h, 0, None
        self.p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, start):.3f}", "-i", str(GAME / "demo.avi"),
                                   "-vf", f"scale={w}:{h}:flags=lanczos", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                  stdout=subprocess.PIPE)

    def at(self, t):
        want = int(t * FPS)
        while self.n <= want:
            buf = self.p.stdout.read(self.w * self.h * 3)
            if len(buf) < self.w * self.h * 3:
                break
            self.last = Image.frombytes("RGB", (self.w, self.h), buf)
            self.n += 1
        return self.last

    def close(self):
        self.p.kill()


# ---------------- 竖版画面 ----------------
def head_v(c, head, points, y=150):
    d = ImageDraw.Draw(c)
    for line in wrap(d, head, font(76, True), 960):
        d.text((W / 2, y), line, font=font(76, True), fill=C_NEON, anchor="mt")
        y += 96
    if points:
        y += 6
        for line in wrap(d, "　·　".join(points), font(40), 960):
            d.text((W / 2, y), line, font=font(40), fill=C_TEXT, anchor="mt")
            y += 56
    return y


def render_v(frame):
    c = BG.convert("RGBA").copy()
    d = ImageDraw.Draw(c)
    lay = frame["layout"]
    if lay == "title":
        d.text((W / 2, 230), frame["title"], font=font(140, True), fill=C_PINK, anchor="mt")
        y = 420
        for line in wrap(d, frame.get("sub", ""), font(48), 940):
            d.text((W / 2, y), line, font=font(48), fill=C_TEXT, anchor="mt")
            y += 68
        if frame.get("phones"):
            place_phones(c, frame["phones"][:2], (90, y + 30, W - 90, 1440))
    elif lay in ("phones", "clip"):
        y = head_v(c, frame.get("head", ""), frame.get("points"))
        area = (60, y + 10, W - 60, 1440)
        if lay == "clip":
            frame["_slot"] = place_clip(c, area)
        else:
            names = frame["phones"]
            if len(names) == 3:   # 竖屏放三部太小：只放前两部
                names = names[:2]
            place_phones(c, names, area)
    elif lay == "card":
        has_body = frame.get("code") or frame.get("big")
        y = 520 if has_body else 760
        for line in wrap(d, frame["head"], font(84, True), 960):
            d.text((W / 2, y), line, font=font(84, True), fill=C_NEON, anchor="mt")
            y += 110
        y += 40
        if frame.get("big"):
            for line in wrap(d, frame["big"], font(96, True), 960):
                d.text((W / 2, y), line, font=font(96, True), fill=C_TEXT, anchor="mt")
                y += 124
            y += 30
        if frame.get("code"):
            lines = frame["code"].split("\n")
            fcode = font(46)
            lh = 70
            cw = min(1000, max(text_w(d, l, fcode) for l in lines) + 100)
            ch = len(lines) * lh + 80
            x = (W - cw) / 2
            d.rounded_rectangle((x, y, x + cw, y + ch), 28, fill=(22, 18, 15), outline=(90, 74, 62), width=3)
            for i, l in enumerate(lines):
                d.text((x + 50, y + 40 + i * lh), l, font=fcode, fill=C_TEXT)
    else:
        raise SystemExit(f"竖版还不支持这种画面：{lay}")
    d.text((W / 2, 70), "待机回收站", font=font(34, True), fill=C_PINK, anchor="mt")
    return c.convert("RGB")


def subtitle(img, s):
    d = ImageDraw.Draw(img, "RGBA")
    if VERTICAL:   # 竖版：字幕放在画面下方三分之一，避开抖音底部的按钮和文案
        f = font(58, True)
        y = 1500
        for line in wrap(d, s, f, 940):
            d.text((W / 2, y), line, font=f, fill=(255, 255, 255), anchor="mt", stroke_width=6, stroke_fill=(0, 0, 0))
            y += 78
        return img
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
    name = sys.argv[sys.argv.index("--script") + 1] if "--script" in sys.argv else "script.json"
    script = json.loads((HERE / name).read_text("utf-8"))
    global GAP, SCENE_PAD, VOICE_GAIN
    GAP = script.get("gap", GAP)
    SCENE_PAD = script.get("scene_pad", SCENE_PAD)
    VOICE_GAIN = script.get("voice_gain", VOICE_GAIN)
    durations = json.loads((VOICE / "durations.json").read_text("utf-8"))
    BG = make_background()
    if any(fr != "same" and fr["layout"] == "clip" for sc in script["scenes"] for fr in sc["frames"]):
        load_clips()
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

    silent = OUT_DIR / ("_video_v.mp4" if VERTICAL else "_video.mp4")
    if "--audio-only" in sys.argv and silent.exists():
        mux(segs, total, silent)
        return
    proc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
                             "-crf", "20", "-pix_fmt", "yuv420p", str(silent)], stdin=subprocess.PIPE)
    n_frames = int(total * FPS)
    si = 0
    reader, reader_for = None, None
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
        fr = s["frame"]
        if fr["layout"] == "clip":   # 实机录屏：每帧把录屏贴进手机框
            if reader_for is not fr:
                if reader:
                    reader.close()
                reader, reader_for = ClipReader(CLIP_AT[fr["clip"]] + fr.get("offset", 0.0), *fr["_slot"][2:4]), fr
            shot = reader.at(tt - segs[g0]["start"])
            if shot is not None:
                img = img.copy()
                img.paste(shot, fr["_slot"][:2], fr["_slot"][4])
            zoom = 1.0   # 录屏本身在动，不再推镜头
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
        filters.append(f"[{i + 1}:a]adelay={ms}|{ms},volume={VOICE_GAIN}[v{i}]")   # 第 0 路输入是画面
    n = len(segs)
    bgm = ROOT / "web" / "audio" / "bgm_shop.mp3"
    door = ROOT / "web" / "audio" / "sfx_door.wav"
    inputs += ["-stream_loop", "-1", "-i", str(bgm), "-i", str(door)]
    filters.append(f"[{n + 1}:a]volume=0.10,atrim=0:{total:.2f},afade=t=out:st={total - 2:.2f}:d=2[bgm]")
    filters.append(f"[{n + 2}:a]adelay=200|200,volume=0.6[door]")
    mix = "".join(f"[v{i}]" for i in range(n)) + "[bgm][door]"
    filters.append(f"{mix}amix=inputs={n + 2}:normalize=0,alimiter=limit=0.89,atrim=0:{total:.2f}[a]")
    out = OUT_DIR / (("待机回收站-口播" if "script_self" in " ".join(sys.argv) else "待机回收站-讲解")
                     + ("-竖版" if VERTICAL else "") + ".mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), *inputs,
                    "-filter_complex", ";".join(filters), "-map", "0:v", "-map", "[a]",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)], check=True)
    if "--keep" not in sys.argv:
        silent.unlink()
    print(f"完成：{out}  ({out.stat().st_size // 1024 // 1024} MB)")


if __name__ == "__main__":
    main()
