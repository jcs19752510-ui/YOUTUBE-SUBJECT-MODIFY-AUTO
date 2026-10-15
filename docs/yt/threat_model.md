# 위협 모델 (Threat Model) — 3단계 설계 시점 산출물

- 작성일: 2026-10-10 / 입력: `DESIGN.md`(v0), `02_risk_assessment.md` / 규칙 B 검증 대상(별도 로그)
- 시스템이 작아도 생략하지 않았고(Tier로 완화되지 않음), 작게 썼다.

> **웹 전환 개정(v1-W, 2026-10-10)**: 위 §1~§6은 CLI 트랙 기록(T-01~T-16)이며 삭제하지 않았다. 웹·컨테이너 구조의 STRIDE 갱신(S-W15)은 **문서 맨 아래 Part W(TW-01~TW-36)** 에 있다. 6단계 독립 검증·7단계 통합이 같은 코드를 검증 중이라 Part W 상단의 "검증 대기 항목" 표에 갱신 조건을 적었다.

## 1. 범위와 자산
| 자산 ID | 자산 | 민감도 | 소유 컴포넌트 |
|---|---|---|---|
| A-1 | OAuth 클라이언트 비밀 `secrets/client_secret.json` | 민감 | auth.py |
| A-2 | 읽기 토큰 | 민감 | auth.py (`%LOCALAPPDATA%\youtube-title\tokens`) |
| A-3 | **쓰기 토큰**(제목 수정 가능) | **매우 민감** | auth.py, live_guard.py |
| A-4 | 채널의 공개 메타데이터(제목·설명·태그) — 변경 대상 | 공개(그러나 훼손 시 영향 큼) | YouTube, updater.py |
| A-5 | 변경 이력 DB(백업 snippet 포함) | 내부 | db.py, history.py |
| A-6 | 후보 파일 `candidates/*.json` | 내부 | candidates.py |
| A-7 | 승인 파일 `approvals/*.json` | 내부(쓰기 승인 수단) | approvals.py |
| A-8 | 설정·금칙어 사전 | 내부(안전 규칙 자체) | config.py, banned_terms.py |
| A-9 | 로그 | 내부(비밀이 섞이면 민감) | logging_setup.py |

## 2. 데이터 흐름과 신뢰 경계
```
[사용자] --명령--> [CLI/프로그램] ==TB-1(HTTPS+OAuth)==> [Google API]
                        ^   |
   TB-2 외부 입력 파일 --+   +--TB-3(로컬 파일시스템, 같은 PC의 다른 프로세스)--> data/, secrets/, tokens
   (candidates JSON, CSV, YAML)
   TB-4 PyPI 의존성(설치 시점)
```

## 3. 위협 식별 (STRIDE)
| 위협 ID | 경계/컴포넌트 | STRIDE | 위협 시나리오 | 가능성 | 영향 | 위험도 | 대응 방안 | 대응 SEC-ID | 잔여 위험 |
|---|---|---|---|---|---|---|---|---|---|
| T-01 | TB-3 auth | 위장(S) | 같은 PC의 악성코드가 토큰 파일을 읽어 채널에 접근 | L | H | 중 | 토큰을 사용자 프로필 폴더에 저장, 읽기/쓰기 분리, 쓰기 토큰은 쓰기 순간에만 로드 | SEC-008, SEC-015 | 로컬 악성코드는 완전히 막을 수 없음 |
| T-02 | TB-2 candidates | 변조(T) | 후보 JSON 변조·경로 조작(`../`)으로 엉뚱한 파일 읽기/영상 지정 | M | M | 중 | 경로 해석 후 `candidates/` 하위만 허용, `video_id` 정규식, 크기·타입 검증 | SEC-011 | 낮음 |
| T-03 | TB-3 approvals | 변조(T) | 승인 파일 위조·재사용·다른 계획에 재활용 | L | H | 중 | `plan_hash` 바인딩, 만료, 1회 사용 | SEC-014, SEC-001 | 로컬 공격자가 파일 시스템을 쓸 수 있으면 우회 가능 |
| T-04 | run_logs/title_changes | 부인(R) | 누가 언제 어떤 변경을 승인했는지 불명 | L | M | 하 | approver·시각·`run_id` 기록 | NFR-008, SEC-006 | 낮음 |
| T-05 | logging | 정보노출(I) | 예외·로그에 토큰·키가 찍힘 | M | H | **상** | 마스킹 필터(로그와 예외 공통), 로그 스캔 테스트(K-6) | SEC-008 | 낮음(패턴 밖 형식은 놓칠 수 있음) |
| T-06 | git/저장소 | 정보노출(I) | `client_secret.json`·토큰·`.env`가 커밋됨 | M | H | **상** | `.gitignore`, 토큰을 프로젝트 밖에 저장, 9단계 저장소 스캔 | SEC-008 | 사용자 실수 가능성 |
| T-07 | youtube_read/quota | 서비스거부(D) | 쿼터 소진(다른 도구까지 막힘) | M | M | 중 | 일일 상한, 선예약, 재시도 2회 | SEC-002, SEC-003 | 낮음 |
| T-08 | live_guard | 권한상승(E) | 쓰기 권한 토큰 탈취로 제목 변경 | L | H | 중 | 읽기/쓰기 토큰 분리, 쓰기는 사람 승인 14단계, `auth --revoke` | SEC-015, SEC-001 | T-01과 동일 |
| T-09 | TB-4 의존성 | 변조(T) | 악성·환각 패키지 설치 | L | H | 중 | PyPI 실존·라이선스 확인, 버전 고정, 신규 의존성은 규칙 A | SEC-013 | 정상 패키지의 취약점은 별도 점검(9단계) |
| T-10 | banned_terms | 변조(T) | 금칙어 사전이 실수/악의로 약해져 위험 제목이 통과 | M | M | 중 | 검증 기록에 사전 해시 저장, 리포트에 사전 변경 표시 | SEC-017 | 사용자가 의도적으로 약화하면 막지 못함 |
| T-11 | TB-2 YAML/CSV | 변조(T)/권한상승 | 위험한 YAML 구문·거대 파일·CSV 값으로 코드 실행/자원 고갈 | L | H | 중 | `yaml.safe_load`만, 크기 상한, CSV는 값만 읽음 | SEC-016 | 낮음 |
| T-12 | db | 변조(T) | 제목·설명 문자열을 통한 SQL 인젝션 | L | H | 중 | 파라미터 바인딩만 | SEC-018 | 낮음 |
| T-13 | CLI 출력 | 변조(T) | 제목·설명에 ANSI 이스케이프를 넣어 화면을 속임(승인 요약을 위조) | L | M | 하 | 제어문자 제거/이스케이프 | SEC-019 | 낮음 |
| T-14 | updater | 변조(T) | 사람이 Studio에서 바꾼 제목을 프로그램이 덮어씀(검사 시점-사용 시점 불일치) | M | M | 중 | 호출 직전 재조회·비교 | SEC-009 | 재조회와 호출 사이의 짧은 틈 |
| T-15 | updater | 변조(T) | 설명·태그·카테고리가 삭제됨(미지정 속성 삭제) | M | H | **상** | 전체 snippet 보존, 백업, 사후 재조회 검증, 롤백 | SEC-005, SEC-010, SEC-006 | 낮음 |
| T-16 | apply | 서비스거부(D)/변조 | 실수·스크립트 반복으로 여러 영상을 한꺼번에, 또는 같은 영상을 잦게 변경 | L | H | 중 | `apply`는 후보 1건씩, **하루 적용 건수 상한**, 허용 목록, 영상별 교체 제한(72시간·횟수·최소 노출) | SEC-020, SEC-012, SEC-004 | 낮음 |

## 4. LLM/AI 기능 추가 위협 (규칙 J)
**해당 없음 — 사유**: 프로그램이 LLM을 호출하지 않는다(DEC-003, ADR-007). 후보 제목은 프로그램 밖에서 만들어 파일로 입력된다. 입력 경로의 위험은 T-02, T-13, 후보 내용 검증(FR-002)이 다룬다. LLM 호출을 추가하면 이 절과 Tier를 재평가한다(재평가 트리거).

