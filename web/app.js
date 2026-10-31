// 待机回收站 · 手机网页外壳
// 负责：配对、与电脑连接、员工推门提示、真实批准卡片、锁屏推送、暂停/恢复游戏。
// 游戏（iframe 里的 Godot）只会收到 pause / resume / employee 三种消息，碰不到批准。
"use strict";

const $ = (id) => document.getElementById(id);
const AGENTS = {
  claude: { name: "Claude 员工", avatar: "🧑‍🔧" }, codex: { name: "Codex 员工", avatar: "🦊" },
  deepseek: { name: "DeepSeek 员工", avatar: "🐳" }, kimi: { name: "Kimi 员工", avatar: "🌙" }, glm: { name: "智谱员工", avatar: "🧑‍🏫" },
  gemini: { name: "Gemini 员工", avatar: "🧑‍🚀" }, qwen: { name: "Qwen 员工", avatar: "🧑‍🍳" },
  copilot: { name: "Copilot 员工", avatar: "🧑‍✈️" }, cursor: { name: "Cursor 员工", avatar: "🧑‍🎨" },
};
const UNLOCK_DELAY = 1000; // 卡片出现后 1 秒内按钮不可点，防止玩游戏时误触

const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
  del(k) { try { localStorage.removeItem(k); } catch {} },
};

const state = {
  token: store.get("deviceToken"),
  approvals: new Map(),
  events: [],
  doorShown: new Set(),
  doorQueue: [],
  employees: [],
  cardId: null,
  ws: null,
  retry: 0,
};

// ---------------- 声音 ----------------
// 由外壳播放：Web Audio 在非 HTTPS 页面也能用（Godot 自己的音频需要 HTTPS）。
// iOS 要求用户先点一下屏幕才能出声，所以第一次点击时解锁。
const sound = {
  ctx: null, buffers: new Map(), bgmNode: null, bgmName: "", wantBgm: "", gain: null,
  muted: store.get("muted") === "1",
  music: Number(store.get("vol_music") ?? 0.6), sfxVol: Number(store.get("vol_sfx") ?? 1),
  setVolume(music, sfx) {
    this.music = music; this.sfxVol = sfx;
    store.set("vol_music", String(music)); store.set("vol_sfx", String(sfx));
    if (this.musicGain) { this.musicGain.gain.value = music; this.sfxGain.gain.value = sfx; }
  },
  unlock() {
    if (!this.ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      this.ctx = new AC();
      this.gain = this.ctx.createGain();
      this.gain.gain.value = this.muted ? 0 : 1;
      this.gain.connect(this.ctx.destination);
      this.musicGain = this.ctx.createGain();
      this.sfxGain = this.ctx.createGain();
      this.musicGain.connect(this.gain);
      this.sfxGain.connect(this.gain);
      this.setVolume(this.music, this.sfxVol);
    }
    if (this.ctx.state === "suspended") this.ctx.resume();
    if (this.wantBgm && this.bgmName !== this.wantBgm) this.bgm(this.wantBgm);
  },
  async load(name) {
    if (this.buffers.has(name)) return this.buffers.get(name);
    const url = name.startsWith("bgm_") ? `/audio/${name}.mp3` : `/audio/sfx_${name}.wav`;
    const p = fetch(url).then((r) => r.arrayBuffer()).then((b) => new Promise((ok, bad) => this.ctx.decodeAudioData(b, ok, bad)));
    this.buffers.set(name, p);
    return p;
  },
  async sfx(name) {
    if (!this.ctx || this.muted) return;
    try {
      const buf = await this.load(name);
      const src = this.ctx.createBufferSource();
      src.buffer = buf;
      src.connect(this.sfxGain);
      src.start();
    } catch {}
  },
  async bgm(name) {
    this.wantBgm = name;
    if (!this.ctx) return;
    if (this.bgmNode) { try { this.bgmNode.stop(); } catch {} this.bgmNode = null; }
    this.bgmName = name;
    if (!name) return;
    try {
      const buf = await this.load("bgm_" + name);
      if (this.wantBgm !== name) return;
      const src = this.ctx.createBufferSource();
      const vol = this.ctx.createGain();
      vol.gain.value = 0.35;
      src.buffer = buf;
      src.loop = name === "shop";
      src.connect(vol).connect(this.musicGain);
      src.start();
      this.bgmNode = src;
    } catch {}
  },
  toggle() {
    this.muted = !this.muted;
    store.set("muted", this.muted ? "1" : "0");
    if (this.gain) this.gain.gain.value = this.muted ? 0 : 1;
    $("sound-btn").textContent = this.muted ? "🔇" : "🔊";
  },
};
$("sound-btn").textContent = sound.muted ? "🔇" : "🔊";
$("sound-btn").onclick = (e) => { e.stopPropagation(); sound.unlock(); sound.toggle(); };
document.addEventListener("pointerdown", () => sound.unlock(), { capture: true });

