// 平台层：把微信（wx）、抖音（tt）和浏览器的差别都藏在这里。
// 游戏其余部分只用这里导出的 P，不直接碰 wx / tt / window。

const api = typeof wx !== "undefined" ? wx : typeof tt !== "undefined" ? tt : null;
export const PLATFORM = typeof wx !== "undefined" ? "wechat" : typeof tt !== "undefined" ? "douyin" : "web";

/** 逻辑分辨率：宽固定 720，高按屏幕比例。所有界面坐标都用逻辑像素。 */
export const W = 720;

function sysInfo() {
  if (api) {
    const s = (api.getWindowInfo ? api.getWindowInfo() : api.getSystemInfoSync());
    let safeTop = (s.safeArea && s.safeArea.top) || s.statusBarHeight || 0;
    // 右上角是平台的胶囊菜单（…和关闭），我们的按钮不能和它重叠：顶部从胶囊下面开始
    let menuBottom = 0;
    try {
      const m = api.getMenuButtonBoundingClientRect && api.getMenuButtonBoundingClientRect();
      if (m && m.bottom) menuBottom = m.bottom;
    } catch {}
    // 拿不到胶囊位置时（有的平台或版本没有这个接口），按常见胶囊高度留出来
    safeTop = Math.max(safeTop, menuBottom ? menuBottom + 6 : (s.statusBarHeight || 20) + 44);
    return { w: s.windowWidth, h: s.windowHeight, dpr: s.pixelRatio || 2, safeTop };
  }
  return { w: window.innerWidth, h: window.innerHeight, dpr: window.devicePixelRatio || 1, safeTop: 0 };
}

const info = sysInfo();
export const SCALE = info.w / W;            // 逻辑像素 → 屏幕像素
export const H = Math.round(info.h / SCALE);
export const SAFE_TOP = Math.round(info.safeTop / SCALE);

let canvas;
if (api) {
  canvas = api.createCanvas();               // 小游戏里第一次创建的就是屏幕上的画布
} else {
  canvas = document.createElement("canvas");
  canvas.style.width = info.w + "px";
  canvas.style.height = info.h + "px";
  document.body.appendChild(canvas);
}
canvas.width = Math.round(info.w * info.dpr);
canvas.height = Math.round(info.h * info.dpr);
export const ctx = canvas.getContext("2d");
const RATIO = SCALE * info.dpr;
export function resetTransform() { ctx.setTransform(RATIO, 0, 0, RATIO, 0, 0); }
resetTransform();

// ---------------- 触摸：统一成 down / move / up（逻辑坐标） ----------------
const handlers = { down: [], move: [], up: [] };
export function onPointer(kind, fn) { handlers[kind].push(fn); }
function emit(kind, x, y) { for (const fn of handlers[kind]) fn(x / SCALE, y / SCALE); }

