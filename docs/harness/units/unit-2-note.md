# unit-2 구현 노트 — WU-2 YouTube 조회·쿼터 모듈 (5단계)

- 작업 단위: **WU-2** (feature F-A 인증·조회) / Tier: Standard / 선행: WU-0, WU-1(완료)
- 파일 범위: `src/ytitle/quota.py`, `src/ytitle/youtube_read.py`, `src/ytitle/commands/fetch.py`, `tests/test_quota.py`, `tests/test_read.py`, 이 노트 (범위 밖 수정 없음, 신규 의존성 없음)

## 1. 구현 범위
- `quota.py`: 쿼터 선예약(`reserve`)·결과 표시(`mark`)·오늘 사용량/남은 양/경고 판정. 하루 경계는 태평양 시간. 상한 초과 시 DB에 아무것도 남기지 않고 `QuotaError`(초기화 시각 안내 포함).
- `youtube_read.py`: 읽기 전용 조회. 업로드 재생목록 전 페이지 순회, `videos.list` 50개 배치 조회·정규화·upsert, Analytics 지표 수집(노출수·CTR 거부 시 기본 지표로 폴백), HttpError 변환(Quota/Auth/ApiError), 모든 호출은 선예약 + `retry.call_with_retry`.
- `commands/fetch.py`: `fetch --all | --video ID(반복) | --metrics`, `--phase`, `--days`. 읽기 토큰만 사용. `make_reader(ctx)`로 서비스 생성 분리. SCR-007 형식의 출력.

## 2. 설계서 대비 편차
| # | 편차 | 사유 |
|---|---|---|
| 1 | `YouTubeReader.__init__`에 키워드 전용 인자 `run_id=None` 추가 | `quota_usage.run_id` 기록에 필요. 지정된 위치 인자 순서(`youtube, analytics, quota, conn, settings, clock, sleep`)는 그대로. |
| 2 | **재시도할 때마다 쿼터를 다시 예약**한다(실패한 시도도 차감 유지) | 재시도는 실제 추가 호출이므로 보수적(ADR-008). 503 후 성공이면 2 units 차감. |
| 3 | 예약은 `INSERT ... SELECT ... WHERE (합계 + units <= 상한)` 한 문장으로 확인과 기록을 원자적으로 처리 | 확인과 기록 사이의 틈 제거. 동작은 설계(상한 초과 시 거부, DB 불변)와 동일. |
| 4 | 사용량 합산에 `reserved`·`ok`·`failed` 모두 포함 | 보수적. 결과 표시 전에 프로세스가 죽은 예약도 차감으로 본다. |
| 5 | `read_cost`/`analytics_cost`가 0으로 설정되면 `reserve`가 `InputError`로 거부 | 지시(units 0 이하 거부)를 그대로 적용. 설정 검증은 0을 허용하므로 0으로 두면 fetch가 막힌다 → 질문 7절 참고. |
| 6 | Analytics 영상 ID 필터를 **50개씩 나눠** 호출 | API가 허용하는 한 번의 영상 수 상한은 원문 미확인 [확인 필요]. 보수적으로 영상 조회와 같은 50. 호출 수는 늘 수 있다(호출당 `analytics_cost`). |
| 7 | 지표 기간의 종료일 = 태평양 시간 기준 **어제**, 시작일 = 종료일 − (N−1)일 | 당일분 Analytics 자료 지연과 미래 날짜 거부 가능성을 피하는 보수적 선택 [확인 필요: 실제 자료 지연]. |
| 8 | `fetch --metrics` 단독은 DB에 저장된 영상을 대상으로 함(영상 API 호출 없음), 저장된 영상이 없으면 `InputError` | 설계에 `--metrics`의 대상이 명시되지 않음. 쿼터를 아끼는 쪽 선택. `--all`/`--video`와 함께 쓰면 방금 조회된 영상이 대상. |
| 9 | `--phase`·`--days`는 `--metrics` 없이 줘도 오류 없이 무시 | 단순화. |
| 10 | 403 중 쿼터 사유가 아닌 것은 모두 `AuthError`(지시 그대로). `rateLimitExceeded` 같은 일시적 속도 제한 403도 여기에 해당 | 지시 준수. 일시적 제한이 재로그인 안내로 보일 수 있음 → 질문 7절 참고. |
| 11 | 영상 조회 응답에서 **요청하지 않은 ID·중복·빈 제목**은 건너뜀(건너뛴 개수에 포함). 요청했으나 응답에 없는 ID는 `missing`으로 따로 셈 | 계약 검증을 보수적으로 확대. |
| 12 | 변환된 오류는 `raise ... from None`으로 원본 `HttpError`를 연결하지 않음 | 원본 예외 문자열에 요청 URI 등이 있어 로그/트레이스백에 새는 것을 막음(SEC-008). 디버깅 정보는 `cause`의 `HTTP 상태 + reason 코드`로 제한. |
| 13 | 재생목록 순회 중 같은 `pageToken`이 반복되면 `ApiError`로 중단 | 무한 순회 방지(쿼터 보호). |

