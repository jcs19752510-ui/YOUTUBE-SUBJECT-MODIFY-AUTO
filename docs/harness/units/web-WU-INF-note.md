# 단위 노트 — W-INF (컨테이너·실행 스크립트)

| 항목 | 내용 |
|---|---|
| 작업 단위 | W-INF (WEB_DESIGN §7). 병렬 웨이브: W-BE-A, W-BE-B, W-FE와 동시 진행 |
| 속도 트랙 | 전달받은 표기 없음 -> L3(기본값) |
| 근거 | WEB_DESIGN §1·§5·§7, 요청문 D-01~D-14, DEC-033~038, 조사 `01-axisB`, 조정자 환경 업데이트(Docker 데몬 사용 가능) |
| 결과서·검증 로그 | 06단계 담당이 쓴다. 이 노트는 자체 결과서가 아님 |

## 1. 파일

| 구분 | 경로 |
|---|---|
| compose | `web/compose.yaml`, `web/compose.online.yaml`(M2·M3용 egress 덧씌우기, 기본 미사용) |
| 이미지 | `web/docker/api.Dockerfile`(api·worker·migrate 공용), `web/docker/web.Dockerfile`, `web/docker/db.Dockerfile` |
| 해시 잠금 | `web/docker/requirements-youtube-title.txt` (PyYAML 6.0.3, python-dotenv 1.2.4, tzdata 2026.5; PyPI JSON의 sha256) |
| nginx | `web/docker/nginx/{nginx.conf,security-headers.conf,proxy.conf}` |
| DB | `web/docker/db/{init/01-roles.sh,schema-grants.sql,audit-guard.sql,pg_hba.conf,bin/ytweb-db}`, `web/docker/.gitattributes`(LF 강제) |
| 스크립트 | `web/scripts/{_common,start,stop,status,logs,backup,restore,reset-demo,pin-digests}.ps1` (UTF-8 BOM) |
| 문서·테스트 | `web/README.md`, `web/tests_infra/test_compose_security.py` |
| 루트 | `.dockerignore`(신규), `.gitignore`(추가만: `web/secrets/`, `web/backups/`, `web/frontend/dist/`, `node_modules/`, `*.dump`) |

## 2. 구성도

```
호스트 127.0.0.1:8080 (유일한 게시 포트)
   |
 [edge 네트워크(비 internal, web만)]
   |
 web(nginx 101) --[app 네트워크 internal:true]-- api(10001) -- db(999, PostgreSQL 17)
                                                 worker(10001) -- db
                                                 migrate(10001, 1회, 소유자 계정) -- db
기동 순서: db healthy -> migrate 성공 -> api/worker 시작 -> api healthy -> web
볼륨: pgdata, backups(컨테이너 안 임시 백업 경로), app_secrets(서명 키)   비밀: web/secrets/* -> /run/secrets/*
```

## 3. 설계서·지시 대비 편차 (사유)

| # | 편차 | 사유 |
|---|---|---|
| 1 | `web`만 `edge`(비 internal) 네트워크에 추가로 붙음 | internal 전용 컨테이너는 호스트 포트 게시가 되지 않는 것으로 알려져 있어(조사 1-14는 추정, **이번에 internal 단독 게시는 시험하지 않음**) 안전하게 분리. 게시 전용이며 다른 서비스는 붙지 않음. 실측: edge 구성원 = web뿐. 다만 web(nginx)은 이 네트워크로 외부에 나갈 수 있는 경로가 이론상 존재(nginx는 외부 요청을 하지 않음) |
| 2 | egress를 `profiles: ["online"]`이 아니라 `compose.online.yaml` 덧씌우기 파일로 준비 | compose의 profiles는 서비스에만 적용되고 네트워크에는 적용되지 않음. 기본 실행에서는 egress 네트워크가 아예 만들어지지 않음 |
| 3 | `pip install` youtube_title/backend 대신 `PYTHONPATH=/app/backend:/app/src` | 코어 사본 없이 같은 소스를 쓰고, 빌드 격리(미잠금 setuptools 내려받기)를 피함. `web/backend/requirements.txt`에 youtube_title 의존성(PyYAML 등)이 없어 `requirements-youtube-title.txt` 해시 잠금을 별도로 둠 |
| 4 | 컨테이너 안 임시 백업용 `backups` 명명 볼륨 추가 | PowerShell 리디렉션 바이너리 손상 회피(`docker compose cp` 사용). tmpfs는 cp 불가 |
| 5 | 헬스체크가 `pg_isready` + 초기화 성공 표식 파일(`.ytweb-init-ok`) | 실측: init 스크립트가 실패해도 재시작 시 엔트리포인트가 "이미 초기화됨"으로 보고 정상 기동함(반쯤 초기화된 볼륨). 표식이 없으면 unhealthy 로 남겨 migrate가 돌지 않게 함 |
| 6 | api 명령에 `--no-server-header --no-access-log` 추가, nginx에서 백엔드 보안 헤더 중복 제거(`proxy_hide_header`) | `--no-access-log`는 조정자 요청(쿼리 문자열 로깅 방지). 헤더는 백엔드도 붙이므로 브라우저에 한 벌만 보이게 함 |
| 7 | DB PostgreSQL **17**(18이 아님) | 지원 ~2029-11, 볼륨 경로 `/var/lib/postgresql/data` 안정(18은 변경). `--data-checksums` 직접 지정. **오케스트레이터 ADR 확인 필요**(최종 보고 질문 1) |
| 8 | `Referrer-Policy: same-origin` (no-referrer 아님) | no-referrer 는 일부 요청에서 `Origin: null`을 만들 수 있어 백엔드 Origin 검증과 충돌 위험. 외부로는 리퍼러가 나가지 않음 |
| 9 | CSP에 `style-src-attr 'unsafe-inline'`, `img-src data:` 허용 | React 인라인 style 속성, Vite의 소형 에셋 data URI. 스크립트·`<style>` 블록은 계속 차단. 실제 브라우저 CSP 오류 여부는 **미확인**(브라우저 없음) |

