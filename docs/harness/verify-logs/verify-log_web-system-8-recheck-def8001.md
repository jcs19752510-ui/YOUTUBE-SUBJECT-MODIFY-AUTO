# 검증 로그 — 8단계 재확인(DEF-8-001·DEF-7B-002·DEF-7-002)

- 시작 2026-10-11 23:33:53 UTC. 스택 `harness-tmp-i2`(127.0.0.1:18083). 구글·AI 실호출 없음. 소스 수정 없음. 커밋·푸시 없음.
- 반영 방법: 저장소 `web/docker/api.Dockerfile` 에 프록시 CA 만 추가한 사본(스크래치패드, `--build-context ca=.harness-tmp/i2/ca`)으로 `docker build -t harness-tmp-i2-api:local .`(약 40초, 성공), 이어서 `.harness-tmp/i2/stack/web` 에서 `YTWEB_IMAGE_PREFIX=harness-tmp-i2 docker compose -p harness-tmp-i2 up -d --no-deps --no-build --force-recreate api worker`. db·web 이미지는 재사용(재빌드 없음). 새 이미지에 batches.py 의 수정본(커밋 74a7241) 포함됨(이미지 내 파일 존재만 확인, 원문 diff 대조는 미수행).

## 1회차 (23:35:06 → 23:35:30, 24초)
`python -m pytest test_it_07_rev2.py::test_it_i2_042_db_container_restart_mid_batch_no_double_apply -p no:cacheprovider -q` → rc=0, `.` 1 passed. 로그 `.harness-tmp/i2/logs/rerun_def8001_1.log`
## 2회차 (23:35:30 → 23:35:52, 22초)
동일 명령 → rc=0, 1 passed. 로그 `.harness-tmp/i2/logs/rerun_def8001_2.log`
(시험 본문은 20건 모두 success·이중 반영 없음을 assert 하며 기대값 변경 없음.)

## DEF-7B-002 / DEF-7-002 (23:36:00 → 23:36:59, 59초, 1회 실행)
`pytest test_it_03_state.py::test_it_323_... test_it_05_ops.py::test_it_504_... -q` → rc=0, 2 passed. 로그 `rerun_def7b002_7002.log`. 두 시험 모두 xfail 표지 없는 정상 시험(기대: 감사에 change.apply/recovered 의 변경·영상 ID, 복원 뒤 alembic_version UPDATE/DELETE permission denied).
