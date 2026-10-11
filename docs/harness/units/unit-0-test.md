# 테스트 결과서 — WU-0 공통 기반 (6단계 단위 테스트)

## 1. 개요
- 테스트 대상: WU-0 공통 기반 (`config, logging_setup, errors, retry, db, timeutil, platform_utils, textsafe, ui, cli, commands/purge`)
- 테스트 유형: 단위
- 적용 Tier: Standard (규칙 B 원문: 최소 2회)
- 적용 속도 트랙: L3
- 병렬 실행 정보: 단독 실행 (이 환경은 서브에이전트를 쓰지 않음, DEC-011)
- 테스트 목적: `unit-0-note.md`의 인수 조건(AC)을 테스트로 증명하고 안전 로직의 회귀를 막는다
- 관련 산출물: `docs/yt/DESIGN.md`, `docs/harness/units/unit-0-note.md`, `docs/yt/02_planning.md`
- 테스트 수행자(에이전트): 오케스트레이터(06단계 역할 직접 수행)
- 테스트 일시: 2026-10-10

## 2. 테스트 범위 및 제외 범위
- 범위(In-Scope): 설정 로더, 로깅·마스킹, 재시도, DB 스키마·마이그레이션·백업, 시간(태평양 날짜), 텍스트 안전 처리, UI 컴포넌트, CLI 자동 탐색·오류 처리·실행 기록, purge 명령, 플랫폼 유틸
- 제외 범위(Out-of-Scope) 및 사유: 실제 YouTube API 호출(WU-1 이후, 그리고 테스트에서는 항상 mock), Windows 고유 동작(이 Linux 환경에서 실행 불가 → 미수행으로 기록), 로그 파일 5MB 회전, Python 3.10

