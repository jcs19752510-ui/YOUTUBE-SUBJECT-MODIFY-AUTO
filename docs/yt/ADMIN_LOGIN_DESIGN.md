# 관리자 로그인 설계 (DEC-055, 2026-10-15 / 개정 2: DEC-056)

> **개정 2 (DEC-056, 2026-10-15)**: 선생님이 서버 시작 때 터미널에서 아이디·비밀번호를 입력받는 방식을 강하게 거부했다. **DEC-055 에서 아래 부분이 DEC-056 으로 대체(폐기)되었다**: ①비밀 파일 `web\secrets\admin_login_id`·`admin_login_password`(Docker secret) ②`start.ps1` 의 아이디·비밀번호 입력 ③`set-admin.bat/.ps1` ④API 시작 때 파일 해시를 DB 에 반영하는 동작 ⑤"비밀 파일이 없으면 로그인 불가". **새 방식**: 계정이 없으면 웹이 "관리자 계정 만들기" 화면을 보여 `POST /api/v1/auth/setup` 으로 만든다(한 번만, 만들면 영구히 닫힘). 서버를 띄울 때 입력은 없다. 아래 본문은 DEC-056 기준으로 고쳤고, 대체된 DEC-055 원래 내용은 "(DEC-055 원안, 폐기)"로 표시해 남겼다. 나머지(잠금·60분·속도 제한·세션 정책·감사)는 그대로다.

선생님 요청: 로컬 서버(`http://127.0.0.1:8080`) 접속 시 **아이디·비밀번호 로그인**을 추가한다. github `toyo` 프로젝트의 로그인 개념을 따르되 **사용자는 관리자 1명**이고, **60분 지나면 자동 로그아웃**한다. 아이디·비밀번호 값은 저장소(공개)에 넣지 않는다(DEC-056: 웹에서 직접 정하며 PC 에 파일로 남지 않는다).

## 1. toyo 로그인 설계 검토 (20년차 기준)

| 항목 | toyo 방식 | 판단 | 이 프로젝트 적용 |
|---|---|---|---|
| 인증 방식 | 세션 쿠키 + DB 세션 행(삭제 = 즉시 무효화) | 좋음. JWT보다 로그아웃·강제 만료가 쉽다 | **채택**. 이미 쿠키 세션(`sessions` 표, 토큰은 sha256만 저장)이 있어 그 위에 얹는다 |
| 비밀번호 저장 | Argon2 해시(`pwdlib`) | 좋음. 원문 저장 금지 | **scrypt+솔트**(파이썬 표준 `hashlib.scrypt`, 기존 PIN과 같은 방식)로 DB 에만 저장. 새 라이브러리·이미지 재빌드 위험 없이 같은 등급의 느린 해시. **DEC-056: 평문 비밀번호 파일은 PC 에 남지 않는다**(DEC-055 원안의 비밀 파일 폐기) |
| 최초 계정 | 시드 데이터 / 교사 등록 화면(관리자가 계정 추가) | 계정 관리 화면이 필요한 다중 사용자용 | **웹 최초 설정**: 계정이 없을 때만 "관리자 계정 만들기"(`/auth/setup`)가 열리고 만들면 영구히 닫힘. 서버 시작 때 입력 없음(DEC-056). 선점 위험은 §5 |
| 쿠키 속성 | HttpOnly, SameSite=Lax, Secure는 설정으로 | 좋음 | HttpOnly, **SameSite=Strict**(기존), 로컬 HTTP라 Secure 없음 |
| 로그인 실패 문구 | 동일 문구("아이디 또는 비밀번호가 올바르지 않습니다") | 좋음(계정 열거 방지) | **채택** |
| 세션 토큰 | `secrets.token_hex(32)`, DB에는 해시만 | 좋음 | `secrets.token_urlsafe(32)`, sha256만 저장(기존) |
| 만료 | 고정 만료(`expires_at`)만, **무활동 만료 없음** | 부족 | **60분 무활동 자동 로그아웃**(서버 + 화면 양쪽) |
| 실패 횟수 제한·잠금 | **없음** | 결함(무차별 대입 가능) | **추가**: 연속 5회 실패 시 5분 잠금, 반복하면 2배(최대 1시간), 성공 시 초기화. 로그인 요청 분당 10회 속도 제한 |
| CSRF | SameSite 쿠키만 | 약함 | **기존 방어 유지**: 출처 검증 + `X-CSRF-Token` |
| 로그인 시 세션 | 기존 세션 유지 | 개선 여지 | 로그인 성공 시 **기존 세션을 모두 종료**하고 새 세션 발급(세션 고정 방지, 관리자 1명) |
| 감사 기록 | 로그인 이력 표 | 좋음 | 기존 감사 로그에 `login.success`/`login.denied`/`session.delete`(+DEC-056 `admin.setup`) 기록(비밀번호는 절대 기록하지 않음) |
| 비밀번호 길이 | 4~20자 | 짧음 | 새 비밀번호 **8~64자**(선생님 값은 이 범위) |
| 계정 관리 화면·다중 권한 | 교사 등록, auth 레벨 | 이 프로젝트는 관리자 1명 | **만들지 않음**. 계정은 최초 설정 화면에서 한 번 만들고, 잊었을 때는 `reset-admin.bat` 으로 초기화 후 다시 만든다(DEC-056) |
| 2단계 인증(이메일 코드) | — | DEC-046 계획이었음 | **이번에는 넣지 않음**(선생님이 toyo와 같은 개념 요청, 서버는 `127.0.0.1`에만 열림). 외부 접속 도입 시 재평가 |

