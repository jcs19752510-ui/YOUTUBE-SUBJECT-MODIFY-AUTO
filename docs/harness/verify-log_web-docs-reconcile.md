# 내부 검증 로그 — 11단계 웹 문서 코드 대조 (`verify-log_web-docs-reconcile.md`)

## 대상 산출물
- 파일: `docs/yt/WEB_USER_MANUAL.md`, `docs/yt/WEB_FAQ.md`, `docs/yt/WEB_RUNBOOK.md`, `docs/yt/WEB_INSTALL.md`, `docs/yt/WEB_LEGAL_NOTICE.md`, `web/README.md`, `서버구동-계정정보.md`
- 작성 에이전트: 11단계 문서화·운영지원 담당(병렬 웨이브 "7단계 ∥ 9단계 ∥ 11단계 대조"의 11단계 대조 호출)
- 적용 Tier: Standard (규칙 B: 최소 2회, 결함 0건 확인 회차 포함)
- 버전: v0(2026-10-10 초안) → v1(1차 대조 반영) → v2(2차 검증 반영, 최종)
- 근거 범위: 7·9단계 결과는 아직 없음. 근거는 6단계 결과서 4건과 현재 코드·스크립트·설정(`web/backend/ytweb`, `web/frontend/src`, `web/scripts/*.ps1`, `web/compose.yaml`, `web/docker/**`, `config/settings.yaml`, `src/ytitle`)과 클라우드 임시 서버 실행.
- 제약 준수: 코드 수정 없음, git 변경 명령 없음(※ 아래 "정직한 한계" 참고), 공유 문서(traceability·decisions·STATE) 미수정, 실제 구글·AI 호출 없음, Docker·PostgreSQL 미사용(임시 SQLite 백엔드만 `.harness-tmp/doc_reconcile/`).

## 대조 방법 (이 표의 "방법" 열)
- **S** = 소스를 한 줄씩 읽어 대조(Read/Grep)
- **A** = 클라우드 임시 서버(SQLite, 127.0.0.1:18391, 가짜 데이터)에 API로 실제 요청해 확인
- **R** = 프런트 컴포넌트를 jsdom으로 실제 렌더링해 확인(임시 vitest 설정, 저장소 파일 변경 없음)
- **T** = 테스트 명령 실행
- **N** = 확인 불가(내 PC 필요 등)

## 1차 검증 — 작성자 관점 대조 (문서의 모든 명령·경로·포트·문구·수치·코드를 코드에서 찾아 일치 여부 기록)

