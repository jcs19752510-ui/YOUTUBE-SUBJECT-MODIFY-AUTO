# web-WU-BE-B 구현 노트 — 백엔드 도메인 (5단계)

- 작업 단위: **W-BE-B** (WEB_DESIGN §7) / 속도 트랙: **L3**(표기 없음) / 모드: 데모(M1) 전용 — 유튜브·AI 실호출 코드 없음
- 실행 방식: **병렬 웨이브**(W-BE-A, W-FE, W-INF와 동시). 파일 범위 안에서만 수정했고 `core/`·`app.py`·`worker.py`·`alembic`·`tests/core`·`tests/conftest.py`·`db/*`·`config.py`는 읽기만 했다. `traceability.md`·`decisions.md`는 수정하지 않았다(하단 "공유 문서 갱신 요청").
- 세션 한도로 한 번 중단 후 재개했다. 재개 시 W-BE-A의 실제 `ytweb/core/*`가 이미 있어 **임시 대역은 만들지 않았고 처음부터 실제 모듈로 통합 테스트**했다.

## 1. 파일
| 영역 | 파일 |
|---|---|
| 도메인 | `ytweb/domain/{common,exclusions,seed,suggestions,limits_quota,batches,changes,reports,videos,dashboard,serialize,schemas,deps,handlers}.py`, `domain/__init__.py`(핸들러 등록용 임포트) |
| AI | `ytweb/ai/{base,guard,mock,factory}.py` |
| 유튜브 | `ytweb/youtube/{base,mock}.py` |
| 라우터 | `ytweb/routers/{dashboard,videos,suggestions,batches,changes,reports,jobs,google}.py` |
| 테스트 | `tests/domain/{conftest,helpers,test_seed_ai_gateway,test_suggestions,test_limits_quota,test_batches,test_apply,test_tick,test_changes_reports,test_videos_dashboard,test_routers,test_edge_branches,test_postgres,test_tc_numbers}.py` |

## 2. 공개 인터페이스(다른 담당이 쓰는 것)
- `ytweb.domain.batches.run_due_items(factory, now, env=None, *, batch_id=None, gateway_factory=..., on_progress=None, job_id=None) -> TickResult` — 워커 틱(`worker.py`가 `(factory, now)`로 그대로 호출, 동작 확인함: TC-WB-090).
- `ytweb.domain.batches.recover_running_items(factory, now, env=None, *, stale_after=10분)` — 재시작 복구. **워커 기동 직후 `stale_after=timedelta(0)`으로 한 번 호출해 주길 요청**(기본 틱은 10분 이상 된 running만 정리).
- 작업 핸들러 3종(`videos.sync`, `suggestions.generate`, `batch.execute`)은 `import ytweb.domain` 시점에 `register_handler`로 등록된다(`domain/handlers.py`; 워커가 하위 모듈을 어느 것만 불러와도 패키지 `__init__`이 등록).
- `Env`(`domain/common.py`): 정책(`youtube_title.config.Settings`)·금칙어 사전·비밀 폴더 묶음. 요청 경로는 `Depends(get_env)`, 워커 경로는 환경변수에서 만든 `default_env()`.
- 라우터 의존성 `get_gateway`/`get_title_suggester`/`get_env`(`domain/deps.py`)는 `dependency_overrides`로 교체 가능.

