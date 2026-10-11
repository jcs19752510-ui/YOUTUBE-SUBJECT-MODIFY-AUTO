# 테스트 결과서 — W-FE 웹 프런트엔드 (React, 6단계 독립 검증)

> 작성: 6단계 독립 심사자(QA 리드 역할, 임시 폴더 이름 `vf`), 2026-10-10. 구현자의 시험(TC-WF-001~095)을 믿지 않고 설계서·API.md·요구사항에서 새로 시험(TC-VF)을 만들어 검증했다. 이전에 한도로 중단된 진행분(`web/frontend/verify/`, TC-VF-001~189)은 **검토 후 재사용**했고, 그중 시험 설계 결함 4건을 고쳤다(6절 TD).

## 1. 개요
- 테스트 대상: 모듈 — 작업 단위 **W-FE**(`web/frontend/`: React 19 + TypeScript strict + Vite 프런트엔드, 8개 화면 + 상태 화면 + 모의 서버). 백엔드(W-BE-A/B)와 인프라(W-INF)는 읽기만 했고, 실제 백엔드와의 연동 시험에서 백엔드 결함 1건(DEF-VF-B01)을 발견해 보고한다.
- 테스트 유형: 단위(화면·컴포넌트·API 클라이언트) + 실서버 계약 연동 + 실브라우저(Chromium) 점검. 통합(07단계) 범위의 nginx/compose 경유 시험은 하지 않았다.
- 적용 Tier: Standard (규칙 B 원문: 최소 2회 검증)
- 적용 속도 트랙: L3(노트에 표기 없음 → 기본 L3, 전 섹션 작성)
- 병렬 실행 정보: 병렬 웨이브에서 실행(동시에 W-BE-A `va`, W-BE-B `vb`, W-INF `vi` 독립 검증이 돌고 있었음). 임시 파일은 `.harness-tmp/vf/` 아래에만 만들었다. 06·07 병합은 적용하지 않음(병렬 호출).
- 테스트 목적: 노트의 인수 조건(§13)과 요청서의 중점 검증 항목(전 화면 상태, 확인 문구, 승인 흐름, 폴링, 오류 코드 안내, CSRF·세션·멱등키, XSS, 접근성, 모바일 폭, 한국어 일관성, 정적 검사)을 시험으로 증명하고, 변이 점검으로 시험이 결함을 놓치지 않는지 확인한다.
- 관련 산출물: `docs/harness/units/web-WU-FE-note.md`, `docs/yt/DESIGN.md` Part B(검증 대기 표 V-03), `docs/yt/WEB_DESIGN.md`, `docs/yt/API.md`, `웹프로그램으로수정요청.md`, `docs/harness/_parallel/web-verify-brief.md`
- 테스트 수행자(에이전트): 06단계 독립 검증 에이전트(`vf`)
- 테스트 일시: 2026-10-10 (세션 한도로 중단 후 재개해 완료)

## 2. 테스트 범위 및 제외 범위
- 범위(In-Scope)
  - 화면 8개(홈, 영상 목록, 영상 상세, 배치 목록/상세, 이력·롤백, 성과 리포트, 설정 4탭)의 **정상·빈 상태·오류·로딩** 상태
  - 되돌릴 수 없는 동작의 확인 장치: 배치 실행 확인 문구 `실행 N건`, 롤백 영상 ID 직접 입력, 반려·중지·PIN 해제 대화상자, 승인 규칙(차단 불가, 경고 확인 체크, 엄격 모드)
  - API 클라이언트: 세션 시작, CSRF, Idempotency-Key, 401/403 재발급 1회 재시도, 네트워크 오류·시간 제한, 오류 코드→한국어 안내
  - 배치/작업 폴링(2초/1초)·중지, XSS(외부 문자열 텍스트 출력), 접근성(키보드, 포커스, aria, 색+기호+글자, 색 대비), 해상도(1024/1280/375), 다크 모드
  - 정적 검사(`tsc`, ESLint, Prettier, build, audit), 소스 규칙(저장소 사용 금지 등)
  - **실서버 연동**: 임시 PostgreSQL(포트 54333) + FastAPI 백엔드 + 워커를 띄우고 프런트의 실제 `ApiClient`/`endpoints` 로 계약 확인 21건, 실제 Chromium 으로 전체 흐름·axe(색 대비 포함) 점검
- 제외 범위(Out-of-Scope) 및 사유
  - nginx/compose 경유 구성, 속도 제한(nginx 30/s), CSP 헤더 실동작 → 07단계(V-05) 범위
  - 실제 Windows Docker Desktop, 사용자 PC 실측, 스크린리더(NVDA 등), Edge/Firefox/Safari, 실기기 모바일 → 환경 없음(미수행, 8절)
  - `dist` 에 테스트 파일이 안 들어가는지 → **DEC-041 ⑤ "코드 미반영"** 이라 결함이 아니라 *알려진 미반영*으로 기록(`tsc -b` 가 `src/**/*.test.tsx` 를 포함하지만 번들에는 시험 코드가 0건임을 확인: dist 에서 `TC-WF`·`vitest`·`@testing-library` 검색 0건)
  - 가상 스크롤·OpenAPI 타입 생성(노트가 미적용으로 명시, 설계서 §6 완화) → 대상 아님

## 3. 테스트 환경
- 실행 환경: Linux 6.18, Node 22.22.0 / npm 10.9.4, Vitest 5.0.3 + jsdom 30.1.2 + Testing Library, axe-core 4.14.0. 실브라우저는 Chromium 1194(`/opt/pw-browsers`, 저장소 밖 `playwright-core` 로 구동). 실서버: 호스트 PostgreSQL 16(`/usr/lib/postgresql/16/bin`, 포트 54333, 127.0.0.1 전용), Python 3.13.16 임시 venv(`web/backend/requirements.txt` 해시 잠금 설치, FastAPI 0.143.0, uvicorn 0.54.0) + 워커. 운영 이미지는 PostgreSQL 17·Python 3.12 이므로 **버전 차이**가 있다(해시 잠금 파일 `requirements-youtube-title.txt` 의 pyyaml 은 cp312 휠 해시라 3.13 에서 불일치 → 임시 venv 에서만 같은 버전을 해시 없이 설치).
- 테스트 데이터: 시험 안의 가짜 응답(모의 fetch), 서버의 데모 영상 200개(모의 AI 제안). 실제 구글·유튜브·AI 호출 없음, 외부 전송 없음. 토큰·비밀 값은 출력·기록하지 않았다(시험용 PIN `4321` 등은 임시 DB 안의 가짜 값).
- 전제 조건: `npm ci --ignore-scripts` 는 `.harness-tmp/vf/work/` 에서만 수행(저장소 `web/frontend/node_modules` 없음). 소스는 `.harness-tmp/vf/sync.sh` 로 저장소→작업 복사본에 동기화하여 시험.
- **재실행 방법**
  - 일반 시험(실서버 없이): 작업 복사본에서 `npx vitest run` → 505건 통과, 21건 건너뜀(실서버 시험)
  - 실서버 시험: 백엔드 기동 후 `VF_LIVE_API=http://127.0.0.1:18080 npx vitest run verify/live.verify.test.ts` (`VF_LIVE_SETTLE_MS=0` 이면 DEF-VF-B01 경쟁이 재현됨)
  - 변이 점검: 6절·부록 A 의 변이 목록은 `.harness-tmp/vf/muts_*.py`(정리 시 삭제됨) — 표의 "내용" 만으로 재현할 수 있게 적었다.

## 4. 테스트 케이스 및 결과
> 시험 ID `TC-VF-nnn`(001~241 jsdom 단위, 300~320 실서버). 구현자 시험은 `TC-WF-001~095`(95건, 전부 통과, 이 결과서의 회귀로 같이 실행). "실제 결과: 통과(N건)" 는 같은 ID 아래 표 입력 변형(it.each)이 N건이고 전부 통과했다는 뜻이다. **예상 결과는 시나리오 문장 안의 기대**이며 모두 설계서·API.md·요구사항에서 직접 도출했다. 실행 수치는 4-2.

| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|---|---|---|---|---|---|---|---|
| TC-VF-001 | GET 엔드포인트 전부는 X-CSRF-Token 도 Idempotency-Key 도 보내지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-001"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | CSRF·Idempotency-Key 부착 규칙 |
| TC-VF-002 | 상태 변경 엔드포인트(POST/PATCH) 전부가 세션에서 받은 CSRF 토큰을 보낸다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-002"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | CSRF·Idempotency-Key 부착 규칙 |
| TC-VF-003 | DELETE(로그아웃)도 CSRF 토큰을 보낸다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-003"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | CSRF·Idempotency-Key 부착 규칙 |
| TC-VF-004 | Idempotency-Key 는 위험 동작 3종(배치 생성·실행, 롤백)에만 붙고 넘겨준 값 그대로다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-004"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | CSRF·Idempotency-Key 부착 규칙 |
| TC-VF-005 | 키를 넘기지 않은 위험 호출은 호출마다 서로 다른 키(UUID 형식)를 만든다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-005"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | CSRF·Idempotency-Key 부착 규칙 |
| TC-VF-006 | Content-Type 은 본문이 있을 때만, Accept 는 항상, 쿠키는 same-origin 으로 보낸다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-006"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | CSRF·Idempotency-Key 부착 규칙 |
| TC-VF-007 | 엔드포인트 계약: 메서드·경로·본문이 설계서 §3 과 같다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-007"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | CSRF·Idempotency-Key 부착 규칙 |
| TC-VF-008 | 쿼리 문자열: 빈 값·undefined·null 은 빼고 0·false 는 유지하며 특수문자를 인코딩한다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-008"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | CSRF·Idempotency-Key 부착 규칙 |
| TC-VF-009 | 경로의 영상 ID 는 인코딩되어 다른 경로로 새지 않는다(? # / 포함) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-009"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | CSRF·Idempotency-Key 부착 규칙 |
| TC-VF-010 | 같은 지문은 같은 키, 지문이 바뀌면 새 키, clear 뒤에는 같은 지문이라도 새 키 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-010"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | Idempotency-Key 재사용 규칙 |
| TC-VF-011 | 서로 다른 IdempotencyKeys 인스턴스는 키를 공유하지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-011"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | Idempotency-Key 재사용 규칙 |
| TC-VF-012 | newKey 는 1000번 호출해도 중복이 없다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-012"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | Idempotency-Key 재사용 규칙 |
| TC-VF-013 | crypto.randomUUID 가 없는 환경에서도 32자리 16진수 키를 만든다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-013"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | Idempotency-Key 재사용 규칙 |
| TC-VF-014 | 재시도에서는 새 CSRF 토큰을 쓰되 Idempotency-Key 는 처음과 같다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-014"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 401 재발급 1회와 재시도 |
| TC-VF-015 | 키를 넘기지 않은 위험 호출도 401 재시도에서 처음 만든 키를 그대로 쓴다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-015"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 401 재발급 1회와 재시도 |
| TC-VF-016 | 계속 401 이면 원 요청은 정확히 2번(처음+재시도 1회)만 가고 오류를 던진다(무한 루프 없음) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-016"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 401 재발급 1회와 재시도 |
| TC-VF-017 | GET 이 계속 401 이어도 2번만 보내고 멈춘다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-017"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 401 재발급 1회와 재시도 |
| TC-VF-018 | CSRF 거절(403 csrf_invalid)도 재발급 후 1회만 재시도한다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-018"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 401 재발급 1회와 재시도 |
| TC-VF-019 | CSRF 와 무관한 403(origin_not_allowed 등)은 재발급·재시도를 하지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-019"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 401 재발급 1회와 재시도 |
| TC-VF-020 | 틀린 PIN(401 pin_invalid)은 세션 재발급을 시도하지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-020"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 401 재발급 1회와 재시도 |
| TC-VF-021 | 재발급 중 PIN 이 필요하면 session_expired 로 바꾸고 expired 표시를 켠다(재시도는 하지 않음) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-021"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 401 재발급 1회와 재시도 |
| TC-VF-022 | PIN 을 다시 넣으면 PIN 은 본문으로만 전송되고(URL·헤더 제외) 상태가 online 으로 돌아온다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-022"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 401 재발급 1회와 재시도 |
| TC-VF-023 | problem+json 의 필드가 문자열이 아니어도(숫자·객체·배열) 안전한 기본값으로 바꾼다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-023"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 오류 형태 구분 |
| TC-VF-024 | 오류 본문이 null 이어도 ApiError 로 바뀐다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-024"` | 시나리오 문장의 기대를 모두 충족 | 통과(4건: 표 입력 변형 전부) | Pass | 오류 형태 구분 |
| TC-VF-025 | 프록시가 돌려준 HTML 오류 페이지(502)는 코드 http_502 로만 알리고 HTML 을 화면용 문구에 싣지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-025"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 오류 형태 구분 |
| TC-VF-026 | 200 인데 JSON 이 깨진 응답은 bad_response 로 구분한다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-026"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 오류 형태 구분 |
| TC-VF-027 | 200 빈 본문과 204 는 undefined 로 처리하고 오류로 보지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-027"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 오류 형태 구분 |
| TC-VF-028 | 429 의 Retry-After 는 안내에 넣고, 다른 상태 코드의 Retry-After 는 무시한다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-028"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 오류 형태 구분 |
| TC-VF-029 | 네트워크 오류(fetch 거부)는 status 0 · network_error 로 구분하고 연결 상태를 offline 으로 바꾼다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-029"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 오류 형태 구분 |
| TC-VF-030 | 서버가 오류 응답(500)을 주는 것은 네트워크 끊김이 아니다: 상태는 online 유지 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-030"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 오류 형태 구분 |
| TC-VF-031 | 사용자 취소(AbortError)는 network_error 로 둔갑하지 않고 연결 상태도 바꾸지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-031"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 오류 형태 구분 |
| TC-VF-032 | 응답이 영영 오지 않으면 일정 시간 뒤 연결 끊김 오류로 끝난다(시간 제한) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-032"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | DEF-6-001; 오류 형태 구분 |
| TC-VF-033 | 오류 분류(isLimit): 서버가 실제로 내는 코드 중 한도 계열만 true 다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-033"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 오류 형태 구분 |
| TC-VF-034 | "generate_failed" 같은 한도와 무관한 코드를 한도 초과로 분류하지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-034"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | DEF-6-002; 오류 형태 구분 |
| TC-VF-035 | 로그아웃이 네트워크 때문에 실패하면 loggedout 으로 바꾸지 않고 CSRF 도 유지한다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-035"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 세션 수명 |
| TC-VF-036 | 로그아웃 뒤 상태 변경을 시도하면 먼저 세션을 다시 확인한다(옛 토큰 재사용 금지) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-036"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 세션 수명 |
| TC-VF-037 | CSRF 토큰·PIN 은 localStorage/sessionStorage/document.cookie 에 남지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-037"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 세션 수명 |
| TC-VF-038 | 오류·재시도 경로에서 console 로 토큰·PIN 을 출력하지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-038"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 세션 수명 |
| TC-VF-039 | PIN 이 필요한 서버에서 틀린 PIN 은 pin_required 상태를 유지하고 error 상태로 바뀌지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-039"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 세션 수명 |
| TC-VF-040 | 시작 직후 서버가 꺼져 있으면 offline, 켜진 뒤 bootstrap 하면 online 으로 복구된다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-040"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 세션 수명 |
| TC-VF-041 | 동시에 시작된 bootstrap 호출은 auth/me 를 한 번만 부른다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/client.verify.test.ts -t "TC-VF-041"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 세션 수명 |
| TC-VF-042 | 확인 문구가 정확히 같지 않으면(뒤 공백) 실행 버튼이 꺼져 있고 눌러도 요청이 가지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-042"` | 시나리오 문장의 기대를 모두 충족 | 통과(15건: 표 입력 변형 전부) | Pass | 배치 실행 확인 문구 (F-06, W-009) |
| TC-VF-043 | 정확히 "실행 2건" 을 입력하면 켜지고, 한 번 누르면 문구 그대로 + Idempotency-Key 와 함께 한 번만 전송된다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-043"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 배치 실행 확인 문구 (F-06, W-009) |
| TC-VF-044 | 빠른 더블클릭·연타에도 실행 요청은 한 번만 간다(중복 클릭 방지) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-044"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 배치 실행 확인 문구 (F-06, W-009) |
| TC-VF-045 | 확인 문구 입력칸에서 Enter 를 눌러도 실행되지 않는다(버튼만이 실행 경로) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-045"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 배치 실행 확인 문구 (F-06, W-009) |
| TC-VF-046 | 서버가 준 확인 문구(실행 5건)를 기준으로 하며, 화면의 항목 수(2건)를 임의로 쓰지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-046"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 배치 실행 확인 문구 (F-06, W-009) |
| TC-VF-047 | 일치 안내는 글자(✓/✕)로 나오고, 고쳐 쓰면 다시 꺼진다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-047"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 배치 실행 확인 문구 (F-06, W-009) |
| TC-VF-048 | 서버가 확인 문구 불일치(422/409)를 돌려주면 사유를 보여 주고 버튼은 다시 쓸 수 있다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-048"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 배치 실행 확인 문구 (F-06, W-009) |
| TC-VF-049 | 실행이 실패한 뒤 그대로 다시 눌러 재시도하면 같은 Idempotency-Key 를 쓴다(이중 실행 방지) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-049"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 배치 실행 확인 문구 (F-06, W-009) |
| TC-VF-050 | 반영할 항목이 0건이면 확인 문구 입력칸 자체가 없다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-050"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 배치 실행 확인 문구 (F-06, W-009) |
| TC-VF-051 | 이미 실행 중/끝난 배치에는 실행 입력이 없고, 숫자 id 가 아닌 주소는 "없음" 안내로 간다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-051"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 배치 실행 확인 문구 (F-06, W-009) |
| TC-VF-052 | 영상 ID 가 정확히 같지 않으면(소문자로 바꿈) 롤백 실행이 꺼져 있고 요청이 가지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-052"` | 시나리오 문장의 기대를 모두 충족 | 통과(11건: 표 입력 변형 전부) | Pass | 롤백 영상 ID 직접 입력 (F-06, W-011) |
| TC-VF-053 | ID 가 정확히 같아도 승인자가 비었거나 공백뿐이면 실행할 수 없다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-053"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 롤백 영상 ID 직접 입력 (F-06, W-011) |
| TC-VF-054 | 정상 입력이면 입력한 ID·공백을 다듬은 승인자·멱등키·CSRF 와 함께 한 번 전송된다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-054"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 롤백 영상 ID 직접 입력 (F-06, W-011) |
| TC-VF-055 | 서버가 거절(409 later_change_exists)하면 대화상자를 닫지 않고 사유를 보여 준다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-055"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 롤백 영상 ID 직접 입력 (F-06, W-011) |
| TC-VF-056 | 실패 후 같은 입력으로 재시도하면 같은 멱등키, 승인자 이름을 바꾸면 새 키를 쓴다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-056"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 롤백 영상 ID 직접 입력 (F-06, W-011) |
| TC-VF-057 | 더블클릭해도 롤백 요청은 한 번이고, 처리 중에는 Esc 로 닫히지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-057"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 롤백 영상 ID 직접 입력 (F-06, W-011) |
| TC-VF-058 | Esc 로 닫으면 롤백 버튼으로 포커스가 돌아가고, 다시 열면 이전에 입력한 ID 가 비어 있다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-058"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 롤백 영상 ID 직접 입력 (F-06, W-011) |
| TC-VF-059 | 되돌릴 수 없는 항목(rollbackable=false)에는 롤백 버튼이 없다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-059"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 롤백 영상 ID 직접 입력 (F-06, W-011) |
| TC-VF-060 | 차단 판정 제안은 상태가 검토 대기 여도 승인 버튼이 꺼져 있고 눌러도 대화상자·요청이 없다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-060"` | 시나리오 문장의 기대를 모두 충족 | 통과(2건: 표 입력 변형 전부) | Pass | 승인 규칙 (W-005, W-007) |
| TC-VF-061 | 경고 제안: 사유 확인 체크 전에는 승인할 수 없고(버튼·Enter 모두), 체크를 풀면 다시 막힌다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-061"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 승인 규칙 (W-005, W-007) |
| TC-VF-062 | 경고 제안도 확인·승인자 입력 뒤에는 승인되고, 승인자 이름은 공백을 다듬어 보낸다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-062"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 승인 규칙 (W-005, W-007) |
| TC-VF-063 | 통과 제안이라도 승인자가 비었거나 공백뿐이면 승인할 수 없다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-063"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 승인 규칙 (W-005, W-007) |
| TC-VF-064 | 이미 승인/반려된 제안에는 알맞은 버튼만 보인다(승인됨: 승인 없음·반려 있음, 반려됨: 둘 다 없음) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-064"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 승인 규칙 (W-005, W-007) |
| TC-VF-065 | 반려: 확인 대화상자에서 취소하면 요청이 없고, 확인해야만 전송된다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-065"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 승인 규칙 (W-005, W-007) |
| TC-VF-066 | 서버가 승인을 409 suggestion_blocked 로 거절해도 화면이 깨지지 않고 사유를 보여 준다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-066"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 승인 규칙 (W-005, W-007) |
| TC-VF-067 | 제목 길이/내용 경계: 100자(경계 안) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-067"` | 시나리오 문장의 기대를 모두 충족 | 통과(7건: 표 입력 변형 전부) | Pass | 제목 수정 경계값 (100자) |
| TC-VF-068 | 저장하면 공백을 다듬은 제목을 PATCH 로 보낸다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/confirm.verify.test.tsx -t "TC-VF-068"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 제목 수정 경계값 (100자) |
| TC-VF-069 | 안전 설정 탭의 입력 요소는 하루 상한·영상당 제안 수·말투 3개뿐이고 체크박스·스위치·라디오가 없다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/settings.verify.test.tsx -t "TC-VF-069"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 설정: 라이브 허용은 편집 불가 (W-014, 요청서 설정 화면) |
| TC-VF-070 | 서버가 enable_live=true 를 주어도 켜짐은 글자(▲ 기호 포함)로만 보이고 조작 버튼이 없다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/settings.verify.test.tsx -t "TC-VF-070"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 설정: 라이브 허용은 편집 불가 (W-014, 요청서 설정 화면) |
| TC-VF-071 | 저장 요청 본문에는 허용된 키(daily_apply_cap·suggestions_per_video·tone)만 들어가고 라이브 관련 키가 없다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/settings.verify.test.tsx -t "TC-VF-071"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 설정: 라이브 허용은 편집 불가 (W-014, 요청서 설정 화면) |
| TC-VF-072 | 서버가 setting_not_allowed(403/422)로 거절하면 사유를 보여 주고 화면 값이 서버 값을 가장하지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/settings.verify.test.tsx -t "TC-VF-072"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 설정: 라이브 허용은 편집 불가 (W-014, 요청서 설정 화면) |
| TC-VF-073 | 하루 반영 상한 입력 "0" → 저장 가능 여부 false | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/settings.verify.test.tsx -t "TC-VF-073"` | 시나리오 문장의 기대를 모두 충족 | 통과(11건: 표 입력 변형 전부) | Pass | 설정: 값 범위 경계 (하루 상한 1~20, 영상당 제안 1~5, 말투 5개·20자) |
| TC-VF-074 | 영상당 제안 수 입력 "0" → 저장 가능 여부 false | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/settings.verify.test.tsx -t "TC-VF-074"` | 시나리오 문장의 기대를 모두 충족 | 통과(6건: 표 입력 변형 전부) | Pass | 설정: 값 범위 경계 (하루 상한 1~20, 영상당 제안 1~5, 말투 5개·20자) |
| TC-VF-075 | 값이 바뀌지 않았으면 저장 버튼이 꺼져 있고, 바꿨다 되돌려도 꺼진다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/settings.verify.test.tsx -t "TC-VF-075"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 설정: 값 범위 경계 (하루 상한 1~20, 영상당 제안 1~5, 말투 5개·20자) |
| TC-VF-076 | 말투 목록 경계: 5개(경계 안) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/settings.verify.test.tsx -t "TC-VF-076"` | 시나리오 문장의 기대를 모두 충족 | 통과(7건: 표 입력 변형 전부) | Pass | 설정: 값 범위 경계 (하루 상한 1~20, 영상당 제안 1~5, 말투 5개·20자) |
| TC-VF-077 | 사용자가 말투 3개(각 15자, 쉼표 포함 약 49자)를 직접 입력하면 잘리지 않고 그대로 저장된다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/settings.verify.test.tsx -t "TC-VF-077"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | DEF-6-003; 설정: 값 범위 경계 (하루 상한 1~20, 영상당 제안 1~5, 말투 5개·20자) |
| TC-VF-078 | 새 PIN 형식(3자리) → 설정 가능 여부 123 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/settings.verify.test.tsx -t "TC-VF-078"` | 시나리오 문장의 기대를 모두 충족 | 통과(10건: 표 입력 변형 전부) | Pass | 설정: PIN 규칙 (S-W02 보조) |
| TC-VF-079 | 재입력이 다르면 설정할 수 없고 불일치 안내가 나온다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/settings.verify.test.tsx -t "TC-VF-079"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 설정: PIN 규칙 (S-W02 보조) |
| TC-VF-080 | PIN 입력칸은 모두 password 형식이며, 저장 뒤 입력칸이 비워지고 PIN 이 화면 텍스트에 남지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/settings.verify.test.tsx -t "TC-VF-080"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 설정: PIN 규칙 (S-W02 보조) |
| TC-VF-081 | PIN 이 이미 있으면 현재 PIN 없이는 변경할 수 없고, 변경 본문에 current_pin 이 포함된다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/settings.verify.test.tsx -t "TC-VF-081"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 설정: PIN 규칙 (S-W02 보조) |
| TC-VF-082 | PIN 해제는 확인 대화상자의 현재 PIN 입력 전까지 실행할 수 없고, 취소하면 요청이 없다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/settings.verify.test.tsx -t "TC-VF-082"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 설정: PIN 규칙 (S-W02 보조) |
| TC-VF-083 | 틀린 현재 PIN(401 pin_invalid)은 대화상자 안에 안내하고 세션 재발급·만료 창을 띄우지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/settings.verify.test.tsx -t "TC-VF-083"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 설정: PIN 규칙 (S-W02 보조) |
| TC-VF-084 | 필터(진행 상태)를 바꿔도 선택은 유지되고, 필터를 풀면 같은 체크가 보인다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lists.verify.test.tsx -t "TC-VF-084"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 영상 목록: 선택 상태 유지·초기화 규칙 (F-03) |
| TC-VF-085 | 쪽 크기를 바꿔도 선택은 유지된다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lists.verify.test.tsx -t "TC-VF-085"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 영상 목록: 선택 상태 유지·초기화 규칙 (F-03) |
| TC-VF-086 | "선택 해제" 는 다른 쪽에서 고른 것까지 모두 지우고 선택 바가 사라진다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lists.verify.test.tsx -t "TC-VF-086"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 영상 목록: 선택 상태 유지·초기화 규칙 (F-03) |
| TC-VF-087 | 같은 영상을 두 번 누르면 선택이 풀리고, 전체 선택 체크박스는 일부 선택이면 중간 상태, 전부면 체크 상태다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lists.verify.test.tsx -t "TC-VF-087"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 영상 목록: 선택 상태 유지·초기화 규칙 (F-03) |
| TC-VF-088 | 이 페이지 전체 선택을 풀면 이 페이지 것만 풀리고 다른 쪽에서 고른 것은 남는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lists.verify.test.tsx -t "TC-VF-088"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 영상 목록: 선택 상태 유지·초기화 규칙 (F-03) |
| TC-VF-089 | 모두 제외된 쪽에서는 전체 선택 체크박스가 꺼져 있다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lists.verify.test.tsx -t "TC-VF-089"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 영상 목록: 선택 상태 유지·초기화 규칙 (F-03) |
| TC-VF-090 | AI 제안 생성은 여러 쪽에서 고른 영상 ID 를 한 번의 요청으로, CSRF 와 함께 보낸다(멱등키 없음) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lists.verify.test.tsx -t "TC-VF-090"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 영상 목록: 선택 상태 유지·초기화 규칙 (F-03) |
| TC-VF-091 | /videos?page=-1 → 서버로 가는 쿼리가 안전한 값으로 바뀐다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lists.verify.test.tsx -t "TC-VF-091"` | 시나리오 문장의 기대를 모두 충족 | 통과(11건: 표 입력 변형 전부) | Pass | 영상 목록: 주소(URL) 쿼리 방어 |
| TC-VF-092 | 검색어에 HTML 이 있어도 입력칸의 글자로만 보이고 요소가 만들어지지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lists.verify.test.tsx -t "TC-VF-092"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 영상 목록: 주소(URL) 쿼리 방어 |
| TC-VF-093 | 작업이 성공으로 끝나면 닫기가 켜지고, 닫으면 선택이 초기화된다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lists.verify.test.tsx -t "TC-VF-093"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | AI 제안 생성 작업 창 |
| TC-VF-094 | [관찰 OBS-1] 작업이 실패로 끝나면 오류를 보여 주고, 닫으면 선택도 초기화된다(현재 동작 기록) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lists.verify.test.tsx -t "TC-VF-094"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | AI 제안 생성 작업 창 |
| TC-VF-095 | 작업 상태를 읽지 못해(404) 오류가 보이면 사용자가 창을 닫을 수 있다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lists.verify.test.tsx -t "TC-VF-095"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | DEF-6-004; AI 제안 생성 작업 창 |
| TC-VF-096 | 영상 상세: 제목·설명·제외 사유·제안 제목·근거·사유·승인자·주제·한도 사유가 모두 글자로만 보인다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lists.verify.test.tsx -t "TC-VF-096"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 외부 문자열 렌더링 (F-05, S-W05) |
| TC-VF-097 | 영상 목록: 제목과 영상 ID 에 스크립트·javascript: 가 있어도 링크 주소가 안전하다(HashRouter 실제 주소 형식 포함) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lists.verify.test.tsx -t "TC-VF-097"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 외부 문자열 렌더링 (F-05, S-W05) |
| TC-VF-098 | 이력 화면: 영상 제목·이전/새 제목·승인자·오류 코드가 글자로만 보인다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lists.verify.test.tsx -t "TC-VF-098"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 외부 문자열 렌더링 (F-05, S-W05) |
| TC-VF-099 | 배치 상세: 메모·항목 제목·건너뜀 사유·점검 경고/차단 사유가 글자로만 보인다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lists.verify.test.tsx -t "TC-VF-099"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 외부 문자열 렌더링 (F-05, S-W05) |
| TC-VF-100 | 감사 로그: 행위자·동작·대상이 글자로만 보인다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lists.verify.test.tsx -t "TC-VF-100"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 외부 문자열 렌더링 (F-05, S-W05) |
| TC-VF-101 | 성과 리포트: 서버 notes·사유·제목이 글자로만 보인다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lists.verify.test.tsx -t "TC-VF-101"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 외부 문자열 렌더링 (F-05, S-W05) |
| TC-VF-102 | 서버 오류 메시지(title/detail/hint)에 HTML 이 있어도 화면에는 글자로만 나온다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lists.verify.test.tsx -t "TC-VF-102"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 외부 문자열 렌더링 (F-05, S-W05) |
| TC-VF-103 | 영상 상세 응답에 suggestions 가 빠져도 메뉴·안내는 남는다(빈 화면 금지) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lists.verify.test.tsx -t "TC-VF-103"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | DEF-6-005; 잘못된 서버 응답에 대한 견고성 |
| TC-VF-104 | 목록 응답의 items 가 null 이거나 항목 일부 필드가 null 이어도 표가 그려진다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lists.verify.test.tsx -t "TC-VF-104"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 잘못된 서버 응답에 대한 견고성 |
| TC-VF-105 | 알 수 없는 상태 값(진행 상태·검증 결과·제안 상태·주제)이 와도 원문을 보여 주고 깨지지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lists.verify.test.tsx -t "TC-VF-105"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 잘못된 서버 응답에 대한 견고성 |
| TC-VF-106 | 객체 프로토타입 이름(constructor·toString)이 상태 값으로 와도 함수 원문이 화면에 찍히지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lists.verify.test.tsx -t "TC-VF-106"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 잘못된 서버 응답에 대한 견고성 |
| TC-VF-107 | 빈 문자열 경계: 둘 다 비면 빈 결과, 한쪽만 비면 전부 추가/삭제 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lib.verify.test.tsx -t "TC-VF-107"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 제목 비교 diffTitles (W-006) |
| TC-VF-108 | 같은 제목은 변경 없음(same 한 덩어리)이고, 공백만 다른 제목은 공백 조각으로 구분된다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lib.verify.test.tsx -t "TC-VF-108"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 제목 비교 diffTitles (W-006) |
| TC-VF-109 | 공백뿐인 입력도 잃어버리지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lib.verify.test.tsx -t "TC-VF-109"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 제목 비교 diffTitles (W-006) |
| TC-VF-110 | 특수 문자(이모지)를 쪼개지 않고, 전/후 제목을 정확히 복원한다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lib.verify.test.tsx -t "TC-VF-110"` | 시나리오 문장의 기대를 모두 충족 | 통과(7건: 표 입력 변형 전부) | Pass | 제목 비교 diffTitles (W-006) |
| TC-VF-111 | 무작위 400쌍(시드 고정)에서 복원 가능·빈 조각 없음·인접 같은 종류 없음·최적(LCS 길이 일치)을 만족한다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lib.verify.test.tsx -t "TC-VF-111"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 제목 비교 diffTitles (W-006) |
| TC-VF-112 | 긴 제목(600 단어 대 600 단어, 유튜브 제목 한도 100자의 수십 배)도 3초 안에 끝나고 복원이 정확하다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lib.verify.test.tsx -t "TC-VF-112"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 제목 비교 diffTitles (W-006) |
| TC-VF-113 | 단어 하나가 아주 긴 제목(10만 자, 공백 없음)도 즉시 처리된다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lib.verify.test.tsx -t "TC-VF-113"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 제목 비교 diffTitles (W-006) |
| TC-VF-114 | 글자 수는 코드포인트 기준이고 서버 문자열의 HTML 은 요소가 되지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lib.verify.test.tsx -t "TC-VF-114"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | TitleDiff 컴포넌트 |
| TC-VF-115 | 삭제는 "전" 쪽에만, 추가는 "후" 쪽에만 나오고 각각 스크린리더용 문구가 붙는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lib.verify.test.tsx -t "TC-VF-115"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | TitleDiff 컴포넌트 |
| TC-VF-116 | 빈 제목끼리도 오류 없이 그려진다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lib.verify.test.tsx -t "TC-VF-116"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | TitleDiff 컴포넌트 |
| TC-VF-117 | pass 는 "통과" 글자와 기호 ✓, 색 계열 success 로 표시된다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lib.verify.test.tsx -t "TC-VF-117"` | 시나리오 문장의 기대를 모두 충족 | 통과(3건: 표 입력 변형 전부) | Pass | 검증 배지 매핑 (W-005) |
| TC-VF-118 | 세 판정은 서로 다른 글자·기호·색 계열을 가진다(색만으로 구분하지 않음) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lib.verify.test.tsx -t "TC-VF-118"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 검증 배지 매핑 (W-005) |
| TC-VF-119 | 판정이 null 이면 "검증 전" 같은 중립 표시로 바뀌고 통과로 오인되지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lib.verify.test.tsx -t "TC-VF-119"` | 시나리오 문장의 기대를 모두 충족 | 통과(5건: 표 입력 변형 전부) | Pass | 검증 배지 매핑 (W-005) |
| TC-VF-120 | 시각은 한국 시간으로 보이고 자정 경계(UTC 15:00 → KST 다음 날 00:00)를 정확히 넘긴다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lib.verify.test.tsx -t "TC-VF-120"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 서식·상태 판별 유틸 |
| TC-VF-121 | 날짜만 있는 값(YYYY-MM-DD)은 시간대 변환 없이 그대로, 시각이 있는 값은 한국 날짜로 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lib.verify.test.tsx -t "TC-VF-121"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 서식·상태 판별 유틸 |
| TC-VF-122 | 길이·숫자·퍼센트 경계값 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lib.verify.test.tsx -t "TC-VF-122"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 서식·상태 판별 유틸 |
| TC-VF-123 | 배치/작업 상태 판별: 끝난 상태에서는 폴링 대상이 아니고 모르는 상태는 진행 중으로 본다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lib.verify.test.tsx -t "TC-VF-123"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 서식·상태 판별 유틸 |
| TC-VF-124 | 렌더 확인: ValidationBadge 가 화면 접근성 트리에 글자로 잡힌다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/lib.verify.test.tsx -t "TC-VF-124"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 서식·상태 판별 유틸 |
| TC-VF-125 | 홈 에 접근성 위반이 없다(랜드마크·제목·이름 없는 버튼·라벨·aria 포함) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-125"` | 시나리오 문장의 기대를 모두 충족 | 통과(13건: 표 입력 변형 전부) | Pass | 접근성: 화면 전체(axe, 색 대비 제외) |
| TC-VF-126 | 지난 배치 구역과 변경 이력 구역에서 같은 이름의 랜드마크가 중복되지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-126"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | DEF-6-006; 접근성: 중복 랜드마크 (DEF-6-006) |
| TC-VF-127 | 경고 제안 승인 대화상자: 이름·aria-modal·위반 없음, 처음 포커스는 승인자 입력칸 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-127"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 접근성: 대화상자·오버레이 |
| TC-VF-128 | 반려·수정 대화상자에도 접근성 위반이 없다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-128"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 접근성: 대화상자·오버레이 |
| TC-VF-129 | 대화상자에서 Tab 을 계속 눌러도 포커스가 대화상자 밖으로 나가지 않고(앞으로·뒤로), 뒷배경은 inert 이다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-129"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 접근성: 대화상자·오버레이 |
| TC-VF-130 | Esc 로 닫으면 열었던 버튼으로 포커스가 돌아오고 뒷배경 inert 가 풀린다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-130"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 접근성: 대화상자·오버레이 |
| TC-VF-131 | 롤백 대화상자·진행 중 배치 중지 대화상자에도 위반이 없다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-131"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 접근성: 대화상자·오버레이 |
| TC-VF-132 | 진행 중 배치의 중지 대화상자: 위반 없음, 취소하면 요청이 없다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-132"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 접근성: 대화상자·오버레이 |
| TC-VF-133 | PIN 해제 대화상자와 AI 제안 생성 작업 창에도 위반이 없다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-133"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 접근성: 대화상자·오버레이 |
| TC-VF-134 | 세션 만료 오버레이: Esc 로 닫을 수 없고 포커스는 PIN 입력칸에 있으며 위반이 없다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-134"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 접근성: 대화상자·오버레이 |
| TC-VF-135 | PIN 화면: 입력칸에 이름이 있고 자동 포커스, 틀린 PIN 안내가 role=alert 가 아니어도 글자로 보이며 위반이 없다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-135"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 접근성: 시작·끊김 화면 |
| TC-VF-136 | 시작부터 서버 연결 끊김 화면, 로그아웃 화면에도 위반이 없다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-136"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 접근성: 시작·끊김 화면 |
| TC-VF-137 | 사용 중 서버 연결이 끊기면 경고 배너(role=alert)와 "서버 연결 끊김" 상태가 나오고 다시 연결하면 사라진다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-137"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 접근성: 시작·끊김 화면 |
| TC-VF-138 | 첫 Tab 은 "본문으로 건너뛰기", 이어서 메뉴 6개 순서(홈→영상→배치→이력→리포트→설정) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-138"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 키보드 이동·포커스 |
| TC-VF-139 | 건너뛰기 링크를 Enter 로 누르면 본문(main)으로 포커스가 간다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-139"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 키보드 이동·포커스 |
| TC-VF-140 | 메뉴에서 다른 화면으로 가면 새 화면 제목(h1)으로 포커스가 이동한다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-140"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 키보드 이동·포커스 |
| TC-VF-141 | 현재 화면 메뉴에 aria-current 가 붙는다(색에만 의존하지 않음) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-141"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 키보드 이동·포커스 |
| TC-VF-142 | 설정 탭: 방향키 좌우·Home·End 로 이동하고 선택 탭만 tabIndex 0 이다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-142"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 키보드 이동·포커스 |
| TC-VF-143 | 영상 목록의 정렬 머리글은 버튼이고 aria-sort 가 바뀐다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-143"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 키보드 이동·포커스 |
| TC-VF-144 | 모든 입력칸·선택칸·체크박스에 접근 가능한 이름이 있다(영상 목록·설정·이력) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-144"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 키보드 이동·포커스 |
| TC-VF-145 | 진행률 표시는 progress 요소에 이름·값이 있고 숫자 글자도 함께 나온다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-145"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 키보드 이동·포커스 |
| TC-VF-146 | 홈: 서버가 500 이면 오류 안내(다음에 할 일·오류 코드·다시 시도)를 보이고, 다시 시도하면 복구된다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-146"` | 시나리오 문장의 기대를 모두 충족 | 통과(9건: 표 입력 변형 전부) | Pass | 상태 화면: 로딩·빈·오류·한도 (F-07) |
| TC-VF-147 | 한도 초과(429 quota_exhausted)는 "한도" 제목의 경고로 구분해 보여 준다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-147"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 상태 화면: 로딩·빈·오류·한도 (F-07) |
| TC-VF-148 | 로딩 중에는 role=status 의 불러오는 표시가 보이고 끝나면 사라진다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-148"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 상태 화면: 로딩·빈·오류·한도 (F-07) |
| TC-VF-149 | 빈 상태(영상 목록): 안내 문구가 보이고 접근성 위반이 없다(읽기 전용 로그를 뺀 화면은 다음 행동도 있다) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-149"` | 시나리오 문장의 기대를 모두 충족 | 통과(5건: 표 입력 변형 전부) | Pass | 상태 화면: 로딩·빈·오류·한도 (F-07) |
| TC-VF-150 | 성과 리포트: 데이터 부족 상태에서도 서버가 준 "원인 단정 금지" 문구가 맨 위에 보인다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/a11y-states.verify.test.tsx -t "TC-VF-150"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 상태 화면: 로딩·빈·오류·한도 (F-07) |
| TC-VF-151 | 화면은 서버가 준 행만 그린다(클라이언트가 자르거나 다시 정렬하지 않음) — 총 7건 중 2건이 와도 2행, 총계는 서버 값 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-151"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 영상 목록: 서버측 질의 (F-03) |
| TC-VF-152 | 정렬 머리글 클릭은 서버에 sort/order 를 보내고(제목 오름 → 내림), 다른 키는 오름으로 시작하며 page 는 1로 돌아간다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-152"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 영상 목록: 서버측 질의 (F-03) |
| TC-VF-153 | 진행 상태·제외 필터·검색어는 서버 질의로 가고 URL 에 남으며, 필터 변경은 1쪽으로 돌린다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-153"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 영상 목록: 서버측 질의 (F-03) |
| TC-VF-154 | 쪽 이동은 page 를 서버에 보내고, 첫 쪽에서는 이전 버튼이, 마지막 쪽에서는 다음 버튼이 꺼진다(경계) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-154"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 영상 목록: 서버측 질의 (F-03) |
| TC-VF-155 | 쪽 크기를 바꾸면 page_size 가 서버로 가고 page 는 1로 돌아간다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-155"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 영상 목록: 서버측 질의 (F-03) |
| TC-VF-156 | 쪽 크기 200(노트가 지원한다고 적은 값)이 선택 목록에서 실제 값으로 보인다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-156"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | DEF-6-007; 영상 목록: 서버측 질의 (F-03) |
| TC-VF-157 | 제외된 영상은 체크박스가 꺼져 있고 사유가 보이며, 전체 선택으로도 선택되지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-157"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 영상 목록: 서버측 질의 (F-03) |
| TC-VF-158 | 필터 결과가 0건이면 "필터 지우기" 안내가, 필터 없이 0건이면 첫 사용 안내가 나온다(빈 상태 구분) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-158"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 영상 목록: 서버측 질의 (F-03) |
| TC-VF-159 | 제안 생성: 선택한 ID 로 POST suggestions/generate 를 한 번 보내고, 연타해도 한 번이다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-159"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 영상 목록: 서버측 질의 (F-03) |
| TC-VF-160 | 영상 0개면 "데모 영상 불러오기" 가 할 일이고, 누르면 CSRF 와 함께 POST videos/sync 를 한 번 보낸다(응답 대기 중 연타 포함) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-160"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 홈 화면 |
| TC-VF-161 | 남은 사용량 경계: 79%(경고 없음) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-161"` | 시나리오 문장의 기대를 모두 충족 | 통과(4건: 표 입력 변형 전부) | Pass | 홈 화면 |
| TC-VF-162 | 영상 현황 숫자는 해당 필터가 걸린 영상 목록 링크이고, 할 일은 건수에 맞게 나온다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-162"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 홈 화면 |
| TC-VF-163 | 진행 중 작업이 있으면 안내가 나오고 2초마다 대시보드를 다시 읽는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-163"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 홈 화면 |
| TC-VF-164 | / 상단에 "데모 모드" 배지가 항상 보이고, 화면 어디에도 dry-run 영문 용어가 없다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-164"` | 시나리오 문장의 기대를 모두 충족 | 통과(9건: 표 입력 변형 전부) | Pass | 데모 모드 표시와 용어 |
| TC-VF-165 | 배치 초안의 사전 점검 제목은 "미리보기" 로 표기되고 "아직 아무것도 반영되지 않았습니다" 안내가 있다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-165"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 데모 모드 표시와 용어 |
| TC-VF-166 | 문구 한곳 관리: 소스의 화면 문구에 dry-run 영문이 없다(ko.ts 전체) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-166"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 데모 모드 표시와 용어 |
| TC-VF-167 | 승인 항목 49건을 전체 선택하면 초안 만들기 비활성=false (상한 50 경계), 51건이면 하나 빼면 켜진다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-167"` | 시나리오 문장의 기대를 모두 충족 | 통과(3건: 표 입력 변형 전부) | Pass | 배치 만들기 화면 |
| TC-VF-168 | 아무것도 고르지 않으면 초안 만들기가 꺼져 있다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-168"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 배치 만들기 화면 |
| TC-VF-169 | 초안 만들기: 정렬된 suggestion_ids·메모를 CSRF+Idempotency-Key 와 함께 한 번만 보내고 초안 화면으로 이동한다(더블클릭 포함) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-169"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 배치 만들기 화면 |
| TC-VF-170 | 초안 만들기가 거절되면(422) 오류를 보여 주고, 같은 선택으로 다시 눌러도 같은 Idempotency-Key 를 쓴다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-170"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 배치 만들기 화면 |
| TC-VF-171 | 실행 중인 배치는 서버 상태를 2초마다 읽어 진행률을 갱신하고, 끝나면 폴링을 멈추고 이력 링크를 보인다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-171"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 배치 진행 화면 |
| TC-VF-172 | 중지는 확인 대화상자를 거치고, 확인해야만 CSRF 와 함께 POST cancel 이 한 번 간다(더블클릭 포함) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-172"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 배치 진행 화면 |
| TC-VF-173 | 사전 점검 표: 항목 수·예상 사용량·하루 상한·남은 한도·날짜별 일정·경고·제외 항목을 모두 보여 준다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-173"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 배치 진행 화면 |
| TC-VF-174 | 영상 ID·결과 필터는 서버 질의로 가며(앞뒤 공백 제거), 필터를 걸면 1쪽으로 돌아간다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-174"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 이력 화면 |
| TC-VF-175 | CSV 내보내기는 GET export.csv(토큰·멱등키 없음)를 부르고 blob 앵커 다운로드로 저장한다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-175"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 성과 리포트 CSV 내보내기 |
| TC-VF-176 | CSV 내보내기가 실패하면(500) 오류 안내가 나오고 다운로드는 일어나지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-176"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 성과 리포트 CSV 내보내기 |
| TC-VF-177 | 내보내기 중에는 버튼이 비활성이라 연타해도 요청이 한 번이다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-177"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 성과 리포트 CSV 내보내기 |
| TC-VF-178 | 리포트 영상 필터는 video_id 질의로 가고, 서버 notes 가 비면 기본 안내가 맨 위에 나온다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-178"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 성과 리포트 CSV 내보내기 |
| TC-VF-179 | 불러오기 작업이 진행 중이면 같은 버튼으로 작업을 또 시작할 수 없다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-179"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | DEF-6-008; 홈 화면 |
| TC-VF-180 | 필터 없이 0건이면 "첫 사용" 안내(홈으로 가기)가 나오고 필터 지우기는 없다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-180"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 영상 목록: 서버측 질의 (F-03) |
| TC-VF-181 | 승인된 제안이 없으면 빈 상태 안내(영상 목록으로 가는 다음 행동)가 나온다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-181"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 배치 만들기 화면 |
| TC-VF-182 | 배치 상태 "queued" 가 영문 원문이 아닌 한국어로 표시된다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-182"` | 시나리오 문장의 기대를 모두 충족 | 통과(2건: 표 입력 변형 전부) | Pass | DEF-6-010; 서버 상태 값의 한국어 표기 |
| TC-VF-183 | 홈의 "진행 중인 작업" 이 서버 작업 종류 코드(videos.sync 등)를 한국어로 바꿔 보여 준다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-183"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | DEF-6-011; 서버 상태 값의 한국어 표기 |
| TC-VF-184 | "AI 제안 만들기" 는 POST videos/{id}/suggestions 를 CSRF 와 함께 한 번 보내고(연타 포함), 성공하면 안내가 나온다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-184"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 영상 상세·리포트·시작 화면 보강 |
| TC-VF-185 | 제외된 영상은 "AI 제안 만들기"·승인·수정·반려가 모두 꺼지고 제외 사유가 보인다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-185"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 영상 상세·리포트·시작 화면 보강 |
| TC-VF-186 | 변경 한도에 걸린 영상은 사유와 다시 바꿀 수 있는 시각(한국 시간)을 보여 준다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-186"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 영상 상세·리포트·시작 화면 보강 |
| TC-VF-187 | 리포트 비교 표: 지표 값·차이 부호·CTR 퍼센트·빈 값("-")·집계 기간이 정확히 표시된다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-187"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 영상 상세·리포트·시작 화면 보강 |
| TC-VF-188 | 리포트 "변경 기록 없음"·"데이터 부족(기준 자료 없음+수집 예정일)" 상태가 각각 구분되어 보인다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-188"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 영상 상세·리포트·시작 화면 보강 |
| TC-VF-189 | 세션 시작이 서버 오류(500)로 실패하면 "시작하지 못했습니다" 화면과 다시 연결 버튼이 나오고, 복구되면 홈으로 들어간다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/screens.verify.test.tsx -t "TC-VF-189"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 영상 상세·리포트·시작 화면 보강 |
| TC-VF-190 | 엄격 모드 + 경고: 승인 버튼이 꺼져 있고 "차단" 으로 표시되며 사유 문구가 연결된다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-190"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | DEF-VF-001; 승인 규칙: 엄격 모드(strict) — 서버 is_blocked 와 동일 |
| TC-VF-191 | 엄격 모드 + 통과: 승인할 수 있다(과차단 방지) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-191"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 승인 규칙: 엄격 모드(strict) — 서버 is_blocked 와 동일 |
| TC-VF-192 | 엄격 모드 + 검증 전(null): 통과가 아니므로 승인할 수 없다(fail-closed) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-192"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 승인 규칙: 엄격 모드(strict) — 서버 is_blocked 와 동일 |
| TC-VF-193 | 비엄격 + 경고: 기존대로 승인할 수 있고 경고 확인 체크가 있어야 대화상자의 승인이 켜진다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-193"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 승인 규칙: 엄격 모드(strict) — 서버 is_blocked 와 동일 |
| TC-VF-194 | 제한 시간 직전(29.999초)에는 기다리고 정확히 30초에 연결 끊김 오류로 끝나며 요청 신호를 중단한다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-194"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | DEF-6-001; API 클라이언트: 시간 제한 |
| TC-VF-195 | 정상 응답이 오면 제한 시간 타이머를 남기지 않는다(누수 없음) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-195"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | API 클라이언트: 시간 제한 |
| TC-VF-196 | 오류 응답(500)에서도 타이머를 남기지 않고, 호출자가 낸 중단 신호는 그대로 AbortError 로 전달된다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-196"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | API 클라이언트: 시간 제한 |
| TC-VF-197 | 이미 중단된 신호를 넘기면 요청 신호도 곧바로 중단 상태로 전달된다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-197"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | API 클라이언트: 시간 제한 |
| TC-VF-198 | 한도 계열: rate_limited → true | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-198"` | 시나리오 문장의 기대를 모두 충족 | 통과(6건: 표 입력 변형 전부) | Pass | API 클라이언트: 한도 계열 판별(isLimit) 경계 |
| TC-VF-199 | 한도와 무관: generate_failed → false | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-199"` | 시나리오 문장의 기대를 모두 충족 | 통과(7건: 표 입력 변형 전부) | Pass | API 클라이언트: 한도 계열 판별(isLimit) 경계 |
| TC-VF-200 | 상태 429 는 코드와 무관하게 한도 계열이다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-200"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | API 클라이언트: 한도 계열 판별(isLimit) 경계 |
| TC-VF-201 | "constructor" 는 라벨로 오인되지 않고 원문 그대로 보인다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-201"` | 시나리오 문장의 기대를 모두 충족 | 통과(4건: 표 입력 변형 전부) | Pass | 라벨 조회: 서버 값이 객체 기본 속성 이름이어도 안전 |
| TC-VF-202 | 알려진 값은 한국어로, 빈 값은 "-" 로 보인다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-202"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 라벨 조회: 서버 값이 객체 기본 속성 이름이어도 안전 |
| TC-VF-203 | 2026-10-10T15:00:00Z → 2026-10-11 00:00 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-203"` | 시나리오 문장의 기대를 모두 충족 | 통과(4건: 표 입력 변형 전부) | Pass | 시각 표시: 24시 표기 금지 |
| TC-VF-204 | 목록에 없는 값(30, 200)도 실제 값으로 보이고 정렬되어 들어간다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-204"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | DEF-6-007; 쪽 크기 선택 |
| TC-VF-205 | 목록에 있는 값이면 항목이 늘지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-205"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 쪽 크기 선택 |
| TC-VF-206 | 한 화면이 깨져도 메뉴는 남고, 다른 메뉴로 이동하면 정상 화면이 다시 그려진다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-206"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | DEF-6-005; 화면 오류 경계 |
| TC-VF-207 | 홈: 불러오기 작업 조회가 404 면 오류가 보이고 "데모 영상 불러오기" 가 다시 켜진다(영구 잠금 방지) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-207"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | DEF-6-008; 작업 상태를 읽지 못할 때 |
| TC-VF-208 | 홈: 작업이 실패(failed)로 끝나도 버튼이 다시 켜진다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-208"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 작업 상태를 읽지 못할 때 |
| TC-VF-209 | 5개 × 20자(쉼표 포함 108자)를 붙여 넣어도 잘리지 않고 저장 요청이 그대로 나간다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-209"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | DEF-6-003; 설정: 말투 5개 × 20자 경계 |
| TC-VF-210 | 21자 말투와 6번째 말투는 저장할 수 없다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-210"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 설정: 말투 5개 × 20자 경계 |
| TC-VF-211 | 고른 뒤 한 항목이 승인 목록에서 사라지면(만료 등) 남은 항목만 요청하고 선택 수도 맞다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-211"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 배치 만들기: 목록에서 사라진 선택 항목 |
| TC-VF-212 | 정확히 200개까지는 생성 버튼이 켜져 있고, 201개가 되면 꺼지며 안내가 보이고 요청이 나가지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-212"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | AI 제안 생성: 선택 상한 200 |
| TC-VF-213 | 200개 선택 후 생성하면 영상 ID 200개가 CSRF 와 함께 한 번 전송된다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-213"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | AI 제안 생성: 선택 상한 200 |
| TC-VF-214 | 설정 > 세션 탭: 로그아웃이 서버에 닿지 못하면 오류 토스트가 보이고 화면은 그대로다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-214"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 기타 상태 화면 |
| TC-VF-215 | 홈: 반영 대기(queued) 건수가 있으면 배치 화면으로 가는 안내가 보인다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-215"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 기타 상태 화면 |
| TC-VF-216 | 오류 경계 화면에는 "다음에 할 일" 과 새로고침 버튼이 있다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-216"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 기타 상태 화면 |
| TC-VF-217 | 처음 두 번은 404, 세 번째에 200 이면 오류 화면 없이 진행률이 보인다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-217"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 작업 조회 404 재확인 |
| TC-VF-218 | 계속 404 면 첫 요청 포함 정확히 4번(재확인 3번) 뒤에 오류가 보이고 더는 재확인하지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-218"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 작업 조회 404 재확인 |
| TC-VF-219 | 404 가 아닌 오류(500)는 재확인 없이 바로 보인다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-219"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 작업 조회 404 재확인 |
| TC-VF-220 | auth/me 가 authenticated=true 인데 csrf_token=null 이면 세션을 새로 발급받아 토큰을 얻는다 (fail-safe) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-220"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 세션 시작: 인증됐다는데 CSRF 토큰이 없는 응답 |
| TC-VF-221 | 경고 확인 체크 없이 승인자 입력칸에서 엔터를 눌러도 승인 요청이 나가지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-221"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 경고 제안 승인: 키보드(엔터) 우회 금지 |
| TC-VF-222 | 403 csrf_invalid: 서버 한국어 제목·hint 를 "다음에 할 일" 로 보이고 코드를 함께 표시한다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-222"` | 시나리오 문장의 기대를 모두 충족 | 통과(22건: 표 입력 변형 전부) | Pass | 오류 코드별 한국어 안내와 "다음에 할 일" |
| TC-VF-223 | 422 validation_error: 서버가 hint 를 비워도 "다음에 할 일" 은 항상 한국어 문구로 채워진다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-223"` | 시나리오 문장의 기대를 모두 충족 | 통과(6건: 표 입력 변형 전부) | Pass | 오류 코드별 한국어 안내와 "다음에 할 일" |
| TC-VF-224 | 429 + Retry-After 는 "N초 뒤에 다시 시도" 안내가 hint 에 붙고, 한도 계열은 경고 톤 제목을 쓴다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-224"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 오류 코드별 한국어 안내와 "다음에 할 일" |
| TC-VF-225 | 서버 문구가 영어여도(예: 프록시 502) 화면의 고정 문구(제목·다음에 할 일·코드 라벨)는 한국어다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-225"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 오류 코드별 한국어 안내와 "다음에 할 일" |
| TC-VF-226 | 일반 Error(코드 없음)도 크래시 없이 한국어 기본 안내와 unknown 코드를 보인다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-226"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 오류 코드별 한국어 안내와 "다음에 할 일" |
| TC-VF-227 | 요청이 끝나면(성공·실패 모두) 호출자 신호에 걸어 둔 리스너를 제거한다(반복 호출해도 쌓이지 않음) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-227"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | API 클라이언트: 호출자 중단 신호 정리 |
| TC-VF-228 | 진행 중이면 1초마다 다시 읽어 진행률을 갱신하고, 끝나면 onDone 을 한 번만 부르고 폴링을 멈춘다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-228"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 작업 패널(JobPanel) 폴링 |
| TC-VF-229 | 서버가 hint 를 주면 화면 기본 안내(errorHints)보다 서버 hint 를 "다음에 할 일" 로 쓴다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-229"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 오류 안내 우선순위 |
| TC-VF-230 | 취소(cancelled)로 끝난 작업도 폴링을 멈추고 onDone 을 부른다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-230"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 작업 패널(JobPanel) 폴링 |
| TC-VF-231 | 뒤 공백 가 있으면 안내는 ✕(불일치)이고 ✓ 가 아니다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-231"` | 시나리오 문장의 기대를 모두 충족 | 통과(3건: 표 입력 변형 전부) | Pass | 확인 문구 일치 안내 |
| TC-VF-232 | 403(출처 거절)은 "PIN 이 틀렸다" 가 아니라 서버가 준 사유와 다음에 할 일을 보여 준다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-232"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | DEF-VF-004; PIN 화면 오류 구분 |
| TC-VF-233 | 401 pin_invalid 는 입력칸 아래에 "PIN 이 올바르지 않습니다" 로 보인다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-233"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | PIN 화면 오류 구분 |
| TC-VF-234 | 429 pin_locked 는 틀린 PIN 문구가 아니라 잠금 안내(한도 계열)를 보인다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-234"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | PIN 화면 오류 구분 |
| TC-VF-235 | 한도 계열(429)은 경고 톤, 그 밖의 오류는 위험 톤 스타일을 쓴다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-235"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 오류 톤 구분 |
| TC-VF-236 | 첫 작업이 404 로 닫을 수 있게 된 뒤, 새 작업이 진행 중이면 닫기가 다시 꺼진다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-236"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | X11; 작업 창: 이전 작업의 읽기 오류가 새 작업으로 새지 않는다 |
| TC-VF-237 | PIN 을 비워 둔 채 제출(엔터)해도 세션 발급 요청이 나가지 않는다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-237"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | PIN 화면: 빈 PIN 제출 금지 |
| TC-VF-238 | 서버가 live_enabled=true 를 주면 홈이 "켜짐" 을 글자로 보여 준다(꺼짐 문구는 없다) | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-238"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 홈·영상 목록: 실패와 라이브 표시 |
| TC-VF-239 | live_enabled=false 면 "꺼짐" 이고, 이력의 데모 모드 표기는 ko.ts 문구다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-239"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 홈·영상 목록: 실패와 라이브 표시 |
| TC-VF-240 | 데모 영상 불러오기 요청이 500 이면 오류 안내가 보이고 버튼이 다시 켜진다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-240"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 홈·영상 목록: 실패와 라이브 표시 |
| TC-VF-241 | AI 제안 생성 요청이 409(제외 영상 포함)로 거절되면 오류 창이 뜨고 닫을 수 있으며 선택은 유지된다 | jsdom + 가짜 fetch(실제 네트워크 없음) | `npx vitest run verify/round2.verify.test.tsx -t "TC-VF-241"` | 시나리오 문장의 기대를 모두 충족 | 통과 | Pass | 홈·영상 목록: 실패와 라이브 표시 |
| TC-VF-300 | 시작: auth/me → 세션 발급 → online, CSRF 보관, 쿠키는 HttpOnly(스크립트에 보이지 않음) | 실서버(FastAPI+PostgreSQL 54333+워커), `VF_LIVE_API` 지정 | `VF_LIVE_API=http://127.0.0.1:18080 npx vitest run verify/live.verify.test.ts -t "TC-VF-300"` | 시나리오 문장의 기대를 모두 충족 | 통과(실서버 실행) | Pass | 실서버 계약 연동 (프런트 ApiClient + endpoints) |
| TC-VF-301 | 홈 계약: dashboard 필드가 types.ts 와 일치한다 | 실서버(FastAPI+PostgreSQL 54333+워커), `VF_LIVE_API` 지정 | `VF_LIVE_API=http://127.0.0.1:18080 npx vitest run verify/live.verify.test.ts -t "TC-VF-301"` | 시나리오 문장의 기대를 모두 충족 | 통과(실서버 실행) | Pass | 실서버 계약 연동 (프런트 ApiClient + endpoints) |
| TC-VF-302 | 데모 영상 불러오기: POST videos/sync(CSRF 자동) → 작업 폴링 → succeeded | 실서버(FastAPI+PostgreSQL 54333+워커), `VF_LIVE_API` 지정 | `VF_LIVE_API=http://127.0.0.1:18080 npx vitest run verify/live.verify.test.ts -t "TC-VF-302"` | 시나리오 문장의 기대를 모두 충족 | 통과(실서버 실행) | Pass | 실서버 계약 연동 (프런트 ApiClient + endpoints) |
| TC-VF-303 | 영상 목록 계약·정렬 키·필터 값이 서버에서 받아들여진다 | 실서버(FastAPI+PostgreSQL 54333+워커), `VF_LIVE_API` 지정 | `VF_LIVE_API=http://127.0.0.1:18080 npx vitest run verify/live.verify.test.ts -t "TC-VF-303"` | 시나리오 문장의 기대를 모두 충족 | 통과(실서버 실행) | Pass | 실서버 계약 연동 (프런트 ApiClient + endpoints) |
| TC-VF-304 | 서버 쪽 쪽 크기 상한: 200 은 허용, 201 은 오류(프런트 상한 200 과 일치) | 실서버(FastAPI+PostgreSQL 54333+워커), `VF_LIVE_API` 지정 | `VF_LIVE_API=http://127.0.0.1:18080 npx vitest run verify/live.verify.test.ts -t "TC-VF-304"` | 시나리오 문장의 기대를 모두 충족 | 통과(실서버 실행) | Pass | 실서버 계약 연동 (프런트 ApiClient + endpoints) |
| TC-VF-305 | AI 제안 생성(작업) → 상세에서 제안·reasons·strict 계약 확인 | 실서버(FastAPI+PostgreSQL 54333+워커), `VF_LIVE_API` 지정 | `VF_LIVE_API=http://127.0.0.1:18080 npx vitest run verify/live.verify.test.ts -t "TC-VF-305"` | 시나리오 문장의 기대를 모두 충족 | 통과(실서버 실행) | Pass | 실서버 계약 연동 (프런트 ApiClient + endpoints) |
| TC-VF-306 | 제안 생성 영상 수 상한: 201개는 서버가 거절한다(프런트 상한 MAX_GENERATE=200 과 일치) | 실서버(FastAPI+PostgreSQL 54333+워커), `VF_LIVE_API` 지정 | `VF_LIVE_API=http://127.0.0.1:18080 npx vitest run verify/live.verify.test.ts -t "TC-VF-306"` | 시나리오 문장의 기대를 모두 충족 | 통과(실서버 실행) | Pass | 실서버 계약 연동 (프런트 ApiClient + endpoints) |
| TC-VF-307 | 승인: 승인자 없음은 서버가 거절, 정상 승인 후 approval 채워짐, 차단 제안은 409 suggestion_blocked | 실서버(FastAPI+PostgreSQL 54333+워커), `VF_LIVE_API` 지정 | `VF_LIVE_API=http://127.0.0.1:18080 npx vitest run verify/live.verify.test.ts -t "TC-VF-307"` | 시나리오 문장의 기대를 모두 충족 | 통과(실서버 실행) | Pass | 실서버 계약 연동 (프런트 ApiClient + endpoints) |
| TC-VF-308 | 프런트의 "차단" 판정 규칙이 서버와 일치: 후보 전체에 대해 (block \|\| strict&&!pass) 이면 승인이 409 로 거절된다 | 실서버(FastAPI+PostgreSQL 54333+워커), `VF_LIVE_API` 지정 | `VF_LIVE_API=http://127.0.0.1:18080 npx vitest run verify/live.verify.test.ts -t "TC-VF-308"` | 시나리오 문장의 기대를 모두 충족 | 통과(실서버 실행) | Pass | 실서버 계약 연동 (프런트 ApiClient + endpoints) |
| TC-VF-309 | 배치: 멱등키 필수 — 키 없이 직접 호출하면 400/422, 같은 키+같은 본문은 같은 결과, 같은 키+다른 본문은 422 idempotency_key_reuse | 실서버(FastAPI+PostgreSQL 54333+워커), `VF_LIVE_API` 지정 | `VF_LIVE_API=http://127.0.0.1:18080 npx vitest run verify/live.verify.test.ts -t "TC-VF-309"` | 시나리오 문장의 기대를 모두 충족 | 통과(실서버 실행) | Pass | 실서버 계약 연동 (프런트 ApiClient + endpoints) |
| TC-VF-310 | 배치 상세(draft)가 precheck 를 주는지, 확인 문구 형식이 "실행 N건" 인지 | 실서버(FastAPI+PostgreSQL 54333+워커), `VF_LIVE_API` 지정 | `VF_LIVE_API=http://127.0.0.1:18080 npx vitest run verify/live.verify.test.ts -t "TC-VF-310"` | 시나리오 문장의 기대를 모두 충족 | 통과(실서버 실행) | Pass | 실서버 계약 연동 (프런트 ApiClient + endpoints) |
| TC-VF-311 | 실행: 틀린 확인 문구는 409/422 confirm_text_mismatch(한국어 안내), 맞는 문구로 실행하면 작업이 시작된다 | 실서버(FastAPI+PostgreSQL 54333+워커), `VF_LIVE_API` 지정 | `VF_LIVE_API=http://127.0.0.1:18080 npx vitest run verify/live.verify.test.ts -t "TC-VF-311"` | 시나리오 문장의 기대를 모두 충족 | 통과(실서버 실행) | Pass | 실서버 계약 연동 (프런트 ApiClient + endpoints) |
| TC-VF-312 | 실행 후 상태 값: 배치 status 가 프런트가 아는 값(활성: queued/running, 종료: done/cancelled)만 쓰는지 폴링하며 확인 | 실서버(FastAPI+PostgreSQL 54333+워커), `VF_LIVE_API` 지정 | `VF_LIVE_API=http://127.0.0.1:18080 npx vitest run verify/live.verify.test.ts -t "TC-VF-312"` | 시나리오 문장의 기대를 모두 충족 | 통과(실서버 실행) | Pass | 실서버 계약 연동 (프런트 ApiClient + endpoints) |
| TC-VF-313 | 이력·롤백: 변경 이력 계약, 영상 ID 틀리면 거절, 맞으면 롤백 행 생성(멱등키 재사용 시 같은 결과) | 실서버(FastAPI+PostgreSQL 54333+워커), `VF_LIVE_API` 지정 | `VF_LIVE_API=http://127.0.0.1:18080 npx vitest run verify/live.verify.test.ts -t "TC-VF-313"` | 시나리오 문장의 기대를 모두 충족 | 통과(실서버 실행) | Pass | 실서버 계약 연동 (프런트 ApiClient + endpoints) |
| TC-VF-314 | 리포트·설정·감사·구글 상태 계약 | 실서버(FastAPI+PostgreSQL 54333+워커), `VF_LIVE_API` 지정 | `VF_LIVE_API=http://127.0.0.1:18080 npx vitest run verify/live.verify.test.ts -t "TC-VF-314"` | 시나리오 문장의 기대를 모두 충족 | 통과(실서버 실행) | Pass | 실서버 계약 연동 (프런트 ApiClient + endpoints) |
| TC-VF-315 | 서버 검증 범위가 프런트 검증과 같은 방향: 하루 상한 21·0, 말투 6개/21자, 영상당 6 는 거절 | 실서버(FastAPI+PostgreSQL 54333+워커), `VF_LIVE_API` 지정 | `VF_LIVE_API=http://127.0.0.1:18080 npx vitest run verify/live.verify.test.ts -t "TC-VF-315"` | 시나리오 문장의 기대를 모두 충족 | 통과(실서버 실행) | Pass | 실서버 계약 연동 (프런트 ApiClient + endpoints) |
| TC-VF-316 | 서버에는 라이브 허용을 켜는 입력이 없다: enable_live 키를 보내면 거절된다(프런트가 보내지 않는 이유의 방어선) | 실서버(FastAPI+PostgreSQL 54333+워커), `VF_LIVE_API` 지정 | `VF_LIVE_API=http://127.0.0.1:18080 npx vitest run verify/live.verify.test.ts -t "TC-VF-316"` | 시나리오 문장의 기대를 모두 충족 | 통과(실서버 실행) | Pass | 실서버 계약 연동 (프런트 ApiClient + endpoints) |
| TC-VF-317 | CSRF: 잘못된 토큰으로 상태 변경 → 403 이고, 프런트는 재발급 1회 후 같은 요청을 성공시킨다 | 실서버(FastAPI+PostgreSQL 54333+워커), `VF_LIVE_API` 지정 | `VF_LIVE_API=http://127.0.0.1:18080 npx vitest run verify/live.verify.test.ts -t "TC-VF-317"` | 시나리오 문장의 기대를 모두 충족 | 통과(실서버 실행) | Pass | 실서버 계약 연동 (프런트 ApiClient + endpoints) |
| TC-VF-318 | 모든 오류 응답은 problem+json 이고 title/hint 가 한국어이며 스택·내부 경로가 없다 | 실서버(FastAPI+PostgreSQL 54333+워커), `VF_LIVE_API` 지정 | `VF_LIVE_API=http://127.0.0.1:18080 npx vitest run verify/live.verify.test.ts -t "TC-VF-318"` | 시나리오 문장의 기대를 모두 충족 | 통과(실서버 실행) | Pass | 실서버 계약 연동 (프런트 ApiClient + endpoints) |
| TC-VF-319 | CSV 내보내기: blob 으로 받고 본문에 수식 주입 위험 문자가 셀 맨 앞에 없다 | 실서버(FastAPI+PostgreSQL 54333+워커), `VF_LIVE_API` 지정 | `VF_LIVE_API=http://127.0.0.1:18080 npx vitest run verify/live.verify.test.ts -t "TC-VF-319"` | 시나리오 문장의 기대를 모두 충족 | 통과(실서버 실행) | Pass | 실서버 계약 연동 (프런트 ApiClient + endpoints) |
| TC-VF-320 | PIN: 설정 → 로그아웃 → 틀린 PIN 401 → 맞는 PIN 으로 재로그인 → 해제 | 실서버(FastAPI+PostgreSQL 54333+워커), `VF_LIVE_API` 지정 | `VF_LIVE_API=http://127.0.0.1:18080 npx vitest run verify/live.verify.test.ts -t "TC-VF-320"` | 시나리오 문장의 기대를 모두 충족 | 통과(실서버 실행) | Pass | 실서버 계약 연동 (프런트 ApiClient + endpoints) |

### 4-1. 인수 조건 ↔ 시험 추적
| AC | 인수 조건(출처) | 연결 TC | 판정 |
|---|---|---|---|
| AC-01 | `npm ci && npm run check`(타입·린트·포맷·테스트·빌드) 통과 (노트 §13-1) | 4-2 정적 검사 표, TC-WF 전체 + TC-VF 전체 | 충족 |
| AC-02 | 핵심 흐름: 영상 선택(여러 쪽)→제안 생성→상세 확인→승인→배치 초안→사전 점검→확인 문구→실행→진행·완료→롤백 (노트 §13-2) | TC-VF-084~095, 151~172, 184~188, 300~313, 실브라우저 흐름(4-3) | 충족 |
| AC-03 | PIN 화면·틀린 PIN 안내·세션 만료 재입력 (§13-3) | TC-VF-020~022, 039, 078~083, 134~135, 189, 220, 232~234, 237, 320 | 충족 |
| AC-04 | 서버 끊김 표시·복구 (§13-4) | TC-VF-029~031, 040, 136~137, 189, 194~197, 214 | 충족 |
| AC-05 | 설정의 라이브/허용 영상 읽기 전용 (§13-5) | TC-VF-069~072, 238, 315~316 | 충족 |
| AC-06 | 키보드만으로 가능·포커스 링 (§13-6) | TC-VF-125~145, 실브라우저 Tab 12회 | 충족(수동 스크린리더 제외) |
| AC-07 | 확인 문구 입력이 맞아야만 버튼 (요청 중점) | TC-VF-042~051, 231, 052~058, 309~311, 313 | 충족 |
| AC-08 | 승인 흐름: 경고 확인 체크, 차단 시 승인 불가, 엄격 모드 (요청 중점) | TC-VF-060~066, 190~193, 221, 307~308 | 충족 |
| AC-09 | 배치 진행 폴링(2초)·중지 (요청 중점) | TC-VF-123, 163, 171~172, 217~219, 228~230, 207~208, 312 | 충족 |
| AC-10 | 오류 코드(API.md `code`)별 한국어 안내와 다음에 할 일 | TC-VF-023~028, 146~147, 222~226, 318 | 충족 |
| AC-11 | CSRF·세션·Idempotency-Key 헤더와 재시도 규칙 | TC-VF-001~022, 035~036, 227, 309, 317 | 충족 |
| AC-12 | XSS(외부 문자열 이스케이프) | TC-VF-037~038, 092, 097~102, 106, 114, TC-WF-081(소스 규칙) | 충족 |
| AC-13 | 접근성·색에만 의존하지 않음·대비·모바일 폭 | TC-VF-117~119, 124~145, 실브라우저 axe 34화면(대비 포함), 1024/1280/다크 가로 넘침 없음. **375px 는 설계 비대상(F-10 최소 1024px)이라 관찰로 기록** | 충족(375px 제외, 관찰 OBS-3) |
| AC-14 | 한국어 문구 일관성·문구 한곳 | TC-VF-164~166, 225, 239; 관찰 OBS-2·OBS-4 | 일부 관찰(8절) |
| AC-15 | 화면별 로딩·빈 상태·오류·정상 | TC-VF-104~105, 148~150, 158, 180~181, 185~186, 188~189, 206 | 충족 |
| AC-16 | 타입·린트·빌드 통과 | 4-2 | 충족 |
| AC-17 | 테스트 제외 설정 | DEC-041 ⑤ **알려진 미반영** (결함 아님) | 해당(미반영 기록) |
| AC-18 | 실서버 계약 일치 (DV-W09 타입 불일치 포함) | TC-VF-300~320 | 충족(백엔드 결함 B01 별도) |

### 4-2. 실행 수치
| 항목 | 결과 |
|---|---|
| 전체 Vitest(`npx vitest run`) | **505 통과 / 0 실패 / 21 건너뜀(실서버 시험, 환경변수 없을 때)**, 526건 중. 파일: 구현자 9(95건) + 심사자 verify 8(410건) |
| 실서버 시험(`VF_LIVE_API`) | **21 / 21 통과** (TC-VF-300~320). 변경 직후 대기 0ms 로 돌리면 7건 실패(DEF-VF-B01 재현) |
| TC-VF 고유 ID | 262개(001~241 단위 + 300~320 실서버), 실행 인스턴스 431건 |
| `tsc -b --noEmit`(strict, noUncheckedIndexedAccess) | 오류 0 |
| `tsc -p verify/tsconfig.json --noEmit`(심사자 시험 포함 타입 검사) | 오류 0 |
| ESLint(react-hooks, jsx-a11y, no-explicit-any 등) | 오류 0, 경고 0 |
| Prettier `--check .` | 통과 |
| `vite build` | 성공, JS 392.9 kB(gzip 119 kB), CSS 16.2 kB, `dist/index.html` 에 인라인 스크립트·스타일 없음 |
| `npm audit` | 취약점 0 |
| 구현자 노트 게이트(린트·타입·포맷·자체 리뷰) 확인 | 노트 §2·§11 의 수치를 직접 재실행으로 재현(수정 전 기준선: 397 통과 + 11 expected-fail) |

### 4-3. 실브라우저 점검 (Chromium 1194, 실서버 + 빌드 산출물 `dist` 를 백엔드가 서빙)
| 항목 | 결과 |
|---|---|
| 전체 흐름(UI 조작): 홈(빈) → 데모 영상 불러오기 → 목록에서 2개 선택 → 제안 생성 창 → 상세 → 승인(경고면 확인 체크) → 배치 사전 점검 → 확인 문구 `실행 1건` (뒤 공백이면 비활성, 정확히 입력해야 활성) → 실행 → 완료 → 이력 → 롤백 대화상자(처음엔 비활성, Esc 로 닫히고 포커스 복귀) → 리포트 → 설정 4탭 | 전부 정상. 콘솔 오류 0, 4xx/5xx 응답 0 (최종 실행) |
| axe-core(wcag2a·2aa·21a·21aa·22aa·best-practice, **color-contrast 포함**) | 34개 화면·상태 조합 전부 **위반 0** — 라이트 1280(홈 빈/일반, 목록, 작업 창, 상세, 승인 대화상자, 배치 목록/초안/진행, 이력, 롤백 대화상자, 리포트, 설정 4탭), 1024px 6화면, 다크 1280px 6화면, 375px 6화면 |
| 1024px·1280px(라이트/다크) 가로 넘침 | 없음(scrollWidth == innerWidth) |
| 375px 가로 넘침 | **있음**(홈 639px, 배치 588px, 이력 935px, 설정 453px, 목록·리포트 +1px). 설계 F-10 은 "PC 우선, 최소 1024px" 이므로 결함이 아니라 관찰 OBS-3 으로 기록 |
| 키보드: Tab 12회 | 첫 포커스 "본문으로 건너뛰기", 이후 메뉴 6개→로그아웃→본문 링크 순서, 모든 요소에 `outline: solid 3px` 포커스 링 |
| 스크린샷 | 홈·상세·배치·이력·리포트·설정·375px·다크를 눈으로 확인(저장소 밖 임시 폴더, 정리 시 삭제) |

## 5. 커버리지
- 커버리지 지표(`vitest --coverage`, v8, 전체 시험 실행 기준, `src/**` 에서 시험·시험 도구 제외): **줄 98.0% (982/1002), 분기 93.11% (933/1002), 구문 97.5%, 함수 96.76%**. 100% 가 아니다.
| 파일 | 줄 | 분기 | 함수 |
|---|---|---|---|
| src/api/client.ts | 99.23% (129/130) | 96.69% (117/121) | 96.87% |
| src/api/context.tsx | 100% (10/10) | 50% (1/2) | 100% |
| src/api/endpoints.ts | 100% (26/26) | 100% (6/6) | 100% |
| src/api/types.ts | 100% (0/0) | 100% (0/0) | 100% |
| src/app/App.tsx | 100% (2/2) | 100% (0/0) | 100% |
| src/app/AuthGate.tsx | 89.28% (25/28) | 90.9% (20/22) | 77.77% |
| src/app/ErrorBoundary.tsx | 85.71% (6/7) | 100% (6/6) | 75% |
| src/app/Layout.tsx | 100% (22/22) | 92.85% (13/14) | 100% |
| src/app/PinForm.tsx | 100% (19/19) | 100% (13/13) | 100% |
| src/app/providers.tsx | 100% (4/4) | 100% (3/3) | 100% |
| src/components/Badge.tsx | 100% (1/1) | 100% (5/5) | 100% |
| src/components/Button.tsx | 100% (2/2) | 100% (15/15) | 100% |
| src/components/Callout.tsx | 100% (2/2) | 100% (5/5) | 100% |
| src/components/Card.tsx | 100% (2/2) | 75% (6/8) | 100% |
| src/components/ConfirmPhrase.tsx | 100% (4/4) | 75% (9/12) | 100% |
| src/components/EmptyState.tsx | 100% (1/1) | 100% (2/2) | 100% |
| src/components/ErrorPanel.tsx | 100% (7/7) | 96.66% (29/30) | 100% |
| src/components/Field.tsx | 100% (6/6) | 93.33% (14/15) | 100% |
| src/components/Modal.tsx | 94.28% (33/35) | 92.85% (26/28) | 100% |
| src/components/PageHead.tsx | 100% (1/1) | 100% (4/4) | 100% |
| src/components/Pagination.tsx | 100% (7/7) | 100% (5/5) | 100% |
| src/components/Progress.tsx | 100% (1/1) | 100% (0/0) | 100% |
| src/components/QueryView.tsx | 100% (3/3) | 100% (4/4) | 100% |
| src/components/Skeleton.tsx | 100% (2/2) | 100% (1/1) | 100% |
| src/components/Table.tsx | 100% (2/2) | 100% (8/8) | 100% |
| src/components/Tabs.tsx | 94.44% (17/18) | 83.33% (10/12) | 100% |
| src/components/TitleDiff.tsx | 100% (6/6) | 100% (8/8) | 100% |
| src/components/Toast.tsx | 89.47% (17/19) | 75% (3/4) | 86.66% |
| src/components/ValidationBadge.tsx | 100% (4/4) | 100% (4/4) | 100% |
| src/components/index.ts | 100% (0/0) | 100% (0/0) | 100% |
| src/hooks/approver.ts | 100% (5/5) | 100% (0/0) | 100% |
| src/hooks/selection.tsx | 95.83% (23/24) | 83.33% (5/6) | 90% |
| src/hooks/useIdempotency.ts | 100% (2/2) | 100% (0/0) | 100% |
| src/i18n/ko.ts | 97.67% (42/43) | 100% (4/4) | 97.61% |
| src/lib/diff.ts | 100% (26/26) | 100% (16/16) | 100% |
| src/lib/format.ts | 100% (23/23) | 100% (23/23) | 100% |
| src/lib/labels.ts | 93.1% (27/29) | 82.05% (32/39) | 100% |
| src/main.tsx | 100% (0/0) | 100% (0/0) | 100% |
| src/pages/BatchDetailPage.tsx | 98.27% (57/58) | 95.65% (66/69) | 95.83% |
| src/pages/BatchesPage.tsx | 97.43% (38/39) | 80% (32/40) | 95.83% |
| src/pages/HistoryPage.tsx | 100% (45/45) | 95% (38/40) | 100% |
| src/pages/HomePage.tsx | 100% (33/33) | 91.42% (32/35) | 100% |
| src/pages/JobPanel.tsx | 100% (21/21) | 95.65% (22/23) | 85.71% |
| src/pages/ReportsPage.tsx | 100% (31/31) | 93.02% (40/43) | 100% |
| src/pages/SettingsPage.tsx | 100% (94/94) | 93.2% (96/103) | 100% |
| src/pages/SuggestionCard.tsx | 100% (55/55) | 95.55% (86/90) | 100% |
| src/pages/VideoDetailPage.tsx | 100% (23/23) | 88% (22/25) | 100% |
| src/pages/VideosPage.tsx | 95% (76/80) | 92.13% (82/89) | 91.89% |
| src/styles/base.css | 100% (0/0) | 100% (0/0) | 100% |
| src/styles/components.css | 100% (0/0) | 100% (0/0) | 100% |
| src/styles/index.css | 100% (0/0) | 100% (0/0) | 100% |
| src/styles/layout.css | 100% (0/0) | 100% (0/0) | 100% |
| src/styles/tokens.css | 100% (0/0) | 100% (0/0) | 100% |
| **전체** | **98%** (982/1002) | **93.11%** (933/1002) | **96.76%** |
- 커버되지 않은 부분과 사유(줄마다 확인)
  - `AuthGate.tsx` 37(세션 만료 오버레이의 닫기 콜백 `onClose={() => undefined}` — 닫기 금지라 호출되지 않는 자리)은 도달 불필요. `ErrorBoundary.tsx` "화면 새로고침" 버튼 onClick(`window.location.reload()`): jsdom 이 `reload` 를 구현하지 않아 호출 시험 불가(환경 한계). 버튼의 존재·활성은 TC-VF-216 이 확인.
  - `AuthGate.tsx` 첫 연결 전 `loggedout` 화면(79~83): 첫 연결 전에는 로그아웃 상태가 될 수 없음 → **도달 불가한 방어 분기**. 연결 중 로그아웃 화면은 TC-WF/TC-VF-136 이 확인.
  - `client.ts` 204(재발급 중 PIN 외 오류를 그대로 던지는 `throw re`): 재발급 중 비-PIN 오류는 TC-VF-016~018 이 간접 확인(재발급 응답이 오류인 별도 시험은 없음) → 잔여 위험 낮음, 8절 기재.
  - `Modal.tsx` 포커스 가능한 요소가 0개일 때의 Tab 차단: 모든 대화상자에 버튼이 있어 **도달 불가한 방어 분기**.
  - `Toast.tsx`, `labels.ts` 일부 색 톤 분기(`unverified` 등), `ReportsPage.tsx` 일부 지표 표기 분기, `selection.tsx` 일부: 표시용 분기로 서버 값 조합이 시험에 없음 → 변이 점검에서 모두 시험이 잡는 안전 로직은 아니며(표시 톤), 위험도 낮음.
  - 분기 커버리지 가장 낮은 곳: `context.tsx` 50%(Provider 없이 쓰는 오류 던지기, 개발자 실수 방어), `BatchesPage.tsx` 80%.
- 안전 로직(확인 문구·승인·CSRF·멱등키·재시도·폴링·상한)은 커버리지 숫자가 아니라 **변이 점검(부록 A)** 으로 검증했다. 최종 회전에서 동치 3건 외 놓침 0.

## 6. 결함(Defect) 목록
> 이전 진행분이 찾은 결함(DEF-6-001~011)은 **수정 전 실패 → 수정 후 통과**를 이번 세션에서 직접 재현하고 고쳤다. 증거: 수정 전 기준선 `397 통과 + 11 expected-fail(it.fails)`; 수정 후 "Expect test to fail"(= 이제 통과)로 전환 확인 후 `.fails` 제거; 또 수정을 되돌리는 변이 R01~R11 이 해당 시험을 실패시킴(부록 A). 새로 찾은 결함은 `DEF-VF-nnn`. 자기 단위(`web/frontend/`) 안의 결함은 직접 고치고 회귀 시험을 추가한 뒤 전체를 다시 돌렸다(규칙 F).

| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 내용 |
|----|------|-----------|--------|------|-----------|
| DEF-6-001 | 응답이 오지 않는 서버에 시간 제한이 없어 요청이 영원히 대기 | 응답 없는 가짜 fetch 로 10분 경과시켜도 요청이 끝나지 않음(TC-VF-032) | Low | Fixed | `client.ts`: 30초 제한(`REQUEST_TIMEOUT_MS`)+AbortController, 초과 시 연결 끊김 오류·offline. 정확히 29.999초/30초 경계와 타이머·리스너 누수 없음 시험(TC-VF-032, 194~197, 227) |
| DEF-6-002 | 한도 판별 정규식 `/rate/` 가 `generate_failed` 같은 코드에도 걸림(잠복) | `isLimit` 에 `generate_failed`, `migrate_error` 를 넣음(TC-VF-034) | Low | Fixed | 단어 경계 정규식 `(^\|_)(limit\|limited\|quota\|cap\|rate)(_\|$)`. TC-VF-034, 198~200 |
| DEF-6-003 | 말투 입력칸 `maxLength=40`(전체 글자수)이라 서버가 허용하는 5개×20자를 입력 불가 | 설정에서 말투 3개(각 15자)를 입력하면 잘림(TC-VF-077) | Medium | Fixed | `maxLength=200`(범위 검증은 기존 목록·글자수 검사가 담당). TC-VF-077, 209~210, 실서버 315 |
| DEF-6-004 | 작업 상태 조회가 계속 실패하면(404/500) 제안 생성 창을 닫을 방법이 없음(Esc·닫기 모두 비활성) | 제안 생성 후 `GET jobs/{id}` 가 404 → 창이 고정(TC-VF-095) | Medium | Fixed | `JobPanel` 에 `onError` 추가, `VideosPage` 가 조회 실패 시 닫기 활성. 새 작업 시작 시 오류 상태 초기화(TC-VF-236). TC-VF-095 를 Esc 로 실제 닫힘까지 확인하도록 강화 |
| DEF-6-005 | 오류 경계가 없어 응답 형식이 계약과 다르면 앱 전체가 빈 화면 | 영상 상세 응답에서 `suggestions` 제거(TC-VF-103) | Medium | Fixed | `ErrorBoundary`(Layout 안, 메뉴 유지, 스택 비노출, 다른 화면으로 이동하면 복구). TC-VF-103, 206, 216 |
| DEF-6-006 | 같은 이름의 region 랜드마크가 겹침(섹션 제목 = 표 래퍼 라벨) | `/batches` 에 axe landmark-unique(TC-VF-126) | Low | Fixed | 표 래퍼 라벨을 `지난 배치 목록 표` 로 구분. TC-VF-126 |
| DEF-6-007 | `?page_size=200`(노트가 지원한다고 적음)이면 200건을 받는데 선택 목록에는 "25개"로 보임 | `/videos?page_size=200`(TC-VF-156) | Low | Fixed | 목록에 없는 쪽 크기도 정렬해 선택지에 추가. TC-VF-156, 204~205 |
| DEF-6-008 | 불러오기 작업이 진행 중인데 "데모 영상 불러오기" 버튼이 다시 켜져 중복 시작 가능 | 영상 0개 홈에서 불러오기 후 진행 중 다시 클릭(TC-VF-179) | Low | Fixed | 작업 진행 중 비활성, 작업 종료·조회 실패 시 다시 켜짐(영구 잠금 방지). TC-VF-179, 207~208 |
| DEF-6-010 | 배치 상태 `queued`(실행 직후 실제 서버 값)·`paused` 가 영문 원문으로 표시 | 배치 상세에 `queued` 응답(TC-VF-182) | Low | Fixed | `ko.batchStatus` 에 `실행 대기`·`일시 중지` 추가. TC-VF-182, 202 |
| DEF-6-011 | 홈 "진행 중인 작업" 이 `videos.sync` 같은 서버 코드를 그대로 표시 | 대시보드 `active_job.type=videos.sync`(TC-VF-183) | Low | Fixed | `ko.jobType` + `jobTypeLabel`. TC-VF-183, 202 |
| DEF-VF-001 | **엄격 모드(strict) 제안의 경고를 일반 경고처럼 취급**: 서버는 `block` 이거나 `strict` 이면서 `pass` 가 아니면 승인을 거부(409 `suggestion_blocked`)하는데, 화면은 경고 확인 체크 후 승인할 수 있는 것처럼 보여 줌. 검증 전(null)+strict 도 마찬가지 | 건강·금융 등 strict 제안이 `validation_result=warn` → 승인 버튼 활성, 누르면 서버가 거절(서버 규칙: `domain/suggestions.py` `is_blocked`) | Medium | Fixed | `SuggestionCard`: `blocked = block \|\| (strict && result≠pass)`, 배지도 "차단"으로 표시, 승인 버튼 비활성+사유 연결. TC-VF-190~193, 실서버 308(후보 전체에 대해 프런트 판정과 서버 거절이 일치). 서버가 최종 방어선이므로 안전 침해는 아니고 사용자 혼란 결함 |
| DEF-VF-002 | 여러 쪽에서 200개 넘게 선택해도 막지 않아 서버가 422 로 거절(API.md: 영상 1~200개) | 쪽 크기 200 으로 2쪽에 걸쳐 201개 선택 후 생성 | Low | Fixed | `MAX_GENERATE=200`: 초과 시 버튼 비활성+안내(role=alert). TC-VF-212~213, 실서버 304·306 |
| DEF-VF-003 | 배치 만들기에서 한 번 고른 항목이 승인 목록에서 사라져도(승인 만료·다른 배치에 담김) 선택 수와 요청에 계속 포함 | 항목 2개 선택 후 목록 갱신으로 1개가 사라짐 | Low | Fixed | 현재 목록에 있는 항목만 선택으로 계산·전송. TC-VF-211 |
| DEF-VF-004 | PIN 화면이 403(출처·CSRF 거절)까지 "PIN 이 올바르지 않습니다"로 안내해 원인을 오도 | 세션 발급이 403 `origin_not_allowed` | Low | Fixed | 틀린 PIN 안내는 401 에만 사용, 그 밖에는 서버 사유·다음에 할 일 표시. TC-VF-232~234 |
| DEF-VF-005 | 방금 만든 작업을 곧바로 조회하면 404 가 되는 경우(백엔드 DEF-VF-B01) 제안 생성 창/홈에 즉시 오류가 뜸 | 실서버 대기 0ms 시험(TC-VF-305 외 7건 실패) | Medium | Fixed(프런트 완화) | `JobPanel`: 작업 조회 404 는 0.5초 간격 3번까지 재확인 후 오류 표시. TC-VF-217~219. **근본 원인은 백엔드(B01)이므로 B01 이 고쳐지면 완화를 제거할지 결정 필요**(질문 Q3) |
| DEF-VF-006 | 화면 문구 일부가 `ko.ts` 밖에 하드코딩("실제 반영(라이브): 켜짐", 이력의 "데모") — F-08 문구 한곳 원칙 위반 | 소스 검색 | Low | Fixed | `ko.home.liveOn`, `ko.history.modeDemo`. TC-VF-238~239. `client.ts` 의 오류 기본 문구 7곳은 관찰 OBS-4 로 남김 |
| DEF-VF-B01 | **[백엔드, 이 단위 소유 아님] 요청마다 DB 변경(commit)이 응답 전송 *뒤에* 일어나, 바로 다음 요청이 옛 상태를 읽음**. 증상: ① 방금 만든 작업 조회가 404 ② 세션 발급 직후 첫 요청이 401(실브라우저에서 1회 관찰) ③ **PIN 이 이미 설정됐는데 바로 이어진 PIN 변경이 `current_pin` 없이 통과**(40회 중 7회) | `python3 race.py`(연속 PATCH settings) 또는 `VF_LIVE_SETTLE_MS=0 VF_LIVE_API=… npx vitest run verify/live.verify.test.ts` → 7건 실패(`작업을 찾을 수 없습니다`) | **High** | **Open**(W-BE-A 소유) | 원인: `core/deps.get_session` → `db/session.session_scope` 가 `yield` 뒤에서 `commit()` — FastAPI 0.143 은 yield 의존성의 종료 코드를 응답 전송 뒤에 실행. 제안: 라우터에서 응답 전 commit, 또는 `Depends(get_session, scope="function")`(FastAPI ≥0.121)으로 응답 전 종료. 프런트 영향은 DEF-VF-005 완화로 줄였으나 다른 읽기-직후 쓰기(승인→목록 새로고침 등)는 근본 수정 필요 |
| DEF-VF-B02 | **[백엔드]** 일부 오류 코드가 `hint` 를 비움(`pin_invalid`, `pin_not_set`, `title_invalid`, `validation_error`, `no_handler`) → 프런트는 기본 안내로 대체 | 코드 읽기(`ProblemError(...)` 에 hint 없음) | Low | Open(W-BE-A 소유) | 프런트는 `errorHints`/기본 문구로 보완하여 TC-VF-223 이 통과. 서버 쪽 한국어 hint 추가 권장 |

**시험 설계 결함(TD) — 시험 쪽을 고침, 앱 결함 아님**
| ID | 설명 | 조치 |
|---|---|---|
| TD-1 | 이전 진행분 TC-VF-127/129/130 의 경고 제안 고정값이 `strict: true`(서버 규칙과 모순) | `strict: false` 로 정정, 엄격 모드는 TC-VF-190~192 로 별도 시험 |
| TD-2 | TC-VF-179 는 `progressbar` 가 홈에 3개라 선택자가 모호해 *엉뚱한 이유로* 실패(expected-fail 로 가려져 있었음) | 이름으로 선택하도록 수정 |
| TD-3 | TC-VF-095 가 `if (dlg)` 로 Esc 결과를 확인하지 않아 R04 변이를 놓침 | Esc 로 실제 닫히는지 확인하도록 강화 |
| TD-4 | 1회전 변이 M49 가 무관한 시험(TC-WF-027)의 부하 실패로 "잡음" 처리됨(가짜 검출) | 모든 최종 killer 를 검토해 가짜 검출·문법 오류 무효 변이(R05, X23)를 식별하고 교체·개별 확인(부록 A 비고) |

**방어적 수정(결함은 아님, 재현 불가한 예방)**: `fmtDateTime` 의 `hour12:false` → `hourCycle:'h23'`(일부 구현에서 자정을 "24:00" 으로 표기하는 문제 예방, 이 환경에서는 동치 → 부록 A R11), 라벨 조회에 `Object.hasOwn`(서버 값이 `constructor` 등일 때 함수가 라벨로 쓰이는 문제 예방, TC-VF-201).

**결함 0건 주장은 하지 않는다.** 근거: 위 표 18건(프런트 16건 Fixed, 백엔드 2건 Open).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록(경로 포함)
  - `.harness-tmp/vf/work/` — `node_modules` 복사본(`npm ci --ignore-scripts`), 소스 동기화 사본, `dist`, 커버리지 산출물
  - `.harness-tmp/vf/mut/` — 변이 점검 격리 사본(작업자별 `0`,`1`,`2`, 개별 확인용 `one_*`)
  - `.harness-tmp/vf/venv/` — 백엔드 실서버용 Python 임시 가상환경
  - `.harness-tmp/vf/pg/` — 임시 PostgreSQL 16 데이터 디렉터리(포트 **54333**, 127.0.0.1 바인딩, 소유자 `postgres`)와 로그
  - `.harness-tmp/vf/secrets/`(서명 키용 임시 폴더), `api.log`, `worker.log`, `*.pid`, `e2e/`(실브라우저 스크립트·스크린샷), 변이 결과 jsonl·로그, 보고서 생성 스크립트
  - 실행 중이던 프로세스: uvicorn(127.0.0.1:18080), 워커, PostgreSQL(54333), Chromium(스크립트 종료 시 함께 종료)
  - 저장소 밖: 스크래치 폴더의 재현 스크립트 2개(삭제함)
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예 [ ] 아니오 — 저장소 `web/frontend/` 에는 `node_modules`·`dist`·`coverage` 를 만들지 않았다(확인: 없음). 산출물로 남긴 파일은 `web/frontend/verify/**`(시험), 소스 수정분, `docs/harness/` 결과서 2개뿐.
- 정리(삭제) 완료 여부: **예.** (1) uvicorn·워커 프로세스 종료, (2) `pg_ctl stop -m fast` → `server stopped`, (3) 포트 54333·18080 에 리스너 없음(`ss -ltn` 0건), (4) `.harness-tmp/vf/` 전체 삭제(약 406 MB). 다른 에이전트의 폴더(`.harness-tmp/va`, `vb`, `vi`)와 프로세스는 건드리지 않았다.
- 정리 후 점검 — **`git status` 는 이 작업의 지시(공통 지시서 3절: git 명령 금지)에 따라 실행하지 않았다.** 대신 파일시스템으로 확인한 결과:
  ```
  $ ls -la .harness-tmp          -> va  vb  vi 만 존재 (vf 없음)
  $ ls web/frontend              -> dev eslint.config.js index.html package-lock.json package.json public src tsconfig*.json verify vite.config.ts
  $ ls web/frontend/node_modules web/frontend/dist web/frontend/coverage -> 모두 "No such file"
  $ ls .harness-tmp/vf           -> No such file or directory
  ```
  이 단위가 소유한 변경 파일(`web/frontend/src/**` 16개 파일(신규 `ErrorBoundary.tsx` 포함), `web/frontend/verify/**` 10개 파일, 결과서 2개)은 **의도한 산출물**이며 오케스트레이터가 `git status`/`harness-janitor.sh --check` 로 최종 확인·커밋해야 한다.
- 병렬 실행이었다면: 다른 단위 소유분 — `src/youtube_title.egg-info/`(17:15 생성, 내가 만들지 않음: 나는 편집 설치를 하지 않고 `PYTHONPATH` 로만 사용), `web/backend/**/__pycache__`(백엔드 시험·서버 기동 부산물, `.gitignore` 대상 추정), `docs/harness/_parallel/web-verify-brief.md`(오케스트레이터 소유). **이 실행이 만든 임시 아티팩트·미추적 잔여물은 없음**(위 점검 기준). 웨이브 종료 후 전체 트리 점검은 오케스트레이터가 수행.
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [ ] 없음 / [x] 있음 — 세션 사용 한도로 한 번 중단됨. 재개 시 `.harness-tmp/vf/` 잔여물(작업 복사본, 이전 진행분)을 먼저 확인해 재사용했고, 진행 상황을 `PROGRESS.md`(정리 시 삭제)에 남기며 진행했다. 중단 시점에 실행 중이던 서버·DB 프로세스는 없었다.
- 이 절은 완성되었고 임시 아티팩트 정리를 확인했다(규칙 K 2번 충족: 단 `git status` 원문은 지시상 첨부 불가 → 오케스트레이터 확인 필요).

## 8. 리스크 및 잔존 이슈
- **Open 결함**: DEF-VF-B01(High, 백엔드, 경쟁 조건), DEF-VF-B02(Low). B01 은 프런트가 완화했지만 PIN 변경 우회 가능성 등 보안 의미가 있어 07단계 전에 W-BE-A 수정이 필요하다.
- **미수행(PASS 로 세지 않음)**: 스크린리더(NVDA 등) 실청취, Edge/Firefox/Safari, 실기기 모바일 터치, Windows Docker Desktop, nginx 경유 CSP/속도 제한 실동작(V-05), PostgreSQL 17 실측(이번 실서버는 16), Python 3.12 이미지(이번은 3.13 임시 venv).
- 관찰(결함 아님, 사용자 판단 필요) — 질문 목록은 9절 아래.
  - OBS-1 제안 생성 작업이 *실패*로 끝나면 닫을 때 선택이 모두 지워짐(재시도하려면 다시 골라야 함, TC-VF-094에 현재 동작 기록).
  - OBS-2 용어 혼용: "제안 만들기" vs "제안 생성", "사전 점검"(버튼·제목) vs "미리보기"(설계 F-08 의 dry-run 번역).
  - OBS-3 375px 에서 가로 넘침 6화면(설계상 최소 1024px).
  - OBS-4 `client.ts` 의 연결 끊김·세션 만료 등 오류 기본 문구 7곳이 `ko.ts` 밖(F-08 문구 한곳 원칙, 실제 영향은 없음).
  - OBS-5 배치 만들기 승인 목록은 한 번에 200건까지만 불러옴(배치는 50건 상한이라 실사용 영향 낮음, 201건째부터는 안내 없음).
  - OBS-6 DEC-041 ⑤: 운영 빌드(`tsc -b`)가 `src` 의 시험 파일까지 컴파일해 시험 타입 오류가 빌드를 막을 수 있음 — **코드 미반영(알려진 미반영)**, 번들에는 시험 코드 0건.
  - OBS-7 ESLint 9.39.5 가 npm 에서 EOL 표시(노트 §9, jsx-a11y peer 범위 때문) — 기술부채.
- 후속 조치: ① W-BE-A: B01·B02 수정 후 `VF_LIVE_SETTLE_MS=0` 실서버 시험이 통과하는지 재확인 ② 07단계: nginx 경유 쿠키/CSP/속도 제한과 이번 실서버 시험 21건 재실행 ③ 사용자 결정(질문 Q1~Q5).

## 9. 결론 및 판정
- [ ] PASS
- [x] **CONDITIONAL PASS** — 조건: ① 백엔드 DEF-VF-B01(High, Open)이 W-BE-A 에서 수정·재검증될 것(또는 사용자가 위험을 수용하고 DEC 로 기록) ② 8절의 미수행 항목은 07단계 이후 환경에서 수행 ③ 사용자 질문 Q1~Q5 처리.
- [ ] FAIL
- 근거: 이 단위(`web/frontend/`)의 결함 16건은 모두 Fixed 이고 회귀 시험이 있으며, 최종 변이 점검에서 동치 3건을 뺀 96건 + 개별 확인 3건 모두 시험이 잡았고, 정적 검사·505건 통과·실서버 21건·실브라우저 axe(대비 포함) 위반 0 이다. 그러나 규칙상 Open 결함(백엔드 B01 High, B02 Low)이 남아 있으므로 PASS 가 아니다. 프런트 자체의 판정은 "백엔드 B01 해소 시 PASS" 이다.

### 사용자 질문 목록 (규칙 A)
- Q1. 용어를 하나로 통일할까요? ("제안 만들기"/"제안 생성", "사전 점검"/"미리보기") — 지금은 둘 다 쓰입니다.
- Q2. 1024px 미만(모바일) 화면은 지원 범위에 넣을까요? 지금은 설계상 비대상이라 375px 에서 가로 스크롤이 생깁니다.
- Q3. 백엔드 B01 이 고쳐지면 프런트의 "작업 404 재확인(0.5초×3)" 완화를 제거할까요, 방어로 유지할까요?
- Q4. AI 제안 생성 작업이 실패했을 때, 창을 닫아도 선택을 유지할까요?(현재는 지워짐, OBS-1)
- Q5. 승인 목록이 200건을 넘는 경우 안내가 필요한가요?(OBS-5)

## 10. 내부 검증 (최소 2회, `verification-log-template.md` 사용)
- 1차 검증(작성자 관점): 인수 조건 18개 전부에 시험을 연결하고(4-1), 기대 결과가 설계서·API.md·서버 코드에 근거하는지 확인. 이전 진행분 시험을 검토해 시험 설계 결함 4건(TD-1~4)을 고침. 정적 검사·전체 시험·커버리지 측정.
- 2차 검증(심사자 관점): 변이 점검 3회전+개별 확인(안전 로직 99+3개), 실서버 계약 연동 21건, 실브라우저 axe/흐름, 소스 직접 읽기(보안·접근성)로 새 결함 8건(DEF-VF-001~006, B01·B02) 발견 → 수정 → 회귀 시험.
- 3차 확인: 최종 코드에서 전체 시험·정적 검사 재실행(결함 0건 확인은 프런트 범위 한정), 변이 최종 회전 놓침 0(동치 제외).
- 검증 로그 파일 경로: `docs/harness/verify-log_web-WU-FE-test.md`

### 부록 A. 변이 점검(코드를 일부러 망가뜨려 시험이 실패하는지 확인) — 격리 사본(`.harness-tmp/vf/mut/`)에서만 적용, 원본 소스 무변경
> 각 변이는 대상 문자열이 소스에 **정확히 1곳** 인지 먼저 확인했다(1곳이 아니면 무효 처리). "잡음" = 시험이 실패해 변이를 검출. 1회전 71개, 2회전 96개(보강 후 + 신규 25개), 3회전 99개(최종 코드 전체), 4회전은 놓친 것·동치 재확인. 놓친 변이는 (a) 시험 보강 후 재점검 또는 (b) 동치 근거를 비고에 적었다. R 계열은 **내가 고친 결함을 되돌리는 변이**(수정 전 FAIL 증명 대용).
> 한계: `git` 사용이 금지되어 "이전 커밋 추출" 방식 대신, 수정 전 상태를 **변이(되돌림)** 와 이전 진행분의 expected-fail 기준선으로 증명했다.

| 변이 | 파일 | 내용 | 1회전 | 2회전 | 3회전(최종) | 4회전 | 비고 |
|---|---|---|---|---|---|---|---|
| M01 | api/client.ts | CSRF 헤더 부착 조건 반전 | 잡음 | 잡음 | 잡음 | - |  |
| M02 | api/client.ts | PATCH/DELETE 에 CSRF 미부착 | 잡음 | 잡음 | 잡음 | - |  |
| M03 | api/client.ts | 멱등키 헤더 조건 반전 | 잡음 | 잡음 | 잡음 | - |  |
| M04 | api/client.ts | 호출자가 넘긴 멱등키 무시(재시도마다 새 키) | 잡음 | 잡음 | 잡음 | - |  |
| M05 | api/client.ts | 세션 재발급 뒤 재시도에서 새 멱등키 | 잡음 | 잡음 | 잡음 | - |  |
| M06 | api/client.ts | PIN 오류 401 도 세션 만료로 처리 | 잡음 | 잡음 | 잡음 | - |  |
| M07 | api/client.ts | 모든 403 을 재발급 대상으로 | 잡음 | 잡음 | 잡음 | - |  |
| M08 | api/client.ts | 로그아웃 실패를 삼킴 | 잡음 | 잡음 | 잡음 | - |  |
| M09 | api/client.ts | 로그아웃 뒤 CSRF 토큰 잔존 | 잡음 | 잡음 | 잡음 | - |  |
| M10 | api/client.ts | PIN 미전송 | 잡음 | 잡음 | 잡음 | - |  |
| M11 | api/client.ts | 쿠키 미전송 | 잡음 | 잡음 | 잡음 | - |  |
| M12 | api/client.ts | Retry-After 를 429 아닌 응답에도 안내 | 잡음 | 잡음 | 잡음 | - |  |
| M13 | api/client.ts | 204 처리 제거 | 놓침 | 놓침 | 놓침 | 놓침 | 동치: 204 응답은 본문이 비어 있어 `res.text()` 가 빈 문자열 → 같은 `undefined` 반환 |
| M14 | api/client.ts | JSON 아닌 오류 코드 구분 상실 | 잡음 | 잡음 | 잡음 | - |  |
| M15 | api/client.ts | 시간 제한 10배 | 잡음 | 잡음 | 잡음 | - |  |
| M16 | api/client.ts | CSRF 토큰 없는 인증 허용 | 놓침 | 잡음 | 잡음 | - | 1회전 놓침 → TC-VF-220 추가 |
| M17 | api/client.ts | PIN 제출 시에도 PIN 화면 반복 | 잡음 | 잡음 | 잡음 | - |  |
| M18 | api/client.ts | 요청 내용이 바뀌어도 같은 멱등키 | 잡음 | 잡음 | 잡음 | - |  |
| M19 | api/client.ts | 지문 미저장(항상 새 키) | 잡음 | 잡음 | 잡음 | - |  |
| M20 | api/client.ts | 429 를 한도로 분류하지 않음 | 잡음 | 잡음 | 잡음 | - |  |
| M21 | pages/BatchDetailPage.tsx | 확인 문구 공백 허용 | 잡음 | 잡음 | 잡음 | - |  |
| M22 | pages/BatchDetailPage.tsx | 실행 성공 뒤 멱등키 유지 | 놓침 | 놓침 | 놓침 | 놓침 | 동치(도달 불가): 실행 성공 뒤 배치가 draft 가 아니어서 실행 입력 화면이 사라지므로 같은 멱등키를 다시 쓸 길이 없음 |
| M23 | pages/BatchDetailPage.tsx | 폴링 간격 10배 | 잡음 | 잡음 | 잡음 | - |  |
| M24 | lib/labels.ts | 중지된 배치를 진행 중으로 판단 | 잡음 | 잡음 | 잡음 | - |  |
| M25 | pages/BatchDetailPage.tsx | 실행 가능 항목 0건 차단 제거 | 잡음 | 잡음 | 잡음 | - |  |
| M26 | pages/HistoryPage.tsx | 롤백 영상 ID 대소문자·공백 허용 | 잡음 | 잡음 | 잡음 | - |  |
| M27 | pages/HistoryPage.tsx | 롤백 승인자 필수 제거 | 잡음 | 잡음 | 잡음 | - |  |
| M28 | pages/HistoryPage.tsx | 롤백 진행 중 Esc 로 닫힘 | 잡음 | 잡음 | 잡음 | - |  |
| M29 | pages/HistoryPage.tsx | 승인자가 바뀌어도 같은 멱등키 | 잡음 | 잡음 | 잡음 | - |  |
| M30 | pages/SuggestionCard.tsx | 엄격 모드 경고를 차단으로 보지 않음 | 잡음 | 잡음 | 잡음 | - |  |
| M31 | pages/SuggestionCard.tsx | 차단 제안의 승인 버튼 활성 | 잡음 | 잡음 | 잡음 | - |  |
| M32 | pages/SuggestionCard.tsx | 경고 확인 체크 없이 엔터로 승인 | 놓침 | 잡음 | 잡음 | - | 1회전 놓침 → TC-VF-221 추가 |
| M33 | pages/SuggestionCard.tsx | 경고 확인 체크 없이 승인 버튼 활성 | 잡음 | 잡음 | 잡음 | - |  |
| M34 | pages/SuggestionCard.tsx | 제목 길이 상한 경계 | 잡음 | 잡음 | 잡음 | - |  |
| M35 | pages/SuggestionCard.tsx | 동일 제목 저장 허용 | 잡음 | 잡음 | 잡음 | - |  |
| M36 | pages/SuggestionCard.tsx | 승인자 공백 정리 제거 | 잡음 | 잡음 | 잡음 | - |  |
| M37 | pages/BatchesPage.tsx | 배치 50건 상한 경계 | 잡음 | 잡음 | 잡음 | - |  |
| M38 | pages/BatchesPage.tsx | 선택 무시(전부 전송) | 잡음 | 잡음 | 잡음 | - |  |
| M39 | pages/SettingsPage.tsx | 하루 상한 20 경계 | 잡음 | 잡음 | 잡음 | - |  |
| M40 | pages/SettingsPage.tsx | 영상당 제안 1 경계 | 잡음 | 잡음 | 잡음 | - |  |
| M41 | pages/SettingsPage.tsx | 말투 5개 경계 | 잡음 | 잡음 | 잡음 | - |  |
| M42 | pages/SettingsPage.tsx | 말투 20자 경계 | 잡음 | 잡음 | 잡음 | - |  |
| M43 | pages/SettingsPage.tsx | PIN 최소 자릿수 | 잡음 | 잡음 | 잡음 | - |  |
| M44 | pages/SettingsPage.tsx | PIN 변경 시 현재 PIN 불필요 | 잡음 | 잡음 | 잡음 | - |  |
| M45 | pages/SettingsPage.tsx | PIN 해제에 현재 PIN 미전송 | 잡음 | 잡음 | 잡음 | - |  |
| M46 | components/Modal.tsx | 닫기 금지 대화상자가 Esc 로 닫힘 | 잡음 | 잡음 | 잡음 | - |  |
| M47 | components/Modal.tsx | Tab 순환 제거(마지막에서 밖으로) | 잡음 | 잡음 | 잡음 | - |  |
| M48 | components/Modal.tsx | 배경 inert 제거 | 잡음 | 잡음 | 잡음 | - |  |
| M49 | components/ConfirmPhrase.tsx | 확인 문구 표시 공백 허용 | 잡음 | 놓침 | 잡음 | - | 1회전 KILLED 는 무관한 시험(TC-WF-027)의 부하 실패(가짜 검출)로 판명 → 실제로는 놓침. TC-VF-231 추가로 해결 |
| M50 | components/Button.tsx | 진행 중 중복 클릭 허용 | 잡음 | 잡음 | 잡음 | - |  |
| M51 | pages/VideosPage.tsx | 제외 영상도 전체 선택 | 잡음 | 잡음 | 잡음 | - |  |
| M52 | pages/VideosPage.tsx | 쪽 크기 상한 | 잡음 | 잡음 | 잡음 | - |  |
| M53 | pages/VideosPage.tsx | 생성 200개 상한 경계 | 잡음 | 잡음 | 잡음 | - |  |
| M54 | pages/HomePage.tsx | 사용량 80% 경고 경계 | 잡음 | 잡음 | 잡음 | - |  |
| M55 | lib/format.ts | 표시 시간대 | 잡음 | 잡음 | 잡음 | - |  |
| M56 | components/TitleDiff.tsx | 변경 전 칸에 추가분 표시 | 잡음 | 잡음 | 잡음 | - | 3회전 killer 는 TC-WF-086(부하) → 개별 실행으로 TC-VF-115 가 잡음 확인(2회전도 TC-VF-115) |
| M57 | pages/ReportsPage.tsx | 원인 단정 금지 기본 문구 제거 | 잡음 | 잡음 | 잡음 | - |  |
| M58 | pages/HomePage.tsx | 홈 진행 작업 폴링 제거 | 잡음 | 잡음 | 잡음 | - |  |
| M59 | pages/JobPanel.tsx | 작업 폴링 제거 | 놓침 | 잡음 | 잡음 | - | 1회전 놓침 → TC-VF-228 추가 |
| M60 | components/ErrorPanel.tsx | 서버 hint 보다 기본 안내 우선 | 놓침 | 잡음 | 잡음 | - | 1회전 놓침 → TC-VF-222/229 추가 |
| R01 | api/client.ts | [수정 되돌림] 시간 제한 경쟁 제거 | 잡음 | 잡음 | 잡음 | - |  |
| R02 | api/client.ts | [되돌림] isLimit 느슨한 정규식 | 잡음 | 잡음 | 잡음 | - |  |
| R03 | pages/SettingsPage.tsx | [되돌림] 말투 입력 40자 제한 | 잡음 | 잡음 | 잡음 | - |  |
| R04 | pages/VideosPage.tsx | [되돌림] 작업 조회 실패 시 닫기 불가 | 놓침 | 잡음 | 잡음 | - | 1회전 놓침(TC-VF-095 가 Esc 를 확인하지 않음) → 시험 강화 |
| R05 | app/Layout.tsx | [되돌림] 오류 경계 제거 | 잡음 | 잡음 | 잡음 | - | 2회전 KILLED 는 문법 오류(닫는 태그 불일치)에 의한 무효 변이 → 3회전에서 유효 변이로 교체 |
| R06 | components/Pagination.tsx | [되돌림] 쪽 크기 목록 고정 | 잡음 | 잡음 | 잡음 | - |  |
| R07 | pages/HomePage.tsx | [되돌림] 불러오기 중복 시작 허용 | 잡음 | 잡음 | 잡음 | - |  |
| R08 | i18n/ko.ts | [되돌림] 배치 상태 queued 한글 없음 | 잡음 | 잡음 | 잡음 | - |  |
| R09 | lib/labels.ts | [되돌림] 라벨 조회 prototype 오인 | 잡음 | 잡음 | 잡음 | - |  |
| R10 | pages/BatchesPage.tsx | [되돌림] 중복 랜드마크 이름 | 잡음 | 잡음 | 잡음 | - |  |
| R11 | lib/format.ts | [되돌림] hour12:false | 놓침 | 놓침 | 잡음 | 놓침 | 환경 동치: 이 환경(Node 22/V8·ICU 77)에서 hour12:false 와 hourCycle:h23 이 같은 결과. 24시 표기 방지는 방어적 수정이며 TC-VF-203 이 h24 변이(X09)는 잡음 |
| X01 | pages/VideosPage.tsx | 생성 상한 200 경계 | - | 잡음 | 잡음 | - |  |
| X02 | pages/JobPanel.tsx | 404 재확인 횟수 | - | 잡음 | 잡음 | - |  |
| X03 | pages/JobPanel.tsx | 404 외 오류도 재확인 | - | 잡음 | 잡음 | - |  |
| X04 | app/ErrorBoundary.tsx | 화면 이동해도 오류 화면 유지 | - | 잡음 | 잡음 | - |  |
| X05 | app/Layout.tsx | 오류 경계 reset 키 고정 | - | 잡음 | 잡음 | - |  |
| X06 | pages/HomePage.tsx | 작업 조회 실패 후 버튼 영구 잠금 | - | 잡음 | 잡음 | - |  |
| X07 | pages/HomePage.tsx | 작업 종료 후 버튼 영구 잠금 | - | 잡음 | 잡음 | - |  |
| X08 | pages/SuggestionCard.tsx | 엄격 모드 경고 배지가 '경고'로 표시 | - | 잡음 | 잡음 | - |  |
| X09 | lib/format.ts | 24시 표기 | - | 잡음 | 잡음 | - |  |
| X10 | components/Pagination.tsx | 쪽 크기 목록 문자열 정렬 | - | 잡음 | 잡음 | - |  |
| X11 | pages/VideosPage.tsx | 새 작업에 이전 오류 상태 유지 | - | 놓침 | 잡음 | - | 2회전 놓침 → TC-VF-236 추가, 3회전 잡음 |
| X12 | pages/BatchesPage.tsx | 선택 수 표시에 사라진 항목 포함 | - | 잡음 | 잡음 | - |  |
| X13 | api/client.ts | 시간 제한 타이머 정리 제거 | - | 잡음 | 잡음 | - |  |
| X14 | api/client.ts | 중단 신호 리스너 정리 제거 | - | 잡음 | 잡음 | - |  |
| X15 | api/client.ts | 시간 초과 시 offline 표시 안 함 | - | 잡음 | 잡음 | - |  |
| X16 | lib/labels.ts | 취소된 작업을 진행 중으로 판단 | - | 잡음 | 잡음 | - |  |
| X17 | pages/SettingsPage.tsx | 말투 입력 길이 제한 100 | - | 잡음 | 잡음 | - |  |
| X18 | components/Modal.tsx | 대화상자 닫힐 때 포커스 복귀 제거 | - | 잡음 | 잡음 | - | 3회전 killer 는 TC-VF-095(부하 실패 추정) → 개별 실행으로 TC-VF-058 이 잡음을 확인 |
| X19 | app/Layout.tsx | 화면 이동 시 제목 포커스 제거 | - | 잡음 | 잡음 | - |  |
| X20 | app/PinForm.tsx | [되돌림] 403 도 틀린 PIN 으로 안내 | - | 놓침 | 잡음 | - | 2회전 놓침 → 수정(DEF-VF-004)과 TC-VF-232 로 3회전 잡음 |
| X21 | pages/HistoryPage.tsx | 롤백 불가 항목에도 버튼 | - | 잡음 | 잡음 | - |  |
| X22 | components/ErrorPanel.tsx | 한도 오류 톤 구분 제거 | - | 놓침 | 잡음 | - | 2회전 놓침 → TC-VF-235 추가. 3회전 killer 는 TC-VF-095(부하) → 개별 실행으로 TC-VF-235 가 잡음 확인 |
| X23 | api/client.ts | 이미 중단된 신호 전달 제거(문법 유지) | - | 잡음 | 잡음 | - | 2·3회전 KILLED 는 문법 오류(else 단독)에 의한 무효 변이 → 문법 유지 변이로 교체해 TC-VF-197 이 잡음을 개별 확인 |
| X24 | pages/SuggestionCard.tsx | 엄격 모드: 검증 전(null)을 허용 | - | 잡음 | 잡음 | - |  |
| X25 | pages/BatchDetailPage.tsx | 서버 확인 문구 무시 | - | 잡음 | 잡음 | - |  |
| Y01 | app/PinForm.tsx | 틀린 PIN 안내 제거 | - | - | 잡음 | - |  |
| Y02 | app/PinForm.tsx | 빈 PIN 제출 허용 | - | - | 놓침 | 잡음 | 3회전 놓침 → TC-VF-237 추가, 4회전에서 잡음 |
| Y03 | pages/JobPanel.tsx | 404 재확인 간격 10배 | - | - | 잡음 | - |  |
| Y04 | pages/HomePage.tsx | 라이브 켜짐 표시 반전 | - | - | 개별 확인: 잡음 | - |  |
| Y05 | pages/HomePage.tsx | 라이브 켜짐을 항상 꺼짐으로 표시 | - | - | 개별 확인: 잡음 | - |  |
| Y06 | pages/VideosPage.tsx | 생성 오류 창 Esc 로 닫히지 않음 | - | - | 개별 확인: 잡음 | - |  |

| 회전 | 변이 수 | 잡음 | 놓침 | 비고 |
|---|---|---|---|---|
| 1회전 | 71 | 63 | 8 | 놓침 8 중 M49 는 가짜 검출이었음이 나중에 판명(실제 놓침 9) → 시험 보강 |
| 2회전 | 96 | 89 | 7 | 무효 변이 2(R05, X23: 문법 오류)가 "잡음"에 섞임 → 3회전에서 교체 |
| 3회전(최종) | 99 | 96 | 3 | 놓침 3 = 동치 2(M13, M22) + Y02 → TC-VF-237 추가. 환경 동치 R11 은 부하 실패로 가짜 검출되어 개별 확인에서 "놓침(동치)" 로 정정 |
| 4회전(놓침 재점검) + 개별 확인 | 4 + 7 | Y02 잡음 + Y04~Y06·X18·X22·X23·M56 개별 잡음 | 동치 3 | **마지막 회전 놓침 0(동치 M13·M22·R11 제외)** |

### 부록 B. 공유 문서 갱신 요청 (오케스트레이터가 반영 — 직접 수정하지 않음)
| 문서 | REQ-ID/항목 | 컬럼 | 값 |
|---|---|---|---|
| `traceability.md` | F-01, F-02(타입 생성 제외), F-04~F-11, S-W02·S-W03·S-W04(프런트 측)·S-W05 | 단위테스트 | TC-VF-001~241, 300~320(실서버) + TC-WF-001~095, 판정 CONDITIONAL PASS(백엔드 B01 Open) |
| `traceability.md` | F-03 | 단위테스트 / 비고 | TC-VF-084~091, 151~157, 204, 211~213 (가상 스크롤 미적용은 설계 §6 완화) |
| `decisions.md` | 기록 요청 | — | ① JobPanel 404 재확인(0.5초×3) 프런트 완화(백엔드 B01 의 임시 대응) ② 엄격 모드 경고=차단을 프런트도 서버와 동일하게 표시 ③ 요청 시간 제한 30초 ④ 쪽 크기 선택지에 URL 값 추가 ⑤ 한 번에 제안 생성 영상 수 상한 200(API.md) 프런트 가드 ⑥ ErrorBoundary 도입 |
| `DESIGN.md` Part B | 검증 대기 표 V-03 | 상태 | 완료(조건부): DV-W09 타입 불일치는 `queued/done/paused` 표기와 실서버 폴링으로 확인(활성=queued/running, 종료=done/cancelled), NFR-W10 색 대비는 **실브라우저 axe 로 측정 완료**(위반 0, 라이트/다크) |
| `DESIGN.md` Part B | V-08 | 비고 | DEC-041 ⑤ 코드 미반영 재확인(번들엔 시험 코드 0건) |
| 백엔드 단위(W-BE-A) | 결함 | — | DEF-VF-B01(High), DEF-VF-B02(Low) — 재현 절차 6절 |
