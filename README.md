<h1 align="center">待机回收站</h1>

<p align="center">
AI 在电脑上干活，你在手机上经营回收站。<br>
AI 要你拍板的时候，员工推门进来找你；活干完了，员工回来跟你汇报。
</p>

<p align="center">
  <a href="../../releases/latest"><b>⬇ 下载 Windows 版</b></a>
</p>

<p align="center">
  <img src="devlog/screens/吧台前排队.jpg" width="230">
  <img src="devlog/screens/商店页修好宽度-加3成.jpg" width="230">
  <img src="devlog/screens/汇报对话框-展开全文-跳过.jpg" width="230">
</p>

## 这是什么

用 AI 写代码时，它经常干到一半停下来问你：“这个命令能跑吗？”你不在电脑前，它就一直等着。

待机回收站把这件事做成了一个手机游戏：

- **每个 AI 对话就是一个员工**：围巾颜色代表是哪家的 AI（橙色 Claude、蓝色 DeepSeek、白色 Codex）。
- **AI 要你批准时**，员工推门进来，你在手机上看清楚它要做什么，再决定批不批。
- **AI 干完活**，员工回来汇报，可以听、跳过、或者看全文；还会顺手带个包裹。
- **不等 AI 的时候**，它就是个回收站经营游戏：验货、砍价、揭穿编故事的顾客、每天打烊还贷款；赚了钱升级店铺、抽员工造型、集 1000 多件收藏品、解锁成就。

整个游戏是用 AI 做的：代码 Claude 写，美术 Codex 画，音乐 ACE-Step 生成，作者一行代码都没写。

## 怎么玩（3 步）

1. 到 [Releases](../../releases/latest) 下载 `待机回收站-Windows.zip`，解压，双击 `待机回收站.exe`
   - 弹出蓝色的“Windows 已保护你的电脑”：点“更多信息” → “仍要运行”（程序没有付费签名）
   - 弹出防火墙提示：点“允许”，不然手机连不上
2. 手机和电脑连同一个 Wi-Fi，用手机相机扫电脑上设置页的二维码，就能开始玩
3. 在设置页点“一键连接”，把你的 AI 接进来

详细说明在压缩包里的 `使用说明.txt`。

## 支持哪些 AI

| AI | 批准请求送到手机 | 干完活回来汇报 |
|---|---|---|
| Claude Code | ✅ | ✅ |
| Claude Code + DeepSeek / Kimi 等接口 | ✅ | ✅ |
| Codex | ❌（目前 Codex 不会把批准请求交给外部程序，还是在电脑上批） | ✅ |

## 安全

- 游戏只负责“通知你、让你看清楚”，**任何情况下都不会自动批准**。
- 批准卡片和游戏画面是分开的，玩游戏时手滑不会批到东西。
- 待机回收站没开、或者你没在手机上处理时，AI 照常在电脑上问你。
- 一键连接前会备份你的 AI 设置文件，设置页里随时可以“断开”。
- 所有通信只在你自己的电脑和手机之间（同一个 Wi-Fi），不经过任何服务器。

## 从源码运行

```bash
pip install -r connector/requirements.txt
python connector/main.py
```

游戏本体是 Godot 4.7 项目（`src/`），导出网页版：`python tools/export_web.py`。

## 致谢

项目骨架来自 [Claude Code Game Studios](https://github.com/Donchitos/Claude-Code-Game-Studios)（MIT 协议），原说明见 [docs/Claude-Code-Game-Studios-README.md](docs/Claude-Code-Game-Studios-README.md)。

## 协议

MIT，见 [LICENSE](LICENSE)。