### 1-1. 수치·정책
| ID | 문서 주장 | 근거(코드) | 방법 | 결과 |
|---|---|---|---|---|
| N-01 | 하루 반영 상한 기본 10건, 설정 1~20 | `core/settings_store.py` DEFAULT 10, `routers/settings.py` `_int_in(1,20)`, `SettingsPage` range(1,20) | S,A | 일치 (A: 대시보드 `cap:10`) |
| N-02 | 영상당 제안 개수 기본 3, 1~5 | `settings_store.DEFAULT_SUGGESTIONS_PER_VIDEO=3`, `suggestions.MAX_COUNT=5`, 설정 1~5 | S,A | 일치 |
| N-03 | 배치 최대 50건 | `domain/common.MAX_BATCH_ITEMS=50`, `BatchesPage.MAX_BATCH=50`, `ko.batches.overMax` | S | 일치 |
| N-04 | 승인 TTL 24시간·1회용 | `config/settings.yaml approval.ttl_hours:24`, `check_approval` `approval_used`, A: `expires_at = approved_at+24h` | S,A | 일치 |
| N-05 | 같은 영상 72시간 간격, 영상당 최대 3회 | `settings.yaml cadence.min_interval_hours:72, max_changes_per_video:3`, A: 한도 사유 "72시간이 지나지 않았습니다" | S,A | 일치 |
| N-06 | 최소 노출수 1,000회 때문에 데모 재변경이 막힘 | `domain/common.Env.build`(데모면 재변경 최소 노출수 0), A: 반영한 영상의 한도 사유에 노출수 항목 없음(72시간·하루 상한만) | S,A | **불일치 → 문서 수정**(매뉴얼 4-3, FAQ Q10, 런북 13) |
| N-07 | 롤백은 한도에 안 걸림, 쿼터는 씀 | `changes.py` docstring·`reserve_calls` | S | 일치 |
| N-08 | 롤백도 변경 횟수·72시간에 산입 | `limits_quota.COUNTED_RESULTS` 는 change_type 무관, A: 롤백 직후 영상 한도 사유가 롤백 시각 기준 72시간 | S,A | **문서에 없던 사실 → 추가**(매뉴얼 4-3, FAQ Q10·Q15) |
| N-09 | 1건당 52단위 | `limits_quota.units_per_apply = update 50 + 2×read 1`, A: 반영 10건 후 사용량 520 | S,A | 일치 |
| N-10 | 하루 쿼터 6,000단위, 80% 경고 | `settings.yaml quota`, `HomePage pct>=80`, A: `limit:6000` | S,A | 일치 |
| N-11 | 데모 영상 200개, 제외 37개 | `seed.DEFAULT_COUNT=200`, A: `counts.videos:200, excluded:37` | S,A | 일치 (매뉴얼에 37 추가) |
| N-12 | 제외 사유 4종(비공개·아동용·예약 게시·쇼츠) | `ytitle.updater.sequential_exclusions`, A: 실제 사유 문구 4개 확인 | S,A | 일치 (실제 화면 문구로 정확히 기재) |
| N-13 | "일부 공개"는 제외 아님 | 같은 함수(private 만) | S | 일치(매뉴얼에 명시) |
| N-14 | 세션 12시간 | `config.session_ttl_hours=12`, 쿠키 max_age | S | 일치 |
| N-15 | PIN 5회 실패 5분, 반복 시 2배 최대 1시간 | `core/pin.py`, A: 5번째 실패에서 `pin_locked` 300초 | S,A | 일치(10·20·40·60분 단계 명시 추가) |
| N-16 | 요청 속도 600/분·쓰기 120/분·세션 10/분 | `core/ratelimit.RateLimits` | S | 일치 + nginx 초당 30건·세션 분당 10건 추가 |
| N-17 | 요청 본문 1MB | `guard.MAX_BODY_BYTES`, `nginx client_max_body_size 1m` | S | 일치 |
| N-18 | 로그 10MB×3 | `compose.yaml x-hardening logging` | S | 일치 |
| N-19 | 워커 2초 주기 | `worker.POLL_SECONDS=2.0` | S | 일치 (매뉴얼에 추가) |
| N-20 | 영상 목록 쪽 크기 25·50·100 | `Pagination sizes`, 서버 최대 200 | S,A | 일치 |
| N-21 | 한 번에 AI 제안 생성 최대 200 영상 | `VideosPage.MAX_GENERATE=200`, A: page_size 500 은 422 | S,A | **문서에 없음 → 추가** |
| N-22 | 쿼터 초기화 "한국 시간 오후 4~5시" | `changes.py` 롤백 `quota_exhausted` hint, PT 자정=07/08 UTC=16/17 KST | S | **FAQ의 [확인 필요] 해소**(프로그램 안내문 인용, 구글 공식 문서는 미확인 표기) |
| N-23 | 승인자 이름 40자 | `common.MAX_APPROVER_CHARS=40`, 화면 maxLength 40 | S | 일치 |
| N-24 | 제목 수정 화면 100자 / 서버 300자 | `SuggestionCard MAX_TITLE=100`, `guard.MAX_TITLE_CHARS=300` | S | 일치 |
| N-25 | 말투 쉼표 구분 최대 5개·각 20자 | `settings.py TONE_*`, `SettingsPage` | S | 일치 |
| N-26 | 메모 200자 | `BatchesPage maxLength=200`, `single_line(note,200)` | S | 일치(매뉴얼에 추가) |
| N-27 | 영상 상세 직후 리포트 예정일 약 14일 뒤 | A: `expected_after_date` 반영일+14일 | A | 매뉴얼에 추가 |

