// 打包：src/ → dist/wechat（微信小游戏）、dist/douyin（抖音小游戏）、dist/web（浏览器试玩）。
// 每次都会先跑 tools/build_minigame_data.py（清理数据）；图片和声音只在 build/assets 不存在或加 --assets 时重新压。
// 用法：node build.mjs            三个都打
//       node build.mjs --web      只打浏览器版
//       node build.mjs --assets   连图片声音一起重新生成
import * as esbuild from "esbuild";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ASSETS = path.join(HERE, "build", "assets");
const DIST = path.join(HERE, "dist");
const APPIDS = JSON.parse(fs.readFileSync(path.join(HERE, "appid.json"), "utf8"));
const NAME = "待机回收站";

const targets = process.argv.includes("--web") ? ["web"] : ["wechat", "douyin", "web"];

function copyDir(src, dst) {
  fs.mkdirSync(dst, { recursive: true });
  for (const e of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, e.name), d = path.join(dst, e.name);
    if (e.isDirectory()) copyDir(s, d); else fs.copyFileSync(s, d);
  }
}
const write = (p, obj) => fs.writeFileSync(p, typeof obj === "string" ? obj : JSON.stringify(obj, null, 2));
function dirSize(p) {
  if (!fs.existsSync(p)) return 0;
  let n = 0;
  for (const e of fs.readdirSync(p, { withFileTypes: true })) {
    const f = path.join(p, e.name);
    n += e.isDirectory() ? dirSize(f) : fs.statSync(f).size;
  }
  return n;
}

const TOOLS = path.join(HERE, "..", "tools");
const py = (script) => execFileSync("python", [path.join(TOOLS, script)], { stdio: "inherit", env: { ...process.env, PYTHONIOENCODING: "utf-8" } });
py("build_minigame_data.py");
if (!fs.existsSync(ASSETS) || process.argv.includes("--assets")) py("build_minigame_assets.py");

for (const t of targets) {
  const out = path.join(DIST, t);
  fs.rmSync(out, { recursive: true, force: true });
  fs.mkdirSync(out, { recursive: true });
  await esbuild.build({
    entryPoints: [path.join(HERE, "src", "main.js")],
    bundle: true, minify: true, format: "iife", target: "es2017",
    outfile: path.join(out, "game.js"),
    loader: { ".json": "json" },
    legalComments: "none",
  });
  copyDir(ASSETS, out);
  if (t === "web") {
    write(path.join(out, "index.html"), `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<title>${NAME}</title>
<style>html,body{margin:0;height:100%;background:#0e0b09;overflow:hidden;touch-action:none;overscroll-behavior:none}canvas{display:block}</style>
</head><body><script src="game.js"></script></body></html>
`);
  } else {
    // 分包入口文件（平台要求每个分包里有一个 game.js）
    write(path.join(out, "res", "game.js"), "// 分包：图片和背景音乐\n");
    write(path.join(out, "game.json"), {
      deviceOrientation: "portrait",
      showStatusBar: false,
      networkTimeout: { request: 10000, connectSocket: 10000, uploadFile: 10000, downloadFile: 10000 },
      subpackages: [{ name: "res", root: "res/" }],
    });
    write(path.join(out, "project.config.json"), {
      appid: APPIDS[t] || (t === "wechat" ? "touristappid" : ""),
      projectname: "standby-salvage",
      compileType: "game",
      description: NAME,
      setting: { es6: true, postcss: false, minified: true, urlCheck: true },
      packOptions: { ignore: [] },
    });
  }
  const main = fs.statSync(path.join(out, "game.js")).size + dirSize(path.join(out, "audio"));
  const sub = dirSize(path.join(out, "res"));
  console.log(`${t.padEnd(7)} 首包 ${(main / 1048576).toFixed(2)} MB　分包 res ${(sub / 1048576).toFixed(2)} MB　→ dist/${t}`);
}
