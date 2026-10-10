# YT-04 설계서 (TRD) — 유튜브 제목 수정 자동화

- 입력: `02_planning.md`(v4, PASS), `01_policy_research.md`(CONDITIONAL PASS), `02_risk_assessment.md`
- 작성: 오케스트레이터(3단계 역할 직접 수행). 위협 모델은 `threat_model.md`, UX는 `04_ux_design.md`
- 되돌리기 어려운 결정은 `ADR-xxx`로 `decisions.md`(DEC-013~023)와 상호 참조한다.
- **상태: 사용자 승인 대기 (★승인 게이트 a)** — 이 문서 맨 끝 13장 참고

## 1. 아키텍처 개요

### 1-1. 구성 (텍스트 다이어그램)
```
[사용자 PowerShell]
      │  python -m ytitle <서브커맨드> [--live]
      ▼
┌─────────────────────────────  CLI 계층 (cli.py + commands/*.py)  ─────────────────────────────┐
│ auth  fetch  validate  plan  approve  apply  rollback  report  purge   (각 파일이 서브커맨드 1개) │
└──────┬──────────────┬───────────────┬────────────────┬──────────────────┬───────────────────────┘
       ▼              ▼               ▼                ▼                  ▼
  auth.py        youtube_read.py   validator.py     updater.py        report.py
 (OAuth,        (조회·Analytics)   candidates.py   limits.py         csv_import.py
  토큰 2종)       quota.py          banned_terms.py history.py
                                                    live_guard.py
                                                    approvals.py
       └──────────────┴───────────────┴────────┬───────┴──────────────────┘
                                                ▼
        공통 기반(WU-0): config · logging_setup(마스킹) · errors · retry · db · timeutil · platform_utils · textsafe · ui
                                                ▼
   ┌───────────── 로컬 저장소 ─────────────┐        ┌──────── 외부 ────────┐
   │ data/ytitle.sqlite3  (DB 7개 테이블)   │        │ YouTube Data API v3  │  ← HTTPS, OAuth 토큰
   │ data/backups/  data/logs/              │        │ YouTube Analytics API│
   │ candidates/  approvals/  config/       │        └──────────────────────┘
   │ secrets/client_secret.json (프로젝트)  │
   │ %LOCALAPPDATA%\ytitle\tokens\ (토큰)   │
   └────────────────────────────────────────┘
```

### 1-2. 신뢰 경계 (상세는 `threat_model.md`)
TB-1 PC ↔ Google API, TB-2 외부 입력 파일(후보 JSON·CSV·YAML) ↔ 프로그램, TB-3 프로그램 ↔ 같은 PC의 다른 프로세스·파일, TB-4 PyPI 의존성 ↔ 프로그램.

