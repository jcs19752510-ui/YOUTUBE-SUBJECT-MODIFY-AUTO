# 테스트 결과서 — 백엔드 M2·M3·W-FIX-BE 독립 검증 (web-WU-M23-BE)

> 한 줄 결론: **CONDITIONAL PASS.** 시험 388건 중 369건 통과, 18건은 열린 결함 확인용(xfail, 아래 DEF-VM-001~010), 1건 미수행(openapi 비활성). 실제 구글 호출 0회, 허용 목록 밖 영상 쓰기 0회, 이중 반영 0건은 확인됐다. 다만 **실제 제목 변경을 처음 켜기 전에 고쳐야 할 Medium 결함 6건**(DEF-VM-003, 006, 007, 008, 009, 010)이 열려 있다. Critical/High 결함은 없다.

## 1. 개요
- 테스트 대상 (모듈/기능/업무단위/전체 시스템 중 명시): 모듈·기능 묶음 — ①W-FIX-BE(면책·AI 고지 필드, 초안 배치 취소 C-2, Medium 수정 4건 중 백엔드 해당분) ②M2 단위 1~3(`web/backend/ytweb/youtube/google_oauth.py`, `routers/google.py`, `youtube/live_read.py`, `domain/live_sync.py`) ③M3 단위 1·2·4(`youtube/live_write.py`, `domain/live_gateway.py`, `routers/google.py`의 connect-write, 배치·롤백·변경 기록에 연결된 부분 `domain/batches.py`·`changes.py`)
- 테스트 유형: 단위 + HTTP API 수준 + 워커 틱 수준(가짜 구글 사용) + PostgreSQL 실측. (통합 7단계가 아니라 이 작업 묶음의 독립 6단계 검증)
- 적용 Tier (Low/Standard/High): 이 저장소의 프로젝트 등급은 이번 호출에 전달되지 않음 → 가장 엄격한 쪽(Standard 이상: 내부 검증 2회 이상, 변이 점검)으로 수행
- 적용 속도 트랙 (L1~L5): L3(일반)로 간주(표기 없음)
- 병렬 실행 정보: 단독 실행(같은 시간대에 프런트·인프라 독립 검증이 도는 것으로 보이나 이 호출은 `web/backend/tests/verify_m23/`와 전용 DB `ytweb_test_h`만 사용, 다른 단위 파일 수정 없음)
- 테스트 목적: 구현자의 시험을 믿지 않고, M2·M3 실제 연동 코드가 ①실제 구글 호출을 만들지 않고 ②허용 목록 밖 영상에 쓰지 않고 ③읽기/쓰기 토큰을 분리하고 ④state를 1회용으로 지키고 ⑤토큰을 어디에도 남기지 않고 ⑥불명확 응답을 "반영 여부 불명"으로 다루고 ⑦확인 문구를 데모/실제로 구분하고 ⑧롤백에도 허용 목록을 적용하고 ⑨오류마다 한국어 안내를 주고 ⑩이중 반영을 막는지 독립 시험으로 증명한다
- 관련 산출물: `docs/yt/WEB_DESIGN.md`, `docs/yt/API.md`, `docs/harness/decisions.md`(DEC-046~048), `docs/harness/security-web-m1-test.md`, `docs/harness/feature-web-m1-integration-test.md`, 상태 기록 `docs/harness/STATE.md`(M2 단위 1~4, M3 단위 1~4 완료 줄). M2·M3 작업단위별 `unit-n-note.md`(인수 조건)는 저장소에 없다 → 인수 조건은 이번 호출의 "필수 관점" 10개와 DEC-048·API.md 165행으로 대신했다(아래 4절 매핑)
- 테스트 수행자(에이전트): 06 독립 검증자(구현자 아님)
- 테스트 일시: 2026-10-11

## 2. 테스트 범위 및 제외 범위
- 범위 (In-Scope): 위 대상 코드 전부. 시험 소스 `web/backend/tests/verify_m23/test_vm_01~10_*.py`(구현자 시험 재사용 없음. 기반 fixture인 `tests.domain.conftest`의 앱·DB·시계만 임포트).
- 제외 범위 (Out-of-Scope) 및 사유:
  - 실제 구글 서버 접속(금지됨). 가짜 구글의 응답 형식은 우리가 만든 가정이다 → 잔여 위험은 8절.
  - 프런트 화면(별도 독립 검증), 인프라/컨테이너 실가동(별도), 11단계 문서 대조.
  - 코드 줄·분기 커버리지 수치 측정(미수행, 5절).
  - M2·M3 작업단위 note의 5단계 린트/코드리뷰 게이트 확인: note 파일이 없어 **확인 불가**. 대체로 STATE.md의 "백엔드 전체 1461 통과" 기록만 있음 → 8절에 후속 조치로 남김.
  - 수정 전 FAIL 증명(`.harness-tmp/pre_06_*`): 신규 기능 검증이라 해당 없음(버그 수정 업무 아님).

## 3. 테스트 환경
- 실행 환경: Linux 6.18(컨테이너), Python 3.13(`.harness-tmp/venv_fix_be`), pytest, FastAPI TestClient(ASGI, 실제 소켓 없음), SQLite 파일 DB(기본) + 임시 PostgreSQL 16(`127.0.0.1:54329`, 전용 DB `ytweb_test_h`, 이번에 생성)
- 테스트 데이터: 데모 시드 영상 60개(`seed_demo`), 가짜 구글(`tests/verify_m23/fakegoogle.py`): 토큰 발급(PKCE S256·redirect_uri·client_secret 검증, 인가 코드 1회용), 읽기 API(channels·playlistItems·videos), 쓰기 API(PUT videos: 쓰기 범위 토큰만 허용, 정상/4xx/5xx(반영됨·안 됨)/타임아웃(반영됨·안 됨)/제목 불일치 응답/빈 응답 모드)
- 실제 구글 호출 차단 장치(모든 시험에 자동 적용, `conftest.py` `no_real_network`): `urllib.request.urlopen`을 가짜 구글로 교체하고, 구글 두 호스트가 아닌 주소·http는 `RealNetworkAttempt`로 즉시 실패, `socket.getaddrinfo`는 loopback 외 이름 해석을 거부.
- 전제 조건: 실제 배선(`GoogleCtx` 기본 생성, `select_gateway`, 환경변수 `YTWEB_LIVE_WRITE`·`YTWEB_LIVE_ALLOWED_VIDEOS`·`YTWEB_SECRETS_DIR`·`YTWEB_GOOGLE_CLIENT_FILE`)을 그대로 쓰고 로그인 흐름으로 읽기·쓰기 토큰을 실제로 발급받은 상태에서 시험한다.

