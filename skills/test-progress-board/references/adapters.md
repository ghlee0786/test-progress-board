# 어댑터

공통: 진행판을 쓸 수 없으면 이유를 알리고 테스트만 돌린다. 종료 코드는 원래 도구의 것을 그대로 돌려준다 (명령 목록은 아래).

## pytest — `run_pytest.py`

- 수집이 끝나면 목록을 올린다. 파일 = 그룹. setup · teardown 실패도 실패로 잡고 어느 단계인지 적는다. `xfail` 은 건너뜀.
- 멈추기: 하던 테스트까지 하고 끝낸다.
- `pytest-xdist`(`-n`)를 쓰면 목록을 먼저 올리지 못하고 시작하는 대로 추가된다 (시험해 보지 않음).

## Playwright — `run_playwright.mjs`

- 파일(프로젝트가 있으면 프로젝트 · 파일) = 그룹. 재시도는 마지막 결과만 남기고 "재시도 n번째에 통과" 라고 적는다. `test.fail()` 로 예상한 실패는 완료.
- `--reporter` 를 직접 주면 진행판 리포터가 빠진다. 리포터를 더 쓰려면 `playwright_reporter.mjs` 를 설정의 `reporter` 목록에 넣는다.
- 멈추기: 실행 중인 테스트를 바로 끊는다. 종료 코드 3.

## dotnet — `run_dotnet.py`

- 목록은 `dotnet test --list-tests`, 결과는 콘솔 출력(영어로 고정)을 읽는다. 클래스 = 그룹.
- dotnet 이 테스트의 시작을 알려 주지 않아 항목은 대기에서 바로 완료 · 실패로 바뀐다. 걸린 시간이 아주 짧으면 0초로 보인다.
- VSTest 방식만. Microsoft.Testing.Platform 방식의 `dotnet test` 는 지원하지 않는다.
- 멈추기: 바로 끊는다. 종료 코드 3.

## 명령 목록 — `run_commands.py`

```json
{ "title": "배포 전 점검",
  "groups": [
    { "id": "build", "label": "빌드", "stop_on_fail": true,
      "items": [ { "name": "설치", "run": ["npm", "ci"], "timeout": 300 },
                 { "name": "빌드", "run": "npm run build", "needs": ["설치"] } ] },
    { "id": "smoke", "label": "확인",
      "items": [ { "name": "응답", "run": ["curl", "-fsS", "http://127.0.0.1:3000/health"], "env": { "LANG": "C" } } ] } ] }
```

- `run` 이 목록이면 셸 없이, 문자열이면 셸로. 종료 코드 0 = 완료, 설명에는 마지막 출력 줄이 남는다.
- `cwd` 는 이 파일이 있는 폴더 기준. `timeout`(초)이 지나면 자식 프로세스까지 끝내고 실패.
- `needs` 는 같은 그룹의 앞 항목. 통과하지 못했으면 건너뜀. `stop_on_fail` 은 그 그룹의 남은 항목을 중단.
- `--only <그룹 id>` 로 일부만. 종료 코드: 0 모두 통과 · 1 실패나 건너뜀 · 2 설정 오류 · 3 멈춤.
- 목록의 명령을 그대로 실행한다. 믿을 수 없는 곳에서 받은 목록은 돌리지 않는다.