## 4. D-01~D-14 ↔ 구현 ↔ TC (충족/부분/미충족)

| 요구 | 구현 | TC | 판정 |
|---|---|---|---|
| D-01 4서비스+healthy 뒤 시작, `dev/test` 프로필 | `depends_on` 조건 체인 + migrate. **dev/test 프로필은 만들지 않음**(M1 범위 밖) | 016 | 부분(프로필 미구현: 사유 M1 불필요, 테스트는 `YTWEB_PROJECT` 분리로 대체) |
| D-02 127.0.0.1 한정 게시 | `127.0.0.1:8080:8080`, 실측 `docker port`=127.0.0.1:8080, `/proc/net/tcp` LISTEN 127.0.0.1 뿐, 호스트의 다른 IP 4개로 접속 시도 전부 실패 | 001,002,030 | 충족(클라우드 Linux 엔진). **Docker Desktop은 사용자 PC 확인 필요** |
| D-03 비루트·read_only·cap_drop·no-new-privileges·금지 항목 | 5개 서비스 전부 실측(`docker inspect`: user, ReadonlyRootfs, CapDrop=ALL, NoNewPrivs=1, CapEff=0) | 003~008,032 | 충족(Linux 엔진 실측). 공식 postgres 이미지 + `user: 999:999` + read_only + cap_drop ALL 조합이 **실제로 동작**(조사 `[확인 필요]` 해소) |
| D-04 다이제스트 고정, 멀티 스테이지 | 4개 베이스 이미지 모두 `tag@sha256` 고정(아래 §6). 최종 이미지에 빌드 도구·소스맵 없음(`*.map` 삭제, dist만 복사) | 022 | 충족 |
| D-05 .dockerignore, 레이어에 비밀 없음 | `.dockerignore` 작성. **이미지 레이어 비밀 스캔(Trivy 등)은 미수행**(9단계 범위) | 021,029 | 부분 |
| D-06 비밀은 secrets 파일 | compose `secrets`(file), 환경변수는 `*_FILE`만, 값은 이미지·compose·환경에 없음(실측 `env | grep pass` -> 경로뿐) | 009,018,026 | 충족 |
| D-07 명명 볼륨, down -v 경고 | pgdata/backups/app_secrets 명명 볼륨, 호스트 바인드 없음. stop.ps1에 볼륨 삭제 없음, 삭제는 reset-demo의 `-DeleteVolumes`+확인 문구 | 004,012,020 | 충족 |
| D-07a PostgreSQL 컨테이너 | `POSTGRES_PASSWORD_FILE`, 역할 3분리, 포트 미게시, scram-sha-256+사설망 pg_hba(실측: app 계정의 postgres DB 접속 거부), UTF8, 시간대 UTC, `max_connections=50`, `pg_isready` 헬스체크, `stop_grace_period 60s`. **부분**: 로컬 소켓/루프백도 scram(컨테이너 안 점검 시 비밀번호 필요) | 017,018,025,026 | 충족 |
| D-07b Alembic 별도 단계 | `migrate` 1회성 서비스(소유자 계정), 매 `up` 마다 재실행 확인. **"실행 전 자동 백업"은 미구현**(복원/초기화 스크립트에만 사전 백업) | 016,019 | 부분 |
| D-08 헬스체크·재시작·우아한 종료·로그 | healthcheck 전부, `unless-stopped`, `init: true`, 종료 시 exit 0 확인, json-file 10m x 3 | 014,015 | 충족. 워커 헬스체크는 프로세스 생존만 |
| D-09 TZ=Asia/Seoul, 저장 UTC | 전 서비스 TZ, DB `timezone=UTC`, 역할 timezone UTC | 017 | 충족(slim 이미지에 tzdata 없음: 앱은 파이썬 tzdata 사용) |
| D-10 아웃바운드 제한 | app internal. 실측: api에서 외부 접속 `Network is unreachable`. db는 egress 불가(overlay도) | 010,011,031 | 충족 |
| D-11 취약점 점검·SBOM | 해시 잠금 + `npm ci`. **Trivy/Scout·SBOM 미수행**(9단계) | - | 미충족(범위: 9단계) |
| D-12 Windows 스크립트 | start/stop/status/logs/backup/restore/reset-demo/pin-digests, 한국어 안내 | 027,033 | 충족(실행 환경 차이는 §7 참고) |
| D-13 임시 환경 `harness-tmp` 접두사 | `YTWEB_PROJECT`, `YTWEB_IMAGE_PREFIX` 환경변수로 분리, 이번 실측은 `harness-tmp-inf` 로 수행 후 전부 정리 | - | 충족 |
| D-14 자원 상한 | 전 서비스 cpus/memory/pids | 013 | 충족. 실측 `docker inspect` 로 값 확인 |

