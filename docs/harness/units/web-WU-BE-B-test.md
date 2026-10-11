# 테스트 결과서 — web-WU-BE-B 백엔드 도메인 (6단계 독립 검증)

## 1. 개요
- 테스트 대상: W-BE-B(백엔드 도메인) — `web/backend/ytweb/domain/`, `ytweb/ai/`, `ytweb/youtube/`, 라우터 8종(`dashboard, videos, suggestions, batches, changes, reports, jobs, google`), 구현자 시험 `tests/domain/`
- 테스트 유형: 단위(독립 검증, 구현자 시험을 복사하지 않고 설계서·API.md·요구사항에서 새로 작성) + 변이 점검 + 실제 PostgreSQL 16 동시성 실측
- 적용 Tier: Standard(웹 전환 기본 등급), 규칙 B 원문(최소 2회, 결함 0건 확인 회차까지)
- 적용 속도 트랙: L3 / 병렬 실행 정보: 병렬 웨이브(W-BE-A·W-FE·W-INF와 동시), 임시 폴더 `.harness-tmp/vb/`, PostgreSQL 포트 54332
- 테스트 목적: `web-WU-BE-B-note.md` 12절 인수 조건 7개와 중점 검증 항목을 시험으로 증명하고, 안전 로직 회귀를 막는다
- 관련 산출물: `docs/harness/units/web-WU-BE-B-note.md`, `docs/yt/DESIGN.md` Part B, `docs/yt/WEB_DESIGN.md`, `docs/yt/API.md`, `웹프로그램으로수정요청.md`, DEC-042
- 테스트 수행자: 06단계 독립 검증 에이전트 `vb` / 일시: 2026-10-10~11 (세션 한도·컨테이너 재시작으로 3회 중단 후 재개. 중단 전 진행분은 검토 후 재사용, 변이 점검은 재개 후 격리 사본이 잘못 설정된 것을 발견해 처음부터 다시 수행 — 14절 한계 참고)

## 2. 테스트 범위 및 제외 범위
- 범위: 제안 생성·검증(금칙어·엄격 모드·글자수), 승인(계획 해시·HMAC·24시간·1회용·재승인), 배치 만들기(50건 상한·영상당 1건·사전 점검 수치·KST/PT 경계·`daily_apply_cap`), 배치 실행(확인 문구 `실행 N건`, 실행 시점 재확인, 멱등성, 이중 실행·동시성), 워커 처리(재시도 없음, 놓친 예약 몰아서 실행 금지, 중지·취소 복귀), 롤백(영상 ID 직접 입력·`later_change_exists`·`backup_invalid`·쿼터), 교체 제한 4종, 리포트·CSV(수식 무력화), 대시보드, 데모 모드 외부 호출 0건(런타임 소켓 차단), 오류·사유 코드 대조, 영상 제외 규칙, 보안 코드 읽기
- 제외(PASS로 세지 않음): 실서비스 AI·라이브 유튜브·구글 OAuth(M2/M3 미구현), 프런트·브라우저(W-FE), 컨테이너 실기동(Docker 없음), 코어 `ytweb/core/`·CLI `src/youtube_title/` 자체(읽기만)

## 3. 테스트 환경
- 실행 환경: Linux 컨테이너, Python 3.13.16(요구 ≥3.12), pytest 9.1.1, coverage 7.16.2, ruff 0.17.0, SQLAlchemy 2.1.4, FastAPI 0.143.0, psycopg 3.3.6. 가상환경 `.harness-tmp/vb/venv`(백엔드 `requirements-dev.txt` 해시 잠금 설치)
- PostgreSQL: 호스트 16.x(`/usr/lib/postgresql/16/bin`)로 전용 임시 인스턴스(`.harness-tmp/vb/pg`, 127.0.0.1:54332)
- 테스트 데이터: 시연용 가상 영상 60~200개, 가짜 비밀 폴더. 실제 구글·유튜브·AI 호출 없음(TC-VB-278/340)
- 재실행 방법(저장소 루트 기준):
```
python3 -m venv .harness-tmp/vb/venv && .harness-tmp/vb/venv/bin/pip install -r web/backend/requirements-dev.txt pyyaml python-dotenv tzdata ruff coverage
.harness-tmp/vb/venv/bin/pip install --no-deps -e .
cd web/backend
../../.harness-tmp/vb/venv/bin/python -m pytest tests/verify_wb tests/domain -o addopts=""              # SQLite(PG 전용은 skip)
YTWEB_TEST_PG_URL=postgresql+psycopg://postgres@127.0.0.1:54332/ytvb ../../.harness-tmp/vb/venv/bin/python -m pytest tests -o addopts=""   # PG 포함 전체
../../.harness-tmp/vb/venv/bin/python tests/verify_wb/_mutation/mutate.py <회차>                      # 변이 점검(91곳)
```
- 전제 조건: W-BE-A `core/`(세션 commit 순서 수정 포함)가 반영된 작업 트리에서 실행. 5단계 게이트: 노트 8절에 정적 분석(`ruff F,E9`)·자체 리뷰 통과 기록 확인 → 이 검증에서도 재실행해 통과(5절)

## 4. 테스트 케이스 및 결과
시험 파일: `web/backend/tests/verify_wb/test_vb_01~13_*.py`(독립 시험 **347건**, 이름에 `test_tc_vb_<번호>`가 시험 ID `TC-VB-<번호>`) + 구현자 `tests/domain` 182건(참고·회귀용, 독립 시험으로 세지 않음).