## 3. 테스트 환경
- 실행 환경: Linux, Python 3.12.3 (주 실행) · 3.11 · 3.13 (호환 확인), pytest, pytest-cov. 가상환경은 `.harness-tmp/` 아래에만 생성
- 테스트 데이터: 임시 폴더의 가짜 설정·DB·후보, 가짜 토큰 문자열(실제 비밀 아님). **실제 YouTube API는 호출하지 않음**
- 전제 조건: 이전 단위 없음(공통 선행 단위)

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
| TC-011 | 토큰·키 형식(액세스/리프레시 토큰, GOCSPX, Bearer, JSON 키, 긴 문자열)이 가려진다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_logging.py::test_mask_hides_each_secret_format` | docstring의 기대 결과가 모두 충족 | Pass(7건) | Pass | SEC-008 / 변형 7건 |
| TC-012 | 일반 한글 문장과 11자 영상 ID는 가리지 않는다(과잉 마스킹 방지). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_logging.py::test_mask_keeps_normal_text_and_video_id` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-011 |
| TC-013 | 로그 파일에 메시지·인자·예외 추적 어디에도 비밀이 남지 않고 한글이 정상 저장된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_logging.py::test_log_file_masks_message_args_and_traceback` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-002, SEC-008 |
| TC-014 | setup_logging을 다시 호출해도 핸들러가 중복되지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_logging.py::test_setup_logging_replaces_handlers` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-011 |
| TC-015 | 2번 실패 후 3번째 성공하며 대기는 1초→2초(지수 백오프). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_retry.py::test_succeeds_after_two_retries_with_exponential_backoff` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-004, SEC-003 |
| TC-016 | 계속 실패하면 총 3번(최초+재시도 2회)만 호출하고 예외를 올린다. 무한 재시도 없음. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_retry.py::test_gives_up_after_max_retries` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-003 |
| TC-017 | retries에 큰 값을 줘도 상한(2회)을 넘지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_retry.py::test_retries_parameter_is_capped` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-003 |
| TC-018 | 재시도 불가 오류(인증·할당량 등)는 재시도하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_retry.py::test_non_retryable_error_is_raised_immediately` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-003 |
| TC-019 | 연결 오류와 HTTP 5xx는 재시도 대상, 4xx는 아니다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_retry.py::test_connection_errors_and_http_5xx_are_retryable` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-004 |
| TC-020 | 재시도 콜백이 호출되고, retries=0이면 재시도하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_retry.py::test_on_retry_callback_and_zero_retries` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-004 |
| TC-021 | 7개 테이블이 만들어지고 migrate를 다시 불러도 안전하다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_db.py::test_migrate_creates_seven_tables_and_is_idempotent` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-002 |
| TC-022 | 외래키가 켜져 있어 없는 후보를 가리키는 변경 기록은 거부된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_db.py::test_foreign_keys_enforced` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-006 |
| TC-023 | 상태·종류 값이 허용 목록에 없으면 DB가 거부한다(상태 머신 보호). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_db.py::test_check_constraints_reject_invalid_enums` | docstring의 기대 결과가 모두 충족 | Pass(7건) | Pass | ADR-002, SEC-006 / 변형 7건 |
| TC-024 | 따옴표·SQL 구문이 든 제목도 값으로만 저장되고 테이블은 그대로다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_db.py::test_parameter_binding_stores_injection_text_literally` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-018 |
| TC-025 | 백업 사본이 만들어져 같은 내용을 읽을 수 있고, 같은 초에 두 번 만들어도 덮어쓰지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_db.py::test_backup_creates_readable_copy_without_overwrite` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-010 |
| TC-026 | 프로그램보다 새 버전의 DB는 거부하고 업데이트를 안내한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_db.py::test_newer_db_version_rejected` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-002 |
| TC-027 | 실행 기록이 시작·종료 시각, 종료 코드와 함께 저장된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_db.py::test_run_log_start_and_finish` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-020 |
| TC-028 | 열 수 없는 경로는 한국어 안내가 있는 DatabaseError가 된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_db.py::test_connect_failure_gives_korean_error` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007 |
| TC-029 | 겨울(PST, UTC-8)에는 UTC 08:00에 쿼터 날짜가 바뀐다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_timeutil.py::test_pt_date_boundary_in_winter_pst` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-006, NFR-003 |
| TC-030 | 여름(PDT, UTC-7)에는 UTC 07:00에 날짜가 바뀐다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_timeutil.py::test_pt_date_boundary_in_summer_pdt` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-006 |
| TC-031 | 서머타임 시작일(2026-03-08) 전후로 날짜 경계가 올바르다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_timeutil.py::test_pt_date_around_dst_switch` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-006 |
| TC-032 | UTC ISO 문자열 변환이 왕복되고, 고정 시계는 시각을 앞으로 보낼 수 있다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_timeutil.py::test_iso_roundtrip_and_fixed_clock` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-008 |
| TC-033 | 날짜 형식이 틀리면 형식 예시와 함께 ConfigError가 난다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_timeutil.py::test_parse_date_errors_are_korean` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007 |
| TC-034 | ANSI 이스케이프·제어 문자가 제거되어 화면을 속일 수 없다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_textsafe.py::test_sanitize_strips_ansi_and_control_chars` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-019 |
| TC-035 | 방향 제어 문자(RLO 등)를 제거하고 None도 안전하게 처리한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_textsafe.py::test_sanitize_removes_bidi_override_and_handles_none` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-019 |
| TC-036 | 길이 제한 시 말줄임표로 줄인다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_textsafe.py::test_sanitize_truncates_with_ellipsis` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007 |
| TC-037 | 글자 수는 유니코드 문자 기준(NFC)이며 한글·결합 문자가 올바르다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_textsafe.py::test_char_count_is_unicode_code_points` | docstring의 기대 결과가 모두 충족 | Pass(6건) | Pass | FR-002 / 변형 6건 |
| TC-038 | 띄어쓰기·기호·전각 문자로 숨긴 표기도 같은 형태로 정규화된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_textsafe.py::test_normalize_defeats_evasion` | docstring의 기대 결과가 모두 충족 | Pass(7건) | Pass | FR-003 / 변형 7건 |
| TC-039 | 정규화 결과는 문자·숫자만 남고 소문자이다(제로폭 문자 포함 제거). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_textsafe.py::test_normalize_keeps_letters_digits_only` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-003 |
| TC-040 | 한글·전각은 2칸, 영문·숫자는 1칸, 결합 문자는 0칸으로 센다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_textsafe.py::test_display_width_counts_hangul_as_two` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-002, SCR-002 |
| TC-041 | 상태 배지는 기호+글자이며 색을 꺼도 구분되고, 색을 켜도 글자는 유지된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_ui.py::test_status_badges_are_symbol_plus_text_and_color_optional` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SCR-002, UX-002 |
| TC-042 | 제목 줄이 모의 실행과 실제 적용(LIVE)을 눈에 띄게 구분한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_ui.py::test_title_line_marks_live_clearly` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001 |
| TC-043 | 한글이 섞인 표가 80열 안에서 열 경계가 맞게 정렬된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_ui.py::test_table_aligns_korean_columns_within_width` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-002, SCR-002 |
| TC-044 | --plain 모드는 표 대신 `항목: 값` 목록으로 출력한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_ui.py::test_plain_mode_lists_items_instead_of_table` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SCR-002, UX-002 |
| TC-045 | 표에 들어가는 외부 문자열의 제어 문자가 제거된다(승인 요약 위조 방지). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_ui.py::test_table_sanitizes_external_strings` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-019 |
| TC-046 | 오류 블록은 코드·원인·다음에 할 일을 담고 비어 있어도 기본 안내를 준다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_ui.py::test_error_block_has_what_why_next` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007 |
| TC-047 | 확인 문구를 정확히 입력해야 통과하고, 3번 틀리면 중단한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_ui.py::test_confirm_accepts_exact_text_only` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001 |
| TC-048 | 빈 줄이나 입력 불가(EOF)는 취소로 처리한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_ui.py::test_confirm_cancel_on_blank_and_eof` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001 |
| TC-049 | 면책 문구가 고정되어 있고 진행 표시가 단계 상태를 보여 준다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_ui.py::test_footer_and_progress` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | POL-002 |
| TC-050 | 기본 토큰 폴더는 사용자 프로필 아래 ytitle/tokens 이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_platform.py::test_default_token_dir_is_outside_project_and_named` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-004, SEC-015 |
| TC-051 | POSIX에서 파일 권한이 소유자 전용(600)으로 제한된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_platform.py::test_restrict_permissions_posix` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-008 |
| TC-052 | 없는 파일에 대해 예외 없이 실패 결과(False)와 한국어 메시지를 돌려준다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_platform.py::test_restrict_permissions_missing_file_does_not_raise` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007 |
| TC-053 | 표준 출력이 바뀐 환경에서도 UTF-8 설정이 예외 없이 동작한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_platform.py::test_ensure_utf8_console_is_safe_on_replaced_streams` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-002 |
| TC-054 | [Windows 전용] icacls로 파일 권한이 현재 사용자로 제한된다. [SEC-008] — 이 환경 미수행 | 자동 테스트 환경(임시 폴더) | `pytest tests/test_platform.py::test_windows_acl_restriction` | docstring의 기대 결과가 모두 충족 | 미수행(건너뜀)(1건) | 미수행(건너뜀) | SEC-008 |
| TC-055 | --help가 등록된 명령(purge)과 '기본은 모의 실행' 안내, 면책 문구를 보여 준다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_cli.py::test_help_lists_registered_commands_and_disclaimer` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-017, POL-002, SCR-001 |
| TC-056 | 인자 없이 실행하면 도움말을 보여 주고 정상 종료한다(초보자 친화). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_cli.py::test_no_arguments_shows_help_and_exits_zero` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SCR-001 |
| TC-057 | 알 수 없는 명령은 종료 코드 2(사용법 오류)이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_cli.py::test_unknown_command_exit_code_2` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-017 |
| TC-058 | 쓰기 명령이 아닌 purge에는 --live 옵션이 존재하지 않는다(기본 dry-run 보장). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_cli.py::test_live_flag_not_accepted_by_purge` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001 |
| TC-059 | commands 폴더에 파일만 추가하면 --help에 자동으로 나타난다(병렬 개발 충돌 방지). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_cli.py::test_commands_are_auto_discovered` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-003 |
| TC-060 | 안전 게이트 오류는 한국어 오류 블록으로 출력되고 종료 코드 3이 된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_cli.py::test_ytierror_is_shown_in_korean_and_exit_code_mapped` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007, SEC-001 |
| TC-061 | 예상 못한 오류도 비밀 없이 한국어로 안내되고 로그에 남는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_cli.py::test_unexpected_exception_is_masked_and_logged` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007, SEC-008 |
| TC-062 | 명령 실행이 run_logs에 시작·종료 시각과 종료 코드로 기록된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_cli.py::test_run_is_recorded_in_run_logs` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-020 |
| TC-063 | 설정 오류는 명령 실행 전에 한국어 안내와 함께 중단된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_cli.py::test_invalid_settings_stop_with_config_error` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007 |
| TC-064 | settings.yaml의 live 값이 무시되면 [주의] 경고가 화면에 나온다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_cli.py::test_settings_warning_is_printed` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001 |
| TC-065 | 전역 옵션 --plain은 명령 뒤에 써도 적용된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_cli.py::test_plain_option_accepted_after_subcommand` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-017, SCR-002 |
| TC-066 | 기본(미리보기)은 대상 건수만 보여 주고 아무것도 지우지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_purge.py::test_preview_deletes_nothing` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-009, SCR-010 |
| TC-067 | --execute라도 '삭제'를 직접 입력해야 하고, 입력이 없으면 삭제하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_purge.py::test_execute_requires_typed_confirmation` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SCR-010, SEC-001 |
| TC-068 | 실행하면 DB 사본을 먼저 만들고, 영상별 가장 최근 성공 변경(롤백용)과 그 후보는 보존한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_purge.py::test_execute_deletes_old_rows_but_protects_latest_success_and_backs_up` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-009, SEC-006 |
| TC-069 | 미래 날짜와 잘못된 형식은 거부되고 아무것도 지우지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_purge.py::test_future_date_and_bad_format_rejected` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007 |
| TC-070 | 대상이 없으면 확인 없이 '삭제할 기록이 없습니다'로 끝난다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_purge.py::test_nothing_to_delete` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SCR-010 |
| TC-071 | 지금 실행 중인 명령의 run_logs 행은 삭제 대상에서 제외된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_purge.py::test_run_log_of_current_run_survives_purge` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-020 |
| TC-072 | --base-dir/--plain이 명령 앞·뒤 어느 위치에서도 적용되고, 현재 폴더에는 아무것도 만들지 않는다(회귀 방지). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_cli.py::test_global_options_honored_before_and_after_subcommand` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-017 |
| TC-073 | 사용자가 Ctrl+C로 중단하면 한국어 안내와 함께 종료 코드 130이 된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_edge.py::test_keyboard_interrupt_exit_130` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-020, NFR-008 |
| TC-074 | `python -m ytitle --version`이 실제로 실행되어 버전을 출력한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_edge.py::test_python_dash_m_entrypoint_works` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-017 |
| TC-075 | 비어 있는 설정 파일은 기본값으로, 항목이 목록/숫자 형태로 잘못되면 ConfigError. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_edge.py::test_empty_yaml_and_wrong_section_type` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007 |
| TC-076 | 마이그레이션 SQL이 실패하면 한국어 DatabaseError가 되고 DB는 부분 적용되지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_edge.py::test_migration_failure_becomes_database_error` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-002 |
| TC-077 | tzdata가 없어 태평양 시간대를 못 찾으면 설치 방법을 안내하는 ConfigError. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_edge.py::test_missing_tzdata_gives_actionable_error` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-006 |
| TC-078 | 콘솔 로그(경고 이상)도 같은 마스킹을 거친다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_edge.py::test_console_logging_handler_masks_secrets` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-008 |
| TC-079 | 닫힌 연결에 실행 기록을 저장하려 하면 한국어 DatabaseError가 된다(조용히 삼키지 않음). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_edge.py::test_finish_run_failure_is_database_error` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-020, NFR-007 |