## 5. 결과 숫자

- 정적 점검 `.venv python -m pytest web/tests_infra`: **35 통과 / 1 건너뜀 / 0 실패** (TC-WI-001~034, 파라미터화 포함 36개 시험 항목). 건너뜀 = TC-WI-033(pwsh 없음, 정리 후). 정리 전에는 pwsh 7.5.4를 `.harness-tmp`에 받아 **36 통과**(9개 ps1 문법 오류 0).
- 변이 점검(수동): 포트 0.0.0.0 게시, 루트 사용자, read_only 해제, 환경변수 평문 비밀, db를 edge에 연결, server_tokens on, pg_hba trust, Dockerfile USER root, docker.sock 마운트 = **9/9 탐지**.
- Docker 실측(클라우드 Linux 엔진 29.8.2, compose 5.6.0): 이미지 3종 빌드 성공(api 해시 잠금 설치는 **Python 3.12 이미지에서 3.13 잠금 그대로 성공**), compose 전체 기동, 모든 서비스 healthy, migrate 종료 0, DB 재생성에도 데이터 유지, 백업->삭제->복원->행 수 일치.

## 6. 다이제스트 고정 결과 (2026-10-10 레지스트리 API 조회)

| 이미지 | 고정값 |
|---|---|
| `python:3.12-slim` (= 3.12-slim-trixie) | `sha256:a6e34c59...c11b1` (조사 4-1과 일치) |
| `node:22-bookworm-slim` | `sha256:c3de60bf...78392` |
| `nginxinc/nginx-unprivileged:stable-alpine` | `sha256:15c994d1...516e3` |
| `postgres:17-bookworm` | `sha256:3645570c...b03826` (조사 3-3과 일치) |

충족. 클라우드에서 `curl`(토큰+매니페스트 HEAD)로 조회. `pin-digests.ps1` 재조회 시험: 2개 일치 확인, 2개는 Docker Hub 429(속도 제한)로 조회 실패 -> 스크립트가 실패로 보고함(재시도 6회 후). Node 22는 유지보수 ~2027-04(조사 4-3) -> 프런트 호환 확인 후 24/26 전환 여부는 최종 보고 질문 3.

## 7. 실측하지 못했거나 사용자 PC 확인이 필요한 것

| 항목 | 상태 | 확인 절차 |
|---|---|---|
| Docker Desktop(WSL2)에서 127.0.0.1 한정 게시 | **미수행**(클라우드는 Linux 엔진) | `status.ps1`(리스너 주소 검사 포함) + 휴대폰에서 `http://PC-IP:8080` 접속 불가 확인 |
| Windows 호스트 파일 secrets를 비루트 컨테이너가 읽는지 | **미수행**(클라우드에선 파일 0644 root 소유로 읽힘). 참고: 리눅스 호스트에서 0600 root 소유면 비루트가 못 읽음 | `docker compose exec api ls -l /run/secrets` 후 앱 기동 성공 여부 |
| PowerShell **5.1** 동작 | **미수행**(pwsh 7.5.4 on Linux로만 실행·검증). 5.1 호환 대비: BOM, stderr 처리 래퍼, `-UseBasicParsing`, 따옴표 포함 `--format` 회피 | 사용자 PC에서 `start.ps1` |
| ACL 제한(`Set-OwnerOnlyAcl`) | **미수행**(Windows 전용 경로) | `icacls web\secrets` 로 현재 사용자만 있는지 |
| 브라우저 CSP 호환 | **미수행**(브라우저 도구 없음). curl로 헤더·HTML(인라인 스크립트/스타일 0개)만 확인 | F12 콘솔 |
| `docker compose cp` 의 Windows 경로/권한 | 미수행. 복원은 임시 사본(읽기 허용)을 cp, 백업은 `./상대경로` 사용 | 백업->복원 체크리스트 |
| 클라우드의 api/web 이미지 빌드 | 빌드 시 프록시 CA 필요: 테스트용 Dockerfile 사본(`.harness-tmp`)에 CA만 주입해 빌드(저장소 Dockerfile은 그대로). 저장소 Dockerfile 직접 빌드는 **이 클라우드에서 TLS 오류**(사용자 PC와 무관) | - |
| 최신 프런트 빌드 | 최신 `web/frontend`(저장소)에서 `npm run build` 실패: `src/pages/misc.test.tsx(265,4) TS1005` 등(**W-FE 작업 중 파일**). 이전 시점 프런트로는 빌드·기동 성공 | W-FE 수정 후 재빌드 필요 |
| 이미지 취약점·SBOM | 미수행(9단계) | - |
| `restart` 후 PC 재부팅 복구 | 미수행 | 체크리스트 5 |

