# B. PowerShell 스크립트 Linux 검증 결과 (pwsh 7.4.13)

시작 01:43:39Z, 종료 약 01:46Z(실측 약 2분 30초, 상한 12분 이내). 소스 편집·docker 사용·git 작업 없음. 시험 코드: `web/tests_fullcheck/b/`(parse.ps1, docker-shim.sh, fake-web.py).

**한 줄 결론:** `web/scripts/*.ps1` 13개 모두 pwsh 7.4.13 파서 오류 0건, 7 전용 문법 0건, 가짜 docker 로 실행한 status/live-* 의 논리는 기대대로 동작. 단 PowerShell 5.1 과 Windows 콘솔, icacls, Docker Desktop 에서의 실행은 확인하지 못했다. status.ps1 -Detail 의 이상 출력은 재현되지 않았다. 대신 `docker ps` 가 빈 결과일 때 포트 점검이 조용히 통과하는 논리상 약점을 확인했다.

## 1. pwsh 확보
`which pwsh` 없음 -> GitHub 공식 릴리스 v7.4.13 linux-x64 tar.gz(72MB)를 `.harness-tmp/pwsh` 에 받아 풀었다(프록시 경유, TLS 검증 유지, 해시·서명 검증은 하지 않음). `$PSVersionTable.PSVersion` = 7.4.13. 오류 없음.

## 2. 구문 검사·5.1 호환·BOM (parse.ps1 이 AST 로 판정)
| 파일 | 파서 오류 | 7 전용(?? ?. 삼항 && \|\| -Parallel -AsByteStream) | UTF-8 BOM | 비ASCII(한글) | 줄바꿈 |
|---|---|---|---|---|---|
| _common.ps1 | 0 | 없음 | 있음 | 있음 | LF |
| backup.ps1 | 0 | 없음 | 있음 | 있음 | LF |
| e2e.ps1 | 0 | 없음 | 있음 | 있음 | CRLF |
| live-check.ps1 | 0 | 없음 | 있음 | 있음 | LF |
| live-off.ps1 | 0 | 없음 | 있음 | 있음 | CRLF |
| live-on.ps1 | 0 | 없음 | 있음 | 있음 | CRLF |
| logs.ps1 | 0 | 없음 | 있음 | 있음 | LF |
| pin-digests.ps1 | 0 | 없음 | 있음 | 있음 | LF |
| reset-demo.ps1 | 0 | 없음 | 있음 | 있음 | LF |
| restore.ps1 | 0 | 없음 | 있음 | 있음 | LF |
| start.ps1 | 0 | 없음 | 있음 | 있음 | LF |
| status.ps1 | 0 | 없음 | 있음 | 있음 | LF |
| stop.ps1 | 0 | 없음 | 있음 | 있음 | LF |

- 5.1 이 BOM 없는 UTF-8 을 ANSI 로 읽는 문제: 13개 모두 BOM 이 있어 해당 없음(file 명령으로도 "UTF-8 (with BOM)" 확인). 단 작업 복사본을 Windows 에서 다른 편집기로 저장하면 BOM 이 사라질 수 있다(미확인 위험).
- 줄바꿈이 파일마다 LF/CRLF 로 섞여 있다(e2e, live-on, live-off 만 CRLF). PowerShell 은 둘 다 읽으므로 동작 영향은 없을 것으로 보이나 5.1 에서 확인하지 못했다.
- 사용 cmdlet 목록(AST)을 훑은 결과 모두 5.1 에도 있는 것들이다(Get-FileHash, Invoke-WebRequest -UseBasicParsing 등). `Split('|', 2)`(status.ps1 34행)은 .NET Framework 에 (string,int) 오버로드가 없어 5.1 에서는 char[] 로 변환되어 동작하는 방식이다. 5.1 에서의 실제 동작은 **확인하지 못함**.
- .bat 2개(live-on.bat, live-off.bat): ASCII/CRLF. `cd /d "%~dp0\..\.."` 후 `powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0live-on.ps1"` (live-off.bat 은 live-off.ps1) 호출, 끝에 pause. 호출 대상이 올바른 ps1 임을 읽어서 확인했다. 실행은 안 함(Windows 아님).

