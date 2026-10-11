# 하네스 진행 상태 (STATE) — 세션 재개용

> 오케스트레이터만 수정하는 단일 작성자 문서. 새 세션/컨텍스트 압축 후에는 이 파일과 `decisions.md`를 가장 먼저 읽는다. 시크릿·토큰·개인정보 원문은 쓰지 않는다.

## 1. 프로젝트 기본 설정
| 항목 | 값 | decisions.md ID |
|---|---|---|
| 적용 업무 | "시니어 생활팁" 채널 제목 최적화 CLI(본인 채널, 공식 OAuth) | DEC-001 |
| 업무 유형 | 신규 개발 | DEC-001 |
| 위험도 등급 Tier | Standard (Low 완화 미적용) | DEC-004 |
| 병렬 모드 | P1 (이 환경은 서브에이전트 미사용으로 실제 순차, DEC-011) | DEC-005, DEC-011 |
| MCP 연동 | 안 함 | DEC-005 |
| 레퍼런스 서비스 | 없음 | DEC-005 |
| 적용 법규 기준 | 대한민국 + YouTube/Google 약관, 규칙 I 보수 적용 | DEC-005, DEC-012 |
| git | AI는 조회 포함 전면 금지(사용자 지시). 제안 브랜치명·커밋 메시지만 출력 | DEC-006 |

## 2. 단계 진행표
| 단계 | 상태 | 산출물 | 검증 로그 | 비고 |
|---|---|---|---|---|
| 1 | **CONDITIONAL PASS** | `docs/yt/01_policy_research.md` | `verify-log_01_policy_research.md` | 공식 문서 도메인 차단으로 원문 미열람(DEC-010) |
| 2 | PASS | `02_planning.md`, `02_risk_assessment.md`, `traceability.md` | `verify-log_02_planning.md` | |
| 3 | PASS | `DESIGN.md`, `threat_model.md`, (부속) `03_manual_setup.md` | `verify-log_DESIGN.md`, `verify-log_03_manual_setup.md` | 03 가이드는 CONDITIONAL(화면 이름 미확인) |
| 4 | PASS | `04_ux_design.md` | `verify-log_DESIGN.md` | CLI UX |
| ★게이트 a | 통과 | `DESIGN.md` §13 | - | 사용자 "진행"(DEC-024) |
| 5~7 | **진행 중** | WU-0~3 PASS(`docs/harness/units/unit-N-test.md`), WU-4 구현 중(서브에이전트) | `verify-log_unit-N-test.md` | WU-5∥WU-6, 07 통합 테스트 남음 |
| 8~11 | 대기 | - | - | |
| 12~13 | 대기 | - | - | 12단계는 사용자 승인·테스트 영상 ID·실제 로그인 필요 |

## 3. feature / 작업단위 진행표
| feature | 트랙 | 작업단위 | 05 | 06 | 07 | 부채 |
|---|---|---|---|---|---|---|
| F-0 | L3 | WU-0 | 대기 | 대기 | - | - |
| F-A | L5/L3 | WU-1, WU-2 | 대기 | 대기 | 대기 | - |
| F-B | L3 | WU-3 | 대기 | 대기 | 대기 | - |
| F-C | L5 | WU-4, WU-5 | 대기 | 대기 | 대기 | - |
| F-D | L3 | WU-6 | 대기 | 대기 | 대기 | - |

