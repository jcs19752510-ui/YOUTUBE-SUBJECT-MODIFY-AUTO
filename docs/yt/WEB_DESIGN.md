# 웹 전환 설계서 (WEB_DESIGN) — 유튜브 제목 웹

| 항목 | 내용 |
|---|---|
| 문서 상태 | **v4 (2026-10-11 11단계 대조 1차 반영; 본문 골격은 v2 2026-10-10) — 구현 결과(as-built)에 맞춰 개정한 압축판.** 원래는 1차 데모(M1) 구현용 속도 우선 설계(DEC-038)였고, 풀 설계서는 `DESIGN.md` **Part B**다. 두 문서가 다르면 Part B와 실제 코드가 기준이며, 아래 "변경 이력"(맨 끝)에 바뀐 곳을 표시했다. 6단계 독립 검증 대기 항목은 `DESIGN.md` 맨 위 표 참고 |
| 근거 | `웹프로그램으로수정요청.md`, DEC-032~042, 1단계 조사 조각 `docs/harness/_parallel/01-axis*.md`, 구현 노트 `docs/harness/units/web-WU-*-note.md`, 실제 코드(개정 근거) |
| 작성일 | 2026-10-10 |
| 읽는 사람 | 구현 담당(백엔드 2, 프런트 1, 인프라 1)과 채널 소유자 |
| 짝 문서 | `DESIGN.md` Part B(풀 설계서·ADR·편차·질문), `API.md`(엔드포인트 상세), `openapi.json`(앱 객체에서 추출한 스키마) |

## 0. 마일스톤
| 마일스톤 | 내용 | 라이브 위험 |
|---|---|---|
| **M1 (구현·자체 테스트 완료, 독립 검증 대기)** | **데모 모드** 웹 1차: 가짜 영상 200개, 모의 AI 제안, 기존 검증기, 승인, 배치 미리보기·모의 반영, 이력·롤백, 설정, 리포트. `web\scripts\start.ps1`(내부적으로 `docker compose`) 한 번으로 내 PC `http://127.0.0.1:8080` | **없음** — 유튜브·AI 호출 코드가 아예 연결되지 않음 |
| M2 | 구글 OAuth(데스크톱 앱 클라이언트, 읽기 전용 범위)로 내 채널 영상 실제 가져오기 **(코드 구현됨·가짜 구글 시험만, 실제 접속 미수행 — §12)** | 읽기만 |
| M3 | 쓰기 로그인·라이브 반영 코드는 **구현됨(가짜 구글 시험만, 실제 접속·실제 제목 변경 미수행 — §12)**. 실제 AI 어댑터는 **미구현**(서비스 미정). 실제 제목 변경은 테스트 영상 1개로 먼저, 사용자 승인 필수 | 사용자 승인 필수 |
| M4 | 통합·전체·보안·구동 검증 문서(7~11단계) 마무리, 풀 설계서 확정 | - |

## 1. 구성
```
브라우저(127.0.0.1:8080) ─▶ web(nginx 비루트: React 정적 + /api 프록시)
                               └▶ api(FastAPI) ──▶ db(PostgreSQL 17, internal 네트워크, 명명 볼륨)
                                  worker(같은 이미지, 다른 명령) ──▶ db
                                  migrate(같은 이미지, Alembic 1회, 소유자 계정) ──▶ db
```
- 상시 서비스 4개(web, api, worker, db) + 1회성 `migrate`(compose 서비스 5개). 기동 순서 `db healthy → migrate 성공 → api/worker → api healthy → web`. *(v2: 원문 "4서비스"에 migrate 명시)*
- 호스트 게시 포트는 `127.0.0.1:8080:8080`(web) **하나뿐**. api/worker/db는 호스트 포트 없음. `app` 네트워크는 `internal: true`이고, **web만 게시를 위해 비-internal `edge` 네트워크에 추가로 붙는다**(internal 전용 컨테이너는 호스트 게시가 안 되는 것으로 알려져 분리, internal 단독 게시는 시험하지 않음 — 편차 DV-W02). 구글·AI 통신이 필요한 M2·M3에서는 `compose.online.yaml`로 api/worker에만 외부 네트워크를 연다. *(v2 추가)*
- 저장소 레이아웃(신규): `web/backend/ytweb/`(백엔드 패키지), `web/frontend/`(Vite React TS), `web/docker/`(Dockerfile·nginx·db 초기화), `web/compose.yaml`, `web/scripts/*.ps1`. 기존 `src/youtube_title`은 **패키지로 설치해 재사용(복사 금지)**.
- 코어 재사용(복사 없이 `PYTHONPATH=/app/backend:/app/src`로 같은 소스, 순수 함수만): `youtube_title.validator.validate_file`, `youtube_title.candidates.CandidateFile/Candidate`, `youtube_title.banned_terms.load_dictionary`, `youtube_title.limits.evaluate_limits`(+`LimitFacts`), `youtube_title.updater.compute_plan_hash/validate_new_title/snippet_hash`, `youtube_title.config.load_settings`(정책 기본값 `config/settings.yaml`). sqlite3 직접 의존 모듈(`db.py`, `history.py`, `quota.py`, `live_guard.py`)은 재사용하지 않고 웹에서 PostgreSQL 기반으로 재구현한다(M3 의 실제 모드 안전장치는 포팅이 아니라 웹에 새로 구현했다: §12-4, §12-7).
- 스택(DEC-035, 실제 채택): FastAPI 0.143.0+Pydantic 2.14.0+Uvicorn 0.54.0, SQLAlchemy 2.1.4(동기)+Alembic 1.20.0+psycopg 3.3.6, **PostgreSQL 17**(DEC-041), React **19.3.0**+TypeScript 5.9.3+Vite 8.3.4+TanStack Query 5.104.1+**react-router-dom 7(HashRouter)**, nginx. *(v2: DEC-035의 "React 18, TanStack Router"는 실제와 달라 정정 — 편차 DV-W10)* 라이선스 확인은 `DESIGN.md` W2-1(psycopg는 LGPL-3.0).
- 시간: DB는 UTC(timestamptz). 일일 반영 건수 기준일은 KST 날짜, API 쿼터 기준일은 태평양 시간(기존 `limits._pt_day_bounds`와 같은 규칙). API 시각 출력은 UTC이며 `Z`/`+00:00` 표기가 섞인다(DV-W06). 상세 `DESIGN.md` W6.

