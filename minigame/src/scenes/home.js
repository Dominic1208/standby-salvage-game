// 大本营：员工在店里走来走去；出门的人不在；回来的人在吧台前排队等你听汇报。点吧台开店。
import { ctx, W, H, SAFE_TOP, img } from "../platform.js";
import { C, rrect, text, textFit, button, image, hit, vgrad } from "../ui.js";
import { G, tickStaff, staffData } from "../state.js";
import { floatText } from "../ui.js";

// 房间图里标定好的位置（和电脑版 home_room.gd 一样，按图片比例 0~1）
const DOOR = { x: 0.5, y: 0.285 };
const FLOOR = { x: 0.22, y: 0.37, w: 0.52, h: 0.24 };
const BAR_TOP = 0.70;
const DEPTH = [0.29, 0.68];
const SCALE = [0.7, 1.08];
const STAFF_H = 230;
const QUEUE = [[0.5, 0.665], [0.27, 0.665], [0.73, 0.665], [0.385, 0.575], [0.615, 0.575]];

const actors = new Map();   // 员工 id → 走路状态（不存档）

/** 房间图的位置：贴底，铺满顶栏以下的高度（太高就左右裁掉一点）。 */
export function roomRect() {
  const im = img("lounge_bg");
  const iw = im ? im.width : 1024, ih = im ? im.height : 1536;
  const h = Math.max(W * ih / iw, H - SAFE_TOP - 150);
  const w = h * iw / ih;
  return { x: (W - w) / 2, y: H - h, w, h };
}
const toScreen = (r, p) => ({ x: r.x + p.x * r.w, y: r.y + p.y * r.h });
const randomFloor = () => ({ x: FLOOR.x + Math.random() * FLOOR.w, y: FLOOR.y + Math.random() * FLOOR.h });

function actorFor(s) {
  let a = actors.get(s.id);
  if (!a) {
    a = { pos: { ...DOOR }, target: randomFloor(), wait: Math.random() * 1.5, t: Math.random() * 10, alpha: 0 };
    actors.set(s.id, a);
  }
  return a;
}

/** 员工在房间里的位置更新。dt 秒。 */
function stepActors(dt, r) {
  const present = G.staff.filter((s) => s.status !== "away");
  const queue = present.filter((s) => s.status === "back");
  for (const [id] of actors) if (!present.find((s) => s.id === id)) actors.delete(id);
  for (const s of present) {
    const a = actorFor(s);
    a.t += dt;
    a.alpha = Math.min(1, a.alpha + dt * 3);
    const qi = queue.indexOf(s);
    if (qi >= 0) a.target = qi < QUEUE.length ? { x: QUEUE[qi][0], y: QUEUE[qi][1] } : DOOR;
    if (a.wait > 0) { a.wait -= dt; continue; }
    const dx = a.target.x - a.pos.x, dy = a.target.y - a.pos.y;
    const dist = Math.hypot(dx * r.w, dy * r.h);
    if (dist > 3) {
      const step = Math.min(dist, 120 * (r.w / 720) * dt);
      a.pos.x += dx * r.w / dist * step / r.w;
      a.pos.y += dy * r.h / dist * step / r.h;
      a.walking = true;
      a.flip = dx < 0;
    } else {
      a.walking = false;
      if (qi < 0) { a.wait = 1.2 + Math.random() * 2.3; a.target = randomFloor(); }
    }
  }
  return { present, queue };
}