## 8. 실측 결과 요약 (클라우드 Linux 엔진, 프로젝트 `harness-tmp-inf`)

- DB 역할: `postgres`(슈퍼유저) / `ytweb_owner`(비슈퍼, 연결 10) / `ytweb_app`(비슈퍼, 연결 30). 인코딩 UTF8, 시간대 UTC, `max_connections=50`, `data_checksums=on`, `hba_file` 적용.
- 권한: app은 DML만 가능, `CREATE TABLE`(public) / `DROP` / `pg_read_file` 거부. **마이그레이션 0001 적용 후 `audit_log`: app UPDATE/DELETE/TRUNCATE = 거부, INSERT 허용, 다른 테이블 UPDATE 허용, 시퀀스 사용 가능**(조정자 요청 5번 실측 완료).
- 중요 발견: `pg_restore --clean` 후 기본 권한 때문에 `audit_log`의 UPDATE 권한이 앱에 다시 생김(실측 재현 `t`). `ytweb-db restore` 가 `audit-guard.sql` 로 다시 회수하고 검사한다(복원 후 `f` 확인).
- nginx 경유: 보안 헤더 7종 한 벌, 불허 Host `Empty reply`(444), `localhost:8080` 허용, TRACE 405, 세션 발급 속도 제한(분당 10 + burst 10 -> 이후 429), api 컨테이너 재생성 후에도 프록시 유지(동적 DNS), `Set-Cookie ytw_session` HttpOnly·SameSite=strict 통과.
- 스크립트(pwsh 7 on Linux): status(문제 없음, 포트 점검 포함), backup(크기·`pg_restore --list`·SHA-256), restore(오답 문구 취소, 정답 시 복원, 행 수 출력), reset-demo(기본/`-DeleteVolumes`), stop(볼륨 보존), start -NoBuild 모두 동작.
- 정리: 테스트 컨테이너·네트워크·볼륨·이미지 삭제, `docker ps -a / network ls / volume ls / images` 에 `harness-tmp`·`ytweb` 잔여 없음, `web/secrets`·`web/backups`·`.harness-tmp/inf` 삭제.

## 9. 6단계 테스터를 위한 인수 조건

1. `python -m pytest web/tests_infra` -> TC-WI-001~034 모두 통과(pwsh/docker CLI 없으면 해당 TC만 건너뜀으로 기록).
2. `docker compose -f web/compose.yaml config` 성공, 호스트 게시 1건(`127.0.0.1:8080`).
3. (데몬 있을 때) `YTWEB_PROJECT=harness-tmp-x YTWEB_IMAGE_PREFIX=harness-tmp-x` 로 start.ps1(또는 compose up) -> 전 서비스 healthy, `status.ps1` 문제 없음, `curl -H 'Host: evil:8080' http://127.0.0.1:8080/api/healthz` 응답 없음.
4. DB 권한 실측(§8)을 재현: app 계정으로 audit_log UPDATE/DELETE/TRUNCATE 거부, CREATE 거부.
5. 백업->데이터 삭제->복원 후 행 수 일치, 복원 후 audit_log 권한 회수 유지.
6. 종료 후 `down` 만으로는 볼륨이 남고, `-DeleteVolumes` 는 확인 문구 없이는 동작하지 않음. 후처리: harness-tmp 자원 정리 확인.

## 10. 자체 코드 리뷰 체크리스트 (게이트 2)

