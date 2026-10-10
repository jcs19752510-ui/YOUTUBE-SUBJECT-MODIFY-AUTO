# 1단계 조사 조각 — 축 D: 로컬 웹앱 보안·프런트엔드·API 규약

- 조사 시점: 2026-10-10 (모든 "최신 버전"은 이 날짜의 레지스트리 조회값)
- 모드: 조각 모드(축 D만). 취합본 `01-trend-analysis.md`와 검증 로그는 쓰지 않았다.
- 입력으로 읽은 문서: `웹프로그램으로수정요청.md` 5~9장(전체), `docs/yt/threat_model.md`, `docs/harness/decisions.md` DEC-036/037(DEC-032~035 행은 긴 줄이라 grep 출력이 생략되어 본문을 읽지 못함 → [확인 필요]), `ORCHESTRATOR.md`는 헤딩 목록만 확인(1장 본문 미정독 → 취합 단계에서 규칙 B/J 준수 재확인 필요).
- 도구 제약(중요): 이 호출에는 Bash가 없어 `npm view` / `pip index versions` 를 **실행하지 못했다**. 대신 레지스트리 JSON API(`registry.npmjs.org/<pkg>/latest`, `pypi.org/pypi/<pkg>/json`)를 WebFetch로 직접 조회했다. WebFetch는 소형 모델이 응답을 요약해 돌려주므로 값은 **2차 요약**이다(원문 JSON 그대로가 아님). 설치는 하지 않았다.
- 비밀값은 쓰지 않았다.

## 0. 요약 5줄