## 4. 테스트 케이스 및 결과
총 388건(시험 함수 약 170개, 매개변수 포함). **통과 369 / 열린 결함 확인 18(xfail) / 미수행 1(skip) / 예기치 않은 실패 0.** 재실행: `cd web/backend && YTWEB_TEST_PG_URL=postgresql+psycopg://ytweb_test@127.0.0.1:54329/ytweb_test_h python -m pytest tests/verify_m23 -p no:cacheprovider -o addopts=''` (열린 결함을 xfail 표식 없이 보려면 `--runxfail`).

### 4-1. 파일별 결과
| 파일 | 대상 | 건수 | 통과 | 결함확인(xfail) | 미수행 |
|---|---|---|---|---|---|
| test_vm_01_oauth_core.py | google_oauth.py | 65 | 60 | 5 (030×2, 067×3) | 0 |
| test_vm_02_google_router.py | routers/google.py | 36 | 33 | 2 (104, 122) | 1 (130) |
| test_vm_03_live_read.py | live_read.py | 61 | 60 | 1 (200b, Info) | 0 |
| test_vm_04_live_sync.py | live_sync.py·videos.sync 핸들러 | 17 | 17 | 0 | 0 |
| test_vm_05_live_write.py | live_write.py | 63 | 59 | 4 (411) | 0 |
| test_vm_06_live_gateway.py | live_gateway.py | 79 | 79 | 0 | 0 |
| test_vm_07_live_e2e.py | 배치·워커·롤백 종단(HTTP+틱) | 49 | 44 | 5 (650,651,652,662,663) | 0 |
| test_vm_08_recovery_live.py | 재시작 복구(실제 모드) | 4 | 3 | 1 (702) | 0 |
| test_vm_09_postgres.py | PG 실측 | 5 | 5 | 0 | 0 |
| test_vm_10_wfixbe_and_hints.py | W-FIX-BE·hint | 9 | 9 | 0 | 0 |
| 합계 | | 388 | 369 | 18 | 1 |

합계 확인: 통과 60+33+60+17+59+79+44+3+5+9 = 369, 결함확인 5+2+1+4+5+1 = 18, 미수행 1.

### 4-2. 필수 관점 ↔ 시험 추적 (1:1 근거)
| # | 필수 관점 | 대표 시험 ID | 결과 |
|---|---|---|---|
| 1 | 실제 구글 호출 절대 금지(가짜 http 주입만) | 전 시험에 자동 적용(`no_real_network`), TC-VM-050·220·433(비 https 즉시 거부·호출 0) | PASS — `RealNetworkAttempt` 발생 0회 |
| 2 | 허용 목록 밖 영상은 네트워크 호출 0회 | TC-VM-400(허용 목록 9종 변형: 빈 목록·대소문자·공백·1글자 모자람), 401(스냅샷), 403(검사 순서), 600·601(초안 단계), 610(확인 전), 623(반영 직전), 624(초안~확정 사이 변경), 642(롤백), 801(PG) | PASS — 구글 호출 기록(`fg.calls`)이 비어 있거나 허용 영상만 포함. 게이트웨이 `read_snippet`은 허용 검사를 하지 않음(OBS-VM-1) |
| 3 | 쓰기 토큰·읽기 토큰 분리 | TC-VM-111·112·120·121(저장 파일·범위 분리), 440(읽기 범위 토큰으로 PUT → 구글 403), 500~507(선택표 32조합·읽기 토큰만 있으면 쓰기 불가·쓰기 게이트웨이는 쓰기 파일만 읽음), 620(PUT·GET 모두 쓰기 토큰), 322(쓰기만 연결 시 영상 불러오기는 데모 경로) | **FAIL 1건**: TC-VM-122(DEF-VM-003) — 미완료 쓰기 로그인이 20개를 넘으면 쓰기 토큰이 읽기 파일에 저장됨 |
| 4 | state 1회용·위조 거부 | TC-VM-011~016(256비트·재사용·위조 7종·600초 경계 599.999/600·한도 20 오래된 것부터 제거), 113(재사용해도 구글 코드 교환 0회), 114(위조 4종), 115, 116(HTTP 만료), 117(거부 시 state 소진), 124(세션 없이 위조 → 상태 변화 없음) | PASS |
| 5 | 토큰이 로그·응답·감사 기록에 남지 않음 | TC-VM-032·051·222·233·431·433(오류 메시지·예외 `__cause__`에 토큰/내부 주소 없음), 110(응답·헤더·status), 126(감사 6종 기록+체인 검증+토큰/코드 문자열 없음), 127(전체 흐름 로그 DEBUG+모든 응답), 660(실제 모드 한 사이클 후 모든 응답·로그·DB 전 테이블 덤프에서 `AT-`/`RT-`/client_secret/`CODE-` 0건) | PASS |
| 6 | 모호 응답(unconfirmed/5xx)은 definite=False | TC-VM-420(제목 불일치 9종 응답), 421(제목 정확 일치), 430(상태코드 15종: 4xx 정의됨, 5xx·599 불명), 431(타임아웃·끊김 4종), 432(JSON 아님), 630(실제 반영됐으나 응답 모호 4종 → 재조회로 확정·PUT 1회), 631(반영 안 됨 3종 → planned 유지·재시도 없음), 643(롤백 모호 3종) | PASS |
| 7 | 확인 문구 데모/실제 구분 | TC-VM-510(0·1·2·9·10·50·100건, 접두어 아님), 600(문구·경고 맨 앞), 610(오입력 11종 → 422·바뀌는 것 없음), 611(모드 전환 시 서로 거부), 622 | PASS |
| 8 | 롤백도 허용 목록 적용 | TC-VM-642(허용 해제 → 409 `live_not_allowed`, 호출 0), 640·641·644, 643 | PASS. 단 모드를 끄고 롤백하면 DEF-VM-006 |
| 9 | 오류 응답마다 한국어 hint | TC-VM-103·104·601·610·611·624·640~644·911·930 (`err_ok`: hint·title에 한글) | PASS — 단 DEF-VM-001은 hint 이전에 500(예외) |
| 10 | 이중 반영 방지 | TC-VM-621(같은 키 재전송·다른 키 재실행·틱 3회 → PUT 1회), 630~632, 700·701(복구), 800(PG에서 워커 4개 동시 → 영상당 PUT 정확히 1회, 변경 기록 2건 success·mode live) | PASS |
| 추가 | 응답 제목 확인 | TC-VM-003 계열은 변이 M03로 확인, 420·421 | PASS |
| 추가 | 변경 기록 mode | TC-VM-620·640·660(실제 `live`, 데모 `demo`), 802(PG CHECK 제약) | PASS (DEF-VM-006/008과 별개) |