- [x] 지시·설계와 구현 일치 (편차는 §3에 사유와 함께 기록)
- [x] 에러 처리: 스크립트는 종료 코드 검사 후 원인·조치 출력, 예외 삼키지 않음(ACL 실패·WSL 상태는 경고로 노출)
- [x] 경계 입력 검증: 백업 파일명 정규식(스크립트·`ytweb-db` 이중), 서비스명 ValidateSet, 확인 문구
- [x] 하드코딩 비밀 없음 (테스트 TC-029가 64자 16진수 검사, 로그·출력에 비밀 미출력)
- [x] 새 외부 의존성: PyPI JSON으로 PyYAML 6.0.3 / python-dotenv 1.2.4 / tzdata 2026.5 실존·해시 직접 조회. 베이스 이미지 4종 레지스트리 조회 + 실제 pull·빌드 성공. **새 패키지 설치는 컨테이너 빌드 안에서만**
- [x] 범위 외 변경 없음 (소유 범위 외 파일 미수정. 루트 `.gitignore` 추가만)
- 게이트 1(린트): 이 단위에는 lint 설정 없음(셸/PowerShell/Dockerfile 린터 미설치). 대체로 `bash -n`, pwsh 파서(오류 0), 정적 테스트 36개를 사용. hadolint/shellcheck/PSScriptAnalyzer는 **미수행**.

## 11. 공유 문서 갱신 요청 (병렬 웨이브 규칙)

- traceability: D-01~D-14, D-07a/b, S-W01, S-W13a, S-W14, W-001, W-016 의 작업 단위 = W-INF, 구현 상태 = 구현됨(위 표의 "부분/미충족" 항목 제외: D-01 프로필, D-05 레이어 스캔, D-07b 자동 사전 백업, D-11).
- decisions: (1) PostgreSQL 17 선택, (2) web만 edge 네트워크 추가(internal 게시 불가 실측), (3) egress는 overlay 파일, (4) 헬스체크 init 표식, (5) 코어는 PYTHONPATH 사용.


---

# 수정 단위 (2026-10-11) — W-FIX-INF

| 항목 | 내용 |
|---|---|
| 근거 | DEC-046(사용자 승인), 7단계 통합 시험 결과서 `feature-web-m1-integration-test.md`(DEF-7-001·002·006·007), 9단계 `security-web-m1-test.md`(DEF-9-006·011·013·014·017) |
| 속도 트랙 | 전달받은 표기 없음 -> L3(기본값). 구현 절차(게이트 1·2)는 트랙과 무관하게 동일 |
| 병렬 실행 | 프런트(`web/frontend/`)·백엔드(`web/backend/`) 수정 담당과 동시 진행. 이 단위는 두 폴더를 수정하지 않았다(읽기만: 마이그레이션 0002 대조, 이미지 빌드 입력) |
| 결과서·검증 로그 | 이후 독립 검증 에이전트가 쓴다. 이 절은 자체 결과서가 아님 |

## A. 변경 파일

| 구분 | 파일 | 내용 |
|---|---|---|
| DB | `web/docker/db/audit-guard.sql` | 복원 뒤 `alembic_version` 의 INSERT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER 재회수 + 검증(SELECT 는 남아 있어야 함). 기존 `audit_log` 회수 유지. 파일 이름은 그대로(참조 시험·Dockerfile 영향 없음) |
| DB | `web/docker/db/bin/ytweb-db` | 복원 완료 메시지 문구만 변경 |
| DB | `web/docker/db/schema-grants.sql` | 주석만 갱신(0002 와 guard 의 역할) |
| nginx | `web/docker/nginx/nginx.conf` | 루트 `/healthz`·`/readyz` 정확 일치 location 2개(404 text/plain, 보안 헤더·no-store). `/api/*` 4개 location 이 `security-headers-api.conf` 를 include |
| nginx | `web/docker/nginx/security-headers-api.conf` (신규) | `/api` JSON 응답용 헤더 한 벌. CSP 만 `default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'`, 나머지 6줄은 페이지용과 동일 |
| nginx | `web/docker/nginx/proxy.conf` | `proxy_hide_header Cache-Control;` 추가 |
| 이미지 | `web/docker/web.Dockerfile` | 새 헤더 파일 COPY 1줄 |
| 이미지 | `web/docker/api.Dockerfile` | `COPY web/backend` 를 `ytweb`·`alembic`·`alembic.ini` 3개 COPY 로 축소 |
| 루트 | `.dockerignore`(추가만) | `*.pem`·`**/*.pem`·`*.key`·`**/*.key`·`credentials*.json`·`**/credentials*.json`·`**/client_secret*.json`·`**/*.p12`·`**/id_rsa*`·`**/.ruff_cache`·`**/.mypy_cache`·`**/.coverage`·`**/.coverage.*`·`**/htmlcov/` |
| 루트 | `.gitignore`(추가만) | `client_secret*.json`·`*client_secret*.json`·`credentials*.json`·`*.pem`·`*.key`·`*.p12` (추적 중인 파일 중 해당 패턴 0건 확인) |
| 문서 | `docs/yt/WEB_INSTALL.md` 7장, `docs/yt/WEB_RUNBOOK.md` 13-2, `web/README.md` 10장 | DEF-9-011·014·013 보안 결정(DEC-046)과 "선생님이 지금 할 일". RUNBOOK 에 상태 확인 경로 정리(DEF-7-006) 추가 |
| 시험(신규) | `web/tests_infra/test_fix_inf.py` | TC-WIX-001~011(정적), TC-WIX-030~033(실가동) |
| 시험(수정) | `web/tests_infra/test_compose_security.py` TC-WI-023, `test_vi_independent.py` TC-VI-020·042 및 nginx 하네스 마운트 | 새 설정에 맞게 기대 수정(아래 C) |
| 시험(수정) | `web/tests_integration/test_it_01_nginx.py`·`test_it_04_contract.py`·`test_it_05_ops.py`, `web/tests_security/test_sec_03_static_repo.py`·`test_sec_06_live_known_limits.py` | 수정 완료된 결함의 `xfail(strict)` 표식 제거·기대 갱신(아래 C) |