| 구분 | 실행 | 통과 | 실패 | 건너뜀 |
|---|---|---|---|---|
| `tests/verify_wb` (PG 포함) | 347 | 347 | 0 | 0 |
| `tests/domain` (PG 포함) | 182 | 182 | 0 | 0 |
| 백엔드 전체 `tests/`(W-BE-A·다른 검증 포함, PG 포함) | 1218 | 1218 | 0 | 0 |
| `tests/verify_wb`+`tests/domain` PG 없이(SQLite) | 529 | 503 | 0 | 26(PG 전용, **PASS로 세지 않음** — PG 포함 실행에서 별도 통과) |

세부 시험 목록(실행 기대값과 실제 비교는 각 시험의 assert, 번호로 구분):
- 영상·동기화·제외: 001~006, 241, 242 / 제안 생성·AI 가드·마스킹: 010~017, 020~026, 030~032, 306, 340, 341 / 수정·반려: 040~045, 314
- 승인(해시·HMAC·TTL·1회용·재승인): 050~065, 307, 310, 311 / 배치 크기·확인 문구·취소: 070~076, 120~124, 315, 319, 327
- 일정·상한: 080~089, 097, 098, 303, 304, 316, 251, 251b, 252 / 교체 제한·DEC-042: 090~096, 325 / 쿼터: 100~107, 317, 324, 254, 262
- 사전 점검: 110~113 / 반영·재확인·멱등: 130~143, 300~302, 312, 313, 328, 250, 253, 255 / 복구·재시작: 150~156, 284~286, 318
- 롤백: 160~178, 287, 257 / 이력: 180, 181 / 리포트·CSV: 190~200, 320 / 감사: 210~214, 259 / 상세·대시보드: 220~222, 321~323, 326
- HTTP·보안·멱등성키: 230~240, 263, 305 / PG 제약·락: 256, 258, 260, 261 / 게이트웨이·공용: 270~283, 289

### 4-1. 인수 조건 ↔ 시험 추적 (1:1)
| AC (노트 12절) | 시험 ID | 결과 |
|---|---|---|
| 1. 동기화 후 200개(생활 140·건강 40·금융 20), 재실행해도 200·스냅샷 불변 | TC-VB-001, 002, 003, 004, 005, 242 | PASS |
| 2. 제안 1~5개 결정적·통과/경고/차단 혼재, 건강·금융 경고는 차단, 차단 승인 409 `suggestion_blocked` | TC-VB-010~017, 020~026, 311, 312, 341 | PASS |
| 3. 승인은 plan_hash·24시간·HMAC, 제목 수정·영상 변경·변조 무효, 만료 `expired` | TC-VB-050~065, 307, 310, 240 | PASS |
| 4. 배치 ≤50, 확인 문구 `실행 N건`, 상한 3·항목 8 → 3/3/2, 꺼졌다 켜져도 하루 상한만 | TC-VB-070~076, 080~089, 097, 098, 251, 316, 086 | PASS |
| 5. 실패는 해당 항목만 `failed\|skipped`(`[코드] 사유`), 이중 반영 불가, 설명 소실 `verify_failed`+롤백 복구 | TC-VB-130~143, 150~156, 250, 253, 300~302, 328 | PASS |
| 6. 롤백: 영상 ID 직접 입력·이후 변경 없음, 백업 전체 복원+재조회 검증 | TC-VB-160~178, 257, 287 | PASS |
| 7. 리포트 데이터 부족 명시·원인 단정 금지, CSV 수식 무력화 | TC-VB-190~200, 320 | PASS |
| 중점: 소켓 차단 외부 호출 0건 | TC-VB-340(+278 정적) | PASS |
| 중점: 오류·사유 코드 ↔ API.md | 11절 대조표, TC-VB-289, 305 | PASS(문서 보완 요청 1건) |
| 중점: 영상 제외 규칙(D3) | TC-VB-004, 005, 016, 113 | PASS |
- 연결 없는 AC: 0건. 정상·경계(50/51건, 299·300·301자, TTL ±1초, 72시간 ±1초, 노출수 999/1000, 쿼터 51/52, KST 자정, PT 자정)·예외(빈 입력·null·비문자열·제어/방향 문자·주입 문자열)·권한(세션·CSRF·Origin)·악의 입력(SQL 유사 검색어, 수식 제목, AI 응답 조작)을 모두 포함.

## 5. 커버리지
- 측정 범위: `domain/*`, `ai/*`, `youtube/*`, 라우터 8종. 줄+분기, 백엔드 전체 시험(PG 포함) 1회 실행 합산
- 결과: 문장 2018 / 미실행 25 / 분기 428 / 부분 25 → **98%**(100% 미달). 독립 시험(`verify_wb`)만으로는 96%였고 보강 후 합산.
- 100% 미달 줄과 사유(모두 방어 코드·경합 전용·환경 한계, 동작 결함 아님):
  - `batches.py` 64·73·84·103·359: 영상·제안 행이 사라진 경우 등 FK 때문에 정상 경로로 도달 불가한 방어 분기, 400일 초과 일정(상한 최소값 때문에 도달 불가); 155-156·428-429: 제안/영상 고유 제약 경합 IntegrityError(타이밍 의존이라 결정적 재현 불가 — 부분 고유 인덱스 자체는 TC-VB-260으로 PG에서 검증); 375-378: 승인 해시가 먼저 걸려 도달 불가한 제목 규격 재검사; 491-548 일부: 복구 중 행 삭제 방어 분기
  - `changes.py` 81·119-122: 영상 행 삭제, 롤백 중 고유 제약 경합(타이밍)
  - `suggestions.py` 63-64(키 동시 생성 경합), 101(저장 snippet 비정상); `seed.py` 135·`serialize.py` 57·`videos.py` 32·48·`mock.py` 41: 입력 검증 방어·빈 목록 분기
