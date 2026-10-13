# e 에이전트 보고: Gemini 실서버 재확인 + 요구사항 추적성 (2026-10-13 UTC)

시작 01:44:24, 보고서 작성 시점 약 01:52 (상한 12분 이내). 소스 편집·git 조작·docker 사용 없음. 키는 보지도 쓰지도 않음(더미 문자열 `dummy-not-a-key` 를 넘김, 프록시가 교체).

## 작업 1. Gemini 실서버 (프롬프트 수정 후 첫 실서버 확인)

명령: `.harness-tmp/be/bin/python -I web/tests_fullcheck/e/gemini_live_check.py` (01:44:56~01:50:10, 5분 14초). `GeminiSuggester("dummy-not-a-key")`, 모델 gemini-flash-latest(기본값), 합성 영상 8편(생활 4·건강 2·금융 2, 설명에 챕터 포함 5/미포함 3) x 2회 = 16회, 후보 수 3. 둘째 호출에는 앱과 같이 첫 호출의 제목을 `이미_만든_제목`으로 전달. 판정은 `ytweb.ai.guard.sanitize_drafts` 후 `youtube_title.validator.validate_file`(앱의 `validate_title` 과 같은 방식: 요약=설명).
요청·응답 원문: `.harness-tmp/results/e-gemini/` (요청 16 + 응답 16 + summary.json, 키 없음).

프록시 주입: 첫 호출부터 401/403 없음(HTTP 200 응답 8건). 즉 키 주입은 작동.

### 호출 결과 (16회)
| 결과 | 건수 | 비율 | 응답 시간(초) |
|---|---|---|---|
| 후보 3개 정상 수신 | 5 | 31% | 21.2~26.0 |
| HTTP 200 이나 형식 오류("Gemini 응답 형식이 올바르지 않습니다") | 3 (S02-1, S04-1, S08-1) | 19% | 21.7~23.3 |
| HTTP 503 (서버 오류, "high demand") | 4 | 25% | 0.7~4.8 |
| HTTP 502 (서버 오류) | 4 | 25% | 30.1~30.2 |
| HTTP 401/403/429, 네트워크 오류 | 0 | 0% | - |

형식 오류 3건의 원인(응답 원문으로 확인): `finishReason: MAX_TOKENS`. 생각 토큰이 3837~3839개로 출력 한도(`MAX_OUTPUT_TOKENS = 4000`, gemini.py 29행)를 거의 다 써서 JSON 이 중간에 잘림(후보 출력 146~149 토큰에서 끊김). 성공한 5건도 응답에 20초 이상 걸림(생각 토큰이 큼). 502 4건은 약 30.1초에서 끊김(프록시 또는 상위 서버 시간 제한 추정, 확인한 것은 아님).

### 후보 품질 (정상 수신 5호출, 후보 15개)
| 항목 | 결과 |
|---|---|
| 45~60자 | 15/15 (47~57자) |
| 검증 통과/경고/차단 | 통과 15 / 경고 0 / 차단 0 |
| 근거 문장이 설명에 실제로 있음(evidence_found) | 15/15 |
| 일치율 | 0.64~1.00 (최저 S03 의 0.636) |
| 건강(S02,S05)·금융(S03,S06) 후보 12개의 금칙어·과장 표현 | 0건(검증기 BANNED_* 0건, 경고 코드 전체 0건) |
| 둘째 호출 vs 첫 호출 중복 | **판정 불가**: 중복을 비교할 수 있는 영상(양쪽 호출 모두 성공)이 0편. 둘째 호출 후보 15개는 모두 서로 다른 제목(같은 호출 안 중복 없음) |
| 영상별 승인 가능 후보(차단 아님) 1개 이상 | 5/8편 (S02·S03·S05·S06·S07). 0개인 3편(S01·S04·S08)은 후보 자체를 받지 못한 것(호출 실패)이며 검증기 차단이 아님 |

### 합격선 제안(근거 있는 기준) 과 판정
- 기준 A "수신한 후보의 검증 통과율 90% 이상, 차단 0": 15/15 → 충족(표본 작음, 5호출).
- 기준 B "영상당 승인 가능 후보 1개 이상": 5/8 = 63% → 미충족(원인은 호출 실패).
- 기준 C "호출 성공률 90% 이상": 5/16 = 31% → 미충족. 실패 8건은 서버 502/503, 3건은 출력 한도 초과.
- 판정: 후보 품질은 수신분에 한해 양호, **호출 신뢰도는 불합격**. 재시도 없이 사용자가 버튼을 다시 눌러야 하는 비율이 69%(11/16).

### 결함 (고치지 않음, 보고만)
1. **GEM-1 (Medium)**: `MAX_OUTPUT_TOKENS = 4000` 이 생각 토큰 포함 한도로 부족해 19%(3/16) 응답이 잘려 "응답 형식 오류"가 된다. 사용자에게는 원인(길이 초과)이 아니라 일반 오류로 보인다. 조치 후보: 한도 상향 또는 생각 예산 제한(`thinkingConfig`) — 임의 변경하지 않음.
2. **GEM-2 (Medium)**: 어댑터에 재시도가 없다. 502/503 은 일시 오류로 보이는데(503 본문: "high demand, try again later") 한 번 실패하면 바로 오류. 50%(8/16)가 502/503.
3. **GEM-3 (Low)**: 성공 응답도 21~26초 걸린다(화면 대기 안내 필요 여부 확인 필요).
- 미확인: 502/503 이 구글 쪽인지 이 컨테이너 프록시 때문인지(선생님 PC 에서는 다를 수 있음). 이 재확인의 한계.