### 4-3. 열린 결함 확인 시험 18건 (xfail strict, 표식은 `conftest.py` `KNOWN_DEFECTS`)
| 시험 | 결함 | 실제 결과(첫 실행) |
|---|---|---|
| TC-VM-030 `[]`, `"str"`(2건), TC-VM-104 `[]`(1건) | DEF-VM-001 | `AttributeError: 'list' object has no attribute 'get'` — `POST /api/v1/google/connect` 가 500(미처리 오류) |
| TC-VM-067 ×3 | DEF-VM-002 | `TypeError: fromisoformat: argument must be str` / naive 시각 비교 TypeError |
| TC-VM-122 | DEF-VM-003 | "400회 중 9회 새 쓰기 state 소실, 그중 9회 쓰기 토큰이 읽기 저장소에 저장됨" |
| TC-VM-200b | DEF-VM-004(Info) | `parse_duration("PT1M\n") == 60` (None 기대) |
| TC-VM-411 ×4 | DEF-VM-005 | `AttributeError: 'NoneType'/'list'/'str'/'int' object has no attribute 'get'` |
| TC-VM-650 | DEF-VM-006 | 롤백 201 성공인데 구글 PUT 0회·구글 제목 그대로 |
| TC-VM-651 | DEF-VM-007 | 데모 문구로 확정한 배치가 실제 모드 켠 뒤 틱에서 구글 PUT 1회 발생 |
| TC-VM-652 | DEF-VM-008 | 실제 문구로 확정한 배치가 모드 해제 뒤 틱에서 `mode=demo`·`success`로 기록, 구글 호출 0 |
| TC-VM-662, 663 | DEF-VM-010 | 대시보드 `mode=demo, live_enabled=False`, `google.connected=False` (실제는 쓰기 준비 완료·구글 연결됨) |
| TC-VM-702 | DEF-VM-009 | 복구 중 구글 읽기 실패 `GatewayError: quota_exceeded` 가 `run_due_items` 밖으로 전파 |

### 4-4. 정상 경로·경계값·예외 입력 균형
- 정상 경로: 읽기/쓰기 로그인 전체 흐름(PKCE 서버 쪽 검증 포함), 영상 불러오기 3페이지·150개, 실제 모드 사전 점검→확정→반영→롤백 전체.
- 경계값: state 만료 599.999/600초, 대기 20/21개, 토큰 만료 여유 60초 경계(59/60/61), Shorts 길이(정책 초±1), videos.list 50/51/100/101개 묶음, 목록 쪽 상한 40, 확인 문구 0/1/50건, 5분 stale 경계.
- 예외 입력: 위조·빈·초대형 state, 손상 토큰 파일 7종, 클라이언트 파일 9종, 비정상 본문 11종+4종, 모호 응답 9종, 상태코드 15종, `YTWEB_LIVE_WRITE` 값 12종, 허용 목록 문자열 10종, 확인 문구 오입력 11종.

## 5. 커버리지
- 커버리지 지표: 기능 커버리지는 4-2 추적표(필수 관점 10/10에 시험 연결). **코드 줄·분기 커버리지는 측정하지 않음(미수행: 이번 호출 범위 밖, 도구는 환경에 있으나 실행하지 않음)** — 대신 핵심 가드 변이 점검 48곳 중 47곳 탐지(6-1 아래 표 참조).
- 변이 점검(소스 복사본 `.harness-tmp/vm23/mutwork/`에서 수행. 원본 소스는 건드리지 않았고 `git diff -- web/backend/ytweb` = 0줄): **48곳 변형, 47곳 시험이 실패해 탐지(KILLED), 1곳 생존(M20)**.
  - 생존 M20: `TokenStore.save`의 `os.open(..., 0o600)`을 0o644로 바꿔도 직후 `os.chmod(self.path, 0o600)`이 덮어써 결과 파일 권한이 같다. chmod 쪽을 바꾼 M45와 둘 다 바꾼 M46은 탐지됨. → 동등 변이(방어 중복)로 판정. 교체 직후 chmod 전까지의 짧은 구간 노출은 시험으로 잡히지 않음(잔여 위험, 아주 낮음).
  - 탐지 목록(요약): M01 허용목록 검사 제거·M02 반전, M03 응답 제목 확인 제거, M04 unconfirmed definite 반전, M05 5xx definite 반전, M06 네트워크 단절 definite 반전, M07 categoryId 검사 제거, M08 본문 id 검사 제거, M09 허용 목록 공백 처리 제거, M10 LIVE_WRITE 판정 완화, M11 허용 목록 비어도 준비됨, M12 not_allowed_reason 무력화, M13 확인 문구 분기 반전, M14 쓰기 게이트웨이가 읽기 토큰 파일 사용, M15 DB 제목 동기화 제거, M16 state 1회용 해제, M17 state 만료 경계, M18 대기 한도, M19 PKCE S256→sha1, M21 기본 scope=쓰기, M22 refresh 토큰 유실, M23 만료 여유 제거, M24 쓰기 콜백 읽기 저장소로, M25 connect-write 읽기 범위, M26 쓰기 state 소진 제거, M27 해제 시 쓰기 토큰 유지, M28 감사 기록에 토큰 포함, M29 확인 문구 실제 모드 무시, M30 초안 단계 허용목록 제거, M31 반영 직전 허용목록 제거, M32 롤백 허용목록 제거, M33 변경 기록 mode 항상 demo, M34 데모 기록 있어도 삭제 진행, M35 이력 영상 보존 해제, M36 Shorts 경계, M37 묶음 50→51, M38 쪽 상한, M39 중복 제거 해제, M40 401 번역 제거, M41 경고 맨 앞 삽입 해제, M42 초안 취소 was_draft 오류, M43 모호 응답 재조회 생략, M44 planned 유지 해제, M45·M46 chmod, M47 롤백 영상 ID 입력 검사 제거, M48 롤백 mode 항상 demo. 원문 로그: `docs/harness/verify-logs/web-WU-M23-BE-raw/mutation_run_M01-M44.log`, `mutation_run_M45-M48.log`, 스크립트 `mutate.py`.
