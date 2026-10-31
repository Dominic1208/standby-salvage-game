// 入口：主循环、场景切换、各种弹窗（结果、包裹、员工、汇报、升级、抽造型、图鉴、成就、设置、新手引导）。
import { ctx, W, H, SAFE_TOP, onPointer, raf, audio, loadArtPackage, whenArtReady, setupShare, now, vibrate } from "./platform.js";
import { C, beginFrame, tap, rrect, text, textFit, para, paraHeight, button, image, dim, floatText, drawFloats,
  Scroller, vgrad, anim, kick, ease, wrapLines } from "./ui.js";
import { G, load, save, newPlayer, startDay, resultNext, resultAlt, openGift, upcomingDue, meta, staffData, gifts,
  upLevel, buyUpgrade, nextHireCost, hire, placesOpen, tripMinutes, sendStaff, answerDilemma, finishReport, draw,
  setLook, tickStaff, bump } from "./state.js";
import * as S from "./state.js";
import { drawHome } from "./scenes/home.js";
import { drawShop } from "./scenes/shop.js";
import { showRewardedAd, adsEnabled } from "./ads.js";

// ---------------- 场景和弹窗 ----------------
let scene = "splash";          // splash → home ⇄ shop
let overlay = null;            // 当前弹窗名
let overlayData = null;        // 弹窗用的数据
const scroller = new Scroller();
const splashAt = now();

const nav = {
  openShop() {
    if (G.runState !== "playing" || !G.deal) startDay();
    scene = "shop";
    kick("arrive", 500);
  },
  goHome() { scene = "home"; audio.bgm("shop"); },
  open(name, data = null) { overlay = name; overlayData = data; scroller.y = 0; },
  close() { overlay = null; overlayData = null; },
  openGift() {
    const r = openGift();
    if (r) { overlay = "gift"; overlayData = { ...r, t0: now() }; vibrate(); }
  },
  tapStaff(s) {
    if (s.status === "back") nav.open("report", { staff: s, page: 0, answer: null });
    else nav.open("staffCard", { staff: s });
  },
  dueText() {
    const d = upcomingDue();
    return d ? `第 ${d.day} 天要还贷 ¥${d.amount}` : "";
  },
};

// ---------------- 启动 ----------------
function boot() {
  const had = load();
  if (!had) { newPlayer(); save(); }
  if (G.runState !== "playing" && G.runState !== "day_end") G.runState = "day_end";
  setupShare();
  whenArtReady(() => audio.bgm("shop"));   // 背景音乐在分包里
  loadArtPackage();
  if (!had) overlayData = { intro: true };
}

// ---------------- 输入 ----------------
let downAt = null;
onPointer("down", (x, y) => { downAt = { x, y, t: now() }; scroller.down(x, y); audio.resume(); });
onPointer("move", (x, y) => scroller.move(x, y));
onPointer("up", (x, y) => {
  const moved = scroller.up();
  if (!downAt) return;
  const far = Math.hypot(x - downAt.x, y - downAt.y) > 14;
  downAt = null;
  if (moved || far) return;                 // 滑动不算点击
  if (scene === "splash") { if (now() - splashAt > 1200) enterGame(); return; }
  tap(x, y);
});

function enterGame() {
  scene = "home";
  if (overlayData && overlayData.intro) nav.open("intro", { page: 0 });
}

// ---------------- 主循环 ----------------
function frame() {
  beginFrame();
  ctx.clearRect(0, 0, W, H);
  if (scene === "splash") drawSplash();
  else {
    // 员工到点回来：不管在哪个画面都要检查
    if (scene === "shop") for (const s of tickStaff()) floatText(`${s.name} 带着汇报回来了！`, C.neon);
    if (scene === "home") drawHome(nav); else drawShop(nav);
    if (G.result) drawResult();
    if (overlay) drawOverlay();
  }
  drawFloats();
  drawAchToasts();
  raf(frame);
}

