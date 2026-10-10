# ytitle 웹 API 설명서 (v1, 구현 결과 기준 as-built)

| 항목 | 내용 |
|---|---|
| 문서 상태 | **초안(검증 대기)** — 6단계 독립 검증 4건이 진행 중이라 결함이 나오면 갱신된다. 상단 "검증 대기 항목" 표는 `DESIGN.md` 맨 위에 있다 |
| 작성 기준일 | 2026-10-10 |
| 근거 | 실제 코드 `web/backend/ytweb/routers/*.py`, `ytweb/domain/schemas.py`, `ytweb/core/*.py`(직접 읽음), 앱 객체에서 직접 생성한 `docs/yt/openapi.json`(31개 동작), 임시 SQLite+워커로 실제 호출해 얻은 응답 예시(이 문서의 JSON 예시는 모두 그 호출 결과이며 값만 줄였다) |
| 짝 문서 | `DESIGN.md`(Part B 설계서), `WEB_DESIGN.md`(압축 설계), `openapi.json`(기계용 스키마) |
| 모드 | **M1 데모 전용**: 유튜브·AI를 실제로 호출하지 않는다. 모든 영상·성과는 시연용 가상 데이터 |
| 엔드포인트 ID | `EVT-W01`~`EVT-W31`(DESIGN.md 부록 A와 같은 번호) |

> 읽는 법: 사람이 쓰는 화면은 이 API를 그대로 호출한다. 직접 호출해 볼 때는 2장의 "세션 시작" 순서를 지켜야 한다. 계약(스키마)의 최종 기준은 `openapi.json`이지만, 그 파일에는 아래 "알려진 스키마 한계"(9장)가 있어 오류 응답과 일부 응답 본문은 이 문서가 더 정확하다.

---

## 1. 접속 조건과 기본 규약

| 항목 | 값 |
|---|---|
| 주소 | `http://127.0.0.1:8080`(또는 `http://localhost:8080`). 호스트의 이 한 포트만 열려 있고 nginx(`web`)가 `/api/`를 api 컨테이너로 넘긴다 |
| 기본 경로 | `/api/v1/...`. 상태 점검만 `/healthz`, `/readyz`(+`/api/healthz`, `/api/readyz`) |
| 형식 | 요청·응답 JSON(UTF-8). 예외: `reports/export.csv`(CSV). 메시지는 한국어 |
| Host 헤더 | `127.0.0.1:8080` 또는 `localhost:8080`만 허용(DNS 리바인딩 방어). 다르면 `403 host_not_allowed`(nginx 단계에서는 응답 없이 연결 종료 444). 헬스 경로는 백엔드 Host 검사 면제 |
| 요청 크기 | 본문 1MB 초과 → `413 payload_too_large` |
| 문서 화면 | `/docs`, `/openapi.json`은 기본 꺼짐(`YTWEB_ENABLE_DOCS=1`일 때만, 개발용). 이 저장소의 `docs/yt/openapi.json`은 앱 객체에서 직접 뽑은 사본이다 |
| 버전 정책 | `v1` 안에서는 **필드 추가·선택 파라미터 추가만** 허용하고, 필드 삭제·이름 변경·의미 변경·필수화는 `v2`에서만 한다. 클라이언트는 모르는 필드를 무시해야 한다 |

### 1-1. 요청 헤더 규약
| 헤더 | 필요한 곳 | 설명 |
|---|---|---|
| `Cookie: ytw_session=...` | `auth/session`(발급) 외 모든 `/api/v1` 호출 | 세션 쿠키. `HttpOnly; SameSite=Strict; Path=/api`, 최대 12시간(`YTWEB_SESSION_TTL_HOURS`). 토큰 원문은 DB에 저장되지 않는다(sha256만) |
| `X-CSRF-Token` | 상태를 바꾸는 모든 호출(POST/PUT/PATCH/DELETE, `auth/session` 발급 제외) | `POST auth/session` 또는 `GET auth/me` 응답의 `csrf_token`. 세션마다 다르다. 틀리면 `403 csrf_invalid` |
| `Origin` | 상태 변경 + 세션 발급 | 허용 출처(`http://127.0.0.1:8080`, `http://localhost:8080`)와 **정확히 일치**해야 한다. 없거나 `null`이면 `403 origin_not_allowed`. 브라우저가 `Sec-Fetch-Site`를 보내면 `same-origin`이어야 한다(아니면 `403 cross_site_request`) |
| `Idempotency-Key` | `POST /batches`, `POST /batches/{id}/execute`, `POST /changes/{id}/rollback` | **필수**(없으면 `400 idempotency_key_required`). 형식 `[A-Za-z0-9._:-]{8,80}`. 다른 엔드포인트는 보내도 무시된다 |
| `Content-Type: application/json` | 본문이 있는 호출 | |

