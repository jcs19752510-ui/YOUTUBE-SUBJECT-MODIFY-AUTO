# 배치 목록·이력 화면 조회 기간 추가 결과서 (2026-10-14 UTC, 시작 10:37 · 종료 10:39, 약 2분)

## 변경 파일
- 백엔드: `web/backend/ytweb/routers/batches.py`, `routers/changes.py`(쿼리 `date_from/date_to: date|None`), `domain/batches.py list_batches`(기준 `Batch.created_at`), `domain/changes.py list_changes`(기준 `coalesce(applied_at, created_at)`). 둘 다 `core/dates.kst_range_utc` 사용, 한국시간 날짜·양 끝 포함, total도 필터 후. 미지정이면 기존 동작.
- 프런트: `pages/BatchesPage.tsx`(기준 "만든 시각 기준"), `pages/HistoryPage.tsx`(기준 "처리 시각 기준"). `useDateRange()` 기본값 오늘, 바꾸면 1쪽, valid=false면 조회 안 함+오류, 0건이면 `ko.dateRange.none`(이력은 영상/결과 조건이 없고 기간만 걸린 경우). 영상 ID·결과 조건은 그대로 유지·함께 적용.
- BatchesPage의 초안 조회(`['batches','drafts']`, 전체 기간)는 기간과 무관하게 유지. 진행 중 배치 배너는 기간 밖 배치도 보이도록 초안 조회 결과에서도 찾는다.
- 신규 시험: `web/backend/tests/domain/test_batches_changes_date_range.py`, `web/frontend/src/pages/batches.daterange.test.tsx`, `history.daterange.test.tsx`.
- 기존 시험 수정 2건(아래 첫 실행 실패 참조): `misc.test.tsx`, `wfx.test.tsx`.

## batch_id 링크
배치 상세 화면의 이력 링크는 `/history`(batch_id 없음)뿐이고 HistoryPage는 batch_id 조건을 받지 않는다. 따라서 "batch_id 지정 시 전체 기간" 처리 대상이 현재 없다. 미수행(대상 없음). 나중에 batch_id 링크를 만들면 그때 전체 기간으로 시작해야 한다.

## 시험 결과
| 구분 | 명령 대상 | 결과 |
|---|---|---|
| 백엔드 신규 | test_batches_changes_date_range.py | 8 통과 / 0 실패 (기간 안·밖, KST 자정 00:00:00·23:59:59 경계, 한쪽만 지정, from>to 422 `date_range_invalid`, 미지정 기존 동작, total 필터 후, 처리시각 기준(applied 우선·없으면 created), 다른 조건 결합, HTTP 쿼리·잘못된 날짜 422) |
| 백엔드 관련 | test_batches.py, test_changes_reports.py, test_routers.py | 60 통과 / 0 실패 |
| 프런트 신규 | batches/history.daterange.test.tsx | 10 통과 / 0 실패 (기본값 오늘, 날짜 변경 시 쿼리·1쪽, 전체 기간, 잘못된 범위 시 미조회+오류, 0건 안내) |
| 프런트 관련 | batch*·misc·wfx·formids·a11y·daterange 10파일 | 93 통과 / 0 실패 (수정 후 재실행) |
| 정적 | tsc --noEmit, eslint(페이지 2개+수정 시험 2개) | 오류 0 |

## 첫 실행 결과 (실패 포함)
관련 프런트 시험 첫 실행: 84 중 82 통과, **2 실패**.
- `misc.test.tsx` TC-WF-063 "변경 이력이 없으면 다음 행동을 안내한다", `wfx.test.tsx` TC-WFX-010 "이력 화면 위에도 AI 생성 고지".
- 원인: 기간 기본값이 오늘이 되어, 이력이 0건이면 기존 문구("아직 변경 이력이 없습니다") 대신 기간 안내("선택한 기간에 해당하는 항목이 없습니다. [전체 기간]을 눌러 보세요.")가 나온다.
- 판단: 오늘만 보다가 0건일 때 "이력이 아예 없다"고 말하면 사용자가 오해하므로 새 동작이 맞다. 기대값 문구는 바꾸지 않았고, 두 시험이 의도한 "전체 기간에서 이력이 없음" 상황을 만들도록 시험 첫 단계에 [전체 기간] 클릭만 추가했다. 재실행 결과 위 표와 같이 통과.

## 미수행
실제 브라우저 화면 캡처, 전체 회귀(지시상 생략), PostgreSQL 외 DB, `docs/yt/openapi.json` 재생성(수정 금지 파일; 새 쿼리 `date_from/date_to`가 `GET /batches`, `GET /changes`에 추가됐으니 재생성 필요).
필요한 문구: 없음(기존 `ko.dateRange.*`로 충분). 배너/기준 문구("만든 시각 기준", "처리 시각 기준")는 페이지에 직접 쓴 상수이므로 원하면 ko.ts로 옮길 것.