## 2. 데이터 모델 (`web/backend/ytweb/db/models.py`가 원본)
**14테이블**: videos, suggestions, ai_runs, approvals, batches, batch_items, changes, quota_usage, metrics_snapshots, jobs, audit_log(추가 전용·해시 체인), settings_kv, sessions, idempotency_keys (모델 ↔ 마이그레이션 컬럼 대조 일치, `DESIGN.md` 부록 A-3). 핵심 제약:
- 한 제안(suggestion)은 동시에 진행 중인 배치 항목 1개만 가질 수 있다(부분 고유 인덱스).
- 한 영상에는 `planned` 상태 변경(changes)이 동시에 1개만 존재(부분 고유 인덱스) → 이중 반영 차단.
- 감사 로그는 앱 계정에 INSERT/SELECT만 허용(UPDATE/DELETE/TRUNCATE 회수), 각 행에 이전 행 해시를 포함(변조 탐지). *(v2: 해시 체인은 키 없는 SHA-256, 꼬리 절단은 탐지 못함 — DV-W08)*
- 승인(approvals)에는 HMAC `mac`·`used_at`(1회용)·`expires_at`이 있다. 서명 키는 DB가 아닌 `app_secrets` 볼륨의 `approval_hmac.key`. *(v2 추가)*
- 앱 계정은 DDL 권한 없음(마이그레이션 계정 별도). 모든 SQL은 ORM/파라미터 바인딩.

## 3. REST API 계약 (`/api/v1`, JSON, 한국어 메시지)
공통: 오류는 `application/problem+json` `{type,title,status,detail,code,hint}`(스택트레이스·경로 금지). 상태 변경(`POST/PUT/PATCH/DELETE`)은 쿠키 세션 + `X-CSRF-Token` + 허용 `Origin` 필수(세션 발급도 Origin 필수), 위험 동작(**배치 생성·배치 실행·롤백 3개**)은 `Idempotency-Key` 헤더 필수(같은 키 재전송=저장된 응답 재생, 다른 요청이면 422, 처리 중이면 409). 목록은 `?page=1&page_size=50`(최대 200, **초과는 422**) → `{items,total,page,page_size}`. 오류 코드·헤더 규약·예시 전체는 `API.md`, 엔드포인트 31개 대조는 `DESIGN.md` 부록 A-1. *(v2 보강)*