검사 순서(상태 변경): Host → 본문 크기 → 속도 제한 → **출처(Origin/Sec-Fetch-Site)** → 세션 → CSRF → 본문 검증 → 멱등성 → 업무 규칙. 출처 검사가 세션 확인보다 먼저라서 허용되지 않은 출처에는 세션 유무도 알리지 않는다.

### 1-2. 응답 헤더
모든 응답에 `X-Request-Id`(요청 번호, 로그 검색용). `/api` 응답은 `Cache-Control: no-store`, CSP `default-src 'none'`. 브라우저에 보이는 보안 헤더 한 벌(CSP·`X-Frame-Options`·`Referrer-Policy: same-origin` 등)은 nginx가 붙인다.

### 1-3. 속도 제한 (임의 기본값 — 사용하면서 조정)
| 계층 | 값 | 초과 시 |
|---|---|---|
| 백엔드(프로세스 내 슬라이딩 1분) | 전체 600, 쓰기(POST/PUT/PATCH/DELETE) 120, 세션 발급 10 | `429 rate_limited` + `Retry-After` 초 |
| nginx | `/api/` 30건/초(버스트 60), `auth/session` 10건/분(버스트 10) | `429` |

### 1-4. 시간·날짜 표기
- 시각은 **UTC ISO 8601**. 엔드포인트에 따라 `2026-10-10T16:25:38.321041Z` 또는 `2026-10-10T16:25:38.387695+00:00` 두 가지 표기가 섞여 나온다(같은 시각, 편차 DV-W06). 클라이언트는 둘 다 파싱해야 한다.
- 날짜 필드: `scheduled_date`, `queue.next_run_date`, `schedule[].date`는 **한국 시간(KST) 날짜**, `quota.pt_date`는 **태평양 시간 날짜**(`YYYY-MM-DD`). 규칙은 `DESIGN.md` W6장.

### 1-5. 페이지네이션 (목록 공통)
`?page=1&page_size=50` → `{items, total, page, page_size}`. `page`≥1, `page_size` 1~200(**200 초과는 잘리지 않고 `422 validation_error`**). 정렬 기본: 영상 `video_id` 오름차순, 그 외 `id` 내림차순(최신순).

### 1-6. 멱등성 동작
- 같은 키 + 같은 요청(경로·본문) → **저장된 첫 응답을 그대로 재생**(상태 코드 포함, 부작용 1회).
- 같은 키 + 다른 요청 → `422 idempotency_key_reuse`. 처리 중인 같은 키 → `409 idempotency_in_progress`(잠시 후 같은 요청 재전송).
- 요청이 업무 오류(4xx)로 끝나면 키 자리가 지워져 같은 키로 **다시 시도할 수 있다**. 키는 24시간 보관(워커가 48시간 지난 키를 삭제).
- 첫 응답이 `+00:00` 표기라면 재생 응답도 같은 표기다(저장된 JSON 그대로).

### 1-7. 오류 형식 (RFC 9457 problem+json)
`Content-Type: application/problem+json`
```json
{
  "type": "urn:ytweb:problem:confirm_text_mismatch",
  "title": "확인 문구가 일치하지 않습니다.",
  "status": 422,
  "detail": "정확히 '실행 1건' 라고 입력해야 합니다.",
  "code": "confirm_text_mismatch",
  "hint": "사전 점검 화면에 표시된 확인 문구를 그대로 입력하세요."
}
```
`code`는 프로그램이 분기할 때 쓰는 안정 값, `title`·`hint`는 사람용 한국어. 스택트레이스·내부 경로·입력값 원문은 절대 포함되지 않는다(입력 검증 오류도 위치와 사유만).

---

## 2. 세션 시작 순서 (직접 호출 예)
```bash
# 1) 세션 발급 (Origin 필수, PIN이 설정돼 있으면 {"pin":"1234"})
curl -i -c jar.txt -H 'Origin: http://127.0.0.1:8080' -H 'Content-Type: application/json' \
     -d '{}' http://127.0.0.1:8080/api/v1/auth/session
#   → 200 {"csrf_token":"uQo--fuk_..."}  + Set-Cookie: ytw_session=...; HttpOnly; SameSite=Strict; Path=/api
# 2) 조회 (쿠키만)
curl -b jar.txt http://127.0.0.1:8080/api/v1/dashboard
# 3) 상태 변경 (쿠키 + X-CSRF-Token + Origin)
curl -b jar.txt -X POST -H 'Origin: http://127.0.0.1:8080' -H 'X-CSRF-Token: uQo--fuk_...' \
     http://127.0.0.1:8080/api/v1/videos/sync
```

---

## 3. 인증·세션 (EVT-W05~W07)