### 4-1. 인수 조건 ↔ 테스트 케이스 추적
| AC | 인수 조건 | 연결 TC | 판정 |
|---|---|---|---|
| AC-01 | `--help`가 commands를 자동 탐색해 표시 | TC-055, TC-056, TC-059 | 충족 |
| AC-02 | 기본 dry-run(쓰기 아닌 명령에 --live 없음, 실행 모드 기록) | TC-058, TC-062 | 충족 |
| AC-03 | 설정 로드·우선순위·검증, live는 local에서만, 위험한 YAML 거부 | TC-001, TC-002, TC-003, TC-004, TC-005, TC-006, TC-007, TC-008, TC-009, TC-010, TC-063, TC-064, TC-075 | 충족 |
| AC-04 | 로그·예외·콘솔에서 비밀 마스킹, 정상 문장은 유지 | TC-011, TC-012, TC-013, TC-014, TC-061, TC-078 | 충족 |
| AC-05 | 재시도 최대 2회·지수 백오프·재시도 불가 즉시 중단 | TC-015, TC-016, TC-017, TC-018, TC-019, TC-020 | 충족 |
| AC-06 | DB 7개 테이블·제약·원자적 마이그레이션·바인딩·백업·새 버전 거부 | TC-021, TC-022, TC-023, TC-024, TC-025, TC-026, TC-027, TC-028, TC-076, TC-079 | 충족 |
| AC-07 | textsafe: 제어문자 제거, 글자 수, 우회 표기 정규화, 표시 폭 | TC-034, TC-035, TC-036, TC-037, TC-038, TC-039, TC-040 | 충족 |
| AC-08 | timeutil: 태평양 날짜 경계(겨울/여름/서머타임 전환), tzdata 없을 때 안내 | TC-029, TC-030, TC-031, TC-032, TC-033, TC-077 | 충족 |
| AC-09 | purge: 미리보기·확인·사본·보존·날짜 검증 | TC-066, TC-067, TC-068, TC-069, TC-070, TC-071 | 충족 |
| AC-10 | ui 컴포넌트(배지·표·plain·오류 블록·영상 ID 입력 확인·면책) | TC-041, TC-042, TC-043, TC-044, TC-045, TC-046, TC-047, TC-048, TC-049 | 충족 |
| AC-11 | 전역 옵션이 어느 위치에서나 적용, 현재 폴더 비오염 | TC-065, TC-072 | 충족 |
| AC-12 | 플랫폼 유틸(토큰 폴더, 권한, UTF-8) | TC-050, TC-051, TC-052, TC-053 | 충족 |
| AC-13 | 오류 처리: 종료 코드·한국어 블록·Ctrl+C·진입점 | TC-057, TC-060, TC-073, TC-074 | 충족 |