## B. 결함 ID <-> 변경 <-> TC

| 결함 | 처리 | 변경 | TC / 실측 |
|---|---|---|---|
| DEF-7-002 (Medium) | 수정 | `audit-guard.sql` 확장 | TC-WIX-001·002(마이그레이션 0002 와 권한 목록 동일)·003, **TC-WIX-032 실가동**: 대조군(가드 없는 `pg_restore --clean`)에서 앱 계정 `alembic_version` INSERT/UPDATE/DELETE = t, `audit_log` UPDATE/DELETE = t 재현 -> `ytweb-db restore` 뒤 전부 f, SELECT t, 앱 계정 UPDATE/DELETE/TRUNCATE 는 `permission denied`, 두 번 실행(멱등)도 동일. IT-504 의 xfail 표식 제거 |
| DEF-9-006 (Medium) | 수정 | `.gitignore` 추가 | TC-WIX-004, 기존 `test_gitignore_has_client_secret_pattern` xfail 표식 제거 |
| DEF-9-017 (Low) | 수정(둘 다) | api.Dockerfile COPY 축소 + `.dockerignore` 패턴 추가. `.dockerignore` 의 전면 허용 목록(`*` 후 `!`) 전환은 하지 않음(알려진 제한 1) | TC-WIX-005·006, **TC-WIX-033 실가동**: 이미지 `/app` 에 `.ruff_cache`·`.coverage`·`pyproject.toml`·`requirements*`·`*.egg-info`·tests·`*.md`·`*.pem`·`*.key`·`credentials*`·`client_secret*`·`.env*`·`settings.local.yaml` 0건(`find` 출력 비어 있음). 작업 폴더에는 `web/backend/.ruff_cache`·`.coverage`·`.pytest_cache` 가 실제로 있어 시험이 공허하지 않음. 파일 199개, `/app` 최상위 = `backend config src`, `/app/backend` = `alembic alembic.ini ytweb`. 기존 xfail 2개(`test_sec_03`·`test_sec_06`) 표식 제거 후 통과 |
| DEF-7-006 (Low) | 수정(닫기) | nginx `/healthz`·`/readyz` -> 404 | TC-WIX-007·030, IT-436 재작성, IT-030·IT-420 갱신. **문서 불일치 남음**: API.md 21·151행, WEB_DESIGN 46행, openapi.json 이 루트 경로도 열린다고 적음 -> 11단계 문서 정정 필요(이 단위 소유 문서 아님) |
| DEF-7-007 (Low) | 수정(설정을 문서에 맞춤) | `security-headers-api.conf` | TC-WIX-008·009·031, IT-437·IT-432·IT-001 갱신 |
| DEF-7-001 (Low) | 수정 | `proxy_hide_header Cache-Control` | TC-WIX-009·031, IT-053 xfail 표식 제거 |
| DEF-9-011/013/014 | 문서화(DEC-046 M1 한정 수용) | INSTALL 7장·RUNBOOK 13-2·README 10장 | TC-WIX-010(절 안에서 필수 문구 확인) |

## C. 판단 근거와 시험 수정 사유

