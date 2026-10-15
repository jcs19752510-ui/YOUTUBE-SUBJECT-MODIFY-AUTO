# 11단계 최종 대조 1차 — 사용자용 문서 5종 + API.md + WEB_DESIGN.md ↔ 실제 코드·화면 문구 (`doc-reconcile-web.md`)

> 8단계 전체 시험 **전** 선행 대조. 작성: 11단계 문서화·운영지원 담당 / 일시: 2026-10-11 / 저장소 브랜치 `PROD_SCH`(최신 커밋 95879ea 기준 작업 트리).
> 수정 범위: `docs/yt/` 문서 7개만. 소스·설정·시험·git 은 건드리지 않음. 새 명령 실행·Windows 실행·실제 구글 접속은 하지 않음(정적 읽기 + 파일 존재·문구 자동 대조만).

## 1. 한 줄 결론

- **수정 142건**(문서 7개) 완료, **이미 일치로 확인한 항목 36묶음**, **확인 필요 항목 아래 5절 참고**. 검증 로그 3회(결함 0건 회차 포함): `docs/harness/verify-logs/verify-log_doc-reconcile-web.md`.
- 가장 큰 불일치 4가지(사용자 영향 큼): ①차단된 제안 버튼·초안 버리기 버튼·면책/AI 고지·A/B 확인란이 이미 구현됐는데 문서는 "없음"으로 적혀 있었음 ②상단 모드 띠가 3가지로 바뀌는데 문서는 "고정 결함"으로 적혀 있었음 ③실제 수정 스위치(`web\.env`)가 있는데 문서는 "전달 방법 없음"으로 적혀 있었음 ④실제 모드 롤백 거부 3종(`live_changed_since_apply`·`live_mode_mismatch`·`live_not_allowed`)이 문서에 없었음.
- 쿼터 불일치(50 vs 52): **모순이 아니었음**. `videos.update` 1회 = 50단위(`config/settings.yaml` quota.update_cost), 반영 1건 = 50 + 조회 2×1 = **52단위**(`domain/limits_quota.py:95-97`). 문서마다 다른 것을 세고 있어서 "요청 1회 50 / 반영 1건 52"로 문구를 통일했다. 구글이 실제로 적용하는 값은 공식 원문을 열람하지 못해 **확인 필요**.

## 2. 문서별 수정 건수

| 문서 | 수정 건수 |
|---|---|
| WEB_USER_MANUAL.md | 33 |
| WEB_FAQ.md | 19 |
| WEB_INSTALL.md | 14 |
| WEB_RUNBOOK.md | 33 |
| WEB_LEGAL_NOTICE.md | 16 |
| API.md | 11 |
| WEB_DESIGN.md | 16 |
| **합계** | **142** |

※ 합계 중 134건은 검증 1회차(대조·수정), 8건(D12~D16, L16, R32, A11)은 2회차 재대조에서 추가 발견·수정한 것이다. 이와 별도로 2회차에서 고친 서식·표현 5곳(중첩 따옴표 4곳, 표현 1곳)은 수정 행에 포함하지 않고 검증 로그에 따로 적었다.

## 3. 대조표 — 수정한 항목

열: ID · 문서 · 절 · 항목 · 기존 표현(앞부분) · 실제 근거 파일:줄 · 조치

