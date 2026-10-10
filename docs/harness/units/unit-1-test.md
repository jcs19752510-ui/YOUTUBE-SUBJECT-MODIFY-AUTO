# 테스트 결과서 — WU-1 OAuth 인증 (6단계 단위 테스트)

## 1. 개요
- 테스트 대상: WU-1 OAuth 인증 (`auth, commands/auth`)
- 테스트 유형: 단위
- 적용 Tier: Standard (규칙 B 원문: 최소 2회)
- 적용 속도 트랙: L5
- 병렬 실행 정보: 단독 실행 (이 환경은 서브에이전트를 쓰지 않음, DEC-011)
- 테스트 목적: `unit-1-note.md`의 인수 조건(AC)을 테스트로 증명하고 안전 로직의 회귀를 막는다
- 관련 산출물: `docs/yt/DESIGN.md`, `docs/harness/units/unit-1-note.md`, `docs/yt/02_planning.md`
- 테스트 수행자(에이전트): 오케스트레이터(06단계 역할 직접 수행)
- 테스트 일시: 2026-10-10

## 2. 테스트 범위 및 제외 범위
- 범위(In-Scope): 읽기/쓰기 로그인 분리 저장, 토큰 로드·갱신·재로그인 안내, 토큰·키 비노출, 로컬 토큰 삭제, `auth` 명령(상태/--read/--write/--revoke)
- 제외 범위(Out-of-Scope) 및 사유: 실제 구글 서버와의 로그인·토큰 발급·갱신(사용자가 03 가이드 8장대로 수행), Windows 권한 제한(WU-0 TC-054와 동일 사유), 쓰기 범위의 최소성 확인(원문 미열람, 12단계 전 [확인 필요])

## 3. 테스트 환경
- 실행 환경: Linux, Python 3.12.3 (주 실행) · 3.11 · 3.13 (호환 확인), pytest, pytest-cov. 가상환경은 `.harness-tmp/` 아래에만 생성
- 테스트 데이터: 임시 폴더의 가짜 설정·DB·후보, 가짜 토큰 문자열(실제 비밀 아님). **실제 YouTube API는 호출하지 않음**
- 전제 조건: 이전 단위 WU-0 PASS(공통 기반)

