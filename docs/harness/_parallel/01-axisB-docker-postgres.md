# 1단계 조사 조각 — 축 B: Docker Desktop(Windows) · PostgreSQL · 컨테이너 보안

| 항목 | 내용 |
|---|---|
| 조사 시점 | 2026-10-10 (모든 "현재" 표기는 이 날짜 기준) |
| 모드 | 조각 모드(축 B). `01-trend-analysis.md`·검증 로그는 쓰지 않음 |
| 입력 근거 | ORCHESTRATOR.md 1장(규칙 B·I·J·K), 웹프로그램으로수정요청.md 3·5·7장, decisions.md DEC-032~037 |
| 법규 기준 | 대한민국 + YouTube/Google 약관(DEC-032). 이 축에서 Docker 라이선스는 요약만 하며 **법률 자문이 아님** |
| 한계(중요) | 이 에이전트는 Bash 도구가 없다(WebSearch/WebFetch/Read/Write/Grep/Glob만 가짐). 따라서 6번의 `pip download`·`apt-get download` 실행 시도는 **수행하지 못했다**. 대신 파일 시스템 조회와 HTTPS 열람으로 얻은 근거를 6장에 기록했고, 호출자가 직접 실행할 명령을 적었다 |

---

## 0. 요약 (5줄)

1. 로컬 호스트 한정 게시(`127.0.0.1:포트:포트`)는 Docker 공식 문서(엔진 port-publishing 원문 열람)상 호스트 자신만 접근 가능하게 하는 정식 방법이다. 다만 Docker Desktop(WSL2)에서 실제로 루프백에만 열리는지에 대한 **Docker Desktop 전용 공식 문서는 못 찾았고**, 커뮤니티에는 "루프백 바인딩이 WSL 쪽에서 안 보임" 류 보고만 있다. 따라서 **사용자 PC에서의 실측(`Get-NetTCPConnection`, 다른 기기에서 접속 시도)은 생략 불가**하다.
2. PostgreSQL은 2026-10-10 기준 18(~2030-11-14)·17(~2029-11-08)·16(~2028-11-09)·15(~2027-11-11)가 지원 중이고, 14는 2026-11-12에 종료(곧 EOL)되며 19는 베타(`19beta4`)다. Docker Hub에서 18.6·17.11 이미지와 다이제스트를 직접 확인했다. 18부터 데이터 볼륨 마운트 경로가 `/var/lib/postgresql`로 바뀌었다(17 이하는 `/var/lib/postgresql/data`).
3. **이 클라우드 환경에는 이미 PostgreSQL 16.15 서버 바이너리(Ubuntu 패키지)와 `postgres` OS 계정이 설치되어 있다**(dpkg 상태·파일 존재 확인). 또 `dockerd`·`containerd`·`runc` 실행 파일도 있다(데몬만 미기동). 따라서 DEC-033의 "데몬 없음" 전제는 "데몬 미기동"으로 정정될 수 있으며, 기동 가능 여부는 Bash 권한이 있는 호출자가 시도해야 한다.
4. 컨테이너 보안 설정(`read_only`, `cap_drop`, `no-new-privileges`, `tmpfs`, 파일 기반 secrets)은 Compose 공식 참조 원문(GitHub 소스) 기준으로 모두 존재하나, **공식 `postgres` 이미지와 `cap_drop: ALL`·`read_only`의 조합**과 **Windows 호스트 파일을 secrets로 줄 때 비루트 컨테이너 읽기 권한**은 문서에 답이 없어 실측이 필요하다.
5. 보안 도구 주의: Trivy는 2026-03-19~23에 공급망 침해 사고(악성 `0.69.4`~`0.69.6`, `latest`)가 있었고 Docker 공식 블로그가 확인했다. 도구도 **다이제스트로 고정**하고 `latest`를 쓰지 않는다. Docker Scout 무료 범위는 출처별로 "저장소 1개" vs "3개"로 상충한다.

---

## 1. Docker Desktop for Windows (항목 1)

확신도: 상(원문 직접 열람·교차 확인) / 중(2차 자료·단일 출처·일부 추정) / 하(커뮤니티 일화·추정). 열람: 원문(공식 문서의 GitHub 소스 또는 1차 페이지 직접 열람) / 요약(검색 요약만, `[확인 필요: 원문 미열람]`).

