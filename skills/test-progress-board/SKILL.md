---
name: test-progress-board
description: 테스트 진행판(로컬 React 체크리스트 화면)을 프로젝트에 만들어 넣고 테스트를 그 위에서 돌린다. 항목 목록을 먼저 다 보여 주고, 하나씩 대기 → 진행 중 → 완료 · 실패 · 건너뜀으로 실시간 체크하며, 예상 남은 시간과 멈추기 버튼이 있다. pytest · Playwright · dotnet test · 임의의 명령 목록을 지원한다. "테스트 진행판", "테스트 목록 체크하면서 진행", "테스트 진행 상황 보여줘", "체크리스트 화면으로 테스트", "테스트가 어디까지 됐는지", live test checklist, test progress dashboard 를 말할 때 쓴다. 오래 걸리는 테스트 · 점검을 사용자가 지켜보는 상황에서도 쓴다.
---

# 테스트 진행판

오래 걸리는 테스트를 조용히 돌리지 않는다. 무엇을 할지 먼저 다 보여 주고, 하나씩 체크하면서 한다.

## 순서

1. **범위를 정한다.** 사용자가 시킨 것만. 관련 있어 보인다는 이유로 다른 프로젝트 · 버전 · 묶음까지 넓히지 않는다. 애매하면 시작하기 전에 묻는다.
2. **넣는다** (프로젝트에 한 번).
   ```
   python <이 스킬>/scripts/apply.py <프로젝트 폴더> --dry-run     # 무엇을 넣을지 먼저 보기
   python <이 스킬>/scripts/apply.py <프로젝트 폴더>
   ```
   `tools/test-board/` 에 들어가고, 쓰는 테스트 도구를 찾아 어댑터를 고른 뒤 실행 명령을 알려 준다. 다시 실행하면 새 판으로 바꾸되 사용자가 고친 파일은 남긴다.
3. **돌린다.** 알려 준 명령을 **백그라운드로** 실행하고, 시작했다는 것과 진행판 주소를 바로 말한다. 서버가 꺼져 있으면 켜고 브라우저를 연다.

   | 어댑터 | 명령 | 그룹 · 항목 |
   |---|---|---|
   | pytest | `python tools/test-board/adapters/run_pytest.py [pytest 인자]` | 파일 · 테스트 |
   | Playwright | `node tools/test-board/adapters/run_playwright.mjs [playwright 인자]` | 파일(프로젝트) · 테스트 |
   | dotnet | `python tools/test-board/adapters/run_dotnet.py [dotnet test 인자]` | 클래스 · 테스트 |
   | 그 밖의 모든 것 | `python tools/test-board/adapters/run_commands.py tools/test-board/checklist.json` | 직접 쓴 목록 |

   다른 도구이거나 직접 만든 시험이면 `checklist.json` 을 쓰거나, 코드에서 이벤트를 보낸다 → [references/events.md](references/events.md).
4. **결과를 말한다.** 통과 · 실패 · 건너뜀 수, 걸린 시간, 실패한 항목과 원인, 하지 않은 것. 진행판 화면만 가리키고 끝내지 않는다.

## 지킬 것

- **건너뜀은 완료가 아니다.** 앞이 실패해서 못 본 것을 통과로 세지 않는다.
- **재시도로 통과한 것은 그렇게 적는다.** 간헐 실패는 정상이 아니다.
- 실패의 원인을 확인하기 전에 "환경 문제" 라고 하지 않는다. 확인하지 못했으면 못 했다고 쓴다.
- 사용자가 "멈추기" 를 누르면(종료 코드 3) 다시 돌리지 않는다. 남은 항목은 '중단' 이다.
- 정상 확인은 한 번이면 된다. 반복 실행은 불안정함을 조사할 때만.
- 항목 이름 · 설명(`detail`)에 비밀번호 · 토큰 · 개인 정보를 넣지 않는다. 화면과 `.data/` 에 그대로 남는다.
- 한 화면(데스크톱 · 브라우저 포커스)을 쓰는 테스트는 동시에 하나만 돌린다.

## 설정

- 포트: 넣을 때 `--port`, 또는 환경 변수 `TEST_BOARD_PORT` (기본 8790). 다른 프로그램이 쓰는 포트면 진행판 없이 테스트만 돌고 그 사실을 알린다.
- `TEST_BOARD=0` 진행판 끄기(CI 등) · `TEST_BOARD_OPEN=0` 브라우저 열지 않기.
- 서버 끄기: `GET /api/health` 의 `pid` 를 끝낸다.
- 화면을 고치려면 `src/app.jsx` 를 고친 뒤 `npm i && npm run build`. 실행에는 필요 없다.

어댑터별 동작과 한계(dotnet 의 '진행 중' 표시, xdist, 멈추기 방식)는 [references/adapters.md](references/adapters.md).