## 3. 설계 결정
1. **승인 HMAC**: `secrets_dir/approval_hmac.key`(hex 32바이트, 없으면 0600으로 생성; 검증 경로는 키를 만들지 않고 없으면 `approval_tampered`). mac 입력 = 제안 ID·영상 ID·plan_hash·승인자·승인/만료 시각. 승인은 1회용(`used_at`).
2. **plan_hash** = `compute_plan_hash(영상 ID, 제안 ID, 이전 제목, 새 제목, snippet 전체)`. 반영 직전 재조회한 snippet으로 다시 계산해 비교(제목 외 필드가 바뀌면 `video_changed`).
3. **제안은 제안마다 CandidateFile 1개**로 검증(주제·엄격 모드가 제안별로 정해짐). 엄격 모드(건강·금융·주제 불명)는 검증기가 경고를 차단으로 바꾸며, 승인 시점에 **다시 검증**(사전·영상 변경 대비)하고 `is_blocking`(차단 또는 엄격+비통과)로 한 번 더 막는다.
4. **쿼터는 반영 1건당 3행(재조회 1 + 갱신 50 + 검증 재조회 1)을 한꺼번에 선예약**(전부 아니면 전무). 쓰기 뒤 검증할 쿼터가 없어 검증 못 하는 상황을 없애기 위함. 호출하지 않은 예약만 0으로 환원, 호출했다 실패한 것은 차감 유지. PostgreSQL은 advisory lock으로 직렬화.
5. **하루 상한**은 KST 날짜 기준 `apply`의 `success+planned` 건수. `evaluate_limits`의 DAILY 검사에는 `max_live_changes_per_day=daily_apply_cap`을 넣어 재사용. 간격(72h)·횟수(3)·최소 노출수는 기존 정책 그대로.
6. **일정 배정**: 오늘 남은 칸 = 상한 − 오늘 반영 수 − 오늘까지 밀린 pending 예약 수, 이후 날짜는 그날 예약 수를 뺀 칸. 다른 큐 배치와 칸을 공유한다.
7. **워커 틱**: 반복마다 `상한 − 오늘 반영 수`와 쿼터 잔여를 다시 계산해 0이면 멈춘다. 밀린 예약도 같은 하루 몫을 쓰므로 몰아서 실행되지 않는다(TC-WB-082). 쿼터 부족은 건너뛰지 않고 pending으로 대기.
8. **항목 선점**은 compare-and-set(`pending→running`) + PG `FOR UPDATE SKIP LOCKED`. 한도 검사~planned 기록~커밋 구간은 PG advisory lock(`7340003`)으로 워커 사이에 직렬화(없으면 동시 틱에서 상한 초과를 실제로 재현: 아래 §7 변이 점검).
9. **커밋 지점**: 선점 → (planned 기록+쿼터 예약+승인 소진) → 갱신 → 최종. 모의 게이트웨이의 "유튜브"가 같은 DB라도 각 지점을 따로 커밋해 실제 서비스처럼 중간에 끊긴 상태를 재현·복구할 수 있다.
10. **롤백 복원 본문은 백업 snippet 전체**(spec). 반영 중 설명이 사라진 경우도 복원된다(TC-WB-100).
11. 설정 화면의 `tone`은 문자열 목록(W-BE-A) → 도메인에서는 `", "`로 합친 한 문자열로 AI 어댑터에 전달(모의는 말투를 쓰지 않음).

## 4. 설계서 대비 편차 / 해석 (확인 요청 포함)
| # | 내용 | 사유 |
|---|---|---|
| D1 | **승인 만료 판정 시각 = 배치 실행 확정 시각(`batch.executed_at`)**. 사전 점검·실행 확정은 현재 시각 기준(만료되면 `precheck_stale`/차단) | 상한 때문에 여러 날에 걸친 배치가 24시간 TTL로 둘째 날부터 전부 건너뛰어지는 것을 막기 위해. 1회용·HMAC·plan_hash(영상 변경 시 무효)는 그대로. **TTL을 반영 시각에도 엄격 적용하길 원하면 알려 주세요**(코드 1줄) |
| D2 | 반영은 됐으나 재조회 검증 실패(예: 설명 소실) → **변경 `result=success`+`error_code=verify_failed`, 배치 항목은 `failed`, 제안은 `applied`, 롤백 가능** | 제목이 실제로 바뀌었으므로 이력·한도(72h/횟수)에 반영하고 롤백 대상이어야 함. 자동 롤백은 하지 않음(CLI와 동일) |
| D3 | **제외 영상(Shorts·비공개·아동용·예약)은 제안 생성(409)·승인(409)·배치 사전 점검(blocked)·반영(skipped)에서 모두 막음** | Q-7 "기존 제외 정책 유지". 일찍 알리는 편이 낫다고 판단(CLI는 순차 모드에서만 강제). 완화하려면 알려 주세요 |
| D4 | 최소 노출수 조건(`min_impressions_before_rechange` 1000, fail-closed)을 그대로 적용 → **데모에서는 변경 후 지표가 없어 같은 영상의 재변경이 `limit_impressions`로 막힘** | 안전 한도를 줄이지 않는다(DEC-038). 데모에서 재변경을 시연하려면 정책 값을 0으로 낮출지 결정 필요(질문 1) |
| D5 | 같은 영상에 같은 제목을 다시 생성하면 **새로 만들지 않고 기존 제안을 돌려줌**(UNIQUE(video_id,title)) | 멱등 |
| D6 | 응답에 **선택 필드 추가**: `VideoDetail.preserved`(카테고리·태그·언어·설명 길이, W-006용), `BlockedItem.code`, `Batch.precheck`(상세·생성·실행 응답에만, 목록은 null) | 프런트 요청(precheck)과 W-006 |
| D7 | `GET /batches` 목록의 각 배치는 `items: []`(상세에서만 채움) | 응답 크기 |
| D8 | 롤백도 쿼터를 쓴다(CLI 게이트 4와 동일). 부족하면 429 `quota_exhausted` | 일치 |
| D9 | `batches.status` 전체 값: `draft|queued|running|paused|done|cancelled`. **`paused`는 정의만 있고 M1에서 사용하지 않음, `failed`는 배치 상태에 없음**(실패는 항목 상태 `failed`와 `counts.failed`) | 프런트 요청 ⑤ |

