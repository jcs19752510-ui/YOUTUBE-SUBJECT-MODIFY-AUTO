# traceability.md 갱신안 (제안만, 원본 미수정)

작성 2026-10-13 UTC. 규칙 H: 아래 `W-N01`~ 은 **미승인 임시 ID** 이다(정식 부여는 오케스트레이터 확인 필요). 시험 ID 는 이름이 실제 시험 파일에 있는 것만 적었고, 시험 ID 가 따로 없는 시험은 `파일::함수` 로 적었다.

## A. 이번 세션 기능별 현황 (traceability.md 에 있는지 / 시험 연결 / 실행 확인)

| 기능 | traceability.md 에 행 있음? | 시험 파일(함수) | 이번 실행 결과(표본) |
|---|---|---|---|
| 구글 읽기 로그인 | 있음 W-M2-01·02 | `test_google_oauth.py` TC-M2-001~017, `domain/test_google_router.py` TC-M2-020~031 | 17 + 12 통과 |
| 내 영상 읽기·저장 | 있음 W-M2-03 | `domain/test_live_sync.py` TC-M2-040~053 | 통과(표본 94건에 포함) |
| 구글 연결 화면 | 있음 W-M2-04, W-M3-04 | `google.test.tsx` TC-WF-200~203·210~212 | 8 통과 |
| 쓰기 로그인·수정 게이트웨이 | 있음 W-M3-01 | `test_live_write.py`, `domain/test_live_gateway.py` TC-M3-010~013 | 통과 |
| live 3조건 | 있음 W-M3-02 (Partial) | `domain/test_live_gateway.py` TC-M3-020·021·030·031 | 통과 |
| 실제 모드 확인 문구·허용 영상 | 있음 W-M3-03 | `domain/test_live_guard.py` TC-M3-040~047 | 통과 |
| 준비 점검(live-check) | **없음** | `domain/test_live_check.py` TC-M3-070·071 | 2 통과 |
| 직접 고친 제목 출처 구분 | **없음** | `domain/test_source_edit.py` TC-M3-060 | 1 통과 |
| 규칙 기반 제안 | **없음** | `test_rule_suggester.py` (5 함수) | 5 통과 |
| Gemini 제안 | **없음**(Gemini 단어 0회) | `test_gemini_suggester.py` (8), `domain/test_live_suggest.py` (5) | 8 + 5 통과 |
| 실제 영상 제안에서 모의 제안기 제외 | **없음** | `domain/test_live_suggest.py::test_live_video_gets_only_approvable_candidates_of_sufficient_length` | 통과 |
| 반영 후 검증(완화, 달라진 항목 표시) | **없음**(행 없음, 주변 SEC-010 은 CLI 용) | `domain/test_verify_report.py` (3), `verify_wb/test_vb_04_apply_recover.py` | test_verify_report 3 통과 |
| 유튜브에서 직접 바꾼 제목 갱신 | **없음** | `domain/test_live_sync.py::test_tc_live_sync_refreshes_a_video_changed_by_the_program_and_by_hand_but_not_one_in_flight` | 통과 |
| AI 제안 종류 표시 | **없음** | `ai.aibadge.test.tsx` (7), `verify_ai_badge/test_source_exposed.py` (2) | 7 + 2 통과 |
| 실행 버튼 비활성 이유 안내 | **없음** | `batchdetail.execgate.test.tsx` (4) | 4 통과 |
| 입력칸 id/name | **없음** | `formids.test.tsx` (4) | 4 통과 |
| 실제 모드 꺼짐일 때 실제 영상 모의 성공 금지(DEF-LIVE-005) | **없음** | `domain/test_live_off_block.py` (3) | 3 통과 |
| 제안 점검 점수 | **없음** | 확인된 전용 시험 파일 없음(`src/lib/score.test.ts` 가 있으나 이번에 실행하지 않음) | 미실행 |

## B. 추가할 행(제안, 표 형식은 기존 v5 표와 동일)

