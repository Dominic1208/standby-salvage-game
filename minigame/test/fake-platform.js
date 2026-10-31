// 测试用的平台层：没有画布、没有声音，存储放在内存里。时间可以手动拨。
const noop = () => {};
export const PLATFORM = "test";
export const W = 720, H = 1560, SCALE = 1, SAFE_TOP = 0;
export const ctx = new Proxy({}, { get: (_, k) => (k === "measureText" ? (s) => ({ width: String(s).length * 20 }) : noop), set: () => true });
export const resetTransform = noop;
export const onPointer = noop;
const mem = new Map();
export const storage = {
  get(k, fallback = null) { return mem.has(k) ? JSON.parse(mem.get(k)) : fallback; },
  set(k, v) { mem.set(k, JSON.stringify(v)); },
  clear() { mem.clear(); },
};
export const audio = { music: 0, sfxVol: 0, sfx: noop, bgm: noop, setVolume: noop, resume: noop };
export const img = () => null;
export const loadArtPackage = () => Promise.resolve();
export const whenArtReady = (f) => f();
export const vibrate = noop;
export const setupShare = noop;
export const raf = noop;
let offset = 0;
/** 把“现在”往后拨 ms 毫秒（员工外出计时用） */
export function advanceTime(ms) { offset += ms; }
export const now = () => Date.now() + offset;
