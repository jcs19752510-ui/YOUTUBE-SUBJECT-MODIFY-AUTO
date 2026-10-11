# 테스트 결과서 — WU-2 YouTube 조회·쿼터 (6단계 단위 테스트)

## 1. 개요
- 테스트 대상: WU-2 YouTube 조회·쿼터 (`quota, youtube_read, commands/fetch`)
- 테스트 유형: 단위
- 적용 Tier: Standard (규칙 B 원문: 최소 2회)
- 적용 속도 트랙: L3
- 병렬 실행 정보: 단독 실행 (이 환경은 서브에이전트를 쓰지 않음, DEC-011)
- 테스트 목적: `unit-2-note.md`의 인수 조건(AC)을 테스트로 증명하고 안전 로직의 회귀를 막는다
- 관련 산출물: `docs/yt/DESIGN.md`, `docs/harness/units/unit-2-note.md`, `docs/yt/02_planning.md`
- 테스트 수행자(에이전트): 오케스트레이터(06단계 역할 직접 수행)
- 테스트 일시: 2026-10-10

## 2. 테스트 범위 및 제외 범위
- 범위(In-Scope): 쿼터 선예약·상한·경고, 읽기 전용 채널 영상 조회, 영상 정보 저장, Analytics 지표 수집과 폴백, 오류 변환, `fetch` 명령
- 제외 범위(Out-of-Scope) 및 사유: 실제 구글 서버 호출(응답 모양·지표 이름·쿼터 비용·필터 상한은 가짜 응답으로만 확인, 원문 미열람 [확인 필요])