### 1-3. 작업 단위 확정표 (02 §9를 설계 경계에 맞춰 확정)
| 단위 | feature | 소유 파일(수정 범위) | 공유 자원 접촉 | 선행 | 확정 사항 |
|---|---|---|---|---|---|
| **WU-0** (공통 선행, unit-0) | F-0 | `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, `.gitignore`(추가), `config/settings.yaml`, `src/ytitle/{__init__,__main__,config,logging_setup,errors,retry,db,timeutil,platform_utils,textsafe,ui,cli}.py`, `src/ytitle/commands/{__init__,purge}.py`, `tests/conftest.py`, `tests/test_{config,logging,retry,db,timeutil,textsafe,ui,cli,purge}.py` | **모든 공유 자원을 선점**: 의존성 매니페스트(전체 의존성 사전 선언), DB 스키마 전체(7개 테이블), CLI 서브커맨드 자동 탐색부, 설정 로더 | 없음 | 02 대비 변경: `timeutil`·`platform_utils`·`textsafe`·`ui`(터미널 출력 컴포넌트, `04_ux_design.md`) 추가(공통 유틸) |
| WU-1 | F-A | `src/ytitle/auth.py`, `src/ytitle/commands/auth.py`, `tests/test_auth.py` | 없음(등록부는 자동 탐색, 의존성은 WU-0이 선언) | WU-0 | 불확실이던 칸 확정: **접촉 없음** |
| WU-2 | F-A | `src/ytitle/{youtube_read,quota}.py`, `src/ytitle/commands/fetch.py`, `tests/test_{read,quota}.py` | DB 읽기·쓰기(스키마는 WU-0 소유) | WU-1 | 변경 없음 |
| WU-3 | F-B | `src/ytitle/{candidates,validator,banned_terms}.py`, `config/banned_terms.yaml`, `src/ytitle/commands/validate.py`, `tests/test_{candidates,validator}.py` | 없음(PyYAML은 WU-0 선언) | WU-0 | **WU-1과 병렬 가능**(파일·데이터·의존성 독립 확정) |
| WU-4 | F-C | `src/ytitle/{updater,limits,history}.py`, `src/ytitle/commands/{plan,rollback}.py`, `tests/test_{updater,limits,history}.py` | DB `title_changes` 쓰기, `quota` 모듈 호출 | WU-2, WU-3 | 02 대비 변경: `rollback`의 쓰기 게이트는 WU-5의 `live_guard`를 호출하므로 **롤백 명령의 쓰기 실행부는 WU-5 완료 후 활성화**(WU-4는 롤백 계획·DB 처리까지, 실제 호출은 인터페이스 스텁) |
| WU-5 | F-C | `src/ytitle/{live_guard,approvals}.py`, `src/ytitle/commands/{approve,apply}.py`, `tests/test_{live_guard,approvals}.py` | 설정 계층(`settings.local.yaml` 읽기) | WU-4 | 02 대비 변경: `approve` 명령 추가(FR-013), 롤백의 실제 호출 활성화 포함 |
| WU-6 | F-D | `src/ytitle/{report,csv_import}.py`, `src/ytitle/commands/report.py`, `tests/test_{report,csv_import}.py` | DB 읽기 | WU-2, WU-4 | **WU-5와 병렬 가능**(파일 독립, 읽기 전용, 테스트는 임시 DB 별도) |

**웨이브 초안** (오케스트레이터가 5단계 착수 직전에 판정·통지): 웨이브0 = WU-0 → 웨이브1 = WU-1 ∥ WU-3 → 웨이브2 = WU-2 → 웨이브3 = WU-4 → 웨이브4 = WU-5 ∥ WU-6. 병렬 실행의 근거는 위 표의 "공유 자원 접촉"과 파일 범위이다. 이 환경에서는 하네스 서브에이전트를 쓰지 않으므로(DEC-011) 실제 실행은 순차이다.

## 2. 기술 스택과 근거

| 영역 | 선택 | 근거 |
|---|---|---|
| 언어/런타임 | Python 3.12 + venv | 사용자 기본값(DEC-003). 3.10 이상에서 동작하도록 작성(이 클라우드에서 3.11·3.12·3.13 모두 테스트함) |
| CLI | 표준 라이브러리 `argparse` + `commands/` 자동 탐색 | 의존성 최소(초보자 설치 부담↓), 단위마다 파일이 분리되어 병렬 개발 시 충돌 없음 |
| DB | 표준 라이브러리 `sqlite3` | 사용자 기본값. 단일 사용자 로컬 도구에 충분. 별도 서버 불필요 |
| Google 연동 | `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2` | 공식 클라이언트. 직접 HTTP 구현보다 인증·재시도 오류가 적다 |
| 설정 | `PyYAML`(`safe_load`만 사용), `python-dotenv` | 금칙어·정책값은 YAML, 경로·비밀은 `.env` |
| 시간대 | 표준 `zoneinfo` + `tzdata` | 쿼터 하루 경계가 태평양 시간. **Windows는 tzdata 패키지가 없으면 zoneinfo가 동작하지 않음** |
| 테스트 | `pytest`, `pytest-cov` | NFR-006 커버리지 측정 |

### 2-1. 의존성 실존·라이선스 확인 (SEC-013, 2026-10-10 PyPI 조회)
| 패키지 | 최신 | 라이선스 | 비고 |
|---|---|---|---|
| google-api-python-client | 2.201.0 (2026-09-30) | Apache 2.0 | yanked 아님 |
| google-auth-oauthlib | 1.5.0 | Apache 2.0 | |
| google-auth-httplib2 | 0.4.4 | Apache 2.0 | |
| PyYAML | 6.0.3 | MIT | |
| tzdata | 2026.5 | Apache-2.0 | |
| python-dotenv | 1.2.4 | BSD-3-Clause | |
| pytest / pytest-cov (개발용) | 9.1.1 / 7.1.0 | MIT | |
- 개인용 도구 사용에 라이선스 충돌 없음. **버전은 5단계에서 `pip install`로 확정 후 `requirements.txt`에 고정(`==`)**한다. 지금 표의 버전은 조회 시점 값이다.
- **외부 제공자 약관 확인 근거**: YouTube Data/Analytics API는 사용자 본인 OAuth로 본인 채널만 호출하고, 쿼터 우회·크롤링을 하지 않는다. 약관 조항 번호는 확인하지 못했다 → **[확인 필요]** (1단계 e, CONDITIONAL).

## 3. 데이터 모델

### 3-1. 테이블 (SQLite, 외래키 ON, 모든 시각은 UTC ISO8601 문자열)
| 테이블 | 컬럼 | 설명 |
|---|---|---|
| `schema_meta` | `version INTEGER` | 마이그레이션 버전 |
| `videos` | `video_id PK`, `title`, `category_id`, `privacy_status`, `made_for_kids`(0/1/NULL), `live_broadcast_content`, `duration_sec`, `description_excerpt`(앞 500자), `snippet_json`(최신 조회본 전체), `fetched_at` | 조회 결과 캐시 |
| `title_candidates` | `id PK`, `video_id FK`, `candidate_title`, `evidence`, `source`(`human`/`ai-assisted`/…), `topic`(`life`/`health`/`finance`/NULL), `strict_mode`(0/1), `validation_result`(`pass`/`warn`/`block`), `validation_reasons_json`, `dictionary_hash`, `file_name`, `file_sha256`, `status`, `created_at`, `updated_at` | 후보와 검증 결과, 사용한 금칙어 사전 해시(SEC-017) |
| `title_changes` | `id PK`, `video_id`, `candidate_id FK NULL`, `change_type`(`apply`/`rollback`), `previous_title`, `new_title`, `backup_snippet_json`(적용 직전 snippet 전체), `reason`, `approver`, `approved_at`, `plan_hash`, `result`(`planned`/`success`/`failed`/`aborted`), `error_code`, `applied_at`, `verified_at`, `verify_result_json`, `run_id` | 모든 쓰기 시도와 결과(성공·실패·중단 모두 기록) |
| `metrics_snapshots` | `id PK`, `video_id`, `taken_at`, `phase`(`before`/`after`/`periodic`), `source`(`api`/`csv`), `period_start`, `period_end`, `impressions`, `ctr`, `views`, `watch_minutes`, `raw_json` | 변경 전후 지표(FR-007) |
| `run_logs` | `id PK`, `run_id`, `started_at`, `ended_at`, `command`, `mode`(`dry_run`/`live`), `exit_code`, `summary` | 실행 단위 기록(FR-020). 토큰·키는 저장하지 않음 |
| `quota_usage` | `id PK`, `pt_date`(태평양 시간 날짜), `method`, `units`, `called_at`, `run_id`, `status`(`reserved`/`ok`/`failed`) | 쿼터 선예약 기록(ADR-008) |
- 인덱스: `title_changes(video_id, applied_at)`, `quota_usage(pt_date)`, `metrics_snapshots(video_id, phase, taken_at)`.
- 모든 SQL은 **파라미터 바인딩**만 사용한다(SEC-018).

### 3-2. 상태 머신 (`title_candidates.status`)
```
candidate ──검증──▶ filtered(pass/warn) ──approve──▶ approved ──apply 성공──▶ applied ──평가창 경과+after 지표──▶ evaluated
    │                                                                              │                                   │
    └──검증 block(엄격 모드의 warn 포함)──▶ blocked(종료)                                          rollback│                                  │rollback
                                                                                   ▼                                  ▼
                                                                              rolled_back(종료)             rolled_back(종료)
