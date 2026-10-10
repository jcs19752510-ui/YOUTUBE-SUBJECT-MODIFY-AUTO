> 초안 — 6단계 검증·7~10단계 후 대조 필요

# ytitle 웹 설치 안내 (Windows 10/11 + Docker Desktop, 데모 모드)

> **지금은 데모 모드입니다.** 설치하면 가짜 영상 200개와 가짜(모의) AI로 연습하는 화면이 열립니다. 유튜브·AI 서비스에는 **아무것도 전송되지 않고**, 실제 영상 제목은 바뀌지 않습니다. 실제 구글·AI 연결은 이후 단계에서 별도 승인 후에만 추가됩니다.
> **이 안내의 한계**: 명령과 순서는 `web/README.md` 와 `web/scripts/*.ps1` 을 읽고 정리했습니다. 이 안내를 쓴 환경(클라우드 Linux)에는 PowerShell과 Windows Docker Desktop이 없어 **Windows에서 직접 실행해 보지 못했습니다** [확인 필요]. 그래서 각 단계마다 "이렇게 보이면 성공"을 적었으니, 다르게 보이면 멈추고 `WEB_FAQ.md` 를 확인하세요.

기준 문서: `web/README.md`(모순이 있으면 `web/README.md` 와 스크립트가 우선이며, 불일치는 알려 주세요). 쓰는 법은 `WEB_USER_MANUAL.md`.

---

## 1. 준비물 체크

| 필요한 것 | 확인 방법 |
|---|---|
| Windows 10 또는 11 | 시작 > 설정 > 시스템 > 정보 |
| **Docker Desktop** (Linux 컨테이너 모드) | 시작 메뉴에서 "Docker Desktop" 실행 → 작업 표시줄 고래 아이콘이 "실행 중"이 될 때까지 대기 |
| **WSL2** (Docker Desktop 기본 방식) | PowerShell에서 `wsl --status`. 오류가 나면 `wsl --update` 후 PC 재시작 |
| PC 가상화 켜짐 | 작업 관리자 > 성능 > CPU > "가상화: 사용". "사용 안 함"이면 PC 제조사 안내에 따라 BIOS 설정 필요 (Windows 기능 "가상 머신 플랫폼"도 켜져 있어야 함) |
| 인터넷 연결 (처음 한 번, 이미지·패키지 내려받기) | - |
| 디스크 여유 약 3GB, 메모리 여유 약 2GB | Docker Desktop 설정 > Resources |
| 빈 포트 **8080** | 다른 프로그램이 쓰고 있으면 시작 때 알려 줍니다 |
| 최신 Chrome 또는 Edge, 화면 폭 1024px 이상 | - |
| 이 저장소 폴더 (예: `C:\big21\vibe-coding\YOUTUBE-SUBJECT-MODIFY-AUTO`) | 폴더 안에 `web` 폴더가 있어야 합니다 |

**Docker Desktop 라이선스**: 회사 규모에 따라 유료일 수 있습니다. 해당 여부는 선생님이 Docker 약관에서 직접 확인하세요 (이 프로그램은 판단하지 않습니다).

---

## 2. 설치·첫 실행 (순서대로)

### 단계 1. Docker Desktop 실행
1. 시작 메뉴 > Docker Desktop.
2. 고래 아이콘이 움직임을 멈추고 "실행 중"이 될 때까지 1~2분 기다립니다.
3. 성공 신호: Docker Desktop 창에 "Engine running" 같은 상태가 보입니다 [확인 필요: 실제 문구는 버전마다 다름].
4. 아이콘 오른쪽 클릭 메뉴에 "Switch to Windows containers..." 가 보이면 정상(= 지금 Linux 모드)일 것으로 보입니다 [확인 필요]. "Switch to Linux containers..." 가 보이면 그것을 눌러 바꿉니다.

### 단계 2. PowerShell 열고 폴더로 이동
```powershell
cd C:\big21\vibe-coding\YOUTUBE-SUBJECT-MODIFY-AUTO
```
폴더 위치가 다르면 실제 위치로 바꾸세요. 성공 신호: 프롬프트가 그 폴더 경로로 바뀝니다.

