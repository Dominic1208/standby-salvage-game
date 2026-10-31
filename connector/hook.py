"""通用 AI 钩子：任何"执行前会回调一个命令"的 AI 工具都能用它接入待机回收站。

用法（由 AI 工具在执行操作前调用，JSON 从 stdin 传入）：
  待机回收站.exe hook --agent <名字>
  python connector/main.py hook --agent <名字>

--agent 决定怎么读输入、怎么写输出（见 PROFILES）。不认识的名字按 generic 处理。

安全原则：
- 连接程序没开、或手机一直没处理 → 绝不自动批准。
  能"交回电脑询问"的工具就交回；不能的工具（没输出就等于放行）就拦下并说明原因。
- 只认手机上的批准/拒绝，钩子本身从不替用户做决定。
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8787"
POLL = 25

# 每种工具的输出格式。fallback 是"没有手机决定时"的处理：
#   "silent"  什么都不输出，工具照常在电脑上询问（只有 Claude 的 PermissionRequest 是这样）
#   "ask"     输出 ask，让工具在电脑上询问
#   "deny"    输出拒绝并说明原因（用于"没输出就放行"的工具，防止超时被自动执行）
PROFILES = {
    "claude": {"fallback": "silent", "max_wait": 55 * 60},
    "codex": {"fallback": "silent", "max_wait": 55 * 60},
    "qwen": {"fallback": "ask", "max_wait": 9 * 60},
    "copilot": {"fallback": "ask", "max_wait": 9 * 60},
    "gemini": {"fallback": "deny", "max_wait": 9 * 60},
    "cursor": {"fallback": "deny", "max_wait": 9 * 60},
    "generic": {"fallback": "deny", "max_wait": 9 * 60},
}
# Claude Code 可以改接国内模型的兼容接口：按接口地址识别，员工算在对应模型名下
PROVIDERS = (("deepseek", "deepseek", "DeepSeek"), ("moonshot", "kimi", "Kimi"),
             ("kimi", "kimi", "Kimi"), ("bigmodel", "glm", "智谱 GLM"), ("zhipu", "glm", "智谱 GLM"))
LABELS = {"claude": "Claude Code", "codex": "Codex", "gemini": "Gemini CLI", "qwen": "Qwen Code",
          "copilot": "Copilot", "cursor": "Cursor"}


def emit(agent: str, event: str, decision: str, reason: str = "") -> None:
    """按工具要求的格式输出决定。decision: allow / deny / ask。"""
    if agent in ("claude", "codex") and event == "PermissionRequest":
        if decision == "ask":
            return  # 不输出 = 交回电脑上的确认框
        body = {"behavior": decision}
        if decision == "deny":
            body["message"] = reason
        out = {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": body}}
    elif agent in ("claude", "codex", "qwen"):
        out = {"hookSpecificOutput": {"hookEventName": event or "PreToolUse",
                                      "permissionDecision": decision,
                                      "permissionDecisionReason": reason}}
    elif agent == "copilot":
        out = {"permissionDecision": decision, "permissionDecisionReason": reason}
    elif agent == "cursor":
        out = {"permission": decision, "userMessage": reason, "agentMessage": reason}
    else:  # gemini 和 generic
        out = {"decision": "deny" if decision == "ask" else decision, "reason": reason}
    sys.stdout.write(json.dumps(out))  # ASCII 转义，避免 Windows 控制台编码问题
    sys.stdout.flush()


def normalize(raw: dict) -> dict:
    """把各家工具不同的字段名统一成 {event, session_id, cwd, tool_name, tool_input}。"""
    ti = raw.get("tool_input") or raw.get("toolInput") or raw.get("toolArgs") or raw.get("args") or {}
    if isinstance(ti, str):
        try:
            ti = json.loads(ti)
        except ValueError:
            ti = {"command": ti}
    if "command" in raw and "command" not in ti:
        ti = {**ti, "command": raw["command"]}
    return {
        "event": raw.get("hook_event_name") or raw.get("hookEventName") or raw.get("event") or "",
        "session_id": str(raw.get("session_id") or raw.get("sessionId") or raw.get("conversation_id")
                          or raw.get("generation_id") or ""),
        "cwd": raw.get("cwd") or (raw.get("workspace_roots") or [""])[0],
        "tool_name": raw.get("tool_name") or raw.get("toolName") or ("Bash" if "command" in raw else ""),
        "tool_input": ti,
        "transcript_path": raw.get("transcript_path", ""),
    }


def post(path: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(BASE + path, data=json.dumps(body, ensure_ascii=False).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def ask_phone(agent: str, hook: dict) -> None:
    profile = PROFILES.get(agent, PROFILES["generic"])
    deadline = time.time() + profile["max_wait"]
    who, label = display_agent(agent)
    body = {"agent": who, "label": label, "hook": hook, "wait": POLL}
    approval_id = None
    reached = False
    while time.time() < deadline:
        try:
            res = post("/hook/permission", body, timeout=POLL + 10)
            reached = True
        except Exception:
            break
        approval_id = res.get("approvalId")
        decision = res.get("decision")
        if decision == "allow":
            return emit(agent, hook["event"], "allow", "已在手机上批准")
        if decision == "deny":
            return emit(agent, hook["event"], "deny", "用户在手机上拒绝了这个操作。")
        if decision != "wait":
            break  # 已在电脑上处理或失效
        body = {"approvalId": approval_id, "wait": POLL}
    if approval_id:
        try:
            post("/hook/abandon", {"approvalId": approval_id}, timeout=5)
        except Exception:
            pass
    fallback = profile["fallback"]
    if fallback == "silent":
        return
    reason = ("手机上一直没有处理，已拦下这一步。请在电脑上确认后重试。" if reached
              else "待机回收站没有运行，已拦下这一步。打开待机回收站，或在电脑上重试。")
    emit(agent, hook["event"], "ask" if fallback == "ask" else "deny", reason)


def display_agent(agent: str) -> tuple[str, str]:
    """返回（显示用的员工归属, 显示名）。输出格式仍按原来的工具。"""
    if agent == "claude":
        base = (os.environ.get("ANTHROPIC_BASE_URL", "") + " " + os.environ.get("ANTHROPIC_MODEL", "")).lower()
        for key, who, label in PROVIDERS:
            if key in base:
                return who, label
    return agent, LABELS.get(agent, agent)


def run(agent: str) -> None:
    try:
        raw = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    except ValueError:
        return
    hook = normalize(raw)
    event = hook["event"]
    # 只通知、不需要决定的事件
    if event in ("Stop", "Notification", "PostToolUse", "UserPromptSubmit", "AfterAgent", "stop",
                 "SessionEnd", "afterAgentResponse"):
        try:
            who, label = display_agent(agent)
            post("/hook/event", {"agent": who, "label": label, "hook": {**raw, **hook,
                                 "hook_event_name": "Stop" if event in ("AfterAgent", "stop", "afterAgentResponse")
                                 else event}}, timeout=3)
        except Exception:
            pass
        return
    ask_phone(agent, hook)


if __name__ == "__main__":
    agent = sys.argv[sys.argv.index("--agent") + 1] if "--agent" in sys.argv else "generic"
    run(agent)
