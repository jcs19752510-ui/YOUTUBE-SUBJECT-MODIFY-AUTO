# 관리자 로그인 설계 (DEC-055, 2026-10-15)

선생님 요청: 로컬 서버(`http://127.0.0.1:8080`) 접속 시 **아이디·비밀번호 로그인**을 추가한다. github `toyo` 프로젝트의 로그인 개념을 따르되 **사용자는 관리자 1명**이고, **60분 지나면 자동 로그아웃**한다. 아이디·비밀번호 값은 저장소(공개)에 넣지 않는다.

## 1. toyo 로그인 설계 검토 (20년차 기준)

| 항목 | toyo 방식 | 판단 | 이 프로젝트 적용 |
|---|---|---|---|
| 인증 방식 | 세션 쿠키 + DB 세션 행(삭제 = 즉시 무효화) | 좋음. JWT보다 로그아웃·강제 만료가 쉽다 | **채택**. 이미 쿠키 세션(`sessions` 표, 토큰은 sha256만 저장)이 있어 그 위에 얹는다 |
| 비밀번호 저장 | Argon2 해시(`pwdlib`) | 좋음. 원문 저장 금지 | **scrypt+솔트**(파이썬 표준 `hashlib.scrypt`, 기존 PIN과 같은 방식). 새 라이브러리·이미지 재빌드 위험 없이 같은 등급의 느린 해시 |
| 쿠키 속성 | HttpOnly, SameSite=Lax, Secure는 설정으로 | 좋음 | HttpOnly, **SameSite=Strict**(기존), 로컬 HTTP라 Secure 없음 |
| 로그인 실패 문구 | 동일 문구("아이디 또는 비밀번호가 올바르지 않습니다") | 좋음(계정 열거 방지) | **채택** |
| 세션 토큰 | `secrets.token_hex(32)`, DB에는 해시만 | 좋음 | `secrets.token_urlsafe(32)`, sha256만 저장(기존) |
| 만료 | 고정 만료(`expires_at`)만, **무활동 만료 없음** | 부족 | **60분 무활동 자동 로그아웃**(서버 + 화면 양쪽) |
| 실패 횟수 제한·잠금 | **없음** | 결함(무차별 대입 가능) | **추가**: 연속 5회 실패 시 5분 잠금, 반복하면 2배(최대 1시간), 성공 시 초기화. 로그인 요청 분당 10회 속도 제한 |
| CSRF | SameSite 쿠키만 | 약함 | **기존 방어 유지**: 출처 검증 + `X-CSRF-Token` |
| 로그인 시 세션 | 기존 세션 유지 | 개선 여지 | 로그인 성공 시 **기존 세션을 모두 종료**하고 새 세션 발급(세션 고정 방지, 관리자 1명) |
| 감사 기록 | 로그인 이력 표 | 좋음 | 기존 감사 로그에 `login.success`/`login.denied`/`session.delete` 기록(비밀번호는 절대 기록하지 않음) |
| 비밀번호 길이 | 4~20자 | 짧음 | 새 비밀번호 **8~64자**(선생님 값은 이 범위) |
| 계정 관리 화면·다중 권한 | 교사 등록, auth 레벨 | 이 프로젝트는 관리자 1명 | **만들지 않음**. 계정은 스크립트(`set-admin.ps1`)로만 설정 |
| 2단계 인증(이메일 코드) | — | DEC-046 계획이었음 | **이번에는 넣지 않음**(선생님이 toyo와 같은 개념 요청, 서버는 `127.0.0.1`에만 열림). 외부 접속 도입 시 재평가 |

## 2. 동작 규칙

