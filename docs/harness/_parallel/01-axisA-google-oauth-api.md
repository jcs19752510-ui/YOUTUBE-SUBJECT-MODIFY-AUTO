# 1단계 조사 조각 — 축 A: 구글 OAuth 웹 애플리케이션 방식 + YouTube Data API 정책

- 조사 시점: 2026-10-10 (모든 "확인 일자" 동일). 검색 모드: standard 중심 + extended 1회.
- 모드: 조각 모드(축 A). `01-trend-analysis.md`와 검증 로그는 쓰지 않았다. 코드·설정 파일은 수정하지 않았다.
- 적용 법규 기준: 대한민국(기본값) + Google/YouTube 약관. 이 조각은 법률 자문이 아니다.
- **공통 한계(DEC-010)**: `developers.google.com`, `developers.google.cn`, `support.google.com`은 이 환경에서 DNS 오류(`getaddrinfo ENOTFOUND`)로 열리지 않았다. 아래 모든 사실은 **WebSearch가 돌려준 공식 URL의 검색 요약**(또는 제3자 자료)에만 근거하며, 그래서 **모든 사실 항목에 `[확인 필요: 원문 미열람]`이 붙는다.** 표에서 "열람 여부"가 "검색요약(공식URL)"이면 공식 URL이 검색에 나와 그 요약이 내용을 인용한 경우, "제3자"면 공식 근거 없이 제3자 글만 있는 경우다.
- 확신도 기준: 상(공식 URL 요약 + 제3자 다수 일치) / 중(공식 URL 요약 1건 또는 제3자 다수) / 하(제3자 단일, 추론, 상충).

## 요약 (5줄)
1. 웹 애플리케이션 유형은 리디렉션 URI가 **콘솔에 정확히 등록**돼야 하고 http는 localhost 계열만 예외로 허용된다는 것이 검색 요약으로 확인된다. `127.0.0.1`이 웹 유형에서 받아들여지는지는 **명시 근거가 없어 사용자가 콘솔에서 실제 등록해 확인**해야 한다(추론: 허용 가능성 높음).
2. 코드 교환은 서버측에서 `client_secret`과 함께 하는 것이 안전한 패턴이다(웹 유형은 PKCE를 써도 secret이 필요하다는 단일 블로그 실험). state와 PKCE(S256)를 함께 쓴다.
3. 동의 화면 "테스트" 상태의 refresh token은 동의 후 7일에 만료한다(공식 URL 요약). "프로덕션" 게시 후 만료 동작은 자료가 상충하고, `youtube*` 스코프가 민감 범위면 **미검증 앱 경고와 신규 사용자 100명 평생 한도**가 걸린다(공식 URL 요약). 1인 개인용이어도 면제 근거는 찾지 못했다.
4. `videos.update`는 snippet 갱신 시 `title`+`categoryId` 필수이고 **요청에 빠진 snippet 속성은 삭제**된다(공식 URL 요약). 쿼터는 기본 10,000/일, 태평양 자정 초기화, 쓰기는 일반적으로 50이지만 `videos.update` 행 자체는 공식 표에서 못 봤다. 200개 변경만 10,000단위(=기본 한도 전부)다.
5. **롤백용 원본 snippet을 30일보다 오래 보관하는 것이 YouTube Developer Policies III.E.4(2026-09-14판, 2차 요약)와 충돌할 수 있다.** 이 도구에 적용되는지 원문 확인이 필요하고, 사용자 결정이 필요한 최우선 쟁점이다.

---

## 1. 항목별 조사표

### 1-1. OAuth 흐름: 웹 vs 데스크톱, 리디렉션, state/PKCE, secret, refresh token

