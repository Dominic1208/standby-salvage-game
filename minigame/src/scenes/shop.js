// 开店画面：顾客上门 → 看线索 → 质疑来历 → 出价砍价 → 成交或拒绝。布局照电脑版：顶栏、店内场景、当票、收银机。
import { ctx, W, H, SAFE_TOP } from "../platform.js";
import { C, rrect, text, textFit, para, paraHeight, button, image, hit, vgrad, anim, kick, shakeX, ease } from "../ui.js";
import { G, tuning, revealClue, challenge, quickOffer, stepOffer, makeOffer, takeAsk, refuse, upValue } from "../state.js";

export function drawShop(nav) {
  vgrad(0, 0, W, H, C.bgTop, C.bgBottom);
  const d = G.deal;
  let y = SAFE_TOP + 8;
  y = drawHud(nav, y);
  // 剩下的高度分给：场景（可伸缩）+ 当票 + 收银机
  const ticketH = 112 + d.clues.length * 70 + 76;
  const registerH = 318;
  const sceneH = Math.max(200, Math.min(520, H - y - ticketH - registerH - 70));
  drawScene(nav, 16, y, W - 32, sceneH);
  y += sceneH + 12;
  drawTicket(16, y, W - 32, ticketH);
  y += ticketH + 4;
  textFit(G.log.text, W / 2, y + 24, W - 40, 24, G.log.color, "center");
  drawRegister(16, H - registerH - 12, W - 32, registerH);
}

function drawHud(nav, y) {
  button("‹ 大本营", 12, y, 140, 52, () => nav.goHome(), { fill: "rgba(0,0,0,0)", stroke: "#4a3f36", color: C.text, size: 22 });
  rrect(162, y + 2, 120, 48, 24, null, C.neon, 2);
  text(`第 ${G.day} 天`, 222, y + 27, 24, C.neon, "center", true);
  text("待机回收站", 400, y + 27, 34, C.pink, "center", true);
  ctx.beginPath(); ctx.arc(560, y + 27, 13, 0, Math.PI * 2); ctx.fillStyle = "#f2c14e"; ctx.fill();
  ctx.strokeStyle = "#b8862a"; ctx.lineWidth = 3; ctx.stroke();
  textFit(`¥${G.cash}`, 582, y + 27, W - 594, 28, C.text, "left", true);
  y += 64;
  textFit(`今日订单：收购商高价收【${G.orderTag}】类，${tuning.order_bonus} 倍`, 16, y + 12, W - 170, 21, C.neon);
  text(`口碑 ${G.rep}`, W - 16, y + 12, 21, C.ok, "right");
  y += 34;
  text("营业时间", 16, y + 10, 20, C.muted);
  const total = tuning.time_per_day + upValue("sign");
  const pw = (W - 140 - 16) / total;
  for (let i = 0; i < total; i++) rrect(120 + i * pw, y + 4, pw - 4, 12, 6, i < G.timeLeft ? C.neon : "#3a302a");
  if (G.intel > 0) text(`情报 ×${G.intel}`, W - 16, y + 10, 18, C.lcd, "right");
  return y + 30;
}

function drawScene(nav, x, y, w, h) {
  const d = G.deal;
  ctx.save();
  rrect(x, y, w, h, 18, "#2a1d15");
  ctx.clip();
  image("shop_bg", x, y, w, h, { cover: true });
  ctx.fillStyle = "rgba(0,0,0,0.25)"; ctx.fillRect(x, y, w, h);
  // 顾客：进门时从右边滑进来
  const k = ease.out(anim("arrive"));
  const sx = shakeX("figure", 12);
  const pw = Math.min(w * 0.42, h * 0.95);
  image(d.customer.art, x + 10 + (1 - k) * 120 + sx, y + h - pw * 1.05, pw, pw * 1.05, { alignY: 1 });
  ctx.restore();
  // 名字 + 耐心
  rrect(x + 12, y + 12, 220, 70, 12, "rgba(0,0,0,0.55)");
  textFit(d.customer.name, x + 24, y + 34, 200, 24, C.text, "left", true);
  const maxP = tuning.patience_start * 1.3;
  for (let i = 0; i < 5; i++) {
    const on = d.patience / maxP > i / 5;
    rrect(x + 24 + i * 38, y + 58, 32, 12, 6, on ? C.ok : "#3a302a");
  }
  // 对话气泡：顾客讲的来历
  const bx = x + w * 0.4, bw = w * 0.58;
  const bh = Math.min(h - 70, paraHeight(`“${d.story}”`, bw - 32, 24) + 30);
  ctx.globalAlpha = k;
  rrect(bx, y + 20, bw, bh, 20, C.paper);
  ctx.save(); ctx.beginPath(); ctx.rect(bx, y + 20, bw, bh); ctx.clip();
  para(`“${d.story}”`, bx + 16, y + 34, bw - 32, 24, C.ink);
  ctx.restore();
  ctx.globalAlpha = 1;
  if (G.giftQueue.length) button(`📦 包裹 ×${G.giftQueue.length}`, x + w - 200, y + h - 64, 188, 52, () => nav.openGift(), { size: 22 });
}

