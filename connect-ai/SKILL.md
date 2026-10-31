---
name: connect-standby-salvage
description: 把"待机回收站"接到你（正在读这份说明的 AI 编程工具）身上：在你执行需要用户批准的操作前，把请求发到用户手机上的游戏里，由用户在手机上批准或拒绝。用户说"连接待机回收站""把待机回收站连到你身上"时使用。
---

# 把待机回收站连接到你自己

你是用户的 AI 编程工具（Claude Code、Codex、Gemini CLI、Qwen Code、GitHub Copilot CLI、Cursor 或其他）。
用户希望：你需要他批准某个操作时，请求出现在他手机上的游戏《待机回收站》里，他在手机上点批准或拒绝，你据此继续或停下。

做法：在**你自己的钩子（hook）配置**里加一条"执行操作前运行的命令"，指向待机回收站的钩子程序。
你最了解你自己的配置文件在哪、格式是什么——下面的表格是参考，**以你当前版本的官方文档为准**。

## 第 0 步：确认几件事

1. **你是哪个工具**，决定 `--agent` 的值：`claude` / `codex` / `gemini` / `qwen` / `copilot` / `cursor`；都不是就用 `generic`。
2. **钩子命令**（把 `<AGENT>` 换成上面的值）：
   - 如果这份 SKILL.md 所在文件夹的上一级有 `待机回收站.exe`（打包版）：
     `"<那个文件夹>\待机回收站.exe" hook --agent <AGENT>`
   - 否则（源码版）：`python "<那个文件夹>\connector\main.py" hook --agent <AGENT>`
   - 用**绝对路径**，路径里有中文和空格要加引号。
3. **待机回收站有没有在运行**：访问 `http://127.0.0.1:8787/api/push/key`，返回 JSON 就是在运行。没在运行就请用户双击 `待机回收站.exe`（或运行 `python connector/main.py`）。

## 第 1 步：改配置（先备份）

- 改之前把原配置文件复制一份，文件名后加 `.bak-待机回收站`。
- **合并**进现有配置，不要覆盖用户已有的钩子。
- 默认写到**用户级**配置（所有项目都生效）；用户只想在某个项目里用，就写项目级。
- 把改动内容给用户看一眼，用户同意后再写入。

### 各工具参考写法

| 工具 | 配置文件 | 需要批准时的事件 | 完成时的事件（可选） | 备注 |
|---|---|---|---|---|
| Claude Code | `~/.claude/settings.json` 的 `hooks` | `PermissionRequest`，matcher `*`，timeout `3600` | `Stop`、`Notification`、`PostToolUse`、`UserPromptSubmit`（timeout `10`） | 最理想：电脑上的确认框同时照常弹出，在哪边处理都行 |
| Codex | `~/.codex/hooks.json` 或 `config.toml` 的 hooks（可能要开 hooks 功能开关） | 优先 `PermissionRequest`；没有就用 `PreToolUse` | `Stop` | 部分版本的 `PreToolUse` 只支持拒绝、只覆盖 shell。按你的版本确认 |
| DeepSeek（模型） | 看用户用哪个工具调用 DeepSeek | 同那个工具 | 同那个工具 | 最常见是 Claude Code 设置 `ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic`：按 Claude Code 那一行接，仍用 `--agent claude`。钩子会根据这个地址自动把员工算作 DeepSeek（蓝色工牌），Kimi、智谱同理 |
| Gemini CLI | `~/.gemini/settings.json` 的 `hooks`（需要打开 hooks 的实验开关） | `BeforeTool`，matcher 只填会改东西的工具，例如 `run_shell_command\|write_file\|replace` | `AfterAgent` | 每次调用工具都会触发，**matcher 一定要收窄**，否则读文件也要手机批准 |
| Qwen Code | `~/.qwen/settings.json` 的 `hooks` | `PreToolUse`，matcher 如 `run_shell_command\|write_file\|edit` | `Stop` | 同上，收窄 matcher |
| GitHub Copilot CLI | 仓库 `.github/hooks/*.json`（`version: 1`） | `preToolUse`，只匹配 shell / 写文件类工具 | — | 同上 |
| Cursor | `~/.cursor/hooks.json`（`version: 1`） | `beforeShellExecution`（以及需要的话 `beforeMCPExecution`） | `stop` | 已知部分版本 `ask` 不生效；我们超时时返回拒绝并说明原因 |
| 其他工具 | 你自己的钩子配置 | "执行前"类事件 | "结束"类事件 | 用 `--agent generic`，输出 `{"decision":"allow\|deny","reason":"..."}`；格式对不上就写个小包装脚本转换 |

**超时**：把这条钩子的超时设成你允许的最大值（10 分钟以上更好），用户可能过一会儿才看手机。

## 第 2 步：钩子程序的行为（你需要知道的）

- 从 stdin 读你传来的 JSON，自动识别常见字段（`tool_name`/`toolName`、`tool_input`/`toolArgs`、`command`、`cwd`、`session_id`）。
- 手机上批准 → 输出"允许"；拒绝 → 输出"拒绝"并附原因。
- **永远不会自动批准**：
  - 待机回收站没开、或手机一直没处理时：钩子不输出任何决定（Qwen、Copilot 明确输出 ask），你的工具按它原本的规则在电脑上询问用户——效果等于没装待机回收站。
- "完成"类事件只通知手机（员工回店汇报），不阻塞你。

## 第 3 步：测试

1. 如果你的工具需要重启或重新加载配置才能读到新钩子，请提醒用户。
2. 做一个无害、但需要用户批准的操作，例如在当前目录新建 `standby-salvage-test.txt`。
3. 请用户看手机：应该有员工推门进来，卡片上写着你的工具名、这个文件路径，**没有**"模拟请求"的黄色提示。
4. 用户在手机上滑动批准 → 文件被创建，说明连接成功；点拒绝 → 你应收到拒绝。
5. 测完删掉测试文件。

## 撤销

把备份的配置文件改回原名即可；或者只删除包含 `hook --agent` 的那几条钩子。
