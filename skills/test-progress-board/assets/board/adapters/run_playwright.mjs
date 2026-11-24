// Playwright 를 진행판에 체크하며 돌린다. 뒤의 인자는 그대로 playwright test 로 넘어간다.
//   node <진행판 폴더>/adapters/run_playwright.mjs --project=chromium
// 진행판의 '멈추기' 는 실행 중인 테스트를 바로 끊는다 (남은 항목은 '중단').
import path from "node:path";
import { createRequire } from "node:module";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { Board } from "./board.mjs";

const here = path.dirname(fileURLToPath(import.meta.url)), b = new Board();
let cli;
try { cli = createRequire(path.join(process.cwd(), "package.json")).resolve("@playwright/test/cli"); }
catch { console.error("이 폴더에서 @playwright/test 를 찾을 수 없습니다 (npm i -D @playwright/test)."); process.exit(2); }
try { await b.ensure(); } catch (e) { console.error(`[진행판] ${e.message} — 진행판 없이 돌립니다.`); b.enabled = false; }

const child = spawn(process.execPath, [cli, "test", `--reporter=list,${path.join(here, "playwright_reporter.mjs")}`, ...process.argv.slice(2)],
  { stdio: "inherit", env: { ...process.env, TEST_BOARD: b.enabled ? "1" : "0", TEST_BOARD_PORT: String(b.port) } });
let stopped = false;
const watch = b.enabled && setInterval(async () => {
  try {
    const s = await (await fetch(`${b.url}/api/state`, { signal: AbortSignal.timeout(500) })).json();
    if (s.stop && !s.endedAt && !stopped) { stopped = true; process.platform === "win32" ? spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore" }) : child.kill("SIGTERM"); }
  } catch {}
}, 500);
child.on("exit", async (code) => { if (watch) clearInterval(watch); if (stopped) await b.finish(); process.exitCode = stopped ? 3 : code ?? 1; });