let last = Date.now();
export function drawHome(nav) {
  const t = Date.now();
  const dt = Math.min(0.1, (t - last) / 1000);
  last = t;
  for (const s of tickStaff()) floatText(`${s.name} 带着汇报回来了！`, C.neon);

  vgrad(0, 0, W, H, "#140d09", "#0e0b09");
  const r = roomRect();
  image("lounge_bg", r.x, r.y, r.w, r.h, { placeholder: "#3a2618" });
  const { present, queue } = stepActors(dt, r);

  // 员工：远的先画
  const order = [...present].sort((a, b) => actorFor(a).pos.y - actorFor(b).pos.y);
  for (const s of order) {
    const a = actorFor(s);
    const p = toScreen(r, a.pos);
    const depth = Math.max(0, Math.min(1, (a.pos.y - DEPTH[0]) / (DEPTH[1] - DEPTH[0])));
    const sc = (SCALE[0] + (SCALE[1] - SCALE[0]) * depth) * (r.w / 720);
    const h = STAFF_H * sc, w = h * 0.66;
    const bob = a.walking ? -Math.abs(Math.sin(a.t * 11)) * 7 : 0;
    const qi = queue.indexOf(s);
    if (qi >= QUEUE.length) continue;   // 排不下的在门外等
    ctx.globalAlpha = a.alpha;
    const im = img(s.look);
    if (im) {
      ctx.save();
      ctx.translate(p.x, p.y + bob);
      if (a.flip) ctx.scale(-1, 1);
      const s2 = Math.min(w / im.width, h / im.height);
      ctx.drawImage(im, -im.width * s2 / 2, -im.height * s2, im.width * s2, im.height * s2);
      ctx.restore();
    } else rrect(p.x - w / 4, p.y - h, w / 2, h, 20, "#7a5d44");
    // 名牌：排队时只有最前面那位写全名，其余只写“汇报”
    const back = s.status === "back";
    const label = back ? (qi === 0 ? `${s.name} · 汇报` : "汇报") : s.name;
    ctx.font = "bold 22px sans-serif";
    const tw = Math.max(60, ctx.measureText(label).width + 28);
    const ty = p.y - h - 22 + bob;
    rrect(p.x - tw / 2, ty - 18, tw, 36, 12, back ? C.neon : "rgba(255,250,240,0.92)");
    text(label, p.x, ty, 22, back ? "#1a1208" : C.ink, "center", true);
    if (back && qi === 0) {
      const k = Math.sin(t / 150) * 6;
      text("!", p.x, ty - 44 + k, 44, C.bad, "center", true);
    }
    ctx.globalAlpha = 1;
    hit(p.x - w / 2, p.y - h, w, h + 10, () => nav.tapStaff(s));
  }
  const outside = queue.length - QUEUE.length;
  if (outside > 0) {
    const d = toScreen(r, DOOR);
    text(`门外还有 ${outside} 人排队`, W / 2, d.y + 30, 24, C.text, "center", true);
  }

  // 吧台：点击开店
  const barY = r.y + BAR_TOP * r.h;
  hit(0, barY, W, H - barY, () => nav.openShop());
  const k = 0.65 + 0.35 * Math.sin(t / 450);
  ctx.globalAlpha = k;
  text("点吧台开店", W / 2, r.y + (BAR_TOP + 0.075) * r.h, 28, C.neon, "center", true);
  ctx.globalAlpha = 1;
  if (!present.length) {
    const away = G.staff.filter((s) => s.status === "away").length;
    text(away ? "员工们都出门探险了，到点就回来" : "点上方“员工”派他们出门探险", W / 2, r.y + 0.47 * r.h, 24, C.text, "center", true);
  }

  drawTopBar(nav);
}

function drawTopBar(nav) {
  const top = SAFE_TOP + 10;
  vgrad(0, 0, W, top + 210, "rgba(20,13,9,1)", "rgba(20,13,9,0.85)");
  text("待机回收站", W / 2, top + 40, 46, C.pink, "center", true);
  const due = nav.dueText();
  text(`第 ${G.day} 天　¥${G.cash}　口碑 ${G.rep}`, W / 2, top + 88, 26, C.text, "center");
  if (due) text(due, W / 2, top + 120, 22, C.muted, "center");
  const away = G.staff.filter((s) => s.status === "away").length;
  const back = G.staff.filter((s) => s.status === "back").length;
  const btns = [
    ["员工" + (back ? `·${back}` : away ? `·外出${away}` : ""), () => nav.open("staff")],
    ["升级", () => nav.open("upgrades")],
    ["抽造型", () => nav.open("gacha")],
    ["图鉴", () => nav.open("book")],
    ["成就", () => nav.open("ach")],
    ["设置", () => nav.open("settings")],
  ];
  const bw = (W - 24 - 8 * 5) / 6;
  btns.forEach(([label, fn], i) => {
    button(label, 12 + i * (bw + 8), top + 140, bw, 56, fn,
      { fill: "rgba(0,0,0,0.35)", color: i === 0 && back ? C.neon : C.text, stroke: i === 0 && back ? C.neon : "#5a4a3e", size: 22 });
  });
  if (G.giftQueue.length) {
    button(`📦 包裹 ×${G.giftQueue.length}`, W - 220, top + 210, 200, 56, () => nav.openGift(), { size: 24 });
  }
}

export function homeQueueFront() {
  return G.staff.find((s) => s.status === "back") || null;
}
export { staffData };
