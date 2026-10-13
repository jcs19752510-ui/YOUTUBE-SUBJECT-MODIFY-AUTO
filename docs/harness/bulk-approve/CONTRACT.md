# 일괄 승인(N건) 계약서 — 백엔드·프런트 공통 (2026-10-13, 선생님 결정 4건 반영)

선생님 결정: ①체크박스 선택 + 영상 ID 붙여넣기 **둘 다** ②한 영상에 후보가 여러 개면 **선택 화면** ③**최대 50건** ④승인과 배치 실행은 **분리**(승인 후 배치 만들기·실행은 지금 화면 그대로, 확인 문구 단계 유지).
원칙: 검증 강도를 낮추지 않는다. 일괄 승인 = 기존 `approve()`(재검증·서명·감사)를 **건마다 그대로** 호출. 실제 제목 변경·배치 실행·구글 호출은 이 기능에 없다.

## API (기존 규약: /api/v1, 세션 필요, 쓰기는 CSRF 필요, 오류는 ProblemError 한국어 메시지)

### 1) POST /api/v1/suggestions/resolve-videos  (읽기 전용, 상태 변경 없음, 세션 필요, CSRF 필요)
요청 `{ "video_ids": ["<11자 영상 ID>", ...] }` — 1~50개, 각 VIDEO_ID_PATTERN, 중복은 서버가 제거(순서 유지).
응답 200 `{ "items": [ResolvedVideo...] }` 입력 순서대로:
```
ResolvedVideo = {
  "video_id": str,
  "found": bool,                 // videos 테이블에 있는가
  "video_title": str|null,       // found일 때 현재 제목
  "excluded_reasons": [str],     // 제외 대상이면 사유(없으면 [])
  "candidates": [SuggestionOut]  // status in (candidate, expired, approved)인 제안, 최신순. found=false면 []
}
```
SuggestionOut은 기존 `suggestion_dict` 형태 그대로. 51개 이상이면 422 `bulk_too_many`.

### 2) POST /api/v1/suggestions/approve-batch  (CSRF 필요)
요청:
```
{ "approver": str(1..200, 기존 ApproveIn과 같은 규칙),
  "suggestion_ids": [int ...]            // 1~50개
  "acknowledged_warning_ids": [int ...]  // 경고(warn) 판정 제안 중 사용자가 확인 체크한 id. 기본 []
}
```
응답 200:
```
{ "approved": [ {"suggestion_id": int, "video_id": str} ... ],
  "skipped":  [ {"suggestion_id": int, "video_id": str|null, "code": str, "reason": str} ... ],
  "counts": {"requested": int, "approved": int, "skipped": int} }
```
- 51개 이상 → 422 `bulk_too_many`("한 번에 최대 50건까지 승인할 수 있습니다"), 빈 목록 → 422 `bulk_empty`, 같은 id 중복 → 422 `duplicate_suggestion`.
- 건별 처리: 각 id를 **SAVEPOINT(begin_nested)** 안에서 기존 `approve()`로 처리. `ProblemError`가 나면 그 건만 롤백하고 `skipped`에 `{code: 오류 코드, reason: 한국어 제목+detail}`로 기록(예: suggestion_blocked, video_excluded, same_as_current, suggestion_state, video_inconsistent). 존재하지 않는 id는 code `suggestion_not_found`. 예상 못 한 예외는 전체를 실패(500)시키고 부분 커밋 없음.
- 같은 영상의 제안이 요청에 둘 이상이면 **첫 번째만** 처리하고 나머지는 skipped code `duplicate_video_in_request`.
- 경고 서버 강제(프런트 우회 방지): `approve()`에 키워드 `ack_warning: bool | None = None` 추가. None(기존 단건 경로)이면 동작 완전 동일. False이면 **재검증 후** 판정이 warn이고 확인 목록에 없으면 ProblemError(409, `warning_not_acknowledged`, "경고가 있는 제안은 확인 체크 후에만 승인할 수 있습니다")로 거부(승인·서명 생성 전에). 일괄 경로는 id가 `acknowledged_warning_ids`에 있으면 True, 없으면 False를 넘긴다.
- 감사: 건별 `suggestion.approve`(기존) + 요약 1건 `suggestion.approve_batch` {requested, approved, skipped}. 승인자 이름·id만 기록, 제목 전문 불필요.
- 승인 유효 시간(기본 1시간)은 기존 정책 그대로(변경 없음).
- 중복 클릭 대비: 기존 Idempotency-Key 규약(`idempotent()`)을 `approve-batch`에도 적용(배치 생성 라우터와 같은 방식).

## 화면 (프런트)
새 페이지 `일괄 승인`(경로 `#/bulk-approve`, 상단 메뉴 추가). 비개발자 선생님이 이해·조작할 수 있어야 한다(못 하면 제품 결함).
1. **방법 A — 목록에서 고르기**: 상태 candidate/expired 제안 표(영상 제목·ID, 새 제목, 판정 pass/warn/block, 글자 수), 체크박스(차단 건은 비활성+사유), "전체 선택(현재 페이지)", 선택 N/50 표시, 50 초과 선택 불가 안내.
2. **방법 B — 영상 ID 붙여넣기**: 줄바꿈·쉼표·공백 구분 입력, "찾기" → resolve-videos. 결과 표: 못 찾은 ID(없음)·제외 대상·후보 0개는 따로 표시하고 승인 대상에서 제외. 후보가 2개 이상인 영상은 **라디오로 하나 선택해야** 선택 목록에 들어감(자동 선택 금지, 선택 전에는 "선택 필요" 표시). 후보가 1개면 그 하나가 미리 선택되되 확인 창에서 다시 보여준다.
3. 두 방법의 선택은 하나의 "승인 대기 목록"(최대 50)으로 합쳐 보여준다(같은 영상은 하나만).
4. **확인 창**: 승인자 이름 입력(기존 훅 `useApproverName`), N건 표(영상 ID·현재 제목→새 제목), 경고 건은 **건별 확인 체크** 필수(전체 체크 버튼 없음), 조건 미충족이면 버튼 옆에 남은 조건을 글로 표시(버튼 비활성 사유 미표시는 기존 결함이었음). 문구에 "이 단계는 승인만 합니다. 제목은 아직 바뀌지 않습니다. 바꾸려면 배치를 만들어 실행하세요"를 명시.
5. **결과 패널**: 승인 N건 / 제외 M건 + 제외 사유 표(한국어), "배치 만들기로 이동" 링크(기존 배치 화면). 모드(데모/실제) 배지는 기존 규약 유지.
6. 접근성: 표 캡션, 체크박스 라벨, 라이브 영역, 키보드 조작, 1024px 이상만 지원(좁은 화면은 미지원 확정).

## 비범위
배치 생성·실행 자동 연결(분리 확정), 승인 유효 시간 변경, DB 구조 변경(없음), 구글/실제 모드 변경.