## 4. 테스트 케이스 및 결과
| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고(검증하는 ID) |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-080 | 읽기 로그인은 읽기 토큰 파일만 저장하고 쓰기 토큰은 만들지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_auth.py::test_read_login_saves_only_read_token` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-016, SEC-015 |
| TC-081 | 쓰기 로그인은 별도 파일에 저장되고 읽기 토큰 파일을 건드리지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_auth.py::test_write_login_is_separate_file_and_leaves_read_token_untouched` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-004, SEC-015 |
| TC-082 | 기본 토큰 저장 위치는 프로젝트 폴더 밖이라 저장소에 올라갈 수 없다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_auth.py::test_token_dir_is_outside_project_by_default` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | ADR-004, SEC-008 |
| TC-083 | 저장된 토큰 파일은 소유자만 읽을 수 있고(POSIX), 임시 파일이 남지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_auth.py::test_token_file_permission_restricted` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-008 |
| TC-084 | 사용자가 권한 일부만 허용하면 저장하지 않고 안내한다(최소 권한 확인). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_auth.py::test_login_requires_all_requested_scopes` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-016 |
| TC-085 | 로그인 도중 예외 내용(토큰이 섞일 수 있음)은 오류 메시지에 노출하지 않고 종류만 남긴다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_auth.py::test_login_failure_masks_exception_content` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-008 |
| TC-086 | 클라이언트 비밀 파일이 없으면 03 가이드 위치를 안내한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_auth.py::test_missing_client_secret_points_to_guide` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007 |
| TC-087 | 유효한 읽기 토큰은 그대로 읽힌다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_auth.py::test_load_valid_token` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-016 |
| TC-088 | 토큰이 없으면 어떤 명령을 먼저 실행할지 알려 준다(읽기/쓰기 구분). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_auth.py::test_load_without_token_tells_next_step` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007 |
| TC-089 | 만료된 토큰은 갱신 토큰으로 갱신되어 파일에 다시 저장된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_auth.py::test_expired_token_is_refreshed_and_saved` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-016 |
| TC-090 | 갱신이 거부되면(7일 만료·철회) 재로그인 안내를 하고 토큰 내용은 노출하지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_auth.py::test_refresh_failure_asks_relogin_without_leaking` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-016, RISK-012, SEC-008 |
| TC-091 | 갱신 토큰이 없는 만료 토큰은 재로그인을 안내한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_auth.py::test_expired_without_refresh_token` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-016 |
| TC-092 | 손상된 토큰 파일은 삭제 후 재로그인 안내가 있는 AuthError가 된다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_auth.py::test_corrupted_token_file` | docstring의 기대 결과가 모두 충족 | Pass(4건) | Pass | NFR-007 / 변형 4건 |
| TC-093 | 필요한 권한 범위가 빠진 토큰(예: 쓰기 파일에 읽기 토큰)은 거부한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_auth.py::test_token_with_missing_scope_rejected` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-015 |
| TC-094 | 읽기 토큰을 읽을 때 쓰기 토큰 파일은 열지 않는다(깨져 있어도 영향 없음). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_auth.py::test_read_load_never_touches_write_token` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-015 |
| TC-095 | 로그인 삭제는 읽기·쓰기 토큰을 모두 지우고, 없어도 오류 없이 끝난다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_auth.py::test_revoke_deletes_both_and_is_idempotent` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-015 |
| TC-096 | 옵션 없이 실행하면 로그인 상태(없음)와 시작 안내를 보여 준다. 토큰 값은 읽지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_auth.py::test_cli_status_without_option` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-001, UX-001 |
| TC-097 | `auth --read`가 저장까지 끝내고, 화면과 로그 어디에도 토큰이 찍히지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_auth.py::test_cli_read_login_end_to_end_no_token_in_output_or_log` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-001, SEC-008 |
| TC-098 | `auth --write`는 '쓰기권한'을 직접 입력해야 진행하고, 입력이 없으면 토큰을 만들지 않는다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_auth.py::test_cli_write_requires_typed_confirmation` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | SEC-001, SEC-015 |
| TC-099 | `auth --revoke`는 로컬 토큰을 지우고 구글 쪽 회수 방법을 안내한다. 옵션 동시 지정은 거부. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_auth.py::test_cli_revoke_and_exclusive_options` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | EVT-001 |
| TC-100 | 클라이언트 비밀 파일이 올바르면 요청한 권한 범위로 실제 설치형 앱 흐름 객체가 만들어진다(네트워크 호출 없음). | 자동 테스트 환경(임시 폴더) | `pytest tests/test_auth.py::test_new_flow_builds_real_installed_app_flow_from_client_file` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-016 |
| TC-101 | 흐름에서 이미 한국어 AuthError가 올라오면 다른 오류로 바꾸지 않고 그대로 전달한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_auth.py::test_auth_error_from_flow_passes_through_unchanged` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | NFR-007 |
| TC-102 | 갱신 함수를 따로 주지 않으면 구글 인증 라이브러리의 기본 갱신 경로(Request)를 사용한다. | 자동 테스트 환경(임시 폴더) | `pytest tests/test_auth.py::test_default_refresh_path_uses_google_request` | docstring의 기대 결과가 모두 충족 | Pass(1건) | Pass | FR-016 |

### 4-1. 인수 조건 ↔ 테스트 케이스 추적
| AC | 인수 조건 | 연결 TC | 판정 |
|---|---|---|---|
| AC-01 | `auth --read`가 읽기 범위로 로그인하고 읽기 토큰만 저장 | TC-080, TC-087 | 충족 |
| AC-02 | `auth --write`는 별도 파일 저장, 읽기 토큰 불변, 직접 입력 확인 | TC-081, TC-098 | 충족 |
| AC-03 | 토큰은 프로젝트 밖에 저장, 권한 제한, 임시 파일 없음 | TC-082, TC-083 | 충족 |
| AC-04 | 권한 일부 허용 시 저장 안 함, 클라이언트 비밀 파일 없으면 가이드 안내, 실제 흐름 객체 생성, 한국어 오류 전달 | TC-084, TC-086, TC-100, TC-101 | 충족 |
| AC-05 | 토큰 읽기: 유효/없음(읽기·쓰기 구분 안내)/손상/범위 부족 | TC-088, TC-092, TC-093 | 충족 |
| AC-06 | 만료 갱신·저장, 갱신 실패와 갱신 토큰 없음은 재로그인 안내 | TC-089, TC-090, TC-091, TC-102 | 충족 |
| AC-07 | 화면·로그·오류 메시지에 토큰·키 비노출 | TC-085, TC-090, TC-097 | 충족 |
| AC-08 | 읽기 로드가 쓰기 파일을 열지 않음, revoke 둘 다 삭제·반복 안전 | TC-094, TC-095, TC-099 | 충족 |
| AC-09 | 옵션 없이 실행 시 상태 표시, 동시 옵션 거부 | TC-096, TC-099 | 충족 |

- 인수 조건에 연결되지 않은 TC(추가 안전 케이스): 없음
- 정상 경로, 경계값(날짜 경계·상한·빈 입력), 예외 입력(잘못된 형식·악성 문자열), 권한 경계를 포함했다.

## 5. 커버리지
- 전체 지표: 이 단위 모듈(ytitle.auth, ytitle.commands.auth)의 줄+분기 합산 **99%** (pytest-cov, `--cov-branch`)
- 회귀(이전 단위 산출물을 깨뜨리지 않음): 전체 테스트 스위트 `134 passed, 1 skipped` (통과)
- 호환 실행: 3.11 → 26 passed / 3.13 → 26 passed / 3.12(주) → 26 passed
- 커버되지 않은 부분과 사유:
  - src/ytitle/auth.py               77      0     18      0   100%
  - src/ytitle/commands/auth.py      36      1     10      1    96%   46
  - 이 단위 모듈의 줄·분기 커버리지는 위 수치(미커버 없음 또는 아래 목록).

## 6. 결함(Defect) 목록
| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 내용 |
|----|------|-----------|--------|------|-----------|
| DEF-6-010 | **토큰 파일 내용이 JSON 목록(`[]`)이면 `AttributeError`로 한국어 안내 없이 종료**(외부 파일 입력 경계 검증 누락) | TC-092 첫 실행(`[]` 케이스) | Medium | Fixed | 객체 여부 검사 추가, 예외 범위에 TypeError/AttributeError 포함 |
| DEF-6-011 | 테스트 코드의 미사용 import 1건 | pyflakes | Low | Fixed | 제거 |
| DEF-6-012 | [테스트 결함] TC-091이 갱신 토큰이 없을 때 갱신(네트워크)을 시도하지 않는지 확인하지 않음 | 변이 점검(검사 제거 변이 통과) | Medium | Fixed | 갱신 함수 호출 0회를 단언 |

- 두 결함 모두 이 단위 안에서 수정·재검증되었다(상위 산출물 결함 없음). 커버리지 점검에서 비어 있던 경로(실제 흐름 객체 생성, 흐름의 AuthError 통과, 기본 갱신 경로)는 결함이 아니라 테스트 공백으로 보고 TC-100~102를 추가했다. Open 결함 0건.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트: `.harness-tmp/junit_06.xml`, `.harness-tmp/junit_py311.xml`, `.harness-tmp/junit_py313.xml`, `.harness-tmp/junit_regress.xml`, `.harness-tmp/venv_py311`, `.harness-tmp/venv_py312`, `.harness-tmp/venv_py313` (+ 변이 점검용 임시 사본 `.harness-tmp/mut_06/`, 편집 설치로 생긴 `src/*.egg-info`, 캐시 `__pycache__`/`.coverage`)
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예 [ ] 아니오 — 예외: 편집 설치가 `src/ytitle.egg-info/`를 만들고 파이썬이 `__pycache__`를 만든다(둘 다 `.gitignore` 대상이며 정리 대상에 포함)
- 정리(삭제) 완료 여부: 예. 결과서 생성 스크립트가 `.harness-tmp/`, `data/`, `.coverage`, `src/*.egg-info`, `__pycache__`를 삭제했다
- **정리 후 점검: `git status`는 실행하지 않았다** — 프로젝트 지시(프롬프트 §1)로 git 명령 전면 금지(DEC-006). 대신 파일시스템 점검 결과를 첨부한다: 잔여물 없음 (점검 목록: .harness-tmp, .venv*, venv, *.egg-info, .pytest_cache, .coverage*, __pycache__, data)
- 병렬 실행이었다면: 해당 없음(단독 실행)
- 이번 테스트 도중 강제 중단: [x] 없음 / [ ] 있음

## 8. 리스크 및 잔존 이슈
- **미검증(PASS로 세지 않음)**: 실제 구글 서버와의 로그인·토큰 갱신·7일 만료 동작, 쓰기 범위의 최소성, Windows `icacls` 권한 제한(WU-0 TC-054와 동일)
- 잔존 위험: 로컬 악성코드가 토큰 파일을 읽는 위협은 완화(프로필 폴더, 권한 제한, 읽기/쓰기 분리)뿐이며 threat_model 5장의 Q-3-1 사용자 확인 대기
- 후속 조치: 사용자가 03 가이드대로 읽기 로그인을 실제로 수행해 결과 알림 / 12단계 전 쓰기 범위 확정

## 9. 결론 및 판정
- 판정: **PASS**
- 근거: 실패 TC 0건, 미수행 TC 0건(-), AC↔TC 추적 문제 0건, 정적 분석(pyflakes) 통과, 변이 점검 13/13 잡아냄, Open 결함 0건
- WU-2(조회)가 이 단위의 `load_credentials("read", ...)`를 입력으로 쓸 수 있다.

## 10. 내부 검증 (최소 2회)
- 1차(작성자 관점): AC↔TC 추적, 정적 분석, 커버리지에서 비어 있던 경로 보강. 결함 2건 발견·수정
- 2차(독립 심사자 관점): 변이 점검으로 토큰 노출·범위·분리·확인 절차 등 안전 로직 13곳을 일부러 망가뜨림. 결과는 부록 A
- 3차: 결함 0건 확인
- 검증 로그 파일 경로: `docs/harness/verify-log_unit-1-test.md`

### 부록 A. 변이 점검(코드를 일부러 망가뜨려 테스트가 실패하는지 확인)
| 변이 | 파일 | 결과 |
|---|---|---|
| 권한 범위 검사 제거(로드) | `auth.py` | 잡아냄(테스트 실패) |
| 쓰기 토큰을 읽기 파일에 저장 | `auth.py` | 잡아냄(테스트 실패) |
| 로그인 실패 시 예외 내용 노출 | `auth.py` | 잡아냄(테스트 실패) |
| 갱신 실패 시 예외 내용 노출 | `auth.py` | 잡아냄(테스트 실패) |
| 유효 토큰 검사 제거 | `auth.py` | 잡아냄(테스트 실패) |
| 일부 권한만 허용해도 저장 | `auth.py` | 잡아냄(테스트 실패) |
| 권한 제한 생략 | `auth.py` | 잡아냄(테스트 실패) |
| revoke가 읽기만 삭제 | `auth.py` | 잡아냄(테스트 실패) |
| 클라이언트 비밀 파일 확인 제거 | `auth.py` | 잡아냄(테스트 실패) |
| 쓰기 로그인 확인 제거 | `commands/auth.py` | 잡아냄(테스트 실패) |
| 토큰 없음 안내가 항상 --read | `auth.py` | 잡아냄(테스트 실패) |
| 갱신 토큰 없음 검사 제거 | `auth.py` | 잡아냄(테스트 실패) |
| 갱신 후 저장 생략 | `auth.py` | 잡아냄(테스트 실패) |

### 부록 B. 공유 문서 갱신
`traceability.md`의 단위테스트 컬럼과 구현 상태를 스크립트로 갱신했다(통과한 TC만 연결).
