"""프로젝트에 테스트 진행판을 넣는다.

    python apply.py <프로젝트 폴더> [--dest tools/test-board] [--adapter auto] [--port 8790] [--title 이름] [--force] [--dry-run]

어댑터: auto(찾아서 고름) · pytest · playwright · dotnet · commands. 여러 번 줄 수 있다.
이미 넣은 프로젝트에 다시 쓰면 새 판으로 바꾼다. 사용자가 고친 파일은 --force 없이 덮어쓰지 않는다.
"""
import argparse, hashlib, json, shutil, sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "board"
CORE = ["server.mjs", "public/index.html", "public/app.js", "src/app.jsx", "build.mjs", "package.json", "adapters/board.py", "adapters/board.mjs"]
ADAPTERS = {
    "pytest": ["adapters/run_pytest.py"],
    "playwright": ["adapters/run_playwright.mjs", "adapters/playwright_reporter.mjs"],
    "dotnet": ["adapters/run_dotnet.py"],
    "commands": ["adapters/run_commands.py"],
}
SKIP = {"node_modules", "bin", "obj", ".git", ".venv", "venv", "dist", "build", "packages", "__pycache__"}
MANIFEST, MAX_DEPTH = ".manifest.json", 4


def digest(data): return hashlib.sha256(data).hexdigest()


def walk(root, depth=0):
    """깊이와 폴더를 제한해 훑는다 (큰 저장소에서도 빠르게)."""
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return
    for p in entries:
        if p.is_symlink():
            continue
        if p.is_dir():
            if p.name not in SKIP and not p.name.startswith(".") and depth < MAX_DEPTH:
                yield from walk(p, depth + 1)
        else:
            yield p


def read(p):
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def detect(project, dest):
    """파일을 보고 쓰는 테스트 도구를 고른다 → {어댑터: 근거}"""
    found = {}
    for p in walk(project):
        if dest in p.parents:
            continue
        rel = p.relative_to(project).as_posix()
        if p.name in ("pytest.ini", "conftest.py") or (p.name == "pyproject.toml" and "pytest" in read(p)) or (p.name.startswith("test_") and p.suffix == ".py"):
            found.setdefault("pytest", rel)
        elif p.name.startswith("playwright.config.") or (p.name == "package.json" and '"@playwright/test"' in read(p)):
            found.setdefault("playwright", rel)
        elif p.suffix in (".csproj", ".fsproj", ".vbproj") and "Microsoft.NET.Test.Sdk" in read(p):
            found.setdefault("dotnet", rel)
    return found


def example(rel):
    return {"title": "점검 목록", "groups": [{"id": "example", "label": "예시", "items": [
        {"name": "첫 항목", "run": ["python", "-c", "print('ok')"]},
        {"name": "앞 항목이 통과해야 하는 항목", "run": ["python", "-c", "print('ok')"], "needs": ["첫 항목"]}]}]}


def main(argv):
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("project"); ap.add_argument("--dest", default="tools/test-board"); ap.add_argument("--adapter", action="append", choices=["auto", *ADAPTERS])
    ap.add_argument("--port", type=int); ap.add_argument("--force", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    project = Path(a.project).resolve()
    if not project.is_dir():
        print(f"폴더가 없습니다: {project}", file=sys.stderr); return 2
    dest = (project / a.dest).resolve()
    if dest == project or project not in dest.parents:
        print("--dest 는 프로젝트 안의 하위 폴더여야 합니다.", file=sys.stderr); return 2
    if a.port is not None and not 1024 <= a.port <= 65535:
        print("--port 는 1024~65535 입니다.", file=sys.stderr); return 2
    if dest.exists() and any(dest.iterdir()) and not (dest / MANIFEST).exists():
        print(f"이미 다른 내용이 있는 폴더입니다: {dest} — --dest 로 다른 곳을 고르세요.", file=sys.stderr); return 2

    wanted = a.adapter or ["auto"]; chosen = [x for x in wanted if x != "auto"]
    if "auto" in wanted:
        for name, why in detect(project, dest).items():
            print(f"찾음: {name}  ({why})")
            if name not in chosen: chosen.append(name)
        if not chosen:
            print("알려진 테스트 도구를 찾지 못해 명령 목록(commands) 방식으로 넣습니다."); chosen = ["commands"]

    old = json.loads((dest / MANIFEST).read_text(encoding="utf-8")) if (dest / MANIFEST).exists() else {"files": {}, "adapters": []}
    adapters = list(dict.fromkeys([*old["adapters"], *chosen]))
    files = {f: (ASSETS / f).read_bytes() for f in [*CORE, *(x for n in adapters for x in ADAPTERS[n])]}
    cfg = {}
    if (dest / "board.config.json").exists():
        try: cfg = json.loads((dest / "board.config.json").read_text(encoding="utf-8"))
        except ValueError: pass
    cfg["port"] = a.port or cfg.get("port") or 8790

    kept, wrote, new = [], [], {}
    for rel, data in files.items():
        p = dest / rel
        if p.exists():
            cur = digest(p.read_bytes())
            if cur == digest(data): new[rel] = cur; continue
            if cur != old["files"].get(rel) and not a.force:
                kept.append(rel); new[rel] = old["files"].get(rel); continue
        wrote.append(rel); new[rel] = digest(data)
        if not a.dry_run:
            p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
    if not a.dry_run:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "board.config.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        (dest / MANIFEST).write_text(json.dumps({"app": "test-progress-board", "adapters": adapters, "files": new}, indent=1) + "\n", encoding="utf-8")
        ig = dest / ".gitignore"
        if not ig.exists(): ig.write_text(".data/\nnode_modules/\n__pycache__/\n", encoding="utf-8")
        if "commands" in adapters and not (dest / "checklist.json").exists():
            (dest / "checklist.json").write_text(json.dumps(example(a.dest), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    d = dest.relative_to(project).as_posix()
    print(f"\n{'넣을' if a.dry_run else '넣은'} 파일 {len(wrote)}개 · 그대로 {len(files) - len(wrote) - len(kept)}개 → {dest}")
    for k in kept: print(f"고친 파일이라 그대로 둠 (바꾸려면 --force): {k}")
    print(f"진행판 http://127.0.0.1:{cfg['port']}\n\n실행 (프로젝트 폴더에서):")
    cmds = {"pytest": f"python {d}/adapters/run_pytest.py", "playwright": f"node {d}/adapters/run_playwright.mjs",
            "dotnet": f"python {d}/adapters/run_dotnet.py", "commands": f"python {d}/adapters/run_commands.py {d}/checklist.json"}
    for n in adapters: print(f"  {cmds[n]}")
    if not shutil.which("node"): print("\n주의: node 를 찾을 수 없습니다. 진행판 서버에 Node.js 18 이상이 필요합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