## 3. 인수 조건 (AC)
| AC | 인수 조건 | 연결 요구 |
|---|---|---|
| AC-01 | 쿼터를 호출 **전에** 예약하고, 오늘(태평양 날짜) 사용량 + 요청이 상한을 넘으면 `QuotaError`(초기화 시각 안내)이며 DB는 변하지 않는다. 상한 직전까지는 허용된다 | FR-015, SEC-002, NFR-003 |
| AC-02 | 호출이 실패해도(오류·중단 모두) 차감은 유지되고, 결과가 `ok`/`failed`로 기록된다 | ADR-008, FR-015 |
| AC-03 | 날짜 경계는 태평양 시간(서머타임 전후 포함)이며 사용량은 날짜별로 분리된다 | NFR-003, FR-015 |
| AC-04 | 사용량이 상한의 `warn_ratio`(기본 80%) 이상이면 경고를 알린다 | NFR-003 |
| AC-05 | 잘못된 units/호출 이름은 거부하며, 호출 이름 등 외부 문자열은 SQL에 값으로만 들어간다 | SEC-002, SEC-018 |
| AC-06 | 채널 업로드 목록을 전 페이지 순회하고 호출마다 쿼터를 예약한다. 응답 계약 위반·페이지 토큰 반복은 `ApiError` | FR-006, SEC-002 |
| AC-07 | 영상 조회는 한 번에 최대 50개 배치이며(120개 → 50/50/20), 중복 ID는 한 번만, 형식이 틀린 ID는 호출 전에 거부한다 | FR-006, SEC-002 |
| AC-08 | 응답을 `videos` 행으로 정규화해 upsert한다(한글, 길이 파싱, 설명 500자, snippet 전체 JSON). 계약 위반은 `ApiError`, 일부 결측 항목은 건너뛰고 개수를 알린다 | FR-006, SEC-018 |
| AC-09 | 지표를 `metrics_snapshots`에 저장하고(단계·기간·출처 api), 노출수·CTR 지표가 400으로 거부되면 기본 지표로 폴백하며 `impressions_available=False`로 CSV 안내가 가능하다 | FR-007 |
| AC-10 | HttpError 변환: quotaExceeded→`QuotaError`(재시도 0), 401/그 외 403→`AuthError`(재시도 0), 5xx/429/연결 오류→재시도 가능 `ApiError`(최대 2회 재시도), 그 밖의 4xx→재시도 안 하는 `ApiError` | SEC-003, NFR-004 |
| AC-11 | 오류 메시지·원인·문자열 표현에 응답 본문, 요청 주소의 키, 토큰이 없다 | SEC-008, NFR-007 |
| AC-12 | 조회 모듈에는 쓰기 API 호출 코드가 없고 쓰기 토큰도 부르지 않는다(소스 검사 + 쓰기 메서드가 없는 가짜 서비스) | SEC-001, SEC-007, SEC-015 |
| AC-13 | `fetch` 옵션 검증: 옵션 없음→종료 코드 1, 잘못된 영상 ID→1(로그인/API 준비 전), `--all`+`--video`→2, 잘못된 `--days`/`--phase`→2 | EVT-002, FR-006 |
| AC-14 | `fetch` 출력(SCR-007): 모의 실행 제목 줄, 영상 수, 공개/비공개/일부 공개/아동용 개수, 쿼터 사용량, 지표 결과, 건너뛴 항목, 면책 문구. 외부 문자열의 제어 문자는 제거되고 `--plain`을 지원한다 | SCR-007, FR-006, SEC-019, POL-002 |
| AC-15 | `fetch`는 읽기 토큰만 로드하고, 로그인이 없으면 `auth --read`를 안내한다. 쿼터 소진 시 종료 코드 1과 초기화 안내, 80% 이상이면 경고 | FR-016, SEC-015, SEC-002, NFR-003 |

