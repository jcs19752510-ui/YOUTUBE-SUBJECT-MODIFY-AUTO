# 테스트 결과서 — W-INF Docker 인프라(이미지 3종·compose·nginx·DB 초기화·PowerShell 스크립트) (6단계 독립 검증)

## 1. 개요
- 테스트 대상: 작업 단위 **W-INF** — `web/compose.yaml`, `web/compose.online.yaml`, `web/docker/{api,web,db}.Dockerfile`, `web/docker/nginx/*`, `web/docker/db/*`, `web/docker/requirements-youtube-title.txt`, `web/scripts/*.ps1`(9개), `web/README.md`, 루트 `.dockerignore`·`.gitignore`(추가분)
- 테스트 유형: 단위(독립 심사자 재검증, 구현자 시험을 믿지 않고 설계서·요구사항에서 새로 작성)
- 적용 Tier: 속도 트랙 표기 없음 → L3(일반), 위험도 등급은 Standard 로 간주(규칙 B 원문: 최소 2회). 06·07 병합 조건 미적용(병렬 호출)
- 적용 속도 트랙: L3
- 병렬 실행 정보: 병렬 웨이브(W-BE-A, W-BE-B, W-FE, W-INF 독립 검증 4건 동시). 이 단위의 임시 폴더 `.harness-tmp/vi/`, 도커 데몬·소켓·프로젝트 접두사 `harness-tmp-vi`, 호스트 게시 포트 **18081** 한 개만 사용
- 테스트 목적: 노트 9절 인수 조건 6건과 D-01~D-14 를 구현자 시험과 별개로 증명하고, 안전 설정(비루트·읽기 전용·cap 제거·격리·권한 분리·비밀·nginx 방어·백업/복원·파괴 방지)을 변이 점검으로 시험이 실제로 지키는지 확인
- 관련 산출물: `docs/harness/units/web-WU-INF-note.md`, `docs/yt/DESIGN.md` Part B, `docs/yt/WEB_DESIGN.md` §1·§5·§7, `웹프로그램으로수정요청.md` D-01~D-14, `docs/harness/_parallel/web-verify-brief.md`
- 테스트 수행자(에이전트): 6단계 독립 심사자 `vi`(서브에이전트)
- 테스트 일시: 2026-10-10 (rate limit 중단 후 재개 포함)

## 2. 테스트 범위 및 제외 범위
- 범위(In-Scope): 노트 AC 6건, D-01~D-14, S-W01·S-W04 중 인프라 부분. (a) 정적 파싱 42건 (b) 저장소의 nginx·DB 설정을 실제 이미지에 얹은 일회용 컨테이너 시험 (c) 실제 compose 스택(5서비스) 실측 (d) pwsh 7.5.4(Linux) 로 9개 스크립트 실행·추적 (e) 변이 점검 113곳
- 제외 범위(Out-of-Scope) 및 사유 — **모두 PASS 로 세지 않은 미수행 항목**:
  1. **Windows·Docker Desktop(WSL2)·PowerShell 5.1 실측**: 이 컨테이너는 Linux 엔진·pwsh 7 뿐. 127.0.0.1 한정 게시의 Desktop 동작, Windows ACL(`Set-OwnerOnlyAcl`), `wsl --status` 경로, 5.1 호환은 사용자 PC 확인 필요(README 8절 체크리스트)
  2. **브라우저 CSP 동작**: 브라우저 없음. 헤더 문자열·인라인 script/style 0개만 확인
  3. **이미지 취약점 스캔·SBOM(D-11)·레이어 비밀 스캔 도구(Trivy 등)**: 9단계 범위. 대신 이미지 tar 에서 실제 비밀 값 바이트 검색은 수행(TC-VI-107)
  4. **저장소 Dockerfile 의 직접 빌드**: 이 클라우드는 TLS 중간자 프록시 때문에 저장소 Dockerfile 을 그대로 빌드할 수 없다. 빌드는 `api`·`web` 빌더 단계에 프록시 CA 복사·`ENV SSL_CERT_FILE…` 두 줄만 덧붙인 사본으로 했고, 그 외 지시문은 동일하다
  5. **PSScriptAnalyzer**(PowerShell 린터): 설치 불가 → pwsh 파서와 정적 시험으로 대체
  6. 서로 다른 Python 소스 변경으로 인한 api/web 앱 동작(백엔드·프런트 결함)은 대상 아님(읽기만)
- 도커 자원은 `harness-tmp-vi*` 접두사만 사용, 다른 에이전트 자원은 건드리지 않음

## 3. 테스트 환경
- 실행 환경: Linux 6.18(cgroup v1, overlayfs), Docker Engine 29.8.2(심사자 전용 dockerd), Compose 5.6.0, buildx 0.37.1, pwsh 7.5.4, Python 3.13.16 + pytest 9.1.1·PyYAML 6.0.3, pyflakes 4.0.3, hadolint 2.15.1, shellcheck 0.11.0, yamllint 1.38.0, 베이스 이미지: python:3.12-slim / node:22-bookworm-slim / nginx-unprivileged:stable-alpine / postgres 17.11 (Dockerfile 에 고정된 다이제스트 그대로 pull 됨 → 다이제스트가 실제로 존재함을 확인)
- 도커 데몬 기동 방법(노트에 구체 옵션이 없어 로그로 맞춤): `dockerd --config-file .harness-tmp/vi/docker/daemon.json --data-root .harness-tmp/vi/docker/data --exec-root .harness-tmp/vi/docker/exec --pidfile … --host unix://…/vi/docker/docker.sock` (환경에 `HTTPS_PROXY`·`NO_PROXY` 전달, `daemon.json` = `{"default-address-pools":[{"base":"10.99.0.0/16","size":24}],"bip":"10.98.0.1/24"}` 로 다른 데몬과 대역 분리). 기본 iptables 로 bridge 네트워크가 동작했고 `DOCKER_HOST` 로 이 소켓만 사용
- 테스트 데이터: 임의 생성한 비밀 파일 3개(랜덤 64자 16진수, **사본 폴더** `.harness-tmp/vi/work/run/web/secrets`, 파일 모드는 0644 — 0600 이면 비루트 컨테이너가 읽지 못함, 관찰 O-VI-05), 가짜 마커 행. 실제 구글·AI 호출 없음, 외부 전송 없음
- compose 는 사본(`work/run/web/compose.yaml`)에서 호스트 게시를 `127.0.0.1:18081:8080` 로만 바꿔 사용(원본 미수정). nginx 허용 Host 는 `127.0.0.1:8080`/`localhost:8080` 고정이라 curl 은 `Host:` 헤더를 명시. 스크립트 시험은 사본 `scripts_p`(포트·status 정규식·Host 헤더 3곳만 18081 로 패치)와 원본 동작 대조용 `scripts`(패치 없음)를 같이 사용
- 전제 조건: 이전 단위 구현 완료, 백엔드 이미지는 현재 저장소 소스로 빌드(프런트 빌드도 성공)

## 4. 테스트 케이스 및 결과
**실행 합계(최종 공식 실행, 전부 한 번에)**: `pytest web/tests_infra/test_vi_independent.py` → **204 passed, 1 skipped, 3 xfailed(기대와 다른 동작을 결함으로 고정한 시험 3건)**, 실패 0. 건너뜀 1건은 TC-VI-136(pin-digests, Docker Hub 조회 지연·실패 시 시험이 스스로 건너뜀)이며 **같은 환경에서 단독 재실행하면 Pass(1 passed)** — 즉 전체 208건 중 205건 Pass + 3건 xfail, 단 한 번의 연속 실행에서는 204건이다(레지스트리 의존 시험이라 환경 요인). 구현자 시험 `web/tests_infra/test_compose_security.py` → 36 passed(pwsh 를 PATH 에 두고 실행, docker CLI 사용 `compose config` 3건 포함). 항목 수 208 = 함수 87개 + 파라미터 전개.

### 4-1. 인수 조건(AC) ↔ 시험 추적 (노트 9절)
| AC | 내용 | 연결 시험 | 결과 |
|---|---|---|---|
| AC1 | `pytest web/tests_infra` TC-WI-001~034 모두 통과(없는 도구는 건너뜀) | TC-WI-001~034(36항목) 재실행 + TC-VI-034(pwsh 구문) | Pass 36/36 |
| AC2 | `docker compose config` 성공, 호스트 게시 1건(127.0.0.1:8080) | TC-WI-030~032, TC-VI-001, TC-VI-102 | Pass |
| AC3 | 스택 기동 → 전 서비스 healthy, `status.ps1` 문제 없음, 불허 Host 무응답 | TC-VI-100~103, 109, 120, 130, 132b, 133, 137, TC-VI-040 | Pass |
| AC4 | DB 권한 실측: 앱 계정 audit_log UPDATE/DELETE/TRUNCATE·CREATE 거부 | TC-VI-060, 063, 110(41 SQL), 111, 113 | Pass (단 DEF-VI-002 별도) |
| AC5 | 백업→삭제→복원 행 수 일치, 복원 후 audit_log 권한 회수 유지 | TC-VI-064, 131, 026, 025 | Pass |
| AC6 | down 만으로 볼륨 유지, `-DeleteVolumes` 는 확인 문구 없이 불가, harness-tmp 정리 | TC-VI-132, 133, 134, 027, 028, 정리 7절 | Pass |

### 4-2. D-01~D-14 ↔ 시험
| 요구 | 연결 시험 | 판정 |
|---|---|---|
| D-01 서비스·healthy 순서 | 009, 100, 109, 123, 133 | 충족(dev/test 프로필은 구현 안 함 — 노트에 "부분"으로 선언됨, 수용 대상 아님: 사용자 확인 질문 6) |
| D-02 127.0.0.1 한정 게시 | 001, 102, 132b, 040 | 충족(Linux 엔진). **Docker Desktop 미수행** |
| D-03 비루트·RO·cap·nnp | 002, 003, 014, 100, 101 | 충족 |
| D-04 다이제스트·멀티 스테이지 | 013, 015, 016, 108, 136 | 충족 |
| D-05 .dockerignore·레이어 비밀 | 018, 036, 037, 107, 108 | 충족(스캐너 미수행) |
| D-06 비밀 주입 | 008, 036, 107, 137 | 충족 |
| D-07 명명 볼륨·삭제 보호 | 004, 027, 028, 132~134 | 충족 |
| D-07a PostgreSQL | 011, 021~023, 060~064, 110, 111, 113 | 충족(DEF-VI-002 제외) |
| D-07b Alembic 별도 단계 | 009, 123 | 충족(자동 사전 백업은 노트 선언대로 미구현) |
| D-08 헬스·재시작·종료·로그 | 009, 010, 109, 121, 122 | 충족(api 종료코드 143 관찰) |
| D-09 시간대 | 010, 060, 113 | 충족 |
| D-10 아웃바운드 제한 | 005, 006, 103~106 | **부분**: api/worker/db 는 충족, web 은 edge 경유 egress·db 도달 가능(DEF-VI-001) |
| D-11 취약점·SBOM | 017(잠금 부분) | 미수행(9단계) |
| D-12 Windows 스크립트 | 027~034, 130~137 | 충족(Linux pwsh 7). **PS 5.1·Windows 미수행** |
| D-13 harness-tmp 접두사 | 전체 + 7절 | 충족 |
| D-14 자원 상한 | 007, 100 | 충족 |