- 커버되지 않은 부분과 사유: ①실제 구글 응답(금지) ②Windows 파일 권한(0600 비트 미지원 환경) ③실제 시간 경과(10분 state TTL은 가짜 시계) ④openapi 스키마 대조(TC-VM-130 skip: 앱이 `/openapi.json`을 열지 않음. 대체로 정적 문서 `docs/yt/openapi.json`에 `connect-write` 경로가 1건 있음을 grep으로만 확인, 필드 단위 대조는 미수행) ⑤리다이렉트 시 Authorization 헤더 전달 여부(urllib 기본 동작, 미시험).

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 내용 |
|----|------|-----------|--------|------|-----------|
| DEF-VM-001 | 구글 클라이언트 파일이 JSON이지만 객체가 아니면(`[]`, `"str"`) `load_client`가 `AttributeError` → `POST /api/v1/google/connect`·`connect-write`가 500(미처리 오류). 사용자는 한국어 안내(409+hint)를 못 받는다. | `web/secrets/google_client.json` 내용을 `[]`로 두고 로그인 후 `POST /api/v1/google/connect` (시험 TC-VM-030, 104). 위치 `google_oauth.py:49` `raw.get(...)` 앞에 `isinstance(raw, dict)` 검사 없음 | Low | Open | 재작업 요청(5단계). 본 단계는 코드를 고치지 않음 |
| DEF-VM-002 | 토큰 파일의 `expires_at`이 시간대 없는 문자열이거나 문자열이 아니면 `TokenStore.is_fresh`가 `TypeError`(잡는 것은 KeyError·ValueError뿐) → 영상 불러오기·반영 작업이 `internal_error`로 실패. 파일을 직접 고치거나 손상된 경우에만 발생 | `{"access_token":"a","refresh_token":"r","expires_at":"2026-10-11T13:00:00"}` 저장 후 `GoogleAccess.access_token()` (TC-VM-067). 위치 `google_oauth.py:173` | Low | Open | 재작업 요청 |
| DEF-VM-003 | 쓰기 로그인을 마치지 않은 채 20번 넘게 시작하면 `write_states.pop()`이 **임의 원소**를 지워, 방금 시작한 쓰기 state가 사라질 수 있다(실측 400회 중 5~9회). 그 로그인을 마치면 **쓰기 범위 토큰이 읽기 토큰 파일(`google_token.json`)에 저장**돼 "읽기/쓰기 토큰 분리" 불변식이 깨지고 쓰기 연결은 안 됨. 발생 확률은 낮음(미완료 20건 필요) | `POST /connect-write`를 21번 이상 연속 호출하고 마지막 `auth_url`로 로그인 완료 → `google_token.json`의 scope가 `force-ssl` (TC-VM-122, 400회 중 9회/9회 재현). 위치 `routers/google.py` `connect-write`의 `ctx.write_states.pop()` | Medium | Open | 재작업 요청(가장 오래된 state를 지우거나 pending 한도와 함께 관리) |
| DEF-VM-004 | `parse_duration("PT1M\n")`이 60을 돌려줌(`$`가 끝 개행 앞에서도 일치). 구글은 개행을 보내지 않아 사용자 영향 없음 | TC-VM-200b | Low(Info) | Open | 수용 후보: 사용자 영향 없음(근거: 구글 응답 형식). 수용하려면 DEC 기록 필요(Deferred는 사용자 승인) |
| DEF-VM-005 | `LiveYouTubeGateway.update_snippet`가 본문이 dict가 아니면(`None`·list·문자열·정수) `GatewayError`가 아니라 `AttributeError`. 네트워크 호출은 나가지 않아(실패 쪽으로 안전) 위험은 낮으나, 호출한 쪽의 예외 분류(`definite` 판단)가 깨진다 | `update_snippet(VID, None)` (TC-VM-411). 위치 `live_write.py:94` `body.get("id")` 가 isinstance 검사 뒤에 있음 | Low | Open | 재작업 요청 |
| DEF-VM-006 | **실제로 반영한 변경을 실제 모드를 끈 뒤(`YTWEB_LIVE_WRITE=0` 등) 롤백하면 모의 게이트웨이가 처리해 201 "성공"**이다. 구글 제목은 그대로인데 DB의 영상 제목만 원래대로 바뀌고 롤백 기록은 `mode=demo` success. 이후 영상 불러오기도 "이력 있는 영상은 보존" 규칙 때문에 DB의 낡은 값을 유지한다 | `live` 환경에서 1건 반영(실제 PUT 1회) → `YTWEB_LIVE_WRITE=0` → `POST /api/v1/changes/{id}/rollback` → 201, 구글 PUT 0회, 구글 제목 불변 (TC-VM-650) | Medium | Open | 재작업 요청: 대상 변경의 `mode`가 live인데 현재 게이트웨이가 모의면 롤백 거부(409+한국어 hint) |
| DEF-VM-007 | 게이트웨이는 **워커가 항목을 처리하는 시점의 환경변수**로 고른다. 데모 문구(`실행 N건`)로 확정된 배치가 이후 실제 모드(3조건)가 켜진 뒤 틱에서 **"실제 실행" 확인 문구 없이 실제 PUT**을 한다(허용 목록 영상만). 배치가 며칠에 나뉘어 예약되면 현실적으로 가능 | `YTWEB_LIVE_WRITE=0`에서 "실행 1건"으로 확정 → `1`로 변경 → 틱 → 구글 PUT 1회 (TC-VM-651) | Medium | Open | 재작업 요청: 배치(또는 항목)에 확정 시 모드를 기록하고, 실제 모드 항목은 실제 문구로 확정된 것만 처리 |
| DEF-VM-008 | DEF-VM-006과 같은 뿌리의 반대 경우: "실제 실행 N건"으로 확정한 배치가 실제 모드 해제 뒤 틱에서 모의로 처리되어 항목 `success`·변경 `mode=demo`로 기록. 구글은 안 바뀌었는데 DB·화면은 "반영 완료" | 실제 문구로 확정 → `YTWEB_LIVE_WRITE=0` → 틱 (TC-VM-652) | Medium | Open | 재작업 요청(DEF-VM-007과 함께) |
| DEF-VM-009 | 실제 모드에서 재시작 복구(`recover_running_items`)가 구글 읽기 실패(`GatewayError`)를 잡지 않아 `run_due_items` 전체가 예외로 끝난다. 워커는 이를 잡아 로그만 남기므로(`worker.py`) **구글 읽기가 계속 실패하는 동안 다른 모든 배치 항목도 처리가 막힌다**(이중 반영은 없음, 가용성 문제). 모의 모드에서는 발생하지 않음 | `running` 상태 항목+planned 변경이 있을 때 구글 읽기 403(쿼터)로 `run_due_items` 호출 (TC-VM-702). 위치 `batches.py` `_recover_one`의 `gateway.read_snippet` | Medium | Open | 재작업 요청: 읽기 실패 시 해당 항목을 `result_unknown`으로 정리하거나 건너뛰고 틱 계속 |
| DEF-VM-010 | 홈 대시보드 요약(`/api/v1/dashboard`)이 `mode="demo"`, `live_enabled=false`, `google.connected=false`를 **하드코딩**한다. 쓰기 3조건이 모두 맞아 실제 수정이 가능한 상태에서도 홈은 "라이브 꺼짐"·데모로 보인다. 사용자가 "아무것도 실제로 안 바뀐다"고 오해할 수 있는 안전 표시 오류(제품 결함) | `live` 환경에서 `GET /api/v1/google/status` → `live_write_ready:true`, `GET /api/v1/dashboard` → `mode:"demo", live_enabled:false, google:{connected:false}` (TC-VM-662, 663). 위치 `domain/dashboard.py:38-40`, 화면 `HomePage.tsx:190,196` | Medium | Open | 재작업 요청(5단계 백엔드+프런트 영향). 프런트 독립 검증 쪽과 중복 보고 가능성 있음 |

