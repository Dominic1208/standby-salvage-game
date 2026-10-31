// 数值模拟：用真实的游戏代码，按几种打法各玩几百局，看胜率和每天的钱。
// 用法：node test/run.mjs --balance
// 目标：认真玩的人大多能撑过 7 天；乱出价的人会输。
import * as S from "../src/state.js";
import { storage, advanceTime } from "./fake-platform.js";

const { G, tuning } = S;

function seed(n) {
  let s = n >>> 0;
  Math.random = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}

function fresh(n) {
  seed(n);
  storage.clear();
  Object.assign(G, {
    day: 1, cash: tuning.start_cash, rep: 0, inventory: [], timeLeft: tuning.time_per_day, orderTag: "",
    runState: "playing", emergencyUsed: false, extraDue: {}, collection: {}, giftQueue: [], giftsToday: 0, intel: 0,
    lastDaily: "", staff: [], upgrades: {}, skins: {}, stats: {}, ach: {}, deal: null, dealOpen: false, result: null, achToasts: [],
  });
  S.newPlayer();
  S.startDay();
}

/** 估价：参考价 × 已经看到的线索“比一般好多少”（和游戏算真实价值的方式一样；谎话那条不算）。
 *  玩家看文字就知道是好是坏，这里用倍数代替。 */
const meanMult = (tag, part) => {
  const v = S.catalog.categories[tag].parts[part];
  return Math.max(0.1, v.reduce((s, x) => s + Number(x[1]), 0) / v.length);
};
const estimate = (d) => d.exposed ? d.trueValue
  : d.item.base * d.clues.reduce((m, c) => m * (c.revealed && !c.isLie ? c.mult / meanMult(d.item.tag, c.part) : 1), 1);

const STRATS = {
  // 乱出价：不看线索，直接 9 成
  乱出价(d) { S.quickOffer(0.9); S.makeOffer(); },
  // 随手：不看线索，5 成起，还价就 7 成
  随手(d) { S.quickOffer(0.5); if (S.makeOffer() === "counter") { S.quickOffer(0.7); S.makeOffer(); } },
  // 普通玩家：看一处线索，发现谎话就质疑；3 成 → 5 成 → 7 成，超过估价八成就不要了
  普通(d) {
    S.revealClue(0);
    if (d.clues[0].isLie) S.challenge();
    for (const r of [0.3, 0.5, 0.7]) {
      if (!G.dealOpen) return;
      S.quickOffer(r);
      if (G.offer > estimate(d) * 0.8) return;
      if (S.makeOffer() === "accept") return;
    }
  },
  // 认真：看两处线索，其余同上
  认真(d) {
    S.revealClue(0); S.revealClue(1);
    if (d.clues.some((c) => c.revealed && c.isLie)) S.challenge();
    for (const r of [0.3, 0.5, 0.7]) {
      if (!G.dealOpen) return;
      S.quickOffer(r);
      if (G.offer > estimate(d) * 0.8) return;
      if (S.makeOffer() === "accept") return;
    }
  },
};

const STAT = { customers: 0, buy: 0, profit: 0 };
function play(strat, n, useStaff) {
  fresh(n);
  const days = [];
  for (let guard = 0; guard < 2000; guard++) {
    if (G.result) {
      const st = G.runState;
      if (/打烊|收走|七天/.test(G.result.title)) days.push(G.cash);
      if (st === "won" || st === "lost") return { won: st === "won", days };
      if (st === "bankrupt") { S.resultNext(); continue; }
      // 每天打烊后：派员工出门、收包裹（模拟玩家隔一阵回来看一眼）
      if (useStaff && st === "day_end") {
        for (const s of G.staff) if (s.status === "idle") S.sendStaff(s, S.placesOpen().slice(-1)[0]);
        advanceTime(3 * 3600 * 1000);
        S.tickStaff();
        for (const s of G.staff) if (s.status === "back") { if (s.dilemma) S.answerDilemma(s, false); S.finishReport(s); }
        while (G.giftQueue.length) S.openGift();
      }
      S.resultNext();
      continue;
    }
    if (!G.dealOpen) { S.nextCustomer(); continue; }
    const d = G.deal, inv = G.inventory.length, cash = G.cash;
    STRATS[strat](d);
    if (G.inventory.length > inv) { STAT.buy++; STAT.profit += d.trueValue - (cash - G.cash); }
    STAT.customers++;
    if (G.dealOpen) S.refuse();
  }
  return { won: false, days };
}

// 试别的数值：TUNE='{"time_per_day":24,"time_per_customer":2}' node test/run.mjs --balance
if (process.env.TUNE) Object.assign(tuning, JSON.parse(process.env.TUNE));
const N = Number(process.env.N || 300);
console.log(`起始 ¥${tuning.start_cash}，还贷 ${JSON.stringify(tuning.loan_due)}，每天时间 ${tuning.time_per_day}`);
for (const useStaff of [false, true]) {
  console.log(useStaff ? "\n—— 派员工探险、拆包裹 ——" : "—— 只做买卖 ——");
  for (const strat of Object.keys(STRATS)) {
    let wins = 0;
    const perDay = [];
    for (let i = 0; i < N; i++) {
      const r = play(strat, 1000 + i, useStaff);
      if (r.won) wins++;
      r.days.forEach((c, k) => { (perDay[k] = perDay[k] || []).push(c); });
    }
    const avg = perDay.map((a) => Math.round(a.reduce((x, y) => x + y, 0) / a.length));
    const st = { ...STAT };
    console.log(`${strat.padEnd(4, "　")} 每局 ${Math.round(st.customers / N)} 位顾客，成交 ${Math.round(st.buy / st.customers * 100)}%，每笔平均赚 ¥${Math.round(st.profit / Math.max(1, st.buy))}`);
    Object.assign(STAT, { customers: 0, buy: 0, profit: 0 });
    console.log(`${strat.padEnd(4, "　")} 胜率 ${String(Math.round(wins / N * 100)).padStart(3)}%　每天打烊后平均现金 ${avg.join(" → ")}`);
  }
}