| 메서드 경로 | 설명 | 응답 |
|---|---|---|
| GET `/api/healthz` `/api/readyz` (nginx 경유, Host·세션 검사 없음) · api 컨테이너 내부는 `/healthz` `/readyz`도 응답(루트 경로는 nginx에서 404, DEF-7-006 조치) | 생존/준비(DB 연결만 — 구글·AI 상태는 M2·M3) | `{status:"ok"}` / `{status, db:"ok"\|"down", mode}` (DB 불가 시 503) |
| GET `/api/v1/auth/me` | 세션 확인(쿠키 없이도 호출 가능) | `{authenticated, pin_required, csrf_token\|null}` |
| POST `/api/v1/auth/session` | 세션 발급(Host·Origin·`Sec-Fetch-Site` 검증, PIN 설정 시 `{pin}`, 5회 실패 시 429 `pin_locked`) | `{csrf_token}` + `Set-Cookie ytw_session`(HttpOnly, SameSite=Strict, Path=/api, `Secure` 없음) |
| DELETE `/api/v1/auth/session` | 로그아웃 | 204 |
| GET `/api/v1/dashboard` | 홈 요약 | `{mode:"demo"\|"live", live_enabled:bool(실제 수정 3조건이 모두 맞을 때 true), google:{mode:"demo"\|"read",connected}, counts:{videos,excluded,suggested,approved,queued,applied}, today:{applied,cap}, quota:{used,limit,remaining,pt_date}, active_job, queue:{pending_items,next_run_date}}` |
| GET `/api/v1/videos` `?q,status,excluded,sort,order,page,page_size` | 영상 목록(서버측 필터·정렬) | Page<VideoSummary> |
| GET `/api/v1/videos/{video_id}` | 영상 상세 | VideoDetail |
| POST `/api/v1/videos/sync` | (데모) 가짜 영상 200개 시드/새로고침. 이미 진행 중인 같은 작업이 있으면 그 작업을 돌려줌 | 202 Job |
| POST `/api/v1/videos/{video_id}/suggestions` `{count?}` | AI(모의) 제안 생성+검증 | 201 Suggestion[] |
| POST `/api/v1/suggestions/generate` `{video_ids[], count?}` | 여러 영상 제안 생성 | 202 Job |
| GET `/api/v1/suggestions` `?video_id,status,result` | 제안 목록 | Page<Suggestion> |
| PATCH `/api/v1/suggestions/{id}` `{title}` | 사람이 제목 수정 → 재검증, 기존 승인 무효 | Suggestion |
| POST `/api/v1/suggestions/{id}/approve` `{approver}` | 승인(차단 판정·엄격 모드 경고면 409 `suggestion_blocked`, 제외 영상 409 `video_excluded`), plan_hash·HMAC 묶음, TTL 24h. 서버는 경고 사유 확인을 강제하지 않음(화면에서만, DV-W07) | Suggestion |
| POST `/api/v1/suggestions/{id}/reject` | 반려 | Suggestion |
| POST `/api/v1/batches` `{suggestion_ids[], note?}` + `Idempotency-Key` | 배치 초안+사전 점검 | 201 `{batch, precheck}` |
| GET `/api/v1/batches` · `/{id}` | 목록 · 상세(항목 상태) | Page<Batch> · Batch |
| POST `/api/v1/batches/{id}/execute` `{confirm_text}` + Idempotency-Key | 실행(`confirm_text == "실행 {n}건"`, 실제 수정 모드는 `"실제 실행 {n}건"`), 확정 시점에 항목을 전부 다시 점검(하나라도 어긋나면 409 `precheck_stale`), 일일 상한만큼 오늘, 나머지는 다음 날로 예약 | 202 `{batch, job}` |
| POST `/api/v1/batches/{id}/cancel` | 중지(남은 `pending` 항목 취소, 진행 중 항목은 완료까지, 초안도 취소 가능) | Batch |
| GET `/api/v1/jobs/{id}` | 작업 진행 | Job `{id,type,status,progress,total,error,result}` |
| GET `/api/v1/changes` `?video_id,batch_id,result` | 변경 이력 | Page<Change> |
| POST `/api/v1/changes/{id}/rollback` `{typed_video_id, approver}` + Idempotency-Key | 롤백(영상 ID 직접 입력 확인) | 201 Change |
| GET `/api/v1/reports/changes` `?video_id` | 전후 성과 비교(데이터 부족 명시, 원인 단정 금지 문구 포함) | `{items:[VideoReport], notes}` |
| GET `/api/v1/reports/export.csv` | CSV 내보내기 | text/csv |
| GET `/api/v1/audit` | 감사 로그(읽기 전용, 최신순). 호출마다 체인 전체를 검증 | Page<AuditEntry> + `chain_ok:bool` |
| GET/PATCH `/api/v1/settings` | 안전 설정만 변경(`daily_apply_cap` 1~20 기본 10, `suggestions_per_video` 1~5 기본 3, `tone` 문자열 최대 5개·각 20자, `pin` `{action:"set"\|"clear",new_pin?,current_pin?}`). 그 외 키는 400 `setting_not_allowed`(**라이브 허용·허용 영상 목록은 API로 변경 불가**, 읽기 전용 표시) | Settings `{daily_apply_cap,suggestions_per_video,tone,pin_enabled,mode,read_only{enable_live,live_allowlist,note}}` |
| GET `/api/v1/google/status` | 구글 연결 상태 | `{mode:"demo"\|"read", connected, client_ready, message, last_error, write_connected, live_write_enabled, live_allowed_count, live_write_ready}` (M2·M3, §12) |
| POST `/api/v1/google/connect` · `/connect-write` | 읽기 / 제목 수정 권한 구글 로그인 주소 발급(CSRF 필요) | `{auth_url}` |
| GET `/api/v1/google/callback` (OpenAPI 제외) | 구글에서 돌아오는 이동. 세션 대신 1회용 state+PKCE 로 보호 | 303 `/#/` |
| POST `/api/v1/google/disconnect` | 읽기·쓰기 로그인 정보 삭제(CSRF 필요) | `{connected:false}` |

주요 스키마(필드 대조 결과는 `DESIGN.md` 부록 A-2): **VideoSummary** `{video_id,title,privacy_status,duration_sec,is_short,excluded,exclusion_reasons[],workflow_status("none|suggested|approved|queued|applied|rolled_back"),suggestion_count,last_change_at,views}` / **Suggestion** `{id,video_id,title,evidence,source,topic,strict,validation_result("pass|warn|block"),reasons[{code,severity,message}],length,match_ratio,status,plan_hash,approval{approver,approved_at,expires_at}|null,created_at}` / **VideoDetail** = VideoSummary + `{description_excerpt,suggestions[],changes[],limits{allowed,reasons[],next_allowed_at},preserved{category_id,tags[],default_language,default_audio_language,description_chars}}` *(v2: `preserved` 추가)* / **Change** `{id,video_id,video_title,change_type,previous_title,new_title,result,mode,approver,applied_at,verified_at,error_code,rollbackable,batch_id}` / **Batch** `{id,status(draft|queued|running|paused|done|cancelled — paused는 M1 미사용, failed 없음),note,created_at,executed_at,counts{pending,running,success,failed,skipped,cancelled},items[BatchItem],precheck?}` *(v2: `precheck`는 상세·생성·실행 응답에서만 채움, 목록은 `items:[]`·null)* / **BatchItem** `{id,suggestion_id,video_id,video_title,previous_title,new_title,seq,scheduled_date,status,skip_reason,change_id}` / **precheck** `{item_count,estimated_units,daily_cap,quota_remaining_units,schedule[{date,count}],warnings[],blocked[{suggestion_id,reason,code?,batch_id?}],confirm_text,notice}`. **Job** `{id(UUID),type(videos.sync|suggestions.generate|batch.execute),status(queued|running|succeeded|failed|cancelled),progress,total,error,result}`.

