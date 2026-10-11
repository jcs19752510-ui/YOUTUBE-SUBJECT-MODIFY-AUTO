# 유튜브 제목 웹 (데모 모드) 실행 안내

내 PC에서 Docker로 웹 화면을 띄우는 방법입니다. **처음 쓰는 분 기준**으로 적었습니다.

> **데모 모드란?** 가짜 영상 200개와 모의 AI 제안만 쓰는 모드입니다. **유튜브에도, AI 서비스에도 아무것도 전송하지 않으며** 실제 영상 제목은 절대 바뀌지 않습니다. (실제 연동은 이후 단계에서 별도 승인 후에만 추가됩니다.)

## 1. 필요한 것

| 필요한 것 | 확인 방법 |
|---|---|
| Windows 10/11 + **Docker Desktop** (Linux 컨테이너 모드) | 시작 메뉴에서 "Docker Desktop" 실행 → 작업 표시줄 고래 아이콘이 "실행 중"이 될 때까지 대기 |
| WSL2 (Docker Desktop 기본 방식) | PowerShell에서 `wsl --status` 실행. 오류가 나면 `wsl --update` 후 PC 재시작 |
| 인터넷 연결 (처음 한 번, 이미지·패키지 내려받기) | - |
| 디스크 여유 약 3GB, 메모리 여유 약 2GB | Docker Desktop 설정 > Resources |
| 빈 포트 **8080** | 사용 중이면 `start.ps1` 이 알려 줍니다 |

Docker Desktop은 회사 규모에 따라 유료일 수 있습니다. 해당 여부는 본인이 Docker 약관에서 확인하세요(이 프로그램은 판단하지 않습니다).

## 2. 처음 시작

PowerShell을 열고 저장소 폴더로 이동한 뒤 실행합니다.

```powershell
cd C:\big21\vibe-coding\YOUTUBE-SUBJECT-MODIFY-AUTO
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned   # 이 창에서만 스크립트 실행 허용
.\web\scripts\start.ps1 -OpenBrowser
```