| # | 사실 | 근거 URL | 열람 | 확신도 | 이 프로젝트 시사점 |
|---|---|---|---|---|---|
| 1-1 | WSL 2 백엔드 요구: WSL 2.1.5 이상(Enhanced Container Isolation은 2.6 이상). Windows 10은 22H2(빌드 19045), Windows 11은 23H2(빌드 22631) 이상, Pro/Enterprise/Education 에디션 표기. 하드웨어: SLAT 지원 64비트 CPU, RAM 8GB, BIOS/UEFI 가상화 활성. Windows Server 미지원. 서비스 `LanmanServer`가 자동 시작이어야 하고 WSL 2 기능이 켜져 있어야 함 | https://raw.githubusercontent.com/docker/docs/main/content/manuals/desktop/setup/install/windows-install.md (docs.docker.com 페이지의 원본 소스) | 원문(소스) | 상 | `start.ps1`이 사전 점검할 목록(`wsl --version`, `wsl --status`, OS 빌드, 가상화, LanmanServer). 에디션은 Home이면 문서 표기와 다르므로 `[확인 필요: Home 에디션에서 WSL2 백엔드 지원 여부 — 원문은 Pro/Enterprise/Education만 기재]`. 사용자 PC의 에디션·빌드·WSL 버전은 **미확인**(요청문 §2-3: 데몬·WSL2 사용 여부 미확인) |
| 1-2 | 설정 문서: "Start Docker Desktop when you sign in"은 기본 비활성. 메모리 기본 한도는 호스트 메모리의 50%. WSL 2 모드에서는 자원 한도를 WSL 2 유틸리티 VM(`.wslconfig`)에서 설정. Resource Saver는 유휴 시 Linux VM을 끄고 컨테이너가 돌면 3~10초 내 자동 재개. 문서는 "Use the WSL 2 based engine" 옵션을 기본 비활성으로 적었으나 신규 설치 기본값과 일치하는지 불명 | https://raw.githubusercontent.com/docker/docs/main/content/manuals/desktop/settings-and-maintenance/settings.md | 원문(소스) | 상(문서 문구) / 중(실제 기본값) | D-14(자원 상한)는 컨테이너 `mem_limit`뿐 아니라 `.wslconfig` 안내도 필요. 자동 시작이 꺼져 있으므로 PC 재부팅 후 Docker Desktop을 안 켜면 앱이 안 뜬다(W-008 "PC 꺼짐" 시나리오와 직결) |
| 1-3 | 포트 게시: 호스트 IP 없이 `-p 8080:80`이면 모든 주소(0.0.0.0 및 IPv6)에 게시되어 외부 노출 가능. `-p 127.0.0.1:8080:80`은 Docker 호스트만 접근 가능(IPv6는 `::1`). 28.0.0 이전 릴리스는 같은 L2 세그먼트 호스트가 localhost 게시 포트에 접근할 수 있었다는 서술 있음. 방화벽 우회 주의(호스트 IP 미지정 게시, direct routing 옵션) | https://raw.githubusercontent.com/docker/docs/main/content/manuals/engine/network/port-publishing.md | 원문(소스) | 상(엔진 일반) | D-02 근거. 단, 이 페이지는 "Docker Desktop을 다루지 않는다"는 점을 확인했다 — Desktop에서의 동작은 별도 실측 필요 |
| 1-4 | Compose 참조: 포트 짧은 구문 `[HOST:]CONTAINER[/PROTOCOL]`에서 HOST에 IP를 넣을 수 있고, 생략하면 모든 인터페이스(0.0.0.0)에 바인딩. 호스트 IP 생략은 호스트 방화벽 규칙을 우회할 수 있다고 경고 | https://raw.githubusercontent.com/docker/docs/main/content/reference/compose-file/services.md | 원문(소스) | 상 | compose 파일에서 포트는 반드시 `127.0.0.1:` 접두 명시. 환경 변수로 포트 번호만 바꾸게 하고 IP는 고정 |
| 1-5 | Docker Desktop(WSL2)에서 루프백 게시가 실제로 어떻게 보이는지: (a) 커뮤니티 설명은 "WSL의 localhost 포워더가 Windows 측에서 127.0.0.1에만 바인딩, 0.0.0.0은 아무도 안 연다"는 메커니즘(skrog 이슈의 서술, 다른 프로젝트 문서). (b) 같은 자료에 "Docker Desktop 포트 프록시가 모든 인터페이스에 바인딩"이라는 상충 주장이 있음. (c) docker/for-win #13182(2023-01)는 `-p 127.0.0.1:8020:8020`이 WSL2 안에서 "Connection refused"였다는 보고이며 원인은 WSL 1.1.0.0 계열 문제로 추정되고 코드 수정·공식 입장 링크 없이 종결. (d) 2025년 말 "127.0.0.1 또는 LAN IP로 접속 불가, localhost만 가능" 포럼 보고 다수(원인 미확정). (e) WSL 미러드 네트워킹에서 LAN 다른 PC는 접근되나 Windows의 자기 IPv4로는 안 되는 보고(microsoft/WSL #41284) | https://github.com/docker/for-win/issues/13182 (열람) · https://forums.docker.com/t/cannot-access-containers-via-127-0-0-1-or-lan-ip/150176 · https://github.com/Microsoft/wsl/issues/41284 · https://github.com/wslkit/skrog/issues/507 | #13182만 원문 열람, 나머지 요약 `[확인 필요: 원문 미열람]` | 하(일화 위주, 서로 상충) | **상충 보고**: 루프백 한정이 "정상 동작"이라는 쪽과 "Desktop 프록시는 전체 인터페이스에 바인딩"이라는 쪽이 있다. 임의로 고르지 않는다. 설계서에 "게시 IP 고정 + 사용자 PC 실측"을 필수 수용 기준으로 올린다. 실측법: PowerShell `Get-NetTCPConnection -State Listen -LocalPort <포트>`의 LocalAddress가 `127.0.0.1`인지, `docker compose port web <포트>`·`docker ps`의 PORTS 열, 같은 공유기의 다른 기기에서 `http://<PC의 LAN IP>:<포트>` 접속 실패 확인 |
| 1-6 | 바인드 마운트 vs 명명 볼륨: 문서는 명명 볼륨이 백업·이전이 쉽고 고성능 I/O에 유리하다고 서술. 바인드 마운트는 호스트 파일시스템을 컨테이너에 노출하고(쓰기 가능하면 호스트 파일 변경 가능, `ro`로 차단), Docker Desktop에서는 데몬이 Linux VM 안에 있으나 네이티브 경로 마운트를 투명하게 처리한다고 서술. WSL 모범사례 문서는 `/mnt/c` 경로 바인드 마운트의 성능이 리눅스 파일시스템 대비 크게 나쁘다고 권고 | https://raw.githubusercontent.com/docker/docs/main/content/manuals/engine/storage/volumes.md · https://raw.githubusercontent.com/docker/docs/main/content/manuals/engine/storage/bind-mounts.md · https://raw.githubusercontent.com/docker/docs/main/content/manuals/desktop/features/wsl/best-practices.md | 원문(소스) | 상 | R-5(명명 볼륨, 바인드 금지) 근거. 권한 측면: Windows 폴더를 PostgreSQL 데이터로 바인드하면 `chmod` 실패("Operation not permitted") 보고가 다수(포럼, 일화) → 명명 볼륨이 일관되게 해결책으로 언급됨(확신도 중). 단 명명 볼륨은 Docker Desktop VM 내부 디스크에 있어 Windows 탐색기로 직접 못 보므로 백업은 `pg_dump` 경유(W-016) |
| 1-7 | `read_only: true`·`cap_drop`·`security_opt: no-new-privileges`·`tmpfs`·`pids_limit`·`init`·`user`·`mem_limit`은 모두 Compose 참조에 존재. `no-new-privileges`는 값 생략 시 활성으로 취급. `tmpfs`는 `mode/uid/gid` 옵션 | 위 services.md | 원문(소스) | 상 | D-03·D-14 구현 수단 확인. Linux 컨테이너라 Windows 호스트 여부와 무관하게 동일 키 사용 가능(Docker Desktop은 Linux VM에서 실행 — 1-6의 서술 근거) |
| 1-8 | **공식 `postgres` 이미지 + `read_only` + `cap_drop: ALL`**: 이미지 Dockerfile에는 `USER` 지시가 없고 `docker-entrypoint.sh`가 gosu로 root→postgres 강하/`chown`을 하도록 설계(Dockerfile의 gosu 주석 확인). 문서는 임의 `--user`(예: `user: 999:999`) 실행을 허용하되 `initdb`는 `/etc/passwd`에 해당 UID가 필요하다고 명시. STOPSIGNAL은 `SIGINT` | https://raw.githubusercontent.com/docker-library/postgres/master/18/trixie/Dockerfile · https://raw.githubusercontent.com/docker-library/docs/master/postgres/content.md | 원문(소스) | 중(추론 포함) | `cap_drop: ALL`을 그대로 걸면 root로 시작하는 기본 엔트리포인트(gosu·chown)가 실패할 수 있다고 **추정**한다(문서에 직접 서술 없음). 선택지: (a) `user: "999:999"`(postgres 이미지의 postgres UID로 추정 — `[확인 필요: UID 값 이미지에서 확인]`) + `cap_drop: ALL`, (b) 필요한 capability(`CHOWN`, `SETUID`, `SETGID`, `DAC_OVERRIDE`, `FOWNER`)만 `cap_add`. 어느 쪽이든 **설계 단계에서 이론 확정 금지, 사용자 PC 또는 데몬 확보 시 실측** |
| 1-9 | `read_only` + postgres: 데이터 볼륨은 쓰기 가능하게 두고 `/tmp`, `/run/postgresql`(소켓)에 `tmpfs`가 필요하다는 것이 일반 관행이나, 이번 조사에서 공식 문서의 직접 근거는 못 찾음 | 근거 없음(일반 관행, 추정) | 해당 없음 | 하 | `[확인 필요: 실측]`. 실패 시 대안으로 db만 `read_only` 예외로 두고 사유를 위협 모델에 기록 |
| 1-10 | Compose 파일 기반 secrets: 컨테이너의 `/run/secrets/<이름>`에 파일로 마운트. 서비스별로 명시 부여. 접근 제어는 표준 파일시스템 권한에 의존하며 문서는 기본 소유자·모드를 명시하지 않음. 지원은 **Linux 컨테이너만**(Compose가 단일 파일을 바인드 마운트). `_FILE` 환경변수(예: `POSTGRES_PASSWORD_FILE`)는 Compose 기능이 아니라 이미지가 지원해야 하는 관례. 환경변수 방식은 감사 곤란·로그 유출 위험으로 비권장 | https://raw.githubusercontent.com/docker/docs/main/content/manuals/compose/how-tos/use-secrets.md | 원문(소스) | 상 | 한계: 포럼 답변(Swarm 기준)은 compose에서는 긴 구문의 `mode`가 적용되지 않고 호스트 파일의 모드가 유지된다고 한다(커뮤니티, 요약만, 확신도 하). Windows 호스트 파일을 secrets로 줄 때 비루트(api/worker) 컨테이너 사용자가 읽을 수 있는지, 다른 컨테이너도 읽을 수 있는지는 문서에 없음 → `[확인 필요: 사용자 PC 실측 — 컨테이너에서 ls -l /run/secrets]`. 대안: 앱이 시작 시 secret을 읽어야 하므로 api/worker 사용자가 읽을 수 있는 모드가 되도록 `start.ps1`이 secret 파일을 생성·점검 |
| 1-11 | `docker compose down -v`/`--volumes`: Compose 파일 `volumes:`에 선언된 **명명 볼륨**과 컨테이너에 붙은 익명 볼륨을 **삭제**한다. `external` 볼륨과 네트워크는 삭제 대상이 아님. 옵션 없이는 볼륨 유지. `-t/--timeout` 기본값이 문서에 `0`으로 표기됨(의미는 서비스별 `stop_grace_period` 사용으로 추정) | https://raw.githubusercontent.com/docker/compose/main/docs/reference/compose_down.md (열람) · 보조: https://docs.docker.com/reference/cli/docker/compose/down.md (검색 요약만) | compose 원문 열람 / docs.docker.com은 요약 | 상 | D-07 근거. **운영 데이터 볼륨을 `external: true`로 선언**(수동 생성)하면 `down -v`가 실수로도 지우지 못한다 — 후보 설계안(단, 이 경우 첫 실행 시 `docker volume create` 필요). 종료 스크립트에 `-v` 금지 + 파괴적 명령은 별도 스크립트·확인 문구 |
| 1-12 | 종료 대기: `stop_grace_period` 기본 10초 후 SIGKILL, `stop_signal` 미지정이면 SIGTERM. `init: true`는 신호 전달·좀비 수거. 헬스체크·`depends_on: condition: service_healthy` 지원. `restart`는 `no`/`always`/`on-failure`/`unless-stopped` | services.md (위) | 원문(소스) | 상 | PostgreSQL 이미지는 STOPSIGNAL=SIGINT(fast shutdown). 기본 10초가 대용량 쓰기·체크포인트 시 부족할 수 있으므로 db는 30~60초 같은 값을 설계에서 정하되 값은 `[확인 필요: 실측]`. api/worker는 SIGTERM 수신 시 진행 중 작업을 안전 지점에서 멈추는 로직(W-010)과 `stop_grace_period`를 함께 설계 |
| 1-13 | 재시작 정책과 PC 재부팅: 포럼 보고에 Windows 전체 재부팅 후 `restart: unless-stopped` 컨테이너 일부가 종료 상태로 남는 사례가 있고 확정된 해법·공식 설명은 없음. Docker Desktop 자동 시작은 기본 꺼짐(1-2) | https://forums.docker.com/t/some-container-exited-after-host-machine-reboot-some-are-running/144966 (요약) | 요약 `[확인 필요: 원문 미열람]` | 하(일화) | W-008의 "켜지면 이어서 처리하되 몰아서 실행하지 않음"을 **재시작 후에도 앱이 자동으로 안 떠 있을 수 있다는 전제**로 설계. 홈 화면에 마지막 워커 하트비트 시각 표시 제안 |
| 1-14 | `internal: true` 네트워크는 외부와 격리됨(Compose 네트워크 참조). 같은 문서는 `internal`과 포트 게시의 상호작용을 설명하지 않음 | https://raw.githubusercontent.com/docker/docs/main/content/reference/compose-file/networks.md | 원문(소스) | 상(격리 정의) / 하(게시 상호작용) | R-3·D-10 구성안: `db`는 `internal` 네트워크에만. `web`은 호스트 게시가 필요하므로 비-internal 네트워크에도 연결(내부 네트워크만 붙은 컨테이너는 포트 게시가 안 될 것으로 **추정**, `[확인 필요: 실측]`). `api`/`worker`는 구글·AI로 나가야 하므로 외부 접근 가능한 네트워크에도 연결 필요 → "web: edge+internal / api,worker: internal+egress / db: internal만" 3-네트워크 구성이 후보. 요청문의 "web만 호스트 게시" 원칙과 일치 |

## 2. Docker Desktop 라이선스 (항목 2) — 법률 자문이 아님

