// 테스트 진행판 서버 — Node 18+ 만 있으면 된다 (설치할 패키지 없음). 127.0.0.1 에만 연다.
//   node server.mjs [--port 8790] [--data <폴더>]
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const opt = (name, fallback) => { const i = process.argv.indexOf(name); return i > 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback; };
const PORT = Number(opt("--port", process.env.TEST_BOARD_PORT || 8790));
const DATA = path.resolve(opt("--data", path.join(HERE, ".data")));
const APP = { app: "test-progress-board", version: "1.0.0" };
const MAX_BODY = 2 * 1024 * 1024, MAX_ITEMS = 10000, KEEP = 5;
const END = new Set(["pass", "fail", "skip", "stop"]);

fs.mkdirSync(DATA, { recursive: true });
const FILES = { state: path.join(DATA, "state.json"), history: path.join(DATA, "history.json") };
const load = (f, d) => { try { return JSON.parse(fs.readFileSync(f, "utf8")); } catch { return d; } };
const blank = (title = "") => ({ title, startedAt: title ? Date.now() : null, endedAt: null, stop: false, groups: [] });
let state = load(FILES.state, blank());
let history = load(FILES.history, {});            // {"그룹\u0000항목": [최근 통과 시간 …]}

// ── 값 다듬기 ───────────────────────────────────────────────
const text = (v, max, name) => { if (typeof v !== "string" || !v.trim()) throw new Error(`${name} 이(가) 필요합니다`); return v.slice(0, max); };
const note = (v) => (v == null ? "" : String(v).slice(0, 4000));
const secs = (v) => { const n = Number(v); return Number.isFinite(n) && n >= 0 ? Math.round(n * 100) / 100 : 0; };
const hkey = (g, i) => `${g.id}\u0000${i.id}`;
const estimate = (g, i) => { const a = history[hkey(g, i)]; if (!a?.length) return null; const s = [...a].sort((x, y) => x - y); return s[s.length >> 1]; };

function mkItem(g, raw) {
  const o = typeof raw === "string" ? { name: raw } : raw ?? {};
  const name = text(o.name, 300, "항목 이름"), it = { id: o.id ? text(o.id, 300, "항목 id") : name, name, status: "wait", startedAt: null };
  it.est = estimate(g, it); return it;
}
function mkGroup(raw) {
  const id = text(raw?.id, 200, "그룹 id"), g = { id, label: raw.label ? text(raw.label, 200, "그룹 이름") : id, status: "wait", startedAt: null, endedAt: null, items: [] };
  const seen = new Set();
  for (const r of raw.items ?? []) { const it = mkItem(g, r); if (!seen.has(it.id)) { seen.add(it.id); g.items.push(it); } }
  return g;
}
const total = () => state.groups.reduce((n, g) => n + g.items.length, 0);
const active = () => state.startedAt && !state.endedAt;
const findGroup = (id) => state.groups.find((g) => g.id === id);
function needGroup(e) {            // 미리 올리지 않은 그룹도 받는다 (테스트를 돌면서 알게 되는 경우)
  const id = text(e.group, 200, "group"); let g = findGroup(id);
  if (!active()) { state = blank(e.title ? text(e.title, 200, "title") : "테스트"); g = null; }
  if (!g) { g = mkGroup({ id, label: e.label }); state.groups.push(g); }
  return g;
}
function needItem(g, e) {
  const id = text(e.id ?? e.name, 300, "name"); let it = g.items.find((x) => x.id === id);
  if (!it) { if (total() >= MAX_ITEMS) throw new Error("항목이 너무 많습니다"); it = mkItem(g, { id, name: e.name ?? id }); g.items.push(it); }
  return it;
}
function settle(g) {               // 그룹 상태 = 항목 상태에서 계산
  const has = (s) => g.items.some((i) => i.status === s);
  if (has("run") || (has("wait") && g.startedAt && !g.endedAt)) g.status = "run";
  else if (has("fail")) g.status = "fail";
  else if (has("wait")) g.status = "wait";
  else g.status = has("stop") ? "stop" : has("pass") ? "pass" : g.items.length ? "skip" : "wait";
}
const closeOpen = (g) => { for (const i of g.items) if (i.status === "wait" || i.status === "run") { i.status = "stop"; i.startedAt = null; } };