// ---------------- 启动页：健康游戏忠告 ----------------
function drawSplash() {
  vgrad(0, 0, W, H, C.bgTop, C.bgBottom);
  const k = Math.min(1, (now() - splashAt) / 600);
  ctx.globalAlpha = k;
  image("gift_big", W / 2 - 110, H * 0.2, 220, 220);
  text("待机回收站", W / 2, H * 0.2 + 280, 72, C.pink, "center", true);
  text("什么都收的回收站 · 员工出门探险", W / 2, H * 0.2 + 350, 26, C.text, "center");
  const tips = "健康游戏忠告\n抵制不良游戏，拒绝盗版游戏。注意自我保护，谨防受骗上当。\n适度游戏益脑，沉迷游戏伤身。合理安排时间，享受健康生活。";
  para(tips, 60, H - 330, W - 120, 22, C.muted, "center");
  if (now() - splashAt > 1200) {
    ctx.globalAlpha = 0.6 + 0.4 * Math.sin(now() / 400);
    text("点击屏幕开始", W / 2, H * 0.2 + 440, 32, C.neon, "center", true);
  }
  ctx.globalAlpha = 1;
}

// ---------------- 结果卡片（成交 / 打烊 / 破产） ----------------
function drawResult() {
  const r = G.result;
  dim(0.6);
  const k = ease.back(Math.min(1, (now() - r.t0) / 300));
  const w = W - 80;
  const bodyH = paraHeight(r.body, w - 60, 24);
  const h = 230 + bodyH + (r.btn2 ? 76 : 0) + (adOffer(r) ? 76 : 0);
  const x = 40, y = Math.max(SAFE_TOP + 40, (H - h) / 2);
  ctx.save();
  ctx.translate(W / 2, y + h / 2); ctx.scale(0.85 + 0.15 * k, 0.85 + 0.15 * k); ctx.translate(-W / 2, -(y + h / 2));
  rrect(x, y, w, h, 24, C.paper, C.paperDark, 3);
  text(r.title, W / 2, y + 44, 30, C.ink, "center", true);
  text(r.big, W / 2, y + 104, 56, r.bigColor, "center", true);
  para(r.body, x + 30, y + 146, w - 60, 24, C.inkSoft, "center");
  let by = y + 160 + bodyH;
  button(r.btn, x + 30, by, w - 60, 62, () => resultNext(), { size: 28 });
  by += 76;
  if (r.btn2) { button(r.btn2, x + 30, by, w - 60, 56, () => resultAlt(), { fill: "rgba(0,0,0,0)", stroke: C.inkSoft, color: C.inkSoft, size: 24 }); by += 76; }
  const ad = adOffer(r);
  if (ad) button(ad.label, x + 30, by, w - 60, 56, ad.fn, { fill: C.ok, size: 24 });
  ctx.restore();
}

/** 结果卡片上可选的“看广告”按钮（只在开了广告时出现）。 */
function adOffer(r) {
  if (!adsEnabled()) return null;
  if (G.runState === "lost" && !r.adUsed) {
    return { label: "看个广告，收债人再宽限一天", fn: () => showRewardedAd("revive", () => {
      r.adUsed = true;
      G.runState = "day_end";
      G.cash += 300;
      G.result = null;
      floatText("收债人：就再给你一天。", C.ok);
      save();
    }) };
  }
  return null;
}

// ---------------- 弹窗 ----------------
function drawOverlay() {
  switch (overlay) {
    case "gift": return drawGift();
    case "staff": return drawStaffPanel();
    case "staffCard": return drawStaffCard();
    case "send": return drawSendPanel();
    case "report": return drawReport();
    case "upgrades": return drawUpgrades();
    case "gacha": return drawGacha();
    case "gachaResult": return drawGachaResult();
    case "skinPick": return drawSkinPick();
    case "book": return drawBook();
    case "ach": return drawAch();
    case "settings": return drawSettings();
    case "intro": return drawIntro();
  }
}

/** 通用面板：纸色大卡片 + 标题 + 关闭。返回内容区 {x,y,w,h}。 */
function panel(title, sub = "") {
  dim(0.7);
  const x = 20, y = SAFE_TOP + 30, w = W - 40, h = H - y - 30;
  rrect(x, y, w, h, 24, C.paper, C.paperDark, 3);
  text(title, x + 30, y + 46, 34, C.ink, "left", true);
  button("关闭", x + w - 120, y + 20, 100, 52, () => nav.close(), { fill: C.paperDark, color: C.ink, size: 24 });
  let top = y + 90;
  if (sub) { const sh = para(sub, x + 30, top, w - 60, 21, C.inkSoft); top += sh + 10; }
  return { x: x + 20, y: top, w: w - 40, h: y + h - top - 20 };
}

