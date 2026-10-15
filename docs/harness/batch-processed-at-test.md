# 배치 상세 "처리 일시" 열 추가 내부 시험 결과서 (2026-10-14)

요청: 배치 상세의 항목 상태(성공) 오른쪽에 처리 일시 열을 한국 시간 24시 형식으로 표시.
해석(확인 필요 시 알림): 요청의 형식 "yyyy-mm-dd mi:dd:mi:ss"는 오타로 보고 `yyyy-mm-dd hh:mi:ss`(예 2026-10-14 19:26:07)로 구현.
처리 일시 = 항목의 마지막 상태 변경 시각(`batch_items.updated_at`, 성공·실패·건너뜀·취소일 때만). 대기·진행 중은 "-". 서버 DB 변경 없음.
변경: `domain/schemas.py`(`BatchItemOut.processed_at`), `domain/serialize.py`, `docs/yt/openapi.json`(+12줄), 화면 `BatchDetailPage.tsx`·`types.ts`·`ko.ts`(열 "처리 일시").
기존 이력(#1~#5 등)도 같은 규칙으로 표시됨(updated_at 사용).

| 시험 | 결과 |
|---|---|
| 백엔드 test_batch_item_processed_at_only_for_finished_items(성공=값, 진행·대기=None, 실패·건너뜀·취소=값) | 통과 |
| 프런트 TC-FE-BD-PA-001(열 위치가 상태 바로 오른쪽, `2026-10-14 19:26:07`(UTC 10:26:07→KST), 대기는 "-") | 통과 |
| 백엔드 tests/domain + tests/verify_spec 전체 | 첫 실행 **1 실패**: test_routers.py::test_tc_wb_129(응답 항목 필드 집합을 정확히 비교 → 새 필드 `processed_at`이 늘어남). 의도한 API 계약 변경이므로 기대 집합에 `processed_at` 추가(원래 실패 기록 유지). 재실행 전부 통과 |
| openapi.json 최신 여부 시험 | 첫 실행 불합격(스키마 변경), 재생성 후 통과 |
| 프런트 전체 | 893 통과, 1 예상 실패, 21 건너뜀 / build·eslint 통과 |
미수행: 백엔드 전체 회귀 중 tests/domain·verify_spec 외 폴더(보안·인프라·통합), 브라우저 캡처, 선생님 PC 확인(최신 소스 받은 뒤 재시작 필요).