```
- 허용 전이만 코드에서 허용하고, 그 외 전이 시도는 예외로 처리한다. `blocked`와 `rolled_back`은 종료 상태.
- `warn`은 사람이 사유를 읽고 `approve`로 넘어갈 수 있다(건강·금융 주제 엄격 모드에서는 `warn`이 `block`으로 승격: POL-001).

### 3-3. 이관·마이그레이션
- 기존 데이터 이관 없음(신규 개발). `schema_meta.version`과 `db.py`의 순서 있는 마이그레이션 함수로 관리한다. 스키마 변경은 새 번호의 마이그레이션 추가로만 한다(기존 번호 수정 금지).

### 3-4. 보관과 삭제 (NFR-009)
- 변경 이력과 백업 snippet은 기본 365일 보관(설정값), `purge --before <날짜>` 명령으로 삭제하며 **삭제 전 DB 사본을 자동 생성**하고 확인을 요구한다. 최근 `success` 변경의 백업은 롤백 가능성을 위해 삭제하지 않는다(대상에서 제외하고 경고).

## 4. 인터페이스 명세

### 4-1. CLI (`python -m ytitle ...`) — 이벤트/인터페이스 `EVT-xxx`
| ID | 명령 | 쓰기? | 주요 옵션 | 동작 |
|---|---|---|---|---|
| EVT-001 | `auth` | 토큰 파일 | `--read` / `--write` / `--revoke` | 설치형 앱 OAuth. 읽기·쓰기 토큰을 **분리 저장**(ADR-004). `--revoke`는 로컬 토큰 삭제와 구글 계정에서의 앱 접근 제거 안내(계정 회수 절차) |
| EVT-002 | `fetch` | DB | `--all` / `--video ID` / `--metrics` | 영상 목록·snippet 조회(읽기 전용 API), 지표 수집 |
| EVT-003 | `validate` | DB | `--file candidates/ID.json` / `--all` | 후보 검증, 리포트 출력 |
| EVT-004 | `plan` | `run_logs`만 | `--candidate N` | **dry-run diff**. 쓰기 API·읽기 API 호출 없음(마지막 `fetch`로 저장된 `videos.snippet_json` 사용, 저장 시각이 24시간보다 오래되면 `fetch`를 다시 하라고 경고). 계획 해시 `plan_hash = SHA-256(video_id, candidate_id, previous_title, new_title, snippet_json의 해시)`를 계산해 출력. **`title_changes`에는 쓰지 않는다** |
| EVT-005 | `approve` | 승인 파일 | `--candidate N` `--approver 이름` `--ttl-hours` | 사람의 승인 파일 생성(계획 해시 바인딩, 만료 포함) |
| EVT-006 | `apply` | **YouTube 쓰기** | `--candidate N` `--live` | 후보 **1건씩만** 처리. 5-2의 안전 게이트를 모두 통과해야 실행. 기본(옵션 없음)은 dry-run |
| EVT-007 | `rollback` | **YouTube 쓰기** | `--change N` `--live` | 이전 제목 복원(복원도 이력 기록). 게이트: `--live` + `enable_live` + 영상 ID 직접 입력 확인 + 허용 목록 |
| EVT-008 | `report` | 파일 | `--video ID` `--import-csv 파일` | 변경 전후 비교 리포트와 CSV 가져오기 |
| EVT-009 | `purge` | DB | `--before 날짜` | 오래된 이력 삭제(자동 DB 사본, 확인 필요) |
- 모든 명령 공통 전역 옵션: `--plain`(스크린리더 친화 목록 출력), `--color`(색 켜기, 기본 꺼짐). 기본은 dry-run/읽기, `--help` 제공, 종료 코드 0(정상) / 1(오류) / 2(사용법) / 3(안전 게이트로 중단). 오류 메시지는 한국어 + "다음에 할 일"(NFR-007).

### 4-2. 외부 API 호출 `EVT-1xx`
| ID | 호출 | 용도 | 단위 비용(가정, 설정값) |
|---|---|---|---|
| EVT-101 | `channels.list` (mine=true, part=contentDetails) | 업로드 재생목록 ID 획득 | 1 |
| EVT-102 | `playlistItems.list` | 영상 ID 목록(50개씩 페이지) | 1 |
| EVT-103 | `videos.list` (part=snippet,status,contentDetails, 최대 50 ID) | snippet 전체·상태 조회 | 1 |
| EVT-104 | `videos.update` (part=snippet) | 제목 변경(전체 snippet 보존 본문) | **50** |
| EVT-105 | Analytics `reports.query` | 영상별 지표 | **미확인**(설정값, 기본 1) |
- 모든 호출은 `retry.py`를 거친다(최대 2회, 지수 백오프 1s→2s, 인증 오류·할당량 초과는 재시도하지 않음). 호출 전에 쿼터를 **선예약**한다(ADR-008).
- 계약 검증: 응답 JSON에서 필요한 필드의 존재·타입을 검사하는 함수를 두고, 8단계가 mock 응답으로 확인한다. API 버전은 `v3`/Analytics `v2`로 고정한다(변경 시 [확인 필요]).

### 4-3. 파일 형식 `EVT-2xx`
| ID | 파일 | 형식 |
|---|---|---|
| EVT-201 | `candidates/{video_id}.json` | `{"video_id","current_title","topic":"life|health|finance","summary","source":"human|ai-assisted","description_excerpt"?,"candidates":[{"title","evidence"}]}`. 최대 256KB, `video_id`는 `^[A-Za-z0-9_-]{11}$`, 후보 최대 20개 |
| EVT-202 | `approvals/{video_id}-{candidate_id}.approved.json` | `{"video_id","candidate_id","new_title","plan_hash","approver","approved_at","expires_at","used":false}` |
| EVT-203 | Studio 내보내기 CSV | 열 이름은 Studio 화면의 한글/영문 헤더를 `config/csv_mapping.yaml`로 매핑(헤더가 달라도 수정 가능). 실제 헤더는 [확인 필요] |
| EVT-204 | `config/banned_terms.yaml` | `{"version", "types": {"fear":[...], "medical":[...], "finance":[...], "impersonation":[...], "superlative":[...]}, "warning_patterns":{...}}` |
| EVT-205 | `config/settings.yaml` + `config/settings.local.yaml` | 5-3 참고 |

## 5. 비기능 요구사항 (구체화)

### 5-1. NFR 목표
| ID | 항목 | 구체화 |
|---|---|---|
| NFR-001 | 지원 환경 | Windows 10/11, PowerShell 5.1+, Python 3.12(3.10+ 호환). **Windows 전용 동작(파일 권한, 콘솔 인코딩)은 `platform_utils.py`에 격리** |
| NFR-002 | UTF-8 | 모든 파일 입출력은 `encoding="utf-8"` 명시, 콘솔은 시작 시 UTF-8로 재설정 시도 |
| NFR-003 | 쿼터 | 일일 상한 6,000 units(60%), 80% 도달 시 경고, 100% 시 즉시 중단. 날짜 경계 `America/Los_Angeles` |
| NFR-004 | 재시도 | 최대 2회, 지수 백오프, 이후 중단·기록 |
| NFR-005 | 성능 | 후보 100건 검증 5초 이내(로컬) |
| NFR-006 | 테스트 | 검증기·요청 본문 구성 모듈 줄 커버리지 90%+ |
| NFR-007 | 사용성 | 한국어 오류 + 다음 행동 안내 |
| NFR-008 | 감사 | 모든 쓰기 시도·결과·승인자 DB 기록, 로그 365일 |
| NFR-009 | 데이터 최소 보관 | 3-4 |
| **NFR-010** (신규) | 복구 목표 | **RPO ≤ 24시간, RTO ≤ 30분(가정)**. 쓰기 직전마다 DB 사본(`data/backups/`)을 만들고, 복구는 사본 파일 복사로 한다 |
| **NFR-011** (신규) | 관측성 | 실행 로그는 사람이 읽는 한국어 한 줄 + `run_id`, `data/logs/ytitle.log`(회전 5MB×10). 토큰·키 마스킹(SEC-008) |

### 5-2. 안전한 쓰기 흐름 (`apply --live`) — 앞 단계가 하나라도 실패하면 **즉시 중단(fail-closed)**하고 `result=aborted`로 기록. 값싼 로컬 검사를 먼저, 네트워크 호출은 나중에 한다
```
1  --live 플래그 있음?                                   (SEC-001 ①)
2  settings.local.yaml 의 enable_live=true?               (SEC-001 ③)  ※ settings.yaml 의 값은 무시
3  영상 ID ∈ live_allowlist? (빈 목록 = 전부 거부)          (SEC-012)
4  쿼터 여유? (오늘 남은 양 ≥ 읽기 2 + 쓰기 50 + 여유)      (SEC-002)
5  교체 제한 통과? (72h, 횟수, 최소 노출 수, 오늘 live 적용 건수)  (SEC-004, SEC-020)
6  [네트워크 읽기] 영상 snippet 재조회 → 저장본/승인 당시 제목과 동일?  (SEC-009)
7  승인 파일 유효? plan_hash를 6단계의 최신 snippet으로 다시 계산해 승인 파일의 값과 비교, 만료·사용 여부  (SEC-001 ②, SEC-014)
   → 불일치면 "승인 이후 영상 정보가 바뀌었습니다. plan부터 다시 하세요"로 중단
