// 游戏状态和全部规则：存档、开店流程、买卖、打烊结算、贷款、包裹、员工外出、升级、抽卡、成就。
// 界面（scenes/）只读这里的状态、调这里的函数，不自己改数值。
import tuning from "../build/data/tuning.json";
import catalog from "../build/data/catalog.json";
import customersData from "../build/data/customers.json";
import personalitiesData from "../build/data/personalities.json";
import gifts from "../build/data/gifts.json";
import staffData from "../build/data/staff.json";
import meta from "../build/data/meta.json";
import { Deal, pick, rand, randi } from "./deal.js";
import { storage, audio, now } from "./platform.js";
import { floatText, C } from "./ui.js";

export { tuning, catalog, gifts, staffData, meta };
const archetypes = customersData.archetypes;
const personas = personalitiesData.types;
const SAVE_KEY = "standby_salvage_save_v1";

/** 全局状态。G.deal 是当前顾客（不存档，读档时重新来一位）。 */
export const G = {
  day: 1, cash: tuning.start_cash, rep: 0, inventory: [], timeLeft: tuning.time_per_day, orderTag: "",
  runState: "playing", emergencyUsed: false, extraDue: {},
  collection: {}, giftQueue: [], giftsToday: 0, intel: 0,
  settings: { music: 0.6, sfx: 1 },
  staff: [], upgrades: {}, skins: {}, stats: {}, ach: {},
  // 以下不存档
  deal: null, dealOpen: false, offer: 0, log: { text: "", color: C.text }, result: null,
  achToasts: [], tagNote: null,
};

// ---------------- 存档 ----------------
const SAVED = ["day", "cash", "rep", "inventory", "timeLeft", "orderTag", "runState", "emergencyUsed", "extraDue",
  "collection", "giftQueue", "giftsToday", "intel", "settings", "staff", "upgrades", "skins", "stats", "ach"];
export function save() {
  const d = {};
  for (const k of SAVED) d[k] = G[k];
  storage.set(SAVE_KEY, d);
}
/** 读档。返回 true = 有存档。 */
export function load() {
  const d = storage.get(SAVE_KEY);
  if (!d) return false;
  for (const k of SAVED) if (d[k] !== undefined) G[k] = d[k];
  audio.setVolume(G.settings.music, G.settings.sfx);
  return true;
}

// ---------------- 第一次打开 ----------------
export function newPlayer() {
  for (const s of meta.gacha.skins.slice(0, 4)) G.skins[s.look] = true;   // 送 4 个普通造型
  for (let i = 0; i < staffData.start_staff; i++) addStaff();
  G.giftQueue.push("small");   // 见面礼
}

// ---------------- 升级 ----------------
export const upLevel = (id) => G.upgrades[id] || 0;
/** 某个升级当前生效的数值（没买为 0）。 */
export function upValue(id) {
  const u = meta.upgrades.find((x) => x.id === id);
  const lv = upLevel(id);
  return lv > 0 ? u.levels[lv - 1].value : 0;
}
export function buyUpgrade(id) {
  const u = meta.upgrades.find((x) => x.id === id);
  const lv = upLevel(id);
  if (lv >= u.levels.length) return false;
  const cost = u.levels[lv].cost;
  if (G.cash < cost) { floatText("钱不够", C.bad); return false; }
  G.cash -= cost;
  G.upgrades[id] = lv + 1;
  bump("upgrades");
  setStat("maxed_upgrades", meta.upgrades.filter((x) => upLevel(x.id) >= x.levels.length).length);
  audio.sfx("coin");
  floatText(`${u.name} 升到 ${lv + 1} 级`, C.ok);
  save();
  return true;
}
const dayLength = () => tuning.time_per_day + upValue("sign");