- 정적 분석: `ruff check --select F,E9`(미사용 임포트·구문 오류) 대상 소스+독립 시험 **통과**. 린트·타입 도구 설정이 프로젝트에 없어 **기술부채로 기록**(규칙: 도구 부재만으로 반려하지 않음; 변경 없음).

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 내용 |
|---|---|---|---|---|---|
| DEF-VB-01 | 오늘 상한이 찬 뒤 도달한 항목(동시 틱 경쟁 포함)이 다음 날로 이월되지 않고 `limit_daily`로 영구 `skipped` 처리됨. W-008 "초과분은 다음 날 자동 예약"과 불일치 | 상한 1·항목 2를 오늘로 맞춘 뒤 `apply_one` 두 번(TC-VB-098), 상한 3·항목 10을 4개 틱이 경쟁(TC-VB-251) | High | **Fixed** | `batches.py` `_apply` 3단계: 실패 사유가 DAILY뿐이면 항목을 `pending`+다음 KST 날짜로 되돌리고 `deferred` 결과·감사 `batch.item.deferred` 기록(쿼터·변경 기록 소비 없음). 간격 등 다른 사유가 함께 있으면 기존대로 skipped(TC-VB-304). `TickResult`는 `deferred`를 처리 수로 세지 않음. 시험 097·098·251·303·304 |
| DEF-VB-02 | DEC-042(데모 모드 재변경 최소 노출수 0)가 코드에 미반영 → 데모에서 72시간 뒤에도 재변경이 `limit_impressions`로 막힘 | 영상에 73시간 전 변경 이력을 넣고 `check_video_limits`(TC-VB-094) | Medium | **Fixed** | `common.py` `Env.rechange_min_impressions`/`limits_policy` 추가, `Env.build`가 데모에서 0 지정. **교체 한도 판정 3곳(`videos.py` 1, `batches.py` 2)에서만 사용**하고 `env.policy`(리포트 '데이터 부족' 기준 1000)는 그대로 둠. 처음에 정책 값을 통째로 바꿨을 때 TC-VB-194(리포트 노출수 기준)가 실패해 POL-002 약화를 잡아냄 → 위 방식으로 재설계. 72시간 간격·3회 제한 유지(TC-VB-093) |
| DEF-VF-B02 | `title_invalid` 오류의 한국어 `hint`가 빔(프런트 검증 요청) | 제목에 숫자를 넘겨 `edit_title` 호출(TC-VB-306) | Low | **Fixed** | `suggestions.py` hint 추가. 소스 전체 `ProblemError` 호출을 AST로 훑어 hint 없는 호출 0건을 보증하는 TC-VB-305 추가 |
| DEF-VB-03 | 승인 HMAC 키 파일이 깨져 있으면 `approve`가 `ProblemError`가 아닌 원시 `ApprovalInvalid` 예외를 내 500(일반 오류)이 됨(fail-closed이긴 하나 사용자 안내 없음) | 키 파일에 `zz-corrupt`를 쓰고 `approve` 호출(TC-VB-307, 작성 중 탐침으로 발견) | Low | **Fixed** | `suggestions.py` 승인 시 키 로드 실패를 `ProblemError(500, approval_key_unreadable, hint)`로 변환. 키 파일은 덮어쓰지 않음(기존 승인 전부 무효화 방지), 승인 기록도 남지 않음(TC-VB-307) |
| DEF-VB-04 | [시험 결함] 이전 중단 시점의 독립 시험이 DEF-VB-01·DEC-042 미반영 동작을 `xfail`/"현재 동작 고정"으로 기록 | 2회 완주 후 정리 | Low | Fixed | 수정 후 기대 동작 시험(093·094·097·098·220·251)으로 교체, 구현자 `tests/domain` TC-WB-043은 변경 없이 통과(정책값 직접 사용) |
| DEF-VB-05 | [시험 결함] 변이 점검 1회전 첫 실행이 격리 사본 경로 때문에 설정을 못 찾아 **모든 변이를 가짜로 "잡음" 처리**(70/72). 무변이 기준선(baseline)을 먼저 돌려 발견 | 기준선 실행 실패 확인 | Medium | Fixed | 실행기가 사본의 `REPO_ROOT`를 절대 경로로 교체하도록 수정, 기준선 통과(303 passed) 후 1회전부터 재수행. 이후 모든 수치는 재수행분 |
- **Open 결함: 0건.** 다른 단위로 넘기는 사항(이 단위가 고칠 수 없는 문서·타 단위)은 8절·부록 B.
- 이 단위 밖 원인 가능성: 없음(결함 5건 모두 이 단위 소유 파일·시험에서 발생·수정). `core/`의 세션 commit 순서는 W-BE-A 수정이 반영된 상태에서 전체 1218건 통과로 확인.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 생성한 임시 아티팩트: `.harness-tmp/vb/venv`, `.harness-tmp/vb/pg`(PostgreSQL 데이터·로그, 변이용 DB `ytvb_mut_m89~m91`), `.harness-tmp/vb/mut/`(변이 사본), 진행 메모·커버리지·라운드 결과 파일, 파이썬 `__pycache__`/`.coverage`
- 모두 `.harness-tmp/vb/` 하위에서만 생성했는가: [x] 예 (예외: 파이썬이 `web/backend/**/__pycache__`를 만듦 — `.gitignore` 대상)
- 정리 완료 여부: 예. 임시 PostgreSQL 프로세스를 종료(포트 54332 응답 없음 확인)한 뒤 `.harness-tmp/vb/` 전체를 삭제. 다른 에이전트 폴더(`va`, `vf`, `vi`)는 건드리지 않음
- 정리 후 점검: 병렬 지시서 3절에 "git 명령 금지"가 있어 `git status`를 새로 실행하지 않고 파일시스템으로 점검. `ls .harness-tmp` 결과에 `vb` 없음. 이 단위의 미추적 잔여물은 의도한 산출물(시험·결과서·로그·`tests/verify_wb/_mutation/`)뿐
- 이번 테스트 도중 강제 중단: [ ] 없음 / [x] 있음 — 세션 한도·컨테이너 재시작으로 중단. 재개 시 `.harness-tmp/vb/` 잔여물(가상환경·PG 데이터)을 먼저 확인해 재사용했고, 죽은 PG 프로세스의 `postmaster.pid`를 정리 후 재기동(내 인스턴스만)

