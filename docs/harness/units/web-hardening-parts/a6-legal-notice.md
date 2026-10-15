# A6 면책·AI 고지 공용 컴포넌트 (DEF-9-007·008, Q-42 "추천안대로 초안 작성")

시작 01:24:29 UTC, 종료 약 01:27 UTC (소요 약 3분, `date -u` 실측). 문구는 모두 **초안**이며 최종 문구는 채널 소유자(사용자) 승인 전까지 확정이 아니다. 법적 충분성은 이 문서가 판단하지 않는다(공개·실연동 전 전문가 확인 필요).

## 1. 현황 표 (grep 확인, 2026-10-13)
결함 서술(security-web-m1-test.md DEF-9-007·008)은 "화면에 없음"이었으나, **현재 작업 트리에는 이미 상당 부분이 반영되어 있다**(ko.ts `legal.*`는 다른 에이전트가 수정 중인 미커밋 변경 포함 — 커밋 여부는 확인하지 않음).

| 항목 | 상태 | 근거 |
|---|---|---|
| POL-002 면책(`legal.disclaimer`) 전 화면 푸터 | 있음 | `app/Layout.tsx:127-129` 푸터에 disclaimer+aiNotice |
| 면책: 영상 상세 | 있음 | `VideoDetailPage.tsx:115-117` (validationNote+disclaimer) |
| 면책: 제안 카드 상세 | 있음 | `SuggestionCard.tsx:300-304` |
| 면책: 배치 상세 | 있음 | `BatchDetailPage.tsx:154-156` (서버 `pc.notice` 우선, 없으면 disclaimer) |
| 면책: 리포트 | 있음 | `ReportsPage.tsx:163` (서버 notes에 없을 때) |
| 서버 면책 필드 | 있음 | `ytweb/domain/notices.py DISCLAIMER`, `batches.py:218 "notice"` |
| POL-006 AI 고지(`legal.aiNotice`) | 있음 | SuggestionCard 160·301, HistoryPage 136, 푸터 |
| POL-008 AI 한계·표시광고(`legal.aiLimit`) | 있음 | SuggestionCard 161·302, BatchDetailPage 155 |
| 건강·금융 주의(`legal.strictCaution`) | 있음 | SuggestionCard 156·303 (엄격 모드 영상) |
| POL-013 A/B 확인 체크+버튼 비활성 | 있음 | `legal.abConfirm/abHint/abNeeded`, `execGate`, BatchDetailPage 294-309 |
| SettingsPage / BatchesPage 면책 | 없음 | 둘 다 grep 0건. 단, 전 화면 푸터가 이미 면책을 표시하므로 개별 연결 불요(판단) |
| 한 모양으로 쓰는 공용 컴포넌트 | **없었음 → 이번에 추가** | 화면마다 `<div className="legal-note">`를 직접 씀 |
| 추적표 POL-006·008·013 등록(DEF-9-018) | 이번 범위 밖 | 미확인 |

## 2. 구현 (빠진 것만)
- 신규 `web/frontend/src/components/LegalNotice.tsx` (`kind`: `disclaimer`|`ai`|`topic`, `role="note"`, `aria-label`, 클래스 기존 `legal-note muted` 재사용). `components/index.ts`에 export 1줄 추가.
- `ko.ts`에 새 최상위 키 `legalNotice`만 추가(기존 키 변경·삭제 없음). `disclaimer`는 `legal.disclaimer` 재사용.
- 편집 금지 파일(SuggestionCard·VideoDetailPage·BatchDetailPage·VideosPage·HomePage)은 건드리지 않음. SettingsPage·ReportsPage·HistoryPage·BatchesPage도 수정하지 않음(이미 푸터·본문에 문구 있음).