// ---- 包裹 ----
function drawGift() {
  const g = overlayData;
  dim(0.75);
  const w = W - 100, x = 50;
  const bodyH = paraHeight(g.body, w - 60, 25);
  const h = 430 + bodyH;
  const y = Math.max(SAFE_TOP + 40, (H - h) / 2);
  rrect(x, y, w, h, 24, C.paper, C.paperDark, 3);
  text(g.title, W / 2, y + 44, 32, g.good ? C.ink : C.stamp, "center", true);
  const k = ease.back(Math.min(1, (now() - g.t0) / 400));
  const s = 220 * (0.6 + 0.4 * k);
  image(g.art, W / 2 - s / 2, y + 80 + (220 - s) / 2, s, s);
  para(g.body, x + 30, y + 320, w - 60, 25, C.ink, "center");
  const more = G.giftQueue.length;
  button(more ? `收下，再拆一个（还有 ${more} 个）` : "收下", x + 30, y + h - 82, w - 60, 62,
    () => { if (more) nav.openGift(); else nav.close(); }, { size: 26 });
}

// ---- 员工列表 ----
function drawStaffPanel() {
  const cost = nextHireCost();
  const r = panel("员工", "派员工出门探险：到点会自己回来，带着冒险故事和包裹。可以关掉游戏，回来再收。");
  const rowH = 132;
  let y = scroller.begin(r.x, r.y, r.w, r.h);
  for (const s of G.staff) {
    rrect(r.x, y, r.w, rowH - 12, 16, "#f8efd9", "#c9b48d", 2);
    image(s.look, r.x + 10, y + 6, 90, 108, { alignY: 1 });
    text(s.name, r.x + 116, y + 34, 28, C.ink, "left", true);
    let status = "在店里歇着", color = C.inkSoft;
    if (s.status === "away") {
      const place = staffData.places.find((p) => p.id === s.place);
      const left = Math.max(0, s.returnAt - Date.now());
      status = `在${place ? place.name : "外面"}，${fmtLeft(left)}后回来`; color = "#2f6fa8";
    } else if (s.status === "back") { status = "回来了，等你听汇报！"; color = C.stamp; }
    textFit(status, r.x + 116, y + 76, r.w - 320, 22, color);
    if (s.status === "idle") button("派出门", r.x + r.w - 190, y + 30, 170, 58, () => nav.open("send", { staff: s }), { size: 24 });
    else if (s.status === "back") button("听汇报", r.x + r.w - 190, y + 30, 170, 58, () => nav.open("report", { staff: s, page: 0, answer: null }), { size: 24 });
    else button("换造型", r.x + r.w - 190, y + 30, 170, 58, () => nav.open("skinPick", { staff: s }), { fill: C.paperDark, color: C.ink, size: 22 });
    y += rowH;
  }
  if (cost !== null) {
    button(cost === 0 ? "招一个新员工（免费）" : `招一个新员工 ¥${cost}`, r.x, y + 6, r.w, 64, () => hire(),
      { fill: C.ok, size: 26, disabled: G.cash < cost });
    y += 84;
  } else { text("店里已经满员了", r.x + r.w / 2, y + 30, 22, C.inkSoft, "center"); y += 60; }
  scroller.end(y - r.y + scroller.y);
}

function fmtLeft(ms) {
  const m = Math.ceil(ms / 60000);
  if (m < 60) return `${m} 分钟`;
  return `${Math.floor(m / 60)} 小时${m % 60 ? ` ${m % 60} 分` : ""}`;
}

// ---- 点店里的员工：小卡片 ----
function drawStaffCard() {
  const s = overlayData.staff;
  dim(0.6);
  const x = 40, w = W - 80, h = 520, y = (H - h) / 2;
  rrect(x, y, w, h, 24, C.paper, C.paperDark, 3);
  image(s.look, x + 20, y + 20, 220, 300, { alignY: 1 });
  text(s.name, x + 260, y + 60, 34, C.ink, "left", true);
  const lines = ["今天想去哪儿逛逛？", "老板，有什么吩咐？", "我刚擦完柜台。", "听说码头最近有好货。", "要不要派我出去转转？"];
  para(lines[s.name.length % lines.length], x + 260, y + 100, w - 290, 25, C.inkSoft);
  button("派出门探险", x + 30, y + 340, w - 60, 62, () => nav.open("send", { staff: s }), { size: 26 });
  button("换造型", x + 30, y + 420, (w - 76) / 2, 56, () => nav.open("skinPick", { staff: s }), { fill: C.paperDark, color: C.ink, size: 24 });
  button("关闭", x + 46 + (w - 76) / 2, y + 420, (w - 76) / 2, 56, () => nav.close(), { fill: C.paperDark, color: C.ink, size: 24 });
}

