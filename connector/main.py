"""待机回收站 · 程序入口

双击 / 不带参数：启动连接程序，并在电脑浏览器里打开设置页（扫码配对、连接 AI）
hook --agent <名字>：给 AI 工具调用的钩子（见 connect-ai/SKILL.md）
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "hook":
        import hook  # 只用标准库，启动快
        agent = sys.argv[sys.argv.index("--agent") + 1] if "--agent" in sys.argv else "generic"
        hook.run(agent)
        return
    import server
    server.main(open_browser="--no-browser" not in sys.argv)


if __name__ == "__main__":
    main()