### 관찰(결함 아님, 판단 근거 기록)
- OBS-VM-1: `LiveYouTubeGateway.read_snippet`은 허용 목록을 보지 않는다(읽기만이며 배치·롤백 경로는 앞단에서 차단됨). "허용 밖 영상 네트워크 0회"는 쓰기(`update_snippet`)와 배치·롤백 경로에서 증명, 게이트웨이 읽기 단독에는 해당하지 않음(TC-VM-442, 703). 복구(`_recover_one`)도 허용 목록 축소 후 읽기를 할 수 있음.
- OBS-VM-2: `videos.list` 요청에 `id`와 `maxResults`가 함께 나간다. YouTube Data API 문서는 이 조합을 지원하지 않는다고 적는 것으로 알고 있으나 공식 문서·실서버에 접속할 수 없어 **미확인**(TC-VM-217은 사실 기록만). 실서버에서 오류가 나면 영상 불러오기 전체가 막힐 수 있으므로 M2 실연동 때 최우선 확인 필요.
- OBS-VM-3: 반영 경로는 불명확 응답 뒤 재조회로 자동 확정(TC-VM-630)하지만 롤백 경로는 확정하지 않고 `planned`로 남긴다(TC-VM-643). 안전(이중 반영 없음)하나 수동 정리 절차가 필요.
- OBS-VM-4: 4xx 중 429(요청 과다)·409도 "처리되지 않음(definite)"으로 분류된다. 구글이 429를 돌려줄 때 실제로 미반영인지는 문서 미확인.

### 6-1. 결함 0건이 아닌 이유와 확인 범위
- 위 DEF-VM-001~010은 모두 시험으로 재현했으며(4-3), 재실행 명령으로 누구나 재현 가능하다.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록: `.harness-tmp/vm23/`(로그, 변이 점검용 소스 복사본 `mutwork/`, 스크립트), 시험 중 pytest `tmp_path`(자동 삭제), PostgreSQL 데이터베이스 `ytweb_test_h`(생성함, 시험이 매번 테이블을 만들고 `drop_all`로 지움), 시험 소스 `web/backend/tests/verify_m23/`(산출물). 새 venv는 만들지 않음(`.harness-tmp/venv_fix_be` 기존 것 재사용, 내 소유 아님).
- `.harness-tmp/` 하위에서만 생성했는가: [x] 예 (시험 소스와 결과서·원문 로그 복사본 `docs/harness/verify-logs/web-WU-M23-BE-raw/`만 저장소 안에 둠)
- 정리(삭제) 완료 여부: `.harness-tmp/vm23/` 전체 삭제 완료(원문 로그는 위 raw 폴더로 복사 후 삭제). 내가 띄운 pytest·변이 점검 프로세스 없음(`pgrep` 0건, 내 PID만 종료 — 시험 소스 생성 중 멈춘 내 셸 2개를 PID로 종료). `ytweb_test_h` 테이블 수 0(public). DB 자체는 다른 단위가 재사용할 수 있어 남김(빈 DB).
- 정리 후 `git status` 실행 결과 (그대로 첨부):
```
 M docs/yt/WEB_FAQ.md                      (다른 에이전트 소유: 11단계 문서)
 M docs/yt/WEB_LEGAL_NOTICE.md             (다른 에이전트 소유)
 M docs/yt/WEB_RUNBOOK.md                  (다른 에이전트 소유)
 M docs/yt/threat_model.md                 (다른 에이전트 소유)
 M web/backend/tests/verify_m23/conftest.py          (이 단위: 시험 소스, 오케스트레이터가 WIP 커밋한 파일의 후속 수정)
 M web/backend/tests/verify_m23/test_vm_07_live_e2e.py (이 단위)
?? docs/harness/verify-logs/web-WU-M23-BE-raw/        (이 단위: 원문 로그)
```
  (위 출력 뒤에 이 결과서와 검증 로그 `docs/harness/verify-logs/verify-log_web-WU-M23-BE-test.md`, `docs/harness/units/web-WU-M23-BE-test.md`가 추가됨. `web/backend/ytweb/` 소스 diff는 0줄.)