| # | 사실 | 근거 URL | 열람 | 확신도 | 이 프로젝트 시사점 |
|---|---|---|---|---|---|
| 2-1 | Docker 구독 서비스 약정 "Last updated on August 26, 2026". 유료 구독 없이 독립 Docker Desktop을 쓸 수 있는 경우(§3.2): (a) 비상업 오픈소스 프로젝트, (b) **직원 250명 미만 AND 연매출 US$10,000,000 미만**의 상업 활동(또는 환산 통화). 정부 기관은 유료 구독 필요 | https://www.docker.com/legal/docker-subscription-service-agreement/ | 원문(직접 열람, 서브 모델 요약) | 상 | 개인 크리에이터가 자기 채널용으로 쓰는 사례는 (b)에 해당할 가능성이 높으나, 해당 여부는 **사용자가 약정 원문으로 확인**해야 한다(Q-9). 임계값 산정 방식(직원·매출 측정)은 페이지에 정의가 없음 |
| 2-2 | Personal Service Subscription(§3.1(b)) "Developer Use"는 "개인이 비상업적 자격으로 **오픈소스 또는 무료 애플리케이션을 개발**"하는 경우로 서술되고, 회사·기관 고용/계약과 관련된 사용은 제외. "Educational Use"는 교실 학습 환경에 등록된 개인의 학문·연구 목적. Docker는 사용 감사 후 유료 전환을 요구할 수 있음. §3.3(a)(8): 무료 계정으로 고용주 등 상업 주체에 서비스를 제공하는 것 금지 | 위와 동일 | 원문(직접 열람, 서브 모델 요약) | 중 | 이전의 "개인 사용 무료"라는 통상 인식보다 문구가 좁다(Developer Use는 OSS·무료 앱 개발). 이 프로젝트는 비공개 개인 도구이므로 §3.1(b)보다 §3.2(b)(소규모 상업) 경로가 해당될 가능성이 크다고 **추정**. 최종 판단은 사용자 책임, 에이전트는 판단하지 않음 |
| 2-3 | 유료 요금(참고): 출처마다 상이(2021 출시가 $5/7/21 vs 2024 인상 후 Pro $9·Team $15·Business $24 서술 vs 2026 제3자 사이트 $11/16/24). 공식 요금 페이지는 못 열람 | https://toolradar.com/tools/docker/pricing · https://costbench.com/software/developer-tools/docker/free-plan/ (검색 요약) | 요약 `[확인 필요: 원문 미열람]` | 하 | 가격은 설계·기획 의사결정에 필요하지 않음. 11단계 문서에는 금액을 쓰지 않고 "약정 페이지 확인" 안내만 |
| 2-4 | Docker Engine 등 오픈소스 구성요소의 라이선스 조건은 Desktop 약정과 별개(제3자 해설) | https://www.usu.com/en/blog/quick-guide-to-docker-licensing (검색 요약) | 요약 | 중 | 대안(Docker Desktop 대신 WSL2 내 Docker Engine 직접 설치)은 가능하나 사용자 PC 지원·`start.ps1` 복잡도 증가 → 범위 밖 제안, 사용자 확인 사항 |

## 3. PostgreSQL (항목 3)