if (api) {
  api.onTouchStart((e) => { const t = e.changedTouches[0]; emit("down", t.clientX, t.clientY); });
  api.onTouchMove((e) => { const t = e.changedTouches[0]; emit("move", t.clientX, t.clientY); });
  api.onTouchEnd((e) => { const t = e.changedTouches[0]; emit("up", t.clientX, t.clientY); });
  api.onTouchCancel && api.onTouchCancel((e) => { const t = e.changedTouches[0]; emit("up", t.clientX, t.clientY); });
} else {
  const pos = (e) => { const r = canvas.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
  let pressed = false;
  canvas.addEventListener("pointerdown", (e) => { pressed = true; emit("down", ...pos(e)); });
  window.addEventListener("pointermove", (e) => { if (pressed) emit("move", ...pos(e)); });
  window.addEventListener("pointerup", (e) => { if (pressed) { pressed = false; emit("up", ...pos(e)); } });
}

// ---------------- 存储 ----------------
export const storage = {
  get(key, fallback = null) {
    try {
      const raw = api ? api.getStorageSync(key) : localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch { return fallback; }
  },
  set(key, value) {
    try {
      const raw = JSON.stringify(value);
      if (api) api.setStorageSync(key, raw); else localStorage.setItem(key, raw);
    } catch {}
  },
};

// ---------------- 图片 ----------------
// 图片和背景音乐放在分包 "res" 里（微信首包限制 4MB），启动时先加载分包；背景图是 jpg，其余 png。
const images = new Map();
let artReady = !api;
const readyFns = [];
/** 分包加载好以后执行（浏览器里立刻执行）。 */
export function whenArtReady(fn) { if (artReady) fn(); else readyFns.push(fn); }
export function loadArtPackage() {
  return new Promise((resolve) => {
    if (!api || !api.loadSubpackage) { artReady = true; resolve(); return; }
    api.loadSubpackage({
      name: "res",
      success: () => { artReady = true; readyFns.splice(0).forEach((f) => f()); resolve(); },
      fail: () => { artReady = true; readyFns.splice(0).forEach((f) => f()); resolve(); },  // 加载失败也继续，没图的地方画色块
    });
  });
}
/** 取一张图；还没加载好时返回 null（下一帧再画）。name 不带扩展名。 */
export function img(name) {
  if (!name || !artReady) return null;
  let rec = images.get(name);
  if (!rec) {
    const image = api ? api.createImage() : new Image();
    rec = { image, ok: false };
    image.onload = () => { rec.ok = true; };
    image.onerror = () => { rec.failed = true; };
    image.src = `res/art/${name}.${name.endsWith("_bg") ? "jpg" : "png"}`;
    images.set(name, rec);
  }
  return rec.ok ? rec.image : null;
}

// ---------------- 声音 ----------------
const sfxPool = new Map();
let bgmCtx = null, bgmName = "";
export const audio = {
  music: 0.6, sfxVol: 1,
  sfx(name) {
    if (this.sfxVol <= 0) return;
    try {
      if (api) {
        const a = api.createInnerAudioContext();
        a.src = `audio/sfx_${name}.mp3`;
        a.volume = this.sfxVol;
        a.onEnded(() => a.destroy());
        a.onError(() => a.destroy());
        a.play();
      } else {
        let el = sfxPool.get(name);
        if (!el) { el = new Audio(`audio/sfx_${name}.mp3`); sfxPool.set(name, el); }
        const c = el.cloneNode();
        c.volume = this.sfxVol;
        c.play().catch(() => {});
      }
    } catch {}
  },
  bgm(name) {
    if (name === bgmName && bgmCtx) return;
    bgmName = name;
    try {
      if (bgmCtx) { bgmCtx.stop ? bgmCtx.stop() : bgmCtx.pause(); if (bgmCtx.destroy) bgmCtx.destroy(); }
      bgmCtx = null;
      if (!name) return;
      if (api) {
        bgmCtx = api.createInnerAudioContext();
        bgmCtx.src = `res/audio/bgm_${name}.mp3`;
        bgmCtx.loop = true;
        bgmCtx.volume = this.music * 0.5;
        bgmCtx.play();
      } else {
        bgmCtx = new Audio(`res/audio/bgm_${name}.mp3`);
        bgmCtx.loop = true;
        bgmCtx.volume = this.music * 0.5;
        bgmCtx.play().catch(() => {});
      }
    } catch {}
  },
  setVolume(music, sfx) {
    this.music = music; this.sfxVol = sfx;
    if (bgmCtx) bgmCtx.volume = music * 0.5;
  },
  /** 浏览器要先点一下才能出声；切回前台时恢复背景音乐。 */
  resume() {
    if (bgmCtx && bgmCtx.paused !== false && bgmCtx.play) {
      const p = bgmCtx.play(); if (p && p.catch) p.catch(() => {});
    }
  },
};
if (api && api.onShow) api.onShow(() => audio.resume());
if (!api) {
  document.addEventListener("pointerdown", () => audio.resume());
  document.addEventListener("visibilitychange", () => { if (!document.hidden) audio.resume(); });
}

// ---------------- 其他 ----------------
export function vibrate() { try { api && api.vibrateShort && api.vibrateShort({ type: "light" }); } catch {} }
export const now = () => Date.now();
export function raf(fn) { return api ? requestAnimationFrame(fn) : window.requestAnimationFrame(fn); }

/** 新版本：平台在后台下载好新包后，问玩家要不要马上重启更新（存档在本地，更新后还在）。 */
export function setupUpdate() {
  if (!api || !api.getUpdateManager) return;
  try {
    const um = api.getUpdateManager();
    um.onUpdateReady(() => {
      api.showModal({
        title: "有新版本", content: "新版本已经准备好，重启一下就能用。存档不会丢。", confirmText: "重启", cancelText: "等会儿",
        success: (r) => { if (r.confirm) um.applyUpdate(); },
      });
    });
  } catch {}
}

/** 分享（右上角菜单“转发”） */
export function setupShare() {
  if (!api) return;
  try {
    api.showShareMenu && api.showShareMenu({ withShareTicket: false, menus: ["shareAppMessage", "shareTimeline"] });
    const card = { title: "开一家什么都收的回收站，揭穿骗子、等员工带宝贝回来", imageUrl: "share.jpg" };
    api.onShareAppMessage && api.onShareAppMessage(() => card);
    api.onShareTimeline && api.onShareTimeline(() => ({ title: card.title, imageUrl: card.imageUrl }));
  } catch {}
}
