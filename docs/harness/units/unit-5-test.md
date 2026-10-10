# 테스트 결과서 — WU-5 승인·쓰기 안전 게이트·apply/rollback --live (6단계 단위 테스트)

## 1. 개요
- 테스트 대상: WU-5 승인·쓰기 안전 게이트·apply/rollback --live (`approvals, live_guard, commands/apply, commands/approve, commands/rollback`)
- 테스트 유형: 단위
- 적용 Tier: Standard (규칙 B 원문: 최소 2회)
- 적용 속도 트랙: L5
- 병렬 실행 정보: 단독 실행(독립 검증 단계)
- 테스트 목적: `unit-5-note.md`의 인수 조건(AC)을 테스트로 증명하고 안전 로직의 회귀를 막는다
- 관련 산출물: `docs/yt/DESIGN.md`, `docs/harness/units/unit-5-note.md`, `docs/yt/02_planning.md`
- 테스트 수행자(에이전트): 오케스트레이터(06단계 역할 직접 수행)
- 테스트 일시: 2026-10-10

## 2. 테스트 범위 및 제외 범위
- 범위(In-Scope): 승인 파일(해시 묶음·만료·1회용·HMAC), 쓰기 안전 게이트 14단계, 유일한 videos.update 호출, 호출 도중 오류 처리, 사후 검증, `apply`·`approve`·`rollback --live` 명령
- 제외 범위(Out-of-Scope) 및 사유: 실제 YouTube 쓰기 호출(12단계, 사용자 승인 필요), 읽기 전용 필드를 포함한 snippet이 videos.update에서 받아들여지는지([확인 필요])