| # | 사실 | 근거 URL | 열람 | 확신도 | 이 프로젝트 시사점 |
|---|---|---|---|---|---|
| 3-1 | 지원 메이저와 종료일(2026-10-10 기준): **18**(출시 2025-09-25, 종료 2030-11-14, 최신 18.6), **17**(2024-09-26, 2029-11-08, 17.11), **16**(2023-09-14, 2028-11-09, 16.15), **15**(2022-10-13, 2027-11-11, 15.19), **14**(2021-09-30, **2026-11-12**, 14.24 — 곧 종료), 13은 2025-11-13 종료. 커뮤니티 정책은 메이저당 5년 지원(제3자 글) | https://raw.githubusercontent.com/endoflife-date/endoflife.date/master/products/postgresql.md (열람) · 보조: https://www.instaclustr.com/education/postgresql/postgres-versions-supported-releases-eol-dates-upgrades/ · https://wz-it.com/en/blog/postgresql-14-end-of-life-upgrade-guide/ (검색 요약) | endoflife.date 소스 열람(2차 집계). **postgresql.org 공식 versioning 페이지는 도메인 열람 불가** `[확인 필요: 공식 원문 미열람]` | 중-상(2차 집계 + 검색 요약이 일치) | 18 또는 17 선택이 후보. 18은 종료까지 ~4.1년, 17은 ~3.1년. 결정은 3단계 ADR(DEC-035). 신규 프로젝트에 15 이하는 비권장 |
| 3-2 | PostgreSQL 19는 정식 아님: Docker Hub에 `19beta4` 태그만 존재(2026-10-07 갱신), `19` 정식 태그는 해당 쿼리 1페이지에서 미확인. 제3자 글은 19를 "2026-10 발표 예정"으로 서술 | https://hub.docker.com/v2/repositories/library/postgres/tags?name=19&page_size=6 (열람) | 원문(API) | 상 | 운영 DB로 19 베타 금지 |
| 3-3 | 공식 이미지 태그·다이제스트(2026-10-10 조회, 인덱스 다이제스트): `18`/`18.6`/`18-trixie`/`18.6-trixie` = `sha256:74935e72…c4336`(2026-10-07), `18.6-bookworm` = `sha256:afc7e2d4…a647c`, `18.6-alpine` = `sha256:77f58511…a1873`, `17.11`/`17.11-trixie` = `sha256:2d2b8998…ddf9e3`, `17.11-bookworm` = `sha256:36455 70c…b6e..`(전체 값은 6장 부록 참조 불가, 아래 주석) | https://hub.docker.com/v2/repositories/library/postgres/tags?name=18&page_size=10 · …?name=17.&page_size=6 | 원문(API) | 상(값 자체) | 다이제스트는 **빌드 시점에 다시 조회해서 고정**한다(위 값은 조사 시점 스냅샷이며 주기적으로 갱신됨). 고정 방식: `image: postgres:18.6-trixie@sha256:<인덱스 다이제스트>` — 태그는 사람이 읽는 표시, 실제 해석은 다이제스트. 인덱스 다이제스트는 멀티 아키텍처(amd64/arm64) 공통 |
| 3-4 | 이미지 사용법: `POSTGRES_PASSWORD_FILE`은 `_FILE` 규약으로 `POSTGRES_INITDB_ARGS`, `POSTGRES_PASSWORD`, `POSTGRES_USER`, `POSTGRES_DB`에만 지원. `POSTGRES_USER`는 **슈퍼유저**를 만든다. `/docker-entrypoint-initdb.d`의 `*.sql`/`*.sh`는 **데이터 디렉터리가 비어 있을 때만** 실행(sorted 순). PG 18+는 PGDATA가 버전별 경로(`/var/lib/postgresql/18/docker`)이고 VOLUME은 `/var/lib/postgresql`; 17 이하는 `/var/lib/postgresql/data` 마운트이며 18 방식으로 `/var/lib/postgresql`에 마운트하면 컨테이너 재생성 시 데이터가 유지되지 않을 수 있다는 경고 | https://raw.githubusercontent.com/docker-library/docs/master/postgres/content.md | 원문(소스) | 상 | 앱 전용 롤 생성은 초기화 스크립트(최초 1회)와 **Alembic 마이그레이션 단계 롤/권한 부여**로 이원화해야 한다. 이미 초기화된 볼륨에서는 초기화 스크립트가 안 돌므로, 비밀번호 변경·롤 추가는 별도 절차(마이그레이션 단계 또는 `psql` 관리 스크립트) 필요. 마운트 경로는 선택한 메이저에 맞게 고정 |
| 3-5 | `pg_hba` 기본: 이미지는 `POSTGRES_HOST_AUTH_METHOD` 기본 `scram-sha-256`(PG14+), **로컬(소켓) 연결은 `trust`** 이므로 컨테이너 안에서 `psql`을 실행하면 비밀번호 없이 접속된다. `pg_hba.conf`는 위에서 아래로 첫 일치 규칙을 사용하며 일치 규칙이 없으면 거부. `md5`는 deprecated(향후 제거), `scram-sha-256` 권장 | docker-library content.md (위) · https://raw.githubusercontent.com/postgres/postgres/REL_18_STABLE/doc/src/sgml/client-auth.sgml | 원문(소스) | 상 | "pg_hba로 컴포즈 내부 네트워크만 허용"(D-07a)은 (a) db를 `internal` 네트워크에만 붙이고, (b) 커스텀 `pg_hba.conf`(읽기 전용 마운트)로 앱 롤은 내부 서브넷 `scram-sha-256`만 허용, 그 외 `reject`로 구현 후보. 소켓 `trust`는 `docker compose exec db psql` 점검 편의이자 위험(컨테이너 안 접근 = 슈퍼유저)이므로 위협 모델에 기록. 서브넷 CIDR은 compose 네트워크에 `ipam`으로 고정해야 pg_hba에 쓸 수 있음 |
| 3-6 | 앱 전용 최소권한 롤 패턴: 객체 소유자는 항상 그 객체를 변경·삭제할 수 있고(권한 철회 불가 고유 권리), 일반 권한은 소유자가 스스로 철회 가능. 테이블 권한 부여가 시퀀스 권한을 자동 포함하지 않음. `TRUNCATE`는 `DELETE`와 별개 권한. `ALTER DEFAULT PRIVILEGES`로 향후 생성 객체의 기본 권한 지정 가능. PG15부터 새 DB의 `public` 스키마 `CREATE` 권한이 DB 소유자 외에는 회수됨(새 클러스터·DB 한정) | https://raw.githubusercontent.com/postgres/postgres/REL_18_STABLE/doc/src/sgml/ddl.sgml · …/ref/grant.sgml (열람) · PG15 변경: https://www.percona.com/blog/public-schema-security-upgrade-in-postgresql-15/ (검색 요약) | ddl/grant 원문 열람, PG15 건은 요약 `[확인 필요: 원문 미열람]` | 상(ddl·grant) / 중(PG15) | 3-롤 구성 후보: (1) 슈퍼유저(`POSTGRES_USER`, 평소 앱이 쓰지 않음, 비밀번호 secret), (2) 마이그레이션/스키마 소유 롤(DDL), (3) 앱 런타임 롤(필요한 테이블에 SELECT/INSERT/UPDATE만, 시퀀스는 `USAGE`/`SELECT`를 별도 부여 — 시퀀스 `USAGE` 요건은 문서에서 직접 확인 못함 `[확인 필요]`). 앱이 슈퍼유저를 쓰는 것은 금지(요청문 §11-2) |
| 3-7 | `SELECT … FOR UPDATE SKIP LOCKED`: 잠금 불가 행을 건너뛴다. 문서는 "일관되지 않은 뷰를 제공"하므로 **범용 용도가 아니며** 큐 형태 테이블에서 다수 소비자의 경합 회피에 쓸 수 있다고 서술. `LIMIT` 사용 시 필요한 행이 확보되면 잠금을 멈춘다. `WITH TIES`와 함께 사용 불가 | https://raw.githubusercontent.com/postgres/postgres/REL_18_STABLE/doc/src/sgml/ref/select.sgml | 원문(소스) | 상 | R-4 근거. 잠금은 트랜잭션 동안만 유지되므로 "잡 가져오기 → 상태 `running`·리스(임대) 만료 시각 기록 → 커밋" 후 외부 호출(YouTube)을 트랜잭션 밖에서 하고, 완료 시 다시 트랜잭션으로 갱신하는 패턴이 필요(크래시 시 리스 만료로 회수). 외부 API 호출 전에 사용량 예약을 같은 트랜잭션에 기록(S-W12). 큐 소비자는 워커 1개로 시작해 중복 가능성을 줄이되 SKIP LOCKED·고유 제약은 방어로 유지 |
| 3-8 | 어드바이저리 락: 세션 수준 락은 명시 해제 또는 세션 종료까지 유지되며 **트랜잭션 롤백에도 유지**. 같은 락을 여러 번 얻으면 해제도 그만큼 필요. 트랜잭션 수준 락은 트랜잭션 종료 시 자동 해제. `LIMIT`과 함께 락 함수를 쓰면 의도치 않은 락이 세션 끝까지 남을 수 있음. 일반 락과 공유 메모리 풀을 쓰며 고갈 시 서버가 어떤 락도 못 줄 수 있음. (함수 이름 `pg_try_advisory_xact_lock` 등은 이 페이지에 없고 별도 함수 참조 필요) | https://raw.githubusercontent.com/postgres/postgres/REL_18_STABLE/doc/src/sgml/mvcc.sgml | 원문(소스) | 상 | "배치 실행 중복 방지"에는 트랜잭션 수준 `pg_try_advisory_xact_lock`을 쓰고 락 키는 배치/영상 ID에서 도출. 세션 수준 락은 커넥션 풀 환경에서 누수 위험 → 지양. 함수명·시그니처는 `[확인 필요: 함수 참조 원문 미열람]` |
| 3-9 | 추가 전용(append-only) 감사 테이블: 문서상 확인된 것은 (a) `REVOKE`로 `UPDATE`/`DELETE`/`TRUNCATE`를 개별 철회 가능, (b) 소유자는 고유 권한을 항상 가짐(3-6), (c) `BEFORE TRUNCATE` 트리거는 **문장 수준에서만** 가능(create_trigger 원문 열람), (d) 행 수준 BEFORE 트리거는 해당 행의 동작을 건너뛸 수 있다는 서술. 해시 체인·pgAudit 관련은 검색 결과가 없거나 단편적 | https://raw.githubusercontent.com/postgres/postgres/REL_18_STABLE/doc/src/sgml/ref/create_trigger.sgml · grant.sgml · ddl.sgml; pgAudit/wiki는 https://wiki.postgresql.org/wiki/Audit_trigger_91plus (검색 요약) | 일부 원문, 일부 요약 | 중 | 후보 설계: 감사 테이블은 **소유 롤(마이그레이션 롤)이 소유**, 앱 롤에는 `INSERT`·`SELECT`만 부여(`UPDATE/DELETE/TRUNCATE` 미부여), 추가로 `BEFORE UPDATE OR DELETE` 행 트리거와 `BEFORE TRUNCATE` 문장 트리거에서 예외를 던져 방어(심층방어), 각 행에 이전 행 해시를 담는 해시 체인 컬럼. **한계(명시)**: 소유자·슈퍼유저는 우회 가능하고 해시 체인은 변조를 "탐지"할 뿐 막지 못한다. 앱 롤이 슈퍼유저가 아니라는 전제와 마이그레이션 롤 비밀 분리가 핵심. 해시 체인 검증 시점·주기는 설계서에서 정함 |
| 3-10 | 헬스체크 `pg_isready`: 종료코드 0=정상 수락, 1=거부(예: 시작 중), 2=무응답, 3=시도 안 함(잘못된 인자). **인증 정보 유효성은 검사하지 않으며** 잘못된 사용자·DB 이름을 줘도 상태를 알려 주고 서버 로그에 실패 시도가 남는다. 기본 타임아웃 3초 | https://raw.githubusercontent.com/postgres/postgres/REL_18_STABLE/doc/src/sgml/ref/pg_isready.sgml | 원문(소스) | 상 | compose `healthcheck.test: ["CMD-SHELL","pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]` 형태(비밀번호 불필요, 로그 오염 최소화를 위해 실제 존재하는 롤/DB를 지정). 이는 "연결 수락"만 보증 → `/readyz`는 앱 롤로 `SELECT 1`과 마이그레이션 버전까지 확인 필요(W-017). `start_period`·`interval` 값은 `[확인 필요: 실측]` |
| 3-11 | 백업·복원: `pg_dump`는 동시 사용 중에도 일관된 내보내기를 만들고 읽기·쓰기를 막지 않음. 사용자 정의 형식 `-Fc`는 `pg_restore`로 선택 복원 가능하고 기본 압축. **단일 DB만** 덤프하며 롤·테이블스페이스는 `pg_dumpall`(`--globals-only` 등) 필요. 자기보다 새 메이저 서버는 덤프 불가. 병렬(`-j`)은 디렉터리 형식만. 문서는 단순한 경우 외 "정기 백업의 일반 해법이 아니다"라고도 서술. 복원: `pg_restore --list`로 목차 확인, `--clean --if-exists`, `--single-transaction`(= `--exit-on-error` 포함, `--jobs`와 병용 불가), `-d`로 직접 복원, 새 DB는 `createdb -T template0` 후 복원 권장, 소유자 변경은 슈퍼유저 또는 전 객체 소유자만 가능하며 `--no-owner`로 회피 가능 | https://raw.githubusercontent.com/postgres/postgres/REL_18_STABLE/doc/src/sgml/ref/pg_dump.sgml · …/ref/pg_restore.sgml | 원문(소스) | 상 | W-016 절차 후보: (1) 컨테이너 안에서 `pg_dump -Fc`를 실행해 **백업 전용 명명 볼륨 또는 컨테이너 내 경로**에 저장하고 `docker cp`로 꺼낸다. (2) 파워셸의 `>` 리디렉션으로 바이너리 덤프를 받으면 인코딩 변환으로 손상될 수 있다는 것이 일반 지식이나 **이번 조사에서 출처를 못 찾음** → `[확인 필요: 실측]`, 그래서 호스트 리디렉션을 쓰지 않는 설계를 권장. (3) 검증: 임시 DB(`harness-tmp` 접두)에 `createdb -T template0` 후 `pg_restore --single-transaction --exit-on-error`로 복원하고, 핵심 테이블 건수·해시 체인 검증·마이그레이션 버전을 원본과 비교. (4) 복원은 같은 또는 더 새로운 메이저 서버에만(덤프 규칙). 롤은 덤프에 없으므로 복원 대상 DB에 롤이 이미 있어야 하거나 `--no-owner`+권한 재부여 스크립트 필요. (5) 토큰·비밀은 DB 밖(S-W13a)이어야 백업 파일에 섞이지 않음 |
| 3-12 | 시간대: `timestamp with time zone`은 입력 시 UTC로 변환해 내부 저장하고 **원래 시간대는 보존되지 않음**, 출력은 세션 `TimeZone`으로 변환. `timestamp without time zone`은 시간대 표기를 조용히 무시. 시간대 포함 타입 사용을 권고 | https://raw.githubusercontent.com/postgres/postgres/REL_18_STABLE/doc/src/sgml/datatype.sgml | 원문(소스) | 상 | 모든 시각 컬럼은 `timestamptz`. 앱 롤의 `ALTER ROLE … SET timezone='UTC'`(또는 접속 옵션)으로 세션도 UTC로 고정. 화면 표시만 `Asia/Seoul`(D-09), 구글 쿼터 초기화(태평양 시간)는 앱 로직에서 `zoneinfo`로 계산 — 컨테이너의 `tzdata` 존재 확인 필요(slim 이미지는 `tzdata`가 없을 수 있음 `[확인 필요]`; 기존 의존성에 `tzdata` 파이썬 패키지가 있음) |
| 3-13 | PostgreSQL 18 변경: 새 클러스터의 `initdb`가 **데이터 체크섬을 기본 활성화**(제3자 해설이 릴리스 노트를 인용). `pg_upgrade` 시 원본·대상 체크섬 설정이 같아야 함 | https://www.crunchydata.com/blog/postgres-18-new-default-for-data-checksums-and-how-to-deal-with-upgrades · https://www.credativ.de/en/blog/postgresql-en/postgresql-18-enables-datachecksums-by-default/ | 요약 `[확인 필요: 공식 릴리스 노트 원문 미열람]`(release-18.sgml 열람 시도는 일부만 읽혀 해당 절 미확인) | 중 | 18 선택 시 유리(디스크 손상 탐지). 메이저 업그레이드 절차는 이 프로젝트 범위 밖이므로 "메이저 변경 = 덤프/복원으로 이전"을 11단계 Runbook에 명시하는 편이 안전 |
| 3-14 | 연결 수 상한(D-07a): `max_connections`는 공유 메모리와 락 풀 크기에 영향(어드바이저리 락 서술 3-8). 구체 권장값은 이번 조사에서 별도 근거를 못 찾음 | mvcc.sgml (위) | 부분 | 하 | api 풀 크기 + worker + 점검용 여유로 소수(예: 수십 이하)로 제한. 값은 설계서에서 정하고 부하 시험으로 확인 `[확인 필요]` |