// ---------------- 成就 ----------------
export function bump(stat, n = 1) { G.stats[stat] = (G.stats[stat] || 0) + n; checkAch(); }
export function setMax(stat, v) { if (v > (G.stats[stat] || 0)) { G.stats[stat] = v; checkAch(); } }
function setStat(stat, v) { G.stats[stat] = v; checkAch(); }
export function checkAch() {
  for (const a of meta.achievements) {
    if (G.ach[a.id]) continue;
    if ((G.stats[a.stat] || 0) >= a.goal) {
      G.ach[a.id] = Date.now();
      G.achToasts.push({ a, t0: now() });
      audio.sfx("win");
    }
  }
}
function refreshCollectionStats() {
  setStat("collection", Object.keys(G.collection).length);
  const bySeries = {};
  for (const c of gifts.collectibles) {
    const s = bySeries[c.series] || (bySeries[c.series] = { have: 0, all: 0 });
    s.all++; if (G.collection[c.id]) s.have++;
  }
  setStat("series_done", Object.values(bySeries).filter((s) => s.have === s.all).length);
  setStat("legend_items", gifts.collectibles.filter((c) => c.rarity >= 5 && G.collection[c.id]).length);
  setStat("skins", Object.keys(G.skins).length);
}

// ---------------- 开店流程 ----------------
export function setLog(text, color = C.text) { G.log = { text, color }; }

export function startDay() {
  audio.bgm("shop");
  G.runState = "playing";
  G.timeLeft = dayLength();
  G.orderTag = pick(tuning.order_tags);
  setMax("best_day_reached", G.day);
  const h = new Date().getHours();
  if (h < 5) setMax("night", 1);
  nextCustomer();
  floatText(`第 ${G.day} 天开张`);
}

export function nextCustomer() {
  if (G.timeLeft < tuning.time_per_customer + 1) { endDay(); return; }
  G.timeLeft -= tuning.time_per_customer;
  const d = new Deal(tuning, catalog, archetypes, personas, G.rep);
  d.patience *= 1 + upValue("charm");
  G.deal = d;
  G.dealOpen = true;
  G.offer = Math.max(10, Math.min(d.ask, Math.max(G.cash, 10)));  // 出价屏先显示顾客要价
  G.tagNote = null;
  setLog(`“${d.line("greet")}”`);
  if (upLevel("appraiser")) d.reveal(randi(0, d.clues.length - 1));   // 老鉴定师免费看一处
  audio.sfx("door");
}

export function revealClue(i) {
  const d = G.deal;
  if (!G.dealOpen || d.clues[i].revealed) return;
  const free = G.intel > 0 || Math.random() < upValue("lens");
  if (!free && G.timeLeft < tuning.time_per_clue) { setLog("今天没时间细看了。", C.bad); return; }
  if (G.intel > 0) { G.intel--; floatText("用掉一条情报，不耗时"); }
  else if (free) floatText("放大镜：一眼看穿，不耗时");
  else G.timeLeft -= tuning.time_per_clue;
  d.reveal(i);
  audio.sfx("clue");
}

export function challenge() {
  const d = G.deal;
  if (!G.dealOpen || d.exposed) return null;
  const r = d.challenge();
  setLog(r.text, r.mood === "caught" || r.mood === "confess" ? C.ok : C.bad);
  if (r.mood === "caught" || r.mood === "confess") {
    G.tagNote = `揭穿了：它其实只值 ¥${d.ask} 左右`;
    changeRep(1, "揭穿了骗子");
    bump("liars");
    audio.sfx("caught");
  } else {
    if (r.mood === "honest") bump("wrong_accuse");
    audio.sfx("angry");
  }
  if (d.patience <= 0) { closeDeal("顾客扭头就走了。"); return r; }
  G.offer = Math.min(G.offer, d.ask);
  return r;
}

export function quickOffer(ratio) {
  if (!G.dealOpen) return;
  const d = G.deal;
  G.offer = clampOffer(Math.round(d.ask * ratio / 10) * 10);
  G.lastRatio = ratio;
}
export function stepOffer(dir) {
  if (!G.dealOpen) return;
  const d = G.deal;
  const step = Math.max(10, Math.round(d.ask * tuning.offer_step_ratio / 10) * 10);
  G.offer = clampOffer(G.offer + dir * step);
  G.lastRatio = null;
}
const clampOffer = (v) => Math.max(10, Math.min(v, Math.min(Math.max(G.cash, 10), G.deal.ask)));

/** 出价，返回结果 accept / counter / leave（界面用来做动画） */
export function makeOffer() {
  if (!G.dealOpen) return null;
  if (G.offer > G.cash) { setLog("钱不够了。", C.bad); return null; }
  const d = G.deal;
  const r = d.offer(G.offer);
  if (r.result === "accept") {
    setLog(r.text, C.ok);
    if (G.lastRatio && G.lastRatio <= 0.31) bump("lowball");
    buy(G.offer);
  } else if (r.result === "leave") {
    setLog(r.text, C.bad);
    closeDeal(r.text);
  } else {
    setLog(r.text);
    audio.sfx("counter");
    G.offer = Math.min(G.offer, d.ask);
  }
  return r.result;
}