### EVT-W05 `GET /api/v1/auth/me`
세션 확인(쿠키 없이도 호출 가능). 응답 200
```json
{"authenticated": false, "pin_required": false, "csrf_token": null}
```
세션이 유효하면 `authenticated:true`와 `csrf_token`을 돌려준다(새로고침한 화면이 토큰을 복구하는 용도).

### EVT-W06 `POST /api/v1/auth/session`
세션 발급. 본문 `{"pin": "<숫자 4~12자리>"}`(PIN이 설정된 경우만 필요, 그 외 `{}` 또는 본문 없음, 알 수 없는 필드는 422). 응답 200 `{"csrf_token": "..."}` + `Set-Cookie`.
| 오류 | 의미 |
|---|---|
| 403 `origin_not_allowed` / `cross_site_request` | Origin 없음·불일치 / 다른 사이트에서 온 요청 |
| 401 `pin_invalid` | PIN 불일치(5회 연속이면 잠금) |
| 429 `pin_locked` | 5회 연속 실패 → 5분 잠금, 반복할 때마다 2배(최대 1시간). `Retry-After` 초 |
| 429 `rate_limited` | 세션 발급 분당 10회 초과 |
감사 로그: 성공 `session.create`, 실패·잠금 `session.denied`. 세션은 최대 20개(오래된 것부터 삭제).

### EVT-W07 `DELETE /api/v1/auth/session`
로그아웃. CSRF 필요. 응답 204(본문 없음), 쿠키 삭제. 서버의 세션 행도 지운다.

---

## 4. 요약·상태 (EVT-W08, W23, W31, W01~W04)

### EVT-W08 `GET /api/v1/dashboard`
홈 요약. 응답 200 (실제 호출 결과):
```json
{
  "mode": "demo", "live_enabled": false,
  "google": {"mode": "demo", "connected": false},
  "counts": {"videos": 200, "excluded": 37, "suggested": 0, "approved": 0, "queued": 0, "applied": 0},
  "today": {"applied": 0, "cap": 10},
  "quota": {"used": 0, "limit": 6000, "remaining": 6000, "pt_date": "2026-10-10"},
  "active_job": null,
  "queue": {"pending_items": 0, "next_run_date": null}
}
```
`today`는 KST 하루 기준 반영 건수와 하루 상한, `quota`는 태평양 시간 기준 API 사용 단위. 호출할 때마다 만료된 승인을 `expired`로 정리한다. `active_job`은 진행 중 작업 1건(`JobOut`)이거나 `null`.

### EVT-W23 `GET /api/v1/jobs/{job_id}`
`job_id`는 UUID(36자). 응답 200 `JobOut`:
```json
{"id": "365ab5fe-168d-4df1-a41d-f99eba7d9a7e", "type": "videos.sync", "status": "succeeded",
 "progress": 200, "total": 200, "error": null,
 "result": {"created": 200, "updated": 0, "snapshots_created": 62, "total": 200}}
```
| 필드 | 값 |
|---|---|
| `type` | `videos.sync` · `suggestions.generate` · `batch.execute` |
| `status` | `queued` → `running` → `succeeded` / `failed` / `cancelled` |
| `error` | 실패 시 예외 클래스명 또는 오류 코드만(경로·메시지 비노출) |
| `result` | 유형별: `suggestions.generate` → `{videos, suggestions, skipped:[{video_id,code}]}`, `batch.execute` → `{processed, success, failed, skipped, stopped_by, note}`(`stopped_by`: `null`/`cap_reached`/`quota_exhausted`) |
오류: 404 `job_not_found`, 422(UUID 형식 아님). **작업 핸들러가 실패해도 자동 재시도하지 않는다**(배치 부작용 중복 방지). 폴링은 화면이 2초 간격으로 한다.

### EVT-W31 `GET /api/v1/google/status`
M1 고정 응답 200: `{"mode":"demo","connected":false,"message":"데모 모드입니다. 구글(유튜브)에 연결되어 있지 않고, 아래 영상은 모두 시연용 가상 데이터입니다."}`. M2부터 연결 상태를 돌려줄 자리.

### EVT-W01~W04 `GET /healthz`, `/api/healthz`, `/readyz`, `/api/readyz`
세션·CSRF·Host 검사 없음(컨테이너 헬스체크용). `healthz` → 200 `{"status":"ok"}`. `readyz` → 200 `{"status":"ok","db":"ok","mode":"demo"}`, DB 연결 실패 시 **503** `{"status":"degraded","db":"down","mode":"demo"}`(이 503은 `openapi.json`에 없음). 구글·AI 연결 상태는 아직 포함하지 않는다(M2·M3).

---

## 5. 영상·제안 (EVT-W09~W17)