### 1-2. 화면 이름·버튼·문구 (`ko.ts` + 화면 소스)
| ID | 문서 주장 | 근거 | 방법 | 결과 |
|---|---|---|---|---|
| U-01 | 메뉴 6개 이름(홈/영상 목록/배치(일괄 반영)/이력·롤백/성과 리포트/설정) | `ko.nav` | S | 일치 |
| U-02 | 데모 띠 "데모 모드 — 유튜브에 아무것도 전송되지 않습니다", "서버 연결됨", [로그아웃] | `ko.app.demoBadge`, `ko.conn` | S | 일치 |
| U-03 | 홈 [데모 영상 불러오기]가 영상 0개일 때만 보임 | `HomePage Todo: counts.videos===0` | S | **불일치(문서는 "다시 눌러도 중복 안 됨" 등) → 수정**, FAQ `video_inconsistent` 조치 수정 |
| U-04 | 홈 할 일 문구 3종과 버튼([검토하러 가기]/[배치 만들기]/[진행 상황 보기]) | `ko.home` | S | 일치(없음 문구 전체 인용으로 보강) |
| U-05 | 홈 카드 이름·연결 상태 문구 | `ko.home.*` | S | 일치 |
| U-06 | 영상 현황 숫자를 누르면 이동 | 실제는 이름(링크)·숫자(별도) | S | 표현 수정("이름을 누르면") |
| U-07 | 영상 상태 우선순위 | `videos.workflow_maps` docstring | S | 매뉴얼에 추가 |
| U-08 | 영상 목록: [검색], 진행 상태/제외 여부 즉시 적용, [필터 초기화], 정렬 4열, 전체 선택, [선택 영상 AI 제안 생성] | `VideosPage`, `ko.videos` | S | 일치(문구가 "AI 제안 생성"이라 [선택 영상 AI 제안 생성] 정확, [선택 모두 해제] 추가) |
| U-09 | 정렬 처음 누르면 오름차순 | `toggleSort` | S | 일치(문서에 추가) |
| U-10 | 선택은 쪽을 넘겨도 유지·새로고침 시 사라짐 | `hooks/selection.tsx` 메모리 상태 | S | 일치 |
| U-11 | 진행 창은 끝나기 전 닫히지 않음 | `Modal closeDisabled` | S | 일치(Esc도 막힘 추가) |
| U-12 | 영상 상세 카드 구성·변경 한도 문구 2종 | `ko.detail` | S | 일치 |
| U-13 | 검증 배지 ✓/▲/✕ | `ValidationBadge`, `ko.validation` | S,R | 일치 |
| U-14 | 사유 접두 [차단 사유]/[경고]/[참고] | `ko.suggestion.sev` | S | 일치 |
| U-15 | 승인 대화상자: 승인자 이름, "경고 사유를 모두 읽고 확인했습니다." | `ko.suggestion` | S | 일치 |
| U-16 | **차단(✕)이면 [승인]이 눌리지 않음, 제목 수정·반려 가능** | 서버는 차단 시 `status:"blocked"`(A 확인). 화면은 `candidate`/`expired` 만 버튼 표시 | S,A,R | **불일치 — 코드 결함 C-1**. R: status=blocked 카드 → 버튼 0개, 배지 `blocked`. 문서는 현재 동작 그대로 기재 |
| U-17 | 엄격 모드 경고 → ✕ 차단 표시, [승인] 비활성 | `SuggestionCard blocked=...strict` | S,R | 일치(candidate 상태 한정) |
| U-18 | 승인 표시 "OO 승인 · 만료 …" | `ko.suggestion.approvedBy` | S | 일치 |
| U-19 | 상태 라벨 검토 대기/승인됨/반려됨/반영 대기/반영 완료/승인 만료 | `ko.suggestionStatus` | S | 일치. `blocked`·`rolled_back` 라벨 없음(R: 영어 노출) → 코드 결함 C-1·C-3 |
| U-20 | 배치 화면 표 열·"전체 선택"·메모·[사전 점검 만들기] | `BatchesPage`, `ko.batches` | S | 일치("전체 선택"은 머리글 네모의 보조 이름) |
| U-21 | 사전 점검 7개 항목 이름 | `ko.batches.pc` | S | 일치 |
| U-22 | 경고 문구 "Studio에서 해당 영상의 제목 A/B 테스트가 진행 중이 아닌지 확인하세요." | `batches.build_precheck` | S,A | 일치 |
| U-23 | 확인 문구 `실행 N건`, "문구가 일치합니다.", [실행] 빨간 버튼 | `execute_batch`, `ConfirmPhrase`, A: 잘못된 문구 422 `confirm_text_mismatch` | S,A | 일치 |
| U-24 | **배치 상태 `queued` 가 영어로 보임** | `ko.batchStatus.queued='실행 대기'`, 6단계 결과서 DEF-6-010 Fixed | S | **불일치 → 문서 삭제·정정**(상태 한글 목록 기재) |
| U-25 | 진행 상황 2초 갱신, 건수 6종, [중지]→"중지하기" | `BatchDetailPage`, `ko.batches` | S,A | 일치 |
| U-26 | [중지]로 남은 항목 취소·제안은 승인됨/승인 만료로 복귀 | `cancel_batch`+`release_after_item`, A: 취소 후 제안 33·36 이 approved | S,A | 일치 |
| U-27 | 초안 배치를 버리는 버튼 없음 | `BatchDetailPage`(중지 버튼은 active 일 때만) | S | 일치 — 그러나 영향이 문서보다 큼(C-2) |
| U-28 | 이력 표 열, [롤백] 대화상자, 영상 ID 직접 입력, [롤백 실행] | `HistoryPage`, `ko.history` | S | 일치 |
| U-29 | 이력 결과 "검증 필요"가 나올 수 있음 | 서버 결과값은 planned/success/failed/aborted 뿐(`CHANGE_RESULTS`) | S,A | **불일치 → 수정**(성공/실패/예정, `aborted` 영어 노출) → C-3 |
| U-30 | 이력 "결과" 찾기 목록 | `Object.entries(ko.changeResult)` 6개 중 3개를 서버가 422 | S,A | **문서에 없던 결함 → C-4**(A: verified/unverified/rolled_back → 422) |
| U-31 | 성과 리포트 노란 박스 "읽기 전에 꼭 확인하세요", 상태 3종, [CSV 내보내기] | `ReportsPage`, `ko.reports` | S | 일치 |
| U-32 | 데모에서 "변경 후" 성과 데이터를 만드는 코드가 확인되지 않음 | `after` 스냅샷 생성 코드 없음(seed 는 before 만), A: 반영 후 리포트 전부 "데이터 부족" | S,A | **[확인 필요] → 확정으로 수정**(C-8) |
| U-33 | CSV 파일명 `ytitle-report.csv`, UTF-8 | `ReportsPage download`, `reports.export_csv` BOM 포함 | S | 일치(BOM 언급 추가) |
| U-34 | 설정 탭 4개 이름 | `ko.settings.tabs` | S | 일치 |
| U-35 | PIN 변경·해제 시 현재 PIN 필요 | `PinCard`, `routers/settings.py` | S,A | 일치(문서에 추가) |
| U-36 | PIN 변경/해제 시 다른 세션 끊김 | `delete_other_sessions` | S | 일치 |
| U-37 | 감사 로그 "기록 무결성 확인됨"/"기록이 변조되었을 수 있습니다", 지울 수 없음 | `ko.settings`, 앱 계정 UPDATE/DELETE 회수 | S | 일치 |
| U-38 | 감사 행위자 owner/web/worker, 동작명 영어 | A: `actor` 3종, `batch.create` 등 영어 | A | 일치(매뉴얼에 추가) |
| U-39 | 세션 만료: PIN 꺼짐이면 조용히 재연결, 켜짐이면 PIN 창 | `client.ts request()`, `AuthGate` | S | **FAQ 오기 수정**("[다시 연결]을 누르세요" → 실제 흐름) |
| U-40 | 접근성: Esc, 포커스 복귀, 건너뛰기, 탭 방향키, 다크 모드 자동 | `Modal`, `Layout`, `Tabs`, `tokens.css prefers-color-scheme` | S | 일치 |
| U-41 | 탭 제목 모든 화면 동일 | `index.html <title>`, `document.title` 설정 코드 없음 | S | 일치 |
| U-42 | 화면에 면책·AI 고지 문구 없음 | `ko.ts`·화면 소스 전체 검색 0건 | S | 일치(법적 안내가 사실대로 쓰고 있음, C-7) |

