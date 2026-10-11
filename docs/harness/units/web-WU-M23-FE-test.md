# 테스트 결과서 — M23-FE 프런트 (W-FIX-FE 재검증 + M2 단위4 + M3 단위3, 6단계 독립 검증)

> 작성: 6단계 독립 검증 에이전트(임시 폴더 `cap_m23`, 변이 사본 폴더는 정리함), 2026-10-11. 구현자의 시험(`src/pages/*.test.tsx`, `verify_fix/`)을 믿지 않고 사용자(비개발자 채널 소유자) 관점으로 `web/frontend/verify_m23/` 시험(TC-VMF)을 새로 만들었다. **소스(`web/frontend/src`)는 한 줄도 고치지 않았다**(결함은 재현 절차와 함께 보고).

**한 줄 결론: CONDITIONAL PASS.** 요청 범위의 기능(차단 카드·초안 버리기·A/B 확인·면책 위치·구글 연결/해제/불러오기·쓰기 권한 구역)은 동작하지만, **화면 안내가 서로 모순되는 결함 1건(High)과 Low 3건이 열려 있다.** 구현자 시험의 실패 2건(TC-VWF-005, 012)은 **시험 코드 문제**로 판정했고 화면 결함이 아니다.

## 1. 개요
- 테스트 대상 (모듈/기능): 모듈 3개 묶음 — ① W-FIX-FE(면책·AI 고지·AI 한계/표시광고 안내·A/B 확인 문구, 차단 제안 카드 버튼 C-1, 초안 배치 버리기 C-2) ② M2 단위4 `src/pages/GoogleCard.tsx`(구글 연결·해제·내 영상 불러오기·오류 안내) ③ M3 단위3 같은 카드의 "제목 수정 권한" 구역
- 테스트 유형: 단위(화면 단위, jsdom) + 실브라우저(Chromium, 모의 서버) 증빙. 통합(07)·백엔드 연동 시험은 아님.
- 적용 Tier: Standard (규칙 B 원문: 최소 2회 검증 — 3회 수행)
- 적용 속도 트랙: L3(표기 없음 → 기본, 전 섹션 작성)
- 병렬 실행 정보: 병렬 웨이브에서 실행 추정 — 같은 시각 백엔드 쪽 `web/backend/tests/verify_m23/`, `web/tests_infra/` 변경이 작업 트리에 보였음(다른 검증자 소유, 건드리지 않음). 06·07 병합 적용 안 함.
- 테스트 목적: 사용자가 이해·조작할 수 없거나 거짓 안내가 있으면 제품 결함이라는 기준으로 안내 문구의 진실성·버튼 노출 조건·확인 절차·오류 안내를 증명한다.
- 관련 산출물: `docs/yt/WEB_DESIGN.md`, `docs/yt/04_ux_design.md`, `docs/harness/decisions.md`(DEC-046~048), `docs/harness/security-web-m1-test.md`(DEF-9-007·008), `docs/harness/feature-web-m1-integration-test.md`(DEF-7-008 C-1, DEF-7-009 C-2)
- 테스트 수행자(에이전트): 06단계 독립 검증 에이전트(M23-FE)
- 테스트 일시: 2026-10-11

## 2. 테스트 범위 및 제외 범위
- 범위 (In-Scope)
  - `GoogleCard`: 연결 파일 없음/미연결/연결됨/쓰기 연결됨(수정 꺼짐)/실제 수정 가능 5상태의 문구·버튼 노출, 연결·쓰기 연결·불러오기·해제의 요청 경로·중복 클릭 방지·실패 안내, 마지막 오류 안내, 상태 조회 실패/로딩, axe 접근성, 서버가 만들 수 있는 상태 조합 속성 시험
  - C-1 차단 제안 카드(4가지 차단 유형, 승인 비활성·사유·수정/반려 가능·경계값 100/101자), 승인 대화상자 규칙
  - C-2 초안 버리기(상세·목록, 취소/확정/실패/연타/비초안 배치)
  - A/B 확인 문구와 실행 버튼 조건, 서버로 가는 본문
  - 면책·AI 고지가 실제 App 화면 어디에 나오는지(푸터·본문·대화상자), 숨김 처리 여부
  - 상단 모드 배지·홈 상태 카드가 현재 모드에 대해 사실인지
  - 구현자 시험 `verify_fix/notice.verify.test.tsx` 실패 2건의 원인 판정
- 제외 범위(Out-of-Scope) 및 사유
  - 실제 FastAPI 백엔드·PostgreSQL 연동 → **미수행(사유: 15분 상한, 클라우드 PostgreSQL 기동·마이그레이션 시간. 대신 저장소 `web/frontend/dev/mock-server.mjs` 모의 서버로 Chromium 증빙). 잔여 위험: 실제 응답 모양 차이(다만 `dashboard.py`·`google.py` 를 직접 읽어 응답 모양을 확인하고 시험 응답에 반영함)**
  - 실제 구글 로그인·실제 제목 수정 → 연결돼 있지 않음(대상 아님, 승인 없이 실행 금지)
  - 스크린리더·Edge/Firefox·실기기 → 환경 없음(미수행)
  - 백엔드 쓰기 안전장치(`live_guard`) → 다른 검증 단위

## 3. 테스트 환경
- 실행 환경: Linux 6.18, Node 22.x, Vitest 5.0.3 + jsdom 30.1.2 + Testing Library, axe-core 4.14.0. 실브라우저 Chromium 1194(`/opt/pw-browsers/chromium`, 저장소 밖 `/opt/node-tools` 의 playwright-core 로 구동, `playwright install` 안 함), 뷰포트 1280x900.
- 테스트 데이터: 시험 내 가짜 응답과 `dev/mock-server.mjs`(데모 영상 200개). 구글 상태·차단 제안은 브라우저에서 응답 가로채기로 주입. 실제 구글·AI·유튜브 호출 없음.
- 전제 조건: `web/frontend/node_modules` 사용, `dist/` 는 `npm run build` 로 방금 빌드.
- 재실행 방법: `cd web/frontend && npx vitest run verify_m23 verify_fix` (약 20초). 브라우저 증빙: `.harness-tmp/cap_m23/cap.mjs`, `cap2.mjs` (이 폴더는 정리 대상이 아니라 증빙으로 남김).
- 시험 설계 원칙: 기대값은 구현이 아니라 "사용자에게 사실인가·조작 가능한가"에서 도출했다. 실패한 시험의 기대값을 구현에 맞춰 고치지 않았다.

