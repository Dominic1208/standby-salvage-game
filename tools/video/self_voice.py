"""把作者自己录的口播接进视频：修音 → 按句切开（去掉念错和重录的部分）→ 换成字幕 → 交给 make_video.py。

用法：python tools/video/self_voice.py <录音文件>
然后：python tools/video/make_video.py

CUTS 里每句：(开始秒, 结束秒, 字幕, 画面)。时间来自逐字时间戳（voice_words.py），字幕按实际说的话、改掉识别错字。
画面写 "same" 沿用上一句；其他写成 "场景id:第几句"，引用 script.json 里口播版的画面。
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
from tts import voice_name  # noqa: E402

VOICE = ROOT / "build_tmp" / "video" / "voice"
WORK = ROOT / "build_tmp" / "video" / "myrec"
VOICE_ID = "self:zhuzi-v3"

# 口播修音：去低频浑浊、提 2-5k 清晰度和“往前冲”的感觉、加空气感、压缩得紧一点让每个字都饱满、去齿音、
# 响度到短视频常用的 -14 LUFS
# aexciter 给高频补一点泛音，声音更“亮”、更透，不只是把高音调大
FX = ("highpass=f=100,afftdn=nr=10:nf=-50,"
      "equalizer=f=200:t=q:w=1:g=-2,equalizer=f=350:t=q:w=1:g=-5,"
      "equalizer=f=2800:t=q:w=1:g=4,equalizer=f=5000:t=q:w=1.2:g=4,equalizer=f=8000:t=q:w=1.5:g=3,"
      "treble=g=4:f=10000,aexciter=amount=2:drive=6:freq=4500:blend=0,"
      "acompressor=threshold=-24dB:ratio=4:attack=5:release=80:makeup=4,deesser=i=0.6,"
      "loudnorm=I=-14:TP=-1.2:LRA=5")
TEMPO = 1.10   # 快一点，口播更有精神
PITCH = 1.04   # 音调抬高一点点（约 0.7 个半音，保留共振峰，不会变成“小黄人”），声音不那么低沉

CUTS = [
    # 开头钩子
    ("k_hook", [(2.0, 4.3, "这个游戏，我一行代码都没写。", "k_hook:0"),
                (5.05, 9.6, "代码、画面、音乐，全是 AI 搞的。我就动动嘴，一天就做完了。", "k_hook:1")]),
    ("k_hi", [(9.95, 11.5, "哈喽，大家好，我是竹子。", "k_hi:0")]),
    ("k_pain", [(12.35, 15.2, "你要是用 AI 写代码，肯定有遇到过这种事。", "k_pain:0"),
                (15.45, 17.6, "你让它干活，它干到一半，停了。", "k_pain:1"),
                (17.85, 20.15, "弹个框问你：这个命令，我能跑吗？", "k_pain:2"),
                (20.75, 22.65, "你不在电脑前，它就一直等着。", "k_pain:3"),
                (22.95, 29.0, "有的时候我去倒个水，或者去刷个抖音，回来一看，它已经干等了半个小时了。", "k_pain:4")]),
    ("k_fix", [(29.75, 32.7, "所以我干脆做了个游戏，叫《待机回收站》。", "k_fix:0"),
               (32.95, 36.0, "AI 在电脑上干活，我在手机上开回收站。", "k_fix:1"),
               (36.4, 39.15, "它要我拍板的时候，店门一推，进来一个员工：", "k_fix:2"),
               (39.35, 40.95, "“老板，这事儿得你点头。”", "same"),
               (41.0, 43.75, "我手指一划，那边 AI 接着干，完事了。", "k_fix:3")]),
    ("k_feat", [(44.55, 46.55, "每个 AI 对话，就是一个员工。", "k_feat:0"),
                (46.95, 50.65, "橙围巾的是 Claude，蓝色的是 DeepSeek，白色的是 Codex。", "same"),
                (51.1, 55.5, "活干完了，员工还会回来，继续跟我汇报，顺手帮我带个包裹。", "k_feat:1"),
                (56.05, 59.95, "你可能会担心：玩着玩着手一划，会不会批到不该批的？", "k_feat:2"),
                (60.15, 63.45, "放心，批准的卡片跟游戏是完全分开的。", "k_feat:3"),
                (63.75, 66.2, "其实你不理它，它也不会自己放行。", "same")]),
    ("k_game", [(69.95, 73.75, "当你不等 AI 的时候，它就是个正经的经营游戏。", "k_game:0"),
                (74.15, 76.4, "顾客来卖东西，你得验货、砍价，", "k_game:1"),
                (76.45, 79.25, "你还得防着点，因为有人会编故事坑你。", "k_game:2"),
                (79.75, 83.1, "你戳穿了他呢，他就只能乖乖地按实价卖。", "k_game:3"),
                (83.1, 86.35, "赚了钱，升级店铺，抽员工的皮肤，", "k_game:4"),
                (86.55, 89.6, "我还在包裹里隐藏了一千多件收藏品。", "same")]),
    # 结尾用第二遍（第一遍在 90-100 秒，念到一半重来了）
    ("k_end", [(104.5, 107.85, "想玩的话，代码我全都开源了，链接我放在评论区。", "k_end:0"),
               (108.15, 111.9, "下载、双击、手机扫码，然后连上你的 AI，就可以玩了。", "k_end:1"),
               (112.5, 115.1, "你觉得 AI 做游戏，能做到什么程度？", "k_end:2"),
               (116.95, 118.75, "我是竹子，我们下期再见。", "k_end:3")]),
]

# 换掉口播稿里的画面：(段, 第几句) → 画面。clip 是 src/dev/demo.gd 录的实机片段，offset 是从片段开头往后几秒；
# terminal 是画出来的终端窗口（AI 干活、停下来问你）；collage 是“谁做了什么”配真实的美术图
def clip(name, head, offset=0.0, points=None):
    return {"layout": "clip", "clip": name, "offset": offset, "head": head, "points": points or []}


GAME_FOOTAGE = {
    ("k_hook", 0): clip("expose", "一行代码都没写", -0.3),
    ("k_fix", 0): clip("home", "待机回收站", 0.0, ["回收站经营游戏", "也是电脑上 AI 的遥控器"]),
    ("k_fix", 1): "same",
    ("k_feat", 2): clip("gift", "回来汇报，顺手带个包裹"),
    ("k_game", 0): clip("shop", "验货 · 砍价 · 揭穿骗子", 0.0, ["什么都收的回收站"]),
    ("k_game", 1): "same",
    ("k_game", 2): "same",
    ("k_game", 3): "same",
    ("k_game", 4): clip("gacha", "升级店铺 · 抽员工皮肤"),
    ("k_game", 5): clip("book", "1000 多件收藏品"),
    # 原来只有几行字的画面
    ("k_hook", 1): {"layout": "collage", "head": "全是 AI 做的"},
    ("k_pain", 0): {"layout": "terminal", "head": "它干活，你干等", "state": "work"},
    ("k_pain", 1): "same",
    ("k_pain", 2): {"layout": "terminal", "head": "它还停下来问你", "state": "ask"},
    ("k_pain", 3): {"layout": "terminal", "head": "你不在电脑前？", "state": "wait", "badge": "等待你的确认…"},
    ("k_pain", 4): {"layout": "terminal", "head": "它干等了半小时", "state": "wait", "badge": "已等待 32:07"},
    ("k_feat", 3): {"layout": "phones", "phones": ["approve_card"], "head": "手一滑批错了？", "points": ["不会"]},
    ("k_end", 1): {"layout": "image", "image": "10-电脑设置页-扫码和连接AI", "head": "想玩？三步",
                   "points": ["GitHub 下载，解压，双击", "手机连同一个 Wi-Fi，扫码", "点一下“连接你的 AI”"]},
    ("k_end", 2): clip("home", "AI 做游戏，能做到什么程度？", 0.5),
}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    src = Path(sys.argv[1])
    WORK.mkdir(parents=True, exist_ok=True)
    VOICE.mkdir(parents=True, exist_ok=True)
    fixed = WORK / "rec_fixed.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", FX, "-ac", "1", "-ar", "48000", str(fixed)],
                   check=True)

    script_path = HERE / "script.json"
    script = json.loads(script_path.read_text("utf-8"))
    frames = {sc["id"]: sc["frames"] for sc in script["scenes"]}

    def frame(ref):
        if ref == "same":
            return "same"
        sid, i = ref.split(":")
        f = frames[sid][int(i)]
        return f

    durations = {}
    scenes = []
    for sid, cuts in CUTS:
        sc = {"id": f"self_{sid}", "chapter": "", "lines": [], "frames": []}
        for i, (a, b, text, ref) in enumerate(cuts):
            out = VOICE / voice_name(sc["id"], i, text, VOICE_ID)
            # 每句前后留一点点气口，淡入淡出 30 毫秒免得切口“咔”一声
            fade = f"afade=t=in:d=0.03,afade=t=out:st={(b - a) / TEMPO - 0.04:.3f}:d=0.04"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a:.2f}", "-to", f"{b:.2f}", "-i", str(fixed),
                            "-af", f"rubberband=tempo={TEMPO}:pitch={PITCH}:formant=preserved,{fade}", "-ar", "44100", "-b:a", "192k", str(out)], check=True)
            durations[out.name] = (b - a) / TEMPO
            sc["lines"].append(text)
            sc["frames"].append(GAME_FOOTAGE.get((sid, i)) or frame(ref))
        scenes.append(sc)

    dur_file = VOICE / "durations.json"
    old = json.loads(dur_file.read_text("utf-8")) if dur_file.exists() else {}
    old.update(durations)
    dur_file.write_text(json.dumps(old, ensure_ascii=False, indent=1), "utf-8")
    # 口播版脚本另存一份，make_video 用它出片
    script["scenes"] = scenes
    script["voice"] = VOICE_ID
    script["gap"] = 0.08          # 句子之间收紧：口播节奏快
    script["scene_pad"] = 0.3
    script["voice_gain"] = 1.0    # 已经修过音、响度够了
    (HERE / "script_self.json").write_text(json.dumps(script, ensure_ascii=False, indent=1), "utf-8")
    total = sum(durations.values())
    print(f"{sum(len(c) for _, c in CUTS)} 句，原声共 {total:.0f} 秒")


if __name__ == "__main__":
    main()
