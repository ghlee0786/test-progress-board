import { memo, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";

const KO = {
  wait: "대기", run: "진행 중", pass: "완료", fail: "실패", skip: "건너뜀", stop: "중단",
  title: "테스트 진행판", idle: "아직 시작한 테스트가 없습니다.", connecting: "서버에 연결하는 중입니다.", off: "연결 끊김 · 다시 연결하는 중",
  elapsed: (t) => `경과 ${t}`, left: (t) => `남은 시간 약 ${t}`, ended: (t) => `끝남 · 걸린 시간 ${t}`,
  stopBtn: "멈추기", stopping: "하던 항목까지만 하고 멈춥니다", preparing: "다음 항목을 준비하는 중입니다.", none: "진행 중인 항목이 없습니다.",
  items: "항목", all: "전체", usual: (s) => `보통 ${s}`, about: (s) => `약 ${s}`, more: (n) => `외 ${n}개`, sec: (s) => `${s}초`, min: (m, s) => `${m}분 ${s}초`,
  empty: "이 조건에 맞는 항목이 없습니다.",
};
const EN = {
  wait: "Waiting", run: "Running", pass: "Passed", fail: "Failed", skip: "Skipped", stop: "Stopped",
  title: "Test progress", idle: "No test run has started yet.", connecting: "Connecting to the server.", off: "Disconnected · reconnecting",
  elapsed: (t) => `Elapsed ${t}`, left: (t) => `about ${t} left`, ended: (t) => `Finished in ${t}`,
  stopBtn: "Stop", stopping: "Stopping after the current item", preparing: "Preparing the next item.", none: "Nothing is running.",
  items: "items", all: "All", usual: (s) => `usually ${s}`, about: (s) => `~${s}`, more: (n) => `+${n} more`, sec: (s) => `${s}s`, min: (m, s) => `${m}m ${s}s`,
  empty: "No items match this filter.",
};
const lang = new URLSearchParams(location.search).get("lang") || (navigator.language || "ko").slice(0, 2);
const T = lang === "ko" ? KO : EN;
document.documentElement.lang = lang === "ko" ? "ko" : "en";
const STATUSES = ["pass", "fail", "run", "wait", "skip", "stop"];

const clock = (ms) => { const s = Math.max(0, Math.round(ms / 1000)); return s >= 60 ? T.min(Math.floor(s / 60), String(s % 60).padStart(2, "0")) : T.sec(s); };
const short = (s) => T.sec(s < 10 ? s.toFixed(1) : s.toFixed(0));

const PATHS = { pass: "M3.5 8.5l3 3 6-7", fail: "M4.5 4.5l7 7m0-7l-7 7", skip: "M4 8h8", stop: "M4 8h8" };
const Mark = ({ status }) => (
  <span className={`mark ${status}`} role="img" aria-label={T[status]}>{PATHS[status] && <svg viewBox="0 0 16 16" aria-hidden="true"><path d={PATHS[status]} /></svg>}</span>
);

const Item = memo(function Item({ it, now }) {
  const running = it.status === "run", spent = running && it.startedAt ? Math.max(0, (now - it.startedAt) / 1000) : 0;
  const time = running ? `${short(spent)}${it.est ? ` / ${T.usual(short(it.est))}` : ""}`
    : it.status === "wait" ? (it.est ? T.about(short(it.est)) : T.wait)
    : it.status === "pass" || it.status === "fail" ? short(it.sec ?? 0) : T[it.status];
  return (
    <li className={`item ${it.status}`}>
      <Mark status={it.status} />
      <div className="body">
        <div className="row"><span className="name">{it.name}</span><span className="time">{time}</span></div>
        {running && it.est > 0 && <div className="bar"><i style={{ width: `${Math.min(100, (spent / it.est) * 100)}%` }} /></div>}
        {it.detail && !running && <p className="detail">{it.detail}</p>}
      </div>
    </li>
  );
}, (a, b) => a.it === b.it && a.it.status !== "run" && b.it.status !== "run");

function Group({ g, now, filter }) {
  const items = filter === "all" ? g.items : g.items.filter((i) => i.status === filter);
  if (filter !== "all" && !items.length) return null;
  const pass = g.items.filter((i) => i.status === "pass").length;
  return (
    <section className={`group ${g.status}`}>
      <header>
        <h2 title={g.label}>{g.label}</h2>
        <span className={`chip ${g.status}`}>{T[g.status]}</span>
        <span className="count">{pass}/{g.items.length}{g.startedAt ? ` · ${clock((g.endedAt || now) - g.startedAt)}` : ""}</span>
      </header>
      <ol>{items.map((it) => <Item key={it.id} it={it} now={now} />)}</ol>
    </section>
  );
}

function App() {
  const [st, setSt] = useState(null), [live, setLive] = useState(false), [skew, setSkew] = useState(0), [tick, setTick] = useState(Date.now()), [filter, setFilter] = useState("all");
  useEffect(() => {
    const es = new EventSource("/api/stream");
    es.onopen = () => setLive(true); es.onerror = () => setLive(false);
    es.onmessage = (m) => { const d = JSON.parse(m.data); setSkew(d.now - Date.now()); setSt(d); };
    const t = setInterval(() => setTick(Date.now()), 500);
    return () => { es.close(); clearInterval(t); };
  }, []);
  const now = tick + skew;
  const all = useMemo(() => (st ? st.groups.flatMap((g) => g.items.map((it) => ({ it, g }))) : []), [st]);
  const n = useMemo(() => Object.fromEntries(STATUSES.map((s) => [s, all.filter((x) => x.it.status === s).length])), [all]);
  useEffect(() => { if (st) document.title = st.startedAt && !st.endedAt ? `${all.length - n.wait - n.run}/${all.length} · ${st.title}` : st.title || T.title; }, [st, all, n]);
  if (!st) return <main className="empty"><p>{T.connecting}</p></main>;

  const finished = all.length - n.wait - n.run, running = all.filter((x) => x.it.status === "run"), on = st.startedAt && !st.endedAt;
  const known = all.some((x) => x.it.est != null);
  const left = all.reduce((s, { it }) => s + (it.status === "wait" ? it.est ?? 0 : it.status === "run" ? Math.max(0, (it.est ?? 0) - (now - (it.startedAt || now)) / 1000) : 0), 0);
  const stop = () => fetch("/api/event", { method: "POST", headers: { "Content-Type": "application/json" }, body: '{"type":"stop"}' });
  const pct = (k) => `${(k / (all.length || 1)) * 100}%`;
  const shown = st.groups.some((g) => filter === "all" || g.items.some((i) => i.status === filter));

  return (
    <main>
      <div className="top">
        <div>
          <h1>{st.title || T.title}</h1>
          <p className="sub">
            {!live ? <b className="off">{T.off}</b>
              : !st.startedAt ? T.idle
              : on ? `${T.elapsed(clock(now - st.startedAt))}${known && left > 0.5 ? ` · ${T.left(clock(left * 1000))}` : ""}`
              : T.ended(clock(st.endedAt - st.startedAt))}
          </p>
        </div>
        {on && <button className="stop" onClick={stop} disabled={st.stop}>{st.stop ? T.stopping : T.stopBtn}</button>}
      </div>

      <div className="progress" role="progressbar" aria-label={T.title} aria-valuemin="0" aria-valuemax={all.length} aria-valuenow={finished}>
        <i className="p" style={{ width: pct(n.pass) }} /><i className="f" style={{ width: pct(n.fail) }} /><i className="k" style={{ width: pct(n.skip + n.stop) }} />
      </div>

      <div className="filters">
        {[["all", T.all, all.length], ...STATUSES.map((s) => [s, T[s], n[s]])].filter(([k, , v]) => k === "all" || v > 0 || k === filter).map(([k, label, v]) => (
          <button key={k} className={`f-${k}`} aria-pressed={filter === k} onClick={() => setFilter(k)}>{label} <b>{v}</b></button>
        ))}
      </div>

      <div className={`nowline ${running.length ? "on" : ""}`} aria-live="polite">
        {running.length ? <><span className="spin" /><span>{running.slice(0, 2).map(({ it, g }, k) => <span key={k} className="cur"><b>{g.label}</b> {it.name}</span>)}{running.length > 2 && <span className="cur">{T.more(running.length - 2)}</span>}</span></> : on ? T.preparing : T.none}
      </div>

      <div className="groups">{st.groups.map((g) => <Group key={g.id} g={g} now={now} filter={filter} />)}</div>
      {!shown && all.length > 0 && <p className="sub">{T.empty}</p>}
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