// ---- 选目的地 ----
function drawSendPanel() {
  const s = overlayData.staff;
  const r = panel(`派 ${s.name} 去哪儿？`, "越远越久，带回来的包裹越好。真实时间计时，关掉游戏也会照常回来。");
  let y = scroller.begin(r.x, r.y, r.w, r.h);
  const open = placesOpen();
  for (const p of staffData.places) {
    const ok = open.includes(p);
    const h = 128;
    rrect(r.x, y, r.w, h - 12, 16, ok ? "#f8efd9" : "#e3d5bb", "#c9b48d", 2);
    text(p.name, r.x + 20, y + 32, 28, ok ? C.ink : C.inkSoft, "left", true);
    const tier = { small: "小包裹", big: "大包裹", weird: "怪包裹" }[p.tier] || "包裹";
    text(ok ? `${fmtLeft(tripMinutes(p) * 60000)} · ${tier}` : `第 ${p.unlock_day} 天解锁`, r.x + r.w - 20, y + 32, 22,
      ok ? "#2f6fa8" : C.inkSoft, "right");
    textFit(p.desc, r.x + 20, y + 76, r.w - 200, 21, C.inkSoft);
    if (ok) button("出发", r.x + r.w - 150, y + 56, 130, 48, () => {
      sendStaff(s, p);
      floatText(`${s.name} 出发去${p.name}了`, C.ok);
      nav.close();
    }, { size: 24 });
    y += h;
  }
  scroller.end(y - r.y + scroller.y);
}

// ---- 员工汇报：立绘 + 一页页的故事 + 可能的小选择 ----
function drawReport() {
  const d = overlayData, s = d.staff;
  if (!s.report) { nav.close(); return; }
  dim(0.55);
  const boxH = 420, y = H - boxH - 30;
  image(s.look, 30, y - 360, 300, 400, { alignY: 1 });
  rrect(20, y, W - 40, boxH, 22, "rgba(20,14,10,0.94)", C.neon, 2);
  rrect(40, y - 26, 260, 52, 14, C.neon);
  textFit(`${s.name} · 汇报`, 170, y, 240, 26, "#1a1208", "center", true);
  const pages = pageText(s.report, W - 100, 26, boxH - 150);
  const page = Math.min(d.page, pages.length - 1);
  para(pages[page], 50, y + 50, W - 100, 26, C.text);
  const last = page >= pages.length - 1;
  const bw = (W - 100) / 2;
  if (!last) {
    button("跳过", 50, y + boxH - 82, bw - 10, 60, () => { d.page = pages.length - 1; }, { fill: "rgba(0,0,0,0)", stroke: C.muted, color: C.muted, size: 24 });
    button("继续", 60 + bw, y + boxH - 82, bw - 10, 60, () => { d.page++; }, { size: 26 });
    return;
  }
  if (s.dilemma && !d.answer) {
    rrect(30, y - 170, W - 60, 130, 18, C.paper, C.stamp, 3);
    para(s.dilemma.text, 50, y - 154, W - 100, 23, C.ink);
    button(`花 ¥${s.dilemma.cost}`, 50, y + boxH - 82, bw - 10, 60, () => { d.answer = answerDilemma(s, true); }, { fill: C.ok, size: 26, disabled: G.cash < s.dilemma.cost });
    button("不用了", 60 + bw, y + boxH - 82, bw - 10, 60, () => { d.answer = answerDilemma(s, false); }, { fill: C.paperDark, color: C.ink, size: 26 });
    return;
  }
  if (d.answer) { rrect(30, y - 120, W - 60, 90, 18, C.paper, C.ok, 3); para(d.answer, 50, y - 104, W - 100, 23, C.ink); }
  button("收下包裹", 50, y + boxH - 82, W - 100, 60, () => {
    finishReport(s);
    nav.close();
    nav.openGift();
  }, { size: 28 });
}