// ── 이벤트 ─────────────────────────────────────────────────
const handlers = {
  suite(e) {                       // 전체 목록을 먼저 올린다 — 모두 '대기'
    const groups = (Array.isArray(e.groups) ? e.groups : []).map(mkGroup);
    if (groups.reduce((n, g) => n + g.items.length, 0) > MAX_ITEMS) throw new Error("항목이 너무 많습니다");
    state = blank(text(e.title ?? "테스트", 200, "title")); state.groups = groups;
  },
  plan(e) {                        // 한 그룹의 목록을 새로 올리고 시작
    const g = needGroup(e), n = mkGroup({ id: g.id, label: e.label ?? g.label, items: e.items });
    if (total() - g.items.length + n.items.length > MAX_ITEMS) throw new Error("항목이 너무 많습니다");
    Object.assign(g, n, { startedAt: Date.now() }); settle(g);
  },
  start(e) { const g = needGroup(e), it = needItem(g, e); g.startedAt ??= Date.now(); g.endedAt = null; Object.assign(it, { status: "run", startedAt: Date.now(), detail: "" }); settle(g); },
  end(e) {
    if (!END.has(e.status)) throw new Error("status 는 pass · fail · skip · stop 중 하나입니다");
    const g = needGroup(e), it = needItem(g, e);
    g.startedAt ??= Date.now();
    const sec = e.sec != null ? secs(e.sec) : it.startedAt ? secs((Date.now() - it.startedAt) / 1000) : 0;
    Object.assign(it, { status: e.status, sec, detail: note(e.detail), startedAt: null });
    if (e.status === "pass") { const k = hkey(g, it); history[k] = [...(history[k] ?? []), sec].slice(-KEEP); dirtyHistory = true; }
    settle(g);
  },
  done(e) { const g = findGroup(text(e.group, 200, "group")); if (!g) return; closeOpen(g); g.startedAt ??= Date.now(); g.endedAt = Date.now(); settle(g); },
  finish() { for (const g of state.groups) { closeOpen(g); if (g.startedAt && !g.endedAt) g.endedAt = Date.now(); settle(g); } if (state.startedAt) state.endedAt = Date.now(); },
  stop() { if (active()) state.stop = true; },
  reset() { state = blank(); },
};

// ── 화면으로 흘리기 (0.2초에 한 번으로 모은다) ──────────────────
const clients = new Set(); let timer = null, dirtyHistory = false;
const frame = () => `data: ${JSON.stringify({ ...state, now: Date.now() })}\n\n`;
function changed() {
  timer ??= setTimeout(() => {
    timer = null; const msg = frame();
    for (const c of clients) c.write(msg);
    save();
  }, 200);
}
function save() {
  try {
    fs.writeFileSync(FILES.state, JSON.stringify(state));
    if (dirtyHistory) { dirtyHistory = false; fs.writeFileSync(FILES.history, JSON.stringify(history)); }
  } catch (err) { console.error("저장 실패:", err.message); }
}
for (const s of ["SIGINT", "SIGTERM"]) process.on(s, () => { save(); process.exit(0); });

// ── HTTP ───────────────────────────────────────────────────
const HOSTS = new Set([`127.0.0.1:${PORT}`, `localhost:${PORT}`]);
const STATIC = { "/": ["public/index.html", "text/html"], "/app.js": ["public/app.js", "text/javascript"] };
const send = (res, code, body, type = "application/json") => res.writeHead(code, {
  "Content-Type": `${type}; charset=utf-8`, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
  "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'",
}).end(body);

const server = http.createServer((req, res) => {
  // 다른 사이트가 이 서버를 부르지 못하게: Host(DNS 재바인딩)와 Origin 을 확인한다
  if (!HOSTS.has(req.headers.host ?? "")) return send(res, 403, '{"error":"host"}');
  const origin = req.headers.origin;
  if (origin && !HOSTS.has(origin.replace(/^http:\/\//, ""))) return send(res, 403, '{"error":"origin"}');
  const { pathname } = new URL(req.url, `http://127.0.0.1:${PORT}`);

  if (req.method === "POST" && pathname === "/api/event") {
    const chunks = []; let size = 0;
    req.on("data", (c) => { size += c.length; if (size > MAX_BODY) { send(res, 413, '{"error":"too large"}'); req.destroy(); } else chunks.push(c); });
    req.on("end", () => {
      if (res.writableEnded) return;
      try {
        const e = JSON.parse(Buffer.concat(chunks).toString("utf8"));
        if (!e || typeof e !== "object" || !Object.hasOwn(handlers, e.type)) throw new Error("모르는 이벤트입니다");
        handlers[e.type](e); changed();
        send(res, 200, JSON.stringify({ ok: true, stop: state.stop }));
      } catch (err) { send(res, 400, JSON.stringify({ error: String(err.message || err) })); }
    });
    return;
  }
  if (req.method !== "GET") return send(res, 405, '{"error":"method"}');
  if (pathname === "/api/health") return send(res, 200, JSON.stringify({ ...APP, pid: process.pid }));
  if (pathname === "/api/state") return send(res, 200, JSON.stringify({ ...state, now: Date.now() }));
  if (pathname === "/api/stream") {
    res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-store", Connection: "keep-alive" });
    res.write(frame()); clients.add(res); req.on("close", () => clients.delete(res)); return;
  }
  const file = STATIC[pathname];
  if (!file) return send(res, 404, '{"error":"not found"}');
  send(res, 200, fs.readFileSync(path.join(HERE, file[0])), file[1]);
});
server.on("error", (err) => { console.error(err.code === "EADDRINUSE" ? `포트 ${PORT} 을(를) 이미 쓰고 있습니다` : err.message); process.exit(1); });
server.listen(PORT, "127.0.0.1", () => console.log(`테스트 진행판 http://127.0.0.1:${PORT}`));