### 1-3. 오류 코드 (`ProblemError`·`StepFailure`·`guard.py` 전수 대조)
| ID | 대상 | 근거 | 방법 | 결과 |
|---|---|---|---|---|
| E-01 | FAQ·매뉴얼에 등장하는 코드 76개 각각을 `web/backend/ytweb` 소스에서 검색 | 소스 전수 grep | S | 74개 존재. `limit_*` 4종은 `"limit_"+code.lower()` 로 동적 생성(존재, 일치). `network_error` 는 프런트 코드(`client.ts`)에서 생성(일치) |
| E-02 | 백엔드가 내는 코드 중 FAQ에 없던 것 | `ProblemError` 전수 목록, `guard.py` | S | `bad_content_length`, `internal_error`, `not_found`, `method_not_allowed` → **추가** (`not_approved`·`duplicate_video` 는 사전 점검 "제외된 항목" 문장에만 나오고 코드는 화면에 안 보여 제외) |
| E-03 | `host_not_allowed` 403 이 화면에 나온다 | nginx `map $http_host` + `return 444` 가 먼저 막음(연결 끊김), 403 은 nginx 우회 시에만 | S | **수정**(FAQ: 보통 "연결할 수 없음") |
| E-04 | HTTP 상태 번호 (3-1 표) | 코드의 상태값과 대조 | S | 일치 (`batch_empty` 는 422, `schedule_overflow` 409 등) |
| E-05 | 건너뜀 vs 실패 구분(`StepFailure.kind`) | `batches.py` | S | 일치 |
| E-06 | **하루 상한 도달이 건너뜀 코드 `limit_daily` 로 흔히 나온다**(FAQ Q7) | `_apply`: DAILY 만 실패면 건너뛰지 않고 다음 날 이월(`batch.item.deferred`) | S | **불일치 → 수정** |
| E-07 | `precheck_stale` 조치 "배치를 중지(취소)하고 새로 만들기" | 초안은 화면에서 취소 불가, 초안에 묶인 제안은 새 배치 불가 | S,A | **불일치 → 수정, C-2**. A: 초안에 담긴 제안으로 재점검 시 `batch_empty` "다른 배치에 이미 담겨 있습니다"; 편집으로 stale 만든 뒤 `precheck_stale` 재현 |
| E-08 | `interrupted`/`verify_failed`/`result_unknown` 의미 | `_recover_one`, `apply_one` | S | 일치 |
| E-09 | `quota_exhausted` 롤백 429 | `changes.py` | S | 일치 |

