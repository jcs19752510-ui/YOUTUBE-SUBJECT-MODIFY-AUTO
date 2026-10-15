# 관리자 로그인 프런트 시험 결과서 (DEC-055, 프런트 담당)

- 시작 2026-10-15 02:20:06 UTC, 종료 약 02:25 UTC (실제 소요 약 5분, `date -u` 측정). 하드 상한 12분 이내.
- 범위: `web/frontend/src/**`만. 백엔드·docs 계약 외 파일은 수정하지 않음. git add/commit/push 안 함.

## 한 것
- `api/types.ts`: `AuthMe`에 `login_required?`·`admin_login_id?`·`idle_timeout_seconds?`, `LoginResponse` 추가.
- `api/client.ts`: 상태 `login_required`; `/auth/me`가 `login_required`이면 익명 `POST /auth/session` 없이 상태 전환 후 ApiError(`login_required`); `login()`; 로그인 모드에서 사용 중 401은 조용한 재발급 없이 `login_required`+`expired` 후 `session_expired` 오류; `logout()`은 로그인 모드면 `login_required`, 그 외 `loggedout` 유지; `markExpired()`, `adminLoginId`·`idleTimeoutSeconds` 접근자. PIN/비로그인 경로는 `loginMode`가 아닐 때 기존 코드 그대로.
- `app/LoginForm.tsx`(새), `app/IdleLogout.tsx`(새), `app/AuthGate.tsx`(login_required 전체 화면 교체·`queryClient.clear()`·online 자식 옆에 IdleLogout 마운트), `app/Layout.tsx`(아이디 표시, 기존 로그아웃 버튼 재사용), `i18n/ko.ts`(`ko.login.*`).
- 자동 로그아웃: `Date.now()` 차이 계산, 1초 간격, visibilitychange 즉시 재계산, 경고 = 한도 5분 전(한도가 짧으면 한도의 1/6, 최소 1초), 경고 중에는 마우스 이동으로 연장되지 않고 "계속 사용" 버튼만(`GET /auth/me` 호출 + 리셋), 한도 도달 시 `logout()`(실패해도) 후 만료 안내. 활동 스로틀 1초. 사용자 조작만 있고 요청이 없어 서버 마지막 사용 시각이 한도의 1/4 넘게 오래되면 `GET /auth/me`로 미리 갱신(설계서에 없는 추가 동작).
- 시험 신규 20개: `src/app/adminLogin.test.tsx` (client 5, LoginForm 4, AuthGate 2, IdleLogout 8, Layout 1).

## 시험 결과
| 실행 | 결과 |
|---|---|
| 신규 시험 첫 실행 | 20 중 13 통과, **7 실패** (모두 시험 코드 문제: ①`role=alert/status`가 토스트 영역과 겹쳐 다중 일치 4건 ②가짜 타이머에서 `findBy*`(내부 setTimeout 사용)가 멈춰 시간 초과 3건). 구현은 바꾸지 않고 시험의 조회 방법만 `getByText`/`getBy*`로 고침 |
| 신규 시험 재실행 | 20/20 통과 |
| 전체 `npx vitest run` | 47 파일 통과·1 건너뜀, **953 통과**(기존 933 + 신규 20), 1 expected fail·21 skipped(기존부터), 실패 0 |
| `npx eslint src` | 오류 0 (중간에 `Date.now()` 렌더 중 호출 규칙 위반 1건 → `useRef(0)`로 수정) |
| `npx tsc --noEmit` | 오류 0 |
| `npm run build` | 성공 |
기존 시험의 기대값은 하나도 바꾸지 않았다.

## 안 한 것 / 미확인
- 실제 브라우저(Chrome)에서 로그인 화면·모달·자동 로그아웃 확인: **미수행**. 가짜 fetch와 가짜 타이머로만 확인.
- 실제 백엔드와의 통합(응답 필드명·`Retry-After` 헤더·쿠키 동작): **미확인**, 계약(§3)대로 가정. 429 문구는 서버 `hint` + `Retry-After` 초 안내에 의존.
- 휴대폰 폭은 지원 대상 아님(CLAUDE.md 확정).
- 활동 이벤트 시험은 `mousemove`만 검증(키 입력·터치·스크롤은 같은 핸들러를 쓰지만 개별 시험 없음).
- 다른 탭과 로그아웃 동기화는 구현 안 함.
- 비밀번호 manager 자동 완성 동작은 미확인(autocomplete 속성만 확인).