function drawTicket(x, y, w, h) {
  const d = G.deal;
  const k = anim("arrive");
  ctx.globalAlpha = Math.min(1, k * 1.5);
  rrect(x, y, w, h, 18, C.paper, C.paperDark, 3);
  image(d.item.art, x + 16, y + 14, 96, 96);
  text("回 收 单", x + 128, y + 26, 18, C.inkSoft);
  textFit(d.item.name, x + 128, y + 60, w - 300, 32, C.ink, "left", true);
  const hot = d.item.tag === G.orderTag;
  const tag = G.tagNote ? `【${d.item.tag}】${G.tagNote}` : `【${d.item.tag}】${hot ? "今日订单！" : ""}　市场参考价 ¥${d.item.base}`;
  textFit(tag, x + 128, y + 94, w - 300, 20, G.tagNote ? "#2e9b5f" : hot ? C.stamp : C.inkSoft);
  // 要价印章
  const ps = 1 + 0.15 * (1 - anim("ask")) * (anim("ask") < 1 ? 1 : 0);
  ctx.save();
  ctx.translate(x + w - 80, y + 60); ctx.scale(ps, ps); ctx.rotate(-0.05);
  rrect(-62, -44, 124, 88, 8, "rgba(200,55,45,0.08)", C.stamp, 3);
  text("要价", 0, -16, 24, C.stamp, "center", true);
  textFit(`¥${d.ask}`, 0, 18, 116, 28, C.stamp, "center", true);
  ctx.restore();
  // 线索
  let cy = y + 124;
  d.clues.forEach((c, i) => {
    if (c.revealed) {
      rrect(x + 14, cy, w - 28, 60, 12, "#f8efd9", "#c9b48d", 2);
      textFit(`✓ ${c.part}：${c.text}`, x + 30, cy + 30, w - 60, 22, C.ink);
    } else {
      rrect(x + 14, cy, w - 28, 60, 12, C.paperDark, "#a8916b", 2);
      text(`◎  检查${c.part}`, x + 30, cy + 30, 26, C.ink);
      text(G.intel > 0 ? "情报" : `耗时 ${tuning.time_per_clue}`, x + w - 30, cy + 30, 20, C.inkSoft, "right");
      if (G.dealOpen) hit(x + 14, cy, w - 28, 60, () => revealClue(i));
    }
    cy += 70;
  });
  const exposed = d.exposed;
  rrect(x + 14, cy, w - 28, 60, 12, exposed ? "rgba(76,209,138,0.15)" : "rgba(200,55,45,0.06)", exposed ? C.ok : C.stamp, 2);
  text(exposed ? "已揭穿：顾客说了实话" : "质疑来历：“这东西真是你的？”", x + w / 2, cy + 30, 26,
    exposed ? "#2e9b5f" : C.stamp, "center");
  if (G.dealOpen && !exposed) hit(x + 14, cy, w - 28, 60, () => {
    const r = challenge();
    if (r && (r.mood === "caught" || r.mood === "confess")) kick("ask"); else kick("figure", 500);
  });
  ctx.globalAlpha = 1;
}

function drawRegister(x, y, w, h) {
  const d = G.deal;
  rrect(x, y, w, h, 22, C.metal, "#3a322c", 2);
  const open = G.dealOpen;
  // − 显示屏 +
  button("−", x + 14, y + 14, 92, 110, () => stepOffer(-1), { fill: "#2e2722", color: C.text, size: 48, radius: 46, disabled: !open });
  button("+", x + w - 106, y + 14, 92, 110, () => stepOffer(1), { fill: "#2e2722", color: C.text, size: 48, radius: 46, disabled: !open });
  rrect(x + 118, y + 14, w - 236, 110, 12, C.lcdBg, "#24402f", 2);
  text("你的出价", x + 134, y + 34, 18, "#4f9a6d");
  for (let i = 0; i < 3; i++) {   // 剩余砍价轮数
    ctx.beginPath(); ctx.arc(x + w - 150 - i * 24, y + 34, 8, 0, Math.PI * 2);
    ctx.fillStyle = i < d.roundsLeft ? C.lcd : "#24402f"; ctx.fill();
  }
  const pulse = 1 + 0.06 * (1 - anim("offer")) * (anim("offer") < 1 ? 1 : 0);
  ctx.save(); ctx.translate(x + w / 2, y + 80); ctx.scale(pulse, pulse);
  text(`¥ ${G.offer}`, 0, 0, 50, G.offer > G.cash ? C.bad : C.lcd, "center", true);
  ctx.restore();
  // 3/5/7/9 成
  const ratios = tuning.quick_offer_ratios;
  const cw = (w - 28 - 10 * (ratios.length - 1)) / ratios.length;
  ratios.forEach((r, i) => button(`${Math.round(r * 10)} 成`, x + 14 + i * (cw + 10), y + 136, cw, 52,
    () => { quickOffer(r); kick("offer"); }, { fill: "#2e2722", color: C.lcd, stroke: "#24402f", size: 24, disabled: !open }));
  button("出 价", x + 14, y + 198, w - 28, 56, () => {
    const r = makeOffer();
    if (r === "counter") { kick("figure", 500); kick("ask"); }
  }, { size: 30, disabled: !open });
  const hw = (w - 38) / 2;
  button(`按要价收 ¥${d.ask}`, x + 14, y + 262, hw, 46, () => takeAsk(),
    { fill: "rgba(0,0,0,0)", stroke: C.ok, color: C.ok, size: 22, disabled: !open || d.ask > G.cash });
  button("不收了", x + 24 + hw, y + 262, hw, 46, () => refuse(),
    { fill: "rgba(0,0,0,0)", stroke: C.bad, color: C.bad, size: 22, disabled: !open });
}