## 8. 리스크 및 잔존 이슈
- **PASS로 세지 않은 것**: 실서비스 AI·라이브 유튜브·구글(M2/M3), 프런트 연동, Docker 컨테이너 실기동, Windows 환경, 15분 이상 장시간 부하·지연 주입, 다중 프로세스(워커 컨테이너 2개 이상) 실측(스레드 경합과 PG 락으로만 확인)
- 문서 보완 요청(이 단위가 소유하지 않는 문서, 오케스트레이터가 반영): `docs/yt/API.md` 사유 코드 표에 ① `deferred`(오늘 몫 소진 → 다음 날 이월, 항목은 `pending` 유지) 설명, ② 승인 키 손상 `approval_key_unreadable`(500, 승인 시) 추가, ③ `limit_daily`는 상한 외 다른 한도와 함께 걸린 경우에만 `skipped`로 남음 명시
- 설계 질문 / 확인 대기(구현자 노트 D1~D4와 DEC-042 처리 결과): D1(만료 판정 = 실행 확정 시각)과 D3(제외 영상 승인 단계 차단)은 DEC-042에서 수용됨. 이 검증은 해당 동작을 시험으로 고정함(TC-VB-062, 016). M3 라이브에서 TTL 재평가 필요(DEC-042 기록 그대로)
- 잔존 관찰: `planned` 상태가 `result_unknown`으로 남은 영상은 자동 정리 도구가 없음(노트 10절, 의도적, 이중 반영 방지 우선)

## 9. 결론 및 판정
- 판정: **PASS**
- 근거: 인수 조건 7개·중점 항목 전부 시험 연결, 독립 시험 347건 + 구현자 182건 + 전체 1218건 통과(PG 실제 실행 포함), 실패 0건, 결함 5건 모두 Fixed(Open 0), 변이 점검 91곳 최종 회전 90곳 잡음·1곳 동치(근거 TC-VB-341), 커버리지 98%(미달 줄 사유 기록), 정적 검사 통과
- 조건 없음. 단 8절의 "PASS로 세지 않은 것"은 이 판정에 포함되지 않음.

## 10. 내부 검증 (최소 2회)
- 1차(작성자 관점): AC↔TC 추적, 이전 진행분 시험 검토, 전체 실행, 정적 검사, 커버리지, 코드 읽기에서 DEF-VB-01·02·03·VF-B02 발견·수정
- 2차(독립 심사자 관점): 변이 점검 3회전(부록 A). 1회전 72곳 중 15곳 놓침 → 시험 15건 보강 → 2회전 91곳 중 7곳 놓침(신규 변이) → 시험 6건 보강 → 3회전 91곳 중 놓침 1(동치)
- 3차: 결함 0건(Open) 확인 후 전체 1218건 재실행 통과, 소켓 차단·PG 실측 재확인
- 검증 로그 파일 경로: `docs/harness/verify-log_web-WU-BE-B-test.md`

## 11. 오류·사유 코드 ↔ API.md 대조
- 소스에서 추출한 `ProblemError` 코드 40여 개와 항목 사유 코드(`StepFailure`/`ApprovalInvalid`)를 API.md 6·7절과 대조: 문서에 없는 코드는 `approval_key_unreadable`(승인 시 500, 이번에 신설·수정), `approval_key_missing`(검증 경로에서 `approval_tampered`로 변환되어 사용자에게 보이지 않음), `video_missing`(내부 복귀 판단용으로만 쓰임). 문서에 있는데 소스에 없는 코드: `cancelled`(`[cancelled]` 문자열로 존재, 일치), `interrupted`(복구 경로에 존재, TC-VB-151)
- 일치 시험: TC-VB-289(모든 도메인 오류에 hint·title), TC-VB-305(정적 hint 전수)