## 2. 동작 규칙

- 로그인은 **항상 필수**다(`YTWEB_ADMIN_LOGIN=1`이 compose 기본). **계정이 없으면 아무도 API 를 쓸 수 없고**(닫힘, fail-closed) 웹은 "관리자 계정 만들기" 화면만 보여 준다. 계정이 있으면 로그인 화면이다.
- **최초 계정 만들기(DEC-056)**: 화면 입력은 아이디(영문·숫자 4~20자)·비밀번호(8~64자)·비밀번호 확인(화면에서만 대조). `POST /api/v1/auth/setup {login_id,password}` 가 계정을 `admin_accounts` 에 **scrypt 해시로만** 저장하고 바로 로그인된 세션을 돌려준다. **계정이 한 번 생기면 이 화면과 API 는 영구히 닫힌다**(409 `setup_closed`; 동시에 두 요청이 와도 DB 잠금으로 한 건만 성공). 출처 검사가 먼저, 속도 제한 분당 10회. `start.ps1` 은 관리자 아이디·비밀번호를 묻지 않는다.
- **잊었을 때(DEC-056)**: `web\scripts\reset-admin.bat`(확인 문구 `관리자초기화`)가 api 컨테이너의 `python -m ytweb.admin_cli reset` 으로 계정·세션·잠금을 지우고, 웹에서 새 계정을 만든다. 복구(원래 비밀번호 확인)는 없다. 다른 사람이 먼저 계정을 만들었을 때도 같은 방법이다.
- (DEC-055 원안, 폐기) 아이디·비밀번호를 `web\secrets\admin_login_id`, `admin_login_password` 파일(Docker secret)에 두고 `start.ps1` 이 없으면 물어 만들며, API 가 시작할 때 해시를 DB 에 반영하고 값이 바뀌면 세션을 종료한다. 비밀 파일이 없으면 로그인 불가.
- 익명 세션 발급(`POST /api/v1/auth/session`)은 로그인 모드에서 **막는다**(`login_required`). 기존 PIN 기능은 로그인 모드에서 쓰이지 않는다.
- **자동 로그아웃 60분(무활동)**: 마지막 사용자 조작 뒤 60분이면 로그아웃.
  - 서버: 마지막 요청(`last_seen`) 뒤 `YTWEB_SESSION_IDLE_MINUTES`(compose 기본 60)분이 지나면 세션을 지운다. 절대 만료는 기존대로 12시간.
  - 화면: 마우스·키보드·터치가 60분 없으면 로그아웃하고 로그인 화면으로 이동. 만료 5분 전에 "N분 뒤 자동 로그아웃됩니다" 안내와 **계속 사용** 버튼. 화면이 켜진 채 방치돼도 화면 타이머가 로그아웃한다(백그라운드 조회가 서버 시간을 늘리는 것을 막기 위함).
  - 서버 시간 기준은 `idle_timeout_seconds`로 화면에 내려 준다.

## 3. API 계약

모든 오류는 기존 problem+json(`code`,`title`,`detail`,`hint`).