// ---------------- 游戏通讯 ----------------
const game = $("game");
function tellGame(msg) {
  try { game.contentWindow.postMessage(msg, location.origin); } catch {}
}
function pauseGame() { tellGame({ type: "pause" }); }
function resumeGame() {
  if ($("card").classList.contains("hidden") && $("console").classList.contains("hidden") && $("door").classList.contains("hidden")) {
    tellGame({ type: "resume" });
  }
}
fetch("/game/index.html", { method: "HEAD" }).then((r) => {
  if (!r.ok) { $("game").classList.add("hidden"); $("game-missing").classList.remove("hidden"); }
}).catch(() => {});

// ---------------- 配对 ----------------
function showPair() { $("pair").classList.remove("hidden"); $("pair-code").focus(); }
async function pairWith(code) {
  $("pair-code").value = code;
  await $("pair-go").onclick();
  if (!state.token) showPair();
}
$("pair-go").onclick = async () => {
  const code = $("pair-code").value.trim();
  $("pair-err").textContent = "";
  try {
    const r = await fetch("/api/pair", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, name: navigator.platform || "手机" }) });
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    state.token = data.token;
    store.set("deviceToken", data.token);
    $("pair").classList.add("hidden");
    connect();
  } catch (e) {
    $("pair-err").textContent = "配对失败：" + (e.message || e);
  }
};
$("pair-skip").onclick = () => $("pair").classList.add("hidden");

// ---------------- 连接 ----------------
function setConn(on, text) {
  $("conn-dot").classList.toggle("off", !on);
  $("conn-text").textContent = text;
}