## 5. 프런트 요청 처리 결과 (coordinator 메시지)
1. `GET /batches/{id}`에 `precheck` 포함 — **처리**(TC-WB-131).
2. 배치 `status`: **`running`은 실제 처리 중(running 항목 존재)일 때만**, 오늘 몫을 끝내고 미래 pending만 남으면 `queued` 유지, 모두 끝나면 `done` — **처리**(TC-WB-081, 159).
3. `GET /videos` `sort`: `title|views|duration_sec|last_change_at|video_id|suggestion_count|workflow_status`, `order=asc|desc`(값 없음은 항상 맨 뒤), 필터 `q`(제목·ID 부분 일치, 대소문자 무시, 글자 그대로)·`status`(workflow_status)·`excluded` — **이미 지원**(TC-WB-113~116, 125).
4. 승인 만료 시 제안 `status=expired` — **지연 만료 처리 포함**: 제안·영상 목록, 영상 상세, 대시보드, 워커 틱, 배치 사전 점검 시점에 `expire_stale_approvals` 실행(TC-WB-035, 092, 121). 단 배치에 담긴(queued) 제안은 D1에 따라 만료로 바꾸지 않는다.
5. 배치 `status` 값 목록 — D9.

## 6. 데모 게이트 ↔ live_guard 14단계 대응
| live_guard | 데모 구현(위치) | 상태 |
|---|---|---|
| 1 `--live` 플래그 | 해당 없음(데모 전용). 사람 확인은 배치 `confirm_text`("실행 N건", `execute_batch`) | 대응 |
| 2 `enable_live` | 해당 없음(`YTWEB_MODE=demo` 고정, 라이브 게이트웨이 코드 없음) | **M3에서 이식** |
| 3 허용 목록 | 해당 없음 | **M3에서 이식** |
| 4 쿼터 여유 | `apply_one` 4단계 `reserve_calls`(52단위 선예약, 부족 시 `quota_exhausted`) | 이식 |
| 5 교체 제한·미확정 planned | 2~3단계: `pending_change_exists`, `check_video_limits`(INTERVAL/COUNT/IMPRESSIONS/DAILY) | 이식 |
| 6 호출 직전 재조회 | 5단계: `title_changed`, `video_changed` | 이식 |
| 7 승인(해시·만료·1회용) | 1단계 `check_approval`(HMAC·만료·사용됨·plan_hash) + 재조회 snippet 해시 비교 | 이식(만료 기준은 D1) |
| 8 변경 전 지표 | 게이트로 막지 않음. 기준선이 없으면 리포트가 "기준선 없음/데이터 부족"으로 표시 | 변경(데모) — M3에서 확인 절차 검토 |
| 9 요청 본문(snippet 전체 보존) | `build_update_body` + `_check_body`(`body_invalid`) | 이식 |
| 10 영상 ID 직접 입력 | 배치는 `confirm_text`, 롤백은 `typed_video_id` | 부분 — **영상별 ID 입력 방식은 M3에서 이식** |
| 11 백업·planned·쿼터 선예약·승인 소진 | `backup_snippet`+`planned` 행+3행 예약+`used_at`을 한 커밋으로. DB 사본(백업)은 W-INF `backup.ps1` 담당 | 이식 |
| 12 `videos.update` | `MockYouTubeGateway.update_snippet`(snippet 통째 교체 — 빠진 필드는 소실) | 모의 |
| 13 재조회 사후 검증 | `verify_snippet`(제목 + description/tags/categoryId/defaultLanguage/defaultAudioLanguage) | 이식 |
| 14 결과 기록 | `changes`(success/failed/aborted/planned)+`audit_log` | 이식 |
- 라이브 허용·허용 목록·쓰기 토큰·영상 ID 직접 입력: **"M3에서 이식"**.

