// 画面工具：每一帧整屏重画（即时模式），按钮在画的时候登记点击区域。
import { ctx, W, H, img, audio, now } from "./platform.js";

export const C = {
  bgTop: "#2b1e17", bgBottom: "#0e0b09", neon: "#ffb347", pink: "#ff6b8b", text: "#f6ede2", muted: "#a8998a",
  paper: "#efe1c6", paperDark: "#d9c6a3", ink: "#3a2618", inkSoft: "#7a5d44", stamp: "#c8372d", ok: "#4cd18a",
  bad: "#ff5d5d", lcdBg: "#0d1a13", lcd: "#7dffb2", metal: "#1c1815",
};
const FONT = '"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans SC",sans-serif';

// ---------------- 点击区域 ----------------
let hits = [];          // 这一帧登记的按钮 [{x,y,w,h,fn,layer}]
let layer = 0;          // 弹窗会提高层级，下面的按钮就点不到
export function beginFrame() { hits = []; layer = 0; }
export function pushLayer() { layer++; }
/** 登记一块可点击区域。弹窗打开时，只有最高层的区域有效。 */
export function hit(x, y, w, h, fn) { hits.push({ x, y, w, h, fn, layer }); }
export function tap(x, y) {
  const top = hits.reduce((m, r) => Math.max(m, r.layer), 0);
  for (let i = hits.length - 1; i >= 0; i--) {
    const r = hits[i];
    if (r.layer === top && x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h) {
      audio.sfx("tap");
      r.fn();
      return true;
    }
  }
  return false;
}

// ---------------- 基础图形 ----------------
export function rrect(x, y, w, h, r, fill, stroke, lw = 2) {
  ctx.beginPath();
  r = Math.min(r, w / 2, h / 2);
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
  if (fill) { ctx.fillStyle = fill; ctx.fill(); }
  if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = lw; ctx.stroke(); }
}

export function vgrad(x, y, w, h, top, bottom) {
  const g = ctx.createLinearGradient(0, y, 0, y + h);
  g.addColorStop(0, top); g.addColorStop(1, bottom);
  ctx.fillStyle = g; ctx.fillRect(x, y, w, h);
}

export function font(size, bold = false) { ctx.font = `${bold ? "bold " : ""}${size}px ${FONT}`; }

/** 画一行文字。align: left / center / right。返回宽度。 */
export function text(s, x, y, size, color, align = "left", bold = false) {
  font(size, bold);
  ctx.fillStyle = color;
  ctx.textAlign = align;
  ctx.textBaseline = "middle";
  ctx.fillText(String(s), x, y);
  return ctx.measureText(String(s)).width;
}

/** 太长就截断加省略号 */
export function textFit(s, x, y, maxW, size, color, align = "left", bold = false) {
  font(size, bold);
  s = String(s);
  if (ctx.measureText(s).width > maxW) {
    while (s.length > 1 && ctx.measureText(s + "…").width > maxW) s = s.slice(0, -1);
    s += "…";
  }
  return text(s, x, y, size, color, align, bold);
}

const wrapCache = new Map();
/** 按宽度把文字拆成多行（中文逐字断，保留换行符）。 */
export function wrapLines(s, maxW, size, bold = false) {
  const key = `${size}|${bold}|${maxW}|${s}`;
  const cached = wrapCache.get(key);
  if (cached) return cached;
  font(size, bold);
  const out = [];
  for (const para of String(s).split("\n")) {
    let line = "";
    for (const ch of para) {
      if (ctx.measureText(line + ch).width > maxW && line) { out.push(line); line = ch; }
      else line += ch;
    }
    out.push(line);
  }
  if (wrapCache.size > 500) wrapCache.clear();
  wrapCache.set(key, out);
  return out;
}

/** 多行文字，返回占用的高度。 */
export function para(s, x, y, maxW, size, color, align = "left", lineH = 1.45, bold = false) {
  const lines = wrapLines(s, maxW, size, bold);
  const lh = size * lineH;
  const ax = align === "center" ? x + maxW / 2 : align === "right" ? x + maxW : x;
  lines.forEach((l, i) => text(l, ax, y + lh * i + lh / 2, size, color, align, bold));
  return lines.length * lh;
}
export function paraHeight(s, maxW, size, lineH = 1.45, bold = false) {
  return wrapLines(s, maxW, size, bold).length * size * lineH;
}

/** 按钮：圆角底 + 居中文字，登记点击。disabled 时变暗且点不了。 */
export function button(label, x, y, w, h, fn, opt = {}) {
  const { fill = C.neon, color = "#1a1208", stroke = null, size = 28, disabled = false, radius = 16, bold = true } = opt;
  ctx.globalAlpha = disabled ? 0.4 : 1;
  rrect(x, y, w, h, radius, fill, stroke, 2);
  textFit(label, x + w / 2, y + h / 2 + 1, w - 16, size, color, "center", bold);
  ctx.globalAlpha = 1;
  if (!disabled) hit(x, y, w, h, fn);
}