- 병렬 실행이었다면: 같은 시간대의 프런트·인프라·문서 작업 변경분(`docs/yt/*`)은 이 단위 소유가 아님. "이 단위가 만든 임시 아티팩트·미추적 잔여물은 `docs/harness/verify-logs/web-WU-M23-BE-raw/`(의도한 증빙)뿐"이라는 판정 근거는 위 `git status`와 `.harness-tmp/vm23` 부재. 전체 트리 점검은 오케스트레이터가 별도 수행.
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 없음 (단, 시험 소스 생성 중 내 셸 명령이 stdin 대기로 멈춰 내가 직접 PID로 종료함. 영향 없음)
- 소스 변경 0 확인: `git diff --stat -- web/backend/ytweb` 출력 없음.

## 8. 리스크 및 잔존 이슈
- 이번 테스트로 커버되지 않는 알려진 리스크:
  1. 가짜 구글은 우리가 가정한 응답 형식이다. 실제 구글의 오류 본문·필드 차이, `videos.list`의 `id`+`maxResults` 조합(OBS-VM-2), 429 처리, 토큰 응답의 `scope` 필드 불일치(사용자가 쓰기 권한 체크를 해제한 경우 등) 는 **M2/M3 실연동 첫 호출에서 확인해야 한다**. 특히 쓰기 범위 로그인에서 구글이 요청한 범위보다 적은 범위를 허용한 경우를 코드가 검사하지 않는다(응답 `scope`를 비교하지 않음 — 시험으로 확인한 사실이 아니라 코드 읽기에서 본 점, 미시험).
  2. 코드 줄·분기 커버리지 수치 미측정.
  3. M2·M3 작업단위 note의 5단계 린트/자체 리뷰 게이트 통과 여부는 note 파일 부재로 확인하지 못했다(원칙상 5단계로 되돌릴 사유이나, 이번 호출은 코드 결함 검증이 목적이라 결과서에 기록만 함).
  4. 프런트 화면에서 DEF-VM-010 등 표시가 어떻게 보이는지, 컨테이너 실가동 환경변수 전달(`compose.online.yaml`) 경로는 이 검증 범위 밖.
- 후속 조치가 필요한 항목:
  - 실제 제목 변경(M3 첫 실반영) 전 필수: DEF-VM-003, 006, 007, 008, 009, 010 수정 → 해당 시험의 `KNOWN_DEFECTS` 표를 지우고 재실행(수정되면 xfail strict가 XPASS로 실패해 알려 줌).
  - DEF-VM-001, 002, 005는 Low이므로 같은 수정 배치에 포함 권장. DEF-VM-004는 수용 여부를 사용자 결정으로.
  - 5단계 수정 후 이 결과서의 시험 전체(+기존 전체 시험)를 재실행하는 재검증 회차 필요.

## 9. 결론 및 판정
- [ ] PASS
- [x] **CONDITIONAL PASS** — 조건: ①실제 제목 변경을 처음 켜기 전에 Medium 결함 6건(DEF-VM-003, 006, 007, 008, 009, 010) 수정과 재검증 ②Low 3건(001, 002, 005)은 같은 수정에 포함하거나 DEC로 수용 ③DEF-VM-004는 수용 결정. 수용·수정 전에는 데모 모드(실제 연동 비활성)로만 사용 가능. 근거: Critical/High 없음, 실제 구글 호출 0회·허용 밖 영상 쓰기 0회·이중 반영 0건·토큰 노출 0건이 시험으로 확인됨.
- [ ] FAIL

## 10. 내부 검증 (최소 2회, `verification-log-template.md` 사용)
- 1차 검증 결과 요약: 인수 조건(필수 관점 10개) 시험 연결 100%, 기대값은 코드가 아니라 설계서·API.md·DEC-048·구글 공개 규격(PKCE RFC 7636 등)에 근거. 시험 자체 오류 6건을 발견해 시험을 고침(원인과 판단은 검증 로그 1차 항목). 결함 후보 10건 중 9건 확정.
- 2차 검증 결과 요약: "이 결과로 다음 단계에 넘겨도 되는가"를 의심해 변이 점검 48곳(47 탐지, 1 동등), 대시보드 하드코딩(DEF-VM-010), 모드 전환 3건(006~008), 복구 중 구글 실패(009) 같은 경계를 추가 발견. 3차에서 결과서 수치·ID 대응을 원문 로그와 대조해 결과서 자체의 결함 0건 확인.
- 검증 로그 파일 경로: `docs/harness/verify-logs/verify-log_web-WU-M23-BE-test.md` (원문 로그 `docs/harness/verify-logs/web-WU-M23-BE-raw/`)