## 7. REQ ↔ 구현 ↔ TC
| REQ | 구현 | TC-WB |
|---|---|---|
| W-003 목록·검색·정렬·필터 | `videos.py`, `routers/videos.py` | 113~116, 125 |
| W-004 후보 생성·근거 저장·설정 | `suggestions.generate_for_video`, `ai/*` | 008~013, 018~023, 126, 128 |
| W-005 검증·차단 | `validate_title`, 승인 게이트 | 013, 024~026, 039 |
| W-006 전후 비교 데이터 | `VideoDetail.preserved`, 변경 이력 | 118, 093 |
| W-007 수정·승인·반려 | `edit_title/approve/reject` | 027~038, 127 |
| W-008 일일 상한·다음 날 예약·몰아서 실행 금지 | `assign_dates`, `run_due_items` | 050, 051, 081~083 |
| W-009 사전 점검·확인 문구 | `create_draft/build_precheck/execute_batch` | 049, 052~061, 129~130, 145~147 |
| W-010 진행·중지·이중 반영 금지 | `cancel_batch`, `apply_one`, `recover_running_items` | 062~080, 085~086, 137~141, 148~156 |
| W-011 롤백 | `changes.rollback_change` | 094~103, 132 |
| W-012 이력 | `changes.list_changes`, audit | 093, 136 |
| W-013 리포트·CSV | `reports.py` | 104~112, 133 |
| POL-001 엄격 모드 | 검증기 + `is_blocking` | 013, 026 |
| POL-002 데이터 부족·원인 단정 금지 | `youtube_title.report.build_report` 재사용 | 104~109, 133 |
| POL-003 제외 영상 | `exclusions.py` | 004, 020, 028, 055 |
| S-W03 CSRF/상태 변경 | 라우터 `require_csrf` | 123 |
| S-W06 / SEC-C03·C04·C05 (AI 응답 검증·검증기 필수·사람 승인) | `ai/guard.py`, 승인 게이트 | 008~011, 023~024, 070 |
| S-W07 / SEC-C06 최소 전송·마스킹, 원문 비저장 | `build_summary/mask_pii`, `ai_runs.prompt_hash` | 011, 018 |
| S-W12 동시성·멱등 | CAS, 부분 고유 인덱스, advisory lock, `Idempotency-Key` | 064, 129~132, 137~143 |
| S-W13 입력 검증·SQL 바인딩 | Pydantic `extra=forbid`, ORM만 | 114, 122, 125, 127 |
| S-W16 감사 | 상태 변경마다 `audit.record` | 018, 027, 031, 063, 094, 136 |
| CSV 수식 주입 방지 | `reports.csv_safe` | 110~112 |

## 8. 게이트
- **게이트 1(정적 분석)**: 프로젝트에 린트/타입 설정이 없다(`pyproject`에 ruff/mypy 설정 없음). 대신 내 파일에 `ruff check --select F,E9`(미사용 임포트·구문 오류)를 임시로 돌려 **통과**(도구는 `.harness-tmp/venv_be_b` 안에만 설치, 저장소 의존성 아님). **요청**: 린트·포맷터·타입 검사 설정은 공통 선행 단위에서 추가 필요(오케스트레이터).
- **게이트 2(자체 리뷰)**:
  - [x] 설계서/디자인서와 일치(편차는 §4)
  - [x] 에러 처리 누락 없음 — 예상 밖 예외는 `apply_one`에서 로그(`log.exception`)+항목 `failed`로 기록하며 삼키지 않음. AI 어댑터 경계에서만 광범위 `except`(실패 기록 후 502)
  - [x] 시스템 경계 검증: Pydantic(`extra=forbid`, 패턴·길이), 승인자 이름, 영상 ID 형식, AI 응답 `sanitize_drafts`
  - [x] 하드코딩 비밀 없음(HMAC 키는 런타임 생성, 파일 0600)
  - [x] 새 외부 패키지 추가 없음(W-BE-A의 `requirements.in` 항목만 사용; `psycopg[binary]` 포함 확인)
  - [x] 범위 밖 변경 없음 — 단 `web/backend/pyproject.toml`의 `[tool.coverage.run] omit`이 내 모듈을 제외하고 있어 **수정하지 않고** 임시 rc 파일(스크래치패드)로 측정함 → W-BE-A에 omit 제거 요청