## 4. 동작 규칙 (기존 안전장치 이식)
1. **M1은 데모 모드뿐**: `YTWEB_MODE=demo` 고정. 기본 유튜브 게이트웨이는 `MockYouTubeGateway`(`videos` 테이블이 곧 "유튜브")이고, M3 에서 실제 수정 3조건이 맞을 때만 쓰는 `LiveYouTubeGateway`(`youtube/live_write.py`)와 선택 로직(`domain/live_gateway.py`)이 추가됐다(§12). AI는 `MockSuggester`(결정적 한국어 템플릿, 일부러 경고·차단 후보 포함)만 존재하며 어댑터 인터페이스(`TitleSuggester`)는 실서비스 교체 가능하게 정의.
2. **승인**: 승인은 `plan_hash`(영상 ID·후보 ID·이전/새 제목·snippet 해시)와 HMAC 서명에 묶이고 1회용이며 TTL(기본 24시간, `approval.ttl_hours`) 후 만료. 제목 수정·영상 변경 시 무효. **만료 판정 시각은 "배치 실행 확정 시각"**(여러 날에 걸친 배치가 둘째 날부터 전부 건너뛰는 것을 막기 위함, DEC-042 D3 — M3에서 재평가, DV-W11). *(v2: 판정 시각 명시)* 차단(block) 판정은 승인 불가, 경고(warn)는 사유 확인 후 승인 가능(엄격 모드 주제는 경고도 차단 — 기존 검증기 규칙 그대로).
3. **한도**: 하루 반영 건수 `daily_apply_cap`(기본 10, 최대 20)과 배치당 최대 50건 두 겹. 영상별 재변경 간격 72시간, 영상당 최대 3회, 최소 노출수 1000(`youtube_title.limits.evaluate_limits`; 데모 모드에서는 '재변경 최소 노출수'를 0 으로 낮춰 판정하도록 **코드에 반영됨** — `domain/common.py` `Env.build`. 72시간 간격·영상당 3회 제한과 리포트의 '데이터 부족' 기준은 그대로). API 쿼터는 호출 전 **3행(재조회+갱신+검증 재조회=52단위) 일괄 예약**(`reserved`→`ok|failed`, 전부/전무), 일일 한도 기본 6,000단위의 80%에서 경고(기존 설정). 제외 영상(Shorts·비공개·아동용·예약)은 제안·승인·배치·반영 4곳에서 차단.
4. **배치 실행(워커)**: `execute` → 항목에 `scheduled_date` 배정(오늘 남은 상한만큼 오늘, 이후 날짜는 상한씩). 워커는 `scheduled_date <= 오늘(KST)`인 `pending` 항목을 **오늘 남은 상한 안에서만** 처리한다(PC가 꺼져 있다 켜져도 놓친 예약을 몰아서 실행하지 않음). 항목 처리 = ①승인 유효·해시 일치 ②한도 ③쿼터 예약 ④실행 직전 재조회(이전 제목 변동 시 중단) ⑤(모의) 갱신 ⑥재조회 검증(제목 일치, description·tags·categoryId 등 보존) ⑦changes 기록. 어느 단계든 실패하면 해당 항목만 `failed|skipped`로 기록하고 이중 반영을 막는다. 행 잠금(`FOR UPDATE SKIP LOCKED`)으로 워커 중복 처리 방지, 재시작 후 `running`으로 남은 항목은 재조회로 상태 확정 후 정리.
5. **롤백**: 대상 영상의 `typed_video_id` 입력 일치 필요, 해당 변경 이후 다른 변경이 있으면 거부(기존 `plan_rollback` 규칙), 백업 snippet **전체** 기준 복원, 결과 재조회 검증. 쿼터는 쓰지만 교체 한도(간격·횟수·하루 상한)는 적용하지 않는다. 사후 검증 불일치는 변경 `success`+`error_code=verify_failed`·항목 `failed`로 알리고 자동 롤백은 하지 않는다(DV-W12). *(v2 보강)*
6. **감사 로그**: 세션 발급·거부·삭제, 설정 변경, 영상 새로고침, 제안 생성·수정·승인·반려, 배치 생성·실행·취소·항목 실패/복구, 반영, 롤백을 모두 기록(비밀·PIN·본문 전체는 제외).

## 5. 보안 (M1에 반드시 포함)
Host 허용 목록(`127.0.0.1:8080`, `localhost:8080`) · Origin 정확히 일치 + `Sec-Fetch-Site`가 있으면 same-origin만(상태 변경·세션 발급) · 쿠키 세션(HttpOnly, SameSite=Strict, `Secure` 없음) + CSRF 토큰 · 보안 헤더(nginx: CSP `default-src 'self'`에 `style-src-attr 'unsafe-inline'`·`img-src data:` 예외, `frame-ancestors 'none'`, `X-Content-Type-Options`, `Referrer-Policy: same-origin`, `Permissions-Policy`, COOP/CORP) · OpenAPI 문서(`/docs`)는 `YTWEB_ENABLE_DOCS=1`일 때만(개발 프로필 없음, DV-W03) · 요청 크기·속도 제한 · 로그 마스킹 · DB 비밀번호는 secrets 파일 · 컨테이너 비루트·`read_only`·`cap_drop: ALL`·`no-new-privileges`·자원 상한 · 외부 CDN 금지 · `dangerouslySetInnerHTML` 금지 · 입력은 Pydantic 검증. 위협 모델 STRIDE 갱신은 M4에서 확정(DEC-038) — 입력 목록은 `DESIGN.md` W9-6(특히 PIN이 꺼져 있으면 같은 PC의 다른 프로그램이 세션을 얻을 수 있음). S-W 요구별 구현 위치는 `DESIGN.md` W9-1.

