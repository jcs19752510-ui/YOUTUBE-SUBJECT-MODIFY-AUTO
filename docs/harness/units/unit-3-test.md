# 테스트 결과서 — WU-3 후보 입력·안전 필터 (6단계 단위 테스트)

## 1. 개요
- 테스트 대상: WU-3 후보 입력·안전 필터 (`candidates, banned_terms, validator, commands/validate`)
- 테스트 유형: 단위
- 적용 Tier: Standard (규칙 B 원문: 최소 2회)
- 적용 속도 트랙: L3
- 병렬 실행 정보: 단독 실행 (이 환경은 서브에이전트를 쓰지 않음, DEC-011)
- 테스트 목적: `unit-3-note.md`의 인수 조건(AC)을 테스트로 증명하고 안전 로직의 회귀를 막는다
- 관련 산출물: `docs/yt/DESIGN.md`, `docs/harness/units/unit-3-note.md`, `docs/yt/02_planning.md`
- 테스트 수행자(에이전트): 오케스트레이터(06단계 역할 직접 수행)
- 테스트 일시: 2026-10-10

## 2. 테스트 범위 및 제외 범위
- 범위(In-Scope): 후보 파일 읽기·입력 검증, 금칙어 사전, 제목 검증기(길이·규격·금칙어·경고·영상 일치·엄격 모드), DB 기록, `validate` 명령
- 제외 범위(Out-of-Scope) 및 사유: 금칙어 사전의 법적 적절성(사용자 검토 필요), 실제 채널 제목·요약으로 한 과차단/과소차단 측정, 일치율 휴리스틱의 실데이터 정확도

