# DEF-LIVE-006 AI 제안 종류 표시 / 구글 연결 시 데모 문구 (A3)
소요: 01:22:46 ~ 약 01:30 UTC (약 7분).

## 원인 파악
- 백엔드는 이미 제안기 정보를 저장·전달한다: suggestions.py 가 source=`ai:{mock|rule|gemini}`(고치면 `+edited`)로 저장, serialize.suggestion_dict 가 `source` 를 그대로 내보냄. **백엔드·API 명세 변경 없음**(openapi.json/API.md 재생성 불필요).
- 프런트 SuggestionCard 가 종류를 버리고 모두 "AI 제안"으로 표시했음.
- 구글 연결(실제) 상태에서도 홈 "오늘 할 일"(영상 0개일 때)이 "데모 영상 200개를 불러와…" 문구와 "데모 영상 불러오기" 버튼을 보여 줌. 상단 띠(Layout ModeBadge)·홈 연결 상태는 이미 연결/실제 모드를 구분하고 있어 변경 없음.

## 변경 파일
- web/frontend/src/pages/SuggestionCard.tsx: `aiKindLabel(source)` 추가, 배지가 이를 사용. 모의 "연습용 모의 제안(데모)", 규칙 "규칙 기반 제안(영상 설명의 장면 제목을 조합)", Gemini "Gemini AI 제안", 직접 고침은 뒤에 "(직접 고침)", 종류 불명(옛 `ai`)은 기존 "AI 제안" 유지.
- web/frontend/src/pages/HomePage.tsx: 영상 0개 + (google.connected 또는 mode==='live')이면 데모 안내·버튼 대신 `aiBadgeNoVideosLive`("…아래 '구글(유튜브) 연결' 카드에서 내 채널 영상 목록을 불러오세요.") 표시. 데모 모드는 그대로.
- web/frontend/src/i18n/ko.ts: 키 추가만(suggestion.aiKindMock/Rule/Gemini/Edited, home.aiBadgeNoVideosLive).
- 새 시험: web/frontend/src/pages/ai.aibadge.test.tsx (7개), web/backend/tests/verify_ai_badge/test_source_exposed.py (6개).

## 수정 전 첫 실행(프런트 신규 시험 7개)
5 실패 / 2 통과. 실패: 모의·규칙·Gemini·직접 고침 표시(모두 "AI 제안"만 나옴), 구글 연결 시 데모 영상 안내 숨김. 통과 2: 옛 `ai` 표시, 데모 모드 안내 유지.
(참고: 첫 수정 후 실행에서 시험 자체 오류 3건 — 고정 근거 문구 "모의 근거"를 모의 문구로 오인, 같은 글자가 카드 제목에도 있어 중복 매칭 — 은 시험 코드 쪽 문제라 시험의 증거/검색어만 고쳤고 기대 동작은 바꾸지 않았다.)

## 수정 후 결과
- 프런트: tsc -b 0 오류, eslint 0, vitest 29 파일 통과 / 758 통과·21 skip·1 expected fail, 실패 0. 기존 시험 기대값 수정 없음.
- 백엔드: tests/domain tests/verify_ai_badge tests/test_rule_suggester.py tests/test_gemini_suggester.py 300 통과, 17 skip, 실패 0 (01:30 UTC).

## 한계
- 화면을 눈으로 확인·캡처하지 않음(jsdom 시험만).
- VideosPage.tsx(편집 금지)의 빈 목록 문구 `videos.emptyFirstBody`("…데모 영상 200개를 만들 수 있습니다")는 구글 연결 상태에서도 나옴 — 다른 에이전트 담당이라 미수정. 같은 방식(연결 상태면 aiBadge 계열 문구)으로 고쳐야 함. (기존 시험 videos.test TC-WF-032 가 이 문구를 기대하므로 연결 상태 분기 시 데모 기준 유지.)
- 영상 자체의 source(demo/live)는 API에 없어 "연결 상태(대시보드)" 기준으로 판단. 모의 제안은 데모 영상에만 생성되므로(suggestions.py:157) 제안 배지 쪽은 영상 source 와 일치.
- aiNotice("AI가 생성한 제안입니다…")는 규칙 기반에도 그대로 나옴(미변경).
