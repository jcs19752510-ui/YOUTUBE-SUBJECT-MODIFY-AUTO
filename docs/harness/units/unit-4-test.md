# 테스트 결과서 — WU-4 변경 계획·이력·롤백 계획 (6단계 단위 테스트)

## 1. 개요
- 테스트 대상: WU-4 변경 계획·이력·롤백 계획 (`limits, updater, history, commands/plan, commands/rollback`)
- 테스트 유형: 단위
- 적용 Tier: Standard (규칙 B 원문: 최소 2회)
- 적용 속도 트랙: L5
- 병렬 실행 정보: 단독 실행(독립 검증 단계)
- 테스트 목적: `unit-4-note.md`의 인수 조건(AC)을 테스트로 증명하고 안전 로직의 회귀를 막는다
- 관련 산출물: `docs/yt/DESIGN.md`, `docs/harness/units/unit-4-note.md`, `docs/yt/02_planning.md`
- 테스트 수행자(에이전트): 오케스트레이터(06단계 역할 직접 수행)
- 테스트 일시: 2026-10-10

## 2. 테스트 범위 및 제외 범위
- 범위(In-Scope): 교체 제한 4종, 변경 계획(전체 snippet 보존 본문·plan_hash), 변경 이력 기록과 후보 상태 전이, 롤백 계획·DB 처리, `plan`·`rollback` 명령(드라이런)
- 제외 범위(Out-of-Scope) 및 사유: 실제 YouTube 쓰기 호출(WU-5), 읽기 전용 필드를 포함한 snippet을 videos.update가 받아들이는지([확인 필요], 12단계 실측)