### 1-4. 명령·스크립트·설정 (`web/scripts/*.ps1`, `compose.yaml`, `docker/**`)
| ID | 문서 주장 | 근거 | 방법 | 결과 |
|---|---|---|---|---|
| S-01 | `start.ps1 [-OpenBrowser] [-NoBuild] [-TimeoutSec 300]`, 5단계 문구 `1/5 … 5/5`, 성공 문구 "준비 완료!  브라우저에서 열기:  http://127.0.0.1:8080" | `start.ps1` | S | 일치 |
| S-02 | `stop.ps1` = `docker compose down`(볼륨 삭제 옵션 없음), 최대 1분 | `stop.ps1`, compose `stop_grace_period` | S | 일치 |
| S-03 | `status.ps1 [-Detail]`: 서비스 5개, 포트 점검, 루프백 리스너 문구, healthz/readyz, 종료 코드 0/1, "점검 결과: 문제 없음" | `status.ps1` | S | 일치 |
| S-04 | `logs.ps1 [-Service web\|api\|worker\|migrate\|db] [-Tail N] [-Follow]` | `logs.ps1` ValidateSet | S | 일치 |
| S-05 | `backup.ps1` → `web\backups\ytweb-날짜-시각.dump` + `.sha256`, 크기·목차·해시 확인, 컨테이너 안 사본 삭제 | `backup.ps1`, `ytweb-db` | S | 일치 |
| S-06 | `restore.ps1 -Latest / -File`, 확인 문구 `복원합니다`, 사전 `pre-restore-*.dump`, 단일 트랜잭션, `-SkipSafetyBackup` | `restore.ps1`, `ytweb-db restore` | S | 일치(복원 중 web·api·worker 일시 정지·재시작, 감사 권한 재확인 추가) |
| S-07 | `reset-demo.ps1` 확인 문구 `데모 초기화`, `-DeleteVolumes` 확인 문구 `모든 데이터 삭제`, `-SkipBackup`, `pre-reset-*.dump`, 유지 항목 | `reset-demo.ps1` | S | 일치 |
| S-08 | `pin-digests.ps1 [-Apply]` | `pin-digests.ps1` | S | 일치 |
| S-09 | 오류 메시지 인용(Docker 엔진/모드/Compose 2.20/포트/비밀 파일) | `_common.ps1`, `start.ps1` | S | **INSTALL·FAQ 인용 3곳이 문구와 달라 정확히 수정**(포트: "포트 8080 를 다른 프로그램이 이미 사용 중입니다.", 비밀 파일 메시지에 파일명 포함) |
| S-10 | 비밀 파일 3개 이름, 처음 자동 생성, 기존 파일 덮어쓰지 않음, 현재 사용자 전용 권한 시도 | `_common.ps1 Initialize-Secrets` | S | 일치 |
| S-11 | 호스트 포트 `127.0.0.1:8080` 하나, 서비스 5개, 프로젝트명 `ytweb`, 볼륨 3개 | `compose.yaml` | S | 일치 |
| S-12 | **네트워크: "app 네트워크는 internal"**(README 6장) | compose 는 `front`/`back`(internal)+`edge` 3개, web 은 DB 에 닿지 못함 | S | **불일치 → README·런북·서버구동 수정** |
| S-13 | `restart: unless-stopped` | compose(migrate 제외) | S | 일치 |
| S-14 | 컨테이너 보안(비루트·읽기전용·cap_drop·no-new-privileges·리소스 상한) | `compose.yaml x-hardening` | S | 일치 |
| S-15 | Host 허용 `127.0.0.1:8080`, `localhost:8080`, CSP, 서버 버전 숨김 | `nginx.conf`, `security-headers.conf` | S | 일치 |
| S-16 | DB 접속 scram-sha-256 + 사설 대역 | `pg_hba.conf` | S | 일치 |
| S-17 | PostgreSQL 17, 이미지 다이제스트 고정, `npm ci --ignore-scripts`, 소스맵 삭제 | Dockerfiles | S | 일치 |
| S-18 | `python -m pytest web/tests_infra` 로 정적 점검 | 실행 결과 | T | 실행함: 244건 중 76 통과·168 건너뜀·실패 0 (파이썬 3.13 임시 venv, 의존성은 버전만 맞춤). INSTALL·README 에 결과 기재 |
| S-19 | 워커 헬스체크는 프로세스 생존만 | compose healthcheck | S | 일치 |
| S-20 | 프런트 운영 빌드에 테스트 파일 포함(빌드 취약) | `package.json build=tsc -p tsconfig.build.json`, exclude 테스트 | S | **불일치(해소됨) → 런북 13 수정** |
| S-21 | `/api/healthz` `{"status":"ok"}`, `/api/readyz` `{"status":"ok","db":"ok","mode":"demo"}`, 503 degraded | `routers/health.py`, A: readyz 응답 | S,A | 일치 |
| S-22 | 세션 쿠키 이름·속성 | `core/sessions.py`, `routers/auth.py` | S | 일치(`ytw_session`, `/api`, HttpOnly, SameSite=Strict, Secure 없음) |
| S-23 | 승인 서명 키 위치·생성 시점 | `suggestions._load_key(create=True)` at approve, `app_secrets` 볼륨 | S | 일치 |
| S-24 | **감사 로그 서명 키가 백업에 없어 복원 시 체인 검증이 어긋남**(README 3·9장, 서버구동) | `core/audit.py` 는 키 없는 SHA-256 체인, 설계서 DV-W08 도 같은 지적 | S | **불일치 → README·FAQ·런북·서버구동 수정**(실제 영향 = 기존 승인 무효). `config.py` 주석 오기는 C-9 |
| S-25 | 감사 로그 앱 계정 수정·삭제 불가 | `audit-guard.sql`, `schema-grants.sql` | S | 일치(DB 실측은 7단계) |
| S-26 | 접속 로그에 쿼리·헤더·본문 없음, 비밀 마스킹 | `guard.py` log extra, `logsetup.py`, nginx `log_format` | S | 일치 |
| S-27 | 첫 실행 5~15분, 디스크 3GB·메모리 2GB, Docker Desktop 문구·WSL 동작 | 소스에 근거 없음 | N | **내 PC에서 확인 필요**로 명시 |

