# 일괄 승인 백엔드 회귀 B (be-regress-b)

시작 2026-10-13 03:39:07 UTC, 종료 03:41 UTC (총 약 2분, 상한 12분 이내). 소스·시험·git 무변경.

## 결론
회귀 B 구간 실패 0 (일괄 승인 변경과 무관한 회귀 없음). 폴더 목록 대조 결과 빠진 폴더 없음.

## 구간 대조 (ls web/backend/tests)
이미 확인: core, domain, test_*.py, verify_ai_badge, verify_fix_be, verify_m23, verify_revoke, verify_spec, verify_bulk. 타 에이전트: verify_wa, verify_wb. 이 에이전트: verify_wfixbe, verify_trace. 그 밖의 폴더 없음(`__pycache__` 제외).

## 실행
공통: `cd web/backend; YTWEB_TEST_PG_URL=postgresql+psycopg://postgres@127.0.0.1:54329/<DB> .harness-tmp/venv_06_web_be_b/bin/python -m pytest <구간> -o addopts= -q -p no:cacheprovider`
| 구간 | DB | 통과 | 실패 | 건너뜀 | xfail | 소요(date) |
|---|---|---|---|---|---|---|
| verify_wfixbe | ytweb_test_e1 | 16 | 0 | 0 | 1 | 03:39:17~03:39:33 |
| verify_trace | ytweb_test_e2 | 9 | 0 | 0 | 3 | 03:39:40~03:40:01 |

## verify_trace와 t-cli venv
시험(test_trace_unlinked.py:18)은 환경변수 TRACE_CLI_PY 또는 `.harness-tmp/t-cli/bin/python`을 CLI(`src/youtube_title`) 시험·커버리지용 인터프리터로 서브프로세스 실행한다. 저장소 밖 설치는 없고 `.harness-tmp/`(gitignore) 안이라 생성 허용으로 판단, `python3 -m venv .harness-tmp/t-cli` + `pip install -r requirements.txt -r requirements-dev.txt`(네트워크 정상, 약 20초) 완료. 이전의 verify_trace 실패는 이 venv 부재 때문이었다(venv 생성 후 재실행에서 실패 0; 부재 상태 실패는 이 에이전트가 직접 재현하지 않고 전달받은 내용). 규칙 K: 남은 임시물 = `.harness-tmp/t-cli`(venv). 정리 승인되면 삭제 가능.

## xfail 4건
시험에 표시된 기존 알려진 xfail이며 이번 변경으로 새로 생긴 것인지는 미확인(xfail 사유 미조사).

## 실패 분류
없음. 임시 DB ytweb_test_e1, e2는 삭제함. 남은 프로세스 없음.

## 미수행 / 질문
- xfail 4건의 사유·기준선 대비 증감은 확인하지 않음.
- 질문: `.harness-tmp/t-cli` 유지 여부.