## 3. status.ps1 -Detail 재현 시험
방법: PATH 앞에 가짜 `docker`(docker-shim.sh)와 127.0.0.1:8080 가짜 응답 서버(fake-web.py, Content-Type application/json). 모드별 실제 출력:

| 모드 | 입력 | 기대 | 실제 |
|---|---|---|---|
| full | 5개 서비스 정상, web 만 127.0.0.1:8080 | 서비스 5줄, 포트 5줄+compose port+리스너 1줄, 응답 2줄, 보안 5줄, "문제 없음" | 모두 한 번씩, 중복·겹침 없음, exit 0 |
| partial | db/api/web 만 | migrate/worker "없음" 2건 | `[주의] migrate  없음`, `[주의] worker   없음`, 마지막 줄 `[주의] 점검 결과: 확인이 필요한 항목 2 건. 로그: .\web\scripts\logs.ps1`, exit 1 |
| empty | compose ps 빈 결과 | 경고 후 종료 | `[주의] 실행 중인 서비스가 없습니다. 시작: .\web\scripts\start.ps1`, exit 1 |
| badport | api 가 0.0.0.0:8000 게시 | [위험] | `[위험] api      0.0.0.0:8000->8000/tcp` 와 `:::8000->8000/tcp` 두 줄, 문제 2건, exit 1 |
| psempty | compose ps 정상, `docker ps` 빈 결과 | (설계 의도상) 포트 점검 불가 경고 | "호스트에 열린 포트" 구역에 서비스 줄이 하나도 없이 compose port·리스너 줄만 나오고 **"점검 결과: 문제 없음", exit 0** |
| array json | compose ps 가 JSON 배열 | 동일 | 서비스 5줄 정상 |

실제 출력 발췌(full):
```
--- 서비스 상태 ---
[완료] db       정상
[완료] migrate  마이그레이션 완료
...
[완료] web      127.0.0.1:8080->8080/tcp
[완료] docker compose port: 127.0.0.1:8080
[완료] 이 PC 의 포트 8080 리스너는 루프백(127.0.0.1)뿐입니다.
```
판정:
- 한글 이중 출력("서서비비스스"), `web` 이 `worker` 줄 끝에 겹침: **pwsh 7 / Linux 에서 재현되지 않음**. 스크립트 논리는 정상이며 해당 이상은 Windows 콘솔 렌더링 문제로 추정된다. 단 이는 추정이고 Windows 에서 확인한 것이 아니다.
- 선생님 PC 에서 "포트 구역 4줄+리스너 줄 누락"처럼 보인 현상은, 스크립트 코드상 항상 출력되는 줄이라 콘솔 표시 문제이거나, `docker ps` 가 일부만 돌려준 경우일 수 있다. psempty 시험이 보여 주듯 후자라면 스크립트가 "문제 없음"으로 끝난다. 어느 쪽인지 **판별하지 못함**(판별 방법은 CLAUDE.md 기재대로 `| Out-File status.txt -Encoding utf8`).
- 첫 시험 참고: 첫 가짜 서버가 Content-Type 을 보내지 않아 `/api/healthz -> 200 123 34 115 ...`(바이트 배열 숫자) 로 출력됐다. 시험 도구의 결함이며 Content-Type 을 넣은 재실행에서 정상(`{"status":"ok"}`). 실제 nginx 가 JSON Content-Type 을 주는지는 이 시험으로 확인하지 못했다(Content-Type 없는 응답이면 PS 5.1/7 모두 숫자열로 보일 수 있음).

