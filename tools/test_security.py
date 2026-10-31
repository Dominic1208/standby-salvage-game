"""安全测试（清单 A1–A7）：对着正在运行的待机回收站逐项验证。

用法：先运行待机回收站，再 python tools/test_security.py
"""

import io
import json
import socket
import sys
import time
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "connector"))
import hook  # noqa: E402

LOCAL = "http://127.0.0.1:8787"
results = []


def call(base, path, body=None, token="", method=None):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "X-Device-Token": token},
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, None


def check(name, ok, detail=""):
    results.append((name, ok))
    print(("✅" if ok else "❌"), name, detail)


def lan_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    _, info = call(LOCAL, "/api/setup-info")
    code = info["code"]
    st, dev = call(LOCAL, "/api/pair", {"code": code, "name": "安全测试"})
    tok = dev["token"]
    check("配对成功", st == 200)
    st, _ = call(LOCAL, "/api/pair", {"code": code, "name": "再用一次"})
    check("A5 配对码只能用一次", st == 403, f"(第二次 {st})")

    _, a = call(LOCAL, "/api/setup-test", {})
    _, pend = call(LOCAL, "/api/pending", token=tok)
    item = next(x for x in pend if x["id"] == a["approvalId"])
    st, _ = call(LOCAL, "/api/decide", {"approvalId": item["id"], "hash": item["hash"], "decision": "allow"})
    check("A1 未配对设备不能批准", st == 401, f"({st})")
    st, _ = call(LOCAL, "/api/pending", token="fake-token-123")
    check("A1 假令牌查不到请求", st == 401, f"({st})")
    st, r = call(LOCAL, "/api/decide", {"approvalId": item["id"], "hash": "0000", "decision": "allow"}, tok)
    _, pend = call(LOCAL, "/api/pending", token=tok)
    check("A2 内容校验不对被拒绝且请求仍待处理", st == 409 and any(x["id"] == item["id"] for x in pend), f"({st})")
    st, r = call(LOCAL, "/api/decide", {"approvalId": item["id"], "hash": item["hash"], "decision": "allow"}, tok)
    check("A3 第一次批准成功", st == 200 and r["result"] == "ok", str(r))
    st, r = call(LOCAL, "/api/decide", {"approvalId": item["id"], "hash": item["hash"], "decision": "deny"}, tok)
    check("A3 第二次不再生效", r and r["result"] == "already" and r["status"] == "allow", str(r))

    lan = f"http://{lan_ip()}:8787"
    for path, body, method in [("/hook/permission", {"hook": {}}, None), ("/hook/event", {"hook": {}}, None),
                               ("/api/setup-info", None, None), ("/api/connect/claude", {}, "POST"),
                               ("/api/autostart", {}, "POST"), ("/api/setup-test", {}, None)]:
        st, _ = call(lan, path, body, method=method)
        check(f"A4 局域网访问 {path} 被拒绝", st == 403, f"({st})")

    # A7：手机一直不处理（把等待时间缩短到 3 秒）
    for agent, expect in [("claude", ""), ("gemini", ""), ("qwen", '"permissionDecision": "ask"'),
                          ("cursor", "")]:
        hook.PROFILES[agent]["max_wait"] = 3
        hook.POLL = 1
        buf = io.StringIO()
        with redirect_stdout(buf):
            hook.ask_phone(agent, {"event": "PermissionRequest" if agent == "claude" else "PreToolUse",
                                   "session_id": f"timeout-{agent}", "cwd": "D:/安全测试", "tool_name": "Bash",
                                   "tool_input": {"command": f"echo {agent}"}, "transcript_path": ""})
        out = buf.getvalue()
        ok = (out == "") if expect == "" else (expect in out)
        check(f"A7 {agent} 超时不自动批准", ok, out[:90] or "(无输出 = 交回电脑)")
        if agent != "claude":
            check(f"A7 {agent} 超时没有放行", '"allow"' not in out)

    print(f"\n通过 {sum(ok for _, ok in results)} / {len(results)}")


if __name__ == "__main__":
    main()
