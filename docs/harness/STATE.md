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
- **사용자 결정 대기(진행 비차단)**: WU-5 질문 5가지(승인 파일 HMAC 서명 추가 승인, planned 기록 정리 방법, 불확실 결과를 planned로 두는 규칙, 롤백에 승인 파일 요구 여부, 읽기 전용 필드 전송 가능 여부=12단계 실측), 기준 폴더를 프로젝트 루트로 고정할지, 금칙어 사전 검토, read_cost 0 하한, 403 안내 문구, CSV 위치 제한, blocked 재검증 상태 복귀(DESIGN 3-2 정정), 실제 Studio CSV 샘플
- **화면 캡처에서 발견한 UI 이상 6건**(소스 미수정, 결정 후 반영): 읽기·승인 명령 제목줄이 "모의 실행"으로 표시, 표 사유 말줄임, aborted 행이 변경 번호를 차지, 네트워크 오류 재시도 횟수 미표시, 게이트 배지 줄 맞춤, 롤백 안내 표기 불일치
- **git**: 허용됨(DEC-027). 원격 PROD_SCH에 푸시 완료. 사용자 커밋 2건의 Unverified 표시는 이력 재작성이 필요해 사용자 지시 전 보류
- **TC 번호**: WU-5 TC-6xx는 TC-9xx로 재번호(DEC-028)
- **임시 아티팩트(규칙 K)**: `.harness-tmp/`는 결과서 도구가 정리함
- **전체 진행률**: 약 70%
