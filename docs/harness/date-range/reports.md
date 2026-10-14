# 성과 리포트 조회 기간 추가 결과서 (2026-10-14)

시작 10:37:18Z, 종료 약 10:39Z (소요 약 2분, 상한 12분 이내).

## 변경 파일
- `web/backend/ytweb/routers/reports.py`: `/reports/changes`, `/reports/export.csv`에 `date_from`, `date_to` (date|None) 추가.
- `web/backend/ytweb/domain/reports.py`: `build_reports`, `export_csv`가 기간을 받음. `kst_range_utc`로 UTC [시작,끝) 변환 후, `coalesce(applied_at, created_at)`이 구간 안인 성공 apply 변경이 있는 영상만 대상. 영상별 전/후 계산은 기존대로 그 영상의 전체 변경·스냅샷 사용.
- `web/frontend/src/pages/ReportsPage.tsx`: `useDateRange()`(기본 오늘 KST) + `<DateRangeFilter basis="제목 변경 시각 기준">`. 조회·CSV에 `range.query` 전달, valid=false면 조회 안 함(enabled=false)+오류 박스+CSV 버튼 비활성, 기간 지정 후 0건이면 `ko.dateRange.none`(전체 기간·영상 ID 지정이면 기존 안내).
- 신규 시험: `web/backend/tests/domain/test_reports_date_range.py`, `web/frontend/src/pages/reports.daterange.test.tsx`.

## video_id 지정 시 기간을 무시하는 이유
사용자가 영상을 직접 지정한 조회는 "이 영상의 성과를 보겠다"는 명시 의도이고, 기간 때문에 비어 보이면 기존 동작(변경 없음/데이터 부족 안내)을 잃는다. 단 형식 검증(from>to 422)은 동일하게 적용.

## 시험 결과
| 구분 | 명령 대상 | 결과 |
|---|---|---|
| 백엔드 신규 | test_reports_date_range.py | 10 통과 / 0 실패 (안/밖, 한쪽만, KST 경계 14:59:59Z·15:00:00Z, created_at 대체, 실패·롤백 제외, 전체 변경 사용, video_id 무시, 422(서비스·HTTP·CSV), CSV 동일 필터, HTTP 쿼리, 미지정 기존 동작) |
| 백엔드 기존 | test_changes_reports.py, test_routers.py, test_wbx_fixes.py | 위 신규와 합쳐 83 통과 / 0 실패 (기대값 수정 없음) |
| 프런트 신규 | reports.daterange.test.tsx | 4 통과 / 0 실패 (기본 오늘, 0건 안내+전체 기간, from>to 미조회+오류+CSV 비활성, CSV 기간 전달) |
| 프런트 기존 | misc.test.tsx | 18 통과 / 1 실패 (아래) |
| eslint | ReportsPage.tsx, reports.daterange.test.tsx | 오류 0 |
| tsc --noEmit | 전체 | 오류 0 |

## 첫 실행 실패
- 백엔드: 첫 실행 실패 없음(전부 통과).
- 프런트 `misc.test.tsx` 1건 실패: `TC` 이력 화면 "아직 변경 이력이 없습니다"(HistoryPage). 화면에는 "선택한 기간에 해당하는 항목이 없습니다"가 나옴. 원인은 다른 작업자가 진행 중인 HistoryPage의 기간 기본값 변경이며 리포트 화면과 무관. 금지 파일이라 수정·기대값 변경 안 함. 이력 화면 작업 쪽에서 '전체 기간'으로 의도하거나 별도 처리 필요.
- 리포트 관련 기존 시험(TC-WF-064~066)은 기본값(오늘) 적용 후에도 통과(응답을 모의하므로 영향 없음).

## 미수행
- 전체 회귀, 실제 브라우저 화면 캡처, 실스택(docker) E2E, OpenAPI(`docs/yt/openapi.json`) 재생성(수정 금지 파일이라 date_from/date_to 문서 반영은 별도 필요).
- 추가 문구 요청 없음.