## 4. 지금 상태 (개발·단위 검증 완료, 통합테스트 이후는 사용자 지시로 중지)
- **단위 검증 PASS(독립 변이 점검 포함)**: WU-0, 1, 2, 3, 4(변이 47/47), 5(변이 93/93), 6(변이 71/71). 결과서 `docs/harness/units/unit-N-test.md`, 검증 로그 `docs/harness/verify-log_unit-N-test.md`. 3개 Python 버전(3.11/3.12/3.13) 통과, 커버리지 100%(WU-2 99%)
- **중지(사용자 지시)**: 7단계 통합테스트(F-A·F-B, F-C, F-D), 11단계 문서. 통합테스트 파일(`tests/integration/`)은 미완성 중간 저장 상태. 화면 캡처 스크립트(`scripts/capture_demo.py`)와 `docs/demo/screens.json`은 완료
- **다음 순서(사용자 지시가 있을 때)**: 7단계 통합 → 8단계 → 9단계 → 10단계 → 11단계 문서 대조 → 12단계 직전 사용자 승인
- **사용자 결정 완료(DEC-031)**: 기준 폴더는 프로젝트 루트로 고정(반영 완료). WU-5 질문 5가지와 UI 이상 6건은 "무시하고 진행, 추후 수정 예정"(현재 구현 유지, 아래 목록은 추후 수정 대상)
- **추후 수정 대상**: WU-5 질문 5가지(승인 파일 HMAC 서명 추가 승인, planned 기록 정리 방법, 불확실 결과를 planned로 두는 규칙, 롤백에 승인 파일 요구 여부, 읽기 전용 필드 전송 가능 여부=12단계 실측), 기준 폴더를 프로젝트 루트로 고정할지, 금칙어 사전 검토, read_cost 0 하한, 403 안내 문구, CSV 위치 제한, blocked 재검증 상태 복귀(DESIGN 3-2 정정), 실제 Studio CSV 샘플
- **화면 캡처에서 발견한 UI 이상 6건**(소스 미수정, 결정 후 반영): 읽기·승인 명령 제목줄이 "모의 실행"으로 표시, 표 사유 말줄임, aborted 행이 변경 번호를 차지, 네트워크 오류 재시도 횟수 미표시, 게이트 배지 줄 맞춤, 롤백 안내 표기 불일치
- **git**: 허용됨(DEC-027). 원격 PROD_SCH에 푸시 완료. 사용자 커밋 2건의 Unverified 표시는 이력 재작성이 필요해 사용자 지시 전 보류
- **TC 번호**: WU-5 TC-6xx는 TC-9xx로 재번호(DEC-028)
- **임시 아티팩트(규칙 K)**: `.harness-tmp/`는 결과서 도구가 정리함
- **전체 진행률**: 약 70%

## 5. 웹 전환 트랙 (2026-10-10 시작, DEC-032~037)
- **업무**: CLI(유튜브 제목) → Docker 기반 로컬 웹(Python/FastAPI, React, REST, PostgreSQL). 유형: 기능 추가(구조 전환). Tier High, 병렬 P1, MCP 안 함, 법규 한국
- **요구사항 원본**: `웹프로그램으로수정요청.md`(2~11장). 기존 CLI 7~13단계 중지 상태는 사용자 지시로 무시하고 웹 전환에 집중(보류 항목은 설계서에서 함께 결정, DEC-036)
- **진행**: 0단계(질문·답변 기록) 완료 → 1단계 조사 4축 병렬 진행 중(`docs/harness/_parallel/01-axis*.md`) → 2 기획 개정 → 3 설계 → 4 디자인 → ★설계 승인 게이트(여기서 반드시 멈춤, DEC-037)
- **구현 금지**: 설계 승인("진행") 전에는 구현 코드를 쓰지 않는다. 실제 구글·AI 호출, 라이브 반영, 배포는 별도 승인
- **환경**: 사용자 PC(Windows, Docker Desktop)에서 구동. 클라우드에는 Docker 데몬이 없어 컨테이너 검증은 미수행으로 정직하게 기록(DEC-033)

## 6. 웹 전환 트랙 — 현재 상태 (2026-10-10, 사용자 지시로 전 작업 중지)
- **구현 완료(M1 데모 모드)**: W-BE-A 백엔드 기반(테스트 212, PG 실측), W-BE-B 백엔드 도메인(도메인 182, 백엔드 전체 605 통과), W-FE 프런트(95 테스트, 빌드·타입·린트 통과, 실제 백엔드 연동 확인), W-INF 인프라(이미지 3종 빌드·compose 전체 healthy, 정적 점검 35 통과 — 클라우드 Linux 엔진 실측). 구현 노트: `docs/harness/units/web-WU-*-note.md`
- **중지됨(미완료)**: 6단계 독립 검증 결과서 4건(`web-WU-*-test.md` 아직 없음, 시험 파일 `web/backend/tests/verify_wa|verify_wb`, `web/frontend/verify`, `web/tests_infra`는 미완성 저장), 7단계 전체 스택 통합 시험(시작 직후 중지), 문서 개정 3건(2단계 기획서·위험·위협 모델 STRIDE, 3단계 DESIGN.md·openapi·API.md, 4단계 04_ux_design.md — 모두 시작 직후 중지, 산출물 없음)
- **재개 순서(사용자 지시가 있을 때)**: ①전체 스택 통합 시험(`-p harness-tmp-int`, 포트 18080) ②독립 검증 4건 ③문서 개정 3건(코드 기준 as-built) ④후속: 데모 최소 노출수 0(DEC-042 D1, 코드 미반영), 프런트 운영 빌드에서 테스트 제외(DEC-041), 워커 하트비트, 감사 키 백업 안내 ⑤선생님 PC에서 `web/scripts/start.ps1`로 첫 화면 확인(README §8)
- **임시 산출물(규칙 K, 사용자 삭제 승인 대기)**: 이미지 `harness-tmp-int-*`·`harness-tmp-vinf*-*` 6개와 컨테이너·볼륨 `harness-tmp-vinf*`, `.harness-tmp/` 아래 가상환경·변이 복사본(약 2GB), 임시 PostgreSQL(`.harness-tmp/pg`, 127.0.0.1:54329)·dockerd 프로세스. 저장소에는 포함되지 않음(.gitignore)
- **진행률(추정)**: 전체 약 68%, M1 기준 약 93%. 세션 사용량은 계정 값을 읽을 수 없어 추정(마지막 사용자 제공 값: 현재 세션 1%, 이번 주 14%)

