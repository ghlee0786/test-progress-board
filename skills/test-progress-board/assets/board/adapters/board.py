"""진행판에 보내는 파이썬 클라이언트 (표준 라이브러리만 사용).

    from board import Board
    b = Board(); b.ensure()                       # 서버가 꺼져 있으면 켜고 브라우저를 연다
    b.suite("배포 전 점검", [{"id": "api", "label": "API", "items": ["로그인", "조회"]}])
    with b.item("api", "로그인"):                  # 들어갈 때 '진행 중', 나올 때 '완료' · 예외면 '실패'
        ...
    b.done("api"); b.finish()

진행판이 없거나 느려도 테스트를 막지 않는다 — 한 번 실패하면 그 뒤로는 보내지 않는다.
"""
import contextlib, json, os, shutil, socket, subprocess, sys, time, urllib.error, urllib.request, webbrowser
from pathlib import Path

DEFAULT_PORT = 8790
HERE = Path(__file__).resolve().parent


class BoardError(RuntimeError):
    pass


def _config_port():
    try:
        return int(json.loads((HERE.parent / "board.config.json").read_text(encoding="utf-8"))["port"])
    except (OSError, ValueError, KeyError):
        return DEFAULT_PORT


class Board:
    def __init__(self, port=None, timeout=0.5):
        self.port = int(port or os.environ.get("TEST_BOARD_PORT") or _config_port())
        self.url, self.timeout = f"http://127.0.0.1:{self.port}", timeout
        self.enabled, self.stop_requested = os.environ.get("TEST_BOARD", "1") != "0", False

    # ── 서버 ──
    def health(self):
        try:
            with urllib.request.urlopen(f"{self.url}/api/health", timeout=1) as r:
                return json.load(r)
        except (OSError, ValueError):
            return None

    def ensure(self, open_browser=True):
        """진행판을 쓸 수 있게 한다. 꺼져 있으면 켠다. 그 포트를 다른 프로그램이 쓰면 BoardError."""
        if not self.enabled:
            return False
        h = self.health()
        if not (h and h.get("app") == "test-progress-board"):
            with socket.socket() as s:
                s.settimeout(0.5)
                if s.connect_ex(("127.0.0.1", self.port)) == 0:
                    raise BoardError(f"포트 {self.port} 을(를) 다른 프로그램이 쓰고 있습니다. TEST_BOARD_PORT 로 바꾸세요.")
            node = shutil.which("node")
            if not node:
                raise BoardError("node 를 찾을 수 없습니다 (Node.js 18 이상 필요).")
            kw = {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
            subprocess.Popen([node, str(HERE.parent / "server.mjs"), "--port", str(self.port)], cwd=str(HERE.parent),
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
            end = time.time() + 10
            while not self.health():
                if time.time() > end:
                    raise BoardError("진행판 서버가 켜지지 않습니다.")
                time.sleep(0.15)
        if open_browser and os.environ.get("TEST_BOARD_OPEN", "1") != "0":
            webbrowser.open(self.url)
        return True

    # ── 이벤트 ──
    def send(self, kind, **kw):
        """보내고 '멈추기' 요청 여부를 갱신한다. 잘못된 이벤트(400)는 알리고, 연결 문제는 조용히 끈다."""
        if not self.enabled:
            return False
        body = json.dumps({"type": kind, **kw}, ensure_ascii=False).encode("utf-8")
        try:
            req = urllib.request.Request(f"{self.url}/api/event", body, {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                self.stop_requested = bool(json.load(r).get("stop"))
            return True
        except urllib.error.HTTPError as e:
            print(f"[진행판] 보내지 못함: {e.read().decode('utf-8', 'replace')[:200]}", file=sys.stderr)
        except (OSError, ValueError):
            self.enabled = False
        return False

    def suite(self, title, groups): return self.send("suite", title=title, groups=groups)
    def plan(self, group, items, label=None): return self.send("plan", group=group, label=label or group, items=items)
    def start(self, group, name, id=None, label=None): return self.send("start", group=group, name=name, id=id or name, label=label or group)
    def end(self, group, name, status, sec=None, detail="", id=None, label=None):
        return self.send("end", group=group, name=name, id=id or name, status=status, sec=sec, detail=detail, label=label or group)
    def done(self, group): return self.send("done", group=group)
    def finish(self): return self.send("finish")

    @contextlib.contextmanager
    def item(self, group, name):
        self.start(group, name)
        t = time.monotonic()
        try:
            yield
        except BaseException as e:
            self.end(group, name, "stop" if isinstance(e, KeyboardInterrupt) else "fail", time.monotonic() - t, f"{type(e).__name__}: {e}")
            raise
        self.end(group, name, "pass", time.monotonic() - t)
