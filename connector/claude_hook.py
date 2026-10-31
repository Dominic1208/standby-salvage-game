"""兼容旧配置：等同于 `main.py hook --agent claude`。新接入请用 connect-ai/SKILL.md 里的命令。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hook

if __name__ == "__main__":
    hook.run("claude")
