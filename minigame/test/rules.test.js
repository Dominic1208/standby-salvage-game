// 游戏规则的单元测试。由 test/run.mjs 打包后用 node --test 跑（平台层换成 fake-platform.js，随机数固定种子）。
import test from "node:test";
import assert from "node:assert/strict";
import * as S from "../src/state.js";
import { advanceTime, storage } from "./fake-platform.js";

const { G, tuning, meta, staffData, gifts } = S;

// 固定种子的随机数：每次跑结果都一样
function seed(n) {
  let s = n >>> 0;
  Math.random = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}

/** 每个测试开头调用：清空存档，回到第一天。 */
function fresh(n = 1) {
  seed(n);
  storage.clear();
  Object.assign(G, {
    day: 1, cash: tuning.start_cash, rep: 0, inventory: [], timeLeft: tuning.time_per_day, orderTag: "",
    runState: "playing", emergencyUsed: false, extraDue: {}, collection: {}, giftQueue: [], giftsToday: 0, intel: 0, lastDaily: "",
    staff: [], upgrades: {}, skins: {}, stats: {}, ach: {}, deal: null, dealOpen: false, result: null, achToasts: [],
  });
  S.newPlayer();
  G.giftQueue = [];
  S.startDay();
}

/** 换顾客，直到满足条件（换的时候不耗营业时间）。 */
function customerWhere(fn) {
  for (let i = 0; i < 200; i++) {
    if (G.deal && fn(G.deal)) return G.deal;
    G.timeLeft = 99;
    S.nextCustomer();
  }
  throw new Error("200 位顾客里没有符合条件的");
}

test("新玩家：送 4 个造型、2 名员工、造型不重复", () => {
  fresh();
  assert.equal(Object.keys(G.skins).length, 4);
  assert.equal(G.staff.length, staffData.start_staff);
  assert.equal(new Set(G.staff.map((s) => s.look)).size, G.staff.length);
});

test("揭穿骗子：要价降到真实价值附近，按要价收不会亏太多", () => {
  for (let n = 1; n <= 30; n++) {
    fresh(n);
    const d = customerWhere((x) => x.lying);
    S.revealClue(d.clues.findIndex((c) => c.isLie));
    const r = S.challenge();
    assert.equal(r.mood, "caught");
    assert.ok(d.ask <= Math.max(10, Math.round(d.trueValue * tuning.exposed_ask_ratio / 10) * 10),
      `要价 ${d.ask}，真实价值 ${d.trueValue}`);
    G.cash = 99999;
    S.takeAsk();
    // 四舍五入到 10 元，最多亏 10 元以内
    assert.ok(d.trueValue - d.ask >= -10, `揭穿后按要价收还亏 ${d.ask - d.trueValue}`);
  }
});

test("质疑诚实的顾客会掉耐心，不会揭穿", () => {
  fresh(3);
  const d = customerWhere((x) => !x.lying);
  const before = d.patience;
  const r = S.challenge();
  assert.equal(r.mood, "honest");
  assert.ok(d.patience < before);
  assert.equal(d.exposed, false);
});

test("出价不低于底价一定成交，钱和仓库都对", () => {
  fresh(5);
  const d = customerWhere(() => true);
  G.cash = 99999;
  G.offer = d.minPrice;
  const cash = G.cash;
  assert.equal(S.makeOffer(), "accept");
  assert.equal(G.cash, cash - d.minPrice);
  assert.equal(G.inventory.length, 1);
  assert.ok(G.result && G.result.title === "成交");
});

test("打烊：货卖给收购商，订单类别多卖", () => {
  fresh(7);
  G.inventory = [{ name: "甲", paid: 100, value: 200, tag: "电子" }, { name: "乙", paid: 50, value: 100, tag: "古董" }];
  G.orderTag = "电子";
  G.timeLeft = 0;
  const cash = G.cash;
  S.nextCustomer();   // 时间不够 → 打烊
  const expect = Math.round(200 * tuning.order_bonus) + 100;
  assert.equal(G.cash, cash + expect);
  assert.equal(G.inventory.length, 0);
  assert.equal(G.runState, "day_end");
  assert.equal(G.day, 2);
});

test("第 3 天还贷：钱够就扣，钱不够店被收走", () => {
  fresh(9);
  const due = tuning.loan_due["3"];
  G.day = 3; G.cash = due + 100; G.inventory = []; G.timeLeft = 0;
  S.nextCustomer();
  assert.equal(G.runState, "day_end");
  assert.equal(G.cash, 100);

  fresh(9);
  G.day = 3; G.cash = due - 1; G.inventory = []; G.timeLeft = 0;
  S.nextCustomer();
  assert.equal(G.runState, "lost");
});