## 6. 화면 (M1, PC 우선, 최신 Chrome/Edge)
홈(오늘 할 일·사용량·대기열·상태) / 영상 목록(검색·필터·정렬·체크박스·가상 스크롤 아님이면 페이지네이션 허용) / 영상 상세(현재 제목, AI 제안 생성, 검증 결과, 변경 전후 비교, 수정·승인·반려) / 배치(선택 → 사전 점검 → 확인 문구 → 실행, 진행률·중지) / 이력·롤백 / 성과 리포트 / 설정 / 상단 모드 띠(서버가 알려 준 상태에 따라 "데모 모드 — 유튜브에 아무것도 전송되지 않습니다" · "구글 연결됨(읽기) — 제목은 바뀌지 않습니다" · "실제 수정 모드 — 허용된 영상의 제목이 실제 유튜브에서 바뀝니다", "dry-run"은 "미리보기"로 표기) / 모든 화면 바닥글의 면책·AI 안내 / 배치 실행 화면의 A/B 테스트 아님 확인란과 [초안 버리기]. 디자인 토큰(색·간격·타이포)을 한 파일에 정의, 한국어 문구는 한 파일(`ko.ts`)에서 관리, 키보드 조작·포커스 표시·상태 색 외 아이콘/텍스트 병기.

## 7. 작업 단위 (M1 — 4개 모두 구현 완료, 독립 검증 대기)
| WU | 담당 | 범위 | 파일 소유 범위(겹치지 않음) |
|---|---|---|---|
| W-BE-A | 백엔드 기반 | 앱 팩토리, 설정, 보안(Host/Origin/세션/CSRF/속도 제한), 오류(problem+json), 멱등성, 감사 해시 체인, Alembic 초기 마이그레이션(models.py 기준), 헬스·인증·설정·감사 라우터, 작업(jobs) 큐 프레임워크와 워커 진입점 | `ytweb/core/`, `ytweb/app.py`, `ytweb/routers/{health,auth,settings,audit}.py`, `ytweb/worker.py`, `alembic/`, `tests/core/` |
| W-BE-B | 백엔드 도메인 | 데모 시드, 모의 AI·게이트웨이, 제안+검증, 승인, 한도·쿼터, 배치(사전 점검·예약·실행 서비스), 변경·롤백, 리포트, 대시보드 서비스+라우터 | `ytweb/domain/`, `ytweb/ai/`, `ytweb/youtube/`, `ytweb/routers/{dashboard,videos,suggestions,batches,changes,reports,jobs,google}.py`, `tests/domain/` |
| W-FE | 프런트 | 8개 화면, API 클라이언트(계약 기준 타입), 디자인 토큰, 오류·로딩·빈 상태, 접근성 기본, Vitest+RTL | `web/frontend/` 전체 |
| W-INF | 인프라 | Dockerfile 3종(api/worker 공용, web), nginx 설정, compose, DB 초기화(역할 분리·권한), secrets 생성 스크립트, `start/stop/status/logs/backup/restore.ps1`, `.dockerignore`, 한국어 시작 안내 | `web/docker/`, `web/compose.yaml`, `web/scripts/`, `web/README.md`, `.dockerignore` |
`ytweb/db/models.py`, `ytweb/db/session.py`, `ytweb/config.py`는 설계 담당(오케스트레이터)이 먼저 작성해 W-BE-A/B가 읽기만 한다(수정 필요 시 오케스트레이터에 요청). 확정된 작업 단위 표와 공유 파일 목록은 `DESIGN.md` W1-3.

## 8. 테스트 방침
- 백엔드: pytest. 단위·서비스 테스트는 SQLite(JSON/인덱스 variant)로 빠르게, **PostgreSQL 전용 동작(부분 고유 인덱스, SKIP LOCKED, 권한)은 PG가 있을 때 돌리는 `@pytest.mark.postgres` 테스트**로 분리. 클라우드에 PG가 없으면 해당 테스트는 "미수행(사유)"로 결과서에 기록하고 PASS로 세지 않는다.
- 프런트: Vitest + React Testing Library + 키 화면 접근성(axe). 브라우저 자동화 도구는 도입하지 않는다(DEC-034). 단, 클라우드에 사전 설치된 Chromium으로 개발 중 화면 캡처 확인은 한다(저장소 의존성 아님).
- 인프라: `docker compose config` 검증, 정적 점검(루트 사용자·포트 게시·비밀 포함 여부) 테스트 스크립트. 컨테이너 실기동은 **클라우드 Linux 엔진에서 실측**(DEC-039: 이미지 3종 빌드·compose 전체 healthy·권한·포트·백업→복원), **Windows Docker Desktop·PowerShell 5.1은 사용자 PC 확인 필요**(`web/README.md` §8). *(v2: DEC-039로 정정)*
- 결과(구현 노트 기준, 독립 검증 전): 백엔드 605 통과/8 xfail(PG 포함), 프런트 95, 인프라 정적 35 통과/1 건너뜀.
- 모든 작업 단위: 단위 노트 + 결과서(`templates/test-report-template.md` 전 섹션) + 검증 로그(최소 2회, 변이 점검 포함). 결과서는 `docs/harness/units/web-<WU>-test.md`.

## 9. 사용자 확인 대기 항목
*(v2)* 전체 질문 목록(Q-W01~Q-W18, 선택지·권장안 포함)은 `DESIGN.md` Part B **W13**으로 옮겼다. 기존 항목은 그대로 유효하다: Q-3 일일 상한 기본 10건 해석 / Q-8 브라우저 자동화 미도입 해석 / X-2 보류 항목(WU-5 질문 5가지, UI 이상 6건, 금칙어 사전 검토 등)을 웹에서 어떻게 둘지(Q-W01, Q-W02, Q-W04) / 다크 모드 필요 여부 / 포트 8080 사용 가능 여부(Q-W17).

