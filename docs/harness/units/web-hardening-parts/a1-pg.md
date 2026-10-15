# a1: PostgreSQL 전용 시험 실제 실행 결과 (2026-10-13)

한 줄 결론: 첫 실행은 156개 중 통과 67 / 실패 4 / 오류 85 (환경 문제: 시험 DB 인코딩이 SQL_ASCII). DB 2개를 UTF8로 다시 만든 뒤 재실행에서 156개 모두 통과(실패 0, 오류 0, 건너뜀 0).

## 대상
YTWEB_TEST_PG_URL 을 쓰는 시험 파일 7개 (pg_url 픽스처, tests/conftest.py:117):
- 묶음1 (ytweb_test_a): tests/core/test_postgres.py, tests/domain/test_postgres.py, tests/domain/test_wbx_postgres.py, tests/verify_fix_be/test_vfb_05_input_caps.py → 96개
- 묶음2 (ytweb_test_b): tests/verify_m23/test_vm_09_postgres.py, tests/verify_wa/test_va_07_postgres.py, tests/verify_wb/test_vb_08_pg_concurrency.py → 60개

## 실행 명령 (web/backend 에서, 두 묶음 병렬)
`YTWEB_TEST_PG_URL=postgresql+psycopg://postgres@127.0.0.1:54329/ytweb_test_{a|b} ../../.harness-tmp/be/bin/python -m pytest -q -rs -p no:cacheprovider --junitxml=../../.harness-tmp/results/pg-{1|2}.xml <파일들>`
시작 01:22:18 UTC. 첫 실행 약 30초(01:22:18~01:22:48), 재실행 23초(01:23:02~01:23:25). 시험 시간: 묶음1 19.1초, 묶음2 21.2초. 전체 약 1분 10초.

## 첫 실행 결과 (보존: .harness-tmp/results/first/)
| 묶음 | 시험 수 | 통과 | 실패 | 오류 | 건너뜀 |
|---|---|---|---|---|---|
| 1 (a) | 96 | 67 | 2 | 27 | 0 |
| 2 (b) | 60 | 0 | 2 | 58 | 0 |

(묶음1 통과 수는 junit의 tests-failures-errors 계산값이며 직접 세지 않음. 묶음2는 60-2-58=0.)

실패(failure) 4건:
| 시험 | 오류 첫 줄 |
|---|---|
| tests/core/test_postgres.py::test_app_role_cannot_update_or_delete_audit_log | TypeError: cannot use a string pattern on a bytes-like object |
| tests/core/test_postgres.py::test_migration_works_without_app_role | 같음 |
| tests/verify_wa/test_va_07_postgres.py::test_upgrade_existing_0001_database_revokes_version_table_dml | 같음 |
| tests/verify_wa/test_va_07_postgres.py::test_upgrade_without_app_role_still_works_and_offline_render_has_revoke | 같음 |

오류(error) 85건: 모두 setup 단계에서 같은 TypeError.

## 원인 분석: 환경 문제 (제품 결함·시험 결함 아님)
- 임시 PostgreSQL의 ytweb_test_a~e DB 인코딩이 SQL_ASCII(`select ... pg_encoding_to_char`로 확인). SQL_ASCII DB에서는 psycopg 3가 `select version()`을 bytes로 돌려주고, SQLAlchemy 접속 초기화(`_get_server_version_info`, re.match)가 TypeError로 죽음. psycopg 단독 접속으로도 bytes 반환을 재현함.
- 소스·시험 파일은 수정하지 않음.

## 조치와 재실행 결과
- 조치: 내 몫인 ytweb_test_a, ytweb_test_b 만 DROP 후 `CREATE DATABASE ... ENCODING 'UTF8' TEMPLATE template0 LC_COLLATE 'C.UTF-8' LC_CTYPE 'C.UTF-8'` 로 재생성(둘 다 UTF8 확인). 같은 방식이 필요한 ytweb_test_c, d, e 는 건드리지 않음(아직 SQL_ASCII → 그 DB를 쓰는 다른 에이전트의 PG 시험도 같은 TypeError가 날 것).
- 재실행: 묶음1 96개 통과 / 실패 0 / 오류 0 / 건너뜀 0. 묶음2 60개 통과 / 실패 0 / 오류 0 / 건너뜀 0. 합계 156/156 통과.

## 이전 건너뜀 104개와의 관계
- 이전에 "건너뜀 104개"의 정확한 목록은 확인 못 함(이번에 전체 시험을 PG 없이 다시 돌려 대조하지 않음). 이번 PG 시험 파일 7개 전체는 156개이며, 재실행에서 모두 실제로 실행되어 통과했다. 156 중 일부는 PG 없이도 도는 시험일 수 있어, "104개 중 통과 몇 개"를 정확히 분리한 숫자는 낼 수 없음(확인 못 함). 104개가 모두 이 7개 파일에 속한다면 104개 전부 통과로 볼 수 있으나 이는 가정임.
- 남은 skip: 없음(건너뜀 0).

## 한계
- 이 7개 파일 밖에도 pg_url 을 쓰는 시험이 있는지는 grep(`pg_url|YTWEB_TEST_PG_URL`, tests/ 의 test_*.py)으로만 확인함. run_mut.py, mutate.py 등 변이 점검 도구는 실행하지 않음.
- 전체 백엔드 스위트를 PG 환경변수와 함께 돌리지 않음(범위 밖).
- Ubuntu 패키지 PostgreSQL 16.15 한 개 환경, 실제 docker 이미지 postgres 와의 차이는 확인 못 함.