test("撑过最后一天就赢；升级和员工保留", () => {
  fresh(11);
  G.upgrades.lens = 1;
  G.day = tuning.run_days; G.cash = 99999; G.inventory = []; G.timeLeft = 0;
  S.nextCustomer();
  assert.equal(G.runState, "won");
  S.resultNext();   // 再开一局
  assert.equal(G.day, 1);
  assert.equal(G.upgrades.lens, 1);
  assert.equal(G.staff.length, staffData.start_staff);
});

test("破产：第一次借应急款，第二次就关门", () => {
  fresh(13);
  G.cash = 10; G.inventory = [];
  G.result = { title: "成交" };
  S.resultNext();
  assert.equal(G.runState, "bankrupt");
  S.resultNext();   // 借
  assert.equal(G.emergencyUsed, true);
  assert.equal(G.cash, 10 + tuning.emergency_loan);
  G.cash = 10; G.inventory = [];
  G.result = { title: "成交" };
  S.resultNext();
  assert.equal(G.runState, "lost");
});

test("员工出门：按真实时间回来，带着汇报和包裹", () => {
  fresh(15);
  const s = G.staff[0], place = staffData.places[1];
  S.sendStaff(s, place);
  assert.equal(S.tickStaff().length, 0);
  advanceTime(S.tripMinutes(place) * 60000 + 1000);
  const back = S.tickStaff();
  assert.deepEqual(back.map((x) => x.id), [s.id]);
  assert.equal(s.status, "back");
  assert.ok(s.report.length > 10);
  S.finishReport(s);
  assert.equal(s.status, "idle");
  assert.equal(G.giftQueue.length, 1);
});

test("每天的包裹有上限", () => {
  fresh(17);
  for (let i = 0; i < gifts.daily_cap + 5; i++) S.addGift("small");
  assert.equal(G.giftQueue.length, gifts.daily_cap);
});

test("拆包裹：每种结果都能拆，收藏品记进图鉴", () => {
  fresh(19);
  for (let i = 0; i < 300; i++) {
    G.giftQueue = [["small", "big", "weird"][i % 3]];
    const r = S.openGift();
    assert.ok(r && r.title && r.body);
  }
  assert.ok(Object.keys(G.collection).length > 10);
});

test("抽造型：十连扣对钱、重复的退钱、概率表加起来是 100%", () => {
  fresh(21);
  G.cash = 99999;
  const before = G.cash;
  const res = S.draw(10);
  assert.equal(res.length, 10);
  const refund = res.reduce((s, r) => s + r.refund, 0);
  assert.equal(G.cash, before - meta.gacha.ten_cost + refund);
  const total = meta.gacha.rarities.reduce((s, r) => s + r.weight, 0);
  assert.equal(total, 100);
  G.cash = 0;
  assert.equal(S.draw(1), null);
});

test("升级：钱够才能买，满级买不了", () => {
  fresh(23);
  const u = meta.upgrades[0];
  G.cash = 0;
  assert.equal(S.buyUpgrade(u.id), false);
  G.cash = 999999;
  for (let i = 0; i < u.levels.length; i++) assert.equal(S.buyUpgrade(u.id), true);
  assert.equal(S.buyUpgrade(u.id), false);
});

test("存档读档：关掉再开，进度还在", () => {
  fresh(25);
  G.cash = 4321; G.day = 4; G.collection = { abc: 2 };
  S.save();
  G.cash = 0; G.day = 1; G.collection = {};
  assert.equal(S.load(), true);
  assert.equal(G.cash, 4321);
  assert.equal(G.day, 4);
  assert.equal(G.collection.abc, 2);
});

test("成就：达到目标就解锁，只解锁一次", () => {
  fresh(27);
  const a = meta.achievements.find((x) => x.stat === "deals" && x.goal === 1);
  S.bump("deals");
  assert.ok(G.ach[a.id]);
  const n = G.achToasts.length;
  S.bump("deals");
  assert.equal(G.achToasts.length, n);
});

test("员工等级：探险次数够了就升级，等级越高越容易带大包裹", () => {
  fresh(29);
  const s = G.staff[0];
  assert.equal(S.staffLevel(s).title, staffData.levels[0].title);
  for (let i = 0; i < staffData.levels[1].trips; i++) { s.report = "x"; S.finishReport(s); }
  assert.equal(S.staffLevel(s).title, staffData.levels[1].title);
  const last = staffData.levels[staffData.levels.length - 1];
  s.trips = last.trips;
  assert.equal(S.staffLevel(s), last);
  assert.ok(last.big_chance > staffData.levels[1].big_chance);
});

test("每日包裹：一天只给一次", () => {
  fresh(31);
  const n = G.giftQueue.length;
  assert.ok(S.dailyGift("2026-11-01"));
  assert.equal(S.dailyGift("2026-11-01"), null);
  assert.ok(S.dailyGift("2026-11-02"));
  assert.equal(G.giftQueue.length, n + 2);
});