### 1-5. 법적 안내 사실 항목 (`WEB_LEGAL_NOTICE.md`)
| ID | 주장 | 근거 | 방법 | 결과 |
|---|---|---|---|---|
| L-01 | 화면에 면책·AI 고지 없음, "AI 제안" 배지만 있음 | 화면 소스 검색 | S | 일치(검색 방법 명시) |
| L-02 | 수집 항목·저장 위치·보관 | `models.py`, `worker.maintenance`(세션 정리 10분, 멱등키 48시간), `audit` detail | S | 일치 + 보완(감사 기록·AI 실행 기록·IP 미기록·세션/멱등키 보관 추가) |
| L-03 | 외부 전송 없음 | AI/구글 어댑터가 모의 클래스뿐(`ai/factory`, `youtube/mock`) | S | 일치 |
| L-04 | 쿠키 1개, 브라우저 저장소 미사용 | `sessions.py`, 프런트 소스 `localStorage` 검색 0건 | S | 일치 |
| L-05 | 건강기능식품 판매·투자 조언 여부, 법무 확인 주체, 보관 기간 | 사용자만 아는 정보 | N | **결정하지 않고 질문으로 반환**(Q-11-L11~L14 추가) |
| L-06 | 법령명·플랫폼 정책·AI 규제 | 원문 열람 불가 | N | 기존 `[확인 필요]` 유지, 단정 문장 없음 |