## 5. 수용하는 잔여 위험
| 위협 ID | 수용 사유 | 수용 결정자 | decisions.md ID |
|---|---|---|---|
| T-01, T-03, T-08 (같은 PC의 악성코드/로컬 공격자) | 개인 PC 도구의 범위를 넘는 위협. 완화만 하고 완전 차단은 불가 | **사용자 확인 대기(규칙 A)** — Q-3-1 | (대기) |
- 위험도 High 위협을 대응 없이 수용하는 항목은 **없다**. 위 항목은 "중"이며 완화 대응이 있다.
- **Q-3-1**: 같은 PC의 악성코드·로컬 공격자는 이 도구의 방어 범위 밖으로 두고 완화(SEC-008/014/015)만 하는 것에 동의하시나요? (기본값: 동의로 간주하고 진행하되 사용자 확인 시 DEC로 기록)

## 6. 9단계 인계
- 9단계가 구현 여부를 확인할 SEC-ID: **SEC-001 ~ SEC-020 전부**(SEC-007은 금지 사항 부재 점검, SEC-013은 의존성 점검).
- 변경 이력
| 일시 | 버전 | 변경 내용 | 사유 |
|---|---|---|---|
| 2026-10-10 | v0 | 초안 | 3단계 |


---

# Part W — 웹·컨테이너 위협 모델 갱신 (STRIDE, as-built, v1-W) — 요구 S-W15

- 작성일: 2026-10-10 / 입력: `docs/yt/WEB_DESIGN.md` §5, 구현 노트 4건, `02_planning.md` Part W, `02_risk_assessment.md` Part W, 1단계 축 D·B·C·A, **코드·설정 직접 확인**
- 위 §1~§6은 CLI 트랙(T-01~T-16)이며 삭제하지 않았다. 웹 트랙의 위협 ID는 `TW-xx`이고, 대응 ID는 요구서의 `S-W01~S-W16`, `D-xx`, 그리고 `02_planning.md` Part W의 제안 ID(`POL-0xx`, `SEC-021~030`)다.
- **"구현됨" 표기 규칙**: 코드·설정 파일을 직접 읽어 확인한 것만 `구현됨 [코드]`로 쓰고 파일 경로를 달았다. 구현 노트의 실측·수치를 옮긴 것은 `[보고값]`(이 개정에서 재확인하지 않음, 6·7단계 검증 대기), 아직 어떤 증거도 없는 것은 `미확인`, 의도적 미구현(데모 모드)은 `M2/M3 예정`이다.

### 검증 대기 항목 (다른 단계가 같은 코드를 검증 중 — 결과에 따라 이 문서를 고쳐야 할 수 있음)
| # | 대기 중인 것 | 영향받는 위협 |
|---|---|---|
| V-1 | 6단계 독립 검증 결과서 4건(`web-WU-{BE-A,BE-B,FE,INF}-test.md`) — 변이 점검에서 "구현됨"이 깨지면 해당 TW의 상태를 내린다 | TW-01~04, 06~11, 17~21, 25~34 |
| V-2 | 7단계 전체 스택 통합(포트 18080): 127.0.0.1 한정, 재시작 중 이중 반영, 백업 복원 | TW-02, 06, 21, 25, 31, 36 |
| V-3 | 노트-코드 불일치 처리 결정(감사 체인 키, POL-002 문구, 세션 유휴 만료) | TW-08, TW-20, TW-16 |
| V-6 | 사용자 PC(Docker Desktop·Chrome/Edge) 실측 | TW-01, 02, 11, 23, 31 |
| V-9 | 9단계 보안 점검(Trivy·SBOM·`pip-audit`·인젝션 시험) 미수행 | TW-13, 15, 18 |

## W1. 범위와 자산
| 자산 ID | 자산 | 민감도 | 소유 컴포넌트 / 위치 |
|---|---|---|---|
| AW-1 | 세션 토큰(쿠키, DB에는 sha256만), CSRF 토큰(세션별) | 민감 | `core/sessions.py`, 브라우저 쿠키/메모리 |
| AW-2 | PIN 해시(scrypt)·실패 카운터 | 민감 | `core/pin.py`, `settings_kv` |
| AW-3 | DB 비밀번호 3종(superuser/owner/app) | 매우 민감 | `web/secrets/*`(호스트, 저장소 제외), 컨테이너 `/run/secrets` |
| AW-4 | 승인 HMAC 키 `approval_hmac.key` | 민감(승인 위조 수단) | `app_secrets` 명명 볼륨(api·worker 공유, 0600) |
| AW-5 | 구글 OAuth client_secret·읽기/쓰기 토큰 | 매우 민감 | **M2 이후**(현재 존재하지 않음) |
| AW-6 | AI 서비스 API 키 | 민감 | **M3 이후**(현재 존재하지 않음) |
| AW-7 | 영상 메타(제목·설명 발췌·snippet 백업)·제안·승인·배치·이력 | 내부(공개 메타이나 롤백 원천) | PostgreSQL `pgdata` 볼륨 |
| AW-8 | 감사 로그(해시 체인) | 내부(변조 시 책임 추적 불가) | `audit_log` |
| AW-9 | 안전 설정(하루 상한, PIN, 라이브 허용=읽기 전용) | 내부(안전 규칙 자체) | `settings_kv`, `config/settings.yaml`, `config/banned_terms.yaml` |
| AW-10 | 백업 덤프(`web/backups/*.dump`) | 내부(영상 메타·이력·감사 포함, 비암호화) | 호스트 폴더 |
| AW-11 | 컨테이너 이미지·compose 설정·nginx 설정 | 내부(보안 통제 자체) | `web/docker/*`, `web/compose.yaml` |
| AW-12 | 채널의 실제 제목(라이브 반영 대상) | 공개(훼손 영향 큼) | YouTube — **M3 이후** |
| AW-13 | 사용자 PC 자체(호스트 OS, Docker 엔진) | 최상위 | 범위 밖(전제) |

