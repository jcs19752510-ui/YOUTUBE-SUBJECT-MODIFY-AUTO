# 관리자 로그인 화면 FE3 결과서 (계정 만들기 화면 완전 제거 + 가운데 배치 확인)

- 시작 2026-10-15 03:08:42 UTC, 종료 03:11:25 UTC 이후 결과서 작성, 소요 약 3분(상한 12분 이내). 가짜 값 `testadmin` / `Test-Passw0rd!` 만 사용.

## 한 것
1. 삭제: `src/app/SetupForm.tsx`, `client.setup()`, 연결 상태 `setup_required`, `AuthMe.setup_required`, ko 문구 `setup` 블록, `AuthGate` 의 setup 분기. `grep -rni setup src` 결과는 시험 도우미 함수 이름(`userEvent.setup`, `const setup`)뿐이며 제품 코드에는 흔적 없음.
2. `LoginForm`: 409 `login_not_configured` 이면 서버 `title`+`hint` 를 빨간 안내줄에 그대로 표시(없으면 기존 문구).
3. 시험(`adminLogin.test.tsx`): SetupForm·client.setup·setup_closed·AuthGate 계정 만들기 시험을 삭제(사유: 해당 기능 자체가 제거됨, 기대값을 바꿔 통과시킨 것이 아니라 대상 소멸). 409 title+hint 표시 시험 1건 추가. 로그인·자동 로그아웃·접근성 시험은 유지.
4. 실제 크로미움(playwright, /opt/pw-browsers)으로 1280x800 캡처, `/api/v1/**` 는 `page.route` 모의.

## 화면 배치 결함에 대한 정확한 보고
- 요청은 "카드가 오른쪽 아래 구석"이었으나, 현재 소스(`styles/layout.css` `.auth-page` = `min-height:100vh; display:flex; align-items:center; justify-content:center`, 배경 회색, `.auth-card` 흰색·둥근 모서리·연한 테두리·폭 26.25rem=420px)로 빌드한 화면에서는 **구석 배치를 재현하지 못함**. 측정값(getBoundingClientRect): 1280x800 에서 카드 중심 (640, 400) = 뷰포트 정중앙, 다크 모드 (640, 400), 1920x1080 에서 (960, 540). 따라서 CSS 수정은 하지 않음. 선생님 캡처는 이전 빌드(이미지 재빌드 전)였을 가능성이 있으나 **확인한 것은 아님**; 선생님 PC 에서 새 소스로 `start.ps1` 재빌드 후 Ctrl+F5 로 확인 필요(미확인).

## 시험 결과
- 첫 실행 `npx vitest run`(삭제·추가 반영 후): 47 파일 통과 / 1 skip, 955 통과·1 expected fail·21 skip, 실패 0. 실패한 첫 실행 없음.
- `npm run build` 성공, `npx eslint src` 출력 없음(통과), `npx tsc --noEmit` 출력 없음(통과). 재실행(빌드·린트 후)도 동일.

## 스크린샷 (docs/harness/admin-login-shots/, 직접 열어 눈으로 확인)
| 파일 | 내용 | 판정 |
|---|---|---|
| 1-initial.png | 초기: 가운데 카드, 제목, 오른쪽 빨간 "아이디를 입력해 주세요.", 입력칸 2, 파란 전체폭 버튼(입력 전이라 연한 비활성색) | 가운데 확인 |
| 2-error-401.png | 401 오류 문구 | 파일 저장, 3·4와 같은 배치(개별 열람은 3·4·6만 함) |
| 3-locked-429.png | 429 잠금 문구 | 가운데 확인 |
| 4-not-configured-409.png | 409 서버 title+hint 표시(`web\.env`, 설정 방법) | 가운데 확인 |
| 5-after-login.png | 로그인 성공 후 앱 상단에 "관리자: testadmin"·[로그아웃] | 확인 |
| 6-dark-409.png | 다크 모드 | 가운데 확인 |

## 안 한 것 / 미확인
- 2-error-401.png 는 내용을 눈으로 열어 보지 않음(배치는 측정값 동일).
- 실제 백엔드 연동 시험 없음(전부 모의 응답). 선생님 PC 확인 안 함. 1024px 미만 폭 미확인(미지원 확정).
- 버튼이 입력 전 연한 색인 것은 비활성 상태 표시이며 입력 후 활성색은 캡처하지 않음.
