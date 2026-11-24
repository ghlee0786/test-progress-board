"""진행판 서버 · 어댑터 · 적용 스크립트 시험 (python -m pytest). Node 18+ 필요. dotnet 시험은 SDK 가 있을 때만."""
import http.client, json, os, shutil, socket, subprocess, sys, time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "test-progress-board"
BOARD = SKILL / "assets" / "board"
sys.path.insert(0, str(BOARD / "adapters"))
sys.dont_write_bytecode = True
from board import Board, BoardError  # noqa: E402

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node 없음")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


class Server:
    def __init__(self, data, port=None):
        self.port, self.data = port or free_port(), data
        self.p = subprocess.Popen(["node", str(BOARD / "server.mjs"), "--port", str(self.port), "--data", str(data)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        end = time.time() + 15
        while time.time() < end:
            try: self.req("GET", "/api/health"); return
            except OSError: time.sleep(0.05)
        raise RuntimeError("서버가 안 켜짐")

    def req(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request(method, path, body=json.dumps(body).encode() if isinstance(body, (dict, list)) else body, headers=headers or {})
        r = c.getresponse(); data = r.read(); c.close()
        return r.status, data

    def ev(self, **e):
        code, data = self.req("POST", "/api/event", e); return code, json.loads(data)

    def state(self): return json.loads(self.req("GET", "/api/state")[1])
    def items(self): return {(g["id"], i["name"]): i for g in self.state()["groups"] for i in g["items"]}
    def close(self): self.p.kill(); self.p.wait()


@pytest.fixture
def srv(tmp_path):
    s = Server(tmp_path / "data"); yield s; s.close()


@pytest.fixture
def env(srv):
    return {**os.environ, "TEST_BOARD_PORT": str(srv.port), "TEST_BOARD_OPEN": "0", "TEST_BOARD": "1", "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}


def run(cmd, env, cwd, timeout=240):
    r = subprocess.run(cmd, env=env, cwd=cwd, capture_output=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr).decode("utf-8", "replace")


# ── 서버 ──────────────────────────────────────────────────
def test_lifecycle(srv):
    srv.ev(type="suite", title="점검", groups=[{"id": "a", "label": "가", "items": ["하나", "둘", "셋"]}, {"id": "b", "items": ["넷"]}])
    assert [i["status"] for i in srv.items().values()] == ["wait"] * 4
    srv.ev(type="start", group="a", name="하나"); s = srv.state()
    assert s["groups"][0]["status"] == "run" and srv.items()[("a", "하나")]["startedAt"]
    srv.ev(type="end", group="a", name="하나", status="pass", sec=1.5)
    srv.ev(type="end", group="a", name="둘", status="fail", sec=2, detail="이유")
    srv.ev(type="done", group="a"); s = srv.state()
    assert s["groups"][0]["status"] == "fail" and srv.items()[("a", "셋")]["status"] == "stop"
    srv.ev(type="finish"); s = srv.state()
    assert s["endedAt"] and s["groups"][1]["status"] == "stop"


def test_unknown_items_are_added(srv):
    assert srv.ev(type="start", group="new", name="나중에 알게 된 것")[0] == 200
    assert srv.items()[("new", "나중에 알게 된 것")]["status"] == "run"


def test_same_name_different_id(srv):
    srv.ev(type="plan", group="g", items=[{"id": "1", "name": "같은 이름"}, {"id": "2", "name": "같은 이름"}])
    srv.ev(type="end", group="g", id="2", name="같은 이름", status="fail")
    assert [i["status"] for i in srv.state()["groups"][0]["items"]] == ["wait", "fail"]


def test_stop_flag_and_reset_by_new_suite(srv):
    srv.ev(type="suite", title="t", groups=[{"id": "a", "items": ["x"]}])
    assert srv.ev(type="stop")[1]["stop"] is True
    assert srv.ev(type="start", group="a", name="x")[1]["stop"] is True
    assert srv.ev(type="suite", title="t2", groups=[])[1]["stop"] is False


def test_stop_without_run_is_ignored(srv):
    assert srv.ev(type="stop")[1]["stop"] is False


@pytest.mark.parametrize("bad", [{"type": "nope"}, {"type": "constructor"}, {"type": "__proto__"}, {"type": "end", "group": "a", "name": "x", "status": "maybe"}, {"type": "start", "group": "", "name": "x"}, {"type": "start", "group": "a"}, [], "글자"])
def test_bad_events(srv, bad):
    code, data = srv.req("POST", "/api/event", json.dumps(bad).encode())
    assert code == 400 and "error" in json.loads(data)
    assert srv.req("GET", "/api/health")[0] == 200


def test_broken_json_and_large_body(srv):
    assert srv.req("POST", "/api/event", b"{")[0] == 400
    try: code = srv.req("POST", "/api/event", b"x" * (3 * 1024 * 1024))[0]
    except (OSError, http.client.HTTPException): code = 413        # 다 보내기 전에 끊긴 것
    assert code == 413 and srv.req("GET", "/api/health")[0] == 200


def test_other_origin_and_host_are_refused(srv):
    ok = json.dumps({"type": "reset"}).encode()
    assert srv.req("POST", "/api/event", ok, {"Origin": "http://evil.example"})[0] == 403
    assert srv.req("POST", "/api/event", ok, {"Origin": "null"})[0] == 403
    assert srv.req("GET", "/api/state", headers={"Host": f"evil.example:{srv.port}"})[0] == 403
    assert srv.req("POST", "/api/event", ok, {"Origin": f"http://127.0.0.1:{srv.port}"})[0] == 200


def test_listens_on_loopback_only(srv):
    try: addrs = {a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)} - {"127.0.0.1"}
    except OSError: addrs = set()
    for a in addrs:
        with socket.socket() as s:
            s.settimeout(1); assert s.connect_ex((a, srv.port)) != 0


def test_pages_and_paths(srv):
    code, html = srv.req("GET", "/"); assert code == 200 and b'id="root"' in html
    code, js = srv.req("GET", "/app.js"); assert code == 200 and len(js) > 50000
    for p in ("/server.mjs", "/../server.mjs", "/.data/state.json", "/api/nope"): assert srv.req("GET", p)[0] == 404
    assert srv.req("PUT", "/api/event")[0] == 405


def test_state_and_estimates_survive_restart(tmp_path):
    s = Server(tmp_path / "d")
    for v in (2, 4, 9):
        s.ev(type="suite", title="t", groups=[{"id": "a", "items": ["x"]}]); s.ev(type="end", group="a", name="x", status="pass", sec=v)
    s.ev(type="end", group="a", name="x", status="fail", sec=100); time.sleep(0.6); s.close()      # 실패 시간은 예상에 넣지 않는다
    s = Server(tmp_path / "d")
    try:
        assert s.items()[("a", "x")]["status"] == "fail"
        s.ev(type="suite", title="t", groups=[{"id": "a", "items": ["x"]}]); assert s.items()[("a", "x")]["est"] == 4
    finally: s.close()


def test_stream_sends_updates(srv):
    c = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5); c.request("GET", "/api/stream"); r = c.getresponse()
    r.readline(); r.readline()
    srv.ev(type="suite", title="흐름", groups=[{"id": "a", "items": ["x"]}])
    assert json.loads(r.readline()[6:])["title"] == "흐름"; c.close()


# ── 파이썬 클라이언트 ─────────────────────────────────────────
def test_client_never_breaks_tests():
    b = Board(port=free_port()); assert b.start("a", "x") is False and b.enabled is False
    with b.item("a", "x"): pass
    with pytest.raises(ZeroDivisionError), b.item("a", "y"): 1 / 0


def test_client_refuses_foreign_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); s.listen()
        with pytest.raises(BoardError): Board(port=s.getsockname()[1]).ensure(open_browser=False)


def test_client_item(srv):
    b = Board(port=srv.port); b.suite("t", [{"id": "a", "items": ["ok", "ng"]}])
    with b.item("a", "ok"): assert srv.items()[("a", "ok")]["status"] == "run"
    with pytest.raises(ValueError), b.item("a", "ng"): raise ValueError("왜냐하면")
    i = srv.items(); assert i[("a", "ok")]["status"] == "pass" and "왜냐하면" in i[("a", "ng")]["detail"]


# ── 어댑터 ────────────────────────────────────────────────
def test_pytest_adapter(srv, env, tmp_path):
    d = tmp_path / "p"; d.mkdir()
    (d / "test_a.py").write_text("import pytest\ndef test_ok(): pass\ndef test_ng(): assert 1 == 2, 'nope'\n@pytest.mark.skip(reason='later')\ndef test_sk(): pass\n@pytest.mark.xfail\ndef test_xf(): assert 0\n@pytest.fixture\ndef f():\n    yield\n    raise RuntimeError('teardown')\ndef test_td(f): pass\n@pytest.mark.parametrize('n',[1,2])\ndef test_pa(n): pass\n", encoding="utf-8")
    rc, out = run([sys.executable, str(BOARD / "adapters/run_pytest.py"), "-q", "-p", "no:cacheprovider"], env, d)
    i = srv.items(); st = {k[1]: v["status"] for k, v in i.items()}
    assert rc == 1, out
    assert st == {"test_ok": "pass", "test_ng": "fail", "test_sk": "skip", "test_xf": "skip", "test_td": "fail", "test_pa[1]": "pass", "test_pa[2]": "pass"}
    assert "nope" in i[("test_a.py", "test_ng")]["detail"] and i[("test_a.py", "test_sk")]["detail"].endswith("later") and "teardown" in i[("test_a.py", "test_td")]["detail"]
    assert srv.state()["endedAt"]


def test_pytest_adapter_stop(srv, env, tmp_path):
    d = tmp_path / "p"; d.mkdir()
    (d / "test_s.py").write_text("import json,os,urllib.request\ndef test_1():\n    urllib.request.urlopen(urllib.request.Request(f\"http://127.0.0.1:{os.environ['TEST_BOARD_PORT']}/api/event\", b'{\"type\":\"stop\"}'))\ndef test_2(): pass\ndef test_3(): pass\n", encoding="utf-8")
    run([sys.executable, str(BOARD / "adapters/run_pytest.py"), "-q", "-p", "no:cacheprovider"], env, d)
    st = {k[1]: v["status"] for k, v in srv.items().items()}
    assert st["test_1"] == "pass" and st["test_3"] == "stop"


def test_pytest_runs_without_board(env, tmp_path):
    (tmp_path / "test_x.py").write_text("def test_x(): pass\n")
    assert run([sys.executable, str(BOARD / "adapters/run_pytest.py"), "-q", "-p", "no:cacheprovider"], {**env, "TEST_BOARD": "0"}, tmp_path)[0] == 0


def write_plan(d, groups):
    p = d / "c.json"; p.write_text(json.dumps({"title": "목록", "groups": groups}), encoding="utf-8"); return str(p)


PY = sys.executable
def test_commands_adapter(srv, env, tmp_path):
    f = write_plan(tmp_path, [{"id": "g", "items": [
        {"name": "ok", "run": [PY, "-c", "print('마지막 줄')"]}, {"name": "ng", "run": [PY, "-c", "import sys;sys.exit(4)"]},
        {"name": "needs ok", "run": [PY, "-c", "0"], "needs": ["ok"]}, {"name": "needs ng", "run": [PY, "-c", "0"], "needs": ["ng"]},
        {"name": "slow", "run": [PY, "-c", "import time;time.sleep(60)"], "timeout": 1}, {"name": "shell", "run": "echo hi"}, {"name": "none", "run": ["no-such-program-xyz"]}]},
        {"id": "other", "items": [{"name": "x", "run": [PY, "-c", "0"]}]}])
    t = time.time(); rc, out = run([PY, str(BOARD / "adapters/run_commands.py"), f, "--only", "g"], env, tmp_path)
    i = srv.items(); st = {k[1]: v["status"] for k, v in i.items()}
    assert rc == 1 and time.time() - t < 30
    assert st == {"ok": "pass", "ng": "fail", "needs ok": "pass", "needs ng": "skip", "slow": "fail", "shell": "pass", "none": "fail"}, out
    assert "종료 코드 4" in i[("g", "ng")]["detail"]


def test_commands_timeout_kills_children(srv, env, tmp_path):
    """셸이 띄운 자식까지 끝나야 한다 (남으면 출력 파이프가 안 닫혀 멈춘다)."""
    f = write_plan(tmp_path, [{"id": "g", "items": [{"name": "tree", "run": f'"{PY}" -c "import subprocess,sys;subprocess.run([sys.executable,\'-c\',\'import time;time.sleep(60)\'])"', "timeout": 2}]}])
    t = time.time(); run([PY, str(BOARD / "adapters/run_commands.py"), f], env, tmp_path, timeout=50); assert time.time() - t < 25


@pytest.mark.parametrize("groups", [[], [{"id": "g", "items": [{"name": "a"}]}], [{"id": "g", "items": [{"name": "a", "run": "x"}, {"name": "a", "run": "x"}]}], [{"id": "g", "items": [{"name": "a", "run": "x", "needs": ["z"]}]}]])
def test_commands_bad_plan(env, tmp_path, groups):
    assert run([PY, str(BOARD / "adapters/run_commands.py"), write_plan(tmp_path, groups)], env, tmp_path)[0] == 2


def test_dotnet_parsing():
    import run_dotnet as d
    assert d.listing("x\nThe following Tests are available:\n    A.B.C\n    A.B.D(x: 1.5)\n") == ["A.B.C", "A.B.D(x: 1.5)"]
    assert d.split("A.B.C(x: 1.5)") == ("A.B", "C(x: 1.5)") and d.seconds("1 m 3 s") == 63 and d.seconds("< 1 ms") == 0.001
    m = d.RESULT.match("  Failed A.B.C(s: \"a [b]\") [12 ms]"); assert m.group(1, 2, 3) == ("Failed", 'A.B.C(s: "a [b]")', "12 ms")
    assert not d.RESULT.match("Passed!  - Failed: 0")


# ── 적용 스크립트 ─────────────────────────────────────────────
def apply(*a): return run([PY, str(SKILL / "scripts/apply.py"), *map(str, a)], {**os.environ, "PYTHONIOENCODING": "utf-8"}, ROOT)


def test_apply_detects_and_is_idempotent(tmp_path):
    (tmp_path / "tests").mkdir(); (tmp_path / "tests/test_a.py").write_text("")
    (tmp_path / "package.json").write_text('{"devDependencies":{"@playwright/test":"1"}}')
    (tmp_path / "T").mkdir(); (tmp_path / "T/T.csproj").write_text('<PackageReference Include="Microsoft.NET.Test.Sdk" />')
    rc, out = apply(tmp_path, "--port", 8912); d = tmp_path / "tools/test-board"
    assert rc == 0 and all(x in out for x in ("run_pytest.py", "run_playwright.mjs", "run_dotnet.py")), out
    assert json.loads((d / "board.config.json").read_text())["port"] == 8912 and (d / "server.mjs").exists()
    rc, out = apply(tmp_path); assert rc == 0 and "넣은 파일 0개" in out and "8912" in out


def test_apply_keeps_user_edits(tmp_path):
    apply(tmp_path); f = tmp_path / "tools/test-board/server.mjs"; f.write_text("// 내가 고침", encoding="utf-8")
    rc, out = apply(tmp_path); assert "그대로 둠" in out and "server.mjs" in out and f.read_text(encoding="utf-8") == "// 내가 고침"
    rc, out = apply(tmp_path); assert "그대로 둠" in out                  # 두 번째에도 지킨다
    apply(tmp_path, "--force"); assert f.read_bytes() == (BOARD / "server.mjs").read_bytes()


def test_apply_refuses_foreign_or_outside_folder(tmp_path):
    (tmp_path / "tools/test-board").mkdir(parents=True); (tmp_path / "tools/test-board/mine.txt").write_text("x")
    assert apply(tmp_path)[0] == 2 and apply(tmp_path, "--dest", "..")[0] == 2 and apply(tmp_path, "--dest", ".")[0] == 2 and apply(tmp_path / "none")[0] == 2


def test_apply_dry_run_writes_nothing(tmp_path):
    assert apply(tmp_path, "--dry-run")[0] == 0 and not (tmp_path / "tools").exists()


def test_applied_project_works_end_to_end(tmp_path):
    """넣은 그대로 서버가 켜지고 예시 목록이 통과한다 — 서버는 이 시험이 직접 끈다."""
    port = free_port(); apply(tmp_path, "--adapter", "commands", "--port", port)
    env = {**os.environ, "TEST_BOARD_OPEN": "0", "PYTHONIOENCODING": "utf-8"}; env.pop("TEST_BOARD_PORT", None); env.pop("TEST_BOARD", None)
    rc, out = run([PY, "tools/test-board/adapters/run_commands.py", "tools/test-board/checklist.json"], env, tmp_path)
    h = Board(port=port).health()
    try: assert rc == 0 and h["app"] == "test-progress-board", out
    finally:
        if h: subprocess.run(["taskkill", "/PID", str(h["pid"]), "/F"], capture_output=True) if os.name == "nt" else os.kill(h["pid"], 15)
        time.sleep(0.3)


def test_no_unexpected_files_in_skill():
    """공개 저장소에 실행 기록 · 설치물이 섞이지 않는다."""
    names = {p.name for p in SKILL.rglob("*")}
    assert not names & {"node_modules", ".data", "state.json", "history.json", "__pycache__", "package-lock.json"}
