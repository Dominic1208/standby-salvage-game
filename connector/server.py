"""待机回收站 · 电脑端连接程序

职责：
- 接收 Claude Code 钩子发来的批准请求（只接受本机 127.0.0.1 的请求）
- 通过 WebSocket 推给已配对的手机，并发送锁屏推送（Web Push）
- 把手机上的决定交回给正在等待的钩子
- 托管手机网页（web/）和导出的游戏（web/game/）

运行：python connector/main.py   （默认端口 8787，会自动打开电脑上的设置页）
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import os
import socket
import json
import mimetypes
import secrets
import sys
import time
from pathlib import Path

from aiohttp import web

from push import PushSender

FROZEN = getattr(sys, "frozen", False)   # 打包成 exe 时为 True
ROOT = Path(__file__).resolve().parent
WEB_DIR = Path(sys._MEIPASS) / "web" if FROZEN else ROOT.parent / "web"
# 打包版把数据放在用户目录，升级覆盖程序文件夹也不会丢配对和存档
DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "StandbySalvage" if FROZEN else ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SAVES_DIR = DATA_DIR / "saves"
SAVES_DIR.mkdir(exist_ok=True)
DEVICES_FILE = DATA_DIR / "devices.json"
EMPLOYEES_FILE = DATA_DIR / "employees.json"
PORT = 8787
PAIR_CODE_TTL = 1800         # 配对码有效期（秒）
REMIND_AFTER = (300, 900)    # 5 分钟、15 分钟再提醒

mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/manifest+json", ".webmanifest")

# 员工（外出探险的冒险家）形象：30 个形象所有 AI 通用，只用领巾和名牌的颜色区分是哪家 AI；已经有人用的形象不重复分配
ALL_LOOKS = ([f"claude_{i}" for i in range(1, 7)] + [f"deepseek_{i}" for i in range(1, 7)]
             + [f"codex_{i}" for i in range(1, 7)] + [f"special_{i}" for i in range(1, 5)]
             + [f"staff_{i}" for i in range(1, 9)])
GENERIC_LOOKS = ALL_LOOKS
SPECIAL_LOOKS = [f"special_{i}" for i in range(1, 5)]
EMPLOYEE_FORGET = 3 * 24 * 3600   # 3 天没动静的员工不再显示


def pick_look(used: set) -> str:
    """从还没人用的形象里随机挑一个；全用过了就挑用得最少的。"""
    free = [x for x in ALL_LOOKS if x not in used]
    return free[secrets.randbelow(len(free))] if free else ALL_LOOKS[secrets.randbelow(len(ALL_LOOKS))]


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
        self.employees: dict[str, dict] = (json.loads(EMPLOYEES_FILE.read_text("utf-8"))
                                           if EMPLOYEES_FILE.exists() else {})
        # 旧版按文件夹登记的员工（没有对话 id）已被“按对话登记”取代，启动时清掉
        self.employees = {k: v for k, v in self.employees.items()
                          if v.get("session") or "演示项目" in str(v.get("project", ""))}
        for e in self.employees.values():
            if not isinstance(e.get("look"), str):  # 旧版数字形象 → 重新分配
                e["look"] = pick_look(self.used_looks())
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

    # ---- 员工：每个“AI 工具 + 项目”是一位员工 ----
    def save_employees(self) -> None:
        EMPLOYEES_FILE.write_text(json.dumps(self.employees, ensure_ascii=False, indent=2), "utf-8")

    def employee_for(self, agent: str, label: str, cwd: str, session_id: str = "", title: str = "") -> dict:
        """每个对话一位员工：名字用对话标题；拿不到标题时退回按文件夹。用户改过的名字不会被覆盖。"""
        project = Path(cwd.replace("\\", "/")).name if cwd else ""
        project = project or "未命名项目"
        key = f"{agent}:s:{session_id}" if session_id else f"{agent}:{project.lower()}"
        emp = self.employees.get(key)
        if emp and title and not emp.get("renamed") and emp.get("name") != title:
            emp["name"] = title  # 对话标题出来了或改了
        if not emp:
            same_agent = [e for e in self.employees.values() if e["agent"] == agent]
            emp = {"id": secrets.token_urlsafe(6), "key": key, "agent": agent, "label": label or agent,
                   "project": project, "name": title or project, "session": session_id,
                   "look": pick_look(self.used_looks()),
                   "index": len(same_agent), "created": now(), "status": "working"}
            self.employees[key] = emp
        emp["last_seen"] = now()
        self.save_employees()
        return emp

    def used_looks(self) -> set:
        return {e.get("look") for e in self.employees.values()
                if now() - e.get("last_seen", e.get("created", 0)) <= EMPLOYEE_FORGET}

    def employees_public(self) -> list:
        waiting = {a.get("employeeId") for a in self.approvals.values() if a["status"] == "pending"}
        out = []
        for e in sorted(self.employees.values(), key=lambda e: e["created"]):
            if now() - e.get("last_seen", e["created"]) > EMPLOYEE_FORGET:
                continue  # 好几天没动静的对话，员工就不来店里了
            status = "waiting" if e["id"] in waiting else e.get("status", "working")
            if status == "working" and now() - e.get("last_seen", 0) > 3600:
                status = "resting"
            out.append({k: e.get(k) for k in ("id", "agent", "label", "project", "name", "look", "index")}
                       | {"status": status, "reported": bool(e.get("reported"))})
        return out

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
            "employees": self.employees_public(),
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
    keys = ("id", "agent", "label", "employeeId", "employeeName", "employeeLook", "context", "sessionId", "cwd", "toolName", "summary", "detail",
            "hash", "status", "created", "resolvedBy", "simulated")
    return {k: a.get(k) for k in keys}


def describe_tool(tool_name: str, tool_input: dict) -> tuple[str, str]:
    """把 Claude Code 的工具调用翻译成一句摘要 + 原文细节。"""
    ti = tool_input or {}
    name = (tool_name or "").lower()
    path = ti.get("file_path") or ti.get("path") or ti.get("notebook_path") or ti.get("absolute_path") or ""
    if ti.get("command") or name in ("bash", "shell", "run_shell_command", "powershell", "exec"):
        return "运行命令", str(ti.get("command") or ti.get("cmd") or json.dumps(ti, ensure_ascii=False))
    if path or any(k in name for k in ("write", "edit", "replace", "patch", "create")):
        return "修改文件", str(path or json.dumps(ti, ensure_ascii=False)[:2000])
    if ti.get("url") or "fetch" in name or "web" in name:
        return "访问网页", str(ti.get("url") or json.dumps(ti, ensure_ascii=False)[:2000])
    return f"使用工具 {tool_name or '（未知）'}", json.dumps(ti, ensure_ascii=False, indent=2)[:2000]


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
                          tool_input: dict, simulated: bool = False, label: str = "", title: str = "",
                          context: str = "") -> dict:
    emp = STATE.employee_for(agent, label, "D:/演示项目" if simulated else cwd,
                             "" if simulated else session_id, title)
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
        "label": label or agent,
        "employeeId": emp["id"],
        "employeeName": emp["name"],
        "employeeLook": emp["look"],
        "context": context,
        "hash": content_hash(body),
        "status": "pending",
        "created": now(),
        "resolvedBy": None,
        "simulated": simulated,
    }
    STATE.approvals[a["id"]] = a
    STATE.waiters[a["id"]] = asyncio.get_running_loop().create_future()
    await STATE.broadcast({"type": "approval", "approval": public(a)})
    await STATE.broadcast({"type": "employees", "employees": STATE.employees_public()})
    title = f"{emp['name']}（{agent_label(agent)}）请示：{summary}"
    STATE.push.send_all(STATE.devices, title, short(detail), a["id"])
    asyncio.create_task(remind(a["id"]))
    return a


def agent_label(agent: str) -> str:
    names = {"claude": "Claude", "codex": "Codex", "deepseek": "DeepSeek", "kimi": "Kimi", "glm": "智谱", "grok": "Grok",
             "gemini": "Gemini", "qwen": "Qwen", "copilot": "Copilot", "cursor": "Cursor"}
    return f"{names.get(agent, agent)} 员工"


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
    await STATE.broadcast({"type": "employees", "employees": STATE.employees_public()})
    return True


async def add_event(kind: str, agent: str, text: str, session_id: str = "", emp: dict | None = None,
                    report: str = "") -> None:
    ev = {"id": secrets.token_urlsafe(6), "kind": kind, "agent": agent,
          "text": text, "sessionId": session_id, "time": now(),
          "employeeId": emp["id"] if emp else "", "employeeName": emp["name"] if emp else "",
          "employeeLook": emp["look"] if emp else "", "report": report}
    STATE.events.append(ev)
    STATE.events = STATE.events[-50:]
    await STATE.broadcast({"type": "event", "event": ev})
    label = {"done": "完成汇报", "help": "求援", "idle": "在等你"}.get(kind, kind)
    who = f"{emp['name']}（{agent_label(agent)}）" if emp else agent_label(agent)
    STATE.push.send_all(STATE.devices, f"{who}{label}", short(text), None)


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
            label=data.get("label", ""),
            title=hook.get("title", ""),
            context=hook.get("text", ""),
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
    emp = STATE.employee_for(agent, data.get("label", ""), hook.get("cwd", ""), sid, hook.get("title", ""))
    emp["status"] = "working"
    if name == "Stop":
        emp["status"] = "resting"
        emp["reported"] = True  # 带着汇报回来了，等你听完
        report = hook.get("text", "")
        await add_event("done", agent, short(report, 60) if report else "老板，这一轮工作做完了，回来看看结果吧",
                        sid, emp, report)
    elif name == "Notification":
        msg = hook.get("message", "")
        if "permission" not in msg.lower():   # 批准类已由 PermissionRequest 处理
            emp["status"] = "waiting"
            await add_event("idle", agent, msg or "在等你回复", sid, emp)
    STATE.save_employees()
    await STATE.broadcast({"type": "employees", "employees": STATE.employees_public()})
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


async def pending(request: web.Request) -> web.Response:
    """已配对设备查询当前待批请求（测试和以后的小组件用）。"""
    require_device(request)
    return web.json_response([public(a) for a in STATE.approvals.values() if a["status"] == "pending"])


async def ack_employee(request: web.Request) -> web.Response:
    """手机上听完（或跳过）汇报：员工就可以离开店里了。"""
    require_device(request)
    data = await request.json()
    for e in STATE.employees.values():
        if e["id"] == data.get("id") and e.get("reported"):
            e["reported"] = False
            STATE.save_employees()
            await STATE.broadcast({"type": "employees", "employees": STATE.employees_public()})
    return web.json_response({"ok": True})


async def rename_employee(request: web.Request) -> web.Response:
    require_device(request)
    data = await request.json()
    name = str(data.get("name", "")).strip()[:12]
    for e in STATE.employees.values():
        if e["id"] == data.get("id") and name:
            e["name"] = name
            e["renamed"] = True
            STATE.save_employees()
            await STATE.broadcast({"type": "employees", "employees": STATE.employees_public()})
            return web.json_response({"ok": True})
    return web.json_response({"ok": False}, status=404)


async def reroll_employee(request: web.Request) -> web.Response:
    """随机换一个形象：从这家 AI 的风格池里抽，偶尔抽到特别员工。"""
    require_device(request)
    data = await request.json()
    for e in STATE.employees.values():
        if e["id"] == data.get("id"):
            used = STATE.used_looks() | {e.get("look")}
            e["look"] = pick_look(used)
            STATE.save_employees()
            await STATE.broadcast({"type": "employees", "employees": STATE.employees_public()})
            return web.json_response({"ok": True, "look": e["look"]})
    return web.json_response({"ok": False}, status=404)


async def push_key(request: web.Request) -> web.Response:
    return web.json_response({"publicKey": STATE.push.public_key})


async def simulate(request: web.Request) -> web.Response:
    """模拟一条请求，用来在没有真实 AI 任务时体验流程（卡片会标明“模拟”）。"""
    require_device(request)
    if request.query.get("kind") == "done":
        emp = STATE.employee_for("claude", "Claude Code", "D:/演示项目")
        emp["reported"] = True  # 和真实的完成事件一样：带着汇报回来
        demo = """## 完成了