export function takeAsk() {
  const d = G.deal;
  if (G.dealOpen && d.ask <= G.cash) { setLog(`“${d.line("accept")}”`, C.ok); buy(d.ask); }
}
export function refuse() {
  if (G.dealOpen) closeDeal(`你摆摆手，${G.deal.customer.name} 带着${G.deal.item.name}走了。`);
}

function changeRep(delta, why) {
  G.rep += delta;
  setMax("best_rep", G.rep);
  floatText(`街坊口碑 ${delta > 0 ? "+" : ""}${delta} · ${why}`, delta > 0 ? C.ok : C.bad);
}

function buy(price) {
  const d = G.deal;
  G.cash -= price;
  audio.sfx("coin");
  G.inventory.push({ name: d.item.name, paid: price, value: d.trueValue, leaky: !!d.item.leaky, tag: d.item.tag });
  if (!d.lying) {
    const ratio = price / Math.max(1, d.trueValue);
    if (ratio >= tuning.rep_fair_ratio) changeRep(1, "给了公道价");
    else if (ratio < tuning.rep_lowball_ratio) changeRep(-1, "压价太狠");
  }
  const p = d.profit(price);
  bump("deals");
  setMax("best_profit", p);
  setMax("worst_loss", -p);
  if (d.item.tag === G.orderTag) bump("order_items");
  const lines = [`${d.item.name}　付出 ¥${price}`, `收购商估价 ¥${d.trueValue}`];
  if (d.item.tag === G.orderTag) lines.push(`符合今日订单，打烊时按 ${tuning.order_bonus} 倍收`);
  if (d.lying) {
    const lie = d.clues.find((c) => c.isLie);
    lines.push(`顾客说了谎：${lie ? lie.part + lie.text : ""}`);
  }
  if (d.item.leaky) lines.push("注意：这是会漏液的问题货，可能弄坏仓库里别的货");
  showResult("成交", p >= 0 ? `+¥${p}` : `-¥${-p}`, p >= 0 ? C.ok : C.bad, lines.join("\n"));
}

function closeDeal(textLine) {
  audio.sfx("leave");
  showResult("没谈成", "¥0", C.muted, `${textLine}\n\n它其实值 ¥${G.deal.trueValue}`);
}

function showResult(title, big, bigColor, body, btn, btn2 = null) {
  G.dealOpen = false;
  G.result = { title, big, bigColor, body, t0: now(), btn2,
    btn: btn || (G.timeLeft >= tuning.time_per_customer + 1 ? "下一位顾客" : "打烊结算") };
  setMax("best_cash", G.cash);
  save();
}

/** 结果卡片上的主按钮 */
export function resultNext() {
  G.result = null;
  if (G.runState === "bankrupt") { takeEmergencyLoan(); return; }
  if (G.runState === "playing" && isBroke()) { showBankrupt(); return; }
  if (G.runState === "day_end") startDay();
  else if (G.runState === "lost" || G.runState === "won") restart();
  else nextCustomer();
}
/** 结果卡片上的第二个按钮（破产时“不借了”） */
export function resultAlt() {
  G.result = null;
  G.runState = "lost";
  restart();
}

const isBroke = () => G.cash < 50 && G.inventory.length === 0;

function nextDue(fromDay) {
  for (let d = fromDay; d <= tuning.run_days; d++) {
    const amount = (tuning.loan_due[String(d)] || 0) + (G.extraDue[String(d)] || 0);
    if (amount > 0) return { day: d, amount };
  }
  return null;
}
export function upcomingDue() { return nextDue(G.day); }

