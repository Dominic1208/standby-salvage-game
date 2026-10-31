"""待机回收站 · 电脑端连接程序

职责：
- 接收 Claude Code 钩子发来的批准请求（只接受本机 127.0.0.1 的请求）
- 通过 WebSocket 推给已配对的手机，并发送锁屏推送（Web Push）
- 把手机上的决定交回给正在等待的钩子
- 托管手机网页（web/）和导出的游戏（web/game/）

运行：python connector/server.py   （默认端口 8787）
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import secrets
import sys
import time
from pathlib import Path

from aiohttp import web

from push import PushSender

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT.parent / "web"
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
DEVICES_FILE = DATA_DIR / "devices.json"

PORT = 8787
PAIR_CODE_TTL = 1800         # 配对码有效期（秒）
REMIND_AFTER = (300, 900)    # 5 分钟、15 分钟再提醒

mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/manifest+json", ".webmanifest")


def now() -> float:
    return time.time()


def content_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


class State:
    def __init__(self) -> None:
        self.approvals: dict[str, dict] = {}       # approvalId -> approval
        self.waiters: dict[str, asyncio.Future] = {}
        self.events: list[dict] = []               # 汇报/求援等非批准消息
        self.sockets: set[web.WebSocketResponse] = set()
        self.seq = 0
        self.pair_code = ""
        self.pair_expires = 0.0
        self.devices: dict[str, dict] = self._load_devices()
        self.push = PushSender(DATA_DIR)

    # ---- 设备与配对 ----
    def _load_devices(self) -> dict:
        if DEVICES_FILE.exists():
            return json.loads(DEVICES_FILE.read_text("utf-8"))
        return {}

    def save_devices(self) -> None:
        DEVICES_FILE.write_text(json.dumps(self.devices, ensure_ascii=False, indent=2), "utf-8")

    def new_pair_code(self) -> str:
        self.pair_code = f"{secrets.randbelow(1_000_000):06d}"
        self.pair_expires = now() + PAIR_CODE_TTL
        return self.pair_code

    def device_for(self, token: str | None) -> dict | None:
        if not token:
            return None
        for dev in self.devices.values():
            if secrets.compare_digest(dev["token"], token):
                return dev
        return None

    # ---- 广播 ----
    def snapshot(self) -> dict:
        pending = [a for a in self.approvals.values() if a["status"] == "pending"]
        recent = sorted(self.approvals.values(), key=lambda a: a["created"], reverse=True)[:20]
        return {
            "type": "snapshot",
            "seq": self.seq,
            "pendingCount": len(pending),
            "approvals": [public(a) for a in recent],
            "events": self.events[-20:],
        }

    async def broadcast(self, msg: dict) -> None:
        self.seq += 1
        msg["seq"] = self.seq
        dead = []
        for ws in self.sockets:
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.sockets.discard(ws)


def public(a: dict) -> dict:
    """手机端能看到的字段（不含内部 future）。"""
    keys = ("id", "agent", "sessionId", "cwd", "toolName", "summary", "detail",
            "hash", "status", "created", "resolvedBy", "simulated")
    return {k: a.get(k) for k in keys}


def describe_tool(tool_name: str, tool_input: dict) -> tuple[str, str]:
    """把 Claude Code 的工具调用翻译成一句摘要 + 原文细节。"""
    ti = tool_input or {}
    if tool_name == "Bash":
        return "运行命令", ti.get("command", "")
    if tool_name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        return "修改文件", ti.get("file_path") or ti.get("notebook_path", "")
    if tool_name == "WebFetch":
        return "访问网页", ti.get("url", "")
    if tool_name == "PowerShell":
        return "运行 PowerShell 命令", ti.get("command", "")
    return f"使用工具 {tool_name}", json.dumps(ti, ensure_ascii=False, indent=2)[:2000]


STATE = State()


def local_only(request: web.Request) -> None:
    if request.remote not in ("127.0.0.1", "::1"):
        raise web.HTTPForbidden(text="hook endpoints are local only")


def require_device(request: web.Request) -> dict:
    token = request.headers.get("X-Device-Token") or request.query.get("token")
    dev = STATE.device_for(token)
    if not dev:
        raise web.HTTPUnauthorized(text="not paired")
    return dev


async def create_approval(agent: str, session_id: str, cwd: str, tool_name: str,
                          tool_input: dict, simulated: bool = False) -> dict:
    # 同一会话出现新请求，说明旧请求已在电脑上处理过：标记失效
    for old in STATE.approvals.values():
        if old["status"] == "pending" and old["sessionId"] == session_id and not simulated:
            await resolve(old["id"], "stale", "电脑端")

    summary, detail = describe_tool(tool_name, tool_input)
    body = {"agent": agent, "sessionId": session_id, "cwd": cwd,
            "toolName": tool_name, "detail": detail}
    a = {
        "id": secrets.token_urlsafe(9),
        **body,
        "summary": summary,
        "hash": content_hash(body),
        "status": "pending",
        "created": now(),
        "resolvedBy": None,
        "simulated": simulated,
    }
    STATE.approvals[a["id"]] = a
    STATE.waiters[a["id"]] = asyncio.get_running_loop().create_future()
    await STATE.broadcast({"type": "approval", "approval": public(a)})
    title = f"{agent_label(agent)}请示：{summary}"
    STATE.push.send_all(STATE.devices, title, short(detail), a["id"])
    asyncio.create_task(remind(a["id"]))
    return a


def agent_label(agent: str) -> str:
    return {"claude": "Claude 员工", "codex": "Codex 员工"}.get(agent, agent)


def short(text: str, n: int = 90) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


async def remind(approval_id: str) -> None:
    start = STATE.approvals[approval_id]["created"]
    for delay in REMIND_AFTER:
        await asyncio.sleep(max(0, start + delay - now()))
        a = STATE.approvals.get(approval_id)
        if not a or a["status"] != "pending":
            return
        mins = delay // 60
        STATE.push.send_all(STATE.devices, f"⏰ 还在等你：{agent_label(a['agent'])}已等 {mins} 分钟",
                            short(a["detail"]), approval_id)


async def resolve(approval_id: str, status: str, by: str) -> bool:
    a = STATE.approvals.get(approval_id)
    if not a or a["status"] != "pending":
        return False
    a["status"] = status
    a["resolvedBy"] = by
    fut = STATE.waiters.pop(approval_id, None)
    if fut and not fut.done():
        fut.set_result(status)
    await STATE.broadcast({"type": "approval", "approval": public(a)})
    return True


async def add_event(kind: str, agent: str, text: str, session_id: str = "") -> None:
    ev = {"id": secrets.token_urlsafe(6), "kind": kind, "agent": agent,
          "text": text, "sessionId": session_id, "time": now()}
    STATE.events.append(ev)
    STATE.events = STATE.events[-50:]
    await STATE.broadcast({"type": "event", "event": ev})
    label = {"done": "完成汇报", "help": "求援", "idle": "在等你"}.get(kind, kind)
    STATE.push.send_all(STATE.devices, f"{agent_label(agent)}{label}", short(text), None)


# ---------------- 钩子接口（仅本机） ----------------

async def hook_permission(request: web.Request) -> web.Response:
    """PermissionRequest 钩子：创建请求，长轮询等待决定。

    钩子脚本每次最多等 wait 秒，超时返回 {"decision": "wait"} 后重新调用本接口
    （带 approvalId），直到有决定或钩子自己放弃。
    """
    local_only(request)
    data = await request.json()
    approval_id = data.get("approvalId")
    if approval_id:
        a = STATE.approvals.get(approval_id)
        if not a:
            return web.json_response({"decision": "gone"})
    else:
        hook = data.get("hook", {})
        a = await create_approval(
            agent=data.get("agent", "claude"),
            session_id=hook.get("session_id", ""),
            cwd=hook.get("cwd", ""),
            tool_name=hook.get("tool_name", ""),
            tool_input=hook.get("tool_input", {}),
        )
    if a["status"] != "pending":
        return web.json_response({"approvalId": a["id"], "decision": a["status"]})
    fut = STATE.waiters.get(a["id"])
    try:
        status = await asyncio.wait_for(asyncio.shield(fut), timeout=float(data.get("wait", 25)))
    except asyncio.TimeoutError:
        return web.json_response({"approvalId": a["id"], "decision": "wait"})
    return web.json_response({"approvalId": a["id"], "decision": status})


async def hook_abandon(request: web.Request) -> web.Response:
    """钩子放弃等待（超时）：回到电脑上的确认框，手机端标记失效。"""
    local_only(request)
    data = await request.json()
    await resolve(data.get("approvalId", ""), "stale", "超时，转回电脑处理")
    return web.json_response({"ok": True})


async def hook_event(request: web.Request) -> web.Response:
    """Stop / Notification / PostToolUse 等非阻塞事件。"""
    local_only(request)
    data = await request.json()
    hook = data.get("hook", {})
    name = hook.get("hook_event_name", "")
    sid = hook.get("session_id", "")
    agent = data.get("agent", "claude")
    # 同会话有新动静 → 旧的待批请求已在电脑上处理
    if name in ("PostToolUse", "Stop", "UserPromptSubmit"):
        for a in list(STATE.approvals.values()):
            if a["status"] == "pending" and a["sessionId"] == sid and not a["simulated"]:
                await resolve(a["id"], "stale", "电脑端")
    if name == "Stop":
        project = Path(hook.get("cwd", "")).name or "任务"
        await add_event("done", agent, f"{project}：这一轮工作完成了，回来看看结果吧", sid)
    elif name == "Notification":
        msg = hook.get("message", "")
        if "permission" not in msg.lower():   # 批准类已由 PermissionRequest 处理
            await add_event("idle", agent, msg or "在等你回复", sid)
    return web.json_response({"ok": True})


# ---------------- 手机接口 ----------------

async def pair(request: web.Request) -> web.Response:
    data = await request.json()
    code = str(data.get("code", ""))
    if not STATE.pair_code or now() > STATE.pair_expires or not secrets.compare_digest(code, STATE.pair_code):
        raise web.HTTPForbidden(text="配对码无效或已过期")
    STATE.pair_code = ""  # 一次性
    device_id = secrets.token_urlsafe(6)
    token = secrets.token_urlsafe(32)
    STATE.devices[device_id] = {"id": device_id, "token": token,
                                "name": data.get("name", "手机"), "paired": now(), "push": None}
    STATE.save_devices()
    print(f"[配对] 新设备 {device_id} 已配对")
    return web.json_response({"deviceId": device_id, "token": token})


async def decide(request: web.Request) -> web.Response:
    dev = require_device(request)
    data = await request.json()
    a = STATE.approvals.get(data.get("approvalId", ""))
    if not a:
        return web.json_response({"result": "unknown"}, status=404)
    if data.get("hash") != a["hash"]:
        return web.json_response({"result": "mismatch", "status": a["status"]}, status=409)
    decision = data.get("decision")
    if decision not in ("allow", "deny"):
        raise web.HTTPBadRequest(text="bad decision")
    ok = await resolve(a["id"], decision, f"手机 {dev['name']}")
    return web.json_response({"result": "ok" if ok else "already", "status": a["status"]})


async def push_subscribe(request: web.Request) -> web.Response:
    dev = require_device(request)
    dev["push"] = await request.json()
    STATE.save_devices()
    return web.json_response({"ok": True})


async def push_key(request: web.Request) -> web.Response:
    return web.json_response({"publicKey": STATE.push.public_key})


async def simulate(request: web.Request) -> web.Response:
    """模拟一条请求，用来在没有真实 AI 任务时体验流程（卡片会标明“模拟”）。"""
    require_device(request)
    if request.query.get("kind") == "done":
        await add_event("done", "claude", "demo-project：这一轮工作完成了，回来看看结果吧（模拟）", "demo")
        return web.json_response({"ok": True})
    a = await create_approval("claude", "demo", "D:/demo-project", "Bash",
                              {"command": "npm install left-pad"}, simulated=True)
    asyncio.create_task(_auto_clear_sim(a["id"]))
    return web.json_response({"approvalId": a["id"]})


async def _auto_clear_sim(approval_id: str) -> None:
    fut = STATE.waiters.get(approval_id)
    if fut:
        try:
            await asyncio.wait_for(asyncio.shield(fut), timeout=1800)
        except asyncio.TimeoutError:
            await resolve(approval_id, "stale", "模拟请求过期")


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    require_device(request)
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    STATE.sockets.add(ws)
    await ws.send_json(STATE.snapshot())
    try:
        async for _ in ws:
            pass  # 手机端操作都走 HTTP，WebSocket 只负责下行
    finally:
        STATE.sockets.discard(ws)
    return ws


async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(WEB_DIR / "index.html")


@web.middleware
async def no_cache(request: web.Request, handler):
    resp = await handler(request)
    if request.path.endswith((".html", ".js", ".webmanifest")) or request.path == "/":
        resp.headers["Cache-Control"] = "no-cache"
    return resp


def make_app() -> web.Application:
    app = web.Application(middlewares=[no_cache])
    app.router.add_post("/hook/permission", hook_permission)
    app.router.add_post("/hook/abandon", hook_abandon)
    app.router.add_post("/hook/event", hook_event)
    app.router.add_post("/api/pair", pair)
    app.router.add_post("/api/decide", decide)
    app.router.add_post("/api/push/subscribe", push_subscribe)
    app.router.add_get("/api/push/key", push_key)
    app.router.add_post("/api/simulate", simulate)
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/", index)
    app.router.add_static("/", WEB_DIR, show_index=False)
    return app


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    code = STATE.new_pair_code()
    print("=" * 52)
    print("  待机回收站 · 连接程序")
    print(f"  本机地址:  http://localhost:{PORT}")
    print(f"  配对码:    {code}   （{PAIR_CODE_TTL // 60} 分钟内有效，只能用一次）")
    print(f"  已配对设备: {len(STATE.devices)} 台")
    print("=" * 52)
    web.run_app(make_app(), host="0.0.0.0", port=PORT, print=None)


if __name__ == "__main__":
    main()