- 인수 조건에 연결되지 않은 TC(추가 안전 케이스): TC-054
- 정상 경로, 경계값(날짜 경계·상한·빈 입력), 예외 입력(잘못된 형식·악성 문자열), 권한 경계를 포함했다.

## 5. 커버리지
- 전체 지표: 줄+분기 합산 **95%** (pytest-cov, `--cov-branch`)
- 호환 실행: 3.11 → 108 passed, 1 skipped / 3.13 → 108 passed, 1 skipped / 3.12(주) → 108 passed, 1 skipped
- 커버되지 않은 부분과 사유:
  - src/ytitle/__init__.py                                                                  1      0      0      0   100%
  - src/ytitle/__main__.py                                                                  4      4      2      0     0%   1-6
  - src/ytitle/cli.py                                                                     116      4     22      5    93%   53->exit, 87, 89->85, 104, 147->150, 153-154
  - src/ytitle/commands/__init__.py                                                         0      0      0      0   100%
  - src/ytitle/commands/purge.py                                                           56      0      8      0   100%
  - src/ytitle/config.py                                                                  107      0     30      0   100%
  - src/ytitle/db.py                                                                       69      1     18      2    97%   97, 100->102
  - src/ytitle/errors.py                                                                   26      0      0      0   100%
  - src/ytitle/logging_setup.py                                                            36      0      6      0   100%
  - src/ytitle/platform_utils.py                                                           33     11     10      3    63%   16-17, 26-33, 45-48
  - src/ytitle/retry.py                                                                    26      0      8      0   100%
  - src/ytitle/textsafe.py                                                                 37      0     12      1    98%   46->52
  - src/ytitle/timeutil.py                                                                 32      0      2      0   100%
  - src/ytitle/ui.py                                                                       69      0     18      0   100%
  - Windows 분기(`platform_utils` 16~17, 26~33, 45~48행 중 일부): Linux에서 실행 불가 → TC-054는 **미수행(Windows 필요)**
  - `__main__.py`: 별도 프로세스에서 실행되어 측정되지 않음(TC-074가 실제 실행으로 대신 검증)
  - `cli.py` 일부 방어 분기(예: 설정 오류 후 컨텍스트가 없을 때의 정리): 도달 조건이 인위적

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 내용 |
|----|------|-----------|--------|------|-----------|
| DEF-6-001 | argparse의 `--help`/사용법 오류가 주입한 출력 스트림 대신 실제 stdout으로 나감 | TC-055 첫 실행 | Low | Fixed | `redirect_stdout/redirect_stderr`로 감쌈 |
| DEF-6-002 | **`--base-dir`·`--plain`이 무시됨**: argparse `parents=`가 옵션 객체를 공유해 루트의 set_defaults가 서브커맨드 기본값을 덮어씀. 그 결과 테스트가 저장소 폴더에 `data/`를 생성 | TC-062, TC-066~ 첫 실행(8건 실패) | High | Fixed | 루트·서브커맨드 파서를 분리, 회귀 TC-072 추가, 테스트 작업 폴더를 임시 폴더로 격리(conftest autouse) |
| DEF-6-003 | **마이그레이션이 비원자적**: 중간 SQL 실패 시 앞서 만든 테이블이 남아 이후 영구 오류 | TC-076 첫 실행 | High | Fixed | 명시적 `BEGIN/COMMIT/ROLLBACK` |
| DEF-6-004 | f-string 안의 같은 종류 따옴표 중첩(3.12 전용 문법)이 3.10/3.11 호환 선언과 충돌 | 코드 점검(3.13 pyflakes는 통과해 놓침, 3.11 실행으로 확인) | Medium | Fixed | 따옴표 변경, 3.11/3.12/3.13에서 전체 실행 |
| DEF-6-005 | `cli.py` finally의 `locals().get`과 `except Exception: pass`로 실행 기록 실패를 조용히 삼킴 | 코드 리뷰(게이트 2) | Medium | Fixed | 변수 사전 초기화, `finish_run` 실패를 DatabaseError로 변환해 로그에 남김, TC-079 |
| DEF-6-006 | 미사용 import 4건 | pyflakes | Low | Fixed | 제거 |
| DEF-6-007 | [테스트 결함] 항상 통과하는 단언(`or True`) | 테스트 리뷰 | Low | Fixed | 열 경계 정렬을 실제로 비교하는 단언으로 교체 |
| DEF-6-008 | [테스트 결함] TC-069가 "미래 날짜 검사 제거" 변이를 놓침(다른 예외로 종료 코드 1이 나와 우연히 통과) | 변이 점검 | Medium | Fixed | 오류 코드·메시지·백업 미생성까지 단언 |
| DEF-6-009 | 7개 TC의 docstring에 검증 대상 요구사항 ID 누락(규칙 H) | 추적 점검 스크립트 | Low | Fixed | FR/SCR/ADR 등 ID 보강 |

