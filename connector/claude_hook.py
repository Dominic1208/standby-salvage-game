"""Claude Code 钩子脚本：把事件转给连接程序。

- PermissionRequest：阻塞等待手机决定。连接程序没开、或一直没人处理时，
  什么也不输出就退出，Claude Code 照常在电脑上弹确认框（永远不会自动批准）。
- Stop / Notification / PostToolUse / UserPromptSubmit：只通知，不阻塞。

只用标准库，避免钩子启动慢。
"""

import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8787"
MAX_WAIT = 55 * 60   # 必须小于 settings.json 里这个钩子的 timeout（3600 秒）
POLL = 25


def post(path: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def handle_permission(hook: dict) -> None:
    deadline = time.time() + MAX_WAIT
    body = {"agent": "claude", "hook": hook, "wait": POLL}
    approval_id = None
    while time.time() < deadline:
        try:
            res = post("/hook/permission", body, timeout=POLL + 10)
        except Exception:
            return  # 连接程序不在：交回电脑处理
        approval_id = res.get("approvalId")
        decision = res.get("decision")
        if decision == "allow":
            emit({"behavior": "allow"})
            return
        if decision == "deny":
            emit({"behavior": "deny", "message": "用户在手机上拒绝了这个操作。"})
            return
        if decision != "wait":
            return  # stale / gone：已在电脑上处理或已失效
        body = {"approvalId": approval_id, "wait": POLL}
    if approval_id:
        try:
            post("/hook/abandon", {"approvalId": approval_id}, timeout=5)
        except Exception:
            pass


def emit(decision: dict) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": decision,
        }
    }))  # 保持 ASCII 转义，避免 Windows 控制台编码把中文弄乱


def main() -> None:
    try:
        hook = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    except ValueError:
        return
    if hook.get("hook_event_name") == "PermissionRequest":
        handle_permission(hook)
        return
    try:
        post("/hook/event", {"agent": "claude", "hook": hook}, timeout=3)
    except Exception:
        pass


if __name__ == "__main__":
    main()
