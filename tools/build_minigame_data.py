"""小游戏版的数据：从电脑版 src/data/*.json 复制一份，按微信/抖音的审核规范清理，输出到 minigame/build/data/。

平台规范（抖音《小游戏备案审核规范》、微信同类要求）里和我们有关的几条：
- 不能出现封建迷信（算命、开光、画符、塔罗……）→ 删掉相关的顾客、货物、故事和收藏品，“开光款”改名“限定款”；
- 游戏内不用英文 → 把台词里的英文词换成中文；
- 小游戏版没有“连接 AI”，所以“AI 员工”一类说法也换掉。
电脑版的数据不动。

用法：python tools/build_minigame_data.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "data"
MINI = ROOT / "minigame" / "data"
OUT = ROOT / "minigame" / "build" / "data"

SUPERSTITION = re.compile(r"算命|风水|护身符|退散符|画符|符咒|开光|鬼|冥婚|作法|驱邪|招魂|占卜|塔罗|转运|辟邪|神婆|半仙|灵异|"
                          r"诅咒|求签|算卦|水逆|锦鲤|木鱼|玄学|八字|上香|财神|道士|僵尸")
# 按顺序替换；长的放前面
REPLACE = [
    ("开光款", "限定款"),
    ("去 city 一下", "去城里逛逛"),
    ("MBTI 测出来我是 I 人", "性格测试测出来我是内向型"),
    ("刻着 Au750", "刻着足金印记"),
    ("刻着 S925", "刻着纯银印记"),
    ("刻着「GP」，是镀金", "刻着一个“镀”字，是镀金"),
    ("up 主", "博主"),
    ("DIY 热情", "手工热情"),
    ("「高仿 A 货」", "「高仿货」"),
    ("「Made in 小商品城」", "「产自小商品城」"),
    ("HR 周经理", "人事周经理"),
    ("coser 小葵", "扮演爱好者小葵"),
    ("修了个 bug", "修了个小毛病"),
    ("bug 就好了", "毛病就好了"),
    ("AI 员工纪念", "员工纪念"),
    ("AI 员工", "员工"),
    ("是 AI 画的", "是电脑画的"),
    ("U 型颈枕", "护颈枕"),
    ("deadline", "截止日期"),
    ("Token 储蓄罐", "代币储蓄罐"),
    ("Esc 键", "退出键"),
    ("MP3", "随身听"),
    ("CD", "光碟"),
    ("名字是 AAA", "名字印得歪歪扭扭"),
]
# 这些字段是程序用的，不是给玩家看的，不检查也不替换
CODE_KEYS = {"art", "id", "look", "stat", "_doc", "kind", "tint", "type", "color", "rarity", "tag", "leaky", "series_id"}


def fix_text(s: str) -> str:
    for a, b in REPLACE:
        s = s.replace(a, b)
    return s


def clean(o):
    """递归：替换文字；列表里含迷信内容的字符串直接去掉。"""
    if isinstance(o, dict):
        return {k: (v if k in CODE_KEYS else clean(v)) for k, v in o.items()}
    if isinstance(o, list):
        out = []
        for v in o:
            if isinstance(v, str) and SUPERSTITION.search(v):
                continue
            out.append(clean(v))
        return out
    if isinstance(o, str):
        return fix_text(o)
    return o


def visible_strings(o):
    if isinstance(o, dict):
        for k, v in o.items():
            if k not in CODE_KEYS:
                yield from visible_strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from visible_strings(v)
    elif isinstance(o, str) and not o.startswith("#"):
        yield o


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    load = lambda p: json.loads(p.read_text("utf-8"))

    customers = load(SRC / "customers.json")
    customers["archetypes"] = [a for a in customers["archetypes"]
                               if not any(SUPERSTITION.search(n) for n in a.get("names", []))]

    gifts = load(SRC / "gifts.json")
    before = len(gifts["collectibles"])
    kept = []
    for c in gifts["collectibles"]:
        c = clean(c)
        if SUPERSTITION.search(c["name"]) or SUPERSTITION.search(c.get("desc", "")) or SUPERSTITION.search(c.get("series", "")):
            continue
        kept.append(c)
    gifts["collectibles"] = kept

    meta = load(MINI / "meta.json")
    for a in meta["achievements"]:   # 收藏品少了：“收集 1000 件”改成“收集全部”
        if a["stat"] == "collection" and a["goal"] > len(kept):
            a["goal"] = len(kept)
            a["desc"] = f"收集全部 {len(kept)} 件收藏品"

    files = {
        "catalog.json": clean(load(SRC / "catalog.json")),
        "customers.json": clean(customers),
        "personalities.json": clean(load(SRC / "personalities.json")),
        "gifts.json": clean(gifts),
        "tuning.json": load(SRC / "tuning.json"),
        "staff.json": clean(load(MINI / "staff.json")),
        "meta.json": clean(meta),
        "ads.json": load(MINI / "ads.json"),
    }
    problems = []
    for name, data in files.items():
        (OUT / name).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), "utf-8")
        for s in visible_strings(data):
            t = re.sub(r"\{\w+\}", "", s)
            if SUPERSTITION.search(t):
                problems.append(f"{name}: 迷信？ {s[:40]}")
            elif re.search(r"[A-Za-z]", t) and name not in ("ads.json",) and not re.fullmatch(r"adv_\d+|small|big|weird|[a-z_]+", t):
                problems.append(f"{name}: 英文？ {s[:40]}")
    print(f"收藏品 {before} → {len(kept)}；顾客类型 {len(customers['archetypes'])} 种")
    if problems:
        print("还要处理：")
        for p in problems[:40]:
            print("  ", p)
    else:
        print("检查通过：没有迷信内容，没有英文台词")


if __name__ == "__main__":
    main()