## 10. 백엔드 공용 인터페이스 (W-BE-A가 먼저 제공, W-BE-B는 이것만 임포트한다)
W-BE-A는 **작업 시작 후 가장 먼저** 아래 모듈을 이 시그니처대로 만든다(내부 구현은 자유, 시그니처 변경 금지). W-BE-B는 도메인 서비스(`domain/`, `ai/`, `youtube/`)를 먼저 만들고 라우터는 마지막에 만든다. `core`가 아직 없으면 `ytweb/core` 호출 부분만 인터페이스 그대로의 임시 대역(tests/conftest)으로 시험한다.
```python
# ytweb/core/errors.py
class ProblemError(Exception):            # RFC 9457 problem+json 으로 변환됨(핸들러는 app.py 에서 등록)
    def __init__(self, status: int, code: str, title: str, detail: str = "", hint: str = ""): ...
# ytweb/core/deps.py  (FastAPI 의존성)
def get_session() -> Iterator[Session]                 # 요청당 1세션, 정상 종료 시 commit, 예외 시 rollback
def get_web_settings() -> WebSettings                  # ytweb.config
def get_policy() -> youtube_title.config.Settings             # config/settings.yaml 정책(+웹 settings_kv 덮어쓰기: daily_apply_cap 등은 아래 함수로)
def get_clock() -> Callable[[], datetime]              # tz-aware UTC now (테스트에서 대체 가능)
def require_session(...) -> SessionInfo                # 유효 쿠키 세션 필요(GET용)
def require_csrf(...) -> SessionInfo                   # 세션 + X-CSRF-Token + Origin/Host 검증(상태 변경용)
# ytweb/core/audit.py
def record(session: Session, *, actor: str, action: str, target_type: str | None = None, target_id: str | None = None, detail: dict | None = None, now: datetime) -> AuditLog   # 해시 체인에 한 줄 추가(같은 트랜잭션)
def verify_chain(session: Session) -> bool
# ytweb/core/idempotency.py
def run_idempotent(session: Session, *, key: str | None, route: str, request: dict, now: datetime, handler: Callable[[], tuple[int, Any]], required: bool = True) -> tuple[int, Any]  # key 없으면 required 시 400 `idempotency_key_required`; 같은 key+같은 요청이면 저장 응답 재생, 같은 key+다른 요청이면 422 `idempotency_key_reuse`
# ytweb/core/jobs.py
def enqueue(session: Session, *, type: str, payload: dict, total: int = 0, now: datetime) -> Job
def register_handler(type: str, fn: Callable[[sessionmaker, Job], dict | None]) -> None   # 워커가 호출, 반환값은 job.result
def update_progress(session: Session, job_id: str, *, progress: int, total: int | None = None) -> None
# ytweb/core/settings_store.py
def get_web_setting(session: Session, key: str, default: Any = None) -> Any
def effective_daily_cap(session: Session, policy: Settings) -> int        # settings_kv 'daily_apply_cap' 없으면 10
# ytweb/core/clock.py
def kst_today(now: datetime) -> date           # Asia/Seoul 날짜
def pt_date(now: datetime) -> date             # America/Los_Angeles 날짜
```
*(v2: 구현에서 추가된 공개 항목 — `deps.get_idempotency_key`, `deps.verify_same_origin`, `jobs.claim/complete/fail/requeue_stale/process_next`, `settings_store.set_web_setting/delete_web_setting`, `app.create_app(settings, *, clock, router_modules, rate_limits, time_fn)`, `app.app_from_env()`, `domain.batches.run_due_items/recover_running_items`. 시그니처 변경은 없음.)*
라우터 모듈 규약: 각 라우터 파일은 `router = APIRouter(prefix="/api/v1/...")` 를 노출하고 `app.py`가 자동 포함한다(W-BE-A의 `app.py`는 `ytweb.routers.*` 중 `router` 속성이 있는 모듈을 모두 include). 상태 변경 엔드포인트는 `Depends(require_csrf)`, 조회는 `Depends(require_session)`.
작업(jobs) 처리 유형: `videos.sync`, `suggestions.generate`, `batch.execute`. 워커 프로세스는 ① due 작업 처리 ② 배치 항목 스케줄러 틱(W-BE-B의 `ytweb.domain.batches.run_due_items(session_factory, now)`)을 주기적으로(2초) 호출한다(W-BE-A가 `worker.py`에서 이 함수를 임포트해 호출, 없으면 건너뜀). 기동 직후 `recover_running_items(stale_after=0)`를 1회 호출해 비정상 종료로 남은 `running` 항목을 재조회로 확정한다(DEC-042). 핸들러 실패는 자동 재시도하지 않는다.
개발 편의(운영 이미지에는 영향 없음): `YTWEB_DATABASE_URL=sqlite:///...` 이면 `YTWEB_AUTO_CREATE=1` 에서 `Base.metadata.create_all`, `YTWEB_STATIC_DIR` 가 있으면 빌드된 프런트(dist)를 `/` 에 서빙(클라우드 화면 확인용). 운영(compose)은 Alembic + nginx만 쓴다.

## 11. 변경 이력 (v2 개정 — 바뀐 곳 전부 아래에 적었다)
| 일시 | 버전 | 변경한 곳 | 사유 |
|---|---|---|---|
| 2026-10-10 | v1 | 최초 작성(속도 우선 압축판) | DEC-038 |
| 2026-10-10 | v2 | 헤더(상태·근거·짝 문서), §0 M1 상태·진입점, §1 서비스 5개(migrate)·edge 네트워크·PG17·실제 프런트 버전·시간 표기, §2 14테이블·승인 서명·감사 체인 한계, §3 공통 규약(Origin·멱등 3종·페이지 422)·healthz 행·세션 행·sync·approve·execute/cancel·audit·settings 행·스키마 추가 필드(`preserved`, `precheck`, `blocked.code`, Job), §4 승인 만료 기준·한도(52단위 선예약·최소 노출수)·롤백 세부·감사 범위, §5 보안 세부, §7 완료 표시, §8 테스트 환경 정정(DEC-039)·결과, §9 질문 이관, §10 추가 공개 항목, 본 이력 추가 | 구현 결과(as-built)에 맞춘 풀 설계서(`DESIGN.md` Part B)와 일치시키기. 각 변경은 실제 코드와 대조했다(`DESIGN.md` 부록 A). **의미를 바꾸는 수정은 없다** — 문서와 코드가 달랐던 곳은 편차 표(DV-W)에 올렸다 |
| 2026-10-11 | v4 | 11단계 대조 1차: §3 dashboard·execute·google 행, precheck 필드, §4-3 데모 최소 노출수(코드 반영됨), §6 화면(모드 띠 3상태·면책 바닥글·초안 버리기), §12-3·12-6 상태 갱신, §12-7 신설 | 실제 코드·화면 문구와의 한 줄씩 대조 |
| 2026-10-11 | v3 | §12 M2·M3(구글 읽기 연동·제목 수정) 신설, §3 google/status 행에 §12 참조 | M2·M3 구현 반영(DEC-048), 11단계 문서 갱신 |