我把登录页的表单校验改好了：邮箱格式不对时会提示，密码少于 8 位也会拦下。

**改了这些文件：**
- `src/login.ts`：新增校验函数
- `src/login.test.ts`：补了 6 个测试，全部通过

有一点要你决定：要不要顺便把注册页也用同一套校验？我建议要，改动不大。（这是模拟汇报）"""
        await add_event("done", "claude", "老板，这一轮工作做完了（模拟）", "demo", emp, demo)
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


def lan_ip() -> str:
    """本机在局域网里的地址（手机要用它来访问）。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def qr_svg(text: str) -> str:
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError:
        return ""
    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=12, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode()


async def setup_info(request: web.Request) -> web.Response:
    """电脑上的设置页用：手机网址、二维码、配对码、给 AI 的连接说明路径。只限本机。"""
    local_only(request)
    if request.query.get("new") == "1" or not STATE.pair_code or now() > STATE.pair_expires:
        STATE.new_pair_code()
    url = f"http://{lan_ip()}:{PORT}/?pair={STATE.pair_code}"
    skill = (Path(sys.executable).parent if FROZEN else ROOT.parent) / "connect-ai" / "SKILL.md"
    hook_cmd = (f'"{sys.executable}" hook --agent <你的工具名>' if FROZEN
                else f'python "{ROOT / "main.py"}" hook --agent <你的工具名>')
    return web.json_response({
        "url": url, "code": STATE.pair_code, "expiresIn": int(STATE.pair_expires - now()),
        "qr": base64.b64encode(qr_svg(url).encode()).decode(),
        "devices": [{"name": d["name"], "paired": d["paired"]} for d in STATE.devices.values()],
        "skillPath": str(skill), "hookCommand": hook_cmd,
        "prompt": f"请阅读 {skill}，按里面的步骤把“待机回收站”连接到你自己身上，完成后帮我做一次测试。",
    })