## 7. 웹 전환 트랙 — 재개 웨이브 1 중지 기록 (2026-10-10, 사용자 지시로 중지)
- **완료·푸시**: 문서 개정 3건(2단계 `02_planning/02_risk_assessment/threat_model`, 3단계 `DESIGN/WEB_DESIGN/openapi.json/API.md`, 4단계 `04_ux_design`) + 검증 로그 `verify-log_02_planning_web/DESIGN_web/04_ux_design_web`. 각 문서 상단 '검증 대기 항목' 표와 질문 목록(Q-W·Q-UX)이 남아 있음(사용자 답변 대기, 결정 미기록)
- **중지(미완료)**: 6단계 독립 검증 4건(W-BE-A/W-BE-B/W-FE/W-INF) — 시험 파일·변이 점검 진행분만 WIP 저장, 결과서 `web-WU-*-test.md`·검증 로그 없음. 7단계 통합 시험은 6단계 PASS 전이라 미착수
- **재개 순서**: ①6단계 독립 검증 4건 재투입(공통 지시서 내용은 이 세션 scratchpad라 소실 — 새 세션에서 재작성) ②7단계 통합 ③문서의 '검증 대기 항목' 반영 ④사용자 질문 일괄 확인
- **정리 상태**: 컨테이너·테스트 프로세스 중지함. 임시 PostgreSQL(127.0.0.1:54329)·dockerd·`.harness-tmp/`(약 1.8GB)·`harness-tmp-vinf*` 이미지·볼륨은 남아 있음(저장소 미포함, 컨테이너 회수 시 소멸)

## 8. 웹 전환 트랙 — 6단계 종료, 7단계 진행 (2026-10-11)
- **6단계 독립 검증**: W-BE-A PASS, W-BE-B PASS, W-FE 조건부 PASS, W-INF 조건부 PASS(결과서 `docs/harness/units/web-WU-*-test.md`, 로그 `verify-log_web-WU-*-test.md`, DEC-043)
- **11단계 웹 문서 초안**: `docs/yt/WEB_{USER_MANUAL,FAQ,RUNBOOK,INSTALL,LEGAL_NOTICE}.md` 완료(초안, 7~10단계 후 대조 필요). 코드와 문서의 불일치(면책·AI 고지 문구 없음, `queued` 영문 표시, README 감사 키 설명 등)는 문서 하단 목록 참고
- **진행 중**: 7단계 전체 스택 통합 시험(에이전트, 포트 18080, `.harness-tmp/int/`), DEF-VI-002 조치(W-BE-A)
- **사용자 결정 대기(진행 비차단)**: DEF-VI-001(web→db·외부 통신 차단 설계: 네트워크 3분리/수용/egress 차단), DEF-VI-003 수용 여부, W-FE 질문(용어 통일, 1024px 미만 지원, 작업 404 완화 유지), W-BE-A 질문(`/readyz` mode 노출, hide_parameters, PIN scrypt 비용), W-INF 질문(PostgreSQL 17 ADR, 종료 코드 143, dev/test 프로필), 11단계 문서 질문 11가지(운영 담당자·백업 정책·PIN 필수 등)
- **남은 오케스트레이터 작업**: `traceability.md` 웹 요구사항 단위테스트 컬럼 갱신(각 결과서 부록 B·D 요청), 7단계 결과 반영, 8~10단계, 11단계 문서 대조, 12단계 직전 사용자 승인
- **진행률**: 전체 약 73%, M1 기준 약 97%

