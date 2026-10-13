# f-e2e-rerun: TC-E08 / TC-E20 단독 재실행 (2026-10-13, 소스 수정 없음)
시작 01:50:24 UTC, 종료 약 01:59 UTC (`date -u`, 약 9분).

## 한 줄 결론
**두 시험의 재실행은 못 했다(미수행).** 이미지 db·api 빌드가 Docker Hub 429(Too Many Requests: 기본 이미지 postgres·python 의 매니페스트 조회)로 약 8분간 반복 실패해 스택을 올릴 수 없었다. web 이미지만 빌드됐다. 대신 nginx 설정 분석과 web 이미지 단독 실행으로 TC-E20 의 원인(444 설계)은 근거를 얻었고, 단독 재실행용 시험 코드는 작성해 두었다(미실행).

## 명령·소요
- dockerd 기동(UP 확인), `mkimages.sh $PWD .harness-tmp/full harness-tmp-full "db api web"` 첫 시도 01:50:39 실패(429). 이후 db/api 를 따로·반복(약 12회, 20~90초 간격) 시도: 전부 `HEAD https://registry-1.docker.io/v2/library/{postgres,python}/manifests/... 429`. web 만 `built harness-tmp-full-web:local` 성공.
- 이미지는 a 가 정리해 캐시가 없어 기본 이미지를 다시 받아야 했고, 429 가 풀리지 않았다 = 환경(Docker Hub 익명 한도) 문제.

## TC-E20 (보안) 분석 (확인한 것)
- 설정: `web/docker/nginx/nginx.conf` 54~60행 — `map $http_host` 허용 `127.0.0.1:8080`·`localhost:8080` 외 `if ($ytweb_host_ok = 0) { return 444; }`(응답 없이 연결 종료).
- 설계 문서가 같은 동작을 명시: `docs/yt/API.md:23`("nginx 단계에서는 응답 없이 연결 종료 444"), `docs/yt/threat_model.md` TW-02, `docs/yt/02_risk_assessment.md` RISK-018, `docs/yt/02_planning.md:228`. 즉 **설정 = 설계 의도**.
- 실측(web 이미지 + 저장소 nginx.conf 단독 실행, 호스트 포트 18081, 이후 삭제): Host `127.0.0.1:8080` → 200, Host `evil.example` → curl 000(연결 종료), nginx 로그 `status":444`. 허용 목록에 없는 `127.0.0.1:18081` 도 444.
- 시험 기대 비교: 시험 코드(`web/tests_integration/tools/e2e_functional.mjs` TC-E20)는 `r2.status() >= 400` 을 기대하고 연결 종료 예외를 처리하지 않는다. 과거 결과서(`docs/harness/evidence/web-m1-e2e*/RESULT.md`)에는 "잘못된 Host 403"이 기록돼 있는데, 그 실행 환경의 nginx 가 Host 를 통과시켜 백엔드 403 이 나온 구성이었을 가능성이 있으나 **원인 확인하지 못함**(당시 구성 증거 없음).
- 판정(잠정): a 의 "socket hang up"은 **제품 결함이 아니라 시험 코드 결함**(444 설계의 정상 동작을 거부로 인정하지 않음). 단, 이 판정은 nginx 단독 실측 기반이며 전체 스택 재실행으로는 확인하지 못했다. 시험 코드 기대값을 낮춰 통과시킨 것이 아님: 원래 실패(a 보고서 TC-E20 줄)는 그대로 남기고, 새 시험(`web/tests_fullcheck/f/rerun_e08_e20.mjs`)이 "HTTP 4xx 또는 연결 종료"를 거부로 인정하는 근거는 위 설계 문서다.

## TC-E08 (민감 문구 차단) 분석
- 원 시험은 `sugIds[sugIds.length-1]`(서버 목록 마지막 id)를 조회하고, 화면에서는 `article...last()`(화면 순서 마지막 카드)를 수정한다. 화면 정렬과 id 순서가 다르면 서로 다른 제안을 보게 된다. a 의 TC-E08 캡처에서 화면은 차단·승인 비활성이 정상이었다는 보고와 일치하는 **정황**이지만, **재현해서 확정하지는 못했다**(스택 없음).
- 신규 시험은 수정 저장 요청 URL 에서 실제 제안 id 를 뽑아 그 id 의 서버 검증 결과(block)·화면 [승인] 비활성·"승인할 수 없는 이유"·승인 API 거부(>=400)를 확인한다.
- 제품 결함 여부: 미판정(재실행 미수행). 서버가 정말 pass 를 내는 경우라면 제품 결함이므로, 재실행에서 `E08-server` 가 FAIL 이면 결함으로 기록해야 한다.

## 신규 시험 코드 (미실행)
`web/tests_fullcheck/f/rerun_e08_e20.mjs` (문법 검사 `node --check` 통과만 확인). 사용: `E2E_BASE=http://127.0.0.1:18080 OUT=<폴더> node rerun_e08_e20.mjs`. 포함 점검: E08 4건, E20 — 세션 없음 401, 잘못된 Host(4xx 또는 연결 종료 인정), /docs·/openapi.json·/api/docs·/api/openapi.json·/redoc 미노출(참고: 과거 결과서에 /docs 200 은 앱 index.html), Origin 만 있고 CSRF 토큰 없는 POST(익명·세션 있음), 잘못된 Origin + 토큰 POST.

## 세션·CSRF·/docs·/openapi.json 점검 결과
**미수행**(api 가 없어 확인 불가). 위 신규 시험이 처리한다.

## 정리(규칙 K)
컨테이너 0, 이미지 0(web 이미지 삭제), builder prune, dockerd 종료. `.harness-tmp/full/` 빌드 사본은 남음(.gitignore).

## 다음에 할 일 (한 줄)
429 가 풀린 뒤 a 보고서 명령으로 이미지 3종 빌드 → 스택 기동 → 신규 시험 1회 실행(약 2분). 또는 선생님 PC/다른 네트워크에서 Docker Hub 로그인 후 빌드.
