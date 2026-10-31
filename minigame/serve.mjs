// 浏览器试玩：把 dist/web 放在 http://localhost:8790 上。
// 调试用：POST /__shot?name=xxx（body 是 canvas 的 PNG dataURL）存到 build/shots/xxx.png，方便自动截图。
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), "dist", "web");
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".png": "image/png", ".jpg": "image/jpeg", ".mp3": "audio/mpeg" };

const SHOTS = path.join(path.dirname(fileURLToPath(import.meta.url)), "build", "shots");

http.createServer((req, res) => {
  if (req.method === "POST" && req.url.startsWith("/__shot")) {
    const name = (new URL(req.url, "http://x").searchParams.get("name") || "shot").replace(/[^\w\-一-鿿]/g, "_");
    let body = "";
    req.on("data", (c) => { body += c; });
    req.on("end", () => {
      fs.mkdirSync(SHOTS, { recursive: true });
      fs.writeFileSync(path.join(SHOTS, `${name}.png`), Buffer.from(body.replace(/^data:image\/png;base64,/, ""), "base64"));
      res.writeHead(200); res.end("ok");
    });
    return;
  }
  const url = decodeURIComponent(req.url.split("?")[0]);
  const file = path.join(ROOT, url === "/" ? "index.html" : url);
  if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { "Content-Type": TYPES[path.extname(file)] || "application/octet-stream", "Cache-Control": "no-store" });
  fs.createReadStream(file).pipe(res);
}).listen(8790, () => console.log("试玩：http://localhost:8790"));