## 9. 테스트 결과(이 환경)
- `tests/domain`: **182 passed, 0 failed, 0 skipped**(PostgreSQL URL 지정 시) / URL 없이 **175 passed, 7 skipped**(PG 전용 `@pytest.mark.postgres` 7건 — 사유: `YTWEB_TEST_PG_URL` 없음, PASS로 세지 않음).
- 백엔드 전체(`tests/`, W-BE-A 포함): **605 passed, 8 xfailed**(PG URL 지정).
- 내 모듈 커버리지(분기 포함, `domain/ai/youtube` + 8개 라우터): 문장 2004 / 미실행 39 / 분기 424 / 부분 31 → **합산 약 97%**. 가장 낮은 모듈: `batches.py` 94%, `changes.py` 93%(미실행은 방어용 분기: 날짜 범위 초과 400일, 영상 행 삭제 등).
- **PostgreSQL 16.15 실제 실행 결과(7건, 모두 통과)**: 부분 고유 인덱스(영상당 planned 1개, 제안당 진행 항목 1개), 같은 항목 6스레드 동시 반영 → 성공 1·나머지 `not_pending`·변경 1건·쿼터 52, 워커 3개 동시 틱 → 8건 정확히 1번씩, **동시 4틱에서도 하루 상한 3건 유지**, `SKIP LOCKED`로 서로 다른 항목 배정, 쿼터 예약 16스레드 → 정확히 10건(520단위) 성공.
- **변이 점검**: PG advisory lock 한 줄을 끄면 TC-WB-141이 3회 모두 `4 != 3`(상한 초과)으로 실패 → 락이 실제로 필요하고 테스트가 이를 잡는다. 락 복원 후 통과.
- **PG 테스트가 잡은 실제 버그 1건(수정함)**: 시드가 영상과 `metrics_snapshots`를 한 번에 flush하여 FK 순서가 PostgreSQL에서만 깨짐(SQLite는 FK 미검사) → 영상 flush 후 스냅샷 삽입으로 수정.
- 테스트 번호: TC-WB-001~159 연속·중복 없음(TC-WB-144가 자동 점검).

## 10. 알려진 제한 / 미수행
- 실서비스 AI·라이브 유튜브·구글 OAuth·라이브 게이트 이식은 의도적 미구현(M2/M3).
- 프런트 연동·브라우저 확인은 W-FE 담당. 컨테이너 실기동(Docker 데몬 없음)은 이 단위에서 미수행.
- 변경이 `planned`로 남은 영상(`result_unknown`/내부 오류)은 자동 정리하지 않는다(CLI와 동일: 이중 반영 방지가 우선). 정리 도구는 M1 범위 밖.
- `paused` 배치 상태는 M1에서 쓰지 않는다. 제안별 수동 신규 입력 API(§3에 없음)는 만들지 않았다.
- 단위 테스트 결과서·검증 로그는 6단계 담당이 작성한다(이 단위는 자체 결과서 없음).

## 11. 실행 방법
```bash
# 루트에서 한 번: python3.12 -m venv .harness-tmp/venv_be_b && .harness-tmp/venv_be_b/bin/pip install -r web/backend/requirements-dev.in pyyaml python-dotenv tzdata && .harness-tmp/venv_be_b/bin/pip install --no-deps -e .
cd web/backend
../../.harness-tmp/venv_be_b/bin/python -m pytest tests/domain -q                      # PG 전용 7건은 skip
YTWEB_TEST_PG_URL='postgresql+psycopg://…' ../../.harness-tmp/venv_be_b/bin/python -m pytest tests/domain -q   # PG 포함
```

