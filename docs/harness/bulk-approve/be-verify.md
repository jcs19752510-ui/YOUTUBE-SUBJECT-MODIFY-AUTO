# 일괄 승인 백엔드 독립 검증 결과서 (be-verify)

시작 2026-10-13 03:23:33 UTC, 종료 약 03:35 UTC(상한 12분). 검증자: 구현자와 무관. 소스 수정·git 쓰기 없음(변이는 /tmp/claude-0/m 사본에서만 수행, 저장소 소스 무변경).

## 1. 결론 (한 줄)
**조건부 PASS**: 계약 핵심(경고 서버 강제·SAVEPOINT 부분 처리·서명/체인·멱등·동시성·모의 모드 외부 호출 없음)은 독립 시험 통과. 결함 2건(Low/Info)과 구현자 시험의 공백 1건 발견. 전체 회귀는 아래 6절 구간까지 통과, 나머지는 미수행(사유 명시).

## 2. 한 것 / 안 한 것
한 것: 독립 시험 TC-BV-001~021 작성·실행(`web/backend/tests/verify_bulk/`, PostgreSQL `ytweb_test_b` 포함), 변이 16곳, 회귀 구간 실행.
안 한 것: 실제 모드(구글) 경로의 일괄 승인 실행(실제 모드 환경 구성 없음; 대신 모의 모드에서 socket connect/getaddrinfo 차단 시험 + 소스에 게이트웨이 호출 없음 확인). OpenAPI 일치(미갱신이 구현자 보고 — 확인 안 함). 성능/부하.

## 3. 시험 목록 (TC-BV)
001 단건 approve 불변(ack_warning None/True로 경고 승인) · 002 단건 HTTP 응답 스키마 불변 · 003 응답 스키마 키 정확 일치(approve-batch·resolve) · 004 경고 우회(ack 비움/다른 id/요청에 없는 id) · 005 저장 판정 위조 시 재검증이 우선(경고→pass 위조, 차단→후보 위조) · 006 건별 MAC 재계산·plan_hash·verify_chain·감사 순서 · 007 멱등(재전송 동일 응답, 같은 키 다른 본문·순서·ack 422, 실패 뒤 재시도) · 008 잘못된 id 12종 · 009 잘못된 ack id · 010 승인자 규칙이 단건과 동일(빈/공백/41·200·201·5000자/제로폭·방향·소프트하이픈·NUL·줄구분자/None/숫자) · 011 51개·중복·501개 · 012 resolve 경계(패턴 위반 6종·51개·중복 51개→1·CSRF 없음) · 013 세션 없음 · 014 네트워크 차단 하 정상 동작 · 015 상태별 skip 코드 · 016 같은 영상 2제안 · 020 PG 동시 4요청(교차 순서) 정확히 2건 승인·체인 유효 · 021 PG 혼합 부분 처리(차단·경고·없는 id)·MAC·체인, 요약 감사 실패 시 전체 롤백.

## 4. 실제 결과
첫 실행(그대로): 4건 실패 — 003(시험 데이터가 차단 제안과 같은 영상을 골라 duplicate_video_in_request가 됨 = 시험 결함), 010(내 시험이 같은 제안에 배치→단건 순서로 호출 = 시험 결함), 008[ids5]·008[ids8] = **제품 관찰(DEF-BA-001)**.
시험 결함 2건은 데이터/순서만 고쳐 재실행 통과(기대값 완화 없음). 008 두 건은 **실패로 남김(PASS로 세지 않음)**.
최종 verify_bulk: 위 008 2건을 뺀 전부 통과(PG 시험 020·021 포함 통과), 실패 2.

## 5. 결함·관찰
- **DEF-BA-001 (Low)**: `suggestion_ids`에 문자열 `"1"`·불리언 `true`가 200으로 받아들여져 정수 1로 처리됨(pydantic 느슨 변환, 제안 1번이 없으면 suggestion_not_found로 skip). 재현: POST approve-batch `{"suggestion_ids":["1"]}` 또는 `[true]`. 영향: 의도치 않은 id 승인 가능성(true=1). 기존 batches 등 다른 정수 필드와 같은 규약일 가능성이 크나 이 검증에서 다른 라우터는 확인하지 않음. 권고: StrictInt.
- **DEF-BA-002 (Info)**: 승인자 이름 상한이 스키마 200자인데 실제 규칙은 40자(clean_approver)라 41~200자는 422 approver_invalid(단건과 동일하므로 일관됨). 계약서의 "1..200"과 문구 차이만 있음.
- 구현자 시험 공백(결함 아님): 변이 V8(resolve 후보 상태에서 approved 제외)을 구현자 시험이 못 잡음(아래 7절).
- 구현자 보고 대조: be-impl.md의 "SQLite에서 부분 커밋 가능" 잔여 위험은 이 검증에서 재현 시도하지 않음(PG만 검증).

