# 내부 검증 로그 — 11단계 최종 대조 1차 (`verify-log_doc-reconcile-web.md`)

## 대상 산출물
- 파일: `docs/yt/WEB_USER_MANUAL.md`, `WEB_FAQ.md`, `WEB_INSTALL.md`, `WEB_RUNBOOK.md`, `WEB_LEGAL_NOTICE.md`, `API.md`, `WEB_DESIGN.md`, 대조표 `docs/harness/doc-reconcile-web.md`
- 작성 에이전트: 11단계 문서화·운영지원 담당 (오케스트레이터가 범위를 지정해 호출: 8단계 전체 시험 전 선행 대조)
- 적용 Tier: Standard 이상(규칙 B: 최소 2회, 결함 0건 확인 회차 포함)
- 버전: v0(대조 전) → v1(1회차 수정 134건) → v2(2회차 수정 8건 + 서식·표현 5곳) → v3(3회차 결함 0건, 최종)
- 제약 준수: `docs/` 아래 문서만 수정(`git status`: 수정 7개 문서 + 신규 대조표 + 이 로그뿐). 소스·설정·시험·git 변경 없음. Windows 실행, 실제 구글 접속, pytest/docker 재실행 **하지 않음**(정적 읽기와 파일·문구 자동 대조만).
- 근거(진실의 원천): `web/frontend/src/i18n/ko.ts`, `pages/*.tsx`, `app/Layout.tsx`, `lib/labels.ts`, `api/endpoints.ts`, `web/backend/ytweb/**/*.py`(ProblemError·StepFailure 전수), `config.py`, `domain/common.py`, `core/settings_store.py`, `core/pin.py`, `core/ratelimit.py`, `config/settings.yaml`, `src/youtube_title/{config,limits,updater,report}.py`, `web/scripts/*.ps1`, `web/compose.yaml`, `web/compose.online.yaml`, `web/.env.example`, `web/docker/nginx/nginx.conf`, `docs/harness/decisions.md`, `docs/harness/STATE.md`.

## 1회차 검증 — 대조 (문서 문장을 코드·화면 문구에 한 줄씩 대조)
- 일시: 2026-10-11 / 방법: 코드 정독(Read), 문자열·코드 grep, 일부 자동 대조 스크립트
- 대조 항목(요청 ①~⑦)과 결과
  - [x] ① 화면 버튼·메뉴 이름: `ko.ts`·각 페이지 소스와 대조. 불일치 다수 발견(차단 제안 버튼, [초안 버리기], A/B 확인란, 면책 바닥글, 모드 띠 3종, 감사 로그 한글 이름, 이력 결과 선택지 등) → 수정
  - [x] ② 오류 코드·안내 문구: ProblemError/StepFailure 전수와 FAQ 코드표 대조. 누락 코드 `live_mode_mismatch`·`live_changed_since_apply`·`live_not_allowed`(롤백)·`live_mode_changed`(항목) 추가. 문구 인용(`demo_data_in_use`, 구글 오류 안내 4종) 일치 확인
  - [x] ③ 기본값 숫자: 하루 상한 10(1~20), 제안 3(1~5), 배치 50, 72시간, 영상당 3회, 승인 24시간, PIN 4~12·5회→5분~1시간, 세션 12시간+유휴 30분(**유휴 30분은 문서에 없었음 → 추가**), 속도 제한 값 → 코드와 일치 확인
  - [x] ④ 절차 순서(설치→시작→구글 연결→실제 수정 켜기): INSTALL 8-4 를 이 순서로 재구성. "방법 없음"으로 적힌 곳 4곳(MANUAL·FAQ·RUNBOOK·DESIGN; INSTALL 8-4 는 방법은 맞았고 순서만 재구성)을 `web\.env` 방식으로 정정
  - [x] ⑤ 개발자 용어: 사용자용 5종 본문의 DEC-/DEF-/POL-/test_tc_/DV-W 노출 제거(INSTALL 7장 제목 3, RUNBOOK 13-2·14·15 일부, LEGAL 4곳). 보고서 항목 번호(9-011 등)만 "보고서 항목"으로 유지
  - [x] ⑥ '안 한 것' 표기: Windows 실행·실제 구글 접속·실제 제목 변경 "한 번도 안 함" 문구가 5종 머리글과 API/DESIGN 에 있는지 확인. 있음. 추가로 `.env` 전달 Windows 미확인, 쿼터 공식 값 미열람을 "확인 필요"로 표기
  - [x] ⑦ 쿼터 50 vs 52: 코드 확인 — `videos.update`=50(`config/settings.yaml` quota.update_cost), 반영 1건=50+조회 2×1=52(`domain/limits_quota.py:95-97`). 모순 아님 → "요청 1회 50 / 반영 1건 52"로 통일(MANUAL·FAQ·RUNBOOK·LEGAL 7장·10장)
- 발견된 결함: 134건(대조표 3절 U01~L15, R01~R31, A01~A10, D01~D11 등)
- 조치: 문서 수정 134건 → v1

## 2회차 검증 — 수정분 재대조 (독립 심사자 관점: `git diff` 추가 행 전체를 다시 읽고 코드와 재대조)
- 일시: 2026-10-11
- 체크리스트
  - [x] 1회차 수정이 실제로 반영됐는가(diff 확인) — 반영됨
  - [x] 수정하면서 새로 만든 오류가 없는가 — 아래 결함 발견
  - [x] 같은 사실이 문서 사이에서 다르게 적히지 않았는가(쿼터·세션·띠 문구·확인 문구)