## 4. 수동 확인이 필요한 부분
- **실제 구글 서버를 호출하지 않았다.** 모든 테스트는 가짜 서비스 객체와 `FixedClock`·임시 DB를 사용했다. 실제 응답 모양(특히 `playlistItems`, `videos.list`, `reports.query`의 열 머리글)과 실제 `build()` 동작은 미검증.
- **Analytics 지표 이름은 원문 미확인 [확인 필요]**: 기본 `views, estimatedMinutesWatched, videoThumbnailImpressions, videoThumbnailImpressionsClickRate`. 거부(400)되면 기본 두 지표로 폴백하는 경로는 가짜 응답으로만 확인. CTR 값이 비율인지 퍼센트인지도 미확인(받은 값을 그대로 저장).
- Analytics `filters=video==...`의 최대 영상 수, `reports.query`의 실제 단위 비용, 자료 지연 일수 미확인.
- 403 `reason` 문자열(`quotaExceeded`, `dailyLimitExceeded`)은 공식 문서 원문으로 확인하지 못했다(알려진 값을 상수로 둠).
- 실제 한국 시간 환산(서머타임 중 오후 4시/아니면 5시)은 안내 문구이며, 실제 초기화 시각 확인은 사용자 몫.

## 5. 게이트 1 — 정적 분석
- `py_compile` 및 `pyflakes src tests`: 경고 0건(출력 없음).
- 프로젝트 린터 설정은 없음(WU-0 노트 7절과 동일).

## 6. 게이트 2 — 자체 코드 리뷰
- [x] 설계서 일치(편차는 2절)
- [x] 에러 처리: 외부 예외를 `QuotaError`/`AuthError`/`ApiError`로 변환하고 본문·토큰·URI는 버림(`from None`). 예상 밖 예외는 그대로 전달하되 쿼터는 `failed`로 표시. `KeyboardInterrupt`도 예약을 `failed`로 남김. DB 오류는 `DatabaseError`로 변환
- [x] 입력 검증: 영상 ID 정규식(CLI와 리더 이중), 단계·기간·units 검증, 응답 계약 검증(items/columnHeaders/rows 타입)
- [x] 쓰기 경로 없음: `.update(`/`.insert(`/`.delete(` 부재를 소스 검사 테스트(TC-262)로 고정, 쓰기 토큰 로드 없음
- [x] SQL 전부 파라미터 바인딩(동적 SQL 문자열 결합 없음)
- [x] 하드코딩 비밀 없음(테스트의 가짜 토큰은 더미)
- [x] 신규 의존성 없음(`httplib2`는 google-api-python-client의 기존 의존성이며 예외 처리용으로만 import)
- [x] 범위 밖 변경 없음
- 자체 변이 점검(수동 시험): 상한 비교 `<=`→`<`, 합계 조건 무력화, 날짜 계산을 UTC로, 예약 제거, quotaExceeded 변환 제거, 429 재시도 제거, 폴백 조건 변경, 실패 표시 제거, 배치 크기 50→51 — 각각 테스트가 실패함을 확인.

## 7. 오케스트레이터에게
**공유 문서 갱신 요청**
- `traceability.md`: FR-006, FR-007(API 경로), FR-015, SEC-002, NFR-003의 구현·테스트 칸에 위 AC/TC(TC-200~213, TC-220~290) 연결. TC-200번대 사용 범위: TC-200~213(quota), TC-220~290(read/CLI, 일부 번호 비어 있음).
- `decisions.md`: 편차 2(재시도마다 선예약), 6(분석 50개 분할), 7(지표 기간 종료일=어제), 8(`--metrics` 단독 대상)을 필요 시 DEC로 기록.
- STATE.md: WU-2 구현 완료.

**질문**
1. `read_cost`/`analytics_cost`를 0으로 두는 설정을 허용할지: 현재 0이면 fetch가 `InputError`로 막힌다(config의 하한은 0). 하한을 1로 올릴지 WU-0 결정 필요.
2. 403 `rateLimitExceeded`/`userRateLimitExceeded`(일시적 속도 제한)를 재시도 가능 오류로 볼지: 지시대로 `AuthError`로 처리했으나 재로그인 안내가 부적절할 수 있다.
3. Analytics 지표 이름·CTR 단위·영상 필터 최대 개수·단위 비용의 원문 확인(1단계 [확인 필요])이 끝나면 `METRICS_FULL`/`METRICS_BASIC`/`BATCH_SIZE` 상수 조정.
4. WU-6의 `report --import-csv`는 아직 없다. `fetch`의 폴백 안내 문구가 이 명령 이름을 전제로 한다.