## 12. 인수 조건(6단계 테스터용)
1. `POST /videos/sync` → 워커 처리 후 영상 200개(생활 140·건강 40·금융 20, 제외 사유 포함), 재실행해도 200개·스냅샷 불변.
2. 영상별 제안 생성(1~5개)은 결정적이며 통과/경고/차단이 섞인다. 건강·금융의 경고는 차단으로 표시된다. 차단 제안 승인은 409 `suggestion_blocked`.
3. 승인은 plan_hash·24시간 TTL·HMAC에 묶인다. 제목 수정·영상 변경·DB 변조는 무효, 만료 시 `expired`.
4. 배치: 항목 ≤50, 확인 문구 `실행 N건` 정확 일치, 하루 상한만큼 오늘·나머지 다음 날(상한 3·항목 8 → 3/3/2). 꺼져 있다 켜져도 하루 상한만큼만 처리.
5. 반영 실패는 해당 항목만 `failed|skipped`(`[코드] 사유`)이고 이중 반영 불가. 반영 후 설명 소실은 `verify_failed`로 알리고 롤백으로 복구 가능.
6. 롤백은 영상 ID 직접 입력·이후 변경 없음일 때만, 백업 snippet 전체 복원+재조회 검증.
7. 리포트는 데이터 부족을 명시하고 원인을 단정하지 않으며 CSV는 수식 주입이 무력화된다.

## 질문(규칙 A)
1. (D4) 데모에서 같은 영상 재변경을 시연하려면 `min_impressions_before_rechange`를 웹 정책에서 낮출까요, 아니면 정책 그대로(재변경은 변경 후 지표가 생긴 뒤)로 둘까요?
2. (D1) 승인 TTL을 배치 실행 확정 시각 기준으로 두는 해석을 승인하시나요?
3. (D3) 제외 영상의 승인 단계 차단을 유지할까요(vs. 배치 단계에서만 차단)?

## 공유 문서 갱신 요청 (오케스트레이터가 반영)
- traceability: W-003~W-013, POL-001~003, S-W03/06/07/12/13/16 → 작업 단위 `W-BE-B`, 구현 상태 `구현됨(데모 모드, 모의)`; TC 매핑은 §7.
- decisions: D1(승인 만료 기준), D2(검증 실패 기록 방식), D3(제외 영상 차단 시점), D4(재변경 노출수 조건 적용) 기록 요청 — 사용자 확인 대기 항목으로 분류 권고.
- 다른 담당 요청: W-BE-A — `pyproject.toml`의 coverage `omit`에서 도메인 모듈 제거, 워커 기동 시 `recover_running_items(..., stale_after=timedelta(0))` 1회 호출.

---

## 수정 단위 (2026-10-11) — W-FIX-BE 도메인 부분

- 근거: DEC-046(사용자가 수정 묶음 구현 승인). 속도 트랙 L3(표기 없음). 병렬 웨이브: 프런트(W-FIX-FE)·인프라(W-FIX-INF)와 동시. `web/backend/` 안에서만 수정했고 `web/frontend`·`web/docker`·`scripts`·`compose.yaml`은 건드리지 않았다. 새 패키지 없음(매니페스트 변경 없음).
- 가상환경 `.harness-tmp/venv_fix_be`(해시 잠금 설치), 전용 DB `ytweb_test_f`.

### 변경 파일(도메인)
`ytweb/domain/batches.py`(초안 점유 사유·취소·복구 감사), `ytweb/domain/notices.py`(신규, 면책 문구 단일 출처), `ytweb/domain/reports.py`(notes 첫 줄 면책), `ytweb/domain/schemas.py`(`MAX_ID`·`MAX_PAGE`, `BlockedItem.batch_id`, `PrecheckOut.notice`, `suggestion_ids[]` 항목 범위), `ytweb/domain/common.py`(`clean_approver`), `ytweb/routers/{batches,changes,suggestions,videos}.py`(경로·쿼리 상한). 시험: `tests/domain/test_wbx_fixes.py`(TC-WBX-001~018), `tests/domain/test_wbx_postgres.py`(TC-WBX-034~038). 문서: `docs/yt/API.md`(v0.2), `docs/yt/openapi.json`(앱에서 재생성).

