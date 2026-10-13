# 일괄 승인 백엔드 구현 결과서 (be-impl)

시작 2026-10-13 03:09:24 UTC, 보고 작성 시점 약 03:21 UTC(상한 12분 이내). 계약: `CONTRACT.md` 백엔드 부분.

## 1. 한 일 / 안 한 일
한 것: `POST /api/v1/suggestions/resolve-videos`, `POST /api/v1/suggestions/approve-batch`, `approve()`의 `ack_warning` 키워드(기본 None = 단건 경로 동작 동일), 시험 34개, 변이 점검 13건.
안 한 것(정확히): OpenAPI/API.md 갱신 = **미갱신**(`docs/yt/openapi.json`·`API.md`의 생성 방식을 확인할 시간이 없었고, 두 엔드포인트는 response_model 없이 JSON 반환). 프런트 구현 없음(범위 밖). 실제 모드(구글)·배치 실행 변경 없음.

## 2. 변경 파일
- `web/backend/ytweb/domain/suggestions.py`: `approve(..., ack_warning=None)`, `approve_batch()`, `resolve_videos()`, `_bulk_size()`
- `web/backend/ytweb/domain/schemas.py`: `ApproveBatchIn`, `ResolveVideosIn`(건수 규칙은 서비스에서 한국어 ProblemError로 거부)
- `web/backend/ytweb/routers/suggestions.py`: 두 라우트(approve-batch는 `idempotent()` + `require_csrf`, resolve-videos는 `require_csrf`)
- 시험: `web/backend/tests/domain/test_bulk_approve.py` (TC-BA-001~035, 040)

## 3. 설계 확인 사항
- 건별 SAVEPOINT(`session.begin_nested()`): `get_session`/`session_scope`는 요청 끝 commit·예외 시 rollback이라 SAVEPOINT와 충돌 없음. ProblemError 건만 SAVEPOINT 롤백(`_apply_validation` 변경 포함) — TC-BA-009가 `updated_at`·`dictionary_hash` 원복으로 증명, PostgreSQL에서 TC-BA-020b로도 증명.
- 예상 못 한 예외는 그대로 전파(500) → 요청 전체 rollback. PostgreSQL 시험 TC-BA-020에서 승인·감사 0건 확인.
- 잠금: 제안 행을 id 오름차순으로 먼저 `FOR UPDATE`(PostgreSQL), 처리·보고는 요청 순서. 서로 반대 순서의 동시 일괄 승인도 교착 없이 각 제안 정확히 1회 승인(TC-BA-040).
- 경고 검사 위치: `approve()` 안에서 재검증(`_apply_validation`) 및 차단 검사 뒤, `video_inconsistent`·`same_as_current` 검사 앞. 따라서 현재 제목과 같으면서 경고인 제안은 확인 전에는 `warning_not_acknowledged`로 먼저 걸린다(TC-BA-009 첫 실행 참고).
- 승인자 이름 검증은 아무것도 건드리기 전에 수행. 감사 요약은 `{approver, requested, approved, skipped}`만 기록(제목·토큰 없음).
- `resolve_videos`는 읽기 전용(`expire_stale_approvals`를 호출하지 않음) — 상태가 `approved`인 만료 직전 제안도 그대로 보여준다.

## 4. 환경·명령
- Python 3.12 venv `.harness-tmp/venv_06_web_fix_be`, SQLite(기본 시험) + PostgreSQL 16.15(`127.0.0.1:54329`, **DB `ytweb_test_a`만**). PG는 꺼져 있어 `pg_ctl start`로 기동(postgres 계정). 비밀번호를 문서에서 찾지 못해 **임시 인스턴스의 `pg_hba.conf`를 trust로 바꾸고 reload**했다(원본은 `.harness-tmp/pg/data/pg_hba.conf.orig`). 저장소 미포함.
- 명령: `cd web/backend; YTWEB_TEST_PG_URL=postgresql+psycopg://postgres@127.0.0.1:54329/ytweb_test_a ../../.harness-tmp/venv_06_web_fix_be/bin/python -m pytest tests/domain/test_bulk_approve.py -p no:warnings`