function pageText(s, w, size, h) {
  const lines = wrapLines(s, w, size);
  const per = Math.max(1, Math.floor(h / (size * 1.45)));
  const out = [];
  for (let i = 0; i < lines.length; i += per) out.push(lines.slice(i, i + per).join("\n"));
  return out.length ? out : [""];
}

// ---- 升级 ----
function drawUpgrades() {
  const r = panel("店铺升级", `现金 ¥${G.cash}　升级永久保留，但花的是现在的钱——小心还不上贷款。`);
  let y = scroller.begin(r.x, r.y, r.w, r.h);
  for (const u of meta.upgrades) {
    const lv = upLevel(u.id), max = u.levels.length;
    const h = 150;
    rrect(r.x, y, r.w, h - 12, 16, "#f8efd9", "#c9b48d", 2);
    rrect(r.x + 16, y + 20, 72, 72, 16, C.ink);
    text(u.icon, r.x + 52, y + 57, 38, C.neon, "center", true);
    text(u.name, r.x + 108, y + 36, 28, C.ink, "left", true);
    text("★".repeat(lv) + "☆".repeat(max - lv), r.x + 108 + 30 * u.name.length + 16, y + 36, 22, C.neon);
    textFit(u.desc, r.x + 108, y + 74, r.w - 330, 21, C.inkSoft);
    textFit(lv > 0 ? `现在：${u.levels[lv - 1].text}` : "还没买", r.x + 108, y + 106, r.w - 330, 20, "#2e9b5f");
    if (lv < max) {
      const c = u.levels[lv].cost;
      button(`¥${c}`, r.x + r.w - 190, y + 40, 170, 60, () => buyUpgrade(u.id), { size: 26, disabled: G.cash < c });
    } else text("满级", r.x + r.w - 105, y + 70, 26, "#2e9b5f", "center", true);
    y += h;
  }
  scroller.end(y - r.y + scroller.y);
}

// ---- 抽造型 ----
function drawGacha() {
  const g = meta.gacha;
  const r = panel("抽员工造型", `现金 ¥${G.cash}　已拥有 ${Object.keys(G.skins).length} / ${g.skins.length}　重复的退 ¥${g.dupe_refund}`);
  const total = g.rarities.reduce((s, x) => s + x.weight, 0);
  textFit("概率：" + g.rarities.map((x) => `${x.name} ${Math.round(x.weight / total * 100)}%`).join("　"), r.x, r.y + 16, r.w, 20, C.inkSoft);
  const bw = (r.w - 16) / 2;
  const one = () => { const res = draw(1); if (res) nav.open("gachaResult", { res, t0: now() }); };
  const ten = () => { const res = draw(10); if (res) nav.open("gachaResult", { res, t0: now() }); };
  button(`抽 1 次 ¥${g.cost}`, r.x, r.y + 44, bw, 70, one, { size: 26, disabled: G.cash < g.cost });
  button(`抽 10 次 ¥${g.ten_cost}`, r.x + bw + 16, r.y + 44, bw, 70, ten, { size: 26, disabled: G.cash < g.ten_cost });
  if (adsEnabled() && !G.stats.ad_draw_today) {
    button("看广告免费抽 1 次", r.x, r.y + 126, r.w, 56, () => showRewardedAd("draw", () => {
      G.cash += g.cost; G.stats.ad_draw_today = 1; one();
    }), { fill: C.ok, size: 24 });
  }
  skinGrid(r.x, r.y + (adsEnabled() ? 196 : 130), r.w, r.y + r.h, null);
}