### 단계 3. 이 창에서만 스크립트 허용
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```
이 창을 닫으면 원래대로 돌아갑니다(컴퓨터 전체 설정은 바뀌지 않습니다). 새 창을 열 때마다 다시 입력합니다.

### 단계 4. 시작
```powershell
.\web\scripts\start.ps1 -OpenBrowser
```
스크립트가 알아서 하는 일: Docker 확인 → 비밀번호 파일 만들기(처음 한 번, 값은 화면에 안 나옴) → 포트 확인 → 이미지 빌드·시작 → 준비 대기 → 주소 안내. **첫 실행은 5~15분** 걸릴 수 있으니 창을 닫지 마세요.

진행 중 보이는 메시지(`[안내]` 글자): `1/5 Docker 확인` → `2/5 비밀 파일 확인` → `3/5 포트 확인` → `4/5 이미지 빌드 및 컨테이너 시작` → `5/5 준비될 때까지 대기`.

성공 신호:
```
준비 완료!  브라우저에서 열기:  http://127.0.0.1:8080
```
그리고 브라우저가 열립니다.

주의 메시지: 비밀 파일을 처음 만들 때 "web\secrets 폴더는 데이터베이스 비밀번호입니다. 지우거나 다른 곳에 올리지 마세요." 가 나옵니다. 정상입니다. 이 폴더는 지우지 말고, 값은 누구에게도 보여 주지 마세요.

### 단계 5. 첫 화면 확인
- 접속 주소: **<http://127.0.0.1:8080>** (이 PC에서만 열립니다. 같은 와이파이의 다른 기기에서는 열리지 않는 것이 정상입니다.)
- 화면 위쪽에 노란 띠 **"데모 모드 — 유튜브에 아무것도 전송되지 않습니다"** 와 "서버 연결됨"이 보여야 합니다.
- 왼쪽 메뉴: 홈 / 영상 목록 / 배치(일괄 반영) / 이력·롤백 / 성과 리포트 / 설정.
- 홈에서 **[데모 영상 불러오기]** 를 눌러 영상 200개가 생기면 설치 완료입니다. 이어서 `WEB_USER_MANUAL.md` 를 따라가세요.

### 단계 6. 상태 점검 (권장)
```powershell
.\web\scripts\status.ps1
```
성공 신호: 모든 서비스가 "정상", `migrate` 는 "마이그레이션 완료", 호스트 포트는 `127.0.0.1:8080->8080/tcp` 하나뿐, 마지막 줄이 "점검 결과: 문제 없음". `[위험]` 표시가 있으면 `WEB_RUNBOOK.md` 의 장애 대응을 보세요.

### 단계 7. 끄기 / 다시 켜기
- 끄기: `.\web\scripts\stop.ps1` (데이터 보존)
- 다시 켜기: Docker Desktop 실행 후 `.\web\scripts\start.ps1` (코드를 바꾸지 않았다면 `-NoBuild` 를 붙이면 빠릅니다)
- PC를 껐다 켜면: Docker Desktop은 자동으로 시작되지 않으니 직접 실행한 뒤 `start.ps1`.

---

## 3. 설치 후 내 PC에서 꼭 확인할 것 (체크리스트)

클라우드(Linux)에서는 확인하지 못했고 **선생님 PC에서만 확인할 수 있는** 항목입니다 (`web/README.md` 8장). 결과를 운영 담당에게 알려 주세요.

- [ ] 1. `start.ps1` 이 끝까지 성공하고 <http://127.0.0.1:8080> 이 열린다.
- [ ] 2. `status.ps1 -Detail` 에 `[위험]` 표시가 없고, "이 PC 의 포트 8080 리스너는 루프백(127.0.0.1)뿐입니다." 가 나온다. 같은 와이파이의 다른 기기(휴대폰)에서 `http://<내 PC IP>:8080` 이 **열리지 않는다**.
- [ ] 3. 브라우저에서 F12 키 → "콘솔" 탭에 "Content Security Policy" 오류가 없다.
- [ ] 4. `backup.ps1` → `restore.ps1 -Latest` (확인 문구 `복원합니다`)가 성공하고 행 수가 일치한다.
- [ ] 5. `stop.ps1` 후 `start.ps1` 해도 데이터가 남아 있다. PC를 재부팅한 뒤에도 Docker Desktop 실행 + `start.ps1` 로 복구된다.
- [ ] 6. (개발 담당용) 컨테이너 안에서 비밀 파일이 읽힌다: `docker compose -f web/compose.yaml exec api ls -l /run/secrets` — Windows에서의 읽기 권한 동작은 확인되지 않았습니다.

---

## 4. 자주 나는 문제