## 12. M2·M3 — 구글 읽기 연동과 실제 제목 수정 (2026-10-11 추가, as-built)

> **검증 상태 (정확히)**: 코드와 가짜 구글 자동 시험(백엔드·화면)만 있다. **실제 구글 서버 접속, 실제 채널 영상 읽기, 실제 제목 변경은 한 번도 하지 않았다.** 독립 검증 결과서(`docs/harness/units/web-WU-M23-FE-test.md` 등)의 결함은 조치됐으나 일부 표시 제한이 남았다(아래 12-6, 12-7). 근거 결정: DEC-046~049.

### 12-1. OAuth 흐름 (데스크톱 앱 클라이언트, DEC-048)
1. 소유자가 구글 클라우드에서 **데스크톱 앱** 유형 클라이언트 ID 를 만들고 JSON 을 `web\secrets\google_client.json` 으로 저장 → `start.ps1` 재실행. 이 파일이 있을 때만 `_common.ps1` 의 `Invoke-Compose` 가 `web/compose.online.yaml` 을 함께 쓴다(api·worker 가 `egress` 네트워크 + Docker secret `google_client`). 없으면 M1 데모와 동일(외부 통신 없음).
   - DEC-034 Q-5 의 가정(웹 애플리케이션)에서 바꾼 이유: 복귀 주소를 따로 등록할 필요가 없어 가장 단순하고 `03_manual_setup.md` 와 일치. 구글이 복귀 주소 `http://127.0.0.1:8080/api/v1/google/callback` 을 실제로 받는지는 **미검증-실제환경**.
2. 화면 [구글 계정 연결] → `POST /api/v1/google/connect`(세션+CSRF) → 서버가 state(256비트 1회용, 10분)와 PKCE(S256)를 만들고 `auth_url` 반환 → 브라우저가 구글로 이동(읽기 범위 `youtube.readonly`, `access_type=offline`, `prompt=consent`).
3. 구글이 `GET /api/v1/google/callback?code&state` 로 되돌려 보냄 → state 검증(없음·재사용·만료는 코드 교환 없이 거부) → 서버가 `https://oauth2.googleapis.com/token` 로 코드 교환(PKCE verifier 포함) → 토큰을 `app_secrets` 볼륨의 `google_token.json`(0600, 원자 저장)에 저장 → `303 /#/`. 오류는 한국어 안내를 한 번만 카드에 표시.
4. `POST /api/v1/google/disconnect` 는 읽기·쓰기 토큰 파일을 모두 삭제(구글 쪽 권한 취소 요청은 하지 않음).
5. **GET 상태 변경 예외**: 콜백은 구글에서 오는 최상위 이동이라 SameSite=Strict 세션 쿠키가 실리지 않으므로 세션·CSRF 대신 state+PKCE 로 보호한다. S-W03 의 유일한 예외(위협 모델 TW-37).

### 12-2. 읽기/쓰기 토큰 분리 (M3)
| 항목 | 읽기 | 쓰기 |
|---|---|---|
| 범위 | `youtube.readonly` | `youtube.force-ssl` (videos.update 에 필요) |
| 시작 | `POST /api/v1/google/connect` | `POST /api/v1/google/connect-write` (별도 state 표시: `write_states`) |
| 토큰 파일 | `google_token.json` | `google_write_token.json` (별도) |
| 쓰임 | 내 채널 영상 목록(`live_read.py`: channels → uploads 재생목록 → videos 50개씩, 최대 2,000개, 읽기 약 9단위/200개) | 제목 수정(`live_write.py`, `videos.update` 1회 = 50단위) |
- 같은 콜백이 두 흐름을 받되, 쓰기로 시작한 state 로 돌아온 경우에만 쓰기 토큰 파일에 저장한다(위조 state 는 아무것도 저장하지 않음, TC-M3-013).
- 영상 불러오기(`videos.sync` 작업): 구글에 연결되어 있으면 실제 영상을 `videos`(source='youtube')에 저장, 아니면 데모. 데모 영상에 제안·배치·변경 기록이 있으면 `demo_data_in_use` 로 거부(실제와 데모가 섞이지 않게). 기록 없는 데모 영상만 지우고 불러온다.