function showBankrupt() {
  bump("bankrupts");
  if (!G.emergencyUsed) {
    const due = nextDue(G.day);
    G.runState = "bankrupt";
    showResult("破产了", `¥${G.cash}`, C.bad,
      `钱花光了，仓库也空了。\n\n银行愿意借你一笔应急款 ¥${tuning.emergency_loan}，\n第 ${due ? due.day : tuning.run_days} 天还款时要多还 ¥${tuning.emergency_repay}。\n（每局只能借一次）`,
      "借应急款", "不借了，重新开始");
  } else {
    G.runState = "lost";
    showResult("破产了", `¥${G.cash}`, C.bad, "钱花光了，应急款也借过了……\n店只能先关门了。\n\n收藏品、升级和员工都会保留，下一局再来！", "从头再来");
  }
  audio.sfx("lose");
}

function takeEmergencyLoan() {
  G.emergencyUsed = true;
  G.cash += tuning.emergency_loan;
  const due = nextDue(G.day);
  const key = String(due ? due.day : tuning.run_days);
  G.extraDue[key] = (G.extraDue[key] || 0) + tuning.emergency_repay;
  G.runState = "playing";
  floatText(`借到应急款 ¥${tuning.emergency_loan}`);
  audio.sfx("coin");
  nextCustomer();
}

function restart() {
  G.emergencyUsed = false;
  G.extraDue = {};
  G.day = 1;
  G.cash = tuning.start_cash;
  G.rep = 0;
  G.inventory = [];
  startDay();
}

function endDay() {
  const lines = [];
  const leaky = G.inventory.filter((it) => it.leaky);
  if (leaky.length && G.inventory.length > 1 && !upLevel("safe")) {
    const victims = G.inventory.filter((it) => !it.leaky);
    if (victims.length) {
      const v = pick(victims);
      const loss = Math.round(v.value * tuning.leak_damage);
      v.value -= loss;
      lines.push(`漏液弄坏了${v.name}，少卖 ¥${loss}`);
    }
  }
  let total = 0, paid = 0, bonus = 0;
  const buyer = 1 + upValue("buyer");
  for (const it of G.inventory) {
    let value = Math.round(it.value * buyer);
    if (it.tag === G.orderTag) { const extra = Math.round(value * (tuning.order_bonus - 1)); bonus += extra; value += extra; }
    total += value; paid += it.paid;
  }
  G.cash += total;
  const net = total - paid;
  setMax("best_day", net);
  lines.unshift(`收了 ${G.inventory.length} 件货，花了 ¥${paid}`);
  lines.splice(1, 0, `收购商一共付了 ¥${total}`);
  if (bonus > 0) lines.splice(2, 0, `其中订单加价 ¥${bonus}`);
  G.inventory = [];
  G.runState = "day_end";
  const due = (tuning.loan_due[String(G.day)] || 0) + (G.extraDue[String(G.day)] || 0);
  if (due > 0) {
    if (G.cash >= due) { G.cash -= due; lines.push(`\n还贷 ¥${due} ✓ 收债人点点头走了`); bump("loans_paid"); }
    else { lines.push(`\n今天要还贷 ¥${due}，你只有 ¥${G.cash}……\n收债人把店门锁上了。`); G.runState = "lost"; }
  }
  lines.push(`现金 ¥${G.cash}　口碑 ${G.rep}`);
  if (G.runState === "day_end" && G.day >= tuning.run_days) {
    G.runState = "won";
    bump("wins");
    if (G.emergencyUsed) bump("comebacks");
    lines.push("\n贷款全部还清，这家店归你了。\n升级、员工、收藏品都保留，下一局会更轻松。");
  } else if (G.runState === "day_end") {
    const nd = nextDue(G.day + 1);
    if (nd) lines.push(`下次还贷：第 ${nd.day} 天 ¥${nd.amount}`);
  }
  let title = `第 ${G.day} 天 打烊`, btn = `开始第 ${G.day + 1} 天`;
  if (G.runState === "lost") { title = "店被收走了"; btn = "从头再来"; }
  if (G.runState === "won") { title = "七天撑过来了！"; btn = "再开一局"; }
  if (G.runState === "day_end") G.day++;
  G.giftsToday = 0;
  audio.sfx(G.runState === "lost" ? "lose" : G.runState === "won" ? "win" : "day_end");
  audio.bgm(G.runState === "day_end" ? "closing" : "");
  showResult(title, net >= 0 ? `+¥${net}` : `-¥${-net}`, net >= 0 ? C.ok : C.bad, lines.join("\n"), btn);
}