## 3. 초안 문구 전체 (승인용)
| 종류 | 이름표(aria-label) | 문구 |
|---|---|---|
| disclaimer | 책임 안내 | 이 검증은 법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다. (기존 문장 그대로, CLI·서버와 동일) |
| ai | AI 제안 안내 | AI가 만든 제안입니다. 사실과 맞는지, 광고·표시 규정에 어긋나지 않는지 사람이 최종 확인한 뒤 승인하세요. AI는 틀릴 수 있습니다. |
| topic | 건강·금융 제목 주의 | 건강·금융 내용입니다. 병이 낫는다, 원금이나 수익이 보장된다고 읽힐 수 있는 말이 없는지 직접 읽고 확인하세요. |

참고로 기존 문구(`legal.aiNotice/aiLimit/strictCaution/abConfirm`)도 그대로 남아 있다. 새 `ai`·`topic` 문구와 기존 문구가 **중복·불일치**하므로, 사용자가 어느 쪽을 채택할지 정해야 한다(채택 후 한쪽 삭제는 ko.ts 담당 에이전트 작업 종료 뒤).

## 4. 연결 지점 (이번에 연결하지 않음, 필요 시)
1. `pages/SuggestionCard.tsx` 160-161행 `legal-note` 블록과 300-304행 블록: `<p>{ko.legal.aiNotice}</p><p>{ko.legal.aiLimit}</p>` → `<LegalNotice kind="ai" />`, 엄격(`s.strict`)일 때 `<LegalNotice kind="topic" />`, 끝에 `<LegalNotice kind="disclaimer" />`.
2. `pages/BatchDetailPage.tsx` 154-156행: `<LegalNotice kind="ai" />` + 면책은 서버 `pc.notice` 유지(문구 같음).
3. `pages/VideoDetailPage.tsx` 115-117행: `<LegalNotice kind="disclaimer" />`(validationNote는 별도 유지).
4. `pages/VideosPage.tsx`: 건강·금융 영상 행/필터 위에 `<LegalNotice kind="topic" />`는 선택(현재 없음, 필요 여부는 사용자 판단).
5. `pages/HomePage.tsx`: 승인 대기 요약 상단에 `<LegalNotice kind="ai" />`(Q-42의 "승인 화면 상단" 위치 — 현재 승인 화면 상단에는 별도 고지 없음).
위 파일들은 다른 에이전트가 편집 중이라 손대지 않았다.

## 5. 시험
- 신규 `components/LegalNotice.test.tsx` 8건(3종류 role=note 렌더, disclaimer=기존 문장, ai에 AI·사람·광고, topic에 건강·금융, 금지어 `보증·100%·합법·위법하지 않·법령에 맞` 없음, axe 위반 0).
- **수정 전 첫 실행(01:24:44)**: 파일 실패 "Test Files 1 failed, no tests"(LegalNotice 모듈 없음으로 import 해석 실패). 실제 단정 단위의 실패 수는 측정되지 않음(수집 단계 실패).
- 구현 후(01:24:54): 8/8 통과.
- `npx tsc -b --noEmit`: 오류 0. eslint(변경 파일 4개): 0. prettier(변경 파일): 통과.
- 전체 `npx vitest run`: 755 통과 · **3 실패** · 1 expected fail · 21 skipped. 실패 3건은 모두 `src/pages/ai.aibadge.test.tsx`(다른 에이전트가 작성 중인 미추적 파일, DEF-LIVE-006)이며 내 변경과 무관한 것으로 판단(내 변경은 추가뿐; 해당 파일을 열어 원인 확인은 하지 않음). 전체 eslint(`eslint .`)·빌드는 시간상 미수행.

## 6. 한계
- 문구는 초안. 건강·금융 광고 규제, AI 기본법 고지 충족 여부 판단 안 함.
- 연결 안 해서 사용자 화면에는 아직 새 문구가 보이지 않음(컴포넌트만 추가). 이미 있는 기존 문구가 화면에 보이는 것은 실화면 캡처로 확인하지 않았고 소스 grep으로만 확인.
- 9단계 `test_sec_05` xfail 시험의 XPASS 전환 재검증 미수행.
