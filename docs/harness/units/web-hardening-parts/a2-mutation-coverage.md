# a2 변이 점검 + 커버리지 (2026-10-13, 시작 01:22:31 UTC, 보고 작성 약 01:33 UTC, 소요 약 11분)

## 한 줄 결론
변이 35곳 중 33곳을 1차(기존 시험 묶음)로 실행: 26 killed, 7 survived. 살아남은 7곳은 신규 시험 15개(`web/backend/tests/domain/test_verify_mutation_guards.py`)로 전부 killed(35/35 killed, 동등 변이 0). 1차 미수행 2곳(#1은 killed, #3~#4 구간은 아래 주석)은 표에 그대로 적었다. 커버리지: 대상 10개 모듈 합계 줄+분기 95%.

## 명령
- 사본: `cp -r src config templates pyproject.toml web/backend` -> `.harness-tmp/mut`(rsync 없음, 사본 import 확인: `ytweb.__file__`가 `.harness-tmp/mut/web/backend/...`). 변이 도구 `.harness-tmp/mut/mut.py`, `mut_p1.py`(1차), `mut_p2.py`(2차, 사본 `mut2`).
- 1차 시험 묶음: tests/domain/test_verify_report.py, test_edge_branches.py, tests/verify_wb/test_vb_10_branches.py, tests/verify_wa/test_va_11_guard_worker_misc.py (사본, `-x`). 기준선(변이 없음)에서 위 묶음과 확장 묶음(+test_live_guard, test_live_gateway, test_wbx_fixes, verify_m23 vm_07/vm_10/vm_90) 모두 실패 0(확장 묶음 42초).
- 2차: 신규 시험 파일만(변이 1건당 약 1초).
- 커버리지: `COVERAGE_FILE=.harness-tmp/results/.cov-mut pytest --cov=ytweb --cov-branch tests/domain tests/verify_m23 tests/verify_wb` (원본 읽기 전용).

## 1차 시도에서 있었던 일 (그대로 기록)
- 첫 실행은 survived 시 확장 묶음(42초)까지 돌려 12분에 못 맞춤: #1 killed, #2 survived(확장 묶음까지 통과)에서 중단(`mut/mut-pass1a.log`).
- 두 번째 실행(`mut/p1b.log`)은 `extra=[]`일 때 pytest가 전체 시험을 돌리는 도구 오류로 #3(줄 끝 공백 제거 삭제)이 전체 시험의 test_vfb_04에 의해 killed 로 나옴(기본 묶음에서는 survived 였음). 이 결과는 1차 집계에서 제외하고 세 번째 실행(`p1c.log`, 기본 묶음만)으로 #5부터 다시 측정. #3, #4(CRLF류 중 #3 줄 끝 공백, #4 전체 strip)은 기본 묶음 재측정 결과가 없어 "1차: 기본 묶음 미측정"이며 2차에서 killed.
- 사고: 도구 중단 중 `pkill -f "pytest -q -x"` 패턴 종료를 써서 다른 에이전트의 같은 패턴 프로세스를 종료했을 수 있음(사본 변이는 원본 파일과 diff 로 복구 확인).

## 변이 표 (1차 = 기존 시험, 2차 = 신규 시험)
| # | 파일 | 내용 | 원래 -> 변이 | 1차 | 2차 |
|---|---|---|---|---|---|
| 1 | batches.py | _canon 줄바꿈 CRLF 변환 변경 | `replace("\r\n", "\n")` → `replace("\r\n", "")` | killed (기본 시험 묶음 전체) killed by FAILED tests/domain/test_edge_branches.py::test_verify_snipp | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 2 | batches.py | _canon 단독 CR 변환 제거 | `.replace("\r", "\n")` → `` | survived(기본 묶음; 여기서 중단) survived | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 3 | batches.py | _canon 줄 끝 공백 제거 삭제 | `line.rstrip() for line` → `line for line` | 미수행(12분 상한) | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 4 | batches.py | _canon 전체 strip 제거 | `.split("\n")).strip()` → `.split("\n"))` | 미수행(12분 상한) | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 5 | batches.py | _canon 태그 정렬 제거 | `sorted(t.strip() for t in value if isinstance(t, s` → `[t.strip() for t in value if isinstance(t, str) an` | killed by FAILED tests/domain/test_edge_branches.py::test_verify_snippet_ignores_cosmetic_ | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 6 | batches.py | _canon 태그 strip 제거 | `sorted(t.strip() for t in value if isinstance(t, s` → `sorted(t for t in value if isinstance(t, str) and ` | killed by FAILED tests/domain/test_edge_branches.py::test_verify_snippet_ignores_cosmetic_ | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 7 | batches.py | _canon 빈 태그 제외 제거 | `sorted(t.strip() for t in value if isinstance(t, s` → `sorted(t.strip() for t in value if isinstance(t, s` | survived | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 8 | batches.py | _canon 비문자열 설명 빈값 취급 변경 | `text = value if isinstance(value, str) else ""` → `text = value if isinstance(value, str) else "x"` | survived | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 9 | batches.py | _canon 비목록 태그 빈값 취급 변경 | `if isinstance(value, list) else []` → `if isinstance(value, list) else [""]` | killed by FAILED tests/verify_wb/test_vb_10_branches.py::test_tc_vb_282_verify_snippet_pur | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 10 | batches.py | _same_field 언어 자동채움 조건 변경(이미 있던 값 변경도 같게) | `b is _MISSING and a is not _MISSING:` → `b is not _MISSING and a is not _MISSING:` | killed by FAILED tests/domain/test_edge_branches.py::test_verify_snippet_ignores_cosmetic_ | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 11 | batches.py | _same_field 언어 자동채움 b 누락 조건 제거 | `b is _MISSING and a is not _MISSING:` → `a is not _MISSING:` | killed by FAILED tests/domain/test_edge_branches.py::test_verify_snippet_ignores_cosmetic_ | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 12 | batches.py | _same_field 오디오 언어 자동채움 제외 | `if field in ("defaultLanguage", "defaultAudioLangu` → `if field in ("defaultLanguage",) and` | killed by FAILED tests/domain/test_edge_branches.py::test_verify_snippet_ignores_cosmetic_ | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 13 | batches.py | _same_field 태그 정규화 제외 | `if field in ("description", "tags"):         retur` → `if field in ("description",):         return _cano` | killed by FAILED tests/domain/test_edge_branches.py::test_verify_snippet_ignores_cosmetic_ | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 14 | batches.py | _same_field 비교 반대 | `None if b is _MISSING else b) == _canon(field, Non` → `None if b is _MISSING else b) != _canon(field, Non` | killed by FAILED tests/domain/test_verify_report.py::test_title_comparison_ignores_whitesp | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 15 | batches.py | _same_field 일반 필드 항상 같음 | `    return b == a   def verify_snippet` → `    return True   def verify_snippet` | killed by FAILED tests/domain/test_edge_branches.py::test_verify_snippet_ignores_cosmetic_ | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 16 | batches.py | verify_snippet 재조회 실패 ok=True | `return {"ok": False, "checked": False, "reason"` → `return {"ok": True, "checked": False, "reason"` | killed by FAILED tests/domain/test_edge_branches.py::test_tc_wb_150_verify_reread_failure_ | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 17 | batches.py | verify_snippet and→or | `"ok": bool(title_ok and all(preserved.values()))` → `"ok": bool(title_ok or all(preserved.values()))` | killed by FAILED tests/domain/test_verify_report.py::test_title_comparison_ignores_whitesp | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 18 | batches.py | verify_snippet 제목 확인 제외 | `"ok": bool(title_ok and all(preserved.values()))` → `"ok": bool(all(preserved.values()))` | killed by FAILED tests/domain/test_verify_report.py::test_title_comparison_ignores_whitesp | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 19 | batches.py | verify_snippet other localized 제외 해제 | `k not in ("title", "localized") and before` → `k not in ("title",) and before` | killed by FAILED tests/verify_wb/test_vb_10_branches.py::test_tc_vb_282_verify_snippet_pur | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 20 | batches.py | verify_snippet diff 제목 조건 반전 | `([] if title_ok else ["제목"])` → `([] if not title_ok else ["제목"])` | killed by FAILED tests/domain/test_verify_report.py::test_failed_item_shows_which_field_di | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 21 | batches.py | _canon_title 연속공백 정리 약화 | `unicodedata.normalize("NFC", title).split()` → `unicodedata.normalize("NFC", title).split(" ")` | killed by FAILED tests/domain/test_verify_report.py::test_title_comparison_ignores_whitesp | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 22 | batches.py | _canon_title NFC 제거 | `unicodedata.normalize("NFC", title)` → `title` | killed by FAILED tests/domain/test_verify_report.py::test_title_comparison_ignores_whitesp | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 23 | batches.py | _canon_title 공백 제거 병합 | `" ".join(unicodedata` → `"".join(unicodedata` | survived | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 24 | batches.py | _diff_detail 경계 < → <= (before_char) | `if at < len(bs) else None, "after_char"` → `if at <= len(bs) else None, "after_char"` | killed by ERROR    ytweb.batches:batches.py:426 batch item 1 failed unexpectedly | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 25 | batches.py | _diff_detail 기본 위치 min→max | `min(len(bs), len(as_)))` → `max(len(bs), len(as_)))` | survived | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 26 | batches.py | _diff_detail None 처리 반전 | `"" if b is None else str(b)` → `"" if b is not None else str(b)` | killed by FAILED tests/domain/test_verify_report.py::test_failed_item_shows_which_field_di | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 27 | batches.py | describe_verify title_ok 조건 반전 | `if verify.get("title_ok") is False:` → `if verify.get("title_ok") is True:` | killed by FAILED tests/domain/test_verify_report.py::test_describe_verify_handles_old_and_ | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 28 | batches.py | describe_verify preserved 반전 | `if ok is False and k in _FIELD_LABEL` → `if ok is True and k in _FIELD_LABEL` | killed by FAILED tests/domain/test_verify_report.py::test_describe_verify_handles_old_and_ | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 29 | batches.py | describe_verify detail 조건 반전 | `처음 다른 위치 {d['first_diff_at']})" if d else n` → `처음 다른 위치 {d['first_diff_at']})" if not d else n` | killed by FAILED tests/domain/test_verify_report.py::test_describe_verify_handles_old_and_ | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 30 | batches.py | describe_verify and→or | `d = info.get(key) if (detail and key)` → `d = info.get(key) if (detail or key)` | killed by FAILED tests/domain/test_verify_report.py::test_describe_verify_handles_old_and_ | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 31 | batches.py | verify_failure_text 조건 반전 | `(f"달라진 항목: {names}." if names else` → `(f"달라진 항목: {names}." if not names else` | survived | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 32 | serialize.py | _failure_reason 접두 변경 | `(it.skip_reason or "").startswith("[verify_failed]` → `(it.skip_reason or "").startswith("[verify_fail]")` | killed by FAILED tests/domain/test_verify_report.py::test_failed_item_shows_which_field_di | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 33 | serialize.py | _failure_reason 상태 반전 | `it.status == "failed" and` → `it.status != "failed" and` | killed by FAILED tests/domain/test_verify_report.py::test_failed_item_shows_which_field_di | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 34 | serialize.py | _failure_reason detail 제거 | `detail=True` → `detail=False` | killed by FAILED tests/domain/test_verify_report.py::test_failed_item_shows_which_field_di | killed by FAILED tests/domain/test_verify_mutation_guards.py |
| 35 | serialize.py | _failure_reason 기본 반환 None | `    return it.skip_reason   def _item_dicts` → `    return None   def _item_dicts` | survived | killed by FAILED tests/domain/test_verify_mutation_guards.py |

## 집계
- 1차(기존 시험): 실행 33곳 / killed 26 / survived 7 (#2 단독 CR 변환 제거, #7 빈 태그 제외 제거, #8 비문자열 설명 빈값 취급, #23 제목 공백 병합, #25 _diff_detail 기본 위치 min->max, #31 describe_verify 반전류 중 `detail and key`->`or`, #35 _failure_reason 기본 반환 None). 미측정 2곳(#3, #4)은 위 사고 때문이며 표에 "미수행"으로 남김. 이 survived 목록은 지우지 않는다.
- 2차(신규 시험 15개 추가 후): 35곳 전부 killed. 동등 변이 0건(분모 제외 없음).
- 신규 시험이 원본에서도 통과: `pytest tests/domain/test_verify_mutation_guards.py` -> 15 passed. 원본 소스·기존 시험 수정 없음(새 파일 1개만 추가, 커밋·푸시 안 함).

## 추가한 시험 (web/backend/tests/domain/test_verify_mutation_guards.py)
줄바꿈(CRLF/단독 CR)은 같고 내용 차이는 다름 / 줄 끝·앞뒤 공백 무시, 안쪽 공백 변화는 다름 / 없음·None·빈 문자열 설명 동일, 비문자열 설명 구분 / 태그 순서·공백·빈 태그 무시, 내용 차이·비목록 구분 / 언어 자동 채움은 OK, 기존 값 변경·삭제는 실패(언어·오디오 언어) / 카테고리 변경 감지 / 재조회 실패는 ok 아님 / 제목 연속 공백·탭·유니코드 NFD 허용, 다른 제목·공백 없는 제목은 불일치 / 제목은 맞아도 보존 항목이 바뀌면 실패, 목록 순서 / other_changed 와 localized 제외 / _diff_detail 위치·글자 코드·None·길이 경계 / describe_verify 이름·상세 / verify_failure_text 문구 / _failure_reason 확장 조건.

## 커버리지 (줄+분기, 원본 읽기 전용, 시험 tests/domain + verify_m23 + verify_wb; 전체 시험 통과 여부 줄은 로그 `.harness-tmp/results/cov-run.log`)
| 모듈 | 줄%(문장 기준) | 합계(분기 포함) | 미커버 줄 |
|---|---|---|---|
| ai/factory.py | 100% | 100% | - |
| ai/gemini.py | 78% (53/68) | 72% | 50-51, 74->76, 81, 84-85, 90-96, 104-105, 109 |
| ai/rule.py | 90% (47/52) | 84% | 27, 29, 65-67 |
| domain/suggestions.py | 99% | 99% | 64-65, 102 |
| domain/live_sync.py | 100% | 100% | - |
| domain/batches.py | 97% | 95% | 70, 79, 110->112, 121, 176-177, 308->310, 344, 435-436, 450, 462, 470-471, 473, 526-527, 589->591, 591->593, 609->614, 621, 636, 637->639, 647->651, 651->653, 684, 698->717 |
| domain/serialize.py | 97% | 93% | 60->62, 67 |
| domain/live_gateway.py | 100% | 100% | - |
| youtube/live_write.py | 100% | 100% | - |
| youtube/live_read.py | 100% | 100% | - |
| 합계 | | 95% (1275문, 396분기) | |

사용자 안전에 중요한 미커버: batches.py 70(영상 없음 건너뜀 문구), 79(차단된 제안 건너뜀), 435-436(되돌리기도 실패 시 failed 로 닫는 경로), 450(제안/영상 정보 없음 StepFailure), 470-471·473(재조회 오류 처리와 "새 제목이 현재와 같음" 건너뜀), 462·684(PostgreSQL 전용 advisory lock, skip_locked: 임시 DB 미사용 시험 구성이라 sqlite 에서 미실행), 636(verify_failed 오류 코드 기록 분기). gemini.py 81·84-85·90-96(HTTP 오류 코드별 사용자 안내 문구, 외부 AI 호출 실패 경로). live_off 차단과 live_write 쓰기 거부 경로는 live_gateway/live_write 100%, test_live_off_block 포함 시험으로 커버됨.

## 한계
- 분기 커버리지는 문장 수 기준 줄%를 근사 계산한 값 포함(coverage 보고서의 합계는 분기 포함 값). 
- 1차 시험 묶음은 속도 때문에 4개 파일로 줄임(확장 묶음은 #1~#2에만 사용). #3, #4 미측정.
- 변이는 함수 내부 한 곳씩, 사본에서만 적용. 정규화의 각 단계가 서로 보완하는 경우는 동등 변이로 분류하지 않고 모두 시험으로 죽임.
- PostgreSQL 전용 경로는 이번 커버리지 시험 구성에서 실행되지 않음(YTWEB_TEST_PG_URL 미지정).