## 12. 보안 관점 점검(코드 직접 읽기)
- 입력 검증: Pydantic `extra=forbid`·패턴·길이(TC-VB-237·238), 승인자 이름 제어문자·길이(044), 영상 ID 정규식, AI 응답 `sanitize_drafts`(제어/방향/비가시 문자·링크·연락처·중복·개수; 021~023)
- 권한·CSRF: 변경 엔드포인트 전부 세션+CSRF+Origin 요구(231), GET으로 상태 변경 불가(233·279), 읽기 엔드포인트 세션 요구(232)
- 비밀 비노출: HMAC 키·MAC은 감사 로그에 없음(212), AI에는 마스킹된 최소 요약만 전송(030·032), 프롬프트 원문 미저장(해시만, 031)
- SQL: ORM 바인딩만 사용, 검색어 주입 무해(239)
- 동시성·멱등: 항목 선점 CAS+`SKIP LOCKED`+PG advisory lock, 부분 고유 인덱스, `Idempotency-Key`(250~263, PG 실측)
- fail-closed: 키 없음·손상(054, 307), 승인 만료·1회용·변조(050~058), 재조회 불일치(059~061), 쿼터 선예약 전부 또는 전무(101~104)
- 관찰(결함 아님): 승인 TTL이 반영 시각이 아니라 실행 확정 시각 기준(D1, DEC-042 수용); CSV 수식 방지는 `= + - @ TAB CR` 시작 셀(앞 공백 뒤 수식은 엑셀이 수식으로 읽지 않음)

