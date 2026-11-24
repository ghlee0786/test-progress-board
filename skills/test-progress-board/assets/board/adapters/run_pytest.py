"""pytest 를 진행판에 체크하며 돌린다. 뒤의 인자는 그대로 pytest 로 넘어간다.

    python <진행판 폴더>/adapters/run_pytest.py tests -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from board import Board, BoardError


class BoardPlugin:
    """수집이 끝나면 목록을 먼저 올리고, 테스트마다 시작 · 끝을 보낸다. 파일 하나가 그룹 하나."""

    def __init__(self, board):
        self.b, self.acc, self.groups = board, {}, []

    @staticmethod
    def split(nodeid):
        f, _, rest = nodeid.partition("::")
        return f, rest or f

    def pytest_collection_finish(self, session):
        by = {}
        for it in session.items:
            g, n = self.split(it.nodeid)
            by.setdefault(g, []).append({"id": it.nodeid, "name": n})
        self.groups = list(by)
        self.b.suite(f"pytest · {session.config.rootpath.name}", [{"id": g, "label": g, "items": v} for g, v in by.items()])

    def pytest_runtest_logstart(self, nodeid, location):
        g, n = self.split(nodeid)
        self.acc[nodeid] = {"status": "pass", "sec": 0.0, "detail": ""}
        if g not in self.groups:
            self.groups.append(g)
        self.b.start(g, n, id=nodeid)

    def pytest_runtest_logreport(self, report):
        a = self.acc.setdefault(report.nodeid, {"status": "pass", "sec": 0.0, "detail": ""})
        a["sec"] += report.duration
        if report.failed:
            a["status"] = "fail"
            crash = getattr(getattr(report.longrepr, "reprcrash", None), "message", None)
            a["detail"] = (f"[{report.when}] " if report.when != "call" else "") + str(crash or report.longreprtext)[:1500]
        elif report.skipped and a["status"] != "fail":
            a["status"] = "skip"
            reason = getattr(report, "wasxfail", None)
            a["detail"] = f"xfail: {reason}" if reason is not None else (report.longrepr[2] if isinstance(report.longrepr, tuple) else "")

    def pytest_runtest_logfinish(self, nodeid, location):
        a = self.acc.pop(nodeid, None)
        if a:
            g, n = self.split(nodeid)
            self.b.end(g, n, a["status"], a["sec"], a["detail"], id=nodeid)

    def pytest_runtest_protocol(self, item, nextitem):
        if self.b.stop_requested:
            item.session.shouldstop = "진행판에서 멈춤"

    def pytest_sessionfinish(self, session):
        for g in self.groups:
            self.b.done(g)
        self.b.finish()


def main(argv):
    import pytest
    board = Board()
    try:
        board.ensure()
    except BoardError as e:
        print(f"[진행판] {e} — 진행판 없이 돌립니다.", file=sys.stderr)
        board.enabled = False
    sys.path.insert(0, "")                        # python -m pytest 와 같게
    return int(pytest.main(argv, plugins=[BoardPlugin(board)]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