- 로그인은 **항상 필수**다(`YTWEB_ADMIN_LOGIN=1`이 compose 기본). 비밀번호 파일이 없으면 **아무도 로그인할 수 없다**(열려 있지 않고 닫힘, fail-closed). `start.ps1`이 파일이 없으면 아이디·비밀번호를 물어 만든다.
- 아이디·비밀번호는 `web\secrets\admin_login_id`, `web\secrets\admin_login_password`(저장소 제외, Docker secret)에 있고, API가 시작할 때 DB의 `admin_accounts` 표에 **해시만** 반영한다(파일 값이 바뀌면 해시를 갱신하고 기존 세션을 종료).
- 익명 세션 발급(`POST /api/v1/auth/session`)은 로그인 모드에서 **막는다**(`login_required`). 기존 PIN 기능은 로그인 모드에서 쓰이지 않는다.
- **자동 로그아웃 60분(무활동)**: 마지막 사용자 조작 뒤 60분이면 로그아웃.
  - 서버: 마지막 요청(`last_seen`) 뒤 `YTWEB_SESSION_IDLE_MINUTES`(compose 기본 60)분이 지나면 세션을 지운다. 절대 만료는 기존대로 12시간.
  - 화면: 마우스·키보드·터치가 60분 없으면 로그아웃하고 로그인 화면으로 이동. 만료 5분 전에 "N분 뒤 자동 로그아웃됩니다" 안내와 **계속 사용** 버튼. 화면이 켜진 채 방치돼도 화면 타이머가 로그아웃한다(백그라운드 조회가 서버 시간을 늘리는 것을 막기 위함).
  - 서버 시간 기준은 `idle_timeout_seconds`로 화면에 내려 준다.

## 3. API 계약

모든 오류는 기존 problem+json(`code`,`title`,`detail`,`hint`).

| 요청 | 설명 | 응답/오류 |
|---|---|---|
| `GET /api/v1/auth/me` | 상태 확인(호출하면 마지막 사용 시각이 갱신됨 = "계속 사용") | `{authenticated: bool, pin_required: bool, csrf_token: str\|null, login_required: bool, admin_login_id: str\|null, idle_timeout_seconds: int\|null}`. 로그인 모드에서 미인증이면 `login_required=true`, `pin_required=false` |
| `POST /api/v1/auth/login` | 본문 `{login_id: str(1~40), password: str(1~128)}`, 출처 검증, 속도 제한(분당 10) | 200 `{csrf_token, admin_login_id, idle_timeout_seconds}` + 쿠키. 401 `login_invalid`("아이디 또는 비밀번호가 올바르지 않습니다."), 429 `login_locked`(`Retry-After`), 403 출처 오류, 409 `login_not_configured`(관리자 계정이 아직 없음) |
| `POST /api/v1/auth/session` | 기존 익명/PIN 세션 | 로그인 모드에서 403 `login_required`. 로그인 모드가 아니면 기존 동작 |
| `DELETE /api/v1/auth/session` | 로그아웃(기존) | 204 |
| 보호 API 전체 | 세션 필수(기존 `require_session`/`require_csrf`) | 세션 없음·만료 시 401 `session_required` |

화면 상태: `starting` → (`/auth/me`) → `online` 또는 `login_required`. `login_required`면 로그인 화면(아이디·비밀번호·로그인 버튼, 오류 문구, 잠금 안내). 사용 중 401(`session_required`)을 받으면 "로그인 시간이 지나 로그아웃되었습니다" 안내와 함께 로그인 화면으로 돌아간다.

## 4. 데이터

`admin_accounts(login_id PK, password_hash, created_at, updated_at, last_login_at)` — 마이그레이션 `0003`. 실패 횟수·잠금은 기존 `web_settings`(KV)의 `admin_login_fail` 키(소유자 1명 전역 카운터, PIN과 같은 방식, 같은 PostgreSQL advisory lock으로 직렬화).

## 5. 알려진 한계 (정직하게)

- 관리자 1명이라 잠금은 **계정 전체**에 걸린다(공격자가 일부러 틀려 관리자를 잠글 수 있음, 최대 1시간). 서버가 `127.0.0.1`에만 열려 있어 같은 PC에서만 가능하다. 2단계 인증·외부 접속 도입 전에 재평가한다.
- 비밀번호 원문이 `web\secrets\admin_login_password`(PC 로컬, 저장소 제외) 파일에 남는다. 다른 비밀 파일(`gemini_api_key` 등)과 같은 취급이다. PC가 1인 전용이라는 전제다.
- 아이디·비밀번호는 PC에서 한 번 입력해야 한다(저장소가 공개라 값을 올릴 수 없다).