8  변경 전 지표 스냅샷 존재? (없으면 경고하고 사용자 확인)      (FR-012)
9  요청 본문 = 6단계 snippet 전체 + 제목만 교체                (SEC-005)
10 사용자에게 요약 출력(SCR-005) → 영상 ID를 직접 입력해 확인   (사람 승인)
11 DB 백업 사본 생성 + title_changes(planned) 기록 + 쿼터 선예약
12 [네트워크 쓰기] videos.update 호출 (재시도 ≤ 2)
13 [네트워크 읽기] videos.list 재조회 → 제목 반영·설명·태그·카테고리 보존 검증   (SEC-010)
14 결과 기록(승인 파일 used=true). 검증 실패 시 경보 + rollback 명령 안내(자동 롤백 안 함 — 쓰기이므로 사람 확인)
```
- `title_changes` 행은 **11단계에서 처음 생성**된다(`plan`은 쓰지 않음). 1~10단계에서 중단되면 `aborted` 행을 별도로 남겨 어떤 조건에서 막혔는지 감사할 수 있게 한다.

### 5-3. 설정 파일 구조
`config/settings.yaml`(저장소에 포함, 안전한 기본값) + `config/settings.local.yaml`(`.gitignore`, 사용자별 덮어쓰기). **`enable_live`와 `live_allowlist`는 local 파일에서만 인식**한다.
```yaml
quota:            { daily_limit_units: 6000, warn_ratio: 0.8, update_cost: 50, read_cost: 1, analytics_cost: 1 }
cadence:          { min_interval_hours: 72, max_changes_per_video: 3, min_impressions_before_rechange: 1000, max_live_changes_per_day: 3 }
validation:       { key_phrase_chars: 20, recommended_max_chars: 40, hard_max_chars: 100, warn_match_ratio: 0.5, block_match_ratio: 0.25 }   # 임계값은 가정
sequential_mode:  { enabled: false, evaluation_window_days: 14 }
retention:        { logs_days: 365, history_days: 365 }
live:             { enable_live: false, live_allowlist: [] }      # local 파일에서만 유효
approval:         { ttl_hours: 24 }
exclusions:       { shorts_max_seconds: 180 }      # Shorts 가능성 판별 기준(가정, 순차 교체 모드 제외 근거로만 사용)
```
`.env`: `YT_CLIENT_SECRET_PATH`, `YT_TOKEN_DIR`(기본 `%LOCALAPPDATA%\ytitle\tokens`), `YT_DATA_DIR`(기본 `data`).

### 5-4. 비용·임계값
외부 API는 무료 쿼터 안에서 사용(비용 0원). 50개 영상 전체 조회는 약 4 units, 제목 1건 적용은 약 50 + 조회 2 units. 하루 상한 6,000 units이면 이론상 100건 이상 적용 가능하지만 교체 제한(72시간·3회)이 더 먼저 걸린다. **비용이 통제 범위를 벗어났다고 보는 기준**: 일일 사용량이 상한의 80%를 넘는 날이 일주일에 2번 이상이면 사용량 점검.

## 6. 보안 설계 원칙 (`SEC-xxx`)

### 6-1. 02에서 받은 SEC-001~013의 설계 반영
| ID | 설계 |
|---|---|
| SEC-001 | 기본 dry-run, 쓰기 3중 조건(5-2의 1·2·7단계), `apply`/`rollback`만 쓰기 경로이며 모듈 한 곳(`live_guard.py`)에서만 `videos.update`를 호출 |
| SEC-002 | 5-2의 4단계, 선예약 후 호출 |
| SEC-003 | `retry.py` 단일 구현 |
| SEC-004 | `limits.py` |
| SEC-005 | 재조회한 snippet 전체 + 제목만 교체, 백업은 DB 저장(`backup_snippet_json`) |
| SEC-006 | `title_changes` + `rollback` |
| SEC-007 | 코드 금지: `requests`/`urllib`로 Studio·유튜브 웹 접근 금지, 브라우저 자동화 패키지 의존 금지. 9단계가 의존성·코드를 점검 |
| SEC-008 | 로그 마스킹 필터(`ya29.` `1//` Bearer, `client_secret` 값, 긴 base64 토큰 패턴), 예외 메시지도 같은 필터 통과, 토큰 파일은 사용자 프로필 폴더에 저장 |
| SEC-009 | 5-2의 6단계 |
| SEC-010 | 5-2의 13단계 |
| SEC-011 | `candidates.py`: 경로는 `candidates/` 하위로만 해석(resolve 후 상위 경로 확인), `video_id` 정규식, 크기·후보 수 상한, 필드 타입 검증 |
| SEC-012 | `live_allowlist`(빈 목록이면 모두 거부) |
| SEC-013 | 2-1 |