### 미수행과 사유
- 영상당 2회 모두 성공했을 때의 중복률: 위 사유로 산출 불가. 재호출(재시도)은 "총 16회 이하" 지시 때문에 하지 않음.
- 앱 전체 경로(`generate_for_video`, DB 저장) 통과 여부는 이 확인에서 안 봄(어댑터+검증기까지).

## 작업 2. 요구사항 추적성

파서: `web/tests_fullcheck/e/trace_parse.py` (출력 `trace_parse.json`). 대상: `docs/harness/traceability.md` 의 요구 행 중 유형 FR·NFR·POL·SEC·W·D·F(S-W 는 SEC 유형, W-M2/W-M3 임시 행 포함). EVT/UX/SCR(설계 항목)·ADR·RISK·OOS 는 요구가 아니라서 제외하고 따로 표시.
소스 대조: `tests/`, `web/backend/**`, `web/tests_*`, `web/frontend/src`·`verify*`.

### 숫자 판정
- **요구 148개 중 문서상 시험 연결 137개(92.6%)**, 시험 ID 가 실제 시험 소스 파일에서도 1개 이상 확인되는 것 103개(69.6%), 시험 ID 가 결과서(docs/harness/**/*.md)에만 있고 시험 소스에는 없는 것 34개(23.0%; 대부분 D-xx·POL-005~014·SEC-021~030, 결과서의 TC-VI·TC-WI 계열이며 파일명으로는 매핑 안 됨 = 추적 불가).
- 시험 연결이 없는 요구 11개: NFR-001, NFR-006(커버리지 지표), SEC-013, W-015, S-W10, S-W15, POL-007, POL-012, POL-015, POL-016, SEC-027. (설계 항목 EVT 8·UX 5 도 미연결.)
- 유형별(연결/전체, 소스 확인): FR 20/20(20), NFR 9/11(9), POL 12/16(6), SEC 44/48(32), W 22/23(20), D 16/16(5), F 14/14(11).
- 구현 상태가 Partial/Not Started 인 행과 "근거 미확인"(W-015)이 섞여 있어 연결률이 곧 충족률은 아님.

### 통과 확인 (실제 실행, 표본)
표본 범위: 이번 세션 기능 시험만(전체 시험은 실행하지 않음, 전체는 8단계에서 백엔드 1844·프런트 728 통과 기록).
- 백엔드 `pytest` 13개 파일(test_gemini_suggester, test_rule_suggester, test_google_oauth, test_live_write, domain/test_live_gateway·live_sync·live_suggest·live_off_block·live_guard·live_check·verify_report·source_edit, verify_ai_badge): **94 통과, 실패 0, 7초** (`.harness-tmp/results/e-junit.xml`). 추가 `domain/test_google_router.py`: 12 통과.
- 프런트 `vitest` 5개 파일(ai.aibadge, batchdetail.execgate, google, formids, lib/score): 23 + 7 = **30 통과, 실패 0**, 약 5초.
- 표본 시험 ID 이름 확인: TC-M3 19개 전부·TC-WF-200~212 7개 전부·TC-M2-001~017·040~053 (31개 ID 확인)·TC-M2-020~031 은 `test_google_router.py` 에 있음(12 통과).
- **통과 확인된 요구: 새 기능 행 W-M2-01·02·03·04, W-M3-01·02·03·04 의 8개** (W-M3-05 는 결함 고정 시험, 이번 미실행; S-W17 은 시험 직접 실행 안 함). 나머지 요구의 통과는 이번에 재실행하지 않았음(미수행, 8단계 기록에 의존).

### 이번 세션 기능의 traceability 누락
`web/tests_fullcheck/e/traceability-update.md` 에 표로 정리. 요지:
- 있음: 구글 읽기·쓰기(W-M2-01~04, W-M3-01·03·04), live 3조건(W-M3-02, Partial).
- **누락 10개 항목**: Gemini 제안(단어 0회), 규칙 기반 제안(요구 행 없음), 반영 후 검증(완화·달라진 항목), 직접 바꾼 제목 갱신, AI 제안 종류 표시, 실행 버튼 안내, 입력칸 id/name, 실제 모드 꺼짐 시 실제 영상 모의 성공 금지(DEF-LIVE-005), 준비 점검 live-check, 점검 점수 표시(총 10개 항목, 제안 임시 ID W-N01~11).
- 이 누락 기능의 시험은 모두 존재하고 표본 실행에서 통과함(시험은 있으나 요구 ID 와 연결 안 됨).
- 기존 행 이슈: W-M2/W-M3/S-W17 은 규칙 H 상 미승인 임시 ID.

### 결함 (보고만)
- **TRC-1 (Medium)**: 새 기능 10개 항목이 traceability 에 없음(위).
- **TRC-2 (Medium)**: 34개 요구(D-xx 등)가 가리키는 TC-VI/TC-WI ID 가 시험 소스에서 검색되지 않아, 결과서를 읽어야만 어떤 시험인지 알 수 있음.
- **TRC-3 (Low)**: 문서의 TC 범위 표기("TC-WB-008~013, 018")와 시험 이름이 일치하지 않는 경우가 있어 자동 대조 한계(위 69.6%는 하한에 가까움).
- 파서 한계: ID 범위 `~` 를 끝점까지만 확인, 시험 함수명 규칙이 다른 파일(`test_vb_*` 등)은 ID 와 연결되지 않음.

## 산출물
- `/home/user/youtube-subject-modify-auto/web/tests_fullcheck/e/gemini_live_check.py`, `trace_parse.py`, `trace_parse.json`, `traceability-update.md`
- `/home/user/youtube-subject-modify-auto/.harness-tmp/results/e-gemini/` , `e-junit.xml`, `e-pytest-sample.txt`
- 이 보고서
