# 테스트 결과서 — W-FIX-INF 인프라 수정 단위 + M2 compose.online 덧씌우기 (6단계 독립 검증)

> 한 줄 결론: **CONDITIONAL PASS** — 핵심 수정(DEC-047 루트 /healthz·/readyz 404, DEF-7-001, DEF-7-002)과 하드닝·격리·비밀·compose.online 범위 제한은 실제 스택에서 모두 합격. 열린 결함은 Low 3건(DEF-VIF-001~003)이며 소스·설정은 고치지 않고 보고만 한다. 정적 시험 61건(58 합격 + 알려진 결함 증명 3 xfail), 실가동 시험 29건(28 합격 + 결함 증명 1 xfail), 변이 27/27 검출.

## 1. 개요
- 테스트 대상: 작업 단위 **W-FIX-INF**(`web/docker/nginx/{nginx.conf,proxy.conf,security-headers*.conf}`, `web/docker/db/{bin/ytweb-db,audit-guard.sql,schema-grants.sql}`, `web/compose.yaml`) + M2에서 추가된 `web/compose.online.yaml`, `web/scripts/_common.ps1`(구글 비밀 파일이 있으면 오버레이 적용)
- 테스트 유형: 단위(인프라 수정 단위의 독립 재검증; 정적 + 실제 스택 실측 + 변이 점검). 06·07 병합 조건 미적용(Standard 등급, 독립 검증 호출)
- 적용 Tier: Standard로 간주(규칙 B 원문: 최소 2회)
- 적용 속도 트랙: L3(표기 없음)
- 병렬 실행 정보: 단독 실행(이 호출 외에 `harness-tmp-int`, `harness-tmp-sec`, `harness-tmp-vinf*` 스택이 도커 호스트에 남아 있었으나 이 단위는 접두사 `harness-tmp-v2`·포트 18081만 사용)
- 테스트 목적: DEC-045~048의 결정이 설정에서 실제로 지켜지는지, 수정으로 닫았다는 결함(DEF-7-001·006·007, DEF-7-002)이 실행 중인 컨테이너에서 재현되지 않는지, compose.online 덧씌우기가 구글 비밀 파일 외에 새 포트·권한을 늘리지 않는지 독립적으로 증명
- 관련 산출물: `docs/harness/decisions.md`(DEC-045~048), `docs/harness/feature-web-m1-integration-test.md`, `docs/harness/security-web-m1-test.md`, `docs/harness/units/web-WU-INF-test.md`, `web/compose.yaml`, `web/compose.online.yaml`, `web/docker/nginx/*`, `web/scripts/_common.ps1`
- 테스트 수행자(에이전트): 6단계 독립 검증자(구현자 아님)
- 테스트 일시: 2026-10-11 (UTC 16:2x ~ 17:0x)
- 신규 시험 파일(이 단위 소유): `web/tests_infra/test_vinf2_static.py`(TC-VIF-001~061), `web/tests_infra/test_vinf2_live.py`(TC-VIF-100~199). 기존 구현자·이전 검증 시험을 복사하지 않고 명세에서 새로 작성