### 6-2. 3단계에서 새로 등록하는 SEC (위협 모델 근거)
| ID | 원칙 | 위협 |
|---|---|---|
| SEC-014 | 승인 파일은 `plan_hash`(영상 ID·후보 ID·새 제목·이전 제목·현재 snippet 해시)에 바인딩되고, 만료(기본 24시간)되며, **한 번 사용하면 `used=true`**로 재사용을 막는다 | T-03 |
| SEC-015 | 읽기 토큰과 쓰기 토큰을 분리 저장하고, 쓰기 토큰은 `apply`/`rollback` 실행 순간에만 로드한다. `auth --revoke`로 로컬 삭제 | T-08 |
| SEC-016 | 안전한 파싱: `yaml.safe_load`만 사용, JSON/CSV 크기 상한, CSV는 값을 실행·평가하지 않고 숫자·문자열로만 읽음 | T-11 |
| SEC-017 | 검증 때 사용한 금칙어 사전의 해시를 후보 검증 기록에 저장하고, 사전이 바뀐 사실을 리포트에 표시 | T-10 |
| SEC-018 | 모든 SQL은 파라미터 바인딩(문자열 결합 금지). 제목·설명 등 외부 문자열은 값으로만 전달 | T-12 |
| SEC-019 | 화면·로그에 출력하는 외부 문자열(제목·설명·사유)은 제어 문자(ANSI 이스케이프 포함)를 제거/이스케이프한다 | T-13 |
| SEC-020 | `apply`와 `rollback`은 **1회 실행에 영상 1건만** 처리하고(일괄 적용 없음), 하루 live 적용 건수 상한(`max_live_changes_per_day`, 기본 3)을 둔다 | T-16 |
- AI/LLM 관련(규칙 J): 프로그램이 LLM을 호출하지 않으므로 **프롬프트 인젝션·출력 렌더링·도구 권한·LLM 비용 항목은 해당 없음(사유: LLM 호출 없음, DEC-003)**. 후보 `source` 필드로 AI 보조 여부만 기록한다(POL-004). LLM 호출을 추가하면 규칙 J와 Tier를 재평가한다.
- 개인정보: 채널 소유자 본인의 영상 메타데이터만 다루며 시청자 개인정보(댓글 등)는 수집하지 않는다. 수집 최소화=필요 필드만 저장, 보관 365일, 삭제=`purge`, 제3자 제공 없음. 개인정보 영향평가·ISMS-P 대상 여부는 [확인 필요]이나 개인 도구라 해당 가능성이 낮다.
- 접근 권한: 로컬 사용자 계정 권한에 의존. 토큰 폐기=`auth --revoke` + 구글 계정 보안 설정에서 앱 제거.