function connect() {
  if (!state.token) { setConn(false, "未配对"); showPair(); return; }
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(state.token)}`);
  state.ws = ws;
  setConn(false, "连接中…");
  ws.onopen = () => { state.retry = 0; setConn(true, "已连接电脑"); };
  ws.onmessage = (ev) => handle(JSON.parse(ev.data));
  ws.onclose = (ev) => {
    setConn(false, "已断开，重连中…");
    if (state.retry > 1) {
      // 多次失败时检查令牌是否失效（比如电脑端换了数据目录），失效就重新配对
      fetch("/api/save", { headers: { "X-Device-Token": state.token || "" } }).then((r) => {
        if (r.status === 401) { state.token = null; store.del("deviceToken"); setConn(false, "需要重新配对"); showPair(); }
      }).catch(() => {});
    }
    const delay = Math.min(15000, 1000 * 2 ** state.retry++);
    setTimeout(() => { if (state.token) connect(); }, delay);
  };
}

// 回到前台时立刻重连并拉全量快照（iOS 切后台会断开连接）
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && state.token &&
      (!state.ws || state.ws.readyState > 1)) connect();
});

function handle(msg) {
  if (msg.type === "snapshot") {
    state.approvals.clear();
    for (const a of msg.approvals) state.approvals.set(a.id, a);
    state.events = msg.events || [];
    state.employees = msg.employees || [];
    tellGame({ type: "employees", list: state.employees });
    for (const a of msg.approvals) if (a.status === "pending") queueDoor({ kind: "approval", id: a.id });
    openFromUrl();
  } else if (msg.type === "approval") {
    const a = msg.approval;
    state.approvals.set(a.id, a);
    if (a.status === "pending") queueDoor({ kind: "approval", id: a.id });
    if (state.cardId === a.id) renderCardStatus(a);
  } else if (msg.type === "employees") {
    state.employees = msg.employees || [];
    tellGame({ type: "employees", list: state.employees });
  } else if (msg.type === "event") {
    state.events.push(msg.event);
    queueDoor({ kind: "event", ev: msg.event });
  }
  renderStatus();
  renderConsole();
}

// ---------------- 状态栏 ----------------
function pending() { return [...state.approvals.values()].filter((a) => a.status === "pending"); }
function renderStatus() {
  const p = pending();
  $("pending-badge").textContent = p.length;
  $("pending-badge").classList.toggle("hidden", p.length === 0);
  $("agent-text").textContent = p.length
    ? `${AGENTS[p[0].agent]?.name || p[0].agent}：等你批准`
    : "员工：出勤中";
}
$("statusbar").onclick = () => openConsole();

// ---------------- 员工推门 ----------------
function queueDoor(item) {
  const key = item.kind === "approval" ? "a:" + item.id : "e:" + item.ev.id;
  if (state.doorShown.has(key)) return;
  state.doorShown.add(key);
  state.doorQueue.push(item);
  if ($("door").classList.contains("hidden") && $("card").classList.contains("hidden")) nextDoor();
}

function nextDoor() {
  const item = state.doorQueue.shift();
  if (!item) { $("door").classList.add("hidden"); resumeGame(); return; }
  if (item.kind === "approval") {
    const a = state.approvals.get(item.id);
    if (!a || a.status !== "pending") return nextDoor();
    const ag = AGENTS[a.agent] || { name: `${a.label || a.agent} 员工`, avatar: "🧑" };
    $("door-avatar").textContent = ag.avatar;
    $("door-who").textContent = `${a.employeeName || "员工"}（${ag.name.replace(" 员工", "")}）推门进来`;
    $("door-say").textContent = `“老板，我要${a.summary}，批不批？”`;
    $("door-open").textContent = "查看";
    $("door-open").onclick = () => { $("door").classList.add("hidden"); openCard(a.id); };
    tellGame({ type: "employee", agent: a.agent, kind: "approval", employeeId: a.employeeId, name: a.employeeName });
  } else {
    const ev = item.ev;
    const ag = AGENTS[ev.agent] || { name: ev.agent, avatar: "🧑" };
    $("door-avatar").textContent = ag.avatar;
    const who = `${ev.employeeName || "员工"}（${ag.name.replace(" 员工", "")}）`;
    $("door-who").textContent = ev.kind === "done" ? `${who}回来汇报` : `${who}发来消息`;
    $("door-say").textContent = `“${ev.text}”`;
    $("door-open").textContent = ev.kind === "done" ? "看看成果" : "知道了";
    $("door-open").onclick = () => {
      $("door").classList.add("hidden");
      // 确认了完成汇报 → 员工带回一只大箱子
      if (ev.kind === "done") tellGame({ type: "gift", tier: "big", agent: ev.agent });
      nextDoor();
    };
    tellGame({ type: "employee", agent: ev.agent, kind: ev.kind, employeeId: ev.employeeId, name: ev.employeeName });
  }
  pauseGame();
  sound.sfx("notify");
  $("door").classList.remove("hidden");
}

// ---------------- 批准卡片 ----------------
let unlockTimer = null;

function openCard(id) {
  const a = state.approvals.get(id);
  if (!a) return;
  state.cardId = id;
  pauseGame();
  const ag = AGENTS[a.agent] || { name: a.agent };
  $("f-agent").textContent = `${a.employeeName || ag.name}（${a.label || a.agent}）`;
  $("f-task").textContent = `${a.cwd || "未知目录"}　会话 ${String(a.sessionId).slice(0, 8)}`;
  $("f-summary").textContent = `${a.summary}（工具：${a.toolName}）`;
  $("f-detail").textContent = a.detail || "（无）";
  $("f-after").textContent = a.toolName === "Bash" || a.toolName === "PowerShell"
    ? "电脑会立刻在上面的目录里运行这条命令。"
    : a.summary === "修改文件" ? "电脑会创建或修改上面这个文件。" : "电脑会执行上面这一步。";
  $("f-id").textContent = a.id;
  $("f-hash").textContent = a.hash;
  $("card-sim").classList.toggle("hidden", !a.simulated);
  $("card").classList.remove("hidden");
  $("card").scrollTop = 0;
  resetSlider();
  setActionsEnabled(false);
  clearTimeout(unlockTimer);
  renderCardStatus(a);
  if (a.status === "pending") unlockTimer = setTimeout(() => setActionsEnabled(true), UNLOCK_DELAY);
}

function closeCard() {
  state.cardId = null;
  $("card").classList.add("hidden");
  if (state.doorQueue.length) nextDoor(); else resumeGame();
}

function setActionsEnabled(on) {
  $("btn-deny").disabled = !on;
  $("slider").classList.toggle("disabled", !on);
}

function renderCardStatus(a) {
  const box = $("card-status");
  const by = a.resolvedBy ? `（${a.resolvedBy}）` : "";
  const map = {
    allow: ["ok", `已批准${by}，电脑继续执行`],
    deny: ["bad", `已拒绝${by}`],
    stale: ["stale", `这条请求已失效：${a.resolvedBy || "已在别处处理"}`],
  };
  if (a.status === "pending") { box.classList.add("hidden"); return; }
  const [cls, text] = map[a.status] || ["stale", a.status];
  box.className = "card-status " + cls;
  box.textContent = text;
  setActionsEnabled(false);
  clearTimeout(unlockTimer);
}

async function decide(decision) {
  const a = state.approvals.get(state.cardId);
  if (!a || a.status !== "pending") return;
  setActionsEnabled(false);
  try {
    const r = await fetch("/api/decide", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Device-Token": state.token },
      body: JSON.stringify({ approvalId: a.id, hash: a.hash, decision }),
    });
    const data = await r.json().catch(() => ({}));
    if (data.status) { a.status = data.status; renderCardStatus(a); }
    if (data.result === "ok") {
      // 处理了请求（批准或拒绝都一样）→ 员工带回一个小包裹
      setTimeout(() => { closeCard(); tellGame({ type: "gift", tier: "small", agent: a.agent }); }, 1400);
    }
  } catch (e) {
    const box = $("card-status");
    box.className = "card-status bad";
    box.textContent = "发送失败，请检查连接后重试（电脑那边还在等）";
    setActionsEnabled(true);
  }
  renderStatus();
  renderConsole();
}

$("btn-deny").onclick = () => decide("deny");
$("btn-later").onclick = () => closeCard();

// 滑动批准
(function slider() {
  const el = $("slider"), knob = $("slider-knob"), fill = $("slider-fill");
  let startX = 0, dx = 0, dragging = false;
  const max = () => el.clientWidth - knob.clientWidth - 8;
  el.addEventListener("pointerdown", (e) => {
    if (el.classList.contains("disabled")) return;
    dragging = true; startX = e.clientX; dx = 0; el.setPointerCapture(e.pointerId);
  });
  el.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    dx = Math.max(0, Math.min(max(), e.clientX - startX));
    knob.style.left = 4 + dx + "px";
    fill.style.width = dx + 30 + "px";
  });
  const end = () => {
    if (!dragging) return;
    dragging = false;
    if (dx >= max() * 0.9) { knob.style.left = 4 + max() + "px"; decide("allow"); }
    else resetSlider();
  };
  el.addEventListener("pointerup", end);
  el.addEventListener("pointercancel", end);
})();
function resetSlider() { $("slider-knob").style.left = "4px"; $("slider-fill").style.width = "0"; }

function openFromUrl() {
  const id = new URLSearchParams(location.search).get("approval");
  if (id && state.approvals.has(id)) {
    history.replaceState(null, "", "/");
    $("door").classList.add("hidden");
    openCard(id);
  }
}

// ---------------- 通讯台 ----------------
function openConsole() { pauseGame(); renderConsole(); $("console").classList.remove("hidden"); }
$("console-close").onclick = () => { $("console").classList.add("hidden"); resumeGame(); };

function timeText(t) { return new Date(t * 1000).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }); }
const STATUS_TEXT = { pending: "等你批准", allow: "已批准", deny: "已拒绝", stale: "已失效" };

function renderConsole() {
  const pl = $("list-pending"); pl.innerHTML = "";
  for (const a of pending()) {
    const li = document.createElement("li");
    li.className = "clickable";
    li.textContent = `${AGENTS[a.agent]?.name || a.agent}：${a.summary}${a.simulated ? "（模拟）" : ""}`;
    const m = document.createElement("div"); m.className = "meta";
    m.textContent = `${timeText(a.created)} · ${a.cwd}`;
    li.appendChild(m);
    li.onclick = () => { $("console").classList.add("hidden"); openCard(a.id); };
    pl.appendChild(li);
  }
  if (!pl.children.length) pl.innerHTML = '<li>没有待处理的请求</li>';

  const rl = $("list-recent"); rl.innerHTML = "";
  const items = [
    ...[...state.approvals.values()].filter((a) => a.status !== "pending")
      .map((a) => ({ t: a.created, text: `${AGENTS[a.agent]?.name || a.agent}：${a.summary} → ${STATUS_TEXT[a.status]}`, meta: a.resolvedBy || "" })),
    ...state.events.map((e) => ({ t: e.time, text: `${AGENTS[e.agent]?.name || e.agent}：${e.text}`, meta: "" })),
  ].sort((x, y) => y.t - x.t).slice(0, 20);
  for (const it of items) {
    const li = document.createElement("li");
    li.textContent = it.text;
    const m = document.createElement("div"); m.className = "meta";
    m.textContent = `${timeText(it.t)} ${it.meta}`;
    li.appendChild(m);
    rl.appendChild(li);
  }
  if (!rl.children.length) rl.innerHTML = "<li>还没有记录</li>";
}

$("btn-sim-done").onclick = async () => {
  await fetch("/api/simulate?kind=done", { method: "POST", headers: { "X-Device-Token": state.token || "" } });
  $("console").classList.add("hidden");
};
$("btn-sim").onclick = async () => {
  await fetch("/api/simulate", { method: "POST", headers: { "X-Device-Token": state.token || "" } });
  $("console").classList.add("hidden");
};

// ---------------- 锁屏推送 ----------------
const standalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone;
function pushHint(text) { $("push-hint").textContent = text; }

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
  navigator.serviceWorker.addEventListener("message", (e) => {
    if (e.data?.type === "open-approval" && e.data.id) openCard(e.data.id);
  });
}

function b64ToBytes(b64) {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

$("btn-push").onclick = async () => {
  if (!window.isSecureContext) return pushHint("锁屏通知需要 HTTPS 地址（用 Tailscale 的 https 地址打开）。");
  if (!("PushManager" in window)) {
    return pushHint(standalone ? "这个浏览器不支持推送。" : "iPhone 上要先：Safari 分享 → 添加到主屏幕，再从主屏幕图标打开，才能开启通知。");
  }
  try {
    const perm = await Notification.requestPermission();
    if (perm !== "granted") return pushHint("你没有允许通知。可以在 设置 → 通知 里打开。");
    const reg = await navigator.serviceWorker.ready;
    const { publicKey } = await (await fetch("/api/push/key")).json();
    const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToBytes(publicKey) });
    const r = await fetch("/api/push/subscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Device-Token": state.token },
      body: JSON.stringify(sub.toJSON()),
    });
    pushHint(r.ok ? "锁屏通知已开启。" : "电脑端保存订阅失败。");
  } catch (e) {
    pushHint("开启失败：" + (e.message || e));
  }
};

// 游戏准备好时同步一次暂停状态
window.addEventListener("message", (e) => {
  if (e.origin !== location.origin) return;
  if (e.data?.type === "game-ready" && !$("door").classList.contains("hidden")) pauseGame();
  if (e.data?.type === "sfx") { sound.unlock(); sound.sfx(String(e.data.name)); }
  if (e.data?.type === "bgm") { sound.bgm(String(e.data.name || "")); }
  if (e.data?.type === "save") backupSave(e.data.data);
  if (e.data?.type === "game-ready" || e.data?.type === "need-employees") tellGame({ type: "employees", list: state.employees });
  if (e.data?.type === "volume") sound.setVolume(Number(e.data.music), Number(e.data.sfx));
  if (e.data?.type === "rename-employee") renameEmployee(String(e.data.id), String(e.data.name || ""));
  if (e.data?.type === "reroll-employee" && state.token) {
    fetch("/api/employee/reroll", { method: "POST", headers: { "Content-Type": "application/json", "X-Device-Token": state.token },
      body: JSON.stringify({ id: String(e.data.id) }) }).catch(() => {});
  }
  if (e.data?.type === "need-save") restoreSave();
});

// ---------------- 员工改名（文字输入放在网页里，iPhone 上更好用） ----------------
async function renameEmployee(id, current) {
  const name = window.prompt("给这位员工起个名字（最多 12 个字）", current);
  if (!name || !name.trim() || !state.token) return;
  await fetch("/api/employee/rename", { method: "POST",
    headers: { "Content-Type": "application/json", "X-Device-Token": state.token },
    body: JSON.stringify({ id, name: name.trim() }) }).catch(() => {});
}

// ---------------- 存档备份（电脑上也存一份） ----------------
let saveTimer = null;
function backupSave(data) {
  if (!state.token) return;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    fetch("/api/save", { method: "POST", headers: { "Content-Type": "application/json", "X-Device-Token": state.token },
      body: JSON.stringify(data) }).catch(() => {});
  }, 800);
}
async function restoreSave() {
  if (!state.token) return;
  try {
    const r = await fetch("/api/save", { headers: { "X-Device-Token": state.token } });
    const data = r.ok ? await r.json() : null;
    if (data) tellGame({ type: "load-save", data });
  } catch {}
}

// ---------------- 启动：扫码带来的配对码自动配对 ----------------
(async () => {
  const code = new URLSearchParams(location.search).get("pair");
  if (code) {
    history.replaceState(null, "", "/");
    if (!state.token) { await pairWith(code); restoreSave(); return; }
  }
  connect();
})();
renderStatus();
