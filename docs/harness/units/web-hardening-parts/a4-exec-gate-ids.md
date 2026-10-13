# a4: 실행 버튼 비활성 이유 안내 + 입력칸 id/name

시작 01:22:56 UTC, 마지막 확인 01:26:14 UTC (약 3분 20초, date 로 잰 값; 전체 vitest 1회 93초 포함)

## 변경 파일
- web/frontend/src/i18n/ko.ts: 새 키 `execGate`(title, ab, phrase(p), ready) 추가만 (기존 키 변경 없음)
- web/frontend/src/pages/BatchDetailPage.tsx: 버튼 바로 아래 `#exec-gate`(aria-live=polite) 추가, 버튼 aria-describedby="exec-gate", A/B 체크에 id/name. 기존 활성 조건/로직 불변. 기존 #ab-needed 안내도 그대로 둠(wfx 시험이 의존).
- web/frontend/src/pages/VideosPage.tsx: 머리글 전체선택·행 체크박스 id/name
- web/frontend/src/pages/BatchesPage.tsx: 머리글 전체선택·행 체크박스 id/name
- web/frontend/src/components/Pagination.tsx: 쪽 크기 select 에 useId 기반 id + name
- 안내 문구 동작: 꺼져 있을 때 "아직 필요한 것" 목록에 미충족 항목만(① A/B 확인란, ② 확인 문구 '<필요 문구>' — 데모 `실행 N건`/실제 `실제 실행 N건`은 서버가 준 expected 그대로). 충족 항목은 목록에서 사라지고, 모두 충족하면 "필요한 조건을 모두 채웠습니다. [실행]을 누를 수 있습니다."

## 새 시험
- src/pages/batchdetail.execgate.test.tsx (4건): 데모 문구/버튼 아래 위치·aria 연결, 충족 시 항목 소멸, 실제 모드 문구 '실제 실행 2건', 문구만 맞고 A/B 없으면 A/B 만 남음
- src/pages/formids.test.tsx (4건): 영상 목록, 배치 목록, 배치 상세, 이력·리포트·설정 화면에서 input/select/textarea 의 id 또는 name 누락 0건 + id 중복 0건

## 수정 전 첫 실행 (그대로)
- execgate 4/4 실패 (#exec-gate 없음, 버튼 접근성 설명 비어 있음)
- formids 4건 중 3건 실패 (영상 목록·배치 목록·배치 상세에 id/name 없는 체크박스/select), 이력·리포트·설정 1건 통과(Field 가 id 를 주입)

## 수정 후
- 새 시험 8/8 통과, 기존 batches.test·wfx.test 통과(기대값 수정 없음)
- `npx tsc -b --noEmit` 오류 0, `npx eslint .` 오류 0
- 전체 `npx vitest run`: 747 통과, 3 실패, 21 skip. 실패 3건은 모두 src/pages/ai.aibadge.test.tsx (다른 에이전트가 작성 중인 미추적 파일 + HomePage/SuggestionCard 진행 중 수정). 내 변경과 무관, 건드리지 않음.

## SuggestionCard.tsx / VideoDetailPage.tsx (편집 안 함, 목록만)
- SuggestionCard.tsx: `<input type="checkbox" ... ack>` (약 314행)는 id/name 없음. 약 268행·324행 input 은 Field 안이라 id 자동 주입(Field 가 id 부여). VideoDetailPage.tsx 는 input 없음.
  이 체크박스는 formids 시험이 다루는 화면(영상 상세/제안 카드)에 포함하지 못했음 -> 해당 에이전트가 id/name 추가 필요.

## 한계
- 실제 브라우저(F12 이슈 탭, 화면 육안)로 확인하지 못함. jsdom 시험만.
- 홈 화면·영상 상세·제안 카드 안의 입력칸은 점검 시험에서 제외.
- 접근성 설명이 실제 스크린리더에서 읽히는지는 미확인.