## 3. 테스트 환경
- 실행 환경: Linux, Python 3.12.3 (주 실행) · 3.11 · 3.13 (호환 확인), pytest, pytest-cov. 가상환경은 `.harness-tmp/` 아래에만 생성
- 테스트 데이터: 임시 폴더의 가짜 설정·DB·후보, 가짜 토큰 문자열(실제 비밀 아님). **실제 YouTube API는 호출하지 않음**
- 전제 조건: 이전 단위 WU-0, WU-1 PASS

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고(검증하는 ID) |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-200 | 예약하면 호출 전에 reserved 행이 남고, 아직 결과 표시가 없어도 오늘 사용량에 포함된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_quota.py::test_reserve_records_before_call_and_counts_reserved` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-015, SEC-002 |
| TC-201 | 상한 직전(남은 1)까지는 예약되고, 상한을 채운 뒤의 1 units는 QuotaError이며 DB는 그대로다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_quota.py::test_limit_boundary_exact_allowed_then_rejected_without_db_change` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-015, NFR-003, SEC-002 |
| TC-202 | 남은 양보다 큰 예약은 거부되고 DB에 흔적이 없으며, 태평양 자정·한국 시간 초기화 안내가 나온다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_quota.py::test_single_reserve_over_limit_rejected_with_reset_guidance` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-015, NFR-007, SEC-002 |
| TC-203 | 상한이 0이면 어떤 예약도 거부된다(남은 양은 음수가 되지 않는다). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_quota.py::test_zero_limit_rejects_everything` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-003, SEC-002 |
| TC-204 | 호출이 실패(failed)로 표시돼도 units 차감은 유지되고, ok와 failed가 각각 기록된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_quota.py::test_failed_call_keeps_units_charged` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-008, FR-015, SEC-002 |
| TC-205 | mark는 잘못된 상태·없는 ID·이미 처리된 예약을 거부하고 기록을 바꾸지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_quota.py::test_mark_rejects_bad_status_unknown_id_and_double_mark` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-015 |
| TC-206 | units가 0 이하·정수 아님이거나 호출 이름이 비어 있으면 InputError이고 DB에 남기지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_quota.py::test_invalid_method_or_units_rejected` | docstring의 기대 결과가 모두 충족 | Pass(8건) | Pass | FR-015, SEC-002 / 변형 8건 |
| TC-207 | 예약 행의 pt_date가 태평양 시간 날짜이며 서머타임 전후 경계에서도 맞다(UTC 날짜가 아님). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_quota.py::test_pt_date_boundary_stored_on_reserve` | docstring의 기대 결과가 모두 충족 | Pass(7건) | Pass | FR-015, NFR-003, SEC-002 / 변형 7건 |
| TC-208 | 태평양 자정을 넘기면 어제 사용량은 오늘 집계에서 빠지고 다시 전체 한도를 쓸 수 있다(날짜별 분리). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_quota.py::test_usage_separated_by_pt_day` | docstring의 기대 결과가 모두 충족 | Pass(3건) | Pass | FR-015, NFR-003 / 변형 3건 |
| TC-209 | 사용량이 상한의 80% 미만이면 경고가 없고 정확히 80%가 되면 경고를 알린다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_quota.py::test_warning_threshold_at_80_percent` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-015, NFR-003 |
| TC-210 | 경고 비율은 설정값을 따른다(0.5이면 50%에서 경고). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_quota.py::test_warn_ratio_follows_settings` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-003 |
| TC-211 | 호출 이름·실행 ID에 SQL 조각이 있어도 값으로만 저장되고 테이블은 멀쩡하다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_quota.py::test_sql_injection_in_method_is_stored_as_value` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-018 |
| TC-212 | reserved·ok·failed 모두 합산하고 다른 날짜 행은 합산하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_quota.py::test_used_today_counts_all_statuses` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-015, SEC-002 |
| TC-213 | quota_usage 테이블을 읽거나 쓰지 못하면 한국어 DatabaseError(YT-200)이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_quota.py::test_database_failure_becomes_database_error` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-015, NFR-007 |
| TC-214 | 사용량이 쓰인 뒤 상한 설정을 낮춰 사용량이 상한을 넘어도 남은 양은 0이고 새 예약은 거부된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_quota.py::test_remaining_never_negative_when_limit_lowered` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-015, SEC-002 |
| TC-220 | 업로드 재생목록을 전 페이지(50/50/7) 순회해 순서대로 ID를 모으고 호출마다 쿼터를 예약한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_list_ids_walks_all_pages` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-006, SEC-002 |
| TC-221 | 채널 응답에 업로드 재생목록이 없으면 ApiError이고 재생목록 호출은 하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_list_ids_channel_contract_violation` | docstring의 기대 결과가 모두 충족 | Pass(6건) | Pass | FR-006, NFR-007 / 변형 6건 |
| TC-222 | 재생목록 항목 중 형식이 틀린 ID는 건너뛰어 개수로 세고 중복은 한 번만 담는다. 목록이 아니면 ApiError. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_list_ids_skips_invalid_and_duplicate_entries` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-006 |
| TC-223 | 같은 pageToken이 반복되면 무한 순회하지 않고 ApiError로 중단한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_list_ids_stops_on_repeated_page_token` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-006, SEC-002 |
| TC-224 | 영상 ID 120개는 videos.list 3번(50/50/20)으로 나눠 조회하고 모두 저장하며 호출마다 1 unit을 예약한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_fetch_videos_splits_120_ids_into_50_50_20` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-006, SEC-002 |
| TC-225 | 배치 경계(1/50/51/100/101개)에서 한 번에 50개를 넘기지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_batch_boundaries` | docstring의 기대 결과가 모두 충족 | Pass(5건) | Pass | FR-006 / 변형 5건 |
| TC-226 | 조회할 ID가 없으면 API를 부르지 않고 쿼터도 쓰지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_fetch_videos_empty_makes_no_call` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-006, SEC-002 |
| TC-227 | 응답을 videos 행으로 정규화한다(한글 제목·설명, 카테고리, 공개 상태, 아동용, 길이, 조회 시각). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_fetch_videos_normalizes_korean_row` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-006, SEC-018 |
| TC-228 | ISO8601 길이 파싱 경계값(PT1H2M3S, PT45S, P0D)과 깨진 값은 None이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_parse_duration_boundaries` | docstring의 기대 결과가 모두 충족 | Pass(20건) | Pass | FR-006 / 변형 20건 |
| TC-229 | 설명은 앞 500자만 저장되고(전체는 snippet_json에 보존) 깨진 길이는 NULL이어도 영상은 저장된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_description_excerpt_is_first_500_chars_and_bad_duration_is_null` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-006, NFR-009 |
| TC-230 | status의 공개 상태와 madeForKids(true→1, false→0, 없거나 불린이 아님→NULL) 변환. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_privacy_and_kids_mapping` | docstring의 기대 결과가 모두 충족 | Pass(6건) | Pass | FR-006 / 변형 6건 |
| TC-231 | 응답의 items가 없거나 목록이 아니면 ApiError이고 DB에 저장하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_fetch_videos_items_contract_violation` | docstring의 기대 결과가 모두 충족 | Pass(4건) | Pass | FR-006, NFR-007 / 변형 4건 |
| TC-232 | id·제목이 없거나 요청하지 않은 ID·중복 항목은 건너뛰어 개수를 세고 정상 항목만 저장한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_fetch_videos_skips_malformed_items_and_counts` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-006 |
| TC-233 | 같은 영상을 다시 조회하면 행이 늘지 않고 제목·조회 시각이 최신으로 갱신된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_fetch_videos_upserts_existing_row` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-006 |
| TC-234 | SQL 조각·ANSI 이스케이프가 든 제목도 값 그대로 저장되고 테이블은 멀쩡하다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_malicious_title_is_stored_as_plain_value` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-018, SEC-019 |
| TC-235 | 형식이 틀린 영상 ID가 하나라도 있으면 InputError이고 API를 전혀 부르지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_fetch_videos_rejects_invalid_ids` | docstring의 기대 결과가 모두 충족 | Pass(7건) | Pass | FR-006, SEC-002 / 변형 7건 |
| TC-236 | 요청 ID 중복은 한 번만 조회해 쿼터를 아낀다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_fetch_videos_dedupes_requested_ids` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-006, SEC-002 |
| TC-240 | 지표 조회 요청 모양(채널·기간·차원·지표·필터)과 metrics_snapshots 저장(단계, 출처 api, 기간, 값, 원본)을 확인한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_fetch_metrics_saves_snapshot` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007, SEC-002 |
| TC-241 | 노출수·CTR 지표가 400으로 거부되면 views,estimatedMinutesWatched만으로 재시도하고 impressions_available=False로 알린다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_fetch_metrics_falls_back_when_impressions_rejected` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007, SEC-002 |
| TC-242 | 400이 아닌 오류(쿼터·권한·404·5xx)는 기본 지표로 폴백하지 않고 그대로 변환된 오류를 낸다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_fetch_metrics_no_fallback_except_400` | docstring의 기대 결과가 모두 충족 | Pass(4건) | Pass | FR-007 / 변형 4건 |
| TC-243 | 잘못된 단계·날짜 순서·날짜 형식·영상 ID는 InputError이고 API를 부르지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_fetch_metrics_input_validation` | docstring의 기대 결과가 모두 충족 | Pass(4건) | Pass | FR-007, SEC-002 / 변형 4건 |
| TC-244 | 지표 응답의 열 머리글이 없거나 video 열이 없거나 rows가 목록이 아니면 ApiError이고 저장하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_fetch_metrics_contract_violation` | docstring의 기대 결과가 모두 충족 | Pass(7건) | Pass | FR-007, NFR-007 / 변형 7건 |
| TC-245 | 열 수가 다른 행·요청하지 않은 영상·중복 행은 건너뛰고, 지표가 없는 영상은 missing으로 센다. 숫자가 아닌 값은 NULL. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_fetch_metrics_skips_bad_rows_and_counts_missing` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007 |
| TC-246 | rows가 없는 응답(기간 내 데이터 없음)은 오류가 아니라 missing으로 센다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_fetch_metrics_no_rows_means_no_data` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007 |
| TC-247 | 지표 조회도 50개씩 나누고, 첫 배치에서 폴백이 일어나면 이후 배치는 거부될 지표를 다시 시도하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_fetch_metrics_batches_ids_and_keeps_fallback_for_later_batches` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007, SEC-002 |
| TC-250 | 403 quotaExceeded/dailyLimitExceeded는 QuotaError(YT-300)로 바뀌고 재시도 0회이며 차감은 유지된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_quota_exceeded_http_error_is_quota_error_without_retry` | docstring의 기대 결과가 모두 충족 | Pass(2건) | Pass | NFR-003, SEC-002, SEC-003 / 변형 2건 |
| TC-251 | 401과 쿼터가 아닌 403은 AuthError(YT-400)로 바뀌고 재시도 0회이며 재로그인을 안내한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_auth_http_error_is_auth_error_without_retry` | docstring의 기대 결과가 모두 충족 | Pass(4건) | Pass | FR-016, NFR-007, SEC-003 / 변형 4건 |
| TC-252 | 503 뒤 성공하면 1초 대기 후 재시도해 결과를 얻고, 시도마다 쿼터를 예약한다(failed 1 + ok 1). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_503_then_success_retries_once_and_charges_both_attempts` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-004, SEC-002, SEC-003 |
| TC-253 | 503이 계속되면 최대 2회 재시도(총 3회, 대기 1초·2초) 뒤 재시도 가능 표시의 ApiError로 끝난다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_persistent_503_stops_after_two_retries` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-004, SEC-003 |
| TC-254 | 404 같은 그 밖의 4xx는 재시도하지 않는 ApiError(retryable=False)이고 호출은 1회뿐이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_404_is_non_retryable_api_error` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-004, SEC-003 |
| TC-255 | 429·5xx·연결 끊김·시간 초과·DNS 실패는 재시도 가능 ApiError로 바뀌어 총 3회 시도한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_transient_failures_are_retryable` | docstring의 기대 결과가 모두 충족 | Pass(6건) | Pass | NFR-004, SEC-003 / 변형 6건 |
| TC-256 | 변환된 오류의 메시지·다음 할 일·원인·문자열 표현 어디에도 응답 본문, 요청 주소의 키, 토큰이 없다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_error_messages_never_include_body_or_token` | docstring의 기대 결과가 모두 충족 | Pass(6건) | Pass | NFR-007, SEC-008 / 변형 6건 |
| TC-257 | 로컬 쿼터 상한에 닿으면 API를 부르기 전에 QuotaError로 막고 이후 호출은 0회이다(선예약). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_local_quota_exhaustion_blocks_api_call` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-015, NFR-003, SEC-002 |
| TC-258 | 오늘 남은 쿼터가 비용보다 적으면 첫 호출부터 막힌다(API 호출 0회, DB 불변). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_zero_quota_blocks_even_first_call` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-015, SEC-002 |
| TC-259 | 두 번째 배치가 계속 실패해도 첫 배치 저장분은 남고, 실패한 시도의 쿼터 차감도 유지된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_failure_in_later_batch_keeps_earlier_batch_and_charges` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-008, FR-006 |
| TC-260 | 호출 중 사용자가 중단(Ctrl+C)해도 예약은 failed로 표시돼 차감이 남고 예외는 그대로 전달된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_keyboard_interrupt_marks_reservation_failed` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-008, SEC-002 |
| TC-261 | 응답이 객체가 아니면 ApiError로 처리하고 저장하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_non_dict_response_is_contract_error` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-006, NFR-007 |
| TC-262 | 조회 모듈 소스에 .update( .insert( .delete( 같은 쓰기 호출과 쓰기 토큰 로드, 웹 접근 코드가 없다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_source_has_no_write_api_calls` | docstring의 기대 결과가 모두 충족 | Pass(3건) | Pass | FR-006, SEC-001, SEC-007 / 변형 3건 |
| TC-263 | 가짜 서비스는 읽기 메서드만 가지므로, 리더가 쓰기 메서드를 부르면 테스트가 실패한다(그 보호 장치 자체를 확인). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_fake_service_exposes_only_read_methods` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001 |
| TC-264 | build_services가 YouTube v3와 Analytics v2를 자격 증명과 함께, 디스커버리 캐시 없이 만든다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_build_services_uses_pinned_versions_without_discovery_cache` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-006, FR-007 |
| TC-265 | 본문이 JSON이 아니거나 reason이 이상해도 오류 변환은 상태 코드만 담아 정상 동작한다(본문은 버림). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_unparseable_error_body_gives_status_only_cause` | docstring의 기대 결과가 모두 충족 | Pass(5건) | Pass | NFR-007, SEC-008 / 변형 5건 |
| TC-266 | 예상 밖의 예외(ValueError)는 변환·재시도 없이 그대로 전달되고 예약은 failed로 남는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_unknown_exception_propagates_without_retry_and_charges` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-008, SEC-003 |
| TC-267 | 지표 기간은 date·datetime 객체로도 줄 수 있고 ISO 날짜 문자열로 요청된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_fetch_metrics_accepts_date_objects` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007 |
| TC-268 | 영상·지표 저장 중 DB 오류는 한국어 DatabaseError(YT-200)로 바뀐다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_database_write_failure_becomes_database_error` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-006, FR-007, NFR-007 |
| TC-270 | fetch에 옵션이 없으면 종료 코드 1과 안내(--all/--video/--metrics)를 내고 API 준비도 하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_cli_no_option_is_input_error` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-002, NFR-007 |
| TC-271 | 잘못된 영상 ID는 종료 코드 1로 거부하고 로그인·API 준비 없이 끝난다(한 개라도 틀리면 전체 거부). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_cli_rejects_invalid_video_id` | docstring의 기대 결과가 모두 충족 | Pass(6건) | Pass | FR-006, SEC-011 / 변형 6건 |
| TC-272 | --all과 --video를 함께 쓰면 사용법 오류(종료 코드 2)이고 아무것도 조회하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_cli_all_and_video_are_exclusive` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-002 |
| TC-273 | --days가 1~365 밖이거나 숫자가 아니면 사용법 오류(종료 코드 2)이다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_cli_days_range` | docstring의 기대 결과가 모두 충족 | Pass(5건) | Pass | FR-007 / 변형 5건 |
| TC-274 | --phase는 before/after/periodic만 받는다(그 밖의 값은 종료 코드 2). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_cli_invalid_phase` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007 |
| TC-275 | fetch --all이 영상·공개 구분·아동용·쿼터 사용량·면책 문구를 출력하고 DB에 저장하며 실행 기록을 남긴다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_cli_all_prints_scr007_summary` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-006, FR-015, POL-002, SCR-007 |
| TC-276 | --video를 여러 번 주면 그 영상만 조회하고 채널 목록 API는 부르지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_cli_video_option_repeated_fetches_only_those` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-006 |
| TC-277 | --metrics 단독은 저장된 영상만 대상으로 영상 API 없이 지표를 모으고, 기간(어제까지 N일)·단계가 요청에 반영된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_cli_metrics_only_uses_stored_videos_and_period` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007, SCR-007 |
| TC-278 | --all --metrics는 기본 단계 periodic, 기본 28일 기간으로 방금 조회한 영상의 지표를 모은다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_cli_metrics_default_phase_and_days` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007 |
| TC-279 | 저장된 영상이 없을 때 --metrics 단독은 종료 코드 1과 `fetch --all` 안내이며 API를 부르지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_cli_metrics_without_stored_videos_is_error` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007, NFR-007 |
| TC-280 | 노출수·CTR 지표가 거부돼 폴백되면 종료 코드 0으로 끝나되 Studio CSV 가져오기(report --import-csv)를 안내한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_cli_metrics_fallback_guides_csv_import` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007, SCR-007 |
| TC-281 | 제목의 ANSI 이스케이프·줄바꿈은 화면에 그대로 나오지 않는다(DB에는 값 그대로 저장). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_cli_sanitizes_control_characters_in_titles` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-019 |
| TC-282 | --plain이면 표 대신 `항목: 값` 목록으로 영상을 출력한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_cli_plain_mode_lists_items` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007, SCR-007 |
| TC-283 | 쿼터 상한에 닿으면 종료 코드 1과 초기화 시각 안내를 내고, 그 뒤 API는 부르지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_cli_quota_exhausted_stops_with_reset_guidance` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-015, NFR-003, SEC-002 |
| TC-284 | 오늘 사용량이 상한의 80%를 넘으면 출력에 쿼터 경고가 붙는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_cli_warns_at_80_percent` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-003, SEC-002 |
| TC-285 | 사용량이 80% 미만이면 쿼터 경고 줄이 없다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_cli_no_warning_below_threshold` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-003 |
| TC-286 | 실제 make_reader는 읽기 토큰만 불러 서비스를 만들고 쓰기 토큰은 요청하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_make_reader_loads_read_token_only` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-016, SEC-001, SEC-015 |
| TC-287 | 읽기 로그인이 없으면 종료 코드 1과 `auth --read` 안내이며 DB에 영상이 생기지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_make_reader_without_login_guides_auth` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-016, NFR-007 |
| TC-288 | --help에 fetch 명령이 자동 탐색돼 나타나고 fetch --help에 옵션 설명이 있다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_fetch_is_listed_in_help_with_options` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-003, EVT-002 |
| TC-289 | 영상이 20개를 넘으면 앞 20개만 표로 보이고 나머지 개수를 알리며, 건너뛴 항목·응답에 없던 영상 수를 경고한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_cli_long_list_is_truncated_and_warnings_shown` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-006, SCR-007 |
| TC-290 | 지표 응답에서 건너뛴 항목이 있으면 개수를 경고로 알린다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_read.py::test_cli_metrics_skipped_rows_reported` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007, SCR-007 |

### 4-1. 인수 조건 ↔ 테스트 케이스 추적
| AC | 인수 조건 | 연결 TC | 판정 |
|---|---|---|---|
| AC-01 | 호출 전 선예약, 상한 직전 허용·초과 시 QuotaError이고 DB 불변 | TC-200, TC-201, TC-202, TC-203, TC-212, TC-257, TC-258 | 충족 |
| AC-02 | 호출 실패·중단에도 차감 유지, ok/failed 기록 | TC-204, TC-205, TC-252, TC-253, TC-259, TC-260, TC-266 | 충족 |
| AC-03 | 태평양 날짜 경계(서머타임 포함)와 날짜별 사용량 분리 | TC-207, TC-208 | 충족 |
| AC-04 | 사용량이 warn_ratio 이상이면 경고 | TC-209, TC-210, TC-284, TC-285 | 충족 |
| AC-05 | units·호출 이름 검증, SQL 값 바인딩, DB 오류 변환 | TC-206, TC-211, TC-213, TC-214 | 충족 |
| AC-06 | 채널 업로드 목록 전 페이지 순회와 응답 계약 검증, 토큰 반복 차단 | TC-220, TC-221, TC-222, TC-223 | 충족 |
| AC-07 | 영상 조회 50개 배치, 중복 제거, 잘못된 ID 사전 거부 | TC-224, TC-225, TC-226, TC-235, TC-236 | 충족 |
| AC-08 | videos 정규화·upsert, 계약 위반·결측 건너뛰기 | TC-227, TC-228, TC-229, TC-230, TC-231, TC-232, TC-233, TC-234, TC-261, TC-268 | 충족 |
| AC-09 | metrics_snapshots 저장과 노출수·CTR 거부 시 폴백 | TC-240, TC-241, TC-242, TC-243, TC-244, TC-245, TC-246, TC-247, TC-267, TC-280, TC-290 | 충족 |
| AC-10 | HttpError 변환 5종과 재시도 규칙 | TC-250, TC-251, TC-252, TC-253, TC-254, TC-255 | 충족 |
| AC-11 | 오류 메시지에 본문·키·토큰 없음 | TC-256, TC-265 | 충족 |
| AC-12 | 쓰기 API 호출 코드·쓰기 토큰 부재 | TC-262, TC-263, TC-264, TC-286 | 충족 |
| AC-13 | fetch 옵션 검증 | TC-270, TC-271, TC-272, TC-273, TC-274 | 충족 |
| AC-14 | SCR-007 출력, 제어문자 제거, --plain, --metrics 대상 선택 | TC-275, TC-276, TC-277, TC-278, TC-279, TC-281, TC-282, TC-288, TC-289 | 충족 |
| AC-15 | 읽기 토큰만 사용, 로그인 없으면 안내, 쿼터 소진 시 종료 코드 1 | TC-283, TC-286, TC-287 | 충족 |

- 인수 조건에 연결되지 않은 TC(추가 안전 케이스): 없음
- 정상 경로, 경계값(날짜 경계·상한·빈 입력), 예외 입력(잘못된 형식·악성 문자열), 권한 경계를 포함했다.

## 5. 커버리지
- 전체 지표: 이 단위 모듈(youtube_title.quota, youtube_title.youtube_read, youtube_title.commands.fetch)의 줄+분기 합산 **99%** (pytest-cov, `--cov-branch`)
- 회귀(이전 단위 산출물을 깨뜨리지 않음): 전체 테스트 스위트 `441 passed, 1 skipped` (통과)
- 호환 실행: 3.11 → 178 passed / 3.13 → 178 passed / 3.12(주) → 178 passed
- 커버되지 않은 부분과 사유:
  - src/youtube_title/commands/fetch.py      92      0     30      1    99%   98->103
  - src/youtube_title/quota.py               56      0     10      0   100%
  - src/youtube_title/youtube_read.py       272      1     92      1    99%   110
  - 이 단위 모듈의 줄·분기 커버리지는 위 수치. 미커버 줄은 도달 불가 방어 코드와 영상 0개 분기.

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 내용 |
|----|------|-----------|--------|------|-----------|
| DEF-6-018 | [테스트 결함] remaining()의 하한(0) 검증 없음 — 상한을 낮춘 경우 음수 허용 변이를 놓침 | 변이 점검 | Low | Fixed | TC-214 추가 |

- 서브에이전트가 구현 중 발견·수정한 사항은 unit-2-note에 기록. 오케스트레이터 검증에서 Open 결함 0건이어야 PASS.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트: `.harness-tmp/junit_06.xml`, `.harness-tmp/junit_py311.xml`, `.harness-tmp/junit_py313.xml`, `.harness-tmp/junit_regress.xml`, `.harness-tmp/venv_py311`, `.harness-tmp/venv_py312`, `.harness-tmp/venv_py313` (+ 변이 점검용 임시 사본 `.harness-tmp/mut_06/`, 편집 설치로 생긴 `src/*.egg-info`, 캐시 `__pycache__`/`.coverage`)
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예 [ ] 아니오 — 예외: 편집 설치가 `src/youtube_title.egg-info/`를 만들고 파이썬이 `__pycache__`를 만든다(둘 다 `.gitignore` 대상이며 정리 대상에 포함)
- 정리(삭제) 완료 여부: 예. 결과서 생성 스크립트가 `.harness-tmp/`, `data/`, `.coverage`, `src/*.egg-info`, `__pycache__`를 삭제했다
- **정리 후 점검: `git status`는 실행하지 않았다** — 프로젝트 지시(프롬프트 §1)로 git 명령 전면 금지(DEC-006). 대신 파일시스템 점검 결과를 첨부한다: 잔여물 없음 (점검 목록: .harness-tmp, .venv*, venv, *.egg-info, .pytest_cache, .coverage*, __pycache__, data)
- 병렬 실행이었다면: 해당 없음(단독 실행)
- 이번 테스트 도중 강제 중단: [x] 없음 / [ ] 있음

## 8. 리스크 및 잔존 이슈
- **미검증(PASS로 세지 않음)**: 실제 구글 응답 모양, Analytics 지표 이름·CTR 단위·영상 필터 상한, 쿼터 비용 수치
- 열린 질문: read_cost/analytics_cost 0 설정 처리, 일시적 403 안내 문구, report --import-csv는 WU-6에서 제공

## 9. 결론 및 판정
- 판정: **PASS**
- 근거: 실패 TC 0건, 미수행 TC 0건(-), AC↔TC 추적 문제 0건, 정적 분석(pyflakes) 통과, 변이 점검 32/32 잡아냄, Open 결함 0건
- WU-4가 `videos`·`metrics_snapshots`·`QuotaManager`를 입력으로 쓸 수 있다.

## 10. 내부 검증 (최소 2회)
- 1차(작성자 관점): 서브에이전트 구현·자체 점검, AC↔TC 추적
- 2차(독립 심사자 관점): 오케스트레이터가 변이 점검으로 안전 로직을 일부러 망가뜨림. 결과는 부록 A
- 3차: 결함 0건 확인
- 검증 로그 파일 경로: `docs/harness/verify-log_unit-2-test.md`

### 부록 A. 변이 점검(코드를 일부러 망가뜨려 테스트가 실패하는지 확인)
| 변이 | 파일 | 결과 |
|---|---|---|
| 상한 경계(<=→<) | `quota.py` | 잡아냄(테스트 실패) |
| 선예약 합계 날짜 조건 제거 | `quota.py` | 잡아냄(테스트 실패) |
| 실패 시 차감 취소 | `quota.py` | 잡아냄(테스트 실패) |
| 경고 경계(>=→>) | `quota.py` | 잡아냄(테스트 실패) |
| units 검증 제거 | `quota.py` | 잡아냄(테스트 실패) |
| 호출 이름 검증 제거 | `quota.py` | 잡아냄(테스트 실패) |
| 남은 양 음수 허용 | `quota.py` | 잡아냄(테스트 실패) |
| 날짜 기준 UTC로 변경 | `quota.py` | 잡아냄(테스트 실패) |
| 이중 mark 허용 | `quota.py` | 잡아냄(테스트 실패) |
| 호출 전 예약 생략 | `youtube_read.py` | 잡아냄(테스트 실패) |
| 실패 mark 생략 | `youtube_read.py` | 잡아냄(테스트 실패) |
| 쿼터 사유 구분 제거 | `youtube_read.py` | 잡아냄(테스트 실패) |
| 401/403 인증 변환 제거 | `youtube_read.py` | 잡아냄(테스트 실패) |
| 5xx 재시도 표시 제거 | `youtube_read.py` | 잡아냄(테스트 실패) |
| 오류에 원본 예외 연결 | `youtube_read.py` | 잡아냄(테스트 실패) |
| 배치 크기 변경 | `youtube_read.py` | 잡아냄(테스트 실패) |
| 영상 ID 형식 검사 제거 | `youtube_read.py` | 잡아냄(테스트 실패) |
| 중복 ID 제거 생략 | `youtube_read.py` | 잡아냄(테스트 실패) |
| 페이지 토큰 반복 검사 제거 | `youtube_read.py` | 잡아냄(테스트 실패) |
| 요청 안 한 ID 건너뛰기 제거 | `youtube_read.py` | 잡아냄(테스트 실패) |
| 설명 500자 제한 제거 | `youtube_read.py` | 잡아냄(테스트 실패) |
| 지표 폴백 제거 | `youtube_read.py` | 잡아냄(테스트 실패) |
| 지표 열 불일치 행 건너뛰기 제거 | `youtube_read.py` | 잡아냄(테스트 실패) |
| 지표 단계 검증 제거 | `youtube_read.py` | 잡아냄(테스트 실패) |
| 기간 순서 검사 제거 | `youtube_read.py` | 잡아냄(테스트 실패) |
| bool을 숫자로 허용 | `youtube_read.py` | 잡아냄(테스트 실패) |
| 기간 시작일 계산 변경 | `commands/fetch.py` | 잡아냄(테스트 실패) |
| 종료일을 오늘로 변경 | `commands/fetch.py` | 잡아냄(테스트 실패) |
| 옵션 없음 검사 제거 | `commands/fetch.py` | 잡아냄(테스트 실패) |
| 영상 ID 형식 검사 제거(명령) | `commands/fetch.py` | 잡아냄(테스트 실패) |
| 쿼터 경고 출력 제거 | `commands/fetch.py` | 잡아냄(테스트 실패) |
| 일수 범위 검사 제거 | `commands/fetch.py` | 잡아냄(테스트 실패) |

### 부록 B. 공유 문서 갱신
`traceability.md`의 단위테스트 컬럼과 구현 상태를 스크립트로 갱신했다(통과한 TC만 연결).