### 결함 ↔ 변경 ↔ TC
| 결함 | 변경 | TC |
|---|---|---|
| DEF-7-009 (C-2) | `cancel_batch` 는 원래 초안도 취소했으므로 **의미는 유지**하고 (a) 항목 사유를 초안이면 `[cancelled] 사용자가 초안을 버렸습니다.` 로 구분, (b) 감사 `batch.cancel.detail.was_draft` 추가, (c) 새 배치 사전 점검에서 초안에 붙잡힌 제안은 `blocked[]` 에 `code=already_in_batch`, `reason="초안 배치 #N에 이미 담겨 있습니다…"`, `batch_id=N` 으로 돌려줌(`_active_holder`/`_holder_reason`, 기존 `_active_item` 대체). 부분 고유 인덱스 `uq_batch_items_active_suggestion`(status IN pending/running)은 항목이 `cancelled` 가 되면 풀리므로 변경 없음 | 001~007, 034(동시 취소 2건), 035(취소 vs 실행 경합 ×6), 036(같은 제안 동시 초안) |
| DEF-7B-002 | `_recover_one` 의 "재조회로 success/failed 확정" 분기에서 `change.apply` 감사(`actor=worker`, `target=change`, `detail`: `batch_id, video_id, suggestion_id, verify_ok, recovered:true, reason:"restart_recovery"`)를 기록. `batch.item.recovered.detail` 에 `batch_id·video_id·change_id` 추가. 해시 체인은 `audit.record` 그대로 | 008~010, 038 |
| DEF-9-007 | `notices.DISCLAIMER`; `reports/changes.notes[0]`; CSV 는 기존처럼 notes 가 빈 줄 뒤 일반 행(`csv_safe` 적용)으로 나가므로 자동 포함(`#` 주석 줄 아님); 사전 점검 응답에 `notice` | 011~013 |
| DEF-9-001 | 경로·쿼리 ID `le=2**63-1`, `page le=1_000_000`, 본문 `suggestion_ids[]` 항목 `1..2**63-1` → 422 `validation_error` | 014~015 |
| DEF-9-004 | `common.clean_approver` 가 유니코드 범주 Cf(제로폭·방향·소프트 하이픈·BOM)·Zl·Zp 를 거부(422 `approver_invalid`). **`youtube_title.approvals.clean_approver`(CLI)는 재사용하지 않았다** — 예외 형식이 달라 웹용(`ProblemError`)이 따로 있고, CLI 쪽 같은 갭은 `src/youtube_title` 소유 범위 밖이라 건드리지 않음(알려진 제한) | 016~018 |

### 면책 문구 원문(프런트가 같은 문장 사용)
`이 검증은 법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다.` (끝 마침표 포함, CLI `youtube_title.ui.DISCLAIMER` 와 동일)

### 계약 변경(프런트가 알아야 할 것)
1. `POST /batches/{id}/cancel` : 초안에서도 200 `Batch(status:"cancelled")`, 항목 전부 `cancelled`, 제안은 `approved` 로 남아 바로 새 배치에 담긴다. 두 번째 취소는 409 `batch_not_cancellable`(상태·감사 변화 없음), 취소된 초안의 실행은 409 `batch_not_draft`. 멱등성 키는 받지 않는다(기존과 동일).
2. 사전 점검 `blocked[]` 항목에 선택 필드 `batch_id`(`already_in_batch` 일 때만). 초안이면 [초안 버리기] 대상 번호로 쓴다.
3. `precheck.notice`(문자열|null) 추가. 4. `reports/changes.notes` 첫 항목이 면책 문장(총 5개).
5. 모든 ID·쪽 번호 범위 초과는 422 `validation_error`(이전엔 500). 6. 승인자 이름에 보이지 않는 문자 → 422 `approver_invalid`.

