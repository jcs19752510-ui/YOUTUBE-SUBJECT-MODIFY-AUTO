# 관리자 로그인 문서 개정 2 결과서 (DEC-056)

- 시작 2026-10-15 02:52:54 UTC, 종료 02:55 UTC경 (소요 약 3분, `date -u` 실측). 상한 12분 이내.
- 범위: 문서만 수정(`docs/**`, `CLAUDE.md`). 코드(`web/**`)·git 작업 없음.

## 고친 파일
| 파일 | 내용 |
|---|---|
| `docs/yt/ADMIN_LOGIN_DESIGN.md` | 개정 2 표기, DEC-055 폐기 부분 명시(원문은 "원안, 폐기"로 보존), §1 최초 계정·비밀번호 저장 행, §2 규칙, §3 `/auth/setup`·`me.setup_required`, §4, §5 한계(비밀번호 파일 항목 해소 처리, 최초 선점 위험 추가) |
| `docs/harness/decisions.md` | 맨 끝에 DEC-056 추가(기존 행 수정 없음) |
| `docs/yt/API.md` | EVT-W05 `setup_required`, EVT-W06b `POST /auth/setup`(요청·응답·오류표·감사), `login_not_configured` 설명 |
| `docs/yt/threat_model.md` | W11 TW-53·54 갱신, TW-58·59 추가, 개정 이력 v1-W5 |
| `docs/yt/WEB_USER_MANUAL.md` 3-1, `WEB_FAQ.md` 2-1, `WEB_RUNBOOK.md`(로그인 계정 항목), `WEB_INSTALL.md`(단계 4-1 신설, 안내 문구) | 따라 하기 형식(번호·명령·위치·결과·안 될 때) |
| `CLAUDE.md` | 프로젝트 현황에 관리자 로그인 한 줄 추가(기존 내용 불변) |
| `docs/harness/STATE.md` | 맨 아래 한 줄 추가 |

`web/README.md`, `web/.env.example` 은 이미 새 방식이어서 손대지 않았다(web 밖 대상 아님).

## 잔여 문자열 점검
명령: `grep -rnP '(?<!re)set-admin|admin_login_password|ADMIN_ID_FILE|ADMIN_PASSWORD_FILE' docs CLAUDE.md web/README.md web/.env.example` (과거 결과서 `docs/harness/admin-login-*-test.md` 제외, 이 파일 제외).
결과: 남은 곳은 전부 "폐기됨"을 설명하는 문장뿐이다: `ADMIN_LOGIN_DESIGN.md` 3·31·63행, `threat_model.md` 273행, `decisions.md` DEC-056 행(DEC-055 행은 수정 안 함), `STATE.md` 140·141행(140은 과거 기록). 현재 방식으로 안내하는 문장에는 없음. `ADMIN_ID_FILE`·`ADMIN_PASSWORD_FILE` 은 0건. (`admin_login_id` 는 API 응답 필드 이름이라 남는 것이 맞다.)

## 용어·수치 일치
잠금 5회→5분→최대 1시간, 무활동 60분(절대 12시간), 로그인·setup 분당 10회, 비밀번호 8~64자, 아이디 영문·숫자 4~20자, 확인 문구 `관리자초기화`, 오류 코드 `setup_closed`: 위 문서들에서 동일하게 적었다.

## 미확인
- 코드와의 대조: 실제 구현(`/auth/setup` 오류 코드·형식 검증 상세, `admin.setup` 감사 이름, `reset-admin` 출력 문구, 만들기 화면 버튼 이름 "만들기")은 코드를 보지 않고 지시문 기준으로 썼다. 구현 후 대조 필요.
- 시험 케이스 번호(TC-AL-)는 새 기능분을 매기지 않았다.
- 선생님 Windows PC 실제 확인 안 함.