## 7. 운영/관측성
- **환경 분리**: dev/staging/prod 서버 없음(로컬 CLI). 대신 "테스트 영상 vs 실제 영상"을 `live_allowlist`로 분리하고, 자동 테스트는 항상 mock만 사용(실제 API 호출 금지).
- **SLO/가용성**: 해당 없음(사유: 상시 서비스가 아닌 수동 실행 CLI). 대신 NFR-010(복구 목표)과 NFR-003(쿼터)을 운영 목표로 한다.
- **IaC**: 해당 없음(사유: 로컬 설치형). 재현성은 `requirements.txt` 버전 고정과 `pyproject.toml`로 확보.
- **배포 전략(릴리즈)**: 로컬 설치(`pip install -e .`)와 버전 태그. **실제 채널 변경은 단계적**: ①비공개 테스트 영상 1개 → ②본인이 지정한 공개 영상 1개 → ③소수 → ④확대. **중단 기준**: SEC-010 검증 실패 1건, 롤백 검증 실패 1건, 정책 경고 알림 수신, 쿼터 상한(100%) 도달 중 하나라도 발생하면 중단하고 원인 분석(규칙 F).
- **로깅·알림**: 알림 채널 없음(해당 없음: 1인 수동 실행, 콘솔 경고로 충분). 로그는 `data/logs/`, 보관 365일, 감사 대상=모든 쓰기 시도.
- **백업/복구**: 5-1 NFR-010. 인프라 장애 개념 없음(해당 없음).
- **롤백 전략**: `rollback` 명령 + DB 백업 사본 + 버전 태그 복귀.

## 8. 기획서 대비 트레이드오프와 미해결 사항
1. **02와 달라진 점**: ①`approve` 명령 추가, ②`timeutil`·`platform_utils`·`textsafe`·`ui` 공통 모듈 추가(WU-0), ③`rollback`의 쓰기 실행부를 WU-5로 이동, ④NFR-010·011 및 SEC-014~020 신규 등록, ⑤설정을 `settings.yaml` + `settings.local.yaml`로 계층화(`enable_live`는 local에서만 유효), ⑥토큰 저장 위치를 프로젝트가 아닌 사용자 프로필로 변경(03 가이드의 `.env` 예시를 이에 맞춰 수정).
2. **Windows 검증의 한계**: 이 클라우드 환경은 Linux이며 Python 3.11·3.12·3.13으로 테스트한다. 로직 테스트는 여기서 가능하지만 **Windows 고유 동작(파일 권한, 콘솔 인코딩, 경로 구분자, 실행 정책)은 이 환경에서 검증할 수 없다**. 해당 테스트는 `@windows_only`로 표시해 8·10단계에서 **"미수행(Windows 필요)"**으로 기록하고, 사용자가 PowerShell에서 RUNBOOK의 점검 절차로 확인한다.
3. **미해결(1단계 CONDITIONAL)**: `videos.update`의 정확한 쿼터·필요한 최소 scope·Analytics 지표명은 모두 설정값/후보로 설계했다. 원문 확인 결과가 다르면 설정값 조정 또는 규칙 F.
4. **Shorts 판별**: API로 Shorts 여부를 직접 알 수 없어 `duration_sec ≤ 180`이면 "Shorts 가능성"으로 보수적으로 취급한다(기준 시간은 [확인 필요]). 이 판별은 순차 교체 모드에서만 제외 근거로 쓴다.
5. **자동 롤백 미채택**: 검증 실패 시 자동으로 `videos.update`를 다시 호출하지 않는다(SEC-001 위반 소지). 대신 경보와 명령 안내를 한다. 비용은 사람의 빠른 대응이 필요하다는 점.
6. **로컬 공격자는 범위 밖**: 같은 PC의 악성코드가 승인 파일을 위조하거나 토큰을 읽는 위협은 완화(SEC-008, 014, 015)할 뿐 완전히 막지 못한다. 잔여 위험으로 수용 여부를 `threat_model.md` 5장에서 사용자에게 묻는다.
7. **레퍼런스 대비 비교 반영 여부**: 02에 레퍼런스 비교가 없어(해당 없음) 참조하지 않았다.