## 3. 테스트 환경
- 실행 환경: Linux, Python 3.12.3 (주 실행) · 3.11 · 3.13 (호환 확인), pytest, pytest-cov. 가상환경은 `.harness-tmp/` 아래에만 생성
- 테스트 데이터: 임시 폴더의 가짜 설정·DB·후보, 가짜 토큰 문자열(실제 비밀 아님). **실제 YouTube API는 호출하지 않음**
- 전제 조건: 이전 단위 WU-0 PASS(공통 기반)

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고(검증하는 ID) |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-001 | 설정 파일이 없어도 기본값(60% 상한, 72시간, 3회, 1,000회)으로 로드된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_config.py::test_defaults_without_files` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-003, SEC-004 |
| TC-002 | settings.yaml 값이 기본값을 덮어쓴다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_config.py::test_settings_yaml_overrides_default` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-017 |
| TC-003 | settings.local.yaml이 settings.yaml보다 우선한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_config.py::test_local_overrides_base` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-010 |
| TC-004 | settings.yaml의 live.enable_live=true는 무시되고 경고가 남는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_config.py::test_live_in_base_is_ignored_with_warning` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001 |
| TC-005 | settings.local.yaml의 live 값은 적용된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_config.py::test_live_in_local_is_honored` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001, SEC-012 |
| TC-006 | 형식·범위가 잘못된 설정은 한국어 안내가 있는 ConfigError가 된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_config.py::test_invalid_values_raise_korean_config_error` | docstring의 기대 결과가 모두 충족 | Pass(8건) | Pass | NFR-007 / 변형 8건 |
| TC-007 | 제목 길이(핵심어≤권장≤상한)와 일치율(차단≤경고) 순서가 틀리면 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_config.py::test_length_and_ratio_order_validated` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-002 |
| TC-008 | YAML 문법 오류, 최상위가 목록인 파일은 ConfigError. 위험한 태그는 safe_load로 실행되지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_config.py::test_yaml_syntax_error_and_non_mapping` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-016 |
| TC-009 | live_allowlist가 문자열 목록이 아니면 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_config.py::test_allowlist_must_be_string_list` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-012 |
| TC-010 | .env/환경변수로 경로를 지정하고, 기본 토큰 폴더는 프로젝트 밖이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_config.py::test_env_paths_and_token_dir_outside_project` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-004, SEC-008 |
| TC-300 | 올바른 후보 파일이 읽히고 해시가 기록된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_candidates.py::test_valid_file_loads` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-201, FR-001 |
| TC-301 | 윈도 메모장/PowerShell이 붙이는 UTF-8 BOM이 있어도 읽힌다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_candidates.py::test_bom_utf8_accepted` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-001, NFR-002 |
| TC-302 | UTF-8이 아닌 파일(cp949)은 저장 방법을 안내하는 오류가 된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_candidates.py::test_cp949_file_gives_encoding_guidance` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-001, NFR-007 |
| TC-303 | JSON 문법 오류는 줄·칸 위치를 알려 준다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_candidates.py::test_json_syntax_error_reports_position` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-001, NFR-007 |
| TC-304 | 맨 바깥이 객체가 아닌 JSON은 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_candidates.py::test_non_object_root_rejected` | docstring의 기대 결과가 모두 충족 | Pass(4건) | Pass | FR-001, SEC-011 / 변형 4건 |
| TC-305 | candidates 폴더 밖 경로(../)와 다른 폴더의 파일은 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_candidates.py::test_path_traversal_rejected` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | RISK-010, SEC-011 |
| TC-306 | candidates 안에 있어도 폴더 밖 파일을 가리키는 심볼릭 링크는 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_candidates.py::test_symlink_escape_rejected` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-011 |
| TC-307 | 영상 ID 형식(11자 영문·숫자·-·_)이 아닌 파일 이름은 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_candidates.py::test_bad_file_names_rejected` | docstring의 기대 결과가 모두 충족 | Pass(6건) | Pass | SEC-011 / 변형 6건 |
| TC-308 | 없는 파일은 위치를 알려 주는 오류가 된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_candidates.py::test_missing_file_message` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-001, NFR-007 |
| TC-309 | video_id가 파일 이름과 다르면 거부한다(엉뚱한 영상 지정 방지). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_candidates.py::test_video_id_must_match_file_name` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-011 |
| TC-310 | 256KB를 넘는 파일은 열기 전에 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_candidates.py::test_size_limit` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-011, SEC-016 |
| TC-311 | 후보는 1~20개만 허용한다(0개·21개 거부, 20개 허용). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_candidates.py::test_candidate_count_limit_boundaries` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-001, SEC-011 |
| TC-312 | 필드별 오류(형식·길이·누락)는 어느 항목이 문제인지 한국어로 알려 준다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_candidates.py::test_field_errors_are_specific` | docstring의 기대 결과가 모두 충족 | Pass(10건) | Pass | FR-001, NFR-007 / 변형 10건 |
| TC-313 | 여러 문제는 한 번에 모두 알려 준다(2번 고치게 만들지 않음). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_candidates.py::test_multiple_errors_reported_together` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007 |
| TC-314 | source(후보 생성 출처) 필드는 필수다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_candidates.py::test_missing_source_rejected_for_pol004` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | POL-004 |
| TC-315 | 폴더 목록은 .json 파일만 정렬해서 돌려주고, 폴더가 없으면 빈 목록이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_candidates.py::test_list_candidate_files_sorted_and_only_json` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-003 |
| TC-316 | 저장소의 금칙어 사전이 읽히고 5가지 차단 유형이 모두 있다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_banned_terms.py::test_real_dictionary_loads_with_all_five_types` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-003 |
| TC-317 | 같은 내용은 같은 해시, 단어를 하나 바꾸면 해시가 달라진다(사전 변경 추적). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_banned_terms.py::test_hash_is_stable_and_changes_with_content` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-017 |
| TC-318 | 위험하거나 잘못된 사전(너무 짧은 단어, 잘못된 정규식, 알 수 없는 키, 위험한 YAML 태그)은 안내와 함께 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_banned_terms.py::test_invalid_dictionary_rejected_with_korean_guidance` | docstring의 기대 결과가 모두 충족 | Pass(12건) | Pass | FR-003, SEC-016 / 변형 12건 |
| TC-319 | 사전 파일이 없으면 위치를 알려 주는 오류가 된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_banned_terms.py::test_missing_dictionary` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007 |
| TC-320 | warning 항목을 생략해도 기본 경고 기준이 채워지고, 일부만 바꿀 수 있다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_banned_terms.py::test_warning_defaults_filled` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-002 |
| TC-321 | 영상과 일치하고 규칙에 맞는 생활 주제 한글 제목 12건이 모두 '통과'이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validator.py::test_pass_cases_korean` | docstring의 기대 결과가 모두 충족 | Pass(12건) | Pass | FR-002, FR-004, FR-005 / 변형 12건 |
| TC-322 | 공포·의료·금융·사칭·최상급·우회 표기·길이·규격·불일치 위반 제목 24건이 모두 '차단'이고 해당 사유가 나온다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validator.py::test_block_cases_korean` | docstring의 기대 결과가 모두 충족 | Pass(24건) | Pass | FR-002, FR-003, FR-004 / 변형 24건 |
| TC-323 | 자모가 풀어진(NFD) 한글로 쓴 금칙어도 같은 단어로 인식해 차단한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validator.py::test_decomposed_hangul_cannot_bypass` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-003 |
| TC-324 | 권장 40자는 경고 없음, 41자는 경고, 상한 100자는 차단 아님(경고), 101자는 차단. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validator.py::test_length_boundaries_40_41_100_101` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-002, NFR-002 |
| TC-325 | 길이는 바이트가 아니라 유니코드 문자 수로 센다(한글 100자는 통과 범위, 이모지·결합 문자 포함). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validator.py::test_length_counts_unicode_not_bytes` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-002, NFR-002 |
| TC-326 | 과한 느낌표·이모지·반복 기호·대문자·기호 비율은 '경고'(생활 주제)이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validator.py::test_warning_types` | docstring의 기대 결과가 모두 충족 | Pass(5건) | Pass | FR-002 / 변형 5건 |
| TC-327 | 느낌표 1개, 이모지 2개는 허용 기준 안이라 경고가 없다(경계값). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validator.py::test_single_exclamation_and_two_emoji_are_allowed` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-002 |
| TC-328 | 이모지 개수 세기: 한글·느낌표·물음표는 세지 않고, 이모지와 장식 기호(★ 등)는 보수적으로 센다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validator.py::test_count_emoji` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-002 |
| TC-329 | 건강 주제는 같은 경고도 '차단'이 되고 사유에 엄격 모드가 표시된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validator.py::test_strict_mode_turns_warnings_into_blocks` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-005, POL-001 |
| TC-330 | 건강·금융 주제와 주제 미지정은 엄격 모드이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validator.py::test_strict_reasons_for_topic` | docstring의 기대 결과가 모두 충족 | Pass(3건) | Pass | POL-001 / 변형 3건 |
| TC-331 | 주제를 '생활'로 적어도 제목·요약에 건강·금융 낱말이 보이면 엄격 모드로 올린다(입력 실수 방지). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validator.py::test_strict_upgrade_by_keyword_even_if_topic_is_life` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | POL-001 |
| TC-332 | 일치 근거 문장이 요약·설명에서 확인되지 않으면 경고이다. 설명에 있으면 확인된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validator.py::test_evidence_must_exist_in_summary_or_description` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-004 |
| TC-333 | 일치율 경계: 50%는 경고 아님, 25%는 경고(차단 아님), 25% 미만은 차단. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validator.py::test_match_ratio_thresholds_boundaries` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-004 |
| TC-334 | 제목에서 비교할 낱말이 없으면(숫자·일반어뿐) 일치율은 계산하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validator.py::test_match_ratio_unknown_when_no_comparable_words` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-004 |
| TC-335 | 영상 설명을 쓰면 일치율에 반영되고 '설명 사용' 여부가 결과에 남는다. 없으면 요약만 사용한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validator.py::test_description_improves_match_and_is_reported` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-004 |
| TC-336 | 영상 핵심어가 제목 앞 20자에 없으면 경고, 있으면 없다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validator.py::test_key_phrase_must_appear_in_first_20_chars` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-002 |
| TC-337 | 현재 제목과 똑같은 후보는 경고이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validator.py::test_same_title_as_current_warns` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-002 |
| TC-338 | 정상 낱말('속보' 걷기 운동)이 사칭 금칙어에 걸리는 과차단은 사유가 보이고, 사전에서 빼면 통과한다(알려진 한계). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validator.py::test_known_false_positive_is_visible_and_fixable` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-003, RISK-001 |
| TC-339 | 사전에서 severity를 warn으로 둔 유형은 경고로만 처리된다(생활 주제). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validator.py::test_dictionary_severity_warn_type` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-003 |
| TC-340 | 검증 결과에 사용한 금칙어 사전의 버전과 해시가 담긴다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validator.py::test_result_carries_dictionary_version_and_hash` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-017 |
| TC-341 | 낱말 추출은 숫자 포함 낱말과 일반어(방법·꿀팁 등)를 빼고 조사를 떼어 낸다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validator.py::test_tokens_helper_rules` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-004 |
| TC-342 | 후보 100건 검증이 5초 안에 끝난다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validator.py::test_performance_100_candidates_within_5_seconds` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-005 |
| TC-343 | 검증은 입력 객체를 바꾸지 않고 같은 입력에 같은 결과를 낸다(순수성). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validator.py::test_validate_does_not_mutate_inputs` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-005 |
| TC-344 | `validate --file`이 SCR-002 형식(영상·주제·사전 버전·해시·결과 배지·사유·면책)으로 출력한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validate_cmd.py::test_validate_file_report_screen` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-003, FR-005, POL-002, SCR-002 |
| TC-345 | 검증 결과가 title_candidates에 상태(filtered/blocked)·사전 해시·사유와 함께 기록된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validate_cmd.py::test_validate_records_status_and_dictionary_hash` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-017 |
| TC-346 | 같은 파일을 다시 검증해도 행이 중복되지 않고 갱신된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validate_cmd.py::test_rerun_does_not_duplicate_rows` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-005 |
| TC-347 | 파일 내용이 바뀌면(해시가 다르면) 새 후보로 기록해 이력이 남는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validate_cmd.py::test_changed_file_creates_new_rows` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-005 |
| TC-348 | 이미 승인(approved) 이후 단계인 후보는 재검증해도 상태·결과가 바뀌지 않는다(상태 머신 보호). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validate_cmd.py::test_approved_rows_are_not_reset_by_revalidation` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-006 |
| TC-349 | `--all`은 candidates 폴더의 모든 파일을 검사하고 합계를 보여 준다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validate_cmd.py::test_all_processes_every_file_and_summarizes` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-003 |
| TC-350 | 후보 파일이 없으면 만드는 방법을 안내하고 정상 종료한다(빈 상태). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validate_cmd.py::test_empty_folder_guides_user` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007, SCR-002 |
| TC-351 | 옵션 없이 실행하면 사용법을 안내하는 오류(종료 코드 1)이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validate_cmd.py::test_no_option_is_input_error` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007 |
| TC-352 | candidates 밖의 파일은 종료 코드 1로 거부되고 DB에 아무것도 기록하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validate_cmd.py::test_file_outside_folder_rejected_without_db_write` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-011 |
| TC-353 | 필드 오류가 있는 파일은 어느 항목이 문제인지 알려 주고 아무것도 기록하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validate_cmd.py::test_invalid_file_stops_with_field_message` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-001, NFR-007 |
| TC-354 | 건강 주제는 '엄격 모드' 안내가 나오고 경고급 문제도 차단된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validate_cmd.py::test_strict_banner_and_block_for_health` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | POL-001, SCR-002 |
| TC-355 | 후보 파일에 설명이 없으면 DB videos 테이블의 설명(WU-2가 채움)을 사용하고, 없으면 '설명 미사용'이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validate_cmd.py::test_description_from_videos_table_is_used` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-004 |
| TC-356 | 후보 파일의 description_excerpt가 있으면 그것을 우선 사용한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validate_cmd.py::test_excerpt_in_file_takes_priority_over_db` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-201, FR-004 |
| TC-357 | `--plain`은 표 대신 항목: 값 목록으로 출력한다(스크린리더 친화). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validate_cmd.py::test_plain_mode_for_screen_readers` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SCR-002, UX-002 |
| TC-358 | 제목에 숨긴 ANSI 이스케이프가 리포트 화면에 그대로 나오지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validate_cmd.py::test_external_strings_are_sanitized_in_report` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-019 |
| TC-359 | 후보 입력·검증 모듈에는 네트워크·YouTube 쓰기 호출 코드가 없다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_validate_cmd.py::test_no_write_api_or_network_in_modules` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001, SEC-007 |
| TC-360 | 사전에 숨긴 위험한 YAML 태그는 실행되지 않고(safe_load) 오류로 거부된다. 실행 흔적(표식 폴더)이 남지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_banned_terms.py::test_dangerous_yaml_tag_is_not_executed` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-003, SEC-016 |

### 4-1. 인수 조건 ↔ 테스트 케이스 추적
| AC | 인수 조건 | 연결 TC | 판정 |
|---|---|---|---|
| AC-01 | 후보 파일 필드·형식·크기·후보 수 검증, BOM 허용, 비UTF-8 안내, 오류 일괄 안내 | TC-300, TC-301, TC-302, TC-303, TC-304, TC-308, TC-310, TC-311, TC-312, TC-313, TC-314, TC-315 | 충족 |
| AC-02 | 경로 조작 방지(폴더 바로 아래·ID 형식·video_id 일치·심볼릭 링크) | TC-305, TC-306, TC-307, TC-309 | 충족 |
| AC-03 | 금칙어 사전 로드·검증·안전한 YAML·해시 | TC-316, TC-317, TC-318, TC-319, TC-320, TC-360 | 충족 |
| AC-04 | 차단: 5개 유형·길이·규격·불일치·우회 표기 | TC-322, TC-323, TC-325, TC-338, TC-339 | 충족 |
| AC-05 | 경고: 느낌표·이모지·반복 기호·대문자·기호 비율·권장 길이·핵심어·동일 제목·근거 미확인 | TC-326, TC-328, TC-332, TC-336, TC-337 | 충족 |
| AC-06 | 경계값 40/41/100/101자, 일치율 50%/25%, 느낌표·이모지 | TC-324, TC-327, TC-333, TC-334 | 충족 |
| AC-07 | 엄격 모드(건강·금융·미지정·낱말 감지) | TC-329, TC-330, TC-331, TC-354 | 충족 |
| AC-08 | 영상 일치 점검(요약+설명, 근거 문장, 설명 사용 표시) | TC-332, TC-335, TC-341, TC-355, TC-356 | 충족 |
| AC-09 | 리포트(SCR-002) 형식, --plain | TC-344, TC-340, TC-357 | 충족 |
| AC-10 | DB 기록(상태·해시·사유, 중복 방지, 승인 이후 불변) | TC-345, TC-346, TC-347, TC-348 | 충족 |
| AC-11 | 명령 동작·오류 처리·정화·네트워크 코드 부재 | TC-349, TC-350, TC-351, TC-352, TC-353, TC-358, TC-359 | 충족 |
| AC-12 | 100건 5초 이내, 입력 불변·순수성 | TC-342, TC-343 | 충족 |
| AC-13 | 통과 12건 이상, 차단 10건 이상 | TC-321, TC-322 | 충족 |

- 인수 조건에 연결되지 않은 TC(추가 안전 케이스): TC-001, TC-002, TC-003, TC-004, TC-005, TC-006, TC-007, TC-008, TC-009, TC-010
- 정상 경로, 경계값(날짜 경계·상한·빈 입력), 예외 입력(잘못된 형식·악성 문자열), 권한 경계를 포함했다.

## 5. 커버리지
- 전체 지표: 이 단위 모듈(youtube_title.candidates, youtube_title.banned_terms, youtube_title.validator, youtube_title.commands.validate)의 줄+분기 합산 **100%** (pytest-cov, `--cov-branch`)
- 회귀(이전 단위 산출물을 깨뜨리지 않음): 전체 테스트 스위트 `440 passed, 1 skipped` (통과)
- 호환 실행: 3.11 → 146 passed / 3.13 → 146 passed / 3.12(주) → 146 passed
- 커버되지 않은 부분과 사유:
  - src/youtube_title/banned_terms.py           76      0     24      0   100%
  - src/youtube_title/candidates.py            101      0     36      0   100%
  - src/youtube_title/commands/validate.py      73      0     18      0   100%
  - src/youtube_title/validator.py             139      0     60      0   100%
  - 이 단위 모듈의 줄·분기 커버리지는 위 수치.

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 내용 |
|----|------|-----------|--------|------|-----------|
| DEF-6-013 | `validate --file` 상대 경로가 현재 폴더 기준이라 `--base-dir`와 어긋남 | TC-344 첫 실행 | Medium | Fixed | 프로젝트 폴더 기준으로 해석 |
| DEF-6-014 | `current_title`이 화면에 정화 없이 출력(ANSI 위조 가능) | TC-358 | High | Fixed | sanitize_for_display 적용 |
| DEF-6-015 | 금칙어 사전 오류 안내에 파일 이름 누락 | TC-318 | Low | Fixed | 안내문에 파일 경로 포함 |
| DEF-6-016 | 장식 기호(★)를 이모지로 세지 않아 기대와 불일치 | TC-328 | Low | Fixed | 범위에 0x2600~0x27BF 포함 |
| DEF-6-017 | [테스트 결함] YAML 태그 테스트가 코드 실행 여부를 증명하지 못함(WU-0 TC-008 포함) | 검토/변이 | Medium | Fixed | 표식 폴더 방식으로 보강(TC-008, TC-360) |

- 모두 이 단위 안에서 수정·재검증. WU-0 TC-008 사후 보강(WU-0 결과서에 추가 기록). Open 결함 0건.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트: `.harness-tmp/junit_06.xml`, `.harness-tmp/junit_py311.xml`, `.harness-tmp/junit_py313.xml`, `.harness-tmp/junit_regress.xml`, `.harness-tmp/venv_py311`, `.harness-tmp/venv_py312`, `.harness-tmp/venv_py313`, `.harness-tmp/venv_wu3` (+ 변이 점검용 임시 사본 `.harness-tmp/mut_06/`, 편집 설치로 생긴 `src/*.egg-info`, 캐시 `__pycache__`/`.coverage`)
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예 [ ] 아니오 — 예외: 편집 설치가 `src/youtube_title.egg-info/`를 만들고 파이썬이 `__pycache__`를 만든다(둘 다 `.gitignore` 대상이며 정리 대상에 포함)
- 정리(삭제) 완료 여부: 예. 결과서 생성 스크립트가 `.harness-tmp/`, `data/`, `.coverage`, `src/*.egg-info`, `__pycache__`를 삭제했다
- **정리 후 점검: `git status`는 실행하지 않았다** — 프로젝트 지시(프롬프트 §1)로 git 명령 전면 금지(DEC-006). 대신 파일시스템 점검 결과를 첨부한다: 잔여물 없음 (점검 목록: .harness-tmp, .venv*, venv, *.egg-info, .pytest_cache, .coverage*, __pycache__, data)
- 병렬 실행이었다면: 해당 없음(단독 실행)
- 이번 테스트 도중 강제 중단: [x] 없음 / [ ] 있음

## 8. 리스크 및 잔존 이슈
- **미검증(PASS로 세지 않음)**: 실데이터 기준 과차단/과소차단, 일치율 휴리스틱 정확도, 금칙어 사전의 법적 적절성
- 후속 조치: 사용자가 사전 초안을 검토하고 실제 영상 몇 건으로 `validate`를 돌려 결과 알림

## 9. 결론 및 판정
- 판정: **PASS**
- 근거: 실패 TC 0건, 미수행 TC 0건(-), AC↔TC 추적 문제 0건, 정적 분석(pyflakes) 통과, 변이 점검 34/34 잡아냄, Open 결함 0건
- WU-4가 `title_candidates` 상태(filtered/blocked)를 입력으로 쓸 수 있다.

## 10. 내부 검증 (최소 2회)
- 1차(작성자 관점): AC↔TC 추적, 정적 분석, 커버리지 100%
- 2차(독립 심사자 관점): 변이 점검으로 안전 로직 곳곳을 일부러 망가뜨림. 결과는 부록 A
- 3차: 결함 0건 확인
- 검증 로그 파일 경로: `docs/harness/verify-log_unit-3-test.md`

### 부록 A. 변이 점검(코드를 일부러 망가뜨려 테스트가 실패하는지 확인)
| 변이 | 파일 | 결과 |
|---|---|---|
| 길이 상한 경계(>→>=) | `validator.py` | 잡아냄(테스트 실패) |
| 권장 길이 경계(>→>=) | `validator.py` | 잡아냄(테스트 실패) |
| < > 금지 검사 제거 | `validator.py` | 잡아냄(테스트 실패) |
| 제어 문자 검사 제거 | `validator.py` | 잡아냄(테스트 실패) |
| 빈 제목 검사 제거 | `validator.py` | 잡아냄(테스트 실패) |
| 금칙어 정규화 제거(우회 표기 통과) | `validator.py` | 잡아냄(테스트 실패) |
| 정규식 패턴 검사 제거 | `validator.py` | 잡아냄(테스트 실패) |
| 엄격 모드 승격 제거 | `validator.py` | 잡아냄(테스트 실패) |
| 건강·금융 주제 엄격 판정 제거 | `validator.py` | 잡아냄(테스트 실패) |
| 주제 미지정 엄격 판정 제거 | `validator.py` | 잡아냄(테스트 실패) |
| 엄격 낱말 감지 제거 | `validator.py` | 잡아냄(테스트 실패) |
| 일치율 차단 기준 경계(<→<=) | `validator.py` | 잡아냄(테스트 실패) |
| 일치율 경고 기준 경계(<→<=) | `validator.py` | 잡아냄(테스트 실패) |
| 근거 문장 확인 제거 | `validator.py` | 잡아냄(테스트 실패) |
| 핵심어 위치 검사 제거 | `validator.py` | 잡아냄(테스트 실패) |
| 느낌표 경계(>→>=) | `validator.py` | 잡아냄(테스트 실패) |
| 이모지 경계(>→>=) | `validator.py` | 잡아냄(테스트 실패) |
| 현재 제목 동일 검사 제거 | `validator.py` | 잡아냄(테스트 실패) |
| 설명 사용 무시 | `validator.py` | 잡아냄(테스트 실패) |
| warn 유형도 차단 취급 | `validator.py` | 잡아냄(테스트 실패) |
| 경로 폴더 제한 제거 | `candidates.py` | 잡아냄(테스트 실패) |
| 파일 이름·video_id 일치 검사 제거 | `candidates.py` | 잡아냄(테스트 실패) |
| 크기 상한 검사 제거 | `candidates.py` | 잡아냄(테스트 실패) |
| 후보 수 상한 경계(>→>=) | `candidates.py` | 잡아냄(테스트 실패) |
| BOM 허용 제거 | `candidates.py` | 잡아냄(테스트 실패) |
| 금칙어 길이 검증 제거 | `banned_terms.py` | 잡아냄(테스트 실패) |
| 사전 해시에서 내용 제외 | `banned_terms.py` | 잡아냄(테스트 실패) |
| 사전 safe_load→unsafe | `banned_terms.py` | 잡아냄(테스트 실패) |
| 설정 safe_load→unsafe | `config.py` | 잡아냄(테스트 실패) |
| 승인 이후 행 보호 제거 | `commands/validate.py` | 잡아냄(테스트 실패) |
| 재검증 중복 방지 제거 | `commands/validate.py` | 잡아냄(테스트 실패) |
| 상대 경로 기준 변경 | `commands/validate.py` | 잡아냄(테스트 실패) |
| 현재 제목 정화 제거 | `commands/validate.py` | 잡아냄(테스트 실패) |
| 차단 상태 기록 변경 | `commands/validate.py` | 잡아냄(테스트 실패) |

### 부록 B. 공유 문서 갱신
`traceability.md`의 단위테스트 컬럼과 구현 상태를 스크립트로 갱신했다(통과한 TC만 연결).