## W2. 데이터 흐름과 신뢰 경계
```
[사용자 브라우저(Chrome/Edge)] ──TB-1──▶ 호스트 127.0.0.1:8080 ─▶ [web: nginx 비루트, edge+app 네트워크]
        ▲ 다른 사이트/확장/앱(TB-1')                                  │ Host 444, 보안 헤더, 속도·크기 제한
                                                                    ▼ TB-2 (app 네트워크 internal:true)
                                                   [api: FastAPI 비루트] ◀─ 같은 이미지 ─▶ [worker 비루트]
                                                          │ TB-3 (scram, 사설 대역 pg_hba)        │
                                                          └──────────────▶ [db: PostgreSQL 17] ◀──┘   볼륨: pgdata, backups, app_secrets
 TB-4: 컨테이너 ↔ 호스트(secrets 파일, 백업 폴더, Docker 엔진)    TB-7: 공급망(PyPI·npm·레지스트리)
 TB-5: api/worker ↔ 구글·YouTube  (M1: 코드 없음, M2·M3는 compose.online.yaml로만 egress)
 TB-6: api/worker ↔ AI 서비스     (M1: 모의, M3 실서비스)
```
| 경계 | 설명 | M1 상태 |
|---|---|---|
| TB-1 | 브라우저↔nginx. 같은 PC의 다른 사이트·확장·다른 프로세스도 이 경계로 접근(TB-1') | 활성 |
| TB-2 | nginx↔api. `app` 네트워크는 `internal: true`, api·worker·db는 호스트 포트 없음 | 활성 |
| TB-3 | api/worker↔db. 앱 계정은 비슈퍼·DDL 불가 | 활성 |
| TB-4 | 컨테이너↔호스트. 비밀 파일·백업·엔진 소켓(마운트 안 함) | 활성 |
| TB-5·TB-6 | 외부 서비스. 기본 compose에서는 외부 통신 경로 자체가 없음 | **비활성(데모)** |
| TB-7 | 설치·빌드 시점 의존성 | 활성 |

## W3. 위협 식별 (STRIDE)
가능성·영향은 H/M/L, 위험도는 완화 **전** 기준이다. "상태" = 구현 상태(위 표기 규칙).

### 위장 (Spoofing)
| 위협 ID | 경계/컴포넌트 | 시나리오 | 가능성 | 영향 | 위험도 | 완화와 증거 (상태) | 대응 ID | 잔여 위험 |
|---|---|---|---|---|---|---|---|---|
| TW-01 | TB-1 브라우저 | 악성 웹사이트가 사용자의 브라우저로 `127.0.0.1:8080`에 요청해 세션 발급·승인·반영을 시도(CSRF·로그인 CSRF) | M | H | 상 | **구현됨 [코드]**: 상태 변경·세션 발급은 `Sec-Fetch-Site`가 있으면 same-origin만, `Origin`은 허용 목록과 정확 일치(없음·null 거부)(`web/backend/ytweb/core/deps.py verify_same_origin`); 세션 결합 CSRF 토큰 `hmac.compare_digest`(`deps.py require_csrf`); 쿠키 `HttpOnly; SameSite=Strict; Path=/api`(`routers/auth.py _set_cookie`); CORS 미들웨어 없음(`app.py`); 상태 변경 비-GET. 브라우저 실동작은 `미확인`(Secure 없는 쿠키, Q-WA-1) | S-W02, S-W03, S-W04 | 낮음 |
| TW-02 | TB-1 DNS | DNS 리바인딩: 공격자 도메인이 127.0.0.1로 해석되어 same-origin처럼 요청 | M | H | 상 | **구현됨 [코드]**: nginx `map $http_host` 허용 2개 외 `return 444`(`web/docker/nginx/nginx.conf`); 앱 Host 허용 목록 403, 헬스 경로만 예외(`core/guard.py`). 불허 Host 무응답은 `[보고값]` | S-W01, S-W02 | 낮음. Host 검증은 인증을 대신하지 않음 |
| TW-03 | TB-1' 같은 PC | 같은 PC의 다른 프로세스·사용자가 `Origin`·`Host`를 위조한 비브라우저 요청(curl 등)으로 **PIN 없이 세션 발급** 후 API 전체 조작 | M | H | 상 | **부분**: PIN 옵션(기본 꺼짐, DEC-034)(`core/pin.py`), 세션 발급 속도 제한 앱 10/분(`core/ratelimit.py`)·nginx 10r/m, 모든 세션 발급·거부를 감사 기록(`routers/auth.py`), 반영은 사람 승인+확인 문구 필요, 라이브 허용은 API로 변경 불가. M1은 모의라 실제 채널 피해 없음 | S-W02, POL-010 | **중 — 수용 질문 Q-W7, M3 전 PIN 필수화 Q-W1** |
| TW-04 | PIN 입력 | PIN 무차별 대입 | L | M | 중 | **구현됨 [코드]**: 숫자 4~12자리 scrypt(n=2^14) + 상수 시간 비교, 5회 연속 실패 시 5분 잠금·잠금마다 2배(최대 1시간), 실패 기록은 롤백 전에 commit(`core/pin.py`) | S-W02 | 낮음(전역 카운터라 공격자가 소유자를 잠글 수 있음 — TW-30) |
| TW-05 | TB-5 구글/OAuth | 가짜 콜백·인가 코드 가로채기·리디렉션 위장 | L | H | 중 | **M2 예정**: state(서버측)·PKCE S256·redirect 정확 일치·scope 검사(planning §W7-3 a~h) | S-W08 | M2 전 설계 필요 |

### 변조 (Tampering)
| 위협 ID | 경계/컴포넌트 | 시나리오 | 가능성 | 영향 | 위험도 | 완화와 증거 (상태) | 대응 ID | 잔여 위험 |
|---|---|---|---|---|---|---|---|---|
| TW-06 | 반영 워커/DB | 재전송·워커 중복·재시작 중 같은 영상 이중 변경, 하루 상한 초과 | M | H | 상 | **구현됨 [코드]**: 부분 고유 인덱스 `uq_batch_items_active_suggestion`, `uq_changes_planned_per_video`(`db/models.py`); `FOR UPDATE SKIP LOCKED`; PG advisory lock(`domain/batches.py`·`limits_quota.py`); `Idempotency-Key`(`core/idempotency.py`, 위험 라우트에 적용); 기동 시 running 항목 복구(`worker.py`). PG 동시성 시험 `[보고값]`. 재시작 중 중복은 `미확인`(8단계) | S-W12, W-010 | 낮음~중 (워커 1개 전제 A-W14) |
| TW-07 | 승인 | 승인 변조·재사용·영상이 바뀐 뒤 승인 유효 | L | H | 상 | **구현됨 [코드]**: plan_hash 묶음, HMAC(`approval_hmac.key`) 검증, 1회용 `used_at`, TTL, 제목 수정·영상 변경 시 무효(`domain/suggestions.py check_approval`, `edit_title`→`_drop_approval`). 실패 시 `approval_tampered`. 키 파일 0600, 없으면 검증 실패(생성은 승인 시점만) | SEC-025, POL-011 | 앱 볼륨·DB를 모두 읽고 쓸 수 있는 공격자는 위조 가능(TW-31 범위) |
| TW-08 | 감사 로그 | 이력·감사 기록 삭제·수정으로 책임 추적 방해 | L | M | 중 | **부분**: 앱 계정에 `audit_log` UPDATE/DELETE/TRUNCATE 회수(`alembic/versions/0001_initial.py REVOKE_AUDIT_MUTATION`, 복원 후 `web/docker/db/audit-guard.sql`로 재회수·검사); 해시 체인 `sha256(prev+canonical_json)`·`chain_ok`(`core/audit.py`). **한계 [코드]**: 체인에 키가 없어 DB owner·슈퍼유저가 재계산 가능, 꼬리 절단 미탐지, `changes`·`batches` 등 다른 테이블은 앱 계정이 UPDATE/DELETE 가능. README §9·DEC-041 ④의 "서명 키" 서술과 코드 불일치 | S-W16 | 중 — Q-W6 |
| TW-09 | DB | SQL 인젝션 | L | H | 중 | **구현됨 [코드]**: ORM·바인딩만. `text()` 사용은 상수 `SELECT 1`·`pg_advisory_xact_lock(:k)`·인덱스 조건 조각(`db/models.py`)뿐(grep 확인) | S-W13 | 낮음 |
| TW-10 | 리포트 CSV | 제목·설명에 수식을 넣어 엑셀 실행(CSV 수식 주입) | L | M | 하 | **구현됨 [코드]**: `domain/reports.py csv_safe`(= + - @ 탭 CR 앞에 `'`), UTF-8 BOM | S-W13 | 낮음 |
| TW-11 | 프런트 | 제목·설명·AI 응답의 스크립트 삽입(XSS) | L | H | 중 | **구현됨 [코드]**: React 기본 이스케이프, ESLint 금지 규칙(`dangerouslySetInnerHTML`·`innerHTML`·인라인 `style`·`localStorage`)(`web/frontend/eslint.config.js`), CSP `script-src 'self'`·인라인 스크립트 없음(`nginx/security-headers.conf`, 빌드 산출물 확인은 `[보고값]`). 잔여: `style-src-attr 'unsafe-inline'`(스타일 속성만), 실브라우저 CSP 오류 여부 `미확인` | S-W04, S-W05 | 낮음 |
| TW-12 | 호스트 파일 | 백업 덤프·`web/secrets` 변조 후 복원/기동 시 악성 데이터 유입 | L | M | 하 | 부분: 복원은 파일명 정규식·확인 문구·SHA-256 출력·복원 전 자동 백업·단일 트랜잭션(`web/scripts/restore.ps1`, `ytweb-db`, README §3). 호스트 장악은 범위 밖(AW-13) | W-016, POL-016 | 수용 후보 |
| TW-13 | TB-7 공급망 | 악성·환각 패키지, 취약 이미지, 도구 침해 | L | H | 중 | **부분**: 파이썬 `pip install --only-binary --require-hashes`(`web/docker/api.Dockerfile`), `npm ci --ignore-scripts`(`web.Dockerfile`), 베이스 이미지 digest 고정 4종. **미수행**: 백엔드 `pip-audit`, Trivy·SBOM, 백엔드 라이선스 개별 확인, 전이 의존성 설치 훅 점검. Trivy 도구 자체의 침해 이력(2026-03)이 있어 digest 고정·`latest` 금지 필요 | S-W11, D-04, D-11, NFR-019 | 중 — 9단계 |
| TW-14 | 반영/롤백 경로 | 제목 변경이 설명·태그를 덮어씀(미지정 속성 삭제), 롤백이 Studio에서 고친 내용을 덮어씀 | M | H | 상 | **부분 [코드]**: 반영은 호출 직전 재조회·snippet 전체 보존+제목만 교체·재조회 검증(`domain/batches.py _check_body`·`verify_snippet`). 롤백은 **백업 snippet 전체**를 보내고 현재 제목이 방금 반영한 제목인지 확인하지 않음(`domain/changes.py rollback_change`). 모두 **모의 게이트웨이로만 시험** | SEC-005·010 승계(CLI), RISK-033 | **상 — M3 전 결정, 실계정 1건 시험** |
| TW-15 | AI 입력/출력 | 영상 설명 속 지시문(간접 프롬프트 인젝션)·환각으로 제목 조작 | M | H | 상 | §W4 참고 | SEC-021~030, S-W06 | M3 전 재평가 |

### 부인 (Repudiation)
| 위협 ID | 경계/컴포넌트 | 시나리오 | 가능성 | 영향 | 위험도 | 완화와 증거 (상태) | 대응 ID | 잔여 위험 |
|---|---|---|---|---|---|---|---|---|
| TW-16 | 승인·반영·롤백 | "내가 승인하지 않았다"/누가 무엇을 바꿨는지 불명 | L | M | 하 | **구현됨 [코드]**: 세션 발급·거부, 설정 변경, 제안 생성·수정(전후 제목)·승인·반려, 배치 생성·실행·취소, 반영, 롤백을 `audit.record`로 기록(`routers/auth.py`, `domain/*.py`에 audit.record 호출 9곳 + `routers/auth.py`·`routers/settings.py`). 승인자 이름은 **사용자가 입력한 문자열**(인증된 신원 아님, 1인 운영 전제) | S-W16, NFR-008 승계 | 낮음 |

### 정보 노출 (Information disclosure)
| 위협 ID | 경계/컴포넌트 | 시나리오 | 가능성 | 영향 | 위험도 | 완화와 증거 (상태) | 대응 ID | 잔여 위험 |
|---|---|---|---|---|---|---|---|---|
| TW-17 | 로그·오류 | 로그·오류 응답에 비밀·스택트레이스·경로·입력 원문 | M | H | 상 | **구현됨 [코드]**: JSON 로그 마스킹(키=값·Bearer·URL 자격증명·40자 이상 토큰)(`core/logsetup.py`); 접근 로그는 method/path/status/ms/request_id만; uvicorn `--no-access-log`(`compose.yaml`); nginx 로그 형식에 쿼리·쿠키 없음; 422는 입력값 에코 금지(`app.py _validation`); 500은 일반 문구(`core/guard.py`); `/docs`·`/openapi.json` 기본 비활성(`YTWEB_ENABLE_DOCS=0`) | S-W09 | 낮음(패턴 밖 비밀 형식은 놓칠 수 있음) |
| TW-18 | 이미지·저장소 | 비밀이 이미지·compose·환경변수·저장소에 들어감 | M | H | 상 | **구현됨 [코드]**: 비밀은 `secrets: file`·`*_FILE` 경로만(`compose.yaml`), `.dockerignore`·`.gitignore`가 `web/secrets/`·`web/backups/`·`token*.json`·`client_secret*.json` 등 제외. 이미지 레이어 비밀 스캔은 `미수행`(9단계) | D-05, D-06, S-W08 | 낮음~중 |
| TW-19 | 백업 파일 | 비암호화 백업 유출(영상 메타·이력·감사 로그 포함) | L | M | 중 | **부분**: 비밀번호·승인 키는 백업에 불포함, 복원 전 자동 백업. 암호화·보관 기간 미정(README는 "암호화 없음" 경고만) | W-016, POL-016 | 중 — Q-W4 |
| TW-20 | 세션 | 세션/CSRF 토큰 탈취·고정, 장기 유효 세션 | L | M | 중 | **구현됨 [코드]**: 256비트 CSPRNG 토큰, DB는 sha256만, 로그인(발급)마다 새 토큰, 로그아웃 시 서버 삭제, PIN 변경 시 다른 세션 폐기, JS 메모리에만 CSRF 보관(저장소 금지 lint). **갭 [코드]**: 절대 만료 12시간만 있고 **유휴 만료는 없음**(`last_seen`은 기록만 하고 판정에 쓰이지 않음, `core/sessions.py`) — 축 D 2-1 권장(유휴 30분·절대 8시간)보다 느슨. CSRF 토큰은 DB에 평문(세션 쿠키 없이는 무용) | S-W04 | 낮음~중 |
| TW-21 | TB-3 DB | DB에 외부/다른 컨테이너 접근, 앱 계정 권한 과다 | L | H | 중 | **구현됨 [코드]**: db는 `internal` 네트워크만·호스트 포트 없음, `pg_hba.conf` 모두 scram-sha-256+사설 대역+나머지 reject, 앱 계정 비슈퍼·`ALTER DEFAULT PRIVILEGES`로 DML·시퀀스만(`web/docker/db/schema-grants.sql`), 소유자 계정은 `migrate` 1회성에만, 비밀번호 16자 이상·서로 달라야 함(`01-roles.sh`). DDL 거부·audit 권한은 `[보고값]`(클라우드 실측). 내부 구간 TLS 없음(README §9) | S-W13a, D-07a | 낮음 |
| TW-22 | TB-6 AI | 외부 AI로 개인정보·불필요 데이터 전송, 국외 이전 | M | M | 중 | **부분**: `VideoBrief`는 영상 ID·제목·설명 요약(500자)뿐, 연락처·링크·주민번호 모양 마스킹(`ai/guard.py build_summary·mask_pii`). 전송 미리보기·영상 단위 제외·고지 UI **미구현**, 서비스 미정(Q-1) | S-W07, SEC-026, POL-007 | 중 — M3 전 |
| TW-23 | 응답 헤더/캐시 | 클릭재킹, MIME 스니핑, 민감 응답 캐시 | L | M | 하 | **구현됨 [코드]**: nginx 모든 location에 `add_header ... always`로 CSP·nosniff·X-Frame-Options DENY·Referrer-Policy same-origin·Permissions-Policy·COOP·CORP 7종, `/api/`는 `Cache-Control: no-store`(`nginx/security-headers.conf`, `nginx.conf`); 백엔드 헤더는 `proxy_hide_header`로 중복 제거. 모든 location의 헤더 존재는 `[보고값]` | S-W04 | 낮음 |
| TW-36 | TB-2/TB-4 `web` 컨테이너 | `web`(nginx)이 게시용 비 internal `edge` 네트워크에 붙어 있어, 침해되면 외부로 데이터를 보낼 수 있는 이론상 경로 | L | M | 중 | **부분 [코드]**: nginx는 정적 파일과 고정 업스트림(`http://api:8000`, 사용자 입력으로 바뀌지 않는 변수)만 프록시, 비루트·`read_only`·`cap_drop: ALL`(`compose.yaml`, `nginx.conf`). `edge`에는 `web`만 붙음(INF 노트 실측 `[보고값]`). 외부 egress 차단은 구현되어 있지 않음(internal 네트워크만으로는 게시가 안 된다는 이유, 편차 #1) | D-10, S-W14 | 낮음~중 — 사용자 PC에서 방화벽/아웃바운드 점검은 선택 |
| TW-24 | TB-1' 브라우저 확장 | 호스트 권한 확장이 같은 출처 페이지의 DOM·토큰을 읽거나 API 호출 | L | H | 중 | **완화 불가에 가까움**(축 D 1-8, 근거 약함): HttpOnly 쿠키는 JS로 못 읽지만 확장은 페이지 컨텍스트에서 호출 가능. 반영은 확인 문구 직접 입력+승인 필요(M3는 쓰기 재로그인) | S-W02 | **중 — 수용 질문 Q-W7** |

### 서비스 거부 (Denial of service)
| 위협 ID | 경계/컴포넌트 | 시나리오 | 가능성 | 영향 | 위험도 | 완화와 증거 (상태) | 대응 ID | 잔여 위험 |
|---|---|---|---|---|---|---|---|---|
| TW-25 | TB-1/TB-2 | 요청 폭주·대용량 본문·느린 요청 | M | M | 중 | **구현됨 [코드]**: nginx `limit_req` 30r/s(burst 60)·인증 10r/m, `client_max_body_size 1m`, 헤더·본문 타임아웃, 메서드 제한(`nginx.conf`); 앱 1MB 계수(chunked 포함)·전역 600/분·쓰기 120/분·세션 10/분(`core/guard.py`, `core/ratelimit.py`). Docker Desktop에서는 모든 요청이 같은 IP로 보여 사실상 전역 제한(설계 의도). 임의 기본값 | S-W13, NFR-013 | 낮음 |
| TW-26 | 쿼터 | API 쿼터 소진 | M | M | 중 | **구현됨 [코드]**: 반영 1건당 3행 선예약(전부 아니면 전무)·PT 날짜 기준·advisory lock·자동 재시도 없음(`domain/limits_quota.py`, `batches.py`). 실제 쿼터 값 `[확인 필요]` | RISK-006 승계 | 낮음 |
| TW-27 | 컨테이너 | 자원 고갈로 PC 지연 | L | M | 하 | **구현됨 [코드]**: 서비스별 cpus/memory/pids 상한(`compose.yaml deploy.resources.limits`) | D-14 | 낮음 |
| TW-28 | 워커 | 워커가 멈춰 예약 반영이 조용히 안 됨 | M | M | 중 | **부분**: `unless-stopped`, 헬스체크는 프로세스 생존만(하트비트 아님), 화면에 대기열·다음 실행일 표시. 하트비트는 백로그(DEC-041 ②) | D-08, W-017 | 중 |
| TW-29 | 볼륨 | `down -v`·`docker volume rm` 실수로 데이터 삭제 | M | H | 중 | **부분**: 스크립트에 `-v` 없음, 삭제는 `reset-demo.ps1 -DeleteVolumes`+확인 문구+사전 백업. 사용자가 직접 명령을 치는 경우는 막지 못함 | D-07 | 낮음 |
| TW-30 | PIN | 공격자의 반복 실패로 소유자가 최대 1시간 잠김 | L | L | 하 | 설계상 전역 카운터(소유자 1명 전제). 해제 수단은 시간 경과 | S-W02 | 수용 후보 |

### 권한 상승 (Elevation of privilege)
| 위협 ID | 경계/컴포넌트 | 시나리오 | 가능성 | 영향 | 위험도 | 완화와 증거 (상태) | 대응 ID | 잔여 위험 |
|---|---|---|---|---|---|---|---|---|
| TW-31 | TB-4 컨테이너→호스트 | 컨테이너 탈출·호스트 자원 접근 | L | H | 중 | **구현됨 [코드]**: 전 서비스 비루트 user, `read_only: true`, `cap_drop: [ALL]`, `no-new-privileges`, `init`, 특권·호스트 네트워크·`docker.sock` 마운트 없음(`compose.yaml`), 쓰기 가능 경로는 tmpfs·명명 볼륨뿐. `docker inspect` 실측·정적 점검 35건은 `[보고값]` | S-W14, D-03 | 커널/엔진 취약점은 범위 밖 |
| TW-32 | 앱 DB 계정 | 앱 계정 침해로 스키마 변경·슈퍼유저 기능 사용 | L | H | 중 | **구현됨 [코드]**: 앱 계정 NOSUPERUSER·NOCREATEROLE 등, 스키마 소유자는 별도 `ytweb_owner`(마이그레이션 전용), 앱은 DML만 | S-W13a | 낮음. 앱 계정은 `changes` 등을 UPDATE/DELETE 가능(TW-08) |
| TW-33 | 설정 API | 라이브 반영 허용·허용 영상 목록을 API로 켜서 안전 장치 우회 | L | H | 중 | **구현됨 [코드]**: 설정 PATCH 허용 키 4개(`daily_apply_cap`, `suggestions_per_video`, `tone`, `pin`) 외 400 `setting_not_allowed`(`routers/settings.py ALLOWED_KEYS`), `WebSettings.MODES = ("demo",)`(`config.py`), 라이브 게이트웨이 코드 없음, 정책의 `enable_live`는 `settings.local.yaml`에서만 인식 | S-W03, POL-010 | M3에서 별도 확인 절차(재인증/확인 문구) 설계 필요 |
| TW-34 | 문서/관리 화면 | `/docs`·OpenAPI·관리 경로 노출 | L | L | 하 | **구현됨 [코드]**: `docs_url`·`openapi_url`은 `enable_docs`일 때만(`app.py`), compose는 0. 웹소켓은 거부(`core/guard.py`) | S-W13 | 낮음 |
| TW-35 | 서버 측 요청 위조(SSRF) | 서버가 사용자 입력 URL을 가져옴 | — | — | 해당 없음 | **해당 없음 — 사유**: M1에 서버가 임의 URL을 가져오는 기능이 없다(썸네일 프록시 없음, 외부 호출 코드 없음). M2에서 구글 API 고정 호스트만 호출하도록 재평가 | S-W13 | M2 재평가 |

## W4. LLM/AI 기능 추가 위협 (규칙 J) — 영상 설명 등 외부 문자열이 AI로 들어가고 결과가 화면·DB·배치로 흐른다
M1은 모의 AI이므로 "입력 쪽 방어"는 실서비스 어댑터가 생기는 M3에서 처음 시험된다. 아래는 구조가 막는 것과 아직 막지 못하는 것을 구분한다.
| OWASP LLM | 위협 | 이 시스템에서의 경로 | 완화(상태) | 대응 SEC/POL |
|---|---|---|---|---|
| LLM01 프롬프트 인젝션 | 설명·제목 속 지시문이 제안을 조작 | 영상 설명 발췌 → `VideoBrief.summary` → AI | **영향 범위 축소 중심**(NCSC: 완전 방어는 어려움): AI 권한 0(구조), 응답 정제, 검증기·사람 승인 필수. 입력 정제·길이 상한은 구현됨(`ai/guard.py`), 지시/데이터 구획은 M3 | SEC-021, 022, 024, 025 |
| LLM02 민감 정보 노출 | 설명의 이름·연락처가 외부로 | 설명 → AI | 마스킹·최소 전송 구현됨. 미리보기·고지·서비스 약관 확인 미완 | SEC-026, POL-007 |
| LLM05 부적절한 출력 처리 | AI 문자열이 화면·CSV·SQL·로그로 흘러 XSS/수식/인젝션 | AI 응답 → `sanitize_drafts` → 검증기 → DB → React/CSV | 구현됨: URL·연락처·제어문자 폐기, `<` `>` 검증기 차단, 텍스트 렌더링, `csv_safe`, ORM 바인딩, 로그 마스킹 | SEC-023, 029 |
| LLM06 과도한 권한 | AI가 도구·API를 호출 | 어댑터 SDK | 구조상 권한 없음(`TitleSuggester`는 텍스트만 반환). SDK 도구 기능 비활성은 M3 확인 | SEC-022 |
| LLM07 시스템 프롬프트 유출 | 프롬프트 노출 | 어댑터 | 프롬프트에 비밀·내부 로직을 넣지 않는다는 원칙, 원문 미저장(`prompt_hash`). 실서비스는 M3 | SEC-028 |
| LLM09 허위 정보 | 영상에 없는 내용을 약속하는 제목 | AI 응답 | 영상 일치율 검증(`youtube_title.validator`), 엄격 모드, 사람 승인. **AI 지정 `topic` 의존** 주의(SEC-024, Q-W10) | SEC-024, POL-008 |
| LLM10 무제한 소비 | 호출·재시도·비용 폭주 | 제안 생성 잡(영상 N개) | **미구현(M3)**: 호출·토큰·비용 상한과 빈도 제한 없음. 현재는 자동 재시도 없음 | SEC-027 |
| LLM03 공급망 | SDK·이미지 | 어댑터 의존성 | 일반 의존성 점검(TW-13)에 포함 | S-W11 |
| LLM04·08 | 학습/벡터 오염 | 자체 학습·RAG 없음 | **해당 없음 — 사유**: 자체 모델·임베딩이 없다. 설계가 바뀌면 재평가 | — |
| 투명성 | 사용자가 AI 결과임을 모름 | 제안 카드·이력 | **부분**: "AI 제안" 라벨만. 고지 문장 미구현 | POL-006, POL-008 |

## W5. 구현 증거 인덱스 (이 개정에서 직접 읽어 확인한 파일)
`web/compose.yaml`(게시 포트, 하드닝, 네트워크, 시크릿, 자원 상한), `web/docker/nginx/{nginx.conf,security-headers.conf,proxy.conf}`, `web/docker/db/{pg_hba.conf,schema-grants.sql,audit-guard.sql,init/01-roles.sh}`, `web/docker/{api,web}.Dockerfile`, `web/backend/ytweb/{app.py,config.py}`, `core/{guard.py,deps.py,sessions.py,pin.py,ratelimit.py,audit.py,logsetup.py}`, `routers/{auth.py,settings.py,google.py,health.py}`, `ai/{base.py,guard.py,mock.py,factory.py}`, `domain/{suggestions.py,batches.py(apply_one 일부),changes.py(rollback),exclusions.py,reports.py(csv_safe)}`, `db/models.py`(인덱스·제약), `worker.py`(기동 복구·SIGTERM), `web/frontend/eslint.config.js`, `src/i18n/ko.ts`(문구 검색). **직접 확인하지 않은 것**: 테스트 수치·PG 동시성·`docker inspect`·axe·스크린샷·`pwsh` 동작(모두 노트의 보고값).

## W6. 수용하는 잔여 위험 — 사용자 결정 대기 (규칙 A)
| 위협 ID | 수용 후보 사유 | 수용 결정자 | decisions.md ID |
|---|---|---|---|
| TW-03, TW-24 (같은 PC의 다른 프로세스·브라우저 확장) | 개인 PC 도구의 방어 범위를 넘음. 완화(PIN 옵션·속도 제한·감사·사람 승인·확인 문구)만 있고 완전 차단 불가 | **사용자 확인 대기(Q-W7)** | (대기) |
| TW-12 (호스트 파일 변조), TW-30 (PIN 잠금 DoS) | 호스트 장악 범위 밖 / 영향 작음 | 사용자 확인 대기 | (대기) |
| TW-08 (감사 체인의 키 부재) | 앱 계정 침해까지는 방어, owner·슈퍼유저는 범위 밖 | 사용자 확인 대기(Q-W6) | (대기) |
- **위험도 "상" 위협(TW-01, 02, 03, 06, 07, 14, 15, 17, 18)은 사용자가 수용할 수 없다.** 현재 "상" 가운데 완화 후에도 미해소인 것: **TW-14**(실서비스 시험·롤백 정책, M3 전 해결), **TW-15**(M3 전 재평가), **TW-03**(PIN 필수화·수용 결정), 그리고 TW-01·02의 **사용자 PC 실측**. 이들은 해결 전에는 M3(라이브 반영)로 넘어가지 않는다.
- 위험도 High 위협을 대응 없이 수용하는 항목은 **없다**.

## W7. 9단계 인계
- 9단계가 구현 여부를 확인할 ID: **S-W01~S-W16 전부**, D-02·D-03·D-05·D-06·D-07a·D-10·D-11, **SEC-021~030**(제안 ID, 번호 확정 후), POL-002·006~008·013·016, TW-01~36.
- 특히 확인할 것: ①Host 위조·Origin 위조·Sec-Fetch-Site 우회 시도(비브라우저 포함) ②세션 만료·고정·PIN 잠금 ③컨테이너 강제 종료·DB 재시작 중 이중 반영 ④`audit_log` 권한(복원 후 포함) ⑤CSP 위반 로그를 브라우저에서 확인 ⑥백엔드 `pip-audit`, 이미지 Trivy·SBOM ⑦인젝션 시험 세트(M3) ⑧127.0.0.1 한정 실측(Docker Desktop) ⑨롤백이 다른 필드를 덮어쓰는지(실계정 1건, 사용자 승인 후).

## W8. 변경 이력 (Part W)
| 일시 | 버전 | 변경 내용 | 사유 |
|---|---|---|---|
| 2026-10-10 | v1-W0 | 웹·컨테이너 STRIDE 신설(TW-01~35), LLM 위협 표, 증거 인덱스, 잔여 위험 수용 질문 | S-W15, 웹 전환 문서 개정(as-built) |
| 2026-10-10 | v1-W1 | 2차 검증 반영: TW-36(web의 edge 네트워크 경유 이론상 egress) 추가, 검증 대기 표 갱신 | 규칙 B 2차 검증 |

## W9. M2·M3 구글 연결·실제 제목 수정 위협 추가 (STRIDE, 2026-10-11, v1-W2)

- **상태 표기**: 코드와 가짜 구글 자동 시험으로만 확인했다. **실제 구글 접속·실제 제목 변경·Windows Docker Desktop 실행은 하지 않았다**(`[미검증-실제환경]`). 독립 검증·9단계 보안 재검증은 아직 이 장을 다루지 않았다(확인 필요). 근거 파일: `web/backend/ytweb/youtube/google_oauth.py`, `live_read.py`, `live_write.py`, `domain/live_gateway.py`, `routers/google.py`, `domain/batches.py`, `domain/changes.py`, `core/logsetup.py`, `web/compose.online.yaml`, `web/docker/nginx/nginx.conf`.
- **TW-05 구체화**: 위 TW-05(가짜 콜백·코드 가로채기)는 아래 TW-37로 이어진다. S-W08 대응 시험은 `test_google_oauth.py`(TC-M2-001~017), `domain/test_google_router.py`(TC-M2-020~031).
- **S-W03 예외**: `GET /api/v1/google/callback` 은 구글에서 되돌아오는 브라우저 이동이라 SameSite=Strict 세션 쿠키가 실리지 않아 세션·CSRF 대신 1회용 state+PKCE 로 보호한다(DEC-048). **'GET 은 상태를 바꾸지 않는다'의 유일한 예외**이며, 상태 변경은 토큰 파일 저장과 감사 기록뿐이다.

| 위협 ID | STRIDE | 경계/컴포넌트 | 시나리오 | 가능성 | 영향 | 위험도 | 현재 완화책과 증거 (상태) | 잔여 위험 |
|---|---|---|---|---|---|---|---|---|
| TW-37 | S, T | OAuth 콜백(TB-5 구글) | 공격자가 가짜 콜백 주소(`?code=…&state=…`)를 사용자 브라우저로 열게 해 공격자의 구글 계정 토큰을 저장시키거나(로그인 CSRF), 인가 코드를 가로채 교환 | L | H | 중 | **구현됨 [코드]**: state 256비트·1회용·10분 만료·최대 20개 보관(`PendingAuth`), 모르는/재사용/만료 state 는 코드 교환 자체를 안 함(TC-M2-003~006, 026, 027), PKCE S256(TC-M2-001·009), 인가 코드·state 길이 상한(TC-M2-031), 거부/오류 시 아무것도 저장 안 함(TC-M2-028·029), 모든 시도 감사 기록(`google.connect.*`). 콜백 후 303 으로 `/#/` 이동, `Cache-Control: no-store`. nginx 접근 로그는 쿼리 문자열을 기록하지 않음(`$uri`) | 중간: 로그인을 시작한 세션과 콜백을 묶지 않음(state 는 서버 전체에 대해 유효). 같은 PC 의 다른 프로세스는 state 를 알 수 없지만 로그인 CSRF 완전 차단은 아님. 복귀 주소가 http 루프백이라 브라우저 기록·주소창에 코드가 잠시 남음(1회용·PKCE 로 완화). nginx **오류 로그**의 쿼리 문자열 억제는 부분(DEF-VI-003 재평가 대상). 데스크톱 앱 클라이언트가 이 복귀 주소를 실제 구글이 받아 주는지 `[미검증-실제환경]` |
| TW-38 | I, E | 쓰기 토큰 `google_write_token.json` / `app_secrets` 볼륨 | 쓰기 토큰(`youtube.force-ssl`)이 탈취되면 공격자가 **허용 목록과 무관하게** 채널의 모든 영상을 수정·삭제할 수 있음(구글 쪽 권한이므로 이 프로그램의 안전장치 밖) | L | H | 상 | **부분**: 쓰기 토큰은 읽기 토큰과 **별도 파일**, 0600 원자적 저장(TC-M2-014), 클라이언트 파일은 Docker secret(api·worker 에만), 토큰은 응답·주소·로그·감사 기록에 싣지 않음(TC-M2-008·025, 로그 마스킹 `core/logsetup.py`), [연결 해제] 한 번으로 둘 다 삭제(TC-M3-012), 쓰기 권한은 필요할 때만 연결하도록 운영 안내(`WEB_RUNBOOK.md` 15장) | **높음**: 토큰 파일은 **암호화되지 않음**, 백업 대상은 아니나 볼륨을 읽을 수 있는 사람/컨테이너 탈출/호스트 장악 시 노출. 이 프로그램은 구글에 권한 취소(revoke)를 요청하지 않아 유출 시 사용자가 구글 계정에서 직접 제거해야 함. **사용자 수용 결정 필요(decisions.md 기록 대기)**. 토큰 만료·갱신 동작은 `[미검증-실제환경]` |
| TW-39 | E, T | 허용 영상 목록 `YTWEB_LIVE_ALLOWED_VIDEOS` / 게이트웨이 선택 | 허용 목록에 없는 영상이 실제로 수정됨(우회): 설정 API 로 목록 변경, 환경변수 조작, 초안·반영·롤백 경로 중 한 곳의 검사 누락, 게이트웨이 선택 오류로 의도치 않게 실제 모드 | L | H | 중 | **구현됨 [코드]**: 목록은 설정 API 로 변경 불가(`ALLOWED_KEYS` 4개, TW-33), 실제 쓰기는 3조건 모두 필요(`select_gateway`, TC-M3-020·021), 목록이 비면 수정 0건(TC-M3 live_write), 검사가 4겹: ①초안 `_eligibility` ②반영 직전(변경 기록·쿼터 전) ③롤백 ④`live_write` 가 네트워크 호출 전에 재검사(TC-M3-042·046·047, `test_live_write.py`), 실제/데모 구분은 `changes.mode`. 허용 영상만 입력으로 받는 `update_snippet` 본문 형식 재검사 | 낮음~중: 환경변수를 컨테이너에 넣는 공식 절차가 아직 없어(Q-11-10) **운영 절차 미정**. 환경변수는 호스트에서 컨테이너 설정을 고칠 수 있는 사람은 바꿀 수 있음(호스트 장악 범위). 오타로 다른 영상 ID 를 넣는 휴먼 에러는 막지 못함 |
| TW-40 | S, T | 실제 모드 확인 문구 | 데모 때의 습관(`실행 N건`)이나 자동화된 요청으로 실제 모드 배치를 실행, 문구 검사 우회 | L | H | 중 | **구현됨 [코드]**: 실제 모드 문구는 `실제 실행 N건` 으로 데모와 다르게 하고(`confirm_text`, TC-M3-040·041), 사전 점검에 경고 추가, 승인(plan_hash·HMAC·1회용·24시간)이 별도로 필요(TW-07), CSRF·Idempotency-Key 필요 | 중: 확인 문구는 사람 확인용이며 같은 PC 의 비브라우저 프로세스가 화면 응답을 읽어 문구를 만들 수 있음(TW-03·TW-24 와 같은 한계). **'A/B 테스트 중이 아님' 확인 서버 필드는 M3 로 미뤄진 상태**(DEC-047 ②) — 실제 반영 전 결정 필요. 화면 상단 띠·연결 상태 칸이 구글 연결 후에도 '데모 모드/아무것도 전송 안 됨'으로 보이는 결함(DEF-VMF-001, High)이 사용자 오판(데모인 줄 알고 실제 실행)을 유발할 수 있음 — **실제 연결 전 수정 필수** |
| TW-41 | T, R | 모호 응답(타임아웃·5xx·새 제목 미확인) | 실제 업데이트가 구글에서 처리됐는지 모르는 상태에서 재시도해 **이중 반영**하거나, 실패로 단정해 기록이 실제와 어긋남 | M | M | 중 | **구현됨 [코드]**: `definite=False` 오류는 한 번 재조회로 확인하고 확인 안 되면 `planned` 기록을 남긴 채 `result_unknown` 으로 중단(자동 정리·자동 재시도 없음, `_confirm_indeterminate`), 응답에 새 제목이 없으면 `unconfirmed`, 쓰기 전에 planned 기록·쿼터·승인 소진을 커밋(TC-M3-031 오류 시 DB 불변), 롤백도 같은 규칙(`gateway_error`) | 중: "예정"으로 남은 항목은 **사람이 유튜브 Studio 에서 확인**해야 함(운영 절차 `WEB_RUNBOOK.md` 15-3). 실제 구글에서의 모호 응답 재현은 `[미검증-실제환경]` |
| TW-42 | I | 로그·감사 로그·오류 응답 | 토큰·인가 코드·클라이언트 비밀이 로그/응답/주소에 남음 | M | H | 상 | **구현됨 [코드]**: 로그 마스킹(token·secret·authorization·40자 이상 토큰 모양, `core/logsetup.py`), OAuth 오류는 한국어 고정 메시지만(TC-M2-008·011), 감사 기록에는 scope·코드 문자열만, nginx 접근 로그에 쿼리 없음, uvicorn 접근 로그 끔 | 중: 마스킹은 패턴 기반이라 형식이 다른 값은 놓칠 수 있음. nginx 오류 로그 쿼리 문자열 부분 억제(DEF-VI-003). 구글 오류 응답 본문 일부가 예외 메시지로 이어지는 경로는 코드 읽기로만 확인 `[확인 필요]` |
| TW-43 | D | 구글 쿼터 | 쓰기 1건 50단위로 하루 쿼터가 소진되어 읽기까지 막힘, 또는 반복 실패로 낭비 | M | M | 중 | **구현됨 [코드]**: 반영 전 쿼터 선예약·하루 상한(TW-26), `quota_exceeded` 는 즉시 중단·자동 재시도 없음. 읽기 최대 2,000개·페이지 상한(TC-M2-045) | 낮음. 실제 쿼터 값·소진 동작 `[미검증-실제환경]` |
| TW-44 | I | 외부 통신 경로(compose.online.yaml) | 구글 통신을 위해 `egress` 네트워크에 붙은 api·worker 가 침해되면 데이터가 외부로 나감 | L | M | 중 | **구현됨 [코드]**: `google_client.json` 이 있을 때만 사용, db·web 은 egress 에 붙지 않음, 외부 통신 코드는 3개 모듈로 한정하고 그 밖의 모듈 사용은 시험으로 금지(`test_tc_vb_278` 허용 파일 3개), https 아닌 주소 거부(TC-M2-013·048) | 중: egress 에서 도메인 단위 허용 목록은 없음(컨테이너 방화벽 미구현). DEF-9-011 과 같은 계열 |

### W9-1. 잔여 위험 — 사용자 수용 결정 대기 (규칙 A)
| 위협 ID | 내용 | 결정 | decisions.md ID |
|---|---|---|---|
| TW-38 | 토큰 파일 암호화 없음·구글 권한 취소 요청 미구현 | 대기(수용 또는 구현) | (대기) |
| TW-37 | 로그인 시작 세션과 콜백 비결합, 복귀 주소 http 루프백 | 대기 | (대기) |
| TW-40 | DEF-VMF-001(High) 수정 전에는 실제 연결 금지, 'A/B 확인 서버 필드' 결정 | 수정 후속 조치 예정 | (대기) |
| TW-44 | egress 도메인 제한 없음 | 대기 | (대기) |
- 위험도 "상"인 TW-38·TW-42 는 사용자가 대응 없이 수용할 수 없다. 현재 TW-38 은 완화 후에도 "높음" 잔여다 — **실제 구글 연결 전 결정이 필요하다.**

### W9-2. 9단계 인계 (이 장)
확인할 것: ①콜백 위조·state 재사용·교차 사용(읽기 state 로 쓰기 저장 시도 등, TC-M3-013 참고) ②토큰 파일 권한·백업·로그에 토큰이 없는지(문자열 검색) ③허용 목록 4겹 검사 우회 시도(영상 ID 대소문자·공백·쉼표 처리 포함) ④모호 응답 시 이중 반영 ⑤nginx/uvicorn 로그 쿼리 ⑥egress 네트워크 구성 실측 ⑦DEF-VMF-001 수정 후 화면 문구.

| 일시 | 버전 | 변경 내용 | 사유 |
|---|---|---|---|
| 2026-10-11 | v1-W2 | W9 신설(TW-37~44), TW-05 구체화, S-W03 예외 명시 | M2·M3 구현 반영(DEC-048), 11단계 문서 갱신 |

## W10. 일괄 승인(N건) 위협 추가 (STRIDE, 2026-10-13, v1-W3)

- **상태 표기**: 정적 코드 검토 + 자동 시험(가짜 유튜브, 실제 구글 접속 없음). 출처 `docs/harness/bulk-approve/security-review.md`(조건부 PASS, Critical/High 0건). 결정 대기: SEC-BA-002(승인 유효 시간 기준)·SEC-BA-003(전용 속도 제한).

| ID | STRIDE | 대상 | 위협 | 가능성 | 영향 | 등급 | 대응 | 잔여 |
|----|--------|------|------|--------|------|------|------|------|
| TW-45 | T (변조) | 일괄 승인 경로 | 프런트 조작으로 차단·제외·경고 제안을 일괄 승인에 섞어 서명을 받음 | M | H | 중 | 구현됨 [코드]: 건마다 `approve()` 재검증·서명(domain/suggestions.py:342), 경고 서버 강제 `ack_warning`(:282), 50건 서버 상한(:315) | 낮음: 경고 내용 변경 후 id만 확인(SEC-BA-001) |
| TW-46 | R (부인) | 감사 로그 | 일괄 승인 후 건너뛴 건·승인자 추적 불가 | L | M | 하 | 해시 체인 감사(audit.py), 건별+요약 기록 | 건너뛴 건 id·사유 미기록, 승인자 자기 신고(SEC-BA-004) |
| TW-47 | D (서비스 거부) | 일괄 승인 API | 50건 요청 반복으로 감사 전역 잠금·DB 트랜잭션 장기 점유 | L | M | 하 | 구현됨 [코드]: 50건 상한, 제안 id 오름차순 잠금, nginx 30r/s·1m 본문 제한 | 일괄 전용 속도 제한 없음(SEC-BA-003) |
| TW-48 | E (권한 상승)/T | 승인 시간 창 | 승인 1시간 유효 정책이 이월 항목에서 확정 시각 기준으로만 적용되어 오래된 승인이 반영됨 | L | M | 하~중 | 반영 직전 재조회 제목·plan_hash 대조(batches.py:508-512), 1회용 승인 | 만료 기준 의도 확인 필요(SEC-BA-002) |
| TW-49 | I (정보 노출) | resolve-videos·skipped 사유 | 영상·제안 id 존재 탐지, 오류 메시지 정보 | L | L | 하 | 세션+CSRF 필수, 읽기 전용, 50개 상한, 한국어 사유에 내부 정보 없음 | 단일 소유자 도구라 수용 |
| TW-50 | T (변조) | 멱등 재전송 | 저장된 성공 응답을 재전송해 현재 상태와 다른 결과를 표시 | L | L | 하 | 키·요청 해시 일치 필수, 24시간 TTL | 재전송 응답 표시 방식 미확인(SEC-BA-005) |

| 2026-10-13 | v1-W3 | W10 신설(TW-45~50) | 일괄 승인 기능 보안 검토 반영 |

## W11. 관리자 로그인 위협 추가 (STRIDE, 2026-10-15, DEC-055)

- **상태 표기**: 설계 + 코드 + 자동 시험(`web/backend/tests/core/test_admin_login*.py`, 프런트·인프라 시험). Windows 실기·브라우저 실제 확인은 아직 하지 않았다. 설계서 `ADMIN_LOGIN_DESIGN.md`.

| ID | STRIDE | 대상 | 위협 | 가능성 | 영향 | 등급 | 대응 | 잔여 |
|----|--------|------|------|--------|------|------|------|------|
| TW-51 | S (위장) | 로그인 | 비밀번호 무차별 대입 | M | H | 중 | 연속 5회 실패 시 5분 잠금(반복 시 2배·최대 1시간, 잠금 중 맞는 비밀번호도 거부), 로그인 분당 10회 속도 제한, PostgreSQL advisory lock 으로 동시 추측 직렬화(TC-AL-006·015·102) | 관리자 1명이라 공격자가 일부러 틀려 관리자를 잠글 수 있음(같은 PC 한정, 최대 1시간) |
| TW-52 | I | 로그인 응답 | 아이디 존재 여부·비밀번호 일치 여부 추론(계정 열거, 처리 시간 차이) | L | M | 하 | 아이디·비밀번호 오류가 같은 응답, 아이디 불일치에도 더미 해시로 같은 검증 시간(TC-AL-005) | 단일 계정이라 영향 작음 |
| TW-53 | I | 비밀번호 저장 | DB·백업·로그에서 비밀번호 원문 노출 | L | H | 중 | DB 에는 scrypt 해시만(TC-AL-014), 감사 기록·오류 응답에 값 없음(TC-AL-012·013), 입력값 되돌리기 금지 | `web\secrets\admin_login_password` 파일에는 원문이 있음(PC 1인 전용 전제, 다른 비밀 파일과 같은 취급) |
| TW-54 | E | 로그인 우회 | 익명 세션 발급 경로로 로그인 없이 API 사용 | L | H | 상→중 | 로그인 모드에서 `POST /auth/session` 403, 모든 보호 API 는 세션 필수(TC-AL-002·003), 비밀 파일이 없으면 로그인 불가(닫힘, TC-AL-016) | 로그인 모드를 끄는 설정(`YTWEB_ADMIN_LOGIN=0`)은 compose 파일을 고쳐야 가능(PC 소유자 권한) |
| TW-55 | S/T | 세션 | 훔친 쿠키 재사용·세션 고정·방치된 로그인 화면 | L | H | 중 | HttpOnly·SameSite=Strict, 토큰은 sha256만 저장, 로그인 시 이전 세션 모두 종료(TC-AL-009), **60분 무활동 자동 로그아웃**(서버 `last_seen` + 화면 타이머, TC-AL-008), 비밀번호 변경 시 세션 전부 종료(TC-AL-018), 절대 만료 12시간 | 화면 방치 중 백그라운드 조회가 서버 시간을 갱신하므로 로그아웃은 화면 타이머가 보장 |
| TW-56 | T | CSRF | 다른 사이트가 로그인 요청·로그아웃 요청 유도 | L | M | 하 | 출처(Origin·Sec-Fetch-Site) 검증을 비밀번호 확인보다 먼저(TC-AL-011), 상태 변경은 CSRF 토큰 | — |
| TW-57 | R | 감사 | 로그인 시도 추적 불가 | L | L | 하 | `login.success`/`login.denied` 해시 체인 감사 기록(TC-AL-013) | 접속 IP는 기록하지 않음(127.0.0.1 한정) |

| 2026-10-15 | v1-W4 | W11 신설(TW-51~57) | 관리자 로그인(DEC-055) 위협 반영 |