// ---------------- 包裹 ----------------
export function addGift(tier) {
  if (G.giftsToday >= gifts.daily_cap) { floatText("今天的包裹够多了，员工把它放进了仓库", C.muted); return; }
  G.giftsToday++;
  if (tier === "small" && Math.random() < gifts.weird_chance) tier = "weird";
  G.giftQueue.push(tier);
  audio.sfx("notify");
  save();
}

function pickOutcome(tier) {
  const w = (r) => r.weight * (tier === "big" && (r.min || 0) < 0 ? 0.5 : 1);
  const rows = gifts.outcomes;
  let roll = Math.random() * rows.reduce((s, r) => s + w(r), 0);
  for (const r of rows) { roll -= w(r); if (roll <= 0) return r; }
  return rows[0];
}
function rollCollectible(tier) {
  const pool = gifts.collectibles;
  const ws = pool.map((c) => 1 / c.rarity ** (tier === "big" ? 1.2 : 2));
  let roll = Math.random() * ws.reduce((a, b) => a + b, 0);
  for (let i = 0; i < pool.length; i++) { roll -= ws[i]; if (roll <= 0) return pool[i]; }
  return pool[0];
}
const pickText = (o) => pick(o.text || [""]);

/** 拆开队首的包裹。返回 {title, body, art, good}。 */
export function openGift() {
  const tier = G.giftQueue.shift();
  if (!tier) return null;
  const bonus = gifts.tiers[tier].bonus;
  const o = pickOutcome(tier);
  let good = true, body = "", art = gifts.tiers[tier].art;
  if (o.kind === "cash") {
    const amount = Math.round(randi(o.min, o.max) * (o.min > 0 ? bonus : 1));
    G.cash += amount; good = amount >= 0;
    body = `${pickText(o)}\n\n${amount >= 0 ? "+" : "-"} ¥${Math.abs(amount)}`;
  } else if (o.kind === "collectible") {
    const c = rollCollectible(tier);
    const fresh = !G.collection[c.id];
    G.collection[c.id] = (G.collection[c.id] || 0) + 1;
    art = c.art || "col_" + c.id;
    body = `${fresh ? "新" : "重复的"}收藏品：${c.name} ${"★".repeat(c.rarity)}\n\n${c.desc}`;
    if (!fresh) { const refund = 5 * c.rarity; G.cash += refund; body += `\n\n（重复的卖给了收藏贩子 +¥${refund}）`; }
    refreshCollectionStats();
  } else if (o.kind === "intel") {
    G.intel += o.count;
    body = `${pickText(o)}\n\n情报 +${o.count}：看线索免费、不耗时`;
  } else if (o.kind === "rep") {
    G.rep += o.amount;
    setMax("best_rep", G.rep);
    body = `${pickText(o)}\n\n街坊口碑 +${o.amount}`;
  } else { good = false; body = pickText(o); }
  bump("gifts");
  setMax("best_cash", G.cash);
  audio.sfx(good ? "gift" : "bad_gift");
  save();
  return { title: good ? "拆开了！" : "呃……", body, art, good };
}

// ---------------- 员工 ----------------
let staffSeq = 0;
function addStaff() {
  const used = new Set(G.staff.map((s) => s.name));
  const name = pick(staffData.names.filter((n) => !used.has(n))) || `员工${G.staff.length + 1}`;
  const owned = Object.keys(G.skins);
  const usedLooks = new Set(G.staff.map((s) => s.look));
  const look = pick(owned.filter((l) => !usedLooks.has(l))) || pick(owned) || "adv_01";   // 先用没人穿的造型
  G.staff.push({ id: `s${Date.now().toString(36)}${staffSeq++}`, name, look, status: "idle" });
  setStat("staff", G.staff.length);
}
export const nextHireCost = () => G.staff.length < staffData.max_staff ? staffData.hire_cost[G.staff.length] : null;
export function hire() {
  const cost = nextHireCost();
  if (cost === null) return false;
  if (G.cash < cost) { floatText("钱不够", C.bad); return false; }
  G.cash -= cost;
  addStaff();
  audio.sfx("door");
  floatText(`新员工 ${G.staff[G.staff.length - 1].name} 报到！`, C.ok);
  save();
  return true;
}
export const placesOpen = () => staffData.places.filter((p) => p.unlock_day <= Math.max(G.day, G.stats.best_day_reached || 1));
export function tripMinutes(place) { return place.minutes * (1 - upValue("bed")); }