### 12-3. 게이트웨이 선택 3조건 (`domain/live_gateway.py`)
아래가 **모두** 맞을 때만 `SyncedLiveGateway(LiveYouTubeGateway)`(실제 쓰기), 아니면 `MockYouTubeGateway`.
1. 서버 설정 `YTWEB_LIVE_WRITE=1` (기본 꺼짐)
2. 쓰기 토큰 연결됨(`google_write_token.json` 존재)
3. `YTWEB_LIVE_ALLOWED_VIDEOS`(쉼표 구분 영상 ID)에 1개 이상
- 반영이 확인되면 같은 값으로 `videos` 행(title·snippet)을 동기화한다(오류 시 DB 불변).
- `GET /api/v1/google/status` 필드: `mode`, `connected`, `client_ready`, `message`, `last_error`, `write_connected`, `live_write_enabled`, `live_allowed_count`, `live_write_ready`.
- **해소**: `YTWEB_LIVE_WRITE`·`YTWEB_LIVE_ALLOWED_VIDEOS` 는 `compose.online.yaml` 이 api·worker 에 `${...}` 로 전달한다(기본 0·빈 값). 값은 `web/.env`(복사 원본 `web/.env.example`)에서 읽는다. 구글 연결 파일이 없으면 이 파일 자체가 쓰이지 않는다. Windows PC 실동작은 미확인.

### 12-4. 안전장치 3가지 (실제 모드 = 위 3조건 충족)
1. **허용 영상만**: 초안 단계(`_eligibility`) → 반영 직전(변경 기록·쿼터 확정 전) → 롤백 → 게이트웨이(`live_write`, 네트워크 호출 전 재검사)에서 허용 목록 밖은 `live_not_allowed`. 목록이 비면 수정 0건. 설정 API 로 목록을 바꿀 수 없음.
2. **다른 확인 문구**: 실제 모드의 배치 실행 확인 문구는 `실제 실행 N건`(데모 `실행 N건` 유지) + 사전 점검 경고. 서버가 `confirm_text` 를 알려 주고 화면은 그대로 표시한다.
3. **모호 응답 보호**: 쓰기 응답이 불분명하면(`definite=False`: 5xx·연결 끊김·응답에 새 제목 없음) 한 번 재조회하고, 확인되지 않으면 `planned` 를 남긴 채 `result_unknown` 으로 중단한다(자동 정리·재시도 없음). 변경 기록의 `mode` 는 live/demo 로 구분 저장한다.
- 승인(plan_hash·HMAC·1회용·24시간), 하루 상한, 72시간 간격, 쿼터 선예약 등 M1 안전장치는 그대로 적용된다.

### 12-5. 화면 (`web/frontend/src/pages/GoogleCard.tsx`, 홈의 "구글(유튜브) 연결" 카드)
연결 파일 없음 안내 → [구글 계정 연결] → 연결됨이면 [내 영상 불러오기]·[연결 해제](한 번 더 확인) → "제목 수정 권한" 구역: [제목 수정 권한 연결], 연결됐으나 꺼짐이면 "아직 꺼져 있음(허용 영상 N개)", 3조건이 맞으면 "실제 수정 모드가 켜져 있습니다" 경고. 쓰기 연결/실제 모드에서는 "읽기 전용" 문구를 숨긴다.

### 12-6. 알려진 결함·후속 조치 (6단계 프런트 독립 검증, `web-WU-M23-FE-test.md`)
| ID | 내용 | 등급 | 상태 |
|---|---|---|---|
| **DEF-VMF-001** | 대시보드 모드 표시 결함(상단 띠·홈 "연결 상태"가 고정값) | High | **조치됨(코드 확인)**: 대시보드가 실제 상태에서 `mode`/`live_enabled` 를 계산하고 상단 띠는 3상태. 단 홈 "연결 상태" 첫 줄은 연결 파일만 있어도 "구글 연결됨"으로 나올 수 있고, 설정 > 세션·연결의 "실행 모드"는 아직 고정 문구(새로 확인한 표시 제한, 미조치) |
| DEF-VMF-002 | 읽기 로그인만 풀리고 쓰기 토큰이 남은 드문 경우 경고 숨김 | Low | **조치됨(코드 확인)**: "제목 수정 권한" 구역이 읽기 또는 쓰기 연결 중 하나만 있어도 보인다 |
| DEF-VMF-003 | "꺼짐" 안내가 무엇이 부족한지 구분 못 함 | Low | **조치됨(코드 확인)**: 켜기 / 허용 영상 0개를 나눠 안내 |
| DEF-VMF-004 | 설정 방법이 화면·문서에 없음 | Low | **조치됨**: `web/.env` 전달 + 화면 안내 문구 |
- 외부 통신 모듈은 `google_oauth.py`·`live_read.py`·`live_write.py` 3개로 한정하고 그 밖은 시험이 금지한다(`test_tc_vb_278`).
- 위협 모델: `threat_model.md` W9(TW-37~44). `API.md` 상세·`openapi.json` 은 2026-10-11 갱신됨(EVT-W31~35).

### 12-7. 이후 추가된 실제 모드 안전장치 (DEC-049 등, 2026-10-11, 코드 기준)
- **모드 일관성**: 배치 실행 확정 때의 모드(`precheck.executed_live`)와 반영 시점의 게이트웨이가 다르면 항목을 `live_mode_changed` 로 건너뛴다. 롤백은 대상 변경의 `mode` 와 현재 게이트웨이가 다르면 `live_mode_mismatch`(409)로 거부한다.
- **실제 모드 롤백은 보수적 기본**(DEC-049): 반영 뒤 유튜브에서 제목·설명·태그·카테고리·언어가 바뀌었으면 백업으로 덮어쓰지 않고 409 `live_changed_since_apply`. 반영 중 보존 항목이 손상된 변경(`verify_failed`)은 통째 복원. 데모 롤백은 불변.
- **콜백 보호 보강**: 모르는 state 로 들어온 교차 사이트 콜백은 감사 기록을 쌓지 않고, 구글 호출은 리다이렉트를 따르지 않는다(DEC-049).
- **화면 단계 확인**: 배치 실행에 'A/B 테스트 아님' 확인란(화면 전용, 서버 필드는 실제 반영 단계에서 결정 — DEC-047).