- 발견된 결함과 조치
  1. 매뉴얼·LEGAL 의 중첩 따옴표 4곳(`""통과"는`) — 작은따옴표로 정정 (서식 오류, 내가 만든 것)
  2. 매뉴얼 4장 "모든 화면" 표현이 PIN·로그아웃 화면을 포함하는 것처럼 읽힘 → "메뉴가 있는 모든 화면"
  3. WEB_DESIGN 에 낡은 문장 잔존 5곳(M3 행 "AI 어댑터·쓰기 로그인 미구현" 뉘앙스, §4-1 "라이브 게이트웨이는 코드에 없음", §1 "14단계 게이트 포팅", M2 행 "웹 방식 OAuth"(실제는 데스크톱 앱), 머리글 버전) → D12~D16
  4. LEGAL 3-2 소제목이 새 내용과 어긋남 → L16
  5. RUNBOOK·API: `/readyz` 의 `mode` 가 실제 수정 중에도 `demo` 로 나온다는 사실이 문서에 없었음(`MODES=("demo",)`) → R32, A11
  6. 대조표 근거 줄 번호 오류(MSG_* 줄, common.py, dashboard.py, _common.ps1) — 내가 적은 줄이 실제와 달랐음 → grep 으로 실제 줄 확인 후 정정 (대조표 생성 스크립트의 치환 버그도 같이 수정)
- 조치: 문서 수정 8건 + 서식·표현 5곳 → v2

## 3회차 검증 — 결함 0건 확인 (수정 반영 후 새로 실행한 자동·수동 점검)
- 일시: 2026-10-11
- 점검과 결과
  1. 사용자용 5종에서 개발자 용어 grep (`DEC-|DEF-|TC-|test_tc_|DV-W|POL-|EVT-W`): **0건**
  2. FAQ 코드표의 백틱 코드 93개를 백엔드·코어·nginx·ko.ts 소스와 자동 대조: 누락 5개 모두 동적 생성(`google_client_*`=접두사+`client_missing/invalid`, `limit_*`=`limit_`+코드 소문자) → **불일치 0건**. 매뉴얼·INSTALL·LEGAL 의 백틱 코드는 전부 소스에 존재. RUNBOOK 은 `pwsh`(명령)·`ytweb_pgdata`(볼륨 이름, 문서에 확인 필요 표기)만 소스 밖
  3. 문서에 쓴 환경변수 이름(`YTWEB_*`)이 모두 소스·compose·.env.example 에 존재: **불일치 0건**
  4. 문서의 따옴표 인용 문구(매뉴얼 152, FAQ 62, INSTALL 43개)를 ko.ts·백엔드·스크립트에 자동 대조: 미일치는 자리표시자(N, a/b), 한국어 줄임표, 문서 자체 설명, Windows/구글 화면 문구뿐이며 하나씩 눈으로 확인 — 코드에서 나온 문구의 **불일치 0건**
  5. 상호 참조(INSTALL 8-3~8-5, MANUAL 4-3~4-5·9-5·9-7, RUNBOOK 5·11·13-1·13-2·15-1·15-2, FAQ 4-1, LEGAL 3·10장) 제목 존재 확인: **모두 존재**
  6. 쿼터 표기 일관성(50/52 grep): 모든 문서가 "요청 1회 50 / 반영 1건 52" 구조와 일치
  7. 낡은 표현 grep(`버튼이 없|영어 blocked…|방법은 지금 없|면책 문구가 표시되지 않|초안 배치 #번호 취소`): 남은 3건은 모두 "고쳐진 것" 목록 또는 정상 안내(승인 버튼 없음 조건)로 **의도된 표현**
  8. `git status`: `docs/yt/*.md` 7개 수정 + `docs/harness/doc-reconcile-web.md`, `verify-logs/verify-log_doc-reconcile-web.md` 신규뿐. 다른 경로 변경 **0건**
- 발견된 결함: **0건**
- 한계(정직하게): 이 점검은 **코드·문구의 정적 대조**다. 화면을 실제로 띄워 캡처하며 대조하지 않았고(8단계 몫), Windows·실제 구글에서는 아무것도 실행하지 않았다. 대조표 5절의 확인 필요 항목은 이 회차로 닫히지 않았다.

## 최종 판정
- [x] PASS (결함 0건 회차 포함, 3회 검증 완료) — 8단계 전체 시험으로 handoff 가능. 단 대조표 5-1~5-3 의 "확인 필요"는 열려 있다(PASS 의 의미는 "문서와 현재 코드의 정적 대조에서 알려진 불일치가 없음"이며 "실제 화면·Windows·구글에서 동작이 확인됨"이 아니다).

## 공유 문서 갱신 요청 (이 에이전트는 traceability·decisions·STATE 를 직접 수정하지 않음)
- `docs/harness/STATE.md`: 11단계 대조 1차 완료 한 줄(수정 142건, 확인 필요 항목 대조표 5절, 8단계 후 2차 대조 필요) 추가 요청
- `docs/harness/decisions.md`: 신규 결정 없음. 다만 "A/B 확인은 화면 단계만(서버 필드 없음)", "보안 수용 3건 재평가 기록 없음"은 실제 구글 연결 전 사용자 결정이 필요한 항목으로 기록 권장
- `docs/harness/traceability.md`: 요구사항 변경 없음
