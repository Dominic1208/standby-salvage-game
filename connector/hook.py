"""通用 AI 钩子：任何"执行前会回调一个命令"的 AI 工具都能用它接入待机回收站。

用法（由 AI 工具在执行操作前调用，JSON 从 stdin 传入）：
  待机回收站.exe hook --agent <名字>
  python connector/main.py hook --agent <名字>

--agent 决定怎么读输入、怎么写输出（见 PROFILES）。不认识的名字按 generic 处理。

安全原则：
- 连接程序没开、或手机一直没处理 → 绝不自动批准：钩子不输出（或输出 ask），
  AI 工具按它原本的规则在电脑上问你，效果等于没装待机回收站。
- 只认手机上的批准/拒绝，钩子本身从不替用户做决定。
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8787"
POLL = 25

# 每种工具的输出格式。fallback 是"没有手机决定时"的处理：
#   "silent"  什么都不输出 = 钩子不发表意见，工具按它原本的规则在电脑上询问（等于没装待机回收站）
#   "ask"     明确输出 ask，让工具在电脑上询问
PROFILES = {
    "claude": {"fallback": "silent", "max_wait": 55 * 60},
    "codex": {"fallback": "silent", "max_wait": 55 * 60},
    "qwen": {"fallback": "silent", "max_wait": 55 * 60},
    "copilot": {"fallback": "ask", "max_wait": 9 * 60},
    "gemini": {"fallback": "silent", "max_wait": 9 * 60},
    "cursor": {"fallback": "silent", "max_wait": 9 * 60},
    "generic": {"fallback": "silent", "max_wait": 9 * 60},
}
# Claude Code 可以改接国内模型的兼容接口：按接口地址识别，员工算在对应模型名下
PROVIDERS = (("deepseek", "deepseek", "DeepSeek"), ("moonshot", "kimi", "Kimi"),
             ("kimi", "kimi", "Kimi"), ("bigmodel", "glm", "智谱 GLM"), ("zhipu", "glm", "智谱 GLM"))
LABELS = {"grok": "Grok", "claude": "Claude Code", "codex": "Codex", "gemini": "Gemini CLI", "qwen": "Qwen Code",
          "copilot": "Copilot", "cursor": "Cursor"}


def emit(agent: str, event: str, decision: str, reason: str = "") -> None:
    """按工具要求的格式输出决定。decision: allow / deny / ask。"""
    if agent in ("claude", "codex", "qwen") and event == "PermissionRequest":
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
        "title": chat_title(raw.get("transcript_path", "")),
        "text": next((raw[k] for k in ("last_assistant_message", "prompt_response")
                      if isinstance(raw.get(k), str) and raw.get(k)), ""),
    }


def chat_title(transcript_path: str) -> str:
    """Claude Code 把对话标题记在对话记录里（"custom-title"）。从文件末尾往前找最新的一条。"""
    if not transcript_path:
        return ""
    try:
        with open(transcript_path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 400_000))
            tail = f.read().decode("utf-8", "ignore")
        if '"custom-title"' not in tail and size > 400_000:
            with open(transcript_path, "rb") as f:
                tail = f.read().decode("utf-8", "ignore")
        for line in reversed(tail.splitlines()):
            if '"custom-title"' in line:
                return str(json.loads(line).get("customTitle", ""))[:24]
    except (OSError, ValueError):
        pass
    return ""


REPORT_LIMIT = 6000   # 请示时 AI 动手前的说明最多带多少字
TURN_LIMIT = 40000    # 完成汇报：这一轮 AI 说过的全部话最多带多少字


def _read_tail(path: str, size: int = 600_000) -> str:
    with open(path, "rb") as f:
        f.seek(0, 2)
        end = f.tell()
        f.seek(max(0, end - size))
        return f.read().decode("utf-8", "ignore")


def _is_real_user(item: dict) -> bool:
    """用户真正发的消息（不是工具结果）。Claude 和 Codex 两种对话记录都认。"""
    if item.get("type") == "user":
        content = (item.get("message") or {}).get("content")
        if isinstance(content, str):
            return True
        return any(isinstance(c, dict) and c.get("type") == "text" for c in content or [])
    p = item.get("payload") or {}
    return item.get("type") == "response_item" and p.get("type") == "message" and p.get("role") == "user"         and not any("<environment_context>" in str(c.get("text", "")) for c in p.get("content") or [])


def _ai_texts(item: dict) -> list[str]:
    if item.get("type") == "assistant":
        content = (item.get("message") or {}).get("content") or []
        return [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
    p = item.get("payload") or {}
    if item.get("type") == "response_item" and p.get("type") == "message" and p.get("role") == "assistant":
        return [c.get("text", "") for c in p.get("content") or [] if isinstance(c, dict)]
    return []


def turn_ai_text(transcript_path: str) -> str:
    """完成汇报用：从用户最后一次发消息开始，AI 这一轮说过的全部话（中间的进度说明也算）。"""
    if not transcript_path:
        return ""
    try:
        lines = _read_tail(transcript_path, 3_000_000).splitlines()
    except OSError:
        return ""
    parts: list[str] = []
    for line in reversed(lines):
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if _is_real_user(item):
            break
        texts = [x for x in _ai_texts(item) if x.strip()]
        if texts:
            parts.append(chr(10).join(texts))
    text = (chr(10) * 2).join(reversed(parts)).strip()
    return text[:TURN_LIMIT] + ("……（后面太长，没带过来）" if len(text) > TURN_LIMIT else "")


def latest_ai_text(transcript_path: str) -> str:
    """AI 最近说的话：从对话记录末尾往前，收集上一条用户消息/工具结果之后 AI 写的文字。
    任务完成时就是最终汇报；请示批准时就是它动手前的说明。"""
    if not transcript_path:
        return ""
    try:
        lines = _read_tail(transcript_path).splitlines()
    except OSError:
        return ""
    parts: list[str] = []
    for line in reversed(lines):
        try:
            item = json.loads(line)
        except ValueError:
            continue
        kind = item.get("type")
        if kind == "user":
            break
        if kind != "assistant":
            continue
        content = (item.get("message") or {}).get("content") or []
        texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
        if texts:
            parts.append(chr(10).join(t for t in texts if t.strip()))
    text = (chr(10) * 2).join(reversed([p for p in parts if p.strip()])).strip()
    return text[:REPORT_LIMIT] + ("……" if len(text) > REPORT_LIMIT else "")


def post(path: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(BASE + path, data=json.dumps(body, ensure_ascii=False).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def ask_phone(agent: str, hook: dict) -> None:
    hook["text"] = hook.get("text") or latest_ai_text(hook.get("transcript_path", ""))
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


def server_up() -> bool:
    """先快速探测待机回收站有没有开：没开就立刻退出，不拖慢 AI 的每一步。"""
    try:
        with socket.create_connection(("127.0.0.1", int(BASE.rsplit(":", 1)[1])), timeout=0.3):
            return True
    except OSError:
        return False


def run(agent: str) -> None:
    try:
        raw = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    except ValueError:
        return
    if not server_up():
        return  # 不输出 = 钩子不发表意见，AI 照常在电脑上问你
    hook = normalize(raw)
    event = hook["event"]
    # 只通知、不需要决定的事件
    if event in ("Stop", "Notification", "PostToolUse", "UserPromptSubmit", "AfterAgent", "stop",
                 "SessionEnd", "afterAgentResponse", "BeforeAgent"):
        if event in ("Stop", "stop", "AfterAgent", "afterAgentResponse"):
            # 带上这一轮的全部话；读不到对话记录时退回工具给的“最后一句”
            whole = turn_ai_text(hook.get("transcript_path", ""))
            hook["text"] = whole if len(whole) >= len(hook.get("text") or "") else hook["text"]
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