| # | 사실 | 근거 URL | 열람 여부 | 확신도 | 이 프로젝트 시사점 |
|---|---|---|---|---|---|
| 1 | 웹 서버 앱 문서는 `access_type=offline`(첫 코드 교환 시 refresh token 발급), `include_granted_scopes=true`(증분 권한), `state`(요청-응답 연결 보증)를 설명한다. `prompt=consent`는 "동의 화면을 다시 띄우는 선택 옵션"으로만 확인됐고, **refresh token 재발급 조건이라는 점은 이번 검색에서 미확인**(관행) | https://developers.google.com/identity/protocols/oauth2/web-server (및 구버전 사본 https://googleapis.dev/ruby/google-api-client/v0.36.3/file.oauth-web.html) | 검색요약(공식URL) + 구버전 사본 요약 | 중 [확인 필요: 원문 미열람] | 웹 로그인 URL에 `access_type=offline` 필수. `prompt=consent`는 "refresh token이 없을 때 재요청" 용도로 쓰되, 매번 붙이면 동의 화면이 반복되고 토큰이 누적(아래 #12)되므로 **"토큰 없을 때만" 붙이는 설계**를 ADR로 |
| 2 | 리디렉션 URI 규칙(Cloud 콘솔 도움말): ① **https 필수, localhost(localhost IP 주소 URI 포함)는 예외** ② 호스트는 원시 IP 불가이나 localhost IP는 예외 ③ userinfo·경로 순회(`/..`)·open redirect·fragment 불가 ④ 요청의 `redirect_uri`가 등록값과 **정확히 일치**하지 않으면 `redirect_uri_mismatch` | https://support.google.com/cloud/answer/15549257 , https://developers.google.com/identity/protocols/oauth2/web-server | 검색요약(공식URL) | 중 [확인 필요: 원문 미열람] | 등록 URI는 포트까지 고정(예: `http://127.0.0.1:<포트>/api/v1/auth/google/callback`). 포트 변경 = 콘솔 재등록. 문서에 "정확 일치" 검증 테스트 추가 |
| 3 | **웹 유형에서 `http://127.0.0.1`이 실제로 등록·허용되는지 명시한 자료는 없다.** "localhost IP 주소 URI 예외" 문구가 있어 허용될 가능성은 높다(추론). `*.localhost` 하위 도메인은 콘솔이 거부한다는 오래된(약 2022) 포럼 글, `.local`도 비지원이라는 글이 있음 | https://support.google.com/cloud/answer/15549257 , https://discuss.google.dev/t/a-b-localhost-redirect-uris-in-oidc-oauth2-0-authentication/101237 | 검색요약 + 제3자(포럼) | 하(추론) [확인 필요: 원문 미열람] | **Q-5의 핵심.** 사용자가 콘솔에서 웹 유형 클라이언트에 `http://127.0.0.1:<포트>/...`를 등록해 보면 즉시 판정된다. 실패 시 `http://localhost:...`로 대체 |
| 4 | 같은 페이지의 Ads API 샘플: **웹 유형은 `http://127.0.0.1`을 승인된 리디렉션 URI에 추가해야 하고, 데스크톱 유형은 콘솔 등록 없이 동작**. 제3자 레퍼런스: 진짜 데스크톱 클라이언트는 `127.0.0.1` 루프백에서 포트가 무관하며, 웹 클라이언트를 데스크톱처럼 쓰면 `redirect_uri_mismatch`가 흔하다 | https://developers.google.com/google-ads/api/docs/client-libs/dotnet/oauth-web | 검색요약(공식URL, Ads API 문서) + 제3자 | 중 [확인 필요: 원문 미열람] | 현 CLI는 `InstalledAppFlow`(데스크톱 유형, `src/ytitle/auth.py:40-42`). 웹으로 바꾸면 클라이언트 JSON 키가 `installed`→`web`으로 달라지므로 **기존 `client_secret.json`을 그대로 쓸 수 없고 새 웹 유형 클라이언트를 만들어야 한다**(추론, 검증 필요) |
| 5 | **대안(데스크톱 유형 유지)**: 구글의 루프백 IP 흐름은 iOS/Android/Chrome 유형에서 폐지되지만 **데스크톱 앱에서는 계속 지원**된다. 허용 형식은 `http://127.0.0.1:<port>`, `http://[::1]:<port>`, `http://localhost:<port>` 3종 | https://developers.google.com/identity/protocols/oauth2/resources/loopback-migration | 검색요약(공식URL) | 중 [확인 필요: 원문 미열람] | 컨테이너 안 서버가 받는 콜백이라도 브라우저는 호스트의 `127.0.0.1:<게시포트>`로 돌아오므로 **데스크톱 유형으로도 기술적으로 가능할 수 있다**(추론). 이 경우 콘솔 리디렉션 등록이 필요 없다는 장점, 클라이언트 secret이 비밀이 아니라는 단점. **웹 vs 데스크톱은 ADR 대상**이며 에이전트가 정하지 않는다 |
| 6 | **PKCE**: Google 클라이언트 라이브러리 문서가 `code_challenge`/`code_challenge_method`를 권장 옵션으로 둔다. 메서드는 `S256` 또는 `plain`만, 생략 시 `plain`. RFC 7636 정오표는 관찰 가능한 공격자가 있으면 반드시 S256 | https://googleapis.dev/nodejs/google-auth-library/latest/interfaces/GenerateAuthUrlOpts.html , https://www.rfc-editor.org/rfc/inline-errata/rfc7636.html | 검색요약(공식 라이브러리 문서) | 중 [확인 필요: 원문 미열람] | PKCE는 **S256 명시**. 서버측 코드 교환 시 `code_verifier` 전달. `plain` 금지 |
| 7 | **웹 유형은 PKCE를 써도 토큰 교환에 `client_secret`이 필요**하다는 2025-07 단일 저자 실험. RFC 관점의 "secret 선택" 기대와 다름 | https://ktaka.blog.ccmp.jp/2025/07/oogle-oauth2-and-pkce-understanding.html | 검색요약(제3자, 본문 DNS 오류로 미열람) | 하 [확인 필요: 원문 미열람] | `client_secret`은 Docker secret 파일로 `api` 컨테이너에만 주입(S-W08/D-06). "PKCE가 있으니 secret 불필요"로 설계하지 않는다 |
| 8 | 서버측 코드 교환 샘플은 `client_id`, `client_secret`, `code`, `redirect_uri`, `grant_type=authorization_code`를 구글 토큰 엔드포인트에 POST | 위 #1의 구버전 사본 및 https://developers.google.com/identity/protocols/oauth2/web-server | 검색요약 | 중 [확인 필요: 원문 미열람] | 코드 교환은 `api`에서만. 브라우저(React)는 토큰을 절대 받지 않는다. `redirect_uri`는 인가 요청과 교환 요청에서 동일 값 |
| 9 | 증분 권한(`include_granted_scopes=true`): 이전에 허용한 스코프가 새 요청에 이어진다. **웹 서버 흐름 문서에서 설명되는 기능**이다 | https://developers.google.com/identity/protocols/oauth2/web-server | 검색요약(구버전 사본 포함) | 중 [확인 필요: 원문 미열람] | 읽기/쓰기 **권한 부여** 분리는 웹에서도 가능. 단 true로 쓰면 쓰기 토큰에 읽기 스코프가 합쳐질 수 있다(추론). 현 설계의 "토큰 2종 분리 저장"을 유지하려면 쓰기 요청은 `include_granted_scopes`를 **끄고** 쓰기 스코프만 요청하는 것이 안전하다(ADR로 결정, 실제 응답의 `scope` 값을 검사하는 테스트 필요) |
| 10 | 데스크톱(`InstalledAppFlow`) 현 코드는 `READ_SCOPES=(youtube.readonly, yt-analytics.readonly)`, `WRITE_SCOPES=(youtube.force-ssl,)`, 토큰 파일 2종(`read_token.json`, `write_token.json`) | 저장소 `src/ytitle/auth.py:17-24` | 원문(저장소) | 상 | 이식 대상. 단 쓰기 스코프는 `youtube`/`youtube.force-ssl` 중 `videos.update`에 충분한 최소값이 원문 미확인(#25) |
| 11 | refresh token 소멸 요인(제3자가 공식 문서를 인용): 사용자 철회, **6개월 미사용**, Gmail 스코프 포함 시 비밀번호 변경, 테스트 상태 7일 | https://docs.uipath.com/integration-service/automation-cloud/latest/user-guide/uipath-google-docs-authentication.md | 제3자 | 중 [확인 필요: 원문 미열람] | 만료·철회를 **정상 경로**로 취급: `invalid_grant` 수신 시 토큰 폐기+한국어 재로그인 안내(W-002). "6개월 미사용"이 있으므로 장기 휴면 후 첫 실행에도 같은 처리 |
| 12 | **계정당·클라이언트 ID당 살아 있는 refresh token 100개 한도**, 초과 시 가장 오래된 것이 경고 없이 무효화. 서비스 계정은 제외 | https://help.formstack.com/hc/en-us/articles/44593146748051-Google-Account-Token-Limitations (제3자가 구글 문서 인용) | 제3자 | 중 [확인 필요: 원문 미열람] | 로그인을 반복해도 한도에 닿기는 어렵지만, 읽기·쓰기 2종 × 재로그인 누적을 고려해 "새 토큰 발급 시 이전 토큰 revoke 호출"을 FR 후보로 |
| 13 | refresh token 저장 모범 사례: 공식 자료에서 직접 확인하지 못했다. (RFC 8252/OAuth 일반 원칙은 있으나 이번 조사 근거 아님) | 해당 없음 | 미확인 | 하 | `[확인 필요]`. 프로젝트 요구사항(웹프로그램으로수정요청.md D-06/D-07/S-W08/S-W13a)이 이미 정한 방향(DB가 아닌 secrets/볼륨 파일, 권한 제한, 로그 마스킹, 백업 제외)을 유지하고, 구글 권고 원문은 사용자 허용 도메인 추가 후 재확인 |

### 1-2. 동의 화면 게시 상태, 테스트 사용자, 스코프 검증

| # | 사실 | 근거 URL | 열람 여부 | 확신도 | 이 프로젝트 시사점 |
|---|---|---|---|---|---|
| 14 | 게시 상태 **Testing**에서 테스트 사용자의 인가는 **동의 시점부터 7일** 후 만료. 오프라인 접근으로 받은 refresh token도 만료. (제3자 보충: 기본 프로필 범위만 요청하면 예외) | https://support.google.com/cloud/answer/10311615 , https://developers.google.com/health/setup | 검색요약(공식URL 2건) | 상 [확인 필요: 원문 미열람] | YouTube 스코프를 쓰므로 예외 비해당. **7일마다 재로그인**이 기본 전제(현 CLI의 `RELOGIN_HINT`와 동일). 200개를 여러 날에 걸쳐 반영하는 W-008과 충돌하므로 만료 감지·재로그인 안내·"만료 전 예약 반영 보류"가 필요 |
| 15 | **상충**: 한 2026-05 블로그는 7일이 "비활동 7일"이라고 서술. 공식 요약은 "동의 후 7일" | https://tech.sailjada.com/posts/2026-05-06-1924.html (제3자) vs 위 #14 | 제3자 vs 공식요약 | — | **상충 사실 그대로 보고.** 공식 요약(동의 후 7일)을 기본 가정으로 하되, 실제 만료는 사용자 PC에서만 관측 가능([확인 필요]) |
| 16 | 테스트 사용자 한도 **100명**(제3자 LatePoint 문서). 공식 수치는 못 봄 | https://wpdocs.latepoint.com/?p=488 | 제3자 | 중 [확인 필요: 원문 미열람] | 1인 사용에 충분. 한도 자체는 쟁점 아님 |
| 17 | 민감/제한 스코프를 요청하면서 검증을 안 받은 앱은 "미검증 앱" 경고 화면이 뜨고, **신규 사용자 100명 한도가 프로젝트 평생 적용**되며 초기화 불가. 100명 소진 시 로그인 차단 | https://support.google.com/cloud/answer/7454865 | 검색요약(공식URL) | 상 [확인 필요: 원문 미열람] | 개인용 1계정은 100명 한도를 소진하지 않는다(추론). 단 경고 화면 통과 절차가 UX에 포함됨. **"개인용·본인 계정은 검증 면제"라는 명시 근거는 못 찾음**(면제 목록 문장이 잘려 있었음) → 확인 필요 |
| 18 | YouTube 스코프 분류: 구글 도움말은 3단계(비민감/민감/제한)를 정의하고 민감·제한은 검증 필요. **스코프별 분류를 확정한 공식 표는 못 찾음.** 제3자 Phyllo: "YouTube 스코프는 읽기전용 포함 모두 민감", 다른 제3자: `youtube.readonly`/`youtube`/`youtube.force-ssl`은 민감, `youtubepartner`는 제한(CASA 필요). 이전 조사(`docs/yt/01_policy_research.md` d)도 같은 수준(`youtube`,`youtube.force-ssl`이 민감으로 승인된 사례) | https://support.google.com/cloud/answer/15549135 , https://www.getphyllo.com/post/youtube-oauth-scopes , https://developers.google.com/youtube/analytics/authentication | 검색요약(공식 정의) + 제3자(분류) | 하(분류 확정 불가) [확인 필요: 원문 미열람] | 아래 4개의 **임시 분류**: `youtube.readonly`=민감(제3자), `youtube.force-ssl`=민감(제3자), `youtube`=민감(제3자), `yt-analytics.readonly`=**분류 근거 없음**(Analytics 인증 문서는 "특정 사용자 데이터 접근 스코프를 쓰는 공개 앱은 검증 필요"라고만 요약). Console의 "데이터 액세스(Data Access)" 화면이 프로젝트별 실제 분류를 보여 주므로 **사용자가 스코프를 추가하면 즉시 확인 가능** |
| 19 | 스코프 과잉 요청은 검증 거절 원인. 제3자: `force-ssl`이 `youtube`/`youtube.upload`를 포괄하므로 함께 요청 시 거절 사유 | https://www.getphyllo.com/post/youtube-oauth-scopes | 제3자 | 하 | 쓰기 로그인에서 `youtube`와 `force-ssl`을 동시에 요청하지 않는다(현 코드는 `force-ssl` 1개) |
| 20 | **프로덕션 게시의 영향(개인 1인)**: 상충. ① 여러 제3자: 프로덕션이면 7일 만료가 풀리고 6개월 미사용 등으로만 만료 ② 구글 Health 설정 페이지(공식URL 요약): "In Production이면 일반적으로 만료 안 함(철회 또는 약 6개월 미사용 제외)" ③ 일부 사례: 게시 시 "검증 필요" 상태가 되고 재인가 후 7일 만료가 사라졌다는 포럼 글, 반대로 게시 후에도 7일 만료를 겪었다는 이전 조사 사례(`docs/yt/01_policy_research.md` d) ④ 개인 용도인데 앱 이름 검증 실패로 게시가 막혔다는 포럼 글 | https://developers.google.com/health/setup , https://tech.sailjada.com/posts/2026-05-06-1924.html , https://discuss.google.dev/t/app-name-verification-failures-on-required-publishing-but-this-is-for-my-personal-use-only/354816 , https://developers.google.com/identity/protocols/oauth2/production-readiness/overview | 검색요약(공식 URL 1~2건) + 제3자 | 하(상충) [확인 필요: 원문 미열람] | **결정은 사용자의 몫(에이전트가 대신 판단하지 않음).** 선택지: (A) Testing 유지 + 7일 재로그인 수용 (B) Production 게시 + 미검증 경고 통과 + 장기 refresh token 기대(검증 요구·상충 위험). 어느 쪽이든 앱은 만료를 정상 경로로 처리해야 함. 실측(사용자 계정에서 게시 후 8일째 토큰 유효 여부)만이 상충을 해소 |

### 1-3. YouTube Data API 쿼터

| # | 사실 | 근거 URL | 열람 여부 | 확신도 | 이 프로젝트 시사점 |
|---|---|---|---|---|---|
| 21 | 기본 쿼터 **프로젝트당 일 10,000단위**, 키가 아닌 프로젝트 단위(같은 프로젝트의 여러 키가 공유), 이월 없음, 초과 시 403 `quotaExceeded` | https://developers.google.com/youtube/v3/getting-started , https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits | 검색요약(공식URL) + 제3자 | 상 [확인 필요: 원문 미열람] | `quota.py` 기본 가정 유지. 403 `quotaExceeded`는 재시도하지 말고 "내일 PT 자정 이후" 안내 |
| 22 | 쓰기(생성·수정·삭제)는 **일반적으로 50단위**(공식 개요의 일반 원칙). `videos.update`의 개별 행은 공식 표에서 **확인하지 못했다**(표의 `videos` 행이 검색 발췌에서 잘림; 보인 행은 `channels.update`=50, `captions.update`=450). 제3자 다수는 `videos.update`=50, `videos.list`=1 | https://developers.google.com/youtube/v3/determine_quota_cost , https://www.blotato.com/blog/youtube-api-pricing | 검색요약 + 제3자 | 중 [확인 필요: 원문 미열람] | 사용자 입력 "videos.update=50"과 일치하나 **원문 확인은 못 했다**. 비용은 설정값(`update_cost`, `read_cost`)으로 유지, 하드코딩 금지. 표가 바뀐 전례(제3자: `videos.insert` 약 1,600→약 100, 2025-12)가 있어 **분기마다 재확인** |
| 23 | **초기화 시각: 태평양 시간(PT) 자정** | https://developers.google.com/youtube/v3/determine_quota_cost (미러 요약: "Daily quotas reset at midnight Pacific Time") | 검색요약(공식URL 미러) | 상 [확인 필요: 원문 미열람] | KST 환산(미국 서머타임 규칙 적용 계산, 출처 아닌 추론): PDT(UTC-7) 자정 = 한국 16:00, PST(UTC-8) 자정 = 17:00. 2026년 미국 서머타임은 11월 1일(일) 종료되는 것으로 계산됨 → **약 3주 뒤 한국 시각 경계가 1시간 이동**. 큐 스케줄러는 UTC 고정 오프셋이 아니라 `America/Los_Angeles` 타임존으로 "오늘/내일"을 계산(기존 ADR-006 유지) |
| 24 | 쿼터 증액: 기본 10,000 초과는 **API Compliance Audit** 통과가 필요. 양식: `https://support.google.com/youtube/contact/yt_api_form`. 정기 재감사 있음. API 프로젝트 단위로 감사 | https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits , https://support.google.com/youtube/contact/yt_api_form , https://developers.google.com/youtube/terms/revision-history | 검색요약(공식URL) | 상 [확인 필요: 원문 미열람] | 이 프로젝트의 증액 필요성은 낮다(하루 10~20건 권장 시 약 1,000단위). **증액 신청 비목표**로 명시. 감사 요건 세부(개인용 도구도 대상인지)는 미확인 |
| 25 | **여러 프로젝트로 쿼터 우회 금지**: 구글이 개발자 포럼에서 "여러 프로젝트가 하나처럼 동작해 쿼터 제한을 우회"한다고 경고하고 단일 프로젝트로 통합하도록 요구, 3일 내 시정 안 하면 제한한다는 **2차 인용**. 약관 원문의 조항 번호·문구는 **찾지 못했다** | https://forums.solar2d.com/t/critical-problem-with-your-google-cloud-platform-api-project-appodeal/350374 | 제3자(2차 인용) | 하 [확인 필요: 원문 미열람] | 정책 POL로 "프로젝트 1개만" 고정(웹프로그램으로수정요청.md 6-3-5와 일치). **테스트용 별도 구글 프로젝트도 만들지 않는다**(테스트는 가짜 구글 서버) |

### 1-4. videos.update 동작

| # | 사실 | 근거 URL | 열람 여부 | 확신도 | 이 프로젝트 시사점 |
|---|---|---|---|---|---|
| 26 | `part=snippet` 갱신 시 `snippet.title`과 `snippet.categoryId`는 **필수**. **요청에 값을 주지 않은 snippet 속성은 삭제**된다(공식 부분 갱신 가이드의 예: title만 바꾸면 description이 지워짐). 부분 갱신(PATCH) 불가, PUT 성격 | https://developers.google.com/youtube/v3/docs/videos/update , https://developers.google.com/youtube/v3/guides/implementation/partial | 검색요약(공식URL 2건) | 상 [확인 필요: 원문 미열람] | **title만 보내면 description/tags 등이 소실될 위험이 공식 문서 예로 확인됨.** 반드시 호출 직전 `videos.list(part=snippet)`로 읽은 snippet 전체를 보존·병합해 보낸다(기존 S5/`updater.py` 방향 일치). 전체 보존 후 title만 교체하는 단위 테스트 필수 |
| 27 | `part`에 없는 속성은 영향 없음. 본문에 `part`에 지정하지 않은 객체(예: status)가 있으면 **400**. `snippet.thumbnails`는 수정 불가(읽기전용) | https://developers.google.com/youtube/v3/guides/implementation/partial | 검색요약(공식URL) | 상 [확인 필요: 원문 미열람] | 요청 본문은 `id`+`snippet`만. `part=snippet` 하나. 읽기전용 필드(`thumbnails`, `publishedAt`, `channelId`, `channelTitle`, `liveBroadcastContent`, `localized` 등)를 **그대로 되돌려 보냈을 때 무시되는지 400인지는 미확인** → 가짜 구글 서버가 이를 구분하지 못하므로 실계정 1회 시험 전까지 [확인 필요]. 안전책: 쓰기 가능한 필드 화이트리스트만 전송(`title`,`description`,`tags`,`categoryId`,`defaultLanguage` 등)하되 어떤 필드가 쓰기 가능한지도 원문 확인 필요 |
| 28 | 제목: 최대 100자, `<` `>` 불가, 유효 UTF-8 (이전 조사 A등급) | https://developers.google.com/youtube/v3/docs/videos | 검색요약(공식URL, `01_policy_research.md` c) | 중 [확인 필요: 원문 미열람] | 검증기는 **문자 수 단위(코드포인트? UTF-16? 바이트?)** 가 문서에 불명확 → 이모지·한글 조합 문자 경계 케이스는 [확인 필요]. 보수적으로 코드포인트와 UTF-16 길이 중 작은 쪽 기준 |
| 29 | 변경 즉시 반영/전파 지연, 오류 사유(`invalidVideoMetadata` 등) | 이번 검색에서 근거를 찾지 못함 | 미확인 | 하 | `[확인 필요]`. 사후 재조회 검증이 지연 때문에 오탐(구제목 반환)할 수 있으므로 **지연 재시도 정책(예: 지수 백오프, 최종 불일치는 '확인 보류' 상태)** 을 설계에 넣고, 실계정 1건 시험(승인 후)에서 실측 |
| 30 | `videos.update` 호출에 필요한 최소 스코프: 공식 문서의 메서드별 "Authorization" 절이 정답이나 **못 읽었다**. 클라이언트 라이브러리 설명: `youtube.force-ssl`은 "영상·평점·댓글·자막 편집·삭제", `youtube`는 계정 관리 | https://googleapis.dev/dotnet/Google.Apis.YouTube.v3/latest/api/Google.Apis.YouTube.v3.YouTubeService.Scope.html | 검색요약(공식 라이브러리 문서) | 하 [확인 필요: 원문 미열람] | DEC-016의 미결과 동일. **현 코드의 `force-ssl` 선택은 가능성이 높으나 미확정.** 12단계 전 사용자가 콘솔/문서로 확인하거나, 가짜 서버가 아닌 실계정 시험에서 403 `insufficientPermissions`로 판정 |

### 1-5. YouTube API Services 약관·개발자 정책

| # | 사실 | 근거 URL | 열람 여부 | 확신도 | 이 프로젝트 시사점 |
|---|---|---|---|---|---|
| 31 | **저장 기간(2차 요약)**: 개발자 정책(2026-09-14 갱신판이라는 일본어 GitHub 이슈 요약) III.E.4 — (b) 인가된 데이터 중 조회수 등 **통계**는 필요한 동안 보관 가능하나 인가 상태를 30일마다 재확인, (c) **그 외 인가된 데이터는 30일까지**, (d) 비인가 데이터는 제한된 양만 임시로 30일까지. 구글 개정 이력도 "저장된 리소스 메타데이터는 30일 후 삭제 또는 갱신"을 III.E.4.b-d로 인용 | https://github.com/nanase/kemov/issues/222 (열람 성공, 원문 인용 아님) , https://developers.google.com/youtube/reporting/revision_history , https://developers.google.com/youtube/terms/developer-policies | 제3자(열람) + 검색요약(공식URL) | 중 [확인 필요: 원문 미열람] | **이 프로젝트의 최대 쟁점.** 롤백용 원본 snippet(제목·설명·태그), 반영 이력, 성과 스냅샷을 DB에 무기한 보관하면 "30일 이내 갱신 또는 삭제" 규정과 충돌할 수 있다. 개인 로컬 도구에도 적용되는지, 롤백/감사 로그가 예외인지 **원문과 구글 문의로 확인**해야 한다. 임시 설계안: ① 정책 확인 전까지 보관 필드를 최소화(제목·영상ID·시각), ② 설명·태그 원본은 'N일 후 삭제 또는 재조회 갱신' 설정값 ③ 감사 로그는 영상 메타 본문을 담지 않음. 어느 쪽이든 **사용자 결정 필요** |
| 32 | 파생 지표 정책: 승인된 분석 용도의 API 클라이언트는 조회수·좋아요 등 통계를 최대 36개월 보관 가능, 제목·설명 등은 여전히 30일 규칙 | https://developers.google.com/youtube/terms/derived-metrics-policy | 검색요약(공식URL) | 중 [확인 필요: 원문 미열람] | "승인된(accepted) 클라이언트"에 해당해야 하므로 개인 도구는 해당 없을 가능성 큼(추론). W-013 성과 비교용 스냅샷의 보관 기간에 영향 |
| 33 | 철회·삭제 시한 **상충**: ① Fandom 사본(구버전 정책): 사용자 철회 후 30 달력일 내 삭제 ② 다른 자료: 철회 후 **7일**(III.D.2.1) ③ 이전 정책 문서 계열 요약: 사용자의 삭제 요청 또는 인가 확인 불가 시 30일 | https://youtubehelp.fandom.com/wiki/YouTube_API_Services_-_Developer_Policies , https://developers.google.com/youtube/terms/developer-policies-guide | 제3자 vs 검색요약 | 하(상충) [확인 필요: 원문 미열람] | 가장 짧은 값(7일)을 기본 가정으로 "구글 연결 해제 시 7일 내 데이터 삭제" 동작을 설계하되 확정은 원문 후. 해제 화면에 삭제 범위를 고지 |
| 34 | 인가 데이터 사용 클라이언트는 사용자에게 **구글 보안 설정 페이지에서 접근을 철회할 수 있음을 안내**해야 하고, 사용자 데이터를 무기한 보관하지 말고 삭제 절차를 제공해야 한다(개발자 정책 III.A 8번, 검색요약) | https://developers.google.com/youtube/terms/developer-policies | 검색요약(공식URL) | 중 [확인 필요: 원문 미열람] | W-002 "로그인 해제" 화면에 "구글 계정 > 보안 > 서드파티 연결에서도 철회 가능" 안내 포함(기존 EVT-001 `--revoke` 안내와 동일 취지). 개인용 도구에서의 개인정보처리방침 의무 여부는 [확인 필요] |
| 35 | **자동화된 메타데이터 변경**(제목 일괄 수정)을 직접 규율하는 조항은 이번 검색에서 **찾지 못했다.** 검색 결과가 III.E "YouTube 데이터와 콘텐츠 취급" 제목만 보여 주었고 본문은 못 봄 | https://developers.google.com/youtube/terms/developer-policies | 검색요약(제목만) | 하 [확인 필요: 원문 미열람] | "해당 조항 없음"이라고 단정하지 않는다. 약관 전문 확인 전까지 "본인 채널만, 본인 동의, 사람 승인 후 반영, 쿼터 1프로젝트" 원칙으로 설계 |
| 36 | 제재: 정책 위반 시 API 접근 정지·종료 가능(개정 이력) | https://developers.google.com/youtube/terms/revision-history | 검색요약(공식URL) | 중 [확인 필요: 원문 미열람] | 반영 속도 제한(분당 호출 제한)과 사람 승인이 정책 위험을 낮춘다. 한 번에 수십 건을 연속 변경하는 패턴이 스팸·기만 메타데이터 정책(커뮤니티 가이드라인, 이전 조사 f)에 걸리는지는 이 축에서 판단 불가 → 축 B/규제 축과 연계 |

### 1-6. 롤백 시 주의점 (추론 + 위 사실의 결합, 별도 출처 없음)

| # | 내용 | 근거 | 확신도 | 시사점 |
|---|---|---|---|---|
| 37 | 롤백도 `videos.update`이므로 **롤백 시점의 최신 snippet을 다시 읽고 title만 이전 값으로 교체**해야 한다. 원본 전체 snippet을 되돌려 쓰면 그 사이 사용자가 Studio에서 바꾼 설명·태그를 덮어쓴다 | 위 #26 (삭제 의미) 에서의 논리적 귀결 | 중(추론) | 롤백 계획 = "현재 snippet 재조회 → title만 교체 → 재조회 검증". 저장할 원본은 **제목 중심**, 나머지 필드는 diff 확인용 해시/요약으로 충분한지 설계에서 판단(#31 보관 제한과 연동) |
| 38 | 롤백 전 현재 제목이 '반영한 새 제목'과 다르면(사람이 Studio에서 다시 바꿈) 롤백을 막고 확인을 요구 | 기존 설계 S9(호출 직전 재조회)의 연장 | 중(추론) | 롤백 시 충돌 검사 FR 후보 |
| 39 | 쿼터 부족일에는 롤백도 막힌다(50단위). 긴급 롤백 몫으로 일부 쿼터를 남겨 둘지 | #22 | 중(추론) | 일일 상한 안에 "롤백 예비량" 설정값 |
| 40 | 비공개·삭제된 영상, 소유권 상실, 권한 철회 상태에서는 롤백 실패(404/403) → 상태 `rollback_failed`로 남기고 계속 진행 | 일반 API 동작에 기반한 추론 | 하 [확인 필요] | 오류 사유별 처리표는 실계정 시험 후 보강 |

---

## 2. 설계에 넣을 요구사항 후보 (ID는 임시, 2단계에서 정식 번호 부여)

### POL (정책·규제)
| 임시 ID | 후보 내용 | 근거 항목 |
|---|---|---|
| POL-A1 | 구글 클라우드 프로젝트는 **1개만** 사용한다. 테스트용·추가 프로젝트로 쿼터를 늘리지 않는다 | #25 |
| POL-A2 | **데이터 보관 기간 정책**: 영상 메타데이터(제목 이외 설명·태그 등)와 성과 스냅샷의 보관 상한을 설정값으로 두고(기본 30일 이내 갱신 또는 삭제 가정), 롤백용 제목 이력의 보관 근거를 문서화한다. 정책 원문 확인 전까지 `[확인 필요]` | #31, #32 |
| POL-A3 | 구글 연결 해제 시 저장된 구글 유래 데이터(토큰, 인가 데이터)를 삭제하는 절차와 기한(가정 7일 이내)을 정의하고, 해제 화면에 구글 보안 설정 페이지 철회 안내를 표시 | #33, #34 |
| POL-A4 | OAuth 게시 상태(Testing/Production) 선택과 그 영향(7일 재로그인 vs 미검증 경고)을 사용자가 결정하고 기록한다. 결정 전 기본은 Testing 가정 | #14, #17, #20 |
| POL-A5 | 쿼터 증액·Compliance Audit 신청은 범위 밖(비목표). 필요 시 별도 결정 | #24 |

### SEC (보안)
| 임시 ID | 후보 내용 | 근거 항목 |
|---|---|---|
| SEC-A1 | OAuth 인가 요청에 `state`(암호학적 난수, 1회용, 만료 10분 이내)와 PKCE `code_challenge_method=S256`을 사용. `plain` 금지 | #6 |
| SEC-A2 | **`state` 검증은 쿠키가 아니라 서버측 저장소(DB의 1회용 레코드)로 한다.** 구글에서 돌아오는 콜백은 교차 사이트 최상위 이동이라 `SameSite=Strict` 세션 쿠키가 전송되지 않을 수 있다(추론, 브라우저 표준 동작에 기반). 세션 쿠키는 `Lax` 필요 여부를 ADR로 결정하고 S-W04와 모순되지 않게 문서화 | 추론 (S-W04, S-W08) |
| SEC-A3 | 리디렉션 URI는 서버에 정확히 일치하는 단일 값으로 고정하고, 요청의 Host가 `127.0.0.1`이 아니면 로그인 시작을 거부. `127.0.0.1`과 `localhost`는 쿠키·콜백 출처가 달라지므로 UI·문서에서 한 가지만 안내 | #2, #3 |
| SEC-A4 | `client_secret`은 Docker secret 파일로 `api`에만 주입. 코드 교환은 `api`에서만 수행하고 브라우저·`worker` 외 컨테이너에 토큰 비전달 | #7, #8 |
| SEC-A5 | 읽기 토큰·쓰기 토큰은 분리 저장(DB 외 볼륨 파일, 권한 제한, 백업 제외). 쓰기 로그인 응답의 `scope`가 요청한 쓰기 범위와 일치하고 **불필요한 읽기 스코프가 없는지** 검사하며, 불일치 시 토큰 폐기 | #9, #10 |
| SEC-A6 | `invalid_grant`/만료 수신 시 토큰을 삭제하고 쿼터 소비 없이 작업을 `AUTH_EXPIRED`로 정지(재시도 금지). 로그에 토큰·코드·secret이 남지 않도록 마스킹 테스트 | #11, #14 |
| SEC-A7 | OAuth 콜백(GET)은 상태를 바꾸는 유일한 예외 엔드포인트다. S-W03("상태 변경은 GET 금지")에 대한 **명시적 예외로 문서화**하고, 콜백에서는 state 검증 후 토큰 교환만 수행, 이후 이동은 POST/세션 확인으로 보호 | S-W03 vs OAuth 표준 흐름(추론) |
| SEC-A8 | 새 토큰 발급 시 이전 refresh token을 revoke하여 계정당 클라이언트별 100개 한도 소진을 방지 | #12 |

### FR (기능)
| 임시 ID | 후보 내용 | 근거 항목 |
|---|---|---|
| FR-A1 | 구글 로그인 시작/콜백/상태/해제 API(`/api/v1/auth/google/...`), 읽기·쓰기 별도 흐름, 만료 시 한국어 안내 | W-002, #1~#9 |
| FR-A2 | 반영 직전 `videos.list(part=snippet)` 재조회 → snippet 전체를 보존·병합하여 title만 교체 → `videos.update` → 재조회 검증(설명·태그·카테고리 불변 확인) | #26, #27 |
| FR-A3 | 쿼터 선예약(읽기 1 + 쓰기 50 설정값), 날짜 경계는 `America/Los_Angeles`, 큐의 "다음 날"을 PT 자정 기준으로 계산하고 서머타임 전환일(2026-11-01 추정) 테스트 | #22, #23 |
| FR-A4 | 쿼터 초과(403 `quotaExceeded`) 수신 시 배치 중지, 남은 항목을 PT 자정 이후로 재예약(몰아서 실행 금지) | #21, W-008 |
| FR-A5 | 롤백: 현재 snippet 재조회 → 현재 제목이 '반영한 제목'과 같을 때만 title 복원, 다르면 확인 요구. 롤백 예비 쿼터 설정값 | #37~#39 |
| FR-A6 | 구글 연결 해제 시 삭제 범위(토큰·인가 데이터) 안내와 실행, 보관 기간 만료 데이터의 자동 정리 작업 | POL-A2, POL-A3 |
| FR-A7 | 사후 재조회 불일치 시 즉시 실패 처리하지 않고 지연 재시도 후 `확인 보류` 상태로 표시 | #29 |
| FR-A8 | 제목 검증: 100자, `<` `>` 금지, 문자 수 기준 보수적 적용 | #28 |

---

## 3. [확인 필요] 목록 (우선순위 순)

1. **[사용자 결정] 롤백용 원본 데이터의 보관 기간**과 YouTube Developer Policies III.E.4(30일 규칙) 적용 여부 (#31). 원문 확인 + 필요 시 구글 API 팀 문의.
2. **[사용자 조작] 웹 유형 클라이언트에 `http://127.0.0.1:<포트>/...` 등록 가능 여부** (#3). 콘솔에서 바로 확인되며 실패 시 `localhost`로 전환. 데스크톱 유형 유지안(#5)도 ADR 선택지.
3. **[사용자 결정] OAuth 게시 상태** Testing 유지 vs Production (#14~#20). 프로덕션 후 refresh token 수명은 자료 상충 → 사용자 계정에서의 실측만이 해소.
4. `videos.update`의 쿼터 행 값, `videos.list`=1 (#22): 공식 표 원문.
5. 쓰기 최소 스코프(`youtube.force-ssl` vs `youtube`) (#30), 스코프별 민감/제한 분류와 `yt-analytics.readonly` 분류 (#18): Console 데이터 액세스 화면.
6. 읽기전용 필드를 되돌려 보낼 때의 서버 반응, 제목 길이 계산 단위, 변경 전파 지연, 오류 사유 (#27~#29): 승인 후 실계정 시험 1건에서 실측.
7. 개발자 정책 III.E.4 본문 문구와 버전, 철회 후 삭제 시한(7일 vs 30일) (#31, #33), 개인용 도구에 개인정보처리방침 의무가 있는지 (#34).
8. 자동 메타데이터 변경을 직접 규율하는 약관 조항 유무 (#35), 쿼터 우회 금지 조항의 원문 번호 (#25).
9. 7일 만료가 "동의 후 7일"인지 "비활동 7일"인지 (#15).
10. 개인용 1계정 앱의 검증 면제 여부 (#17).
11. refresh token 저장 모범 사례의 구글 공식 권고 (#13).
12. 테스트 사용자 100명 한도의 공식 수치 (#16).

**권고(허용 도메인)**: 클라우드 환경 네트워크 허용 도메인에 `developers.google.com`, `support.google.com`을 추가하면 위 1·4·5·7·8번 일부와 모든 사실 항목을 원문으로 재확인할 수 있다(DEC-010 후속). 재확인 결과가 다르면 규칙 F에 따라 영향 범위를 다시 산정한다.

---

## 4. 규칙 B 자체 검증 (조각 기준, 2회)

### 1차 검증: 출처·근거 점검
| 점검 | 발견한 결함 | 수정 |
|---|---|---|
| 모든 사실 행에 URL·열람 여부·확신도 존재 | #13, #29, #35는 출처 없음(미확인) 행인데 '사실'처럼 보일 수 있음 | "미확인"과 확신도 '하'로 명시, [확인 필요]에 포함 |
| 추론이 사실로 서술됨 | 초안의 "웹 유형은 `installed`→`web` 키가 달라 기존 JSON 사용 불가"를 단정형으로 적음 | "(추론, 검증 필요)"로 낮춤(#4). 쿠키 `SameSite=Strict` 콜백 문제는 SEC-A2에서 "추론"으로 표기 |
| 검색 요약이 상충하는 항목을 하나만 선택 | 프로덕션 게시 영향(#20), 7일 기준(#15), 철회 후 삭제 시한(#33), 쿼터 단가 변동 전례(#22) | 상충을 그대로 병기, 에이전트가 고르지 않음 |
| `prompt=consent`를 "refresh token 재발급 조건"으로 단정 | 검색 요약은 해당 연결을 확인하지 않았다 | #1에 "관행, 이번 검색 미확인"으로 정정 |
| 서머타임 종료일 | 출처 없는 계산 | #23에 "추론, 출처 아님" 표기, FR-A3에 "추정"으로 표기 |
| 시사점이 조사에서 도출됐는지 | SEC-A7(콜백 GET 예외)은 조사 사실이 아니라 요구사항(S-W03)과 OAuth 표준의 충돌에서 도출됨 | 근거 칸에 "추론"으로 표기 |
| 비밀값·토큰 기재 | 없음 (실제 client_id/secret/토큰 값은 어디에도 쓰지 않음) | 해당 없음 |
| 사용자 지정 7개 조사 항목 누락 | 항목 7(롤백)이 출처 없는 추론 4행으로만 구성됨 | 1-6절에서 "추론" 열을 명시하고 근거를 #26 등에 연결 |

결과: 결함 7건 발견·수정 완료.

### 2차 검증: "이 조각만 보고 기획서를 쓸 사람" 관점
| 점검 | 결과 |
|---|---|
| 요청 항목 1~7이 모두 표에 있는가 | 1(#1~#13), 2(#14~#20), 3(#9), 4(#21~#25), 5(#26~#29), 6(#31~#36), 7(#37~#40) — 있음 |
| 사용자에게 필요한 결정이 분리돼 있는가 | 결정 3건(보관 기간, 게시 상태, 웹 vs 데스크톱 유형)과 조작 1건(콘솔 URI 등록)을 [확인 필요] 1~3번에 명시. 2차에서 "웹 vs 데스크톱 유형" 선택지가 [확인 필요]에 빠졌던 것을 발견해 2번에 추가 |
| 기획자가 바로 쓸 정량 근거 | 200개 변경 = 10,000단위(기본 한도 전부), 권장 하루 10~20개 = 약 510~1,020단위(변경 50 + 사전 조회 1 가정, 설정값) 계산을 요약 4번과 FR-A3에 반영하지 못했다는 점 발견 → 아래 보강 |
| 상충 사실 보고 | #15, #20, #33, #22 병기 — 있음 |
| 다른 축 단서 | 아래 "타 축 참고" 절에 기록 |
| 결함 | 위 1건(정량 계산 누락)을 수정. 재점검 결과 추가 결함 0건 |

**정량 보강(계산, 출처 아닌 산술)**: 읽기 1·쓰기 50 가정에서 영상 1건 반영 = 51단위. 200건 전체 = 10,200단위로 **기본 일 한도(10,000)를 넘는다**(사전 목록 조회 약 8단위 별도). 기존 정책 상한 6,000단위(NFR-003)이면 하루 최대 약 117건이 이론 상한이며, 권장 하루 10~20건이면 510~1,020단위로 쿼터는 병목이 아니다. 병목은 쿼터가 아니라 **토큰 7일 만료와 보관 정책**이다.

결과: 2차 검증 PASS(수정 2건 반영 후 결함 0건). 단 원문 미열람으로 인해 **조건부(CONDITIONAL)** — DEC-010에 따라 PASS로 세지 않는 항목: 위 [확인 필요] 1~12.

---

## 5. 타 축 참고 (이 축에서 발견한 다른 축 단서)
- (규제 축) 커뮤니티 가이드라인의 '오해 소지 있는 메타데이터' 정책 위험: 일괄 제목 변경이 단속 대상이 될 수 있다는 점은 이전 조사(`docs/yt/01_policy_research.md` f)에 있고, 이번 축에서는 새 근거를 못 찾음.
- (LLM 축) AI가 만든 제목이 YouTube API 약관상 "사용자 데이터"에 해당하는 영상 설명을 외부 AI 서비스로 전송하는 경우, 개발자 정책의 제3자 공유·동의 조항(III 계열)이 적용될 수 있다 → 이번 축에서 미조사, LLM·규제 축에서 확인 필요.
- (인프라 축) `127.0.0.1` 고정, 게시 포트 고정은 OAuth 리디렉션 URI 정확 일치 규칙과 직결된다. 포트 충돌 시 대체 포트 자동 선택은 **로그인을 깨뜨리므로 금지**하거나 콘솔에 사전 등록한 후보 포트 목록으로 제한해야 한다(추론).
- (도메인 운영 축) 쿼터 경계가 PT 자정이라 한국 기준 16~17시이며 2026-11-01(추정) 전후로 한 시간 이동한다.

---

## 6. 열람 성공/실패 도메인 표

| 도메인/URL | 도구 | 결과 | 비고 |
|---|---|---|---|
| developers.google.com (web-server, determine_quota_cost, videos/update) | WebFetch | 실패: `getaddrinfo ENOTFOUND` | DEC-010와 동일. 3개 URL 시도 |
| developers.google.cn (web-server) | WebFetch | 실패: `ENOTFOUND` | 우회 시도 |
| support.google.com (cloud/answer/15549945, 7454865) | WebFetch | 실패: `ENOTFOUND` | 2개 URL 시도 |
| ktaka.blog.ccmp.jp, dev.to | WebFetch | 실패: `ENOTFOUND` | 제3자도 일부 차단 |
| github.com (nanase/kemov issue 222) | WebFetch | 성공 | 개발자 정책 III.E.4 **2차 요약**만 확인, 정책 원문 아님 |
| 위 공식 URL 전체 | WebSearch | 검색 요약만 성공 | 모든 사실의 근거는 요약. 원문 열람 0건 |
| (참고) 저장소 `src/ytitle/auth.py` | Read | 성공 | 현 스코프·InstalledAppFlow 사용 확인 |

## 7. Teardown
- 이 작업에서 만든 임시 파일·venv·컨테이너·DB·네트워크: **없음**. 쓴 파일은 이 조각 파일 1개뿐이다. 코드·설정 파일은 수정하지 않았다. `.harness-tmp/` 사용 없음(규칙 K 해당 잔여물 없음).
- 비밀값·토큰·client_id/secret 실값은 이 문서에 기재하지 않았다.
