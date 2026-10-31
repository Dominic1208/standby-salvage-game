# 待机回收站 · 微信 / 抖音小游戏版

电脑版的游戏本体，去掉“连接 AI”，员工改成游戏里的 NPC：派他们出门探险，按真实时间回来讲故事、带包裹。
一份代码打出微信、抖音、浏览器三个版本。上架流程看 [上架材料/上架教程.md](上架材料/上架教程.md)。

## 命令

```bash
npm install            # 第一次：装 esbuild
node build.mjs         # 打包 → dist/wechat、dist/douyin、dist/web（每次都会先清理数据）
node build.mjs --assets   # 图片、声音也重新压缩
node test/run.mjs      # 规则单元测试
node serve.mjs         # 试玩：http://localhost:8790
```

试玩地址：
- 浏览器版：http://localhost:8790
- 微信版模拟：http://localhost:8790/wechat/wx-sim.html（用真实的微信包跑，右上角画了胶囊菜单）
- 抖音版模拟：http://localhost:8790/douyin/wx-sim.html?tt

真机测试用微信开发者工具 / 抖音开发者工具导入 `dist/wechat`、`dist/douyin`。

## 结构

| 位置 | 内容 |
|---|---|
| `src/platform.js` | 平台层：微信（wx）、抖音（tt）、浏览器的差别都在这里（画布、触摸、存储、分包、声音、分享） |
| `src/ui.js` | 画面工具：即时模式绘制，按钮在画的时候登记点击区域 |
| `src/state.js` | 全部规则和存档：开店、买卖、打烊、贷款、包裹、员工、升级、抽造型、成就 |
| `src/deal.js` | 一笔交易：顾客性格、真实价值、线索、揭穿、砍价（从电脑版 `src/deal.gd` 移植） |
| `src/main.js` | 入口、主循环、各种弹窗 |
| `src/scenes/` | 大本营、开店两个场景 |
| `src/ads.js` | 激励视频（没填广告位就不出现） |
| `data/` | 小游戏专用数据：员工和探险地点（`staff.json`）、升级/抽卡/成就（`meta.json`）、广告位（`ads.json`） |
| `appid.json` | 两个平台的 AppID |
| `上架材料/` | 软著、截图、图标、文案、自审报告、上架教程 |

## 数据从哪来

货物、顾客、台词、包裹、数值都和电脑版共用 `../src/data/*.json`。打包时 `tools/build_minigame_data.py` 复制一份到 `build/data/`，按平台审核规范清理：
- 删掉封建迷信内容（算命、开光、塔罗……）
- 台词里的英文换成中文
- 去掉 “AI 员工” 一类说法

清理完会自动检查，有漏网的会列出来。电脑版的数据不受影响。

## 平台规范对代码的要求（改代码时别破坏）

- 顶部从胶囊菜单下面开始（`SAFE_TOP`），右上角不放按钮；面板的“返回”在左上角
- 点“开始”以后才放音乐
- 启动页的《健康游戏忠告》必须一字不差
- 游戏里不能出现英文、不能自己画适龄标识
- 首包 ≤ 4MB（现在约 0.3MB），所有分包加起来 ≤ 30MB（现在约 5.3MB）
