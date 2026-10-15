# 관리자 로그인 설계 (DEC-055, 2026-10-15 / 개정 3: DEC-057)

> **개정 3 (DEC-057, 2026-10-15)**: 선생님이 DEC-056 의 "웹에서 관리자 계정 만들기" 화면을 **강하게 거부**했다("계정 만드는 화면을 달라고 한 적 없다. 아이디·비밀번호를 줬다. 로그인 화면만 만들어라. 나만 쓰는 것이고 다른 사람이 계정을 만들어 쓰면 절대 안 된다"). **DEC-056 의 최초 설정 방식(웹 계정 만들기 화면, `POST /api/v1/auth/setup`, `setup_required`, `reset-admin.bat`, `admin_cli reset`)은 폐기되었다(선생님 거부).** DEC-055 의 비밀 파일(`web\secrets\admin_login_*`)·`set-admin.bat`·`start.ps1` 입력도 계속 폐기 상태다. **새 방식**: 웹에는 **로그인 화면만** 있다. 관리자 아이디·비밀번호는 선생님 PC 의 `web\.env`(저장소 제외) 두 줄 `YTWEB_ADMIN_ID`, `YTWEB_ADMIN_PASSWORD` 로 **한 번 설정**하고, api 가 시작할 때 이 값으로 계정을 DB 에 scrypt 해시로 준비한다. **이 값이 없으면 아무도 로그인할 수 없다(닫힘).** 웹/API 로 계정을 만들 수 있는 경로가 없으므로 "다른 사람이 계정을 만들어 쓰는" 경로가 사라진다. 잠금·60분·속도 제한·세션 정책·감사는 그대로다.
>
> **왜 값을 `.env` 에 두는가(한 줄)**: 이 저장소는 공개라 아이디·비밀번호(또는 해시)를 코드·문서에 넣을 수 없고, 같은 비밀번호를 다른 곳에도 쓰고 있을 수 있어 해시도 올리지 않는다. 그래서 선생님 PC 한 곳(`web\.env`)에만 둔다.

선생님 요청: 로컬 서버(`http://127.0.0.1:8080`) 접속 시 **아이디·비밀번호 로그인**을 추가한다. github `toyo` 프로젝트의 로그인 개념을 따르되 **사용자는 관리자 1명**이고, **60분 지나면 자동 로그아웃**한다. 아이디·비밀번호 값은 저장소(공개)에 넣지 않는다(DEC-057: 선생님 PC 의 `web\.env` 에만 둔다).

## 1. toyo 로그인 설계 검토 (20년차 기준)

| 항목 | toyo 방식 | 판단 | 이 프로젝트 적용 |
|---|---|---|---|
| 인증 방식 | 세션 쿠키 + DB 세션 행(삭제 = 즉시 무효화) | 좋음. JWT보다 로그아웃·강제 만료가 쉽다 | **채택**. 이미 쿠키 세션(`sessions` 표, 토큰은 sha256만 저장)이 있어 그 위에 얹는다 |
| 비밀번호 저장 | Argon2 해시(`pwdlib`) | 좋음. 원문 저장 금지 | **scrypt+솔트**(파이썬 표준 `hashlib.scrypt`, 기존 PIN과 같은 방식)로 DB 에만 저장. 새 라이브러리·이미지 재빌드 위험 없이 같은 등급의 느린 해시. **DEC-057: 원문은 `web\.env` 와 api 컨테이너 환경 변수에만 있고(같은 PC 소유자만 열람) DB·코드·문서에는 해시만/없음** |
| 최초 계정 | 시드 데이터 / 교사 등록 화면(관리자가 계정 추가) | toyo 는 계정을 DB 시드/관리자 화면으로 관리하는 다중 사용자용 | **toyo 는 계정을 DB 시드/관리자 화면으로 관리, 여기는 관리자 1명을 `.env` 로 준비, 웹 생성 없음**(DEC-057). 웹에서 계정을 만드는 화면·API 가 없다 |
| 쿠키 속성 | HttpOnly, SameSite=Lax, Secure는 설정으로 | 좋음 | HttpOnly, **SameSite=Strict**(기존), 로컬 HTTP라 Secure 없음 |
| 로그인 실패 문구 | 동일 문구("아이디 또는 비밀번호가 올바르지 않습니다") | 좋음(계정 열거 방지) | **채택** |
| 세션 토큰 | `secrets.token_hex(32)`, DB에는 해시만 | 좋음 | `secrets.token_urlsafe(32)`, sha256만 저장(기존) |
| 만료 | 고정 만료(`expires_at`)만, **무활동 만료 없음** | 부족 | **60분 무활동 자동 로그아웃**(서버 + 화면 양쪽) |
| 실패 횟수 제한·잠금 | **없음** | 결함(무차별 대입 가능) | **추가**: 연속 5회 실패 시 5분 잠금, 반복하면 2배(최대 1시간), 성공 시 초기화. 로그인 요청 분당 10회 속도 제한 |
| CSRF | SameSite 쿠키만 | 약함 | **기존 방어 유지**: 출처 검증 + `X-CSRF-Token` |
| 로그인 시 세션 | 기존 세션 유지 | 개선 여지 | 로그인 성공 시 **기존 세션을 모두 종료**하고 새 세션 발급(세션 고정 방지, 관리자 1명) |
| 감사 기록 | 로그인 이력 표 | 좋음 | 기존 감사 로그에 `login.success`/`login.denied`/`session.delete` 기록(비밀번호는 절대 기록하지 않음) |
| 비밀번호 길이 | 4~20자 | 짧음 | 새 비밀번호 **8~64자**(선생님 값은 이 범위) |
| 계정 관리 화면·다중 권한 | 교사 등록, auth 레벨 | 이 프로젝트는 관리자 1명 | **만들지 않음**. 계정은 `web\.env` 두 줄로 준비하고, 바꾸거나 잊었으면 `.env` 를 고쳐 `start.ps1` 을 다시 실행한다(DEC-057). 계정 생성·초기화 화면/명령 없음 |
| 2단계 인증(이메일 코드) | — | DEC-046 계획이었음 | **이번에는 넣지 않음**(선생님이 toyo와 같은 개념 요청, 서버는 `127.0.0.1`에만 열림). 외부 접속 도입 시 재평가 |