export function sendStaff(staff, place) {
  staff.status = "away";
  staff.place = place.id;
  staff.departAt = Date.now();
  staff.returnAt = Date.now() + tripMinutes(place) * 60000;
  bump("trips");
  if (place.id === "mansion") bump("mansion_trips");
  audio.sfx("door");
  save();
}

/** 每帧调用：到点的员工变成“带着汇报回来了”。返回这次新回来的人。 */
export function tickStaff() {
  const back = [];
  for (const s of G.staff) {
    if (s.status === "away" && Date.now() >= s.returnAt) {
      const place = staffData.places.find((p) => p.id === s.place) || staffData.places[0];
      s.status = "back";
      s.report = makeReport(place);
      let tier = place.tier;
      if (tier === "small" && Math.random() < upValue("map")) tier = "big";
      s.gift = tier;
      s.dilemma = Math.random() < staffData.dilemma_chance ? makeDilemma() : null;
      back.push(s);
    }
  }
  if (back.length) save();
  return back;
}

function makeReport(place) {
  const scenes = [...place.scenes].sort(() => Math.random() - 0.5).slice(0, 2);
  const lines = [pick(staffData.openings), `这次去了${place.name}。`, `${scenes[0]}。`];
  if (Math.random() < 0.6) lines.push(pick(staffData.events));
  lines.push(`${scenes[1]}。`, `最后${pick(place.finds)}。`, pick(staffData.endings));
  return lines.join("\n");
}
function makeDilemma() {
  const d = pick(staffData.dilemmas);
  const cost = Math.round(d.cost * rand(0.8, 1.3) / 10) * 10;
  return { ...d, cost, text: d.text.replace("{cost}", cost) };
}

/** 回答员工带回的小选择。返回结果文字。 */
export function answerDilemma(staff, yes) {
  const d = staff.dilemma;
  staff.dilemma = null;
  if (!yes) return d.no.text;
  if (G.cash < d.cost) return "钱不够……那就算了吧。";
  G.cash -= d.cost;
  bump("dilemma_yes");
  if (d.yes.rep) { G.rep += d.yes.rep; setMax("best_rep", G.rep); }
  const [lo, hi] = d.yes.cash;
  const got = hi > 0 ? Math.round(rand(lo, hi) / 10) * 10 : 0;
  G.cash += got;
  const r = staffData.dilemma_results;
  const result = got > d.cost * 1.2 ? r.good : got >= d.cost * 0.8 ? r.even : r.bad;
  save();
  return d.yes.text.replace("{result}", hi > 0 ? `${result}（花 ¥${d.cost}，卖了 ¥${got}）` : "");
}

/** 听完汇报：员工回到店里歇着，包裹进队列。 */
export function finishReport(staff) {
  staff.status = "idle";
  staff.report = null;
  addGift(staff.gift || "small");
  staff.gift = null;
  save();
}

// ---------------- 抽皮肤 ----------------
function rollSkin() {
  const rs = meta.gacha.rarities;
  let roll = Math.random() * rs.reduce((s, r) => s + r.weight, 0);
  let rar = rs[0];
  for (const r of rs) { roll -= r.weight; if (roll <= 0) { rar = r; break; } }
  const pool = meta.gacha.skins.filter((s) => s.rarity === rar.id);
  return pick(pool.length ? pool : meta.gacha.skins);
}
/** 抽 n 次，返回结果列表 [{skin, fresh, refund}]；钱不够返回 null。 */
export function draw(n) {
  const cost = n >= 10 ? meta.gacha.ten_cost : meta.gacha.cost * n;
  if (G.cash < cost) { floatText("钱不够", C.bad); return null; }
  G.cash -= cost;
  const out = [];
  for (let i = 0; i < n; i++) {
    const skin = rollSkin();
    const fresh = !G.skins[skin.look];
    G.skins[skin.look] = true;
    if (!fresh) G.cash += meta.gacha.dupe_refund;
    out.push({ skin, fresh, refund: fresh ? 0 : meta.gacha.dupe_refund });
    bump("draws");
    if (skin.rarity === "ssr") bump("ssr");
  }
  refreshCollectionStats();
  audio.sfx("gift");
  save();
  return out;
}
export function setLook(staff, look) { if (G.skins[look]) { staff.look = look; save(); } }
