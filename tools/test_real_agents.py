"""真实 AI 端到端测试：让真实的 AI 工具新建一个文件，测试程序扮演手机自动批准，
检查：① 请求到了“手机” ② 批准后 AI 真的继续执行（文件被创建） ③ 完成后员工带着汇报回来。

用法：python tools/test_real_agents.py codex|gemini|deepseek
需要待机回收站正在运行，并且对应工具已经“一键连接”。
"""

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import winreg
from pathlib import Path

B = "http://127.0.0.1:8787"
WORK = Path(r"D:\AI\standby-real-test")
NODE = r"C:\Program Files\nodejs"
NPM = str(Path.home() / ".npm-global")
CLAUDE = r"C:\Users\ZHA00\AppData\Local\Claude-Data\claude_pzs8sxrjxfjjc\claude-code\2.1.309\9078b9c1d466\claude.exe"
CODEX = r"C:\Users\ZHA00\AppData\Local\OpenAI\Codex\bin\2993767bd1dfb009\codex.exe"


def call(path, body=None, token="", method=None):
    req = urllib.request.Request(B + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "X-Device-Token": token}, method=method)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read() or b"null")


def user_env(name):
    """从注册表读用户环境变量（不打印）。"""
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
        return winreg.QueryValueEx(k, name)[0]


def listen_events(token, sink, stop):
    """扮演手机的 WebSocket：收集员工汇报。"""
    import aiohttp

    async def run():
        async with aiohttp.ClientSession() as s:
            async with s.ws_connect(f"ws://127.0.0.1:8787/ws?token={token}") as ws:
                while not stop.is_set():
                    try:
                        msg = await ws.receive_json(timeout=1)
                    except asyncio.TimeoutError:
                        continue
                    except Exception:
                        return
                    if msg.get("type") == "event":
                        sink.append(msg["event"])
    asyncio.run(run())


def main(which):
    sys.stdout.reconfigure(encoding="utf-8")
    WORK.mkdir(exist_ok=True)
    target = WORK / f"hello_{which}.txt"
    if target.exists():
        target.unlink()
    code = call("/api/setup-info")["code"]
    dev = call("/api/pair", {"code": code, "name": f"真机测试-{which}"})
    token = dev["token"]
    events, approvals, stop = [], [], threading.Event()
    threading.Thread(target=listen_events, args=(token, events, stop), daemon=True).start()

    def phone():
        seen = set()
        while not stop.is_set():
            time.sleep(0.4)
            for a in call("/api/pending", token=token):
                if a["id"] in seen or "standby-real-test" not in (a.get("cwd") or ""):
                    continue
                seen.add(a["id"])
                approvals.append(a)
                print(f"📱 收到请求：{a['employeeName']}（{a['label']}）要{a['summary']}：{a['detail'][:70]!r}")
                if a.get("context"):
                    print(f"   AI 动手前说：{a['context'][:80]!r}")
                r = call("/api/decide", {"approvalId": a["id"], "hash": a["hash"], "decision": "allow"}, token)
                print(f"📱 滑动批准 → {r['result']}")
    threading.Thread(target=phone, daemon=True).start()

    prompt = (f"在当前文件夹新建一个文件 {target.name}，内容是：{which} 手机批准成功。"
              "只做这一件事，完成后用一句话告诉我。")
    env = dict(os.environ)
    env["PATH"] = NODE + ";" + NPM + ";" + env.get("PATH", "")
    if which == "codex":
        cmd = [CODEX, "exec", "--skip-git-repo-check", "-s", "read-only", "-c", 'approval_policy="on-request"', prompt]
    elif which == "gemini":
        env["GEMINI_CLI_TRUST_WORKSPACE"] = "true"  # 测试文件夹是我们自己建的
        cmd = ["cmd", "/c", str(Path(NPM) / "gemini.cmd"), "-p", prompt]
    elif which == "deepseek":
        env["ANTHROPIC_BASE_URL"] = "https://api.deepseek.com/anthropic"
        env["ANTHROPIC_API_KEY"] = user_env("DEEPSEEK_API_KEY")
        env["ANTHROPIC_MODEL"] = "deepseek-chat"
        cmd = [CLAUDE, "-p", prompt, "--permission-mode", "default", "--tools", "Bash,Read,Write,Edit"]
    else:
        raise SystemExit("用法：codex | gemini | deepseek")
    print(f"▶ 运行真实的 {which}……")
    t = time.time()
    p = subprocess.run(cmd, cwd=WORK, env=env, capture_output=True, timeout=600)
    out = p.stdout.decode("utf-8", "ignore").strip()
    print(f"■ {which} 结束（退出码 {p.returncode}，{time.time() - t:.0f} 秒）：{out[-160:]!r}")
    if p.returncode:
        print("  stderr：", p.stderr.decode("utf-8", "ignore")[-400:])
    time.sleep(3)
    stop.set()
    done = [e for e in events if e.get("kind") == "done" and "standby-real-test" in json.dumps(e, ensure_ascii=False)
            or e.get("kind") == "done"]
    print("— 结果 —")
    print("① 请求到了手机：", "✅" if approvals else "❌")
    print("② 批准后文件被创建：", "✅ " + target.read_text("utf-8", "ignore").strip() if target.exists() else "❌")
    if done:
        print(f"③ 员工带着汇报回来：✅ {done[-1].get('employeeName')}：{(done[-1].get('report') or done[-1].get('text'))[:80]!r}")
    else:
        print("③ 员工带着汇报回来：❌")
    call(f"/api/devices/{dev['deviceId']}", method="DELETE")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "codex")