## 3. 테스트 환경
- 실행 환경: Linux, Python 3.12.3 (주 실행) · 3.11 · 3.13 (호환 확인), pytest, pytest-cov. 가상환경은 `.harness-tmp/` 아래에만 생성
- 테스트 데이터: 임시 폴더의 가짜 설정·DB·후보, 가짜 토큰 문자열(실제 비밀 아님). **실제 YouTube API는 호출하지 않음**
- 전제 조건: 이전 단위 WU-2, WU-3 PASS

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고(검증하는 ID) |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-400 | 직전 변경 후 정확히 72시간이면 통과, 1초 모자라면 차단되고 가능한 시각을 알려 준다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_limits.py::test_interval_boundary_72_hours` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-014, SEC-004 |
| TC-401 | 간격은 설정값(cadence.min_interval_hours)을 따른다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_limits.py::test_interval_uses_configured_hours` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-014 |
| TC-402 | 한 번도 바꾸지 않은 영상은 간격·횟수·노출수 조건에 걸리지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_limits.py::test_first_change_has_no_history_limits` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-014 |
| TC-403 | 변경 2회까지는 통과, 이미 3회면 차단되며 시간이 지나도 풀리지 않는다(재시도 시각 없음). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_limits.py::test_count_boundary_three_changes` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-014, SEC-004 |
| TC-404 | 횟수 상한은 설정값을 따른다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_limits.py::test_count_uses_configured_cap` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-014 |
| TC-405 | 재변경 시 변경 이후 노출수 999는 차단, 1000은 통과한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_limits.py::test_impressions_boundary_1000` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-014, SEC-004 |
| TC-406 | 노출수를 모르면(기록 없음·API 미제공) 안전을 위해 거부하고 지표를 가져오는 방법을 안내한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_limits.py::test_unknown_impressions_rejected_with_reason` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007, FR-014 |
| TC-407 | 최소 노출수를 0으로 설정하면 노출수를 몰라도 통과한다(조건 끔). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_limits.py::test_zero_threshold_disables_impressions_check` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-014 |
| TC-408 | 오늘 적용 2건까지는 통과, 3건이면 차단되고 다음 태평양 자정이 가능 시각이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_limits.py::test_daily_cap_boundary` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-020 |
| TC-409 | 하나라도 실패하면 보고서 전체가 실패이고 실패 항목만 failures에 나온다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_limits.py::test_report_fails_if_any_check_fails` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-014 |
| TC-410 | 사용자 화면의 시각은 한국 시간(UTC+9)으로 표시한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_limits.py::test_format_kst` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass |  |
| TC-411 | 변경 횟수는 success·planned(미확정)만 세고 failed·aborted·다른 영상은 세지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_limits.py::test_gather_counts_success_and_planned_only` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-014, SEC-004 |
| TC-412 | 직전 변경 시각은 가장 최근 행(applied_at, 없으면 created_at)이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_limits.py::test_gather_last_change_time_uses_latest` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-014 |
| TC-413 | 노출수는 변경 '이후에 시작하는' after/periodic 기간만 인정한다(이전·같은 날 시작·before 단계·NULL·CSV 시작일 없음 제외, 최댓값 사용). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_limits.py::test_gather_impressions_only_after_change` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-014 |
| TC-414 | 쓸 수 있는 지표가 하나도 없으면 None이고, 재변경은 거부된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_limits.py::test_gather_impressions_none_when_no_usable_metrics` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-014 |
| TC-415 | '하루'는 태평양 시간 날짜다: PT 자정(UTC 07:00) 직전 변경은 어제, 정각 변경은 오늘이다. 롤백 행은 세지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_limits.py::test_daily_count_pt_day_boundary` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-006, SEC-020 |
| TC-416 | 서머타임이 끝나는 날(2026-11-01)은 25시간이고 경계가 정확하다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_limits.py::test_pt_day_bounds_dst_fall_back` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-006, NFR-003 |
| TC-417 | 이력의 시각 형식이 깨져 있으면 추측하지 않고 DatabaseError로 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_limits.py::test_bad_timestamp_in_history_fails_closed` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-014, NFR-007 |
| TC-418 | 영상 ID에 SQL 조각이 있어도 값으로만 쓰여 다른 행을 건드리지 않고 테이블이 유지된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_limits.py::test_sql_injection_in_video_id_is_inert` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-018 |
| TC-419 | DB 이력으로 4가지를 함께 판정하고, 판정 중 DB를 전혀 바꾸지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_limits.py::test_check_limits_end_to_end_and_read_only` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-014, SEC-004, SEC-006 |
| TC-420 | 이력 테이블을 읽을 수 없으면 DatabaseError(한국어 안내)로 변환한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_limits.py::test_db_error_becomes_database_error` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007 |
| TC-421 | canonical JSON은 키 순서와 무관하고 공백이 없으며 한글을 이스케이프하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_canonical_json_is_order_independent_and_keeps_hangul` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-004, SEC-014 |
| TC-422 | 같은 입력이면 plan_hash가 항상 같은 64자리 16진수이고, snippet의 키 순서가 달라도 같다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_plan_hash_is_deterministic_hex` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-004, SEC-014 |
| TC-423 | plan_hash 규격을 고정한다(고정 입력의 기대 해시 값). 규격이 바뀌면 이미 만든 승인 파일이 모두 무효가 되므로 실수로 못 바꾸게 한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_plan_hash_golden_value` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-014 |
| TC-424 | 영상·후보·이전/새 제목·snippet의 어떤 항목이 달라져도(설명 1글자, 태그 순서, 카테고리 포함) 해시가 달라진다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_plan_hash_changes_when_anything_changes` | docstring의 기대 결과가 모두 충족 | Pass(10건) | Pass | SEC-009, SEC-014 / 변형 10건 |
| TC-425 | 이전/새 제목 경계를 옮긴 입력("ab","c" vs "a","bc")이 같은 해시가 되지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_plan_hash_field_boundaries_are_unambiguous` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-014 |
| TC-426 | 요청 본문은 snippet 전체에서 title만 다르다(description·tags·categoryId·기타 전부 보존). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_body_preserves_every_other_field` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-009, SEC-005 |
| TC-427 | 본문을 고쳐도 원본 snippet(백업 재료)이 바뀌지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_body_is_a_deep_copy` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-005 |
| TC-428 | 깨졌거나 제목이 없는 저장 snippet은 거부하고 fetch를 안내한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_parse_snippet_rejects_broken_data` | docstring의 기대 결과가 모두 충족 | Pass(9건) | Pass | NFR-007, SEC-005 / 변형 9건 |
| TC-429 | categoryId가 없는 snippet으로는 쓰기 본문을 만들지 않는다(카테고리가 지워지는 사고 방지). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_parse_snippet_requires_category_id` | docstring의 기대 결과가 모두 충족 | Pass(3건) | Pass | SEC-005 / 변형 3건 |
| TC-430 | 빈 제목·`<` `>`·제어/방향 문자·101자 초과는 쓰기 계획 단계에서도 거부한다(마지막 방어선). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_validate_new_title_rejects` | docstring의 기대 결과가 모두 충족 | Pass(11건) | Pass | FR-002, SEC-019 / 변형 11건 |
| TC-431 | 100자는 통과하고, 이모지 결합 문자(ZWJ)는 거부하지 않는다. 길이 검사를 끄면 긴 원래 제목도 복원 가능하다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_validate_new_title_accepts_boundary_and_emoji` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-002 |
| TC-432 | 정상 후보는 diff·본문·해시·보존 항목을 갖춘 계획이 되고, 계획 생성은 DB를 전혀 바꾸지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_create_plan_success_reads_only` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-004, FR-008, SEC-001 |
| TC-433 | 영상 정보(설명)가 Studio에서 바뀌어 다시 fetch되면 같은 후보라도 plan_hash가 달라진다(승인 무효화 근거). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_plan_hash_depends_on_current_snippet` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-009, SEC-014 |
| TC-434 | 차단된 후보는(상태 또는 검증 결과 중 하나만 차단이어도) 계획을 만들지 않고 안전 게이트 오류(종료 코드 3)이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_create_plan_refuses_blocked_candidate` | docstring의 기대 결과가 모두 충족 | Pass(3건) | Pass | FR-005, POL-001, SEC-001 / 변형 3건 |
| TC-435 | 검증을 통과하지 않은(또는 결과가 비어 있는) 후보는 거부한다(fail-closed). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_create_plan_refuses_unvalidated` | docstring의 기대 결과가 모두 충족 | Pass(3건) | Pass | FR-005 / 변형 3건 |
| TC-436 | 이미 적용·평가·롤백된 후보는 다시 계획하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_create_plan_refuses_finished_candidates` | docstring의 기대 결과가 모두 충족 | Pass(3건) | Pass |  / 변형 3건 |
| TC-437 | 승인됨(approved) 후보와 경고(warn) 후보도 계획은 볼 수 있다(경고는 사유와 함께 표시). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_create_plan_allows_approved_and_warn` | docstring의 기대 결과가 모두 충족 | Pass(2건) | Pass | FR-005 / 변형 2건 |
| TC-438 | 없는 후보 번호나, 영상 정보를 fetch한 적 없는 후보는 안내와 함께 InputError이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_create_plan_missing_candidate_and_video` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-004, SCR-003 |
| TC-439 | 새 제목이 현재 제목과 같으면(쿼터·횟수 낭비) 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_create_plan_same_title_rejected` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-008 |
| TC-440 | videos.title 열과 snippet_json의 제목이 다르면(캐시 훼손) 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_create_plan_cache_mismatch_rejected` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-005, SEC-009 |
| TC-441 | DB의 후보 제목이 규격 위반이면(검증 이후 변조 등) 계획 단계에서 다시 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_create_plan_rechecks_new_title_rules` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-002 |
| TC-442 | 저장 시각이 24시간 이내면 최신, 24시간을 넘으면(또는 읽을 수 없으면) 오래된 것으로 본다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_stale_boundary_24_hours` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-004 |
| TC-443 | 영상 정보가 25시간 전 것이면 plan.stale이 참이다(경고 표시용). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_plan_marks_stale_video` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-004 |
| TC-444 | 교체 제한에 걸리면 plan.ready가 거짓이다(72시간 이내 재변경). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_plan_not_ready_when_limits_fail` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-014, SEC-004 |
| TC-445 | 오늘 남은 쿼터가 필요량(쓰기 50 + 조회 2)보다 적으면 ready가 거짓이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_plan_not_ready_when_quota_short` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SCR-003, SEC-002 |
| TC-446 | 검증 사유 JSON이 깨져 있어도 계획은 만들되 사유를 읽을 수 없다는 경고 항목을 넣는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_reasons_unreadable_json_is_flagged` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-005 |
| TC-447 | 비공개·아동용·예약 라이브/프리미어·Shorts(180초 이하)·모르는 값은 제외 사유가 된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_sequential_exclusions_reasons` | docstring의 기대 결과가 모두 충족 | Pass(8건) | Pass | FR-019, POL-003 / 변형 8건 |
| TC-448 | 181초 공개·일반 영상은 제외 사유가 없다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_sequential_exclusions_boundary_and_clean` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | POL-003 |
| TC-449 | 순차 교체 모드가 켜지면 제외 영상은 계획을 거부하고, 꺼져 있으면 계획은 만들되 제외 사유를 알린다(비공개 테스트 영상 첫 적용을 막지 않기 위함). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_exclusions_enforced_only_in_sequential_mode` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-019, POL-003, SEC-012 |
| TC-450 | 쓰기 실행 자리는 어떤 인자로 불러도 SafetyGateError로 거부하고 가짜 서비스를 건드리지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_execute_update_is_a_refusing_stub` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001 |
| TC-451 | 이 단위의 모듈에는 구글/네트워크 import, 서비스 객체 접근(.videos), 업데이트 호출(.update), 쓰기 호출 문자열이 없다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_no_youtube_write_or_network_code_in_sources` | docstring의 기대 결과가 모두 충족 | Pass(5건) | Pass | SEC-001, SEC-007 / 변형 5건 |
| TC-452 | 위 소스 검사가 `.update` 속성 접근을 전부 막으므로 dict.update도 쓰지 않는다는 사실을 별도로 고정한다(우회 불가). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_no_dict_update_calls_in_sources` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001 |
| TC-453 | 쓰기 규약(UpdateGateway)은 Protocol 선언만 있고 구현 클래스가 없다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_module_has_gateway_protocol_only` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001 |
| TC-454 | 후보·영상 테이블을 읽지 못하면 DatabaseError(한국어 안내)로 변환한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_db_read_failures_become_database_error` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007 |
| TC-455 | 여러 영상이 저장돼 있어도 후보가 가리키는 영상의 snippet으로 계획을 만든다(다른 영상 정보로 본문을 만들지 않음). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_updater.py::test_plan_uses_the_candidates_own_video` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-005 |
| TC-456 | UTC 날짜와 태평양 날짜가 다른 시각(UTC 10-10 03:00 = PT 10-09 20:00)에도 '하루'는 PT 기준(10-09 07:00Z ~ 10-10 07:00Z)으로 센다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_limits.py::test_daily_count_when_utc_and_pt_dates_differ` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-006, SEC-020 |
| TC-460 | 후보 상태 전이는 설계 3-2의 7개 간선만 허용한다(나머지 42개 조합 전부 거부, blocked·rolled_back은 종료 상태). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_transition_table_exact` | docstring의 기대 결과가 모두 충족 | Pass(49건) | Pass | SEC-006 / 변형 49건 |
| TC-461 | 없는 후보는 InputError, 알 수 없는 목표 상태는 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_transition_unknown_candidate_and_target` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass |  |
| TC-462 | 전이하면 updated_at이 갱신된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_transition_updates_timestamp` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-008 |
| TC-463 | 호출 직전 기록은 result=planned, 승인자·승인 시각·계획 해시·run_id와 snippet 전체 백업(description·tags·categoryId 포함)을 저장한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_begin_change_writes_planned_row_with_full_backup` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-009, FR-010, NFR-008, SEC-005, SEC-006 |
| TC-464 | 후보가 승인(approved) 상태가 아니면 이력 행을 만들지 않는다(승인 없는 상태 변경 불가). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_begin_change_requires_approved_candidate` | docstring의 기대 결과가 모두 충족 | Pass(5건) | Pass | FR-013, SEC-001 / 변형 5건 |
| TC-465 | 승인자·승인 시각(시간대 포함)이 없거나 형식이 틀리면 이력 행을 만들지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_begin_change_requires_approver_and_time` | docstring의 기대 결과가 모두 충족 | Pass(7건) | Pass | NFR-008, SEC-001 / 변형 7건 |
| TC-466 | 계획 내용(새 제목·snippet)이 해시와 맞지 않거나 승인된 후보와 다르면 중단하고 아무것도 쓰지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_begin_change_rejects_tampered_plan` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001, SEC-014 |
| TC-467 | 72시간 이내 재변경이면 begin_change도 거부한다(WU-5 5단계와 별개의 방어). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_begin_change_enforces_limits_again` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-004, SEC-020 |
| TC-468 | 제목·승인자·사유에 따옴표·세미콜론·SQL 조각이 있어도 값으로만 저장되고 테이블이 유지된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_begin_change_sql_binding_with_hostile_text` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-018 |
| TC-469 | 이력 저장이 DB 오류로 실패하면 DatabaseError(한국어 안내)이고 행이 남지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_begin_change_db_failure_is_database_error` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007 |
| TC-470 | 후보 테이블을 읽지 못하면 DatabaseError로 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_begin_change_candidate_read_failure` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007 |
| TC-471 | 적용 성공 기록은 이력(success·applied_at·verified_at·검증 결과)과 후보 approved→applied를 함께 바꾼다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_finish_success_moves_candidate_to_applied` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-006, SEC-010 |
| TC-472 | 검증 결과 없이 성공을 기록하면 verified_at은 비어 있다(검증 미실시 표시). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_finish_success_without_verify_result` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-010 |
| TC-473 | 실패·중단 기록은 후보 상태를 바꾸지 않고 applied_at을 비워 두며 사유 코드를 요구한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_finish_failure_keeps_candidate_approved` | docstring의 기대 결과가 모두 충족 | Pass(2건) | Pass | NFR-008, SEC-006 / 변형 2건 |
| TC-474 | 알 수 없는 결과값·없는 변경 번호는 거부한다(planned로 되돌리는 것도 불가). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_finish_unknown_result_and_unknown_change` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-006 |
| TC-475 | 이미 끝난 행(success/failed/aborted)은 다시 바꿀 수 없다(감사 기록 보존). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_finished_rows_are_immutable` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-008, SEC-006 |
| TC-476 | 후보 상태 전이가 불가능하면(승인 없이 적용 성공 기록 시도) 이력 행도 planned로 남는다(부분 반영 없음). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_finish_is_atomic_when_transition_is_illegal` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001 |
| TC-477 | 갱신 중 DB 오류는 DatabaseError로 변환되고 행은 planned로 유지된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_finish_db_failure` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007 |
| TC-478 | 읽은 뒤 다른 실행이 먼저 끝낸 경우(경쟁)에도 덮어쓰지 않고 중단한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_finish_rowcount_race` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-006 |
| TC-479 | 후보 상태가 읽은 뒤 바뀌었거나 DB 오류면 전이하지 않고 안전하게 중단한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_transition_race_and_db_error` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass |  |
| TC-480 | 게이트에서 막힌 시도는 aborted 행으로 남고(승인자 없음 허용), 후보 상태는 바뀌지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_record_aborted_rows_leave_state_untouched` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-008 |
| TC-481 | 변경 종류가 apply/rollback이 아니거나 사유 코드가 비면 기록하지 않는다. DB 오류는 DatabaseError. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_record_aborted_validations` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-008 |
| TC-482 | 이력 조회: 최신순, 영상별 필터, 건수 제한, 없는 번호는 InputError, 잘못된 limit 거부, 바인딩 안전. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_list_and_get_changes` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-010 |
| TC-483 | 롤백 계획은 백업 snippet의 원래 제목으로 복원하고, 본문은 지금 snippet 전체 + 제목만 교체이며 description·tags·categoryId가 보존된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_plan_rollback_restores_original_title_from_backup` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-011, SEC-005, SEC-006 |
| TC-484 | 롤백 plan_hash는 결정적이고, 같은 영상의 적용 해시와 다르며, snippet이 바뀌면 달라진다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_plan_rollback_hash_is_deterministic_and_distinct` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-014 |
| TC-485 | 적용 이후 제목 외 항목이 바뀌었으면 어떤 항목인지 알리고, 복원 본문은 지금 값을 유지한다(사람이 고친 설명을 덮지 않음). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_plan_rollback_reports_changes_since_backup` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-005 |
| TC-486 | 지금 제목이 우리가 적용한 제목과 다르면(Studio에서 또 바꿈) current_matches_applied가 거짓이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_plan_rollback_detects_title_changed_elsewhere` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-009 |
| TC-487 | 롤백 계획은 DB를 바꾸지 않고, 사고 복구를 막지 않도록 72시간·횟수·하루 상한 제한을 적용하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_plan_rollback_is_read_only_and_exempt_from_cadence` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-011, SEC-020 |
| TC-488 | 성공하지 않은 변경(실패·중단·미확정)은 롤백 대상이 아니다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_plan_rollback_requires_successful_apply` | docstring의 기대 결과가 모두 충족 | Pass(3건) | Pass | FR-011 / 변형 3건 |
| TC-489 | 롤백 행을 다시 롤백하거나 없는 번호를 지정하면 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_plan_rollback_refuses_rollback_rows_and_unknown` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-011 |
| TC-490 | 백업 snippet이 없거나 깨졌거나 이력의 이전 제목과 다르면 롤백 계획을 만들지 않고 복구 방법을 안내한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_plan_rollback_requires_consistent_backup` | docstring의 기대 결과가 모두 충족 | Pass(7건) | Pass | NFR-010, SEC-006 / 변형 7건 |
| TC-491 | 같은 영상에 이후 변경(성공 또는 미확정)이 있으면 오래된 제목으로 덮어쓰지 않도록 거부한다. 다른 영상·실패한 행은 영향이 없다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_plan_rollback_only_for_latest_change` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-011, SEC-009 |
| TC-492 | 후보가 applied/evaluated가 아니면(이미 rolled_back 등) 롤백 계획을 만들지 않는다. evaluated는 허용. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_plan_rollback_requires_candidate_in_applied_state` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass |  |
| TC-493 | 후보가 연결되지 않은 이력(candidate_id 없음)도 롤백 계획은 만들 수 있다. 연결은 있는데 후보가 사라졌으면 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_plan_rollback_without_candidate_row_link` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-011 |
| TC-494 | 저장된 영상 정보가 없으면 fetch를 안내하고, 이미 원래 제목이면 되돌릴 것이 없다고 알린다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_plan_rollback_needs_fresh_fetch_and_changed_title` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-011, NFR-007 |
| TC-495 | 설정의 제목 길이 상한을 나중에 낮춰도 원래 제목 복원은 막히지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_plan_rollback_allows_long_original_even_if_limit_lowered` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-011 |
| TC-496 | 롤백 DB 처리 전체: 계획 → 롤백 행(planned, 확인자·해시·현재 snippet 백업) → 성공 기록 → 후보 applied→rolled_back, 원래 적용 행은 그대로, 같은 변경은 다시 롤백 불가. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_rollback_db_flow_end_to_end` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-011, SEC-006 |
| TC-497 | 롤백 호출이 실패하면 후보는 applied로 남고 같은 변경을 다시 롤백 계획할 수 있다(실패 행은 '이후 변경'이 아님). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_rollback_failure_leaves_candidate_applied` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-011, NFR-008 |
| TC-498 | 영상 ID를 직접 입력해 확인하지 않았거나 확인자가 없으면 롤백 행을 만들지 않는다(승인 없는 상태 변경 불가). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_begin_rollback_requires_typed_video_id_and_approver` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-007, SEC-001 |
| TC-499 | 롤백 계획 내용이 해시와 다르거나, 계획 이후 같은 영상에 새 변경이 생겼거나, 후보 상태가 바뀌었으면 중단한다. DB 오류는 DatabaseError. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_history.py::test_begin_rollback_rejects_tampered_or_outdated_plan` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-009, SEC-014 |
| TC-500 | plan이 SCR-003 형식(제목 줄·변경 전/후·유지 항목·교체 제한 표·쿼터·계획 해시·A/B 안내·면책)을 출력하고 정상 종료한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_plan_cmd.py::test_plan_screen_shows_diff_hash_and_checks` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-004, FR-008, POL-002, RISK-011, SCR-003 |
| TC-501 | plan은 title_changes·쿼터·후보 상태를 전혀 바꾸지 않고(run_logs만 남김) 네트워크/구글 클라이언트를 건드리지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_plan_cmd.py::test_plan_writes_nothing_but_run_log` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-004, SEC-001 |
| TC-502 | 차단된 후보는 계획을 출력하지 않고 종료 코드 3으로 거부한다(해시도 출력하지 않음). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_plan_cmd.py::test_plan_refuses_blocked_candidate` | docstring의 기대 결과가 모두 충족 | Pass(2건) | Pass | FR-005, POL-001, SEC-001 / 변형 2건 |
| TC-503 | 없는 후보·fetch 안 한 영상은 종료 코드 1과 다음 행동 안내이고, 미검증 후보는 3이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_plan_cmd.py::test_plan_input_errors` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-004, NFR-007 |
| TC-504 | --candidate 필수(없으면 2), 숫자 아님 2, 0·음수·SQLite 범위 초과는 1, --live 옵션은 존재하지 않는다(2). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_plan_cmd.py::test_plan_option_validation` | docstring의 기대 결과가 모두 충족 | Pass(6건) | Pass | EVT-004, SEC-001 / 변형 6건 |
| TC-505 | 72시간 이내 재변경이면 plan이 사유와 가능한 시각을 보여 주고 종료 코드 3이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_plan_cmd.py::test_plan_limit_violation_screen` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-014, SCR-003, SEC-004 |
| TC-506 | 오늘 남은 쿼터가 필요량보다 적으면 [차단]과 함께 종료 코드 3이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_plan_cmd.py::test_plan_quota_short_screen` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SCR-003, SEC-002 |
| TC-507 | 24시간 넘은 영상 정보·검증 이후 바뀐 금칙어 사전·공식 A/B 비대상 영상·경고 후보를 [주의]로 알린다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_plan_cmd.py::test_plan_notices_stale_dictionary_and_exclusions` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-004, POL-003, SEC-017 |
| TC-508 | 금칙어 사전을 읽을 수 없어도 plan은 동작하고 확인하지 못했다고 알린다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_plan_cmd.py::test_plan_dictionary_unreadable_is_flagged` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-017 |
| TC-509 | 순차 교체 모드를 켜면 비공개 영상은 계획을 거부한다(종료 코드 3). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_plan_cmd.py::test_plan_sequential_mode_excludes_video` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-019, POL-003 |
| TC-510 | 영상 제목·검증 사유·카테고리·저장 시각의 ANSI 이스케이프·방향 제어 문자가 화면에 그대로 나오지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_plan_cmd.py::test_plan_sanitizes_external_strings` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-019 |
| TC-511 | `--plain`에서도 교체 제한 결과가 한 줄씩 `[결과] 항목: 내용`으로 나온다(표·구분선 없음, 스크린리더 친화). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_plan_cmd.py::test_plan_plain_mode` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SCR-003, UX-003 |
| TC-512 | 영상 정보가 fetch로 갱신되면 같은 후보라도 출력되는 계획 해시가 달라진다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_plan_cmd.py::test_plan_hash_in_output_tracks_snippet` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-009, SEC-014 |
| TC-513 | plan·rollback이 --help에 자동으로 나타나고, 이미 승인된 후보도 계획을 볼 수 있다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_plan_cmd.py::test_plan_is_discoverable_and_approved_candidate_ok` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-003, FR-017 |
| TC-520 | rollback --change N은 현재/복원 제목·유지 항목·계획 해시·A/B 안내를 보여 주고 DB와 네트워크를 건드리지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_rollback_cmd.py::test_rollback_plan_screen` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-007, FR-011, SCR-005 |
| TC-521 | (WU-5에서 변경) --live를 줘도 enable_live가 꺼져 있으면 2단계에서 종료 코드 3으로 막히고 쓰기 호출 0건·적용 이력 불변이며 rollback aborted 행만 남는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_rollback_cmd.py::test_rollback_live_without_enable_live_is_gated_and_writes_nothing` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001 |
| TC-522 | 없는 변경은 1, 실패한 변경·이미 롤백 대상이 아닌 변경은 3, 옵션 누락 2, 번호 범위 밖 1. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_rollback_cmd.py::test_rollback_refusals` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-007, NFR-007 |
| TC-523 | 이미 롤백이 기록된 변경은 다시 롤백할 수 없다(이후 변경 존재). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_rollback_cmd.py::test_rollback_after_rollback_is_refused` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-011 |
| TC-524 | 적용 이후 다른 항목·제목이 바뀌었거나 영상 정보가 오래됐으면 [주의]로 알린다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_rollback_cmd.py::test_rollback_cautions` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-005, SEC-009 |
| TC-525 | 제목·항목 이름·저장 시각의 ANSI/방향 제어 문자가 화면에 나오지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_rollback_cmd.py::test_rollback_sanitizes_external_strings` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-019 |
| TC-526 | (WU-5에서 변경) rollback 도움말이 --live(안전 조건 통과 시에만 복원)와 --approver를 설명한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_rollback_cmd.py::test_rollback_help_explains_live_and_approver` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007, SCR-001 |
| TC-983 | 모의 실행 끝에 실제 복원 명령(--approver 이름 --live)을 안내한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_rollback_cmd.py::test_rollback_dry_run_points_to_live_command` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-007 |
| TC-984 | rollback --change N --approver 이름 --live: 게이트 통과·영상 ID 입력 후 이전 제목으로 복원(종료 코드 0), LIVE 표시, 후보 rolled_back. 승인자 누락은 7단계에서 3. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_rollback_cmd.py::test_rollback_live_end_to_end_via_cli` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-007, FR-011, SCR-005, SCR-006 |
| TC-985 | 롤백 후 검증이 실패하면 종료 코드 1이고 경보를 출력한다(자동 재시도 없음). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_rollback_cmd.py::test_rollback_live_verification_failure_exit_1` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-011, SEC-010 |

### 4-1. 인수 조건 ↔ 테스트 케이스 추적
| AC | 인수 조건 | 연결 TC | 판정 |
|---|---|---|---|
| AC-01 | plan_hash 결정성·변경 민감도·규격 고정 | TC-421, TC-422, TC-423, TC-424, TC-425, TC-433, TC-484, TC-512 | 충족 |
| AC-02 | snippet 전체 보존 본문(description·tags·categoryId)·깊은 복사·백업 전체 저장 | TC-426, TC-427, TC-428, TC-429, TC-432, TC-463, TC-483, TC-455 | 충족 |
| AC-03 | 교체 제한 경계(72h/횟수3/노출1000/하루3·PT 날짜·서머타임) | TC-400, TC-401, TC-402, TC-403, TC-404, TC-405, TC-408, TC-409, TC-410, TC-411, TC-412, TC-415, TC-416, TC-419, TC-456 | 충족 |
| AC-04 | 노출수 불명 시 거부와 안내 | TC-406, TC-407, TC-413, TC-414 | 충족 |
| AC-05 | blocked·미검증·처리 완료 후보 거부 및 입력 오류 | TC-434, TC-435, TC-436, TC-437, TC-438, TC-439, TC-440, TC-441, TC-502, TC-503 | 충족 |
| AC-06 | plan 화면·드라이런·경고/주의 표시·--plain | TC-442, TC-443, TC-444, TC-445, TC-446, TC-500, TC-505, TC-506, TC-507, TC-508, TC-511, TC-513 | 충족 |
| AC-07 | 쓰기 호출 0건(소스 AST 검사·가짜 서비스·소켓/build 차단·DB 불변) | TC-450, TC-451, TC-452, TC-453, TC-501, TC-521 | 충족 |
| AC-08 | 외부 문자열 정화 | TC-430, TC-510, TC-525 | 충족 |
| AC-09 | SQL 바인딩 | TC-418, TC-468, TC-482 | 충족 |
| AC-10 | 승인 없는 이력/상태 변경 불가·aborted 기록 | TC-464, TC-465, TC-466, TC-467, TC-480, TC-481, TC-498 | 충족 |
| AC-11 | 후보 상태 머신·원자적 종료·감사 행 불변 | TC-460, TC-461, TC-462, TC-471, TC-472, TC-473, TC-474, TC-475, TC-476, TC-478, TC-479 | 충족 |
| AC-12 | 롤백 계획(원래 제목 복원·본문 보존·최신 변경만·제한 면제) | TC-483, TC-484, TC-485, TC-486, TC-487, TC-488, TC-489, TC-490, TC-491, TC-492, TC-493, TC-494, TC-495 | 충족 |
| AC-13 | 롤백 DB 처리(영상 ID 확인·planned→success·후보 rolled_back) | TC-496, TC-497, TC-498, TC-499 | 충족 |
| AC-14 | rollback 명령(계획 출력·--live 스텁 거부) | TC-520, TC-521, TC-522, TC-523, TC-524, TC-525, TC-526 | 충족 |
| AC-15 | 옵션/입력 검증·제외 영상군 | TC-447, TC-448, TC-449, TC-504, TC-509, TC-522 | 충족 |
| AC-16 | DB 오류의 한국어 DatabaseError 변환 | TC-420, TC-454, TC-469, TC-470, TC-477, TC-482 | 충족 |

- 인수 조건에 연결되지 않은 TC(추가 안전 케이스): TC-417, TC-431, TC-983, TC-984, TC-985
- 정상 경로, 경계값(날짜 경계·상한·빈 입력), 예외 입력(잘못된 형식·악성 문자열), 권한 경계를 포함했다.

## 5. 커버리지
- 전체 지표: 이 단위 모듈(youtube_title.limits, youtube_title.updater, youtube_title.history, youtube_title.commands.plan, youtube_title.commands.rollback)의 줄+분기 합산 **100%** (pytest-cov, `--cov-branch`)
- 회귀(이전 단위 산출물을 깨뜨리지 않음): 전체 테스트 스위트 `1093 passed, 1 skipped` (통과)
- 호환 실행: 3.11 → 241 passed / 3.13 → 241 passed / 3.12(주) → 241 passed
- 커버되지 않은 부분과 사유:
  - src/youtube_title/commands/plan.py          76      0     24      0   100%
  - src/youtube_title/commands/rollback.py      41      0     10      0   100%
  - src/youtube_title/history.py               175      0     58      0   100%
  - src/youtube_title/limits.py                 93      0     16      0   100%
  - src/youtube_title/updater.py               157      0     42      0   100%
  - 이 단위 모듈의 줄·분기 커버리지는 위 수치.

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 내용 |
|----|------|-----------|--------|------|-----------|
| DEF-6-019 | [테스트 결함] 서브에이전트 자체 변이 점검 1회차에서 PT/UTC 날짜 경계·종료 행 보호·다중 영상 선택 3곳을 놓침 | 자체 변이 점검 | Medium | Fixed | TC-455, TC-456, TC-475 추가 |

- 서브에이전트가 이 단위 안에서 수정·재검증. 오케스트레이터 독립 변이 점검 결과는 부록 A.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트: `.harness-tmp/junit_06.xml`, `.harness-tmp/junit_py311.xml`, `.harness-tmp/junit_py313.xml`, `.harness-tmp/junit_regress.xml`, `.harness-tmp/venv_py311`, `.harness-tmp/venv_py312`, `.harness-tmp/venv_py313` (+ 변이 점검용 임시 사본 `.harness-tmp/mut_06/`, 편집 설치로 생긴 `src/*.egg-info`, 캐시 `__pycache__`/`.coverage`)
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예 [ ] 아니오 — 예외: 편집 설치가 `src/youtube_title.egg-info/`를 만들고 파이썬이 `__pycache__`를 만든다(둘 다 `.gitignore` 대상이며 정리 대상에 포함)
- 정리(삭제) 완료 여부: 예. 결과서 생성 스크립트가 `.harness-tmp/`, `data/`, `.coverage`, `src/*.egg-info`, `__pycache__`를 삭제했다
- **정리 후 점검**: 이 스크립트는 git을 실행하지 않는다(커밋·푸시는 오케스트레이터가 DEC-027에 따라 별도 수행). 파일시스템 점검 결과: 잔여물 없음 (점검 목록: .harness-tmp, .venv*, venv, *.egg-info, .pytest_cache, .coverage*, __pycache__, data)
- 병렬 실행이었다면: 해당 없음(단독 실행)
- 이번 테스트 도중 강제 중단: [x] 없음 / [ ] 있음

## 8. 리스크 및 잔존 이슈
- **미검증(PASS로 세지 않음)**: 읽기 전용 필드(thumbnails 등)를 포함한 snippet을 videos.update가 받는지(12단계 실측), 노출수 인정 기준의 실데이터 적합성
- 열린 질문: 오래된 planned 행의 수동 정리 방법, blocked 후보 재검증 시 상태 복귀(설계 3-2와 validate 불일치, DEC-027)

## 9. 결론 및 판정
- 판정: **PASS**
- 근거: 실패 TC 0건, 미수행 TC 0건(-), AC↔TC 추적 문제 0건, 정적 분석(pyflakes) 통과, 변이 점검 47/47 잡아냄, Open 결함 0건
- WU-5가 `updater.compute_plan_hash`·`history.begin_change`·`plan_rollback`을 입력으로 쓸 수 있다.

## 10. 내부 검증 (최소 2회)
- 1차: 서브에이전트 구현·자체 변이 점검 2회(50곳)
- 2차(독립 심사자 관점): 오케스트레이터가 별도 변이 점검으로 안전 로직을 일부러 망가뜨림. 결과는 부록 A
- 3차: 결함 0건 확인
- 검증 로그 파일 경로: `docs/harness/verify-log_unit-4-test.md`

### 부록 A. 변이 점검(코드를 일부러 망가뜨려 테스트가 실패하는지 확인)
| 변이 | 파일 | 결과 |
|---|---|---|
| 간격 경계(>=→>) | `limits.py` | 잡아냄(테스트 실패) |
| 횟수 경계(<→<=) | `limits.py` | 잡아냄(테스트 실패) |
| 노출수 경계(>=→>) | `limits.py` | 잡아냄(테스트 실패) |
| 노출수 모름도 통과 | `limits.py` | 잡아냄(테스트 실패) |
| 하루 상한 경계(<→<=) | `limits.py` | 잡아냄(테스트 실패) |
| 첫 변경 노출수 면제 제거 | `limits.py` | 잡아냄(테스트 실패) |
| planned를 변경으로 세지 않음 | `limits.py` | 잡아냄(테스트 실패) |
| failed도 변경으로 셈 | `limits.py` | 잡아냄(테스트 실패) |
| 하루 경계를 UTC로 | `limits.py` | 잡아냄(테스트 실패) |
| 하루 건수에 롤백 포함 | `limits.py` | 잡아냄(테스트 실패) |
| 노출수 기간 조건 제거 | `limits.py` | 잡아냄(테스트 실패) |
| 전체 판정 any로 완화 | `limits.py` | 잡아냄(테스트 실패) |
| 깨진 시각도 통과 | `limits.py` | 잡아냄(테스트 실패) |
| plan_hash에서 snippet 제외 | `updater.py` | 잡아냄(테스트 실패) |
| plan_hash에서 새 제목 제외 | `updater.py` | 잡아냄(테스트 실패) |
| plan_hash에서 kind 제외 | `updater.py` | 잡아냄(테스트 실패) |
| 본문 깊은 복사 제거 | `updater.py` | 잡아냄(테스트 실패) |
| 본문에서 description 누락 | `updater.py` | 잡아냄(테스트 실패) |
| < > 검사 제거 | `updater.py` | 잡아냄(테스트 실패) |
| 제어문자 검사 제거 | `updater.py` | 잡아냄(테스트 실패) |
| 길이 상한 경계(>→>=) | `updater.py` | 잡아냄(테스트 실패) |
| categoryId 검사 제거 | `updater.py` | 잡아냄(테스트 실패) |
| 같은 제목 허용 | `updater.py` | 잡아냄(테스트 실패) |
| 저장 불일치 검사 제거 | `updater.py` | 잡아냄(테스트 실패) |
| blocked 후보 허용 | `updater.py` | 잡아냄(테스트 실패) |
| 처리 완료 후보 허용 | `updater.py` | 잡아냄(테스트 실패) |
| 미검증 후보 허용 | `updater.py` | 잡아냄(테스트 실패) |
| 순차 모드 제외 무시 | `updater.py` | 잡아냄(테스트 실패) |
| 오래됨 판정 경계 | `updater.py` | 잡아냄(테스트 실패) |
| 쓰기 자리 거부 제거 | `updater.py` | 잡아냄(테스트 실패) |
| 승인 상태 검사 제거 | `history.py` | 잡아냄(테스트 실패) |
| 후보-계획 일치 검사 제거 | `history.py` | 잡아냄(테스트 실패) |
| 계획 해시 검증 제거(적용) | `history.py` | 잡아냄(테스트 실패) |
| 이력 기록 전 제한 재검사 제거 | `history.py` | 잡아냄(테스트 실패) |
| 승인자 검증 제거 | `history.py` | 잡아냄(테스트 실패) |
| 끝난 행 수정 허용 | `history.py` | 잡아냄(테스트 실패) |
| 적용 성공 시 상태 전이 제거 | `history.py` | 잡아냄(테스트 실패) |
| 허용 전이 확장(blocked→approved) | `history.py` | 잡아냄(테스트 실패) |
| filtered→applied 직행 허용 | `history.py` | 잡아냄(테스트 실패) |
| 롤백: 최신 변경만 제한 제거 | `history.py` | 잡아냄(테스트 실패) |
| 롤백: 성공한 적용만 제한 제거 | `history.py` | 잡아냄(테스트 실패) |
| 롤백: 롤백 재롤백 허용 | `history.py` | 잡아냄(테스트 실패) |
| 롤백: 백업 일치 검사 제거 | `history.py` | 잡아냄(테스트 실패) |
| 롤백 확인 입력 검사 제거 | `history.py` | 잡아냄(테스트 실패) |
| 롤백 해시 kind 구분 제거 | `history.py` | 잡아냄(테스트 실패) |
| 롤백 후 후보 상태 전이 제거 | `history.py` | 잡아냄(테스트 실패) |
| 완료 처리 원자성 제거 | `history.py` | 잡아냄(테스트 실패) |

### 부록 B. 공유 문서 갱신
`traceability.md`의 단위테스트 컬럼과 구현 상태를 스크립트로 갱신했다(통과한 TC만 연결).
