# 내부 검증 로그 — 11단계 최종 대조 2차 (`verify-log_doc-reconcile-web-2.md`)

- 대상: docs/yt/WEB_USER_MANUAL.md, WEB_FAQ.md, WEB_RUNBOOK.md (수정), WEB_INSTALL.md·WEB_LEGAL_NOTICE.md (변경 없음 확인), docs/harness/doc-reconcile-web.md 7절
- 제약: docs 만 수정. 소스·설정·시험·git 무변경. 새 명령 실행 없음(코드 정독·grep).

## 1회차 — 문서 ↔ 코드 대조
- 방법: 7e594ae·96a970d·74a7241 변경분(ko.ts, useServerMode.ts, Settings/Home/History/BatchDetail 페이지, changes.py, batches.py, limits.py)을 읽고 해당 문서 문장을 grep 으로 찾아 대조.
- 결함 발견: 4건 — ① USER_MANUAL 홈 ①줄 제한 문장 잔존 ② 설정 "실행 모드" 제한 문장 잔존 ③ 9-5 `live` 표기 잔존 ④ RUNBOOK 15장 두 곳 `live` 표기 잔존. 전부 수정 후 재grep 으로 잔존 0 확인.
- 근거 불일치 1건 기록(수정 보류): limits.py 의 하루 한도 문구는 아직 "태평양 시간 기준"이고 주석도 태평양 날짜라 1차의 "한국 시간 하루" 서술과 어긋나 보임 → 단정하지 않고 확인 필요로 남김.
- 민감정보: 시크릿 값·토큰·키 문자열 추가 없음(`web\.env` 키 이름과 안내만). 판정: 결함 수정 후 통과.

## 2회차 — 독자 관점 재검토
- 사용자(선생님): 롤백 거부 문장이 쉬운 말("반영한 뒤 유튜브에서 영상이 바뀌어 자동으로 되돌리지 않았습니다"+Studio 에서 직접 확인)이고 다음 행동이 있음. 실행 확인 문구가 모드별로 다름(`실행 N건`/`실제 실행 N건`)이 명시됨.
- 신규 온콜: DB 재시작 후 항목이 "대기"로 돌아오는 것이 정상이며 수동 재생성이 필요 없고, 쓰기 시작 후 끊김은 기존 "예정" 규칙임을 구분해 적음. 8단계 수치는 "참고값·합격 기준 없음"으로 단정 표현을 피함.
- 자동 점검: 사용자용 5종 `grep -nE "DEC-|DEF-"` 0건. INSTALL 8장 순서 ↔ `.env.example`·`compose.online.yaml` 일치(수정 없음).
- 결함 0건. 판정: PASS(화면 캡처 확인·Windows PC 확인은 미수행으로 명시).