## 6. 회귀(백엔드 전체, 구간별, -o addopts= 로 요약 확인)
- tests/core | rc/time 38s |                                                                231 passed in 35.08s 
- tests/domain | rc/time 70s |                                      329 passed in 66.25s (0:01:06) 
- tests/test_*.py | rc/time 7s |         66 passed in 5.70s 
- tests/verify_ai_badge | rc/time 2s |                                                                     6 passed in 0.15s 
- tests/verify_fix_be | rc/time 45s |              209 passed in 41.67s 
- tests/verify_m23 | rc/time 59s |                                        397 passed, 1 skipped, 1 xfailed in 55.77s 
- tests/verify_revoke | rc/time 5s |                                                            15 passed in 2.77s 
- tests/verify_spec | rc/time 3s | /home/user/youtube-subject-modify-auto/web/backend/tests/verify_spec/test_openapi_errors.py:50: AssertionError: assert {'openapi': ', }, }}} == {'openapi': 'unts'}, }}
- tests/verify_trace | rc/time 2s | FAILED tests/verify_trace/test_trace_unlinked.py::test_tc_trace_nfr006_validator_and_request_body_line_coverage_at_least_90 FAILED tests/verify_trace/test_trace_unlin
(위 목록에 없는 구간 = 12분 상한 내 **미수행(시간 부족)** 또는 아직 실행 중이었음. PASS로 세지 않음.) tests/core·domain·test_*.py·verify_ai_badge·verify_fix_be 는 위 수치대로 실패 0.

### 6-1. 회귀 추가 결과(종료 직전 확인)
- tests/verify_m23: 397 통과, 1 건너뜀, 1 xfail / verify_revoke: 15 통과.
- **tests/verify_spec 실패 1건 = DEF-BA-003 (Medium, 문서 불일치)**: `test_saved_openapi_json_is_current` 실패. 저장된 `docs/yt/openapi.json`이 새 엔드포인트 2개를 반영하지 않음(구현자가 미갱신 보고한 항목이 실제 시험 실패로 확인됨). 재현: `pytest tests/verify_spec`. 조치: openapi.json·API.md 재생성 필요.
- tests/verify_trace 실패: 실행 환경 문제(`.harness-tmp/t-cli/bin/python` 없음, FileNotFoundError)로 보이며 일괄 승인과 무관할 가능성이 크나 **원인 확정은 안 함**(미수행: 해당 venv 복구 후 재실행).
- 미수행(사유: 12분 상한): verify_wa·verify_wb·verify_wfixbe(실행 중 중단), verify_bulk 최종 재실행(앞 4절의 수치로 갈음).

## 7. 변이 점검 (사본에서, 원복 후 재통과 확인 = 사본 복원 diff 없음)
형식: 변이 / 내 시험 / 구현자 시험 (내 시험 공통 상시 실패 008x2 제외)
| # | 변이 | 내 시험 | 구현자 시험 |
|---|---|---|---|
| V1 | 경고 검사 제거 | 탐지 004·005 | 탐지 011·013·014 |
| V2 | 경고 검사를 block 판정으로 | 탐지 004·005 | 탐지 |
| V3 | 일괄에서 ack 항상 True | 탐지 004·005 | 탐지 |
| V4 | 일괄에서 ack None 전달 | 탐지 004·005 | 탐지 |
| V5 | 단건 경로(None)도 막음 | 탐지 001 | 탐지 015 |
| V6 | ack 목록=요청 전체 | 탐지 004·005 | 탐지 |
| V7 | 영상 중복 추적 제거 | 탐지 016 | 탐지 010 |
| V8 | resolve가 approved 제외 | 탐지 003 | **미탐지(구현자 시험 공백)** |
| V9 | resolve 정렬 오름차순 | **미탐지** | 탐지 031 |
| V10 | resolve 중복 제거 제거 | 탐지 012 | 탐지 032·033 |
| V11 | 상한 51 | 탐지 011·012 | 탐지 |
| V12 | skipped 개수 오기 | 탐지 003·006 | 탐지 다수 |
| V13 | 멱등 요청 지문 제거 | 탐지 007 | 탐지 024 |
| V14 | resolve found 제목 공란 | **미탐지** | 탐지 030 |
| V15 | not_found video_id 변조 | 탐지 003 | 탐지 006 |
| V16 | approved 목록 순서 역전 | **미탐지** | 탐지 001 |
양쪽을 합치면 16/16 탐지. 각 시험 묶음 단독으로는 내 시험 13/16, 구현자 15/16.

## 8. 검증 로그 (최소 2회)
1회차(03:24~03:26): 위 4절 첫 실행 결과 기록 → 원인 분류(시험 결함 2·제품 관찰 2).
2회차(03:26 이후): 시험 데이터 수정 뒤 재실행·변이 16건·회귀 구간. 계약서 대비 재대조: 경고 서버 강제·영상 중복·SAVEPOINT·요약 감사·멱등·상한 422 코드(bulk_too_many·bulk_empty·duplicate_suggestion) 모두 일치.

## 9. 미수행·질문
- 미수행: 6절 목록에 없는 회귀 구간, 실제 모드 일괄 승인, resolve-videos의 모든 읽기 전용 변이, OpenAPI 일치 확인.
- 질문: 정수 필드 느슨 변환(DEF-BA-001)을 전 라우터 공통 규약으로 볼지(StrictInt 적용 범위)?
- 임시: /tmp/claude-0/m(변이 사본), tests/verify_bulk(신규 시험, 저장소 내 미커밋), PG 테이블은 시험이 drop함.