## 4. 테스트 케이스 및 결과
> ID 는 `TC-VMF-nnn`(M23-FE 독립 시험, 파일 `web/frontend/verify_m23/google.verify.test.tsx`(TC-VMF-001~042), `wfix.verify.test.tsx`(TC-VMF-100~142)). 아래 66건은 **최종 실행(3회차)** 결과이며, 첫 실행 결과(실패 포함)는 4-2에 그대로 남긴다.

### 4-1. jsdom 시험 (verify_m23, 66건: 통과 60 / 실패 6)

| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-VMF-001 | 클라이언트 파일 없음: 준비 방법 안내, 어떤 버튼도 없고 쓰기 구역도 없다 | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-001"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M2 단위4 |
| TC-VMF-002 | 준비됨·미연결: [구글 계정 연결]만 보이고 불러오기·해제·쓰기 구역은 없으며 "읽기 전용" 안내가 있다 | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-002"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M2 단위4 |
| TC-VMF-003 | [구글 계정 연결]은 POST /google/connect 후 받은 주소로 이동하고, 중복 클릭해도 요청은 1번 | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-003"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M2 단위4 |
| TC-VMF-004 | 연결 시작이 409(연결 파일 문제)로 실패하면 이동하지 않고 한국어 오류 안내가 보인다 | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-004"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M2 단위4 |
| TC-VMF-010 | 연결됨: [내 영상 불러오기]와 [연결 해제]가 보이고 [구글 계정 연결]은 사라진다 | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-010"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M2 단위4 |
| TC-VMF-011 | [내 영상 불러오기]는 POST /videos/sync 를 1번 보내고 시작 안내를 보인다 | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-011"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M2 단위4 |
| TC-VMF-012 | 불러오기 실패(예: 할당량 초과 429)는 오류 안내가 보이고 시작 안내는 없다 | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-012"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M2 단위4 |
| TC-VMF-013 | 연결 해제는 확인을 한 번 더 묻고, 취소하면 요청이 없으며, 확인하면 POST /disconnect 후 상태를 다시 읽는다 | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-013"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M2 단위4 |
| TC-VMF-014 | 연결 해제 실패(500)면 확인창이 유지되고 오류가 보이며 "해제했습니다" 안내는 없다 | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-014"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M2 단위4 |
| TC-VMF-014b | 해제 확정 버튼을 연타해도 해제 요청은 1번(응답이 느릴 때) | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-014b"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M2 단위4 |
| TC-VMF-015 | 마지막 오류가 있으면 경고 안내(role=alert)로 보이고, "데모" 단어가 있을 때만 초기화 힌트가 붙는다 | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-015"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M2 단위4 |
| TC-VMF-016 | last_error 가 null/빈 문자열이면 오류 안내 칸이 나오지 않는다 | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-016"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M2 단위4 |
| TC-VMF-017 | 상태 조회 실패는 "확인하지 못했습니다"를 보이고 버튼은 만들지 않는다(거짓으로 연결됨 표시 금지) | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-017"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M2 단위4 |
| TC-VMF-020 | 쓰기 미연결: 설명과 [제목 수정 권한 연결]이 있고, 설명은 "권한만으로 제목이 바뀌지 않는다"를 알린다 | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-020"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M3 단위3 |
| TC-VMF-021 | [제목 수정 권한 연결]은 POST /google/connect-write(읽기용 connect 와 다른 경로) 후 이동한다 | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-021"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M3 단위3 |
| TC-VMF-022 | 쓰기 연결 요청이 실패하면 이동하지 않고 오류가 보이며 다시 누를 수 있다 | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-022"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M3 단위3 |
| TC-VMF-023 | 쓰기 연결됨·실제 수정 꺼짐: "연결돼 있습니다"+"아직 꺼져 있습니다"+허용 영상 수, 연결 버튼은 사라지고, 거짓 안내("제목을 바꾸지 않습니다")는 없다 | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-023"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M3 단위3 |
| TC-VMF-024 | 쓰기 연결·꺼짐 상태의 허용 영상 수 0개가 문구에 그대로 나온다 | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-024"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M3 단위3 |
| TC-VMF-024 | 쓰기 연결·꺼짐 상태의 허용 영상 수 1개가 문구에 그대로 나온다 | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-024"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M3 단위3 |
| TC-VMF-024 | 쓰기 연결·꺼짐 상태의 허용 영상 수 3개가 문구에 그대로 나온다 | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-024"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M3 단위3 |
| TC-VMF-024 | 쓰기 연결·꺼짐 상태의 허용 영상 수 200개가 문구에 그대로 나온다 | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-024"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M3 단위3 |
| TC-VMF-025 | live_allowed_count 가 응답에 없어도(undefined) "undefined"/NaN 대신 0개로 보인다 | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-025"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M3 단위3 |
| TC-VMF-026 | 실제 수정 가능: 경고 제목+허용 영상 수+되돌리기 한계, role=alert, 이전 안내("꺼져 있습니다"·"읽기 전용"·연결 버튼)는 없다 | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-026"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M3 단위3 |
| TC-VMF-027 | 실제 수정 가능이지만 연결 해제는 여전히 가능하고(확인 2단계), 불러오기도 가능하다 | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-027"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M3 단위3 |
| TC-VMF-028 | 모든 상태 조합(연결·쓰기연결·수정켜짐·허용수·ready)에서 화면 문구가 사실과 모순되지 않는다(속성 시험 64조합) | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-028"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 불일치(첫 실행부터 동일하게 실패, 재실행 결과 동일) | **Fail** | M3 단위3 → DEF-VMF-002 |
| TC-VMF-029 | 실제 수정은 서버에서 켜졌지만(live_write_enabled) 허용 영상이 0개면 "꺼져 있습니다"가 사실인가 — 켜려면 안내가 현재 상태와 맞아야 한다 | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-029"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 불일치(첫 실행부터 동일하게 실패, 재실행 결과 동일) | **Fail** | M3 단위3 → DEF-VMF-003 |
| TC-VMF-030 | 쓰기 구역 제목·안내에 개발자용 설정 이름이 있으면 비개발자가 실행할 방법도 함께 안내돼야 한다(조작 가능성) | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-030"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 불일치(첫 실행부터 동일하게 실패, 재실행 결과 동일) | **Fail** | M3 단위3 → DEF-VMF-004 |
| TC-VMF-040 | 모든 대표 상태에서 axe 위반이 없다(미연결/연결/쓰기연결/수정가능) | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-040"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M3 단위3 |
| TC-VMF-041 | 상태 확인 중에는 "확인하는 중" 안내만 있고 버튼이 없다 | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-041"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M3 단위3 |
| TC-VMF-042 | 읽기 전용 문구와 수정 가능 경고가 동시에 보이는 일은 없다(상호 배타) | GoogleCard 단독 렌더 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-042"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | M3 단위3 |
| TC-VMF-100 | 검증 차단: 승인은 막히고 이유가 카드에 있으며 [제목 수정]·[반려]는 누를 수 있다 | 영상 상세 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-100"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE C-1(DEF-7-008) |
| TC-VMF-100 | 상태 blocked: 승인은 막히고 이유가 카드에 있으며 [제목 수정]·[반려]는 누를 수 있다 | 영상 상세 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-100"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE C-1(DEF-7-008) |
| TC-VMF-100 | 엄격 모드+경고(건강·금융): 승인은 막히고 이유가 카드에 있으며 [제목 수정]·[반려]는 누를 수 있다 | 영상 상세 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-100"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE C-1(DEF-7-008) |
| TC-VMF-100 | 엄격 모드+검증 전: 승인은 막히고 이유가 카드에 있으며 [제목 수정]·[반려]는 누를 수 있다 | 영상 상세 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-100"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE C-1(DEF-7-008) |
| TC-VMF-101 | 이유가 서버에서 오지 않은 차단도 빈 안내가 아니라 "사유는 위 검증 사유를 확인" 안내가 나온다 | 영상 상세 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-101"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE C-1(DEF-7-008) |
| TC-VMF-102 | 차단 이유 목록은 error/block 심각도 사유만 보이고 정보성 사유는 차단 이유로 나오지 않는다 | 영상 상세 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-102"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE C-1(DEF-7-008) |
| TC-VMF-100b | 서버 상태가 blocked 이면 검증 결과가 pass 여도 승인은 막힌다(상태 단독 판정) | 영상 상세 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-100b"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE C-1(DEF-7-008) |
| TC-VMF-100b | 서버 상태가 blocked 이면 검증 결과가 none 여도 승인은 막힌다(상태 단독 판정) | 영상 상세 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-100b"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE C-1(DEF-7-008) |
| TC-VMF-100b | 서버 상태가 blocked 이면 검증 결과가 warn 여도 승인은 막힌다(상태 단독 판정) | 영상 상세 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-100b"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE C-1(DEF-7-008) |
| TC-VMF-102b | 심각도가 block 인 사유(error 가 아님)도 차단 이유로 보인다 | 영상 상세 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-102b"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE C-1(DEF-7-008) |
| TC-VMF-103 | 통과 제안과 엄격 모드 통과 제안에는 차단 안내가 없고 승인 버튼이 켜져 있다 | 영상 상세 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-103"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE C-1(DEF-7-008) |
| TC-VMF-104 | 이미 승인·반영 완료·반려된 제안에는 차단 안내와 승인 버튼이 없다(상태 거짓 표시 금지) | 영상 상세 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-104"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE C-1(DEF-7-008) |
| TC-VMF-105 | 차단 카드에서 [제목 수정]: 빈 값·같은 값·101자는 저장 불가, 100자는 저장되어 PATCH 로 trim 된 제목이 간다 | 영상 상세 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-105"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE C-1(DEF-7-008) |
| TC-VMF-106 | 차단 카드에서 [반려]는 확인 후 POST reject, 취소하면 요청 없음 | 영상 상세 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-106"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE C-1(DEF-7-008) |
| TC-VMF-107 | 차단 제안이어도 키보드/강제 제출로 승인 요청이 서버에 가지 않는다(화면 방어) | 영상 상세 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-107"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE C-1(DEF-7-008) |
| TC-VMF-108 | 승인 대화상자: 승인자 이름이 비면 승인 불가, 경고 제안은 확인란 체크 전에는 승인 불가, 둘 다 하면 POST approve | 영상 상세 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-108"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE C-1(DEF-7-008) |
| TC-VMF-110 | 초안 상세에 [초안 버리기]가 있고, 누르면 "제목은 그대로" 안내가 있는 확인창, 취소하면 요청이 없다 | 배치 화면 + 상태를 기억하는 가짜 서버(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-110"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE C-2(DEF-7-009) |
| TC-VMF-111 | 확인하면 POST cancel 1번, 완료 안내(토스트)·"버려진 초안" 표시, 실행 영역과 버리기 버튼이 사라진다 | 배치 화면 + 상태를 기억하는 가짜 서버(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-111"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE C-2(DEF-7-009) |
| TC-VMF-112 | 버리기 실패(409: 이미 취소됨)면 확인창이 남고 오류가 보이며 "버렸습니다" 안내는 없다 | 배치 화면 + 상태를 기억하는 가짜 서버(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-112"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE C-2(DEF-7-009) |
| TC-VMF-113 | 확인 버튼을 연타해도 서버 요청은 1번(응답이 느릴 때) | 배치 화면 + 상태를 기억하는 가짜 서버(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-113"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE C-2(DEF-7-009) |
| TC-VMF-114 | 진행 중(running)·완료·실행 전 취소가 아닌 취소(실행 이력 있음) 배치에는 [초안 버리기]가 없다 | 배치 화면 + 상태를 기억하는 가짜 서버(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-114"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE C-2(DEF-7-009) |
| TC-VMF-115 | 목록의 초안 행에만 [초안 버리기]가 있고, 구별용 숨은 이름에 배치 번호가 들어 있다 | 배치 화면 + 상태를 기억하는 가짜 서버(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-115"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE C-2(DEF-7-009) |
| TC-VMF-120 | 확인 문구·설명·"필요" 안내가 보이고 실행은 잠겨 있다 | 배치 상세 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-120"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE A/B 확인(DEF-7-011) |
| TC-VMF-121 | 확인란만 체크 / 확인 문구만 입력 / 둘 다 → 둘 다일 때만 실행 가능, 체크를 풀면 다시 잠기고 안내가 돌아온다 | 배치 상세 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-121"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE A/B 확인(DEF-7-011) |
| TC-VMF-122 | 실행하면 confirm_text 만 서버로 가고 A/B 확인 값은 서버에 보내지 않는다(DEC-047 데모 단계 화면 전용) | 배치 상세 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-122"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE A/B 확인(DEF-7-011) |
| TC-VMF-123 | 모든 항목이 차단이면 A/B 확인란·실행 버튼 없이 "모두 제외" 안내만 나온다 | 배치 상세 + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-123"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE A/B 확인(DEF-7-011) |
| TC-VMF-130 | 영상 상세 화면: 면책은 본문(제안 목록 위)과 화면 맨 아래 푸터 두 곳에 있고 AI 고지는 푸터와 각 AI 제안 카드에 있다 | App 전체(Layout 포함) + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-130"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE 면책·AI 고지(DEF-9-007·008) |
| TC-VMF-131 | / 화면에서 푸터 면책은 정확히 1번 보이고 숨김(hidden/aria-hidden/display:none) 처리가 아니다 | App 전체(Layout 포함) + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-131"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE 면책·AI 고지(DEF-9-007·008) |
| TC-VMF-131 | /videos 화면에서 푸터 면책은 정확히 1번 보이고 숨김(hidden/aria-hidden/display:none) 처리가 아니다 | App 전체(Layout 포함) + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-131"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE 면책·AI 고지(DEF-9-007·008) |
| TC-VMF-131 | /batches 화면에서 푸터 면책은 정확히 1번 보이고 숨김(hidden/aria-hidden/display:none) 처리가 아니다 | App 전체(Layout 포함) + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-131"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE 면책·AI 고지(DEF-9-007·008) |
| TC-VMF-131 | /history 화면에서 푸터 면책은 정확히 1번 보이고 숨김(hidden/aria-hidden/display:none) 처리가 아니다 | App 전체(Layout 포함) + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-131"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE 면책·AI 고지(DEF-9-007·008) |
| TC-VMF-131 | /reports 화면에서 푸터 면책은 정확히 1번 보이고 숨김(hidden/aria-hidden/display:none) 처리가 아니다 | App 전체(Layout 포함) + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-131"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE 면책·AI 고지(DEF-9-007·008) |
| TC-VMF-131 | /settings 화면에서 푸터 면책은 정확히 1번 보이고 숨김(hidden/aria-hidden/display:none) 처리가 아니다 | App 전체(Layout 포함) + 가짜 fetch(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-131"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 일치 | Pass | W-FIX-FE 면책·AI 고지(DEF-9-007·008) |
| TC-VMF-140 | 실제 모드(dashboard.mode=live)인데도 상단 배지가 "유튜브에 아무것도 전송되지 않습니다"라고 하면 거짓 안내 | App 전체 + 실제 백엔드가 보내는 모양의 가짜 응답(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-140"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 불일치(첫 실행부터 동일하게 실패, 재실행 결과 동일) | **Fail** | M2/M3 안내의 진실성(DEC-048) → DEF-VMF-001 |
| TC-VMF-141 | 구글 읽기 연결 상태(실제 영상 목록을 읽는 중)에서 상단 배지가 "데모 모드"라고만 하면 현재 상태와 맞지 않는다 | App 전체 + 실제 백엔드가 보내는 모양의 가짜 응답(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-141"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 불일치(첫 실행부터 동일하게 실패, 재실행 결과 동일) | **Fail** | M2/M3 안내의 진실성(DEC-048) → DEF-VMF-001 |
| TC-VMF-142 | 구글 상태가 live_write_ready=true 인 화면 전체에서 "유튜브에 아무것도 전송되지 않습니다"·"실제 반영(라이브): 꺼짐"이 함께 보이면 서로 모순되는 거짓 안내 | App 전체 + 실제 백엔드가 보내는 모양의 가짜 응답(jsdom) | `npx vitest run verify_m23 -t "TC-VMF-142"` | 제목 문장에 적힌 사용자 관점 기대(문구가 사실이고 조작 가능) | 기대와 불일치(첫 실행부터 동일하게 실패, 재실행 결과 동일) | **Fail** | M2/M3 안내의 진실성(DEC-048) → DEF-VMF-001 |

### 4-2. 첫 실행 결과와 시험 수정 이력 (그대로 기록)

**(가) 구현자 시험 `verify_fix/notice.verify.test.tsx` — 알려진 실패 2건의 원인 판정 (판정: 시험 코드 문제, 화면 결함 아님)**

| 시험 | 첫 실행 결과(수정 전) | 원인 | 판정 | 조치 |
|---|---|---|---|---|
| TC-VWF-005 | 실패: `TypeError: Cannot read properties of null (reading 'querySelectorAll')` (`document.querySelector('main')` 가 null) | 시험이 `Layout` 없이 `VideoDetailPage` 만 그려 `<main>` 이 없다. 앞부분(면책이 본문에 있음)은 통과했다. 이를 고치자 **두 번째 시험 결함**이 나왔다: `findByText('두번째')` 가 카드 제목·비교 표 2곳에서 중복 오류 | 시험 코드 문제 | `main` 대신 `document.body` 로 세고(레이아웃 없는 렌더라 푸터가 없음), `findAllByText` 로 변경. 기대(본문 면책 1번)는 그대로 |
| TC-VWF-012 | 실패: `Unable to find an accessible element with the role "link" and name "영상"` | 화면의 메뉴 이름은 `영상 목록`(`ko.nav.videos`)이고 시험이 `영상`이라고 잘못 찾음. 화면에서 푸터는 이동 뒤에도 남아 있음(Chromium·TC-VMF-131 로 확인) | 시험 코드 문제 | 이름을 `ko.nav.videos`·`ko.videos.title` 로 바로잡음. 기대(이동 뒤에도 푸터 면책 존재)는 그대로 |

수정 후 `verify_fix` 21건 전부 통과. 같은 파일에 **eslint 오류 2건(`no-irregular-whitespace`, 44행)·경고 1건(43행, 불필요한 `eslint-disable`)** 이 원래부터 있고 이번에도 고치지 않았다(시험 코드의 의도적 비가시 문자 정규식이라 의미를 바꿀 위험, 결과서 6절 DEF-VMF-005 Low 로 등록). `verify_fix/shared.tsx` 는 prettier 서식만 바뀜.

**(나) verify_m23 첫 실행 결과(작성 직후)와 시험 설계 오류로 인한 수정** — 기대값을 구현에 맞춘 것이 아니라 *시험 자체의 오류*임을 근거와 함께 남긴다.

| 시험 | 첫 실행 실패 내용 | 원인 | 수정 |
|---|---|---|---|
| TC-VMF-003 | 연결 요청이 2번 나감 | `user.dblClick` 은 응답이 즉시 와서 버튼이 다시 켜진 뒤의 두 번째 클릭이라 연타 상황 재현이 아님 | 응답을 300ms 늦추고 3번 연속 클릭(현실의 느린 응답). 변이 M10 으로 방지 로직이 실제로 잡힘 확인 |
| TC-VMF-012 | 429 오류 제목을 못 찾음 | 화면이 429 를 "한도" 제목으로 바꿔 보여 줌(`describeError`) — 시험이 서버 제목을 기대한 오류 | 한도 제목+서버 상세 문구를 기대 |
| TC-VMF-111·113 | "버려졌습니다" 안내가 안 보임 | 가짜 서버가 취소 뒤 재조회에 계속 초안을 돌려줌(서버는 취소 상태를 기억) | 상태를 기억하는 가짜 서버로 교체 |
| TC-VMF-111 | 링크 이름 중복 오류 | "← 배치 목록" 링크가 화면에 2개(상단·안내 안) | `getAllByRole` |
| TC-VMF-115 | 버튼 이름 불일치 | 접근 가능한 이름에 공백이 없다("초안 버리기(배치 #7)") | 정규식 `\s*` |
| TC-VMF-028 | 실패 메시지에 조합이 안 나옴 | jest-dom 은 사용자 메시지를 지원하지 않음 | 불리언 비교로 바꿔 조합이 출력되게 함(기대는 불변) |
| TC-VMF-030 | 통과해 버림(거짓 통과) | 허용 정규식의 `WEB_` 가 `YTWEB_LIVE_WRITE` 에 걸림 | `WEB_` 제거 후 재실행 → 의도대로 실패 |

위 수정 이후 남은 실패 6건(TC-VMF-028·029·030·140·141·142)은 **첫 작성 때부터 일관되게 실패**했고 기대값은 한 번도 바꾸지 않았다. 원인은 화면 결함(6절)이다.

### 4-3. 브라우저(Chromium) 증빙 — 모의 서버 + 응답 가로채기 (2회 실행 중 같은 결과)
캡처: `.harness-tmp/cap_m23/*.png` (저장소에 넣지 않음). 합계 21건 중 불합격 2건(CAP-04x 결함, CAP-05 모의 서버가 차단 제안을 안 만든 것 → `cap2.mjs` 로 응답 주입 후 재확인).

| ID | 시나리오 | 예상 | 실제 | 결과 |
|---|---|---|---|---|
| CAP-01 | 홈 화면 맨 아래 푸터 | 면책+AI 고지가 보임 | 푸터에 "이 검증은 법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다." / "AI가 생성한 제안입니다. 사람이 검토하고 승인한 제목만 반영됩니다." 표시, 실제로 보임(isVisible) | Pass |
| CAP-02 | 구글 연결됨·쓰기 미연결 | [제목 수정 권한 연결]+"읽기 전용입니다", 경고 없음 | 일치 | Pass |
| CAP-03 | 쓰기 연결됨·수정 꺼짐 | "권한이 연결돼 있습니다"+"아직 꺼져 있습니다", "읽기 전용" 없음 | 일치 | Pass |
| CAP-04 | 실제 수정 가능 | 경고(허용 영상 1개), "읽기 전용/꺼져 있습니다" 없음 | 일치(카드 안) | Pass |
| **CAP-04x** | 같은 화면 전체 | "아무것도 전송되지 않습니다" 없음 | 상단에 **"데모 모드 — 유튜브에 아무것도 전송되지 않습니다"**, 홈 상태 카드에 "구글 연결: 데모 모드(실제 유튜브와 연결되지 않음)"·"구글 연결 안 됨"·"실제 반영(라이브): 꺼짐"이 경고와 함께 보임 | **Fail → DEF-VMF-001** (`CAP-04-live-ready.png`) |
| CAP-05 | 차단 카드(응답 주입) | 승인 비활성, 수정·반려 활성, 사유·안내, 영문 "blocked" 없음 | `{"approveDisabled":true,"editEnabled":true,"rejectEnabled":true,"reasonShown":true,"hint":true,"statusLabel":true,"rawBlockedWord":false}` | Pass |
| CAP-05c | 영상 상세 본문 | 면책 문장 | 있음 | Pass |
| CAP-06 | 승인 대화상자 | 면책+AI 한계 안내 | 둘 다 있음 | Pass |
| CAP-07 | 초안 상세 A/B | 확인 문구 표시·실행 잠김, 체크만으로는 계속 잠김 | 일치 | Pass |
| CAP-08 | 버리기 확인창 | "제목은 그대로" 안내 | 있음 | Pass |
| CAP-09 | 버린 뒤 | "버려진 초안" 표시, 실행 버튼 사라짐 | 일치 | Pass |

**면책이 화면 어디에 표시되는가(실제 확인)**: ① 모든 화면 맨 아래 푸터(`<footer aria-label="면책 및 AI 안내">`, 면책+AI 생성 고지, 6개 화면+없는 주소에서 정확히 1번, 숨김 아님 — TC-VWF-004·VMF-131, CAP-01) ② 영상 상세의 제안 목록 위 안내 칸 ③ 각 AI 제안 카드 안 ④ 승인 대화상자 안(면책+AI 한계, 엄격 모드면 건강·금융 주의 추가) ⑤ 배치 사전 점검 카드 ⑥ 성과 리포트·이력 화면의 안내. 영상 상세 화면에서는 면책이 본문과 푸터 **두 곳**에 보이는데 설계 의도(구현자 TC-VWF-005 주석)이며 결함으로 보지 않았다.

## 5. 커버리지
- 커버리지 지표: 요청 범위 3개 묶음의 인수 조건별 시험 대응을 아래에 둔다(소스 코드 줄 커버리지는 측정하지 않음 — 도구 미도입, 대신 변이 점검 38곳으로 시험의 민감도를 측정).

| 인수 조건(요청 근거) | 시험 |
|---|---|
| 구글 연결 파일 없음 안내/미연결 연결 버튼/연결 후 불러오기·해제/해제 2단계 확인/오류 안내 | TC-VMF-001~017, 014b, 040~042 |
| 쓰기 권한 연결 버튼(경로·실패), 쓰기 연결됐으나 수정 꺼짐 안내, 실제 수정 모드 경고, 허용 영상 수 | TC-VMF-020~030 |
| 쓰기 연결 뒤에도 "제목은 바뀌지 않습니다"가 남는 거짓 안내 점검 | TC-VMF-023, 026, 028 (거짓 문구 없음 확인) |
| C-1 차단 제안 카드 | TC-VMF-100, 100b, 101~108 |
| C-2 초안 버리기 | TC-VMF-110~115 |
| A/B 확인 문구 | TC-VMF-120~123 |
| 면책·AI 고지(위치) | TC-VMF-130~131, TC-VWF-001~012 |
| 안내의 진실성(상단 배지 등) | TC-VMF-140~142 |

- **변이 점검(핵심 분기를 임시로 깨뜨려 시험이 잡는지)**: 38곳(요구 최소 15곳). 소스 사본 변조 후 `verify_m23`+`verify_fix` 를 실행하고 *기준선(실패 6건)에 없던 새 실패*가 나오면 "잡음"으로 셌다. 매번 원본으로 복원했고 마지막에 `git diff cd1579f -- web/frontend/src` 가 0줄임을 확인했다.

| 분류 | 곳 수 | 결과 |
|---|---|---|
| 쓰기 연결 여부별 문구/분기(M01~M07, M11, M20) | 9 | 8 잡음 / 1 동치(M02) |
| 경고·읽기 전용·버튼 노출 조건(M08~M09, M12~M16, M18~M19) | 9 | 9 잡음 |
| 연타 방지(M10, M17) | 2 | 1차 1 잡음 + 1 놓침(M17) → 시험 TC-VMF-014b 추가 후 잡음 |
| 차단 카드·승인 조건(M21~M26) | 6 | 1차 4 잡음 + 놓침 2(M24, M25) → TC-VMF-100b·102b 추가 후 잡음 |
| A/B 확인·실행 조건(M27~M28, M38) | 3 | 3 잡음 |
| 초안 버리기(M29~M32, M35~M36) | 6 | 6 잡음 |
| 면책·AI 고지 표시(M33~M34, M37) | 3 | 3 잡음 |
| **합계** | **38** | **37 잡음, 1 동치(M02)** |

  - M02 동치 근거: `{g.client_ready && !g.write_connected && !g.live_write_ready && ...}` 에서 `!g.live_write_ready` 를 뺀 변이. 서버 규칙 `live_write_ready = 켜짐 and 허용>0 and write_connected`(`web/backend/ytweb/routers/google.py:71`)상 ready 이면 write_connected 도 참이라 앞 조건이 항상 먼저 거른다 → 서버 계약 안에서는 관찰 불가한 중복 조건.
  - 놓침 3건은 시험 공백이었고 시험을 보강해 잡히는 것을 확인(2차 변이 3곳 모두 잡음).
- 커버되지 않은 부분과 사유: ① 실제 백엔드 응답으로의 화면 확인 → 미수행(위 2절). ② 색 대비·반응형은 jsdom 한계로 Chromium 에서 눈으로만(캡처) 확인했고 axe 색 대비 자동검사는 수행하지 않음 → 미수행(잔여 위험: 구현 단위 W-FE 검증에서 별도 수행됨). ③ 쓰기 로그인 복귀(콜백) 이후 화면은 URL 이동 후라 범위 밖.

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 내용 |
|----|------|-----------|--------|------|-----------|
| **DEF-VMF-001** | **화면이 현재 상태와 반대로 안내한다.** 상단 배지가 항상 "데모 모드 — 유튜브에 아무것도 전송되지 않습니다"(`src/app/Layout.tsx:75`, 값 무관 고정 문구)이고, 홈 "연결 상태" 카드는 대시보드 값으로 "구글 연결: 데모 모드(실제 유튜브와 연결되지 않음)"·"구글 연결 안 됨"·"실제 반영(라이브): 꺼짐"을 표시한다. 그런데 백엔드 `web/backend/ytweb/domain/dashboard.py:37-40` 은 `mode:"demo"`, `live_enabled:False`, 구글 상태를 **고정값**으로 내려 준다. 따라서 구글을 연결해도(읽기: 실제로 구글에 요청을 보냄), 실제 수정이 가능해져도 같은 화면에 "아무것도 전송되지 않습니다"가 계속 보이고 같은 화면의 구글 카드 경고("제목이 실제 유튜브에서 바뀝니다")와 정면으로 모순된다. 사용자가 "안전한 데모"로 오해한 채 실제 제목을 바꿀 수 있다 | `npx vitest run verify_m23 -t "TC-VMF-142"`(및 140, 141). 브라우저: 모의 서버+`/api/v1/google/status` 를 `live_write_ready:true` 로 바꾸고 홈 화면을 연다 → `CAP-04-live-ready.png` | **High** | **Open** | 원칙: 소스 미수정. 제안: 상단 배지를 `google/status`(또는 대시보드 모드)로 3상태(데모/읽기 연결/실제 수정 가능)로 바꾸고, 대시보드 응답(`mode`, `live_enabled`, `google`)을 실제 상태에서 계산. 지금 M1 데모에서는 문구가 사실이지만 **M2/M3 기능이 이미 들어 있어 실제 연결 전에 반드시 수정 필요**. 원인은 프런트 1곳+백엔드 1곳(두 곳 모두 이 단위 밖일 수 있음) |
| DEF-VMF-002 | 실제 수정이 가능한 상태인데 **경고가 안 보이는 경우**: 서버가 `live_write_ready=true` 이면서 읽기 로그인만 풀린 상태(`connected=false`, 쓰기 토큰 파일은 남음)이면 "제목 수정 권한" 구역 전체가 `g.connected &&` 안에 있어 경고가 숨는다. 이때 "읽기 전용" 안내도 없다 | `npx vitest run verify_m23 -t "TC-VMF-028"` → 메시지 `경고 누락 {"connected":false,"write":true,"enabled":true,"allowed":2,"ready":true}` | Low(선결 조건: 읽기 토큰만 사라지는 상황. [연결 해제]는 두 토큰을 같이 지움) | Open | 제안: 경고를 `connected` 와 무관하게 `live_write_ready` 로 표시 |
| DEF-VMF-003 | **이미 켜 둔 설정을 또 켜라고 안내**: 서버에서 "실제 수정 켜기"를 켜 뒀고 허용 영상만 0개일 때도 "…켜려면 서버 설정 YTWEB_LIVE_WRITE=1 과 YTWEB_LIVE_ALLOWED_VIDEOS 가 필요합니다"만 나와 무엇이 부족한지 알 수 없다(응답에 `live_write_enabled` 가 있는데 화면이 쓰지 않음) | `npx vitest run verify_m23 -t "TC-VMF-029"` | Low | Open | 제안: `live_write_enabled` 별로 "수정 허용 영상이 0개입니다"와 "수정 켜기가 꺼져 있습니다"를 나눠 안내 |
| DEF-VMF-004 | **비개발자가 따라 할 수 없는 안내**: 환경변수 이름(`YTWEB_LIVE_WRITE=1`)만 있고 어디에서 어떻게 설정하는지(설정 파일·스크립트·문서)가 화면에도, 사용자 문서(`WEB_USER_MANUAL`·`WEB_INSTALL`·`WEB_RUNBOOK`)에도 없다(`YTWEB_LIVE_WRITE` 는 `API.md`·`STATE.md` 에만 있음). 의도적으로 운영자 전용 안전장치라면 "선생님 단독으로 켤 수 없다, 담당자에게 요청"처럼 명시해야 한다 | `npx vitest run verify_m23 -t "TC-VMF-030"`; `grep -rn YTWEB_LIVE_WRITE docs/yt/WEB_*.md` → 0건 | Low | Open | 제안: 안내 문구에 방법 또는 "개발 담당 확인 필요"를 쓰고 `WEB_RUNBOOK.md` 에 절차 추가(11단계 대조 때) |
| DEF-VMF-005 | 구현자 시험 파일 `verify_fix/notice.verify.test.tsx` 의 eslint 오류 2건·경고 1건(원래부터, 4-2 가) | `npx eslint .` | Low(시험 코드, 제품 영향 없음) | Open | 비가시 문자를 이스케이프(`\u00a0` 등)로 바꾸면 해결되나 의도 확인 필요해 미수정. 현재 `npm run check` 의 lint 단계가 이 3건 때문에 실패함 |
| (참고) TD-VWF-005/012 | 구현자 시험 2건 실패 | 4-2 가 | — | **Fixed(시험 코드)** | 시험 문제로 판정해 바로잡음, 원래 실패 기록을 4-2 에 남김 |

- 결함 목록과 별개 사항(관찰, 조치 필요): 내 변이 점검 도중 작업 트리의 `web/frontend/src/pages/GoogleCard.tsx` 가 변조된 상태(M02: 읽기 전용 안내 조건에서 `&& !g.live_write_ready` 제거)에서 다른 세션의 WIP 커밋이 찍혔다. 확인 결과 **커밋 `bcc0cb9` 와 `e956b6e` 의 `GoogleCard.tsx` 에 변이가 그대로 들어 있다**(`80b7a98`·`94598b8`·`6be65a8` 은 원본). 작업 트리의 `GoogleCard.tsx` 는 원본 `cd1579f` 와 같다(`git diff cd1579f -- web/frontend/src` 0줄). **다음 커밋에서 작업 트리 상태(원본)를 반드시 반영해야 한다.** 이 변이는 서버 계약상 동치라 동작은 같지만 소스가 어긋난 채 남으면 안 된다. 또한 `6be65a8`·`bcc0cb9`·`e956b6e` 에 내 첫 변이 실행의 부산물 `web/frontend/.vitest/json/output.json` 이 들어 있어 작업 트리에서 삭제했다(커밋 시 삭제가 반영되면 해결).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트: `.harness-tmp/cap_m23/`(브라우저 스크립트·캡처 PNG, **증빙으로 의도적으로 보존**), `.harness-tmp/mut_m23/`(변이 스크립트·사본·로그 → **삭제함**), 스크래치패드 임시 JSON, 모의 서버 포트 18921·18922(스크립트 종료 시 닫힘, `process.exit`), 저장소 안 `web/frontend/.vitest/`(삭제함). venv·DB·docker 는 만들지 않음.
- 전부 `.harness-tmp/` 하위에서만 생성했는가: [x] 예 (단, 시험 코드 `web/frontend/verify_m23/` 는 요청에 따른 저장소 내 산출물, `.vitest/` 는 도구 부산물이라 삭제)
- 정리(삭제) 완료 여부: 완료 (변이 폴더·`.vitest`). 실행 중 프로세스: 내가 띄운 node 프로세스는 모두 종료(자기 PID만, pkill 미사용).
- 정리 후 `git status` (원문):

```
 M web/backend/tests/verify_m23/conftest.py
 M web/backend/tests/verify_m23/test_vm_02_google_router.py
 D web/frontend/.vitest/json/output.json
 M web/frontend/src/pages/GoogleCard.tsx
 M web/frontend/verify_m23/google.verify.test.tsx
 M web/frontend/verify_m23/wfix.verify.test.tsx
 M web/tests_infra/test_vinf2_live.py
```
- 항목별 소유 표기: `web/backend/tests/verify_m23/*`, `web/tests_infra/test_vinf2_live.py` = 다른 검증자(백엔드/인프라) 소유, 내가 건드리지 않음. `web/frontend/verify_m23/*` = 이 단위(내 시험, 이전 WIP 커밋 대비 수정분). `web/frontend/.vitest/json/output.json` 삭제(D) = 내가 만든 부산물을 지운 것(WIP 커밋에 들어가 있었음). `web/frontend/src/pages/GoogleCard.tsx` 의 `M` = **내 작업 트리 변경이 아니라 HEAD(WIP 커밋)에 변이 상태가 찍힌 것**(위 6절 관찰 ①): `git diff cd1579f -- web/frontend/src` 는 0줄. 이 `M` 은 원본 복구를 의미한다.
- 병렬 실행이었다면 판정 근거: 이 단위가 만든 미추적 잔여물 없음(`git status` 에 `??` 항목 없음, `.harness-tmp/` 는 gitignore).
- 강제 중단: [x] 없음

## 8. 리스크 및 잔존 이슈
- 이번 테스트로 커버되지 않는 알려진 리스크: 실제 FastAPI 응답으로의 화면 확인 미수행(모의 서버 대체); 실제 구글 콜백 이후 흐름; 스크린리더; 다른 브라우저.
- 후속 조치: ① DEF-VMF-001 수정(High, M2/M3 를 켜기 전 필수) 후 TC-VMF-140~142·CAP-04x 재실행 ② DEF-VMF-002~004 는 Low 라 사용자 수용(Deferred, DEC 필요) 또는 수정 선택 ③ DEF-VMF-005 시험 코드 lint ④ 변이 점검 M02 는 동치 변이라 조치 없음 ⑤ 6절 관찰 ①(커밋 오염) 처리.

## 9. 결론 및 판정
- [ ] PASS
- [x] **CONDITIONAL PASS — 조건: DEF-VMF-001(High) 수정 후 TC-VMF-140·141·142·CAP-04x 재통과. 현재 M1 데모 화면 자체에서는 문구가 사실이라 데모 사용에는 영향이 없다. DEF-VMF-002~005(Low)는 수정하거나 사용자 수용(Deferred)이 필요하다.**
- [ ] FAIL
- 시험 수: verify_m23 66건(통과 60, 실패 6) + verify_fix 21건(전부 통과) + 기존 전체 프런트 시험 포함 전체 749건 중 통과 721 / 실패 6(모두 TC-VMF, 열린 결함 대응) / expected-fail 1 / 건너뜀 21. 정적 검사: `tsc -b` 통과, `prettier --check` 통과, `npm run build` 통과, `eslint` 오류 2·경고 1(전부 `verify_fix/notice.verify.test.tsx`, DEF-VMF-005). 변이 38곳 중 37 잡음·1 동치. 브라우저 증빙 21건 중 불합격 1건(DEF-VMF-001).
- 열린 결함: DEF-VMF-001(High), 002·003·004·005(Low).

## 10. 내부 검증 (최소 2회, `verification-log-template.md` 사용)
- 1차 검증 결과 요약: 인수 조건별 시험 대응 100%(5절 표), 기대값의 근거는 문구·서버 응답 규칙(`google.py`, `dashboard.py`)에서 직접 도출. 시험 설계 오류 7건 발견·수정(4-2 나), 거짓 통과 1건(TC-VMF-030) 발견·수정.
- 2차 검증 결과 요약: "이 시험을 통과했다고 다음 단계에 넘겨도 되는가"를 의심해 변이 38곳 점검 → 놓침 3건(M17, M24, M25) 발견·시험 보강·재점검에서 잡음 확인. 3차: 결함 확정 시험(6건)이 첫 작성 때부터 같은 이유로 실패함과 기대값을 바꾸지 않았음을 확인, 동치 변이(M02) 근거 확인.
- 검증 로그 파일 경로: `docs/harness/verify-logs/verify-log_web-WU-M23-FE-test.md`

## 공유 문서 갱신 요청 (병렬 대비, 직접 수정하지 않음)
- `traceability.md`: W-FIX-FE(DEF-9-007·008·7-008·7-009)·M2 단위4·M3 단위3 행의 "단위테스트" 컬럼 = `TC-VMF-001~142 (verify_m23)` / 상태 = CONDITIONAL(DEF-VMF-001 Open)
- `decisions.md`: DEF-VMF-002~004 를 사용자가 수용하면 DEC 기록 필요

---
## 부록 B. 결함 조치와 재실행 결과 (2026-10-11, 오케스트레이터)
첫 실행 결과(위 본문)는 그대로 두고, 조치 후 재실행을 별도로 적는다.
- **조치**: DEF-VMF-001(High) — 서버 대시보드가 실제 상태를 보내도록 고치고(DEF-VM-010), 상단 모드 띠(`Layout.tsx ModeBadge`)가 대시보드의 `mode`/`google.connected` 를 따라 "실제 수정 모드 …" / "구글 연결됨(읽기) — 제목은 바뀌지 않습니다" / "데모 모드 …"를 보이게 했고, 홈 상태 카드의 구글 줄은 `google.mode` 를 쓴다. DEF-VMF-002(읽기 연결 없이 쓰기만 연결해도 경고·구역이 보임), DEF-VMF-003·004(상태별 안내: 꺼진 스위치/허용 영상 없음을 각각 말하고 `web\.env`·`start.ps1` 위치를 안내), DEF-VMF-005(eslint 오류 2건: 시험의 의도적 비정상 공백에 해당 규칙 예외 주석).
- **시험 수정 사유**: TC-VMF-142 의 모의 서버 응답은 "대시보드는 항상 demo·live_enabled=false"라는 옛 서버를 전제로 해서, 조치 후 서버 모양(mode=live, live_enabled=true)으로 바꿨다(원래 실패는 위 본문에 남아 있음). TC-VMF-023 은 문구 생성 함수의 인자가 바뀌어 호출만 맞췄다(검증 내용은 같음).
- **재실행(프런트 전체)**: 727 통과 · 21 건너뜀 · 1 예상 실패 · 실패 0. `tsc` 오류 0, `eslint` 오류·경고 0, 운영 빌드 통과.
- **안 한 것**: 조치 후 변이 점검 재실행, Chromium 화면 캡처 재촬영, 별도 독립 검증자 재검증(9단계 재검증·8단계에서 함께 확인 예정).
