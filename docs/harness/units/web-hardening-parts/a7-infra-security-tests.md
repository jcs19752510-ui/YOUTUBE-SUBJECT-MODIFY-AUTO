# A7 infra/security 시험 갱신 결과서 (2026-10-13, 시작 01:30:25 UTC, 종료 약 01:35 UTC, 소요 약 5분)

수정 전(첫 실행): 5건 실패. 수정 후: 510 통과 / 0 실패 / 427 건너뜀 / 3 xfail (43.77s). 5번은 아래 참고(실행 중 frontend/dist 가 생겨 통과).

| # | 시험 | 수정 전 실패 첫 줄(원문) | 원인(근거) | 조치 |
|---|---|---|---|---|
|1|test_vi_install… test_tc_vi_027 (tests_infra/test_vi_independent.py:479)|`AssertionError: assert ['_common.ps1...-on.ps1', ...] == ['_common.ps1...sts.ps1', ...]` / `At index 4 diff: 'live-off.ps1' != 'logs.ps1'`|scripts/ 에 live-on.ps1·live-off.ps1 추가(목록만 불일치)|목록에 2개 추가. 규칙 검사(UTF-8 BOM, CR 없음, 위험 명령 금지, 비밀 출력 금지)는 그대로 두었고 신규 3개 ps1(live-check/on/off)이 모두 통과함. BOM 3개 직접 확인(ef bb bf). .bat 은 이 시험 대상 아님(미검사)|
|2|test_vif_051 (tests_infra/test_vinf2_static.py:535)|`assert 2 == 1 ... 'Test-Path'.count` (fn.count("Test-Path") == 1)|scripts/_common.ps1:73-75: Gemini 오버레이가 추가됨. 조건 = 키 파일 존재 AND 길이>0, 구글 파일 유무와 독립|"Test-Path 1곳" 기대를 2곳으로 바꾸고 Gemini 조건 정규식과 순서(구글 오버레이 뒤)를 추가. 구글 조건 검사는 그대로. 기대값 완화가 아니라 새 요구(키 비었으면 외부망 불개방)를 정규식으로 더 엄격히 검사|
|3|test_sec_02 test_ytweb_has_no_outbound_capable_imports (:343)|`AssertionError: [('ai/gemini.py', 'import urllib.request')]`|ai/gemini.py:11 `import urllib.request`|허용 목록에 ai/gemini.py 만 추가(정확히 `import urllib.request` 한 줄만; 다른 라이브러리는 여전히 금지)|
|4|test_sec_09 test_d4 (:384)|`AssertionError: ['ai/gemini.py', 'youtube/google_oauth.py', 'youtube/live_read.py', 'youtube/live_write.py']` / `assert [...4] == [...3]`|동일|기대 목록을 정확히 4개로 갱신, 함수명 three->four|
|5|test_sec_09 test_f2 (:434)|`AssertionError: 이 검증은 법률 자문이 아니며 ... assert '...' in ''`|원인은 문구 변경이 아니라 번들 없음: 첫 실행 시 web/frontend/dist/assets 부재(`ls` 실패) -> js 가 빈 문자열. 4개 문구는 frontend/src/i18n/ko.ts:49,51,56,8 에 모두 존재(AB 문구는 '…중이 아님을 확인했습니다.' 포함). 편집 안 함|마지막 실행에서는 dist 가 생겨 통과. 다른 에이전트의 빌드 이후 재확인 필요|

## gemini.py 허용 근거 (코드로 확인)
- 고정 URL 상수 ENDPOINT=https://generativelanguage.googleapis.com/... 만 사용(gemini.py:20), 호스트가 사용자 입력에서 오지 않음(model 만 경로에 들어감, 환경변수 YTWEB_GEMINI_MODEL).
- 키는 `x-goog-api-key` 헤더로만 전송, URL·로그·예외 메시지에 넣지 않음(오류 문구는 고정 한글, `from None`).
- ai/factory.py:22-23: 키 파일을 읽어 값이 있을 때만 GeminiSuggester, 아니면 RuleSuggester(키 없음/데모는 호출 없음). 데모 모드 자체 분기는 factory 외에 확인하지 않음(한계).
- compose.gemini.yaml: api·worker 에만 egress 망 + secret 부착, db·web 제외. _common.ps1:75 키 파일이 비어 있지 않을 때만 포함. compose.online.yaml 에는 gemini 언급 없음.
- 한계: 응답 sanitize(ai.guard) 호출, 키가 실제 로그에 안 나오는지는 동적 시험하지 않음(코드 읽기만).

## 변이 점검
임시 복사본(ytweb 를 mktemp 로 복사)에 core/evil.py(`import urllib.request`)를 추가해 test_d4 로직을 재현: hits 에 core/evil.py 가 포함되어 기대 4개 목록과 불일치(False) -> 가드가 실제로 잡음. test_sec_02 가드는 파일 경로가 허용 집합에 없으면 hit 로 남는 구조(읽어서 판단, 별도 실행 안 함). 소스는 수정하지 않음, 복사본 삭제함.

## 한계
.bat 파일(live-on/off.bat)은 시험 대상 아님. 프런트 빌드 상태는 다른 에이전트 의존.