- 위 결함은 모두 이 6단계 점검 중 발견되어 **같은 세션에서 수정·재검증**되었다(원인이 이 단위 안에 있음, 상위 산출물 결함 없음). Open 결함 0건. 결함 DEF-6-002·003은 High였으며 TC로 재현을 고정했다.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트: `.harness-tmp/junit_06.xml`, `.harness-tmp/junit_py311.xml`, `.harness-tmp/junit_py313.xml`, `.harness-tmp/venv_05_wu0`, `.harness-tmp/venv_05_wu0_py311`, `.harness-tmp/venv_05_wu0_py312`, `.harness-tmp/venv_py311`, `.harness-tmp/venv_py312`, `.harness-tmp/venv_py313` (+ 변이 점검용 임시 사본 `.harness-tmp/mut_06/`, 편집 설치로 생긴 `src/*.egg-info`, 캐시 `__pycache__`/`.coverage`)
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예 [ ] 아니오 — 예외: 편집 설치가 `src/ytitle.egg-info/`를 만들고 파이썬이 `__pycache__`를 만든다(둘 다 `.gitignore` 대상이며 정리 대상에 포함)
- 정리(삭제) 완료 여부: 예. 결과서 생성 스크립트가 `.harness-tmp/`, `data/`, `.coverage`, `src/*.egg-info`, `__pycache__`를 삭제했다
- **정리 후 점검: `git status`는 실행하지 않았다** — 프로젝트 지시(프롬프트 §1)로 git 명령 전면 금지(DEC-006). 대신 파일시스템 점검 결과를 첨부한다: 잔여물 없음 (점검 목록: .harness-tmp, .venv*, venv, *.egg-info, .pytest_cache, .coverage*, __pycache__, data)
- 병렬 실행이었다면: 해당 없음(단독 실행)
- 이번 테스트 도중 강제 중단: [x] 없음 / [ ] 있음