### EVT-W09 `GET /api/v1/videos`
| 쿼리 | 설명 |
|---|---|
| `q` | 제목·영상 ID 부분 일치(대소문자 무시, 최대 100자) |
| `status` | `none`·`suggested`·`approved`·`queued`·`applied`·`rolled_back` (영상의 workflow 상태) |
| `excluded` | `true`/`false` — 제외 사유가 있는지 |
| `sort` | `title`·`views`·`duration_sec`·`last_change_at`·`video_id`(기본)·`suggestion_count`·`workflow_status` |
| `order` | `asc`(기본)·`desc`. 값이 없는 행(null)은 정렬 방향과 무관하게 항상 맨 뒤 |
| `page`, `page_size` | 1-5 참고 |
응답 `Page<VideoSummary>` (필터·정렬은 서버에서 수행):
```json
{"items": [{"video_id": "demoVid0200", "title": "금리 비교 앱 따라 해보세요", "privacy_status": "public",
  "duration_sec": 1240, "is_short": false, "excluded": false, "exclusion_reasons": [],
  "workflow_status": "none", "suggestion_count": 0, "last_change_at": null, "views": 48100}],
 "total": 200, "page": 1, "page_size": 2}
```
`workflow_status` 우선순위: `queued` > `approved` > (마지막 성공 변경이 적용/롤백이면) `applied`/`rolled_back` > `suggested` > `none`.

### EVT-W10 `GET /api/v1/videos/{video_id}`
`video_id`는 11자(`[A-Za-z0-9_-]`). 응답 `VideoDetail` = `VideoSummary` + `description_excerpt`, `suggestions[]`(최신순), `changes[]`(최신순), `limits{allowed, reasons[], next_allowed_at}`, `preserved{category_id, tags[], default_language, default_audio_language, description_chars}`(반영 후에도 보존되는 항목, `preserved`는 계약 외 추가 필드). 오류 404 `video_not_found`.
`limits`는 이 영상에 지금 새 변경을 담을 수 있는지(간격 72시간, 영상당 3회, 최소 노출수, 하루 상한)를 보여 준다.

### EVT-W11 `POST /api/v1/videos/sync`
(데모) 가상 영상 200개를 만들거나 새로고침하는 작업을 큐에 넣는다. CSRF 필요, 본문 없음. 응답 **202** `JobOut`. 이미 `queued/running`인 같은 작업이 있으면 **새로 만들지 않고 그 작업을 돌려준다**(연타 방지). 같은 입력이면 결과가 같고 다시 실행해도 200개 그대로(중복 없음). 이미 우리 앱이 제목을 바꾼 영상은 되돌리지 않는다.

### EVT-W12 `POST /api/v1/videos/{video_id}/suggestions`
한 영상의 제안을 **즉시(동기)** 만들고 검증한다. 본문 `{"count": 1~5}`(생략하면 설정 `suggestions_per_video`, 기본 3). 응답 **201** `Suggestion[]`:
```json
[{"id": 1, "video_id": "demoVid0001", "title": "냉장고 정리 처음이라도 쉽게 따라 하는 순서",
  "evidence": "냉장고 정리 하는 순서와 ...", "source": "ai:mock", "topic": "life", "strict": false,
  "validation_result": "pass", "reasons": [], "length": 24, "match_ratio": 1.0, "status": "candidate",
  "plan_hash": null, "approval": null, "created_at": "2026-10-10T16:25:38.321041Z"}]
```
같은 영상에 같은 제목이 이미 있으면 새로 만들지 않고 기존 제안을 돌려준다. 차단 판정(`block`)이면 `status:"blocked"`.
| 오류 | 의미 |
|---|---|
| 404 `video_not_found` | 영상 없음 |
| 409 `video_excluded` | 제외 대상(Shorts·비공개·아동용·예약). `detail`에 사유 |
| 422 `count_invalid` | 1~5 아님 |
| 502 `ai_unavailable` / `ai_no_candidates` | 제안기 장애 / 쓸 수 있는 후보 없음(M1 모의 제안기는 정상일 때 발생하지 않음) |

### EVT-W13 `POST /api/v1/suggestions/generate`
여러 영상에 대한 제안 생성을 작업으로 요청. 본문 `{"video_ids": ["demoVid0001", ...], "count": 1~5?}`(영상 ID 1~200개, 중복은 제거, 형식 위반 시 422). 응답 **202** `JobOut`(`type: suggestions.generate`). 목록에 없는 ID가 하나라도 있으면 404 `video_not_found`(`detail`에 앞 5개). 개별 영상의 실패(제외 대상 등)는 작업을 멈추지 않고 `result.skipped`에 `{video_id, code}`로 남는다.

### EVT-W14 `GET /api/v1/suggestions`
쿼리 `video_id`, `status`(`candidate|approved|queued|applied|rolled_back|rejected|blocked|expired`), `result`(`pass|warn|block`), 페이지. 응답 `Page<Suggestion>`(최신 id 우선). 호출할 때 만료된 승인을 `expired`로 정리한다.