| 요청 | 설명 | 응답/오류 |
|---|---|---|
| `GET /api/v1/auth/me` | 상태 확인(호출하면 마지막 사용 시각이 갱신됨 = "계속 사용") | `{authenticated: bool, pin_required: bool, csrf_token: str\|null, login_required: bool, setup_required: bool, admin_login_id: str\|null, idle_timeout_seconds: int\|null}`. 로그인 모드에서 미인증이고 계정이 있으면 `login_required=true`, **계정이 없으면 `setup_required=true`(이때 `login_required=false`)**, 둘 다 `pin_required=false` |
| `POST /api/v1/auth/setup` | (DEC-056) 본문 `{login_id: 영문·숫자 4~20자, password: 8~64자}`, 출처 검증, 속도 제한(분당 10). 계정이 없을 때 한 번만 | 200 `{csrf_token, admin_login_id, idle_timeout_seconds}` + 쿠키(바로 로그인됨), 감사 `admin.setup`. 409 `setup_closed`(계정이 이미 있음, 영구), 409 `login_disabled`, 403 출처 오류, 422 형식 위반, 429 `rate_limited` |
| `POST /api/v1/auth/login` | 본문 `{login_id: str(1~40), password: str(1~128)}`, 출처 검증, 속도 제한(분당 10) | 200 `{csrf_token, admin_login_id, idle_timeout_seconds}` + 쿠키. 401 `login_invalid`("아이디 또는 비밀번호가 올바르지 않습니다."), 429 `login_locked`(`Retry-After`), 403 출처 오류, 409 `login_not_configured`(관리자 계정이 아직 없음; 화면은 `setup_required` 로 만들기 화면으로 안내) |
| `POST /api/v1/auth/session` | 기존 익명/PIN 세션 | 로그인 모드에서 403 `login_required`. 로그인 모드가 아니면 기존 동작 |
| `DELETE /api/v1/auth/session` | 로그아웃(기존) | 204 |
| 보호 API 전체 | 세션 필수(기존 `require_session`/`require_csrf`) | 세션 없음·만료 시 401 `session_required` |

화면 상태: `starting` → (`/auth/me`) → `online`, `login_required` 또는 `setup_required`(DEC-056: 관리자 계정 만들기 화면, 만들면 바로 `online`). `login_required`면 로그인 화면(아이디·비밀번호·로그인 버튼, 오류 문구, 잠금 안내). 사용 중 401(`session_required`)을 받으면 "로그인 시간이 지나 로그아웃되었습니다" 안내와 함께 로그인 화면으로 돌아간다.

## 4. 데이터

`admin_accounts(login_id PK, password_hash, created_at, updated_at, last_login_at)` — 마이그레이션 `0003`(DEC-056 에서도 그대로; 계정 행은 `/auth/setup` 이 만들고 `reset-admin` 이 지운다). 실패 횟수·잠금은 기존 `web_settings`(KV)의 `admin_login_fail` 키(소유자 1명 전역 카운터, PIN과 같은 방식, 같은 PostgreSQL advisory lock으로 직렬화).

## 5. 알려진 한계 (정직하게)

- 관리자 1명이라 잠금은 **계정 전체**에 걸린다(공격자가 일부러 틀려 관리자를 잠글 수 있음, 최대 1시간). 서버가 `127.0.0.1`에만 열려 있어 같은 PC에서만 가능하다. 2단계 인증·외부 접속 도입 전에 재평가한다.
- **최초 계정 선점 위험(DEC-056)**: 계정이 생기기 전에는 처음 `/auth/setup` 을 부른 쪽이 관리자가 된다. 서버가 `127.0.0.1` 에만 열려 있어 **같은 PC 의 다른 사용자·프로세스**만 가능하고, 선생님이 서버 시작 직후 바로 만드는 것을 전제로 한다. 완화: 출처 검사·분당 10회·한 번만(영구 닫힘). 다른 사람이 먼저 만들었다면 `reset-admin.bat` 으로 초기화 후 다시 만든다(위협 TW-58).
- `reset-admin` 은 같은 PC 소유자(Docker 접근 권한)만 실행할 수 있고, 지운 기록은 감사 로그(`admin.reset`, 삭제된 계정 수만)와 CLI 출력에 남는다(TW-59).
- 비밀번호 강도 검사는 길이(8~64자)뿐이다. 복구용 이메일·2단계 인증은 없다(잊으면 초기화).
- ~~비밀번호 원문이 `web\secrets\admin_login_password` 파일에 남는다~~ **DEC-056 으로 해소**(파일 자체가 없음). ~~아이디·비밀번호를 PC 에서 터미널로 한 번 입력해야 한다~~ **DEC-056 으로 해소**(웹 화면에서 입력).