## 부록 A. 실행 이력 (첫 실행 결과를 그대로 남김)
| 순번 | 실행 | 결과 |
|---|---|---|
| 1 | 기존 전체 시험 1회(`tests`, `verify_wfixbe`·`verify_m23` 제외, PG `ytweb_test_h`) | **1557 passed, 0 failed**, 4분57초 (`full_regress_1.log`) — 회귀 없음 |
| 2 | 파일별 첫 실행(작성 중 시험 오류 포함) | 01: 5 failed/60 passed(전부 제품 결함 DEF-001·002) · 02: 1 failed(104 `[]`)/34 passed · 03: 1 failed(200 개행)/60 passed · 05: 4 failed(411)/59 passed · 06: 1 failed(521)/78 passed → **시험 오류**(아래) · 07: 9 failed → **시험 오류**(Idempotency-Key 형식 400)와 620(구글 토큰 갱신 호출에 Authorization 없음 가정) · 08: 첫 702는 복구가 실행되지 않아 **거짓 통과**(10분 stale 조건 미충족)→수정 후 실제 실패 확인 · 10: 2 failed → **시험 오류**(910 다른 제안 포함, 921 경계 해석) |
| 3 | 전체 첫 실행(`verify_m23`, `--runxfail`) | 15 failed, 370 passed, 1 skipped (385건). 이때 TC-VM-122는 확률 시험(150회)이 우연히 통과 → 400회·즉시 로그인 완료 방식으로 강화해 재현 확정 |
| 4 | 변이 점검 | M01~M44: 43 KILLED, 1 SURVIVED(M20) → M45~M48 추가: 4 KILLED. 총 48곳 중 47곳 탐지 |
| 5 | 기존 전체 + `verify_m23` 1회 | **1926 passed, 1 skipped, 16 xfailed**, 5분05초 (`full_regress_2.log`; 이후 DEF-VM-010 시험 2건을 추가해 18 xfailed) |
| 6 | 최종 `verify_m23` | **369 passed, 1 skipped, 18 xfailed** 40.7초 (`run3_final.log`); `--runxfail`: 18 failed(=결함 확인 18건), 369 passed (`run3_runxfail.log`) |

### 시험 오류 8건과 처리 (제품 결함을 "기대값 변경"으로 덮지 않았음)
1. 07 전반: 멱등 키를 2글자로 보내 400 → 키 형식(8~80자)을 맞춤(명세 `idempotency_key_invalid` hint에 근거).
2. 620: 토큰 갱신 호출(Authorization 없음)을 쓰기 호출로 오인 → `/token` 제외(가짜 시계 때문에 토큰이 갱신됨).
3. 521: 한 폴더에서 두 환경을 만들어 이전 쓰기 토큰이 남음 → 폴더 분리.
4. 910: 한 영상에 만들어진 다른 후보 제안까지 센 오류 → 대상 제안만 확인.
5. 921: 정확히 5분은 고아가 아니라고 코드가 정함(`<`). 명세에 경계가 없고 사용자 영향도 없어 시험을 코드 동작(5분 초과부터 고아)에 맞춤 — 이 항목만 코드에 맞춰 기대값을 바꾼 것이며 사용자 관점 근거(5분 "경과"는 초과)와 원래 실패를 여기에 남김.
6. 702: 복구 조건(10분 경과)이 안 돼 거짓 통과 → 시계를 11분 진행.
7. 122: 확률 시험이 우연히 통과 → 400회로 강화.
8. 200: 개행 허용은 구글 응답에서 일어나지 않아 DEF-VM-004(Info)로 낮추고 xfail로 분리.

## 공유 문서 갱신 요청 (traceability.md·decisions.md는 직접 수정하지 않음)
- `docs/harness/traceability.md`: M2(구글 읽기 연동)·M3(실제 쓰기 게이트웨이/확인 문구/허용 영상/롤백 허용 목록) 관련 REQ-ID의 "단위테스트" 컬럼에 `web-WU-M23-BE-test.md` TC-VM-010~930 연결, 비고에 "CONDITIONAL PASS, 열린 결함 DEF-VM-003/006~010 수정 전 실제 반영 금지" 표기.
- `docs/harness/decisions.md`: 필요 시 DEF-VM-004(Info) 수용 여부, 실제 모드 전환 시 배치 모드 기록 설계(DEF-VM-007/008) 결정 요청.

---
## 부록 B. 결함 조치와 재실행 결과 (2026-10-11, 오케스트레이터)
첫 실행 결과(위 본문)는 그대로 두고, 조치 후 재실행을 별도로 적는다.
- **조치**: DEF-VM-003(`PendingAuth` 가 state 종류 read/write 를 함께 보관·소진, `ctx.write_states` 제거), DEF-VM-006(롤백: 변경 mode 와 현재 게이트웨이 모드가 다르면 409 `live_mode_mismatch`), DEF-VM-007·008(배치 확정 때 `precheck.executed_live` 기록, 반영 시 모드가 다르면 `live_mode_changed` 로 중단), DEF-VM-009(복구 중 `GatewayError` 는 그 항목만 건너뜀), DEF-VM-010(대시보드가 실제 구글 연결·실제 수정 가능 여부를 반영), DEF-VM-001·002·005(클라이언트 파일 JSON 형식, 만료 시각 형식, 본문 형식 검사). DEF-VM-004(Info)는 수용(구글은 개행을 보내지 않음).
- **시험 표식**: 위 결함의 strict xfail 표식을 제거했다(조치 후 XPASS(strict)가 나와 실패로 보고된 것이 조치 확인 신호). 시험 2건(TC-VM-122·129)은 제거된 내부 속성 `ctx.write_states` 를 직접 참조해 `ctx.pending.peek_kind()` 기반으로 바꿨다 — 검증하는 행동(최근 쓰기 로그인은 쓰기 저장소에 저장, state 는 한도 내 유지·소진)은 같다.
- **재실행(백엔드 전체, verify_wfixbe 제외)**: 1840 통과 · 102 건너뜀 · 1 xfail(DEF-VM-004) · 실패 0 (3분 52초). 실제 구글 호출 없음.
- **안 한 것**: 조치 후 변이 점검 재실행, 별도 독립 검증자의 재검증(오케스트레이터가 직접 조치함 → 9단계 재검증에서 함께 다시 확인 예정).

## 부록 C. 조치 후 변이 점검 (2026-10-11)

