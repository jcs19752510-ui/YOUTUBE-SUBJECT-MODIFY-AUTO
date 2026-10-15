# 관리자 로그인 문서 개정 3 (DEC-057) 결과서

- 시작 2026-10-15 03:09:15 UTC, 종료 Thu Oct 15 03:10:50 UTC 2026 (소요 약 10분 이내, 상한 12분 준수)
- 고친 파일: docs/yt/ADMIN_LOGIN_DESIGN.md(개정 3 재작성, DEC-056 최초 설정 절 "폐기됨(선생님 거부)" 표시), docs/harness/decisions.md(DEC-057 추가만), docs/yt/API.md(setup 절 삭제·EVT-W05 예시·login_not_configured), docs/yt/threat_model.md(W11 TW-53/54 정정, TW-58/59 "제거" 상태 변경·행 유지, v1-W6), docs/yt/WEB_USER_MANUAL.md 3-1, WEB_FAQ.md, WEB_RUNBOOK.md, WEB_INSTALL.md 4-1(web\.env 따라 하기), CLAUDE.md(현황 줄 정정 + "요구를 글자 그대로 구현한다" 상시 지시 추가).
- grep(계정 만들기|setup_required|auth/setup|reset-admin|admin_cli|set-admin|ADMIN_ID_FILE|admin_login_): 과거 기록(decisions DEC-055/056, STATE.md, admin-login-*-test.md)을 제외하면 남은 곳은 전부 "폐기·삭제·제거됨" 명시 문장뿐(ADMIN_LOGIN_DESIGN, API.md 삭제 안내, threat_model TW-58/59·개정 줄, RUNBOOK 폐기 언급). 안내로서의 잔존 0.
- 수치 일치: 잠금 5회/5분→최대 1시간, 분당 10, 60분, 비밀번호 8~64, 아이디 4~20.
- 미확인/미수행: docs/yt/openapi.json 은 코드에서 생성되는 산출물이라 /auth/setup 항목이 남아 있음(코드 개정 단위에서 재생성 필요). STATE.md 갱신 안 함(소유 범위 지시 외). 코드(web/**)는 이 문서 기준으로 아직 개정 전. 선생님 PC 확인 안 함.
