"""명령 목록(JSON)을 진행판에 체크하며 차례로 돌린다. 어떤 언어 · 도구의 테스트에도 쓴다.

    python <진행판 폴더>/adapters/run_commands.py checklist.json [--only 그룹id]

checklist.json
    {"title": "배포 전 점검",
     "groups": [{"id": "api", "label": "API", "stop_on_fail": false,
                 "items": [{"name": "단위 테스트", "run": ["npm", "test"], "cwd": ".", "timeout": 300},
                           {"name": "통합 테스트", "run": "make e2e", "needs": ["단위 테스트"]}]}]}

run 이 목록이면 셸 없이, 문자열이면 셸로 실행한다. 종료 코드 0 = 완료. needs 의 항목이 통과하지 못했으면 '건너뜀'.
종료 코드: 0 모두 통과 · 1 실패 또는 건너뜀 있음 · 2 설정 오류 · 3 진행판에서 멈춤
"""
import argparse, json, os, shutil, signal, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from board import Board, BoardError


def check(plan):
    if not isinstance(plan, dict) or not plan.get("groups"):
        raise ValueError("groups 가 필요합니다")
    for g in plan["groups"]:
        names = [i["name"] for i in g["items"]]
        if len(names) != len(set(names)):
            raise ValueError(f"그룹 {g['id']}: 항목 이름이 겹칩니다")
        for k, i in enumerate(g["items"]):
            if not i.get("run"):
                raise ValueError(f"{g['id']}/{i['name']}: run 이 필요합니다")
            bad = [n for n in i.get("needs", []) if n not in names[:k]]
            if bad:
                raise ValueError(f"{g['id']}/{i['name']}: needs 는 같은 그룹의 앞 항목이어야 합니다: {bad}")


def kill(p):
    """셸이 띄운 자식까지 끝낸다."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
    else:
        try: os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError: pass


def run(item, base):
    cmd, shell = item["run"], isinstance(item["run"], str)
    if not shell:
        cmd = [str(c) for c in cmd]
        cmd[0] = shutil.which(cmd[0]) or cmd[0]
    kw = {} if os.name == "nt" else {"start_new_session": True}
    p = subprocess.Popen(cmd, shell=shell, cwd=str((base / item.get("cwd", ".")).resolve()), env={**os.environ, **{k: str(v) for k, v in item.get("env", {}).items()}},
                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kw)
    try:
        out, _ = p.communicate(timeout=item.get("timeout"))
    except subprocess.TimeoutExpired:
        kill(p); out, _ = p.communicate()
        return "fail", f"{item['timeout']}초 안에 끝나지 않음", out
    except BaseException:
        kill(p); raise
    lines = [l for l in out.decode("utf-8", "replace").splitlines() if l.strip()]
    last = lines[-1].strip()[:400] if lines else ""
    return ("pass", last, out) if p.returncode == 0 else ("fail", f"종료 코드 {p.returncode}" + (f" · {last}" if last else ""), out)


def main(argv):
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(); ap.add_argument("file"); ap.add_argument("--only", action="append", help="이 그룹만 (여러 번 줄 수 있음)")
    a = ap.parse_args(argv)
    try:
        path = Path(a.file).resolve(); plan = json.loads(path.read_text(encoding="utf-8-sig")); check(plan)
        groups = [g for g in plan["groups"] if not a.only or g["id"] in a.only]
        missing = set(a.only or []) - {g["id"] for g in groups}
        if missing: raise ValueError(f"없는 그룹: {sorted(missing)}")
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"설정 오류: {e}", file=sys.stderr); return 2
    b = Board()
    try:
        b.ensure()
    except BoardError as e:
        print(f"[진행판] {e} — 진행판 없이 돌립니다.", file=sys.stderr); b.enabled = False
    b.suite(plan.get("title", path.stem), [{"id": g["id"], "label": g.get("label", g["id"]), "items": [i["name"] for i in g["items"]]} for g in groups])
    bad = stopped = False
    try:
        for g in groups:
            ok = set()
            for k, i in enumerate(g["items"]):
                if b.stop_requested:
                    stopped = True; break
                miss = [n for n in i.get("needs", []) if n not in ok]
                if miss:
                    status, detail = "skip", f"먼저 통과해야 하는 항목: {', '.join(miss)}"; sec = 0.0; b.end(g["id"], i["name"], status, sec, detail)
                else:
                    b.start(g["id"], i["name"]); t = time.monotonic()
                    try: status, detail, out = run(i, path.parent)
                    except OSError as e: status, detail, out = "fail", f"실행할 수 없음: {e}", b""
                    sec = time.monotonic() - t; b.end(g["id"], i["name"], status, sec, detail)
                    if status == "fail": sys.stdout.write(out.decode("utf-8", "replace"))
                print(f"{status.upper():<5} {g['id']} / {i['name']}  {sec:.1f}s  {detail}", flush=True)
                if status == "pass": ok.add(i["name"])
                else: bad = True
                if status == "fail" and g.get("stop_on_fail"): break
            b.done(g["id"])
            if stopped or b.stop_requested and g is not groups[-1]:
                stopped = True; break
    finally:
        b.finish()
    return 3 if stopped else 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