## 8. 리스크 및 잔존 이슈
- **미수행(PASS로 세지 않음)**: TC-054 Windows `icacls` 권한 제한. 잔여 위험: 토큰 파일 권한이 Windows에서 의도대로 제한되지 않을 수 있음 → WU-1에서 토큰 저장 시 실패해도 경고하고 계속하는지 확인, 10단계 전 사용자가 PowerShell에서 확인
- **미검증**: Python 3.10, 로그 5MB 회전, 실제 콘솔 인코딩(cp949), 마스킹 패턴의 한계(비표준 비밀 형식은 못 가림 / 40자 이상 문자열은 과잉 마스킹 가능)
- 후속 조치: 8단계 전체 테스트에서 Windows 점검 목록 작성, 린트 도구 도입 여부 질문(unit-0 노트 7절)

## 9. 결론 및 판정
- 판정: **PASS**
- 근거: 실패 TC 0건, 미수행 TC 1건(TC-054), AC↔TC 추적 문제 0건, 정적 분석(pyflakes) 통과, 변이 점검 23/23 잡아냄, Open 결함 0건
- 다음 단위(WU-1, WU-3)가 이 단위의 공통 기반을 입력으로 쓸 수 있다. 미수행 TC-054는 PASS로 세지 않았고 8·10단계 미수행 목록으로 이월한다.