1. **루트 `/healthz`·`/readyz` 를 프록시하지 않고 404 로 닫은 이유**: 실제 결함은 "프로브가 HTML 200 을 받아 거짓 정상으로 오판"이다. 두 경로를 열면 같은 정보를 내는 경로가 둘이 되어 점검 면이 는다(`/api/readyz` 는 이미 `mode` 를 인증 없이 노출, OBS-10). 헬스 점검은 `status.ps1` 등 모든 소비자가 이미 `/api/` 경로를 쓴다(grep 확인). 컨테이너 내부 헬스체크는 백엔드 8000 포트를 직접 보므로 영향 없음. 대신 문서 3종(API.md·WEB_DESIGN·openapi.json)이 틀려진다 -> 질문으로 올림.
2. **`/api` CSP 를 문서(`'none'`)에 맞춘 이유**: 보수적인 쪽(더 엄격). 단순 문서 정정은 이 단위 소유 문서가 아니기도 했다. 헤더 분기를 `map` 변수로 하지 않고 별도 snippet 파일로 한 이유: `security-headers.conf` 의 CSP 문자열 위치와 형식에 의존하는 기존 시험·변이 점검(`tests_security`, `mutate.py`)을 건드리지 않기 위해서. 6줄 중복은 TC-WIX-008 이 동일성을 강제한다. 오류 응답(413·429 등 `/api/` location 에서 nginx 가 직접 만드는 응답)도 같은 location 헤더를 쓰므로 `'none'` 이 된다.
3. **시험 수정 사유(의도 유지, 기대만 새 설정에 맞춤)**: TC-WI-023(헤더 파일 include 확인에 api 변형 허용), TC-VI-020(location 수 7->9, proxy location 은 api 헤더 파일 include), TC-VI-042(`/api/` 경로 CSP 는 `'none'` 4 지시어), nginx 하네스에 api 헤더 파일 마운트(기존 이미지에 파일이 없어도 시험 가능), `test_sec_03::test_nginx_conf_rules`(api 변형 허용), IT-001/040/030/420/432 갱신, 수정 완료된 결함 고정 시험 6개(IT-053·436·437·504, `test_sec_03` 의 DEF-9-006·017, `test_sec_06` DEF-9-017)의 `xfail(strict)` 제거 — 수정 후에도 남기면 XPASS(strict)로 실패한다(`test_sec_03` 의 두 건은 수정 후 표식이 남아 있을 때 실제로 XPASS(strict) 실패가 나는 것을 확인한 뒤 제거).
4. 새 외부 의존성 없음. 시험 실행용 임시 가상환경(`.harness-tmp/fixinf/venv`: pytest·httpx·jsonschema·pyyaml)만 PyPI 에서 설치(저장소 매니페스트 변경 없음).

## D. 실가동 확인 요약 (클라우드 Linux 엔진, 프로젝트 `harness-tmp-fixinf`, 127.0.0.1:18480, 임시 CA 주입 복사본으로 이미지 3종 빌드: 저장소 Dockerfile 은 그대로)

- 이미지 3종 빌드 성공(실제 프런트 포함), 5개 서비스 healthy, migrate 종료 0.
- HTTP: `/healthz`·`/readyz` 404 text/plain, `/api/healthz` 200 `{"status":"ok"}`, `/api/readyz` 200, `/api/*` CSP `default-src 'none'...` 1개·`Cache-Control: no-store` 1개, 페이지 CSP 불변, 오류(404/413)에도 적용.
- 복원 권한(위 B), 이미지 파일 목록(위 B).
- 시험: `test_fix_inf.py` 정적 13 + 실가동 4 = 17 통과. `tests_infra` 전체(WIX_LIVE=1, VI_DOCKER=1): 176 통과·84 건너뜀·0 실패(1 XPASS = 기존 TC-VI-055). 기본 실행(도커 없음): 89 통과·172 건너뜀. 통합 `test_it_01_nginx.py` 전체 36 통과·1 건너뜀, IT-401·402·420·432·436·437 통과(합 19). 보안 `test_sec_03` 28 통과, `test_sec_04`(실스택) 84 통과(아래 제한 3 참고), `test_sec_06` DEF-9-017 시험 통과.
- 시험의 실효성: 신규 정적 시험에 14곳 변이(권한 목록 축소·검사 제거·COPY 확대·CSP 완화·헤더 파일 교체·hide 제거·문서 문구 삭제 등)를 넣어 14/14 탐지(생존 0). 한 곳은 처음에 생존했고(문서 시험이 다른 장의 문구로 통과) 절 단위 검사로 보강 후 탐지.
- 정리: 이 단위의 컨테이너·네트워크·볼륨·이미지 삭제 및 잔여 0건 확인은 최종 보고에 기재.

## E. 알려진 제한·건너뛴 것