## 4. 베이스 이미지·빌드 도구 (항목 4)

| # | 사실 | 근거 URL | 열람 | 확신도 | 이 프로젝트 시사점 |
|---|---|---|---|---|---|
| 4-1 | `python:3.12-slim` = `3.12-slim-trixie`(Debian 13) 별칭, 인덱스 다이제스트 `sha256:a6e34c59…c11b1`(2026-10-09 갱신). `3.12-slim-bookworm` = `sha256:34386ef0…07a258`(2026-10-06). Python 3.12는 **보안 수정만**(활성 지원 종료 2025-04-02) 2028-10-31까지, 3.13은 활성 지원이 2026-10-01에 끝났고 보안 지원 2029-10-31, 3.14는 2027-10-01(활성)/2030-10-31, 3.15는 2026-10-09 출시. 3.12 최신 패치 3.12.15 | https://hub.docker.com/v2/repositories/library/python/tags?name=3.12-slim&page_size=10 · https://raw.githubusercontent.com/endoflife-date/endoflife.date/master/products/python.md | 원문(API/소스, 2차 집계) | 상(태그·다이제스트) / 중-상(일정) | 요청문 D-04의 `python:3.12-slim`은 존재·갱신 중. 단, 3.12는 보안 전용 단계이며 기존 CLI는 "3.12 이상(검증 3.13.9)". 어느 마이너로 고정할지는 ADR 사항(3.12 유지 시 호환 위험 최소, 3.13/3.14는 지원 기간이 더 김). 다이제스트는 빌드 시 재조회 |
| 4-2 | Debian: 13 Trixie(출시 2025-08-09, LTS 종료 2030-06-30), 12 Bookworm(2023-06-10, 2028-06-30), 11 Bullseye는 2026-08-31 LTS 종료(이미 종료). 3.12-slim-bullseye는 2025-07 이후 갱신 없음 | https://raw.githubusercontent.com/endoflife-date/endoflife.date/master/products/debian.md · python 태그(위) | 원문(소스, 2차 집계) | 중-상 | bullseye 금지. trixie(`-slim-trixie`) 또는 bookworm 택일, 기본 해석 `3.12-slim`은 현재 trixie를 가리키므로 **OS 세대를 태그에 명시**(`-slim-trixie`)해야 다이제스트 갱신 시 의도치 않은 OS 변경 방지 |
| 4-3 | Node: 24는 LTS 2025-10-28, 활성 지원 종료 2026-10-20(10일 후), 유지보수 종료 2028-04-30; **26은 2026-05-05 출시, LTS 진입 2026-10-28**, 종료 2029-04-30; 22는 유지보수 2027-04-30까지; 20은 2026-04-30 종료. Docker Hub `node:lts-slim` 태그 존재(`sha256:d6aa754f…87b20`, 2026-10-06 갱신), 가리키는 Node 메이저는 이 조회로는 미확인 | https://raw.githubusercontent.com/endoflife-date/endoflife.date/master/products/nodejs.md · https://hub.docker.com/v2/repositories/library/node/tags?name=lts-slim&page_size=10 | 원문(소스/API) | 중-상 | 빌드 단계 전용이라 최종 이미지에는 포함되지 않지만 빌드 체인 취약점은 존재. `lts-slim`은 이동 태그이므로 메이저를 명시(`24-slim` 또는 26 LTS 진입 후 `26-slim`)하고 다이제스트 고정. 선택 메이저는 `[확인 필요]`(프런트 의존성 호환 확인 후 결정) |
| 4-4 | nginx: 안정 1.30(2026-04-14, 최신 1.30.5), 메인라인 1.31(2026-05-13, 1.31.6); 1.29는 2026-05-13 종료. Docker Hub `nginxinc/nginx-unprivileged` 최신 태그에 `1.31.6`·`stable-*`·`mainline-*` 존재(Perl 변형 태그가 먼저 노출). 비루트 이미지의 정확한 수신 포트·권한 모델은 이번 조사에서 원문 미열람 | https://raw.githubusercontent.com/endoflife-date/endoflife.date/master/products/nginx.md · https://hub.docker.com/v2/repositories/nginxinc/nginx-unprivileged/tags?page_size=12&ordering=last_updated | 원문(소스/API) | 중 | 정적 파일+프록시 용도라 stable 라인 선호 후보. `nginx-unprivileged`는 1024 이상 포트(일반적으로 8080)를 쓰는 것으로 **알려져** 있으나 `[확인 필요: 원문 미열람]` → 포트 게시 `127.0.0.1:${PORT}:8080` 가정은 실측 필요. 읽기 전용 파일시스템에서는 `/tmp`·캐시·pid 경로에 tmpfs가 필요할 가능성 `[확인 필요: 실측]` |
| 4-5 | 멀티 스테이지 빌드, 다이제스트 고정, `.dockerignore`는 요청문 D-04·D-05에 이미 정의됨. 이번 조사에서 BuildKit 비밀 마운트 등 세부 문서는 열람하지 못함 | 해당 없음 | 미조사 | — | `[확인 필요]` 빌드 시 비밀(npm 토큰 등)이 필요 없으므로 영향 작음 |
| 4-6 | **Trivy 공급망 침해**: 2026-03-19 18:24 UTC~03-23 01:36 UTC 동안 Docker Hub의 `aquasec/trivy` 태그 `0.69.4`, `0.69.5`, `0.69.6`, `latest`가 악성(인포스틸러)이었고 Docker가 제거. 안전한 마지막 버전은 `0.69.3`. 악성 다이제스트 3개 공개. 권고: 다이제스트 고정, 침해 노출 시 자격증명 일괄 회수, Docker 소켓 마운트 상태로 실행했다면 호스트 전체 침해 간주. (GitHub 어드바이저리 GHSA-cxm3-wv7p-598c, `trivy-action` 태그 강제 푸시 등은 제3자 요약) | https://www.docker.com/blog/trivy-supply-chain-compromise-what-docker-hub-users-should-know/ (열람, 게시일 2026-03-23) | 원문(서브 모델 요약) | 상 | 이후 Docker Hub 현재 태그: `0.75.0` = `latest` = `sha256:af6acf9a…855daa`(2026-10-01). Trivy 라이선스 Apache-2.0(저장소 LICENSE 열람). 9단계 계획: 버전·다이제스트 고정, **Docker 소켓 마운트 금지**(D-03과 일치), 이미지 tar를 `docker save` 후 파일로 스캔하는 방식 선호, CI에서 `trivy-action` 사용 시 커밋 SHA 고정 `[확인 필요]`. 이 사고는 "안전 도구도 공급망 대상"이라는 증거 |
| 4-7 | Docker Scout: 이미지 구성 인벤토리(SBOM)를 만들고 취약점 DB와 대조. CLI/Hub/대시보드에서 사용. **무료 범위가 출처별로 상충**: (a) docs 요약 "Scout Free = 최대 3개 Scout 활성 저장소 + 로컬 이미지 분석 무제한(검색 요약 인용)", (b) Docker 문서 `scout/_index.md` 원문 "Personal 구독은 최대 1개 저장소", (c) 2024-12 요금제 공지·제3자는 "1개(3→1 축소)" | https://raw.githubusercontent.com/docker/docs/main/content/manuals/scout/_index.md (열람) · https://docs.docker.com/subscription/scout-details/ (검색 요약만) | (b) 원문 / (a)(c) 요약 `[확인 필요: 원문 미열람]` | 하(상충) | 상충 사실을 그대로 보고: "1개 vs 3개". **로컬 이미지 분석**(저장소 연동 없이)이 무료 범위에 드는지도 출처가 갈린다. 따라서 9단계 주 도구는 Trivy(Apache-2.0, 무료), Scout는 보조·선택. SBOM은 Trivy `--format cyclonedx|spdx` 또는 buildx `--sbom` 후보 `[확인 필요: 명령 실측]` |

## 5. 파이썬 의존성·스택 버전 (항목 5, PyPI JSON 직접 열람, 2026-10-10)

| 패키지 | 안정 버전 | 업로드일 | 라이선스(PyPI 메타) | requires-python | 비고 |
|---|---|---|---|---|---|
| FastAPI | 0.143.0 | 2026-10-08 | MIT | ≥3.10 | 분류자 "Development Status :: 4 - Beta"(0.x, 호환성 깨짐 가능 → 정확 버전 고정). 의존: `starlette>=0.46.0`, `pydantic>=2.9.0` |
| Pydantic | 2.14.0 | 2026-10-08 | MIT | ≥3.10 | v2 계열(3.9 지원 중단, 3.15 추가) |
| Uvicorn | 0.54.0 | 2026-09-25 | BSD-3-Clause | ≥3.10 | |
| SQLAlchemy | 2.1.4 | 2026-10-07 | MIT | **≥3.11** | 분류자 "Production/Stable". **상충**: 검색 요약은 2.1이 아직 프리릴리스(rc2, 2026-09-08 블로그)라고 하나 PyPI JSON은 2.1.4가 안정 분류로 2026-10-07 게시. PyPI를 1차 근거로 하되 `[확인 필요: SQLAlchemy 공식 다운로드/체인지로그 미열람]`. 2.0.x 계열 대안 존재 여부·지원 기간은 미조사 |
| Alembic | 1.20.0 | 2026-09-11 | MIT | ≥3.10 | SQLAlchemy 2.1과의 호환 선언은 미확인 `[확인 필요]` |
| psycopg (v3) | 3.3.6 | 2026-09-18 | **LGPL-3.0-only** | ≥3.10 | LGPL: 로컬 개인 사용·비배포라 부담은 작으나, 이미지를 외부에 배포할 경우 의무 검토 필요(법률 자문 아님). `psycopg[binary]`(libpq 동봉) vs `psycopg[c]`(빌드 도구 필요) 선택은 ADR |
| uv | 0.13.0 | 2026-10-09 | MIT OR Apache-2.0 | ≥3.8 | 0.x(빠른 변경). 저장소 LICENSE-MIT 열람(Astral Software Inc.) |
| pip-tools | 7.6.2 | (미확인) | BSD-3-Clause | ≥3.9 | 파일은 OS·파이썬 버전별로 달라질 수 있어 **대상 환경에서 각각 컴파일** 권고(README) |

