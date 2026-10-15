# D. 보안 추가 점검 (9단계 미수행분) - 결과서
시작 01:44:09 UTC, 종료 약 01:51 UTC(date -u 실측, 상한 12분 이내). 소스 편집 없음. 새 파일: web/tests_fullcheck/d/test_d_security_review.py, 이 문서. docker 미사용. 도구용 venv: .harness-tmp/sec.

## 1. 점검 항목 표
| 항목 | 도구/명령 | 결과 | 건수·심각도 |
|---|---|---|---|
| 파이썬 의존성 취약점 | pip-audit --no-deps --disable-pip -r web/backend/requirements.txt | No known vulnerabilities | 0 |
| 개발 의존성 | 같은 방식 requirements-dev.txt | No known vulnerabilities | 0 |
| npm | npm audit --omit=dev / npm audit (web/frontend) | found 0 vulnerabilities (둘 다) | 0 (Critical/High/Medium/Low 모두 0) |
| 비밀 노출(작업 트리) | git grep 정규식(AIza, GOCSPX-, ya29., -----BEGIN PRIVATE, ghp_, 1//, sk-) | 실제 키 없음. 일치 전부 시험용 가짜 값: tests/integration/it_fab_support.py:27-29, it_fd_support.py:27, test_it_fab.py:293, tests/test_auth.py:14,15,21,124,267, test_edge.py:82, test_logging.py:8-10, tests/wu5_support.py:25,26. 문서 1건 docs/harness/security-web-m1-test.md:495(패턴 설명 문장) | 실제 0 / 가짜 다수(Info) |
| 비밀 노출(git 이력) | git log --all -p 의 추가 줄에 같은 정규식 | 위 가짜 값과 문서 줄만 일치, 실제 형식 키 0 | 0 |
| client_secret 대입 | git grep client_secret | 시험용 가짜 JSON만 | 0 |
| 긴 hex | git grep 40자 이상 hex | 이미지 다이제스트(web/docker/*.Dockerfile)·해시 시험값뿐 | 0 |
| .gitignore | git check-ignore -v | web/secrets/(.gitignore:41), web/.env(:25) 가 google_client.json, gemini_api_key, secrets 하위 파일, .env 모두 차단 | 정상 |
| 추적 중 비밀 파일 | git ls-files 이름 검색 | web/frontend/src/styles/tokens.css 1개(디자인 토큰, 비밀 아님) | 0 |
| 이미지·파일시스템 스캔(trivy) | trivy 릴리스 curl | GitHub 릴리스 URL 이 프록시에서 "Not Found"(9바이트) - 확보 실패, 설치 안 함 | 미수행 |
| misconfig(hadolint/trivy config) | which | 설치 안 됨, 확보 시도 시간 부족 | 미수행 |
| semgrep | pip install 성공, 규칙 p/python 받기 | semgrep.dev 가 프록시 403(ProxyError) - 규칙 확보 실패 | 미수행 |
| bandit | bandit -r web/backend/ytweb src | 아래 3절 | High 1(오탐), Medium 8, Low 다수 |
| 프런트 보안 린트 | eslint-plugin-security 미설치 | 생략(프로젝트에 없음, 설치는 소스 변경 범위) | 미수행 |
| SBOM 비교 | docs/harness/sbom-web-m1.json 과 requirements*/package-lock | 의존성 파일 3종과 SBOM 이 같은 커밋 94598b8(2026-10-11)이 마지막 변경이며 이후 변경 없음. 파이썬 핀 30개 전부 SBOM에 있음, 새 파이썬 의존성 0. npm lock 382개 중 103개가 이름·버전 비교로는 SBOM에 없다고 나오나 SBOM이 스코프 패키지(@scope) 이름을 분리 저장한 형식 차이로 보이며 확정하지 못함(근거: 예시 @babel/core 7.29.7 등 널리 쓰는 패키지). Gemini 연동도 표준 라이브러리 urllib 만 사용(새 의존성 없음) | 신규 의존성 0(파이썬), npm 비교는 불확정 |

## 2. bandit 상세 (web/backend/ytweb, src)
- High 1: B613 trojansource, web/backend/ytweb/ai/guard.py:20 (_INVISIBLE 집합에 U+200F 등 보이지 않는 글자를 리터럴로 씀). 오탐: 제목 속 방향 제어 글자를 걸러내는 목록. 다만 소스에 보이지 않는 글자가 실제 들어 있어 리뷰 때 안 보임 - 개선 권고(chr/\u 이스케이프). Info.
- Medium B310(urlopen 스킴): gemini.py:78, google_oauth.py:120, live_read.py:32 - 모두 코드에서 https 고정 주소만 사용(gemini 는 상수 호스트, google_oauth/live_* 는 startswith("https://") 검사). 실제 위험 없음.
- Medium B608(SQL 문자열): src/youtube_title/commands/purge.py:32,34,69, limits.py:99,103,108 - 옛 CLI 코드. 값이 외부 입력인지 이번에 확인하지 못함(미확인).
- Low: B105(오탐: 파일 이름·URL 상수), B404/B603/B607 platform_utils.py:5,29, B101 report.py:237.

## 3. 코드 리뷰 (파일:줄)
- 키 노출: ai/gemini.py 키는 헤더 x-goog-api-key 로만(:70-72), URL·본문 없음. 예외는 `from None` 으로 원인 제거, 메시지는 고정 문구(:79-85). 시험으로 확인(4종 예외 모두 키 미노출, 로그 미노출).
- 호스트 고정: ENDPOINT 상수(:15). 단 model 값이 검증 없이 URL 경로에 들어감(:68, 환경변수 YTWEB_GEMINI_MODEL) - 쿼리/경로 주입 가능, 호스트는 못 바꿈. 환경변수는 소유자만 설정하므로 Low. [DEF-D-001]
- 응답 파싱: _parse(:96-112) 형식 오류는 TitleSuggestionError 로 닫힘, 후보 수 제한. 시험 통과.
- 리다이렉트: google_oauth.py:31-40 에서 전역 opener 로 3xx 비추종(Authorization 유출 방지). gemini 도 같은 프로세스 opener 사용(live_write.py import 부수효과에 의존). 시험 통과.
- 실제 모드 3조건: live_gateway.py:36-44 스위치는 정확히 "1", 허용 목록 비어 있으면 거부, 토큰 필요. live_write.py:67-80 허용 목록·body.id 일치·title/categoryId 검사를 네트워크 전에 수행. batches.py:80-84, 453-454, 477-479 다중 방어(live_off, live_not_allowed, 모드 변경 감지). 우회 시험: 스위치 변형값 7종("true","yes"," 1","01" 등) 모두 거부, 허용 목록 밖 영상·id 불일치 본문은 네트워크 호출 0건으로 거부. 우회 경로 못 찾음.
- 결함 후보 [DEF-D-002 Low]: 쓰기 토큰 범위 미검증. google.py 콜백(:127-134)은 state 종류가 write 이면 구글이 돌려준 scope 를 확인하지 않고 쓰기 토큰 파일에 저장, google_oauth._tokens_from 은 scope 없는 응답을 기본 readonly 로 채움(:131). live_write_ready 는 파일 존재만 봄 -> 읽기 범위 토큰이어도 "쓰기 준비됨"으로 표시. 구글이 403 으로 막으므로 실제 변경은 일어나지 않음(안전하나 화면 표시가 틀림).
- 데모 모드 외부 호출: ai/factory.py:16-18 get_suggester 는 demo 만 허용하고 MockSuggester 반환. 실제 영상은 get_live_suggester 에서만 키가 있으면 Gemini. 데모에서 외부 호출 없음(코드 확인, 별도 네트워크 감시 시험은 안 함).
- CSRF/Origin: core/guard.py:60-66 Sec-Fetch-Site 가 same-origin/none 이 아니면 외부 요청 취급, POST/PUT/PATCH/DELETE 는 Origin 이 허용 목록이어야 함, Host 정확히 1개·허용 목록 검사(:122). 콜백 GET 은 세션 없이 1회용 state(256비트, 10분, 최대 20개)로 보호, 모르는 state 는 감사 기록 안 함. 로그인 CSRF 불가(state 는 세션 있는 POST 로만 발급).
- 콜백 GET: 외부에서 임의 code 로 호출해도 state 없으면 토큰 교환 안 함(시험: state 1회성·알 수 없는 state 거부 통과).
- 토큰 파일 0600·원자적 교체: 시험 통과(리눅스 기준, Windows ACL 은 미수행).

## 4. 작성한 시험과 첫 실행 결과
파일: web/tests_fullcheck/d/test_d_security_review.py. 명령: cd web/backend && PYTHONPATH=. ../../.harness-tmp/be/bin/python -m pytest ../tests_fullcheck/d -q
첫 실행: 2건 실패, 나머지 통과(재실행에서도 동일 2건 실패, 21 통과, 2 실패(0.42초)). 실패 2건은 결함 재현이며 기대값을 고치지 않았다:
1. test_write_token_scope_not_verified_REPRO 실패 = DEF-D-002 재현(읽기 범위 토큰이 쓰기 슬롯에 있어도 live_write_ready True).
2. test_gemini_model_env_injects_url_path 실패 = DEF-D-001 재현(모델 값에 ?alt=sse 가 URL 에 그대로 들어감).
통과 시험: 3조건 각각 필수(3), 스위치 변형 7종 거부, 허용 밖 영상·id 불일치·빈 제목 네트워크 호출 0, read id 쿼리 주입 방지, Gemini 키 헤더 전용·호스트 고정, 예외 4종 키 미노출, 응답 형식 오류 닫힘, 리다이렉트 비추종, state 1회성, 토큰 0600.

## 5. 확인하지 못한 것
- trivy(파일시스템·misconfig·이미지): 도구 받기 실패(프록시가 GitHub 릴리스 차단). 이미지 스캔은 docker 금지.
- semgrep: 규칙 서버 403. hadolint 등 대체 도구: 시간 부족으로 시도 안 함.
- 이미지 서명(cosign) 검증, 침투 시험, Windows ACL/PowerShell, 실제 브라우저 CSP: 미수행.
- npm lock 대 SBOM 정밀 비교, src/ 옛 CLI 의 B608 SQL 입력 출처: 미확인.
- 실제 구글·유튜브·Gemini 호출은 하지 않음(요청대로, 시험은 urlopen 가짜).