## 2. 동작 규칙

- 로그인은 **항상 필수**다(`YTWEB_ADMIN_LOGIN=1`이 compose 기본). 웹에는 **로그인 화면만** 있다.
- **계정 준비(DEC-057)**: 선생님 PC 의 `web\.env`(저장소 제외) 에 `YTWEB_ADMIN_ID`(영문·숫자 4~20자), `YTWEB_ADMIN_PASSWORD`(8~64자) 두 줄을 **한 번** 적는다(형식 주의: 따옴표·`#` 금지). api 가 시작할 때 이 값으로 `admin_accounts` 의 계정을 **scrypt 해시로** 준비한다. **값이 바뀌었으면** 해시를 갱신하고 **기존 세션을 모두 종료**하며 **실패 잠금을 초기화**한다. 계정은 DB 에 **1개만** 둔다.
- **값이 없으면 닫힘(fail-closed)**: `YTWEB_ADMIN_ID`·`YTWEB_ADMIN_PASSWORD` 가 없거나 형식이 틀리면 아무도 로그인할 수 없다. 로그인 요청은 409 `login_not_configured`, 화면은 `.env` 설정 방법을 안내한다.
- **바꾸거나 잊었을 때**: 복구 화면·초기화 명령은 없다. `web\.env` 의 두 줄을 고치고 `.\web\scripts\start.ps1` 을 다시 실행한다(위 "값이 바뀌었으면" 동작으로 이전 세션 종료·잠금 초기화).
- **폐기됨(선생님 거부, DEC-057)**: DEC-056 의 웹 "관리자 계정 만들기" 화면, `POST /api/v1/auth/setup`, `me.setup_required`, `web\scripts\reset-admin.bat`, `python -m ytweb.admin_cli reset`. 근거: 선생님이 계정 만들기 화면을 요구한 적이 없고 아이디·비밀번호를 이미 주었으며, "다른 사람이 계정을 만들어 쓰면 절대 안 된다"는 요구와 웹 최초 설정(선점 가능)이 충돌한다.
- **폐기됨(DEC-056 에서 이미 폐기)**: DEC-055 원안의 비밀 파일 `web\secrets\admin_login_id`·`admin_login_password`(Docker secret), `set-admin.bat/.ps1`, `start.ps1` 의 아이디·비밀번호 입력.
- 익명 세션 발급(`POST /api/v1/auth/session`)은 로그인 모드에서 **막는다**(`login_required`). 기존 PIN 기능은 로그인 모드에서 쓰이지 않는다.
- **자동 로그아웃 60분(무활동)**: 마지막 사용자 조작 뒤 60분이면 로그아웃.
  - 서버: 마지막 요청(`last_seen`) 뒤 `YTWEB_SESSION_IDLE_MINUTES`(compose 기본 60)분이 지나면 세션을 지운다. 절대 만료는 기존대로 12시간.
  - 화면: 마우스·키보드·터치가 60분 없으면 로그아웃하고 로그인 화면으로 이동. 만료 5분 전에 "N분 뒤 자동 로그아웃됩니다" 안내와 **계속 사용** 버튼. 화면이 켜진 채 방치돼도 화면 타이머가 로그아웃한다(백그라운드 조회가 서버 시간을 늘리는 것을 막기 위함).
  - 서버 시간 기준은 `idle_timeout_seconds`로 화면에 내려 준다.

