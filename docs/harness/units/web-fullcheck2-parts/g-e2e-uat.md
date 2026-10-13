# g-e2e-uat (2026-10-13, 소스 수정 없음, 시작 02:11:31 UTC, 종료 02:22:16 UTC = 약 10분45초)

## 한 줄 결론
데모 E2E 전체 2회와 UI 시험 2회를 실제 스택에서 실행했다. E2E 는 매번 19/21(TC-E08·E20 불합격), TC-E08·E20 은 시험 코드 오류를 고쳐 재실행하여 둘 다 합격 근거를 얻었다. UAT 는 U2(검색)만 불합격(원인 미확정), 접근성 모달 위반 0건, 보안 점검 이상 없음. 제품 결함 확정 1건(경미), 확인 필요 2건.

## 명령·소요 (date 실측)
- 02:11:31 dockerd 기동. 02:11:38~02:11:50 기본 이미지 4종 다이제스트 고정 이름 그대로 `docker pull` (12초): **Docker Hub 429 발생하지 않음**(재시도·mirror.gcr.io 불필요). 다이제스트는 FROM 과 동일하게 받았으므로 일치.
- 02:11:53~02:13:04 `web/tests_integration/tools/mkimages.sh $PWD .harness-tmp/g harness-tmp-g "db api web"` (프록시 CA 2줄 사본, 저장소 Dockerfile 미수정) 71초.
- `mkstack.sh web .harness-tmp/g/stack 18080` + override.yaml(api ALLOWED_HOSTS 에 18080 추가, nginx.conf 사본에 18080 Host 허용 추가). `docker compose -p harness-tmp-g up -d` ~02:13~02:15 (전 서비스 healthy).
- E2E 1회차 02:15:18~02:15:49 (31초), 2회차 ~02:16:16 (27초). 재실행 시험 ~2초. UI 시험(ui_check PHASE=full) 1회 약 40초, 2회 약 39초. UAT 21초.
- 호스트 포트 18080 만 사용.

## 1. E2E 결과 (첫 실행 결과 보존, 증거 `.harness-tmp/results/g-e2e1/`, `g-e2e2/`)
| 실행 | 결과 | 불합격 |
|---|---|---|
| 1회차(첫 실행) | 19/21 | TC-E08 "예상 block / 실제 pass", TC-E20 "socket hang up" |
| 2회차(연속) | 19/21 | 동일 2건 |
**연속 2회 깨끗하게는 달성하지 못함**(두 번 모두 2건 불합격, 같은 항목). 기대값은 고치지 않았다.
- UI 시험 `a/ui_check.mjs` PHASE=full: 1회 PASS 8 FAIL 0 / 2회 PASS 6 FAIL 0 (`g-ui1/`, `g-ui2/`; 2회차는 PASS 줄 수가 적은데 FAIL 0·이슈 0·콘솔 1·CSP 0 으로 끝남. 줄 수 차이 원인은 확인하지 않음, 미확정).

## 2. TC-E08·TC-E20 최종 판정 (`web/tests_fullcheck/f/rerun_e08_e20.mjs` 그대로 실행 → 시험 코드 오류)
- 그대로 실행 결과: E08 `Cannot read properties of undefined (reading 'id')` (시험 코드가 영상 목록 항목의 `.id` 를 읽음; 실제 필드는 `video_id`). 원 결과 보존: 위 한 줄.
- 시험 코드만 고친 사본 `web/tests_fullcheck/g/rerun_e08_e20_fix.mjs`(영상 ID 필드를 `video_id` 로, 로드 대기 추가, 이미 이전 시험이 같은 문구로 수정해 둔 카드가 아닌 [9]번째 영상 사용). 실행 결과(02:18):
  - **E08 합격 4/4**: 서버 검증결과 block(제안 9), 화면 [승인] 비활성, "승인할 수 없는 이유" 표시, 서버 승인 요청 409 거부. → 원 E2E 의 E08 불합격은 제품이 아닌 **시험 쪽 대상 불일치**(마지막 제안 id 와 화면에서 고친 카드가 다름)로 판단. 단 같은 카드를 같은 문구로 다시 수정하면 [저장]이 비활성(변경 없음)이 되는 현상을 관찰(U 참고, 안내 문구 확인 못 함).
  - **E20 합격 9/9**: 세션 없는 조회 401, 잘못된 Host 연결 종료(444, 설계: docs/yt/API.md:23), CSRF 없음 401, 세션 있고 토큰 없음 401, 잘못된 Origin 403, `/api/docs`·`/api/openapi.json` 404. (`/docs`·`/openapi.json` 은 200 text/html = SPA index.html 대체 응답, 아래 보안 표.)