function skinGrid(x, y0, w, yMax, onPick) {
  const g = meta.gacha;
  const cols = 4, gap = 12, cw = (w - gap * (cols - 1)) / cols, ch = cw * 1.35;
  let y = scroller.begin(x, y0, w, yMax - y0);
  const list = onPick ? g.skins.filter((s) => G.skins[s.look]) : g.skins;
  list.forEach((s, i) => {
    const cx = x + (i % cols) * (cw + gap), cy = y + Math.floor(i / cols) * (ch + gap);
    const rar = g.rarities.find((r) => r.id === s.rarity);
    const own = !!G.skins[s.look];
    rrect(cx, cy, cw, ch, 14, own ? "#f8efd9" : "#d7c7a9", rar.color, own ? 3 : 1);
    ctx.globalAlpha = own ? 1 : 0.25;
    image(s.look, cx + 6, cy + 6, cw - 12, ch - 50, { alignY: 1 });
    ctx.globalAlpha = 1;
    textFit(own ? s.name : "？？？", cx + cw / 2, cy + ch - 34, cw - 8, 18, C.ink, "center", true);
    text(rar.name, cx + cw / 2, cy + ch - 14, 15, rar.color, "center", true);
    if (onPick && own) hitCell(cx, cy, cw, ch, () => onPick(s.look));
  });
  const rows = Math.ceil(list.length / cols);
  scroller.end(rows * (ch + gap));
}
function hitCell(x, y, w, h, fn) { button("", x, y, w, h, fn, { fill: "rgba(0,0,0,0)" }); }

function drawGachaResult() {
  const { res, t0 } = overlayData;
  dim(0.82);
  text("抽到了！", W / 2, SAFE_TOP + 90, 44, C.neon, "center", true);
  const fresh = res.filter((r) => r.fresh).length, refund = res.reduce((s, r) => s + r.refund, 0);
  text(`新造型 ${fresh} 个${refund ? `　重复的退 ¥${refund}` : ""}`, W / 2, SAFE_TOP + 140, 24, C.text, "center");
  const g = meta.gacha;
  const single = res.length === 1;
  const cols = single ? 1 : 5, cw = single ? 360 : 124, ch = cw * 1.4, gap = 12;
  const gx = (W - (cols * cw + (cols - 1) * gap)) / 2;
  const gy = single ? (H - ch) / 2 - 20 : SAFE_TOP + 200;
  res.forEach((r, i) => {
    const k = Math.min(1, Math.max(0, (now() - t0 - i * 120) / 300));
    if (k <= 0) return;
    const cx = gx + (i % cols) * (cw + gap), cy = gy + Math.floor(i / cols) * (ch + gap);
    const rar = g.rarities.find((x) => x.id === r.skin.rarity);
    ctx.globalAlpha = k;
    rrect(cx, cy, cw, ch, 16, "#f8efd9", rar.color, r.skin.rarity === "ssr" ? 6 : 3);
    image(r.skin.look, cx + 8, cy + 8, cw - 16, ch - (single ? 90 : 56), { alignY: 1 });
    textFit((r.fresh ? "新·" : "") + r.skin.name, cx + cw / 2, cy + ch - (single ? 56 : 34), cw - 10, single ? 30 : 17, r.fresh ? C.stamp : C.ink, "center", true);
    text(rar.name, cx + cw / 2, cy + ch - (single ? 22 : 14), single ? 24 : 15, rar.color, "center", true);
    ctx.globalAlpha = 1;
  });
  button("再抽", W / 2 - 250, H - 140, 230, 64, () => nav.open("gacha"), { fill: C.paperDark, color: C.ink, size: 26 });
  button("好的", W / 2 + 20, H - 140, 230, 64, () => nav.close(), { size: 26 });
}

function drawSkinPick() {
  const s = overlayData.staff;
  const r = panel(`给 ${s.name} 换造型`, "只能用已经抽到的造型。");
  skinGrid(r.x, r.y, r.w, r.y + r.h, (look) => { setLook(s, look); floatText(`${s.name} 换好了`, C.ok); nav.close(); });
}