# ---------------- 一键连接 Claude Code / 开机自动运行（只限本机） ----------------

CLAUDE_SETTINGS = Path(os.environ.get("STANDBY_CLAUDE_SETTINGS",
                                      Path.home() / ".claude" / "settings.json"))
CLAUDE_EVENTS = {  # 事件 -> (matcher, 超时秒数)
    "PermissionRequest": ("*", 3600),
    "PostToolUse": ("*", 10),
    "Stop": (None, 10),
    "Notification": (None, 10),
    "UserPromptSubmit": (None, 10),
}
STARTUP_DIR = Path(os.environ.get("STANDBY_STARTUP_DIR", Path(os.environ.get("APPDATA", Path.home()))
                                  / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"))
STARTUP_FILE = STARTUP_DIR / "待机回收站.cmd"


def hook_command(agent: str) -> str:
    if FROZEN:
        return f'"{sys.executable}" hook --agent {agent}'
    return f'python "{ROOT / "main.py"}" hook --agent {agent}'


def _is_ours(cmd: str) -> bool:
    return "hook --agent" in cmd and ("待机回收站" in cmd or "main.py" in cmd or "claude_hook.py" in cmd)


def _strip_ours(hooks: dict) -> dict:
    """去掉之前写进去的待机回收站钩子（程序换了位置也能清干净），保留用户自己的。"""
    out = {}
    for event, groups in hooks.items():
        kept = []
        for g in groups if isinstance(groups, list) else []:
            inner = [h for h in g.get("hooks", []) if not _is_ours(str(h.get("command", "")))]
            if inner:
                kept.append({**g, "hooks": inner})
        if kept:
            out[event] = kept
    return out


def claude_status() -> dict:
    try:
        cfg = json.loads(CLAUDE_SETTINGS.read_text("utf-8")) if CLAUDE_SETTINGS.exists() else {}
    except ValueError:
        return {"connected": False, "error": "settings.json 格式有误，没有改动"}
    cmds = [h.get("command", "") for gs in cfg.get("hooks", {}).values() if isinstance(gs, list)
            for g in gs for h in g.get("hooks", [])]
    mine = [c for c in cmds if _is_ours(str(c))]
    return {"connected": any(hook_command("claude") == c for c in mine), "stale": bool(mine) and
            not any(hook_command("claude") == c for c in mine), "path": str(CLAUDE_SETTINGS)}


async def connect_claude(request: web.Request) -> web.Response:
    """把钩子写进用户级 ~/.claude/settings.json（先备份、只增删自己的条目）。DELETE 是断开。"""
    local_only(request)
    if request.method == "GET":
        return web.json_response(claude_status())
    try:
        cfg = json.loads(CLAUDE_SETTINGS.read_text("utf-8")) if CLAUDE_SETTINGS.exists() else {}
    except ValueError:
        return web.json_response({"ok": False, "error": "settings.json 格式有误，没有改动"}, status=400)
    if CLAUDE_SETTINGS.exists():
        backup = CLAUDE_SETTINGS.with_name(f"settings.json.bak-待机回收站-{int(now())}")
        backup.write_text(CLAUDE_SETTINGS.read_text("utf-8"), "utf-8")
    hooks = _strip_ours(cfg.get("hooks", {}))
    if request.method == "POST":
        for event, (matcher, timeout) in CLAUDE_EVENTS.items():
            group = {"hooks": [{"type": "command", "command": hook_command("claude"), "timeout": timeout}]}
            if matcher:
                group = {"matcher": matcher, **group}
            hooks.setdefault(event, []).append(group)
    if hooks:
        cfg["hooks"] = hooks
    else:
        cfg.pop("hooks", None)
    CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    CLAUDE_SETTINGS.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
    return web.json_response({"ok": True, **claude_status()})


async def autostart(request: web.Request) -> web.Response:
    """开机自动运行：在“启动”文件夹里放一个小脚本（不打开设置页）。DELETE 是关闭。"""
    local_only(request)
    if request.method == "POST":
        STARTUP_DIR.mkdir(parents=True, exist_ok=True)
        target = (f'start "" /min "{sys.executable}" --no-browser' if FROZEN
                  else f'start "" /min python "{ROOT / "main.py"}" --no-browser')
        # UTF-8 + chcp 65001：路径里有中文时，任何语言的 Windows 都能正确读取
        STARTUP_FILE.write_text(f"@echo off\r\nchcp 65001 >nul\r\n{target}\r\n", "utf-8", newline="")
    elif request.method == "DELETE" and STARTUP_FILE.exists():
        STARTUP_FILE.unlink()
    return web.json_response({"enabled": STARTUP_FILE.exists()})


async def setup_test(request: web.Request) -> web.Response:
    """设置页的“试一下”：给手机发一条模拟请求。只限本机。"""
    local_only(request)
    a = await create_approval("claude", "demo", "D:/demo-project", "Bash",
                              {"command": "npm install left-pad"}, simulated=True, label="测试")
    asyncio.create_task(_auto_clear_sim(a["id"]))
    return web.json_response({"approvalId": a["id"]})


async def setup_page(request: web.Request) -> web.FileResponse:
    local_only(request)
    return web.FileResponse(WEB_DIR / "setup.html")


async def save_get(request: web.Request) -> web.Response:
    dev = require_device(request)
    f = SAVES_DIR / f"{dev['id']}.json"
    return web.json_response(json.loads(f.read_text("utf-8")) if f.exists() else None)


async def save_put(request: web.Request) -> web.Response:
    """手机上的存档在电脑上也备份一份：换了网络地址、清了浏览器数据都能找回。"""
    dev = require_device(request)
    data = await request.json()
    (SAVES_DIR / f"{dev['id']}.json").write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    return web.json_response({"ok": True})


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
    app.router.add_get("/api/pending", pending)
    app.router.add_post("/api/employee/rename", rename_employee)
    app.router.add_post("/api/employee/ack", ack_employee)
    app.router.add_post("/api/employee/reroll", reroll_employee)
    app.router.add_post("/api/simulate", simulate)
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/setup", setup_page)
    app.router.add_get("/api/setup-info", setup_info)
    app.router.add_post("/api/setup-test", setup_test)
    app.router.add_route("*", "/api/connect/claude", connect_claude)
    app.router.add_route("*", "/api/autostart", autostart)
    app.router.add_get("/api/save", save_get)
    app.router.add_post("/api/save", save_put)
    app.router.add_get("/", index)
    app.router.add_static("/", WEB_DIR, show_index=False)
    return app


def main(open_browser: bool = True) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    STATE.new_pair_code()
    phone = f"http://{lan_ip()}:{PORT}"
    print("=" * 56)
    print("  待机回收站 已启动（关掉这个窗口就会停止）")
    print(f"  手机打开：  {phone}   （手机和电脑连同一个 Wi-Fi）")
    print(f"  电脑设置页：http://localhost:{PORT}/setup   （扫码配对、连接 AI）")
    print(f"  已配对手机：{len(STATE.devices)} 台")
    print("=" * 56)
    if open_browser:
        import threading
        import webbrowser
        threading.Timer(1.2, lambda: webbrowser.open(f"http://localhost:{PORT}/setup")).start()
    web.run_app(make_app(), host="0.0.0.0", port=PORT, print=None)


if __name__ == "__main__":
    main()