## 10. 내부 검증 (최소 2회)
- 1차(작성자 관점): AC↔TC 추적, TC 근거(요구 ID), 정적 분석, 3개 Python 버전 실행. 결함 2건(DEF-6-007, DEF-6-009) 발견·수정
- 2차(독립 심사자 관점): "이 테스트가 통과하면 정말 안전한가"를 의심해 **변이 점검**을 수행. 1건 놓침 → DEF-6-008 수정 후 재확인. 3차에서 결함 0건 확인
- 검증 로그 파일 경로: `docs/harness/verify-log_unit-0-test.md`

### 부록 A. 변이 점검(코드를 일부러 망가뜨려 테스트가 실패하는지 확인)
| 변이 | 파일 | 결과 |
|---|---|---|
| 재시도 상한 2→3 | `retry.py` | 잡아냄(테스트 실패) |
| 백오프 2배→3배 | `retry.py` | 잡아냄(테스트 실패) |
| 재시도 불가 오류도 재시도 | `retry.py` | 잡아냄(테스트 실패) |
| 쿼터 날짜를 UTC로 | `timeutil.py` | 잡아냄(테스트 실패) |
| settings.yaml의 live 무시 제거 | `config.py` | 잡아냄(테스트 실패) |
| 제목 상한 100 완화 | `config.py` | 잡아냄(테스트 실패) |
| ANSI 제거 생략 | `textsafe.py` | 잡아냄(테스트 실패) |
| 방향 제어문자 제거 생략 | `textsafe.py` | 잡아냄(테스트 실패) |
| 정규화에 기호 유지 | `textsafe.py` | 잡아냄(테스트 실패) |
| Bearer 마스킹 제거 | `logging_setup.py` | 잡아냄(테스트 실패) |
| 긴 토큰 마스킹 제거 | `logging_setup.py` | 잡아냄(테스트 실패) |
| purge 최근 성공 보호 제거 | `commands/purge.py` | 잡아냄(테스트 실패) |
| purge 확인 생략 | `commands/purge.py` | 잡아냄(테스트 실패) |
| purge 미래 날짜 허용 | `commands/purge.py` | 잡아냄(테스트 실패) |
| 확인 시도 3→5회 | `ui.py` | 잡아냄(테스트 실패) |
| 외래키 끄기 | `db.py` | 잡아냄(테스트 실패) |
| 마이그레이션 트랜잭션 제거 | `db.py` | 잡아냄(테스트 실패) |
| 백업 덮어쓰기 허용 | `db.py` | 잡아냄(테스트 실패) |
| 전역 옵션 파서 공유(회귀 버그) | `cli.py` | 잡아냄(테스트 실패) |
| argparse 출력 리다이렉트 제거 | `cli.py` | 잡아냄(테스트 실패) |
| Ctrl+C 처리 제거 | `cli.py` | 잡아냄(테스트 실패) |
| 기본 토큰 폴더를 프로젝트 안으로 | `config.py` | 잡아냄(테스트 실패) |
| purge 미래 날짜 허용(약한 TC-069 보강 후) | `commands/purge.py` | 잡아냄(테스트 실패) |

