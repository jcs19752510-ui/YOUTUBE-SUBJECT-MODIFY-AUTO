# 영상 목록 조회 기간 추가 결과서
시작 10:36:58 UTC, 종료 10:38:41 UTC (약 2분) (12분 상한 이내). 커밋·푸시 안 함.

## 변경 파일
- web/backend/ytweb/routers/videos.py: GET /api/v1/videos에 date_from, date_to 쿼리 추가
- web/backend/ytweb/domain/videos.py: list_videos에 기간 필터(기준 = 최근 변경 시각, KST 양 끝 포함, 기간 지정 시 최근 변경 없는 영상 제외, total·페이지는 필터 후 기준). dates.py의 kst_range_utc·in_range 사용
- web/frontend/src/pages/VideosPage.tsx: DateRangeFilter(basis "최근 변경 시각 기준") + useDateRange(기본 오늘), 쿼리 전달, 기간 변경 시 1쪽, valid=false면 조회 안 함(오류는 필터가 표시), 0건이면 ko.dateRange.none, 타입 오류 해결
- 신규 시험: web/backend/tests/domain/test_videos_date_range.py(8건), web/frontend/src/pages/videos.daterange.test.tsx(5건)
- 기존 시험 수정(기대값 불변, 기간을 [전체 기간]으로 두는 단계만 추가): videos.test.tsx(TC-WF-032), videos.emptylive.test.tsx(2건)

## 시험 결과
| 구분 | 대상 | 결과 |
|---|---|---|
| 백엔드 | test_videos_date_range.py | 8 통과 / 0 실패 (첫 실행 그대로) |
| 백엔드 | tests/domain/test_videos*.py + test_routers.py | 32 통과 / 0 실패 |
| 프런트 | videos*.test.tsx (3개 파일) | 14 통과 / 0 실패 (수정 후) |
| 정적 | eslint(VideosPage 및 videos 시험), tsc --noEmit | 오류 0 |

## 첫 실행 실패 (그대로 기록)
기간 UI 추가 직후 videos*.test.tsx 첫 실행: 9건 중 3건 실패, 6건 통과. 실패 3건 = TC-WF-032, emptylive 2건("아직 영상이 없습니다"/데모·내 채널 불러오기 안내를 찾지 못함). 원인: 기본 기간이 오늘이라 0건일 때 "영상 자체가 없음"이 아니라 "기간 내 없음" 안내가 나옴. 사용자 관점 근거: 기간이 걸린 상태의 0건은 영상이 없는 것이 아니므로 기간 안내([전체 기간] 유도)가 맞고, 최초 안내는 전체 기간에서만 나오는 것이 정확함. 기대값은 바꾸지 않고 시험이 [전체 기간]을 먼저 누르도록 의도적 설정만 추가, 재실행 14/14 통과.
참고: 최초 사용자는 처음에 기간 안내를 보고 [전체 기간]을 눌러야 "아직 영상이 없습니다" 안내를 본다(동작 변화).

## 미수행
- 전체 회귀(메인 담당), 다른 화면 영향 시험, 실제 브라우저 화면 캡처, 실스택(Docker) 확인, docs/yt/openapi.json 갱신(수정 금지 대상)
- 새 쿼리 파라미터가 openapi.json에 반영되지 않았음(메인이 재생성 필요)

## 필요한 문구
없음(기존 ko.dateRange.* 사용). 기간 안내와 "조건에 맞는 영상이 없습니다" 제목이 함께 나온다.
