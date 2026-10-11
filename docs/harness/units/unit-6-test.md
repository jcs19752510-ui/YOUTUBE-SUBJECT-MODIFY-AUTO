# 테스트 결과서 — WU-6 성과 리포트·CSV 가져오기 (6단계 단위 테스트)

## 1. 개요
- 테스트 대상: WU-6 성과 리포트·CSV 가져오기 (`report, csv_import, commands/report`)
- 테스트 유형: 단위
- 적용 Tier: Standard (규칙 B 원문: 최소 2회)
- 적용 속도 트랙: L3
- 병렬 실행 정보: 단독 실행(독립 검증 단계)
- 테스트 목적: `unit-6-note.md`의 인수 조건(AC)을 테스트로 증명하고 안전 로직의 회귀를 막는다
- 관련 산출물: `docs/yt/DESIGN.md`, `docs/harness/units/unit-6-note.md`, `docs/yt/02_planning.md`
- 테스트 수행자(에이전트): 오케스트레이터(06단계 역할 직접 수행)
- 테스트 일시: 2026-10-10

## 2. 테스트 범위 및 제외 범위
- 범위(In-Scope): Studio CSV 가져오기(인코딩·머리글 별칭·숫자 파싱·불량 행 처리·한 트랜잭션 저장), 변경 전후 비교 계산(데이터 부족 판정·하루 평균), `report` 명령과 면책 문구
- 제외 범위(Out-of-Scope) 및 사유: 실제 Studio 내보내기 CSV 형식(합성 샘플만 사용), API 경로 CTR 단위와 CSV 단위의 일치([확인 필요]), Windows 콘솔·CP949 실파일

