# 로그인 화면 자동 채움 차단 — 독립 검증 (2026-10-15)

시작 04:50:37 UTC, 종료 약 04:59 UTC (약 8분 30초, 상한 12분 이내). 커밋·푸시·git add·소스 편집 없음. docker 미사용.

## 한 줄 결론
조건부 합격. 차단 기능(속성·읽기 전용·비움·새로고침·뒤로/앞으로·로그아웃)과 사람 키보드 로그인은 정상. 결함 2건: (D-1) 키 이벤트 없이 들어오는 입력(음성·가상 키보드·IME 일부)이 화면이 열린 뒤 1.5초 안에 시작되면 지워짐, (D-2) 화면이 뜬 뒤 1.5초가 지난 늦은 자동 채움은 막지 못함(설계 한계). 헤드리스 Chromium 에는 실제 Chrome 비밀번호 관리자가 없어 실제 효과는 선생님 PC 에서만 확인 가능.

## 명령
- 변경 확인: `git diff web/frontend/src/app/LoginForm.tsx` (검증 시작 시점에는 소스가 아직 미수정이었고 04:50:40 에 반영되어 다시 읽고 검증함)
- 단위: `npx vitest run src/app/loginForm.noautofill.test.tsx src/app/adminLogin.test.tsx` → 2파일 29 통과(04:50:45)
- 빌드: `npm run build` 성공(dist)
- 실제 Chromium: `web/tests_fullcheck/login/login.e2e.mjs` (playwright-core + axe-core, 실행 파일 /opt/pw-browsers/chromium-1194, 작은 정적 서버, `page.route` 로 /api/v1/** 가짜 응답: auth/me·login·session DELETE·dashboard 503)
- 실행 기록(보존): first-run-0-harness-error.txt(시험 코드 변수명 오류 URL 로 실행 즉시 중단, 제품 결과 아님) → first-run-1.txt(25항목 22 통과 3 실패) → second-run-2.txt / third-run-3.txt / fourth-run.txt(27항목)
- 소요: E2E 1회 약 50초. 전체 약 8분 30초.

## 시험표 (첫 실행 first-run-1.txt 와 최종 fourth-run.txt)
| 항목 | 기대 | 실제 | 판정 |
|---|---|---|---|
| a form/아이디/비밀번호 속성 | form off, 아이디 off·admin-login-id, 비번 new-password·admin-login-secret, type=password | 일치 | PASS |
| a2 초기 readOnly·포커스 | 둘 다 readonly, 활성 요소 BODY | 일치(자동 포커스 없음) | PASS |
| b 자동 채움 흉내(input 이벤트 있음) +0/200/800ms | 2.3초 안에 비워짐 | 비워짐, 안내 "아이디를 입력해 주세요." | PASS x3 |
| b 자동 채움 흉내(이벤트 없음, 화면 값만) +0/200/800ms | 비워짐 | 비워짐 | PASS x3 |
| b2 화면 연 지 2초 뒤 늦은 채움 | (참고) 설계상 못 막음 | 값이 남음 | 한계 D-2 |
| c 사람이 클릭 후 타이핑, 2초 대기 | 값 유지, 버튼 활성 | 유지, 활성 | PASS |
| c 제출 | 가짜 /auth/login 에 입력값 그대로 | `{login_id, password}` 입력값 일치 1회 | PASS |
| c2 느린 타이핑(타이머 구간 겹침) | 유지 | 유지 | PASS |
| c3 insertText(키 이벤트 없음) 화면 연 직후 | 유지 | 지워짐 | FAIL(첫 실행부터 동일) D-1 |
| c3b 같은 입력을 2.2초 뒤에 | 유지 | 유지 | PASS |
| c4 붙여넣기 이벤트 + 삽입 | 유지 | 유지 | PASS |
| c5 한글 IME 흉내(composition 이벤트 + insertText, keydown 없음) | 유지 | 지워짐 | FAIL(첫 실행부터 동일) D-1 |
| c6 한글 type() | 유지 | 유지 | PASS |
| d 새로고침 / d2 뒤로 / d3 앞으로 | 비어 있음 | 모두 비어 있음 | PASS x3 |
| e 로그아웃 후 로그인 화면 | 비어 있음 | 비어 있음 | PASS(첫 실행은 가짜 dashboard 응답 결함으로 앱이 빈 화면이 되어 FAIL, 시험 도구 문제로 응답을 고쳐 재실행) |
| e2 로그아웃 뒤 새로고침 직후 자동 채움 흉내 | 비워짐 | 비워짐 | PASS(2~3차 실행은 내 시험이 옛 화면에 채워 FAIL, 시험 코드 경쟁 상태를 고쳐 4차 PASS) |
| f URL·localStorage·sessionStorage·cookie·화면 글자에 값 없음, type=password | 모두 없음 | 없음 | PASS |
| g Tab,Tab,Enter 로 키보드만 로그인 | 아이디→비밀번호→제출 | 일치, 전송 1회 | PASS |
| g2/g3 axe-core 위반 | 0 | 0 / 0 | PASS |
| h 틀린 로그인 | 오류 메시지, 비번 비움 | 메시지 표시, 아이디 유지, 비번 비움 | PASS |
최종 27항목 중 25 통과, 2 실패(D-1, 기대값은 고치지 않음).

## 코드 검토 (LoginForm.tsx, 변경분)
- 줄 41~66 타이머 [60,250,700,1500]ms: `typed.current` 가 false 면 `wipe()` 로 상태와 DOM 을 비움. `typed` 는 `onKeyDown`·`onPaste`(줄 120 전후)에서만 true. 키 이벤트가 없는 입력(음성 입력, 일부 모바일 가상 키보드, IME 가 keydown 없이 확정되는 경우, 드래그 앤 드롭)은 사람 입력으로 인식되지 않아 1.5초 안에 지워진다. 보통 사람이 화면을 보고 칸을 누르는 데 1.5초 이상 걸려 실사용 영향은 낮지만 0 은 아니다. 대안(구현 아님, 보고만): `onChange` 가 `inputType`(insertText 등, 자동 채움은 inputType 없음) 또는 `isTrusted` 입력 이벤트를 받으면 typed=true 로 처리.
- `typed` 는 한 번 true 가 되면 뒤로 가기(pageshow persisted)에서만 false 로 돌아감: 로그인 실패 후 같은 화면에서는 이후 자동 채움을 막지 않음(비번은 이미 비워짐). 영향 낮음.
- 줄 104 전후 `readOnly={!armed}`, `onFocus`·`onPointerDown` 으로 해제: 스크린리더·키보드(Tab)는 포커스 순간 해제되어 조작 가능. 다만 읽기 전용 상태의 칸은 일부 스크린리더가 "읽기 전용"으로 읽을 수 있으나 axe 위반은 0. Tab 이동 시 포커스 직후 해제까지 사이에 첫 글자가 입력될 가능성은 시험(g, c)에서 재현되지 않음.
- 자동 포커스 상호작용: 이 화면은 `data-autofocus` 를 쓰지 않고(시험 a2 에서 포커스 BODY) readOnly 해제가 즉시 일어나지 않음. 단 `Modal` 안에서 재사용되면 포커스 때문에 즉시 해제됨(현재 사용처 아님, 확인 안 함).
- 값 유출: 입력값은 상태와 ref 로만 존재, URL·저장소·쿠키·console 에 없음(f 시험). 줄 69 `wipeDom` 이 제어 입력의 DOM 값을 직접 바꾸지만 상태와 함께 비우므로 불일치 없음.
- 한글 IME: type() 은 유지(c6). 조합 도중 타이머가 지우는 경우는 keydown 이 없는 IME 에서만 발생(c5), 한국어 Windows Chrome 의 일반 한글 입력은 keydown 이 발생하므로 위험은 낮을 것으로 보지만 실제 IME 는 시험하지 못함.
- 기존 시험 `adminLogin.test.tsx` 기대값 변경(autocomplete off/new-password, name admin-login-id)은 변경 의도와 일치. 이 변경으로 실패한 시험을 통과시킨 것이 아니라 속성값 자체를 바꾼 것이며 원래 값이 diff 에 남아 있음.

## 결함 목록
- D-1 (Low~Medium): 화면이 열린 뒤 1.5초 안에 키 이벤트 없이 들어온 입력이 지워짐. 재현: 로그인 화면 로드 직후 칸 클릭, `page.keyboard.insertText('abc')`, 2초 뒤 칸이 비어 있음(c3, c5). 2.2초 뒤 같은 입력은 유지(c3b).
- D-2 (설계 한계, Medium): 화면이 뜬 뒤 1.5초가 지나 브라우저가 채우면 비워지지 않음(b2). 이 화면은 브라우저 자체의 저장·자동 채움을 끌 수 없다. 로그아웃 뒤 새로고침 직후 채움은 막힘(e2).
- 실제 Chrome 에서의 효과는 미확인: `autocomplete="new-password"` 와 readOnly 는 Chrome 이 존중하는 경우가 많지만 Chrome 은 비밀번호 필드에 autocomplete 를 무시할 수 있다. 

## 한계와 미수행
- 헤드리스 Chromium 에는 비밀번호 관리자(저장된 자격 증명)가 없다. 이 시험은 "브라우저가 값을 채우는 상황의 흉내"(DOM 값 직접 설정)이며 실제 Chrome 의 동작은 선생님 PC 에서만 확인 가능.
- 미수행: 실제 IME(한글 조합) 입력, 모바일/터치, 스크린리더 실제 낭독, 실제 백엔드 연동(가짜 응답 사용, 제출 본문만 확인), 전체 회귀, Firefox/Safari.
- 캡처: .harness-tmp/results/login-screens/ (a-initial.png, c-after-login.png, e-no-logout-btn.png 는 시험 도구 결함 때 찍힌 빈 화면). 비밀번호가 글자로 찍힌 캡처 없음(c-after-login 은 로그인 후 화면).