## 9. 구현 단위(WU-0~6)별 완료 기준과 검증 방법 (v1 YT-04 요구)
| 단위 | 완료 기준 | 검증 방법 (실행 명령은 5단계에서 확정) |
|---|---|---|
| WU-0 | 설치 후 `python -m ytitle --help`가 **등록된 서브커맨드를 자동 탐색해 표시**(WU-0 시점에는 `purge`, 이후 단위가 끝날 때마다 추가되어 8단계 시점에 9개 전체). 설정 로드·마스킹·재시도·DB 생성·마이그레이션·textsafe·timeutil(PT 날짜 경계)·`purge` 동작. 기본값이 dry-run | `pytest` 전체 통과, `--help` 출력 확인(자동 탐색 동작: 임시 명령 파일을 추가하면 목록에 나타남), 재시도 횟수·백오프 간격 테스트, 로그에 가짜 토큰 문자열이 마스킹됨, PT 날짜 경계(서머타임 전후) 테스트 |
| WU-1 | `auth --read/--write/--revoke` 동작. 읽기·쓰기 토큰 분리 저장. 만료·재인증 감지 시 한국어 안내 | mock 기반 테스트: 정상 로그인, 토큰 만료, 토큰 폐기, 토큰이 로그·예외에 없음. **실제 로그인은 사용자 수행**(절차 문서 `03_manual_setup.md` 8장) |
| WU-2 | `fetch`가 영상·snippet·지표를 DB에 저장. 쿼터 기록·상한 검사. 쓰기 API 호출 코드 없음 | mock 응답 테스트(50개 배치, 페이지네이션), `quota_usage` 기록 확인, 코드 검색으로 `videos.update` 호출 부재 확인 |
| WU-3 | 후보 읽기·검증·리포트. 차단 유형 5종, 경고 유형 3종, 엄격 모드, 우회 표기 정규화, 길이(유니코드) 계산, `<` `>` 불가 | 통과·차단 케이스 각 10개 이상(한글 포함), 우회 표기 케이스, 100건 5초 이내, 커버리지 90%+ |
| WU-4 | `plan`이 diff와 `plan_hash` 출력(호출 없음). snippet 전체 백업, 이전 값 보존 본문, 교체 제한 검사, 롤백 계획과 DB 처리 | `description`·`tags`·`categoryId` 보존 테스트, 롤백 DB 테스트, 72시간·횟수·최소 노출 테스트, 승인 없는 쓰기 호출 0건 |
| WU-5 | `approve`·`apply --live` 게이트 14단계 전부 동작. 롤백 실제 호출 활성화. 허용 목록 빈 경우 전부 거부 | 게이트 조건 하나씩 빠뜨린 케이스 각각 거부 테스트(mock 호출 0회), 승인 파일 재사용·만료·해시 불일치 거부, 재조회 제목 불일치 중단, 적용 후 검증 실패 경보 |
| WU-6 | 변경 전후 비교 리포트, 순차 비교 한계 문구, CSV 가져오기(헤더 매핑) | 샘플 데이터 리포트 생성, 한계 문구 포함, CSV 인코딩(UTF-8·CP949) 테스트 |
| 8단계 | 전체 시나리오(fetch→validate→plan→approve→apply(mock)→rollback) 통과, `traceability` 커버리지 100% | E2E mock 시나리오, 회귀 스위트 |
| 9단계 | SEC-001~019 항목별 점검 | 코드·의존성·로그 스캔, `pip-audit` 등 취약점 점검(도구 선정은 5~9단계에서 근거와 함께) |
| 10단계 | 깨끗한 venv 설치 스모크 (부록 A CLI 변형) | 새 venv에 설치→`--help`, 이전 태그 복귀 리허설. **Windows 실측은 사용자 수행(미수행으로 기록)** |
| 11단계 | RUNBOOK(일상 사용, 장애 대응: 쿼터 초과·토큰 만료·오적용 롤백, 점검 체크리스트), 사용자 매뉴얼. 최종 점검=완료 기준 대조표 + 미해결 [확인 필요] 목록 | 문서 검증 로그 2회+ |
| 12단계 | ①릴리즈 승인 ②첫 실제 수정 승인(규칙 E). 검증 절차: 적용→제목 반영 확인→설명·태그 보존 확인→롤백 확인 | 비공개 테스트 영상에서 사용자 승인 후 실행 |
| 13단계 | 즉시 검증(S10)과 롤백 확인. 성과 비교는 72시간+ 후 수집 예정(미수행으로 기록) | |