`start.ps1` 이 알아서 하는 일: Docker 확인 → 비밀번호 파일 생성(`web\secrets\`, 처음 한 번, 값은 화면에 표시하지 않음) → 포트 확인 → 이미지 빌드·시작 → 준비 대기. **첫 실행은 5~15분** 걸릴 수 있습니다. 끝나면 아래 주소가 표시됩니다.

**접속 주소: <http://127.0.0.1:8080>** (이 PC에서만 접속됩니다. 같은 와이파이의 다른 기기에서는 열리지 않습니다.)

## 3. 평소 쓰는 명령

| 하고 싶은 일 | 명령 |
|---|---|
| 시작 | `.\web\scripts\start.ps1` (코드를 바꾸지 않았다면 `-NoBuild` 로 빠르게) |
| 종료 (데이터 보존) | `.\web\scripts\stop.ps1` |
| 상태·보안 점검 | `.\web\scripts\status.ps1` (`-Detail` 로 컨테이너 보안 설정까지) |
| 로그 보기 | `.\web\scripts\logs.ps1` / `-Service api` / `-Follow` |
| 백업 | `.\web\scripts\backup.ps1` → `web\backups\ytweb-날짜-시각.dump` |
| 복원 | `.\web\scripts\restore.ps1 -Latest` 또는 `-File 파일명` (확인 문구 `복원합니다` 입력) |
| 데모 데이터 초기화 | `.\web\scripts\reset-demo.ps1` (확인 문구 `데모 초기화` 입력) |
| 베이스 이미지 갱신 확인 | `.\web\scripts\pin-digests.ps1` (`-Apply` 로 반영) |

PC를 껐다 켜면 Docker Desktop을 다시 실행하고 `start.ps1` 을 실행하세요. (Docker Desktop은 기본적으로 로그인 때 자동 시작되지 않습니다.)

### 백업 (알아 둘 것)
- 백업에는 영상·제안·승인·이력·감사 로그가 들어갑니다. **DB 비밀번호(`web\secrets`)와 승인 서명 키(`approval_hmac.key`)는 들어가지 않습니다.** 승인 서명 키는 별도 Docker 볼륨(`app_secrets`)에 있어, 새 PC로 옮겨 복원하면 **기존 승인이 모두 무효가 되어 다시 승인**해야 합니다(알려진 제한). 감사 로그는 키 없는 해시 연결이라 이 때문에 검증이 어긋나지 않는 것이 설계입니다(복원 후 표시는 내 PC에서 확인 필요).
- 백업 파일은 암호화되지 않습니다. `web\backups` 를 다른 사람과 공유하지 마세요.
- 복원은 하나의 트랜잭션이라 실패하면 기존 데이터가 그대로 남습니다. 복원 전에 현재 데이터를 자동으로 `pre-restore-*.dump` 로 백업합니다.
- 복원은 같은 PostgreSQL 메이저 버전(17) 이상으로만 하세요.

## 4. 자주 나는 문제

| 증상 | 원인과 조치 |
|---|---|
| "Docker 엔진에 연결할 수 없습니다" | Docker Desktop을 먼저 실행하고 고래 아이콘이 안정될 때까지 1~2분 기다린 뒤 재실행 |
| "포트 8080 사용 중" | 다른 프로그램이 8080을 씁니다. `Get-NetTCPConnection -LocalPort 8080 -State Listen` 으로 `OwningProcess` 확인 후 종료 |
| WSL 관련 오류 | `wsl --update`, `wsl --shutdown` 후 Docker Desktop 재시작, 그래도 안 되면 PC 재시작. Windows 기능 "가상 머신 플랫폼"·BIOS 가상화가 켜져 있어야 합니다 |
| "스크립트를 실행할 수 없습니다" | 위 2장의 `Set-ExecutionPolicy -Scope Process ...` 를 같은 창에서 먼저 실행 |
| "Windows 컨테이너 모드" 오류 | 고래 아이콘 오른쪽 클릭 > Switch to Linux containers |
| 빌드 중 다운로드 실패 | 인터넷/사내 프록시 확인. 회사 네트워크가 TLS를 가로채면 Docker Desktop에 인증서 설정이 필요할 수 있습니다 |
| 비밀 파일이 없는데 DB 볼륨은 있음 | `web\secrets` 를 지웠기 때문입니다. 비밀번호가 달라지면 접속할 수 없으니 백업해 둔 폴더를 되돌려 놓으세요. 처음부터 다시 시작하려면 `reset-demo.ps1 -DeleteVolumes` |
| 화면이 하얗게 나옴 | 브라우저 개발자 도구(F12) 콘솔에 "Content Security Policy" 오류가 있는지 확인 후 알려 주세요(보안 헤더가 엄격합니다) |
| 컨테이너가 계속 재시작 | `.\web\scripts\logs.ps1 -Service api` (또는 db/worker/migrate) 로 원인 확인 |

## 5. 데이터 삭제 경고

- 일반 종료(`stop.ps1`)는 데이터를 지우지 않습니다.
- **`docker compose down -v` 또는 `--volumes` 를 직접 실행하면 데이터베이스가 영구 삭제됩니다.** 스크립트는 `reset-demo.ps1 -DeleteVolumes`(확인 문구 `모든 데이터 삭제` 입력, 사전 자동 백업)에서만 이를 수행합니다.
- Docker Desktop의 "Clean / Purge data", `docker system prune --volumes` 도 볼륨을 지웁니다.

## 6. 보안 요약

- 호스트에 열리는 포트는 **`127.0.0.1:8080` 하나뿐**입니다(`web`). DB(5432)·API(8000)·워커는 호스트 포트가 없습니다. `status.ps1` 이 실제 게시 주소를 점검합니다.
- 모든 컨테이너: 비루트 사용자, 읽기 전용 루트 파일시스템, 모든 리눅스 권한(cap) 제거, `no-new-privileges`, 메모리·CPU·프로세스 수 상한, Docker 소켓 마운트 없음, 호스트 폴더 마운트 없음(명명 볼륨만).
- 네트워크는 3개입니다: `front`(web↔api)와 `back`(api·worker·migrate↔db)은 외부 통신이 막힌(internal) 네트워크이고, 웹(nginx)만 포트 게시를 위해 별도 `edge` 네트워크에 붙습니다. 그래서 web은 DB에 닿지 못하고, 데모 모드의 api/worker/db는 인터넷에 나가지 못합니다(nginx는 외부로 요청을 보내지 않습니다).
- DB: 슈퍼유저와 별도로 소유자(`ytweb_owner`, 마이그레이션 전용)·앱(`ytweb_app`, 테이블 읽기/쓰기만, 구조 변경 불가) 계정을 쓰고, 모든 접속은 scram-sha-256 + 컨테이너 내부 사설망만 허용합니다. 감사 로그는 앱 계정이 수정·삭제할 수 없습니다.
- 비밀번호는 `web\secrets\` 파일(현재 사용자만 읽도록 권한 제한, git 제외)에서 Docker secrets 로 주입합니다. 이미지·compose·환경변수에 값이 없습니다.
- nginx: Host 헤더 허용 목록(`127.0.0.1:8080`, `localhost:8080`), CSP(`default-src 'self'`)·`frame-ancestors 'none'` 등 보안 헤더, 요청 크기 1MB 제한, 요청 속도 제한, 서버 버전 숨김.
- 이후 단계(M2·M3)에서 구글·AI 통신이 필요해지면 `web/compose.online.yaml` 을 얹어 api/worker 에만 외부 통신 네트워크를 엽니다(DB는 절대 붙지 않음). 지금은 사용하지 않습니다.

## 7. 구성 (개발자용)

```
브라우저 ─▶ 127.0.0.1:8080 ─▶ web(nginx 비루트: React 정적 + /api 프록시)
                                └▶ api(FastAPI, 8000) ─▶ db(PostgreSQL 17)
                                   worker(같은 이미지) ─▶ db        migrate(1회: 소유자 계정으로 Alembic)
```
- 파일: `web/compose.yaml`, `web/docker/{api,web,db}.Dockerfile`, `web/docker/nginx/`, `web/docker/db/`(init 스크립트·pg_hba·관리 도구 `ytweb-db`), `web/scripts/*.ps1`, `web/tests_infra/`.
- 이미지 빌드 컨텍스트는 저장소 루트(`.dockerignore` 적용). api/worker/migrate 는 이미지 하나를 공유합니다.
- **PostgreSQL 17 선택 근거**: 2026-10-10 기준 지원 중(17은 2029-11까지, 조사 `01-axisB` 3-1 — 공식 postgresql.org 는 열람하지 못해 endoflife.date 집계 기반), 데이터 경로가 `/var/lib/postgresql/data` 로 안정적(18은 경로가 바뀜), 체크섬은 `--data-checksums` 로 직접 켬. 18로 올리려면 덤프→새 볼륨에 복원이 필요합니다.
- **베이스 이미지는 다이제스트로 고정**(`python:3.12-slim`, `node:22-bookworm-slim`, `nginxinc/nginx-unprivileged:stable-alpine`, `postgres:17-bookworm`). 보안 업데이트를 받으려면 `pin-digests.ps1 -Apply` 후 다시 빌드·확인합니다.
- 의존성: `web/backend/requirements.txt`(해시 잠금) + `web/docker/requirements-youtube-title.txt`(코어 `src/youtube_title` 런타임 의존성 PyYAML·python-dotenv·tzdata, 해시 잠금)을 `--require-hashes --only-binary` 로 설치합니다. 코어 소스는 복사본 없이 `PYTHONPATH` 로 같은 소스를 씁니다.
- 프런트 빌드는 `npm ci --ignore-scripts`(설치 스크립트 미실행)이며 `web/frontend/package-lock.json` 이 필요합니다. 최종 이미지에는 소스맵이 없습니다.
- 테스트용 별도 환경: `YTWEB_PROJECT=harness-tmp-xxx`, `YTWEB_IMAGE_PREFIX=harness-tmp-xxx` 환경변수로 운영 데이터·이미지와 분리해 실행합니다(규칙 K, D-13).
- 정적 점검: `python -m pytest web/tests_infra` (도커 데몬 불필요, docker CLI 가 있으면 `compose config` 검사도 수행). 2026-10-11 클라우드 Linux(파이썬 3.13 임시 가상환경)에서 실행: 244건 중 76 통과·168 건너뜀(PowerShell·컨테이너 기동 필요 시험)·실패 0. Windows에서는 실행하지 않았습니다. 2026-10-11 수정 단위(W-FIX-INF)의 시험은 `web/tests_infra/test_fix_inf.py`(TC-WIX-001~011 정적, TC-WIX-030~033 실가동: `WIX_LIVE=1`, 임시 스택 `harness-tmp-*` 에서만).

## 8. 내 PC에서 확인하는 체크리스트 (클라우드에서 못 해 본 것)

1. `start.ps1` 이 끝까지 성공하고 <http://127.0.0.1:8080> 이 열린다.
2. `status.ps1 -Detail` 에 [위험] 표시가 없고, "이 PC 의 포트 8080 리스너는 루프백뿐" 으로 나온다. 같은 와이파이의 다른 기기(휴대폰)에서 `http://<내 PC IP>:8080` 이 **열리지 않는다**.
3. 브라우저 F12 콘솔에 CSP 오류가 없다.
4. `backup.ps1` → `restore.ps1 -Latest` 가 성공하고 행 수가 일치한다.
5. `stop.ps1` 후 `start.ps1` 해도 데이터가 남아 있다. PC 재부팅 후에도 Docker Desktop 실행 + `start.ps1` 로 복구된다.
6. 컨테이너 안에서 비밀 파일이 읽힌다(`docker compose -f web/compose.yaml exec api ls -l /run/secrets` — Windows 비루트 읽기 권한은 클라우드 Linux 에서 검증하지 못함).

## 9. 알려진 제한

- 이 구성은 클라우드(Linux Docker 엔진)에서 빌드·기동·권한·포트까지 실측했지만, **Windows Docker Desktop(WSL2)에서의 포트 바인딩·파일 권한 동작은 위 체크리스트로 직접 확인**해야 합니다.
- 서버 시간대 `TZ=Asia/Seoul` 은 설정돼 있으나 slim 이미지에는 tzdata 가 없어 OS 수준에서는 UTC 로 동작합니다(앱은 파이썬 `tzdata` 패키지로 KST/PT 를 계산, DB 저장은 UTC).
- 워커 헬스체크는 "프로세스 생존"만 봅니다(하트비트 아님).
- 승인 서명 키(`approval_hmac.key`)는 DB 백업에 포함되지 않습니다(위 3장). 감사 로그에는 서명 키가 없습니다(키 없는 SHA-256 해시 연결: 맨 뒤쪽 기록을 통째로 지우는 것은 탐지하지 못함).
- DB 접속은 컨테이너 내부 사설망 평문(TLS 없음)입니다. 호스트·외부에 노출되지 않습니다.

## 10. 보안 결정 요약 (M1 한정 수용, DEC-046)

데모 모드(가짜 데이터)에서는 아래 3가지를 알고도 그대로 두기로 했습니다. 실제 구글·AI 연결 전(M2 착수 전)에 다시 판단합니다. 자세한 설명과 "선생님이 지금 할 일"은 `docs/yt/WEB_INSTALL.md` 7장, `docs/yt/WEB_RUNBOOK.md` 13-2.

- **DEF-9-011 (호스트 서비스 도달)**: 컨테이너가 이 PC에서 "모든 곳에 열려 있는" 서비스에 닿을 수 있습니다(Linux에서 측정). **Windows 방화벽을 켜 두고**, 모르는 열린 서비스를 점검하세요. Docker Desktop에서의 실제 동작은 **사용자 PC 실측**이 필요합니다(10단계).
- **DEF-9-014 (감사 로그)**: DB 소유자 비밀번호를 가진 사람이 기록을 고치고 해시를 **재계산**하면, 또 마지막 몇 건을 지우면 알아채지 못합니다. 재평가: M2 착수 전, 다중 사용자, 외부 접속.
- **DEF-9-013 (보관·파기·백업 암호화)**: 기록은 무기한 보관되고 백업은 암호화되지 않습니다. 롤백 데이터 보관 30일은 가정일 뿐 확정이 아닙니다. 개인정보 해당 여부는 판단하지 않으며 **전문가 확인이 필요**합니다(법률 자문 아님).

복원 후 권한(DEF-7-002), 상태 확인 경로(`/api/healthz`·`/api/readyz` 만, 루트 `/healthz`·`/readyz` 는 404), `/api` 응답의 CSP(`default-src 'none'`)는 2026-10-11 수정 단위에서 고쳤습니다.