| ID | 유형 | 요구사항/기능 | 설계 매핑 | 구현 상태 | 단위테스트 (TC-ID / 파일) | 비고 |
|----|------|------|------|------|------|------|
| W-N01 | W | 규칙 기반 제안기(설명의 챕터에서 45~60자 제목 생성, 모든 후보가 검증기 통과) | WEB_DESIGN §12 | Implemented | `web/backend/tests/test_rule_suggester.py` 5건 | 미승인 ID, 이번 실행 5/5 통과 |
| W-N02 | W | Gemini 제안기(키 파일 `web/secrets/gemini_api_key`, 키는 헤더로만, 오류 한국어, 이미 만든 제목 전달, 키 없으면 규칙 기반) | 13c1b2a | Implemented(가짜 응답 시험 + 이번 세션 실서버 재확인은 e-gemini 보고서) | `test_gemini_suggester.py` 8건, `domain/test_live_suggest.py` 5건 | 실서버 결과는 .harness-tmp/parts/e-gemini-traceability.md |
| W-N03 | W | 실제 영상 제안은 승인 가능 후보만·충분한 길이, 다시 눌러도 새 후보 | 631a14c, 08074b5 | Implemented | `domain/test_live_suggest.py` | DEF-LIVE-001 |
| W-N04 | W | 반영 후 검증: 줄바꿈·끝 공백·태그 순서·언어 자동 채움 완화, 달라진 항목을 배치 화면에 표시 | e1bfa0c | Implemented | `domain/test_verify_report.py` 3건 | |
| W-N05 | W | 유튜브에서 직접 바꾼 제목도 내 영상 불러오기 때 갱신(반영 진행 중인 영상 제외), 직접 고친 제목 출처 구분 | 722ae2c, b5a5b9d | Implemented | `domain/test_live_sync.py::test_tc_live_sync_refreshes…`, TC-M3-060 | |
| W-N06 | F | AI 제안 종류 표시(모의/규칙/Gemini/직접 고침/옛 제안) | 1fcef8a | Implemented | `ai.aibadge.test.tsx` 7건, `verify_ai_badge` 2건 | |
| W-N07 | F | 실행 버튼 비활성일 때 남은 조건 표시(A/B 확인·확인 문구) | 1fcef8a, CLAUDE.md 추후 수정 | Implemented | `batchdetail.execgate.test.tsx` 4건 | 선생님 질문("체크도 해야 하나요?")이 근거 |
| W-N08 | F | 모든 입력칸에 id 또는 name | 1fcef8a | Implemented | `formids.test.tsx` 4건 | |
| W-N09 | W | 실제 모드가 꺼진 상태에서 실제 영상은 배치 포함 불가·모의 성공 처리 금지 | 0306011 (DEF-LIVE-005) | Implemented | `domain/test_live_off_block.py` 3건 | |
| W-N10 | W | 실제 수정 준비 점검(live-check) | b5a5b9d | Implemented | `domain/test_live_check.py` TC-M3-070·071 | |
| W-N11 | F | 제안 카드 점검 점수(0~100)·점수순 정렬 | 8d672d1 | Implemented | `web/frontend/src/lib/score.test.ts`(실행 안 함) | 요구 ID·시험 연결 확인 필요 |

## C. 기존 행 수정 제안

| ID | 현재 | 제안 |
|---|---|---|
| W-M3-02 | Partial — 켜는 방법 미정 | live-on/off.bat(1a9e742), `web/.env.example` 로 켜는 방법이 생겼는지 확인 후 상태 갱신(확인 필요) |
| S-W07 | Partial(M1 모의 AI 한정) | Gemini 어댑터 추가(W-N02) 사실과 "전송 데이터는 제목+설명 요약만, 키 헤더 전용" 시험(`test_request_has_key_in_header_only_and_sends_only_title_and_summary`) 연결 |
| SEC-010, FR-… 의 CLI 행 | CLI 기준 | 웹의 반영 후 검증은 W-N04 로 분리 |
| 변경 이력 | v5 | v6 행 추가(위 W-N01~11) |