**Suggestion 필드**: `reasons[]` = `{code, severity: "block"|"warn", message}`(검증기 판정 사유), `strict`(건강·금융 엄격 모드: 경고도 차단으로 처리), `match_ratio`(영상 요약과의 일치율 0~1), `plan_hash`(승인된 경우 계획 해시), `approval` = `{approver, approved_at, expires_at}` 또는 null. `status` 값은 위 8개.

### EVT-W15 `PATCH /api/v1/suggestions/{suggestion_id}`
사람이 제목을 수정. 본문 `{"title": "..."}`(1~2000자, 서버가 제어·방향 문자를 정리하고 300자 초과 거부). **기존 승인은 무효가 되고**(`approval:null`) 다시 검증되어 `blocked`/`candidate`가 된다. 같은 제목이면 변경 없이 그대로 반환. 응답 200 `Suggestion`.
오류: 404 `suggestion_not_found`, 409 `suggestion_state`(배치에 담김 `queued`/이미 `applied`/`rolled_back`이면 수정 불가), 409 `duplicate_suggestion`, 422 `title_empty`·`title_too_long`·`title_invalid`.

### EVT-W16 `POST /api/v1/suggestions/{suggestion_id}/approve`
본문 `{"approver": "홍길동"}`(1~40자, 제어 문자 없음). 응답 200 `Suggestion`(`status:"approved"`, `plan_hash`, `approval`):
```json
{"status": "approved", "plan_hash": "f9312f51...e292c",
 "approval": {"approver": "홍길동", "approved_at": "2026-10-10T16:25:38.349680Z", "expires_at": "2026-10-11T16:25:38.349680Z"}}
```
승인 가능 상태는 `candidate`·`expired`. **승인 시점에 영상 제외 사유와 검증을 다시 확인한다.** 승인은 계획 해시(영상 ID·제안 ID·이전/새 제목·snippet 전체)와 HMAC 서명, 24시간 유효(`approval.ttl_hours`), 1회용에 묶인다. `warn` 판정은 서버가 사유 확인을 강제하지 않는다(화면이 체크 후 호출, 편차 DV-W07).
| 오류 | 의미 |
|---|---|
| 409 `suggestion_blocked` | 차단 판정(또는 엄격 모드의 경고)이라 승인 불가. `detail`에 사유 |
| 409 `suggestion_state` | 현재 상태에서는 승인 불가 |
| 409 `video_excluded` | 제외 대상 영상 |
| 409 `same_as_current` | 현재 제목과 같음 |
| 409 `video_inconsistent` | 저장된 영상 정보 불일치(동기화 필요) |
| 404 `suggestion_not_found`, 422 `approver_required`·`approver_invalid` | |

### EVT-W17 `POST /api/v1/suggestions/{suggestion_id}/reject`
본문 없음. 응답 200 `Suggestion`(`status:"rejected"`, 승인은 제거). 가능 상태: `candidate`·`blocked`·`approved`·`expired`. 배치에 담긴 제안은 409 `suggestion_state`(배치를 먼저 중지).

---

## 6. 배치·반영 (EVT-W18~W22)

### EVT-W18 `POST /api/v1/batches` (Idempotency-Key 필수)
본문 `{"suggestion_ids": [1, 2, ...], "note": "메모(선택, 1000자 이하 입력, 저장 시 200자로 줄임)"}`. 승인된 제안을 배치 **초안(draft)** 으로 묶고 사전 점검을 만든다. 응답 **201** `{batch, precheck}`:
```json
{"batch": {"id": 1, "status": "draft", "note": "예시", "created_at": "2026-10-10T16:25:38.387695+00:00",
  "executed_at": null, "counts": {"pending": 1, "running": 0, "success": 0, "failed": 0, "skipped": 0, "cancelled": 0},
  "items": [{"id": 1, "suggestion_id": 1, "video_id": "demoVid0001", "video_title": "냉장고 정리 이렇게 하세요",
    "previous_title": "냉장고 정리 이렇게 하세요", "new_title": "냉장고 정리 처음이라도 쉽게 따라 하는 순서",
    "seq": 1, "scheduled_date": null, "status": "pending", "skip_reason": null, "change_id": null}]},
 "precheck": {"item_count": 1, "estimated_units": 52, "daily_cap": 10, "quota_remaining_units": 6000,
  "schedule": [{"date": "2026-10-11", "count": 1}],
  "warnings": ["Studio에서 해당 영상의 제목 A/B 테스트가 진행 중이 아닌지 확인하세요."],
  "blocked": [], "confirm_text": "실행 1건"}}
```
- `precheck.schedule`은 하루 상한(KST 기준)에 따라 나눈 반영 예정일. 위 예시는 UTC 16:25가 KST로 다음 날 01:25라 "내일"(2026-10-11)로 잡힌 실제 결과다.
- `estimated_units`는 1건당 52단위(재조회 1 + 갱신 50 + 검증 재조회 1)×건수. `blocked[]` = `{suggestion_id, reason, code}`(제외된 제안과 사유; `code`는 계약 외 추가 필드).
- 영상당 한 번에 한 제목만 담긴다(같은 영상의 다른 제안은 `duplicate_video`로 blocked).
- 응답의 `batch.precheck`는 목록(`GET /batches`)에서는 `null`, 단건·생성·실행 응답에서는 채워진다(계약 외 추가 필드).
| 오류 | 의미 |
|---|---|
| 400 `idempotency_key_required` / `idempotency_key_invalid` | 키 누락 / 형식 오류 |
| 422 `batch_empty` | 담을 수 있는 제안이 하나도 없음(`detail`에 사유). 빈 목록 자체는 스키마 단계에서 422 `validation_error` |
| 422 `batch_too_large` | 50건 초과(스키마 상한은 500, 서비스가 50건으로 거부) |
| 422 `duplicate_suggestion` | 같은 제안을 두 번 선택 |
| 409 `already_in_batch` | 방금 다른 배치가 먼저 담음 |
| 409 `schedule_overflow` | 예약 가능한 날짜 범위(400일) 초과 |

