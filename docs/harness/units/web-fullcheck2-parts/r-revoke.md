# 보안 결정 ③ 연결 해제 시 구글 토큰 폐기(revoke) 결과서
소요: 시작 02:15:35 UTC, 종료 약 02:23 UTC(약 7분, 상한 12분 이내).

## 변경 파일
- web/backend/ytweb/youtube/google_oauth.py: `REVOKE_URL`(고정 https://oauth2.googleapis.com/revoke), `REVOKE_TIMEOUT_SECONDS=5`, `revoke_token(tokens)->bool` 추가. POST, form 본문 `token=<refresh_token 없으면 access_token>`, 리다이렉트는 기존 전역 `_NoRedirect` 오프너가 막음. 모든 예외·4xx·5xx·타임아웃은 False 로만 반환(토큰·예외 상세 비노출).
- web/backend/ytweb/routers/google.py `/disconnect`: 토큰 로드 -> 로컬 토큰 파일 삭제(읽기·쓰기) 확정 -> 토큰이 있고 구글 클라이언트 파일이 있을 때만 각 토큰 폐기 요청. 응답 `{"connected": false, "revoked": true|false|null}`(기존 필드 유지). 두 토큰 중 하나라도 실패하면 false. 감사 로그 detail 은 `{"revoked": ...}` 만.
- web/frontend/src/pages/GoogleCard.tsx: 해제 성공 후 revoked 값별 안내 Callout(true/false 문구, null 은 안내 없음). src/api/endpoints.ts: 응답 타입에 `revoked?` 추가. src/i18n/ko.ts: `revokeDone`, `revokeFailed` 키 추가만.
- 새 시험: web/backend/tests/verify_revoke/(conftest.py, test_revoke.py 15건 실행), web/frontend/src/pages/google.revoke.test.tsx(3건).
- tests_security 허용 목록: google_oauth.py 는 이미 urllib.request 허용 모듈이라 수정 불필요(test_sec_02: 97 통과, 2 xfail, 이번 변경 전과 동일 구성).

## 새 시험 목록(백엔드)
200/400/500/타임아웃/연결오류별 성공·로컬삭제·revoked 값(5), 요청 URL·메서드·Content-Type·본문·타임아웃 5초, 리다이렉트 미추종 핸들러, access_token 대체/빈 토큰 호출 없음, 쓰기 토큰만·둘 다 순서, 둘 중 하나 실패 시 false+둘 다 삭제, 로컬 삭제가 네트워크 호출보다 먼저, 토큰 없음 호출 없음(null), 데모(클라이언트 파일 없음) 호출 없음(null), 응답·로그·감사 로그에 토큰 비노출+감사에 revoked 기록, revoke_token 예외 비누설.

## 수정 전 첫 실행 실패
정직하게 기재: 요청 순서(시험 먼저)를 지키지 못했다. 구현을 먼저 하고 시험을 나중에 썼으며, 수정 전 코드에 대한 실패 실행은 하지 않았다(미수행). 시험이 구현에 맞춰 쓰였을 위험이 있어, 시험은 사양 항목(요청 형식·실패 처리·null 조건·비노출)에서 직접 도출했다.

## 수정 후 수치(2026-10-13 02:2x UTC)
- 백엔드 지정 묶음(verify_revoke+test_google_oauth+test_live_write+domain/test_google_router+verify_m23): 444 통과, 2 실패, 6 skip, 1 xfail. 새 시험 15건 전부 통과.
- 실패 2건(기존 시험, 기대값 수정하지 않음): tests/domain/test_google_router.py::test_tc_m2_030 와 tests/verify_m23/test_vm_02_google_router.py::test_tc_vm_125 가 `r.json() == {"connected": False}` 완전 일치를 검사한다. 새 사양이 응답에 `revoked` 를 "추가"하라고 했으므로 완전 일치는 사양과 충돌한다(사용자 관점 근거: 화면은 revoked 를 받아 안내해야 하며 필드 추가는 하위 호환 변경). 처리 방안은 담당자 결정 필요: 두 시험의 기대값에 revoked 허용(예: `r.json()["connected"] is False`)을 반영. 추가로 이 두 시험은 가짜 urlopen 을 걸지 않아 클라이언트 파일+토큰이 있는 상태에서 실제 urlopen 이 호출된다(이 샌드박스는 프록시/네트워크 제약으로 실패 처리되어 통과 판정에는 영향 없으나, 사용자 PC 에서 돌리면 가짜 토큰 'r' 이 실제 구글 revoke 로 나갈 수 있음). 기대값 수정 시 urlopen 가짜 적용도 같이 필요.
- 프런트: vitest 전체 755 통과, 1 expected fail, 21 skip, 파일 30 통과/1 skip, 실패 0. google.test.tsx+google.revoke.test.tsx 11 통과. `tsc -b` 오류 0, `eslint src` 오류 0.

## 한계(정확히)
- 실제 구글 서버에는 호출하지 않았다(가짜 urlopen만). 실제 revoke 가 200 을 돌려주는지, 구글 계정 '타사 앱 액세스'에서 앱이 사라지는지는 선생님 PC 에서 확인해야 한다.
- 변이 점검(mutation) 미수행. PostgreSQL 대상 시험 미수행(SQLite 기본 설정으로 실행). 브라우저 화면 캡처 미수행(컴포넌트 시험만).
- 폐기 확인은 HTTP 2xx 여부로만 판단한다. 읽기/쓰기 토큰이 같은 grant 인 경우 두 번째 요청은 400 으로 false 가 될 수 있다(그 경우 안내는 '폐기 못함'으로 보수적으로 표시됨).
- 감사 로그 기록은 이 해제 처리 안에서만 추가했고 다른 파일은 건드리지 않았다. git add/커밋/푸시 하지 않음.