방법: 소스는 수정하지 않고 `.harness-tmp/mut_be/mNN/` 사본(매 변이마다 원본에서 새로 복사, 사본 안에서만 1곳 변경)에서 가드 관련 시험(test_live_guard·test_db_transient·test_live_gateway·test_google_router·test_changes_reports·test_batches·verify_m23/*(PostgreSQL 전용 vm_09 제외)·test_google_oauth·test_live_write)을 실행. 시험 실패=killed, 통과=survived. 사본은 종료 후 삭제.

첫 실행(1차): 48곳 중 killed 39, survived 9 — 1(live_mode_changed 코드명), 6(planned_id None 조건 제거), 7(InterfaceError 제외), 13(복구 중 rollback 삭제), 16·17·19(live_changed_since_apply 검사 삭제/예외 반전/보존 필드 제외), 26·27(google_state mode/connected)이 생존... 추가로 34·36·37·38·43 도 생존(아래 표). 실제 생존 합계는 14곳(1,6,7,13,16,17,19,26,27,34,36,37,38,43).

| # | 위치 | 변이 내용 | 1차 결과 | 동등/공백 판정 | 추가 시험 후 |
|---|---|---|---|---|---|
| 0 | batches 모드 불일치 | `!=`→`==` | killed | | |
| 1 | batches | 코드명 live_mode_changed→X | survived | 공백(코드 미검증) | killed(901) |
| 2 | batches | executed_live 읽기 반전 | killed | | |
| 3 | batches | executed_live 항상 False 기록 | killed | | |
| 4 | batches | executed_live 기록 반전 | killed | | |
| 5 | batches | DB끊김 복귀 분기 삭제 | killed | | |
| 6 | batches | `planned_id is None` 조건 제거 | survived | 공백(쓰기 시도 후 DB 오류 미검증) | killed(904) |
| 7 | batches | InterfaceError 제외 | survived | 공백 | killed(903) |
| 8 | batches | 복귀 상태 pending→failed | killed | | |
| 9 | batches | outcome 코드 db_unavailable→other | killed | | |
| 10 | batches | 틱 중단(break) 삭제 | killed | | |
| 11 | batches | stopped_by 값 변경 | killed | | |
| 12 | batches | 복구 GatewayError except 삭제 | killed | | |
| 13 | batches | 복구 GatewayError 시 `s.rollback()` 삭제 | survived | 동등(세션이 with 종료로 폐기, 이후 쓰기 없음) | 동등 |
| 14 | changes | 롤백 모드불일치 `!=`→`==` | killed | | |
| 15 | changes | 롤백 모드불일치 검사 삭제 | killed | | |
| 16 | changes | live_changed_since_apply 검사 삭제 | survived | 공백(오류 코드를 단언하는 시험 없음) | killed(905) |
| 17 | changes | verify_failed 예외 조건 반전 | survived | 공백 | killed(905, 단 verify_failed 면제 경로 자체의 양성 시험은 없음: 잔여) |
| 18 | changes | `if changed` 반전 | killed | | |
| 19 | changes | 보존 필드(description 등) 비교 제외 | survived | 공백 | killed(905) |
| 20 | live_gateway | confirm_text 항상 데모 문구 | killed | | |
| 21 | live_gateway | confirm_text 실제 n+1 | killed | | |
| 22 | live_gateway | not_allowed_reason 반전 | killed | | |
| 23 | live_gateway | not_allowed live_mode 조건 삭제 | killed | | |
| 24 | live_gateway | 확인 접두사 "실제 실행"→"실행" | killed | | |
| 25 | dashboard | live_ready 항상 False | killed | | |
| 26 | dashboard | mode 항상 "read" | survived | 공백 | killed(908) |
| 27 | dashboard | connected 에서 client_ready 제거 | survived | 공백 | killed(908) |
| 28 | google_oauth | PendingAuth kind 항상 read | killed | | |
| 29 | google_oauth | peek_kind 항상 write | killed | | |
| 30 | google_oauth | finish 에서 kind 소진 삭제 | killed | | |
| 31 | google_oauth | load_client dict 검사 삭제 | killed | | |
| 32 | google_oauth | client_secret 검사 삭제 | killed | | |
| 33 | google_oauth | section dict 검사 삭제 | killed | | |
| 34 | google_oauth | is_fresh 시간대 없음 검사 삭제 | survived | 동등(naive-aware 뺄셈 비교 시 TypeError→except→False로 같은 결과) | 동등 |
| 35 | google_oauth | is_fresh 경계 `>`→`>=` | killed | | |
| 36 | google_oauth | 리다이렉트 추종 허용 | survived | 공백 | killed(910) |
| 37 | google_oauth | opener 설치 삭제 | survived | 공백 | killed(910) |
| 38 | live_write | `import google_oauth` 부작용 import 삭제 | survived | 동등(다른 경로로 이미 import 됨, 시험 환경에서 관측 불가) | 동등 |
| 39 | live_write | 본문 id 검사 삭제 | killed | | |
| 40 | live_write | categoryId 검사 삭제 | killed | | |
| 41 | live_write | title 공백 검사 삭제 | killed | | |
| 42 | live_write | 응답 제목 확인 삭제 | killed | | |
| 43 | routers/google | state_invalid 감사 생략 삭제 | survived | 공백 | killed(911) |
| 44 | routers/google | 모든 실패 감사 생략 | killed | | |
| 45 | routers/google | 콜백 write 분기 삭제 | killed | | |
| 46 | routers/google | is_write 항상 False | killed | | |
| 47 | routers/google | is_write 항상 True | killed | | |

집계: 총 변이 48. 1차 killed 34, survived 14(공백 11, 동등 3: #13·#34·#38). 추가 시험 후 killed 45 / 48 (동등 3은 분모 제외 시 45/45). (위 상단 "39/9" 문구는 오기: 정확한 1차 집계는 killed 34·survived 14.)

추가 시험(시험 파일만, 소스 무수정): `web/backend/tests/verify_m23/test_vm_90_mutation_gaps.py` TC-VM-901~911(11개). 원본에서 11개 모두 통과, 위 표의 공백 변이 사본에서 실패 확인. 잔여: verify_failed 인 변경의 실제 롤백 면제 경로(#17)는 양성 시험 없음 — 후속 과제. 시간 상한 내 PostgreSQL 전용 시험은 제외.

확인: `git diff --stat -- web/backend/ytweb` 결과 0줄(소스 무수정). 사본 디렉터리 삭제 완료.
