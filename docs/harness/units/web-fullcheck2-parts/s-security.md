# S. 보안 도구 재시도 + 침투형 시험 (시작 02:11:59 UTC, 종료 약 02:22 UTC, date -u 실측, 상한 12분 이내)
docker 미사용, git add/commit/push 안 함. 주의: 시험 중 다른 에이전트의 미커밋 변경(google.py 등)이 작업 트리에 있었다. 원인 판별용으로 `git stash`/`stash pop`을 한 번 썼고 복원 확인함(실수로 남의 변경을 잠깐 건드린 것 - 공유 트리에서 하지 말았어야 함). 또 `pip install checkov semgrep`를 공유 venv .harness-tmp/be 에 설치해 opentelemetry-api 1.37.0 으로 fastapi 0.143(>=1.44 요구) 충돌 경고가 났다(앱 import 는 정상 동작 확인, 시험 전부 실행됨). 필요하면 venv 를 되돌릴 것.

## 1. 도구 확보
| 도구 | 시도 | 결과 |
|---|---|---|
| trivy | https://github.com/aquasecurity/trivy/releases/download/v0.58.1/trivy_0.58.1_Linux-64bit.tar.gz | 프록시 404(9바이트) - 확보 실패. 파일시스템/misconfig/secret 스캔 미수행 |
| hadolint | github.com/hadolint/hadolint/releases/download/v2.12.0/hadolint-Linux-x86_64 | 성공(2.4MB) |
| checkov | pip install (3.3.28) | 성공. --offline 옵션 없음, 규칙은 내장이라 네트워크 불필요. docker_compose 프레임워크는 이 버전에 없음 -> Dockerfile 만 검사(compose/GitHub Actions: 저장소에 .github/workflows 없음, compose 는 미검사) |
| semgrep | pip install (1.180.0), 로컬 규칙 web/tests_fullcheck/s/rules/local.yml(7규칙) | 성공, --metrics=off |

