# 실제 수정 "모든 영상 허용" 추가 내부 시험 결과서 (2026-10-14)

요청: 실제 수정 모드에서 영상마다 허용 목록(YTWEB_LIVE_ALLOWED_VIDEOS)에 ID를 넣는 일을 매번 하지 않게 해 달라(스크립트 포함).
변경: `YTWEB_LIVE_ALLOWED_VIDEOS=*` = 모든 영상 허용(`live_gateway.py` `allows_all`/`video_allowed`, `live_write.py` 게이트웨이 검사, `routers/google.py`·`schemas.py` `live_allowed_all`, `live_check.py` 안내, 화면 경고문). 스크립트 `web/scripts/live-allow-all.ps1/.bat`(web\.env 설정 + start.ps1 재시작). `.env.example` 설명, `docs/yt/openapi.json` +5줄.
유지되는 안전장치(변경 없음): YTWEB_LIVE_WRITE=1, 쓰기 로그인, 제목은 승인한 제안만, 배치 실행 확인 문구 "실제 실행 N건", 제외 규칙(비공개·어린이용·예약 라이브·쇼츠 설정), 롤백 거부 규칙. 약해지는 것: "허용 영상 목록 밖 영상은 실제로 안 바뀜" 보호 1겹 — `*` 설정 시에만, 기본값은 그대로(비어 있음).

| 시험 | 결과 |
|---|---|
| test_live_guard.py 14개(신규 2: `*`면 임의 영상 통과·ID 지정이면 차단 유지·빈 값이면 준비 안 됨) | 통과 |
| 백엔드 `-k "live or google or openapi or m3 or contract"` | 첫 실행 **1 실패**: test_saved_openapi_json_is_current(스키마에 `live_allowed_all` 추가로 docs/yt/openapi.json 불일치) → openapi.json 재생성 후 재실행 통과 |
| 프런트 전체 | 892 통과, 1 예상 실패, 21 건너뜀 / build·eslint 통과 |
미수행: 전체 백엔드 회귀(1800여 개), Windows 에서 live-allow-all.bat 실행(이 스크립트는 live-on.ps1 복제 기반, 실행 안 해 봄), 실제 구글 호출, 실제 제목 변경.