### EVT-W19 `GET /api/v1/batches`
`Page<Batch>`(최신순). 각 배치의 `items`는 **빈 배열**, `precheck`는 null(응답 크기 때문, 상세에서 채움).

### EVT-W20 `GET /api/v1/batches/{batch_id}`
`Batch`(항목·사전 점검 포함). `status`: `draft`(초안) → `queued`(실행 확정, 대기 중) → `running`(**실제로 처리 중인 항목이 있을 때만**) → `done`. 사용자 중지 `cancelled`. `paused`는 정의만 있고 M1에서 쓰지 않는다. 배치 상태에 `failed`는 없다(실패는 항목 상태와 `counts.failed`). 항목 `status`: `pending|running|success|failed|skipped|cancelled`; `skip_reason`은 `[코드] 한국어 사유` 형식. 404 `batch_not_found`.

### EVT-W21 `POST /api/v1/batches/{batch_id}/execute` (Idempotency-Key 필수)
본문 `{"confirm_text": "실행 1건"}` — 문구는 **정확히 `실행 {대기 항목 수}건`**(사전 점검의 `confirm_text`). 실행 확정 시점에 모든 항목의 승인·제외·한도를 다시 확인하고(하나라도 어긋나면 전체 거부), 예정일을 배정하며, 제안을 `queued`로 바꾸고, `batch.execute` 작업을 큐에 넣는다. 응답 **202** `{batch, job}`. 반영은 워커가 비동기로 한다 — 오늘 몫(하루 상한 − 이미 반영한 수)만 오늘 처리하고 나머지는 예정일에 맞춰 워커가 자동으로 처리한다(꺼져 있다 켜져도 **놓친 예약을 몰아서 실행하지 않는다**).
| 오류 | 의미 |
|---|---|
| 409 `batch_not_draft` | 이미 실행했거나 취소된 배치 |
| 422 `confirm_text_mismatch` | 확인 문구 불일치(`detail`에 정답 문구) |
| 409 `precheck_stale` | 사전 점검 이후 항목 상태 변동(승인 만료·한도·제외). 배치를 취소하고 새로 만들어야 함 |
| 400 / 422 / 409 `idempotency_*` | 1-6 참고 |

### EVT-W22 `POST /api/v1/batches/{batch_id}/cancel`
본문 없음, CSRF 필요(멱등성 키 불필요). `pending` 항목은 `cancelled`(사유 `[cancelled] 사용자가 배치를 중지했습니다.`)로, 진행 중(`running`) 항목은 끝날 때까지 둔다. 제안은 승인이 아직 유효하면 `approved`, 아니면 `expired`로 돌아온다. 초안(draft)도 취소할 수 있다. 응답 200 `Batch`(`status:"cancelled"`). 409 `batch_not_cancellable`(이미 `done`/`cancelled`).