// ---- 图鉴 ----
function drawBook() {
  const series = overlayData && overlayData.series;
  const all = gifts.collectibles;
  const have = all.filter((c) => G.collection[c.id]).length;
  if (!series) {
    const r = panel("收藏图鉴", `已收集 ${have} / ${all.length}　员工带回的包裹里能开出收藏品。`);
    const groups = new Map();
    for (const c of all) { const g = groups.get(c.series) || { list: [], art: c.art }; g.list.push(c); groups.set(c.series, g); }
    const cols = 2, gap = 14, cw = (r.w - gap) / cols, ch = 150;
    let i = 0;
    const y0 = scroller.begin(r.x, r.y, r.w, r.h);
    for (const [name, g] of groups) {
      const cx = r.x + (i % cols) * (cw + gap), cy = y0 + Math.floor(i / cols) * (ch + gap);
      const got = g.list.filter((c) => G.collection[c.id]).length;
      rrect(cx, cy, cw, ch, 16, got === g.list.length ? "#fff4d6" : "#f8efd9", got === g.list.length ? C.neon : "#c9b48d", 2);
      ctx.globalAlpha = got ? 1 : 0.35;
      image(g.art, cx + 8, cy + 8, 120, ch - 16);
      ctx.globalAlpha = 1;
      textFit(name, cx + 136, cy + 52, cw - 146, 22, C.ink, "left", true);
      text(`${got} / ${g.list.length}`, cx + 136, cy + 96, 22, got ? "#2e9b5f" : C.inkSoft);
      hitCell(cx, cy, cw, ch, () => { overlayData = { series: name }; scroller.y = 0; });
      i++;
    }
    scroller.end(Math.ceil(i / cols) * (ch + gap));
    return;
  }
  const list = all.filter((c) => c.series === series);
  const r = panel(series, `${list.filter((c) => G.collection[c.id]).length} / ${list.length}`);
  button("‹ 返回", r.x + r.w - 280, SAFE_TOP + 50, 140, 52, () => { overlayData = null; scroller.y = 0; }, { fill: C.paperDark, color: C.ink, size: 22 });
  let y = scroller.begin(r.x, r.y, r.w, r.h);
  for (const c of list) {
    const own = G.collection[c.id];
    const h = own ? 40 + paraHeight(c.desc, r.w - 40, 20) + 20 : 64;
    rrect(r.x, y, r.w, h, 14, own ? "#f8efd9" : "#e3d5bb", "#c9b48d", 2);
    textFit(own ? `${c.name}　${"★".repeat(c.rarity)}${own > 1 ? `　×${own}` : ""}` : `？？？　${"★".repeat(c.rarity)}`, r.x + 20, y + 30, r.w - 40, 23,
      own ? C.ink : C.inkSoft, "left", true);
    if (own) para(c.desc, r.x + 20, y + 52, r.w - 40, 20, C.inkSoft);
    y += h + 10;
  }
  scroller.end(y - r.y + scroller.y);
}

// ---- 成就 ----
function drawAch() {
  const list = meta.achievements;
  const got = list.filter((a) => G.ach[a.id]).length;
  const r = panel("成就", `已解锁 ${got} / ${list.length}`);
  let y = scroller.begin(r.x, r.y, r.w, r.h);
  const sorted = [...list].sort((a, b) => (G.ach[b.id] ? 1 : 0) - (G.ach[a.id] ? 1 : 0));
  for (const a of sorted) {
    const own = !!G.ach[a.id];
    const secret = a.secret && !own;
    rrect(r.x, y, r.w, 104, 14, own ? "#fff4d6" : "#e8dcc4", own ? C.neon : "#c9b48d", 2);
    text(own ? "★" : "☆", r.x + 40, y + 52, 40, own ? C.neon : C.inkSoft, "center");
    text(secret ? "？？？" : a.name, r.x + 80, y + 34, 26, own ? C.ink : C.inkSoft, "left", true);
    textFit(secret ? "隐藏成就" : a.desc, r.x + 80, y + 70, r.w - 230, 20, C.inkSoft);
    if (!own && !secret) text(`${Math.min(G.stats[a.stat] || 0, a.goal)} / ${a.goal}`, r.x + r.w - 20, y + 52, 22, C.inkSoft, "right");
    y += 114;
  }
  scroller.end(y - r.y + scroller.y);
}

// ---- 设置 ----
function drawSettings() {
  const r = panel("设置");
  let y = r.y + 20;
  const row = (label, key) => {
    text(label, r.x + 10, y + 30, 28, C.ink);
    const v = G.settings[key];
    for (let i = 0; i <= 4; i++) {
      const on = v >= i / 4 - 0.01 && i > 0;
      button(i === 0 ? "关" : "", r.x + 160 + i * 96, y, 84, 60, () => {
        G.settings[key] = i / 4; audio.setVolume(G.settings.music, G.settings.sfx); save();
      }, { fill: i === 0 ? (v === 0 ? C.stamp : C.paperDark) : on ? C.neon : C.paperDark, color: C.ink, size: 22 });
    }
    y += 90;
  };
  row("音乐", "music");
  row("音效", "sfx");
  y += 20;
  para("关于\n待机回收站：开一家什么都收的回收站。验货、砍价、揭穿编故事的顾客；派员工出门探险，带回冒险故事和包裹。\n\n" +
    "隐私说明\n本游戏不收集任何个人信息，存档只保存在你自己的手机上。", r.x + 10, y, r.w - 20, 22, C.inkSoft);
  y = r.y + r.h - 70;
  button("重新看新手引导", r.x, y, r.w, 60, () => nav.open("intro", { page: 0 }), { fill: C.paperDark, color: C.ink, size: 24 });
}

