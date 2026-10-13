# t 보고서: 추적성 보강 (2026-10-13 UTC)

시작 02:15:20, 종료 약 02:22 (약 7분, 상한 12분 이내). docker·git 조작·제품 소스 편집 없음. 편집: docs/harness/traceability.md, 새 시험 `web/backend/tests/verify_trace/`(`__init__.py`, `test_trace_unlinked.py`), 새 가상환경 `.harness-tmp/t-cli`(CLI 의존성, requirements-dev.txt 설치).

## 명령
- 백엔드 W-N 시험: `cd web/backend && ../../.harness-tmp/be/bin/python -m pytest tests/test_rule_suggester.py tests/test_gemini_suggester.py tests/test_gemini_retry.py tests/domain/test_live_suggest.py tests/domain/test_verify_report.py tests/domain/test_live_sync.py tests/domain/test_source_edit.py tests/verify_ai_badge tests/domain/test_live_off_block.py tests/domain/test_live_check.py` → 74 통과.
- 프런트: `npx vitest run src/pages/ai.aibadge.test.tsx src/pages/batchdetail.execgate.test.tsx src/pages/formids.test.tsx src/lib/score.test.ts` → 22 통과(4 파일), `src/a11y.test.tsx` 8 통과.
- 새 시험: `pytest tests/verify_trace`.
- 결과 원문: `.harness-tmp/results/t/`(be-wn.txt, fe-wn.txt, new-run1.txt = 첫 실행 보존, new-run2.txt).

## 새 시험과 첫 실행 결과 (보존)
첫 실행(new-run1): 12개 중 **3 실패 + 3 xfail**. 실패 3건(NFR-006 커버리지, W-015 두 건)은 원인이 제품이 아니라 **웹 가상환경(.harness-tmp/be)에 CLI 의존성(googleapiclient, httplib2)이 없는 것**(`ModuleNotFoundError`). 시험 기대값은 바꾸지 않고, CLI 전용 가상환경 `.harness-tmp/t-cli` 를 만들어 그 파이썬으로 하위 프로세스를 돌리도록 시험 실행기만 수정했다. 재실행(new-run2): **9 통과, 3 xfail(strict)**, 실패 0.
- 통과 9: NFR-006(validator 100%, live_guard 100%, updater 100% 줄+분기), SEC-013(파일 4개 고정 + 해시 존재, 5건), W-015(CLI 동작·웹 임포트 / CLI 회귀 4개 파일), SEC-027 Gemini 타임아웃·재시도·토큰 상한.
- xfail(strict) 3, 구현이 요구에 못 미침: S-W10 CSV 업로드 엔드포인트 없음, POL-007 외부 AI 전송 고지 문구가 프런트에 없음(Gemini 가 이미 외부 전송 중), SEC-027 일/배치당 AI 호출·비용 상한 코드 없음.

## 추가·정정한 행
- 추가: W-N01~11 11행(표 1개). 시험 연결 없던 11개 분류표 11행. S9 연결 표 5행. 변경 이력 1행(v6).
- 정정: 결과서 ID 34개는 "시험 없음"이 아니라 **표기 차이**(TC-VI-025 ↔ test_tc_vi_025, 대소문자·밑줄). 대조해 W-016, D-01·03·04·05·06·07·10·11·12·13·14, S-W06·07·11·14, POL-014, W-M3-02, S-W17 의 ID 가 전부 실제 시험에 있음을 확인. 남은 TC-S9-nn 은 보안 결과서가 함수명으로 지정한 `web/tests_security/` 시험으로 연결. 시험을 "없음"으로 정정한 항목은 없다.

## 발견 (결함 후보, 고치지 않음)
1. `domain/test_google_router.py::test_tc_m2_030_disconnect_clears_token` 실패: 응답 `{'connected': False, 'revoked': False}` vs 시험 기대 `{'connected': False}`. 제품이 필드를 추가한 뒤 시험 미갱신으로 보이나 확인한 것은 아님. 시험은 고치지 않음. (e 에이전트 보고에는 12 통과였음)
2. POL-007: Gemini 가 외부 전송을 하는데 전송 고지 문구가 없음(미구현).
3. 시험 파일을 서로 다른 폴더(예: `tests/domain/test_live_gateway.py` 와 `tests/test_*.py`)를 한 명령에 섞으면 `api`/`env`/`seeded` fixture 오류 14건이 난다(각 폴더를 따로 돌리면 통과). 시험 구성 문제로 보이나 원인 확인은 안 함.

## 최종 숫자 (분모 = FR 20 + NFR 11 + POL 16 + SEC 48 + W 23 + D 16 + F 14 = 148, W-N 11 추가 후 159; EVT/UX/SCR/ADR/RISK 제외)
- 표에 시험 기재: 154/159 (96.9%)
- 시험이 소스에 실제 존재: 151/159 (95.0%)
- 이번에 실제 실행해 통과 확인: 14/159 (8.8%) (W-N01~11, NFR-006, SEC-013, W-015). 나머지는 8단계 기록 의존, 재실행 안 함.
- 이번 실행 실패 1 (W-M2-02 의 TC-M2-030)
- 미구현·결정 대기 5 (POL-012, POL-016, S-W10, POL-007, SEC-027 일부; 이미 Not Started 인 POL-006·008·013 은 xfail 고정으로 별도)
- 시험 대상 아님 2 (POL-015, S-W15)

## 남은 항목 (사유)
- POL-012, POL-016: 정책 미정, 시험 만들지 않음. S-W10: M2 대기. POL-007, SEC-027(상한): 구현 없음.
- POL-015, S-W15: 문서·정책.
- NFR-001: 선생님 Windows PC 필요.
- F-02, F-10: 문서에 시험 ID 없음(타입 생성 미적용, 실브라우저 점검만). F-11: a11y.test.tsx 가 있으나 표 연결은 이번에 안 고침.

## 한계
- 12분 상한 때문에 기존 행(요구 148개)의 통과를 전부 재실행하지 않았다. 범위 표기(`~`), 접미사 ID 는 끝점 개별 확인 안 함. 결과서 파일은 수정하지 않음. SEC-013 의 "PyPI 실존·라이선스"는 시험하지 않음(절차).
