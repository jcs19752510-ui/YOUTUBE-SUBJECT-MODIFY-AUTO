# 관리자 로그인 FE2 시험 결과서 (웹에서 최초 관리자 계정 만들기 + toyo 구성 로그인 화면)

- 시작 2026-10-15 02:50:19 UTC, 종료 약 02:55 UTC (소요 약 5분, 상한 12분 이내). 시각은 `date -u` 실측.
- 범위: `web/frontend/src/**` 만. 가짜 값(`testadmin`, `test-admin`, `Test-Passw0rd!`)만 사용.

## 한 것
- `api/types.ts`: `AuthMe.setup_required`. `api/client.ts`: `ConnectionState 'setup_required'`, `ensureSession` 이 `setup_required` 면 익명 세션 없이 그 상태로, `client.setup(loginId, password)`(성공 시 csrf·아이디·한도 저장 후 online, 실패는 ApiError, 409 `setup_closed` 는 `login_required` 로 전환 후 던짐).
- 새 `app/AuthCard.tsx`(회색 배경 + 가운데 흰 카드 최대 26.25rem), `app/LoginForm.tsx` 재작성(제목 "유튜브 제목 로그인 입력화면", 카드 오른쪽 위 빨간 안내 한 줄: 처음 "아이디를 입력해 주세요."→비밀번호 안내→오류 시 오류 문구 role=alert, placeholder, 전체 폭 파란 버튼), 새 `app/SetupForm.tsx`(검사 4종: 아이디 영숫자 4~20, 비밀번호 8~64, 두 비밀번호 일치; 서버 `setup_invalid` 문구 표시; 확인 입력은 서버로 보내지 않음).
- `app/AuthGate.tsx`: `setup_required`→SetupForm, `login_required`→LoginForm(만료 안내 유지). `i18n/ko.ts` 문구 추가, `styles/layout.css` 에 `.auth-*` 추가(기존 토큰만 사용, 새 색 없음).
- 접근성: 입력칸마다 aria-label + id/name + autocomplete(username / current-password / new-password) + aria-describedby 로 안내 문구 연결. axe 위반 0.
- 시험 `app/adminLogin.test.tsx`: 제품 변경 근거로 헤딩 기대값 `로그인`→`유튜브 제목 로그인 입력화면` 만 갱신(7곳, 문구 상수 `LOGIN_TITLE`), 신규 14개(client 3, SetupForm 검사 4종·성공·setup_invalid·409→로그인 화면·AuthGate 성공 진입·접근성/비밀번호 미노출(console·URL·localStorage·sessionStorage), LoginForm 안내 문구 1).

## 시험 결과
- 첫 실행(`vitest run src/app`): 5개 실패 — 전부 헤딩 `로그인` 기대값이 새 제목으로 바뀐 데서 온 것(기대값 갱신 후 통과). 신규 시험 첫 실행 6개 실패 — 시험 하네스 토스트 영역의 빈 role=alert 와 겹쳐 `findByRole('alert')` 다중 일치(시험 선택자 문제, 제품 결함 아님; 카드 안내 문구만 고르도록 수정).
- 재실행: `adminLogin.test.tsx` 34/34 통과.
- 전체 `npx vitest run`: 47 파일 통과·1 건너뜀, **967 통과**·1 expected fail·21 skip, 실패 0 (소요 76초). 기존 시험 기대값은 위 헤딩 문구 외 변경 없음.
- `npm run build`: 성공. `npx eslint src`: 경고·오류 0. `tsc --noEmit`: 오류 0.

## 안 한 것 / 미확인
- 브라우저(실제 화면·캡처) 확인 안 함: 카드 모양·빨간 문구 위치는 CSS 코드로만 작성, 눈으로 확인 안 함. "카드 오른쪽 위"는 카드 안 제목 아래 오른쪽 정렬 한 줄로 구현(toyo 캡처 대비 위치 차이 가능, 미확인).
- 백엔드 `/auth/setup`·`setup_required` 와의 실제 연동 시험 안 함(모의 응답만). 다크 모드 화면 미확인(토큰 재사용이라 대응될 것으로 추정).
- 변이 점검 안 함. 안내 문구 단계(아이디→비밀번호) 전환은 설계서 외 소폭 추가 동작.