1. `.dockerignore` 를 전면 허용 목록(`*` + `!경로`)으로 바꾸지 않았다. 세 Dockerfile 이 서로 다른 경로를 쓰고 기존 시험(TC-VI-018, `test_sec_03`)이 거부 목록 항목을 요구한다. 대신 api 이미지는 COPY 단위로 좁혔고 web 이미지는 최종 단계에 `dist` 만 복사한다. 허용 목록 전환은 후속 선택 사항.
2. PowerShell 스크립트(`restore.ps1` 등)는 바꾸지 않았다. 이 클라우드에 pwsh 가 없어 **IT-504(restore.ps1 경유)는 실행하지 못했다** — 같은 `ytweb-db restore` 경로를 TC-WIX-032 가 직접 실행해 확인했다. IT-504 실행은 pwsh 가 있는 환경의 몫.
3. 보안 `test_sec_04` 첫 실행에서 2건 실패: (a) `known_limit_app_role_can_modify_non_audit_tables`(TW-32)는 앞선 시험이 남긴 DB 상태 때문이며 스키마 초기화 후 통과, (b) `huge_integers_are_client_errors_on_postgres` 는 **XPASS(strict)** — 병렬 백엔드 수정 담당이 DEF-9-001 을 고쳐 xfail 표식이 낡았다(이 단위 소관 아님, 백엔드/보안 시험 담당이 표식 제거 필요).
4. `VI_LIVE=1` 로 `test_vi_independent.py` 전체 실가동 묶음을 임시 스택에 돌리면 7건이 실패한다(TC-VI-100[db/migrate/api/worker]·107 은 비밀 마운트 원본 경로가 `…/web/secrets/` 라고 가정, 121·123 은 `VI_RUN` 사본 폴더 필요). 제품이 아니라 임시 스택 배치 차이이며 이 단위의 변경과 무관(확인: 실패 메시지가 경로/None). 6단계 담당이 정식 배치로 재실행해야 한다. 또 nginx 하네스 TC-VI-047 이 부하 상황에서 한 번 502 로 실패한 적이 있으나(stub 기동 경합) 단독 3회 재실행 통과.
5. 게이트 1: 이 단위 파일에 대한 린트 설정 없음(셸/Dockerfile/nginx/SQL). 대체로 정적 시험 + 실제 nginx(`nginx -t` 와 동일하게 컨테이너 기동), `psql` 실행, 이미지 빌드로 확인. hadolint·shellcheck·PSScriptAnalyzer 는 미수행.
6. Docker Desktop(WSL2)·Windows 방화벽 동작(DEF-9-011)은 이 단위에서 확인하지 못했고 문서에 "사용자 PC 실측 필요"로 명시.
7. `traceability.md` 는 이 호출에서 갱신하지 않았다(병렬 규칙에 준해 아래 요청으로 남김).

## F. 자체 코드 리뷰 체크리스트 (게이트 2)

- [x] 지시(DEC-046 범위)와 구현 일치 — 편차: DEF-7-001 은 지시 항목 목록에는 없고 "읽을 것"에만 있었으나 같은 파일(`proxy.conf`)의 W-INF 몫 Open 결함이라 함께 수정(질문으로 올림)
- [x] 에러 처리: guard SQL 은 회수 실패·SELECT 상실 시 `RAISE EXCEPTION` -> `psql ON_ERROR_STOP` + `set -e` 로 복원 명령 실패
- [x] 경계 입력 검증: 변경 없음(백업 파일명 정규식 유지). nginx 새 location 은 입력을 쓰지 않는 고정 응답
- [x] 하드코딩 비밀 없음(비밀 파일은 `.harness-tmp/fixinf/secrets`, 저장소 밖 임시 경로)
- [x] 새 외부 의존성 없음(런타임). 시험용 임시 venv 의 패키지는 PyPI 에서 직접 설치되어 실존 확인
- [x] 범위 외 변경 없음: 소유 범위 밖은 시험 기대 갱신뿐(C-3에 사유). 프런트·백엔드 소스 미수정

## G. 6단계(독립 검증)를 위한 인수 조건

1. `python -m pytest web/tests_infra` 통과(도커 없이 89 통과), 임시 스택에서 `WIX_LIVE=1`(`WIX_PROJECT`·`WIX_PORT` 지정) 로 TC-WIX-030~033 통과.
2. 복원 후 `ytweb_app` 이 `alembic_version` 에서 SELECT 만 가능, `audit_log` 는 SELECT·INSERT 만 가능.
3. `curl -H 'Host: 127.0.0.1:8080' http://127.0.0.1:<포트>/healthz` -> 404 text/plain, `/api/healthz` -> 200 JSON, `/api/*` 응답 CSP = `default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'`, Cache-Control 1개.
4. api 이미지 `/app` 에 개발 캐시·비밀형 파일 0건.
5. pwsh 가 있는 환경에서 IT-504, 전체 `test_vi_independent.py` 실가동 묶음 재실행.

## H. 공유 문서 갱신 요청 (병렬 규칙)

- traceability: DEF-7-001·002·006·007, DEF-9-006·017 = 수정(구현됨, 6단계 재검증 대기). DEF-9-011·013·014 = 문서화 수용(DEC-046).
- decisions: (1) `/healthz`·`/readyz` 는 nginx 에서 404, 상태 확인은 `/api/*` 만(문서 3종 정정 필요), (2) `/api` 응답 CSP 는 `default-src 'none'` 별도 snippet, (3) api 이미지 COPY 단위 축소.