## 3. API 계약

모든 오류는 기존 problem+json(`code`,`title`,`detail`,`hint`). **계정을 만드는 API 는 없다**(`/auth/setup` 없음).

| 요청 | 설명 | 응답/오류 |
|---|---|---|
| `GET /api/v1/auth/me` | 상태 확인(호출하면 마지막 사용 시각이 갱신됨 = "계속 사용") | `{authenticated: bool, pin_required: bool, csrf_token: str\|null, login_required: bool, admin_login_id: str\|null, idle_timeout_seconds: int\|null}`. 로그인 모드에서 미인증이면 `login_required=true`(`pin_required=false`). **`setup_required` 는 없다** |
| `POST /api/v1/auth/login` | 본문 `{login_id: str(1~40), password: str(1~128)}`, 출처 검증, 속도 제한(분당 10) | 200 `{csrf_token, admin_login_id, idle_timeout_seconds}` + 쿠키. 401 `login_invalid`("아이디 또는 비밀번호가 올바르지 않습니다."), 429 `login_locked`(`Retry-After`), 403 출처 오류, 409 `login_not_configured`(`web\.env` 에 관리자 아이디·비밀번호가 설정되지 않음; 화면은 설정 방법을 안내) |
| `POST /api/v1/auth/session` | 기존 익명/PIN 세션 | 로그인 모드에서 403 `login_required`. 로그인 모드가 아니면 기존 동작 |
| `DELETE /api/v1/auth/session` | 로그아웃(기존) | 204 |
| 보호 API 전체 | 세션 필수(기존 `require_session`/`require_csrf`) | 세션 없음·만료 시 401 `session_required` |

화면 상태: `starting` → (`/auth/me`) → `online` 또는 `login_required`. `login_required`면 로그인 화면(아이디·비밀번호·로그인 버튼, 오류 문구, 잠금 안내). 로그인이 설정되지 않았으면(`login_not_configured`) 빨간 안내로 `web\.env` 설정 방법을 보여 준다. 사용 중 401(`session_required`)을 받으면 "로그인 시간이 지나 로그아웃되었습니다" 안내와 함께 로그인 화면으로 돌아간다.

## 4. 데이터

`admin_accounts(login_id PK, password_hash, created_at, updated_at, last_login_at)` — 마이그레이션 `0003`(그대로; DEC-057: 계정 행 1개는 api 시작 때 `.env` 값으로 준비·갱신되며 웹/API 로 만들거나 지울 수 없다). 실패 횟수·잠금은 기존 `web_settings`(KV)의 `admin_login_fail` 키(소유자 1명 전역 카운터, PIN과 같은 방식, 같은 PostgreSQL advisory lock으로 직렬화).

## 5. 알려진 한계 (정직하게)

- 관리자 1명이라 잠금은 **계정 전체**에 걸린다(공격자가 일부러 틀려 관리자를 잠글 수 있음, 최대 1시간). 서버가 `127.0.0.1`에만 열려 있어 같은 PC에서만 가능하다. 2단계 인증·외부 접속 도입 전에 재평가한다.
- **잔여 위험(DEC-057)**: 비밀번호 원문이 `web\.env` 와 api 컨테이너 환경 변수에 남는다(같은 PC 소유자만 열람 가능). DB 에는 scrypt 해시만 있다. `.env` 는 저장소에서 제외되어 있으므로 올리지 않는다. `.env` 형식 주의: 따옴표·`#` 금지.
- 웹/API 로 계정을 만들거나 초기화하는 경로가 없어 "최초 계정 선점"(TW-58)과 "초기화 오남용"(TW-59) 위협 경로 자체가 제거되었다. 대신 `.env` 를 고칠 수 있는 같은 PC 소유자를 신뢰한다.
- 비밀번호 강도 검사는 길이(8~64자)뿐이다. 복구용 이메일·2단계 인증은 없다(잊으면 `.env` 를 고쳐 `start.ps1` 재실행).
- ~~비밀번호 원문이 `web\secrets\admin_login_password` 파일에 남는다~~ 비밀 파일은 폐기되었으나 **원문이 `.env`·컨테이너 환경 변수에 남는 것으로 대체**(위 잔여 위험). ~~아이디·비밀번호를 터미널·웹 화면에서 입력~~ **DEC-057 으로 입력 화면 없음**(`.env` 두 줄).