## 10. 요구사항 ↔ 설계 매핑 (traceability 설계 매핑 컬럼의 원본)
| ID | 설계 § |
|---|---|
| FR-001 | 4-3 EVT-201, 6-1 SEC-011 |
| FR-002 | 1-1 validator.py, 9 WU-3, 7장 제목 규칙 → `04` 및 02 §4-1 |
| FR-003 | 4-3 EVT-204, 6-2 SEC-017 |
| FR-004 | 4-3 EVT-201(description_excerpt), 3-1 videos |
| FR-005 | 4-1 EVT-003, `04_ux_design.md` SCR-002 |
| FR-006 | 4-2 EVT-101~103 |
| FR-007 | 4-2 EVT-105, 4-3 EVT-203 |
| FR-008 | 4-1 EVT-004, 5-2 |
| FR-009 | 5-2 9단계, 3-1 title_changes |
| FR-010 | 3-1 title_changes |
| FR-011 | 4-1 EVT-007 |
| FR-012 | 5-2 |
| FR-013 | 4-1 EVT-005, 4-3 EVT-202, 6-2 SEC-014 |
| FR-014 | 5-3 cadence, 5-2 5단계 |
| FR-015 | 3-1 quota_usage, 5-3 quota, ADR-008 |
| FR-016 | 4-1 EVT-001, ADR-004 |
| FR-017 | 4-1 |
| FR-018 | 4-1 EVT-008 |
| FR-019 | 5-3 sequential_mode, 3-2 |
| FR-020 | 3-1 run_logs, 5-1 NFR-011 |
| NFR-001 | 5-1 |
| NFR-002 | 5-1 |
| NFR-003 | 5-1, 5-3 |
| NFR-004 | 4-2 |
| NFR-005 | 5-1, 9 WU-3 |
| NFR-006 | 5-1, 9 |
| NFR-007 | 4-1, `04_ux_design.md` |
| NFR-008 | 3-1, 5-1 |
| NFR-009 | 3-4 |
| NFR-010 | 5-1, 7 |
| NFR-011 | 5-1, 7 |
| POL-001 | 4-3 EVT-201 topic, 3-2 |
| POL-002 | `04_ux_design.md` 면책 문구 규칙 |
| POL-003 | 5-3 sequential_mode, 8-4 |
| POL-004 | 4-3 EVT-201 source |
| SEC-001 | 5-2, 6-1 |
| SEC-002 | 5-2, 6-1 |
| SEC-003 | 4-2, 6-1 |
| SEC-004 | 5-2, 6-1 |
| SEC-005 | 5-2, 6-1 |
| SEC-006 | 3-1, 6-1 |
| SEC-007 | 6-1 (9단계 점검) |
| SEC-008 | 6-1 |
| SEC-009 | 5-2, 6-1 |
| SEC-010 | 5-2, 6-1 |
| SEC-011 | 6-1 |
| SEC-012 | 5-2, 5-3 |
| SEC-013 | 2-1 |
| SEC-014 | 6-2 |
| SEC-015 | 6-2 |
| SEC-016 | 6-2 |
| SEC-017 | 6-2 |
| SEC-018 | 6-2 |
| SEC-019 | 6-2 |
| SEC-020 | 5-2, 5-3, 6-2 |

## 11. 아키텍처 결정 (ADR) — `decisions.md`의 DEC와 상호 참조
| ADR | DEC | 결정 | 근거 | 되돌리기 |
|---|---|---|---|---|
| ADR-001 | DEC-013 | Python 3.12 + venv, 3.10+ 호환 | 사용자 기본값, 개발자 초보 | 쉬움 |
| ADR-002 | DEC-014 | SQLite(`sqlite3` 표준 모듈), 마이그레이션 번호제 | 사용자 기본값, 단일 사용자 | 중간(스키마 변경은 마이그레이션으로) |
| ADR-003 | DEC-015 | `argparse` + `commands/` 자동 탐색 | 의존성 최소, 단위별 파일 분리로 병렬 충돌 방지 | 쉬움 |
| ADR-004 | DEC-016 | OAuth 설치형 앱, 읽기·쓰기 토큰 분리, 토큰은 사용자 프로필 폴더 | 최소 권한, 저장소 유출 방지, Windows 파일 권한 한계 | 쉬움 |
| ADR-005 | DEC-017 | 쓰기 안전 설계 14단계(3중 조건+계획 해시 승인+허용 목록+재조회+사후 검증) | v1 안전장치와 위협 모델 | 쉬움 |
| ADR-006 | DEC-018 | 쿼터 날짜는 `America/Los_Angeles`, `zoneinfo`+`tzdata` | 1단계 c·3-5, Windows tzdata 필요 | 쉬움 |
| ADR-007 | DEC-019 | 후보는 파일 입력, 프로그램은 LLM 비호출 | 사용자 기본값(DEC-003), 규칙 J 비해당 | 중간(LLM 추가 시 규칙 J 재평가) |
| ADR-008 | DEC-020 | 쿼터 선예약 후 호출, 실패해도 차감 유지 | 보수적(상한 초과 방지) | 쉬움 |
| ADR-009 | DEC-021 | 공식 Google 클라이언트 라이브러리 사용 | 인증·재시도 오류 감소 | 쉬움 |
| ADR-010 | DEC-022 | 설정 계층(`settings.yaml`+`settings.local.yaml`), `enable_live`·허용 목록은 local에서만 유효 | 실수로 `enable_live=true`를 커밋·공유하는 사고 방지 | 쉬움 |

## 12. 변경 이력
| 일시 | 버전 | 변경 내용 | 사유 |
|---|---|---|---|
| 2026-10-10 | v0 | 초안 | 3단계 착수 |

## 13. ★ 사용자 승인 요청 (승인 게이트 a)
**DESIGN.md 검토 후 '진행'이라고 답해 주세요.** 특히 아래를 봐 주세요: ①5-2 쓰기 14단계(7장 운영의 단계적 적용), ②5-3 설정 구조, ③6-2 새 보안 요구 7개, ④8장의 한계(Windows 검증 불가, 자동 롤백 미채택, 로컬 공격자 범위 밖).
