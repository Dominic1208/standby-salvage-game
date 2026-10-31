"""自测：用各家工具的输入格式调用钩子，自动在“手机端”批准或拒绝，检查输出格式。

用法（连接程序需要在运行，且至少配对过一台设备）：python tools/test_hooks.py
"""

import json
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8787"
TOKEN = next(iter(json.loads((ROOT / "connector/data/devices.json").read_text("utf-8")).values()))["token"]

CASES = [
    ("claude", {"hook_event_name": "PermissionRequest", "session_id": "t1", "cwd": "D:/x",
                "tool_name": "Bash", "tool_input": {"command": "echo claude"}}, "allow"),
    ("gemini", {"hook_event_name": "BeforeTool", "session_id": "t2", "cwd": "D:/x",
                "tool_name": "run_shell_command", "tool_input": {"command": "echo gemini"}}, "deny"),
    ("qwen", {"hook_event_name": "PreToolUse", "session_id": "t3", "cwd": "D:/x",
              "tool_name": "write_file", "tool_input": {"file_path": "D:/x/a.txt"}}, "allow"),
    ("copilot", {"toolName": "bash", "toolArgs": "{\"command\": \"echo copilot\"}", "cwd": "D:/x"}, "allow"),
    ("cursor", {"hook_event_name": "beforeShellExecution", "command": "echo cursor",
                "conversation_id": "t5", "workspace_roots": ["D:/x"]}, "deny"),
]


def api(path, body=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "X-Device-Token": TOKEN})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def decide_when_ready(summary_hint, decision):
    import asyncio  # noqa: F401  （只为保持标准库）
    for _ in range(50):
        time.sleep(0.2)
        # 通过 WebSocket 太重，这里直接读快照接口不存在 → 用 /api/decide 需要 id，靠 setup 测试太绕，
        # 所以从连接程序的调试端点取最新待批请求
        try:
            pend = api("/api/pending")
        except Exception:
            continue
        for a in pend:
            if summary_hint in a["detail"]:
                return api("/api/decide", {"approvalId": a["id"], "hash": a["hash"], "decision": decision})


def main():
    ok = True
    for agent, payload, decision in CASES:
        hint = json.dumps(payload, ensure_ascii=False)
        hint = "echo " + agent if "echo" in hint else "a.txt"
        t = threading.Thread(target=decide_when_ready, args=(hint, decision))
        t.start()
        out = subprocess.run([sys.executable, str(ROOT / "connector/main.py"), "hook", "--agent", agent],
                             input=json.dumps(payload).encode(), capture_output=True, timeout=60).stdout.decode()
        t.join()
        print(f"{agent:8s} 期望 {decision:5s} → {out}")
        ok &= decision in out
    print("全部通过" if ok else "有失败")


if __name__ == "__main__":
    main()
