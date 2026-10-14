# 이력·성과 리포트 영상 구분(롱폼/쇼츠) 조회 - 결과서 (2026-10-14, 소요 약 4분: 12:38:07 시작 ~ 12:41:30 UTC)

## 변경 파일
- 백엔드: `routers/changes.py`(kind 쿼리, 롤백 응답에도 video_kind), `domain/changes.py`(`list_changes_with_kind` 추가, `list_changes`는 같은 인자+kind 로 감싼 기존 시그니처 유지; total 도 Video 조인 후 집계), `domain/serialize.py`(`change_dict(..., video_kind=None)`), `routers/reports.py`(/changes·/export.csv 에 kind), `domain/reports.py`(kind 는 자동 대상 선정에만 적용, video_id 지정 시 무시, 각 항목에 video_kind; CSV 열 불변).
- 프런트: `pages/HistoryPage.tsx`, `pages/ReportsPage.tsx`.
- 시험: 신규 `tests/domain/test_changes_reports_kind.py`(6), `pages/history.kind.test.tsx`(3), `pages/reports.kind.test.tsx`(3). 기존 `tests/domain/test_routers.py` 220행 응답 필드 집합에 `video_kind` 추가(허용된 조정).

## 시험 결과 (재실행 기준)
| 구분 | 명령 범위 | 결과 |
|---|---|---|
| 백엔드 | test_changes_reports_kind + test_changes* + test_reports* + test_routers | 62 통과, 0 실패 |
| 프런트 | history*·reports*·misc (5파일) | 33 통과, 0 실패 |
| ESLint / tsc | 변경 4파일 / 전체 | 오류 0 |

## 첫 실행 실패 (그대로 기록)
1. 백엔드 첫 실행: `test_routers::test_tc_wb_132`(필드 집합에 video_kind 추가됨 -> 기대 집합에 필드 추가, 허용 범위). `test_routers::test_tc_wb_129`(배치 항목 응답에 video_kind 가 생김)는 다른 작업(배치) 변경 때문이며 내 파일 아님; 재실행 때는 통과.
2. 신규 백엔드 시험 6개 첫 실행 오류: 시험 입력 오류(is_short 에 None 대입 -> NOT NULL 위반; 길이 불명은 is_short=False+duration None 으로 표현). 이어서 `csrf` 픽스처 누락으로 401 -> 시험 입력 수정.
3. 프런트 첫 실행 3건 실패: 시험의 0건 안내 문구 추측 오류(ko.ts 실제 문구로 수정), 이력 "구분" 열 이름 중복(아래 결함), 리포트 '롱폼' 글자가 선택 옵션과 배지 2곳(기대값을 2로, 사유 주석).

## 발견한 결함/제안 (ko.ts 수정 금지라 미조치)
- 이력 표에 이미 `ko.history.colType = '구분'`(변경 종류: 적용/롤백)이 있어 `ko.kind.col`('구분')을 쓰면 같은 이름 열이 둘이 되어 사용자가 헷갈린다. 그래서 영상 구분 열 머리글은 `ko.kind.label`('영상 구분')을 썼다. 권장: `ko.history.colType` 을 '변경 종류'로 바꾼 뒤 이 머리글을 `ko.kind.col` 로 교체.
- 이력·리포트에는 별도 "초기화" 버튼이 없어 0건 안내에 구분을 포함하는 것으로 갈음했다(이력: 구분 선택 시 "조건에 맞는 영상이 없습니다", 리포트: kind 선택 시 기간 안내 대신 기본 0건 안내).

## 동작 메모
- 이력: kind 는 기간·영상 ID·결과와 AND, total 정확. 구분 바꾸면 1쪽.
- 리포트: video_id 지정 시 kind 무시. 길이 불명 영상은 롱폼/쇼츠 어느 쪽에도 안 들어가며 video_kind=None('-').
- CSV: 열 구성 불변(구분 열 없음), 거르기에만 적용.
- 리포트 구분 선택 상자는 데이터 로딩 영역 밖(기간 선택 위)에 두어 재조회 중에도 사라지지 않는다.

## 미수행
- 전체 회귀, 실제 브라우저 화면 캡처, `docs/yt/openapi.json`·API.md 재생성(수정 금지 대상), 변이 점검.