- 원 E2E 의 E20 불합격은 연결 종료(444)를 거부로 인정하지 않은 시험 코드 문제.

## 3. UAT (Chromium, 1280px, 캡처 `.harness-tmp/results/g-screens/<ID>.png`, 데이터 `uat.json`)
| ID | 기대 | 실제 | 판정 |
|---|---|---|---|
| U1 | 홈에 다음 할 일 안내 | "오늘 할 일"·"검토하러 가기"·"배치 만들기"·오늘 반영 건수 표시 (이미 E2E 로 데모가 적재된 상태라 **처음 열기→데모 불러오기 흐름은 이번에 재현 안 함**, E2E TC-E02 가 이전에 담당) | 부분 PASS |
| U2 | 검색어 입력 시 목록이 줄어듦 | 검색칸에 "전기" 입력 1.5초 뒤 행 수 50→50 변화 없음. API 직접 호출 `q=전기` 는 필터 결과 반환 → 화면이 입력만으로 검색되는지(Enter/검색 버튼 필요 여부) **확인 못 함**. 비개발자가 입력 후 아무 반응이 없으면 결함 | **FAIL(원인 미확정, 결함 후보)** |
| U3a | AI 제안 생성 + 점수 | 제안 카드 생성됨, 화면에 "변경 전/후"·점수 영역 표시(점수 문구 추출은 부정확) | PASS |
| U3b | 이름 입력 후 승인 | "승인했습니다" | PASS |
| U4a | 승인한 것으로 배치 사전 점검 | 반영 대상 1건, 예상 52단위, 하루 상한 10건, 경고(A/B) | PASS |
| U4b | 실행 버튼이 꺼진 이유 안내 | 버튼 비활성 + "아직 필요한 것: A/B 테스트 확인…, 확인 문구: 입력칸에 '실행 1건'를 정확히 입력하세요" | PASS (CLAUDE.md 의 '이유 미표시' 항목이 수정된 상태) |
| U8b | 틀린 확인 문구 | 버튼 꺼짐, "확인 문구: 입력칸에 '실행 1건' 를 정확히…" 안내 | PASS |
| U4c | 맞는 문구로 실행→결과 | "성공 1, 이 배치는 끝났습니다. 이력에서 결과 보기" | PASS |
| U5 | 이력 | 반영·롤백 행, 승인자 "김선생", 결과 "성공" | PASS |
| U6 | 리포트 | 제목·CSV 내보내기 버튼 표시. 본문은 캡처 시점 "불러오는 중입니다" (**데이터 표시까지는 확인 못 함**) | 부분 PASS |
| U7 | 설정 | 탭 4개(안전 설정·PIN·세션·연결·감사 로그); 본문에서 "상한" 글자를 못 찾음(안전 설정 탭 내용은 이번에 열어 보지 않음) | 부분 PASS |
| U8a | 승인자 이름 비움 | [승인] 버튼 비활성(눌러서 오류를 보는 경로는 없음). 비어서 꺼진 이유가 화면에 있는지는 대화상자 문구 앞부분만 확인, **미확인** | 부분 PASS |
| U8c | 미승인 항목은 배치 후보에 없음 | 후보 0건 | PASS |
- 전문용어·오류 코드만 노출된 문구는 이번 경로에서 발견하지 못했다. 단 오류 패널 쪽(존재하지 않는 영상): "영상을 찾을 수 없습니다. 목록으로 돌아가 다른 영상을 선택해 주세요." 쉬운 말.
- 틀린 확인 문구를 눌러서 서버 오류를 내는 경로는 없다(버튼 잠금으로 선차단).

## 4. 접근성 모달 상태 (axe-core 설치본, Chromium)
| 상태 | 결과 |
|---|---|
| 승인 대화상자 열림 | axe 위반 0건. 열릴 때 포커스 INPUT(승인자 이름)으로 이동 |
| 제목 수정 대화상자 열림 | axe 위반 0건 |
| 토스트("제목을 수정했습니다") 표시 | axe 위반 0건 |
| 오류 패널(영상 없음) | axe 위반 0건 |
| Esc | 닫힘, 포커스가 [승인] 버튼으로 복귀 PASS (제목 수정 창의 포커스 복귀는 확인 안 함) |
| 포커스 트랩 | 수정 대화상자에서 Tab 14회 모두 대화상자 안 PASS |
미수행: 확인 대화상자(롤백) 열린 상태, 스크린리더 실기.