### 4-3. 케이스 표 (TC-VI-nnn, 함수 단위로 묶음 — 파라미터 전개 건수 표기)
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고(검증하는 AC/요구) |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-VI-001 | compose 에서 호스트 게시 포트가 web 의 127.0.0.1:<포트>:8080 한 건뿐인가(expose 포함) | 정적 | pytest `-k tc_vi_001` (1건) | 게시 1건, 주소 127.0.0.1 | Pass 1건 | Pass | AC2, D-02, S-W01 |
| TC-VI-002 | 5개 서비스 모두 숫자 uid:gid 이고 0 이 아닌가 | 정적 | pytest `-k tc_vi_002` (1건) | 전부 비루트 | Pass 1건 | Pass | AC3, D-03 |
| TC-VI-003 | read_only·cap_drop ALL·cap_add 없음·no-new-privileges·init, privileged/devices/host 네임스페이스/extra_hosts 등 금지 키 없음 | 정적 | pytest `-k tc_vi_003` (1건) | 전부 충족 | Pass 1건 | Pass | D-03 |
| TC-VI-004 | docker.sock·호스트 폴더 바인드 없음, 볼륨은 명명 볼륨뿐·driver_opts 없음, tmpfs 는 noexec,nosuid | 정적 | pytest `-k tc_vi_004` (1건) | 충족 | Pass 1건 | Pass | D-07, D-03 |
| TC-VI-005 | app 네트워크 internal, web 만 edge 추가, db/api/worker/migrate 는 app 만 | 정적 | pytest `-k tc_vi_005` (1건) | 충족 | Pass 1건 | Pass | D-10 |
| TC-VI-006 | compose.online.yaml 은 api·worker 에만 egress 를 붙이고 db/web 은 안 붙이며 기본 compose 에 egress 가 없다 | 정적 | pytest `-k tc_vi_006` (1건) | 충족 | Pass 1건 | Pass | D-10 |
| TC-VI-007 | 자원 상한(cpus≤2, memory≤1G, pids≤512)과 합계 메모리 ≤2.5G | 정적 | pytest `-k tc_vi_007` (1건) | 충족 | Pass 1건 | Pass | D-14 |
| TC-VI-008 | 비밀은 *_FILE 경로만, 평문 환경변수·명령행·빌드 인자 없음, 서비스별 최소 비밀(web 은 비밀 없음) | 정적 | pytest `-k tc_vi_008` (1건) | 충족 | Pass 1건 | Pass | D-06 |
| TC-VI-009 | 기동 순서 체인(db healthy→migrate→api/worker→api healthy→web), 재시작 정책, 헬스체크 정의, db 종료 유예 ≥30초 | 정적 | pytest `-k tc_vi_009` (1건) | 충족 | Pass 1건 | Pass | D-01, D-08 |
| TC-VI-010 | 로그 회전(json-file, ≤100m, 2~10개)과 TZ=Asia/Seoul, DB timezone/log_timezone=UTC | 정적 | pytest `-k tc_vi_010` (1건) | 충족 | Pass 1건 | Pass | D-08, D-09 |
| TC-VI-011 | DB 명령: hba_file, scram, log_statement=none, 연결 수 30~100, 체크섬·UTF8, trust 인증 환경변수 없음 | 정적 | pytest `-k tc_vi_011` (1건) | 충족 | Pass 1건 | Pass | D-07a |
| TC-VI-012 | 앱 환경: API 문서 끔, 허용 Host 정확히 2개, --no-access-log/--no-server-header, --reload/--proxy-headers 없음 | 정적 | pytest `-k tc_vi_012` (1건) | 충족 | Pass 1건 | Pass | S-W01, D-03 |
| TC-VI-013 | Dockerfile 3종의 모든 FROM 이 태그@sha256(64자) 로 고정(latest 금지) | 정적 | pytest `-k tc_vi_013` (3건) | 고정 | Pass 3건 | Pass | D-04 |
| TC-VI-014 | Dockerfile 최종 USER 가 비루트, ADD URL/curl|sh/--insecure/ENV 비밀 등 위험 지시문 없음 | 정적 | pytest `-k tc_vi_014` (3건) | 충족 | Pass 3건 | Pass | D-03, D-04 |
| TC-VI-015 | api 이미지: 멀티 스테이지, pip --require-hashes --only-binary --no-deps, 컨텍스트 통복사·비밀 복사 없음, HEALTHCHECK | 정적 | pytest `-k tc_vi_015` (1건) | 충족 | Pass 1건 | Pass | D-04 |
| TC-VI-016 | web 이미지: npm ci --ignore-scripts, 소스맵 삭제, 런타임 단계에 node 없음, USER 101 | 정적 | pytest `-k tc_vi_016` (1건) | 충족 | Pass 1건 | Pass | D-04, D-05 |
| TC-VI-017 | requirements-youtube-title.txt 와 backend/requirements.txt 의 모든 항목이 ==핀 + 중복 없는 sha256 해시 | 정적 | pytest `-k tc_vi_017` (2건) | 충족 | Pass 2건 | Pass | D-11(잠금 부분) |
| TC-VI-018 | .dockerignore 20개 필수 항목과 .gitignore 의 secrets/backups/*.dump | 정적 | pytest `-k tc_vi_018` (1건) | 충족 | Pass 1건 | Pass | D-05, D-06 |
| TC-VI-019 | nginx 기준선: server_tokens, 본문 1m, 타임아웃, 헤더 버퍼, 속도 제한 구역·429, listen 1개, Host 허용 map(정확 2개)·444, 로그에 query/cookie 변수 없음, error_log 수준 | 정적 | pytest `-k tc_vi_019` (1건) | 충족 | Pass 1건 | Pass | S-W01, S-W04 |
| TC-VI-020 | 모든 proxy location 이 보안 헤더 include·limit_req·proxy.conf·no-store 를 갖고(healthz/readyz 제외 limit_except), 헤더 7종 always, CSP 핵심 지시자, XFF 덮어쓰기, 백엔드 헤더 숨김 | 정적 | pytest `-k tc_vi_020` (1건) | 충족 | Pass 1건 | Pass | S-W04 |
| TC-VI-021 | pg_hba: scram/reject 뿐, 마지막 reject, 슈퍼유저는 루프백만, 앱·소유자는 ytweb DB 와 사설 대역만 | 정적 | pytest `-k tc_vi_021` (1건) | 충족 | Pass 1건 | Pass | D-07a |
| TC-VI-022 | 역할 초기화 스크립트 규칙(NO* 속성 2회, 연결 한도, PUBLIC 회수, 비밀번호 길이·동일 검사, 로그 억제, 표식은 마지막) | 정적 | pytest `-k tc_vi_022` (1건) | 충족 | Pass 1건 | Pass | D-07a |
| TC-VI-023 | schema-grants.sql(PUBLIC 회수, 앱 DML+시퀀스만, TRUNCATE/CREATE 없음)와 audit-guard.sql(UPDATE/DELETE/TRUNCATE 회수+검사+예외) | 정적 | pytest `-k tc_vi_023` (1건) | 충족 | Pass 1건 | Pass | D-07a, AC4 |
| TC-VI-024 | db Dockerfile 복사 모드(0755/0644), /backups 0700, CRLF 제거, 모든 설정 파일 LF | 정적 | pytest `-k tc_vi_024` (1건) | 충족 | Pass 1건 | Pass | D-07a |
| TC-VI-025 | ytweb-db 정적 안전: strict 모드, umask 077, 이름 정규식, 단일 트랜잭션·exit-on-error·clean, 복원 후 audit-guard, 소유자 계정 사용 | 정적 | pytest `-k tc_vi_025` (1건) | 충족 | Pass 1건 | Pass | AC5 |
| TC-VI-026 | ytweb-db 를 호스트에서 실행: 12개 나쁜 이름 × 4개 명령 거부, 알 수 없는 명령, 빈 파일, 없는 파일, 덮어쓰기 거부, remove, 비밀 파일 없음 | 정적 | pytest `-k tc_vi_026` (1건) | 전부 종료코드 1·한국어 메시지 | Pass 1건 | Pass | AC5 |
| TC-VI-027 | PowerShell 9개 파일: BOM, 위험 명령(iex·prune·volume rm·Bypass 등) 없음, 비밀 출력 없음, '--volumes'/'-v' 는 reset-demo 에만, stop 은 down 만 | 정적 | pytest `-k tc_vi_027` (1건) | 충족 | Pass 1건 | Pass | D-07, D-12, AC6 |
| TC-VI-028 | reset-demo: 확인 문구 읽기가 백업·볼륨 삭제·스키마 초기화보다 앞, 문구 2종, exit 2, 사전 백업 실패 시 중단 | 정적 | pytest `-k tc_vi_028` (1건) | 충족 | Pass 1건 | Pass | AC6 |
| TC-VI-029 | restore: 이름 검사→SHA 검사→확인 문구→사전 백업→서비스 정지→복원 순서, 임시 사본 정리, 실패 시 서비스 재기동 후 오류 | 정적 | pytest `-k tc_vi_029` (1건) | 충족 | Pass 1건 | Pass | AC5 |
| TC-VI-030 | backup: Prefix 패턴, 이름 검사→dump→list→cp→해시→컨테이너 파일 삭제 순서, 크기 불일치 거부 | 정적 | pytest `-k tc_vi_030` (1건) | 충족 | Pass 1건 | Pass | AC5 |
| TC-VI-031 | status: 게시 주소 정규식 엄격, [위험] 시 problems++·exit 1, 루프백 검사, healthz/readyz 응답 확인 | 정적 | pytest `-k tc_vi_031` (1건) | 충족 | Pass 1건 | Pass | AC3 |
| TC-VI-032 | _common: StrictMode·Stop, Docker 모드/버전 검사 문자열, 비밀 파일 덮어쓰기 금지(2곳), RandomNumberGenerator(Get-Random 아님), 볼륨 존재 시 비밀 재생성 거부 | 정적 | pytest `-k tc_vi_032` (1건) | 충족 | Pass 1건 | Pass | D-12 |
| TC-VI-033 | start 흐름 순서(Docker→비밀→포트→up→대기→포트 경고), --build/NoBuild | 정적 | pytest `-k tc_vi_033` (1건) | 충족 | Pass 1건 | Pass | D-12, AC3 |
| TC-VI-034 | pwsh 파서로 9개 ps1 구문 오류 0 | 정적 | pytest `-k tc_vi_034` (1건) | 0건 | Pass 1건 | Pass | D-12 |
| TC-VI-035 | README 주장(127.0.0.1, down -v 경고, 확인 문구 3종, PostgreSQL 17, 이미지 이름)이 설정·스크립트와 일치 | 정적 | pytest `-k tc_vi_035` (1건) | 충족 | Pass 1건 | Pass | D-07, D-12 |
| TC-VI-036 | 단위 파일 전체에 비밀 같은 40자 이상 16진수·리터럴 비밀번호·개인키 패턴 없음 | 정적 | pytest `-k tc_vi_036` (1건) | 없음 | Pass 1건 | Pass | D-06 |
| TC-VI-037 | Dockerfile 이 secrets/.env/token/.git/컨텍스트 전체를 COPY 하지 않음 | 정적 | pytest `-k tc_vi_037` (1건) | 충족 | Pass 1건 | Pass | D-05 |
| TC-VI-040 | Host 허용 목록 14종(정상 2, 대문자, 후행 공백, 불허 도메인·IP·포트·IPv6·접미사 위장·쉼표 결합·무포트·빈 값) | 일회용 컨테이너 | pytest `-k tc_vi_040` (14건) | 허용 3건 200, 거부 무응답/400, 빈 값 400 | Pass 14건 | Pass | S-W01, AC3 |
| TC-VI-041 | 메서드×경로 26종(/, /assets, /api, 세션, healthz)에서 허용/403/405 | 일회용 컨테이너 | pytest `-k tc_vi_041` (26건) | 표와 일치 | Pass 26건 | Pass | S-W04 |
| TC-VI-042 | 9개 응답(200/404/403/405/api/healthz/readyz …)에서 보안 헤더 7종이 정확히 1벌, CSP 지시자 정확 일치, X-Frame DENY, Server 에 버전 없음 | 일회용 컨테이너 | pytest `-k tc_vi_042` (9건) | 충족 | Pass 9건 | Pass | S-W04 |
| TC-VI-043 | nginx 가 만든 오류 응답(414/400/413)에도 보안 헤더가 붙는다 | 일회용 컨테이너 | pytest `-k tc_vi_043` (1건) | 충족 | Pass 1건 | Pass | S-W04 |
| TC-VI-044 | 요청 본문 경계: 0, 1KB, 1MB-1, 1MB 는 통과, 1MB+1, 2MB 는 413 | 일회용 컨테이너 | pytest `-k tc_vi_044` (1건) | 경계 정확 | Pass 1건 | Pass | S-W04 |
| TC-VI-045 | 프록시: 경로·질의 그대로 전달, Host 유지, 클라이언트 XFF 위조 무시, 백엔드 CSP·X-Frame·X-Powered-By·Server 숨김, no-store, Set-Cookie 속성 통과 | 일회용 컨테이너 | pytest `-k tc_vi_045` (1건) | 충족 | Pass 1건 | Pass | S-W04 |
| TC-VI-046 | /api/healthz·readyz 가 백엔드 /healthz·/readyz 로 변환(쿼리 제거), 관찰: POST 도 전달됨 | 일회용 컨테이너 | pytest `-k tc_vi_046` (1건) | 충족(관찰 O-VI-01) | Pass 1건 | Pass | D-08 |
| TC-VI-047 | 세션 발급 속도 제한: 새 컨테이너에서 11건 통과 뒤 429, 429 응답에도 보안 헤더, 다른 API 구역·정적 파일은 영향 없음 | 일회용 컨테이너 | pytest `-k tc_vi_047` (1건) | 첫 429 가 10~12번째 | Pass 1건 | Pass | S-W04 |
| TC-VI-048 | 일반 API 폭주(200 동시 ×3)에서 200 과 429 가 모두 나온다 | 일회용 컨테이너 | pytest `-k tc_vi_048` (1건) | 충족 | Pass 1건 | Pass | S-W04 |
| TC-VI-049 | 경로 탈출·점 파일·인코딩 우회 13종이 파일을 노출하지 않고 SPA 폴백만 나온다 | 일회용 컨테이너 | pytest `-k tc_vi_049` (13건) | 노출 0 | Pass 13건 | Pass | S-W01 |
| TC-VI-050 | 소스맵/점 파일 비제공, 캐시 정책(/ no-cache, assets immutable), 인라인 script·style·on* 없음 | 일회용 컨테이너 | pytest `-k tc_vi_050` (1건) | 충족 | Pass 1건 | Pass | D-04 |
| TC-VI-051 | 9KB 헤더 400, CRLF 주입이 응답 헤더에 반영되지 않음 | 일회용 컨테이너 | pytest `-k tc_vi_051` (1건) | 충족 | Pass 1건 | Pass | S-W04 |
| TC-VI-052 | 느린 헤더(slowloris) 10초 후 연결 종료 | 일회용 컨테이너 | pytest `-k tc_vi_052` (1건) | 14초 이내 종료 | Pass 1건 | Pass | S-W04 |
| TC-VI-053 | 느린 본문 10초 후 연결 종료(408/종료) | 일회용 컨테이너 | pytest `-k tc_vi_053` (1건) | 14초 이내 종료 | Pass 1건 | Pass | S-W04 |
| TC-VI-054 | 접근 로그는 JSON 6개 필드뿐이고 쿼리·쿠키·Authorization·UA 가 없다 | 일회용 컨테이너 | pytest `-k tc_vi_054` (1건) | 충족 | Pass 1건 | Pass | S-W04 |
| TC-VI-055 | 오류 로그에 쿼리 문자열이 없다(**기대와 다름 → xfail, DEF-VI-003**) | 일회용 컨테이너 | pytest `-k tc_vi_055` (1건) | xfail(결함 확인) | xfail(결함 확인) 1건 | xfail | S-W04 |
| TC-VI-056 | nginx 시작 로그·nginx -t 에 경고 없음, gzip 은 HTML 에 동작(**DEF-VI-004 회귀**) | 일회용 컨테이너 | pytest `-k tc_vi_056` (1건) | 충족 | Pass 1건 | Pass | D-08 |
| TC-VI-060 | 새 DB 초기화: 역할 속성·연결 한도·시간대·인코딩·DB ACL·PUBLIC 회수·스키마 소유·SCRAM, 소유자 새 테이블에 앱 기본 권한(TRUNCATE 없음), audit-guard 회수 및 PUBLIC 열림 시 가드 실패, 로그에 비밀 없음 | 일회용 컨테이너 | pytest `-k tc_vi_060` (1건) | 충족 | Pass 1건 | Pass | D-07a, AC4 |
| TC-VI-061 | 약한/동일/빈 비밀번호 5종은 초기화 실패(fail-closed), 로그 [ytweb-init], 헬스 표식 없음 | 일회용 컨테이너 | pytest `-k tc_vi_061` (5건) | 전부 실패 | Pass 5건 | Pass | D-07a |
| TC-VI-062 | 정확히 16자 비밀번호는 성공(경계) | 일회용 컨테이너 | pytest `-k tc_vi_062` (1건) | 성공 | Pass 1건 | Pass | D-07a |
| TC-VI-063 | pg_hba 실동작: 허용 3건, 거부 9건(다른 DB·잘못된 비밀번호·교차 비밀번호·없는 계정·replication), 소켓 접속도 비밀번호 필요, 앱 계정 16가지 위험 SQL 거부 | 일회용 컨테이너 | pytest `-k tc_vi_063` (1건) | 충족 | Pass 1건 | Pass | D-07a, AC4 |
| TC-VI-064 | ytweb-db 실동작: dump/list/counts/restore, 덮어쓰기 거부, 복원이 앱 audit 권한 재회수, 끝이 잘린 덤프는 실패하고 기존 데이터 보존(단일 트랜잭션), 손상 파일 친절 오류, 경로 탈출 거부, reset-schema, 파일 권한 600 | 일회용 컨테이너 | pytest `-k tc_vi_064` (1건) | 충족 | Pass 1건 | Pass | AC5 |
| TC-VI-100 | 기동 중 5개 컨테이너의 inspect: 비루트·RO·cap·nnp·init·자원·로그·마운트(비밀 파일 RO 단일 파일 + 명명 볼륨뿐) | 실가동 스택 | pytest `-k tc_vi_100` (5건) | 충족 | Pass 5건 | Pass | D-03, D-14, D-07 |
| TC-VI-101 | 컨테이너 프로세스 CapEff/CapPrm/CapBnd=0·NoNewPrivs=1·Seccomp=2, 루트 FS 쓰기·tmpfs 실행 거부 | 실가동 스택 | pytest `-k tc_vi_101` (4건) | 충족 | Pass 4건 | Pass | D-03 |
| TC-VI-102 | docker inspect 게시 포트 = web 의 127.0.0.1:<포트> 한 건, 호스트 /proc/net/tcp 리스너 127.0.0.1 만, 호스트의 다른 4개 IP 로 접속 실패, 5432/8000 닫힘 | 실가동 스택 | pytest `-k tc_vi_102` (1건) | 충족(Linux 엔진) | Pass 1건 | Pass | AC2, D-02, S-W01 |
| TC-VI-103 | app internal=true·구성원, edge 구성원은 web 뿐, egress 네트워크 없음 | 실가동 스택 | pytest `-k tc_vi_103` (1건) | 충족 | Pass 1건 | Pass | D-10 |
| TC-VI-104 | api/worker/db 에서 인터넷 IP 2종·메타데이터 IP·DNS 조회가 모두 실패 | 실가동 스택 | pytest `-k tc_vi_104` (8건) | 전부 실패 | Pass 8건 | Pass | D-10 |
| TC-VI-105 | 정상 경로(api→db, web→api) 동작과 db→api 도달 관찰 | 실가동 스택 | pytest `-k tc_vi_105` (1건) | 충족 | Pass 1건 | Pass | D-10 |
| TC-VI-106 | web 이 db 포트·인터넷에 도달하지 못한다(**기대와 다름 → xfail, DEF-VI-001**) | 실가동 스택 | pytest `-k tc_vi_106` (1건) | xfail(결함 확인) | xfail(결함 확인) 1건 | xfail | D-10 |
| TC-VI-107 | 비밀 값이 env·inspect·이미지 save·history·로그에 없음, 서비스별 /run/secrets 최소 파일 | 실가동 스택 | pytest `-k tc_vi_107` (1건) | 없음 | Pass 1건 | Pass | D-06, AC |
| TC-VI-108 | 이미지 내용: 소스맵·.ts·테스트·.env·token·.git·approvals·data/secrets 폴더·컴파일러·git·curl 없음, 사용자·환경변수 점검 | 실가동 스택 | pytest `-k tc_vi_108` (1건) | 충족 | Pass 1건 | Pass | D-04, D-05 |
| TC-VI-109 | healthy 4종, 워커 헬스체크 음/양성, migrate 종료 0, DB 초기화 표식 없으면 unhealthy | 실가동 스택 | pytest `-k tc_vi_109` (1건) | 충족 | Pass 1건 | Pass | D-08 |
| TC-VI-110 | 앱 계정 권한 경계 41개 SQL(DML 허용, DDL·DROP·TRUNCATE·audit 수정·역할·확장·파일·프로그램·ALTER SYSTEM 거부) | 실가동 스택 | pytest `-k tc_vi_110` (41건) | 기대와 일치 | Pass 41건 | Pass | D-07a, AC4 |
| TC-VI-111 | audit_log 권한 행렬 = INSERT,SELECT 뿐, 슈퍼유저 속성 계정은 postgres 뿐, 앱/소유자는 다른 역할의 구성원 아님 | 실가동 스택 | pytest `-k tc_vi_111` (1건) | 충족 | Pass 1건 | Pass | AC4 |
| TC-VI-112 | 앱 계정이 alembic_version 을 수정·삭제할 수 없다(**기대와 다름 → xfail, DEF-VI-002**) | 실가동 스택 | pytest `-k tc_vi_112` (1건) | xfail(결함 확인) | xfail(결함 확인) 1건 | xfail | D-07a |
| TC-VI-113 | 서버 설정: scram·체크섬·UTC·max_connections 50·log_statement none·ssl off·hba_file·메이저 17·hba 규칙 오류 0·역할 시간대 | 실가동 스택 | pytest `-k tc_vi_113` (1건) | 충족 | Pass 1건 | Pass | D-07a, D-09 |
| TC-VI-120 | nginx 경유 종단: healthz/readyz JSON, 불허 Host 무응답, 보안 헤더, API 문서 404, 잘못된 Origin 세션 403 | 실가동 스택 | pytest `-k tc_vi_120` (1건) | 충족 | Pass 1건 | Pass | AC3 |
| TC-VI-121 | api 컨테이너를 재생성해도 nginx 가 새 IP 를 따라간다(동적 DNS) | 실가동 스택 | pytest `-k tc_vi_121` (1건) | 200 | Pass 1건 | Pass | D-08 |
| TC-VI-122 | 우아한 종료: worker/web/db 종료코드 0, api 는 0 또는 143 + 'Finished server process'(관찰 O-VI-02), OOM 없음, 재기동 후 healthy, 재시작 정책 | 실가동 스택 | pytest `-k tc_vi_122` (1건) | 충족 | Pass 1건 | Pass | D-08 |
| TC-VI-123 | 틀린 소유자 비밀번호로 migrate 실패 → compose up 이 실패(fail-closed), 로그에 비밀번호 없음, 복구 | 실가동 스택 | pytest `-k tc_vi_123` (1건) | 충족 | Pass 1건 | Pass | D-07b |
| TC-VI-130 | status.ps1 -Detail: 정상 시 '문제 없음'·보안 설정 출력, 8080 을 기대하는 원본 스크립트는 18081 게시를 [위험] 으로 표시하고 exit 1 | 실가동 스택 (pwsh) | pytest `-k tc_vi_130` (1건) | 충족 | Pass 1건 | Pass | AC3, D-12 |
| TC-VI-130B | logs.ps1: 서비스별 로그 출력·ValidateSet 거부·비밀 비노출, backup.ps1 의 나쁜 Prefix 5종 거부 | 실가동 스택 (pwsh) | pytest `-k tc_vi_130b` (1건) | 충족 | Pass 1건 | Pass | D-12 |
| TC-VI-131 | backup→변경→오답 문구 6종 취소→-Latest 선택→변조 SHA 거부→나쁜 이름 3종→쓰레기 덤프 실패 후 서비스 복구→정상 복원(사전 백업 생성·데이터 복원·audit 권한 재회수·임시 파일 정리) | 실가동 스택 (pwsh) | pytest `-k tc_vi_131` (1건) | 충족 | Pass 1건 | Pass | AC5, W-016 |
| TC-VI-132 | reset-demo 오답 문구 7종(볼륨·데이터 불변, 빈 값은 비대화형 실패), 정답 시 스키마 초기화·audit 권한 유지·사전 백업 생성 | 실가동 스택 (pwsh) | pytest `-k tc_vi_132` (1건) | 충족 | Pass 1건 | Pass | AC6 |
| TC-VI-132B | web 이 0.0.0.0 으로 게시되면 status.ps1 이 [위험] 과 exit 1 로 잡는다(복구 후 정상) | 실가동 스택 (pwsh) | pytest `-k tc_vi_132b` (1건) | 충족 | Pass 1건 | Pass | AC3, D-02 |
| TC-VI-133 | stop.ps1 이 볼륨을 보존, 비밀 없고 볼륨 있으면 start.ps1 이 거부(비밀 미생성), 다시 시작하면 복구 | 실가동 스택 (pwsh) | pytest `-k tc_vi_133` (1건) | 충족 | Pass 1건 | Pass | AC6, W-001 |
| TC-VI-134 | -DeleteVolumes 는 정확한 문구에서만 볼륨 삭제, 호스트의 백업·비밀 파일은 유지 | 실가동 스택 (pwsh) | pytest `-k tc_vi_134` (1건) | 충족 | Pass 1건 | Pass | AC6 |
| TC-VI-135 | 포트를 다른 프로그램이 쓰는 중이면 start.ps1 이 컨테이너를 만들기 전에 거부 | 실가동 스택 (pwsh) | pytest `-k tc_vi_135` (1건) | 충족 | Pass 1건 | Pass | D-12 |
| TC-VI-136 | pin-digests.ps1: 비교만 하면 파일 불변·차이 보고, -Apply 는 올바른 다이제스트로 교체(LF·BOM 없음 유지) | 실가동 스택 (pwsh) | pytest `-k tc_vi_136` (1건) | 충족 | Pass 1건 | Pass | D-04 |
| TC-VI-137 | 첫 실행: 비밀 파일이 없고 볼륨도 없으면 start.ps1 이 64자 16진수 무작위 비밀 3개(서로 다름, 화면 비출력)를 만들고 전 서비스 healthy, 재실행 시 기존 비밀을 덮어쓰지 않음 | 실가동 스택 (pwsh) | pytest `-k tc_vi_137` (1건) | 충족 | Pass 1건 | Pass | AC3, D-06, D-12 |

> 정상 경로·경계값(1MB±1, 15/16자 비밀번호, 속도 제한 11번째, 10초 타임아웃)·예외 입력(나쁜 파일명 12종, 경로 탈출 13종, 약한 비밀번호 5종)·권한 경계(앱 계정 41개 SQL)·악의적 입력(Host 위조, XFF 위조, CRLF, SHA 변조, 쓰레기 덤프)을 포함한다.

## 5. 커버리지
- 이 단위의 산출물은 대부분 선언형 설정(YAML·conf·SQL·Dockerfile)이라 줄/분기 커버리지가 정의되지 않는다. 대신 (1) 변이 점검 113곳(부록 A), (2) 실행 가능한 코드(셸·PowerShell)의 줄 추적 커버리지, (3) 설정 지시자별 시험 연결(4-2)로 대체했다.
- **셸 `ytweb-db`**: bash `xtrace` 로 줄 추적 — 실행 대상 59줄 중 58줄 도달(98.3%), 나머지 1줄(알 수 없는 명령 `*) die`)은 TC-VI-026(호스트 실행)이 도달하므로 59/59 도달. 분기: dump/list/counts/restore/reset-schema/remove 6개 서브명령, 이름 검증 실패·파일 없음·비어 있음·덮어쓰기·손상 목차·잘린 덤프(트랜잭션 롤백) 경로 모두 시험. **`01-roles.sh`**: 추적 도구를 끼울 수 없어(엔트리포인트가 실행) 분기 열거로 대체 — 성공(TC-VI-060), 소유자 짧음·앱 짧음·15자 경계·동일·빈 비밀 5건 실패(061), 16자 경계 성공(062)로 모든 `exit 1` 분기와 성공 경로에 도달. 줄 추적 수치는 **미측정**
- **PowerShell 9개**: `Set-PSDebug -Trace 1` 로 실행 줄 추적(근사 — 매개변수 선언·함수 선언 줄은 추적되지 않고 같은 텍스트의 줄은 모호하게 대응). 측정 가능한 506줄 중 381줄(**약 75%**) 도달. 시험 137 이 추가로 비밀 생성 경로(`_common.ps1` 179~211줄, 약 25줄)를 실행했으나 그 뒤에 재측정하지 않았다 → 실제로는 더 높음. 정확한 수치가 아니라 "근사 하한"이다.
- 커버되지 않은 부분과 사유:
  - Windows 전용 경로: `Set-OwnerOnlyAcl`(ACL), `wsl.exe --status` 경고, `Test-DockerReady` 의 Docker 미설치·엔진 미실행·Windows 컨테이너 모드·Compose 구버전 `Stop-Script` 분기 — Linux 에서 재현 불가(환경 한계). 문자열 존재만 정적 시험(TC-VI-032)
  - 오류 분기: `Show-ServiceFailure`·`Wait-ForStack` 시간 초과·`start.ps1` 의 `up` 실패 안내, `backup.ps1` 의 dump 실패·list 실패·cp 실패·크기 불일치, `reset-demo.ps1` 의 reset-schema 실패 롤백 — 해당 상황을 일부러 만들기 어려워(디스크 가득, cp 실패 등) 미시도. 정적 순서 시험(028~030)으로만 확인
  - `logs.ps1`·`start.ps1`·`restore.ps1` 의 `param(...)` 선언 줄은 추적 불가(도달 불가가 아니라 측정 한계)
  - `compose.online.yaml`: 병합 구성만 정적 확인(TC-VI-006, TC-WI-031), 실제 기동·외부 접속 시험은 M2·M3 범위
  - nginx `if`/`location` 의 모든 분기는 TC-VI-040~056 으로 도달. 헬스체크 `start_period` 같은 시간 의존 설정값은 실행으로만 확인

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 내용 |
|----|------|-----------|--------|------|-----------|
| DEF-VI-001 | **web(nginx) 컨테이너가 인터넷으로 나갈 수 있고 db:5432 에 도달할 수 있다.** 노트 편차 #1(web 만 edge 비-internal 망에 추가)의 귀결. README 는 "nginx 는 외부로 요청을 보내지 않는다"고만 하고 db 도달 가능성은 적지 않았다 | 스택 기동 후 `docker exec <web> wget -q -T3 -O- http://1.1.1.1/` → HTTP 응답 수신(403), `docker exec <web> nc -z db 5432` → 연결됨. 시험: `pytest -k tc_vi_106`(xfail strict) | **Medium**(nginx 가 먼저 침해돼야 악용되는 다층 방어 약화. DB 접속에는 SCRAM 비밀번호 필요) | **Open** — 설계 변경·사용자 결정 필요 | 고치지 않음. 제안: 망을 3개로 분리 — `edge`(web 만, 게시용) + `front`(internal: web↔api) + `back`(internal: api·worker·migrate↔db). web 은 back 에 붙지 않는다. 외부로 나가는 경로 자체는 "internal 단독 컨테이너는 게시 불가"(노트 편차 #1, 이번에도 미시험) 때문에 남는다 → nginx 에 egress 차단 방법(호스트 방화벽/ `iptables` 은 Desktop 에서 불가)을 따로 찾거나 수용 필요. 질문 1 |
| DEF-VI-002 | 앱 계정(`ytweb_app`)이 `alembic_version`(마이그레이션 버전 표)을 UPDATE·DELETE 할 수 있다 — 기본 권한(`ALTER DEFAULT PRIVILEGES`)이 소유자가 만드는 모든 표에 DML 을 주기 때문. audit_log 만 마이그레이션 0001 이 회수한다 | `psql -U ytweb_app -c "update alembic_version set version_num=version_num"` 성공. 시험 `tc_vi_112`(xfail strict). 권한 행렬: TC-VI-110/111 | **Low**(앱 침해 시 다음 마이그레이션이 엉뚱한 지점에서 시작되게 만들 수 있음) | **Open** — 백엔드(마이그레이션/`ytweb.migrate`) 소유 파일 | 고치지 않음. 제안: 마이그레이션 완료 후 `REVOKE INSERT,UPDATE,DELETE,TRUNCATE ON alembic_version FROM ytweb_app` (또는 `audit-guard.sql` 과 같은 방식으로 `migrate` 가 매번 실행). 질문 3 |
| DEF-VI-003 | **nginx 오류 로그(stderr)가 쿼리 문자열이 든 요청 줄 전체를 기록한다**(`limit_req` 거절·업스트림 오류 등). `nginx.conf` 의 "쿼리 문자열·쿠키는 기록하지 않는다" 주석은 접근 로그만 해당 → 보안 주석과 실제가 다름. M2 의 OAuth 콜백(`?code=`)이 이 경로에 걸리면 코드가 로그에 남는다 | 속도 제한을 넘겨 429 가 나게 한 뒤 `docker logs <web>` → `request: "POST /api/v1/auth/session?code=…"`. 시험 `tc_vi_055`(xfail strict). 접근 로그는 안전함을 `tc_vi_054` 가 확인 | **Low**(M1 데모 API 에는 비밀 쿼리 없음. M2 전에 해결 필요) | **Open** — 설계 결정 필요 | 고치지 않음. 선택지: (a) `limit_req_log_level info` + 오류 로그 `warn` 으로 속도 제한 거절은 기록하지 않기(업스트림 오류 줄은 남음), (b) 콜백을 POST/프래그먼트로 설계, (c) 수용하고 주석 정정. 질문 2 |
| DEF-VI-004 | nginx 가 시작할 때마다 `[warn] duplicate MIME type "text/html"` 를 낸다 — `location /` 의 `gzip_types` 에 기본 포함 형식인 `text/html` 을 또 적음 | `docker logs <web>` 첫 줄, `nginx -t` 경고. 시험 `tc_vi_056` | Low | **Fixed** | `web/docker/nginx/nginx.conf` 123줄에서 ` text/html` 한 단어 제거(설정 파일 1개·1줄, 동작 불변: HTML 은 `gzip on` 이면 원래 압축됨, 시험이 `Content-Encoding: gzip` 확인). 회귀 시험 TC-VI-056 + 변이 M112(되돌리면 잡힘). 이미지를 다시 빌드·재기동해 경고가 사라진 것까지 실측. **사소한 오탈자 기준(동작·로직·인터페이스 불변, 파일 1개·변경 1줄) 충족** |

- 결함 4건 중 1건 Fixed, 3건 Open(Medium 1, Low 2). 관찰 사항(결함으로 분류하지 않은 것)은 부록 B.
- 구현자의 자체 시험이 놓친 것: DEF-VI-001(구현자는 설계 편차로 기록만 하고 시험하지 않음), 002, 003, 004 — 모두 이번 독립 시험에서 처음 발견.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트: `.harness-tmp/vi/` 전체(심사자 전용 dockerd 데이터 루트·소켓, 가상환경 `venv/`, 변이 사본 `mut/`, compose·스크립트 사본 `work/`, pwsh 7.5.4 `pwsh/`, 추적·실행 로그), 도커 자원 — 이미지 `harness-tmp-vi-{db,api,web}:local` 3개와 pull 된 베이스 이미지 4종, 컨테이너·네트워크(`harness-tmp-vi_app/_edge`, 일회용 시험용 `harness-tmp-vi-ngx*`·`-initok`·`-tool` 등)·볼륨 3종(pgdata/backups/app_secrets), `docker0` 브리지와 iptables 규칙(DOCKER 체인·MASQUERADE 10.98.0.0/24), pytest 임시 폴더 `/tmp/pytest-of-root/*/test_tc_vi_*`
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가(규칙 K 1번): [x] 예 — 예외로 도커 데몬이 만든 커널 자원(브리지·iptables)과 pytest 기본 임시 폴더(`/tmp`)가 있었고 아래에서 함께 정리함
- 정리(삭제) 완료 여부: **완료**. (1) `docker rm -f -v`·`volume rm`·`network rm`·`rmi -f` 로 컨테이너·볼륨·사용자 정의 네트워크·이미지 0개 확인 (2) pidfile 로 **내 dockerd 만** 종료(다른 에이전트 데몬은 없었음, 종료 후 dockerd 프로세스 0) (3) 남은 `docker0` 브리지 삭제, 내 iptables 규칙·체인 제거 및 FORWARD 정책 ACCEPT 복원(`ls /sys/class/net` = eth0 ifb0 ifb1 lo, `iptables -S` 규칙 없음) (4) `rm -rf .harness-tmp/vi`(다른 에이전트의 `.harness-tmp/va`·`vb` 는 건드리지 않음), `web/tests_infra/__pycache__` 삭제, `/tmp` 의 내 pytest 폴더 삭제 (5) `/proc/mounts` 에 `harness-tmp-vi` 잔여 마운트 0
- 정리 후 `git status`: **이 단위는 git 명령 금지 지시(공통 지시서 3절)에 따라 실행하지 않았다.** 대체 점검: `ls .harness-tmp` = `va vb`(타 에이전트 소유, 내 폴더 없음), `ls web/tests_infra` = `test_compose_security.py`(구현자), `test_vi_independent.py`(신규, 내 산출물). 이 단위가 저장소에 남긴 변경은 정확히 ① `web/tests_infra/test_vi_independent.py`(신규) ② `web/docker/nginx/nginx.conf` 1줄(DEF-VI-004) ③ `docs/harness/units/web-WU-INF-test.md` ④ `docs/harness/verify-log_web-WU-INF-test.md` 4개다(`web/frontend`·`web/backend` 등 다른 변경은 병렬 단위 소유)
- 병렬 실행: 다른 단위(W-BE-A `va`, W-BE-B `vb`, W-FE)의 변경분이 트리에 보일 수 있으나 소유가 다르며, "이 단위가 만든 임시 아티팩트·미추적 잔여물이 없음"을 위 점검으로 판정. 전체 트리 점검은 웨이브 종료 후 오케스트레이터가 수행
- 도중 강제 중단: [x] 있음 — 세션 한도·컨테이너 재시작으로 2회 중단. 재개 시 `.harness-tmp/vi/` 잔여물과 dockerd 상태를 먼저 점검(dockerd 는 죽어 있었고 이미지·데이터는 보존) 후 같은 옵션으로 재기동해 재사용했고, 종료 시 위 정리를 전부 수행
- 판정: Teardown 완료 확인됨(PASS 판정의 전제 충족. 최종 판정은 결함 때문에 CONDITIONAL PASS)

## 8. 리스크 및 잔존 이슈
- 이번 테스트로 커버되지 않는 알려진 리스크:
  - **Windows Docker Desktop 에서 127.0.0.1 한정 게시, 파일 권한, 비밀 파일 읽기, PowerShell 5.1 호환 — 사용자 PC 에서 README 8절 체크리스트로 확인 필요(미수행)**. 특히 Docker Desktop 은 `internal` 망·포트 게시 동작이 Linux 엔진과 다를 수 있다.
  - 브라우저 CSP 오류(화면 하얘짐) 가능성 — `style-src-attr 'unsafe-inline'` 외 인라인 요소는 헤더/HTML 수준에서만 확인
  - 이미지 취약점·SBOM·레이어 스캐너(D-11/D-05 일부) 9단계
  - 이 시험은 같은 모델이 만든 것이므로 시험 설계의 맹점이 같은 방향일 수 있음 → 변이 점검과 행동 시험(실제 컨테이너)으로 완화했지만 독립 인간 검토는 아님
- 후속 조치가 필요한 항목: DEF-VI-001~003 결정/조치, 노트 질문 1(PostgreSQL 17 ADR)·3(Node 22 유지) 사용자 확인, `traceability.md`·`decisions.md` 갱신(부록 D), 관찰 O-VI-01~09 중 필요한 것 반영

## 9. 결론 및 판정
- [ ] PASS
- [x] **CONDITIONAL PASS** — 조건: ① DEF-VI-001(Medium)을 설계 변경으로 해결하거나 사용자가 수용(Deferred + DEC-ID)할 것, ② DEF-VI-002·003(Low)을 백엔드/설계 결정에 반영하거나 수용할 것, ③ **Windows Docker Desktop·PowerShell 5.1·브라우저 CSP 는 PASS 로 세지 않은 미수행 항목**이며 사용자 PC 체크리스트로 닫을 것
- [ ] FAIL
- 근거: AC 6건 전부 시험 연결·통과(AC4 는 DEF-VI-002 주석 포함), 시험 204 passed + 1 skipped(재실행 Pass) + 3 xfailed(결함 확인용), 변이 점검 최종 회전 112/112 잡음(생존 1건은 주석 추가 대조군), 정적 검사(pyflakes·hadolint·shellcheck·yamllint·`bash -n`·pwsh 파서) 통과, Open 결함은 PASS 를 막는 Medium 1건 포함

## 10. 내부 검증 (최소 2회, `verification-log-template.md` 사용)
- 1차 검증 결과 요약(작성자 관점): AC↔시험 추적 100%, 시험 설계가 명세(D-xx)에 근거하는지, 시험 자체의 오류(내가 쓴 잘못된 기대: 환경 종속 값·권한 비트·타이밍) 12건을 고쳐 가며 전부 통과시킴. 이 과정에서 DEF-VI-001·004 가 드러남
- 2차 검증 결과 요약(심사자 관점): 변이 점검 1회전 106곳 중 4곳 생존(M26 로그 크기, M97 복원 전 목차 검사, M105 SHA 비교 반전, M109 Windows 컨테이너 모드 검사 반전) → 시험 보강 → 2회전·3회전·최종 회전 모두 생존 0(대조군 제외). 행동 시험 단독 변이(컨테이너 실가동)에서 다시 11곳이 생존해 CSP 지시자 정확 일치·소켓 접속·PUBLIC 권한 열림·경로 탈출·느린 본문·Host 접두사 시험을 추가, 최종 4건 남음(동치 2·재현 불가 1·런타임 무효 1, 부록 A)
- 3차(결함 0건 확인 대신 기록): 최종 공식 전체 실행 204 passed / 1 skipped(136, 단독 재실행 Pass) / 3 xfailed 재확인, Open 결함은 3건이며 모두 "의도적으로 고치지 않고 보고"한 항목이다
- 검증 로그 파일 경로: `docs/harness/verify-log_web-WU-INF-test.md`

## 부록 A. 변이 점검표 (격리 사본 `.harness-tmp/vi/mut/<ID>/` 에서만 적용, 원본 미수정)
- 대상 문자열은 소스에 **정확히 1곳**인지 먼저 확인(복수 곳인 경우 `nth` 로 몇 번째인지 지정: M04, M21, M22, M32, M55, M61, M106, M111). 노트의 자체 변이 9건(포트 0.0.0.0, 루트 사용자, read_only 해제, 평문 비밀, db edge 연결, server_tokens on, pg_hba trust, USER root, docker.sock)과 겹치는 것은 M01·M02·M05·M10·M12·M35·M49·M77(방식이 다른 변형) 정도이며 나머지 100여 곳은 새로 정했다
- **회전 요약**: 1회전 106곳 유효(3곳은 대상 문자열 오지정 BADTARGET 으로 제외 후 수정) → 4곳 생존 → 시험 보강 → **2회전 110/110 잡음 → 3회전 110/110 → 최종 회전 113곳 중 112곳 잡음, 생존 1곳은 대조군 M114(주석 한 줄 추가 = 동작 동일해야 하므로 생존이 정상)**. 마지막 회전 놓침 0
- "정적/행동" 열: 정적 = 파싱형 시험이 잡음, 행동 = 실제 컨테이너(nginx 하네스·새 PostgreSQL)에 변이 설정을 얹어 시험이 잡음. 행동 열은 nginx·DB 파일 변이 53곳만 해당(정적 단계를 건너뛰고 행동 시험만 돌린 결과) — 48곳 잡음
- **행동 시험만으로는 못 잡은 5곳**: M60(`/nginx-health` 의 보안 헤더 include 제거 — 서버 수준 `add_header` 가 상속되므로 동작 동일, **동치 변이**), M66(`default_server` 제거 — server 블록이 하나뿐이라 **동치**), M76(pg_hba 사설 대역을 0.0.0.0/0 으로 — 비사설 출발지 주소를 컨테이너 실험에서 만들 수 없어 **재현 불가**, 정적 시험 TC-VI-021 이 허용 CIDR 목록을 고정해 잡음), M113(오류 로그 debug — 공식 이미지의 일반 nginx 바이너리는 debug 빌드가 아니라 **런타임 무효**, 정적 시험이 잡음), M114(대조군)
| 변이 | 파일 | 내용 | 최종 회전 결과(정적 단계, 처음 실패한 시험) | 행동 시험 단독 |
|---|---|---|---|---|
| M01 | `compose.yaml` | web 게시 주소 0.0.0.0 | 잡음 (static, TC-VI-001) | (해당 없음: 행동 시험 대상 아님) |
| M02 | `compose.yaml` | db 루트 실행 | 잡음 (static, TC-VI-002) | (해당 없음: 행동 시험 대상 아님) |
| M03 | `compose.yaml` | web 루트 실행 | 잡음 (static, TC-VI-002) | (해당 없음: 행동 시험 대상 아님) |
| M04 | `compose.yaml` | api 루트 실행(두 번째 10001) | 잡음 (static, TC-VI-002) | (해당 없음: 행동 시험 대상 아님) |
| M05 | `compose.yaml` | 읽기 전용 루트 해제(앵커) | 잡음 (static, TC-VI-003) | (해당 없음: 행동 시험 대상 아님) |
| M06 | `compose.yaml` | cap 일부만 제거 | 잡음 (static, TC-VI-003) | (해당 없음: 행동 시험 대상 아님) |
| M07 | `compose.yaml` | no-new-privileges 해제 | 잡음 (static, TC-VI-003) | (해당 없음: 행동 시험 대상 아님) |
| M08 | `compose.yaml` | init 끔 | 잡음 (static, TC-VI-003) | (해당 없음: 행동 시험 대상 아님) |
| M09 | `compose.yaml` | app 네트워크 internal 해제 | 잡음 (static, TC-VI-005) | (해당 없음: 행동 시험 대상 아님) |
| M10 | `compose.yaml` | db 를 edge 에 연결 | 잡음 (static, TC-VI-005) | (해당 없음: 행동 시험 대상 아님) |
| M100 | `scripts/reset-demo.ps1` | 오답 문구 종료코드 0 | 잡음 (static, TC-VI-028) | (해당 없음: 행동 시험 대상 아님) |
| M101 | `scripts/reset-demo.ps1` | 사전 백업 조건 반전 | 잡음 (static, TC-VI-028) | (해당 없음: 행동 시험 대상 아님) |
| M102 | `scripts/stop.ps1` | stop 이 볼륨 삭제 | 잡음 (static, TC-VI-027) | (해당 없음: 행동 시험 대상 아님) |
| M103 | `scripts/status.ps1` | status 게시 주소 검사 느슨 | 잡음 (static, TC-VI-031) | (해당 없음: 행동 시험 대상 아님) |
| M104 | `scripts/backup.ps1` | 백업 크기 검증 반전 | 잡음 (static, TC-VI-030) | (해당 없음: 행동 시험 대상 아님) |
| M105 | `scripts/restore.ps1` | SHA 검증 반전 | 잡음 (static, TC-VI-029) | (해당 없음: 행동 시험 대상 아님) |
| M106 | `scripts/_common.ps1` | 기존 비밀 파일 덮어씀(쓰기 루프) | 잡음 (static, TC-VI-032) | (해당 없음: 행동 시험 대상 아님) |
| M107 | `scripts/start.ps1` | start 가 비밀 준비 생략 | 잡음 (static, TC-VI-033) | (해당 없음: 행동 시험 대상 아님) |
| M109 | `scripts/_common.ps1` | Windows 컨테이너 모드 검사 반전 | 잡음 (static, TC-VI-032) | (해당 없음: 행동 시험 대상 아님) |
| M11 | `compose.yaml` | 소유자 비밀번호 평문 환경변수 | 잡음 (static, TC-VI-008) | (해당 없음: 행동 시험 대상 아님) |
| M110 | `README.md` | README 데이터 삭제 경고 제거 | 잡음 (static, TC-VI-035) | (해당 없음: 행동 시험 대상 아님) |
| M111 | `scripts/_common.ps1` | 비밀 파일 존재 판정 오류(사전 검사 루프) | 잡음 (static, TC-VI-032) | (해당 없음: 행동 시험 대상 아님) |
| M112 | `docker/nginx/nginx.conf` | DEF-VI-004 회귀: gzip_types text/html 중복 | 잡음 (docker-nginx, TC-VI-056) | TC-VI-056 |
| M113 | `docker/nginx/nginx.conf` | 오류 로그 debug 수준 | 잡음 (static, TC-VI-019) | 생존 |
| M114 | `docker/nginx/nginx.conf` | (동치 대조군: 주석 추가) | **생존** (docker-nginx, -) | 생존 |
| M12 | `compose.yaml` | 슈퍼유저 비밀번호 평문 | 잡음 (static, TC-VI-008) | (해당 없음: 행동 시험 대상 아님) |
| M13 | `compose.yaml` | API 문서 켬 | 잡음 (static, TC-VI-012) | (해당 없음: 행동 시험 대상 아님) |
| M14 | `compose.yaml` | 허용 Host 와일드카드 | 잡음 (static, TC-VI-012) | (해당 없음: 행동 시험 대상 아님) |
| M15 | `compose.yaml` | migrate 가 db healthy 를 기다리지 않음 | 잡음 (static, TC-VI-009) | (해당 없음: 행동 시험 대상 아님) |
| M16 | `compose.yaml` | web 이 api healthy 를 기다리지 않음 | 잡음 (static, TC-VI-009) | (해당 없음: 행동 시험 대상 아님) |
| M17 | `compose.yaml` | db pids 상한 사실상 해제 | 잡음 (static, TC-VI-007) | (해당 없음: 행동 시험 대상 아님) |
| M18 | `compose.yaml` | db 메모리 상한 8G | 잡음 (static, TC-VI-007) | (해당 없음: 행동 시험 대상 아님) |
| M19 | `compose.yaml` | worker 에 docker.sock 마운트 | 잡음 (static, TC-VI-004) | (해당 없음: 행동 시험 대상 아님) |
| M20 | `compose.yaml` | web tmpfs noexec 제거 | 잡음 (static, TC-VI-004) | (해당 없음: 행동 시험 대상 아님) |
| M21 | `compose.yaml` | db 재시작 정책 제거 | 잡음 (static, TC-VI-009) | (해당 없음: 행동 시험 대상 아님) |
| M22 | `compose.yaml` | db 종료 유예 2초 | 잡음 (static, TC-VI-009) | (해당 없음: 행동 시험 대상 아님) |
| M23 | `compose.yaml` | SQL 전체 로깅 | 잡음 (static, TC-VI-011) | (해당 없음: 행동 시험 대상 아님) |
| M24 | `compose.yaml` | md5 암호화 | 잡음 (static, TC-VI-011) | (해당 없음: 행동 시험 대상 아님) |
| M25 | `compose.yaml` | 전용 pg_hba 미적용 | 잡음 (static, TC-VI-011) | (해당 없음: 행동 시험 대상 아님) |
| M26 | `compose.yaml` | 로그 회전 크기 10g | 잡음 (static, TC-VI-010) | (해당 없음: 행동 시험 대상 아님) |
| M27 | `compose.yaml` | db 에 호스트 폴더 바인드 | 잡음 (static, TC-VI-004) | (해당 없음: 행동 시험 대상 아님) |
| M28 | `compose.yaml` | 기본 compose 에 egress 네트워크 추가 | 잡음 (static, TC-VI-005) | (해당 없음: 행동 시험 대상 아님) |
| M29 | `compose.online.yaml` | online 덮어쓰기에 db 를 egress 연결 | 잡음 (static, TC-VI-006) | (해당 없음: 행동 시험 대상 아님) |
| M30 | `compose.yaml` | uvicorn --reload | 잡음 (static, TC-VI-012) | (해당 없음: 행동 시험 대상 아님) |
| M31 | `compose.yaml` | api 가 소유자 비밀도 받음 | 잡음 (static, TC-VI-008) | (해당 없음: 행동 시험 대상 아님) |
| M32 | `compose.yaml` | worker 그룹 미지정 user | 잡음 (static, TC-VI-002) | (해당 없음: 행동 시험 대상 아님) |
| M33 | `docker/api.Dockerfile` | python 다이제스트 제거 | 잡음 (static, TC-VI-013) | (해당 없음: 행동 시험 대상 아님) |
| M34 | `docker/api.Dockerfile` | requirements.txt 해시 검증 제거 | 잡음 (static, TC-VI-015) | (해당 없음: 행동 시험 대상 아님) |
| M35 | `docker/api.Dockerfile` | api 이미지 root | 잡음 (static, TC-VI-014) | (해당 없음: 행동 시험 대상 아님) |
| M36 | `docker/web.Dockerfile` | web 이미지 root | 잡음 (static, TC-VI-014) | (해당 없음: 행동 시험 대상 아님) |
| M37 | `docker/web.Dockerfile` | 소스맵 삭제 제거 | 잡음 (static, TC-VI-016) | (해당 없음: 행동 시험 대상 아님) |
| M38 | `docker/web.Dockerfile` | npm 설치 스크립트 허용 | 잡음 (static, TC-VI-016) | (해당 없음: 행동 시험 대상 아님) |
| M39 | `docker/db.Dockerfile` | db 이미지 root | 잡음 (static, TC-VI-014) | (해당 없음: 행동 시험 대상 아님) |
| M40 | `docker/web.Dockerfile` | nginx 이미지 latest | 잡음 (static, TC-VI-013) | (해당 없음: 행동 시험 대상 아님) |
| M41 | `docker/web.Dockerfile` | Dockerfile ADD URL | 잡음 (static, TC-VI-014) | (해당 없음: 행동 시험 대상 아님) |
| M42 | `docker/requirements-youtube-title.txt` | 해시 잠금 제거(dotenv) | 잡음 (static, TC-VI-017) | (해당 없음: 행동 시험 대상 아님) |
| M43 | `docker/api.Dockerfile` | 잠금 없는 pip install 추가 | 잡음 (static, TC-VI-015) | (해당 없음: 행동 시험 대상 아님) |
| M44 | `docker/db.Dockerfile` | ytweb-db 777 | 잡음 (static, TC-VI-024) | (해당 없음: 행동 시험 대상 아님) |
| M45 | `.dockerignore` | .dockerignore secrets/ 제거 | 잡음 (static, TC-VI-018) | (해당 없음: 행동 시험 대상 아님) |
| M46 | `.dockerignore` | .dockerignore .env 제거 | 잡음 (static, TC-VI-018) | (해당 없음: 행동 시험 대상 아님) |
| M47 | `.dockerignore` | .dockerignore tests 제거 | 잡음 (static, TC-VI-018) | (해당 없음: 행동 시험 대상 아님) |
| M48 | `.gitignore` | .gitignore *.dump 제거 | 잡음 (static, TC-VI-018) | (해당 없음: 행동 시험 대상 아님) |
| M49 | `docker/nginx/nginx.conf` | 서버 버전 노출 | 잡음 (static, TC-VI-019) | TC-VI-042 |
| M50 | `docker/nginx/nginx.conf` | Host 불허를 200 으로 | 잡음 (static, TC-VI-019) | TC-VI-040 |
| M51 | `docker/nginx/nginx.conf` | Host 정규식 전체 허용 | 잡음 (static, TC-VI-019) | TC-VI-040 |
| M52 | `docker/nginx/nginx.conf` | 본문 10m | 잡음 (static, TC-VI-019) | TC-VI-043 |
| M53 | `docker/nginx/nginx.conf` | 인증 속도 제한 완화 | 잡음 (static, TC-VI-019) | TC-VI-047 |
| M54 | `docker/nginx/nginx.conf` | 인증 속도 제한 제거 | 잡음 (static, TC-VI-020) | TC-VI-047 |
| M55 | `docker/nginx/nginx.conf` | / 에 POST 허용 | 잡음 (static, TC-VI-020) | TC-VI-041 |
| M56 | `docker/nginx/nginx.conf` | 세션에 PUT 허용 | 잡음 (docker-nginx, TC-VI-041) | TC-VI-041 |
| M57 | `docker/nginx/nginx.conf` | 제한 응답 503 | 잡음 (static, TC-VI-019) | TC-VI-047 |
| M58 | `docker/nginx/nginx.conf` | 헤더 버퍼 64k | 잡음 (static, TC-VI-019) | TC-VI-043 |
| M59 | `docker/nginx/nginx.conf` | 헤더 타임아웃 300s | 잡음 (static, TC-VI-019) | TC-VI-052 |
| M60 | `docker/nginx/nginx.conf` | nginx-health 보안 헤더 누락 | 잡음 (static, TC-VI-020) | 생존 |
| M61 | `docker/nginx/nginx.conf` | /api/ 캐시 허용 | 잡음 (static, TC-VI-020) | TC-VI-045 |
| M62 | `docker/nginx/nginx.conf` | 허용 Host 추가 | 잡음 (static, TC-VI-019) | TC-VI-040 |
| M63 | `docker/nginx/nginx.conf` | 쿼리 문자열 로깅 | 잡음 (static, TC-VI-019) | TC-VI-054 |
| M64 | `docker/nginx/nginx.conf` | /api/ 속도 제한 제거 | 잡음 (static, TC-VI-020) | TC-VI-048 |
| M65 | `docker/nginx/nginx.conf` | 본문 타임아웃 1h | 잡음 (static, TC-VI-019) | TC-VI-053 |
| M66 | `docker/nginx/nginx.conf` | default_server 제거(동치 후보) | 잡음 (static, TC-VI-019) | 생존 |
| M67 | `docker/nginx/security-headers.conf` | always 누락 | 잡음 (static, TC-VI-020) | TC-VI-042 |
| M68 | `docker/nginx/security-headers.conf` | CSP object-src 제거 | 잡음 (static, TC-VI-020) | TC-VI-042 |
| M69 | `docker/nginx/security-headers.conf` | CSP unsafe-inline | 잡음 (static, TC-VI-020) | TC-VI-042 |
| M70 | `docker/nginx/security-headers.conf` | frame-ancestors 허용 | 잡음 (static, TC-VI-020) | TC-VI-042 |
| M71 | `docker/nginx/security-headers.conf` | nosniff 변경 | 잡음 (static, TC-VI-020) | TC-VI-042 |
| M72 | `docker/nginx/proxy.conf` | 백엔드 CSP 중복 노출 | 잡음 (static, TC-VI-020) | TC-VI-042 |
| M73 | `docker/nginx/proxy.conf` | XFF 신뢰 | 잡음 (static, TC-VI-020) | TC-VI-045 |
| M74 | `docker/nginx/proxy.conf` | X-Powered-By 노출 | 잡음 (static, TC-VI-020) | TC-VI-045 |
| M75 | `docker/db/pg_hba.conf` | 마지막 reject 를 전체 허용 | 잡음 (static, TC-VI-021) | TC-VI-063 |
| M76 | `docker/db/pg_hba.conf` | 전 세계 허용 | 잡음 (static, TC-VI-021) | 생존 |
| M77 | `docker/db/pg_hba.conf` | 슈퍼유저 소켓 trust | 잡음 (static, TC-VI-021) | TC-VI-063 |
| M78 | `docker/db/pg_hba.conf` | 슈퍼유저 사설망 허용 | 잡음 (static, TC-VI-021) | TC-VI-060 |
| M79 | `docker/db/pg_hba.conf` | 앱 계정 전체 DB 허용 | 잡음 (static, TC-VI-021) | TC-VI-063 |
| M80 | `docker/db/init/01-roles.sh` | 앱 CREATEDB | 잡음 (static, TC-VI-022) | TC-VI-060 |
| M81 | `docker/db/init/01-roles.sh` | 소유자 최소 길이 8 | 잡음 (static, TC-VI-022) | TC-VI-061 |
| M82 | `docker/db/init/01-roles.sh` | 동일 비밀번호 검사 무력화 | 잡음 (static, TC-VI-022) | TC-VI-061 |
| M83 | `docker/db/init/01-roles.sh` | PUBLIC 접속 권한 유지 | 잡음 (static, TC-VI-022) | TC-VI-060 |
| M84 | `docker/db/init/01-roles.sh` | 앱 연결 수 무제한 | 잡음 (static, TC-VI-022) | TC-VI-060 |
| M85 | `docker/db/init/01-roles.sh` | 초기화 표식 미생성 | 잡음 (static, TC-VI-022) | TC-VI-060 |
| M86 | `docker/db/init/01-roles.sh` | 앱 시간대 미설정 | 잡음 (docker-db, TC-VI-060) | TC-VI-060 |
| M87 | `docker/db/schema-grants.sql` | public 스키마 PUBLIC 권한 유지 | 잡음 (static, TC-VI-023) | TC-VI-060 |
| M88 | `docker/db/schema-grants.sql` | 앱에 TRUNCATE 등 전체 권한 | 잡음 (static, TC-VI-023) | TC-VI-060 |
| M89 | `docker/db/schema-grants.sql` | 앱에 스키마 CREATE | 잡음 (static, TC-VI-023) | TC-VI-060 |
| M90 | `docker/db/audit-guard.sql` | audit 회수 범위 축소 | 잡음 (static, TC-VI-023) | TC-VI-060 |
| M91 | `docker/db/audit-guard.sql` | 회수 실패를 무시 | 잡음 (static, TC-VI-023) | TC-VI-060 |
| M92 | `docker/db/bin/ytweb-db` | 복원 단일 트랜잭션 제거 | 잡음 (static, TC-VI-025) | TC-VI-064 |
| M93 | `docker/db/bin/ytweb-db` | 복원 후 audit 가드 제거 | 잡음 (static, TC-VI-025) | TC-VI-064 |
| M94 | `docker/db/bin/ytweb-db` | 백업 이름에 / 허용 | 잡음 (static, TC-VI-025) | TC-VI-064 |
| M95 | `docker/db/bin/ytweb-db` | 덮어쓰기 허용 | 잡음 (static, TC-VI-026) | TC-VI-064 |
| M96 | `docker/db/bin/ytweb-db` | 백업 파일 권한 개방 | 잡음 (static, TC-VI-025) | TC-VI-064 |
| M97 | `docker/db/bin/ytweb-db` | 복원 전 목차 검사 제거 | 잡음 (docker-db, TC-VI-064) | TC-VI-064 |
| M98 | `docker/db/bin/ytweb-db` | --clean 제거(복원 시 기존 객체 충돌) | 잡음 (static, TC-VI-025) | TC-VI-064 |
| M99 | `scripts/reset-demo.ps1` | 볼륨 삭제 확인 문구 약화 | 잡음 (static, TC-VI-028) | (해당 없음: 행동 시험 대상 아님) |

## 부록 B. 관찰 사항 (결함으로 분류하지 않았으나 알아야 할 것)
| ID | 관찰 | 영향 | 근거 |
|---|---|---|---|
| O-VI-01 | `/api/healthz`·`/api/readyz` location 에는 `limit_except` 가 없어 POST 등도 백엔드로 전달됨(백엔드가 거부) | 낮음 | TC-VI-046 |
| O-VI-02 | `api` 컨테이너는 SIGTERM 으로 정상(우아하게) 종료한 뒤 종료 코드가 **143**(uvicorn 0.54 가 종료 후 신호를 다시 던짐). 노트의 "종료 시 exit 0 확인"은 api 에서 재현되지 않음 | 없음(데이터 유실 없음, `Finished server process` 로그 확인, `restart: unless-stopped` 는 수동 정지 후 재시작하지 않음) | TC-VI-122 |
| O-VI-03 | `restore.ps1 -SkipSafetyBackup` 로 실행하고 복원이 실패해도 "복원 전 자동 백업(pre-restore-*.dump)이 있습니다" 안내가 출력됨 | 안내 문구 오류 | restore.ps1 코드 + 쓰레기 덤프 실행 로그 |
| O-VI-04 | `restore.ps1` 은 웹·API·워커를 **먼저 멈춘 뒤** 컨테이너 안에서 덤프를 검증한다 → 손상 파일을 고르면 잠깐 서비스가 내려갔다 올라옴(자동 복구 확인) | 낮음(가용성) | TC-VI-131 |
| O-VI-05 | Linux 호스트에서 `web/secrets` 파일이 0600(root 소유)이면 비루트 컨테이너(db 999 등)가 못 읽어 db 가 기동하지 못한다. Windows 에서는 해당 없음, `start.ps1` 이 만든 파일은 .NET 기본 권한(0644)으로 읽힘 | 낮음(사용자는 Windows) | 직접 겪음 |
| O-VI-06 | api 이미지에 `requirements-dev.*`·`alembic.ini`·`pyproject.toml`·`pip` 이 남아 있다(소스맵·테스트 파일은 없음). DEC-041 ⑤ 계열 | 낮음 | TC-VI-108 + `find /app` |
| O-VI-07 | 세션 발급 속도 제한(분당 10, burst 10)은 출발지 IP 기준이라 Docker Desktop 에서는 사실상 전역 제한 — 연속 새로고침/재로그인이 11번 넘으면 잠시 429 | 낮음 | TC-VI-047 |
| O-VI-08 | `status.ps1` 은 8080 에 리스너가 아예 없어도 "리스너는 루프백뿐" 을 [완료] 로 표시(다른 점검이 응답 없음을 잡아줌) | 낮음 | 원본 스크립트로 18081 스택을 점검했을 때 |
| O-VI-09 | 허용 Host 가 `…:8080` 으로 고정이라 호스트 포트를 바꾸면(예: 이번 18081) nginx·백엔드가 거부한다 — 의도된 설계지만 포트 변경 안내가 README 에 없음 | 문서 | TC-VI-040 |
| O-VI-10 | 백업 파일은 소유자 전용(0600, root 소유)으로 만들어지고 `.sha256` 은 0644 | 양호 | TC-VI-064 |

## 부록 C. 재실행 방법
```
# 1) 정적 42건 (도커 불필요)
python -m pytest web/tests_infra/test_vi_independent.py -q
# 2) + 일회용 컨테이너 시험 (심사자 전용 dockerd + 이미지 harness-tmp-vi-{api,web,db}:local 필요)
DOCKER_HOST=unix://<소켓> VI_DOCKER=1 python -m pytest web/tests_infra/test_vi_independent.py -q
# 3) + 실가동 스택/스크립트 (compose 사본 폴더 VI_RUN/web/{compose.yaml,scripts_p,secrets}, pwsh 필요; 마지막 시험이 볼륨을 지움)
DOCKER_HOST=… VI_DOCKER=1 VI_LIVE=1 VI_RUN=<사본>  VI_PWSH=<pwsh> python -m pytest web/tests_infra/test_vi_independent.py
# 변이 점검: VI_WEB_ROOT=<변이 사본>/web 를 지정해 위 1)·2)를 실행(저장소 web 은 수정하지 않음)
# 구현자 시험: python -m pytest web/tests_infra/test_compose_security.py
```
환경변수: `VI_WEB_ROOT`, `DOCKER_HOST`, `VI_PROJECT`(기본 harness-tmp-vi), `VI_PORT`(18081), `VI_RUN`, `VI_PWSH`. 시험 파일: `web/tests_infra/test_vi_independent.py`(신규 1개).

## 부록 D. 공유 문서 갱신 요청 (병렬 웨이브 규칙 — 직접 수정하지 않음)
- `traceability.md` 단위테스트 컬럼: W-001, W-016, D-01~D-10, D-12~D-14, D-07a, D-07b, S-W01, S-W04(인프라 부분) → `web-WU-INF-test.md` 의 TC-VI 범위(위 4-2 표). D-11 은 "미수행(9단계)", D-10 은 "부분(DEF-VI-001 Open)", D-01 프로필 부분은 노트 선언대로 "부분"
- `decisions.md` 제안: (1) DEF-VI-001 처리(3망 분리 vs 수용), (2) DEF-VI-003 오류 로그 쿼리 문자열 수용 여부, (3) 6단계 독립 검증용 도커 데몬 기동 방식(대역 분리·소켓 분리) 기록
- `STATE.md`: W-INF 6단계 독립 검증 = CONDITIONAL PASS

## 부록 E. 사용자 질문 목록 (규칙 A)
1. **DEF-VI-001**: web 컨테이너가 인터넷과 db 포트에 닿는 문제를 (a) 망을 3개로 나눠 db 접근만 막고(외부 egress 는 남음) 진행할지, (b) 지금 구성을 수용할지(Deferred + DEC), (c) egress 도 막는 다른 방법을 찾을지 결정해 주세요.
2. **DEF-VI-003**: nginx 오류 로그에 쿼리 문자열이 남는 것을 M1 에서는 수용하고 M2 설계(OAuth 콜백)에서 해결해도 되나요, 아니면 지금 `limit_req_log_level` 조정까지 하나요?
3. **DEF-VI-002**: `alembic_version` 권한 회수를 백엔드 담당(W-BE-A)에게 요청해도 되나요?
4. 노트 질문 1·3 재확인: PostgreSQL 17 선택(ADR 필요), Node 22 유지(유지보수 ~2027-04) 여부
5. api 종료 코드 143(O-VI-02)을 수용해도 되나요(노트의 "exit 0" 문구만 정정)?
6. D-01 의 `dev/test` 프로필 미구현을 수용하나요(테스트는 `YTWEB_PROJECT` 분리로 대체됨)?