1. 핵심 방어는 "동일 출처 단일 진입점(nginx) + Host 허용목록(nginx default_server와 FastAPI TrustedHostMiddleware 이중) + Sec-Fetch-Site=same-origin 강제(Origin 폴백) + 세션 결합 CSRF 토큰 + CORS 미사용"의 겹침 구조다. OWASP는 Fetch Metadata를 "primary signal"로, SameSite는 "defense-in-depth"로 분류한다(OWASP 원문 raw 열람).
2. Chrome은 2025-10-28(벤더 문서 기준, 141/142 출처 상충) 이후 공개 사이트 -> loopback 요청에 사용자 권한 프롬프트(LNA)를 붙였지만, Chrome 계열 한정이고 확장·다른 로컬 프로세스·다른 브라우저는 못 막는다. LNA를 방어선으로 세지 않는다.
3. 세션은 서버 측 불투명 세션(DB 저장, 토큰은 해시 저장) + 쿠키(HttpOnly, SameSite=Strict, Path=/)를 권장한다. `Secure`/`__Host-` 는 `http://127.0.0.1` 에서 브라우저별로 동작이 갈리고 **127.0.0.1 자체에 대한 근거를 찾지 못했다** -> 실측 필요.
4. 패키지 조회에서 **중요한 충돌**이 나왔다: `typescript` latest=7.0.2 인데 `openapi-typescript`(7.13.0)는 TS 7 비호환 이슈(#2841, 2026-07-09 개설, 열림 추정)가 있고 peer가 `typescript ^5.x`. TS는 5.x/6.x 로 고정해야 한다(정확한 안정 버전은 미조회). 또 vite 8.3.4 / vitest 5.0.3 는 Node 20.19+/22.12+ 를 요구한다.
5. 못 연 도메인이 많았다(developer.chrome.com, developer.mozilla.org, w3.org, ietf.org, rfc-editor.org, fastapi.tiangolo.com, nginx.org, law.go.kr). GitHub raw 미러로 OWASP·MDN·FastAPI·Starlette 원문 일부는 열람했다. 열람 못한 항목은 "[원문 미열람]"로 표시했다. KWCAG 의무 여부는 확정하지 못했다(법률 자문 아님).

---

## 1. 로컬 서버 공격 유형과 방어

열람 코드: 원문=원문 직접 열람 / 미러=GitHub raw 등 원문 미러 열람 / 검색=검색 요약만(원문 미열람) / 일반=이 세션에서 조회하지 않은 일반 지식(검증 필요).

| # | 사실 | 근거 URL / 조회 | 열람 | 확신도 | 시사점 |
|---|---|---|---|---|---|
| 1-1 | DNS 리바인딩의 서버측 주 방어는 Host 헤더 허용목록(localhost와 루프백 숫자 주소 + 포트만 허용). DNS 응답 필터링은 주방어로 쓰지 말라고 NCC Group이 명시(localhost CNAME 우회 사례). 서비스는 인증도 함께 걸 것을 권고 | https://github.com/nccgroup/singularity/wiki/Preventing-DNS-Rebinding-Attacks | 검색(위키 원문 미열람) [확인 필요: 원문 미열람] | 중 | nginx(`default_server`에서 허용 Host 외 444/403)와 FastAPI `TrustedHostMiddleware` 이중 적용. 허용 Host는 `127.0.0.1:<포트>`(+선택 `localhost:<포트>`). 인증을 Host 검증에 의존하지 않는다 |
| 1-2 | 2025~2026년 실제 사례: MCP TypeScript SDK 로컬 HTTP 서버가 DNS 리바인딩 보호 기본 꺼짐 -> 1.24.0에서 수정(GHSA-w48q-cv73-mx4w, 2025-12), Apollo MCP Server CVE-2026-35577 | https://github.com/modelcontextprotocol/typescript-sdk/security/advisories/GHSA-w48q-cv73-mx4w | 검색 | 중 | "로컬이니 괜찮다"는 가정이 실제 CVE로 반복됨. 위협 모델에 DNS 리바인딩을 명시 등록 |
| 1-3 | 로컬 개발 서버 CSRF/교차 출처 접근 CVE: Vite CVE-2025-24010(WebSocket Origin 미검증), NestJS devtools CVE-2025-54782(치명, 악성 사이트 방문만으로 RCE), webpack-dev-server CVE-2026-14620(무인증 GET 두 개가 상태 변경) | https://www.sentinelone.com/vulnerability-database/cve-2025-24010/ 외 (검색 결과 목록) | 검색 | 중 | 상태 변경 GET 금지(S-W03) 근거. WebSocket/SSE를 쓰면 Origin 검증을 별도로 해야 함(폴링 우선 권장과 일치) |
| 1-4 | OWASP: Fetch Metadata(`Sec-Fetch-Site`)를 CSRF의 "primary signal"로, Origin/Referer 검증은 **필수 폴백**("Missing headers and `Origin: null` are not evidence of a same-origin request"; `null` 허용 금지). SameSite는 "defense-in-depth ... does not replace a proper CSRF defense". 동기화 토큰은 쿠키로 전달하지 말 것. 서명형 이중 제출은 **세션에 바인딩된 HMAC**일 때만 의미 있음. 커스텀 헤더만으로는 CSRF 방어가 안 됨. 로그인 CSRF도 존재 | https://raw.githubusercontent.com/OWASP/CheatSheetSeries/master/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.md | 미러(원문 마크다운) | 높 | 권장: 상태 변경 요청은 (a) `Sec-Fetch-Site == same-origin` 아니면 403, (b) 헤더가 없으면 `Origin`이 허용 Origin과 정확히 일치해야 통과, (c) 세션 결합 CSRF 토큰(`X-CSRF-Token`) 검증. 로그인 엔드포인트도 동일 검사. cheatsheetseries.owasp.org 도메인은 열람 실패(미러로 대체) |
| 1-5 | Fetch Metadata 지원: 2023-03 이후 출시 브라우저 지원이라는 2차 글. `Sec-Fetch-Site` 값은 same-origin / same-site / cross-site / none | https://blog.miguelgrinberg.com/post/csrf-protection-without-tokens-or-hidden-form-fields | 검색 | 중 | 지원 브라우저를 "최신 Chrome/Edge"(F-10)로 한정했으므로 충분. **`same-site`도 거부**해야 함(같은 127.0.0.1의 다른 포트 서비스가 same-site로 분류됨 — 1-9 참고) |
| 1-6 | CORS 비허용 구조: Starlette `CORSMiddleware` 기본값은 제한적이고 `allow_private_network` 기본 False 이면 PNA 사전요청에 400 응답. `allow_origins=['*']`+자격증명 조합 불가 | https://raw.githubusercontent.com/encode/starlette/master/docs/middleware.md | 미러(원문) | 높 | **CORSMiddleware를 아예 설치하지 않는다**(동일 출처 프록시). 개발 모드(Vite dev server 포트가 다름)에서만 별도 프로필로 좁은 허용 — 운영 프로필에는 코드 경로 자체를 두지 않기(SEC 후보) |
| 1-7 | Chrome Local Network Access(LNA): 공개 웹사이트 -> 로컬/루프백 요청에 권한 프롬프트. 2025-06-09 Chrome 138 옵트인 시험, 2025-09 Intent to Ship 은 141, 3자 글은 142로 **버전 표기가 상충**. 벤더 지원문서는 2025-10-28 Chrome 142 안정 배포 + 127.0.0.0/8 포함. WebSocket/WebTransport/WebRTC는 당시 미적용. 거부 시 fetch는 네트워크 오류. 관리형 프로필은 `LocalNetworkAccessAllowedForUrls` 로 프롬프트 없이 허용 가능. PNA(사전요청 방식)를 대체 | https://developer.chrome.com/blog/local-network-access (도메인 열람 실패), 검색 요약 | 검색 [확인 필요: 원문 미열람] | 중 | 2차 방어일 뿐 — Chrome/Edge 한정, 비-Chromium·curl·로컬 프로세스·다른 로컬 서버·확장은 대상 아님. 사용자가 프롬프트를 "허용"해 버릴 수 있음. 설계는 LNA 없이도 안전해야 한다 |
| 1-8 | 브라우저 확장: 호스트 권한을 가진 확장은 CORS를 우회해 127.0.0.1에 요청 가능, 동일 출처 페이지의 DOM을 읽으면 CSRF 토큰도 읽음 | 근거 URL 없음(검색에서 확장 특화 자료를 못 찾음) | 미확인 | 낮(추정) | 완전 방어 불가. HttpOnly 쿠키+서버 측 세션이라도 확장이 페이지 컨텍스트에서 API를 호출할 수 있음. 위협 모델 T-01 계열 "같은 PC의 악성 코드/확장"으로 분류해 수용 여부를 사용자에게 묻고(규칙 A), 완화로 "쓰기 반영은 확인 문구 직접 입력 + 쓰기 재로그인" 유지 |
| 1-9 | 쿠키는 **포트로 격리되지 않고**, SameSite 의 "site"는 포트를 구분하지 않는다(일반 지식). 즉 같은 PC의 다른 `127.0.0.1:<다른포트>` 서비스는 same-site 이고 쿠키를 공유 | RFC 6265bis 열람 실패(datatracker.ietf.org) | 일반 [확인 필요: 원문 미열람] | 중 | SameSite=Strict 만으로는 "다른 로컬 웹앱"을 못 막는다. `Sec-Fetch-Site` 를 same-origin 만 허용(same-site 거부) + CSRF 토큰 + 세션 쿠키 이름을 앱 고유로 + 가능하면 포트를 비표준으로 |
| 1-10 | `Host: localhost` 와 `127.0.0.1` 은 쿠키 도메인이 서로 다른 호스트 | https://www.itechguides.com/?p=393234 계열(품질 낮음) | 검색(저품질) | 낮 | 접속 주소를 `http://127.0.0.1:<포트>` 하나로 문서화·고정하고 `localhost` 접속은 리다이렉트 또는 거부(혼용 시 쿠키·CSRF·OAuth 리디렉션 URI 불일치) |

## 2. 세션 설계

| # | 사실 | 근거 | 열람 | 확신도 | 시사점 |
|---|---|---|---|---|---|
| 2-1 | OWASP 세션 관리: 세션 ID 최소 64비트 엔트로피(자체 생성 시 128비트 이상 권장, 저장 검증값은 160비트 이상), 로그인 등 권한 변경 시 **세션 ID 재발급**(고정 공격 방지), 만료는 서버에서 강제. 유휴 만료 예: 고위험 2~5분 / 저위험 15~30분, 절대 만료 예: 종일 업무 앱 4~8시간. 저장 시 무작위 검증값의 **단방향 해시 저장**(저장소 읽기 유출 대비). JWT/리프레시를 localStorage/sessionStorage에 두지 말 것(XSS로 읽힘). `__Host-` 접두사 권장 | https://raw.githubusercontent.com/OWASP/CheatSheetSeries/master/cheatsheets/Session_Management_Cheat_Sheet.md | 미러(원문) | 높 | 권장 설계값(제안, 사용자 확인 필요): 256비트 CSPRNG 토큰, DB에 SHA-256 해시 저장, 로그인 성공 시 새 토큰 발급·기존 폐기, 유휴 30분(쓰기 화면은 더 짧게도 가능)·절대 8시간, 로그아웃 시 서버 삭제 |
| 2-2 | 서버 세션 vs JWT: 단일 사용자·단일 서버·즉시 폐기 필요(쓰기 권한 도구) 조건에서는 서버 세션이 단순하고 안전. JWT는 폐기·회전·저장 위치 문제가 생김. OWASP 세션 시트의 JWT 언급은 "스토리지 금지" 한 줄뿐 | 위 OWASP 세션 시트. JWT 전용 시트 URL(`JSON_Web_Token_for_Java_Cheat_Sheet.md`)은 404 | 미러(JWT 시트 열람 실패) | 중(근거는 간접, 결론은 일반 설계 판단) | **권장: 서버 측 세션 쿠키.** 이유: (a) 즉시 폐기, (b) 브라우저 JS가 토큰을 못 읽음, (c) 단일 사용자에 무상태 이점 없음, (d) 서명키 관리 불필요. JWT는 비권장 |
| 2-3 | `Secure` 속성: MDN은 "Insecure sites (http:) cannot set cookies with the Secure attribute" 이면서 "The https: requirements are ignored when the Secure attribute is set by localhost" 라고 서술 — **그러나 127.0.0.1 이 "localhost" 취급인지는 쓰여 있지 않음** | https://raw.githubusercontent.com/mdn/content/main/files/en-us/web/http/reference/headers/set-cookie/index.md | 미러(원문) | 높(문장 자체) / 127.0.0.1 적용은 낮 | `Secure` 지정 여부를 문서만으로 결정 못 함 -> 아래 2-5 실측 |
| 2-4 | 브라우저별 `http://localhost` 쿠키(httpwg 이슈 #2605 표): Chrome=Secure 수락, `__Host-`/`__Secure-` 거부 / Firefox=3종 모두 수락 / Safari=3종 모두 거부. 이 표는 `localhost`, localhost 서브도메인, "`http://127.0.1`"(오타로 보임)만 다루고 **127.0.0.1은 다루지 않음** | https://github.com/httpwg/http-extensions/issues/2605 | 원문(GitHub) | 높(표 내용) / 127.0.0.1 적용은 낮 | `__Host-` 접두사는 Chrome에서 http 로컬 환경에서 거부된다 -> **쿠키 이름에 `__Host-` 를 쓰지 않는다**(쓰면 Chrome에서 로그인이 안 될 수 있음). 지원 브라우저는 Chrome/Edge(F-10) |
| 2-5 | 127.0.0.1의 secure context 여부: W3C Secure Contexts 알고리즘은 호스트가 `127.0.0.0/8` 또는 `::1/128`에 매치되면 "Potentially Trustworthy", `localhost` 호스트명은 사용자 에이전트가 let-localhost-be-localhost 규칙을 따를 때만 | https://raw.githubusercontent.com/w3c/webappsec-secure-contexts/main/index.bs | 미러(스펙 소스) | 높 | **127.0.0.1 은 스펙상 secure context** (SubtleCrypto, Clipboard 등 사용 가능). 다만 "secure context" 와 "Secure 쿠키 수락" 은 별개 규칙 — Safari 사례(secure context 이나 Secure 쿠키 거부, WebKit bug 231035 검색 요약)가 증거 |
| 2-6 | 권장 쿠키 속성(제안): `Set-Cookie: ytsid=<토큰>; HttpOnly; SameSite=Strict; Path=/` (Domain 생략). `Secure` 는 **Chrome/Edge에서 127.0.0.1 로 실측해 수락되는 경우에만** 추가, 아니면 생략(트래픽이 같은 PC 루프백이므로 도청 위험 낮음 — 단 Docker Desktop 경유 구간 포함 여부는 [확인 필요]). Max-Age/Expires 생략(세션 쿠키), 만료는 서버가 강제 | 위 2-1~2-5의 종합 | 종합(제안) | 중 | 9단계 시험 항목으로 "Chrome/Edge 최신에서 127.0.0.1 로 Secure 쿠키 설정 후 다음 요청에 전송되는지" 실측을 등록. 결과를 설계서 ADR에 기록 |
| 2-7 | PIN 방식(Q-6): 공유 PC가 아니면 PIN 없이 세션 토큰만으로 충분할 수도 있으나, 세션을 누가 어떻게 발급받는가가 핵심 — 무인증 자동 발급은 "다른 사이트가 로그인 CSRF로 세션을 얻는" 문제 | OWASP CSRF 시트(로그인 CSRF 절) | 미러 | 중 | 권장: 최초 실행 시 `docker compose` 로그/콘솔에 1회용 접속 코드 또는 시작 스크립트가 PIN을 secrets 로 생성 -> 로그인 폼에 입력 -> 세션 발급. PIN 검증은 시도 횟수 제한(지연·잠금)과 상수 시간 비교. PIN 해시 알고리즘 후보(argon2 계열 등)는 **패키지 실존을 아직 조회하지 않음 [확인 필요]** |

## 3. nginx 보안 헤더·제한·비루트

| # | 사실 | 근거 | 열람 | 확신도 | 시사점 |
|---|---|---|---|---|---|
| 3-1 | OWASP 권장 헤더 값: `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: geolocation=(), camera=(), microphone=()`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`(CSP frame-ancestors 우선), COOP `same-origin`, CORP `same-site`, COEP `require-corp`, 민감 응답 `Cache-Control: no-store` | https://raw.githubusercontent.com/OWASP/CheatSheetSeries/master/cheatsheets/HTTP_Headers_Cheat_Sheet.md | 미러(원문) | 높 | 이 앱은 외부 링크·외부 리소스가 거의 없으므로 `Referrer-Policy: no-referrer` 가 더 엄격(제안). COEP `require-corp` 는 외부 이미지(유튜브 썸네일)와 충돌 가능 -> 보류. `/api/*` 는 `Cache-Control: no-store` |
| 3-2 | OWASP CSP: 현대 권장은 nonce/hash 기반 "Strict CSP". `object-src 'none'`, `base-uri 'none'`, `frame-ancestors` 는 `<meta>` 로는 무시되므로 **HTTP 헤더로** 설정, `form-action` 으로 폼 전송처 제한, 시험은 `Content-Security-Policy-Report-Only` | https://raw.githubusercontent.com/OWASP/CheatSheetSeries/master/cheatsheets/Content_Security_Policy_Cheat_Sheet.md | 미러(원문) | 높 | CSP는 반드시 nginx 응답 헤더로. 정적 SPA는 nonce를 서버 템플릿으로 넣기 어려우므로 "인라인 스크립트/스타일 없는 빌드 + `'self'` 만" 방식이 현실적 |
| 3-3 | Vite+React 엄격 CSP: Vite 코어는 nonce 자동 주입이 없고(`html.cspNonce` 는 플러그인 의존), 엄격 CSP의 걸림돌은 **인라인 모듈 스크립트와 런타임 `<style>` 주입(CSS-in-JS)**. 프로덕션은 `unsafe-eval` 불필요. "빌드된 `index.html` 을 직접 확인하라"가 결론 | 검색 요약(StackHawk 등 2차) | 검색 [확인 필요: 원문 미열람] | 중 | 제안 CSP(시작점, **Report-Only로 먼저 시험** — 실측 전에는 확정 아님): `default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; object-src 'none'`. CSS-in-JS 라이브러리·인라인 `style="..."` HTML 속성을 쓰지 않는 디자인 규칙을 FR/SEC에 반영. `style={{}}` 로 인한 CSSOM 설정은 허용되나 [확인 필요: 9단계 브라우저 실측] |
| 3-4 | **외부 이미지 충돌**: F-04(외부 CDN 금지)와 영상 썸네일(`i.ytimg.com` 등)이 충돌할 수 있음. 썸네일을 화면에 보이려면 `img-src` 예외 또는 api가 썸네일을 받아 같은 출처로 중계해야 함 | 요청서 8장 F-04 vs W-003 (사실 확인은 설계 몫) | 문서 | 높(충돌 자체) | 결정 필요: (a) 썸네일 미표시, (b) `img-src https://i.ytimg.com` 허용(예외 1개, 문서화), (c) api 프록시 캐시(SSRF·크기 상한 필요). 기본 권장 (a) 또는 (b). 사용자 확인 대상 |
| 3-5 | add_header 상속 규칙(하위 `location`에 `add_header`가 하나라도 있으면 상위 것이 무시됨), `always` 필요(4xx/5xx에도 헤더 부착) | 일반 지식 | 일반 [확인 필요: nginx.org 열람 실패] | 중 | 설정 테스트: 모든 location(정적, `/api`, 오류 페이지)에서 헤더 존재를 자동 검사(9단계) |
| 3-6 | 속도 제한 `limit_req_zone`/`limit_req`: 기본 burst=0, 초과분은 503(`limit_req_status` 로 429 변경 가능), `nodelay` 로 지연 방지. 같은 `location` 에서 `return 444` 와 `limit_req` 는 단계가 달라 제한이 적용되지 않음(2010 메일링 리스트, nginx 개발자 답변) -> **별도 location 으로 분리** | https://mailman.nginx.org/pipermail/nginx/2010-June/020974.html (검색 요약), nginx.org 문서는 열람 실패 | 검색 | 중 | 제안: 키를 `$binary_remote_addr` 로 두면 Docker Desktop 환경에서 모든 요청이 게이트웨이 IP로 보일 수 있어 사실상 전역 제한이 된다(추정, 실측 필요). 로컬 단일 사용자이므로 "전역 단일 존" 설계로 단순화. 로그인(`/api/v1/auth/login`)은 별도 더 엄격한 존 |
| 3-7 | 요청 크기 제한: `client_max_body_size` 를 location별로 설정(기본 1m) | 일반 지식 | 일반 [확인 필요: 원문 미열람] | 중 | 기본 1m, CSV 업로드 경로만 별도 상한(S-W10). FastAPI 쪽에도 본문 크기 상한(이중) |
| 3-8 | nginx 비루트: `nginxinc/nginx-unprivileged` 공식 프로젝트는 비루트 실행, 기본 포트 **8080**, PID `/tmp/nginx.pid`, temp 경로 `/tmp/`, `nginx.conf`의 `user` 지시어 제거. 이미지는 매주 월요일 밤 갱신 | https://github.com/nginxinc/docker-nginx-unprivileged | 검색 요약(리포 링크 기준; 원문 직접 열람 아님) | 중 | D-03(비루트, `read_only: true`)과 정합: `tmpfs: /tmp` 필요. 호스트 게시는 `127.0.0.1:<포트>:8080`. 다이제스트 고정(D-04). 이미지 실존·다이제스트는 **Docker Hub 조회가 이 축 범위 밖/미실시 [확인 필요]** |

## 4. FastAPI

| # | 사실 | 근거 | 열람 | 확신도 | 시사점 |
|---|---|---|---|---|---|
| 4-1 | Pydantic v2 입력 검증(최신 2.14.0, 2026-10-08, Python 3.10+). 필드 제약(`Field(max_length=...)`), `extra='forbid'` 로 미지의 필드 거부, 엄격 모드로 타입 강제 변환 억제를 권장(일반 지식) | https://pypi.org/project/pydantic/ , https://raw.githubusercontent.com/pydantic/pydantic/main/LICENSE (MIT) | 원문(프로젝트 페이지 일부) | 높(버전) / 중(설정 권장) | 모든 요청 모델 `extra='forbid'`, 문자열 길이·정규식(video_id) 제약, 응답도 모델로 고정(내부 필드 노출 방지) |
| 4-2 | RFC 9457(problem+json): FastAPI/Starlette 자체 기능은 없음(검색). 구현 방식 둘: (a) 직접 구현 — `RequestValidationError`, Starlette `HTTPException`, 일반 `Exception` 핸들러 3개를 등록해 `application/problem+json` 으로 응답. FastAPI 문서는 핸들러를 **Starlette의 HTTPException**에 등록하라고 안내 (b) `fastapi-problem` 0.12.1(Apache-2.0, 2026-02-10 업로드) 사용 | https://raw.githubusercontent.com/fastapi/fastapi/master/docs/en/docs/tutorial/handling-errors.md , https://pypi.org/pypi/fastapi-problem/json | 미러/원문. **RFC 9457 본문은 열람 실패(rfc-editor.org, datatracker.ietf.org) [원문 미열람]** | 중 | 권장 (a) 직접 구현(의존성 0, 한국어 메시지·조치 안내·상관 ID 필드를 확장 멤버로). 기본 422 본문(`detail` 배열의 `loc`/`msg`/`type`)은 입력값이 섞일 수 있어 그대로 노출하지 말고 필드명·사유만 변환. `Exception` 핸들러에서 스택트레이스·경로 제거(S-W09) |
| 4-3 | OpenAPI/문서 비활성: `docs_url=None`, `redoc_url=None`, `openapi_url=None`(이 경우 문서 UI도 함께 꺼짐) | https://raw.githubusercontent.com/fastapi/fastapi/master/docs/en/docs/tutorial/metadata.md | 미러(원문) | 높 | 권장: **운영 프로필에서 세 URL 모두 None**. 프런트 타입 생성은 빌드 시점에 `app.openapi()` 를 파일로 내보내 사용(런타임 엔드포인트 불필요). Swagger UI가 기본적으로 외부 CDN 자산을 불러오는지는 이 세션에서 확인 못 함 [확인 필요] — 개발 프로필에서만 켜고, 켜면 F-04/CSP와 충돌 가능성 |
| 4-4 | Host 검증: Starlette `TrustedHostMiddleware` — 요청의 Host가 허용목록과 다르면 **400**, IPv6는 `"[::1]"` 표기, `allow_hosts=["*"]` 는 무검증 | https://raw.githubusercontent.com/encode/starlette/master/docs/middleware.md | 미러(원문) | 높 | `allowed_hosts=["127.0.0.1", "localhost"]` 처럼 포트 없는 호스트명 기준인지 포트 포함 비교인지 동작 **9단계 시험 필요**(문서에 포트 취급 서술 없음). 컨테이너 간 내부 호출(`api:8000`)과 헬스체크 Host를 허용목록에 별도 반영해야 함 |
| 4-5 | Uvicorn 프록시 헤더: `X-Forwarded-*` 는 기본 무시. `--forwarded-allow-ips` 로 신뢰할 프록시 지정(`*` 는 "프록시만 접근 가능할 때"). `--proxy-headers`. Uvicorn `--workers` 는 spawn 방식. `FORWARDED_ALLOW_IPS` 기본값이 127.0.0.1 이라는 서술은 이 세션에서 문서로 확인 못함 | https://raw.githubusercontent.com/fastapi/fastapi/master/docs/en/docs/advanced/behind-a-proxy.md , https://raw.githubusercontent.com/encode/uvicorn/master/docs/deployment/index.md | 미러(원문), 기본값은 [확인 필요] | 중 | api는 내부 네트워크에만 있으므로 신뢰 대상은 web(nginx) 컨테이너 하나. 서브넷/고정 IP로 좁혀 지정하고 `*` 는 피한다(다른 컨테이너가 붙을 가능성 대비). 클라이언트 IP는 이 앱에서 보안 판단 기준이 아니므로(Docker Desktop 게이트웨이 IP) 로그용으로만 사용 |
| 4-6 | 속도 제한 라이브러리 실존(PyPI JSON 직접 조회): `slowapi` 0.1.10(MIT, 2026-06-13 업로드), `limits` 5.8.0(MIT), `fastapi-limiter` 0.2.0(Apache-2.0, 2026-02-06; 의존성 `fastapi`, `pyrate-limiter>=3.9.0`), `pyrate-limiter` 4.5.0(MIT). slowapi GitHub: 이슈 56/PR 65 열림, 엔드포인트에 `request: Request` 인자 필수, 저장소는 redis/memcached/memory, 웹소켓 미지원, "완전 비동기 전환 시 API 변경 가능" 고지, 최근 커밋 일자는 페이지에서 확인 못함 | https://pypi.org/pypi/slowapi/json , https://github.com/laurentS/slowapi | 원문 | 중 | 유지보수 상태는 "릴리스는 2026-06에도 있음" 까지만 확인(활발 여부 단정 불가). 권장: **1차 제한은 nginx `limit_req`**, 앱 레벨은 로그인 시도 제한 정도만 DB/메모리 기반 소형 자체 구현 또는 slowapi 메모리 백엔드. `fastapi-limiter` 는 Redis 전제로 보이므로(의존성은 pyrate-limiter, 백엔드 요구는 [확인 필요]) 이 프로젝트(Redis 도입 보류, R-4)와 맞지 않음 |
| 4-7 | 멱등성 키 패턴: 키 선점을 **원자적 `INSERT ... ON CONFLICT DO NOTHING RETURNING`** 한 번으로(검사 후 삽입 금지), 키 범위 복합 고유 제약(예: 범위+연산+키), `request_hash` 저장해 같은 키·다른 본문은 별도 오류 코드로 거절, 진행 중이면 409, 결과 응답은 **업무 변경과 같은 트랜잭션에서 커밋**, 5xx는 캐시하지 않고 키 삭제 후 재시도 허용, 시험은 동시 2요청. 이들은 블로그 수준 2차 자료이며 409 사용은 관례 | https://oneuptime.com/blog/post/2026-09-13-concurrent-idempotency-key-wait-replay-conflict/view 외(검색 목록). IETF `Idempotency-Key` 헤더 초안 원문은 URL 404로 열람 실패 | 검색 [원문 미열람] | 중 | `idempotency_keys(scope, key, request_hash, status, response, created_at)` 고유(scope,key). 만료 정책(예: 24~72시간) 설계서에서 결정. S-W12와 직결: 반영 작업은 `video_id` 단위 고유 제약/행 잠금도 별도로 건다(멱등 키만으로 동일 영상 이중 반영은 막지 못함) |
| 4-8 | 로그 마스킹: `logging.Filter` 로 비밀 패턴(`Authorization`, `Cookie`, `access_token`, `refresh_token`, `client_secret`, `Idempotency-Key` 원문, `Set-Cookie`) 마스킹, 요청 본문은 기본 미기록, 예외 로그의 `repr` 도 필터 통과. 기존 `logging_setup.py` 재사용 | `웹프로그램으로수정요청.md` 4-2(기존 모듈) | 문서 | 높(기존 자산) / 일반 | 로그 스캔 테스트(기존 K-6)를 웹 로그에도 확장. Uvicorn 접근 로그는 URL 쿼리에 토큰이 없도록 설계(OAuth `code`/`state` 쿼리는 콜백 경로 한정 마스킹) |
| 4-9 | 백그라운드 워커: 동일 이미지·다른 커맨드의 **별도 프로세스(컨테이너)**, DB 작업 테이블 + `SELECT ... FOR UPDATE SKIP LOCKED`(요청서 R-4). 하트비트·리스(lease) 만료로 죽은 작업 회수, SIGTERM 처리로 진행 중 반영을 안전 중단, 놓친 예약 몰아서 실행 금지(W-008) | `웹프로그램으로수정요청.md` R-4, W-008, D-08 | 문서 | 중 | FastAPI `BackgroundTasks` 는 api 프로세스 재시작 시 유실되므로 부적합(일반 지식). 사용량 예약과 상태 변경을 한 트랜잭션 경계로(S-W12) |

## 5. React / 프런트엔드

| # | 사실 | 근거 | 열람 | 확신도 | 시사점 |
|---|---|---|---|---|---|
| 5-1 | 현재 안정 버전(2026-10-10 조회): react 19.3.0, @tanstack/react-query 5.104.1, @tanstack/react-virtual 3.14.14, react-router-dom 7.18.4, @tanstack/react-router 1.170.42. 요청서 R-2 의 "React 18+" 는 19 도 포함 | 아래 6장 표 | 원문(레지스트리 JSON, 요약 경유) | 높 | Router는 요청서 확정안대로 react-router-dom 유지, TanStack Router는 대안으로만 기록 |
| 5-2 | XSS: React 는 기본 이스케이프. 위험 경로 = `dangerouslySetInnerHTML`, `href`/`src` 에 사용자·외부 문자열을 넣는 경우(`javascript:` URL), `target=_blank` 무 `rel`, 마크다운/HTML 렌더러 도입 | 일반 지식(이 세션에서 React 공식 문서 미열람) | 일반 [확인 필요: 원문 미열람] | 중 | ESLint 규칙으로 `react/no-danger` 금지, 링크 렌더 공통 컴포넌트에서 `new URL()` 로 스킴을 `https:`(및 앱 내부 상대경로)만 허용, 영상 ID로만 유튜브 URL을 자체 조립(외부 문자열 href 금지). AI 응답·설명은 텍스트 노드로만 |
| 5-3 | openapi-typescript 7.13.0(MIT, 설치 훅 없음)의 peer 는 `typescript ^5.x`. 저장소 이슈: #2841 "doesn't work with Typescript 7"(2026-07-09 개설, 열림으로 추정), PR #2818 TS6 지원(2026-05-22 개설), #2872 "TS 6 and 7 without runtime compiler dependency"(2026-09-12 개설) 모두 병합 표기 없음. 한편 `typescript` latest=7.0.2, rc=7.0.1-rc, beta=6.0.0-beta | https://github.com/openapi-ts/openapi-typescript/issues?q=TypeScript+7 , https://registry.npmjs.org/-/package/typescript/dist-tags | 원문(요약 경유; 이슈 상태는 "추정") | 중 | **상충 조사 결과: "최신 안정 TS를 쓰라"와 "계약 생성 도구가 TS 7 미지원"이 충돌.** 권장: TypeScript 를 5.x(openapi-typescript peer 범위 내)로 **고정**. 정확한 최신 5.x 안정 버전은 이 세션에서 조회 못 함 [확인 필요: `npm view typescript@5 version` 실행 필요] |
| 5-4 | 빌드 도구 Node 요구: vite 8.3.4 `node ^20.19.0 || >=22.12.0`; vitest 5.0.3 `node ^22.12.0 || ^24.0.0 || >=26.0.0`; eslint 10.12.0 `node ^20.19.0 || ^22.13.0 || >=24`; `@vitejs/plugin-react` 6.1.2 peer `vite ^8.0.0` | 6장 표 | 원문(요약 경유) | 높 | Dockerfile 의 Node 빌드 단계는 **Node 22.13+ 계열**(공통 충족)으로 고정. 이미지 다이제스트 고정은 별도 |
| 5-5 | TanStack Virtual 은 실존·활발(3.14.14, MIT, peer react 16.8~19). 200행 규모에서는 가상화 없이도 성능 문제가 작을 수 있으나 요청서 F-03 이 가상 스크롤을 요구. 가상 스크롤은 **접근성(스크린리더·행 개수 안내·키보드 이동)을 해칠 수 있음**(일반 지식) | 6장 표 | 원문(요약 경유) / 접근성 부분 일반 | 중 | 200행이면 서버 페이지네이션(예: 50행) + 가상화 불필요 대안을 설계서에서 비교하고 사용자 확인. 가상화 시 `aria-rowcount`/`aria-rowindex` 등 시험 필요 |
| 5-6 | 접근성 시험 도구: axe-core 4.14.0(**MPL-2.0**), jest-axe 11.0.0(MIT, 설치 훅 없음 — Jest 매처 용도), vitest-axe 0.1.0(MIT, peer vitest>=0.16, 마지막 갱신일 미확인), @testing-library/react 16.3.3(peer @testing-library/dom ^10, 10.4.2 확인) | 6장 표 | 원문(요약 경유) | 중 | 요청서는 `jest-axe` 지정이지만 러너가 **Vitest** 이므로 jest-axe 의 Jest 매처 호환 여부는 미확인 [확인 필요: 9단계 전 소형 시험]. 대안 = axe-core 직접 호출 + 자체 `expect` 확장. axe-core 는 개발 전용, MPL-2.0 파일 단위 카피레프트라 수정 배포하지 않으면 영향 작음(법률 자문 아님) |
| 5-7 | WCAG 2.2 AA 핵심(설계서 반영용 체크리스트): 키보드 전체 조작·키보드 트랩 없음(2.1.1/2.1.2), 포커스 가시성 및 **포커스가 가려지지 않음(2.4.11 AA 신규)**, 일반 텍스트 대비 4.5:1·큰 글자/UI 3:1(1.4.3/1.4.11), 색에만 의존 금지(1.4.1), **드래그 대체 수단(2.5.7 신규)**, **최소 타겟 크기 24x24 CSS px(2.5.8 신규)**, 상태 메시지(`aria-live`, 4.1.3), 오류 식별·제안(3.3.1/3.3.3), **중복 입력 방지(3.3.7 신규)** | W3C WCAG 2.2(이 세션에서 W3C 도메인 열람 실패; 성공기준 번호·내용은 일반 지식) | 일반 [확인 필요: 원문 미열람] | 중 | 표의 SC 번호는 W3C 원문 대조 후 확정. 위험 동작 확인 단계의 모달은 포커스 이동·복귀·ESC·`aria-modal` 시험 포함 |
| 5-8 | KWCAG: 검색에서 확인된 것은 (a) 장애인차별금지법 제21조·시행령 제14조에 근거해 웹 접근성 준수가 의무화되었다는 2차 자료, (b) 의무 대상 범위 서술이 자료마다 다름(공공기관·특수학교·종합병원·복지시설·근로자 300인 이상 사업장 등에서 시작해 5년 내 모든 법인까지 확대 vs 공공기관·30인 이상 사업장), (c) 한국 자료는 대부분 **KWCAG 2.0**이며 **KWCAG 2.2 실재는 검색으로 확인 못함** | 검색 요약(nepla.ai, dt.co.kr, peoplepower21.org 등 2차). 국가법령정보센터 열람 실패(law.go.kr) | 검색 [원문 미열람] | 낮 | **개인이 자기 PC에서만 쓰는 비공개 도구에 법적 의무가 있는지는 확정하지 못했다.** 제공 주체(개인/법인)·서비스 대상 범위가 쟁점일 것으로 보이나 이는 추정이며 법률 자문이 아님. 설계서에는 "법적 의무와 무관하게 WCAG 2.2 AA를 자발적 설계 목표로 둔다(F-09), 공개 배포로 바뀌면 재검토"로 쓰는 것이 안전 |
| 5-9 | 외부 CDN 금지 시 폰트: `@fontsource/noto-sans-kr` 5.3.0(OFL-1.1, 설치 훅 없음)으로 번들 자체 호스팅 가능. 한글 폰트는 파일이 크다(정확한 용량은 미조회). 대안 = 시스템 폰트 스택(`Malgun Gothic`, `Apple SD Gothic Neo`, `Noto Sans KR`, sans-serif)으로 0바이트 | https://registry.npmjs.org/@fontsource/noto-sans-kr/latest | 원문(요약 경유) | 중 | 권장: 기본은 시스템 폰트 스택(공급망·용량·CSP `font-src` 단순화), 디자인상 필요 시에만 fontsource 자체 호스팅(OFL-1.1 고지 포함). 사용자 취향 질문으로 4단계에서 확인 |

## 6. 공급망 및 패키지 실존·버전·라이선스 표

### 6-1. 확인 방법과 한계
- 사용한 방법: npm = `GET https://registry.npmjs.org/<pkg>/latest` (`npm view <pkg> version license` 와 같은 정보원), PyPI = `GET https://pypi.org/pypi/<pkg>/json`. WebFetch가 응답을 요약했고, 큰 응답(pydantic 등)은 절단되어 **pydantic은 프로젝트 페이지(2.14.0, 2026-10-08)와 LICENSE 원문(MIT)** 으로 대체 확인했다.
- 못 한 것: (1) `npm view`/`pip index versions`/`npm audit`/`pip-audit` **실행**(Bash 없음), (2) 취약점(CVE) 조회 — 이 표는 **실존·버전·라이선스·최상위 패키지의 설치 훅 유무만** 확인했고, **알려진 취약점 점검은 하지 않았다**, (3) 전이 의존성의 `postinstall` 점검, (4) Python 패키지의 설치 훅(sdist 빌드 스크립트) 점검.
- 이 표의 버전은 "조회 시점의 latest"이며, 이후 단계에서 잠금 파일로 고정한다.

### 6-2. npm 패키지 (조회: registry.npmjs.org, 2026-10-10)

| 패키지 | 실존 | latest | 라이선스 | 설치 훅(preinstall/install/postinstall) | 비고 |
|---|---|---|---|---|---|
| react | 예 | 19.3.0 | MIT | 없음 | |
| vite | 예 | 8.3.4 | MIT | 없음 | node ^20.19.0 \|\| >=22.12.0. dist-tags: previous=6.4.4 |
| typescript | 예 | **7.0.2** | Apache-2.0 | 없음(scripts 필드 없음) | **openapi-typescript 비호환 이슈 -> 5.x 고정 권장.** 5.x/6.x 안정 버전 번호 미조회 |
| @tanstack/react-query | 예 | 5.104.1 | MIT | 없음 | peer react ^18 \|\| ^19 |
| @tanstack/react-virtual | 예 | 3.14.14 | MIT | 없음 | |
| react-router-dom | 예 | 7.18.4 | MIT | 없음 | deprecated 표시 없음(조회상) |
| vitest | 예 | 5.0.3 | MIT | 없음 | node ^22.12 \|\| ^24 \|\| >=26 |
| @testing-library/react | 예 | 16.3.3 | MIT | 없음 | peer @testing-library/dom ^10 |
| @testing-library/dom (peer용) | 예 | 10.4.2 | MIT | (미확인) | |
| openapi-typescript | 예 | 7.13.0 (next=7.0.0-rc.1 은 구버전 태그) | MIT | 없음 | peer typescript ^5.x, TS7 이슈 |
| eslint | 예 | 10.12.0 | MIT | 없음 | node ^20.19.0 \|\| ^22.13.0 \|\| >=24 |
| prettier | 예 | 3.9.10 | MIT | 없음 | |
| axe-core | 예 | 4.14.0 | **MPL-2.0** | 없음 | 개발 전용 |
| jest-axe | 예 | 11.0.0 | MIT | 없음 | Jest 매처, Vitest 호환 미검증 |
| vitest-axe (대안) | 예 | 0.1.0 | MIT | 없음 | 갱신일 미확인, 오래됐을 가능성 |
| @vitejs/plugin-react (필요 시) | 예 | 6.1.2 | MIT | 없음 | peer vite ^8 |
| @tanstack/react-router (대안) | 예 | 1.170.42 | MIT | (미확인) | |
| @fontsource/noto-sans-kr (선택) | 예 | 5.3.0 | OFL-1.1 | 없음 | |

### 6-3. PyPI 패키지 (조회: pypi.org/pypi/<pkg>/json, 2026-10-10)

| 패키지 | 실존 | latest | 라이선스(license_expression) | requires_python | 비고 |
|---|---|---|---|---|---|
| fastapi | 예 | 0.143.0 | MIT | >=3.10 | yanked 아님. 0.x 대로 마이너마다 호환성 변경 가능 -> 고정 |
| uvicorn | 예 | 0.54.0 | BSD-3-Clause | >=3.10 | |
| starlette (fastapi 하위) | 예 | 1.7.0 | BSD-3-Clause | >=3.10 | 1.x 메이저 |
| pydantic | 예 | 2.14.0 (2026-10-08) | MIT (GitHub LICENSE 원문) | 3.10+ (프로젝트 페이지 서술) | JSON 응답 절단으로 requires_python은 페이지 서술 기준 |
| sqlalchemy | 예 | 2.1.4 | MIT | >=3.11 | 2.1 계열. Alembic 1.20.0과의 호환 표기는 미확인 [확인 필요] |
| alembic | 예 | 1.20.0 | MIT | >=3.10 | |
| psycopg | 예 | 3.3.6 | **LGPL-3.0-only** | >=3.10 | `psycopg-binary` 도 3.3.6, LGPL-3.0-only. 비수정 라이브러리로 사용·동적 링크 시 일반적으로 문제 적다고 알려져 있으나 **법률 자문 아님**, 공개 배포 시 재검토 |
| pip-audit | 예 | 2.10.1 | (license 필드 null, 확인 못함) [확인 필요] | >=3.10 | 검색 요약상 PyPI 권고 DB 기본, OSV 선택(`-s osv`), `--require-hashes` 지원 서술 |
| pytest | 예 | 9.1.1 | MIT | >=3.10 | |
| pytest-asyncio | 예 | 1.4.0 | Apache-2.0 | >=3.10 | |
| httpx | 예 | 0.28.1 | BSD-3-Clause | >=3.8 | |
| slowapi (후보) | 예 | 0.1.10 (2026-06-13) | MIT | <4.0,>=3.7 | |
| limits (slowapi 하위) | 예 | 5.8.0 | MIT | >=3.10 | |
| fastapi-limiter (후보) | 예 | 0.2.0 (2026-02-06) | Apache-2.0 | <4,>=3.9 | 의존성 fastapi, pyrate-limiter |
| pyrate-limiter | 예 | 4.5.0 | MIT | >=3.10 | |
| fastapi-problem (후보) | 예 | 0.12.1 (2026-02-10) | Apache-2.0 | >=3.10 | |

- 요청 후보 패키지 중 **존재하지 않거나 이름이 다른 것은 없었다**(위 표 전체 실존 확인). 단, `jest-axe`는 존재하지만 러너(Vitest) 호환이 미확인이고, `typescript`는 존재하나 최신판이 계약 생성 도구와 충돌한다.
- 요청서 4-1 의 Python "3.12 이상" 기준에서 위 requires_python(3.10~3.11) 은 모두 충족.

### 6-4. 공급망 운용(방법 · 근거 · 한계)

| # | 사실 | 근거 | 열람 | 확신도 | 시사점 |
|---|---|---|---|---|---|
| 6-a | npm 수명주기 스크립트는 대표적 공격 경로(Shai-Hulud 2025-09, 2차 2025-11-24 preinstall 은닉 등 사례). 권고: `.npmrc` 에 `ignore-scripts=true`, 필요한 패키지만 `npm rebuild <pkg>`. `npm ci` 는 **스크립트 실행을 막지 않으므로** `npm ci --ignore-scripts` 로 병용. 이견: Koi가 `--ignore-scripts` 우회("PackageGate")를 주장했으나 **검증 안 됨** | https://github.com/lirantal/npm-security-best-practices , https://snyk.io/articles/npm-security-best-practices-shai-hulud-attack/ , https://wellarchitected.github.com/library/application-security/recommendations/managing-dependency-threats/ | 검색 요약 | 중 | 요청서 S-W11 의 "postinstall 필요 시 사유 기록" 을 "기본 `ignore-scripts=true`, 예외는 사유 기록"으로 구체화. 최상위 18개 npm 패키지에서는 설치 훅이 확인되지 않았으나 **전이 의존성(예: 네이티브 바이너리 도구)은 미점검** |
| 6-b | 잠금 파일: `package-lock.json` 커밋 + CI/Docker 에서 `npm ci`(잠금 불일치 시 실패). 버전은 `^` 범위가 아니라 정확 고정(`save-exact`) 또는 잠금 파일에 무결성 해시. Python: 해시 고정 요구 파일 + `pip install --require-hashes` (pip-audit 문서가 `--require-hashes` 를 무결성상 선호한다고 서술) | 위 링크, https://pypi.org/project/pip-audit | 검색 | 중 | D-11 과 일치. 해시 요구 파일 생성 도구(pip-tools 등)는 이 세션에서 **미조회** [확인 필요] |
| 6-c | 취약점 점검: `npm audit`(npm 레지스트리 권고 DB), `pip-audit`(PyPA 권고 DB 기본, OSV 선택), OSV 데이터베이스. pip-audit 는 파이썬 패키지 자체에 포함되지 않은 "전이적" 취약점을 못 찾을 수 있다고 문서에 명시 | https://pypi.org/project/pip-audit | 검색 | 중 | 9단계에서 **실행**하고 결과(고/치명 0건 또는 수용 결정)를 보안 결과서에 첨부. 이번 조사에서는 실행하지 않았음 |
| 6-d | 공통: 존재하지 않는 패키지명 환각(slopsquatting) 방지를 위해 설치 전 레지스트리 실존·게시일·다운로드·저장소 링크 확인 필요 | 요청서 S-W11 | 문서 | 높 | 6-2/6-3 표가 1차 실존 증빙. 신규 의존성 추가 시마다 같은 방식으로 기록 |

## 7. 감사 로그 변조 방지

| # | 사실 | 근거 | 열람 | 확신도 | 시사점 |
|---|---|---|---|---|---|
| 7-1 | "UPDATE/DELETE 차단" 과 "변조 탐지" 는 다른 것. 해시 체인이 탐지를 제공하고 검증기는 처음 어긋나는 행을 보고. 트리거 기반 추가 전용은 테이블 소유자·슈퍼유저가 트리거 비활성화/교체, `TRUNCATE`, 테이블 변경/삭제, 물리 백업 편집으로 우회 가능. 행 수준 트리거는 `TRUNCATE`에 발동하지 않으므로 문(statement) 수준 트리거 또는 권한 회수 필요(검색 요약 중 일부 주장은 상충/미검증). 체인 머리 해시의 **외부 보관(앵커링)** 이 없으면 DB 전권자는 전체 재계산 가능 | https://appmaster.io/blog/tamper-evident-audit-trails-postgresql , https://repo.hex.pm/preview/audit_log/0.1.0/guides/limits.md 외 | 검색 [원문 미열람] | 중 | 설계 패턴(제안): `audit_log(id bigserial PK, occurred_at, actor, action, subject, payload jsonb, prev_hash bytea, row_hash bytea)`. 앱 계정에는 `INSERT`/`SELECT` 만 부여, `UPDATE`/`DELETE`/`TRUNCATE` 회수 + 문 수준 거부 트리거. `row_hash = HMAC-SHA256(키, prev_hash || 정규화된 payload)`로 하면 DB 내용만 입수한 공격자가 재계산하기 어려움(HMAC 키는 DB 밖 secrets) — 이 HMAC 사용은 이 조사의 설계 제안이며 출처가 있는 표준 패턴은 아님. 동시 INSERT 시 체인 분기 방지를 위해 직렬화(어드바이저리 락 또는 머리 행 `FOR UPDATE`) |
| 7-2 | 현실적 위협 수준: 로컬 단일 사용자 PC에서 DB 슈퍼유저/볼륨/호스트 파일 시스템을 가진 공격자는 이미 시스템 전체를 장악한 상태 -> 위협 모델 T-01/T-03/T-08 의 "같은 PC 악성코드" 범주와 동일하며 **완전 차단 불가**. 감사 로그의 실질 가치: (a) 앱 버그·SQL 실수로 인한 이력 훼손 탐지, (b) 사용자 본인이 나중에 "누가/언제 승인·반영했나" 재구성, (c) 웹 계층 침해(앱 계정만 탈취)에서의 흔적 보존 | `docs/yt/threat_model.md` 5장 + 위 7-1 | 문서/추정 | 중(추정 포함) | 문서에 "앱 계정 침해까지는 방어, DB 슈퍼유저·호스트 장악은 범위 밖(수용 사용자 확인 필요, 규칙 A)" 명시. 선택: `verify-audit` 명령으로 체인 검증 + 백업 시 머리 해시를 별도 파일/화면에 출력해 사용자가 보관(외부 앵커) |
| 7-3 | 보존과 삭제 충돌: 추가 전용은 정상 정리도 막으므로 보존 기간·정리 절차(유지보수 DDL, 체인 재앵커링)를 정의해야 함 | 위 7-1 검색 요약 | 검색 | 중 | W-016(백업·복원)과 연결: 복원 후 체인 검증을 완료 조건에 포함 |

---

## 8. SEC- / FR- 후보 (임시 ID — 2단계에서 정식 REQ-ID 로 재부여)

### 8-1. SEC 후보

| 임시 ID | 내용 | 근거 항목 |
|---|---|---|
| SEC-D01 | 모든 Host 는 허용목록 일치만 처리: nginx `default_server`(불일치 거부) + FastAPI `TrustedHostMiddleware` 이중. 허용 호스트는 `127.0.0.1:<포트>`(선택 `localhost`) | 1-1, 4-4 |
| SEC-D02 | 상태 변경(POST/PUT/PATCH/DELETE) 및 로그인은 `Sec-Fetch-Site == same-origin` 이 아니면 거부; 헤더 부재 시 `Origin` 정확 일치 필수; `Origin: null` 거부; `same-site` 거부 | 1-4, 1-5, 1-9 |
| SEC-D03 | 세션 결합 CSRF 토큰(`X-CSRF-Token`, HMAC 바인딩)을 모든 상태 변경 요청에 요구; GET/HEAD 는 상태 변경 금지 | 1-3, 1-4 |
| SEC-D04 | CORS 미들웨어 운영 프로필 미설치(동일 출처 전용); OPTIONS 사전요청 거부; 개발 프로필 허용은 코드·설정으로 분리 | 1-6 |
| SEC-D05 | 서버 측 세션: 256비트 CSPRNG 토큰, DB에는 해시만 저장, 로그인 시 재발급(고정 방지), 유휴·절대 만료 서버 강제, 로그아웃 시 폐기 | 2-1, 2-2 |
| SEC-D06 | 세션 쿠키 `HttpOnly; SameSite=Strict; Path=/`(Domain 없음, 접두사 `__Host-` 미사용), `Secure` 는 Chrome/Edge 127.0.0.1 실측 결과로 결정 | 2-3~2-6 |
| SEC-D07 | 로그인(PIN/접속 코드) 시도 제한·상수 시간 비교·실패 로그; 로그인 CSRF 방어 | 2-7 |
| SEC-D08 | nginx 보안 헤더 일괄(CSP Report-Only 시험 후 강제, `frame-ancestors 'none'`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, `/api` `no-store`) 및 모든 응답(오류 포함, `always`)에 부착 검증 | 3-1~3-5 |
| SEC-D09 | 인라인 스크립트·인라인 스타일 속성·CSS-in-JS 금지(CSP 호환 빌드 규칙); 외부 도메인 리소스는 설계서에 명시한 예외만 | 3-3, 3-4 |
| SEC-D10 | nginx `limit_req`(전역+로그인 별도 존, 429), `client_max_body_size`(기본 1m, CSV 경로 별도), FastAPI 본문 상한 이중 | 3-6, 3-7 |
| SEC-D11 | nginx 비루트 이미지, `read_only`, `tmpfs:/tmp`, 헬스체크 | 3-8 |
| SEC-D12 | 운영 프로필에서 `docs_url=redoc_url=openapi_url=None`; OpenAPI 는 빌드 시 파일 산출 | 4-3 |
| SEC-D13 | 모든 요청 모델 `extra='forbid'` 와 길이·형식 제약; 응답 모델 고정 | 4-1 |
| SEC-D14 | 오류는 RFC 9457 형식, 스택트레이스·경로·입력 원문·토큰 비노출, 상관 ID 제공 | 4-2 |
| SEC-D15 | Uvicorn `--proxy-headers` + `--forwarded-allow-ips` 를 nginx 컨테이너로 한정(`*` 금지) | 4-5 |
| SEC-D16 | 로그 마스킹 필터(Authorization, Cookie, Set-Cookie, 토큰류, Idempotency-Key, OAuth code/state) + 로그 스캔 시험 | 4-8 |
| SEC-D17 | React: `dangerouslySetInnerHTML` 금지 린트, 링크 공통 컴포넌트 스킴 허용목록, 외부 문자열은 텍스트 렌더링 | 5-2 |
| SEC-D18 | npm: `ignore-scripts=true` 기본 + 예외 사유 기록, `npm ci --ignore-scripts`, 정확 버전 고정, 잠금 파일 커밋; Python 해시 고정 설치; 9단계에서 `npm audit`·`pip-audit` 실행·보고 | 6-a~6-c |
| SEC-D19 | 신규 의존성마다 실존·라이선스·게시일 확인 기록(본 조각 6-2/6-3 형식) | 6-d |
| SEC-D20 | 감사 로그: 추가 전용 테이블 + 권한 회수 + 문 수준 거부 트리거 + 해시 체인(HMAC 키는 DB 밖) + 검증 명령 + 머리 해시 외부 보관 안내 | 7-1~7-3 |
| SEC-D21 | LNA/PNA 는 방어선으로 계산하지 않음(설계 원칙), 사용자 문서에 "브라우저의 로컬 네트워크 접근 허용 프롬프트가 뜨면 거부" 안내는 신뢰할 수 없는 출처 사이트에서만 유효함을 명시 | 1-7 |
| SEC-D22 | 같은 PC 악성코드·브라우저 확장·타 로컬 서비스는 완화만 하는 잔여 위험으로 사용자 수용 여부 질문(규칙 A, High 는 수용 불가 기준 유지) | 1-8, 1-9, 7-2 |

### 8-2. FR / 비기능 후보

| 임시 ID | 내용 | 근거 |
|---|---|---|
| FR-D01 | 멱등성 키 저장소(고유 제약 `(scope,key)`, `request_hash`, 진행중 409, 결과 재생, 만료 정책) — 업무 변경과 같은 트랜잭션 | 4-7 |
| FR-D02 | 동일 영상 반영은 DB 고유 제약/행 잠금으로 이중 반영 차단(멱등 키와 별개) | 4-7 |
| FR-D03 | 워커 별도 프로세스, 리스·하트비트, SIGTERM 안전 중단, 놓친 예약 몰아서 실행 금지 | 4-9 |
| FR-D04 | 로그인(PIN/접속 코드) 화면, 세션 만료 안내(한국어), 재로그인 흐름 | 2-1, 2-7 |
| FR-D05 | OpenAPI 계약 -> `openapi-typescript` 타입 생성 파이프라인(TS 5.x 고정) + 계약 시험 | 5-3 |
| FR-D06 | 접근성: WCAG 2.2 AA 체크리스트 + axe 자동 시험 + 수동 키보드 시험(적용 범위는 설계서 확정) | 5-6, 5-7 |
| FR-D07 | 폰트 정책(시스템 스택 기본 / 자체 호스팅 선택) | 5-9 |
| FR-D08 | 영상 썸네일 표시 정책(미표시 / `img-src` 예외 / 프록시) | 3-4 |
| FR-D09 | 감사 로그 조회 화면과 체인 검증 결과 표시, 백업 시 머리 해시 출력 | 7-1~7-3 |
| FR-D10 | 접속 주소를 `http://127.0.0.1:<포트>` 로 고정 안내, `localhost` 접속 리다이렉트/거부 정책 | 1-10 |

---

## 9. [확인 필요] 목록 (이 조각에서 확인하지 못했거나 추정인 것)

1. Chrome LNA 의 정확한 출시 버전(141 vs 142 상충)과 Edge 적용 시점 — 원문(developer.chrome.com) 열람 실패. 벤더 문서는 142·2025-10-28.
2. `http://127.0.0.1` 에서 Chrome/Edge 의 `Secure` 쿠키 설정·전송 동작(httpwg 표는 localhost만 다룸) — **실측 필요**.
3. TypeScript 5.x 의 현재 최신 안정 버전 번호, TS 6 안정판 존재 여부와 openapi-typescript 와의 호환(PR 병합 여부) — `npm view typescript@5 version` 실행 필요.
4. openapi-typescript 이슈 #2841 의 현재 상태(열림 추정).
5. `jest-axe` 의 Vitest 호환, `vitest-axe` 0.1.0 의 유지보수 상태.
6. RFC 9457 본문, IETF Idempotency-Key 초안 본문, RFC 6265bis, WCAG 2.2 W3C 원문 — 열람 실패(해당 항목 모두 "원문 미열람").
7. nginx 지시어(`add_header` 상속, `client_max_body_size` 기본값, `limit_req` 상세) 공식 문서 — nginx.org 열람 실패, 일반 지식/검색 요약 의존.
8. `nginxinc/nginx-unprivileged` 현재 태그·다이제스트 및 Docker Hub 실존 — 이 조각에서 레지스트리 조회 안 함.
9. 장애인차별금지법 제21조·시행령 제14조의 현행 의무 대상 범위(개인·비공개 도구 포함 여부), **KWCAG 2.2 의 실재 및 고시 현황** — law.go.kr 열람 실패, 2차 자료만. 법률 자문 아님.
10. Uvicorn `--forwarded-allow-ips` 기본값(127.0.0.1 여부), `TrustedHostMiddleware` 의 포트 포함 Host 비교 동작.
11. Swagger UI 기본 자산의 CDN 사용 여부(개발 프로필에서 켤 경우 CSP/F-04 영향).
12. SQLAlchemy 2.1.4 ↔ Alembic 1.20.0 호환, pip-audit 라이선스 필드(null), pip-tools/uv 등 해시 고정 도구 실존.
13. 모든 패키지에 대해 **알려진 취약점(CVE) 점검 미실시**, 전이 의존성 설치 훅 미점검, `npm audit`/`pip-audit` 미실행.
14. 브라우저 확장·타 로컬 서비스 시나리오(1-8, 1-9)는 근거 URL 없이 일반 지식/추정 — 9단계 위협 시험 대상.
15. DEC-032~035 본문(grep 출력 생략)과 ORCHESTRATOR.md 1장 본문은 이 조각에서 정독하지 못함 -> 취합 단계에서 대조.
16. 사용자 결정 필요(규칙 A): PIN/접속 코드 사용 여부(Q-6), 썸네일 표시 정책, 폰트 정책, 가상 스크롤 vs 서버 페이지네이션, 같은 PC 악성코드·확장 잔여 위험 수용.
17. 요청서가 언급한 "오류/내부 경로 비노출", "Windows Docker Desktop 에서 127.0.0.1 게시와 실제 소스 IP" 관련 실측은 인프라 축(타 축) 소관이며 여기서는 추정만 사용.

## 10. 타 축 참고

- 인프라/Docker 축: Docker Desktop 환경에서 nginx가 보는 클라이언트 IP가 게이트웨이 IP일 가능성(3-6 추정), `tmpfs:/tmp` 필요(3-8), 이미지 다이제스트 조회.
- 규제·법 축: 장차법 웹접근성(5-8), psycopg LGPL-3.0·axe-core MPL-2.0·OFL-1.1 라이선스 고지(6장).
- LLM/기술 축(규칙 J): 렌더링 단계 XSS(AI 응답을 텍스트로만), 프롬프트 인젝션 방어는 이 조각 범위 밖.
- 도메인 운영 규칙 축: 해당 정보 없음(이 축에서 발견 못 함).

---

## 11. 규칙 B 자체 검증 (조각 기준, 2회)

### 1차 검증 — 출처·근거 점검
| 점검 | 결과 | 조치 |
|---|---|---|
| 모든 주장에 출처/열람 표기가 있는가 | 일부 항목(1-8, 1-9, 3-5, 3-7, 5-2, 5-7, 4-9)이 "일반 지식" 이며 출처 없음 | 열람 열에 "일반/미확인"과 확신도를 명시하고 [확인 필요] 목록(9장)에 올림 |
| 검색 요약만 근거인 항목에 "원문 미열람" 표시 | 1-1, 1-2, 1-7, 3-3, 3-6, 4-7, 5-8, 6-a, 7-1 에 표시 | 완료 |
| 상충 사실을 숨기지 않았는가 | LNA 141 vs 142 상충 기록, TS latest vs openapi-typescript 충돌 기록, KWCAG 대상 범위 자료 간 상충 기록, nginx/삼중 트리거 주장 중 TRUNCATE 관련 상충 기록 | 완료 |
| 수치 오류 점검 | 모든 버전은 조회 요약에서 옮김. pydantic은 JSON 절단으로 프로젝트 페이지 값 사용 사실을 표기 | 완료 |
| **발견 결함 1**: 1차 작성 초안에서 OWASP 사이트 도메인 열람 실패를 숨기고 raw 미러를 "원문"으로만 표기할 뻔함 | 열람 열을 "미러(원문 마크다운)"로 구분하고 도메인 표(12장)에 실패 사실 기록 | 수정 완료 |
| **발견 결함 2**: 6장에서 "알려진 취약점 점검"이 이루어진 것으로 오해될 여지 | 6-1에 "취약점 점검 미실시" 명시, 9장 13번에 등록 | 수정 완료 |
| **발견 결함 3**: `npm view`/`pip index` 를 실행한 것으로 읽힐 수 있음 | 문서 첫머리와 6-1에 "Bash 없음, JSON API 직접 조회, 2차 요약" 명시 | 수정 완료 |
| **발견 결함 4**: 시사점 SEC-D20의 HMAC 제안이 출처 있는 표준처럼 보임 | 7-1 시사점에 "이 조사의 설계 제안, 표준 패턴 아님" 명시 | 수정 완료 |
→ 1차 결과: 결함 4건 발견·수정(수정 후 재점검에서 동일 유형 추가 결함 없음).

### 2차 검증 — "이 보고서만 보고 기획서·설계서를 쓸 사람" 관점
| 점검 | 결과 | 조치 |
|---|---|---|
| 요청 항목 1~7 모두 다뤘는가 | 1(공격·방어), 2(세션·쿠키), 3(nginx), 4(FastAPI 8개 세부), 5(React/접근성/폰트), 6(패키지 표·공급망), 7(감사 로그) 모두 있음 | OK |
| 패키지 표가 요청 목록 전체를 포함하는가 | fastapi, uvicorn, pydantic, sqlalchemy, alembic, psycopg, react, vite, typescript, react-query, react-virtual, react-router-dom, vitest, testing-library/react, openapi-typescript, eslint, prettier, axe-core, jest-axe, pip-audit, pytest, pytest-asyncio, httpx 전부 있음 | OK |
| 기획자가 바로 쓸 결정 필요 사항이 분리되어 있는가 | 9장 16번, 8-1 SEC-D22, FR-D07/D08 | OK |
| 구현 가능한 구체값이 있는가 | 쿠키 속성, CSP 시작안, 타임아웃 값, 감사 로그 컬럼 등 제안 값 제시(모두 "제안" 표시) | OK |
| **발견 결함 5**: 요약 5줄 중 3번 줄이 "Secure/http 127.0.0.1" 결론을 모호하게 표현 | 근거 없음을 명시 + 실측 필요로 정리 | 수정 완료 |
| **발견 결함 6**: 규칙 J(LLM)와 관련된 이 축의 접점(AI 응답 텍스트 렌더링)이 시사점에만 있고 SEC에 약함 | SEC-D17 에 "AI 응답은 텍스트 렌더링" 반영, 10장 타 축 참고에 기록 | 수정 완료 |
| **미해소(결함이 아니라 한계)**: Bash 부재로 `npm view`/`pip-audit`/`npm audit` 실행 불가, 다수 도메인 열람 실패 | 9장에 전부 등록. 취합 단계 또는 Bash 가능한 호출에서 `npm view typescript@5 version`, `npm audit`, `pip-audit`, Chrome 127.0.0.1 Secure 쿠키 실측을 수행해야 함 | 미해소로 보고 |
→ 2차 결과: 결함 2건 발견·수정. 단, 위 "미해소" 항목은 이 조각 자체에서는 해결 불가이므로 **PASS로 선언하지 않고 "조건부 — 열람/실행 제약으로 [확인 필요] 17건 잔존"** 으로 기록한다. (취합본 기준 규칙 B 검증은 취합 에이전트 몫.)

---

## 12. 열람 성공/실패 도메인 표

| 도메인 | 결과 | 사용한 항목 |
|---|---|---|
| registry.npmjs.org | 성공 | npm 패키지 latest/dist-tags (단, `/openapi-typescript`·`/typescript` 전체 문서는 크기 초과로 일부 실패, dist-tags 전용 경로로 대체) |
| pypi.org | 성공(일부 절단) | PyPI JSON (pydantic JSON 절단 -> 프로젝트 페이지로 대체; fastapi/uvicorn 등은 업로드일 일부 미확인) |
| github.com | 성공 | httpwg 이슈 #2605, slowapi, openapi-typescript 이슈 검색 |
| raw.githubusercontent.com | 성공(일부 404) | OWASP 시트(CSRF, Session, CSP, HTTP Headers), MDN set-cookie, W3C secure-contexts 소스, FastAPI/Starlette/Uvicorn 문서, pydantic LICENSE. 404: OWASP JWT 시트 경로, IETF idempotency 초안 경로. WICG LNA README는 개요만 있어 내용 부족 |
| developer.chrome.com | 실패(ENOTFOUND) | LNA 원문 미열람 |
| cheatsheetseries.owasp.org | 실패(ENOTFOUND) | raw 미러로 대체 |
| developer.mozilla.org | 실패(ENOTFOUND) | raw 미러로 대체 |
| www.w3.org | 실패(ENOTFOUND) | raw 미러(secure-contexts)로 대체, WCAG 2.2 원문 미열람 |
| datatracker.ietf.org | 실패(ENOTFOUND) | RFC 9457, RFC 6265bis 원문 미열람 |
| www.rfc-editor.org | 실패(ENOTFOUND) | RFC 9457 원문 미열람 |
| fastapi.tiangolo.com | 실패(ENOTFOUND) | raw 미러로 대체 |
| nginx.org | 실패(ENOTFOUND) | nginx 공식 문서 미열람(검색 요약 의존) |
| www.law.go.kr | 실패(ENOTFOUND) | 법령 원문 미열람 |
| 검색 엔진(WebSearch) | 성공 | NCC Group, MCP 사례, LNA, 쿠키 표, OWASP/Fetch Metadata, 공급망, 감사 로그, 멱등성, RFC 9457 라이브러리, KWCAG 등 요약만 사용(링크 대부분 원문 미열람) |

## 13. Teardown

- 설치한 패키지·가상환경·컨테이너·프로세스·임시 DB: **없음**(설치 금지 준수, 레지스트리 조회만).
- 생성한 파일: 이 파일 `docs/harness/_parallel/01-axisD-local-web-security.md` 하나뿐. 스크래치 디렉터리·`.harness-tmp/`·`/tmp` 사용 없음.
- 수정한 코드·설정: 없음. 비밀값 기록: 없음.
- 네트워크 호출은 모두 읽기 전용 GET 이었고 자격 증명은 사용하지 않았다.
