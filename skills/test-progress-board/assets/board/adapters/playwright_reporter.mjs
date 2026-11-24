// Playwright 리포터 — 보통은 run_playwright.mjs 로 쓴다.
//   npx playwright test --reporter=list,<진행판 폴더>/adapters/playwright_reporter.mjs
// 파일(과 프로젝트) 하나가 그룹 하나. 재시도는 마지막 결과만 남긴다.
import path from "node:path";
import { Board } from "./board.mjs";

const STATUS = { passed: "pass", failed: "fail", timedOut: "fail", interrupted: "stop", skipped: "skip" };
const plain = (s) => String(s ?? "").replace(/\u001b\[[0-9;]*m/g, "");

export default class BoardReporter {
  constructor() { this.b = new Board(); this.q = Promise.resolve(); this.groups = new Set(); }
  push(fn) { this.q = this.q.then(fn, fn); }                    // 이벤트 순서를 지킨다
  where(test) {
    const project = test.parent.project()?.name ?? "", file = path.relative(this.root, test.location.file).replaceAll("\\", "/");
    const titles = test.titlePath().slice(3);                    // ['', 프로젝트, 파일, describe…, 이름]
    return { group: project ? `${project} · ${file}` : file, name: titles.join(" › ") || test.title, id: test.id };
  }
  onBegin(config, suite) {
    this.root = config.rootDir; const by = new Map();
    for (const t of suite.allTests()) { const w = this.where(t); if (!by.has(w.group)) by.set(w.group, []); by.get(w.group).push({ id: w.id, name: w.name }); }
    this.groups = new Set(by.keys());
    this.push(() => this.b.suite("Playwright", [...by].map(([id, items]) => ({ id, label: id, items }))));
  }
  onTestBegin(test) { const w = this.where(test); this.push(() => this.b.start(w.group, w.name, { id: w.id })); }
  onTestEnd(test, result) {
    const w = this.where(test), retrying = test.outcome() !== "skipped" && result.status !== test.expectedStatus && result.retry < test.retries && result.status !== "interrupted";
    if (retrying) return;
    const ok = result.status === test.expectedStatus, status = result.status === "skipped" ? "skip" : ok ? "pass" : STATUS[result.status] === "pass" ? "fail" : STATUS[result.status];
    const detail = status === "fail" ? plain(result.error?.message ?? (result.status === "passed" ? "실패해야 하는 테스트가 통과함" : result.status)) : result.retry && ok ? `재시도 ${result.retry}번째에 통과` : "";
    this.push(() => this.b.end(w.group, w.name, status, result.duration / 1000, detail, { id: w.id }));
  }
  async onEnd() { for (const g of this.groups) this.push(() => this.b.done(g)); this.push(() => this.b.finish()); await this.q; }
  printsToStdio() { return false; }
}
