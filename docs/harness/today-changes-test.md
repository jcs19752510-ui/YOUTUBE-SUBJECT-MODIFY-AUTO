# 오늘 변경(2026-10-12~13) 독립 검증 결과서

## 1. 개요
- 유형: 독립 검증(구현자와 별개). 판정: **조건부 PASS** (결함 0건 열림, 단 아래 "미수행"·"시험 환경 이동 표적" 참조).
- 검증 시각: 2026-10-13 09:34~09:46 UTC (실측 약 11분 이내, 시간 상한 12분 준수).
- 소스(web/frontend/src, web/backend/ytweb)는 수정하지 않음. 검증 중 구현자가 동시에 소스를 고쳐 커밋(d1e96da 등)했으므로 "첫 실행"과 "재실행"의 대상 트리가 다르다.

## 2. 범위(추적)
| 번호 | 변경 | 시험 |
|---|---|---|
| ① | 쇼츠 포함 스위치 YTWEB_INCLUDE_SHORTS | tests/verify_shorts(신규 16개 중 14+), tests/domain/test_include_shorts.py |
| ② | 배치 승인 칸 승인 시각+만료 분리 | verify_today TC-TD-001 |
| ③ | '제안 있음(검토 대기)'·제외 안내문 | TC-TD-002~005, grep |
| ④ | 일괄 승인 검색·진행 상태·판정·정렬·페이지·숨긴 선택 | verify_bulk_unify(22), verify_bulk_filter, bulkapprove/bulkfilter.test |
| ⑤ | 승인 유효시간 24시간 | TC-TD-006 |
| ⑥ | live-check 쇼츠 상태 | TC-VS-06 |
| ⑦ | approve-batch 연동 | tests/domain/test_bulk_approve.py(백엔드 일괄 실행에 포함) |

## 3. 환경
백엔드 .harness-tmp/venv_fix_be(SQLite, PostgreSQL 전용 39건은 건너뜀), 프런트 vitest 5.0.3/jsdom. 변이는 .harness-tmp/mut_today/ 사본에서만.

## 4. 케이스 결과
| 항목 | 첫 실행(그대로) | 재실행(현재 트리) |
|---|---|---|
| 백엔드 tests/domain+verify_wb | 639 통과, 39 건너뜀, 실패 0 | 642 통과, 39 건너뜀, 실패 0 |
| 쇼츠 스위치 신규(verify_shorts)+test_include_shorts | 신규 14개 통과(1차 작성 시 fixture 누락 오류 13건은 시험 코드 오류로 수정) | 16 통과 |
| tsc --noEmit | 통과 | 통과 |
| eslint src | 통과 | 통과 |
| vitest 전체 | **불합격 1건**: TC-BU-006(Found multiple elements, 그때 진행 중이던 WIP 소스 기준) 881 통과/1 실패 | 888 통과, 1 expected fail, 21 skipped, 실패 0 |
| npm run build | 통과(BUILD=0) | 미수행(재실행 생략, 시간 상한) |
| verify_today 신규 6개 | 1건 불합격(TC-TD-001: 승인자 이름 '홍'이 칸에 함께 표시되는 것을 기대값에서 빠뜨림 - 시험 코드 오류) | 6 통과 |
| 스위치 값 매트릭스 | '1'만 켜짐; '0','','true','TRUE','yes','1 ',' 1','11' 꺼짐 확인 | 통과 |
| 비공개/어린이용/길이불명/예약라이브 유지, 180·181초 경계, is_short 유지, live_sync 재계산(켜기->해제, 끄기->재제외) | 통과 | 통과 |
| 상태 문구 일관성 | ko.workflow.suggested == ko.home.counts.suggested == '제안 있음(검토 대기)'; tsx에 하드코딩 '제안 있음' 없음(grep) | 통과 |
| 영상 목록·일괄 승인 진행 상태 선택지(이름·순서·값) | TC-BU-001 통과 | 통과 |

## 5. 커버리지
측정 안 함: 미수행(시간 상한). 대신 변이 점검으로 대체 확인.

## 6. 변이 점검(최소 10곳, 사본 전용)
총 19개: **killed 19 / survived 0** (최종). 상세: F01 정렬 방향, F02 진행 상태 필터 연결, F03 숨긴 선택 유지, F04 페이지 오프셋, F05 판정 필터, F06 승인 시각->만료, F07 만료 문구, F08 24->12시간, F09 제외 안내문 조건, F10 상태 문구, F11 제목 검색, F12 선택지 순서, F13 안내문 인자, B01~B06 스위치 분기·is_short 연동·live-check 표시.
- 첫 실행에서 **F04가 SURVIVED**로 기록됨. 원인은 구현자가 소스를 동시에 고치는 중이라 사본 기준이 바뀐 것으로 의심되며, 현재 트리 사본으로 재실행하니 22/22 실패(KILLED), 무변이 기준선은 22/22 통과. 따라서 시험 공백이 아니라고 판단하나 첫 결과를 숨기지 않고 남긴다.
- 변이 판정 휴리스틱 한계: 'failed' 문자열 포함 여부로 판정(백엔드 B01~B06는 1~3초 만에 끝나 B04는 수동으로 test_vs_02 실패 확인).
- 실제 소스 변경 0줄 확인: `git diff --stat -- web/frontend/src web/backend/ytweb`는 구현자 본인의 진행 중 변경만 보였고 내가 만든 변경은 없음(내가 쓴 파일은 verify_shorts, verify_today, 본 결과서만).

## 7. Teardown(규칙 K)
.harness-tmp/mut_today, .harness-tmp/today_logs를 내가 만든 것으로 삭제. 프로세스 잔여 없음. git status 작업 종료 시점 출력 없음(깨끗, 구현자가 내 시험 파일까지 커밋함).

## 8. 결함
| ID | 내용 | 상태 |
|---|---|---|
| DEF-TD-001 | verify_bulk_unify TC-BU-006이 구현자 WIP 상태에서 queryByText 다중 일치로 실패(첫 실행). 현재 HEAD에서는 통과. 소스 결함이 아니라 중간 상태/시험의 질의 취약성 가능성 | 재현 안 됨(현재 통과), 시험이 `queryAllByText`를 쓰면 더 견고함 - 권고 |
| DEF-TD-002 | verify_today TC-TD-001 기대값 오류(내 시험 코드) | Fixed(시험 파일) |
소스 결함 0건.

## 9. 리스크·미수행
- 미수행(시간 상한): npm run build 재실행, PostgreSQL 전용 시험 39건, 커버리지 측정, 실제 브라우저 화면 캡처, 홈 영상 현황·상세 화면의 상태 문구는 ko.ts 문자열 동일성과 grep으로만 확인(렌더 확인 안 함), approve-batch 연동은 기존 백엔드 시험 의존.
- 소스가 검증 중 바뀌었으므로 최종 커밋 기준 재검증 1회 권장.

## 10. 내부 검증
- 1차: 범위 ①~⑦ 각각에 시험이 있음을 대조. ⑦은 기존 시험에만 의존해 약함으로 기록.
- 2차: "넘겨도 되는가" 의심 - 첫 실행 불합격 1건과 변이 생존 1건을 재현해 원인을 구분했다(환경 이동). 스위치 공백 값(' 1','1 ')을 시험해 엄격 비교임을 확인. 쇼츠 켜짐 시 길이 불명 영상이 계속 제외되는 것도 확인. 남은 의문: 큰 수의 영상(>200) 상태 필터 누락은 TC-BU-026이 현재 통과하나 구현 중 한때 실패했으므로 최종 커밋에서 재확인 필요.
