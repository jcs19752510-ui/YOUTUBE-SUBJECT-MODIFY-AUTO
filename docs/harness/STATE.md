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

## 4. 지금 상태
- **현재 작업**: 6단계 WU-4(plan/rollback 계획, L5) 구현 중. WU-0·1·2·3 PASS(전체 회귀 441 passed/1 skipped, 3.11/3.12/3.13)
- **다음에 할 일**: WU-4 독립 검증·결과서 → WU-5 ∥ WU-6 → 07 통합 테스트 → 8~11단계 → 12단계 직전 사용자 승인 요청
- **사용자 응답 대기(진행 비차단)**: Q-3-1, Q-2-1, 금칙어 사전 검토, read_cost 0 하한, 403 안내 문구, 네트워크 허용 도메인(원문 재확인), 쓰기 범위 확정
- **임시 아티팩트(규칙 K)**: `.harness-tmp/venv_agent_wu4`(서브에이전트 작업 중). 결과서 도구 실행 전 서브에이전트 종료 확인 필수. git 명령 미실행(DEC-006)
- **마지막 갱신**: 2026-10-10, DEC-026 직후
- **전체 진행률**: 약 55%