### 알려진 제한 / 해석
- "멱등"은 **효과 멱등**으로 해석했다: 두 번째 취소는 409 이고 아무것도 바꾸지 않는다(기존 계약 `batch_not_cancellable`·검증된 시험 TC-VB-319 유지). 200 재생으로 바꾸려면 계약 변경이라 질문으로 남긴다.
- 실행 확정된 배치의 제안은 상태가 `queued` 라 `not_approved` 로 먼저 막힌다 → "진행 중 배치" 사유(`_holder_reason` 비초안)는 경합 상황용 방어 문구다.
- 9단계(web/tests_security)·7단계(web/tests_integration)의 `xfail(strict)` 시험 일부가 이제 XPASS 로 바뀐다(DEF-9-001/004/007 관련·IT-318/323/400/404/435 등). 소유 범위 밖이라 표식은 건드리지 않았다. `web/tests_integration/mutate_b.py` M08 은 사라진 `_active_item` 문자열을 가리킨다 → 독립 검증 담당이 `_active_holder` 호출로 갱신 필요.
- 자체 코드 리뷰(게이트 2): 명세 일치 ✔ / 예외 삼킴 없음 ✔(워커의 stale 정리 실패는 `log.error(exc_info)`) / 경계 입력 검증(스키마 상한) ✔ / 하드코딩 비밀 없음 ✔ / 새 패키지 없음 ✔ / 범위 밖 변경 없음(`tests/conftest.py`·기존 4개 시험의 `no_idle` 표식 추가는 아래 BE-A 절에 사유 기록) ✔. 게이트 1: 린트 설정 없음 → 설정 파일 부재 사실만 기록, 대신 `pyflakes` 임시 설치(venv 안, 매니페스트 불변)로 변경 파일 점검: 잔여 경고 0(`ytweb/domain/__init__.py` 의 기존 부수효과 임포트 경고 1건 제외).

### 인수 조건(6단계 재검증용, W-FIX-BE 전체)
1. 초안 배치 생성 → 같은 제안으로 다시 생성하면 `blocked[0]` 에 `초안 배치 #N`·`batch_id=N` → `POST /batches/N/cancel` 200 → 같은 제안으로 새 배치 201. 취소 감사 `batch.cancel` 의 `was_draft=true`, 감사 체인 정상.
2. 취소와 실행이 동시에 와도 최종 배치는 `cancelled`, 제안은 `approved`(`queued` 로 갇히지 않음), 반영 변경 0건.
3. 워커를 `kill -9` 후 재기동하면 30초 안에 `batch.execute` 작업이 종료 상태(IT-318 xfail 해제 대상), 5분 넘게 갱신 없는 `batch.execute` 는 1분 안에 재큐.
4. 반영 직후 죽은 항목이 복구되면 감사에 `change.apply`(`recovered:true`)가 변경·영상·제안 ID 와 함께 남는다(IT-323).
5. `reports/changes.notes[0]`·CSV 끝 행·`precheck.notice` 가 면책 문장과 일치.
6. `GET /batches/99999999999999999999999`·`?page=…` 등은 422(500 아님). 승인자 `홍​길동` 은 422 `approver_invalid`. 마지막 사용 31분 뒤 요청은 401 `session_required`.

### 공유 문서 갱신 요청 (오케스트레이터가 반영)
- traceability: DEF-7-009(C-2)·7B-001·7B-002·9-001·9-003①·9-004·9-007(서버 쪽)·7-003~005(openapi/API.md 문서) → 작업 단위 `W-FIX-BE`, 구현 상태 `구현됨(6단계 재검증 대기)`; POL-002 웹 행의 서버 쪽 근거 = `ytweb/domain/notices.py`.
- decisions: (a) 세션 유휴 만료 기본 30분(`YTWEB_SESSION_IDLE_MINUTES`, 0=끔) — Q-S9-7 추천안 적용, (b) stale 작업 규칙(기동 시 전부 재큐 + `batch.execute` 5분/그 외 10분, 시도 3회 상한), (c) 승인자 이름 Cf/Zl/Zp 거부, (d) "취소 멱등"은 효과 멱등(두 번째 취소 409) 해석.
- 질문(규칙 A): Q1 두 번째 취소를 409 대신 200(재생)으로 바꿀까요? Q2 유휴 30분 기본값이 선생님 사용 패턴에 너무 짧지 않은가요(탭 방치 후 재로그인 필요, PIN 없으면 새로고침만으로 복구)? Q3 CLI `youtube_title.approvals.clean_approver` 의 같은 제로폭 갭도 고칠까요(src/youtube_title 범위)?