근거 URL: `https://pypi.org/pypi/<패키지>/json` 및 버전별 `…/<버전>/json`(모두 열람). 확신도 상(1차 레지스트리). 라이선스는 `license_expression` 필드값이며 법적 해석은 아님. pip-tools 업로드일과 FastAPI/psycopg 외 일부 일자는 응답 절단으로 미확인.

해시 고정 잠금:
- pip 해시 검사 모드: 요구사항에 `--hash`가 하나라도 있으면 전체 필수("all-or-nothing"), 모든 의존성이 `==` 핀+해시를 가져야 하며 sha256 권장, 플랫폼별 휠이 여러 개면 해시 여러 개 필요. (https://raw.githubusercontent.com/pypa/pip/main/docs/html/topics/secure-installs.md, 원문, 상)
- pip-tools: `pip-compile --generate-hashes`. 대상 환경별 별도 컴파일 권고(README 원문, 상).
- uv: `uv pip install/sync --require-hashes`와 빌드 의존성용 `--require-build-hashes`는 문서 원문에서 확인. `--generate-hashes` 및 유니버설 해석은 이 조사에서 해당 페이지에 없어 `[확인 필요: uv pip compile 참조 미열람]`.
- 시사점: 컨테이너(리눅스)용 잠금 파일은 **리눅스 대상**으로 생성해야 하며 Windows에서 생성하면 휠 해시 집합이 달라 컨테이너 빌드가 실패하거나 누락될 수 있다. 빌드 도구는 컨테이너(Dockerfile 빌드 단계) 안에서 잠금 생성·검증을 수행하는 설계가 안전. S-W11의 "실제 존재 확인"은 PyPI JSON 조회로 자동화 가능(이번 조사에서 동일 방식으로 확인).

## 6. 테스트용 임시 PostgreSQL (항목 6)

### 6-1. 수행하지 못한 것 (정직한 보고)
`pip download --no-deps`, `apt-get download` 실제 실행은 **하지 못했다**(이 에이전트에 Bash 도구가 없음). 결과를 "성공/실패"로 쓰지 않고 "미수행"으로 기록한다. 대신 아래 증거를 얻었다.

### 6-2. 확인된 사실 (Glob/Grep/Read/WebFetch)

| # | 사실 | 확인 방법 | 확신도 | 시사점 |
|---|---|---|---|---|
| 6-1 | 환경 OS: Ubuntu 24.04.5 LTS (noble) | `/etc/os-release` 읽기 | 상 | |
| 6-2 | **PostgreSQL 16.15 서버 패키지가 설치됨**: dpkg 상태에 `postgresql-16 16.15-0ubuntu0.24.04.1`, `postgresql-client-16`, `postgresql-common 257build1.1`, `libpq5` "install ok installed". `/usr/lib/postgresql/16/bin/`에 `postgres`, `initdb`, `pg_ctl`, `pg_isready`, `pg_dump`, `pg_restore`, `pg_dumpall`, `psql`, `pgbench`, `pg_basebackup` 등 존재. `/etc/postgresql/16/main/`(설정) 존재, `/etc/passwd`에 `postgres`(uid 102) 계정 존재. `/usr/bin/psql`은 없고(래퍼 미설치) 바이너리는 위 경로에 있음 | Glob · Grep(`/var/lib/dpkg/status`) · Grep(`/etc/passwd`) | 상(파일·패키지 상태). 기동 가능 여부는 미시도 | 데몬 없이 로컬 프로세스로 PostgreSQL 서버를 띄우는 가장 현실적인 방법. **설치 불필요**. 호출자(Bash 보유)가 확인할 절차 후보: (a) 루트면 `su postgres`(PostgreSQL은 루트로 실행 거부)로 `initdb -D <프로젝트>/.harness-tmp/pg/data -A scram-sha-256`(또는 테스트 전용 `trust`) → `pg_ctl -D … -o "-c listen_addresses='' -c unix_socket_directories=<…>/sock" start`(TCP 비활성, 유닉스 소켓만), (b) 시험 후 `pg_ctl stop -m fast` + 디렉터리 삭제(규칙 K, `trap`/janitor 연동), (c) 포트·소켓은 `.harness-tmp` 아래 고정 경로 사용해 사용자 운영 DB와 충돌 방지. 위 실행 가능성은 `[확인 필요: 미시도]` |
| 6-3 | **버전 차이 위험**: 환경은 PG 16.15, 운영 후보는 17/18. 문법/동작 차이로 테스트 통과가 운영 통과를 보증하지 못하는 항목: PG18의 체크섬 기본값, PG18 전용 기능(예: `uuidv7()`), 18의 PGDATA 레이아웃. `SKIP LOCKED`·어드바이저리 락·`timestamptz`·`REVOKE`·`pg_dump -Fc`는 16/18 공통의 오래된 기능 | 추론(위 3장 원문 + 설치 버전) | 중 | 스키마·마이그레이션은 16에서도 돌도록 **공통 부분집합**만 쓰거나, 운영 메이저를 16으로 낮추는 대신 7~8단계 통합 테스트를 "로컬 16 프로세스 + 사용자 PC의 Docker(운영 메이저) 확인" 이원화. 최종 PASS는 운영 메이저로 실측해야 한다는 규칙을 결과서에 반영 |
| 6-4 | **dockerd 실행 파일도 존재**: `/usr/bin/dockerd`, `/usr/bin/containerd`, `/usr/bin/runc` Glob 확인. dpkg: `docker-ce 5:29.8.2`, `docker-ce-cli 5:29.8.2`, `containerd.io 2.3.6`, `docker-compose-plugin 5.6.0`, `docker-buildx-plugin 0.37.1`. `/var/run/docker.sock`은 없음(데몬 미기동) | Glob · Grep(dpkg status) | 상 | **DEC-033의 "데몬이 없다"는 "데몬이 안 떠 있다"로 보는 게 사실에 맞다**. 호출자가 `dockerd`를 백그라운드로 기동해 보는 시도가 필요하다(커널의 cgroup·네트워크 필터·overlay 지원 여부는 이 조사로 확인 불가 `[확인 필요: 미시도]`). 기동되더라도 (1) 레지스트리(Docker Hub) 접근은 데몬이 프록시를 직접 알아야 함, (2) 컨테이너 안에서는 프록시 `127.0.0.1:40293`에 닿지 않고 CA를 신뢰하지 않음 — `/root/.ccr/README.md`가 "docker build/run" 항목에서 `--network host`, CA 번들 복사, 프록시 설정 명시 전달을 안내함. 이 때문에 **데몬이 떠도 이미지 pull·빌드가 막힐 가능성**이 있음 `[확인 필요]` |
| 6-5 | 이 환경 프록시를 통한 HTTPS 열람 가능한 곳: `pypi.org`(JSON), `raw.githubusercontent.com`, `hub.docker.com`(v2 API), `www.docker.com`, `download.docker.com`(우분투 `Packages` 인덱스 456KB가 열림), `archive.ubuntu.com`(HTTPS `Release` 파일 열림). 실패: `www.postgresql.org`, `postgresql.org`, `docs.docker.com`, `endoflife.date`, `registry.hub.docker.com`, `wz-it.com`(DNS 해석 실패 `ENOTFOUND`), `api.github.com`(403), `github.com` 일부(503) | WebFetch 결과 | 상(관측) | WebFetch가 열린 도메인이 `pip`/`apt`에서도 열리는지는 별개(다른 클라이언트, apt는 `http://`·포트 80 사용 설정이어서 프록시가 HTTPS만 지원함과 충돌 가능). `/etc/apt/sources.list.d/ubuntu.sources`의 URI가 `http://archive.ubuntu.com/…`임을 확인 → `apt-get download`가 막힐 가능성 `[확인 필요: 미시도]` |
| 6-6 | PyPI 대안 후보: **pgserver 0.1.4**("Self-contained postgres server for your python applications"; 번들 PostgreSQL **16.2**; 라이선스 메타 null; 최신 파일 목록·업로드일 미확인), **pytest-postgresql 9.1.1**(LGPL-3.0-or-later; 2026-10-04; `postgresql_proc` 픽스처는 로컬 PostgreSQL **서버 설치 필요**, 이미 서버 바이너리가 있으면 사용 가능, `postgresql_noproc`는 외부 서버 사용), **testing.postgresql 1.3.0**(Apache-2.0; 2016-02-04 이후 릴리스 없음 → 사실상 방치, 비권장) | PyPI JSON 열람 | 중-상 | 현실적 선택: **이미 설치된 PG16 바이너리 + `pytest-postgresql`의 `postgresql_proc`(바이너리 경로 지정) 또는 직접 `initdb/pg_ctl` 래퍼**. `pgserver`는 번들 버전이 16.2로 오래되었고 라이선스 불명 → 신규 의존성은 S-W11 절차(존재·라이선스·취약점)를 거쳐야 하며 지금 도입을 권하지 않음. 패키지 설치는 이 조사에서 하지 않았다 |
| 6-7 | 호출자가 실행할 확인 명령(제안, 비밀·설치 없음): `pip download --no-deps --dest <프로젝트>/.harness-tmp/dl pgserver==0.1.4`, `apt-get download postgresql-16` (모두 `.harness-tmp/dl` 아래에서, 끝나면 삭제), `ls -l /usr/lib/postgresql/16/bin/postgres`, `dockerd` 백그라운드 기동 가능 여부(`docker info`) | — | — | 결과는 `[확인 필요: 미시도]` 상태로 둔다 |

## 7. 설계 요구사항 후보 (임시 ID — 2단계 이후 정식 REQ/SEC/POL로 재부여)

| 임시 ID | 후보 요구사항 | 근거 항목 |
|---|---|---|
| B-NET-01 | 호스트 게시는 `web` 하나, compose에 `127.0.0.1:${PORT}:<컨테이너포트>` 형태로만 선언하고 `0.0.0.0`/IP 생략 금지. 검증 절차(netstat/`Get-NetTCPConnection`, `docker compose port`, 다른 기기 접속 실패)를 10단계 구동 검증서와 9단계 보안 점검에 포함. **클라우드에서는 실측 불가 → "미수행(사유)"로 기록하고 PASS 계수 금지** | 1-3~1-5, DEC-033 |
| B-NET-02 | 네트워크 3분할 후보: `edge`(web, 비-internal), `internal`(web·api·worker·db, `internal: true`), `egress`(api·worker만, 구글·AI 접근). `db`는 `internal`에만 연결. 내부 네트워크는 `ipam` 서브넷 고정 | 1-14, 3-5 |
| B-HARD-01 | 모든 컨테이너: 비루트 `user`, `read_only: true`(필요 경로만 `tmpfs`/볼륨), `cap_drop: ALL`, `security_opt: no-new-privileges`, `pids_limit`, `mem_limit`, `init: true`. 공식 `postgres`·`nginx-unprivileged`에 대한 호환성은 실측 후 예외를 위협 모델에 기록 | 1-7~1-9, 4-4 |
| B-VOL-01 | 운영 데이터 볼륨은 명명 볼륨(권장: `external: true` 사전 생성으로 `down -v` 보호). 바인드 마운트 금지(`/mnt/c` 성능·권한 문제). `down -v`는 일반 종료 스크립트에 없음, 별도 파괴 스크립트에 확인 문구 | 1-6, 1-11 |
| B-DB-01 | PG 메이저 선택(후보 18 또는 17)은 ADR로 확정. 이미지는 `태그@sha256:인덱스다이제스트`로 고정하고 빌드 시 재조회·갱신 절차를 문서화. 마운트 경로를 메이저에 맞춤 | 3-1~3-4 |
| B-DB-02 | 롤 3분리(슈퍼유저/스키마 소유/앱 런타임), 앱 런타임은 슈퍼유저 금지, 최소 권한(`ALTER DEFAULT PRIVILEGES` 포함), 시퀀스 권한 별도 부여, 비밀번호는 `POSTGRES_PASSWORD_FILE` 및 앱용 secrets, 연결 문자열 로그 금지 | 3-4, 3-6 |
| B-DB-03 | `pg_hba`: 내부 서브넷만 `scram-sha-256`, 그 외 `reject`. 소켓 `trust`에 대한 잔여 위험 문서화 | 3-5 |
| B-DB-04 | 감사 로그 테이블: 소유 롤 분리 + 앱 롤 `INSERT`/`SELECT`만 + `UPDATE/DELETE/TRUNCATE` 거부 트리거 + 해시 체인, 한계(소유자·슈퍼유저 우회, 탐지 전용) 명시, 체인 검증 작업 | 3-6, 3-9 |
| B-DB-05 | `pg_isready` 헬스체크 + 앱 `/readyz`에서 앱 롤 `SELECT 1`·마이그레이션 버전 확인(헬스체크가 인증을 검사하지 않음) | 3-10 |
| B-DB-06 | 모든 시각은 `timestamptz`(UTC), 세션 UTC 고정, 화면 `Asia/Seoul`, 쿼터 초기화는 태평양 시간으로 앱에서 계산(DST 포함 가능성 `[확인 필요]`) | 3-12 |
| B-Q-01 | 작업 큐: `FOR UPDATE SKIP LOCKED`로 잡 획득 → 상태·리스 기록 후 커밋 → 외부 호출은 트랜잭션 밖 → 완료 시 갱신. 리스 만료 회수, 고유 제약과 `Idempotency-Key`로 이중 반영 방지. 배치 중복 방지는 트랜잭션 수준 어드바이저리 락 | 3-7, 3-8 |
| B-BAK-01 | 백업: 컨테이너 내부에서 `pg_dump -Fc` → 호스트로 `docker cp`(파워셸 리디렉션 지양), 암호화·보관 위치·보관 기간 결정 필요(사용자). 복원 검증: 임시 DB 복원 후 건수·해시체인·마이그레이션 버전 대조, 롤 사전 존재 또는 `--no-owner`+권한 스크립트, 메이저 동일/상향 복원만 허용 | 3-11 |
| B-OPS-01 | 종료/재시작: db `stop_grace_period` 상향(값은 실측), api/worker는 SIGTERM에서 안전 중단, 재시작 후 워커는 놓친 예약을 몰아서 실행하지 않음, Docker Desktop 자동 시작은 기본 꺼짐이며 재부팅 후 컨테이너가 안 올라올 수 있다는 전제로 홈에 하트비트 표시 | 1-2, 1-12, 1-13 |
| B-OPS-02 | `start.ps1` 사전 점검: Docker Desktop 실행, `wsl --version`≥2.1.5, OS 빌드, 가상화, 포트 점유, secrets 파일 존재·권한, 한국어 안내 | 1-1 |
| B-IMG-01 | 베이스 이미지: `python:3.12-slim-trixie`(또는 확정 마이너), `node` 빌드 단계(메이저 명시), `nginxinc/nginx-unprivileged` stable 라인, 모두 다이제스트 고정, OS 세대 명시, bullseye 금지 | 4-1~4-4 |
| B-SEC-01 | 이미지 취약점·SBOM: Trivy(버전·다이제스트 고정, `latest` 금지, Docker 소켓 마운트 금지, 이미지는 tar 파일로 스캔 선호), Scout는 보조(무료 범위 상충으로 의존 금지). 공급망 사고 사례를 위협 모델에 반영 | 4-6, 4-7 |
| B-DEP-01 | 파이썬 잠금: 해시 고정 + `--require-hashes`, 리눅스 대상 환경에서 생성, FastAPI 0.x·uv 0.x 정확 버전 고정, PyPI 존재·라이선스·취약점 점검 자동화. psycopg LGPL, SQLAlchemy 2.1 안정성·Alembic 호환 확인 | 5장 |
| B-TST-01 | 클라우드 테스트 DB: 설치된 PG16.15를 `.harness-tmp` 아래 임시 클러스터(TCP 비활성, 유닉스 소켓)로 기동·종료·삭제, 운영 메이저와의 차이를 결과서에 명시하고 최종 PASS는 운영 메이저 실측으로만 인정. `dockerd` 기동 가능 여부는 호출자가 시도 | 6장 |
| B-LIC-01 | Docker Desktop 라이선스 해당 여부는 사용자가 약정 원문으로 확인(법률 자문 아님). 문서에 판단을 쓰지 않고 확인 안내만 | 2장 |

## 8. [확인 필요] 목록

1. 사용자 PC: Windows 에디션·빌드, WSL 버전, Docker Desktop 실행·WSL2 백엔드 여부, 자동 시작 설정 (요청문 §2-3에서도 미확인).
2. Docker Desktop(Windows)에서 `127.0.0.1:포트` 게시가 실제 루프백 한정인지 — 공식 Desktop 문서 미확인, 커뮤니티 보고 상충. 사용자 PC 실측 필수.
3. docs.docker.com·postgresql.org 원문(요약만 확보한 항목 전부): Windows Home 에디션 지원, 요금표, Scout 무료 범위(1 vs 3), PG 공식 versioning 페이지, PG18 릴리스 노트 체크섬 문구, PG15 `public` 스키마 변경 원문.
4. 공식 `postgres` 이미지의 `cap_drop: ALL`·`read_only`·비루트(`user`) 조합 동작과 UID 값.
5. `nginx-unprivileged`의 수신 포트·읽기 전용 파일시스템 시 필요한 tmpfs 경로.
6. Windows 호스트 secrets 파일의 컨테이너 내 소유자/모드와 비루트 읽기 가능 여부.
7. 파워셸 `>` 리디렉션의 바이너리 덤프 손상 여부(일반 지식, 출처 미확보)와 `docker cp` 절차 실측.
8. db `stop_grace_period` 적정값, `healthcheck` 간격, `max_connections` 값 — 실측 또는 근거 필요.
9. `dockerd`를 이 클라우드 환경에서 기동할 수 있는지, 기동돼도 이미지 pull·build가 프록시 때문에 가능한지.
10. PG16 클러스터를 `.harness-tmp`에 만들어 기동·종료까지 되는지(루트→`postgres` 사용자 전환 포함) — 호출자 시도 필요.
11. `pip download`·`apt-get download` 실제 결과(본 조사에서는 미수행).
12. SQLAlchemy 2.1 안정 선언 근거(공식)와 Alembic 호환, 2.0.x 대안의 지원 기간.
13. uv `--generate-hashes`/리눅스 대상 잠금 생성 명령 원문.
14. Dependabot/Renovate가 다이제스트 고정 이미지를 자동 갱신하는지(도구 선택).
15. `internal: true` 네트워크와 포트 게시의 상호작용(위 B-NET-02는 추정).
16. 법적 판단 영역: Docker 라이선스 해당 여부, psycopg(LGPL) 배포 의무 — 에이전트가 판단하지 않음. 공개 배포 계획이 생기면 법률 자문 필요.

## 9. 규칙 B 자체 검증 기록

### 1차 (출처·근거 점검 — 각 주장에 출처가 달렸는가)
- 점검 방법: 1~6장의 모든 행에 URL, 열람 상태, 확신도가 있는지 행 단위로 확인.
- 발견한 결함과 조치:
  1. 3-3에서 `17.11-bookworm` 다이제스트를 도중에 잘못 줄여 적은 문장이 있었다(값이 깨진 표기). → 해당 값은 신뢰할 수 없으므로 **다이제스트는 "빌드 시 재조회" 원칙으로 일원화**하고, 이 문서에서 직접 인용한 값은 앞부분 일부만 남겼다. 사용자가 이 값을 복사해 쓰지 않도록 본문에 명시. (전체 값이 필요하면 Docker Hub API를 다시 조회)
  2. 1-5의 "Desktop 프록시가 모든 인터페이스에 바인딩" 주장은 단일 비공식 출처라 확신도를 "하"로 낮추고, 상충을 숨기지 않고 그대로 병기했다.
  3. SQLAlchemy 2.1 안정 여부가 검색 요약(프리릴리스)과 PyPI(안정 분류, 2.1.4)에서 상충 → 5장에 상충으로 기재.
  4. Scout 무료 범위 1 vs 3 상충 → 4-7에 상충으로 기재, 단정하지 않음.
  5. 3-1(PG 지원 일정)은 postgresql.org를 못 열어 2차 집계(endoflife.date 소스) + 검색 요약 두 갈래가 일치하는 것으로만 "중-상" 처리.
  6. 서브 모델이 요약한 열람 결과를 원문으로 오인하지 않도록 "서브 모델 요약" 표기를 붙임(2장).
- 시사점이 조사 내용에서 도출됐는지: 7장 각 후보에 근거 항목 번호를 달았고, 근거 없는 후보(1-9, 4-5, 3-14)는 "추정/확인 필요"를 병기했다.
- 결과: 위 6건 조치 후 출처 누락 0건. 단 "1차 PASS"는 근거 표기 기준이며 사실의 정확성을 보증하지 않는다(서브 모델 요약 의존).

### 2차 (이 보고서만 보고 기획서·설계서를 쓸 사람 관점)
- 빠진 정보 점검:
  1. **실측이 필요한 결정 사항이 설계 승인 게이트 전에 해결 불가능**하다는 점을 명시했는지 → 7장 B-NET-01, 8장 2·4·5·6번에 "사용자 PC 또는 데몬 확보 시 실측" 명시. OK.
  2. 6번 요청(`pip download`/`apt-get download` 실제 시도)이 미수행임을 상단 한계와 6-1에 명시, 대체 증거·호출자 실행 명령 제공. 이는 요청 미충족이며 PASS로 포장하지 않았다.
  3. DEC-033 전제에 영향을 주는 새 사실(PG16 서버 설치됨, `dockerd` 파일 존재)을 6-2·요약 3줄에 노출. OK.
  4. 규칙 I(규제 민감 업종)·규칙 J(AI 규제)는 이 축의 범위가 아님 → "해당 없음(타 축 담당: 구글 OAuth/AI/약관/규제)". 다만 AI 키 등 secrets 보관은 B-HARD/secrets 항목으로 연결.
  5. 한국 법규: Docker 라이선스(해외 약관)만 다룸. 개인정보보호법 등은 타 축. 해당 없음(사유: 컨테이너·DB 인프라 축).
  6. 도메인 운영 규칙(6번 섹션 취지)에 해당하는 이 축의 특이 케이스를 별도로 뽑았다: Docker Desktop 자동 시작 꺼짐(재부팅 후 미기동), `internal` 네트워크 게시 제약, 초기화 스크립트는 빈 볼륨에서만 실행, 메이저별 볼륨 경로 차이, `pg_isready`가 인증 미검사. 이 항목들은 일반 경계값 테스트로 발견되지 않는다.
  7. 놓친 가능성: Windows Defender 방화벽/백신이 Docker 포트에 미치는 영향, IPv6(`::1`) 게시, Docker Desktop 업데이트 정책 — 이번 조사에서 다루지 못함 → 아래 "미조사" 목록에 추가.
- 미조사(숨기지 않음): BuildKit 비밀 마운트, Docker Desktop 업데이트/자동 업데이트 정책, IPv6 루프백 게시, Windows 방화벽, 로그 드라이버 `max-size` 동작 세부, `.dockerignore` 문법 세부, `pg_stat` 모니터링, 연결 풀러, Docker Desktop 미사용 대안(WSL 내 Engine)의 상세.
- 결과: 2차에서 추가 보완 1건(상기 7번의 미조사 목록 추가) 반영 후 구조적 결함 0건. 단 **실측 의존 항목이 다수 남아 있어 이 조각은 "조사 완료"이지 "검증 완료"가 아니다**. 취합 시 이를 `01-trend-analysis.md` 7장(리스크·불확실성)에 반영해야 한다.

## 10. 열람 성공/실패 도메인 표 (WebFetch 기준, 2026-10-10)

| 도메인 | 결과 | 비고 |
|---|---|---|
| www.docker.com | 성공 | 구독 약정 페이지, Trivy 사고 블로그 |
| hub.docker.com (`/v2/repositories/…`) | 성공 | postgres·python·node·nginx-unprivileged·aquasec/trivy 태그와 다이제스트 |
| registry.hub.docker.com | 실패(ENOTFOUND) | |
| docs.docker.com | 실패(ENOTFOUND) | 대신 `raw.githubusercontent.com/docker/docs/main/content/…` 소스로 대체 열람(일부 경로 404) |
| raw.githubusercontent.com | 성공(경로 정확 시) | docker/docs, docker-library/*, postgres/postgres, endoflife-date, pypa/pip, jazzband/pip-tools, astral-sh/uv, aquasecurity/trivy(LICENSE). 추측한 경로 일부 404(docker 정책·Scout 라이선스 문서, desktop 네트워킹, `docker compose down` 문서 경로 일부) |
| pypi.org (`/pypi/<pkg>/json`) | 성공 | 응답이 커서 일부 필드는 절단(재조회로 보완) |
| github.com | 부분 | `issues/13182` 성공, `docker-library/postgres` blob 페이지 503 |
| api.github.com | 실패(403) | |
| www.postgresql.org / postgresql.org | 실패(ENOTFOUND) | 대신 `raw.githubusercontent.com/postgres/postgres/REL_18_STABLE/doc/src/sgml/…` 소스로 대체 열람 |
| endoflife.date | 실패(ENOTFOUND) | 대신 `raw.githubusercontent.com/endoflife-date/endoflife.date/master/products/*.md` 열람 |
| wz-it.com | 실패(ENOTFOUND) | 검색 요약만 사용 |
| archive.ubuntu.com (HTTPS) | 성공 | `Release` 파일 |
| download.docker.com | 성공 | 우분투 noble `Packages` 인덱스 |
| WebSearch 결과로만 접한 곳 | 요약만 | forums.docker.com, instaclustr, crunchydata, credativ, percona, usu.com, toolradar, costbench, microsoft/WSL issue, skrog issue 등 모두 `[확인 필요: 원문 미열람]` |

## 11. Teardown (규칙 K)

- 이 조사는 `/home/user/youtube-subject-modify-auto/.harness-tmp/` 아래에 **아무 파일도 만들지 않았다**(Glob으로 `.harness-tmp/**` 조회 시 파일 없음 확인). 패키지 설치, 컨테이너·클러스터 기동, `pip download`/`apt-get download` 실행을 하지 않았으므로 정리할 임시 아티팩트가 없다.
- 예외 1건: WebFetch가 `download.docker.com`의 우분투 `Packages` 인덱스(약 456KB)를 도구 결과 캐시로 자동 저장했다. 위치는 `/root/.claude/projects/-home-user-youtube-subject-modify-auto/f7d07e96-32d2-5d13-ab91-d6446e424ae2/tool-results/webfetch-1791644132242-20uy25.bin`(프로젝트 밖, 하네스 도구의 세션 캐시이며 저장소에 포함되지 않음). 이 에이전트는 삭제 도구가 없어 삭제하지 못했다. 비밀값이 아닌 공개 패키지 인덱스다.
- 저장소 변경은 이 조각 파일 하나뿐이다: `docs/harness/_parallel/01-axisB-docker-postgres.md`. 코드·설정 파일은 수정하지 않았고, 비밀값은 쓰지 않았다.

## 12. 타 축 참고

- (규제·약관 축) Docker 구독 약정 §3.3(a)(8)은 "무료 계정으로 고용주 등 상업 주체에 서비스를 제공하는 것"을 금지한다. 사용자가 채널을 회사/대행 목적으로 운영한다면 라이선스 판단이 달라질 수 있다.
- (LLM·기술 축) AI 키·OAuth 토큰·세션 키는 B-HARD/secrets 설계와 동일 경로로 다루고, db에는 두지 않는다(S-W13a). `egress` 네트워크 분리는 아웃바운드 제한(D-10) 설계의 기반.
- (구글 OAuth 축) 리디렉션 URI는 호스트 게시 주소(`127.0.0.1:<포트>`)와 정확히 일치해야 하므로 포트 선택은 인프라(포트 충돌 처리)와 OAuth 클라이언트 등록이 함께 결정해야 한다.
- (도메인 운영 규칙 축) 구글 쿼터 초기화는 태평양 시간 기준으로 알려져 있어(D-09) DB는 UTC, 앱이 시간대 변환을 책임지는 구조가 필요하다.
