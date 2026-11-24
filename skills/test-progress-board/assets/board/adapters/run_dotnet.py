"""dotnet test 를 진행판에 체크하며 돌린다. 뒤의 인자는 그대로 dotnet test 로 넘어간다.

    python <진행판 폴더>/adapters/run_dotnet.py MyApp.Tests.csproj --filter Category=Smoke

dotnet 은 테스트의 '시작' 을 알려 주지 않으므로 항목은 대기 → 완료 · 실패로 바로 바뀌고, '진행 중' 은 클래스(그룹) 단위로만 보인다.
VSTest 콘솔 출력(기본값)을 읽는다. Microsoft.Testing.Platform 으로 바꾼 프로젝트는 지원하지 않는다.
종료 코드: dotnet test 의 것 · 3 진행판에서 멈춤
"""
import os, re, shutil, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from board import Board, BoardError

RESULT = re.compile(r"^\s{2}(Passed|Failed|Skipped)\s+(.+?)(?:\s+\[([^\]]+)\])?\s*$")
UNITS = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
STATUS = {"Passed": "pass", "Failed": "fail", "Skipped": "skip"}


def seconds(s):
    """'12 ms' · '1 s' · '1 m 3 s' · '< 1 ms' → 초"""
    return sum(float(n) * UNITS[u] for n, u in re.findall(r"([\d.]+)\s*(ms|s|m|h)\b", s or ""))


def split(name):
    """Namespace.Class.Method(args) → (Namespace.Class, Method(args))"""
    head, par, args = name.partition("(")
    cls, _, method = head.rpartition(".")
    return (cls or "tests"), method + par + args


def listing(text):
    """--list-tests 출력에서 테스트 이름"""
    out, on = [], False
    for l in text.splitlines():
        if l.startswith("The following Tests are available"): on = True; continue
        if on:
            if l.startswith("    ") and l.strip(): out.append(l.strip())
            elif l.strip(): on = False
    return out


def main(argv):
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="replace")
    dotnet = shutil.which("dotnet")
    if not dotnet:
        print("dotnet 을 찾을 수 없습니다.", file=sys.stderr); return 2
    env = {**os.environ, "DOTNET_CLI_UI_LANGUAGE": "en", "VSLANG": "1033", "DOTNET_NOLOGO": "1"}     # 출력 문구를 영어로 고정해 읽는다
    b = Board()
    try:
        b.ensure()
    except BoardError as e:
        print(f"[진행판] {e} — 진행판 없이 돌립니다.", file=sys.stderr); b.enabled = False
    r = subprocess.run([dotnet, "test", *argv, "--list-tests"], capture_output=True, env=env)
    names = listing(r.stdout.decode("utf-8", "replace"))
    if r.returncode or not names:
        sys.stdout.write(r.stdout.decode("utf-8", "replace")); sys.stderr.write(r.stderr.decode("utf-8", "replace"))
        print("테스트 목록을 얻지 못했습니다.", file=sys.stderr); return r.returncode or 2
    by = {}
    for n in names: by.setdefault(split(n)[0], []).append(n)
    left = {g: len(v) for g, v in by.items()}
    b.suite("dotnet test", [{"id": g, "label": g.rsplit(".", 1)[-1], "items": [{"id": n, "name": split(n)[1]} for n in v]} for g, v in by.items()])
    p = subprocess.Popen([dotnet, "test", *argv, "--no-build", "--logger", "console;verbosity=normal"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stopped, last, last_id, msg, closing = False, None, None, [], None

    def flush():
        """실패 항목은 뒤따르는 오류 글을 모아 붙인다."""
        nonlocal last, msg, closing
        if last: b.end(*last, detail=" ".join(x for x in msg if x)[:1500], id=last_id, label=last[0].rsplit(".", 1)[-1])
        if closing: b.done(closing)
        last, msg, closing = None, [], None
    for raw in p.stdout:
        line = raw.decode("utf-8", "replace").rstrip("\r\n"); print(line, flush=True)
        m = RESULT.match(line)
        if m:
            flush(); g, n = split(m.group(2)); last, last_id = (g, n, STATUS[m.group(1)], seconds(m.group(3))), m.group(2)
            if g in left:
                left[g] -= 1
                if left[g] == 0: closing = g              # 실패 글을 다 모은 뒤에 그룹을 닫는다
            if last[2] != "fail": flush()
        elif last and not line.startswith("  Stack Trace:") and len(msg) < 12 and line.strip() not in ("Error Message:", "") and not line.strip().startswith("at "):
            msg.append(line.strip())
        if b.stop_requested and not stopped:
            stopped = True
            if os.name == "nt": subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
            else: p.terminate()
    flush(); rc = p.wait(); b.finish()
    return 3 if stopped else rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