### 항목 처리 중 사유 코드 (`skip_reason`의 `[코드]`, 변경 이력의 `error_code`)
| 구분 | 코드 |
|---|---|
| 건너뜀(`skipped`, 아무것도 바꾸지 않음) | `approval_missing` `approval_tampered` `approval_used` `approval_expired` `plan_mismatch` `suggestion_state` `suggestion_blocked` `title_invalid` `same_as_current` `video_excluded` `pending_change_exists` `limit_interval` `limit_count` `limit_impressions` `limit_daily` `quota_exhausted` `title_changed` `video_changed` `batch_not_active` `suggestion_missing` `cancelled` |
| 실패(`failed`, 시도했으나 실패) | `read_failed` `video_not_found` `snippet_invalid` `body_invalid` `update_failed` `result_unknown`(반영됐을 수도 있음 — 유튜브에서 확인) `internal_error` `verify_failed`(제목은 바뀌었으나 보존 항목 검증 불일치 — 변경은 `success`로 남고 롤백 가능) `interrupted`(재시작 복구에서 제목이 바뀌지 않았음을 확인) |
(`limit_*` 코드는 `ytitle.limits`의 판정 코드 `INTERVAL/COUNT/IMPRESSIONS/DAILY`를 소문자로 붙인 것. 정확한 집합은 코어 규칙을 따른다.)

---

## 7. 변경 이력·롤백·리포트·감사 (EVT-W24~W28)

### EVT-W24 `GET /api/v1/changes`
쿼리 `video_id`, `batch_id`, `result`(`planned|success|failed|aborted`), 페이지. 응답 `Page<Change>`(최신 우선):
```json
{"id": 1, "video_id": "demoVid0001", "video_title": "냉장고 정리 처음이라도 쉽게 따라 하는 순서",
 "change_type": "apply", "previous_title": "냉장고 정리 이렇게 하세요", "new_title": "냉장고 정리 처음이라도 쉽게 따라 하는 순서",
 "result": "success", "mode": "demo", "approver": "홍길동", "applied_at": "2026-10-10T16:25:38.525121Z",
 "verified_at": "2026-10-10T16:25:38.525121Z", "error_code": null, "rollbackable": true, "batch_id": 1}
```
`planned`는 반영 직전 기록(결과 미확정이면 그대로 남음 — 영상당 1건만 존재할 수 있고 새 반영을 막는다). `rollbackable`은 "성공한 적용이고, 백업이 있고, 그 영상의 가장 마지막 변경일 때"만 true.

### EVT-W25 `POST /api/v1/changes/{change_id}/rollback` (Idempotency-Key 필수)
본문 `{"typed_video_id": "demoVid0001", "approver": "홍길동"}` — 영상 ID를 **직접 입력**해야 한다. 응답 **201** `Change`(`change_type:"rollback"`, 백업 snippet 전체로 복원 후 재조회 검증). 롤백은 쿼터를 쓰지만 교체 한도(72시간·횟수·하루 상한)는 적용하지 않는다(사고 복구가 막히지 않게).
| 오류 | 의미 |
|---|---|
| 404 `change_not_found` / `video_not_found` | |
| 409 `not_rollbackable` | 성공한 적용(apply)만 가능 |
| 422 `typed_video_id_mismatch` | 입력한 ID가 대상과 다름 |
| 409 `later_change_exists` | 이후 같은 영상에 다른 변경(success/planned)이 있음 |
| 409 `backup_invalid` / `already_restored` / `pending_change_exists` | 백업 불일치 / 이미 원래 제목 / 진행 중 변경 있음 |
| 429 `quota_exhausted` | 오늘 쿼터 부족(태평양 시간 자정에 초기화) |
| 502 `gateway_error` | 재조회·갱신 실패(결과 불확실이면 `planned`가 남을 수 있음 — Studio에서 확인) |

### EVT-W26 `GET /api/v1/reports/changes`
쿼리 `video_id`(선택). 응답 `{items: VideoReport[], notes: string[]}`(최대 200영상). `VideoReport.status`: `no_change`(변경 없음) · `insufficient`(**"데이터 부족" + `reasons[]`**) · `ok`(`before/after` 스냅샷과 `metrics[]` 비교). `notes`에는 "원인을 단정할 수 없다", "데이터 부족이면 결론을 내지 않는다", "데모 성과는 가상 데이터" 문구가 항상 들어간다. 롤백이 끼어 있거나 변경 후 지표가 없으면 `insufficient`. 404 `video_not_found`.

### EVT-W27 `GET /api/v1/reports/export.csv`
쿼리 `video_id`(선택). 응답 200 `text/csv; charset=utf-8`, `Content-Disposition: attachment; filename="ytitle-report.csv"`, UTF-8 BOM. 열: `video_id,title,status,label,changed_at,previous_title,new_title,before_period,before_impressions,before_ctr,before_views,before_watch_minutes,after_period,after_impressions,after_ctr,after_views,after_watch_minutes,reasons,note`. 셀이 `= + - @` 탭·CR로 시작하면 앞에 `'`를 붙여 엑셀 수식 주입을 막는다(숫자는 그대로).