## 2. 스캔 결과
| 도구 | 대상 | 결과 |
|---|---|---|
| hadolint | web/docker/*.Dockerfile | DL3006 경고 5건(api:6,18 db:6 web:7,17 "이미지 태그 명시"). 원문 확인 필요: FROM 이 ARG/다이제스트 변수를 쓰면 오탐 가능. 이번에 FROM 줄을 읽어 판정하지 못함(미확인) |
| checkov dockerfile | web/docker | 통과 175, 실패 4: CKV_DOCKER_7 x3(db/web/api FROM "latest 아닌 태그" - hadolint DL3006 과 같은 줄, 같은 미확인), CKV_DOCKER_2 db.Dockerfile HEALTHCHECK 없음(Low; compose 쪽 healthcheck 가 있으면 대체 가능 - 미확인) |
| semgrep 로컬 규칙 | web/backend/ytweb, src (103 파일) | 4건, 전부 sql-string-format (src/youtube_title/commands/purge.py, limits.py = bandit B608 와 동일 지점). web/backend/ytweb 에는 0건. shell=True·eval·yaml.load·verify=False·하드코딩 비밀·md5/sha1 = 0건 |

## 3. bandit B608 5건 판정 (옛 CLI)
purge.py:32,34,69 의 f-string 에 들어가는 `_PROTECT_CHANGES` 는 모듈 상수 문자열(purge.py:20, 사용자 입력 아님); 날짜 cutoff 는 `?` 바인딩. limits.py:99,103,108 의 `{placeholders}` 는 상수 튜플 COUNTED_RESULTS 길이만큼의 `?,?` 이고 값은 모두 바인딩. 외부 입력이 SQL 문자열에 들어가는 경로 없음 -> SQL 주입 불가, 오탐(Info). 재현 시험은 주입 경로가 없어 만들지 않음.

## 4. 침투형 시험 (web/tests_fullcheck/s/test_s_pentest.py, 데모 모드, SQLite 시험 DB, 소켓/urlopen 차단 하에)
최종 실행: 전부 통과, 건너뜀 2(아래). 첫 실행: 실패 4 (아래 해설).
| 항목 | 시도 | 결과 | 판정 |
|---|---|---|---|
| Origin 변조 | null, 외부, 포트 다름, 접미 도메인, 대문자 스킴, https, 포트 없음, userinfo@, 빈 값, 헤더 없음 | 전부 400/403 | 합격 |
| Host 헤더 | evil.com, 접미 도메인, 포트 없음/다름, 빈 값 | 거부 | 합격 |
| CSRF | 로그아웃 DELETE 에 토큰 없음/틀림/Origin 외부 | 거부 | 합격 |
| 로그아웃 후 재사용 | 옛 쿠키 재주입 -> /me, /audit | 미인증, 거부 | 합격 |
| 세션 고정 | 공격자 지정 쿠키(ytw_session) 로 로그인 | 서버가 새 토큰 발급(세션 토큰은 서버 생성), 지정 값으로 인증 안 됨 | 합격 (첫 실행 실패는 시험 코드의 쿠키 이름 오기[ytweb_session->ytw_session], 제품 결함 아님) |
| 위조 쿠키 | 빈값/5000자/SQL/경로/NUL | 미인증 | 합격 |
| 만료 | 절대 13시간, 유휴 31분 | 미인증 | 합격 |
| 인증 없는 접근 | audit,videos,suggestions,batches,changes,settings | 401/403/404 | 합격 |
| 경로 이탈 | ../, %2e%2e, %00, /.env, /backups, /data/*.db | 내용 노출 없음 | 합격 |
| 오류 응답 정보 노출 | 404, 깨진 JSON, 이상 타입, 이상 쿼리 | Traceback/경로/sqlalchemy/psycopg 문자열 없음 | 합격 |
| 큰 본문/깊은 JSON | 5MB PIN, 중첩 10만 | 4xx 로 닫힘(5xx 없음) | 합격 |
| 입력 퍼징 | 18종(제어문자, RLO, 결합문자, SQL/템플릿/NoSQL, 정수 경계, NaN) x PIN 로그인, x 5개 목록 API 쿼리 | 5xx 없음 | 합격 (첫 실행 실패 2건은 시험이 URL 10만자를 만들어 httpx 가 거절한 시험 결함 -> 길이를 줄여 재실행) |
| 데모 외부 호출 | socket.create_connection/urlopen 차단 하에 주요 API | 호출 0건 | 합격 |
| 감사 로그 변조 | SQLite 에서 UPDATE/DELETE | 첫 실행: 변조 가능(실패). 원인: 보호가 PostgreSQL 권한 회수(alembic 0001 REVOKE ... FROM ytweb_app)이고 SQLite 에는 없음 | 건너뜀으로 바꿨음(사유 명시). PG 에서 ytweb_app 역할로의 실제 시험은 미수행 |
| 속도 제한, PIN 무차별 대입, 실제 수정 3조건 우회 재시도(앱 수준), XSS 저장 후 이스케이프(제목·설명) | 시험 작성 못함(시간): 시험 픽스처에 영상/제안 생성·PIN 설정 경로 조사가 필요 | 미수행. 3조건·PIN 은 직전 d-security 시험과 기존 tests/test_auth.py 가 부분 커버 |

## 5. guard.py 수정
20행 `_INVISIBLE = frozenset("<리터럴 8글자>")` -> `frozenset("​‌‍‎‏⁠﻿­")`. 파이썬 문자열 비교로 이전 리터럴과 같은 집합임을 수정 전 스크립트에서 확인(동일 8글자: U+200B,200C,200D,200E,200F,2060,FEFF,00AD). 시험: tests/verify_wa/test_va_11_guard_worker_misc.py, tests/verify_m23, tests/domain, tests/verify_wb/test_vb_01_catalog_suggest.py, tests/test_rule_suggester.py 실행 -> 2건 실패, 둘 다 google 연결 해제 시험(test_tc_vm_125_disconnect_clears_both_tokens_and_audits, test_tc_m2_030_disconnect_clears_token). `git stash` 상태(=커밋된 원본, guard.py 수정 포함 안 됨)에서 같은 두 파일은 전부 통과 -> 실패 원인은 다른 에이전트의 미커밋 google.py 변경이며 guard.py 와 무관. guard 직접 시험(test_va_11, rule_suggester 등)은 통과. (verify_wa/test_va_08 은 시간 부족으로 별도 결과 확인 못함)

## 6. 결함·권고
- 확정 결함 0건(침투 시험 우회 성공 없음).
- 권고(확인 필요): Dockerfile FROM 태그 고정 여부(DL3006/CKV_DOCKER_7), db.Dockerfile HEALTHCHECK(CKV_DOCKER_2).
- 주의: 다른 에이전트의 google.py 변경이 기존 시험 2건을 깨뜨리고 있음(해당 에이전트가 확인해야 함).

## 7. 미수행
trivy 전체(확보 실패), 이미지 스캔·서명 검증(docker 금지), compose/GitHub Actions 정책 검사, 속도 제한·PIN 무차별 대입·XSS 저장 시험·3조건 앱 수준 우회·PG 감사 로그 권한 시험, 실제 브라우저.