## 3. 테스트 환경
- 실행 환경: Linux, Python 3.12.3 (주 실행) · 3.11 · 3.13 (호환 확인), pytest, pytest-cov. 가상환경은 `.harness-tmp/` 아래에만 생성
- 테스트 데이터: 임시 폴더의 가짜 설정·DB·후보, 가짜 토큰 문자열(실제 비밀 아님). **실제 YouTube API는 호출하지 않음**
- 전제 조건: 이전 단위 WU-0~WU-4 PASS(WU-4 독립 검증 포함)

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고(검증하는 ID) |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-520 | rollback --change N은 현재/복원 제목·유지 항목·계획 해시·A/B 안내를 보여 주고 DB와 네트워크를 건드리지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_rollback_cmd.py::test_rollback_plan_screen` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-007, FR-011, SCR-005 |
| TC-521 | (WU-5에서 변경) --live를 줘도 enable_live가 꺼져 있으면 2단계에서 종료 코드 3으로 막히고 쓰기 호출 0건·적용 이력 불변이며 rollback aborted 행만 남는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_rollback_cmd.py::test_rollback_live_without_enable_live_is_gated_and_writes_nothing` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001 |
| TC-522 | 없는 변경은 1, 실패한 변경·이미 롤백 대상이 아닌 변경은 3, 옵션 누락 2, 번호 범위 밖 1. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_rollback_cmd.py::test_rollback_refusals` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-007, NFR-007 |
| TC-523 | 이미 롤백이 기록된 변경은 다시 롤백할 수 없다(이후 변경 존재). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_rollback_cmd.py::test_rollback_after_rollback_is_refused` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-011 |
| TC-524 | 적용 이후 다른 항목·제목이 바뀌었거나 영상 정보가 오래됐으면 [주의]로 알린다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_rollback_cmd.py::test_rollback_cautions` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-005, SEC-009 |
| TC-525 | 제목·항목 이름·저장 시각의 ANSI/방향 제어 문자가 화면에 나오지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_rollback_cmd.py::test_rollback_sanitizes_external_strings` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-019 |
| TC-526 | (WU-5에서 변경) rollback 도움말이 --live(안전 조건 통과 시에만 복원)와 --approver를 설명한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_rollback_cmd.py::test_rollback_help_explains_live_and_approver` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007, SCR-001 |
| TC-530 | 승인 파일은 영상·후보·새 제목·계획 해시·승인자·승인/만료 시각을 담고 used=false이며 승인 폴더 안 정해진 이름으로 만들어진다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_create_writes_bound_expiring_unused_file` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-202, FR-013, SEC-014 |
| TC-531 | 승인 파일과 인증 키 파일은 현재 사용자만 읽을 수 있게 제한을 시도한다(POSIX 0600). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_file_permissions_are_restricted_on_posix` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-014, SEC-015 |
| TC-532 | 만든 승인은 다시 읽어 검증을 통과한다(같은 영상·후보·제목·해시, 만료 전). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_load_and_verify_roundtrip` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-013, SEC-014 |
| TC-533 | 승인 파일을 손으로 고치면(제목·해시·승인자·만료 연장·used 변경 등) 인증값이 맞지 않아 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_edited_file_is_rejected_by_mac` | docstring의 기대 결과가 모두 충족 | Pass(9건) | Pass | SEC-014 / 변형 9건 |
| TC-534 | 사용된 승인 파일의 used를 false로 되돌리거나 오래된 사본으로 바꿔치면 인증값 때문에 거부된다(1회용 우회 방지). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_unused_flag_reset_after_use_is_rejected` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-014 |
| TC-535 | 다른 키(다른 PC·다른 사람)로 만든 승인 파일은 같은 내용이어도 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_forged_file_made_with_another_key_is_rejected` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-014 |
| TC-536 | 검증 경로는 키가 없으면 새로 만들지 않고 거부한다(키를 만들어 위조 파일을 통과시키는 길 차단). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_missing_key_rejects_without_creating_one` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-014 |
| TC-537 | 손상된 키 파일(16진수 아님·길이 틀림)은 읽기·만들기 모두 거부하고 덮어쓰지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_corrupt_key_is_rejected_on_both_paths` | docstring의 기대 결과가 모두 충족 | Pass(3건) | Pass | SEC-014 / 변형 3건 |
| TC-538 | 키는 첫 승인 때 한 번 만들어지고 이후 승인에서도 같은 키를 쓴다(기존 승인이 무효가 되지 않음). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_key_is_created_once_and_stable` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-014 |
| TC-539 | 두 실행이 동시에 키를 만들려 하면(O_EXCL 충돌) 먼저 만든 쪽의 키를 쓴다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_key_creation_race_uses_the_winner` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-014 |
| TC-540 | 키를 저장할 폴더를 만들 수 없으면 한국어 오류로 알리고 승인 파일도 만들지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_key_dir_unwritable_is_a_korean_error` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007, SEC-014 |
| TC-541 | 만료 1초 전은 통과, 만료 시각 정각과 그 이후는 만료로 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_expiry_boundary` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-013, SEC-014 |
| TC-542 | mark_used 후에는 검증도, 다시 mark_used도 거부한다(1회용). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_used_approval_cannot_be_used_again` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-014 |
| TC-543 | 확인한 뒤 승인 파일이 다른 승인(다른 해시)으로 바뀌었으면 소진하지 않고 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_mark_used_rejects_changed_file` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-014 |
| TC-544 | 다른 계획 해시(영상 정보가 바뀜)·다른 새 제목·다른 영상·다른 후보에는 승인을 재활용할 수 없다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_approval_does_not_transfer_to_another_plan` | docstring의 기대 결과가 모두 충족 | Pass(4건) | Pass | SEC-014 / 변형 4건 |
| TC-545 | 승인 시각이 미래이거나 유효 기간이 설정 상한(approval.ttl_hours)을 넘으면 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_future_dated_and_overlong_periods_are_rejected` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-014 |
| TC-546 | 영상 ID가 정규식(영문·숫자·-·_ 11자)을 통과하지 못하면 경로를 만들지 않는다(경로 조작 차단). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_path_traversal_and_bad_video_ids` | docstring의 기대 결과가 모두 충족 | Pass(10건) | Pass | SEC-011, SEC-014 / 변형 10건 |
| TC-547 | 후보 번호가 1 이상의 정수가 아니면 경로를 만들지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_bad_candidate_ids` | docstring의 기대 결과가 모두 충족 | Pass(6건) | Pass | SEC-014 / 변형 6건 |
| TC-548 | 승인 파일이 심볼릭 링크이면 폴더 밖을 가리키든 폴더 안 다른 파일을 가리키든 거부한다(위치 제한). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_symlinked_file_is_rejected` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-014 |
| TC-549 | 승인 파일이 없으면 approve 명령을 안내한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_missing_file_has_actionable_message` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-013, NFR-007 |
| TC-550 | 인증값이 맞더라도(키를 가진 쪽이 만들었더라도) 항목 구성·형식이 규격과 다르면 거부한다(fail-closed). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_schema_violations_are_rejected_even_with_valid_mac` | docstring의 기대 결과가 모두 충족 | Pass(20건) | Pass | SEC-014 / 변형 20건 |
| TC-551 | 비어 있거나 JSON이 아니거나 객체가 아닌 파일은 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_garbage_files_are_rejected` | docstring의 기대 결과가 모두 충족 | Pass(6건) | Pass | SEC-014, SEC-016 / 변형 6건 |
| TC-552 | 크기 상한(8KB)을 넘거나 UTF-8이 아닌 파일은 읽지 않고 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_oversize_and_non_utf8_files_are_rejected` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-014, SEC-016 |
| TC-553 | 같은 이름의 승인 파일이 있으면 overwrite 없이는 만들지 않고, 요청하면 새 승인으로 교체한다(이전 해시는 사라짐). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_create_refuses_overwrite_unless_asked` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SCR-004, SEC-014 |
| TC-554 | 새 제목·계획 해시·승인자·유효 시간이 잘못되면 파일도 키도 만들지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_create_validates_inputs_and_writes_nothing` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-013, SEC-014 |
| TC-555 | 유효 시간은 1시간 이상 설정값(approval.ttl_hours) 이하만 가능하다(경계 포함). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_ttl_boundaries_follow_the_setting` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-013, SEC-014 |
| TC-556 | 승인자 이름은 비어 있지 않고 40자 이하이며 제어 문자(ANSI·줄바꿈·방향 문자)가 없어야 한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_approver_name_rules` | docstring의 기대 결과가 모두 충족 | Pass(8건) | Pass | NFR-008, SEC-019 / 변형 8건 |
| TC-557 | 파일 쓰기가 중간에 실패하면 한국어 오류로 알리고 기존 승인 파일과 임시 파일을 남기지 않는다(교체는 원자적). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_write_failure_leaves_no_partial_file` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007, SEC-014 |
| TC-558 | 임시 파일 정리마저 실패해도 원래 저장 실패 오류를 그대로 알린다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_write_failure_when_tmp_cannot_be_removed_still_reports` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007 |
| TC-559 | inspect_active는 유효·미사용·미만료 승인만 돌려주고, 없음·만료·사용됨·훼손은 예외 없이 None이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_inspect_active_never_raises` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SCR-004 |
| TC-560 | remove_approval은 파일을 지우고, 없으면 아무 일도 하지 않으며, 지울 수 없으면 한국어 오류를 낸다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_remove_approval` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-014 |
| TC-561 | 오류 메시지·안내에 인증 키 값이 나오지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approvals.py::test_secrets_are_not_in_error_messages` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-008, SEC-014 |
| TC-570 | 14단계를 모두 통과하면 videos.update를 정확히 1회 호출하고, 이력 success·후보 applied·승인 소진·쿼터 기록이 남는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_all_gates_pass_calls_update_exactly_once` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-009, FR-012, SEC-001, SEC-010, SEC-014 |
| TC-571 | 순서: 재조회(6) → 영상 ID 확인(10) → 쓰기 토큰 로드(11) → videos.update(12) → 재조회 검증(13). 쓰기 토큰은 1번만, 사람 확인 뒤에만 읽는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_write_happens_only_after_human_confirmation_in_documented_order` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-012, SEC-001, SEC-015 |
| TC-572 | 요청 본문은 description·tags·categoryId 등 snippet 전체를 그대로 두고 제목만 바꾸며, 백업은 적용 직전 snippet 전체다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_request_body_preserves_every_field_and_backup_is_whole_snippet` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-009, SEC-005 |
| TC-573 | 본문은 저장본이 아니라 6단계에서 다시 조회한 snippet으로 만든다(승인 당시와 같을 때만 통과하므로 결과가 같아도 출처가 다르다). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_body_is_built_from_fresh_snippet_not_stored_copy` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-005, SEC-009 |
| TC-574 | 14단계 중 1~10단계 각각이 실패하면 videos.update 가짜 호출 0회·쓰기 토큰 미로드·승인 미소진이며 aborted 행(GATE-nn) 하나만 남고 종료 코드 3이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_each_gate_failure_stops_before_any_write` | docstring의 기대 결과가 모두 충족 | Pass(27건) | Pass | FR-012, SEC-001, SEC-002, SEC-004, SEC-009, SEC-012, SEC-014, SEC-020 / 변형 27건 |
| TC-575 | 1단계: live_flag가 거짓이면 어떤 조건이 맞아도 중단한다(엔진 수준 방어). 쓰기 0회, aborted GATE-01 기록. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_step1_requires_live_flag` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001 |
| TC-576 | enable_live는 불리언 true만 인정한다(문자열 'true'·1 등은 거부). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_enable_live_must_be_boolean_true` | docstring의 기대 결과가 모두 충족 | Pass(4건) | Pass | SEC-001 / 변형 4건 |
| TC-577 | settings.yaml에 enable_live=true와 허용 목록이 있어도 무시한다(settings.local.yaml에서만 유효): 2단계에서 중단, 쓰기 0회. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_enable_live_in_settings_yaml_is_ignored` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-010, SEC-001, SEC-012 |
| TC-578 | 여러 조건이 동시에 틀려 있을 때 문서 순서(2→3→…→10)대로 하나씩만 드러난다: 앞 단계를 고칠 때마다 다음 단계에서 멈춘다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_gate_order_is_exactly_the_documented_one` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001 |
| TC-579 | 쿼터는 남은 양이 쓰기 50 + 조회 2 = 52 units 이상일 때만 통과한다(52 통과, 51 거부). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_quota_boundary_needs_update_plus_two_reads` | docstring의 기대 결과가 모두 충족 | Pass(2건) | Pass | FR-015, SEC-002 / 변형 2건 |
| TC-580 | 하루 live 적용 상한(3) 경계: 오늘 다른 영상에 2건 적용했으면 통과하고 이번이 3건째가 된다(3건이면 5단계 TC-574에서 중단). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_daily_cap_boundary_two_pass` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-020 |
| TC-581 | 같은 날 3건째 적용이 성공한 뒤에는 4건째가 5단계에서 막힌다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_daily_cap_counts_the_apply_just_made` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-020 |
| TC-582 | 적용 후 설명이 사라졌으면 사후 검증 실패: result=success + verify.ok=false, 경보와 rollback 안내만 하고 자동 롤백(추가 update 호출)은 하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_verification_failure_records_success_with_ok_false_and_never_rolls_back` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001, SEC-010 |
| TC-583 | 호출은 성공했는데 재조회 제목이 새 제목이 아니면 검증 실패로 기록한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_title_not_reflected_is_a_verification_failure` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-010 |
| TC-584 | 사후 재조회 자체가 실패하면 검증을 하지 못했다고 기록·경보한다(성공으로 속이지 않음). 호출은 1회뿐이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_verification_read_failure_is_recorded_not_hidden` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-010 |
| TC-585 | 설명·태그·카테고리 외 항목이 달라지면 검증 실패로 보지 않고 이름만 알린다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_other_changed_fields_are_reported_but_not_a_failure` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-010 |
| TC-586 | 비교 규칙: 태그 순서가 달라도 변경으로 본다, 양쪽에 없는 선택 항목은 같다고 본다, localized는 무시한다, 제목이 다르면 실패. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_compare_after_rules` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-010 |
| TC-587 | 구글이 400으로 거절하면(처리되지 않음이 분명) 재시도 없이 1회 호출, 이력 failed·쿼터 50 units 차감 유지, 후보는 approved 그대로, 승인은 소진된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_definite_rejection_400_marks_failed_with_one_attempt` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-008, SEC-003, SEC-006 |
| TC-588 | 쿼터 초과(403)·인증 거부(401/403)는 재시도하지 않고 failed로 기록한다(제목은 바뀌지 않음). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_quota_and_auth_rejections_are_not_retried` | docstring의 기대 결과가 모두 충족 | Pass(4건) | Pass | SEC-002, SEC-003, SEC-015 / 변형 4건 |
| TC-589 | 429는 최대 2회 재시도(1초→2초 대기)한 뒤 처리되지 않았음이 분명한 실패(failed)로 기록하며, 시도마다 50 units를 선예약해 차감한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_429_is_retried_twice_then_failed_as_definite` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-008, NFR-004, SEC-003 |
| TC-590 | 503 한 번 뒤 성공하면 1초 대기 후 재시도해 success로 끝나고, 실패한 시도의 쿼터도 차감이 남는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_503_then_success_charges_both_attempts` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-008, SEC-003 |
| TC-591 | 5xx가 계속되면 반영 여부를 알 수 없으므로 재조회로 확인하고, 새 제목이 아니면 이력을 planned로 남긴다(자동 삭제 없음). 쿼터 150 units 차감 유지, 후보 approved 유지, 안내 출력. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_persistent_5xx_leaves_planned_and_quota_when_state_unknown` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-008, NFR-008, SEC-006 |
| TC-592 | 응답이 끊겼지만(타임아웃) 서버에는 반영됐으면, 재조회로 새 제목을 확인해 success로 이어서 검증한다(메모 포함). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_timeout_after_server_applied_is_recovered_by_reread` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-008, SEC-010 |
| TC-593 | 타임아웃 뒤 재조회도 실패하면 결과를 알 수 없으므로 planned로 남기고 후보·승인 상태를 되돌리지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_timeout_then_unreadable_state_stays_planned` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-008 |
| TC-594 | 앞선 시도가 '알 수 없음'(503)이었다면 마지막이 분명한 거절(400)이어도 알 수 없음으로 취급해 planned로 남긴다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_definite_error_after_an_unknown_attempt_is_still_unknown` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass |  |
| TC-595 | 재시도 선예약이 쿼터 상한에 걸려도(첫 시도가 503) 상태를 알 수 없음으로 취급해 planned로 남기고 호출은 더 하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_quota_runs_out_during_retry_keeps_state_unknown` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-008, SEC-002 |
| TC-596 | 예상 못 한 예외(메시지에 토큰 포함)도 반영 여부 불명으로 planned에 남기고, 메시지·로그·DB·화면 어디에도 토큰이 나오지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_unexpected_exception_is_unknown_and_secrets_stay_out` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-008, SEC-015 |
| TC-597 | 호출 중 Ctrl+C: 더 호출하지 않고 planned로 남기며 예외를 그대로 올린다. 쿼터 차감은 유지된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_keyboard_interrupt_during_update_leaves_planned_and_reraises` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-008, NFR-008 |
| TC-598 | 영상 ID 입력 중 Ctrl+C: 쓰기 없이 aborted(GATE-10)를 남기고 예외를 그대로 올린다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_keyboard_interrupt_at_confirmation_records_abort` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-008 |
| TC-599 | 쓰기 로그인이 없거나 만료돼 쓰기 토큰을 못 읽으면 11단계에서 중단하고, 승인은 소진하지 않으며 DB에는 aborted만 남는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_write_token_failure_aborts_without_consuming_approval` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001, SEC-015 |
| TC-900 | DB 사본(백업)을 만들 수 없으면 쓰기 전에 중단하고 승인은 소진하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_backup_failure_aborts_before_consuming_approval` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-010, SEC-006 |
| TC-901 | 쓰기 전 DB 사본이 data/backups에 만들어지고, 그 사본에는 아직 이번 변경의 planned 행이 없다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_backup_copy_is_made_before_the_write` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-010 |
| TC-902 | planned 행을 만들지 못하면 호출하지 않는다. 승인은 이미 소진되어 새 승인이 필요하다(최대 1회 우선). aborted GATE-11 기록. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_history_insert_failure_after_approval_consumed_leaves_no_write` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-008, SEC-014 |
| TC-903 | 승인 소진(used=true 기록)에 실패하면 이력 행도 호출도 없이 중단한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_approval_consume_failure_aborts_before_history` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-014 |
| TC-904 | planned 행을 만든 뒤 쓰기 쿼터 예약이 거절되면 호출하지 않고 그 행을 aborted(GATE-11)로 끝낸다(중복 aborted 행 없음). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_quota_reservation_failure_after_planned_marks_aborted` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-008, SEC-002 |
| TC-905 | 구글에는 반영됐는데 이력을 success로 바꾸지 못하면 경보를 출력하고 오류를 올린다(조용히 넘어가지 않음). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_record_finish_failure_after_success_is_loud` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-008 |
| TC-906 | 검증에서 차단된 후보는 게이트 이전(계획 단계)에서 거부하고 aborted(PLAN) 행으로 남긴다. 쓰기 0회. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_blocked_candidate_is_refused_and_audited` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-008, SEC-001 |
| TC-907 | 없는 후보 번호는 오류로 거부하고(기록할 대상이 없어) 이력을 만들지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_unknown_candidate_is_refused_without_audit` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-005 |
| TC-908 | aborted 기록 자체가 실패해도 원래 중단 사유(게이트 오류)가 가려지지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_audit_failure_does_not_mask_the_original_block` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-008 |
| TC-909 | 적용이 끝난 후보를 같은 승인 파일로 다시 적용할 수 없다(후보가 applied, 승인 used). 두 번째 호출은 쓰기 0회. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_second_apply_of_the_same_candidate_is_refused` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-014 |
| TC-910 | 사용 전 승인 파일 사본을 되돌려 놓고 재생해도(인증값은 통과) 후보 상태·이력 때문에 다시 적용되지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_replayed_unused_approval_copy_cannot_reapply` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-014 |
| TC-911 | 모의 실행(preview)은 구글에 연결하지 않고 DB·쿼터·승인 파일에 아무것도 쓰지 않으며, 막는 조건을 알려 준다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_preview_reports_gates_without_any_side_effect` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-008, SEC-001 |
| TC-912 | 미리보기는 enable_live 꺼짐·허용 목록·쿼터·제한·승인 문제를 단계별 [차단]으로 보여 주고, 기준선 없음은 경고로 보여 준다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_preview_shows_each_blocking_gate` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001, SEC-012 |
| TC-913 | 롤백은 같은 엔진으로 이전 제목을 복원한다: 재조회→영상 ID 확인→쓰기 토큰→update 1회→검증, 이력 rollback success, 후보 rolled_back, 승인 파일 없이 확인자만. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_rollback_restores_title_with_same_gates` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-007, FR-011, SEC-006, SEC-015 |
| TC-914 | 롤백은 72시간 간격·횟수·노출수·하루 상한을 적용하지 않는다(방금 적용했고 하루 상한에 도달해도 복구 가능). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_rollback_is_exempt_from_cadence_limits` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-011 |
| TC-915 | 롤백도 enable_live·허용 목록·쿼터·미확정 기록·재조회 제목/계획 해시·영상 ID 확인·쓰기 토큰 실패 시 update 0회, aborted(rollback, GATE-nn)만 남고 후보는 applied 그대로다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_rollback_gate_failures_write_nothing` | docstring의 기대 결과가 모두 충족 | Pass(7건) | Pass | FR-011, SEC-001, SEC-009, SEC-012 / 변형 7건 |
| TC-916 | 확인자 이름 없이는 롤백하지 않는다(7단계). 이름에 제어 문자가 있어도 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_rollback_requires_an_approver_name` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-008, SEC-019 |
| TC-917 | 엔진에 live_flag가 없으면 롤백도 1단계에서 중단한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_rollback_requires_live_flag` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001 |
| TC-918 | 롤백 계획을 만들 수 없는 경우(이미 롤백됨·이후 변경 존재)는 거부하고 aborted(PLAN) 행을 남긴다. 없는 변경 번호는 기록 없이 오류. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_rollback_plan_refusals_are_audited` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-011, SEC-006 |
| TC-919 | 롤백 계획 거부 기록이 실패해도 원래 오류가 그대로 올라온다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_rollback_audit_failure_does_not_mask_error` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-008 |
| TC-920 | 롤백 후 검증이 실패(제목 미반영)해도 success + ok=false로 기록하고 추가 호출은 하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_rollback_verification_failure_is_recorded_without_auto_retry` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-011, SEC-010 |
| TC-921 | 롤백 호출이 400으로 거절되면 rollback 행을 failed로 끝내고 후보는 applied로 둔다(원래 적용 행도 그대로). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_rollback_call_failure_marks_failed_and_keeps_candidate` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-011, SEC-006 |
| TC-922 | 소스 전체에서 `.videos().update(` 호출은 live_guard.py의 `_send_update` 단 한 곳이다(다른 모듈·다른 표기 없음). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_videos_update_exists_in_exactly_one_place` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001, SEC-007 |
| TC-923 | 다른 표기로 쓰기 호출을 숨기지 못한다: `.update(part=`, `videos().update`(줄바꿈 포함), getattr로 'update'를 꺼내는 코드는 live_guard 밖에 없다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_no_other_spelling_of_the_write_call_exists` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001, SEC-007 |
| TC-924 | 쓰기 토큰(`load_credentials("write"`)은 live_guard.make_write_service 한 곳에서만 읽고, 다른 곳의 load_credentials는 모두 읽기 토큰이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_write_credentials_are_loaded_in_one_place_only` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-015 |
| TC-925 | 소스에 Studio·웹 접근용 HTTP 라이브러리(requests/urllib/httpx)나 브라우저 자동화(selenium/playwright/pyppeteer)를 import하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_no_web_scraping_or_browser_automation_imports` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-007 |
| TC-926 | make_write_service는 쓰기 토큰 종류("write")만 읽어 그 자격증명으로 서비스를 만든다. make_reader는 읽기 토큰만 쓴다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_make_write_service_loads_only_the_write_token` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-015 |
| TC-927 | env_from_ctx는 서비스를 미리 만들지 않는다(토큰도 읽지 않음). 팩토리를 부를 때에만 읽고, 쓰기 팩토리는 write 토큰을 요청한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_env_from_ctx_wires_lazy_factories` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-015 |
| TC-928 | 이 테스트 파일은 소켓·google build()를 막은 채 실행된다: 전체 적용·롤백 시나리오가 가짜 서비스만으로 끝나고 연결 시도가 0건이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_no_network_during_gate_tests` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001 |
| TC-929 | build_write_body는 snippet을 깊은 복사하고 제목만 바꾼다(원본 불변). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_build_write_body_deep_copies_and_replaces_only_title` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-009, SEC-005 |
| TC-930 | 12단계 실측 후 읽기 전용 항목을 빼야 하면 NOT_SENT_SNIPPET_FIELDS에 이름만 추가하면 본문과 본문 검사가 함께 바뀐다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_not_sent_fields_hook_changes_body_and_check_together` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-005 |
| TC-931 | check_body는 구조 이상·제목 불일치·항목 누락·값 변경·추가 항목이 있는 본문을 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_check_body_rejects_unsafe_bodies` | docstring의 기대 결과가 모두 충족 | Pass(8건) | Pass | SEC-005 / 변형 8건 |
| TC-932 | categoryId가 없는 본문은 보내지 않는다(전체 보존 대상에서 빠지도록 설정돼도). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_check_body_requires_category` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-005 |
| TC-933 | 쓰기 직전 새 제목 규격 재검사(길이·< >·제어 문자)에 걸리면 9단계에서 중단한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_invalid_new_title_is_rejected_at_step_9` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-002, SEC-005 |
| TC-934 | 쓰기 오류 분류: 쿼터/인증은 분명한 거절, 429는 재시도하는 분명한 거절, 5xx·네트워크는 재시도하는 불명, 그 밖의 4xx는 분명한 거절, 모르는 예외는 불명이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_classify_write_error` | docstring의 기대 결과가 모두 충족 | Pass(12건) | Pass | NFR-004, SEC-003 / 변형 12건 |
| TC-935 | HTTP 오류 본문에 토큰·긴 문자열이 있어도 메시지·원인에 넣지 않고 상태 코드와 안전한 reason만 남긴다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_classify_does_not_leak_response_body` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-008 |
| TC-936 | 게이트 표시는 상태를 기호+글자로 보여 주고(색 비의존) 외부 문자열의 제어 문자를 제거한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_gate_line_formats_all_statuses` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-019 |
| TC-937 | 해결되지 않은 planned 행이 있으면 롤백도 5단계에서 중단한다(자동으로 지우지 않음). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_rollback_blocked_by_unresolved_planned_row` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-006 |
| TC-938 | 6단계 결과(재조회 snippet·계획 해시)가 없는 채로 7단계가 불리면(게이트 순서가 깨진 경우) 승인을 믿지 않고 중단한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_step7_without_fresh_hash_fails_closed` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-014 |
| TC-939 | 쓰기 직후 재조회에서 영상이 보이지 않으면(삭제·비공개) 검증을 하지 못했다고 기록하고 success(ok=false)로 끝낸다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_verification_when_video_disappears_after_write` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-010 |
| TC-950 | --live 없는 apply는 모의 실행이다: 계획 정보와 14단계 조건 표를 보여 주고, 구글 연결·쓰기 토큰 로드·이력/쿼터 기록·승인 소진이 전혀 없으며 종료 코드 0이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_apply_cmd.py::test_dry_run_is_default_and_writes_nothing` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-006, FR-008, SEC-001 |
| TC-951 | 모의 실행은 막는 조건을 단계 번호와 해결 방법으로 보여 주고 종료 코드 3을 낸다(--live 없음 자체는 막힘으로 세지 않음). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_apply_cmd.py::test_dry_run_shows_which_gate_blocks` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-006, SCR-005, SEC-001 |
| TC-952 | 승인 파일이 없으면 7단계 [차단], 변경 전 지표가 없으면 8단계 [주의]로 안내한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_apply_cmd.py::test_dry_run_missing_approval_and_baseline` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-012, FR-013 |
| TC-953 | --candidate는 필수 정수 1개다(없으면 2, 숫자 아님 2, 0·음수·범위 밖·없는 번호 1). 일괄 적용 옵션(--all, 여러 번호)은 없다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_apply_cmd.py::test_candidate_option_rules` | docstring의 기대 결과가 모두 충족 | Pass(8건) | Pass | EVT-006, SEC-020 / 변형 8건 |
| TC-954 | apply --candidate N --live: 14단계 통과 후 영상 ID를 직접 입력하면 제목이 바뀌고 SCR-005/006 화면(조건 표·LIVE 경고·결과·롤백 명령)이 나오며 run_logs는 live/0이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_apply_cmd.py::test_live_apply_end_to_end_via_cli` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-006, FR-012, SCR-005, SCR-006 |
| TC-955 | 게이트에서 막히면 종료 코드 3, 한국어 오류 블록(다음에 할 일 포함), 호출 0회, aborted 행 1개. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_apply_cmd.py::test_live_gate_failure_exit_code_and_message` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007, SCR-009, SEC-001 |
| TC-956 | 영상 ID를 3번 틀리게 입력하면 종료 코드 3, 호출 0회. (확인 문구는 y/n이 아니라 영상 ID) | 자동 테스트 환경(임시 폴더) | `pytest tests/test_apply_cmd.py::test_live_typed_id_mismatch_exits_3` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001 |
| TC-957 | 사후 검증이 실패하면 종료 코드 1과 큰 경보, 롤백 안내를 출력한다(자동 롤백 없음). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_apply_cmd.py::test_live_verification_failure_exit_code_1` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SCR-006, SEC-010 |
| TC-958 | 구글이 요청을 거절하면 종료 코드 1, 한국어 안내, 이력 failed. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_apply_cmd.py::test_live_api_rejection_exit_code_1` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007, SEC-006 |
| TC-959 | 호출 결과를 알 수 없으면 종료 코드 1, 이력 planned, 안내(Studio 확인)를 출력한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_apply_cmd.py::test_live_unresolved_result_exit_code_1_and_planned` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-008 |
| TC-960 | 명령 수준에서도 settings.yaml의 enable_live는 무시된다: [주의] 안내와 함께 2단계에서 종료 코드 3, 호출 0회. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_apply_cmd.py::test_settings_yaml_enable_live_is_ignored_via_cli` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-010, SEC-001 |
| TC-961 | 차단된 후보는 모의 실행·실제 적용 모두 종료 코드 3으로 거부한다(live는 aborted PLAN 기록). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_apply_cmd.py::test_blocked_candidate_exit_3_dry_and_live` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | POL-001, SEC-001 |
| TC-962 | apply --help가 기본이 모의 실행이고 --live가 실제 적용임을 밝힌다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_apply_cmd.py::test_apply_help_explains_dry_run_default` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007, SCR-001 |
| TC-963 | 영상 제목·검증 사유에 ANSI/방향 제어 문자가 있어도 apply 화면에 그대로 나오지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_apply_cmd.py::test_external_strings_are_sanitized_on_screen` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-019 |
| TC-964 | 영상 정보를 가져온 지 24시간이 넘으면 모의 실행이 [주의]로 fetch를 안내한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_apply_cmd.py::test_dry_run_stale_info_is_cautioned` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-004 |
| TC-965 | 하루 적용 상한에 닿으면 모의 실행은 5단계 [차단], 실제 적용은 종료 코드 3이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_apply_cmd.py::test_daily_cap_via_cli` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-020 |
| TC-966 | 오늘 쿼터가 부족하면 실제 적용은 4단계에서 종료 코드 3으로 막히고 구글 호출이 없다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_apply_cmd.py::test_quota_exhausted_via_cli` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-002 |
| TC-970 | approve는 계획 요약을 보여 주고 영상 ID를 직접 입력해야 승인 파일(계획 해시·만료·미사용)을 만들며 후보를 approved로 바꾼다. 구글 연결 없음. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approve_cmd.py::test_approve_creates_bound_file_after_typing_video_id` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-005, FR-013, SCR-004, SEC-014 |
| TC-971 | 영상 ID 확인이 틀리거나 비었거나 입력이 끊기면 종료 코드 3, 승인 파일 없음, 후보 상태 그대로. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approve_cmd.py::test_wrong_confirmation_creates_nothing` | docstring의 기대 결과가 모두 충족 | Pass(3건) | Pass | SEC-014 / 변형 3건 |
| TC-972 | 교체 제한을 지금 통과하지 못하는 계획은 승인하지 않는다(질문 없이 종료 코드 3). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approve_cmd.py::test_not_ready_plan_is_not_approved` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-014, SEC-004 |
| TC-973 | 없는 후보는 1, 차단된 후보·이미 적용된 후보는 3으로 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approve_cmd.py::test_unapprovable_candidates` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | POL-001 |
| TC-974 | 이미 유효한 승인이 있으면 '덮어쓰기'를 직접 입력해야 새로 승인한다. 거절하면 기존 승인이 그대로 남는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approve_cmd.py::test_existing_active_approval_needs_overwrite_confirmation` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SCR-004 |
| TC-975 | 후보가 이미 approved이고 이전 승인이 만료됐으면 질문 없이 새로 승인하고 상태는 approved 그대로다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approve_cmd.py::test_reapprove_when_already_approved_keeps_status_and_replaces_expired` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-013 |
| TC-976 | --ttl-hours는 1 이상 설정값(24) 이하만 가능하다(범위 밖 1, 숫자 아님 2). 잘못된 값이면 승인 파일을 만들지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approve_cmd.py::test_ttl_option` | docstring의 기대 결과가 모두 충족 | Pass(5건) | Pass | FR-013 / 변형 5건 |
| TC-977 | 승인자 이름은 필수이며 비거나 제어 문자·41자 이상이면 거부한다(옵션 누락은 2). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approve_cmd.py::test_approver_validation` | docstring의 기대 결과가 모두 충족 | Pass(5건) | Pass | NFR-008, SEC-019 / 변형 5건 |
| TC-978 | 후보번호 범위 밖은 종료 코드 1이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approve_cmd.py::test_candidate_range` | docstring의 기대 결과가 모두 충족 | Pass(3건) | Pass | EVT-005 / 변형 3건 |
| TC-979 | 후보 상태 전이에 실패하면 방금 만든 승인 파일을 지워 'approved 상태 없는 승인 파일'을 남기지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approve_cmd.py::test_state_transition_failure_removes_the_file` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-014 |
| TC-980 | 경고 판정 후보·오래된 영상 정보는 [주의]로 알리고, 제목의 제어 문자는 화면에 나오지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approve_cmd.py::test_warn_and_stale_cautions_and_sanitizing` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-004, POL-001, SEC-019 |
| TC-981 | 전체 흐름: approve로 승인 → apply 모의 실행(7단계 통과) → apply --live로 적용 → 승인은 소진되어 다시 apply하면 3. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approve_cmd.py::test_full_flow_approve_then_apply_live` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-012, FR-013, SEC-014 |
| TC-982 | approve --help가 승인자·유효 시간 옵션과 1회용·만료 성격을 설명한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_approve_cmd.py::test_approve_help` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SCR-001 |
| TC-983 | 모의 실행 끝에 실제 복원 명령(--approver 이름 --live)을 안내한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_rollback_cmd.py::test_rollback_dry_run_points_to_live_command` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-007 |
| TC-984 | rollback --change N --approver 이름 --live: 게이트 통과·영상 ID 입력 후 이전 제목으로 복원(종료 코드 0), LIVE 표시, 후보 rolled_back. 승인자 누락은 7단계에서 3. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_rollback_cmd.py::test_rollback_live_end_to_end_via_cli` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-007, FR-011, SCR-005, SCR-006 |
| TC-985 | 롤백 후 검증이 실패하면 종료 코드 1이고 경보를 출력한다(자동 재시도 없음). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_rollback_cmd.py::test_rollback_live_verification_failure_exit_1` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-011, SEC-010 |
| TC-986 | 설정의 제목 길이 상한을 나중에 낮춰도 롤백(원래 제목 복원)은 길이 검사에 막히지 않는다(적용은 검사). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_rollback_restores_original_title_even_if_length_limit_was_lowered` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-011 |
| TC-987 | 9단계는 적용의 새 제목 길이 상한을 쓰기 직전에 다시 검사한다(계획 이후 설정이 낮아진 경우). 롤백은 면제(TC-986). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_live_guard.py::test_step9_rechecks_title_length_for_apply_but_not_rollback` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-002, SEC-005 |

### 4-1. 인수 조건 ↔ 테스트 케이스 추적
| AC | 인수 조건 | 연결 TC | 판정 |
|---|---|---|---|
| AC-01 | 승인 파일 바인딩·만료·1회용·재활용 거부 | TC-530, TC-532, TC-541, TC-542, TC-544, TC-545, TC-555, TC-559 | 충족 |
| AC-02 | 승인 위조·키·경로·규격 방어 | TC-531, TC-533, TC-534, TC-535, TC-536, TC-537, TC-538, TC-539, TC-540, TC-546, TC-547, TC-548, TC-550, TC-551, TC-552, TC-553, TC-554, TC-556, TC-557, TC-558, TC-560, TC-561 | 충족 |
| AC-03 | 14단계 문서 순서·단계별 fail-closed | TC-574, TC-575, TC-576, TC-578, TC-571, TC-938 | 충족 |
| AC-04 | enable_live local 전용·허용 목록·--live | TC-575, TC-576, TC-577, TC-574, TC-960 | 충족 |
| AC-05 | 쿼터·교체 제한·하루 상한·planned 잔여 | TC-579, TC-580, TC-581, TC-574, TC-595, TC-937, TC-965, TC-966 | 충족 |
| AC-06 | 호출 직전 재조회·해시 불일치 | TC-574, TC-573, TC-955 | 충족 |
| AC-07 | 1회 호출·본문 전체 보존·백업 | TC-570, TC-572, TC-573, TC-901, TC-929, TC-930, TC-931, TC-932, TC-933, TC-987 | 충족 |
| AC-08 | 영상 ID 직접 입력·기준선 확인 | TC-574, TC-598, TC-956 | 충족 |
| AC-09 | 사후 검증·자동 롤백 없음 | TC-582, TC-583, TC-584, TC-585, TC-586, TC-939, TC-957 | 충족 |
| AC-10 | 호출 도중 오류 처리(failed/planned/쿼터) | TC-587, TC-588, TC-589, TC-590, TC-591, TC-592, TC-593, TC-594, TC-595, TC-596, TC-597, TC-934, TC-935, TC-958, TC-959 | 충족 |
| AC-11 | videos.update 단일 위치·쓰기 토큰 단일 위치·금지 import | TC-922, TC-923, TC-924, TC-925 | 충족 |
| AC-12 | 쓰기 토큰 로드 시점·토큰/키 비노출 | TC-571, TC-574, TC-596, TC-599, TC-926, TC-927, TC-928, TC-561, TC-935 | 충족 |
| AC-13 | apply 명령(모의 실행·종료 코드·정화) | TC-950, TC-951, TC-952, TC-953, TC-954, TC-955, TC-956, TC-957, TC-958, TC-959, TC-961, TC-962, TC-963, TC-964, TC-965, TC-966, TC-936 | 충족 |
| AC-14 | approve 명령 | TC-970, TC-971, TC-972, TC-973, TC-974, TC-975, TC-976, TC-977, TC-978, TC-979, TC-980, TC-981, TC-982 | 충족 |
| AC-15 | rollback --live | TC-521, TC-526, TC-913, TC-914, TC-915, TC-916, TC-917, TC-918, TC-920, TC-921, TC-983, TC-984, TC-985, TC-986 | 충족 |
| AC-16 | 계획 단계 거부 기록·기록 실패 비가림 | TC-902, TC-903, TC-904, TC-905, TC-906, TC-907, TC-908, TC-909, TC-910, TC-919 | 충족 |

- 인수 조건에 연결되지 않은 TC(추가 안전 케이스): TC-520, TC-522, TC-523, TC-524, TC-525, TC-543, TC-549, TC-900, TC-911, TC-912
- 정상 경로, 경계값(날짜 경계·상한·빈 입력), 예외 입력(잘못된 형식·악성 문자열), 권한 경계를 포함했다.

## 5. 커버리지
- 전체 지표: 이 단위 모듈(ytitle.approvals, ytitle.live_guard, ytitle.commands.apply, ytitle.commands.approve, ytitle.commands.rollback)의 줄+분기 합산 **100%** (pytest-cov, `--cov-branch`)
- 회귀(이전 단위 산출물을 깨뜨리지 않음): 전체 테스트 스위트 `1097 passed, 1 skipped` (통과)
- 호환 실행: 3.11 → 278 passed / 3.13 → 278 passed / 3.12(주) → 278 passed
- 커버되지 않은 부분과 사유:
  - src/ytitle/approvals.py             206      0     70      0   100%
  - src/ytitle/commands/apply.py         53      0     12      0   100%
  - src/ytitle/commands/approve.py       66      0     18      0   100%
  - src/ytitle/commands/rollback.py      41      0     10      0   100%
  - src/ytitle/live_guard.py            478      0    132      0   100%
  - 이 단위 모듈의 줄·분기 커버리지는 위 수치.

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 내용 |
|----|------|-----------|--------|------|-----------|
| DEF-6-023 | [테스트 결함] 오케스트레이터 독립 변이 점검 1회차(93개 중 91개 적발)에서 apply 후보번호 범위 검사 제거·approve 덮어쓰기 확인 제거 2곳을 놓침(관찰 가능한 차이가 문구·질문 순서뿐이라 종료 코드만 보던 테스트가 통과) | 독립 변이 점검 | Medium | Fixed | TC-953, TC-974 단언 보강 후 재점검 |
| DEF-6-021 | [테스트 결함] 서브에이전트 자체 변이 점검 1회차에서 출력 문구·Ctrl+C 처리·롤백 길이 면제·승인자 조기 검증·롤백 종료 코드 등 7곳을 놓침 | 자체 변이 점검 | Medium | Fixed | 테스트 보강 후 2회차 생존 0건(동치 변이 2건 제외) |

- 서브에이전트가 이 단위 안에서 수정·재검증. 오케스트레이터 독립 변이 점검 결과는 부록 A.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트: `.harness-tmp/junit_06.xml`, `.harness-tmp/junit_py311.xml`, `.harness-tmp/junit_py313.xml`, `.harness-tmp/junit_regress.xml`, `.harness-tmp/venv_py311`, `.harness-tmp/venv_py312`, `.harness-tmp/venv_py313` (+ 변이 점검용 임시 사본 `.harness-tmp/mut_06/`, 편집 설치로 생긴 `src/*.egg-info`, 캐시 `__pycache__`/`.coverage`)
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예 [ ] 아니오 — 예외: 편집 설치가 `src/ytitle.egg-info/`를 만들고 파이썬이 `__pycache__`를 만든다(둘 다 `.gitignore` 대상이며 정리 대상에 포함)
- 정리(삭제) 완료 여부: 예. 결과서 생성 스크립트가 `.harness-tmp/`, `data/`, `.coverage`, `src/*.egg-info`, `__pycache__`를 삭제했다
- **정리 후 점검**: 이 스크립트는 git을 실행하지 않는다(커밋·푸시는 오케스트레이터가 DEC-027에 따라 별도 수행). 파일시스템 점검 결과: 잔여물 없음 (점검 목록: .harness-tmp, .venv*, venv, *.egg-info, .pytest_cache, .coverage*, __pycache__, data)
- 병렬 실행이었다면: 해당 없음(단독 실행)
- 이번 테스트 도중 강제 중단: [x] 없음 / [ ] 있음

## 8. 리스크 및 잔존 이슈
- **미검증(PASS로 세지 않음)**: 읽기 전용 필드를 포함한 snippet을 videos.update가 받는지(12단계 실측), 실제 구글 응답 형식
- 결정 대기: unit-5-note의 질문 5가지(HMAC 서명 추가, planned 정리 방법, 불확실 결과 규칙, 롤백 승인 파일, 읽기 전용 필드 검증)

## 9. 결론 및 판정
- 판정: **PASS**
- 근거: 실패 TC 0건, 미수행 TC 0건(-), AC↔TC 추적 문제 0건, 정적 분석(pyflakes) 통과, 변이 점검 93/93 잡아냄, Open 결함 0건
- 실제 구글 쓰기는 12단계 사용자 승인 전까지 실행하지 않는다.

## 10. 내부 검증 (최소 2회)
- 1차: 서브에이전트 구현·자체 변이 점검 2회(122곳씩)
- 2차(독립 심사자 관점): 오케스트레이터가 서브에이전트 목록과 겹치지 않게 새로 작성한 변이 점검. 결과는 부록 A
- 3차: 결함 0건 확인
- 검증 로그 파일 경로: `docs/harness/verify-log_unit-5-test.md`

### 부록 A. 변이 점검(코드를 일부러 망가뜨려 테스트가 실패하는지 확인)
| 변이 | 파일 | 결과 |
|---|---|---|
| 1단계: --live 검사 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 2단계: enable_live 검사 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 3단계: 빈 허용 목록 통과 | `live_guard.py` | 잡아냄(테스트 실패) |
| 3단계: 목록 밖 영상 통과 | `live_guard.py` | 잡아냄(테스트 실패) |
| 4단계: 쿼터 경계(<→<=) | `live_guard.py` | 잡아냄(테스트 실패) |
| 4단계: 쿼터 검사 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 4단계: 조회 비용 누락 | `live_guard.py` | 잡아냄(테스트 실패) |
| 5단계: planned 잔여 검사 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 5단계: 롤백도 교체 제한 적용 | `live_guard.py` | 잡아냄(테스트 실패) |
| 5단계: 교체 제한 무시 | `live_guard.py` | 잡아냄(테스트 실패) |
| 6단계: 현재 제목 일치 검사 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 6단계: 재조회 빈 결과 통과 | `live_guard.py` | 잡아냄(테스트 실패) |
| 7단계: 승인 상태 검사 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 7단계: 승인 파일 검증 생략 | `live_guard.py` | 잡아냄(테스트 실패) |
| 7단계: 승인 해시를 저장본 해시로 검증 | `live_guard.py` | 잡아냄(테스트 실패) |
| 7단계: 롤백 계획 해시 검사 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 7단계: 확인자 이름 검사 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 8단계: 지표 없으면 확인 없이 통과 | `live_guard.py` | 잡아냄(테스트 실패) |
| 8단계: 롤백에도 지표 확인 | `live_guard.py` | 잡아냄(테스트 실패) |
| 9단계: 본문 보존 검사 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 9단계: categoryId 검사 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 9단계: 새 제목 일치 검사 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 9단계: 영상 ID 일치 검사 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 9단계: 제목 규격 검사 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 9단계: 롤백 길이 면제 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 본문에서 snippet 일부 제외 | `live_guard.py` | 잡아냄(테스트 실패) |
| 10단계: 영상 ID 확인 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 10단계 이전에 쓰기 토큰 로드 | `live_guard.py` | 잡아냄(테스트 실패) |
| 게이트 순서 뒤집기(2·3 교환) | `live_guard.py` | 잡아냄(테스트 실패) |
| 게이트 순서 뒤집기(7·6 교환) | `live_guard.py` | 잡아냄(테스트 실패) |
| 11단계: 승인 소진 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 11단계: DB 백업 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 11단계: 쿼터 선예약 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 11단계: 예약 실패 시 aborted 안 남김 | `live_guard.py` | 잡아냄(테스트 실패) |
| 12단계: 재시도마다 재예약 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 12단계: 실패 호출 쿼터 환불 표시 | `live_guard.py` | 잡아냄(테스트 실패) |
| 12단계: 성공 호출 쿼터 표시 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 13단계: 제목 반영 확인 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 13단계: 보존 항목 검사 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 13단계: 재조회 실패를 성공으로 | `live_guard.py` | 잡아냄(테스트 실패) |
| 13단계: 보존 항목에서 description 제외 | `live_guard.py` | 잡아냄(테스트 실패) |
| 13단계: 보존 항목에서 tags 제외 | `live_guard.py` | 잡아냄(테스트 실패) |
| 14단계: 검증 실패해도 자동 롤백 호출 흉내(성공 처리 제거) | `live_guard.py` | 잡아냄(테스트 실패) |
| 결과 코드: 검증 실패도 성공 | `live_guard.py` | 잡아냄(테스트 실패) |
| 오류분류: 5xx를 확정 실패로 | `live_guard.py` | 잡아냄(테스트 실패) |
| 오류분류: 네트워크 오류를 확정 실패로 | `live_guard.py` | 잡아냄(테스트 실패) |
| 오류분류: 알 수 없는 오류를 확정 실패로 | `live_guard.py` | 잡아냄(테스트 실패) |
| 오류분류: 쿼터 초과를 권한 오류로 | `live_guard.py` | 잡아냄(테스트 실패) |
| 오류분류: 429 재시도 불가 | `live_guard.py` | 잡아냄(테스트 실패) |
| 불확실 결과: 재조회 확인 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 불확실 결과: planned 대신 failed 처리 | `live_guard.py` | 잡아냄(테스트 실패) |
| Ctrl+C: 미확정 처리 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 확정 실패: failed 기록 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 중단 기록: planned 이후에도 aborted 추가 | `live_guard.py` | 잡아냄(테스트 실패) |
| 중단 기록 제거(감사 누락) | `live_guard.py` | 잡아냄(테스트 실패) |
| 계획 실패 기록 제거 | `live_guard.py` | 잡아냄(테스트 실패) |
| 승인: 만료 경계(>=→>) | `approvals.py` | 잡아냄(테스트 실패) |
| 승인: 만료 검사 제거 | `approvals.py` | 잡아냄(테스트 실패) |
| 승인: 사용 여부 검사 제거 | `approvals.py` | 잡아냄(테스트 실패) |
| 승인: 미래 승인 시각 허용 | `approvals.py` | 잡아냄(테스트 실패) |
| 승인: TTL 상한 검사 제거 | `approvals.py` | 잡아냄(테스트 실패) |
| 승인: 새 제목 불일치 허용 | `approvals.py` | 잡아냄(테스트 실패) |
| 승인: 계획 해시 불일치 허용 | `approvals.py` | 잡아냄(테스트 실패) |
| 승인: 영상·후보 불일치 허용 | `approvals.py` | 잡아냄(테스트 실패) |
| 승인: 서명(MAC) 검증 제거 | `approvals.py` | 잡아냄(테스트 실패) |
| 승인: 항목 규격 검사 제거 | `approvals.py` | 잡아냄(테스트 실패) |
| 승인: 심볼릭 링크 허용 | `approvals.py` | 잡아냄(테스트 실패) |
| 승인: 파일 크기 상한 제거 | `approvals.py` | 잡아냄(테스트 실패) |
| 승인: 사용 여부-시각 일치 검사 제거 | `approvals.py` | 잡아냄(테스트 실패) |
| 승인: 경로 부모 검사 제거 | `approvals.py` | 잡아냄(테스트 실패) |
| 승인: 영상 ID 형식 검사 제거 | `approvals.py` | 잡아냄(테스트 실패) |
| 승인: 후보 번호 bool 허용 | `approvals.py` | 잡아냄(테스트 실패) |
| 승인: 키 없을 때 새로 생성(검증 경로) | `approvals.py` | 잡아냄(테스트 실패) |
| 승인: 키 길이 검사 제거 | `approvals.py` | 잡아냄(테스트 실패) |
| 승인: 소진 시 이미 사용 검사 제거 | `approvals.py` | 잡아냄(테스트 실패) |
| 승인: 소진 시 내용 변경 검사 제거 | `approvals.py` | 잡아냄(테스트 실패) |
| 승인: 덮어쓰기 금지 제거 | `approvals.py` | 잡아냄(테스트 실패) |
| 승인: 승인자 길이 상한 경계 | `approvals.py` | 잡아냄(테스트 실패) |
| 승인: TTL 하한 완화(0 허용) | `approvals.py` | 잡아냄(테스트 실패) |
| 승인: TTL 상한 경계(<=→<) | `approvals.py` | 잡아냄(테스트 실패) |
| 승인: 계획 해시 형식 검사 제거 | `approvals.py` | 잡아냄(테스트 실패) |
| 승인: 만료 시각 계산(TTL 2배) | `approvals.py` | 잡아냄(테스트 실패) |
| 활성 승인 조회: 사용된 것도 활성 | `approvals.py` | 잡아냄(테스트 실패) |
| apply 명령: 후보번호 범위 검사 제거 | `commands/apply.py` | 잡아냄(테스트 실패) |
| apply 명령: --live 실패해도 종료 0 | `commands/apply.py` | 잡아냄(테스트 실패) |
| apply 모의 실행: 차단돼도 종료 0 | `commands/apply.py` | 잡아냄(테스트 실패) |
| apply 모의 실행: 1단계 차단을 막힘으로 셈 | `commands/apply.py` | 잡아냄(테스트 실패) |
| approve 명령: 영상 ID 확인 제거 | `commands/approve.py` | 잡아냄(테스트 실패) |
| approve 명령: 덮어쓰기 확인 제거 | `commands/approve.py` | 잡아냄(테스트 실패) |
| approve 명령: 제한 미통과여도 승인 | `commands/approve.py` | 잡아냄(테스트 실패) |
| approve 명령: 실패 시 승인 파일 정리 제거 | `commands/approve.py` | 잡아냄(테스트 실패) |
| approve 명령: 후보 상태 전이 제거 | `commands/approve.py` | 잡아냄(테스트 실패) |
| rollback 명령: --live 실패해도 종료 0 | `commands/rollback.py` | 잡아냄(테스트 실패) |

### 부록 B. 공유 문서 갱신
`traceability.md`의 단위테스트 컬럼과 구현 상태를 스크립트로 갱신했다(통과한 TC만 연결).