## 4. live-* 스크립트 (임시 복사본 .harness-tmp/repo-copy, start.ps1 은 가짜)
| 시험 | 입력 | 기대 | 실제 |
|---|---|---|---|
| live-on 잘못된 ID | `short`, `abc`, 12자, `dQw4w9WgXc!`, 공백 포함 | 오류·exit 1·.env 미생성 | 5건 모두 `[오류] 영상 ID 형식이 아닙니다...`, exit 1, .env 없음 |
| live-on 빈 ID | `-VideoId ''`, stdin 없음 | Read-Host 로 묻고 거부 | stdin 이 /dev/null 이라 Read-Host InvalidOperation(시험 환경 한계, 빈 입력 거부 자체는 미확인) |
| live-on 올바른 ID | dQw4w9WgXcQ, .env 없음 | .env.example 복사 후 WRITE=1, ALLOWED=ID, 가짜 start 호출 | 일치(4행 WRITE=1, 6행 ALLOWED=dQw4w9WgXcQ), `[FAKE start.ps1 called]`, exit 0, BOM 없는 UTF-8 |
| live-on 갱신 | a-b_c1D2e3F(- 와 _ 포함) | 기존 줄 교체, 중복 없음 | 교체됨, WRITE 줄 1개 |
| live-on 키 없는 .env | `FOO=bar` CRLF | 두 줄 추가 | `FOO=bar`, `YTWEB_LIVE_WRITE=1`, `YTWEB_LIVE_ALLOWED_VIDEOS=...` (LF 로 정규화) |
| live-on stdin 입력 | 파이프로 ID | Read-Host 경로 동작 | 동작 |
| live-off | 위 .env | WRITE=0, ALLOWED= 비움, start 호출 | 일치, 가짜 start 호출 |
| live-off .env 없음 | - | 안내 후 exit 0 | 일치 |
| live-check 상태별(실제 live_check.py 를 가짜 docker exec 로 실행, .harness-tmp/be 가상환경) | A 전부 없음 / B 파일+읽기 로그인만 / C 전부 / D 스위치 1·영상 없음 | 항목별 [OK]/[필요], 결과 문구 | A: [필요] 5개, "아직 실제 수정은 꺼져 있습니다". B: [OK] 2 + [필요] 3. C: [OK] 5, "실제 수정이 가능한 상태입니다". D: 마지막만 [필요]. 전부 exit 0 |
| docker exec 실패 경로 | docker 가 exit 1 | 경고·exit 1 | Invoke-Compose 가 ExitCode=1 반환까지만 확인(live-check.ps1 의 경고 출력 줄 자체는 미실행) |

## 5. Set-OwnerOnlyAcl(icacls) 문자열 구성만 확인
Linux 에 icacls 없고 함수는 `$env:OS -ne 'Windows_NT'` 이면 즉시 true 를 돌려주므로 **함수 실행은 불가**. 함수 본문을 읽고 인자 배열만 pwsh 에서 재구성: `C:\Users\김 선생\web\backups | /grant:r | *S-1-5-21-...-1001:(OI)(CI)F | /grant:r | *S-1-5-18:(OI)(CI)F | /inheritance:r` (경로 공백·한글은 배열 인자라 따옴표 문제 없음). 소유자·SACL 을 건드리지 않아 SeSecurityPrivilege 가 필요 없다는 설계 근거는 코드 주석으로만 확인했다. icacls 가 이 인자를 실제로 받아들이는지, `*S-1-5-18` 구문, `${sid}:` 표기가 5.1 에서 맞는지는 **확인하지 못함**.

## 결함·약점 (고치지 않고 보고)
1. [Low~Medium, 확인됨] status.ps1 `docker ps` 결과가 비거나 web 행이 없어도 "호스트에 열린 포트" 점검이 아무것도 출력하지 않고 통과하여 최종 "문제 없음"이 된다(psempty 시험). 포트 노출 점검이 fail-open 이다. 개선안: web 행이 없으면 경고/문제로 센다.
2. [Low, 확인됨] 줄바꿈 LF/CRLF 혼재(3개만 CRLF). 동작 영향 미확인.
3. [Low, 미확인] live-on 의 빈 입력 거부 경로는 이 환경에서 시험하지 못함.
4. 한글 이중 출력·줄 겹침은 이 환경에서 결함으로 재현되지 않음(원인 미확정).

## 확인하지 못한 것
Windows PowerShell 5.1 에서의 실행·파싱(파서는 7.4.13 기준), Windows 콘솔/Windows Terminal 렌더링, icacls 실제 실행, Docker Desktop 의 실제 `compose ps --format json`·`docker ps` 출력 형식(가짜 docker 는 이 저장소 코드가 기대하는 형식을 내가 가정해 만든 것), start/stop/backup/restore/reset-demo/logs/e2e/pin-digests 실행(시험 범위 밖, 파서 검사만 함), .bat 실행.