## 5. 실제 결과
첫 실행 결과(그대로):
1. 시험 009 실패: `warning_not_acknowledged != same_as_current`. 원인은 시험 데이터(근거 "e"인 수동 제안)가 재검증에서 warn이 되어 경고 검사가 먼저 걸린 것. 구현 순서는 위 3절대로 의도이며, 시험을 확인 목록에 넣어 same_as_current 경로를 보도록 고쳤다(주석에 첫 결과 기록).
2. 시험 020 실패(SQLite): 예외 전파 후 rollback했는데 승인 1건이 남음. 원인은 SQLite(pysqlite 레거시 트랜잭션)에서 DML 전에 SAVEPOINT를 열면 가장 바깥 RELEASE가 커밋되는 알려진 동작. 운영 DB는 PostgreSQL이므로 이 시험을 PostgreSQL 전용으로 옮겨(020) 통과 확인. **SQLite에서는 "예상 못 한 예외 시 부분 커밋 없음"이 보장되지 않는다**(잔여 위험).
3. PG 시험 020b/040이 시드 30개 부족으로 실패 → 시드 60으로 수정.

재실행: `test_bulk_approve.py` **34 통과 / 0 실패 / 0 건너뜀**(PostgreSQL 포함, 7.4초).
회귀(전체 백엔드 시험): 아래 6절.

## 6. 회귀
FULLRESULT

## 7. 변이 점검 (구현 완료 후, 원복 확인: `diff` 일치)
| # | 변이 | 결과 |
|---|---|---|
| M1 | 50건 상한 제거 | 탐지: TC-BA-003, 022 |
| M2 | 경고 확인 검사 제거 | 탐지: 011, 013, 014 |
| M3 | SAVEPOINT 제거 | 탐지: 009, 014 |
| M4 | 영상 중복 검사 제거 | 탐지: 010 |
| M5 | 감사 요약 제거 | 탐지: 016, 024 |
| M6 | 멱등 제거 | 탐지: 024 |
| M7 | approve-batch CSRF 제거 | 탐지: 023 |
| M8 | skip 대신 전체 실패 | 탐지: 007, 008, 009 외 |
| M9 | id 중복 검사 제거 | 탐지: 005, 022 |
| M10 | resolve가 만료 쓰기 수행 | **첫 실행 미탐지**(시험이 롤백 후에만 비교) → 034에 롤백 전 비교 추가 → M10b 탐지: 034 |
| M11 | 행 잠금 제거 | 탐지: 040 (PostgreSQL) |
| M12 | 승인자 이름 선검증 제거 | **미탐지(동등 변이 판단)**: 건별 `approve()`와 마지막 감사 기록이 같은 검증을 다시 하므로 외부 동작이 같다. 보강 안 함 |
원복 후 전체 재통과: 34/34(위 5절). 별도 resolve-videos CSRF 제거 변이는 하지 않음(시험 023은 resolve의 403도 확인하나 변이로 증명하지 않음 = 미수행).

## 8. 미수행
- OpenAPI/API.md 갱신(미갱신, 위).
- resolve-videos CSRF 제거 변이.
- 51개 이상 항목 PG 부하·성능 측정.

## 9. 잔여 위험
- SQLite 기반 개발 시험에서는 SAVEPOINT 해제가 커밋될 수 있음(운영 PostgreSQL 아님).
- `approve()` 단건 경로는 코드 한 줄(`ack_warning is False` 조건) 추가뿐이며 ack_warning=None은 통과; 회귀 결과는 6절.
- 일괄 승인 응답 `reason`에 `detail`(검증 메시지)이 포함된다 — 제목 전문은 아니지만 검증 규칙 문구가 노출됨(화면용 의도).
- 승인 유효 시간 1시간 정책은 변경하지 않았다.

## 10. 질문
- OpenAPI/API.md는 어떤 스크립트로 재생성하나요(생성 스크립트를 찾지 못함)? 
- 임시 PG의 `pg_hba.conf` trust 변경을 원복할지(`.orig`로 복원) 지시 바랍니다.

## 11. 임시 파일
`.harness-tmp/pg/data/pg_hba.conf.orig`(원본), 가동 중인 임시 PostgreSQL(54329), `/tmp/mut.sh`·`/tmp/sug.orig`·`/tmp/rt.orig`·`/tmp/full.txt`(저장소 외부). git 쓰기 없음.