## 부록 A. 변이 점검(코드를 일부러 망가뜨려 시험이 실패하는지 확인)
- 방식: 격리 사본(`.harness-tmp/vb/mut/mNN/`)에서만 소스 1곳을 바꾸고 `tests/verify_wb`(PG 변이 3건은 PG 전용 시험)를 `-x`로 실행, 실패하면 "잡음". 대상 문자열이 소스에 정확히 1곳인지 먼저 확인(아니면 BADTARGET, 재작성). 구현자 노트의 자체 변이(PG advisory lock 1줄)와 겹치지 않는 대상만 선정(m91은 같은 락을 다른 방식으로 확인한 보조 점검)
- 무변이 기준선: 303 passed(PG 전용 18 skip) — 이 기준선 없이는 "잡음"이 무의미함(DEF-VB-05)
- 수치: **1회전 72곳: 잡음 57 / 놓침 15**, **2회전 91곳(신규 19 포함): 잡음 84 / 놓침 7**, **3회전 91곳: 잡음 90 / 놓침 1(동치)**
- 놓침 처리: 1회전 15곳 → TC-VB-310~323으로 보강. 2회전 7곳 중 m08 제외 6곳 → TC-VB-251b, 324~328로 보강. m08은 동치(아래)
- 동치 변이 m08: 승인 경로 `is_blocking(sug)` → `validation_result == "block"`. 승인 직전 `_apply_validation`이 검증기를 다시 돌리고, 검증기는 엄격 모드의 경고를 항상 차단으로 바꾸므로(`youtube_title/validator.py:156`) (엄격, 경고) 조합이 존재하지 않는다 → 두 식이 같은 결과. 전제를 TC-VB-341이 전수 확인. 반영 경로의 같은 식은 저장 상태가 이상할 때를 대비한 방어이며 TC-VB-312가 직접 잡음(m09)
| ID | 파일 | 변이(원본 → 변이) | 1회 | 2회 | 3회 |
|---|---|---|---|---|---|
| m01 | `domain/suggestions.py` | `if ref_time >= ap.expires_at:` → `if ref_time > ap.expires_at:` | 잡음 | 잡음 | 잡음 |
| m02 | `domain/suggestions.py` | `if ap.used_at is not None: ⏎` → `if False: ⏎` | 잡음 | 잡음 | 잡음 |
| m03 | `domain/suggestions.py` | `if not hmac.compare_digest(expected, ap.mac):` → `if False:` | 잡음 | 잡음 | 잡음 |
| m04 | `domain/suggestions.py` | `"plan_hash": plan_hash, "approver": approver,` → `"plan_hash": plan_hash,` | 잡음 | 잡음 | 잡음 |
| m05 | `domain/suggestions.py` | `sug.plan_hash != ap.plan_hash or plan_hash_for(sug, video, s` → `sug.plan_hash != ap.plan_hash` | 놓침 | 잡음 | 잡음 |
| m06 | `domain/suggestions.py` | `timedelta(hours=env.policy.approval_ttl_hours)` → `timedelta(hours=env.policy.approval_ttl_hours + 1)` | 잡음 | 잡음 | 잡음 |
| m07 | `domain/suggestions.py` | `if sug.status not in ("candidate", "expired"):` → `if sug.status not in ("candidate", "expired", "blocked"):` | 놓침 | 잡음 | 잡음 |
| m08 | `domain/suggestions.py` | `if is_blocking(sug): ⏎         raise ProblemError(409, "sugg` → `if sug.validation_result == 'block': ⏎         raise Problem` | 놓침 | 놓침 | 놓침 |
| m09 | `domain/suggestions.py` | `sug.strict_mode and sug.validation_result != "pass"` → `sug.strict_mode and sug.validation_result == "block"` | 놓침 | 잡음 | 잡음 |
| m10 | `domain/suggestions.py` | `if reasons: ⏎         raise ProblemError(409, "video_exclude` → `if False: ⏎         raise ProblemError(409, "video_excluded"` | 잡음 | 잡음 | 잡음 |
| m11 | `domain/suggestions.py` | `if sug.title == video.title: ⏎         raise ProblemError(40` → `if False: ⏎         raise ProblemError(409, "same_as_current` | 잡음 | 잡음 | 잡음 |
| m12 | `domain/suggestions.py` | `not 1 <= count <= MAX_COUNT` → `not 1 <= count <= MAX_COUNT + 1` | 잡음 | 잡음 | 잡음 |
| m13 | `domain/suggestions.py` | `isinstance(count, bool) or` → `` | 잡음 | 잡음 | 잡음 |
| m14 | `domain/suggestions.py` | `if reasons: ⏎         raise ProblemError(409, "video_exclude` → `if False: ⏎         raise ProblemError(409, "video_excluded"` | 잡음 | 잡음 | 잡음 |
| m15 | `domain/suggestions.py` | `Suggestion.video_id == video_id, Suggestion.title == draft.t` → `Suggestion.video_id == video_id, Suggestion.title == draft.t` | 잡음 | 잡음 | 잡음 |
| m16 | `domain/suggestions.py` | `sug.status = "blocked" if res.result == "block" else "candid` → `sug.status = "candidate" ⏎     session.flush()` | 잡음 | 잡음 | 잡음 |
| m17 | `domain/suggestions.py` | `invalidated = _drop_approval(session, sug) ⏎     old = sug.t` → `invalidated = False ⏎     old = sug.title` | 잡음 | 잡음 | 잡음 |
| m18 | `domain/suggestions.py` | `Approval.expires_at <= now` → `Approval.expires_at < now` | 잡음 | 잡음 | 잡음 |
| m19 | `domain/suggestions.py` | `if sug.status != "queued": ⏎         return ⏎     try:` → `if False: ⏎         return ⏎     try:` | 놓침 | 잡음 | 잡음 |
| m20 | `domain/common.py` | `len(name) > MAX_APPROVER_CHARS` → `len(name) >= MAX_APPROVER_CHARS` | 잡음 | 잡음 | 잡음 |
| m21 | `domain/suggestions.py` | `if len(title) > MAX_TITLE_CHARS:` → `if len(title) >= MAX_TITLE_CHARS:` | 놓침 | 잡음 | 잡음 |
| m22 | `domain/batches.py` | `len(suggestion_ids) > MAX_BATCH_ITEMS` → `len(suggestion_ids) >= MAX_BATCH_ITEMS` | 잡음 | 잡음 | 잡음 |
| m23 | `domain/batches.py` | `suggestion_ids.count(i) > 1` → `suggestion_ids.count(i) > 2` | 잡음 | 잡음 | 잡음 |
| m24 | `domain/batches.py` | `if problem is None and video.video_id in seen_videos:` → `if False:` | 잡음 | 잡음 | 잡음 |
| m25 | `domain/batches.py` | `if confirm_text != expected:` → `if confirm_text.strip() != expected:` | 잡음 | 잡음 | 잡음 |
| m26 | `domain/batches.py` | `if batch.status != "draft":` → `if batch.status == "cancelled":` | 잡음 | 잡음 | 잡음 |
| m27 | `domain/batches.py` | `overdue = sum(c for d, c in rows if d <= today)` → `overdue = sum(c for d, c in rows if d < today)` | 잡음 | 잡음 | 잡음 |
| m28 | `domain/batches.py` | `(applied_today(session, now) + overdue) if offset == 0` → `(overdue) if offset == 0` | 잡음 | 잡음 | 잡음 |
| m29 | `domain/batches.py` | `min(max(0, cap - used), n - len(dates))` → `min(max(0, cap - used + 1), n - len(dates))` | 잡음 | 잡음 | 잡음 |
| m30 | `domain/batches.py` | `if sug.status != "approved": ⏎         return "not_approved"` → `if sug.status not in ("approved", "candidate"): ⏎         re` | 잡음 | 잡음 | 잡음 |
| m31 | `domain/batches.py` | `if c.code != "DAILY"]` → `if c.code != "INTERVAL"]` | 잡음 | 잡음 | 잡음 |
| m32 | `domain/batches.py` | `batch.status not in ("queued", "running"): ⏎         raise S` → `batch.status not in ("queued", "running", "cancelled"): ⏎   ` | 놓침 | 잡음 | 잡음 |
| m33 | `domain/batches.py` | `if sug.status != "queued": ⏎         raise StepFailure("sugg` → `if False: ⏎         raise StepFailure("suggestion_state"` | 잡음 | 잡음 | 잡음 |
| m34 | `domain/batches.py` | `if is_blocking(sug): ⏎         raise StepFailure("suggestion` → `if False: ⏎         raise StepFailure("suggestion_blocked"` | 잡음 | 잡음 | 잡음 |
| m35 | `domain/batches.py` | `reasons = exclusion_reasons(video, policy) ⏎     if reasons:` → `reasons = [] ⏎     if reasons: ⏎         raise StepFailure("` | 잡음 | 잡음 | 잡음 |
| m36 | `domain/batches.py` | `Change.video_id == video.video_id, Change.result == "planned` → `Change.video_id == video.video_id, Change.result == "xplanne` | 잡음 | 잡음 | 잡음 |
| m37 | `domain/batches.py` | `if fresh["title"] != video.title: ⏎` → `if False: ⏎` | 잡음 | 잡음 | 잡음 |
| m38 | `domain/batches.py` | `ap.used_at = now ⏎` → `pass ⏎` | 잡음 | 잡음 | 잡음 |
| m39 | `domain/batches.py` | `backup_snippet=copy.deepcopy(fresh)` → `backup_snippet={"title": fresh["title"], "categoryId": fresh` | 잡음 | 잡음 | 잡음 |
| m40 | `domain/batches.py` | `ref_time = batch.executed_at or now` → `ref_time = now` | 잡음 | 잡음 | 잡음 |
| m41 | `domain/batches.py` | `if not verify["ok"]: ⏎         change.error_code = "verify_f` → `if False: ⏎         change.error_code = "verify_failed"` | 잡음 | 잡음 | 잡음 |
| m42 | `domain/batches.py` | `item.status, item.updated_at = ("success" if verify["ok"] el` → `item.status, item.updated_at = "success", now ⏎     item.ski` | 잡음 | 잡음 | 잡음 |
| m43 | `domain/batches.py` | `remaining = effective_daily_cap(s, env.policy) - applied_tod` → `remaining = effective_daily_cap(s, env.policy)` | 잡음 | 잡음 | 잡음 |
| m44 | `domain/batches.py` | `if remaining <= 0:` → `if remaining < 0:` | 잡음 | 잡음 | 잡음 |
| m45 | `domain/batches.py` | `BatchItem.scheduled_date <= today,` → `BatchItem.scheduled_date <= today + timedelta(days=1),` | 놓침 | 잡음 | 잡음 |
| m46 | `domain/batches.py` | `.remaining < units_per_apply(env.policy):` → `.remaining <= units_per_apply(env.policy):` | 놓침 | 잡음 | 잡음 |
| m47 | `domain/batches.py` | `STALE_RUNNING = timedelta(minutes=10)` → `STALE_RUNNING = timedelta(minutes=1)` | 놓침 | 잡음 | 잡음 |
| m48 | `domain/batches.py` | `if it.status != "pending": ⏎             continue  # 진행 중` → `if it.status not in ("pending", "running"): ⏎             co` | 잡음 | 잡음 | 잡음 |
| m49 | `domain/batches.py` | `if batch.status in ("cancelled", "done"): ⏎         raise Pr` → `if batch.status in ("cancelled",): ⏎         raise ProblemEr` | 놓침 | 잡음 | 잡음 |
| m50 | `domain/batches.py` | `if all(c.code == "DAILY" for c in report.failures):` → `if any(c.code == "DAILY" for c in report.failures):` | 잡음 | 잡음 | 잡음 |
| m51 | `domain/batches.py` | `kst_today(now) + timedelta(days=1), now` → `kst_today(now), now` | 잡음 | 잡음 | 잡음 |
| m52 | `domain/changes.py` | `if typed_video_id != target.video_id:` → `if False:` | 잡음 | 잡음 | 잡음 |
| m53 | `domain/changes.py` | `Change.id > target.id, Change.result.in_(COUNTED_RESULTS)` → `Change.id > target.id, Change.result == "success"` | 잡음 | 잡음 | 잡음 |
| m54 | `domain/changes.py` | `or backup.get("title") != target.previous_title` → `` | 잡음 | 잡음 | 잡음 |
| m55 | `domain/changes.py` | `if current.get("title") == restore_title:` → `if False:` | 잡음 | 잡음 | 잡음 |
| m56 | `domain/changes.py` | `body = {"id": video.video_id, "snippet": copy.deepcopy(backu` → `body = {"id": video.video_id, "snippet": {"title": restore_t` | 잡음 | 잡음 | 잡음 |
| m57 | `domain/changes.py` | `if sug is not None and sug.status == "applied":` → `if False:` | 잡음 | 잡음 | 잡음 |
| m58 | `domain/changes.py` | `if target.change_type != "apply" or target.result != "succes` → `if target.result != "success":` | 잡음 | 잡음 | 잡음 |
| m59 | `domain/limits_quota.py` | `COUNTED_RESULTS = ("success", "planned")` → `COUNTED_RESULTS = ("success",)` | 잡음 | 잡음 | 잡음 |
| m60 | `domain/limits_quota.py` | `_change_time() < end` → `_change_time() <= end` | 잡음 | 잡음 | 잡음 |
| m61 | `domain/limits_quota.py` | `if used + need > policy.daily_limit_units:` → `if used + need >= policy.daily_limit_units:` | 잡음 | 잡음 | 잡음 |
| m62 | `domain/limits_quota.py` | `QuotaUsage.status == "reserved").values(units=0, status="fai` → `QuotaUsage.status.in_(("reserved", "failed"))).values(units=` | 잡음 | 잡음 | 잡음 |
| m63 | `domain/reports.py` | `_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")` → `_FORMULA_START = ("=", "+", "-", "@", "\t")` | 잡음 | 잡음 | 잡음 |
| m64 | `domain/reports.py` | `return "'" + value` → `return value` | 잡음 | 잡음 | 잡음 |
| m65 | `domain/reports.py` | `return "﻿" + buf.getvalue()` → `return buf.getvalue()` | 잡음 | 잡음 | 잡음 |
| m66 | `domain/reports.py` | `writer.writerow([csv_safe(note)])` → `writer.writerow([note])` | 놓침 | 잡음 | 잡음 |
| m67 | `domain/videos.py` | `needle not in row.title.casefold()` → `needle not in row.title` | 놓침 | 잡음 | 잡음 |
| m68 | `domain/videos.py` | `present + [r for r in rows if key(r) is None]` → `[r for r in rows if key(r) is None] + present` | 놓침 | 잡음 | 잡음 |
| m69 | `domain/dashboard.py` | `Batch.status.in_(("queued", "running")))` → `Batch.status.in_(("queued", "running", "cancelled")))` | 놓침 | 잡음 | 잡음 |
| m70 | `ai/guard.py` | `elif has_contact_or_url(title):` → `elif False:` | 잡음 | 잡음 | 잡음 |
| m71 | `ai/guard.py` | `_PHONE.sub("[전화번호]", text)` → `text` | 잡음 | 잡음 | 잡음 |
| m72 | `ai/guard.py` | `elif len(title) > MAX_TITLE_CHARS:` → `elif len(title) > MAX_TITLE_CHARS + 1:` | 잡음 | 잡음 | 잡음 |
| m73 | `domain/limits_quota.py` | `QuotaUsage.id == reservation_id, QuotaUsage.status == "reser` → `QuotaUsage.id == reservation_id)` | - | 놓침 | 잡음 |
| m74 | `domain/limits_quota.py` | `MetricsSnapshot.period_start > last_at.date()` → `MetricsSnapshot.period_start >= last_at.date()` | - | 잡음 | 잡음 |
| m75 | `domain/limits_quota.py` | `MetricsSnapshot.phase.in_(("after", "periodic"))` → `MetricsSnapshot.phase.in_(("before", "after", "periodic"))` | - | 잡음 | 잡음 |
| m76 | `domain/limits_quota.py` | `if retry and len(retry) == len(report.failures) else None` → `if retry else None` | - | 놓침 | 잡음 |
| m77 | `domain/videos.py` | `if sc.get("queued"): ⏎             st = "queued" ⏎         e` → `if sc.get("approved"): ⏎             st = "approved" ⏎      ` | - | 놓침 | 잡음 |
| m78 | `domain/videos.py` | `and needle not in row.video_id.casefold()` → `or needle not in row.video_id.casefold()` | - | 잡음 | 잡음 |
| m79 | `domain/batches.py` | `if done_today >= cap:` → `if done_today > cap:` | - | 잡음 | 잡음 |
| m80 | `domain/batches.py` | `BatchItem.status.in_(("pending", "running"))) ⏎     if exclu` → `BatchItem.status.in_(("pending",))) ⏎     if exclude_batch_i` | - | 놓침 | 잡음 |
| m81 | `domain/batches.py` | `if snap is not None and snap.get("title") == change.new_titl` → `if snap is not None:` | - | 잡음 | 잡음 |
| m82 | `domain/changes.py` | `or not isinstance(backup.get("categoryId"), str) or not back` → `` | - | 잡음 | 잡음 |
| m83 | `domain/changes.py` | `and latest.get(c.video_id) == c.id` → `and True` | - | 잡음 | 잡음 |
| m84 | `domain/changes.py` | `verify["changed_since_backup"] = sorted(k for k in set(backu` → `verify["changed_since_backup"] = []` | - | 잡음 | 잡음 |
| m85 | `domain/changes.py` | `sug.status, sug.updated_at = "rolled_back", now` → `sug.status, sug.updated_at = "applied", now` | - | 잡음 | 잡음 |
| m86 | `domain/batches.py` | `release_unused(session, state.reserved) ⏎     change = state` → `change = state.change` | - | 잡음 | 잡음 |
| m87 | `domain/batches.py` | `if c["pending"] == 0 and c["running"] == 0:` → `if c["pending"] == 0:` | - | 놓침 | 잡음 |
| m88 | `domain/batches.py` | `"confirm_text": f"실행 {n}건"` → `"confirm_text": f"실행 {n} 건"` | - | 잡음 | 잡음 |
| m89 | `domain/batches.py` | `stmt = stmt.with_for_update(skip_locked=True, of=BatchItem)` → `stmt = stmt.with_for_update(of=BatchItem)` | - | 놓침 | 잡음 |
| m90 | `domain/limits_quota.py` | `session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"` → `pass` | - | 잡음 | 잡음 |
| m91 | `domain/batches.py` | `session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"` → `pass` | - | 잡음 | 잡음 |

### 부록 B. 공유 문서 갱신 요청 (오케스트레이터가 반영)
- `traceability.md`: REQ-ID W-003~W-013, POL-001~003, S-W03/06/07/12/13/16 → 단위테스트 컬럼 `web-WU-BE-B-test.md` PASS(독립 347 + 구현자 182건). W-008에 "초과분 다음 날 이월(deferred)" 반영 표기
- `decisions.md`: ① DEC-042 D1 구현 방식 — 완화는 교체 한도 판정에만, 리포트 기준은 유지(`Env.limits_policy`) ② 일일 상한 초과 항목은 skipped가 아니라 다음 날 이월(`deferred`) ③ 승인 키 손상 시 500 `approval_key_unreadable`(덮어쓰지 않음)
- `docs/yt/API.md`: 8절 문서 보완 요청 3건
- W-BE-A: 요청 없음(세션 commit 수정 반영 확인, 전체 1218건 통과). 노트 8절의 coverage `omit`은 오케스트레이터가 이미 제거(DEC-042)해 도메인 모듈 측정이 가능했음을 확인