## 5. nginx·세션 수준 보안 (curl, 호스트 127.0.0.1:18080)
| 점검 | 실제 | 판정 |
|---|---|---|
| 잘못된 Host `evil.example` (`/`, `/api/v1/auth/me`) | 연결 종료(curl exit 52, 444 설계) | PASS |
| Origin 없는 POST(세션 있음, CSRF 토큰 없음) | 403 problem+json | PASS |
| 잘못된 Origin 으로 세션 만들기 | 403 | PASS |
| 세션 쿠키 | `ytw_session=…; HttpOnly; Max-Age=43200; Path=/api; SameSite=strict`. **Secure 없음** (http://127.0.0.1 평문이라 Secure 쿠키는 브라우저가 거부/미전송할 수 있어 설계상 불가, 루프백 한정 사유. 확인한 것은 속성 목록뿐) | PASS(사정 설명) |
| `/api/docs`, `/api/openapi.json` | 404 | PASS |
| `/docs`, `/openapi.json` | 200 text/html = SPA index.html(API 문서 아님, 본문 앞 120자 확인) | PASS |
| 보안 헤더(HTML) | CSP(default-src 'self', frame-ancestors 'none' 등), X-Content-Type-Options nosniff, X-Frame-Options DENY, Referrer-Policy same-origin, Permissions-Policy | PASS |
| 보안 헤더(API) | CSP default-src 'none', nosniff, DENY, Referrer-Policy, Cache-Control no-store | PASS |
| 메서드 | TRACE 405, DELETE /api/v1/videos 405, PUT / 403, OPTIONS 403 | PASS |
| 3MB 본문 POST | 413 | PASS |
| URL 20000자 / 쿼리 9000자 | 414 / 414 | PASS |
| 경로 이탈 `/../../etc/passwd`, `%2e%2e`, `/assets/../..` | 400 | PASS |
| `/api/v1/..%2f..%2fetc/passwd` | 200 text/html(SPA 대체 응답, 파일 내용 아님; 본문 확인은 생략) | PASS(잠정) |
| HTTP/1.0 (Host 포함) | 200 | PASS. Host 없는 HTTP/1.0 결과는 출력이 잘려 **확인 못 함** |
| HSTS | 없음(http 루프백이라 해당 없음) | 설명 |

## 6. 결함·확인 필요
1. (확인 필요, 결함 후보 Medium) U2 영상 검색: 화면에서 검색어 입력 후 1.5초 안에 목록이 변하지 않음. Enter/버튼 조작이 필요한지 확인하지 못함. 재현: 영상 목록 → 검색칸에 "전기" 입력 → 행 수 50 유지. 증거 `g-screens/U2.png`.
2. (경미, 확인 필요) 이미 같은 제목으로 수정된 제안을 같은 제목으로 다시 저장하려면 [저장]이 비활성인데 이유 문구를 확인하지 못함(`web/tests_fullcheck/g/dbg.mjs` 로 재현, 대화상자 문구에는 "(17/100)"만).
3. 원 E2E TC-E08/E20 불합격은 시험 코드 문제로 판단하나, 원본 `e2e_functional.mjs` 는 수정하지 않았으므로 **원본 E2E 는 계속 19/21**. 시험 코드 수리는 별도 필요.
4. 제품 결함 확정: 없음.

## 7. 호환성 한계
Chromium 한 가지(/opt/pw-browsers/chromium)만. Firefox·WebKit·Edge·Windows 실기 미수행(`playwright install` 금지). 휴대폰 폭은 미지원 확정.

## 8. 미수행과 사유
처음 열기→데모 불러오기 재현(스택 초기화 시간), U2 원인 규명, U6 데이터 표시·U7 안전 설정 탭 내용·U8a 이유 문구, 롤백 확인 대화상자 접근성, Host 없는 HTTP/1.0, 이미지 취약점 스캔, 실제 구글·실제 제목 변경. 12분 상한 때문.

## 9. 정리(규칙 K)
`docker compose down -v`, 이미지 3종 삭제, builder prune(1.7GB), 컨테이너 0·볼륨 0 확인, dockerd 종료 신호 전송. 기본 이미지 4종(다이제스트)은 dockerd 종료와 함께 남았을 수 있음(이미지 저장소 `/var/lib/docker`). `.harness-tmp/g/`(빌드 사본·시험 비밀 파일)는 .gitignore 대상으로 남아 있음.
신규 파일: `web/tests_fullcheck/g/{uat.mjs,rerun_e08_e20_fix.mjs,dbg.mjs}`, 증거 `.harness-tmp/results/g-*`.
