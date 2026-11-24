// 진행판에 보내는 Node 클라이언트 (설치할 패키지 없음, Node 18+)
//   import { Board } from "./board.mjs";
//   const b = new Board(); await b.ensure();
//   await b.suite("점검", [{ id: "api", items: ["로그인"] }]);
//   await b.item("api", "로그인", async () => { ... });
//   await b.done("api"); await b.finish();
// 진행판이 없거나 느려도 테스트를 막지 않는다 — 한 번 실패하면 그 뒤로는 보내지 않는다.
import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const configPort = () => { try { return Number(JSON.parse(fs.readFileSync(path.join(ROOT, "board.config.json"), "utf8")).port) || 8790; } catch { return 8790; } };
const listening = (port) => new Promise((ok) => {
  const s = net.connect({ port, host: "127.0.0.1", timeout: 500 }), end = (v) => { s.destroy(); ok(v); };
  s.on("connect", () => end(true)).on("error", () => end(false)).on("timeout", () => end(false));
});

export class Board {
  constructor({ port, timeout = 500 } = {}) {
    this.port = Number(port || process.env.TEST_BOARD_PORT || configPort());
    this.url = `http://127.0.0.1:${this.port}`; this.timeout = timeout;
    this.enabled = process.env.TEST_BOARD !== "0"; this.stopRequested = false;
  }
  async health() { try { return await (await fetch(`${this.url}/api/health`, { signal: AbortSignal.timeout(1000) })).json(); } catch { return null; } }
  async ensure({ open = process.env.TEST_BOARD_OPEN !== "0" } = {}) {
    if (!this.enabled) return false;
    if ((await this.health())?.app !== "test-progress-board") {
      if (await listening(this.port)) throw new Error(`포트 ${this.port} 을(를) 다른 프로그램이 쓰고 있습니다. TEST_BOARD_PORT 로 바꾸세요.`);
      spawn(process.execPath, [path.join(ROOT, "server.mjs"), "--port", String(this.port)], { cwd: ROOT, detached: true, stdio: "ignore", windowsHide: true }).unref();
      const end = Date.now() + 10000;
      while ((await this.health())?.app !== "test-progress-board") {
        if (Date.now() > end) throw new Error("진행판 서버가 켜지지 않습니다.");
        await new Promise((r) => setTimeout(r, 150));
      }
    }
    if (open) {
      const [cmd, args] = process.platform === "win32" ? ["rundll32", ["url.dll,FileProtocolHandler", this.url]] : process.platform === "darwin" ? ["open", [this.url]] : ["xdg-open", [this.url]];
      spawn(cmd, args, { detached: true, stdio: "ignore" }).on("error", () => {}).unref();
    }
    return true;
  }
  async send(type, body = {}) {
    if (!this.enabled) return false;
    try {
      const r = await fetch(`${this.url}/api/event`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ type, ...body }), signal: AbortSignal.timeout(this.timeout) });
      const d = await r.json();
      if (!r.ok) { console.error(`[진행판] 보내지 못함: ${d.error}`); return false; }
      this.stopRequested = !!d.stop; return true;
    } catch { this.enabled = false; return false; }
  }
  suite(title, groups) { return this.send("suite", { title, groups }); }
  plan(group, items, label) { return this.send("plan", { group, items, label }); }
  start(group, name, extra) { return this.send("start", { group, name, ...extra }); }
  end(group, name, status, sec, detail, extra) { return this.send("end", { group, name, status, sec, detail, ...extra }); }
  done(group) { return this.send("done", { group }); }
  finish() { return this.send("finish"); }
  async item(group, name, fn) {
    await this.start(group, name); const t = performance.now(), sec = () => (performance.now() - t) / 1000;
    try { const v = await fn(); await this.end(group, name, "pass", sec()); return v; }
    catch (e) { await this.end(group, name, "fail", sec(), String(e?.message ?? e)); throw e; }
  }
}