### 부록 B. 공유 문서 갱신
`traceability.md`의 단위테스트 컬럼과 구현 상태를 스크립트로 갱신했다(통과한 TC만 연결).

### 부록 C. 사후 보강 (WU-3 중 수행, 2026-10-10)
`tests/test_config.py` TC-008을 보강했다. 위험한 YAML 태그를 설정 파일에 넣고 **표식 폴더가 만들어지지 않음**(코드 비실행)과 한국어 오류를 함께 확인한다. 변이 점검(설정 `safe_load`→`UnsafeLoader`)이 WU-3 결과서에서 이 테스트로 잡힘을 확인했다. 판정 변경 없음(PASS).

### 부록 C. 사후 변경 기록 (2026-10-10, DEC-031)
- 변경: `--base-dir`이 없을 때 기준 폴더를 실행한 폴더(cwd)가 아니라 프로젝트 루트(`pyproject.toml`과 `src/ytitle/cli.py`가 있는 곳)로 고정(소스 트리 밖 설치형은 cwd). 사용자 지시("권장사항으로 진행").
- 추가 테스트: TC-103(루트 고정·cwd 무관), TC-104(소스 트리 밖 폴백, pyproject만 있는 폴더 거부), TC-105(기본 실행이 루트를 기준으로 쓰고 현재 폴더를 오염하지 않음). AC-11(전역 옵션·현재 폴더 비오염)에 연결.
- 변이 점검(수작업 5개, 모두 적발): 기준을 cwd로 되돌림 / 루트 판정에서 `src/ytitle/cli.py` 조건 제거 / `pyproject.toml` 조건 제거 / 상위 폴더 수 변경 / 폴백을 cwd 대신 루트로 변경. 1회차에서 `src/ytitle/cli.py` 조건 제거를 놓쳐 TC-104에 'pyproject만 있는 폴더' 사례를 추가한 뒤 5/5 적발.
- 전체 회귀: 1,154 통과 / 1 건너뜀 / 2 예상 실패(xfail).