## 9. 웹 전환 트랙 — 7·9·11단계 웨이브 중지 기록 (2026-10-11, 사용자 지시로 전체 중지)
- **완료·푸시**: 11단계 웹 문서 5종 + `web/README.md` + `서버구동-계정정보.md` 코드 대조(불일치 22건 수정, 검증 로그 `verify-log_web-docs-reconcile.md`). 코드 후속 조치 C-1~C-10은 `docs/yt/WEB_RUNBOOK.md` 13-1 (C-1·C-2 높음: 차단 제안 카드에 버튼 없음·초안 배치 버릴 방법 없음 — 7~8단계 전 수정 여부는 사용자 결정 대기 Q-11-09)
- **중지(미완료)**: 7단계 통합 시험(`web/tests_integration/` 진행분만 WIP 저장, 결과서 `feature-web-m1-integration-test.md` 없음), 9단계 보안 검증(`web/tests_security/` 진행분만 WIP 저장, 결과서 `security-web-m1-test.md` 없음, SBOM만 존재). 8단계는 7단계 PASS 전이라 미착수
- **사용자 요청 대기(검토 완료, 구현 전)**: 관리자 1명 아이디·비밀번호 로그인 + 로그인마다 이메일 코드(2단계 인증). 현재 인증은 세션 발급 + 선택 PIN뿐. 설계안과 질문 8개는 대화에 기록(이메일 인증 의미, 메일 서비스, 최초 계정 생성 방식, 분실 복구, TOTP 보조, PIN 대체, 외부 접속 계획, 시작 시기). 7·9단계 이후 별도 작업 단위로 넣는 것을 권장. 답변 전에는 코드 변경 없음
- **재개 순서**: ①7단계 통합 시험 완성 ②9단계 보안 검증 완성 ③C-1·C-2 수정 여부 결정 ④8단계 ⑤11단계 최종 대조 ⑥관리자 로그인 작업 단위(승인 후)
- **정리 상태**: 컨테이너·테스트 프로세스·임시 PostgreSQL 인스턴스 중지함. 클라우드 임시 PostgreSQL(54329)·dockerd·`.harness-tmp/`·`harness-tmp-int*`/`harness-tmp-sec*` 이미지·볼륨은 남아 있음(저장소 미포함, 사용자 삭제 승인 대기)
- **진행률(추정)**: 전체 약 79%, M1 약 97%

## 10. 웹 전환 트랙 — 실제 상태 정정 및 재개 (2026-10-11, 새 세션)
- **정정(§9가 낡음)**: 다른 세션이 §9 이후 작업을 이어서 원격에 올렸다. 7단계 통합 시험 결과서 완성(`feature-web-m1-integration-test.md`, CONDITIONAL PASS: High 2·Medium 5 열림), 9단계 보안 검증 결과서 완성(`security-web-m1-test.md`, **FAIL**: Critical 1·High 1 = 면책·AI 고지 미반영 DEF-9-007·008), 사용자 결정 4건(DEC-046, 추천안), 수정 단위 구현 W-FIX-BE·W-FIX-FE·W-FIX-INF(DEC-047). C-1·C-2 수정은 DEC-046 ①로 이미 승인·구현됨
- **지금 남은 순서(DEC-046)**: ①수정 단위 3건 독립 검증(06) ②9단계 보안 재검증(xfail→XPASS 전환 확인, 판정 재확정) ③7단계 영향분 재실행 ④8단계 전체 시험 ⑤11단계 최종 대조 ⑥관리자 로그인(아이디·비밀번호+이메일 코드)은 8단계 이후 시작, 시작 전 질문 8개 확인
- **이번 세션 1차 웨이브**: 수정 단위 독립 검증 3건(W-FIX-BE/FE/INF) ∥ 9단계 재검증(병렬). 7단계 영향분·8단계는 선행 결과 PASS 후
- **환경**: 클라우드 임시 PostgreSQL 16(127.0.0.1:54329, DB `ytweb_test_a`~`_f`·`_int`)·dockerd를 새로 기동. 임시 파일은 `.harness-tmp/`(저장소 미포함)
- **진행률(추정)**: 전체 약 82%, M1 약 98%
