# 백엔드 회귀 재실행 결과서 (요약판) — be-regress-c

기준: 병합 후 작업 트리, 커밋 5cda6c9 이후 HEAD 21175d6 (DEF-BA-001 조치·openapi.json 재생성 포함). 시험·소스 수정 없음, git 쓰기 없음.

## 환경
- 새 임시 PostgreSQL 16.15 클러스터 `.harness-tmp/pg2/data`(UTF8, trust, 포트 54330). 기존 54329 인스턴스는 접속·변경하지 않음.
- 파이썬 `.harness-tmp/venv_06_web_be_b/bin/python -m pytest -q -p no:cacheprovider -rfEs`, `YTWEB_TEST_PG_URL=postgresql+psycopg://postgres@127.0.0.1:54330/ytweb_rN`, 구간별 별도 DB r1~r8, 8개 병렬.
- 확장(pgvector 등) 필요한 시험 없음 확인(설치 목록에 없고 건너뜀도 발생 안 함).

## 첫 실행 (실패 그대로 기록)
- 23:43:37~23:45 UTC. initdb를 로케일 기본값(SQL_ASCII)으로 만들어 서버 버전 문자열이 bytes로 와 SQLAlchemy가 `TypeError: cannot use a string pattern on a bytes-like object`로 PostgreSQL 연결 단계에서 실패. PG 사용 시험이 전부 setup ERROR(core, domain, verify_fix_be, verify_m23, verify_bulk 일부). 원인은 **시험 환경 구성 오류(클러스터 인코딩)**, 제품·일괄 승인 변경과 **무관**. 이 실행 결과는 합격으로 세지 않음.
- 조치: 클러스터를 `-E UTF8 --locale=C.UTF-8`로 다시 만들고 재실행.

## 재실행 (UTF8 클러스터, 01:10:01 UTC 시작, 전 구간 rc=0)
| 구간 | DB | 통과 | 실패 | 건너뜀 | xfail | 소요(date) | 이전 |
|---|---|---|---|---|---|---|---|
| r1 core | r1 | 231 | 0 | 0 | 0 | 32초(01:10:01~01:10:33) | 231 동일 |
| r2 domain(test_bulk_approve 포함) | r2 | 338 | 0 | 0 | 0 | 57초 | 329, +9 |
| r3 tests/test_*.py 5개 | r3 | 66 | 0 | 0 | 0 | 8초 | 66 동일 |
| r4 verify_ai_badge | r4 | 6 | 0 | 0 | 0 | 4초 | 6 동일 |
| r5 verify_fix_be | r5 | 209 | 0 | 0 | 0 | 38초 | 209 동일 |
| r6 verify_m23 | r6 | 397 | 0 | 1 | 1 | 51초 | 397 통과, 동일 |
| r7 verify_revoke+verify_spec+verify_bulk | r7 | 48 | 0 | 0 | 0 | 14초 | revoke 15 (spec·bulk 개별 이전 수치는 이 과제에 없음) |
| r8 verify_shorts(신규 폴더) | r8 | 14 | 0 | 0 | 0 | 6초 | 신규 |
합계 통과 1309, 실패 0, 건너뜀 1(`verify_m23/test_vm_02_google_router.py:313` "openapi 비활성", 시험 자체의 조건 건너뜀), xfail 1.
- 통과 수는 `-q`(요약 줄 미출력 설정) 때문에 진행 점 문자 수로 센 값. 구간 내 일부 xfail/건너뜀 문자는 로그로 확인.
- domain +9: 병합으로 추가된 `test_pass_only.py`, `test_live_guard.py` 등 신규 시험으로 추정(개수 대조는 안 함 → 원인 확정은 "원인 미확정(추정)").
- 실패 0건이므로 관련/무관 분류 대상 없음. DEF-BA-001·openapi 재생성 이후 기준 통과.

## 미수행
- 이전 수치가 없는 구간(verify_spec, verify_bulk 개별)의 증감 비교, 프런트 시험, 변이 점검, 54329 기존 DB에 대한 실행.
- 첫 실행 로그(.harness-tmp/pg2/out)는 클러스터 재생성 때 삭제됨(원인 위 기록으로 대체).

## 질문
- 없음.

## 정리 내역
- `pg_ctl -m fast stop -D .harness-tmp/pg2/data`로 pg2 정지 후 `.harness-tmp/pg2` 삭제(DB ytweb_r1~r8 포함). 자기 PID 외 프로세스 종료 없음. 총 소요 약 3분(상한 12분 이내).