| 증상 | 원인과 조치 |
|---|---|
| "Docker 가 설치되어 있지 않거나 PATH 에 없습니다" | Docker Desktop 설치 후 PowerShell을 **새로** 열고 다시 실행 |
| "Docker 엔진에 연결할 수 없습니다" | Docker Desktop을 먼저 실행하고 고래 아이콘이 안정될 때까지 1~2분 기다린 뒤 다시 |
| "Docker 가 Windows 컨테이너 모드입니다" | 고래 아이콘 오른쪽 클릭 > Switch to Linux containers... |
| "Docker Compose 버전이 너무 낮습니다" | 2.20 이상이 필요합니다. Docker Desktop을 최신으로 업데이트 |
| "포트 8080 사용 중" | 다른 프로그램이 8080을 씁니다. `Get-NetTCPConnection -LocalPort 8080 -State Listen` 으로 `OwningProcess`(번호) 확인 → `Get-Process -Id 번호` 로 프로그램 이름 확인 → 그 프로그램 종료 후 다시 시작. (이 프로그램이 이미 켜져 있어서 나오는 경우는 없습니다) |
| WSL 관련 오류 | `wsl --update`, `wsl --shutdown` 후 Docker Desktop 재시작. 그래도 안 되면 PC 재시작. Windows 기능 "가상 머신 플랫폼"과 BIOS 가상화가 켜져 있어야 함 |
| "스크립트를 실행할 수 없습니다" | 단계 3의 `Set-ExecutionPolicy -Scope Process ...` 를 **같은 창**에서 먼저 실행 |
| 빌드 중 다운로드 실패 | 인터넷/사내 프록시 확인. 회사 네트워크가 암호화 통신을 가로채면 Docker Desktop에 인증서 설정이 필요할 수 있습니다 |
| 처음인데 오래 걸림 | 5~15분은 정상. 제한 시간(기본 300초) 안에 준비되지 않았다는 경고가 나오면 `.\web\scripts\logs.ps1` 로 확인하고 `start.ps1 -NoBuild -TimeoutSec 600` 처럼 대기 시간을 늘려 보세요 |
| "비밀 파일이 없는데 데이터베이스 볼륨은 이미 있습니다" | `web\secrets` 를 지웠기 때문입니다. 새 비밀번호를 만들면 기존 DB에 접속할 수 없으니, 백업해 둔 `web\secrets` 폴더를 되돌려 놓으세요. 데이터를 버리고 처음부터 시작하려면 `reset-demo.ps1 -DeleteVolumes` (**모든 데이터 삭제**, 확인 문구 `모든 데이터 삭제`) |
| 컨테이너가 계속 재시작 | `.\web\scripts\logs.ps1 -Service api` (또는 db / worker / migrate) 로 원인 확인 |
| 화면이 하얗게 나옴 | F12 콘솔의 "Content Security Policy" 오류 문구를 운영 담당에게 전달 |
| 브라우저에서 "연결할 수 없음" | 주소를 정확히 `http://127.0.0.1:8080` 로. 다른 주소·다른 포트는 열리지 않습니다 |

---

## 5. 설치하면서 조심할 것

- 설치 과정에서 `docker compose down -v`, `docker system prune --volumes`, Docker Desktop의 "Clean / Purge data" 는 **데이터가 영구 삭제**되니 사용하지 마세요.
- `web\secrets` 폴더는 지우거나 남에게 보내지 마세요.
- 베이스 이미지 갱신(`pin-digests.ps1`)은 설치 때가 아니라 정기 점검 때 합니다 (`WEB_RUNBOOK.md`).
- 개발자용 정보(구성, PostgreSQL 17 선택 이유, 테스트용 환경변수, 정적 점검 `python -m pytest web/tests_infra`)는 `web/README.md` 7장에 있습니다. 정적 점검 명령은 이 문서 작성 환경에 pytest가 없어 **실행해 보지 못했습니다** [확인 필요].

---

## 6. 이 안내에서 확인하지 못한 항목

| 항목 | 상태 |
|---|---|
| Windows 10/11에서 `start.ps1` 실제 실행 | 미확인 (PowerShell 없음) |
| Docker Desktop(WSL2) 포트 바인딩·파일 권한 | 미확인 |
| Docker Desktop 화면 문구("Engine running" 등) | 미확인 |
| 첫 실행 소요 시간 5~15분 | `web/README.md` 기재값, 직접 측정 안 함 |
| Windows PowerShell 5.1 호환 | 스크립트는 5.1·7 모두를 목표로 작성되었으나 실행 확인 안 됨 |
| 방화벽/보안 프로그램과의 충돌 | 미확인 |