### EVT-W28 `GET /api/v1/audit`
읽기 전용. 쿼리는 페이지만. 응답 `Page<AuditEntry>` + `chain_ok`:
```json
{"items": [{"id": 9, "ts": "2026-10-10T16:25:38.639948+00:00", "actor": "web", "action": "change.rollback",
  "target_type": "change", "target_id": "2", "detail": {"target_change": 1, "video_id": "demoVid0001", "approver": "홍길동", "verify_ok": true},
  "prev_hash": "b934ceae...", "hash": "d0fa29e8..."}],
 "total": 9, "page": 1, "page_size": 2, "chain_ok": true}
```
`chain_ok=false`는 기록이 중간에서 바뀌거나 지워졌음을 뜻한다(꼬리 삭제는 이 방법만으로는 탐지 못한다 — DESIGN.md W9장). 최신순. 주요 `action`: `session.create/denied/delete`, `settings.update`, `videos.sync_request`·`videos.sync`, `suggestion.generate_request/generate/generate_failed/edit/approve/reject`, `batch.create/execute/cancel`, `batch.item.skipped/failed/recovered`, `change.apply/rollback/rollback_failed`. 비밀·PIN 값·본문 전체는 기록하지 않는다. `actor`: `owner`(세션), `web`(화면 요청), `worker`.

---

## 8. 설정 (EVT-W29, W30)

### EVT-W29 `GET /api/v1/settings`
```json
{"daily_apply_cap": 10, "suggestions_per_video": 3, "tone": [], "pin_enabled": false, "mode": "demo",
 "read_only": {"enable_live": false, "live_allowlist": [],
   "note": "라이브 반영 허용과 허용 영상 목록은 화면에서 바꿀 수 없습니다."}}
```

### EVT-W30 `PATCH /api/v1/settings`
본문은 아래 **4개 키만** 허용(섞여 있으면 전체 거부). 하나라도 허용 목록 밖이면 `400 setting_not_allowed`(`enable_live`·`live_allowlist` 포함 — **라이브 허용은 이 API로 켤 수 없다**).
| 키 | 값 |
|---|---|
| `daily_apply_cap` | 정수 1~20 (기본 10) |
| `suggestions_per_video` | 정수 1~5 (기본 3) |
| `tone` | 문자열 목록, 최대 5개, 각 1~20자(제어 문자 불가) |
| `pin` | `{"action":"set"\|"clear","new_pin":"숫자 4~12","current_pin":"기존 PIN"}` — 이미 PIN이 있으면 `current_pin` 필수. 설정·변경·해제 시 **현재 세션 외 모든 세션이 폐기**된다. PIN 값은 로그·감사에 남지 않는다(`detail.pin = set/changed/cleared`만) |
응답 200: GET과 같은 설정 객체. 오류: 400 `setting_not_allowed`, 422 `validation_error`(범위·형식), 422 `pin_invalid`(PIN 형식), 401 `pin_invalid` / 429 `pin_locked`(현재 PIN 불일치·잠금), 409 `pin_not_set`(없는 PIN 해제), 403 CSRF/Origin 계열. 감사 `settings.update`.

---

## 9. 알려진 스키마 한계 (`openapi.json`과 실제 동작의 차이)
`docs/yt/openapi.json`은 앱 객체에서 직접 뽑은 원본이며 **임의로 고치지 않았다**. 다음 차이는 `DESIGN.md` 편차 표(DV-W05)에 올라 있고 사용자 결정 대기다.
1. `Idempotency-Key` 헤더가 **선택**으로 표기되지만 3개 엔드포인트에서 실제로는 필수(누락 시 400).
2. 오류 응답이 FastAPI 기본(`422 HTTPValidationError`)만 표기. 실제 입력 검증 오류는 `422 application/problem+json`(`code: validation_error`)이고, 401·403·409·429·502 등은 스키마에 없다.
3. `auth/me`, `auth/session`, `settings`, `audit`, `healthz/readyz`는 응답 스키마가 없다(`additionalProperties: true`). 이 문서의 필드 목록이 기준이다.
4. `readyz`의 503, `reports/export.csv`의 `text/csv`가 표기되지 않았다.
5. `Suggestion.status`, `Batch.status`, `Job.status` 등은 문자열로만 표기(허용 값은 본문 참고).
영향: 프런트 타입은 OpenAPI에서 생성하지 않고 `web/frontend/src/api/types.ts`를 손으로 맞췄다(F-02 미수행). 계약 테스트(8단계)는 이 문서의 필드·코드 표와 `openapi.json`을 **함께** 기준으로 삼아야 한다.

## 10. 변경 이력
| 일시 | 버전 | 변경 | 사유 |
|---|---|---|---|
| 2026-10-10 | v0.1 | 최초 작성(as-built) | STATE §6 "문서 개정 3건"의 3단계 산출물. 코드·실제 호출 결과 기준, 6단계 독립 검증 결과 반영 전 |
