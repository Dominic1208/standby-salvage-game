// 跑单元测试：把 test/*.test.js 和游戏代码打包（平台层换成 fake-platform.js），再交给 node --test。
// 用法：node test/run.mjs
import * as esbuild from "esbuild";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(HERE, "..", "build", "test");
fs.rmSync(OUT, { recursive: true, force: true });

const fakePlatform = {
  name: "fake-platform",
  setup(b) {
    b.onResolve({ filter: /(^|\/)platform\.js$/ }, () => ({ path: path.join(HERE, "fake-platform.js") }));
  },
};

const tests = fs.readdirSync(HERE).filter((f) => f.endsWith(".test.js"));
for (const t of tests) {
  await esbuild.build({
    entryPoints: [path.join(HERE, t)], bundle: true, platform: "node", format: "esm",
    outfile: path.join(OUT, t.replace(/\.js$/, ".mjs")), plugins: [fakePlatform], logLevel: "warning",
  });
}
const r = spawnSync(process.execPath, ["--test", ...tests.map((t) => path.join(OUT, t.replace(/\.js$/, ".mjs")))], { stdio: "inherit" });
process.exit(r.status ?? 1);