// ---- 新手引导 ----
const INTRO = [
  { art: "lounge_bg", title: "欢迎来到待机回收站", body: "这是你的店。大本营里住着你的员工。\n点下方吧台就开门营业。" },
  { art: "shop_bg", title: "收货：先验货，再砍价", body: "顾客会讲东西的来历。点“检查”看线索——\n有的人在撒谎。发现破绽就“质疑来历”，\n揭穿了他只能按实价卖给你。" },
  { art: "gift_small", title: "派员工出门探险", body: "点上方“员工”，派他们去跳蚤市场、码头、拍卖行……\n按真实时间回来，带着冒险故事和包裹。\n关掉游戏也照常计时。" },
  { art: "gift_big", title: "七天还清贷款", body: "第 3 天和第 7 天要还贷。\n打烊时把收来的货卖给收购商，符合“今日订单”的卖得更贵。\n赚了钱就升级店铺、抽员工造型、集收藏品。" },
];
function drawIntro() {
  const d = overlayData;
  const p = INTRO[d.page];
  dim(0.8);
  const x = 40, w = W - 80, h = 680, y = Math.max(SAFE_TOP + 30, (H - h) / 2);
  rrect(x, y, w, h, 24, C.paper, C.paperDark, 3);
  ctx.save(); ctx.beginPath(); ctx.rect(x + 20, y + 20, w - 40, 320); ctx.clip();
  image(p.art, x + 20, y + 20, w - 40, 320, { cover: p.art.endsWith("_bg") });
  ctx.restore();
  text(p.title, W / 2, y + 390, 32, C.ink, "center", true);
  para(p.body, x + 30, y + 430, w - 60, 24, C.inkSoft, "center");
  for (let i = 0; i < INTRO.length; i++) {
    ctx.beginPath(); ctx.arc(W / 2 + (i - (INTRO.length - 1) / 2) * 28, y + h - 110, 7, 0, Math.PI * 2);
    ctx.fillStyle = i === d.page ? C.neon : C.paperDark; ctx.fill();
  }
  const last = d.page >= INTRO.length - 1;
  button(last ? "开始！" : "下一页", x + 30, y + h - 84, w - 60, 62, () => {
    if (last) { nav.close(); bump("tutorial"); if (G.giftQueue.length) floatText("员工给你留了一个见面礼，点右上角包裹", C.neon); }
    else d.page++;
  }, { size: 28 });
}

// ---------------- 成就弹出 ----------------
function drawAchToasts() {
  const t = now();
  G.achToasts = G.achToasts.filter((x) => t - x.t0 < 3200);
  G.achToasts.slice(0, 2).forEach((x, i) => {
    const k = Math.min(1, (t - x.t0) / 300), out = Math.max(0, (t - x.t0 - 2800) / 400);
    // 放在屏幕下方中间，不挡右上角的“关闭”
    const y = H - 150 - i * 100 + (1 - k) * 60;
    const bx = W / 2 - 200;
    ctx.globalAlpha = 1 - out;
    rrect(bx, y, 400, 84, 16, "rgba(20,14,10,0.95)", C.neon, 2);
    text("★", bx + 40, y + 42, 40, C.neon, "center");
    text("成就解锁", bx + 80, y + 26, 18, C.muted);
    textFit(x.a.name, bx + 80, y + 58, 300, 26, C.neon, "left", true);
    ctx.globalAlpha = 1;
  });
}

boot();
raf(frame);
// 浏览器试玩时方便调试（小游戏里没有 window，不会生效）
if (typeof window !== "undefined" && typeof wx === "undefined" && typeof tt === "undefined") {
  window.__ss = { G, S, nav, frame, get scene() { return scene; }, get overlay() { return overlay; }, enterGame };
}