| ID | 문서 | 절 | 항목 | 기존 표현(앞부분) | 실제 근거 | 조치 |
|---|---|---|---|---|---|---|
| U01 | WEB_USER_MANUAL.md | 머리말 | 문서 상태 표시 | > 초안 — 2026-10-11 코드 대조 반영본. 7~10단계 결과와 선생님 PC 확인 후 다시 대조해야 합니다. | 요청 지시(8단계 전 선행 대조) | 수정 |
| U02 | WEB_USER_MANUAL.md | 머리말 박스 | 구글 연결 정정 문장 | 구글 연결 파일을 넣기 전까지는 위 내용 그대로입니다. 연결하면 달라지는 점은 9장을 보세요. | web/frontend/src/app/Layout.tsx:11-33 | 수정 |
| U03 | WEB_USER_MANUAL.md | 2장 8번 | 초안 버리기 버튼 유무(과거 표현) | 8. **사전 점검(초안)을 만들었다면 바로 실행하거나 끝까지 마무리하세요.** 지금 화면에는 초안을 버리는 버튼이 없고, 초안에 담긴 제안은 다른 배치에 쓸 수 없습니다(4-4 참고). | web/frontend/src/pages/DiscardDraft.tsx, BatchDetailPage.tsx:267, BatchesPage.tsx:269-271, ko.ts:523-534 | 수정 |
| U04 | WEB_USER_MANUAL.md | 3장 시작하기 4~5번 | 시작 직후 띠와 PIN/세션 안내 | 4. 화면 위쪽에 **"데모 모드 — 유튜브에 아무것도 전송되지 않습니다"** 띠(노란 계열)가 보이면 정상입니다. 5. PIN을 설정해 둔 경우에는 "PIN 을 입력해 주세요" 화면이 먼저 나옵니다. PIN을 입력하고 [확인]을 누릅니다. PIN이  | web/backend/ytweb/config.py:32 (session_idle_minutes=30), ko.ts:58-81, config.py:63-64 | 수정 |
| U05 | WEB_USER_MANUAL.md | 4장 첫머리 | 화면 구성(띠·바닥글) | 화면 왼쪽 메뉴는 항상 같은 자리에 있습니다: **홈 / 영상 목록 / 배치(일괄 반영) / 이력·롤백 / 성과 리포트 / 설정**. 화면 위쪽에는 "데모 모드" 띠, "서버 연결됨" 표시, [로그아웃] 버튼이 있습니다. | Layout.tsx:11-33,127-130; ko.ts:6-8,41-44 | 수정 |
| U06 | WEB_USER_MANUAL.md | 4-1 홈 | 쿼터 한도 설명 | 데모 한도는 하루 6,000단위입니다.) | config/settings.yaml: quota.daily_limit_units=6000 (데모 전용 값이 아님) | 수정 |
| U07 | WEB_USER_MANUAL.md | 4-1 홈 | 연결 상태 카드와 알려진 결함 문단 | - **연결 상태**: "구글 연결: 데모 모드(실제 유튜브와 연결되지 않음)", "구글 연결 안 됨", "실제 반영(라이브): 꺼짐".   - **주의(알려진 결함, 수정 예정)**: 구글을 연결해도 이 카드와 화면 맨 위 띠("데모 모드 — 유튜브 | HomePage.tsx:186-197; ko.ts:264-269; domain/dashboard.py:21-29,50-52 | 수정 |
| U08 | WEB_USER_MANUAL.md | 4-3 제안 카드 4번 | 상태 배지 목록 | - **상태 배지**: 검토 대기 / 승인됨 / 반려됨 / 반영 대기 / 반영 완료 / 승인 만료. 그리고 "AI 제안"(또는 직접 수정한 경우 "직접 수정"), "주제: 생활·건강·금융 등". | ko.ts:130-139,372,44-46,53; SuggestionCard.tsx:118,138-141; VideoDetailPage.tsx:114-117; suggestions.py:213-238 (edit 시 source 불변) | 수정 |
| U09 | WEB_USER_MANUAL.md | 4-3 제안 카드 4번 | 엄격 모드 배지 설명 | - **엄격 모드** 배지: 건강·금융 등 민감 주제라는 뜻입니다. 경고도 차단으로 처리됩니다. | ko.ts:47-48; SuggestionCard.tsx:133-137 | 수정 |
| U10 | WEB_USER_MANUAL.md | 4-3 5번(카드 버튼) | 버튼 표시 조건과 승인 창 | - **[제목 수정]**: 새 제목(1~100자)을 직접 씁니다. 저장하면 **검증을 다시 하고, 이미 받은 승인은 무효**가 됩니다. "검토 대기·승인 만료·승인됨" 카드에 보입니다.    - **[승인]**: "검토 대기·승인 만료" 카드에 보입니 | SuggestionCard.tsx:70-80,177-220; ko.ts:405-429 | 수정 |
| U11 | WEB_USER_MANUAL.md | 4-4 ① 항목 고르기 | 초안 버리기 버튼 유무(4번) | 4. **중요(알려진 제한):** 사전 점검을 만들면 담긴 제안들은 그 "초안"에 묶입니다. 지금 화면에는 **초안을 버리는 버튼이 없고**, 초안에 묶인 제안으로는 새 사전 점검을 만들 수 없습니다("다른 배치에 이미 담겨 있습니다"). 그러니 사전 | BatchesPage.tsx:48-65,168-176,269-271; DiscardDraft.tsx; ko.ts:523-534; labels.ts:15-18 | 수정 |
| U12 | WEB_USER_MANUAL.md | 4-4 ② 사전 점검 표 | 예상 사용량·경고·제외 항목 행 | \| 예상 사용량 \| 1건당 52단위 × 건수 \| | domain/limits_quota.py:95-97 (update_cost 50 + 2×read_cost 1); config/settings.yaml quota | 수정 |
| U13 | WEB_USER_MANUAL.md | 4-4 ② 사전 점검 표 | 경고 행 | \| 경고 \| 항상 "Studio에서 해당 영상의 제목 A/B 테스트가 진행 중이 아닌지 확인하세요." 가 들어 있습니다. 상한 도달, 쿼터 부족, 경고 판정 제안 포함 안내가 더 붙을 수 있습니다 \| \| 제외된 항목 \| "제안 번호: 이유" 형식으로  | domain/batches.py:186-214; BatchDetailPage.tsx:35-73,154-157 | 수정 |
| U14 | WEB_USER_MANUAL.md | 4-4 ③ 실행 | 실행 조건·거부 시 안내 | 1. "실행 확인" 카드의 "확인 문구 입력:" 옆에 보이는 문구를 **그대로 직접 입력**합니다. 형식은 `실행 N건` 입니다. 예) 3건이면 `실행 3건`. 띄어쓰기도 같아야 하고 앞뒤 공백도 틀린 것으로 봅니다. 2. "✓ 문구가 일치합니다."가 | BatchDetailPage.tsx:280-319; ko.ts:49-52,482-488; batches.py:265-279 | 수정 |
| U15 | WEB_USER_MANUAL.md | 4-4 ③ 실행 | 같은 요청 두 번 | 4. 같은 요청을 두 번 눌러도(또는 새로고침해도) 한 번만 처리됩니다. | 번호 정리(위 항목 추가에 따름) | 수정 |
| U16 | WEB_USER_MANUAL.md | 4-4 ④ 진행 | 배치 상태 이름 | 배치 상태는 한글로 나옵니다: 초안 / 실행 대기 / 실행 중 / 완료 / 중지됨 / 실패 (일시 중지 문구도 있으나 실제로 쓰이지는 않습니다). | ko.ts:149-158,529; labels.ts:15-18 | 수정 |
| U17 | WEB_USER_MANUAL.md | 4-5 이력 | 결과 칸·찾기 목록·모드 | 1. "이력·롤백"에는 시각, 영상, 구분(반영/롤백)과 모드("데모"), 이전→새 제목, 결과, 승인자, 조치가 나옵니다. 영상 ID나 결과로 찾을 수 있습니다. 2. 결과 칸 글자: **성공 / 실패 / 예정**. 실패 기록에는 "오류 코드 …"가 | HistoryPage.tsx:134-137,154-170,210-213; ko.ts:169-178,554-557 | 수정 |
| U18 | WEB_USER_MANUAL.md | 4-5 이력 | 롤백 6~9번 | 6. 되돌리기가 **안 되는** 경우: 그 뒤에 같은 영상이 또 바뀌었거나(롤백 자체도 "바뀜"입니다), 이미 원래 제목이거나, 처리 중인 변경이 있을 때. 이때는 "되돌릴 수 없음"으로 표시됩니다. 롤백한 뒤에는 그 롤백을 다시 롤백할 수 없습니다. | domain/changes.py:66-138 | 수정 |
| U19 | WEB_USER_MANUAL.md | 4-5 이력 | 롤백 9번(영어 rolled_back) | 9. 롤백한 제안은 영상 상세 카드의 상태 칸에 영어 `rolled_back` 으로 보입니다(문구 누락, 알려진 제한). | ko.ts:138 | 수정 |
| U20 | WEB_USER_MANUAL.md | 4-6 리포트 | 안내 상자 내용 | 데이터가 부족하면 결론을 내지 않으며, **데모의 성과 숫자는 가짜 데이터**라는 내용입니다. | ReportsPage.tsx:158-165; ko.ts:55-56 | 수정 |
| U21 | WEB_USER_MANUAL.md | 4-7 설정 | 안전 설정 읽기 전용 구역 | 아래의 **"이 화면에서는 켤 수 없는 설정"** (실제 반영 "꺼짐", 허용 영상 목록)은 안전을 위해 화면에서 바꿀 수 없고, 바꾸는 방법도 이 문서에서 안내하지 않습니다. | SettingsPage.tsx:124-154; routers/settings.py:64-78 (policy.enable_live) | 수정 |
| U22 | WEB_USER_MANUAL.md | 4-7 설정 | 세션·연결 / 감사 로그 | - **세션·연결**: 서버 연결, 구글 연결(데모 안내 문장), 실행 모드, [로그아웃]. 로그아웃하면 "로그아웃되었습니다" 화면에서 [다시 연결]을 누릅니다. - **감사 로그**: 누가 언제 무엇을 했는지의 읽기 전용 기록(시각·행위자·동작·대상 | SettingsPage.tsx:309-354,356-419; ko.ts:656-696; labels.ts:19-26 | 수정 |
| U23 | WEB_USER_MANUAL.md | 5장 흐름표 | 단계 4·6·8 | \| 4 \| 배치 만들기 (최대 50건) \| 배치 \| 아니요 \| \| 5 \| 사전 점검 확인 \| 배치 상세 \| 아니요 \| \| 6 \| `실행 N건` 입력 후 [실행] \| 배치 상세 \| **데모 데이터의 제목이 바뀜** \| | BatchDetailPage.tsx:280-319; live_gateway.py:confirm_text | 수정 |
| U24 | WEB_USER_MANUAL.md | 5장 숫자 규칙·알려진 제한 | 숫자 요약과 제한 목록 | 숫자 규칙: 한 배치 최대 50건 / 하루 반영 상한 기본 10건(1~20, 한국 시간 하루) / 1건당 52단위(데모 하루 한도 6,000단위, 태평양 시간 하루) / 승인 24시간·1회용 / 같은 영상 72시간 간격·영상당 최대 3회(롤백 포함)  | ko.ts / 각 페이지 소스(위 U03~U22 근거), SettingsPage.tsx:327-328, HomePage.tsx:189-195, BatchDetailPage.tsx:288, HistoryPage.tsx:212 | 수정 |
| U25 | WEB_USER_MANUAL.md | 8장 한계 | 7·9단계 반영 여부 | - 7단계(전체 통합 시험)·9단계(보안 점검) 결과는 아직 반영되지 않았습니다. | STATE.md 최신 줄: 통합 재시험 결과서 개정 2판 작성 전 | 수정 |
| U26 | WEB_USER_MANUAL.md | 9-1 | 구글 연결 파일 없음 안내문 | - 준비가 안 되면 홈의 "구글(유튜브) 연결" 카드에 "실제 유튜브에 연결하려면 web\secrets\google_client.json 을 저장한 뒤 .\web\scripts\start.ps1 을 다시 실행하세요."가 보이고 연결 버튼은 없습니다.  | routers/google.py:30-32; ko.ts:208-209 | 수정 |
| U27 | WEB_USER_MANUAL.md | 9-2 3번 | 연결 완료 안내 문장 | 3. 홈으로 돌아오면 카드에 "구글(유튜브)에 읽기 전용으로 연결돼 있습니다"가 보입니다. | routers/google.py:32; Layout.tsx:21-27 | 수정 |
| U28 | WEB_USER_MANUAL.md | 9-3 | 서버 설정을 켜는 방법(과거: 방법 없음) | - 서버 설정을 **선생님이 혼자 켤 수 있는 방법은 지금 없습니다**(어디에 넣는지 **확인 필요**, `WEB_INSTALL.md` 8-4). 화면의 안내 문구에 설정 이름이 나오면 개발 담당에게 요청해야 하는 항목이라는 뜻입니다. | web/.env.example; web/compose.online.yaml:10-12,22-24; ko.ts:213-224 | 수정 |
| U29 | WEB_USER_MANUAL.md | 9-4 | 상태별 뜻 표와 알려진 표시 문제 | \| "제목 수정 권한이 연결돼 있습니다." + "실제 수정은 아직 꺼져 있습니다(수정 허용 영상 N개)…" \| 권한은 있으나 서버 설정이 꺼져 있거나 허용 영상이 0개 \| 아니오 (가짜 방식으로만 동작) \| | ko.ts:215-224; GoogleCard.tsx:89-98 | 수정 |
| U30 | WEB_USER_MANUAL.md | 9-4 | 알려진 표시 문제 문단 | - 알려진 표시 문제: 읽기 로그인만 풀리고 쓰기 정보가 남은 드문 경우, 실제 수정이 가능한데도 경고가 보이지 않을 수 있고, "아직 꺼져 있음" 안내가 무엇이 부족한지 구분해 주지 않을 수 있습니다(수정 예정). 헷갈리면 **실제 수정이 켜져 있다 | GoogleCard.tsx:79-108 ((g.connected \|\| g.write_connected) 조건); ko.ts:215-224 | 수정 |
| U31 | WEB_USER_MANUAL.md | 9-5 | 쿼터 문장 | - **쿼터**: 제목 한 건을 바꾸는 요청 1회가 API 사용량 **50단위**입니다(코드 기준). 홈의 "남은 API 사용량"과 하루 반영 한도를 확인하세요. | config/settings.yaml quota.update_cost=50, read_cost=1; domain/limits_quota.py:95-97 | 수정 |
| U32 | WEB_USER_MANUAL.md | 9-5 | 실제 모드 변경점 추가(띠·모드 변경 거부) | - **이력의 구분**: 변경 기록에 실제(live)인지 데모인지 구분되어 저장됩니다. | domain/batches.py:383-384; domain/changes.py:72-76; Layout.tsx:14-20 | 수정 |
| U33 | WEB_USER_MANUAL.md | 9-7 | 롤백 한계 | - 이력·롤백 화면(4-5)에서 바뀐 영상을 선택해 이전 제목으로 되돌릴 수 있습니다. 롤백도 이력에 남습니다. 허용 목록에서 빠진 영상은 되돌릴 수 없고(`live_not_allowed`), 이때는 **유튜브 Studio 에서 직접** 고치거나 허용 | domain/changes.py:72-76,117-128; decisions.md DEC-049(실제 모드 롤백 보수적 기본) | 수정 |
| F01 | WEB_FAQ.md | 머리말 | 문서 상태 표시 | > 초안 — 2026-10-11 코드 대조 반영본. 7~10단계 결과와 선생님 PC 확인 후 다시 대조해야 합니다. | 요청 지시 | 수정 |
| F02 | WEB_FAQ.md | Q2 | [승인] 버튼이 눌리지 않을 때 | - 검증이 **차단(✕)** 이면서 상태 칸에 영어 `blocked` 가 보이는 카드는 [제목 수정]·[승인]·[반려] 버튼이 **아예 나타나지 않습니다**(화면의 알려진 한계, 아래 Q17). | SuggestionCard.tsx:70-80,177-220; ko.ts:130-139,420-425 | 수정 |
| F03 | WEB_FAQ.md | Q6 | [실행] 버튼이 안 눌릴 때 | **Q6. [실행] 버튼이 안 눌려요.** "실행 확인" 칸에 화면의 빨간 박스 문구(`실행 N건`)를 **글자 하나, 띄어쓰기 하나까지 똑같이** 입력해야 합니다. 앞뒤 공백도 틀린 것으로 봅니다. "문구가 일치합니다."가 뜨면 눌립니다. | BatchDetailPage.tsx:289-311; ko.ts:49-52; live_gateway.py confirm_text | 수정 |
| F04 | WEB_FAQ.md | Q13 | 영어 표시 안내 | **Q13. 화면에 `blocked`, `aborted`, `rolled_back` 같은 영어가 보여요.** 문구가 빠진 알려진 제한이며 동작에는 문제가 없습니다. 뜻: `blocked` = 검증에서 차단된 제안(Q17), `aborted` = 반영  | ko.ts:136-138,171-176; HistoryPage.tsx:212; labels.ts:19-26 | 수정 |
| F05 | WEB_FAQ.md | Q16 | 실제 채널·AI 질문 | **Q16. 실제 내 채널 영상을 불러오고 싶어요 / 진짜 AI로 제안받고 싶어요.** 아직 만들어지지 않았습니다. 구글 연결(읽기)과 AI·실제 반영은 이후 단계이며, 그 전에 선생님의 승인과 준비(구글 로그인용 설정, AI 서비스 선택 등)가 필요 | routers/google.py; ai/factory.py (모의 AI만); 사용자 지시의 '안 한 것' 목록 | 수정 |
| F06 | WEB_FAQ.md | Q17 | 차단된 제안 | **Q17. 차단(✕)된 제안에 버튼이 하나도 없어요.** 검증에서 "차단"이 나온 제안은 상태 칸에 영어 `blocked` 가 보이고 [제목 수정]·[승인]·[반려] 버튼이 나타나지 않습니다. 지금 화면의 알려진 한계입니다(고쳐야 하는 항목으로 개발 | SuggestionCard.tsx:177-220; ko.ts:420-425 | 수정 |
| F07 | WEB_FAQ.md | Q18 | 초안 배치에 이미 담김 | 이전에 사전 점검(초안)을 만들고 실행하지 않았거나 실행이 `precheck_stale` 로 거부됐을 때 생깁니다. 초안에 담긴 제안은 그 초안에 묶여 있어 새 배치에 쓸 수 없는데, 지금 화면에는 초안을 버리는 버튼이 없습니다(알려진 한계). 해결: | BatchesPage.tsx:48-65,168-176; DiscardDraft.tsx; ko.ts:523-534 | 수정 |
| F08 | WEB_FAQ.md | 2장 접속 문제 | 세션 만료 행 | \| "세션이 만료되었습니다" \| 12시간이 지났거나 다른 곳에서 PIN을 바꿨습니다. | config.py:32 session_idle_minutes=30, session_ttl_hours=12 | 수정 |
| F09 | WEB_FAQ.md | 3-2 | suggestion_blocked 해결 | 엄격 모드 경고는 [제목 수정]으로 고쳐 다시 검증하거나 [반려]. 영어 `blocked` 로 보이는 카드는 버튼이 없으니 쓰지 말고 다른 후보를 고르세요(Q17) \| | domain/suggestions.py:259,269; SuggestionCard.tsx | 수정 |
| F10 | WEB_FAQ.md | 3-3 | precheck_stale 해결 | \| 화면에는 초안을 취소하는 버튼이 없으니 개발 담당에게 "초안 배치 #번호 취소"를 요청한 뒤 새로 점검을 만드세요(Q18) \| | batches.py:279 hint; DiscardDraft.tsx | 수정 |
| F11 | WEB_FAQ.md | 3-3 | 건너뜀 사유 코드 표 | \| `video_excluded` \| 제외 대상 영상 \| \| `pending_change_exists` | batches.py:384,409 | 수정 |
| F12 | WEB_FAQ.md | 3-4 | 롤백 오류 코드 표 | \| `typed_video_id_mismatch` \| 입력한 영상 ID가 다름 \| 영상 ID를 화면 그대로 다시 입력 \| | domain/changes.py:72-76,117-128 | 수정 |
| F13 | WEB_FAQ.md | 4-1 첫 Q | 구글 연결 후 띠 안내(알려진 결함 문장) | (참고: 홈 맨 위 띠와 "연결 상태" 칸은 알려진 결함으로 계속 "데모 모드"로 보일 수 있으니, 구글 연결 후에는 카드 쪽을 믿으세요.) | Layout.tsx:11-33; HomePage.tsx:189-195 | 수정 |
| F14 | WEB_FAQ.md | 4-1 허용 영상 Q | 서버 설정 넣는 방법 | 서버 설정을 넣는 구체적 방법은 아직 정해지지 않았습니다 [확인 필요, `WEB_INSTALL.md` 8-4]. | web/.env.example; compose.online.yaml:10-12 | 수정 |
| F15 | WEB_FAQ.md | 4-1 끄는 법 Q | 서버 설정 파일 위치 | 서버 설정으로 끄려면 `YTWEB_LIVE_WRITE` 를 끄거나 허용 영상 목록을 비운 뒤 다시 시작해야 하며, 설정 파일 위치는 [확인 필요]입니다. | web/.env.example:3-6 | 수정 |
| F16 | WEB_FAQ.md | 4-1 실제 모드 확인 문구 Q | 실제 모드에서 데모 문구 입력 시 | 데모 때처럼 `실행 N건` 을 입력하면 `confirm_text_mismatch` 가 나오며 아무것도 바뀌지 않습니다. | BatchDetailPage.tsx:310 (phrase !== expected → 버튼 비활성); batches.py:263-265 | 수정 |
| F17 | WEB_FAQ.md | 4-1 쿼터 행 | 쿼터 단위 | \| 오늘 구글 API 사용량 소진 \| 미국 태평양 시간 자정 이후 다시. 제목 수정 1건은 50단위 \| | config/settings.yaml quota; limits_quota.py:95-97 | 수정 |
| F18 | WEB_FAQ.md | 4-1 마지막 Q | 상단 띠 결함 Q | **Q. 구글을 연결했는데 상단에는 계속 "데모 모드 — 유튜브에 아무것도 전송되지 않습니다"라고 나와요.** 알려진 결함입니다(수정 예정). 구글을 연결하면 [내 영상 불러오기] 때 실제로 구글에 요청을 보냅니다. 화면 맨 위 띠는 이 상태를 반영하 | Layout.tsx:11-33; domain/dashboard.py:50-52 | 수정 |
| F19 | WEB_FAQ.md | 5장 확인하지 못한 항목 | 7·9단계 반영 전 | - 7단계(전체 통합)·9단계(보안) 결과 반영 전입니다 | STATE.md | 수정 |
| I01 | WEB_INSTALL.md | 머리말 | 문서 상태 표시 | > 초안 — 2026-10-11 스크립트 대조 반영본. 7~10단계 결과와 선생님 PC 확인 후 다시 대조해야 합니다. | 요청 지시 | 수정 |
| I02 | WEB_INSTALL.md | 2장 단계 5 | 첫 화면 확인(띠·바닥글) | - 화면 위쪽에 노란 띠 **"데모 모드 — 유튜브에 아무것도 전송되지 않습니다"** 와 "서버 연결됨"이 보여야 합니다. | Layout.tsx:11-33,127-130; ko.ts:6,42 | 수정 |
| I03 | WEB_INSTALL.md | 5장 | 정적 점검 건수 | 정적 점검 명령은 클라우드 Linux에서 임시 가상환경으로 실행해 244건 중 76 통과·168 건너뜀(Windows PowerShell·실제 컨테이너 기동이 필요한 시험)·실패 0을 확인했습니다. Windows PC에서는 실행하지 않았고, 일반 사용 | docs/harness/STATE.md 2026-10-11 인프라 독립 검증 줄(197 통과·331 건너뜀·1 xfail); units/web-WU-FIX-INF-test.md 159-165 | 수정 |
| I04 | WEB_INSTALL.md | 7장 머리말 | DEC-046 노출·M2 재평가 시점 | ## 7. 알려진 보안 사항 3가지와 선생님이 지금 할 일 (M1 한정 수용, DEC-046)  9단계 보안 점검에서 나온 항목 중, **지금(데모 모드, 가짜 데이터)에는 그대로 두기로 결정한 3가지**입니다(2026-10-11 DEC-046, "M | decisions.md DEC-046(수용 조건·재평가 트리거); 재평가 기록 없음(docs/harness grep 결과) | 수정 |
| I05 | WEB_INSTALL.md | 7-1 제목 | DEF 번호 노출 | ### 7-1. DEF-9-011 — 프로그램 안의 컨테이너가 이 PC에서 열려 있는 다른 서비스에 닿을 수 있음 | 사용자용 문서에서 DEF 용어 제거 | 수정 |
| I06 | WEB_INSTALL.md | 7-1 마지막 줄 | 다시 판단하는 때(7-1) | - 다시 판단하는 때: M2 착수 전, 다중 사용자, 외부 접속(다른 기기에서 접속)을 허용하기 전.  ### 7-2. | DEC-046 재평가 트리거를 현재 상태(M2 코드 존재)에 맞춤 | 수정 |
| I07 | WEB_INSTALL.md | 7-2 제목 | DEF 번호 노출 | ### 7-2. DEF-9-014 — 감사 로그가 "DB 관리자 계정이 기록을 고치고 다시 계산"하는 것은 알아채지 못함 | DEF 용어 제거 | 수정 |
| I08 | WEB_INSTALL.md | 7-2 마지막 줄 | 다시 판단하는 때(7-2) | - 다시 판단하는 때: **M2 착수 전**, **다중 사용자**가 생길 때, **외부 접속**을 허용할 때. | DEC-046 재평가 트리거를 현재 상태에 맞춤 | 수정 |
| I09 | WEB_INSTALL.md | 7-3 제목 | DEF 번호 노출 | ### 7-3. DEF-9-013 — 데이터 보관 기간·삭제·백업 암호화가 아직 없음 | DEF 용어 제거 | 수정 |
| I10 | WEB_INSTALL.md | 7-3 | 실제 채널 연결 전 결정 | 2. 실제 채널을 연결하기 전(**M2 착수 전**)에 ① 보관 기간 | DEC-046 재평가 트리거를 현재 상태에 맞춤 | 수정 |
| I11 | WEB_INSTALL.md | 7장 끝 | 결정 근거 문장(DEC 번호) | 결정 근거는 `docs/harness/decisions.md` DEC-046, 원 보고서는 `docs/harness/security-web-m1-test.md` 입니다. | DEC 번호 제거 | 수정 |
| I12 | WEB_INSTALL.md | 8-2 3번 | 카드 안내문 | 3. 브라우저 홈 화면의 **"구글(유튜브) 연결"** 카드에서 "구글 연결 파일 없음" 안내가 사라지고 [구글 계정 연결] 버튼이 보이면 준비된 것입니다. (실제로 그렇게 보이는지는 내 PC에서 확인 필요.) | ko.ts:208-209; routers/google.py:30-32 | 수정 |
| I13 | WEB_INSTALL.md | 8-4~8-5 | 실제 수정 켜기 절차 순서·표현 | ### 8-4. 실제 제목 수정을 켜는 방법 실제 수정은 아래 **3가지가 모두** 맞을 때만 켜집니다. 하나라도 아니면 가짜(모의) 방식으로만 동작합니다. 1. 서버 설정 `YTWEB_LIVE_WRITE=1` (기본은 꺼짐) 2. 화면에서 [제목 수 | web/.env.example; compose.online.yaml:10-12,22-24; GoogleCard.tsx:79-108; Layout.tsx:14-20; 사용자 지시 절차 순서 | 수정 |
| I14 | WEB_INSTALL.md | 8-5 6번 | 끄는 방법 문장(중복·깨진 표기) | 6. 끄려면: 서버 설정 `YTWEB_LIVE_WRITE` 를 끄거나 허용 목록을 비우고 `start.ps1` 로 다시 시작하거나, 화면의 [연결 해제]를 누르면 됩니다(쓰기 토큰도 함께 지워져 실제 수정이 멈춥니다). `web\\.env` 에서 `Y | routers/google.py disconnect(읽기·쓰기 토큰 삭제); web/.env.example | 수정 |
| R01 | WEB_RUNBOOK.md | 머리말 | 문서 상태 표시 | > 초안 — 2026-10-11 코드·스크립트 대조 반영본. 7~10단계 결과와 선생님 PC 확인 후 다시 대조해야 합니다. | 요청 지시 | 수정 |
| R02 | WEB_RUNBOOK.md | 머리말 박스 | 오타와 네트워크 설명 | 실제 구글·AI 연결과 실제 제목 변경은 별도 승인 후에만 진행합니다.니다. 이 서버의 `api/worker/db` 컨테이너는 인터넷으로 나가지 못하는 내부 네트워크에 있고, 화면 서버(`web`)는 DB에 닿지 못하게 네트워크가 나뉘어 있습니다(`f | compose.online.yaml:5-17; compose.yaml:251-258 | 수정 |
| R03 | WEB_RUNBOOK.md | 2-1 시작 | 구글 파일 유무에 따른 compose 구성 | 4. "준비 완료!" 가 나오면 성공. 실패하면 문제 서비스의 마지막 로그 25줄이 자동 출력됩니다. | scripts/_common.ps1:Invoke-Compose | 수정 |
| R04 | WEB_RUNBOOK.md | 3장 정상 범위 | 세션 만료 기준 | 요청 본문은 1MB까지. 세션은 12시간. | config.py:32,63-64; decisions.md 세션 유휴 만료 30분 유지 결정 | 수정 |
| R05 | WEB_RUNBOOK.md | 7 감사 로그 확인 | 기록 항목과 영어 동작 이름 | - 기록되는 것: 세션 발급·거부·종료, 설정 변경, 영상 새로고침, 제안 생성·수정·승인·반려, 배치 생성·실행·취소, 항목 건너뜀·실패·이월·복구, 반영, 롤백. 화면에는 `suggestion.approve` 같은 영어 동작 이름 그대로 나옵니다. | ko.ts:656-696; SettingsPage.tsx:390-405; routers/google.py audit.record 호출 | 수정 |
| R06 | WEB_RUNBOOK.md | 8 비밀 관리 표 | web\.env 항목 추가 | \| AI 키 \| **존재하지 않음** (AI 실서비스 미연결) \| 연동 단계에서 별도 설계 \| | web/.env.example; compose.online.yaml:10-12; .gitignore:25 | 수정 |
| R07 | WEB_RUNBOOK.md | 9 정기 점검 | 비용 문장의 쿼터 단위 | 구글 API 한도(하루 6,000단위 기본, 1건당 52단위)와 AI 비용은 **데모에서는 발생하지 않으며** 실제 연동 단계에서 정합니다(`[확인 필요]`: 실제 구글 쿼터 수치는 확인되지 않음). | config/settings.yaml quota; limits_quota.py:95-97 | 수정 |
| R08 | WEB_RUNBOOK.md | 13장 | 보안 점검 결과 확인 문장 | - 6단계 독립 검증은 4건 결과서가 있습니다(백엔드 기반·도메인 PASS, 프런트·인프라 조건부 PASS). 7단계 통합 시험과 9단계 보안 점검(이미지 취약점·SBOM·`pip-audit`·인젝션 시험)은 이 문서 작성 시점에 **결과를 확인하지  | docs/harness/STATE.md 최신 줄들; security-web-m1-test.md; decisions.md DEC-046·DEC-049 | 수정 |
| R09 | WEB_RUNBOOK.md | 13장 | 정적 점검 건수 | - 인프라 정적 점검 `python -m pytest web/tests_infra` 를 클라우드 Linux(임시 가상환경, 파이썬 3.13, 의존성은 버전만 맞춤)에서 실행했습니다: 244건 중 76 통과·168 건너뜀(Windows PowerShel | STATE.md 인프라 독립 검증 줄; units/web-WU-FIX-INF-test.md:159-165 | 수정 |
| R10 | WEB_RUNBOOK.md | 13장 | 실제 구글 연동 없음(과거 문장) | - 실제 구글·AI 연동은 없음. 연동 시 `web/compose.online.yaml` 로 api/worker에만 외부 통신을 열 계획이며 지금은 사용하지 않습니다. | compose.online.yaml; ai/factory.py(모의 AI만) | 수정 |
| R11 | WEB_RUNBOOK.md | 13-1 표 제목~표 끝 | 코드 후속 조치 표 전체와 초안 취소 우회 절차 | ### 13-1. 코드 후속 조치 필요 (문서가 아니라 화면·서버 코드를 고쳐야 하는 것) 2026-10-11 코드 대조에서 발견했습니다. 문서는 현재 동작을 사실대로 적었습니다. \| 번호 \| 증상 \| 근거 \| 영향 \| \|---\|---\|---\|---\| | SuggestionCard.tsx; DiscardDraft.tsx; ko.ts; Layout.tsx; SettingsPage.tsx:124-154,327-328; BatchDetailPage.tsx:288; limits.py:147,163; config.py:22; HomePage.tsx:71-83 | 수정 |
| R12 | WEB_RUNBOOK.md | 13-2 머리말 | DEC 번호와 재평가 시점 | ### 13-2. 보안 결정: M1 한정 수용 3가지와 선생님이 지금 할 일 (DEC-046)  9단계 보안 점검에서 나온 항목 중, **지금(데모 모드, 가짜 데이터)에는 그대로 두기로 결정한 3가지**입니다(2026-10-11 DEC-046, "M | decisions.md DEC-046; 재평가 기록 없음 | 수정 |
| R13 | WEB_RUNBOOK.md | 13-2-1 | 제목 DEF 번호 | #### 13-2-1. DEF-9-011 — 프로그램 안의 컨테이너가 이 PC에서 열려 있는 다른 서비스에 닿을 수 있음 | DEF 용어 제거 | 수정 |
| R14 | WEB_RUNBOOK.md | 13-2-1 | 재판단 시점 | - 다시 판단하는 때: M2 착수 전, 다중 사용자, 외부 접속(다른 기기에서 접속)을 허용하기 전.  #### 13-2-2. | DEC-046 재평가 트리거를 현재 상태에 맞춤 | 수정 |
| R15 | WEB_RUNBOOK.md | 13-2-2 | 제목 DEF 번호 | #### 13-2-2. DEF-9-014 — 감사 로그가 "DB 관리자 계정이 기록을 고치고 다시 계산"하는 것은 알아채지 못함 | DEF 용어 제거 | 수정 |
| R16 | WEB_RUNBOOK.md | 13-2-2 | 재판단 시점 | - 다시 판단하는 때: **M2 착수 전**, **다중 사용자**가 생길 때, **외부 접속**을 허용할 때. 해결 방법 후보 | DEC-046 재평가 트리거를 현재 상태에 맞춤 | 수정 |
| R17 | WEB_RUNBOOK.md | 13-2-3 | 제목 DEF 번호 | #### 13-2-3. DEF-9-013 — 데이터 보관 기간·삭제·백업 암호화가 아직 없음 | DEF 용어 제거 | 수정 |
| R18 | WEB_RUNBOOK.md | 13-2-3 | 결정 시점 | 2. 실제 채널을 연결하기 전(**M2 착수 전**)에 ① 보관 기간 | DEC-046 재평가 트리거를 현재 상태에 맞춤 | 수정 |
| R19 | WEB_RUNBOOK.md | 13-2 끝 | DEC 번호와 healthz 문단 | > 위 3가지는 모두 "선생님이 지금 해야 할 큰 일"은 없고, 방화벽 확인(13-2-1)만 권장입니다. 결정 근거는 `docs/harness/decisions.md` DEC-046, 원 보고서는 `docs/harness/security-web-m1- | DEC/DEF 번호 제거; nginx.conf:72-85 | 수정 |
| R20 | WEB_RUNBOOK.md | 14장 | 결정 대기 표 Q-11-09~11 | \| Q-11-09 \| 13-1의 C-1~C-2(차단 제안 버튼, 초안 배치 취소 버튼)를 7~8단계 전에 고칠지 \| 소유자 승인(코드 수정은 이 문서 소관 밖) \| \| Q-11-10 \| **실제 수정 켜기(`YTWEB_LIVE_WRITE`)·허용 영상 | web/.env.example; compose.online.yaml; Layout.tsx:11-33; HomePage.tsx:186-197; SettingsPage.tsx:327-328 | 수정 |
| R21 | WEB_RUNBOOK.md | 15-1 | 켜는 방법 확인 필요(과거) | - **켜는 방법 — 확인 필요**: 2026-10-11 `web/compose.yaml`, `web/compose.online.yaml`, `web/scripts/*.ps1` 을 확인한 결과 `YTWEB_LIVE_WRITE`·`YTWEB_LIVE_A | web/.env.example; compose.online.yaml:10-12,22-24 | 수정 |
| R22 | WEB_RUNBOOK.md | 15-1 | 끄는 가장 빠른 방법 보충 | - **끄는 가장 빠른 방법(코드로 확인)**: 화면 [연결 해제]는 | 문장 구조 보강(② 추가를 위한 선행 수정) | 수정 |
| R23 | WEB_RUNBOOK.md | 15-1 | 끄는 방법 ② 추가 | 이미 큐에 있는 반영 작업이 있어도 워커가 같은 선택 규칙을 쓰므로 토큰이 없으면 실제 쓰기를 하지 않는 구조입니다(코드 읽기 기준, 실행 확인 아님). | domain/batches.py:383-384; domain/changes.py:72-76 | 수정 |
| R24 | WEB_RUNBOOK.md | 15-3 | 되돌리기 단계(6번) | 6. **되돌리기**: 이력·롤백 화면(영상 ID를 직접 입력해 확인). 허용 목록에서 빠진 영상은 롤백이 `live_not_allowed` 로 막히니 Studio 에서 직접 고칩니다. | domain/changes.py:117-128; decisions.md DEC-049 | 수정 |
| R25 | WEB_RUNBOOK.md | 15-4 쿼터 | 쓰기 단위 | - **쓰기: 제목 1건 변경(`videos.update`) = 50단위.** 하루 반영 10건이면 500단위. | config/settings.yaml quota; limits_quota.py:95-97 | 수정 |
| R26 | WEB_RUNBOOK.md | 15-5 정기 점검 표 | 반영 후 정리 행 | \| 반영 끝나면 즉시 \| 더 쓸 계획이 없으면 [연결 해제] (쓰기 권한을 필요한 때만 연결) \| | web/.env.example | 수정 |
| R11b | WEB_RUNBOOK.md | 13-1 | 초안 배치 취소 우회 절차(파이썬 코드) | **초안 배치 취소 절차 (개발 담당용, C-2 임시 우회)** … | DiscardDraft.tsx, BatchDetailPage.tsx:267 (화면 버튼 존재) | 수정(삭제) |
| R27 | WEB_RUNBOOK.md | 5-2 | 내부 코드 번호 노출(DV-W08) | (`core/audit.py`, 설계서 DV-W08) | 개발자 용어 제거 | 수정 |
| R28 | WEB_RUNBOOK.md | 15-1 | 시험 이름 노출(test_tc_m3_012) | `routers/google.py` disconnect, 시험 `test_tc_m3_012`) | 개발자 용어 제거 | 수정 |
| R29 | WEB_RUNBOOK.md | 15-2 표 | 시험 이름 노출 | \| 시험 `test_tc_m3_012`. Windows 실제 클릭 미확인 \| | 개발자 용어 제거 | 수정 |
| R30 | WEB_RUNBOOK.md | 15-2 | 시험 이름·threat_model W9 노출 | (시험 `test_tc_m2_008·025`) | 개발자 용어 제거 | 수정 |
| R31 | WEB_RUNBOOK.md | 15-2 | threat_model W9 노출 | (threat_model W9 참고) | 개발자 용어 제거 | 수정 |
| L01 | WEB_LEGAL_NOTICE.md | 머리말 | 문서 상태 표시 | > 초안 — 2026-10-11 코드 대조 반영본. 7~10단계 결과와 법률 검토 후 다시 대조해야 합니다. | 요청 지시 | 수정 |
| L02 | WEB_LEGAL_NOTICE.md | 머리말 표 | 근거 행의 내부 번호 | `docs/yt/02_planning.md` Part W(POL-001~016) | 개발자 용어 제거 | 수정 |
| L03 | WEB_LEGAL_NOTICE.md | 1장 표 | 현재(데모) 통신 경로 | \| 현재(데모) \| 유튜브·AI로 나가는 통신 경로가 없음. 이 PC 안(127.0.0.1)에서만 열림 \| | compose.online.yaml:5-17; scripts/_common.ps1:Invoke-Compose | 수정 |
| L04 | WEB_LEGAL_NOTICE.md | 3-2 | 면책·AI 고지 미구현 문단(전체) | - **현재 웹 화면에는 "이 검증은 법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다" 같은 면책 문구가 표시되지 않습니다.** (기획서에서는 표시하도록 정했으나 미구현. 2026-10-11 화면 문구 파일 `ko.ts` 와 화면 소스 전체를 | ko.ts:41-57; Layout.tsx:127-130; SuggestionCard.tsx:133-141,279-284; BatchDetailPage.tsx:154-157; VideoDetailPage.tsx:114-117; HistoryPage.tsx:134-137; ReportsPage.tsx:158-165; domain/notices.py:4; domain/batches.py:213 | 수정 |
| L05 | WEB_LEGAL_NOTICE.md | 4장 | A/B 확인 문구 미구현 문장 | 실제 연동 단계에서는 **A/B 테스트 중인 영상은 소유자가 직접 Studio에서 확인해 제외**해야 하며, 확인 문구에 "A/B 테스트 중이 아님" 확인을 넣는 안(POL-013)은 **미구현**입니다. | BatchDetailPage.tsx:289-311; endpoints.ts:60-65 (confirm_text만 전송); decisions.md DEC-047(②) | 수정 |
| L06 | WEB_LEGAL_NOTICE.md | 5장 표 | 외부 전송 행 | \| 외부 전송 \| **없음.** AI 호출 코드가 없고 api/worker/db 컨테이너는 외부 통신이 막힌 내부 네트워크에 있음 \| 연동 시 별도 승인 후 `compose.online.yaml` 로 api/worker에만 외부 통신을 열 계획 \| | ai/factory.py(모의 AI만); compose.online.yaml | 수정 |
| L07 | WEB_LEGAL_NOTICE.md | 5장 규제 목록 | 출처 표기 한계(유지 확인) | AI 제안은 출처가 `ai:모델명`으로 기록되지만, **사람이 제목을 고쳐도 출처 표기가 바뀌지 않아** AI 원문과 사람 수정본을 구분할 수 없음 (알려진 제한) | domain/suggestions.py:213-238 (edit_title 이 source 를 바꾸지 않음); SuggestionCard.tsx:118 | 수정 |
| L08 | WEB_LEGAL_NOTICE.md | 6장 표 | 수집 항목·제3자 제공 행 | \| 수집하지 않는 것 \| 시청자 개인정보. 구글 계정 정보·토큰은 아직 없음 \| | routers/google.py; live_sync.py (videos 저장) | 수정 |
| L09 | WEB_LEGAL_NOTICE.md | 6장 표 | 제3자 제공 행 | \| 제3자 제공 \| 현재 없음. 실제 연동 시: 구글(본인 채널 읽기), AI 서비스(제목+설명 요약) \| | compose.online.yaml; google_oauth.py | 수정 |
| L10 | WEB_LEGAL_NOTICE.md | 7장 표 | 쿼터 행(단위 혼용) | \| API 쿼터 \| 기본 하루 10,000단위, 제목 변경 1건 50단위(이 프로그램 기본 상한은 6,000단위, 1건 52단위로 계산) \| `[확인 필요]` 공식 원문 확인 전. | config/settings.yaml quota(update_cost 50, read_cost 1, daily_limit_units 6000); domain/limits_quota.py:95-97 | 수정 |
| L11 | WEB_LEGAL_NOTICE.md | 7장 표 | 쿼터 행 뒤 정책 번호 | 여러 프로젝트로 한도를 늘리지 않는 정책(POL-015) | 개발자 용어 제거 | 수정 |
| L12 | WEB_LEGAL_NOTICE.md | 9장 표 | 면책 문구 결정 행 | \| Q-11-L5 \| 화면에 면책 문구·AI 생성 고지·건강/금융 주의 문구를 넣을 위치와 문구 \| 결정 대기 (현재 미구현) \| | ko.ts:41-57 | 수정 |
| L13 | WEB_LEGAL_NOTICE.md | 10-1 표 | 구글 쪽 통신 가능성 문장 보강 없음(표시 결함 행) | \| 표시 결함 \| 구글 연결 후에도 상단 띠가 "아무것도 전송되지 않습니다"로 보일 수 있음(DEF-VMF-001, 수정 예정) — **실제 전송이 일어나는데 화면이 아니라고 안내하는 것은 고지의 정확성 문제**이므로 실제 연결 전에 수정 필요 \| 6 | Layout.tsx:11-33; SettingsPage.tsx:327-328; 6단계 프런트 검증 결과서 결함 항목의 조치 기록(STATE.md) | 수정 |
| L14 | WEB_LEGAL_NOTICE.md | 10-2 | 쿼터 차이 문장 | 제목 1건 수정은 코드 주석상 50단위(이 문서 7장의 "52단위" 기재와 차이 — 어느 쪽이 맞는지 `[확인 필요]`). | config/settings.yaml quota; domain/limits_quota.py:95-97 | 수정 |
| L15 | WEB_LEGAL_NOTICE.md | 10-2 | 정책 번호 노출 | 여러 프로젝트로 한도를 늘리는 행위는 하지 않는다는 정책(POL-015) | 개발자 용어 제거 | 수정 |
| A01 | API.md | 머리말 표 | 문서 상태·근거·모드 행 | \| 문서 상태 \| **초안(검증 대기)** — 6단계 독립 검증 4건이 진행 중이라 결함이 나오면 갱신된다. 상단 "검증 대기 항목" 표는 `DESIGN.md` 맨 위에 있다 \| \| 작성 기준일 \| 2026-10-10 \| \| 근거 \| 실제 코드 `we | openapi.json 경로·동작 수 직접 집계(34/31); STATE.md; routers/google.py | 수정 |
| A02 | API.md | EVT-W08 대시보드 | 필드 설명 | `today`는 KST 하루 기준 반영 건수와 하루 상한, `quota`는 태평양 시간 기준 API 사용 단위. | domain/dashboard.py:21-29,50-52; Layout.tsx:11-33 | 수정 |
| A03 | API.md | EVT-W11 sync | 데모 전용 설명 | (데모) 가상 영상 200개를 만들거나 새로고침하는 작업을 큐에 넣는다. | domain/handlers.py:40-60; domain/live_sync.py:30-70 | 수정 |
| A04 | API.md | EVT-W22 위 규칙·EVT-W21 아래 | 실제 모드 확인 문구(execute 설명) | 본문 `{"confirm_text": "실행 1건"}` — 문구는 **정확히 `실행 {대기 항목 수}건`**(사전 점검의 `confirm_text`). | domain/batches.py:263; live_gateway.py:confirm_text; endpoints.ts:60-65 | 수정 |
| A05 | API.md | EVT-W21 오류 표 뒤 | 실행 시 항목 단위 모드 변경 | \| 400 / 422 / 409 `idempotency_*` \| 1-6 참고 \| | domain/batches.py:383-384,407-409 | 수정 |
| A06 | API.md | 항목 처리 중 사유 코드 표 | 건너뜀 코드 목록 | `title_changed` `video_changed` `batch_not_active` `suggestion_missing` `cancelled` \| | domain/batches.py:383-384,409 | 수정 |
| A07 | API.md | EVT-W25 롤백 오류 표 | 실제 모드 거부 코드 | \| 429 `quota_exhausted` \| 오늘 쿼터 부족(태평양 시간 자정에 초기화) \| | domain/changes.py:72-76,92-94,117-128 | 수정 |
| A08 | API.md | EVT-W28 감사 | 주요 action 목록 | `batch.create/execute/cancel`, `batch.item.skipped/failed/recovered`, `change.apply/rollback/rollback_failed`. | routers/google.py audit.record 호출; domain/handlers.py:_sync_live; batches.py:421 | 수정 |
| A09 | API.md | EVT-W29 설정 | read_only 설명 | {"daily_apply_cap": 10, "suggestions_per_video": 3, "tone": [], "pin_enabled": false, "mode": "demo",  "read_only": {"enable_live": false, " | routers/settings.py:64-78 (policy.enable_live, policy.live_allowlist) | 수정 |
| A10 | API.md | 10 변경 이력 | v0.3 행 추가 | \| 2026-10-11 \| v0.2 \| | 변경 이력 추가 | 수정 |
| D01 | WEB_DESIGN.md | §3 표 dashboard 행 | live_enabled 고정값 | `{mode:"demo"\\|"live", live_enabled:false, google:{mode,connected}, counts | domain/dashboard.py:50-52; schemas.py DashboardOut | 수정 |
| D02 | WEB_DESIGN.md | §3 표 execute 행 | 확인 문구 | 실행(`confirm_text == "실행 {n}건"`) | live_gateway.py:confirm_text; batches.py:263 | 수정 |
| D03 | WEB_DESIGN.md | §3 표 google 행 | 구글 엔드포인트 누락 | \| GET `/api/v1/google/status` \| 구글 연결 상태 \| `{mode:"demo", connected:false, message}` (M1) — M2·M3 에서 필드가 늘었다: §12 \| | routers/google.py:62-150; API.md EVT-W31~W35 | 수정 |
| D04 | WEB_DESIGN.md | §3 주요 스키마 | precheck 필드 | blocked[{suggestion_id,reason,code?}],confirm_text}`. | domain/batches.py:166-214 (blocked 항목의 batch_id, notice) | 수정 |
| D05 | WEB_DESIGN.md | §4-3 한도 | 데모 최소 노출수 0 미반영(과거) | (`youtube_title.limits.evaluate_limits`; **데모 최소 노출수 0 결정은 코드 미반영**, DV-W15) | domain/common.py:44-46 (relax = 0 if web.mode == 'demo'); decisions.md 데모 최소 노출수 결정 | 수정 |
| D06 | WEB_DESIGN.md | §6 화면 | 구글 상태 배지 상시 데모 표시 | 설정 / 구글 상태 배지("데모 모드" 상시 표시, "dry-run"은 "미리보기"로 표기). | Layout.tsx:11-33,127-130; BatchDetailPage.tsx:267,289-311; ko.ts:6-8 | 수정 |
| D07 | WEB_DESIGN.md | §12-3 미해소 | 설정 전달 항목 없음(과거) | - **미해소 (확인 필요)**: `YTWEB_LIVE_WRITE`·`YTWEB_LIVE_ALLOWED_VIDEOS` 를 컨테이너에 전달하는 항목이 `compose.yaml`·`compose.online.yaml`·스크립트에 **없다**(2026-10 | web/compose.online.yaml:10-12,22-24; web/.env.example | 수정 |
| D08 | WEB_DESIGN.md | §12-6 결함 표 | DEF-VMF-001~004 상태 | \| **DEF-VMF-001** \| **대시보드 모드 표시 결함**: 상단 띠("데모 모드 — 유튜브에 아무것도 전송되지 않습니다")와 홈 "연결 상태" 칸이 고정값(`Layout.tsx`, `domain/dashboard.py` 가 `mode:"de | Layout.tsx; dashboard.py; GoogleCard.tsx:79-108; ko.ts:215-224; compose.online.yaml; HomePage.tsx:189-195; SettingsPage.tsx:327-328 | 수정 |
| D09 | WEB_DESIGN.md | §12-6 뒤 | 검증 상태 머리말 | 독립 검증 결과서(`docs/harness/units/web-WU-M23-FE-test.md` 등)에 열린 결함이 있다(아래 12-6). 근거 결정: DEC-046~048. | decisions.md DEC-046~049 | 수정 |
| D10 | WEB_DESIGN.md | §12-6 끝 | 12-7 추가 | - 위협 모델: `threat_model.md` W9(TW-37~44). 미반영: `API.md` 상세·`openapi.json` 은 2026-10-11 갱신됨(EVT-W31~35), 독립 검증·9단계 재검증은 이 장을 아직 다루지 않았다. | domain/batches.py:285,383-384; domain/changes.py:72-76,117-128; routers/google.py:126; decisions.md DEC-047·049 | 수정 |
| D11 | WEB_DESIGN.md | §11 변경 이력 | v4 행 | \| 2026-10-11 \| v3 \| §12 M2·M3 | 변경 이력 | 수정 |
| D12 | WEB_DESIGN.md | §0 마일스톤 표 | M3 행 | \| M3 \| 실제 AI 어댑터(서비스 확정 후), 쓰기 로그인, 라이브 반영(테스트 영상 1개로 먼저, 사용자 승인) \| 사용자 승인 필수 \| | STATE.md M3 단위 1~4 완료 줄; youtube/live_write.py, domain/live_gateway.py 존재; ai/factory.py(모의만) | 수정 |
| D13 | WEB_DESIGN.md | §4-1 동작 규칙 | 라이브 게이트웨이는 코드에 없음(과거) | 유튜브 게이트웨이는 `MockYouTubeGateway`(`videos` 테이블이 곧 "유튜브")만 존재, 라이브 게이트웨이는 코드에 없음. | youtube/live_write.py; domain/live_gateway.py:select_gateway | 수정 |
| D14 | WEB_DESIGN.md | §1 코어 재사용 | 14단계 게이트 포팅 문구 | (M3에서 14단계 게이트 포팅) | STATE.md M3 단위 4 완료 줄(CLI 이식이 아니라 웹에 새로 구현) | 수정 |
| D15 | WEB_DESIGN.md | §0 마일스톤 표 | M2 행(OAuth 유형) | \| M2 \| 구글 웹 방식 OAuth(읽기)로 내 채널 영상 실제 가져오기 | decisions.md DEC-048(웹 애플리케이션 가정 → 데스크톱 앱); WEB_DESIGN §12-1 | 수정 |
| D16 | WEB_DESIGN.md | 머리말 표 | 문서 상태 행 | \| 문서 상태 \| **v2 (2026-10-10) — 구현 결과(as-built)에 맞춰 개정한 압축판.** | 변경 이력 v4 | 수정 |
| L16 | WEB_LEGAL_NOTICE.md | 3-2 제목 | 소제목이 새 내용과 어긋남 | ### 3-2. 프로그램이 하지 못하는 것 (소유자가 직접 확인) | 3-2 본문 변경(L04)에 맞춤 | 수정 |
| R32 | WEB_RUNBOOK.md | 3장 상태 점검 | readyz 의 mode 값 의미 | - `readyz` 가 503 `{"status":"degraded","db":"down"}` 이면 DB 문제입니다 → `logs.ps1 -Service db`. | config.py:9,47-50 (MODES=('demo',)); routers/health.py:28 | 수정 |
| A11 | API.md | EVT-W01~W04 | readyz mode 의미 | `readyz` → 200 `{"status":"ok","db":"ok","mode":"demo"}`, | config.py:9,47-50; routers/health.py:28 | 수정 |

## 4. 대조표 — 이미 일치한 항목(수정 없음)

| 번호 | 문서 | 항목 | 실제 근거 | 조치 |
|---|---|---|---|---|
| M-01 | WEB_USER_MANUAL·INSTALL·RUNBOOK | 메뉴 이름 6개(홈/영상 목록/배치(일괄 반영)/이력·롤백/성과 리포트/설정) | web/frontend/src/i18n/ko.ts:31-38; app/Layout.tsx:35-42 | 이미 일치 |
| M-02 | WEB_USER_MANUAL | 홈 카드 문구(오늘 할 일, 오늘 반영 건수, 남은 API 사용량, 80% 경고, 반영 대기열) | ko.ts:234-280; pages/HomePage.tsx:70-183 | 이미 일치 |
| M-03 | WEB_USER_MANUAL | 영상 목록: 검색칸 이름·[검색]·필터 이름·정렬 머리글·[선택 모두 해제]·[선택 영상 AI 제안 생성]·최대 200개·25/50/100개 | ko.ts:283-336; pages/VideosPage.tsx:26-27,141-170,265-289; components Pagination sizes | 이미 일치 |
| M-04 | WEB_USER_MANUAL | 영상 상세: 현재 제목, 변경 한도 상태 문구, [AI 제안 만들기], 변경 이력 | ko.ts:346-370; pages/VideoDetailPage.tsx | 이미 일치 |
| M-05 | WEB_USER_MANUAL | 제안 카드 버튼명 [제목 수정][승인][반려], 확인란 "경고 사유를 모두 읽고 확인했습니다.", 승인자 이름 40자 | ko.ts:405-429; pages/SuggestionCard.tsx:299-310 | 이미 일치 |
| M-06 | WEB_USER_MANUAL | 엄격 모드 규칙(경고도 차단), 제목 1~100자 | ko.ts:384-385,412; SuggestionCard.tsx:70-75 | 이미 일치 |
| M-07 | WEB_USER_MANUAL·FAQ | 배치 한 건 최대 50건 / 메모 200자 / [사전 점검 만들기] / 사전 점검 항목명(반영 대상·예상 사용량·하루 반영 상한·남은 API 한도·날짜별 일정·경고·제외된 항목) | ko.ts:436-475; domain/common.py:21; BatchesPage.tsx:26,196-203 | 이미 일치 |
| M-08 | WEB_USER_MANUAL·FAQ | 확인 문구 형식 `실행 N건`(실제 모드 `실제 실행 N건`) | domain/live_gateway.py:confirm_text; domain/batches.py:263 | 이미 일치 |
| M-09 | WEB_USER_MANUAL | 진행 화면: 2초 자동 새로고침, 건수 라벨(대기/진행 중/성공/실패/건너뜀/취소됨), [중지]→[중지하기] | ko.ts:490-506; BatchDetailPage.tsx:331-359,394-396 | 이미 일치 |
| M-10 | WEB_USER_MANUAL | 이력·롤백 대화상자 문구(영상 ID 직접 입력, 승인자 이름, [롤백 실행]) | ko.ts:558-568; HistoryPage.tsx:57-108 | 이미 일치 |
| M-11 | WEB_USER_MANUAL·API | CSV 파일명 youtube-title-report.csv, [CSV 내보내기] | pages/ReportsPage.tsx:135; ko.ts:577; API.md EVT-W27 | 이미 일치 |
| M-12 | WEB_USER_MANUAL | 설정 탭 4개(안전 설정/PIN/세션·연결/감사 로그), PIN 4~12자리, 말투 5개·20자 | ko.ts:603-614,631-633; routers/settings.py:41-42 | 이미 일치 |
| M-13 | WEB_USER_MANUAL·FAQ·RUNBOOK | 하루 반영 상한 기본 10(1~20), 영상당 제안 기본 3(1~5) | core/settings_store.py:12-13,38-42; ko.ts:607-609; routers/settings.py | 이미 일치 |
| M-14 | WEB_USER_MANUAL·FAQ | 같은 영상 72시간 간격·최대 3회·최소 노출수 1,000(데모는 0), 승인 24시간 | config/settings.yaml cadence·approval; domain/common.py:44-46 | 이미 일치 |
| M-15 | WEB_USER_MANUAL·FAQ·RUNBOOK | PIN 5회 실패 5분 잠금, 2배씩 최대 1시간 | core/pin.py:24-26,102 | 이미 일치 |
| M-16 | WEB_FAQ | 오류 코드 표(93개 백틱 단어) — 모든 코드가 백엔드·코어·nginx 소스에 존재(google_client_*·limit_* 는 접두사+코드로 생성) | 자동 대조: web/backend/ytweb/**/*.py, src/youtube_title/*.py, nginx.conf | 이미 일치 |
| M-17 | WEB_FAQ | rate_limited / payload_too_large(1MB) / host_not_allowed / bad_content_length / internal_error | core/guard.py:122-182 | 이미 일치 |
| M-18 | WEB_FAQ·RUNBOOK | 속도 제한 수치(백엔드 600·쓰기 120·세션 10/분, nginx 30/초 버스트 60, 세션 10/분) | core/ratelimit.py:11-14; docker/nginx/nginx.conf:39-40,87-117 | 이미 일치 |
| M-19 | WEB_FAQ | demo_data_in_use 문구 "데모 기록이 있어 불러올 수 없습니다" | domain/live_sync.py:45 | 이미 일치 |
| M-20 | WEB_FAQ | 구글 오류 안내 문구(로그인 요청 만료, 로그인 취소, 장기 로그인 정보, 인터넷 연결 확인) | youtube/google_oauth.py:101,129,139; routers/google.py:130 | 이미 일치 |
| M-21 | WEB_FAQ·USER_MANUAL | 제외 사유 문구(비공개 영상/아동용 영상/예약 라이브·프리미어 또는 라이브 중/Shorts 가능성(180초 이하)) | src/youtube_title/updater.py:130-142; config/settings.yaml exclusions | 이미 일치 |
| M-22 | WEB_FAQ·USER_MANUAL | 리포트 "변경 후 지표가 아직 없습니다." | src/youtube_title/report.py:229 | 이미 일치 |
| M-23 | WEB_INSTALL·RUNBOOK | start.ps1 단계 문구(1/5 Docker 확인 … 5/5 준비될 때까지 대기)와 "준비 완료!  브라우저에서 열기:  http://127.0.0.1:8080" | web/scripts/start.ps1:26-67 | 이미 일치 |
| M-24 | WEB_INSTALL·FAQ | 시작 오류 문구(Docker 미설치/엔진 연결 불가/Windows 컨테이너 모드/Compose 2.20 미만/포트 8080 사용 중/비밀 파일 없음+볼륨 있음) | web/scripts/_common.ps1:86-100,201; start.ps1:36 | 이미 일치 |
| M-25 | WEB_INSTALL·RUNBOOK | status.ps1 출력(정상/마이그레이션 완료/[위험]/루프백 8080/점검 결과: 문제 없음) | web/scripts/status.ps1:23-82 | 이미 일치 |
| M-26 | WEB_INSTALL·RUNBOOK | 확인 문구 `복원합니다` / `데모 초기화` / `모든 데이터 삭제`, 백업 파일명 ytweb-날짜-시각.dump | scripts/restore.ps1:52; reset-demo.ps1:21,26; backup.ps1:11 | 이미 일치 |
| M-27 | WEB_INSTALL·RUNBOOK | 호스트 게시 포트는 127.0.0.1:8080 하나, 네트워크 front/back(internal)/edge | web/compose.yaml:225-226,251-258 | 이미 일치 |
| M-28 | WEB_RUNBOOK | /api/healthz·/api/readyz 응답, 루트 /healthz·/readyz 는 nginx 404 | routers/health.py:15-29; docker/nginx/nginx.conf:72-101 | 이미 일치 |
| M-29 | WEB_RUNBOOK | 구글 연결 파일이 있을 때만 compose.online.yaml 사용, api·worker 만 egress | scripts/_common.ps1:Invoke-Compose; compose.online.yaml:9-26 | 이미 일치 |
| M-30 | WEB_RUNBOOK·INSTALL | 실제 수정 3조건(YTWEB_LIVE_WRITE=1, 쓰기 토큰, 허용 영상 1개 이상) | domain/live_gateway.py:1-3,43-44 | 이미 일치 |
| M-31 | WEB_RUNBOOK | 토큰 파일명 google_token.json / google_write_token.json | routers/google.py:51-52; live_gateway.py:WRITE_TOKEN_FILE | 이미 일치 |
| M-32 | API | 세션 12시간+유휴 30분, 쿠키 ytw_session, 세션 최대 20개 | config.py:32,63-64; core/sessions.py:16 | 이미 일치 |
| M-33 | API | 에러 코드 표(영상·제안·배치·롤백) — ProblemError 호출 전수와 대조(추가분은 수정 행 참고) | web/backend/ytweb/domain/*.py (ProblemError 목록 grep) | 이미 일치 |
| M-34 | API | Idempotency-Key 필수 3개(배치 생성·실행·롤백), 페이지 최대 200 초과 422 | core/idempotency.py:34-62; domain/common.py:22 | 이미 일치 |
| M-35 | API·DESIGN | 구글 엔드포인트 W31~W35 필드(mode, connected, client_ready, message, last_error, write_connected, live_write_enabled, live_allowed_count, live_write_ready) | routers/google.py:62-77; domain/schemas.py:261-270 | 이미 일치 |
| M-36 | DESIGN | 한도 3겹: 하루 상한(기본 10, 최대 20)·배치 50건·쿼터 6,000단위 80% 경고 | core/settings_store.py:12,38-42; domain/common.py:21; config/settings.yaml | 이미 일치 |

## 5. 확인 필요 목록 (이 대조로 닫지 못한 것)

### 5-1. 사용자(선생님 PC)만 확인할 수 있는 것 — 한 번도 안 한 것

- Windows 10/11 + Docker Desktop(WSL2)에서 `start.ps1`·`status.ps1`·`backup.ps1`·`restore.ps1`·`reset-demo.ps1` 실행 — **한 번도 안 함**(이 환경은 Linux, Windows PowerShell 5.1 없음). 문서마다 "내 PC에서 확인 필요"로 표기돼 있음을 확인.
- 실제 구글 서버 접속, 실제 채널 영상 읽기, 실제 제목 변경 — **한 번도 안 함**(가짜 구글 자동 시험만). 구글이 복귀 주소 `http://127.0.0.1:8080/api/v1/google/callback`(데스크톱 앱 클라이언트)을 받아 주는지, 테스트 상태 7일 만료, 확인되지 않은 앱 화면 — 모두 미확인.
- `web\.env` 가 Windows PC 에서 실제로 api·worker 에 전달되는지(문서는 코드와 이전의 `docker compose config` 확인 기록까지만 인용; 이번 대조에서는 다시 실행하지 않음). 또 `.env` 수정 후 `start.ps1` 재실행 때 구글 로그인 정보가 남아 있는지(저장 공간이 유지된다는 코드 읽기 근거만).
- 구글 쪽 화면 이름("타사 앱 및 서비스 액세스" 등), 구글 쿼터 공식 수치(하루 10,000단위, `videos.update` 50단위)는 공식 원문 미열람 — **확인 필요**.

### 5-2. 문서가 아니라 화면·서버 코드를 고쳐야 하는 불일치(이번 작업은 docs 만 수정 — 문서는 현재 동작을 "알려진 제한"으로 정확히 적음)

| 번호 | 증상 | 근거 |
|---|---|---|
| X-01 | 설정 > 세션·연결 "실행 모드" 칸이 항상 "데모 모드(유튜브에 아무것도 전송되지 않음)" | `SettingsPage.tsx:327-328`, `ko.ts:646` |
| X-02 | 설정 > 안전 설정 "실제 반영(라이브)"·"라이브 허용 영상"이 정책 파일 값(`settings.local.yaml`)만 표시하고 `web\.env` 스위치를 반영하지 않음 | `routers/settings.py:72-76`, `SettingsPage.tsx:129-153` |
| X-03 | 배치 실행 확인 카드 안내문이 실제 수정 모드에서도 "실행하면 데모 데이터의 제목이 바뀝니다" | `ko.ts:482-483`, `BatchDetailPage.tsx:288` |
| X-04 | 홈 "연결 상태" 첫 줄이 구글 연결 파일만 있어도(로그인 전) "구글 연결됨"으로 표시 | `HomePage.tsx:189-195`, `domain/dashboard.py:29` |
| X-05 | 이력 모드 칸에 실제 기록이 영어 `live` 로 표시, 감사 로그 `google.*`·`videos.sync.live` 동작은 한글 이름 없음 | `HistoryPage.tsx:212`, `ko.ts:662-686` |
| X-06 | 제목을 사람이 고쳐도 제안 출처가 바뀌지 않아 "AI 제안" 배지 유지(AI 원문/사람 수정본 구분 불가) | `domain/suggestions.py:213-238`, `SuggestionCard.tsx:118` |
| X-07 | A/B 테스트 아님 확인이 화면 전용(서버가 저장·검사하지 않음) | `api/endpoints.ts:60-65`(confirm_text 만 전송), 결정 기록 2026-10-11 ② |
| X-08 | 한도 문구: "태평양 시간 기준"(실제 한국 시간 하루), "설정 cadence.max_changes_per_video를 바꿔야 합니다"(개발자용) | `src/youtube_title/limits.py:147,163` |
| X-09 | `config.py:31` 주석 "승인·감사 HMAC 키"(감사는 키 없음), `config.py:9` MODES=("demo",)라 `/readyz` 의 `mode` 는 실제 수정 중에도 "demo" | `web/backend/ytweb/config.py`, `routers/health.py:28` |
| X-10 | 데모에서 성과 리포트가 "비교 가능"이 될 수 없음(변경 후 지표 생성 코드 없음, 데모 한계) | `domain/reports.py` (이전 기록) |

### 5-3. 결정 대기·기록 부재

- 보안 수용 3건(컨테이너→호스트 서비스 도달·감사 로그 키 없음·보관/파기/백업 암호화)은 "M2 착수 전 재평가" 조건으로 수용됐는데, M2 코드는 이미 만들어졌고 **재평가 기록은 docs/harness 에서 찾지 못했다**. 문서는 "실제 구글에 연결하기 전에 다시 판단해야 한다"로 현재 상태에 맞춰 적고 확인 필요로 표시했다.
- 인프라 정적 점검 건수(최근 기록 197 통과·331 건너뜀·1 xfail)는 이번에 재측정하지 않았다 — 8단계에서 재측정.
- 운영 담당·문의처·응답 시간(Q-11-01 등 RUNBOOK 14장)은 계속 "미정" — 지어내지 않음.
- 면책·AI 고지 문구의 법적 충분성, 건강·금융 표시·광고, AI 규제 적용 여부, 개인정보 해당 여부 — 법률 자문 아님, 전문가 확인 필요(LEGAL 9·10장 목록 유지).
- 7단계 통합 재시험 결과서(개정 2판)·8단계·9단계 후속·10단계 결과 — 이 대조에 반영하지 못했다(문서 8장/5장에 "2차 대조에서 반영"으로 표기).

## 6. 근거 파일 목록(진실의 원천)

`web/frontend/src/i18n/ko.ts`, `web/frontend/src/pages/*.tsx`, `web/frontend/src/app/Layout.tsx`, `web/frontend/src/lib/labels.ts`, `web/frontend/src/api/endpoints.ts`, `web/backend/ytweb/{config.py,app.py,core/*,domain/*,routers/*,youtube/*}`, `src/youtube_title/{config.py,limits.py,updater.py,report.py}`, `config/settings.yaml`, `web/compose.yaml`, `web/compose.online.yaml`, `web/.env.example`, `web/docker/nginx/nginx.conf`, `web/scripts/*.ps1`, `docs/harness/decisions.md`(2026-10-11 결정 4건: 면책·A/B·필수 수정 묶음 / 수정 단위 질문 처리 / M2 설계 / 실제 모드 롤백 보수적 기본), `docs/harness/STATE.md`.

---

## 7. 2차 대조 (1차 이후 변경분만, 2026-10-11)

> 범위: 1차 이후 커밋(7e594ae 화면 서버 모드 반영·한도 문구, 96a970d DEC-049 롤백, 74a7241 DEF-8-001 조치·8단계 결과)만 반영. `docs/` 문서만 수정, 소스·설정·시험·git 변경 없음. 새 명령 실행·Windows 실행·실제 구글 접속 없음(코드 정독 + grep). 검증 로그 `docs/harness/verify-logs/verify-log_doc-reconcile-web-2.md`(2회).

### 7-1. 한 줄 결론
- **수정 23건**(WEB_USER_MANUAL 10, WEB_FAQ 1, WEB_RUNBOOK 12). WEB_INSTALL·WEB_LEGAL_NOTICE 는 변경 없음(8장 순서 일치 확인, 새 불일치 없음). 5절의 X-01·X-02·X-03·X-05 와 X-04 는 해결, X-08 은 일부 해결.

### 7-2. 수정 내역
| ID | 문서 | 항목 | 근거 | 조치 |
|---|---|---|---|---|
| U34 | USER_MANUAL 4-1 | 홈 "연결 상태" ①줄 "알려진 표시 제한" 삭제(로그인 전 "구글 연결 안 됨") | HomePage.tsx:190-196, ko.ts:268 | 수정 |
| U35 | USER_MANUAL 4-1 | 기준일 문구 "미국 태평양 시간 기준 — 한국 시간 오후 4~5시에 하루가 바뀝니다" | ko.ts:259 | 수정 |
| U36 | USER_MANUAL 4-3 | 3회 한도 사유 문장이 쉬운 말로 바뀜(설정 이름은 괄호로 1회 남음) | limits.py:147 | 수정 |
| U37 | USER_MANUAL 4-4 ③ | 실행 확인 안내문: 데모/실제 수정 모드 문구 구분, 실제 모드 입력 문구 `실제 실행 N건` | ko.ts confirmBodyLive, BatchDetailPage.tsx | 수정 |
| U38 | USER_MANUAL 4-5 | 이력 모드 칸 "실제" 표기(영어 live 제한 삭제) | HistoryPage.tsx, ko.ts modeLive | 수정 |
| U39 | USER_MANUAL 4-5 6번 | 실제 모드 롤백 거부(`live_changed_since_apply`)를 쉬운 말로 추가 | domain/changes.py(반영 뒤 유튜브에서 바뀌면 409) | 수정 |
| U40 | USER_MANUAL 4-7 | 설정 "실행 모드" 칸이 서버 실제 상태를 따름(제한 삭제) | SettingsPage.tsx, useServerMode.ts, ko.ts sessionModeLive | 수정 |
| U41 | USER_MANUAL 9-5 | 이력 모드 칸 표기 "실제"/"데모" | 동일 | 수정 |
| U42 | USER_MANUAL 5장 | 알려진 제한 9개 → 5개로 축소(해결 4건 제외, 1건 부분해소) | 위 근거 | 수정 |
| U43 | USER_MANUAL 5장 | "고쳐진 것" 목록에 서버 모드 반영 4건 추가 | 위 근거 | 수정 |
| F20 | FAQ Q13 | 영어 표시 목록에서 이력 `live` 제거(감사 로그 `google.*`·오류 코드만 남음) | HistoryPage.tsx | 수정 |
| R33 | RUNBOOK 13-1 | 표 머리말을 2차 기준으로 | — | 수정 |
| R34 | RUNBOOK 13-1 | 쿼터 기준일 표시 "고쳐짐" 행 추가 | ko.ts:259 | 수정 |
| R35 | RUNBOOK 13-1 | 하루 한도 사유 "태평양 시간 기준" 행: 남은 제한으로 범위 좁힘(limits.py:163,165 에 문구 잔존) | limits.py | 수정 |
| R36 | RUNBOOK 13-1 | 3회 사유 개발자 문장 → 부분 해소 | limits.py:147 | 수정 |
| R37 | RUNBOOK 13-1 | 설정 "실행 모드"·"실제 반영(라이브)" → 고쳐짐 | SettingsPage.tsx | 수정 |
| R38 | RUNBOOK 13-1 | 실행 확인 안내문 → 고쳐짐 | BatchDetailPage.tsx | 수정 |
| R39 | RUNBOOK 13-1 | 이력 `live` → 고쳐짐, 감사 로그 `google.*` 는 남음(행 분리) | HistoryPage.tsx | 수정 |
| R40 | RUNBOOK 13-1 | 홈 ①줄 제한 → 해소 | HomePage.tsx | 수정 |
| R41 | RUNBOOK 10장 | DB 재시작·연결 끊김 시 반영 항목이 실패가 아니라 "대기"로 돌아가 다음 차례에 처리됨(쓰기 전 단계만, 쓰기 시작 후 끊김은 기존 "예정" 규칙) | domain/batches.py:369-372 | 수정(추가) |
| R42 | RUNBOOK 15-3 6번 | 실제 모드 롤백 거부는 정상 동작이라는 쉬운 설명 | changes.py | 수정 |
| R43 | RUNBOOK 13 | 8단계 결과·성능 참고값·429 설명 추가(DEC/DEF 번호 없이) | docs/harness/system-web-m1-test.md | 수정(추가) |
| R44 | RUNBOOK 15-2·15-5 | 이력 `live` → "실제" 표기 2곳 | HistoryPage.tsx | 수정 |

### 7-3. 자동 대조 결과
- 사용자용 5종 DEC-/DEF- 번호: `grep -nE "DEC-|DEF-"` **0건**(수정 전·후 모두). (참고: API.md·WEB_DESIGN.md 는 개발자용이라 번호를 유지.)
- WEB_INSTALL 8장 순서(구글 파일 → start.ps1 → [구글 계정 연결] → [제목 수정 권한 연결] → `web\.env` → start.ps1 재실행 → 띠·카드 확인)는 `web/.env.example`(두 값, 화면에서 권한 연결까지 필요, 값을 바꾸면 start.ps1 재실행)과 `web/compose.online.yaml`(api·worker 에만 `YTWEB_LIVE_WRITE`·`YTWEB_LIVE_ALLOWED_VIDEOS`, 기본 0·빈 값, google_client.json 있을 때만 사용)에 **일치**. 수정 없음.

### 7-4. 확인 필요 (이 2차로 닫지 못한 것)
- **아직 한 번도 안 한 것**: 선생님 Windows PC 에서 `start.ps1` 등 실행 / `web\.env` 가 PC 에서 실제로 컨테이너에 전달되는지 / 실제 구글 서버 접속·실제 영상 읽기·실제 제목 변경 / 구글이 복귀 주소 `http://127.0.0.1:8080/api/v1/google/callback` 을 받는지 / 이번에 고친 화면 문구(띠 3종, 설정 칸, 실행 확인 안내문, 이력 "실제")를 **화면에서 눌러 캡처 확인한 것은 아님**(코드 정독만).
- 하루 반영 한도 사유의 "오늘(태평양 시간 기준)" 문장(limits.py:163,165)은 코드에 남아 있고, 실제로 어느 시간대로 세는지 문서(1차: 한국 시간 하루)와 `limits.py` 주석 11행(태평양 날짜)이 어긋나 보임 — **개발 담당 확인 필요**(문서는 1차 판단 유지, 단정하지 않음).
- DEF-8-001 조치 후 8단계 재실행 결과(통과 여부)는 결과서에서 확인하지 못함 — RUNBOOK 에 "조치됨, 재실행 결과 확인 필요"로 적음.
- 구글 쿼터 공식 수치, 구글 화면 이름, 보안 수용 3건의 재평가 기록 부재, 운영 담당·응답 시간 "미정", 법적 충분성(전문가 확인) — 1차 5-1·5-3 그대로 유지.
- X-06(직접 고친 제목의 "AI 제안" 배지), X-07(A/B 확인 서버 미검사), X-10(데모 리포트) — 여전히 코드 변경이 필요한 제한.

---

## 3차 대조(줄여 보기·전체 흐름) — 2026-10-13

- 수정 건수: **신규 절 4건 + 문구 정정 2건** — WEB_USER_MANUAL.md 4-3-1(일괄 승인·목록 줄여 보기) 신설, 5-1(영상 목록→제안→일괄 승인→배치→실제 실행 단계표) 신설, 숫자 규칙의 "승인 24시간" 옆에 안내문 불일치 주석 추가. WEB_FAQ.md 4-2장(방금 만든 제안 찾기, 후보 3개 중 하나 고르기, 경고 확인란, 승인 유효시간, 영상 ID 위치, 허용 영상 여러 개 넣기, 쇼츠) 신설, 3-2 "승인은 24시간" 문장에 주석 추가. 쇼츠·허용 영상 목록은 기존 항목(4-1장, 마지막 쇼츠 항목)이 `web/.env.example`·`web/compose.online.yaml` 과 일치함을 확인했고, 4-2장은 여러 영상 쉼표 입력 예만 보강했다.
- 코드 확인: 승인 유효시간은 `web/backend/ytweb/domain/suggestions.py:289` 가 `approval_ttl_hours` 를 쓰고, 이 값은 `config/settings.yaml` `approval.ttl_hours: 24` 에서 읽는다(코드에 기본값 24). 화면 안내문 `ko.bulk.ttlNotice` 는 "기본 1시간" → **불일치**.
- 확인 필요 / 개발 확인 항목: ①`ko.bulk.ttlNotice` "기본 1시간" 안내문을 실제 24시간에 맞춰 수정(소스 수정은 이번 범위 밖이라 하지 않음) ②`config.py` 의 설정 읽기 대체값이 1이라 설정 항목이 빠지면 1시간이 될 수 있음(현재 설정 파일에는 24가 있음, 설정 항목 누락 시 실제 동작은 실행해 확인하지 않음) ③`web/.env.example` 7행 "Shorts(3분 이하)는 제외되어 바꿀 수 없다" 문구가 `YTWEB_INCLUDE_SHORTS` 설명과 어긋남 ④일괄 승인 화면이 왼쪽 메뉴에도 있는지, 영상 ID 가 목록에서 제목 아래 11자로 보이는지, 쉼표 뒤 공백 허용 여부는 화면·실행 미확인.
- 미수행: 화면 직접 실행·캡처, 문서 명령 실행(이번 범위는 문서 수정만).