/** 图片按比例放进框里（contain）。没加载好时画一个占位色块。 */
export function image(name, x, y, w, h, opt = {}) {
  const im = img(name);
  if (!im) {
    if (opt.placeholder) rrect(x, y, w, h, 12, opt.placeholder);
    return false;
  }
  const s = opt.cover ? Math.max(w / im.width, h / im.height) : Math.min(w / im.width, h / im.height);
  const dw = im.width * s, dh = im.height * s;
  const ax = opt.alignX ?? 0.5, ay = opt.alignY ?? 0.5;
  ctx.drawImage(im, x + (w - dw) * ax, y + (h - dh) * ay, dw, dh);
  return true;
}

/** 整屏暗色遮罩，并提高层级（下面的按钮点不到）。 */
export function dim(alpha = 0.72) {
  ctx.fillStyle = `rgba(3,2,2,${alpha})`;
  ctx.fillRect(0, 0, W, H);
  pushLayer();
  hit(0, 0, W, H, () => {});   // 吞掉点在空白处的点击
}

// ---------------- 浮动提示 ----------------
const floats = [];
export function floatText(s, color = C.neon) { floats.push({ s, color, t0: now() }); }
export function drawFloats() {
  const t = now();
  for (let i = floats.length - 1; i >= 0; i--) {
    const f = floats[i];
    const k = (t - f.t0) / 1600;
    if (k >= 1) { floats.splice(i, 1); continue; }
    ctx.globalAlpha = k < 0.5 ? 1 : 1 - (k - 0.5) * 2;
    const y = H * 0.32 - k * 70 - (floats.length - 1 - i) * 44;
    font(28, true);
    const w = ctx.measureText(f.s).width + 40;
    rrect(W / 2 - w / 2, y - 26, w, 52, 26, "rgba(0,0,0,0.65)");
    text(f.s, W / 2, y, 28, f.color, "center", true);
    ctx.globalAlpha = 1;
  }
}

// ---------------- 小动画 ----------------
const pulses = new Map();
/** 触发一个 0→1 的短动画，用 anim(key) 读进度（没在播放时返回 1）。 */
export function kick(key, ms = 350) { pulses.set(key, { t0: now(), ms }); }
export function anim(key) {
  const p = pulses.get(key);
  if (!p) return 1;
  const k = (now() - p.t0) / p.ms;
  if (k >= 1) { pulses.delete(key); return 1; }
  return k;
}
export const ease = { out: (k) => 1 - (1 - k) ** 3, back: (k) => 1 + 2.7 * (k - 1) ** 3 + 1.7 * (k - 1) ** 2 };
export function shakeX(key, amp = 10) { const k = anim(key); return k >= 1 ? 0 : Math.sin(k * 30) * amp * (1 - k); }

// ---------------- 拖动滚动 ----------------
/** 一块可滚动区域的状态；在 scene 里用 scroller.begin(...)/end() 包住内容。 */
export class Scroller {
  constructor() { this.y = 0; this.max = 0; this.drag = null; this.box = null; this.moved = false; }
  begin(x, y, w, h) {
    this.box = { x, y, w, h };
    ctx.save();
    ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip();
    ctx.translate(0, -this.y);
    this._hitStart = hits.length;
    return y;
  }
  /** contentH：内容总高度 */
  end(contentH) {
    ctx.restore();
    this.max = Math.max(0, contentH - this.box.h);
    this.y = Math.max(0, Math.min(this.max, this.y));
    // 把这块区域里登记的按钮坐标换算回屏幕坐标，并裁掉看不见的
    const { y: by, h: bh } = this.box;
    for (let i = this._hitStart; i < hits.length; i++) {
      const r = hits[i];
      r.y -= this.y;
      const top = Math.max(r.y, by), bot = Math.min(r.y + r.h, by + bh);
      if (bot <= top) { r.h = 0; r.w = 0; } else { r.h = bot - top; r.y = top; }
    }
    if (this.max > 0) {   // 滚动条
      const bx = this.box.x + this.box.w - 6;
      const th = Math.max(40, bh * bh / (contentH));
      rrect(bx, by + (bh - th) * (this.y / this.max), 4, th, 2, "rgba(255,255,255,0.25)");
    }
  }
  down(x, y) {
    const b = this.box;
    if (b && x >= b.x && x <= b.x + b.w && y >= b.y && y <= b.y + b.h) { this.drag = { y, start: this.y }; this.moved = false; }
  }
  move(x, y) {
    if (!this.drag) return;
    if (Math.abs(y - this.drag.y) > 8) this.moved = true;
    this.y = Math.max(0, Math.min(this.max, this.drag.start - (y - this.drag.y)));
  }
  up() { const m = this.moved; this.drag = null; this.moved = false; return m; }
}
