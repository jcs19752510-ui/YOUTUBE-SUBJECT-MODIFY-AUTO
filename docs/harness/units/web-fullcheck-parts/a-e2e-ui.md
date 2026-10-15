# a-e2e-ui: 데모 E2E + 화면 + F12 이슈 + axe + 키보드 (2026-10-13, 소스 수정 없음)
시작 01:43:25 UTC, 종료 01:49:32 UTC (약 6분, `date -u` 실측).

## 환경·명령·소요
- dockerd 수동 기동 후 `web/tests_integration/tools/mkimages.sh $PWD .harness-tmp/full harness-tmp-full "db api web"` (프록시 CA 주입 사본, 저장소 Dockerfile 미수정). 이미지 3종 빌드 01:43:49~01:45:11 (약 82초, 최신 코드).
- 스택: `mkstack.sh web .harness-tmp/full/stack 18080` + override.yaml(nginx Host 허용 사본·ALLOWED_HOSTS에 18080 추가). `docker compose -p harness-tmp-full ... up -d` 01:45:15~01:45:32 (17초). 호스트 포트 18080만.
- 시험 코드(신규): `web/tests_fullcheck/a/ui_check.mjs`. 기존 `web/tests_integration/tools/e2e_functional.mjs` 그대로 재사용(E2E_BASE=http://127.0.0.1:18080).
- 단계 소요: 빈 화면 시험 9초, E2E 30초(01:45:49~01:46:19), 화면·axe·키보드 시험 약 22초, 스택 초기화 후 빈 화면 재실행 11초.
- 증거: `.harness-tmp/results/a-e2e/`(TC 캡처·run1.log), `.harness-tmp/results/a-screens/`(S* 캡처, *-result.json, keyboard.json).

## 1. 데모 E2E (첫 실행 결과 그대로, 19/21 통과)
TC-E01~E07, E09~E19, E21 통과. 불합격 2건:
- TC-E08 (민감 문구 차단): "수정 후 검증 결과 예상 block / 실제 pass". 캡처 TC-E08.png 를 보면 화면의 수정된 카드는 "차단·승인 비활성·승인할 수 없는 이유"가 정상 표시됨. 시험 스크립트가 서버 목록의 마지막 제안(sugIds 끝)을 조회하는데 화면에서 수정한 카드와 다른 제안이었을 가능성이 큼(원인 확정은 안 함, 미재현 확인 안 함). 제품 결함으로는 판단하지 않았으나 **시험 코드 기대/조회 대상 불일치로 재확인 필요**. 기대값을 고쳐 통과시키지 않음.
- TC-E20 (보안): "apiRequestContext.get: socket hang up". 잘못된 Host 요청을 nginx 가 444(연결 종료)로 거부한 것으로 보이며(nginx.conf `return 444`) 시험 스크립트가 예외를 거부로 처리하지 않음. 이번에 보안 항목(세션 없음 401, /docs, CSRF)은 이 시험으로 확인되지 않았음 = **미확인**. 과거 결과서(web-m1-e2e-after-fix)에는 "잘못된 Host 403"으로 기록됨 — 이번 구성에서는 다름(18080 시험 구성 영향 가능).
- 재실행 안 함(상한 시간 내 범위 외).

## 2. 화면 판정
| ID | 화면 | 기대 | 실제 | 캡처(.harness-tmp/results/a-screens/) |
|---|---|---|---|---|
| S01 | 홈(영상 0) | "아직 영상이 없습니다. 데모 영상 200개를 불러와 시작하세요." + [데모 영상 불러오기] | PASS | empty-S01.png |
| S02 | 영상 목록 빈 화면 | "아직 영상이 없습니다" + 홈 안내 본문 | PASS | empty-S02.png |
| S03 | 홈 푸터 | 첫 실행: 푸터에 "건강·금융 주의" 있음 기대 → **FAIL**(`empty-run1-result.json`). 푸터는 면책+AI 고지 두 줄만 있고 건강·금융 주의는 영상 상세·배치 상세 본문에 있음(설계). 이는 내 기대 가정 오류. 정정 기대(푸터 면책+AI 고지)로 재실행 PASS | PASS(재실행) | empty-S03.png |
| S10 | 제안 카드 종류 | "연습용 모의 제안(데모)" | PASS | full-S10.png |
| S11 | 영상 상세 면책·AI·건강금융 | 면책, "AI가 생성한 제안", "AI 제안은 ... 건강·금융 내용은" | PASS | full-S11.png |
| S12 | 영상 목록(데이터) | 행 존재+푸터 | PASS(50행) | full-S12.png |
| S13 | 홈 안내 | "오늘 할 일"+검토 안내+푸터 | PASS | full-S13.png |
| S20 | 배치 상세 실행 버튼 아래 | 버튼 비활성 + "아직 필요한 것" + A/B 안내 | PASS | full-S20.png |
| S21 | 조건 충족 | "필요한 조건을 모두 채웠습니다", 실행 활성, AI 한계 문구 | PASS | full-S21.png |
| S30/S31 | 이력/리포트 | AI 고지/면책 | PASS | full-S30.png, full-S31.png |
- 확인 못 한 것: 확인 문구가 틀렸을 때 "아직 필요한 것"의 확인 문구 항목 표시(문구를 먼저 입력해 A/B 항목만 확인함). 제안 종류가 규칙 기반/Gemini/직접 고침인 경우의 표시(데모 모의만 확인).

## 3. F12 이슈·콘솔·CSP (CDP Audits.enable)
- 수집 단계: 빈 화면(홈·영상 목록·푸터), 전체 흐름(영상 상세·목록·홈·승인·배치·이력·리포트·설정).
- 결과: 이슈 0건, 콘솔 오류 0건, CSP 위반 0건(재실행 기준). "A form field element should have an id or name attribute" 는 이번에 **나오지 않음**(CLAUDE.md 기록 Low 항목이 수정됐거나 이 화면 경로에서 미발생; 영상 목록 필터 입력칸은 S12에서 열렸음).
- 첫 실행의 CSP 이슈 2건은 내 시험이 axe 를 addScriptTag(인라인)로 넣어 생긴 시험 도구 영향이라 axe 주입을 CDP evaluate 로 바꿨다(`empty-run1-result.json` 에 보존). 제품 위반 아님.

## 4. axe-core 4.10.2 (위반만)
홈(빈), 영상 목록(빈), 영상 상세, 영상 목록, 홈, 배치 상세(실행 전), 배치 목록, 배치 상세(완료), 이력·롤백, 성과 리포트, 설정 모두 **위반 0건**. (자동 검사로 잡히지 않는 대비·초점 순서 등은 수동 확인 안 함. 모달 열린 상태는 axe 미실행.)

## 5. 키보드 전용 흐름 (Tab·Enter·Space, `keyboard.json`)
K1 제안 카드 [승인] 도달, K2 Enter 로 창 열림, K3 승인자 입력, K4 창 [승인] Enter→"승인했습니다", K5 승인 항목 체크(Space), K6 [사전 점검 만들기] Enter, K7 확인 문구 입력, K8 A/B 확인란 Space, K9 [실행] Enter→"이 배치는 끝났습니다": **9/9 PASS**. 

## 6. 결함·확인 필요
- 제품 결함 확정: 없음.
- 확인 필요: TC-E08(위 설명), TC-E20(시험 구성 대 444 응답). 둘 다 시험 코드 쪽 가능성이 높으나 확정 안 함.

## 7. 미수행
Windows/Edge 실기, 휴대폰 폭(미지원 확정), 실제 구글·실제 제목 변경, 모달 안 axe, 이미지 취약점 스캔.

## 8. 정리(규칙 K)
compose down -v, 이미지 3종 삭제, builder prune, 컨테이너 0, dockerd 종료. `.harness-tmp/full/`(빌드 사본·시험 비밀 파일, .gitignore 대상)은 남아 있음.