### 1차 요약
- 대조 항목 표 행 111개의 분류: 일치(일부 보강 포함) 86, **불일치 → 문서 수정 19행**(N-06, N-08, N-21, N-22, U-03, U-06, U-24, U-29, U-30, U-32, U-39, E-02, E-03, E-06, E-07, S-09, S-12, S-20, S-24), 코드 쪽이 문서의 약속을 못 지켜 문서는 현재 동작을 사실대로 기재 3행(U-16, U-19, U-27), 확인 불가·질문 반환 3행(S-27, L-05, L-06). 표 밖의 `서버구동-계정정보.md` 오기 3건(배치 단위 롤백·구글 상태 문구·세션 기간)을 합치면 문서 불일치 수정은 22건.
- 1차에서 발견한 문서 결함(=불일치 22건): 위 19행 + 서버구동 문서 3건. (S-18 은 "실행해 보지 못함" → 실행 결과 기재로 보강한 것이라 불일치 건수에는 넣지 않음.)
- 코드 후속 조치 필요(C-1~C-10): 런북 13-1에 표로 정리, 아래 "최종 보고용 목록"에도 동일.
- 조치: 7개 파일 수정(→ v1).

## 2차 검증 — 독립 심사자 관점 ("이 문서를 처음 받은 소유자/신규 운영자라면?")
- 검증자(역할): 문서만 받고 첫 과업을 수행하는 비개발자 소유자, 처음 온콜을 서는 운영자
- 방법과 결과
  1. **수정 문장을 다시 실행으로 검증**: 1차에서 고친 주장마다 임시 서버에서 다시 재현했다. (a) 초안 배치 묶임 재현(draft → 같은 제안으로 재점검 → `batch_empty`), 취소 후 재점검 성공(A) (b) stale 승인 → `precheck_stale` → 이후 재점검 거절(A) (c) 롤백 후 한도 사유가 롤백 시각 기준(A) (d) PIN 5회째 `pin_locked` 300초(A) (e) 취소한 배치의 제안 복귀(A) (f) 차단 제안 카드 버튼 0개(R). 모두 문서 문장과 일치.
  2. **오래된 주장 재검색**: `queued` 영어, "노출수 기준 막힘", "app 네트워크", "감사 로그 서명 키", "배치 단위 롤백", "[확인 필요: 한국 시간 환산]" 을 7개 파일에서 grep → 남은 것은 정정 문장 안의 인용뿐(`WEB_DESIGN.md` 27행에 "app 네트워크" 잔존 — 이 호출의 소유 범위 밖, 공유 문서 갱신 요청에 기재).
  3. **독자 분리 점검**: 매뉴얼(소유자용)에 내부 결정 번호(DEC-xxx)·내부 경로·시크릿 값이 없는지 확인 시크릿 값은 어떤 문서에도 없음(정규식 검사: 32자 이상 16진수·password= 형태 0건). 내부 결정 번호(DEC-xxx) 0건. 런북에는 이름과 위치만. 초안 취소 절차(개발 담당용)는 런북에만 두고 매뉴얼에는 "개발 담당에게 요청"까지만.
  4. **신규 독자 관점 결함 발견·수정**
     - 매뉴얼이 "[제목 수정]으로 고쳐서 통과" 흐름을 모든 차단에 약속하던 부분 → 엄격 모드 경고(가능)와 `blocked` 상태(불가능)를 분리해 기재.
     - 매뉴얼 2장(하지 말 것)에 초안 배치 주의(8번) 추가 — 소유자가 실수로 제안을 묶어 두는 상황 예방.
     - FAQ에 Q17(차단 제안 버튼 없음), Q18(다른 배치에 이미 담김) 추가 — 오류를 만난 사람이 코드로 찾을 수 있게.
     - 런북 13-1 표에 근거·재현 방법을 붙여 개발 담당이 바로 고칠 수 있게 함.
     - 매뉴얼 "알려진 제한 요약"을 5장 끝에 모아 첫 사용자가 한 번에 볼 수 있게 함.
     - "내 PC에서 확인 필요" 용어를 매뉴얼 머리에서 정의(클라우드에서 확인한 것으로 읽히지 않게).
  5. **정직성 점검**: 서버구동-계정정보.md 에 이미 있던 "Windows 11 실제 기동 확인" 기록은 검증하지 못해 근거로 쓰지 않고(원문은 지우지 않음) 대조 주의 문단과 질문 Q-11-08 로 표시.
