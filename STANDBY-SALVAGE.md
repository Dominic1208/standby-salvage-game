# 待机回收站（Standby Salvage）

手机上的小经营游戏，同时是电脑上 AI（Claude Code，之后加 Codex）的随身通讯台：
AI 要你批准操作时，"员工"推门进来请示，你在手机上看清楚再批准或拒绝，AI 不会因为等你而卡住。

设计依据：[design/game-brief.md](design/game-brief.md)

## 运行

1. 安装依赖（一次）：

```bash
python -m pip install --user aiohttp pywebpush cryptography
```

2. 启动电脑端连接程序，窗口里会显示 6 位配对码：

```bash
python connector/server.py
```

3. 手机和电脑连同一个 Wi-Fi，用浏览器打开 `http://<电脑局域网 IP>:8787`，输入配对码。
   想要锁屏推送：用 Tailscale 的 HTTPS 地址打开，Safari「分享 → 添加到主屏幕」，从主屏幕图标打开后点「开启锁屏通知」。

4. 接 Claude Code：把 `connector/claude-hooks.example.json` 里的 `hooks` 合并进本项目的
   `.claude/settings.local.json`，然后在这个文件夹里新开 Claude Code 会话。
   连接程序没开时钩子立刻退出，电脑上照常弹确认框；**永远不会自动批准**。

## 改游戏

- 数值：`src/data/tuning.json`；货物和顾客：`src/data/items.json`；顾客台词：`src/data/personalities.json`
- 改完导出网页版：`python tools/export_web.py`（需要 Godot 4.7.2 和网页导出模板）
- 改了台词里的新汉字，先重建字体：`python tools/build_font.py <NotoSansSC-Regular.otf>`

## 结构

| 目录 | 内容 |
| --- | --- |
| `connector/` | 电脑端连接程序（Python）+ Claude Code 钩子脚本 |
| `web/` | 手机网页外壳：配对、状态栏、员工推门、**真实批准卡片**、推送 |
| `src/` | Godot 4 游戏（只负责游戏，碰不到批准界面） |
| `tools/` | 导出、字体、美术缩图脚本 |

安全边界：批准卡片由网页外壳绘制，全屏纯文字，批准要滑动、拒绝单击、出现 1 秒内不可点；
游戏只收到 pause / resume / employee 三种消息。

字体：Noto Sans SC（SIL Open Font License 1.1）。美术：由 Codex 生成。