## 2. 테스트 범위 및 제외 범위
- 범위(In-Scope)
  1. compose 정적: 하드닝 4종(비root, read_only, cap_drop ALL, no-new-privileges), 호스트 탈출 옵션 부재, 포트 게시, 네트워크 3분리와 internal, 비밀 파일 분배·평문 부재, 쓰기 표면, 자원 한도, 헬스체크·기동 순서
  2. compose.online 정적+병합: 키 허용 목록(권한·포트·마운트 추가 불가), 병합 결과 비교, egress 소속, google_client 비밀 범위, `docker compose config` 교차 검증
  3. nginx 정적: 루트 /healthz·/readyz 404 정확 일치, /api/* 프록시 경로, 단일 업스트림, 보안 헤더 스니펫·상속, Cache-Control 1회, 프록시 중복 헤더 숨김, Host 허용 목록, 로그 형식(쿼리·쿠키 없음), 메서드·크기 제한
  4. PowerShell 정적: BOM, 괄호 짝, Invoke-Compose 오버레이 로직, compose 우회 호출 부재, 상수·서비스·비밀 이름 일치, 비밀 생성 정책, 위험 구문 부재, 확인 문구, 백업 파일명 정규식 일치, status.ps1 프로브 경로
  5. 문서 일관성(DEC-047): API.md·WEB_DESIGN.md·README·DESIGN.md
  6. 실제 스택(`harness-tmp-v2`, 127.0.0.1:18081): 전 컨테이너 기동·건강, 런타임 하드닝(/proc 실측), 읽기 전용 루트, 포트 바인딩·리스너, 네트워크 internal·소속, 경로·헤더(정상·오류·429·414·400), Host 차단, 쿼리·쿠키 비기록, web→db 불가/api→db 가능(양성 대조), 내부 서비스 외부 통신 불가, 비밀 평문 부재(inspect·로그·프로세스 환경·이미지 이력·이미지 tar 바이트 검색), 재시작·down/up 후 데이터 유지, DB 재시작 복구, 백업·복원(SQL 단계)과 alembic_version 권한, 오버레이 실가동(가짜 구글 파일)과 원복
  7. 변이 점검 27곳
- 제외 범위(Out-of-Scope)와 사유 — **모두 PASS로 세지 않은 미수행 항목**
  1. **`backup.ps1`/`restore.ps1`/`start.ps1`을 pwsh로 실제 실행**: 지시에 따라 동등한 `docker compose exec ... ytweb-db dump|list|restore` 단계를 같은 순서로 수행했다(`compose cp`·SHA-256 파일·Windows ACL 부분은 미검증, 잔여 위험: 스크립트 자체의 호스트 파일 처리 오류). 지시문은 pwsh 없음이라 했으나 다른 에이전트의 임시 폴더(`.harness-tmp/int/pwsh/pwsh`, 읽기 전용 사용)에 pwsh 7.5가 있어 **구문 파서(AST)로 10개 스크립트 구문 오류 0건**과 `Invoke-Compose` 오버레이 동작(TC-VIF-070)만 추가로 확인했다
  2. **Windows PowerShell 5.1·Docker Desktop(WSL2)·Windows 경로 구분자 실동작**: 이 환경은 Linux 엔진. 파일명 검사 `secrets\google_client.json`의 Windows 의미는 역슬래시 이름 파일로 에뮬레이션했다. 잔여 위험: 사용자 PC 첫 실행(10단계에서 확인)
  3. **실제 구글 OAuth 통신**: 가짜 구글 클라이언트 파일로 마운트·망·권한만 확인(구글 호출 코드 시험은 백엔드 단위 범위)
  4. **저장소 Dockerfile을 그대로 빌드**: 이 클라우드의 TLS 가로채기 프록시 때문에 pip/npm 단계가 실패한다(1회차 `compose build` 실패 로그 확인). `api`·`web` 빌더 단계에 CA 인증서만 추가한 사본 Dockerfile(`.harness-tmp/v2/df/`, 삭제됨)로 빌드했고 최종 이미지 환경변수에 CA 변수가 남지 않음을 TC-VIF-122에서 확인했다. 잔여 위험: 원본 Dockerfile의 빌드 성공 자체는 이 환경에서 미검증(이전 검증 보고서와 동일한 제약)
  5. **기존 시험 중 실가동 게이트(VFI_LIVE/VI_LIVE/IT_*) 331건**: 환경변수·전용 스택이 달라 실행하지 않음(건너뜀 331건을 PASS로 세지 않음)
  6. 이미지 취약점 스캔·SBOM: 9단계 범위
  7. 화면(브라우저) 동작: 프런트 단위 범위

## 3. 테스트 환경
- 실행 환경: Linux 6.18, Docker Engine 29.8.2, Compose v5.6.0, Python 3.13 + pytest + PyYAML(httpx 없음 → 표준 `http.client`로 직접 요청), pwsh 7.5(구문 검사 한정)
- 스택: `docker compose -p harness-tmp-v2 -f web/compose.yaml -f .harness-tmp/v2/override.yaml`(override는 web 포트를 `127.0.0.1:18081:8080`으로만 교체, 원본 파일 무수정). 이미지 `harness-tmp-v2-{db,api,web}:local`(현재 소스 `cd1579f` 이후 작업 트리로 빌드). nginx는 Host `127.0.0.1:8080`만 허용하므로 요청에 Host 헤더를 직접 지정
- 테스트 데이터: `web/secrets/` 안에 임의 생성한 비밀 파일 3개(48자 16진수, 시험 후 삭제)와 가짜 `google_client.json`(시험 중에만 존재). 데모 모드 영상 200건(앱 자체 생성)
- 전제 조건: `docker info` 응답, dockerd 이미 기동. 시작은 `up -d` 후 상태 폴링(고정 sleep 없음; 새 스택에서 건강 확인까지 약 0.2~4.4초)

## 4. 테스트 케이스 및 결과
> 합격/불합격 표기: PASS / FAIL(1회차 실패는 비고에 원인 분류) / XFAIL(열린 결함을 증명하는 시험 — 결함이 고쳐지면 XPASS로 실패해 표식 제거를 알린다). 요구 근거 열은 비고에 적었다.

### 4-A. 정적 시험 (`test_vinf2_static.py`, 최종 실행 58 PASS + 3 XFAIL)
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-VIF-001(×5) | 서비스별 하드닝 플래그 | compose.yaml | YAML 파싱 후 read_only/cap_drop/cap_add/security_opt/privileged | 5개 모두 true/[ALL]/없음/no-new-privileges:true/false | 일치 | PASS | NFR 보안, DEC-045 |
| TC-VIF-002(×5) | 비root 숫자 uid:gid | 〃 | user 값 검사 | db 999, api·worker·migrate 10001, web 101, 0 아님 | 일치 | PASS | |
| TC-VIF-003 | 호스트 탈출 옵션 부재 | 〃 | network_mode/pid/ipc/devices/sysctls/extra_hosts/dns 키, docker.sock, 호스트 경로 마운트 | 없음, 마운트는 이름 붙은 볼륨만 | 일치 | PASS | |
| TC-VIF-004 | 호스트 포트는 127.0.0.1:8080 하나 | 〃 | ports 수집 | web만, `127.0.0.1:8080:8080`, 0.0.0.0/IP 없는 게시 행 없음 | 일치 | PASS | DEC-045 |
| TC-VIF-005 | 네트워크 정의 | 〃 | networks 최상위 | front·back internal true, edge만 비-internal, external 없음 | 일치 | PASS | DEF-VI-001 |
| TC-VIF-006 | 소속 행렬 | 〃 | 서비스별 networks | db/migrate/worker=back, api=front+back, web=front+edge, web∩db=∅, edge는 web만 | 일치 | PASS | |
| TC-VIF-007 | 비밀 파일·분배 | 〃 | secrets 최상위·서비스별 | 3개 `./secrets/<이름>`, db 3개/migrate owner/api·worker app/web 없음 | 일치 | PASS | 최소 권한 |
| TC-VIF-008 | 환경변수 평문 비밀 부재 | 〃 | PASS/SECRET/TOKEN/KEY 키 | *_FILE이며 /run/secrets 경로 | 1회차 FAIL(`YTWEB_SECRETS_DIR`은 경로이지 값이 아님) → `_DIR` 제외 후 PASS | PASS | **시험 설계 오류**(제품 결함 아님, 9절 참고) |
| TC-VIF-009 | 쓰기 표면 | 〃 | tmpfs 옵션, 볼륨 분배 | tmpfs마다 noexec,nosuid; db(pgdata,backups), api·worker(app_secrets)만 | 일치 | PASS | |
| TC-VIF-010 | 자원 상한 | 〃 | deploy.resources.limits | 전 서비스 cpus·memory·pids | 일치 | PASS | |
| TC-VIF-011 | 헬스체크·기동 순서 | 〃 | healthcheck/depends_on | migrate는 disable·restart no, api·worker는 migrate 성공 후, web은 api 건강 후 | 일치 | PASS | |
| TC-VIF-012 | 이미지 공유·pull 정책 | 〃 | image/pull_policy/build | api·worker·migrate 동일 이미지, migrate·worker pull never, build는 api만 | 일치 | PASS | |
| TC-VIF-013 | 헬스체크 경로 | 〃 | api 헬스체크 URL | 내부 `127.0.0.1:8000/healthz`, web은 `/nginx-health` | 일치 | PASS | DEC-047과 정합 |
| TC-VIF-014 | compose.yaml 머리 주석이 3망 구조와 모순 없음 | 〃 | 앞 10줄에서 "app 네트워크" 검색 | 없음 | **있음**(6~7행 "app 네트워크는 internal … 모든 서비스가 붙는다") | XFAIL | **DEF-VIF-002**(Low) |
| TC-VIF-020 | 오버레이 키 허용 목록 | compose.online.yaml | 키 집합·금지 키 | services는 api·worker의 networks/environment/secrets만, 최상위 secrets=google_client, networks=egress, ports/cap_add/privileged/volumes/user 등 없음 | 일치 | PASS | DEC-048 ⑤ |
| TC-VIF-021 | 병합 후 새 포트·권한 없음 | 기본+오버레이 병합 | 5개 서비스의 ports/hardening/user/volumes/tmpfs/image/command/healthcheck/deploy 비교 | 기본과 완전히 동일, 게시 포트 web 하나 | 일치 | PASS | |
| TC-VIF-022 | egress 소속·db 격리 | 〃 | 소속 집계 | api·worker만 egress, db/migrate=back, web=front+edge, egress는 기본에 없고 `driver: bridge`뿐, front/back internal 유지 | 일치 | PASS | |
| TC-VIF-023 | google_client 비밀 범위 | 〃 | secrets/env | api·worker만, 환경변수는 경로 `/run/secrets/google_client`, 기존 환경변수 보존 | 일치 | PASS | |
| TC-VIF-024 | 오버레이 파일 ↔ ps1 경로 일치 | 〃 | 정규식 | `./secrets/google_client.json` == `secrets\google_client.json`, 오버레이 파일명 일치 | 일치 | PASS | |
| TC-VIF-025 | 구글 비밀 git·빌드 컨텍스트 제외 | .gitignore/.dockerignore | 정규식 | `web/secrets/`, `secrets/`, `**/secrets/` | 일치 | PASS | |
| TC-VIF-026 | `docker compose config` 교차 검증 | docker CLI | 임시 폴더에 가짜 비밀과 함께 병합 | 내 병합 함수와 같은 결론(포트 불변, hardening, 망, 비밀) | 일치 | PASS | |
| TC-VIF-030 | 루트 프로브 404 | nginx.conf | `= /healthz`·`= /readyz` 블록 | `return 404`, proxy_pass/try_files/rewrite 없음, 우회 위치 없음 | 일치 | PASS | DEC-047 ③ |
| TC-VIF-031 | /api 프로브 프록시 | 〃 | 블록 검사 | `proxy_pass $api_upstream/healthz|readyz`, 속도 제한, API용 헤더 | 일치 | PASS | |
| TC-VIF-032 | 업스트림 단일 | 〃 | proxy_pass/set 수집 | `http://api:8000` 하나 | 일치 | PASS | SSRF 방지 |
| TC-VIF-033 | 보안 헤더 스니펫 | 두 스니펫 | 7헤더 always 각 1줄, CSP 내용 | 페이지 CSP에 unsafe-eval·script 인라인·`*` 없음, API CSP `default-src 'none'`, 나머지 6줄 동일 | 일치 | PASS | DEF-7-007 |
| TC-VIF-034 | add_header 상속 소실 방지 | 〃 | location별 include 검사 | add_header를 가진 모든 위치가 스니펫 include, server 레벨도 include | 일치 | PASS | |
| TC-VIF-035 | Cache-Control 정확히 1회 | 〃 | 위치별 개수·proxy.conf | nginx-health 제외 위치마다 1개, 프록시 위치는 proxy.conf include + `proxy_hide_header Cache-Control` | 일치 | PASS | DEF-7-001 |
| TC-VIF-036 | 프록시가 업스트림 헤더 숨김 | proxy.conf | 정규식 | 7헤더+Server+X-Powered-By+Cache-Control 숨김, XFF는 `$remote_addr`만 | 일치 | PASS | |
| TC-VIF-037 | 서버 수준 통제 | nginx.conf | listen/map/444/error_log | server_tokens off, listen 8080 하나, 허용 Host 2개, `default 0`, 444, error_log error, autoindex/alias 없음 | 일치 | PASS | |
| TC-VIF-038 | 액세스 로그에 쿼리·쿠키 없음 | 〃 | log_format | `$args`/`$request_uri`/`$request`/쿠키/Authorization/Referer 없음, `$uri` 사용 | 일치 | PASS | DEF-VI-003 |
| TC-VIF-039 | 메서드·크기 제한 | 〃 | limit_except 등 | `/`·`/assets/` GET/HEAD만, `/api/` 6메서드만, 본문 1m, 429 | 일치 | PASS | |
| TC-VIF-040 | /nginx-health 정적 | 〃 | 블록 | return 200, 프록시 없음 | 일치 | PASS | |
| TC-VIF-041 | 루트 프로브 변형 경로도 HTML 200 아님 | 〃 | `/healthz/` 등을 받을 폴백 위치 존재 여부 | 폴백 위치 존재 | **없음**(정확 일치뿐) → `/healthz/`는 `location /`로 감 | XFAIL | **DEF-VIF-001**(Low), 실측 TC-VIF-111 |
| TC-VIF-050(×10) | ps1 BOM·괄호 짝·줄바꿈 혼재 | scripts/*.ps1 | 바이트/렉서 검사 | 전 파일 UTF-8 BOM, `{}()[]` 짝 일치, 혼재 없음 | 일치 | PASS | 한글+PS 5.1 |
| TC-VIF-051 | Invoke-Compose 오버레이 로직 | _common.ps1 | 정규식 | 기본 파일 → (구글 파일 있을 때만) 오버레이 순서, `-p` 프로젝트, Test-Path 1곳 | 일치 | PASS | DEC-048 ⑤ |
| TC-VIF-052 | compose 직접 호출 우회 없음 | 다른 ps1 | 검색 | `$YtwebComposeFile` 직접 사용/`docker compose` 직접 호출 없음 | 일치 | PASS | |
| TC-VIF-053 | 상수·서비스·비밀 이름 일치 | _common ↔ compose | 비교 | 포트 8080, URL 127.0.0.1:8080, 서비스 5개 순서, 비밀 3개, 프로젝트 기본 ytweb | 일치 | PASS | |
| TC-VIF-054 | 비밀 생성 정책 | _common.ps1 | 함수 본문 | CSPRNG 32바이트, 기존 파일 덮어쓰기 금지, DB 볼륨 있으면 중단, 값 출력 없음 | 1회차 FAIL(`$text`는 명령 출력 변수) → 범위 좁힘 후 PASS | PASS | **시험 설계 오류** |
| TC-VIF-055 | 위험 구문·URL | scripts | 검색 | Invoke-Expression·0.0.0.0·비밀 폴더 삭제 없음, 외부 URL은 허용 목록(Docker 레지스트리 조회 등)만 | 1회차 FAIL ×2(pin-digests의 레지스트리 조회, status.ps1의 로컬 Invoke-WebRequest) → 설계상 정당한 사용을 허용 목록에 반영 후 PASS | PASS | **시험 설계 오류** |
| TC-VIF-056 | 파괴적 스크립트 확인 문구 | restore/reset | 검색 | Read-ConfirmText, `exit 2`, 파일명 검증, SHA-256 | 일치 | PASS | |
| TC-VIF-057 | 백업 파일명 정규식 ps1 = bash | _common ↔ ytweb-db | 비교+샘플 | 동일 `^[A-Za-z0-9._-]+\.dump$`, `../`·`/`·개행 거부 | 일치 | PASS | 경로 이탈 방지 |
| TC-VIF-058 | status.ps1 프로브 경로 | status.ps1 | 정규식 | `/api/healthz`·`/api/readyz`만 | 일치 | PASS | DEC-047 |
| TC-VIF-060 | 문서가 /api/* 와 루트 404를 명시 | API.md·WEB_DESIGN.md·README | 정규식 | 명시 | 일치 | PASS | |
| TC-VIF-061 | DESIGN.md 가용성 측정 경로 | DESIGN.md NFR-W07 | 행 검색 | `/api/readyz` | **`/readyz`로 적혀 있음**(사용자 포트에서는 404) | XFAIL | **DEF-VIF-003**(Low) |

### 4-B. 실가동 시험 (`test_vinf2_live.py`, 최종 실행 28 PASS + 1 XFAIL, 새 스택·같은 스택 재실행 각각)
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고 |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-VIF-100 | 전 컨테이너 건강 | 스택 기동 | inspect 폴링(최대 120초) | db/api/worker/web running+healthy, migrate exited(0) | 일치(0.2~4.4초) | PASS | 새 스택 직후 1회차에서 worker 건강 확인 전에 판정해 FAIL → 폴링으로 수정(**시험 경합 오류**) |
| TC-VIF-101(×5) | 런타임 하드닝 | 〃 | inspect + `/proc/1/status` | ReadonlyRootfs, CapDrop ALL, no-new-privileges, 비특권, 지정 uid, **CapEff=0, NoNewPrivs=1**, 마운트는 volume/tmpfs/읽기전용 /run/secrets 바인드뿐 | 일치 | PASS | 1회차 FAIL(파일 비밀은 bind 마운트인데 volume/tmpfs만 허용) → `/run/secrets/*` 읽기 전용 bind 허용으로 수정(**시험 설계 오류**) |
| TC-VIF-102 | 읽기 전용 루트 | 〃 | api/worker/web에 `/usr`에 touch, /tmp에 touch, /tmp 실행 | 앞은 "Read-only file system", /tmp 쓰기 가능, /tmp 실행 거부(noexec) | 일치 | PASS | |
| TC-VIF-103 | 포트 게시·리스너 | 〃 | PortBindings, /proc/net/tcp 리스너, 비루프백 IP 접속 시도 | web만 `127.0.0.1:18081`, 리스너 주소 0100007F뿐, 비루프백 IP 13개로 접속 불가 | 일치 | PASS | 1회차 FAIL(`ss` 없음 → /proc/net/tcp 사용, **환경 제약**) |
| TC-VIF-104 | 네트워크 internal·소속 | 〃 | docker network inspect | front·back internal, edge 비-internal, 소속 행렬 일치, egress에 붙은 컨테이너 없음 | 일치 | PASS | 2회차 FAIL(오버레이 시험 뒤 빈 egress 망이 남아 "망 부재"로 판정 → "붙은 컨테이너 부재"로 수정, **시험 순서 의존 오류**, 관찰 O-2) |
| TC-VIF-110 | 프로브 경로 실측 | 〃 | GET /healthz,/readyz,/api/healthz,/api/readyz,/nginx-health, HEAD/POST | 404("not found\n", text/plain) ×2, 200 `{"status":"ok"}`, 200 `{"status":"ok","db":"ok","mode":"demo"}`, 200 ok, HEAD 404, POST /api/healthz 405 | 일치 | PASS | DEC-047 ③ |
| TC-VIF-111 | 프로브 변형 경로 | 〃 | `/healthz/`,`/HEALTHZ`,`/readyz/`,`/healthz%2f` 등 | HTML 200이 아니어야 함 | **네 경로가 SPA index.html(200, text/html)** — `/healthz?x=1`·`//healthz`는 404, `/api/healthz/`는 307→`/api/healthz`, `/api//healthz`는 200 JSON | XFAIL | **DEF-VIF-001**(Low) |
| TC-VIF-112 | 모든 응답 유형의 헤더 | 〃 | `/`, SPA 경로, 404 프로브, /api 200·401·404·405, DELETE / (403), /nginx-health, 해시 자산, 없는 자산 | 보안 7헤더 각 1줄, Cache-Control 0 또는 1줄(`no-cache`/`no-store`/`immutable`), `Server: nginx`만, X-Powered-By 없음 | 일치 | PASS | DEF-7-001 |
| TC-VIF-113 | 세션 발급·잘못된 본문·413 | 〃 | POST /api/v1/auth/session {}, 깨진 JSON, 1MiB+ 본문 | 200/400·422/413 모두 헤더 1벌 | 일치 | PASS | |
| TC-VIF-114 | Host·메서드 차단 | 〃 | 나쁜 Host 9종, TRACE/DELETE/PUT/PATCH/POST/CONNECT/PROPFIND | 앱 응답 없음(연결 종료 또는 400), 허용 Host 200, 메서드 400/403/405/501 | 일치(`evil.com`·`127.0.0.1:18081`·`localhost`·`[::1]:8080` 등은 연결 종료, 빈 Host·`127.0.0.1:8080.evil.com`은 400) | PASS | 1회차 FAIL(빈 Host는 nginx가 400으로 거부하는데 "연결 종료"만 기대 → 기대를 "앱 응답 없음"으로 수정: 사용자 위험 변화 없음, **시험 기대 과도**) |
| TC-VIF-115 | 쿼리·쿠키 비기록 | 〃 | `?code=<토큰>`, 쿠키에 토큰 | web 로그에 uri는 있고 토큰은 없음 | 일치 | PASS | DEF-VI-003 / M2 OAuth |
| TC-VIF-116 | 오류 경로 헤더, 429 | 〃 | 9KB 주소(414), 9KB 헤더(400), /api/healthz 연속 요청 | 414·400에도 7헤더 1벌, 429가 실제 발생하며 헤더 1벌+Cache-Control 1줄 | 일치 | PASS | 2차 검증에서 추가 |
| TC-VIF-120 | web→db 불가, api→db 가능 | 〃 | web에서 `nc db 5432`, `nc <db IP> 5432`, `getent hosts db`; 대조로 web→api:8000, api→db | web→db 실패·이름 해석 실패, 양성 대조 성공 | 일치 | PASS | DEC-045 |
| TC-VIF-121 | 내부 서비스 외부 통신 불가 | 〃 | api·worker·db에서 1.1.1.1:443, 외부 이름 해석 | 모두 차단 | 일치(관찰: web은 외부로 나가진다 `rc=0`) | PASS | web egress는 수용된 잔여 위험(DEC-045), 관찰 O-1 |
| TC-VIF-122 | 비밀 평문 부재 | 〃 | 실제 비밀값을 inspect·로그·`/proc/1/environ`·이미지 이력·이미지 tar 바이트·파일명 검색, /run/secrets 분배 | 어디에도 없음, db 3개/api·worker 1개/web 0개, api에서 owner 비밀 읽기 불가, 이미지에 CA 변수 없음 | 일치 | PASS | 빌드 컨텍스트에 비밀 파일이 존재하던 상태에서 수행(이미지 유입 가능 조건에서의 부재 확인) |
| TC-VIF-130 | 데이터 생성 | 〃 | 세션 발급 → 영상 불러오기(작업 큐→워커) | 작업 succeeded, videos 200, audit_log>0 | 일치 | PASS | |
| TC-VIF-131 | 재시작·down/up 후 데이터 유지 | 〃 | `compose restart`, `down`(볼륨 유지) → `up` | 15개 테이블 행 수 동일, readyz 200 | 일치(readyz 복귀 3.1초) | PASS | |
| TC-VIF-132 | DB 재시작 복구 | 〃 | `docker restart db` | api가 재연결, readyz 200, 데이터 동일 | 일치(1.0초) | PASS | |
| TC-VIF-133 | 백업 단계(dump→list) | 〃 | `ytweb-db dump/list`, 중복 이름, 나쁜 이름 7종 | 크기>1000, 목차 수, 모드 600, 중복·나쁜 이름 거부 | 일치 | PASS | backup.ps1 동등 단계(pwsh 미경유) |
| TC-VIF-134 | 손상 백업 복원 거부 | 〃 | 랜덤 4KB, 잘린 덤프, 없는 파일 | 모두 비정상 종료, 행 수 불변 | 일치 | PASS | 단일 트랜잭션 |
| TC-VIF-135 | 복원 순서 + alembic_version 권한 | 〃 | 데이터 변경 → 안전 백업 → web/api/worker 중지 → (대조) 가드 없는 `pg_restore` → 실제 `ytweb-db restore` → 권한 확인 → up | 가드 없이는 권한이 풀리고(대조), 복원 명령 뒤에는 SELECT만 가능, UPDATE/DELETE/INSERT 및 audit_log UPDATE/DELETE는 `permission denied`, 일반 조회 가능, 행 수 백업 시점으로 복귀, 복원 후 세션 발급 가능 | **대조에서 `has_table_privilege=true`(권한 풀림), 복원 명령 뒤 `DELETE=false,INSERT=false,REFERENCES=false,SELECT=true,TRIGGER=false,TRUNCATE=false,UPDATE=false`**, 거부 5건 모두 permission denied, 행 수 복귀 | PASS | **DEF-7-002 해소 확인 + 시험 민감도 입증** |
| TC-VIF-136 | 마이그레이션 head | 〃 | DB 버전 vs 코드 head, migrate 재실행 | 같음, 재실행 성공·불변 | 일치 | PASS | |
| TC-VIF-140 | compose.online 실가동 | 가짜 `google_client.json` | 오버레이 포함 `up -d` → 검사 → 파일 삭제 후 오버레이 없이 `up -d` | api=front+back+egress, worker=back+egress, 마운트에 google_client 추가(읽기 전용), 환경변수 추가, 하드닝·사용자·포트 불변, db/migrate/web에 egress 없음, 비밀 내용이 inspect·로그에 없음, 원복 후 api/worker에서 egress·google 마운트 제거 | 일치(관찰: 오버레이 중 api는 외부로 나간다 `OPEN`, db는 `BLOCKED`) | PASS | 1회차 FAIL(원복 뒤 빈 egress 망이 남음 — compose 동작, 컨테이너 부착 없음으로 판정 수정) |
| TC-VIF-150 | 시험 민감도(변이 nginx) | 〃 | proxy.conf에서 Cache-Control 숨김을 뺀 일회용 nginx(포트 18082) | Cache-Control 2줄 | 2줄 | PASS | DEF-7-001 재현, 112의 판정이 의미 있음을 입증 |
| TC-VIF-070 | pwsh 7로 Invoke-Compose 실행(에뮬레이션) | `docker` 함수를 가짜로 대체 | 구글 파일 없을 때/있을 때 인자 수집 | 없을 때 `-f compose.yaml`만, 있을 때 `-f compose.yaml -f compose.online.yaml` | 일치 | PASS | 수작업 실행, 임시 폴더 삭제됨. Linux라 역슬래시 이름 파일로 에뮬레이션 |
| TC-VIF-071 | pwsh 7 구문(AST) | scripts/*.ps1 10개 | `Parser::ParseFile` | 오류 0 | 오류 0 | PASS | 5.1 문법 호환은 미검증 |
| TC-VIF-199 | 관찰값 기록 | 〃 | STATE 덤프 | 파일 기록 | 기록 | PASS | 판정 아님 |

### 4-C. 변이 점검 (정적 시험 대상, 원본은 건드리지 않고 사본에서만 수행)
무변이 사본 기준선: 실패 0, XFAIL 3. 아래 27곳을 한 곳씩 깨뜨려 정적 시험을 돌렸다(`VINF2_ROOT`로 사본 지정).

| # | 변이 | 검출 여부 | 잡은 시험 |
|---|------|-----------|-----------|
| M01 | web 포트 `127.0.0.1:8080:8080` → `8080:8080` | 검출 | 004, 021, 026 |
| M02 | front `internal: true` → false | 검출 | 005, 022, 026 |
| M03 | back `internal: true` → false | 검출 | 005, 022, 026 |
| M04 | 하드닝 앵커 `read_only` → false | 검출 | 001, 026 |
| M05 | `cap_drop: [ALL]` → `[NET_RAW]` | 검출 | 001, 026 |
| M06 | `no-new-privileges:true` → false | 검출 | 001 |
| M07 | web을 back 망에 추가 | 검출 | 006, 022 |
| M08 | 루트 `/healthz` 404 → 200 | 검출 | 030 |
| M09 | proxy.conf의 Cache-Control 숨김 제거 | 검출 | 035, 036 |
| M10 | API 스니펫의 X-Frame-Options 삭제 | 검출 | 033 |
| M11 | Host 허용 목록에 `evil.com` 추가 | 검출 | 037 |
| M12 | online에 호스트 포트 `9000:9000` 추가 | 검출 | 020, 021, 026 |
| M13 | online worker에 `cap_add: [NET_ADMIN]` | 검출 | 020, 021 |
| M14 | online에서 db에 egress 부여 | 검출 | 020, 022, 026 |
| M15 | `_common.ps1` 오버레이 무조건 적용 | 검출 | 051 |
| M16 | `_common.ps1` 구글 파일 경로 불일치 | 검출 | 024 |
| M17 | migrate 사용자 `0:0` | 검출 | 002 |
| M18 | tmpfs `noexec` 제거 | 검출 | 009 |
| M19 | 액세스 로그에 `$request_uri` | 검출 | 038 |
| M20 | status.ps1 BOM 제거 | 검출 | 050 |
| M21 | db 환경변수에 평문 `POSTGRES_PASSWORD` | 검출 | 008 |
| M22 | `server_tokens on` | 검출 | 037 |
| M23 | web에 `docker.sock` 마운트 | 검출 | 003, 009 |
| M24 | api에 owner 비밀 추가 | 검출 | 007, 023, 026 |
| M25 | status.ps1이 루트 `/healthz` 조회 | 검출 | 058 |
| M26 | `/api/healthz` 업스트림 경로 오류 | 검출 | 031 |
| M27 | 백업 파일명 정규식에 `/` 허용 | 검출 | 057 |

결과: **27/27 검출**(생존 0). 실가동 쪽 민감도는 TC-VIF-135(가드 없는 복원에서 권한이 실제로 풀림)와 TC-VIF-150(변이 nginx에서 Cache-Control 2줄)으로 확인했다. 변이 점검 후 `git diff`에 소스·설정 변경 없음(7절 참고).

### 4-D. 합격/불합격 집계
| 구분 | 합격 | 불합격(최종) | 알려진 결함 증명(XFAIL) | 건너뜀/미수행 |
|------|------|--------------|--------------------------|----------------|
| 정적 신규(`test_vinf2_static.py`) | 58 | 0 | 3 (DEF-VIF-001·002·003) | 0 |
| 실가동 신규(`test_vinf2_live.py`) | 28 (3회 실행: 27 / 27 / 28 합격 — 아래 참고) | 0 | 1 (DEF-VIF-001) | 게이트 없으면 전체 건너뜀 |
| 수작업(pwsh 7) | 2 | 0 | 0 | — |
| 변이 | 27 검출 / 27 | 생존 0 | — | — |
| 기존 `tests_infra` 전체(참고) | 195 합격(신규 58 포함 → 기존 137) | 0 | 3 | 331 건너뜀(실가동 게이트, PASS로 세지 않음) |

첫 실행 결과(그대로): 정적 1회차 = 3 FAIL(TC-VIF-008·054·055, 모두 시험 설계 오류). 실가동 1회차(전체 실행) = 2 FAIL(TC-VIF-103 `ss` 없음, TC-VIF-114 빈 Host 기대), 앞서 TC-VIF-101 1 FAIL(bind 마운트). 같은 스택 재실행 중 TC-VIF-104 FAIL(시험 순서 의존), 새 스택 재생성 직후 TC-VIF-100 FAIL(건강 경합). TC-VIF-140 첫 실행 FAIL(빈 egress 망). 이 7건은 **제품 결함이 아니라 시험 설계·환경 문제**이며, 수정 근거는 각 행에 적었다. 제품 쪽 동작은 수정 전후 동일하다(제품 코드·설정 무수정).

## 5. 커버리지
- 커버리지 지표: 인프라 설정 파일이라 라인 커버리지 대신 **결정·결함 추적 커버리지**로 본다.
  | 대상 | 시험 |
  |------|------|
  | DEC-047 ③ 루트 404 / /api/* 노출 | 030, 031, 058, 060, 110, 111 |
  | DEF-7-001 Cache-Control 중복 | 035, 036, 112, 113, 116, 150 |
  | DEF-7-002 복원 뒤 alembic_version 권한 | 133~136 |
  | DEF-7-006/007 (HTML 200 오판, API CSP) | 030, 033, 041, 110~112 |
  | DEC-045 네트워크 3분리·web→db 불가 | 005, 006, 104, 120, 121 |
  | DEF-VI-003 쿼리 비기록 | 038, 115 |
  | DEC-048 compose.online·_common.ps1 | 020~026, 051, 052, 070, 140 |
  | 하드닝·비밀·포트 | 001~013, 101~103, 122 |
  | 데이터 유지·백업·복원 | 131~136 |
- 커버되지 않은 부분과 사유: 2절 제외 범위 1~7번(특히 실제 `.ps1` 경유 백업·복원, Windows/Docker Desktop, 원본 Dockerfile 직접 빌드, 이미지 취약점 스캔). 오버레이 실가동은 가짜 구글 파일로만 확인(구글 호출 없음). 다중 워커·장시간 부하·디스크 가득 참 같은 운영 장애는 범위 밖

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 내용 |
|----|------|-----------|--------|------|-----------|
| DEF-VIF-001 | DEC-047 ③이 닫은 것은 정확 경로 `/healthz`·`/readyz`뿐이다. `/healthz/`, `/readyz/`, `/HEALTHZ`, `/healthz%2f`는 SPA 폴백(`location /`)으로 가서 **HTML 200**을 돌려준다. DEF-7-006(프로브가 HTML 200을 정상으로 오판)과 같은 종류가 변형 경로에 남아 있다. 실제 사용 경로(`status.ps1`, 헬스체크)는 영향 없음 | `curl -i -H 'Host: 127.0.0.1:8080' http://127.0.0.1:<포트>/healthz/` → `200 text/html`(index.html). 시험: `VINF2_LIVE=1 pytest web/tests_infra/test_vinf2_live.py -k 111`, 정적 TC-VIF-041 | Low | Open | 수정 요청(5단계): `location ~* ^/(healthz|readyz)/?$ { return 404 ...}` 형태로 변형까지 닫거나, 위험 수용 시 DEC로 Deferred 기록. 소스는 고치지 않음 |
| DEF-VIF-002 | `web/compose.yaml` 머리 주석(6~7행)이 "app 네트워크는 internal … 모든 서비스가 붙는다 … web만 edge에 추가로 붙는다"로 DEC-045 이전 구조를 설명한다. 실제 구성(front/back/edge, web은 db 도달 불가)과 모순되어 사용자·운영자가 격리 수준을 오해할 수 있다 | `sed -n 1,10p web/compose.yaml`; 시험 TC-VIF-014 | Low | Open | 수정 요청(주석 문구 수정; 오탈자 수준 조건은 만족하나 이 단위 검증자의 수정 범위 밖이라 직접 고치지 않음). 5단계에서 수정 |
| DEF-VIF-003 | `docs/yt/DESIGN.md` NFR-W07(649행)이 가용성 측정을 "`/readyz`=200"으로 적고, 610·621행도 `/healthz`·`/readyz`를 경로 구분 없이 쓴다. DEC-047은 API.md·WEB_DESIGN.md만 정정하기로 했고 DESIGN.md는 남았다. 사용자 포트(8080)에서 `/readyz`는 404다 | `grep -n 'NFR-W07' docs/yt/DESIGN.md`; 시험 TC-VIF-061 | Low | Open | 수정 요청(문서 정정: "nginx 경유는 `/api/readyz`, 컨테이너 내부는 `/readyz`") |
- 이 단위 밖 원인 가능성: 세 건 모두 이 단위(인프라 설정·문서) 안의 원인이다. 병렬 단위의 규칙 F 회귀 범위에는 영향이 없다.
- **시험 설계 오류 7건**(위 4-D 첫 실행 참고)은 제품 결함이 아니라 이 검증자 시험의 과도한 기대·환경 가정이었고 모두 고쳐 재실행했다. 고친 근거: `YTWEB_SECRETS_DIR`은 경로, `$text`는 명령 출력 변수, `pin-digests.ps1`은 Docker 레지스트리 조회가 존재 목적, `ss` 없음, 파일 비밀은 읽기 전용 bind, 빈 Host는 nginx 표준 400, 상태 폴링 필요. 어느 것도 사용자 관점 위험을 줄이는 방향으로 기대를 낮춘 것이 아니다.
- **관찰(결함 아님, 후속 판단용)**
  - O-1: web은 edge 망 때문에 외부로 나갈 수 있다(`nc 1.1.1.1:443 rc=0`). DEC-045에서 수용된 잔여 위험과 일치
  - O-2: 오버레이를 걷은 뒤에도 빈 `<프로젝트>_egress` 망이 남는다(컨테이너 없음). compose 동작이며 위험 없음. 정리가 필요하면 `docker network rm`
  - O-3: 오버레이를 켜면 api/worker의 외부 통신이 **목적지 제한 없이** 열린다(`OPEN` 실측; 구글 도메인 허용 목록 없음). DEC-048 설계 그대로이며 위협 모델 갱신(단위 5) 때 이그레스 제어(프록시/허용 목록) 필요 여부를 판단할 것
  - O-4: `/api//healthz`는 200 JSON(슬래시 병합), `LOCALHOST:8080` 대문자 Host는 허용(호스트명 대소문자 비구분). 모두 앱 응답이며 우회 위험 아님

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록
  - 컨테이너: `harness-tmp-v2-{db,migrate,api,worker,web}-1`, `harness-tmp-v2-mutweb`(일회용 변이 nginx), 오버레이 시험 중 재생성된 api/worker
  - 이미지: `harness-tmp-v2-db:local`, `harness-tmp-v2-api:local`, `harness-tmp-v2-web:local` (참고: 시작 시점에 `harness-tmp-v2-db:local`이 이전 세션 산물로 이미 있었고 같은 접두사라 이번 빌드로 교체 후 함께 삭제)
  - 볼륨: `harness-tmp-v2_{pgdata,backups,app_secrets}`
  - 네트워크: `harness-tmp-v2_{front,back,edge,egress}`
  - 파일: `web/secrets/{db_superuser_password,db_owner_password,db_app_password}`(gitignored, 임시 생성)와 시험 중 `web/secrets/google_client.json`(가짜), `.harness-tmp/v2/`(override.yaml, 사본 Dockerfile, CA 사본, 변이 사본, 로그), `.harness-tmp/v2b/`(pwsh 에뮬레이션)
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가: [x] 예 / [ ] 아니오 — 예외: 도커 비밀 파일 경로가 compose.yaml 기준 `web/secrets/`로 고정이라 gitignored 폴더 `web/secrets/`에 임시 비밀 3개와 가짜 구글 파일을 만들었다(규칙 K의 취지: 저장소 추적 대상 아님, 시험 후 폴더째 삭제). 도커 자원은 `harness-tmp-v2` 접두사만
- 정리(삭제) 완료 여부: 완료. `docker compose -p harness-tmp-v2 down -v --remove-orphans`, `docker rm -f harness-tmp-v2-mutweb`, `docker rmi harness-tmp-v2-{db,api,web}:local`, `docker network rm harness-tmp-v2_egress`, `rm -rf web/secrets .harness-tmp/v2`(`v2b`는 사용 직후 삭제). 잔여 확인: 접두사 `^harness-tmp-v2[-_]`의 컨테이너·이미지·볼륨·네트워크 모두 0건. 다른 접두사(`harness-tmp-int` 5개, `harness-tmp-sec` 5개, `harness-tmp-vinf` 5개, `harness-tmp-vinf2` 1개 컨테이너)는 건드리지 않았고 그대로 남아 있다. 빌드 캐시(dangling)는 다른 에이전트와 공유라 정리하지 않았다
- 정리 후 `git status` 실행 결과(그대로 첨부): 아래 "최종 git status" 블록(결과서·검증 로그 작성 후 재실행한 값)
- 병렬 실행 여부: 단독 호출. 다만 오케스트레이터가 WIP로 시험 파일을 커밋한 이력이 있어(`80b7a98`, `94598b8`, `6be65a8`, `e956b6e`, `b8fec92`) `test_vinf2_static.py`는 추적 상태이고 `test_vinf2_live.py`는 마지막 수정분(TC-VIF-116)만 변경으로 보인다. 둘 다 이 단위 소유. 이 검증자는 커밋·푸시를 하지 않았다
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 없음 / [ ] 있음
- 최종 git status(결과서 작성 후):
```
FINAL_GIT_STATUS_PLACEHOLDER
```

## 8. 리스크 및 잔존 이슈
- 이번 테스트로 커버되지 않는 알려진 리스크
  1. 사용자 PC(Windows, Docker Desktop, PowerShell 5.1)에서의 `start/backup/restore.ps1` 실제 동작과 `127.0.0.1` 한정 게시의 Desktop 동작 — 10단계에서 확인해야 한다
  2. 원본 Dockerfile의 빌드 성공(이 환경 프록시 제약으로 CA 추가 사본으로 빌드)
  3. 오버레이 사용 시 api/worker 이그레스 무제한(O-3)과 web의 외부 통신(O-1)
  4. 변이 점검은 정적 시험에 대해 27곳, 실가동은 2곳(권한, Cache-Control)만 수행
- 후속 조치가 필요한 항목: DEF-VIF-001~003 처리(또는 사용자 수용 시 DEC 기록 후 Deferred), O-3은 M2 위협 모델 갱신(단위 5)에서 판단, `docs/harness/traceability.md`는 직접 수정하지 않음(요청 사항은 아래)

## 9. 결론 및 판정
- [ ] PASS — 다음 단계 진행 가능
- [x] CONDITIONAL PASS — 조건: DEF-VIF-001~003(모두 Low)을 5단계에서 수정하거나 사용자 수용(Deferred + DEC)으로 정리. 세 건 모두 현재 동작하는 기능·보안 통제를 막지 않으며 7단계 영향 재시험은 진행 가능. 이 조건이 정리되기 전에는 "PASS"로 세지 않는다
- [ ] FAIL

판정 근거: 지시된 확인 항목은 전부 실제로 수행되어 합격했다 — 전 컨테이너 건강, 루트 /healthz·/readyz 404 및 /api/* 200, 헤더 중복 없음(변이 nginx에서는 중복이 재현되어 시험이 유효함을 입증), web→db 불가, 비밀 평문 없음, 재시작 후 데이터 유지, 복원 뒤 alembic_version 권한(가드 없이는 풀림을 대조로 입증), compose.online이 구글 비밀·egress 외에 새 포트·권한을 늘리지 않음(실가동·병합·정적 3중 확인). 열린 결함은 Low 3건이다.

### 공유 문서 갱신 요청 (이 단위는 traceability.md·decisions.md를 직접 수정하지 않음)
- `docs/harness/traceability.md`: W-FIX-INF 관련 REQ(인프라 보안·헬스·백업/복원·compose.online) "단위테스트" 컬럼에 `TC-VIF-001~061`, `TC-VIF-100~199`, `TC-VIF-070·071`을 연결하고 비고에 "CONDITIONAL PASS, 열린 Low 3건(DEF-VIF-001~003)"을 표시
- `docs/harness/decisions.md`: 신규 결정 없음. DEF-VIF 3건을 수용하는 경우에만 DEC 추가(Low 한정 Deferred)

## 10. 내부 검증 (최소 2회, `verification-log-template.md` 사용)
- 1차 검증 결과 요약: 지시 항목 ↔ 시험 ID 100% 매핑(5절 표), 기대값이 명세(DEC-045~048, 템플릿 지시문)에 근거함을 확인. 시험 설계 오류 5건을 발견·수정(근거 기록). 결함 후보 3건 확정
- 2차 검증 결과 요약: "이 시험을 통과했다고 다음 단계로 넘겨도 되는가"를 의심해 (a) 새 스택 재생성 후 전체 재실행, (b) 시험이 놓칠 경계(414/400/429 응답 헤더, 비밀 이미지 바이트 검색, 시험 민감도 변이 2건, 오버레이 실가동·원복)를 추가. 추가 중 시험 설계 오류 2건(경합, 순서 의존) 발견·수정
- 3차(확정) 회차: 같은 스택에서 전체 재실행 28 PASS + 1 XFAIL, 정적 전체 195 PASS, 시험 설계 오류 0건·신규 제품 결함 0건 확인. **제품 결함 0건은 아니다(Low 3건 Open)**
- 검증 로그 파일 경로: `docs/harness/verify-logs/verify-log_web-WU-FIX-INF-test.md`