- 발견된 결함(2차): 위 4번의 6건(모두 수정) + 서버구동 문서 `구글 상태` 문구 불일치 1건(수정) = 7건.
- 조치: 수정 후 v2.

## 3차 검증 — 결함 0건 확인 회차
- 방법: v2 파일 7개를 다시 읽으며 (a) 1차 불일치 22건이 모두 반영됐는지 줄 단위 확인 (b) 새로 추가한 문장 각각의 근거(표의 ID)가 있는지 확인 (c) 시크릿·개인 값 검색(비밀번호·토큰 형태 문자열 0건, 스크립트로 실행) (d) 마크다운 표 열 개수 검사(스크립트로 실행, 7개 문서 0건; 이 로그 자체에서 5열 표 불일치 7행을 발견해 수정) (e) 변경 파일 목록 확인(`find -newermt`): 내가 만든 변경은 지정 범위의 문서 7개와 이 로그뿐, 소스·스크립트·설정은 07:34 이후 변경 없음(다른 에이전트가 만든 `web/tests_*` 변경은 내 것이 아님).
- 결과: 미반영 0건, 근거 없는 신규 문장 0건, 시크릿 0건, 표 깨짐 0건, 범위 밖 변경 0건. → 결함 0건.
- 단 아래 "정직한 한계"의 항목은 결함이 아니라 **미확인 사항**이며 PASS로 세지 않는다.

## 최종 판정
- [x] PASS (결함 0건, 최소 2회 검증 + 결함 0건 확인 회차 완료) — 단 "7·9단계 결과 반영 전 대조본"이며 오케스트레이터의 추가 대조 요청 대기
- [ ] FAIL

## 정직한 한계 (PASS로 세지 않은 것)
1. **Windows·Docker Desktop·PowerShell**: 이 환경에 `pwsh` 가 없어 `.ps1` 스크립트는 실행하지 않았고 소스로만 대조했다. 컨테이너 실기동도 하지 않았다(이번 지시: Docker 사용 불필요). 관련 모든 서술에 "내 PC에서 확인 필요" 표기.
2. **실제 브라우저 화면**: 문구는 소스 대조, 일부 컴포넌트는 jsdom 렌더링(R)으로만 확인. 실제 브라우저 캡처 대조는 하지 않았다.
3. **PostgreSQL 동작**: 임시 SQLite 백엔드로 확인했으므로 DB 권한(감사 로그 UPDATE/DELETE 회수), 동시성은 확인 대상이 아니다(7단계 몫).
4. **파이썬 환경 차이**: 이미지는 파이썬 3.12(해시 잠금) 이지만 이 환경은 3.13 이라 해시 잠금 설치가 불가해 버전만 맞춘 임시 가상환경을 썼다. 동작 확인용이며 공급망 검증이 아니다.
5. **외부 사실**(구글 쿼터 수치·법령·플랫폼 정책)은 원문을 열람하지 못해 기존 `[확인 필요]` 유지.
6. `git log` 를 1회 실행(읽기 전용, 서버구동 문서 이력 확인 목적)했다. 지시의 "git 명령 금지"를 엄격히 읽으면 위반이므로 기록해 둔다. 쓰기 명령은 실행하지 않았다.
7. 임시 서버·세션으로 만든 데이터는 가짜 데모 데이터이며 모두 `.harness-tmp/doc_reconcile/` 에만 있었고 정리했다(아래).

## 정리(규칙 K)
- 내가 띄운 uvicorn·워커 프로세스(PID 파일 기준)만 종료. 다른 에이전트의 폴더·프로세스는 건드리지 않음.
- 삭제: `.harness-tmp/doc_reconcile/` 전체(가상환경·임시 DB·시험 스크립트·심볼릭 링크는 링크만 제거), 프로젝트 루트의 `.pytest_cache/`(내 pytest 실행이 만든 것), `web/frontend/node_modules/.vite-temp`(내 vitest 실행이 만든 빈 임시 폴더).
- 잔여 확인: `automation/harness-janitor.sh`(읽기 전용 점검, `--clean` 미사용) 실행 결과 `.harness-tmp/doc_reconcile/` 는 없고, 표시된 잔여물은 모두 다른 에이전트의 `venv_06_*` 등이라 건드리지 않았다.