## 3. 테스트 환경
- 실행 환경: Linux, Python 3.12.3 (주 실행) · 3.11 · 3.13 (호환 확인), pytest, pytest-cov. 가상환경은 `.harness-tmp/` 아래에만 생성
- 테스트 데이터: 임시 폴더의 가짜 설정·DB·후보, 가짜 토큰 문자열(실제 비밀 아님). **실제 YouTube API는 호출하지 않음**
- 전제 조건: 이전 단위 WU-2, WU-4(스키마 참조) PASS

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고(검증하는 ID) |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-600 | 영문 Studio 머리글(Content/Views/Watch time (hours)/Impressions/CTR)을 인식하고 합계 행·모르는 열은 건너뛰며 시간은 분으로 바꾼다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_english_studio_headers_are_recognized` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-203, FR-007 |
| TC-601 | 한글 머리글(콘텐츠/조회수/시청 시간(단위: 시간)/노출수/노출 클릭률(%))을 인식한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_korean_studio_headers_are_recognized` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-203, FR-007 |
| TC-602 | 대소문자·공백·밑줄 같은 표기 차이가 있어도 별칭으로 인식한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_header_alias_spelling_variants` | docstring의 기대 결과가 모두 충족 | Pass(6건) | Pass | EVT-203 / 변형 6건 |
| TC-603 | 분 단위 열과 시간 단위 열이 함께 있으면 분 단위를 쓰고 시간 열은 무시한다(단위를 추측하지 않음). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_minutes_header_preferred_over_hours` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007 |
| TC-604 | 단위를 알 수 없는 `시청 시간` 단독 열은 추측하지 않고 무시한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_bare_watch_time_column_is_not_guessed` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007 |
| TC-605 | UTF-8 BOM(utf-8-sig)이 붙은 파일도 머리글을 올바르게 읽는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_utf8_bom_is_accepted` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-203, NFR-002 |
| TC-606 | 엑셀 한글 저장(CP949)과 UTF-16(BOM) 파일도 읽는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_cp949_and_utf16_files_are_accepted` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-002 |
| TC-607 | 인코딩을 알 수 없거나 바이너리인 파일은 안내와 함께 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_undecodable_and_binary_files_rejected` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-016 |
| TC-608 | 쉼표 천단위·퍼센트·빈 값 표기(-, N/A)를 올바르게 읽는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_parse_number_accepts_common_formats` | docstring의 기대 결과가 모두 충족 | Pass(19건) | Pass | FR-007 / 변형 19건 |
| TC-609 | 수식처럼 보이는 값·지수 표기·NaN·무한대·범위 밖 값은 읽지 않고 이유를 돌려준다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_parse_number_rejects_formulas_and_garbage` | docstring의 기대 결과가 모두 충족 | Pass(17건) | Pass | SEC-016 / 변형 17건 |
| TC-610 | 불량 행(영상 ID 형식·숫자 형식·열 개수·지표 없음·중복)은 건너뛰고 이유를 모아 알리며 정상 행은 계속 읽는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_bad_rows_are_skipped_and_reported_together` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007 |
| TC-611 | `=+-@`로 시작하는 문자열은 수식으로 해석되지 않고 값으로만 남으며, 화면용 문자열은 앞에 `'`가 붙고 제어문자가 제거된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_injection_strings_are_values_only_and_neutralized` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-016, SEC-019 |
| TC-612 | 5MB를 넘는 CSV는 읽기 전(파일 크기)·파싱 전(바이트 수) 모두에서 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_file_size_limit_rejected` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-016 |
| TC-613 | stat 이후 파일이 커져도 읽는 양은 상한+1바이트까지만이라 상한 초과로 거부된다(검사-사용 시점 틈 방어). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_file_grows_while_reading_is_still_capped` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-016 |
| TC-614 | 데이터 행이 상한(10,000)을 넘으면 거부하고, 정확히 상한이면 허용한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_row_count_limit_rejected` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-016 |
| TC-615 | 머리글 문제(영상 ID 열 없음 + 지표 열 없음 + 중복 열)를 한 번에 모아 알린다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_header_errors_are_reported_at_once` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007 |
| TC-616 | 오류 메시지에 들어가는 머리글 이름도 정화된다(ANSI 제거, 수식 문자 무력화). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_header_cells_with_control_chars_are_sanitized_in_errors` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-019 |
| TC-617 | 영상 ID 열이 없는 파일은 `--video` 기본 영상으로 한 줄만 가져오고, 둘째 줄부터는 건너뛴다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_no_id_column_requires_single_row_with_default_video` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007 |
| TC-618 | 기본 영상 ID도 형식을 검증한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_default_video_id_is_validated` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-016 |
| TC-619 | 세미콜론·탭으로 구분된 파일도 읽는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_other_delimiters_are_detected` | docstring의 기대 결과가 모두 충족 | Pass(2건) | Pass | EVT-203 / 변형 2건 |
| TC-620 | 빈 파일은 거부하고, 머리글만 있는 파일은 행 0개로 정상 처리한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_empty_and_header_only_files` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007 |
| TC-621 | 필드 하나가 지나치게 큰 CSV는 예외 대신 한국어 안내(InputError)로 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_malformed_csv_oversized_field_is_input_error` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-016 |
| TC-622 | 읽기는 입력 파일을 바꾸지 않는다(내용 해시·수정 시각 동일). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_parse_does_not_modify_input_file` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-016 |
| TC-623 | 상대 경로는 base_dir 기준으로 읽고, .csv가 아니거나 없거나 폴더이면 안내와 함께 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_read_file_resolves_relative_to_base_dir_and_checks_type` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-008, SEC-016 |
| TC-624 | 행을 metrics_snapshots에 source='csv'로 저장하고, 악의적 문자열도 값으로만 들어가 테이블이 유지된다(SQL 바인딩). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_store_rows_saves_csv_source_with_binding` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007, SEC-018 |
| TC-625 | 같은 내용을 다시 가져와도 중복 저장하지 않고(NULL 값 포함), DB에 영상 정보가 없는 영상 수를 센다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_store_rows_is_idempotent_and_counts_unknown_videos` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007 |
| TC-626 | 잘못된 단계·한쪽만 있는 기간·거꾸로 된 기간은 거부하고 DB에 아무것도 쓰지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_store_rows_validates_arguments_and_writes_nothing` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007 |
| TC-627 | 저장 도중 DB 오류가 나면 이미 넣은 행도 취소(전부 또는 전무)하고 한국어 DatabaseError로 알린다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_store_rows_is_atomic_on_db_error` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007 |
| TC-628 | 날짜는 YYYY-MM-DD만 허용하고 없는 날짜·다른 형식·유니코드 숫자는 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_parse_day_validation` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007 |
| TC-629 | CSV 모듈에는 네트워크·코드 실행(eval/exec/pickle 등) 코드가 없다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_module_has_no_network_or_eval` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-007, SEC-016 |
| TC-630 | 자료가 충분하면 하루 평균(노출·조회·시청 시간)과 클릭률의 전후 차이·변화율을 계산한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report.py::test_sufficient_data_compares_per_day_rates` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-018, SCR-008 |
| TC-631 | 전·후 집계 기간 길이가 달라도 하루 평균으로 비교한다(합계 직접 비교 금지). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report.py::test_different_period_lengths_are_normalized_per_day` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-018 |
| TC-632 | 노출수 최소 기준(1,000) 경계: 999 미달, 1,000 충족. 변경 전·후 각각 적용한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report.py::test_min_impressions_boundary_both_sides` | docstring의 기대 결과가 모두 충족 | Pass(4건) | Pass | FR-018 / 변형 4건 |
| TC-633 | 집계 기간 최소 7일 경계: 6일 부족, 7일 충족(양끝 포함 계산). 변경 전·후 각각 적용한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report.py::test_min_period_days_boundary` | docstring의 기대 결과가 모두 충족 | Pass(3건) | Pass | FR-018 / 변형 3건 |
| TC-634 | 변경 전 지표(기준선)가 없으면 '데이터 부족'이며 비교 수치를 만들지 않고 신뢰도 낮음 표시를 켠다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report.py::test_missing_baseline_is_insufficient_not_a_conclusion` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-012, FR-018, SCR-008 |
| TC-635 | 변경 후 지표가 없으면 데이터 부족이며 수집 예정일(변경일 + 평가 기간)을 알려 준다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report.py::test_missing_after_gives_expected_collection_date` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-019, SCR-008 |
| TC-636 | 지표가 하나도 없으면 사유를 한 번에 모두 알린다(기준선 없음 + 변경 후 없음). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report.py::test_no_snapshots_at_all_collects_both_reasons` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SCR-008 |
| TC-637 | 변경 전 자료의 집계 종료일은 변경일보다 앞서야 한다(당일분 제외). 겹치면 기준선으로 쓰지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report.py::test_before_period_must_end_before_change_day` | docstring의 기대 결과가 모두 충족 | Pass(3건) | Pass | FR-018 / 변형 3건 |
| TC-638 | 변경 후 자료의 집계 시작일은 변경일보다 뒤여야 한다. 변경 이전과 겹치면 쓰지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report.py::test_after_period_must_start_after_change_day` | docstring의 기대 결과가 모두 충족 | Pass(3건) | Pass | FR-018 / 변형 3건 |
| TC-639 | 기간 정보가 없으면 수집 시각으로 전·후를 가리되, 기간을 모르므로 데이터 부족으로 처리한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report.py::test_snapshot_without_period_falls_back_to_taken_time_but_is_insufficient` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-018, SEC-016 |
| TC-640 | 노출수가 없으면(API 미제공) 데이터 부족이며 CSV 가져오기를 안내한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report.py::test_missing_impressions_asks_for_csv` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007, FR-018 |
| TC-641 | 거꾸로 된 기간·잘못된 날짜 문자열은 기간 정보 없음으로 처리하고 예외를 내지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report.py::test_reversed_or_garbled_periods_are_unusable` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-018, SEC-016 |
| TC-642 | 같은 단계 자료가 여러 건이면 가장 최근(수집 시각, 번호) 것을 쓰고 알린다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report.py::test_multiple_valid_snapshots_use_latest_and_note_it` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-018 |
| TC-643 | 변경이 여러 번이면 가장 최근 적용을 기준으로 하고, 그 뒤 롤백이 있으면 데이터 부족이다. 이전 롤백은 영향 없음. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report.py::test_several_changes_use_latest_apply_and_rollback_invalidates` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-018, SEC-006 |
| TC-644 | 시각이 같은 변경은 번호 순으로 앞뒤를 가린다(같은 시각이어도 번호가 큰 롤백은 뒤). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report.py::test_same_timestamp_rollback_orders_by_id` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-006 |
| TC-645 | 성공한 적용 기록이 없으면(실패·중단·계획·롤백만) 비교하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report.py::test_no_successful_apply_means_no_comparison` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-010, FR-018 |
| TC-646 | 변경 시각을 해석할 수 없으면 전후를 나눌 수 없어 데이터 부족이다(예외 없음). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report.py::test_unparseable_change_time_is_insufficient` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-018 |
| TC-647 | 변경 전 값이 0이거나 없으면 변화율은 계산하지 않는다(0으로 나누기 없음). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report.py::test_percent_change_is_none_when_baseline_zero_or_missing` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-018 |
| TC-648 | 리포트 계산은 입력(변경·지표 목록)을 바꾸지 않는 순수 함수이며 결과가 항상 같다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report.py::test_build_report_does_not_mutate_inputs` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-018 |
| TC-649 | 면책 문구는 원인 단정 금지와 다른 요인 가능성(시기·노출·A/B)을 담고, 결과 구조에는 '효과 있음' 같은 판정 필드가 없다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report.py::test_disclaimer_texts_forbid_causal_claims` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-018, POL-002, SCR-008 |
| TC-650 | 최소 노출 기준은 설정(cadence.min_impressions_before_rechange), 평가 기간은 sequential_mode.evaluation_window_days에서 가져온다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report.py::test_rules_from_settings` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-014, FR-019 |
| TC-651 | DB 조회는 성공한 변경과 해당 영상의 지표만 시각순으로 읽고, DB를 바꾸지 않으며, 영상 ID에 SQL 조각이 있어도 값으로만 쓴다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report.py::test_load_video_data_reads_only_success_and_is_read_only` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-018, SEC-018 |
| TC-652 | 보고 대상 영상은 성공한 적용 기록이 있는 영상만, 최근 변경 순이다(실패·롤백만 있는 영상 제외). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report.py::test_list_changed_video_ids_orders_by_latest_success_apply` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-018 |
| TC-653 | 리포트 모듈에는 쓰기 SQL(INSERT/UPDATE/DELETE/DROP)·네트워크 코드가 없다(읽기 전용). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report.py::test_module_has_no_write_sql_or_network` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-018, SEC-001, SEC-007 |
| TC-660 | `--import-csv`가 CSV를 metrics_snapshots(source=csv)에 저장하고 단계·기간·인코딩을 포함한 요약을 보여 준다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report_cmd.py::test_import_csv_saves_rows_and_summarizes` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-008, FR-007 |
| TC-661 | fetch의 폴백 안내가 가리키는 `report --import-csv`가 실제로 존재하고 --help에 보인다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report_cmd.py::test_fetch_fallback_guidance_option_exists` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-002, EVT-008, FR-007 |
| TC-662 | 변경 전·후 CSV를 가져온 뒤 `--video` 리포트가 전후 표(변화율)를 보여 주고, 단정 금지 한계 문구와 면책 문구가 항상 나온다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report_cmd.py::test_full_flow_sufficient_data_shows_table_and_disclaimers` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-018, POL-002, SCR-008 |
| TC-663 | 변경 후 자료가 없으면 '데이터 부족'과 사유·수집 예정일만 보여 주고 비교 표·결론을 내지 않지만 면책 문구는 나온다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report_cmd.py::test_insufficient_data_shows_label_reasons_and_no_conclusion` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-018, POL-002, SCR-008 |
| TC-664 | 변경 전 기준선이 없으면 신뢰도 낮음 경고를 표시한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report_cmd.py::test_baseline_missing_warns_low_reliability` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-012, SCR-008 |
| TC-665 | 노출수 경계(설정 최소 기준 1,000회)가 명령 출력에도 반영된다: 하루 평균이 아니라 기간 합계 노출수 기준. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report_cmd.py::test_min_impressions_boundary_through_command` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-014, FR-018 |
| TC-666 | `--plain`은 표 대신 `항목: 값` 목록으로 출력한다(스크린리더 친화). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report_cmd.py::test_plain_mode_lists_items` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SCR-008, UX-007 |
| TC-667 | 불량 행은 건너뛰고 이유별 개수와 예시(줄 번호)를 보여 주며 나머지는 저장한다(종료 코드 0). 예시는 10개까지만 보여 준다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report_cmd.py::test_skipped_rows_reported_with_counts_and_examples` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007 |
| TC-668 | 유효한 행이 하나도 없으면 이유를 보여 주고 오류(종료 코드 1, 다음에 할 일 포함)로 끝나며 DB에 아무것도 저장하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report_cmd.py::test_all_rows_bad_is_error_and_saves_nothing` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007, NFR-007 |
| TC-669 | 같은 CSV를 다시 가져오면 중복 저장하지 않고 알린다. 영상 정보가 DB에 없거나 기간이 없거나 periodic이면 주의 문구를 보여 준다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report_cmd.py::test_reimport_is_idempotent_and_warns` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007 |
| TC-670 | 옵션 없이 실행했는데 변경 기록이 없으면 안내만 하고 정상 종료한다(빈 상태). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report_cmd.py::test_no_args_without_history_guides_user` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007, SCR-008 |
| TC-671 | 옵션 없이 실행하면 제목을 바꾼 영상을 최근 순으로 보여 주고 20개를 넘으면 `외 N개`로 줄인다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report_cmd.py::test_no_args_lists_changed_videos_and_truncates` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-018 |
| TC-672 | 변경 기록이 없는 영상은 비교할 수 없다고 알리고 DB에 제목이 없어도 오류 없이 처리한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report_cmd.py::test_video_without_changes_says_not_comparable` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-018 |
| TC-673 | 잘못된 옵션 조합·영상 ID·날짜·파일은 종료 코드 1과 다음에 할 일을 안내하고 지표를 저장하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report_cmd.py::test_invalid_options_are_input_errors_without_db_write` | docstring의 기대 결과가 모두 충족 | Pass(10건) | Pass | NFR-007, SEC-016 / 변형 10건 |
| TC-674 | `--phase`는 before/after/periodic만 받는다(그 밖의 값은 사용법 오류, 종료 코드 2). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report_cmd.py::test_import_phase_choices_enforced_by_argparse` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-008 |
| TC-675 | CSV 안의 수식 문자열·ANSI 이스케이프는 화면에 날것으로 나오지 않는다(앞에 '가 붙고 제어문자 제거). DB 제목의 ANSI도 정화된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report_cmd.py::test_csv_injection_and_ansi_never_reach_screen_raw` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-016, SEC-019 |
| TC-676 | CSV 셀·DB 문자열의 SQL 조각은 값으로만 쓰여 테이블이 유지된다(영상 ID 형식 검증 + 바인딩). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report_cmd.py::test_sql_injection_like_values_are_bound` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-018 |
| TC-677 | 리포트(가져오기 없음)는 run_logs 외 어떤 테이블도 바꾸지 않는다(읽기 전용). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report_cmd.py::test_report_run_is_read_only_except_run_log` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-018, SEC-001 |
| TC-678 | CSV 가져오기는 metrics_snapshots 외 테이블과 입력 파일을 바꾸지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report_cmd.py::test_import_does_not_modify_other_tables_or_input_file` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-007, SEC-016 |
| TC-679 | CP949(엑셀 한글 저장) CSV도 명령으로 가져오고 인코딩을 알려 준다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report_cmd.py::test_cp949_file_imports_through_command` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-002 |
| TC-680 | 5MB를 넘는 CSV는 명령에서도 거부되고 아무것도 저장하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report_cmd.py::test_oversized_csv_rejected_by_command` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-016 |
| TC-681 | 시각은 한국 시간으로, 해석할 수 없는 값은 정화한 원문으로 표시하고, 숫자 서식은 없음(-)·부호를 처리한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report_cmd.py::test_kst_helper_and_number_formats` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass |  |
| TC-682 | report 명령 모듈에는 네트워크·YouTube 호출 코드가 없다(이 단위는 읽기 전용 + CSV 읽기 + DB 기록). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report_cmd.py::test_module_has_no_network_or_write_api` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001, SEC-007 |
| TC-683 | 인식하지 못한 열(영상 제목·게시 시간 등)은 무시하고 어떤 열을 무시했는지 알려 준다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report_cmd.py::test_unrecognized_columns_are_listed_as_ignored` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-203, FR-007 |
| TC-684 | 영상 ID 열이 없는 CSV(한 영상의 합계 줄)는 `--video ID`로 대상 영상을 지정해 가져온다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report_cmd.py::test_video_option_supplies_id_for_csv_without_id_column` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-008, FR-007 |
| TC-685 | 클릭률 열의 한글/영문 별칭을 모두 인식한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_ctr_header_aliases` | docstring의 기대 결과가 모두 충족 | Pass(6건) | Pass | EVT-203 / 변형 6건 |
| TC-686 | 시작일이 종료일보다 늦은 기간만 있어도 '기간 정보 없음'으로 처리하고 음수·0일 같은 이상한 일수를 이유에 쓰지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_report.py::test_reversed_period_alone_is_reported_as_missing_period_info` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-018, SEC-016 |
| TC-687 | 영상 ID 열 값이 10자·12자이면 형식 오류로 건너뛰고(정확히 11자만 허용) 저장 대상에서 뺀다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_video_id_must_be_exactly_eleven_characters` | docstring의 기대 결과가 모두 충족 | Pass(2건) | Pass | FR-007, SEC-016 / 변형 2건 |
| TC-688 | 크기 검사 뒤에 파일이 커져도 상한(5MB)+1바이트까지만 읽고 거부한다(메모리 보호). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_csv_import.py::test_read_is_capped_even_if_file_grows_after_size_check` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-002, SEC-016 |

### 4-1. 인수 조건 ↔ 테스트 케이스 추적
| AC | 인수 조건 | 연결 TC | 판정 |
|---|---|---|---|
| AC-01 | CSV 크기·행 상한과 인코딩(UTF-8/CP949/UTF-16) 처리 | TC-605, TC-606, TC-607, TC-612, TC-613, TC-614, TC-620, TC-621, TC-623, TC-629, TC-679, TC-680, TC-688 | 충족 |
| AC-02 | 머리글 별칭·단위 추측 금지·머리글 오류 모아서 안내 | TC-600, TC-601, TC-602, TC-603, TC-604, TC-615, TC-616, TC-617, TC-618, TC-619, TC-683, TC-685 | 충족 |
| AC-03 | 숫자 표기와 수식·지수·NaN·범위 밖 값 거부 | TC-608, TC-609, TC-611, TC-675, TC-683 | 충족 |
| AC-04 | 불량 행 건너뛰기와 보고 | TC-600, TC-610, TC-667, TC-668, TC-687 | 충족 |
| AC-05 | metrics_snapshots 저장(바인딩·전부 또는 전무·중복 방지) | TC-624, TC-625, TC-626, TC-627, TC-628, TC-660, TC-669, TC-676, TC-678 | 충족 |
| AC-06 | 전후 비교 계산(하루 평균·변화율) | TC-630, TC-631, TC-647 | 충족 |
| AC-07 | 데이터 부족 판정과 경계값 | TC-632, TC-633, TC-634, TC-635, TC-636, TC-637, TC-638, TC-639, TC-640, TC-641, TC-642, TC-643, TC-644, TC-645, TC-646, TC-650, TC-663, TC-664, TC-665, TC-686 | 충족 |
| AC-08 | 결론 단정 금지·면책 문구 항상 출력 | TC-649, TC-662, TC-663, TC-666, TC-672 | 충족 |
| AC-09 | report 명령 옵션·오류 처리 | TC-660, TC-661, TC-662, TC-666, TC-670, TC-671, TC-672, TC-673, TC-674, TC-681, TC-684 | 충족 |
| AC-10 | 외부 문자열 정화 | TC-616, TC-675 | 충족 |
| AC-11 | 읽기 전용·순수 함수·네트워크 호출 없음 | TC-622, TC-629, TC-648, TC-651, TC-652, TC-653, TC-677, TC-678, TC-682 | 충족 |

- 인수 조건에 연결되지 않은 TC(추가 안전 케이스): 없음
- 정상 경로, 경계값(날짜 경계·상한·빈 입력), 예외 입력(잘못된 형식·악성 문자열), 권한 경계를 포함했다.

## 5. 커버리지
- 전체 지표: 이 단위 모듈(ytitle.report, ytitle.csv_import, ytitle.commands.report)의 줄+분기 합산 **100%** (pytest-cov, `--cov-branch`)
- 회귀(이전 단위 산출물을 깨뜨리지 않음): 전체 테스트 스위트 `1097 passed, 1 skipped` (통과)
- 호환 실행: 3.11 → 147 passed / 3.13 → 147 passed / 3.12(주) → 147 passed
- 커버되지 않은 부분과 사유:
  - src/ytitle/commands/report.py     121      0     52      0   100%
  - src/ytitle/csv_import.py          225      0     88      0   100%
  - src/ytitle/report.py              161      0     36      0   100%
  - 이 단위 모듈의 줄·분기 커버리지는 위 수치.

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 내용 |
|----|------|-----------|--------|------|-----------|
| DEF-6-022 | [테스트 결함] 오케스트레이터 독립 변이 점검 1회차에서 영상 ID 길이(10·12자 허용)·읽기 상한 제거(파일이 커지는 경우)·거꾸로 된 기간의 사유 3곳을 놓침 | 독립 변이 점검(71개 중 68개 적발) | Medium | Fixed | TC-686, TC-687, TC-688 추가 후 재점검 |
| DEF-6-020 | [테스트 결함] 서브에이전트 자체 변이 점검 1회차에서 stat 경계·상한 경계·최신 지표 선택·열 개수 비교 등 7곳을 놓침 | 자체 변이 점검 | Medium | Fixed | TC-612, 609, 642, 610, 684 보강 |

- 서브에이전트가 이 단위 안에서 수정·재검증. 오케스트레이터 독립 변이 점검 결과는 부록 A.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트: `.harness-tmp/junit_06.xml`, `.harness-tmp/junit_py311.xml`, `.harness-tmp/junit_py313.xml`, `.harness-tmp/junit_regress.xml`, `.harness-tmp/venv_py311`, `.harness-tmp/venv_py312`, `.harness-tmp/venv_py313` (+ 변이 점검용 임시 사본 `.harness-tmp/mut_06/`, 편집 설치로 생긴 `src/*.egg-info`, 캐시 `__pycache__`/`.coverage`)
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예 [ ] 아니오 — 예외: 편집 설치가 `src/ytitle.egg-info/`를 만들고 파이썬이 `__pycache__`를 만든다(둘 다 `.gitignore` 대상이며 정리 대상에 포함)
- 정리(삭제) 완료 여부: 예. 결과서 생성 스크립트가 `.harness-tmp/`, `data/`, `.coverage`, `src/*.egg-info`, `__pycache__`를 삭제했다
- **정리 후 점검**: 이 스크립트는 git을 실행하지 않는다(커밋·푸시는 오케스트레이터가 DEC-027에 따라 별도 수행). 파일시스템 점검 결과: 잔여물 없음 (점검 목록: .harness-tmp, .venv*, venv, *.egg-info, .pytest_cache, .coverage*, __pycache__, data)
- 병렬 실행이었다면: 해당 없음(단독 실행)
- 이번 테스트 도중 강제 중단: [x] 없음 / [ ] 있음

## 8. 리스크 및 잔존 이슈
- **미검증(PASS로 세지 않음)**: 실제 Studio CSV 머리글·시청 시간 단위·합계 행, API ctr 단위와 CSV 단위 일치, 노출 1,000회·기간 7일 기준의 채널 적합성
- 열린 질문: unit-6-note 7절의 질문 1~5

## 9. 결론 및 판정
- 판정: **PASS**
- 근거: 실패 TC 0건, 미수행 TC 0건(-), AC↔TC 추적 문제 0건, 정적 분석(pyflakes) 통과, 변이 점검 71/71 잡아냄, Open 결함 0건
- 실제 CSV 샘플과 단위 확인 전까지 가져오기 별칭 표는 가정이다.

## 10. 내부 검증 (최소 2회)
- 1차: 서브에이전트 구현·자체 변이 점검 2회
- 2차(독립 심사자 관점): 오케스트레이터가 별도 변이 점검(코드를 일부러 망가뜨림). 결과는 부록 A
- 3차: 결함 0건 확인
- 검증 로그 파일 경로: `docs/harness/verify-log_unit-6-test.md`

### 부록 A. 변이 점검(코드를 일부러 망가뜨려 테스트가 실패하는지 확인)
| 변이 | 파일 | 결과 |
|---|---|---|
| 크기 상한 경계(>→>=) | `csv_import.py` | 잡아냄(테스트 실패) |
| 행 수 상한 경계(>→>=) | `csv_import.py` | 잡아냄(테스트 실패) |
| 행 수 상한 제거 | `csv_import.py` | 잡아냄(테스트 실패) |
| 바이너리(NUL) 검사 제거 | `csv_import.py` | 잡아냄(테스트 실패) |
| UTF-16 BOM 처리 제거 | `csv_import.py` | 잡아냄(테스트 실패) |
| CP949 폴백 제거 | `csv_import.py` | 잡아냄(테스트 실패) |
| BOM 제거 안 함(utf-8-sig→utf-8) | `csv_import.py` | 잡아냄(테스트 실패) |
| 수식 시작 문자 무력화 제거 | `csv_import.py` | 잡아냄(테스트 실패) |
| 수식 시작 문자에서 @ 누락 | `csv_import.py` | 잡아냄(테스트 실패) |
| 퍼센트 상한 경계(<=→<) | `csv_import.py` | 잡아냄(테스트 실패) |
| 퍼센트 상한 제거 | `csv_import.py` | 잡아냄(테스트 실패) |
| 정수 상한 제거 | `csv_import.py` | 잡아냄(테스트 실패) |
| 분 상한 경계(<=→<) | `csv_import.py` | 잡아냄(테스트 실패) |
| 정수 칸에 소수 허용 | `csv_import.py` | 잡아냄(테스트 실패) |
| % 기호를 정수에도 허용 | `csv_import.py` | 잡아냄(테스트 실패) |
| 숫자 정규식 느슨화(지수 허용) | `csv_import.py` | 잡아냄(테스트 실패) |
| 결측 표기 N/A 미인식 | `csv_import.py` | 잡아냄(테스트 실패) |
| 시간→분 환산 제거 | `csv_import.py` | 잡아냄(테스트 실패) |
| 분·시간 동시에 있을 때 시간 우선 | `csv_import.py` | 잡아냄(테스트 실패) |
| 영상 ID 정규식 길이 | `csv_import.py` | 잡아냄(테스트 실패) |
| 합계 행 건너뜀 제거 | `csv_import.py` | 잡아냄(테스트 실패) |
| 중복 영상 건너뜀 제거 | `csv_import.py` | 잡아냄(테스트 실패) |
| 열 개수 검사 제거 | `csv_import.py` | 잡아냄(테스트 실패) |
| 지표 전부 비어도 저장 | `csv_import.py` | 잡아냄(테스트 실패) |
| ID 열 없을 때 여러 줄 허용 | `csv_import.py` | 잡아냄(테스트 실패) |
| 머리글 오류 무시 | `csv_import.py` | 잡아냄(테스트 실패) |
| 중복 열 오류 제거 | `csv_import.py` | 잡아냄(테스트 실패) |
| 지표 열 없음 오류 제거 | `csv_import.py` | 잡아냄(테스트 실패) |
| 구분자 탭 미지원 | `csv_import.py` | 잡아냄(테스트 실패) |
| 빈 줄 건너뛰기 제거 | `csv_import.py` | 잡아냄(테스트 실패) |
| 파일 확장자 검사 제거 | `csv_import.py` | 잡아냄(테스트 실패) |
| 일반 파일 검사 제거 | `csv_import.py` | 잡아냄(테스트 실패) |
| 읽기 상한 제거 | `csv_import.py` | 잡아냄(테스트 실패) |
| 날짜 정규식 느슨화 | `csv_import.py` | 잡아냄(테스트 실패) |
| 기간 역전 허용 | `csv_import.py` | 잡아냄(테스트 실패) |
| 기간 한쪽만 허용 | `csv_import.py` | 잡아냄(테스트 실패) |
| 단계 값 검사 제거 | `csv_import.py` | 잡아냄(테스트 실패) |
| 중복 저장 방지 제거 | `csv_import.py` | 잡아냄(테스트 실패) |
| 중복 판정에서 단계 제외 | `csv_import.py` | 잡아냄(테스트 실패) |
| 트랜잭션 제거(부분 저장) | `csv_import.py` | 잡아냄(테스트 실패) |
| 알 수 없는 영상 개수 제거 | `csv_import.py` | 잡아냄(테스트 실패) |
| 기준선 종료일 경계(<→<=) | `report.py` | 잡아냄(테스트 실패) |
| 변경 후 시작일 경계(>→>=) | `report.py` | 잡아냄(테스트 실패) |
| 기준선 수집시각 경계(<=→<) | `report.py` | 잡아냄(테스트 실패) |
| 변경 후 수집시각 경계(>=→>) | `report.py` | 잡아냄(테스트 실패) |
| 최소 노출수 경계(<→<=) | `report.py` | 잡아냄(테스트 실패) |
| 노출수 없음 통과 | `report.py` | 잡아냄(테스트 실패) |
| 최소 기간 경계(<→<=) | `report.py` | 잡아냄(테스트 실패) |
| 기간 일수 +1 제거 | `report.py` | 잡아냄(테스트 실패) |
| 기간 역전 허용 | `report.py` | 잡아냄(테스트 실패) |
| 기간 정보 없음 통과 | `report.py` | 잡아냄(테스트 실패) |
| 롤백 이후 검사 제거 | `report.py` | 잡아냄(테스트 실패) |
| 가장 최근 변경 대신 처음 변경 | `report.py` | 잡아냄(테스트 실패) |
| 여러 자료 중 가장 오래된 것 사용 | `report.py` | 잡아냄(테스트 실패) |
| 하루 평균 환산 제거 | `report.py` | 잡아냄(테스트 실패) |
| 클릭률에 하루 평균 적용 | `report.py` | 잡아냄(테스트 실패) |
| 변화율 분모를 변경 후로 | `report.py` | 잡아냄(테스트 실패) |
| 변경 전 0일 때 변화율 계산 | `report.py` | 잡아냄(테스트 실패) |
| 차이 부호 반전 | `report.py` | 잡아냄(테스트 실패) |
| 이유가 있어도 ok 반환 | `report.py` | 잡아냄(테스트 실패) |
| 수집 예정일 계산 변경 | `report.py` | 잡아냄(테스트 실패) |
| 실패한 변경도 포함(SQL) | `report.py` | 잡아냄(테스트 실패) |
| 목록에 롤백 포함 | `report.py` | 잡아냄(테스트 실패) |
| 면책 문구 약화 | `report.py` | 잡아냄(테스트 실패) |
| 명령: 옵션 조합 검사 제거 | `commands/report.py` | 잡아냄(테스트 실패) |
| 명령: 영상 ID 형식 검사 제거 | `commands/report.py` | 잡아냄(테스트 실패) |
| 명령: 가져올 행 없음 오류 제거 | `commands/report.py` | 잡아냄(테스트 실패) |
| 명령: 한계 문구 출력 제거 | `commands/report.py` | 잡아냄(테스트 실패) |
| 명령: 영상 표시 개수 상한 제거 | `commands/report.py` | 잡아냄(테스트 실패) |
| 명령: periodic 경고 제거 | `commands/report.py` | 잡아냄(테스트 실패) |
| 명령: 기간 미지정 경고 제거 | `commands/report.py` | 잡아냄(테스트 실패) |

### 부록 B. 공유 문서 갱신
`traceability.md`의 단위테스트 컬럼과 구현 상태를 스크립트로 갱신했다(통과한 TC만 연결).
