# 이벤트

`POST http://127.0.0.1:<포트>/api/event` 에 JSON 하나. 답은 `{"ok": true, "stop": false}` — `stop` 이 `true` 면 사용자가 멈추기를 눌렀다는 뜻이니 하던 항목까지만 하고 끝낸다. 잘못된 이벤트는 400 과 `error`.

| type | 필드 | 뜻 |
|---|---|---|
| `suite` | `title`, `groups: [{id, label?, items: [이름 또는 {id, name}]}]` | 새 실행. 전체 목록을 올린다 (모두 대기) |
| `plan` | `group`, `label?`, `items` | 한 그룹의 목록을 새로 올리고 시작 |
| `start` | `group`, `name`, `id?` | 항목 진행 중 |
| `end` | `group`, `name`, `id?`, `status`, `sec?`, `detail?` | 항목 끝. `status`: `pass` 완료 · `fail` 실패 · `skip` 건너뜀 · `stop` 중단 |
| `done` | `group` | 그룹 끝. 남은 항목은 중단 |
| `finish` | — | 실행 전체 끝. 남은 항목은 중단 |
| `stop` | — | 멈추기 요청 (화면의 버튼이 보낸다) |
| `reset` | — | 비우기 |

- 항목은 `id` 로 찾고, 없으면 `name` 이 `id` 다. 이름이 겹치면 `id` 를 준다.
- 올리지 않은 그룹 · 항목에 `start` / `end` 를 보내면 그 자리에서 추가된다.
- `sec` 을 안 주면 `start` 부터의 시간을 쓴다. 통과한 시간의 최근 5번 중간값이 다음 실행의 예상 시간이 된다.
- 한도: 본문 2MB, 항목 10,000개, `detail` 4,000자.

그 밖에 `GET /api/state`(지금 상태) · `GET /api/stream`(SSE) · `GET /api/health`(`app`, `version`, `pid`).

## 파이썬

```python
import sys; sys.path.insert(0, "tools/test-board/adapters")
from board import Board

b = Board(); b.ensure()
b.suite("배포 전 점검", [{"id": "api", "label": "API", "items": ["로그인", "조회"]}])
for name, fn in {"로그인": check_login, "조회": check_list}.items():
    if b.stop_requested: break
    try:
        with b.item("api", name): fn()
    except AssertionError: pass          # 화면에는 '실패' 로 남는다
b.done("api"); b.finish()
```

## Node

```js
import { Board } from "./tools/test-board/adapters/board.mjs";
const b = new Board(); await b.ensure();
await b.suite("점검", [{ id: "web", label: "웹", items: ["첫 화면"] }]);
await b.item("web", "첫 화면", async () => { /* … */ }).catch(() => {});
await b.done("web"); await b.finish();
```

## 셸

```bash
curl -s -X POST http://127.0.0.1:8790/api/event -d '{"type":"end","group":"g","name":"x","status":"pass","sec":1.2}'
```

Windows 셸에서 한글을 `curl -d` 로 보내면 인코딩이 깨질 수 있다 — UTF-8 파일에 쓰고 `--data-binary @파일` 로 보낸다.
