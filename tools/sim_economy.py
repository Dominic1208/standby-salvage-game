"""经济模拟：照 src/deal.gd 的规则跑几万笔交易，看几种打法平均赚多少。

用法：python tools/sim_economy.py
改了 tuning.json / catalog.json / deal.gd 的定价规则后跑一下，确认“认真玩能赚、乱出价会亏”。
"""

import json
import random
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "src" / "data"
T = json.loads((DATA / "tuning.json").read_text("utf-8"))
CAT = json.loads((DATA / "catalog.json").read_text("utf-8"))
ARCH = json.loads((DATA / "customers.json").read_text("utf-8"))["archetypes"]
PERS = json.loads((DATA / "personalities.json").read_text("utf-8"))["types"]


def r10(v):
    return max(10, round(v / 10) * 10)


def mean_mult(variants):
    return max(0.1, sum(float(v[1]) for v in variants) / max(1, len(variants)))


class Deal:
    """deal.gd 的 Python 版（只保留数值部分）。"""

    def __init__(self, rng):
        arch = rng.choice(ARCH)
        self.p = PERS[arch["type"]]
        row = rng.choice(CAT["items"])
        conds = CAT["conditions"]
        cond = rng.choices(conds, weights=[float(c[2]) for c in conds])[0]
        base = max(10, round(float(row[2]) * float(cond[1])))
        self.base = base
        cat = CAT["categories"][row[1]]
        self.lying = rng.random() < min(0.9, max(0.0, T["lie_chance"] * float(self.p["lie_mult"])))
        lie = rng.choice(cat["lies"]) if self.lying else None
        parts = rng.sample(list(cat["parts"].keys()), 3)
        if self.lying and lie["part"] not in parts:
            parts[rng.randrange(3)] = lie["part"]
        value = float(base)
        for part in parts:
            if not (self.lying and part == lie["part"]):
                value *= float(rng.choice(cat["parts"][part])[1])
        for part in parts:
            value /= mean_mult(cat["parts"][part])
        if self.lying:
            value *= float(lie["mult"])
        self.true = max(10, round(value * rng.uniform(0.9, 1.1)))
        greed = rng.uniform(T["greed_min"], T["greed_max"]) + float(self.p["greed_add"])
        self.ask = r10(base * greed)
        floor = rng.uniform(T["min_price_min"], T["min_price_max"]) + float(self.p["floor_add"])
        if self.lying:
            floor *= T["liar_min_factor"]
        self.min = min(r10(self.true * floor), self.ask)
        self.patience = T["patience_start"] * float(self.p["patience_mult"])
        self.rounds = T["haggle_rounds"]

    def expose(self):
        self.min = r10(self.true * T["exposed_floor_ratio"])
        self.ask = max(self.min, r10(self.true * T["exposed_ask_ratio"]))

    def offer(self, amount):
        if amount >= self.min:
            return "accept"
        self.rounds -= 1
        gap = (self.min - amount) / self.min
        self.patience -= T["patience_base_loss"] + T["patience_gap_loss"] * gap
        if self.patience <= 0 or self.rounds <= 0:
            return "leave"
        self.ask = max(r10(max(self.min * T["counter_floor"], (amount + self.ask) / 2)), self.min)
        return "counter"


def haggle(d, ratios):
    """按顺序用几个“成数”出价，返回利润（没谈成为 0）。"""
    for r in ratios:
        price = r10(d.ask * r)
        res = d.offer(price)
        if res == "accept":
            return d.true - price
        if res == "leave":
            return 0
    return 0


STRATEGIES = {
    "乱出价：直接 9 成": lambda d: haggle(d, [0.9]),
    "不看线索：5 成→7 成": lambda d: haggle(d, [0.5, 0.7]),
    "认真：看线索，揭穿骗子后 7 成；老实人 5 成→7 成": None,
    "认真 + 先砍狠：揭穿后 5 成→7 成；老实人 3 成→5 成→7 成": None,
}


def careful(d, aggressive):
    if d.lying:  # 认真看线索的玩家能发现矛盾，揭穿
        d.expose()
        return haggle(d, [0.5, 0.7] if aggressive else [0.7])
    return haggle(d, [0.3, 0.5, 0.7] if aggressive else [0.5, 0.7])


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    n = 20000
    for name, fn in STRATEGIES.items():
        rng = random.Random(42)
        total, losses, deals = 0, 0, 0
        for _ in range(n):
            d = Deal(rng)
            if fn:
                p = fn(d)
            else:
                p = careful(d, "先砍狠" in name)
            total += p
            losses += p < 0
            deals += p != 0
        print(f"{name}：平均每位顾客 ¥{total / n:+.0f}，成交 {deals / n:.0%}，亏本的占 {losses / n:.0%}")


if __name__ == "__main__":
    main()
