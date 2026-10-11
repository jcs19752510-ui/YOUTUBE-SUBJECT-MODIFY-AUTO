# 보안 검증 결과서 — 웹 M1 데모 모드 (9단계)

> 판정은 **FAIL** 이다(9절). Critical 1건·High 1건이 Open 이다(DEF-9-007, DEF-9-008). 둘 다 "화면에 면책·AI 고지 문구가 없음"이라는 같은 뿌리(규칙 I·J 미반영)이며, 고치는 비용은 작지만 규칙상 축소 판단하지 않는다. **Critical/High 는 사용자가 수용(Deferred)할 수 없고, 수정한 뒤 이 단계를 재검증해야 한다**(규칙 C 보칙 2). 이 문서의 시험은 수정 즉시 재검증이 되도록(xfail strict → XPASS 로 일부러 실패) 만들어 두었다(6절 DEF-9-007·008, 부록 I).
> 이 문서는 정적 분석·코드 리뷰·**로컬 임시 환경에서의 재현**에 한정한다. 외부 침투 테스트·운영 환경(8080) 점검·실제 구글/AI 호출은 하지 않았다. **이 문서는 법률 자문이 아니다**: 면책·표시광고·AI 고지가 "법적으로 충분한가"는 판단하지 않았고, 기획서(POL-002·006·008·013)가 정한 문구가 화면에 존재하는지만 확인했다. 법적 충분성·PIA·ISMS-P 해당 여부는 "확인 필요"이며 전문가(변호사 등) 확인을 권고한다.
> 이번 완성 회차(2026-10-11)에서 이전 세션이 남긴 임시 환경(`.harness-tmp/sec`)이 사라져 있어 **venv·이미지·임시 스택·스캐너·SBOM·변이 점검을 전부 처음부터 다시 만들어 재실행**했다. 아래 숫자는 이번 회차의 재현 값이다.

## 0. 침투/동적 점검 범위 (에이전트 정의 요구)
| 항목 | 내용 |
|---|---|
| 대상 | ① 저장소 `web/backend/ytweb/**`, `web/frontend/src/**`, `web/docker/**`, `web/compose*.yaml`, `web/scripts/*.ps1`, `automation/`, 저장소 전체 비밀 점검, 의존성 잠금 파일. ② 이 코드에서 **새로 빌드한 이미지 3종**과 그 위에서 띄운 **임시 스택**(nginx → FastAPI → PostgreSQL 17). ③ 임시 SQLite 로 띄운 앱(프로세스 내 TestClient). |
| 환경 | Linux 6.18(Ubuntu 24.04), Docker 엔진 29.8.2(Linux 컨테이너)·Compose 5.6.0. 스택은 프로젝트 `harness-tmp-sec`, 호스트 `127.0.0.1:18380` 한 포트만 게시, 비밀은 임의 문자열 3개(저장소 밖). 시험용 파이썬은 3.13.16(컨테이너 런타임은 3.12.15). |
| 허용한 기법 | 코드 정독, 의존성·이미지 스캐너(pip-audit, npm audit, Trivy 0.75.0), 레지스트리 조회, **Host/Origin/Sec-Fetch-Site 위조, CSRF, 요청 밀수 패킷(원시 소켓), 경로 순회, 느린 헤더, 속도 제한 소진, 본문 크기 폭탄, JSON 깊이 폭탄, 로그인 CSRF, PIN 동시 추측**, 앱 DB 계정으로의 **권한 상승 시도 26종**(임시 DB 안에서만), 컨테이너 안에서의 쓰기·실행·네트워크 도달 시도(이 PC 안의 임시 리스너까지만), 소스 사본 변이 점검 119곳, **저장소 이력 비밀 검색(읽기 전용 `git log`/`git rev-list`/`git status` 만 사용 — 쓰기 git 명령은 쓰지 않음)**. |
| 금지·하지 않은 것 | 운영 스택(8080)·남의 컨테이너·`harness-tmp-int`/`vinf` 접촉, 실제 구글·YouTube·AI 호출, 외부 인터넷으로 가는 모든 요청(내부 망 격리는 "즉시 실패하는 연결 시도"와 설정·경로표 증거로만 확인, 제3자 서버에는 아무 패킷도 보내지 않음), 쓰기 git 명령(add/commit/push/reset 등), 운영 소스 코드 수정(시험 파일은 `web/tests_security/` 에만 추가). |
| 이 에이전트가 하지 못하는 것 → 규칙 A 알림 | **외부 침투 테스트·모의해킹, Windows Docker Desktop 실측, 실제 브라우저(CSP 위반 로그·확장프로그램) 점검, 실서비스 LLM 인젝션 시험**은 별도 승인된 전문 점검/후속 단계가 필요하다(8절·부록 H). |
| 실행 방식 | 단독 실행(병렬 웨이브 "7단계 ∥ 9단계 ∥ 11단계 대조"에서 9단계 담당; 7단계 에이전트가 같은 dockerd 에서 `harness-tmp-int` 를 동시에 사용). 카테고리 조각 모드가 아니라 전 항목을 이 문서 하나로 점검했다. 변이 점검은 코드 2분할+설정 1개로 병렬(4코어를 독점하지 않도록 3프로세스). |

## 1. 개요
- 테스트 대상: 웹 M1(데모 모드) 전체 시스템 — 백엔드·프런트·인프라·스크립트·CI 예시·의존성·이미지. 실제 구글·AI 연동 코드는 없다(M2·M3).
- 테스트 유형: **보안**
- 적용 Tier: Standard 취급(규칙 B: 최소 2회 검증 + 결함 0건 확인 회차). 속도 트랙과 무관하게 전체 코드베이스를 대상으로 했다(핸드오프 규칙).
- 적용 속도 트랙: N/A (06/07 전용)
- 병렬 실행 정보: 병렬 웨이브(7단계 `harness-tmp-int`/18080 ∥ 9단계 `harness-tmp-sec`/18380 ∥ 11단계 문서 대조)에서 실행. 공유 dockerd 를 쓰므로 Docker 객체는 `harness-tmp-sec` 접두사만 만들고 정리했다.
- 테스트 목적: 위협 모델 Part W(TW-01~36)의 "구현됨/부분/미구현"을 코드 근거와 **동작**으로 재확인하고, OWASP Top 10·컨테이너·공급망·규칙 I/J 관점의 새 결함을 찾는다.
- 관련 산출물: `docs/yt/threat_model.md` Part W, `docs/yt/DESIGN.md` Part B, `docs/yt/02_risk_assessment.md`, `웹프로그램으로수정요청.md` §9, 6단계 결과서 4건, 이전 SBOM `docs/harness/sbom-web-m1.json`, 지시서 `docs/harness/_parallel/web-verify-brief.md`.
- 테스트 수행자(에이전트): 9단계 보안 감사자(서브에이전트, 모델 Sonnet 5.5)
- 테스트 일시: 2026-10-11

## 2. 테스트 범위 및 제외 범위
- **범위(In-Scope)**: 인증·세션·CSRF·Host/Origin, 입력 검증·SQL, XSS·CSV·AI 출력 처리, 프롬프트 인젝션(규칙 J, 모의 AI), 승인 HMAC·감사 로그 무결성, 비밀 관리·로그 마스킹·오류 노출, 속도·크기 제한, 컨테이너 격리·네트워크·DB 권한, 의존성 취약점·환각(slopsquatting)·라이선스·SBOM, 이미지 취약점·내용물, CI/자동화 예시, 규제 도메인(규칙 I) 문구 반영, 개인정보·보관·파기, 접근권한·로그 보관·사고 대응 근거.
- **제외 범위와 사유**
  | 제외 | 사유(유형) | PASS 로 세지 않음 |
  |---|---|---|
  | Windows Docker Desktop·PowerShell 5.1·Windows ACL 실측 | 환경 없음(클라우드 Linux) — 미수행 | 예 |
  | 실제 브라우저(Chrome/Edge)의 CSP 위반·확장프로그램(TW-24)·`SameSite`/`Sec-Fetch-Site` 실동작 | 브라우저 미사용 — 미수행(7단계 Chromium 시험에 위임) | 예 |
  | 실서비스 LLM 프롬프트 인젝션 시험 세트(SEC-030) | M1 은 모의 AI — 대상 자체가 없음(M3 에서 수행) | 해당 없음 |
  | OAuth·구글 API(TW-05, S-W08) | 코드 없음(M2) | 해당 없음 |
  | 외부 침투 테스트·운영 환경 점검 | 이 에이전트의 권한 밖 — 별도 승인 필요(규칙 A) | 미수행 |
  | 이미지 서명(cosign) 검증, Trivy 도구 자체의 서명 검증 | 도구 없음 — 미수행(8절) | 예 |
  | 재시작 중 이중 반영·장시간 부하 | 7단계 몫 | 위임 |
  | Windows 에서의 호스트 게이트웨이 도달(DEF-9-011)의 의미 | Linux 엔진에서만 실측. Docker Desktop(WSL2) 에서는 게이트웨이가 Windows 호스트가 아니라 Docker VM 쪽일 수 있어 결과가 다를 수 있음 — 미수행 | 예 |
| Docker Scout | `docker scout` 명령이 이 환경에 없음(미설치·로그인 필요) — Trivy 로 대체, Scout 결과는 **미수행** | 예 |
| `npm audit signatures`·이미지 서명(cosign)·Trivy 서명 | 서명 키 조회 불가/도구 없음 — 미수행 | 예 |
| `node:22-bookworm-slim` 태그의 오늘 다이제스트 재확인 | 레지스트리 429(요청 한도) — 미수행(고정값 `c3de60bf…` 은 이전 세션 기록) | 예 |

## 3. 테스트 환경
- **실행 환경**: 위 0절. 도구 버전 — pip-audit 2.10.1, npm 10.9.4/node 22.22.0, **Trivy 0.75.0**(`aquasec/trivy:latest`, 다이제스트 `sha256:af6acf9a6b85dfe389a1941505c0ce9efef52a4719635e1a962f022a3d855daa`, 취약점 DB `mirror.gcr.io/aquasec/trivy-db:2` 2026-10-11 내려받음, 스캐너 컨테이너에는 프록시 CA 를 읽기 전용으로 마운트 — TLS 검증은 끄지 않음), cyclonedx-bom 7.5.0, @cyclonedx/cyclonedx-npm 6.0.1, pytest 9.1.1(저장소 잠금 파일 그대로, 해시 강제 설치). 시험용 파이썬 3.13.16.
- **이미지**(저장소 `web/docker/*.Dockerfile` 의 사본에 builder 단계의 CA 2줄만 더해 빌드 — 최종 단계 동일; 저장소 Dockerfile 은 수정하지 않음): `harness-tmp-sec-api:local` `sha256:4f68b1c5…`(299 MB), `-web:local` `sha256:57024d9e…`(91 MB), `-db:local` `sha256:5a79de4d…`(632 MB). 런타임: Python 3.12.15, nginx 1.30.5, PostgreSQL 17.11. 스택은 compose 사본(호스트 포트만 18380 으로 변경)·임의 비밀 3개(`.harness-tmp/sec/stack/secrets`, 저장소 밖)로 기동했다.
- **테스트 데이터**: 데모 시드(`seed_demo`, 가짜 영상 60~200개), 시험이 만드는 가짜 제안·승인·배치. 임시 비밀 3종(임의 64자). 실제 개인정보·실제 채널 데이터 없음.
- **전제 조건**: 6단계 4건 결과서 존재(백엔드 PASS 2·프런트 CONDITIONAL·인프라 CONDITIONAL → 이후 DEF-VI-001 은 네트워크 3분리로, 프런트 B01 은 백엔드 DEF-VA-010 으로 해소 보고). 7단계는 병렬로 진행 중이므로 이 문서는 7단계 결과에 의존하지 않는다.
- **재실행 방법**: `web/tests_security/README.md` (오프라인 약 2분, 실스택 약 3분, 변이 점검 약 1시간).

## 4. 테스트 케이스 및 결과
> 시험 코드는 `web/tests_security/` (6파일 + `mutation_check.py` + `sbom_from_npm_lock.py`). 개별 항목은 시험 함수 단위(총 **174개 함수 / 파라미터 포함 313건**: 01=91, 02=93, 03=28, 04=86, 05=12, 06=3)이며 아래는 묶음 ID 이다. 최종 실행 결과: **통과 298 · xfail(결함 확인용 기대 실패) 15 · 실패 0 · 오류 0** (오프라인·정적 224건 중 05 의 번들 4건은 스택이 필요해 live 회차에서 실행). "Pass(재현)" 는 알려진 한계·결함이 의도대로 **재현**됐다는 뜻이고, `xfail` 은 "바람직한 동작" 시험이 결함 때문에 실패한 것(결함 확인용)이다.

| ID | 시나리오 | 사전조건 | 실행 절차 | 예상 결과 | 실제 결과 | Pass/Fail | 비고(관련 ID) |
|----|----------|----------|-----------|-----------|-----------|-----------|------|
| TC-S9-001 | 불허 Host 9종(evil.com·포트 틀림·`127.0.0.1:8080.evil.com`·IPv6·빈 값…)으로 API 호출 | 임시 앱 | `test_host_not_allowed_is_403_for_api` | 403 `host_not_allowed` | 9/9 | Pass | TW-02, S-W02 |
| TC-S9-002 | Host 헤더 2개, 대소문자, 헬스 4경로만 Host 면제 | 〃 | `duplicate_host…`, `allowed_hosts_case…`, `health_is_the_only…` | 중복 거부, 면제는 헬스뿐 | 통과 | Pass | TW-02 |
| TC-S9-003 | Origin 11종(없음·null·https·`@evil`·포트 틀림…)으로 세션 발급 | 〃 | `session_issue_requires_exact_origin` | 403 `origin_not_allowed`, 쿠키 미발급 | 11/11 | Pass | TW-01, S-W02 |
| TC-S9-004 | `Sec-Fetch-Site` cross-site/same-site/none/빈 값/복합 → 거부, same-origin → 허용 | 〃 | `rejects_non_same_origin_fetch_site`, `allows_same_origin` | 403 `cross_site_request` | 5+1 | Pass | TW-01 |
| TC-S9-005 | 쿠키 속성(HttpOnly·SameSite=Strict·Path=/api·Max-Age, Secure 없음=설계), 거부된 교차 출처 요청은 감사에 안 남음 | 〃 | `cookie_flags`, `login_csrf_rejection…` | 설계대로 | 통과 | Pass | TW-01·20, S-W04 |
| TC-S9-006 | **상태 변경 라우트 전수**(OpenAPI 의 POST/PUT/PATCH/DELETE) × {CSRF 없음, 틀린 토큰, 교차 출처 Origin, same-site} | 세션 보유 | `every_state_changing_route_rejects_missing_csrf` | 모두 403(코드별) | 전부 | Pass | TW-01, S-W03 |
| TC-S9-007 | 다른 세션의 CSRF 토큰 재사용 | 두 세션 | `csrf_token_of_other_session…` | 403 | 통과 | Pass | TW-01 |
| TC-S9-008 | 미인증 GET 전수 401, GET 이 DB 상태를 바꾸지 않음, `/auth/me` 무쿠키 | 임시 앱 | `unauthenticated_get_routes_all_401`, `get_routes_do_not_change_state`, `me_endpoint…` | 401, 행 수 불변 | 통과 | Pass | 인가 경계, S-W03 |
| TC-S9-009 | 세션 고정(공격자 지정 쿠키 무시), 토큰 sha256 저장·256비트, 로그아웃 서버 삭제·재사용 실패, 12시간 절대 만료·활동으로 연장 안 됨, 5 KB 쿠키 | 〃 | `session_fixation…`, `session_token_not_stored…`, `logout…`, `absolute_expiry…`, `activity_does_not_extend…`, `oversized_cookie…` | 설계대로 | 통과 | Pass | TW-20 |
| TC-S9-010 | **세션 상한 20: 21개 로그인으로 소유자 세션 축출**, 유휴 11시간 59분 뒤에도 유효 | 〃 | `session_cap_evicts…`, `…documented_idle_gap` | 축출·유휴 만료 없음이 재현됨 | 재현 | Pass(재현) | **DEF-9-003**, TW-03·20 |
| TC-S9-011 | PIN: 5회 실패 잠금·정상 PIN 도 잠금 중 거부·잠금 배증/상한 1시간·**설정 API 경로로 추측해도 잠금**·형식 9종·변경/해제는 현재 PIN 필요+다른 세션 폐기·PIN 값 감사/로그 무기록·scrypt | 〃 | `pin_*` 8함수 | 설계대로 | 통과 | Pass | TW-04·30, S-W02 |
| TC-S9-012 | 속도 제한: 세션 발급 10/분, 교차 출처 요청은 별도 한도(자체 상한 포함) | 시계 제어 | `session_issue_rate_limit…`, `foreign_origin_flood_has_its_own_cap` | 11번째 429, 교차 출처 30건 후 429 | 통과 | Pass | TW-25 |
| TC-S9-013 | 본문 1 MB 초과(고정/chunked), Content-Length 변형 8종(`-1`·`+5`·`1_0`·`0x10`…)·중복 | 〃 | `body_size_limits`, `bad_content_length…`, `duplicate_content_length…` | 413/400 | 통과 | Pass | TW-25 |
| TC-S9-014 | 보안 헤더(성공·404·422·429·교차 Host 응답) | 〃 | `security_headers_on_success_and_error_paths` | 7종+API no-store | 통과 | Pass | TW-23 |
| TC-S9-015 | `/docs`·`/redoc`·`/openapi.json`·`/admin`·`.env` 등 11경로 비노출, 웹소켓 1008, CORS 헤더 없음 | 〃 | `no_docs_or_admin_surface`, `websocket_rejected…`, `cors_not_enabled…` | 404/401/403, 1008 | 통과 | Pass | TW-34 |
| TC-S9-016 | 오류 본문 비노출(스택·경로·DB·비밀), 422 입력 에코 없음, JSON 깊이 폭탄(20만 중첩) 400, 큰 정수 입력의 응답 누설 없음·서버 생존 | 〃 | `error_bodies_do_not_leak…`, `422_does_not_echo…`, `json_depth_bomb…`, `huge_integers_never_leak…` | 누설 0 | 통과 | Pass | TW-17, S-W09 |
| TC-S9-017 | **상한 없는 정수 ID/페이지**(`99999999999999999999999`) → 4xx 기대 | 〃 | `huge_integers_are_client_errors_not_500` (xfail strict) | 4xx | **HTTP 500**(일반 문구, 누설 없음) | xfail(결함) | **DEF-9-001**, S-W13 |
| TC-S9-018 | 정적 파일 모드 경로 순회 11종, 오픈 리다이렉트 6종 | 정적 폴더 | `static_mode_path_traversal`, `no_open_redirect…` | 파일 미반환, 외부 Location 없음 | 통과 | Pass | 경로 순회 |
| TC-S9-020 | **M1 전체 흐름이 외부 연결을 전혀 시도하지 않음**(소켓 connect·DNS 차단 상태로 제안→승인→배치→반영→CSV) | 소켓 차단 | `full_flow_makes_no_network_calls` | 오류 없이 완료, mode=demo | 통과 | Pass | TW-35, TB-5·6, SEC-022 |
| TC-S9-021 | SQL 인젝션 페이로드 9종 × GET 9경로 + 쓰기 5경로, 행 수 불변, 소스에 문자열 조립 SQL 없음 | 〃 | `sql_injection_payload_sweep`, `no_raw_sql_string_building…` | 500 없음, 테이블 유지 | 통과 | Pass | TW-09, S-W13 |
| TC-S9-022 | XSS: `<script>`·`<img onerror>`·`<svg onload>` 제목 → 검증기가 차단·승인 불가, API 응답은 JSON·nosniff·CSP none, 메모 단일 행 | 〃 | `html_in_titles…`, `api_responses_are_never_html…`, `batch_note_html…` | 차단 409 | 통과 | Pass | TW-11, LLM05 |
| TC-S9-023 | 승인자 이름: HTML 문자 허용(텍스트로만 표시), 제어·방향 문자·41자 거부, **제로폭 문자 허용** | 〃 | `approver_name_controls…`(7), `approver_zero_width…` | 제로폭은 거부돼야 함 | 제로폭 통과 | Pass(재현) | **DEF-9-004**, TW-16 |
| TC-S9-024 | CSV 수식 주입: 단위 7종, 전 셀·주석 행·외부에서 온 값 | 〃 | `csv_safe_unit`, `csv_export_neutralizes…`, `csv_notes_and_titles…` | 모든 셀 `'` 접두 | 통과 | Pass | TW-10 |
| TC-S9-025 | AI 입력 요약: 링크·이메일·전화·주민번호 마스킹, 500자, 제어/방향 문자 제거; 어댑터 입력은 영상 ID·제목·요약뿐 | 〃 | `build_summary…`, `prompt_input_is_data…` | 마스킹 | 통과 | Pass | SEC-021·026, LLM01·02 |
| TC-S9-026 | 악성 AI 출력 11종(링크·이메일·전화·제어문자·301자·중복·비문자열·`tool_calls`·잘못된 topic·과대 evidence) 정제, `<>` 후보는 blocked, **AI 가 topic=life 로 속여도 건강 키워드면 엄격 모드**, 말투 설정 제어문자·길이 | 〃 | `malicious_ai_output…`, `ai_output_with_angle…`, `ai_cannot_downgrade_strict…`, `tone_setting…` | 안전한 후보만 남음 | 통과 | Pass | SEC-023·024, LLM05·06, 규칙 J |
| TC-S9-026b | **엄격 모드는 25개 키워드에 의존**: 목록 밖 건강 용어(허리·무릎)+AI topic=life → 엄격 모드 꺼짐 | 〃 | `strict_keyword_list_gap_is_documented` | (한계) 경고만 | 재현 | Pass(재현) | OBS-3, SEC-024, Q-W10 |
| TC-S9-027 | 승인 변조: DB 에서 approver/plan_hash/mac/만료 연장, HMAC 키 삭제·손상, 키 파일 0600, **1회용 플래그**, 상태 우회, 만료 경계(±1초), 제목 수정·영상 변경 시 무효, 대기열/반영 후 제목 수정 불가, 미승인 제안·50건 초과 배치 불가 | 〃 | `db_level_approval_tamper…`(3), `expiry_extension…`, `missing_or_corrupt_hmac…`, `check_approval_gate…`, `used_approval…`, `title_edit_or_video_change…`, `title_cannot_be_edited…`, `unapproved_suggestions…` | 전부 fail-closed | 통과 | Pass | TW-07, SEC-025, POL-011 |
| TC-S9-028 | 멱등성(재생·본문 다른 재사용 422·키 형식), 설정 API 로 live/모드/내부 키 쓰기 9종 거부·정수 경계 10종·환경으로 live 선택 불가 | 〃 | `idempotency_replay…`, `settings_cannot_enable_live…`, `daily_cap_bounds`, `live_mode_cannot…` | 400/422 | 통과 | Pass | TW-06·33, POL-010 |
| TC-S9-029 | 감사 체인: 행 수정·중간 삭제·`prev_hash` 열 수정 탐지; **DB 소유자 재계산·꼬리 절단은 탐지 불가(재현)**; 보안 이벤트가 비밀 없이 기록 | 〃 | `audit_chain_detects…`(3), `audit_limitation_repro…`, `audit_records_security_events…` | 탐지 / 한계 재현 | 통과 | Pass(재현) | **DEF-9-014**, TW-08, S-W16 |
| TC-S9-030 | 배치 실행 확인 문구(6종 틀린 값 422), 롤백 영상 ID 재입력·이중 롤백·후속 변경 시 거부 | 〃 | `batch_execute_requires_exact_confirm_text`, `rollback_requires_typed_id…`, `rollback_refused_when_a_later…` | 거부 | 통과 | Pass | TW-14 |
| TC-S9-030b | **롤백이 Studio 에서 따로 고친 제목·설명을 덮어씀** (바람직: 거부) | 〃 | `rollback_should_refuse…`, `rollback_should_not_overwrite…`(xfail), `rollback_repro_overwrites…`(재현) | 409 | **덮어씀(201)** | xfail(결함)+재현 | **DEF-9-002**, TW-14 |
| TC-S9-031 | `planned` 잔류 → 그 영상의 새 배치 차단, 해제 API 없음 | 〃 | `stuck_planned_change…` | fail-closed | 재현 | Pass(재현) | OBS-4 |
| TC-S9-032 | 로그 마스킹 12형식·extra·예외 문자열, 정규식 선형성(악의적 입력 6종 5초 이내), 요청 로그에 PIN·쿠키·본문·쿼리 없음 | 〃 | `log_masking_*`, `request_logs_do_not_contain…` | 비밀 미노출 | 통과 | Pass | TW-17, S-W09 |
| TC-S9-033 | 조회(GET)가 승인 만료 정리(쓰기)를 수행 | 〃 | `get_requests_expire_stale_approvals…` | (정보) | 재현 | Pass(재현) | OBS-5, S-W03 |
| TC-S9-040 | 현재 파일 트리 비밀 패턴 14종 0건, 비밀형 파일 0건, `.gitignore`·`.dockerignore` 필수 항목 | 정적 | `test_sec_03` 4함수 | 0건 | 통과 | Pass | TW-18, D-05 |
| TC-S9-040b | `.gitignore` 에 `client_secret*.json` 이 없음 | 정적 | `gitignore_has_client_secret_pattern`(xfail) | 있어야 함 | 없음 | xfail(결함) | **DEF-9-006**, TW-18 |
| TC-S9-041 | Dockerfile: 다이제스트 고정·`latest` 없음·최종 단계 비루트·원격 스크립트 없음·해시 강제·`npm ci --ignore-scripts`·소스맵 삭제 | 〃 | 4함수 | 충족 | 통과 | Pass | TW-13, D-04, S-W11 |
| TC-S9-042 | compose: 5개 서비스 하드닝(읽기 전용·cap_drop·no-new-privileges·비루트·자원 상한·로그 상한)·게시는 web 127.0.0.1:8080 하나·망 3분리+edge 는 web 만·비밀은 `*_FILE`·docker.sock 없음 | 〃 | 5함수 | 충족 | 통과 | Pass | TW-31·21, D-02·03·06·10 |
| TC-S9-043 | nginx 규칙(Host 444·location 별 보안 헤더 include·정확한 헤더 값·CSP 지시자·업스트림 상수)·DB 설정(pg_hba trust 없음·리터럴 비밀번호 없음·역할 속성) | 〃 | `nginx_conf_rules`, `db_configs…` | 충족 | 통과 | Pass | TW-23·21 |
| TC-S9-044 | 파이썬 잠금 3개(고정·해시·직접 URL 없음, 주석 처리된 해시는 해시 아님), `package.json` 정확 버전·`package-lock` 레지스트리 전용·설치 스크립트는 fsevents(dev 선택) 뿐 | 〃 | 4함수 | 충족 | 통과 | Pass | S-W11, TW-13 |
| TC-S9-045 | 프런트 소스: DOM 주입·저장소·eval·외부 URL·CDN·원격 폰트·`fetch` 는 `client.ts` 뿐·ESLint 금지 규칙·소스맵 없음·테스트 제외 빌드 | 〃 | 5함수 | 충족 | 통과 | Pass | TW-11, S-W05, F-04·05 |
| TC-S9-046 | PowerShell 8개 스크립트: 위험 구문 없음·파괴 작업 확인 문구·종료 스크립트에 `-v` 없음·`pin-digests` 접속처 2곳뿐 | 〃 | 1함수 | 충족 | 통과 | Pass | TW-29·12 |
| TC-S9-047 | CI 예시: `.github` 없음(활성 CI 없음), 예시 워크플로의 권한·고정 갭 | 〃 | `ci_files_inventory…` | (갭 재현) | 재현 | Pass(재현) | **DEF-9-005** |
| TC-S9-050 | 게시 범위: `docker port`·`/proc/net/tcp`·이 호스트의 비-루프백 주소 연결 거부·다른 서비스 포트 없음 | 실스택 | `port_is_published_on_loopback_only` | 127.0.0.1 만 | 통과 | Pass | S-W01, D-02 |
| TC-S9-051 | nginx Host 불허 7종·중복 Host·HTTP/1.0·절대 URI → 무응답(444) | 〃 | `nginx_drops_unapproved_hosts…`(7) 외 2 | 무응답 | 통과 | Pass | TW-02 |
| TC-S9-052 | 메서드(TRACE·CONNECT·PROPFIND·PUT·DELETE…) 정적·API, CORS 사전 요청 | 〃 | `methods_on_static_paths`(8), `exotic_methods_on_api`(5), `options_cors…` | 403/405/501 | 통과 | Pass | TW-25 |
| TC-S9-053 | **요청 밀수/비정상**: CL+TE, 중복 CL, TE 변형 2종, 음수 CL, 헤더 이름 공백, 개행 단독, NUL | 〃 | `request_smuggling_and_malformed_requests` | 응답 1개 이하·거부 | 통과 | Pass | TW-02·25 |
| TC-S9-054 | 정적 경로 탐침 21종(`/.env`·`/.git/config`·`%2e%2e`·`/proc/self/environ`·`.map`·소스 경로…)과 디렉터리 리다이렉트 | 〃 | `static_path_probes_never_leak_files`(21), `open_redirect…` | SPA 인덱스 외 반환 없음 | 통과 | Pass | TW-18·23 |
| TC-S9-055 | 9 KB URL·헤더, 2 MB 본문, chunked 폭탄, **느린 헤더(10초)** 연결 종료 | 〃 | `oversize_…`, `slowloris_…` | 400/413/408/종료 | 통과 | Pass | TW-25 |
| TC-S9-056 | 11개 location + nginx 가 만든 오류(413·405) 의 보안 헤더 7종, 버전 비노출 | 〃 | `security_headers_on_every_location`(11), `…nginx_generated_errors` | 7종 | 통과 | Pass | TW-23 |
| TC-S9-057 | nginx 경유 세션·CSRF·Origin·Sec-Fetch-Site, `/docs` 류 비노출, `X-Forwarded-*` 위조 무효 | 〃 | `session_cookie_and_csrf_over_nginx`, `docs_and_openapi…`, `forwarded_header_spoofing…` | 설계대로 | 통과 | Pass | TW-01·34 |
| TC-S9-058 | PostgreSQL 에서의 큰 정수 입력 | 〃 | `huge_integers_are_client_errors_on_postgres`(xfail), `server_survives_500_probes…` | 4xx | **500, 누설 없음, 서버 생존** | xfail(결함) | **DEF-9-001** |
| TC-S9-059 | 컨테이너 하드닝 실측 4개: Privileged false·ReadonlyRootfs·CapDrop ALL·**CapEff=0**·no-new-privileges·seccomp 해제 없음·비루트 uid(10001/101/999)·자원 상한·docker.sock/호스트 경로 마운트 없음; 루트/`/app` 쓰기 실패·`/tmp` 실행 불가·su/sudo 불가 | 〃 | `container_hardening_runtime_flags`(4), `runtime_identity_caps_and_writability` | 충족 | 통과 | Pass | TW-31, S-W14, D-03 |
| TC-S9-060 | 비밀: 서비스별 마운트 최소(api·worker=앱 비번만, web=없음, db=3개)·HMAC 키 볼륨은 api·worker 만·**inspect/env/cmdline/이미지 히스토리/컨테이너 로그에 비밀 3종·세션·CSRF 토큰 없음**·nginx 접근 로그에 쿼리 없음 | 〃 | `secrets_mounts…`, `no_secret_values_in_inspect…`, `secret_values_not_in_container_logs…` | 0건 | 통과 | Pass | TW-18, S-W08, D-05·06 |
| TC-S9-061 | 네트워크 격리 행렬(api→db 허용, api/worker/db→외부 즉시 실패, worker→web 불가, **web→db 이름·IP 모두 불가**, web→api 허용)·망 플래그(front/back internal, edge 비-internal, edge 에는 web 만)·web 기본 경로 존재 | 〃 | `network_isolation_matrix`, `docker_network_flags…` | 설계대로 | 통과 | Pass | TW-21·36, D-10 |
| TC-S9-062 | **앱 DB 계정 권한 공격 26종**(audit UPDATE/DELETE/TRUNCATE, 버전표 변경, DDL, COPY PROGRAM, 파일 읽기, pg_authid, ALTER ROLE, SET ROLE, ALTER SYSTEM, lo_import, 트리거 끄기…) 전부 거부; 속성 `f\|f\|f\|f\|f`; 다른 DB·owner·postgres(네트워크) 로그인 거부; scram·log_statement=none | 〃 | `app_role_attributes…`, `app_role_cannot_reach…`, `db_runtime_settings…` | 거부 | 통과 | Pass | TW-21·32, S-W13a, D-07a |
| TC-S9-062b | 앱 계정은 `changes`·`approvals` 등 감사 외 표를 UPDATE/DELETE 할 수 있음 | 〃 | `known_limit_app_role_can_modify…` | (한계) | 재현 | Pass(재현) | **DEF-9-014**, TW-08·32 |
| TC-S9-063 | 백업 스크립트에 파일 이름으로 명령/경로 주입 16종 × 4개 명령 거부, 정상 덤프는 600 권한이고 **비밀번호·서명 키 흔적 없음** | 〃 | `ytweb_db_admin_script…`, `ytweb_db_dump_and_list…` | 거부 / 무비밀 | 통과 | Pass | TW-12·19, S-W13a |
| TC-S9-064 | PostgreSQL 위 전체 흐름: 불러오기 작업→제안→승인, HMAC 키 `600 10001:10001`, 감사 체인 정상, 실스택 XSS 제목 차단·CSV 헤더 | 〃 | `end_to_end_flow_on_postgres…`, `xss_and_csv_payloads…` | 정상 | 통과 | Pass | TW-07·08·10 |
| TC-S9-065 | **PIN 동시 추측(PostgreSQL advisory lock)**: 10개 동시 오답 중 401 ≤ 5, 이후 잠금 | 〃 | `pin_guess_race_is_serialized_on_postgres` | ≤5 | 통과 | Pass | TW-04 |
| TC-S9-066 | nginx 속도 제한: 140회 폭주 시 429, 세션 발급 10/분 | 〃 | `zz_nginx_rate_limits_trigger` | 429 | 통과 | Pass | TW-25 |
| TC-S9-070 | pip-audit 5개 요구 파일 + core 해석 환경(29패키지) | 도구 | 부록 B | 취약점 0 | 0 (**감도 확인**: 알려진 취약 버전 입력 시 PYSEC 다수 검출) | Pass | TW-13, S-W11 |
| TC-S9-071 | npm audit 전체 384·운영 의존 9 | 도구 | 부록 B | 0 | 0 (**감도 확인**: lodash 4.17.15 입력 시 high 검출) | Pass | 〃 |
| TC-S9-072 | 환각(slopsquatting)·무결성: Py 36(고유)·npm 384 전부 레지스트리 실존, **잠금 해시가 레지스트리 파일 해시와 일치**, 고아 패키지 0, 타이포 후보 0, 내부 이름(`youtube_title`·`ytweb`) 레지스트리 미점유 | 도구 | 부록 B | 전부 실존 | 전부 | Pass | S-W11, TW-13 |
| TC-S9-073 | Trivy 이미지 3종(취약점·비밀·설정·라이선스) | 도구 | 부록 C | 비밀 0 | 비밀 0 / 취약점은 DEF-9-009·010 | Pass(결함 별도) | D-11, TW-13 |
| TC-S9-074 | Trivy 파일 트리 비밀 0·Dockerfile 설정(LOW 1: db 이미지 HEALTHCHECK 없음 — compose 에 있음) | 도구 | 부록 C | 0 | 0 | Pass | TW-18 |
| TC-S9-075 | 이미지 내용물: 소스맵·테스트·`.env`·비밀·`.git` 없음, 세계 쓰기 파일 0, 앱 비밀 폴더 0700 | 도구 | 부록 C | 없음 | 없음(단, 개발용 `requirements*.txt` 포함) | Pass | D-04·05 |
| TC-S9-076 | SBOM 6종 생성(이미지 3 + 파이썬 런타임 + npm 2), 이전 SBOM 검토 | 도구 | 부록 D | 산출 | 산출 | Pass | D-11 |
| TC-S9-077 | 변이 점검: 코드 74곳 + 설정 45곳(합 119) | 도구 | 부록 E | 마지막 회전 놓침 0 | **코드 73 killed + 동치 대조군 1 생존(정상), 설정 45/45 killed, 놓침 0·오류 0** (이번 회차 재실행) | Pass | 규칙 B |
| TC-S9-078 | 수동 프로브: web→호스트 게이트웨이, internal 망 게시 불가, `isolated` 모드 불가, nginx 오류 로그 요청 줄, 경로 변형 POST 307 | 실스택 | 8절 | — | 아래 DEF-9-011·016 | Pass(결함 별도) | TW-36, DEF-VI-003 |
| TC-S9-079 | **규칙 I·J 문구 반영**: POL-002 면책·POL-006 AI 고지·POL-008 표시광고/한계·POL-013 A/B 확인이 `ko.ts`·화면 연결·빌드 번들에 있는가. 이미 구현된 POL-005(데모 배지)·AI 제안 배지·엄격 모드 안내·서버 사전 점검 A/B 경고는 회귀 방지로 통과해야 함 | 소스 + 실스택 번들 | `test_sec_05_regulatory_ai_notice.py` (12건) | 문구 존재·연결 | 구현분 4건 통과, **필수 문구 8건 xfail(없음)**. 번들 문자열 직접 검색: 법률 자문 0·면책 0·최종 책임 0·AI가 생성 0·표시광고 0·A/B 0 (데모 모드 3, AI 제안 8, 민감 주제 1). 수정 모사 사본(문구 추가)에서 5건이 XPASS 로 바뀜을 확인(시험이 공허하지 않음) | xfail(결함) | **DEF-9-007·008**, POL-002·006·008·013 |
| TC-S9-080 | 이미지 내용물 재검사(이번 회차 직접): web 에 소스맵·테스트 0·세계 쓰기 파일 0·비루트(101), api 에 `.env`·테스트·소스맵 없음·세계 쓰기 0·비루트(10001), db `/backups` 0700 | 실스택 | `docker run --entrypoint sh` | 없음 | 충족. 단 api 이미지에 `/app/backend/.ruff_cache`·`.coverage`·`pyproject.toml`·`requirements*.txt` 포함 | Pass(결함 별도) | **DEF-9-017**·DEF-9-009 |
| TC-S9-081 | `.dockerignore` 가 비밀형(`*.pem`·`*.key`·`credentials*.json`)·개발 캐시를 거르는가 | 정적 + 이미지 | `dockerignore_covers_…`, `api_image_has_no_dev_cache…` | 있어야 함 | 없음(거부 목록 방식) — 두 시험 모두 올바른 이유로 실패(`--runxfail` 로 확인: 누락 항목 5개·`/app/backend/.ruff_cache`·`.coverage`) | xfail(결함) | **DEF-9-017**, D-05, TW-18 |
| TC-S9-082 | nginx 오류 로그가 요청 줄(쿼리)을 남기는가(api 정지 → `?code=CANARY…` 요청 → 로그 검색) | 실스택 | `nginx_error_log_keeps_query…_repro` | (한계) | 오류 로그에 쿼리 포함, 접근 로그에는 없음 — 재현 | Pass(재현) | **DEF-9-016**, TW-17 |
| TC-S9-083 | 컨테이너→호스트 게이트웨이 도달(이 PC 의 0.0.0.0 임시 리스너): web(edge)·**api/worker/db(internal back)·web(front)** 모두 자기 망 게이트웨이:포트 OPEN, 127.0.0.1 전용 리스너 CLOSED | 실스택 | `web_container_reaches_host_gateway…_repro` + 수동 4개 망 | (한계) | **internal 망 컨테이너도 도달(범위 확대)** — 재현 | Pass(재현) | **DEF-9-011**, TW-36, D-10 |
| TC-S9-084 | **저장소 이력 비밀 검색**(읽기 전용 git, 96커밋 전 브랜치): 비밀형 파일명(`.env`·`token*.json`·`client_secret*`·`*.pem`·`*.key`·`data/`·DB 덤프) 이력 0건, 비밀 패턴(AIza·sk-ant·개인키·ghp_·AKIA·xox·ya29.·1//0·googleusercontent 클라이언트 ID·refresh_token) 일치는 전부 명백한 시험 더미(`FAKE…`·`EXAMPLE`·`topsecretvalue`) | 정적 | 부록 K | 0 | 실제 비밀 0 | Pass | TW-18, S-W08 |
| TC-S9-085 | Trivy fs 비밀·설정 스캔(저장소 전체, `.git`·`node_modules`·`.harness-tmp` 제외) | 도구 | 부록 K | 0 | 비밀 0, 설정 LOW 1(db.Dockerfile HEALTHCHECK 없음 — compose 에 정의) | Pass | TW-18 |
| TC-S9-086 | 임시 스택 `/api/healthz`·`/api/readyz` 비인증 응답 | 실스택 | curl | 최소 정보 | `/api/readyz` 가 `{"status","db","mode":"demo"}` 를 인증 없이 반환(Host 허용된 요청만) | Pass(관찰) | OBS-10 |

## 5. 커버리지
- **점검 항목 체크리스트(에이전트 정의의 최소 항목)** — 전부 수행. 결과는 아래 한 줄 요약이며 근거는 4절·부록이다.
  | 최소 점검 항목 | 수행 | 결과 |
  |---|---|---|
  | 위협 모델 대응 확인(TW-01~36 전부) | 예 | 부록 A. 구현됨 19(한계·의존 표기 포함)·부분 13·해당 없음 2·수용 대기 2·미구현 0. 모델에 없던 새 표면 → 부록 G (규칙 F 요청) |
  | CI·자동화(`automation/`, `.github/`) | 예 | `.github` 없음(활성 CI 없음). 예시 워크플로 갭 → DEF-9-005 |
  | 인증/인가 우회·권한 경계 | 예 | 단일 소유자 구조(수평/수직 권한 개념 없음, IDOR 대상 없음). 세션·CSRF·Host·Origin·PIN 우회 시도 전부 실패. PIN 꺼짐 시 같은 PC 프로세스는 세션 취득 가능(TW-03, 수용 질문) |
  | 인젝션(SQL/커맨드/XSS 등)·입력 검증 | 예 | SQL·XSS·CSV·파일 이름 명령 주입·헤더 주입 모두 불성립. 입력 검증 갭 = DEF-9-001(정수 상한) |
  | 시크릿/자격증명 | 예 | 하드코딩·로그·이미지·inspect·덤프 노출 0, **현재 트리(Trivy fs+자체 14패턴)와 저장소 전체 이력(96커밋, 읽기 전용 git)에서 실제 비밀 0**(부록 K). 방지 장치 갭 = DEF-9-006(.gitignore)·DEF-9-017(.dockerignore 거부 목록) |
  | 의존성 취약점(CVE) | 예 | pip-audit·npm audit 0건(감도 확인 포함). 이미지 OS 패키지는 DEF-9-009·010 |
  | **의존성 환각** | 예 | Py 36+npm 384+베이스 이미지 4 전부 실존·해시 일치. 신선도 갭 = DEF-9-015 |
  | 민감정보 저장/전송 암호화 | 예 | 저장(볼륨)·백업·내부 구간 TLS 없음 — 문서화된 설계(README §9). 쿠키 `Secure` 없음(http 로컬). DEF-9-013 |
  | 에러 메시지 정보 노출 | 예 | 앱 오류는 일반 문구. nginx 오류 로그 요청 줄에 쿼리 → DEF-9-016 |
  | 설계서 보안 원칙 vs 구현 | 예 | 불일치: TW-18 의 ".gitignore 에 client_secret" 서술(DEF-9-006), TW-08 서술은 README 정정으로 해소 |
  | 개인정보 컴플라이언스 | 예 | M1 은 합성 데이터라 처리 대상 개인정보가 사실상 없음. 보관·파기·백업 암호화 미구현 → DEF-9-013. **PIA·ISMS-P 해당 여부는 판단하지 않음 — "확인 필요"**, 전문가 확인 권고 |
  | 라이선스 | 예 | 부록 B-4. 충돌 없음(비배포 로컬 사용). 재배포 시 LGPL/GPL 고지 필요 |
  | **SBOM** | 예 | `docs/harness/sbom-web-m1/` 6종(이미지 3종 CycloneDX 1.7, 나머지 1.6). 이번 회차에 이미지 재빌드분으로 재생성. 이전 `sbom-web-m1.json` 은 12개 누락·라이선스 없음·OS 패키지 없음으로 **대체**(폐기 여부는 오케스트레이터 결정) |
  | 자체 ML 모델 거버넌스(규칙 J) | 해당 없음(대상 자체가 없음) | 자체 학습/운영 모델 없음(모의 제안기 + M3 외부 서비스 예정) → 모델 카드/편향/drift 대상 아님 |
  | 외부 데이터/API 약관 | 해당 없음(M1) | 외부 호출 코드 없음(TC-S9-020). M2 에서 재점검 |
  | **규제 민감 도메인(규칙 I)** | 예 | 실제 화면·번들·API 직접 확인(TC-S9-079, 부록 J). **POL-002 면책 문구 미노출 → DEF-9-007 (Critical)**, POL-008(표시광고·한계)·POL-013(A/B 확인 문구) → DEF-9-008 (High). POL-001(건강·금융 엄격 모드)·POL-005(데모 표시)·POL-014(제외 영상)는 구현 확인. **개별 REQ-ID 등록 갭 → DEF-9-018** |
  | **AI/LLM 내장(규칙 J)** | 예 | M1 모의 AI 범위: 입력 정제·출력 새니타이즈·권한 0·사람 승인 게이트 동작 확인(TC-S9-025·026). 인젝션 직접 재현·출력 기반 XSS 재현 시도 → 불성립. **투명성 고지(POL-006) 미노출 → DEF-9-008**. 미반영(M3 진입 차단 조건, 부록 F-4): SEC-027(호출·비용 상한)·SEC-026 일부(전송 미리보기 UI)·SEC-021 지시/데이터 구획·SEC-028 키 주입·SEC-030 실서비스 시험 |
  | 접근 권한(최소권한·회수)·로그 보관·감사 추적 | 예 | 최소권한 = DB 3계정·시크릿 분리·api/worker 비밀 최소(TC-S9-060·062). 계정 회수 = PIN 변경 시 타 세션 폐기. 로그 보관 = json-file 10 MB×3 + 감사 로그 무기한, 보관기간 미정(DEF-9-013) |
  | 보안 사고 대응(탐지→격리→통지→복구) 근거 | 예 | `WEB_RUNBOOK.md` §11 에 4단계 있음. **비밀번호 교체 절차 미검증**(Q-11-06). 탐지 근거 = 감사 `chain_ok`·`session.denied` 기록 |
- **코드 커버리지(보안 시험 단독)**: 오프라인 3파일이 `ytweb` 3,344문장·704분기 중 **79 %**(미실행 599문장·분기부분 136). 낮은 곳은 `worker.py`·`migrate.py`(컨테이너 안에서 실스택 시험이 실행), `core/jobs.py`·`domain/handlers.py`(워커 경로), `domain/batches.py` 62 %(실패·복구 경로는 6단계 시험이 담당). 보안 통제 모듈(`core/guard·deps·sessions·pin·audit·idempotency·logsetup`, `ai/guard`, `routers/auth·settings`)은 82~100 %.
- **변이 점검**: 코드 74곳(73 killed + 동치 대조군 1) · 설정 45곳(45 killed) — 부록 E.
- 커버되지 않은 부분과 사유: 2절 제외 표, 8절.

## 6. 결함(Defect) 목록
> ID 는 `DEF-9-nnn`, 관련 `SEC/POL/TW/S-W/D` ID 를 함께 적었다(규칙 H·C 보칙 4). 심각도는 **기획서의 비즈니스 영향**과 연결했고 계획서가 낮게 본 항목도 규칙 I·J 에 따라 상향했다. **Open 은 전부 사용자/오케스트레이터 결정 또는 타 단위 소유 파일** 때문에 고치지 않았다(소스 수정 금지 지시).

| ID | 설명 (관련 ID) | 재현 절차 | 심각도 | 상태 | 조치 내용(권장) |
|----|---------------|-----------|--------|------|-----------------|
| **DEF-9-007** | **면책 문구(POL-002)가 웹 화면·API 어디에도 없다.** 기획 문구: "이 검증은 법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다"(CLI 는 `src/youtube_title/ui.py:10 DISCLAIMER` 로 구현·표시, 웹은 미이식). 대상 콘텐츠가 **건강·금융**(표시광고·의료광고·금융소비자 보호 규제 대상)이라 규칙 I 의 핵심 요구다. 실측: `ko.ts`·`pages/**`·`app/**`·`ytweb/**`·실스택 번들(393 KB)에서 "법률 자문"·"면책"·"최종 책임"·"책임" 0건. 관련: **POL-002**(traceability 39행, 현재 CLI 근거로만 Done), RISK-003·RISK-036, C-7, 규칙 I-3, 계획 W-FIX-4 | `grep -rn "법률 자문" web/frontend/src web/backend/ytweb` → 0; `curl -H 'Host: 127.0.0.1:8080' http://127.0.0.1:18380/assets/index-*.js \| grep -c 면책` → 0; 시험 `test_sec_05` 의 `test_disclaimer_*`·`test_bundle_contains_disclaimer`(xfail) | **Critical** (규칙 I: 규제 REQ 미반영은 축소 불가. 계획서는 RISK-036 을 "중"으로 봤으나 9단계 기준으로 상향. 사용자·시장 규모가 작다는 이유로 낮추지 않음) | **Open** — 프런트 소유(W-FIX-4). **사용자 수용 불가** | **어디에**: ① `ko.ts` 에 `legal.disclaimer` 한 곳 정의 → 전 화면 공통 `app/Layout.tsx` 하단 상시 푸터(권장), 그리고 ② 영상 상세의 검증 결과(`VideoDetailPage`/`SuggestionCard`), ③ 배치 사전 점검·실행 확인 대화상자(`BatchDetailPage`), ④ 성과 리포트(`ReportsPage`) 에 명시 표시. ⑤ API: `GET /api/v1/reports/changes` 응답 `notes` 에 같은 문장 추가(→ CSV `youtube-title-report.csv` 끝 주석 행에도 자동 포함), 배치 사전 점검 응답에 `notice` 필드. ⑥ `WEB_USER_MANUAL`·`WEB_LEGAL_NOTICE` 3-2 의 "미구현" 문구를 구현 후 정정. **재검증**: `test_sec_05` 의 `test_disclaimer_text_exists_in_ko_ts`·`test_disclaimer_is_rendered_globally_or_on_all_result_screens`·`test_bundle_contains_disclaimer` 가 XPASS(strict → 일부러 실패)로 바뀌면 xfail 표식을 지우고 통과를 확인한다(수정 모사로 전환 확인 완료). 문구의 법적 충분성은 이 문서가 판단하지 않는다 — 공개·실연동 전 전문가(변호사 등) 확인 필요 |
| **DEF-9-008** | **AI 생성 고지(POL-006)·AI 한계/표시광고 규정 확인 안내(POL-008)가 없고, POL-013(A/B 확인)은 사전 점검 경고 한 줄(`domain/batches.py:184`)뿐이다.** 제안 카드에는 "AI 제안" 배지와 엄격 모드 문구("건강·금융 등 민감 주제는 경고도 차단으로 처리합니다.")만 있다. 없는 문장: "AI가 생성한 제안입니다. 사람이 검토·승인한 제목만 반영됩니다", "사실·법령 적합성을 보장하지 않으며 건강·금융은 표시·광고 규정을 확인하세요", 실행 확인 단계의 "A/B 테스트 중이 아님" 확인. 관련: **POL-006, POL-008, POL-013**(02_planning Part W 제안 ID), SEC-029, 규칙 I·J, AI 기본법 투명성 `[확인 필요]` | 번들 문자열 검색 "AI가 생성" 0·"표시광고/표시·광고" 0·"A/B" 0; `test_sec_05` 의 `test_ai_generated_notice_*`·`test_ai_limit_and_advertising_*`·`test_batch_execute_confirmation_*`·번들 2건(xfail) | **High** (POL-006·008·013 은 traceability.md 에 아직 미등록이라 Critical 대신 High — **등록되면 규칙 J·I 에 따라 Critical 로 상향**, 미등록 자체는 DEF-9-018. 어느 쪽이든 열린 High 이상이라 PASS 불가) | **Open** — 프런트 소유(W-FIX-4). **사용자 수용 불가** | **어디에**: ① POL-006 — `SuggestionCard`(제안 카드 상단 또는 배지 옆)·승인 대화상자·변경 이력(`HistoryPage`)에 `ko.suggestion.aiNotice` 상시 노출. ② POL-008 — `SuggestionCard` 에 `ko.suggestion.aiLimit`(엄격 모드 영상은 더 눈에 띄게), 배치 사전 점검 카드에도 표시. ③ POL-013 — `BatchDetailPage` 실행 확인에 체크 항목 "Studio 에서 A/B 테스트 중이 아님을 확인했습니다"(미체크 시 실행 버튼 비활성) 및 필요 시 서버 확인 필드. 문구 초안은 `WEB_LEGAL_NOTICE.md` 3-2·4 장. **재검증**: `test_sec_05` 의 해당 5건+번들 2건이 XPASS 로 바뀌면 xfail 표식 제거 후 통과 확인. 법적 충분성은 판단하지 않음(전문가 확인 필요) |
| DEF-9-002 | **롤백이 "현재 제목이 방금 반영한 제목인지" 확인하지 않고 반영 전 백업 snippet 전체를 되돌려 쓴다** → Studio 에서 따로 고친 제목·설명·태그가 옛 값으로 덮어써진다(사후에 `changed_since_backup` 로 표시만). 관련: **TW-14**, SEC-005·010 승계, RISK-033 | `rollback_repro_overwrites_title_and_description_edited_elsewhere`(재현, 201) 와 `rollback_should_*`(xfail) — 반영 뒤 Studio 편집(모의: DB snippet 수정)→롤백 | **Medium** (M1: 모의 게이트웨이뿐이라 실채널 피해 없음. **M3 진입 시 High 로 승격 — 해결 전 M3 금지**, 위협 모델 W6 과 동일) | Open — 설계 결정(질문 Q-S9-2) | (a) 현재 제목 ≠ 반영한 제목이면 409 + Studio 수동 안내, (b) 제목만 현재 재조회 snippet 에 교체해 복원(설명 등은 현재값 유지), (c) 실계정 1건 시험 |
| DEF-9-006 | `.gitignore` 에 `client_secret*.json` 이 없다(`.dockerignore` 에는 있음). 위협 모델 TW-18 은 "`.gitignore` 가 제외"라고 서술 → 문서-구현 불일치. 구글이 내려주는 `client_secret_*.json` 을 저장소 루트에 두면 `git add`(자동 푸시 허용됨, `.claude/settings.json`)로 올라간다. 관련: **TW-18**, D-05, S-W08, M2 | `test_gitignore_has_client_secret_pattern`(xfail) / `.gitignore` 정독 | **Medium** | Open — 공유 파일(`.gitignore`) | `client_secret*.json`, `*client_secret*.json`, `credentials*.json`, `*.pem`, `*.key` 추가. 커밋 전 비밀 검사 훅(gitleaks 등) 권장 |
| DEF-9-010 | **베이스 이미지 OS 패키지의 HIGH/CRITICAL 취약점** (Trivy 0.75.0): api(Debian 13.7) HIGH 8개 CVE(44건·패키지별)·**수정본 없음**, web(Alpine 3.24.2) HIGH 1(`tiff` CVE-2026-4775→4.7.2-r0)·MEDIUM 1(`zlib`) **수정본 있음**, db(Debian 12.15) CRITICAL 3(`libsqlite3`·`libxml2`·`zlib1g`: 미수정/ will_not_fix)+HIGH 22 CVE 및 `gosu` Go 표준 라이브러리(수정본 있음, 단 비루트 기동이라 gosu 미사용). **현재 고정한 4개 다이제스트가 2026-10-11 기준 각 태그의 최신 다이제스트**라 다시 고정해도 해소되지 않는다. 관련: **TW-13, D-11, S-W11**, D-04 | 부록 C 표; `trivy image --input <tar> --scanners vuln` | **Medium** (도달성: 취약 구성요소 대부분이 네트워크 입력 경로 밖 — db 는 호스트 포트·외부 경로 없음, api 입력은 파이썬만 처리, web 은 이미지 변환 모듈 미사용. 악용에는 컨테이너 내 코드 실행이 선행돼야 하고 비루트·읽기 전용·cap_drop 으로 완화. 단 **상류 수정본이 없어 프로젝트가 직접 해소할 수 없음**) | Open — 추적·수용 질문(Q-S9-4) | 릴리스 전 재스캔·`pin-digests.ps1`, 수정본이 나온 항목 갱신, CI 에 이미지 스캔(고정 버전 도구) 추가, M2(외부 TLS 사용 시작) 전 `openssl`/`libssl3` 재평가 |
| DEF-9-011 | **컨테이너가 자기 망의 게이트웨이 주소로 호스트(Linux 엔진)의 `0.0.0.0` 서비스에 도달한다 — web 뿐 아니라 internal 망의 api·worker·db 도 해당(이번 회차 재측정으로 범위 확대).** 위협 모델 TW-36 은 "외부로 데이터를 보낼 수 있는 이론상 경로"만 서술. 실측: 호스트에 `0.0.0.0` 임시 리스너를 열고 web(edge `172.23.0.1`·front `172.22.0.1`)·api/worker/db(back `172.21.0.1`, internal=true)에서 연결 → 전부 OPEN, `127.0.0.1` 전용 리스너는 전부 CLOSED. 즉 DEC-045 의 3망 분리는 인터넷 경로는 막지만 **호스트의 0.0.0.0 서비스 도달은 막지 못한다**. edge 를 빼면 게시가 안 된다(internal 단독 컨테이너는 `-p` 무시, `gateway_mode_ipv4=isolated` 는 internal 전용 — 이전 회차 실측). 선행조건: 컨테이너 침해(비루트·읽기 전용·cap_drop). Windows Docker Desktop 에서는 게이트웨이가 Docker VM 쪽일 수 있어 **의미가 다를 수 있음(미수행)**. 관련: **TW-36, D-10, S-W14, DEC-045** | `test_sec_06::test_web_container_reaches_host_gateway_listener_repro`(통과=재현), 수동 4개 망 프로브 | **Medium** (선행조건이 높고 호스트 쪽 0.0.0.0 서비스는 사용자 PC 에 따라 다름. 단 DEC-045 수용 범위를 넘는 새 사실) | Open — 사용자 결정(Q-S9-3) | DEC 에 확장 수용 기록 + WEB_INSTALL 에 "호스트에 0.0.0.0 로 열린 서비스가 없는지, Windows 방화벽의 Docker 가상 NIC 인바운드 제한" 안내, Docker Desktop 실측(10단계), 장기적으로 게시 전용 중계 컨테이너 분리 |
| DEF-9-013 | **데이터 보관·파기(POL-012)·백업 암호화·보관기간(POL-016)이 미구현·미정**: `jobs`·`ai_runs`·`audit_log`·`changes.backup_snippet` 무기한 보관(`purge_expired` 는 세션만, 멱등키 48시간), 백업 덤프 무암호화, 로그 보관 정책 없음. M1 은 합성 데이터와 승인자 이름뿐이라 현재 위반 소지는 낮으나 M2(구글 유래 데이터, API 정책의 저장 기간) 전에 필요. 관련: **POL-012, POL-016, TW-19, RISK-024·035**, W-016 | 코드 정독(`worker.py maintenance`), `ytweb-db dump`, README §3 | **Medium** | Open — 사용자 결정(Q-W2·Q-W4) | 보관기간 확정 후 정리 작업·백업 암호화(예: `age`) 옵션. **개인정보 보호법·PIA·ISMS-P 해당 여부는 판단하지 않음 — 전문가 확인 필요** |
| DEF-9-014 | **감사 로그 체인에 키가 없고, 앱 계정이 감사 외 표(`changes`·`approvals`·`batch_items`…)를 UPDATE/DELETE 할 수 있다**: DB 소유자/슈퍼유저가 기록을 고치고 해시를 다시 계산하면 `chain_ok` 가 계속 True, 꼬리(마지막 N건) 삭제도 탐지 불가. 앱 계정은 `audit_log` UPDATE/DELETE/TRUNCATE 권한이 없음을 PostgreSQL 에서 실측. 문서 불일치(README "서명 키")는 README 114행 정정으로 해소됨. 관련: **S-W16, TW-08, TW-32, DV-W08** | `audit_limitation_repro…`(재현), `known_limit_app_role_can_modify…`(재현) | **Medium** (앱 계정 침해까지는 방어 — 요구 S-W16 은 충족, 소유자 이상은 범위 밖. 수용 질문 Q-W6 대기) | Open — 사용자 결정 | HMAC(키=`app_secrets`) 체인으로 전환하거나 마지막 해시를 별도 위치(백업·화면)에 주기적으로 기록, 또는 수용을 DEC 로 기록 |
| DEF-9-001 | **상한 없는 정수 입력이 HTTP 500 을 낸다**: `/batches/{id}`·`/suggestions/{id}`·`/changes/{id}/rollback`·`?batch_id=`·`?page=`·`suggestion_ids:[…]` 에 DB 정수 범위(2⁶³) 초과 값을 넣으면 SQLite `OverflowError`/PostgreSQL `DataError`→500(일반 문구, **누설 없음**, 서버 생존). 오류 로그 폭증 가능. 관련: **S-W13, TW-25·09**, DEF-VA-005(감사 `page` 만 고쳐짐) | `GET /api/v1/batches/99999999999999999999999` — 오프라인·PostgreSQL(실스택) 모두 | **Low** | Open — 백엔드 소유 | 경로·쿼리 `le=2**63-1`, 본문 리스트 항목 `Field(ge=1, le=…)`. 시험의 xfail 표식 제거 |
| DEF-9-003 | **세션 관리 갭 2건**: ① 유휴 만료 없음(절대 12시간만; 축 D 권장 유휴 30분+절대 8시간보다 느슨), ② 세션 상한 20 — PIN 이 꺼져 있으면 같은 PC 프로세스가 21번 로그인해 소유자 세션을 축출(로그아웃 DoS). 관련: **TW-20, TW-03**, S-W02·W04 | `session_cap_evicts…`, `session_absolute_expiry_and_documented_idle_gap`(재현) | **Low** | Open — 설계 결정(Q-S9-7) | 유휴 만료 추가, PIN 필수화(Q-W1)로 ②는 해소, 세션 발급 속도 제한은 있음 |
| DEF-9-004 | 승인자 이름이 제로폭 문자(U+200B 등, 범주 Cf)를 허용해 눈에 같은 이름을 만들 수 있다. 승인자는 인증된 신원이 아니라 자유 입력(1인 운영 전제). 관련: **TW-16**, S-W16 | `approver_zero_width_chars_are_accepted_info` | **Low** | Open | `clean_approver` 에서 Cf 범주도 제거/거부 |
| DEF-9-005 | **CI 예시 워크플로(`automation/github-actions-harness.yml`)의 보안 갭** — 활성 CI 는 없지만 이대로 `.github/workflows/` 에 넣으면: `permissions:` 선언 없음(기본 토큰 권한), `actions/checkout@v4` 태그 고정(SHA 아님), `npm install -g @anthropic-ai/claude-code` **버전 미고정**(비밀 `ANTHROPIC_API_KEY` 가 워크플로 전체 `env` 라 설치 단계에도 노출), 러너 `ubuntu-latest`, 에이전트가 `--permission-mode dontAsk` 로 PR 내용을 읽고 도구 실행(프롬프트 인젝션 → 비밀 접근 경로). 배포 승인 environment 는 있음. 관련: S-W11, 규칙 E | `ci_files_inventory…`(재현) | **Low** (비활성; 활성화 전 차단 조건) | Open — Deferred 후보(활성화 계획 없음 시 DEC 필요) | 최소 `permissions: contents: read`, 액션 SHA 고정, CLI 버전 고정, 비밀은 필요한 step 의 env 로만, 포크 PR 에는 비밀 미제공 |
| DEF-9-009 | 실행 이미지에 불필요한 **pip 25.0.1**(CVE 6개: 5 MEDIUM+1 LOW, 모두 26.x 에서 수정)이 남아 있고, 개발용 `requirements*.txt`·`pyproject.toml` 도 포함. 설치에는 `--only-binary --require-hashes` 라 악용 불가이나 런타임에 pip 은 필요 없다. 관련: **TW-13, D-04, D-11** | 부록 C(`Python` 결과 12건) | **Low** | Open | 런타임 단계에서 `pip` 제거(또는 distroless 계열), `COPY web/backend` 를 `ytweb`·`alembic` 만으로 축소 |
| DEF-9-012 | `restore.ps1` 은 `.sha256` 파일이 **없으면 경고만 하고 복원을 진행**한다(무결성 확인 fail-open). `pg_restore` 는 덤프 안의 SQL 을 소유자 권한으로 실행하고, 복원 뒤 `audit-guard.sql` 은 `audit_log` 권한만 다시 회수한다(덤프의 다른 GRANT 는 유지). 선행조건: 호스트 사용자 권한으로 `web\backups` 쓰기(=이미 호스트 장악, TW-12 수용 후보). 관련: **TW-12, TW-19**, POL-016 | `restore.ps1` 36~44행 정독 | **Low** | Open | `.sha256` 없으면 중단(`-AllowNoHash` 명시 옵션), 복원 후 앱 계정 권한을 `schema-grants` 기준으로 재설정 |
| DEF-9-015 | **의존성 신선도**: 잠금 시점(2026-10-10)에 릴리스 후 7일 미만인 버전을 채택 — fastapi 0.143.0(10-08)·pydantic 2.14.0(10-08)·pydantic-core 2.50.0(10-08)·sqlalchemy 2.1.4(10-07)·opentelemetry-api 1.45.1(10-06). 모두 대형 프로젝트(수백 릴리스)이고 해시·존재·CVE 점검은 통과했으나 갓 올라온 버전의 공급망 탈취 창을 줄이는 쿨다운이 없다. `eslint 9.39.5` 는 npm 에서 "지원 종료"로 표시. 관련: **S-W11, TW-13** | 부록 B-1 | **Low** | Open | 쿨다운(예: 최소 7일) 정책과 갱신 절차 문서화, ESLint 대체(노트의 jsx-a11y peer 제약) |
| DEF-9-016 | **nginx 오류 로그에 요청 줄(쿼리 문자열 포함)이 남는다**(업스트림 오류 등). 실측: api 정지 후 `GET /api/v1/videos?q=…&code=OAUTHCODE_CANARY` → 로그에 `request: "GET …?q=…&code=OAUTHCODE_CANARY"`. 접근 로그는 안전. M1 API 는 비밀 쿼리가 없으나 **M2 OAuth 콜백(`?code=&state=`)이 걸리면 인가 코드가 로그에 남는다**. 6단계 DEF-VI-003 의 잔여(속도 제한 거절은 warn 으로 낮춰 해소, 업스트림 오류는 미해소). 관련: **TW-17, S-W08·W09**, DEF-VI-003 | 위 canary 요청 후 `docker logs <web>` | **Low** (M2 전 필수) | Open — 설계 결정(M2 콜백 설계 때) | 콜백 location 에 `error_log /dev/null crit;`, 또는 콜백을 POST/프래그먼트로 설계 |
| DEF-9-017 | **`.dockerignore` 가 거부 목록 방식이라 비밀형 파일(`*.pem`·`*.key`·`credentials*.json`)과 개발 캐시가 이미지 빌드 컨텍스트에 들어간다.** 실측: api 이미지에 `/app/backend/.ruff_cache`(24 KB)·`/app/backend/.coverage` 가 실제로 포함됨(작업 폴더의 미추적 개발 산출물이 빌드 컨텍스트를 통해 유입). 빌드가 git 이 아니라 **작업 폴더** 를 쓰므로 `.gitignore` 와 무관하게 로컬 미추적 비밀 파일이 이미지에 구워질 수 있다(`.gitignore` 에도 같은 패턴이 없음, DEF-9-006). 관련: **D-05, TW-18, S-W08** | `test_sec_03::dockerignore_covers_secret_like_and_dev_cache_patterns`·`test_sec_06::api_image_has_no_dev_cache_directories`(xfail; `--runxfail` 로 올바른 이유로 실패함 확인) / `docker run --rm --entrypoint sh <api> -c 'find /app -name .ruff_cache'` | **Low** (현재 이미지에 비밀은 0건 — Trivy·이미지 열람; 잠재 경로) | Open — 인프라 소유 | `.dockerignore` 를 허용 목록(`*` 후 `!web/backend/ytweb`·`!web/backend/alembic*`·`!src/youtube_title`·`!config/*.yaml`…)으로 바꾸거나 `**/.ruff_cache`·`**/.coverage`·`*.pem`·`*.key`·`credentials*.json` 추가. xfail 표식 제거 |
| DEF-9-018 | **규칙 I·J 의 REQ-ID 등록 갭**: 웹 트랙 POL-005~016 · SEC-021~030 이 `02_planning.md` Part W 에서 "제안 ID"로만 있고 `traceability.md` 에 정식 행으로 등록되지 않았다(87행 서술 "오케스트레이터가 재부여"). POL-002 행은 CLI 근거로 `Done` 이라 웹 화면 미구현(DEF-9-007)이 추적표에서 보이지 않는다. 규칙 H·I-2·J-2 위반 소지이며 8단계 커버리지에서 빠질 수 있다. 관련: **POL-002·006·008·013, SEC-021~030, 규칙 H·I·J** | `grep -n "POL-00[5-9]\|SEC-02[1-9]" docs/harness/traceability.md` → 0건 | **Medium** (코드 취약점은 아님; DEF-9-008 의 심각도 상향 조건) | Open — 오케스트레이터(문서) | traceability 에 웹 행으로 등록(POL-002 웹 범위 분리 Not Done, POL-006·008·013 Not Done), 09 확인 결과는 부록 F-1 |

- 집계: **Critical 1 · High 1 · Medium 7 · Low 9 (총 18건, 전부 Open)**. Fixed 0건(운영 소스 수정 금지 지시). 이번 회차 신규: DEF-9-017(Low)·DEF-9-018(Medium), DEF-9-011 범위 확대(여전히 Medium). **Critical/High(DEF-9-007·008)는 사용자 수용(Deferred) 불가 — 수정 후 9단계 재검증 필수.** Deferred 가능한 것은 Low·Medium 이며 수용 결정은 사용자만 한다(규칙 C 보칙 2).
- 6단계에서 이월된 항목의 현재 상태: DEF-VI-001(web→db 도달)=**해소 확인**(web→db 이름·IP 모두 불가, 단 범위 확대 DEF-9-011), DEF-VI-002(`alembic_version` 쓰기)=**해소 확인**(권한 `f`), DEF-VI-003=**부분**(DEF-9-016), DEF-VF-B01(PIN 변경 우회 경쟁)=**해소 확인**(PostgreSQL 에서 동시 추측 직렬화 실측, TC-S9-065).
- "결함 0건" 주장은 하지 않는다. 대신 **무엇이 불성립했는지** 부록 H 에 공격 시도별 결과를 남겼다.

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록:
  - 파일: `.harness-tmp/sec/**` (venv 3개·`stack/`(임시 비밀 3개 포함)·`out/`(스캔 결과·tar)·`work/`(빌드 사본)·`mut/`(변이 사본)·`npm/`·`trivycache/`)
  - Docker(전부 `harness-tmp-sec` 접두사): 컨테이너 `harness-tmp-sec-{db,migrate,api,worker,web}-1`(+ 실험용 `-iso-web`·`-pubtest`, 이미 삭제), 네트워크 `harness-tmp-sec_{front,back,edge}`(+실험용 `-iso`), 볼륨 `harness-tmp-sec_{pgdata,backups,app_secrets}`, 이미지 `harness-tmp-sec-{api,web,db}:local`, 스캐너 이미지 `harness-tmp-sec-trivy:scan`(원래 `aquasec/trivy:latest`, 태그를 바꿔 접두사 규칙 준수)
  - 호스트 포트: 127.0.0.1:18380 (이 단위 전용)
  - 저장소 안(의도한 산출물): `web/tests_security/**`, `docs/harness/security-web-m1-test.md`, `docs/harness/verify-log_security-web-m1-test.md`, `docs/harness/sbom-web-m1/*.json`
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예 — 단 Docker 객체는 파일시스템이 아니라 공유 dockerd 에 생기므로 위 접두사 규칙으로 구분했다(저장소 밖). 파이썬이 만든 `__pycache__` 는 정리.
- 정리(삭제) 완료 여부: [x] **완료**. `docker compose -p harness-tmp-sec down -v`(컨테이너 5·네트워크 3·볼륨 3 삭제), 이미지 `harness-tmp-sec-{api,web,db}:local`·`harness-tmp-sec-trivy:scan`·`mirror.gcr.io/aquasec/trivy:latest`(내가 받은 스캐너 태그) 삭제, `.harness-tmp/sec/`(venv 3·스택·비밀 3개·스캔 결과·변이 사본·npm·trivy 캐시) 삭제, `web/tests_security/__pycache__` 삭제. 확인(원문): `docker ps -a | grep harness-tmp-sec` 0줄, `docker network ls` 0줄, `docker volume ls` 0줄, `docker images | grep -i 'harness-tmp-sec\|trivy'` 0줄, `.harness-tmp/` 에 `sec` 없음(남은 항목은 7단계·이전 단위 소유: int·vinf·pg·venv_* 등). 임시 PostgreSQL 내 내 DB `ytweb_test_g`: 이번 감사는 SQLite 임시 파일과 컨테이너 안 DB 만 사용해 **접속·생성한 객체가 없음**. **dockerd·임시 PostgreSQL 은 끄지 않았다**: 내가 띄운 것이 아니고, 7단계 에이전트의 `harness-tmp-int-*` 컨테이너 4개가 지금 실행 중이라 끄면 그 시험이 깨진다 — 웨이브 종료 후 오케스트레이터가 종료해 달라. 공유 Docker 빌드 캐시는 프로젝트별로 구분되지 않아 건드리지 않았다. 파이썬 `__pycache__`(cpython-313)가 `web/backend/ytweb`·`src/youtube_title` 에 생길 수 있으나 `.gitignore` 대상이다.
- 정리 후 `git status` 실행 결과: 읽기 전용 `git status --short` 를 실행했다(쓰기 git 명령은 쓰지 않음). 원문은 아래.
  ```
  $ git status --short   (읽기 전용, 정리 후)
 M docs/harness/security-web-m1-test.md        <- 이 단계의 의도된 산출물(9단계 소유)
(이 단계가 만든 `web/tests_security/test_sec_05·06`, `sbom_from_npm_lock.py`, `docs/harness/sbom-web-m1/*` 는 02ec286 에 이미 커밋됨; verify-log 는 마지막에 수정됨)
$ docker ps -a / network ls / volume ls / images  -> harness-tmp-sec 접두사 0건 (위 원문 요약)
  ```
- 병렬 실행이었다면: 7단계가 `harness-tmp-int`·`.harness-tmp/int*`·포트 18080 을, 11단계 대조가 `.harness-tmp/doc_reconcile` 을 쓰고 있었다. 나는 그 폴더·컨테이너·이미지(`harness-tmp-int-*`, `harness-tmp-vinf-*`)를 건드리지 않았다(삭제·정지 없음). 이 단위가 만든 임시 아티팩트·미추적 잔여물은 위 "정리 완료"의 확인 범위에서 없음. 웨이브 종료 후 전체 트리 점검은 오케스트레이터 몫.
- 이번 테스트 도중 강제 중단: [x] 없음(백그라운드 변이 점검 한 번을 내가 직접 중지·재시작: 프로세스 PID 로 내 것만 종료).
- 규칙 K 2번의 "깨끗함" 판정은 위 원문으로 한다. 다른 에이전트(7단계)가 동시에 같은 저장소·dockerd 를 쓰고 있어, 전체 트리 점검은 웨이브 종료 후 오케스트레이터 몫이다. 9절은 어차피 FAIL 이다.

## 8. 리스크 및 잔존 이슈
- **이번 테스트로 커버되지 않는 알려진 리스크(PASS 로 세지 않음)**
  1. Windows Docker Desktop(WSL2)에서의 127.0.0.1 한정 게시·`internal` 망 동작·비밀 파일 권한·PowerShell 5.1 호환 — 미수행(Linux 엔진만).
  2. 실제 브라우저: CSP 가 화면을 깨뜨리는지, `SameSite=Strict`·`Sec-Fetch-Site` 동작, 브라우저 확장(TW-24) — 미수행.
  3. 실서비스 LLM 인젝션 시험 세트(SEC-030)·비용/호출 상한(SEC-027) — M3.
  4. 이미지 서명·스캐너 도구 서명 검증 — 도구 없음(Trivy 는 태그로 받아 다이제스트를 기록했음. 위협 모델 TW-13 은 "도구 침해 이력, 다이제스트 고정 필요"를 요구했고 이번에는 기록만 했다).
  5. 같은 모델이 시험을 설계·실행했다 — 변이 점검 119곳으로 시험의 실효성은 보강했으나 독립된 사람의 검토는 아니다. 시험은 파이썬 3.13 에서, 컨테이너는 3.12 에서 돌았다.
  6. 재시작 중 이중 반영·장시간 부하·다중 워커 — 7단계.
  7. 비밀번호 교체·유출 대응 절차 검증(Q-11-06), 백업 복원 후 `audit-guard` 재회수 — 6·7단계 결과에 의존.
  8. 브라우저 없이 확인하지 못한 프런트 페이지별 전수 정독: 위험 싱크는 소스 전수 grep(0건)·ESLint 금지 규칙·번들 문자열 검사로 확인했고 페이지 컴포넌트 전체를 줄 단위로 정독하지는 않았다.
- **후속 조치가 필요한 항목**
  - 즉시(재검증 전 필수): DEF-9-007·008(프런트 W-FIX-4), DEF-9-018(추적표 등록). 수정 후 `test_sec_05` 의 xfail 해제·통과와 전체 재실행.
  - M2 전: DEF-9-016, DEF-9-013(보관·파기), DEF-9-006, 토큰 저장·OAuth 설계 시 TW-35 재평가.
  - M3 전: DEF-9-002(롤백), SEC-021·026·027·028·030, Q-W10(AI topic 의존 제거), PIN 필수화·쓰기 재로그인, TW-15.
  - 릴리스 전: DEF-9-010 재스캔, DEF-9-009, DEF-9-017(.dockerignore), DEF-9-011 의 Docker Desktop 실측(10단계).
- 11단계 Runbook 에 담을 보안 사고 대응 근거: 탐지(`GET /api/v1/audit` 의 `chain_ok`, `session.denied`, 429/403 빈도) → 격리(`stop.ps1`, 필요 시 네트워크 분리) → 통지(소유자 판단, 개인정보 포함 시 법적 통지 의무 확인 `[확인 필요]`) → 복구(`restore.ps1` 해시 확인 필수·비밀번호 교체 절차 **미검증**). 부록 F-2 의 11단계 대조 항목 참고.

## 9. 결론 및 판정
- [ ] PASS
- [ ] PASS (수용된 알려진 제한 포함)
- [ ] CONDITIONAL PASS
- [x] **FAIL** — 사유: **Critical 1건(DEF-9-007: 규제 도메인 면책 문구 미노출, 규칙 I) + High 1건(DEF-9-008: AI 고지·표시광고 안내 미노출, 규칙 I·J)이 Open**이다. 7절 `git status` 원문이 없어 Teardown 확인도 미완이다.
  - 재작업 요청: ① 화면·API 에 POL-002·006·008·013 문구 반영(W-FIX-4, 프런트 소유; 위치는 DEF-9-007·008 의 "어디에") → 9단계가 `test_sec_05` 로 재검증(xfail strict → XPASS 전환 확인 후 표식 제거). ② DEF-9-018 추적표 등록(오케스트레이터). ③ 나머지 Medium 7건은 사용자 결정(부록 F-3 질문 목록)을 받아 수정 또는 Deferred(DEC-ID)로 닫는다. Deferred 는 Low·Medium 만 가능하다. **Critical/High 는 사용자가 원해도 수용할 수 없다.**
  - 판정 근거 요약: 위협 모델 36개 중 구현 확인 19(한계·의존 표기 포함), 부분 13, 해당 없음 2, 수용 대기 2, 미구현 0. 공격자 관점 시험(313건, 통과 298·xfail 15·실패 0)에서 **Critical/High 급 기술 취약점(인증 우회·인젝션·비밀 노출·권한 상승)은 발견되지 않았다.** 막은 것은 실제 동작으로 확인했고 시험이 통제 파괴를 잡는지는 변이 119곳으로 확인했다. FAIL 은 기술 취약점 때문이 아니라 규칙 I·J 의 "규제·AI 고지 문구 미반영" 때문이다.
  - 다음 단계(10 배포 테스트) 진행: 가능하나 DEF-9-007·008 이 닫히기 전에는 12단계(배포) 승인 요청을 올리지 않는다.

## 10. 내부 검증 (최소 2회, `verification-log-template.md` 사용)
- 1차 검증 결과 요약(작성자 관점): 최소 점검 항목 체크리스트 19개 전부 수행(이번 회차에 환경을 처음부터 재구성해 오프라인·실스택·변이 점검·스캐너·SBOM 을 재현, 이전 숫자와 일치 확인). 시험 코드 자체의 오류 1건 발견·수정(신규 `.dockerignore` 시험이 `REPO` 이름 오류로 NameError 로 xfail 되던 공허한 시험 — `--runxfail` 로 발견, 올바른 이유로 실패하도록 수정). SBOM 도구 한계 1건 발견(cyclonedx-npm 이 잠금 파일의 중첩 12개를 누락) → 잠금 기반 생성기 추가.
- 2차 검증 결과 요약(공격자 관점, 카테고리 연쇄 포함): 변이 119곳(코드 73 killed+대조군 1, 설정 45 killed)을 재실행해 시험 실효성 재확인(놓침 0). 새 연쇄 경로 점검 CH-10(컨테이너 침해 → 게이트웨이 → 호스트 0.0.0.0 서비스)·CH-11(AI 고지 부재 + 인간 승인 → 건강·금융 과장 제목 승인) 추가. 이 과정에서 **새 사실 3건**: DEF-9-011 범위 확대(internal 망 컨테이너도 호스트 도달), DEF-9-017(.dockerignore 거부 목록·이미지 내 `.ruff_cache`/`.coverage`), DEF-9-018(POL/SEC 제안 ID 미등록). 수정 모사 사본으로 `test_sec_05` 의 5개 xfail 이 XPASS 로 전환됨을 확인(시험의 비공허성).
- 3차(결함 0건 확인 회차): 시험·소스 확정 후 **새로 만든 스택에서 전체 재실행** — 오프라인·정적(01·02·03·05) 224건: 통과 210·xfail 10·건너뜀 4(05 번들, 스택 필요)·실패 0, 실스택(04·05 번들 포함) 98건: 통과 89·xfail 9·실패 0, 06 3건: 통과 2·xfail 1·실패 0. 합산(중복 제외) 313건 통과 298·xfail 15·실패 0. **기록된 결함 18건 외 신규 결함 0건** 확인. (xfail 15 = DEF-9-001×2, DEF-9-002×2, DEF-9-006×1, DEF-9-007×3, DEF-9-008×5, DEF-9-017×2 — 합 15.)
- 검증 로그 파일 경로: `docs/harness/verify-log_security-web-m1-test.md`

---

## 부록 A. 위협 모델 TW-01~36 재확인 매핑표 (규칙: 코드 근거는 파일:줄)
> 상태: **구현됨**(코드+동작 확인) / **부분** / **미구현** / **해당 없음**. "모델과 차이"는 `threat_model.md` Part W 의 서술과 다른 점이다(→ 부록 G 갱신 요청). 경로는 `web/` 기준(`backend/ytweb/…`).

| TW | 위협 | 판정 | 코드·설정 근거 | 동작 근거 | 모델과 차이·비고 |
|---|---|---|---|---|---|
| TW-01 | CSRF·로그인 CSRF | **구현됨** | `core/deps.py:44-54`(Origin 정확 일치+Fetch-Metadata), `:68-79`(CSRF `compare_digest`), `routers/auth.py:39-41`(HttpOnly·Strict·Path=/api), `core/guard.py:58-65`, `app.py:106-131`(CORS 미들웨어 없음) | TC-S9-003~007·057 | 브라우저 실동작은 계속 미확인 |
| TW-02 | DNS 리바인딩 | **구현됨(이중)** | `docker/nginx/nginx.conf:48-52,58-60`(map+444), `core/guard.py:121-124` | TC-S9-001·002·051 | nginx 는 대소문자 무시(같은 호스트라 우회 아님) |
| TW-03 | 같은 PC 프로세스의 세션 발급 | **부분(수용 대기)** | PIN 선택(`core/pin.py:80`), `core/ratelimit.py:42-62`, 감사 `routers/auth.py:68,72` | TC-S9-010·020(위조 Origin 만으로 전 흐름 자동화 가능) | 세션 21개 축출 DoS 추가(DEF-9-003). 수용 Q-W7·PIN 필수화 Q-W1 |
| TW-04 | PIN 무차별 대입 | **구현됨** | `core/pin.py:24-28,80-110`, advisory lock `:84` | TC-S9-011·065(PostgreSQL 동시 10건 중 401≤5) | 설정 API 경로도 같은 잠금 |
| TW-05 | OAuth 위장 | **해당 없음(M2)** | `routers/google.py` 는 상태 조회만, 구글 라이브러리 import 0 | TC-S9-020 | M2 설계 필요 |
| TW-06 | 이중 반영·재시작 중복 | **구현됨(6·7단계 의존)** | `db/models.py:200,239`(부분 고유 인덱스), `core/jobs.py:62`, `domain/batches.py:325-328,367`, `core/idempotency.py:22` | TC-S9-028(멱등) + 6단계 PG 시험 | 재시작 중 중복은 7단계 |
| TW-07 | 승인 변조·재사용 | **구현됨** | `domain/suggestions.py:70-75,83-103,203-210`, 키 `:62`(0600) | TC-S9-027·064 | 키 파일 실스택 `600 10001:10001` |
| TW-08 | 감사 로그 삭제·수정 | **부분** | `alembic/versions/0001_initial.py:240-254`, `docker/db/audit-guard.sql:6`, `core/audit.py:21,74` | TC-S9-029·062·062b | 한계 재현(키 없음·꼬리 절단·owner 재계산). README 서술은 정정됨(114행) → DEF-9-014 |
| TW-09 | SQL 인젝션 | **구현됨** | ORM·바인딩(`db/session.py`), `text()` 는 상수·`pg_advisory_xact_lock(:k)` | TC-S9-021 | 정수 범위 초과 500 은 인젝션 아님(DEF-9-001) |
| TW-10 | CSV 수식 주입 | **구현됨** | `domain/reports.py:25-29,104-107` | TC-S9-024 | |
| TW-11 | XSS | **구현됨** | `frontend/eslint.config.js:23`, CSP `docker/nginx/security-headers.conf:4`, 소스 전수 grep 0건 | TC-S9-022·045 | 브라우저 CSP 위반 로그 미확인 |
| TW-12 | 호스트 파일(백업) 변조 | **부분** | `scripts/restore.ps1:36-44`, `docker/db/bin/ytweb-db:63-73` | TC-S9-063 | 해시 없으면 진행(DEF-9-012) |
| TW-13 | 공급망 | **부분(미수행 항목 수행 완료)** | `docker/api.Dockerfile:15-16`, `docker/web.Dockerfile:11`, 다이제스트 4종 | TC-S9-070~076 | pip-audit·Trivy·SBOM·환각 점검 **완료**. 잔여: DEF-9-009·010·015, 스캐너 서명 미검증 |
| TW-14 | 반영·롤백 덮어쓰기 | **부분 → 결함 재현** | `domain/batches.py:317,411`(반영은 재조회·보존), `domain/changes.py:82,105,109`(롤백은 백업 전체 복원) | TC-S9-030b | DEF-9-002 (M3 전 해결) |
| TW-15 | 간접 프롬프트 인젝션 | **부분(M1 모의)** | `ai/guard.py:46,77`, `domain/suggestions.py:108` | TC-S9-025·026·026b | 엄격 모드 키워드 25개 한계 재현; 지시/데이터 구획·상한 M3 |
| TW-16 | 부인 방지 | **구현됨(한계)** | `audit.record` 호출(9곳+auth/settings), `domain/common.py:97` | TC-S9-029·023 | 제로폭 문자 허용(DEF-9-004) |
| TW-17 | 로그·오류 노출 | **구현됨(잔여 1)** | `core/logsetup.py:22`, `core/guard.py:179`, `app.py:63`, `compose.yaml:141` | TC-S9-016·032·060 | nginx 오류 로그 요청 줄(DEF-9-016) |
| TW-18 | 비밀이 이미지·저장소에 | **부분** | `compose.yaml:267`, `.dockerignore` | TC-S9-040·040b·060·073·074 | `.gitignore` 에 client_secret 없음(DEF-9-006); 이미지·inspect·히스토리·로그·덤프 비밀 0 ; `.dockerignore` 거부 목록·이미지에 `.ruff_cache`(DEF-9-017) |
| TW-19 | 백업 유출 | **부분** | `scripts/backup.ps1`, `_common.ps1 Set-OwnerOnlyAcl` | TC-S9-063 | 덤프 무비밀·600 확인; 암호화·보관기간 미정(DEF-9-013); Windows ACL 미실측 |
| TW-20 | 세션 탈취·장기 | **부분** | `core/sessions.py:16,30,46` | TC-S9-009·010 | 유휴 만료 없음·상한 축출(DEF-9-003) |
| TW-21 | DB 접근·권한 | **구현됨** | `docker/db/pg_hba.conf:13`, `schema-grants.sql:8`, `init/01-roles.sh:40` | TC-S9-061·062 | 권한 공격 26종 거부 |
| TW-22 | AI 개인정보 전송 | **부분** | `ai/guard.py:46-55`(mask_pii) | TC-S9-025 | 미리보기·영상 제외·고지 UI 없음(SEC-026), 서비스 미정 |
| TW-23 | 헤더·캐시 | **구현됨** | `docker/nginx/security-headers.conf`, `core/guard.py:25,67-75` | TC-S9-014·056 | nginx 생성 오류에도 7종 |
| TW-24 | 브라우저 확장 | **해당(완화 불가·수용 대기)** | — | 미시험 | Q-W7 |
| TW-25 | 요청 폭주·대용량 | **구현됨** | `nginx.conf:30,39`, `core/guard.py:126-163`, `core/ratelimit.py` | TC-S9-012·013·055·066 | 정수 오버플로 500(DEF-9-001); `/audit` 는 행 수에 비례(20,000행에서 0.61초, 정보) |
| TW-26 | API 쿼터 | **구현됨(6단계 의존)** | `domain/limits_quota.py:100-111` | 정독 | 동작 시험은 6·7단계 |
| TW-27 | 자원 고갈 | **구현됨** | `compose.yaml` deploy limits | TC-S9-059(Memory·PidsLimit·NanoCpus > 0, 4개 서비스) | |
| TW-28 | 워커 정지 | **부분** | `compose.yaml:199-208`(프로세스 생존만) | 정독 | 변동 없음 |
| TW-29 | 볼륨 삭제 실수 | **부분** | `scripts/stop.ps1:11`, `reset-demo.ps1:6` | TC-S9-046 | 직접 명령은 못 막음 |
| TW-30 | PIN 잠금 DoS | **수용 후보** | `core/pin.py` 전역 카운터 | TC-S9-011 | 재현됨 |
| TW-31 | 컨테이너 탈출 | **구현됨(Linux 한정)** | `compose.yaml:11-20` | TC-S9-059 | CapEff=0, seccomp 기본, 소켓 없음 |
| TW-32 | 앱 DB 계정 침해 | **구현됨(한계)** | `01-roles.sh:38-41`, `schema-grants.sql:8-11` | TC-S9-062·062b | 감사 외 표 수정 가능(DEF-9-014) |
| TW-33 | 설정 API 안전장치 우회 | **구현됨** | `routers/settings.py:40,94-98`, `config.py:8` | TC-S9-028 | |
| TW-34 | 문서·관리 경로 | **구현됨** | `app.py:110-112`, `core/guard.py:78` | TC-S9-015·057 | |
| TW-35 | SSRF | **해당 없음 확인** | 외부 호출 코드 없음 | TC-S9-020(소켓 차단 하 전 흐름) | M2 재평가 |
| TW-36 | web 침해 시 외부 경로 | **부분 → 범위 확대** | `compose.yaml:233,251-259` | TC-S9-061·078·083 | **internal 망 컨테이너(api·worker·db)도 자기 망 게이트웨이로 호스트 0.0.0.0 서비스에 도달(이번 회차 재측정)**; 인터넷 경로는 차단됨; edge 제거는 게시 불가(실측) → DEF-9-011 |

## 부록 B. 의존성 점검
### B-1 파이썬 (고유 36개 = 이름·버전 쌍: 백엔드 런타임 20·개발 추가 10·youtube_title 3 + CLI 직접 의존 3)
- **환각/유사 이름**: 36개 전부 `pypi.org/pypi/<name>/<ver>/json` 에 실존, 릴리스 이력 5~335개·최초 등록 2006~2025년(최근 6개월 안에 새로 등록된 패키지 0), **해시 잠금 33개의 해시가 PyPI 파일 해시와 전부 일치**(핵심 증거; 나머지 3개는 해시 없는 CLI 직접 의존 `google-*` 로 웹 이미지에 설치되지 않음), 고아(어떤 직접 의존에서도 도달 불가) 패키지 0 — `fastapi 0.143.0` 의 `requires_dist` 에 `opentelemetry-api`·`annotated-doc` 가 실제로 포함. 타이포 후보 0. 직접 의존 6개(fastapi·uvicorn·pydantic·sqlalchemy·alembic·psycopg[binary]) 모두 공식 프로젝트.
- **신선도(DEF-9-015)**: 2026-10-10 잠금 기준 7일 미만 — fastapi(10-08)·pydantic(10-08)·pydantic-core(10-08)·sqlalchemy(10-07)·opentelemetry-api(10-06)·iniconfig(10-06, dev).
- **취약점**: pip-audit 2.10.1 — `web/backend/requirements.txt`·`requirements-dev.txt`·`web/docker/requirements-youtube-title.txt`·루트 `requirements.txt`·`requirements-dev.txt` 전부 **0건**. 루트 requirements 는 직접 의존만 적혀 있어 전이 의존까지 풀어 설치한 환경(29패키지)도 검사 → 0건. **도구 감도 확인**: `requests==2.19.0`·`jinja2==2.10` 를 넣으면 PYSEC-2026-1471~1475 등이 검출됨.
### B-2 npm (384 패키지, 운영 의존 9)
- 전부 `registry.npmjs.org` 실존, **integrity(sha512) 레지스트리 값과 일치 384/384**, `resolved` 가 레지스트리 밖인 항목 0, 설치 스크립트 보유 `fsevents`(dev·선택)뿐(`--ignore-scripts` 로 미실행), `npm ls --all` extraneous/invalid 0.
- `npm audit`(전체·`--omit=dev`) **0건**(감도 확인: `lodash@4.17.15` → high 1). `npm audit signatures` 는 서명 키 조회 실패("Failed to download", 네트워크 제한) → **미수행**.
- 운영 의존 9: `react 19.3.0`·`react-dom`·`scheduler`·`react-router(-dom) 7.18.4`·`@tanstack/(react-)query(-core) 5.104.1`·`cookie 1.1.1`·`set-cookie-parser 2.7.2` — 전부 MIT, 메인테이너 공식 계정.
- 폐기 표시: `eslint 9.39.5`(npm "지원 종료", 개발 전용).
### B-3 베이스 이미지 (공식 레지스트리)
| 이미지 | 고정 다이제스트 | 2026-10-11 태그의 최신 다이제스트 |
|---|---|---|
| python:3.12-slim | `sha256:a6e34c59…c11b1` | 동일(오늘 재확인) |
| node:22-bookworm-slim | `sha256:c3de60bf…78392` | **미확인**(오늘 조회가 레지스트리 429 로 실패; 이전 세션 기록은 동일) |
| nginxinc/nginx-unprivileged:stable-alpine | `sha256:15c994d1…516e3` | 동일(오늘 재확인) |
| postgres:17-bookworm | `sha256:3645570c…03826` | 동일(오늘 재확인) |
### B-4 라이선스
- 파이썬 런타임 24개: MIT·BSD-3·Apache-2.0·PSF-2.0 중심, **`psycopg`·`psycopg-binary` = LGPL-3.0-only**(동적 사용·비수정·비배포 → 문제 없음. 이미지를 남에게 배포하면 고지·재링크 조건 필요). 개발 전용 `certifi` = MPL-2.0.
- npm 운영 의존 9개 전부 MIT. 개발 전용: MPL-2.0 13개(`lightningcss*`·`axe-core`), CC-BY-4.0(`caniuse-lite` 데이터), Python-2.0(`argparse`), BlueOak-1.0.0 4개, CC0 2개 — 번들에 들어가지 않음.
- 이미지 OS 패키지(Trivy 라이선스 스캔): api 625 항목·web 103·db 1,019 — GPL-2/3·LGPL 등 **배포판 기본 구성**. 앱 코드와 결합 링크하지 않음. 로컬 빌드·비배포라 충돌 없음. **상용/재배포 계획이 생기면 법무 확인 필요.**
- 결론: 상용/배포 목적과 충돌하는 강한 카피레프트(AGPL 등)가 앱 의존성에 섞여 있지 않다. `[확인 필요]` 재배포 시.

## 부록 C. 컨테이너 이미지 점검 (Trivy 0.75.0, 취약점·비밀·설정·라이선스)
| 이미지 | OS | 취약점(고유 CVE, 심각도) | 수정본 있음 | 비밀 | 설정 |
|---|---|---|---|---|---|
| api | Debian 13.7 | HIGH 8, MEDIUM 29, LOW 33, UNKNOWN 3 (OS) · pip 25.0.1: MEDIUM 5+LOW 1 | OS HIGH 전부 없음(affected 43·fix_deferred 1), pip 6개는 있음(26.x) | 0 | 0 |
| web | Alpine 3.24.2 | HIGH 1(tiff CVE-2026-4775), MEDIUM 1(zlib CVE-2026-85091) | 둘 다 있음 | 0 | 0 |
| db | Debian 12.15 | **CRITICAL 3**(libsqlite3 CVE-2025-7458, libxml2 CVE-2026-6653, zlib1g CVE-2023-45853), HIGH 22, MEDIUM 52, LOW 62 · gosu(Go 1.24.6): CRITICAL 1+HIGH 24 | OS 전부 없음, gosu 는 있음 | 0 | LOW 1(HEALTHCHECK 없음 — compose 에 정의됨) |
- 파일 트리 비밀 스캔(Trivy fs, 저장소 전체 – `.git`·node_modules·`.harness-tmp` 제외): **0건**. Dockerfile 설정 스캔: 3개 중 LOW 1건.
- 내용물 검사(레이어 직접 열람): api — `/app` 은 `ytweb`·`youtube_title`·alembic·config(`settings.yaml`·`banned_terms.yaml`·`settings.local.yaml.example`)뿐, **시험 파일·.env·비밀 없음**, `__pycache__` 만 root 소유 0644; 개발용 `requirements*.txt`·`pyproject.toml` 포함(DEF-9-009). web — `/usr/share/nginx/html` 은 `index.html`·`assets/index-*.js`(385 KB)·`style-*.css`·`favicon.svg`·`50x.html` 뿐, `.map`·테스트·`mock-server`·`sourceMappingURL` 0. db — `/backups` 0700 postgres, 스크립트 3개·pg_hba. 모든 이미지 `USER` 비루트, 세계 쓰기 파일 0, setuid 바이너리는 베이스 배포판 기본(`su`·`mount` 등 — `no-new-privileges`+`cap_drop` 로 무력).
- 번들에서 문구 검색: "법률 자문" 0, "면책" 0, "AI가 생성" 0, "표시광고" 0, "A/B 테스트" 0, "민감 주제" 1, "데모 모드" 3 → DEF-9-007·008 의 근거.
- 도달성 판단은 DEF-9-010 설명 참조. `pip` 취약점은 설치 시 `--only-binary` 라 sdist 추출 경로(CVE-2025-8869)가 열리지 않는다.

## 부록 D. SBOM
- 산출물 `docs/harness/sbom-web-m1/`(이번 회차 재생성): `api.image.cdx.json`(113 구성요소)·`web.image.cdx.json`(71)·`db.image.cdx.json`(150) — Trivy 이미지 SBOM(OS 패키지+언어 패키지+라이선스+의존 그래프, **CycloneDX 1.7**), `python-runtime.cdx.json`(24, cyclonedx-py environment, 1.6), `frontend-npm-all.cdx.json`(**382 고유 name@version**, 잠금 항목 384), `frontend-npm-prod.cdx.json`(9) — `web/tests_security/sbom_from_npm_lock.py`(잠금 파일 기반 CycloneDX 1.6, 해시·라이선스·의존 그래프 포함). **왜 직접 생성기인가**: `@cyclonedx/cyclonedx-npm 6.0.1` 은 `--package-lock-only` 에서 같은 이름·다른 버전의 중첩 12개를 합쳐 370개만 내고, 설치 기반 실행은 이 OS 에 설치되지 않는 선택 의존성을 뺀다(347개). 잠금 파일이 "설치 가능한 전부"의 근거이므로 도구 출력 대신 잠금 기반 산출물을 정본으로 하고 이 한계를 명시한다. 개인정보 최소화를 위해 패키지 유지보수자 **이메일 주소 302건을 제거**했다(이미지 SBOM 3종, 이름만 남김; 제거 후 purl 훼손 0 확인). 이미지 SBOM 의 metadata 이름은 `/in/x.tar` 대신 이미지 이름으로 바꿨다.
- **이전 SBOM(`docs/harness/sbom-web-m1.json`, 427개) 검토 결과**: ① npm 12개 누락(lock 382 고유 중 370), ② 파이썬 구성요소에 라이선스 없음, ③ 의존 그래프 없음, ④ 베이스 이미지는 "내용 미열거" — OS 패키지 없음, ⑤ 컨테이너 버전이 태그만. → 위 6종으로 **대체**한다(이전 파일은 삭제하지 않았으니 오케스트레이터가 폐기 여부 결정).
- 생성 도구 한계: 이미지 SBOM 의 이미지 ID 는 빌드마다 달라질 수 있다(재현 가능 빌드 아님).

## 부록 E. 변이 점검 (시험이 보안 통제 파괴를 잡는지 — 원본 소스 미수정, 사본에서만)
- 방법: `web/tests_security/mutation_check.py`. 사본 `.harness-tmp/sec/mut/` 에 한 곳만 고쳐 오프라인 시험을 돌린다. 대상 문자열은 **원본에 정확히 1곳**임을 자동 확인(아니면 오류). 동치 대조군 1곳(독스트링)은 "살아남는 것이 정상".
- 회전(이전 세션 기록): **코드 변이** 1회전 58곳 → 8곳 생존(시험 구멍) → 시험 보강 후 2회전 → 최종 회전 74곳. **설정 변이** 1회전 45곳 → 5곳 생존 → 보강 → 최종 45곳. **이번 회차 재실행(최종 시험·소스 기준)**: 코드 74곳 = **73 killed + 동치 대조군 1(독스트링만 변경, 생존이 정상)**, SURVIVED 0, ERROR 0 (2분할 병렬, 각 8~9분); 설정 45곳 = **45 killed**, SURVIVED 0 (1.6분). 합계 119곳 중 118 killed, 놓침 0. 참고: 변이 재실행 이후 `test_sec_03` 에 xfail 시험 1건(DEF-9-017)과 `test_sec_05`·`06` 이 추가됐으나 변이 점검 대상 시험(01·02, 설정은 03)의 기존 시험은 바꾸지 않았다.
- 1회전 생존과 조치: 교차 출처 별도 한도 제거(자체 상한 시험 추가)·CSV 주석 행(외부 값 주입 시험)·승인 1회용·승인 만료(경계 단위 시험)·감사 `prev_hash` 열·롤백 후속 변경·배치 확인 문구·`/docs` 노출(변이 자체가 동치였음 — `docs_url` 만 바꾸면 `openapi_url` 이 None 이라 라우트가 없음 → `openapi_url` 변이로 교체)·nginx assets location 헤더·X-Frame-Options 값·CSP 인라인 허용·앱 DB 슈퍼유저·해시 줄 주석 처리(정적 시험을 값·구조 검사로 강화)·PIN 실패 기록 commit·수정 가능 상태.
- 변이 목록 전체: `mutation_check.py` 의 `M`(코드)·`MC`(설정). 위협별 분포: TW-01~04·06~08·10·11·13·14·17·20·21·23·25·31~34 와 LLM01·02·05.

## 부록 F. 요청·질문
### F-1 규칙 H — `traceability.md` "비고" 컬럼에 "09단계 확인" 갱신 요청 (오케스트레이터가 반영)
| ID | 09단계 확인 결과 |
|---|---|
| S-W01 | 확인(127.0.0.1 한정 실측, Linux). Windows 미수행 |
| S-W02 | 확인(Host·Origin·Fetch-Metadata·CSRF·세션). PIN 꺼짐 시 같은 PC 프로세스 취득 가능 = 수용 대기 |
| S-W03 | 확인. 예외: GET 이 승인 만료 정리 수행(OBS-5) |
| S-W04 | 확인(쿠키 속성·헤더 7종, 모든 location·오류 포함) |
| S-W05 | 확인(소스 grep 0·ESLint·CSP·번들). 브라우저 미수행 |
| S-W06 | 부분(M1 모의 AI 범위 확인, 실서비스는 M3) |
| S-W07 | 부분(마스킹·최소 입력 확인 / 미리보기·고지 UI 없음) |
| S-W08 | 비밀 관리 확인 / OAuth 해당 없음(M2). **`.gitignore` 갭 DEF-9-006** |
| S-W09 | 확인(앱). nginx 오류 로그 DEF-9-016 |
| S-W10 | 해당 없음(업로드 없음). CSV 내보내기 수식 주입 방어 확인 |
| S-W11 | 확인(존재·해시·취약점·라이선스·설치 스크립트). 신선도 DEF-9-015 |
| S-W12 | 확인(PIN 동시성 PostgreSQL 실측). 이중 반영은 6·7단계 |
| S-W13 | 부분(입력 검증 DEF-9-001, SQL 바인딩 확인) |
| S-W13a | 확인(권한 공격 26종 거부) |
| S-W14 | 확인(Linux 엔진 inspect 실측) |
| S-W15 | 이 문서가 갱신 요청(부록 G) |
| S-W16 | 부분(앱 계정 변조 불가 실측, 키 없음 DEF-9-014) |
| D-02·D-03·D-04·D-05·D-06·D-07a | 확인 |
| D-10 | 부분(web edge 예외, DEF-9-011) |
| D-11 | 수행(Trivy+SBOM+pip-audit+npm audit, 결과 이 문서) |
| SEC-021 | 부분 / SEC-022·023·024·025·029 확인 / SEC-026 부분 / SEC-027 미구현(M3) / SEC-028 부분 / SEC-030 M1 정제 시험만(실서비스 M3) |
| POL-002 | **미구현(DEF-9-007)** — traceability.md 에 웹 행을 따로 두고 Not Done 으로 |
| POL-006·008 | **미구현/부분(DEF-9-008)** |
| POL-007 | M3 예정 |
| POL-012·016 | 미구현·미정(DEF-9-013) |
| POL-013 | 부분(사전 점검 경고 문구만; 확인 문구에 "A/B 테스트 중이 아님" 없음 — DEF-9-008) |
| POL-001 | 확인(건강·금융 엄격 모드, 키워드 25개 한계 OBS-3) |
| POL-005 | 확인(데모 배지 상시, TC-S9-079) |
| POL-014 | 확인(제외 영상 차단은 6단계 시험 근거; 9단계는 코드 정독) |
| SEC·POL 제안 ID 전체 | **traceability.md 미등록 — DEF-9-018** |
| D-01·D-07·D-07b·D-08·D-09·D-12·D-13·D-14 | 확인(부록 I 대응표) |
### F-2 11단계 문서 대조에 줄 사실 (실측으로 확인된 것)
1. `WEB_RUNBOOK.md` §13 "edge 제거 가능 여부는 미시험" → **시험함**: internal 단독 시 게시 불가(포트 매핑 무시), `isolated` 게이트웨이 모드는 internal 전용. 대안은 방화벽·중계 컨테이너.
2. `WEB_RUNBOOK.md` §13-1 C-7(면책·고지 없음)은 **정확**하다 — 9단계가 Critical/High 로 확정(DEF-9-007·008).
3. `WEB_RUNBOOK.md` §11: 4단계는 있으나 "비밀번호 교체 절차"는 **미검증**(Q-11-06). 제안: 임시 스택에서 `ALTER ROLE` 교체+컨테이너 재시작 절차를 시험으로 검증.
4. `WEB_INSTALL.md`/README 에 "web 컨테이너는 호스트 서비스·LAN 에 도달 가능(이론상)" 한 줄 추가 권고(DEF-9-011).
5. 백업: `restore.ps1` 는 `.sha256` 없으면 계속 진행(DEF-9-012) — 문서에 "`.sha256` 파일을 반드시 같이 보관"을 명시.
### F-3 질문 목록 (규칙 A — 사용자/오케스트레이터에게)
| # | 질문 | 추천 |
|---|---|---|
| Q-S9-1 | 면책·AI 고지 문구(POL-002·006·008·013)를 화면에 넣고 9단계 재검증을 받을까요? 문구 초안은 `WEB_LEGAL_NOTICE.md` 3-2 의 문장을 쓰면 됩니다. | **예, 즉시(W-FIX-4)** |
| Q-S9-2 | 롤백 정책: (a) 현재 제목이 방금 반영한 제목일 때만 허용 + (b) 제목만 현재값 위에 교체? 아니면 현행 유지(M3 전까지 보류)? | (a)+(b), M3 전 필수 |
| Q-S9-3 | web 컨테이너의 호스트·LAN 도달(DEF-9-011)을 수용(DEC-045 확장 기록)할까요, 아니면 방화벽 안내/중계 컨테이너로 줄일까요? | 우선 수용 + 설치 문서에 방화벽 안내 |
| Q-S9-4 | 이미지 취약점(DEF-9-010): 수정본이 없는 베이스 이미지 취약점을 "릴리스 전 재스캔, 수정본 나오면 갱신, 나머지 수용(DEC)" 방침으로 둘까요? | 예 |
| Q-S9-5 | 데이터 보관·파기·백업 암호화(DEF-9-013, Q-W2·Q-W4)와 **개인정보 처리 해당 여부(PIA·ISMS-P)** 는 전문가 확인이 필요합니다. 확인 대상으로 올릴까요? | 올림(M2 전) |
| Q-S9-6 | 감사 로그 체인에 키를 도입할까요(DEF-9-014, Q-W6)? | 도입 권장 |
| Q-S9-7 | 세션 유휴 만료(30분)·절대 8시간으로 줄일까요(DEF-9-003)? PIN 필수화(Q-W1) 시점은? | 줄임, M3 전 PIN 필수 |
| Q-S9-8 | CI 예시 워크플로를 실제로 활성화할 계획이 있나요(DEF-9-005)? 없으면 Deferred(DEC) 처리. | 계획 확정 전 Deferred |
| Q-S9-9 | 호출 지시의 "7절에 git status 원문"과 "git 명령 금지"가 충돌합니다. 오케스트레이터가 `git status`/janitor 결과를 7절에 덧붙여 주세요. | — |
| Q-S9-10 | POL-006·008 이 traceability.md 에 등록되면 DEF-9-008 을 Critical 로 올립니다(규칙 J). 등록 시점은? | 지금 등록 |
| Q-S9-12 | `.dockerignore` 를 허용 목록 방식으로 바꿀까요(DEF-9-017)? | 예 |
| Q-S9-13 | POL-006·008·013·SEC-021~030 을 traceability 에 정식 등록(DEF-9-018)하고 DEF-9-008 을 Critical 로 올릴까요? | 지금 등록 |
| Q-S9-14 | 법률 검토(면책·표시광고·AI 고지의 충분성, PIA·ISMS-P 해당 여부)를 누가 언제 받을까요? 이 문서는 판단하지 않았습니다. | 실연동(M2·M3) 전 전문가 확인 |
| Q-S9-11 | 이전 `sbom-web-m1.json` 을 폐기하고 `sbom-web-m1/` 로 일원화할까요? | 예 |
### F-4 M3 진입 차단 조건(지금 결함으로 세지 않지만 해결 전 M3 금지)
DEF-9-002 · SEC-021(지시/데이터 구획 — 보안 경계 아님을 문서화)·SEC-026(전송 미리보기·영상별 제외)·SEC-027(호출·토큰·비용 상한)·SEC-028(키 주입 경로)·SEC-030(인젝션 시험 세트 실서비스 수행)·Q-W10(AI topic 판정 의존 제거)·PIN 필수화·쓰기 재로그인·TW-15 재평가·`error_log` 요청 줄(DEF-9-016).

## 부록 G. 규칙 F — 위협 모델 갱신 요청 (`docs/yt/threat_model.md` Part W)
| 변경 | 내용 |
|---|---|
| TW-13 | "미수행" 항목 수행 완료: pip-audit 0건·npm audit 0건·Trivy·SBOM·환각 점검. 새 잔여: 베이스 이미지 미수정 CVE(DEF-9-010), pip 잔존(DEF-9-009), 신선도(DEF-9-015), 스캐너 서명 미검증 |
| TW-14 | "재현 확인" — 롤백이 제목·설명을 덮어씀(DEF-9-002) |
| TW-17 | 상태 유지, 잔여 = nginx 오류 로그 요청 줄(DEF-9-016) |
| TW-18 | 서술 정정: `.gitignore` 에 `client_secret*.json` 없음(DEF-9-006). 실스택에서 비밀 노출 0 확인 추가 |
| TW-20·03 | 세션 상한 20 축출(DoS) 추가(DEF-9-003) |
| TW-36(재측정) | internal 망 컨테이너(api·worker·db)도 호스트 0.0.0.0 서비스에 도달 — 3망 분리(DEC-045)는 인터넷 경로만 막음. 아래 기존 서술에 이어 반영 |
| TW-36 | **범위 확대**: 외부 인터넷뿐 아니라 호스트 게이트웨이의 0.0.0.0 서비스·LAN 도달(실측). edge 제거 불가(게시 불가 실측)를 근거로 추가. 위험도 "낮음~중" 유지 또는 "중" 상향 검토 |
| 신규 표면(제안 ID TW-37) | CI/자동화 공급망(예시 워크플로, 에이전트 `dontAsk` 실행 + 비밀) — DEF-9-005 |
| 신규(제안 TW-38) | 입력 경계: 상한 없는 정수 → 500·로그 폭증(DEF-9-001), `/audit` 는 행 수에 비례하는 검증 비용 |
| 신규(제안 TW-39) | 복원 경로 fail-open(해시 없으면 진행) + 덤프 내 SQL 실행(DEF-9-012) |
| 검증 대기 표 | V-9 닫음(수행 완료). V-1 중 6단계 결과에 더해 9단계 확인 |
| W4 LLM | LLM01·02·05·06 은 M1 모의 범위에서 확인됨으로, LLM10(호출 상한)·LLM07(키)·투명성(POL-006·008)은 계속 미구현 |

## 부록 H. 공격자 관점 — 시도한 것과 결과, 연쇄 공격
### H-1 막힌 시도(불성립, 근거는 4절)
Host/Origin/Sec-Fetch-Site 위조, 로그인 CSRF, 상태 변경 전수 CSRF, 세션 고정·재사용·평문 저장, PIN 추측(순차·동시·설정 API 경로), 요청 밀수(CL+TE·중복 CL·TE 변형·NUL·개행), 경로 순회·`.env`/`.git`/소스맵 탐침 21종, 오픈 리다이렉트, 느린 헤더, 크기 폭탄·JSON 깊이 폭탄, SQL 인젝션 9종, 저장형 XSS(제목·승인자·메모), CSV 수식 주입, 악성 AI 출력 11종, 승인 HMAC 변조·키 삭제·재사용·만료 연장, 감사 행 수정·삭제, 앱 DB 계정 권한 상승 26종, 다른 DB/계정 로그인, 백업 스크립트 이름 주입 16종, 컨테이너 내 쓰기·실행·권한 상승, web→db 도달, 컨테이너 로그·inspect·히스토리·덤프에서 비밀 찾기.
### H-2 연쇄 공격(카테고리를 가로지르는 경로 — 규칙 B 2차 검증)
| # | 경로 | 결과 | 연결 결함·질문 |
|---|---|---|---|
| CH-1 | 같은 PC 프로세스 → 위조 `Origin` 으로 세션 발급(PIN 꺼짐) → 제안 생성·승인(승인자 임의 이름)·배치·반영·롤백 전 과정 자동화 | **성립**(M1 은 모의라 피해 없음). M3 실채널이면 치명적 | TW-03 수용 질문, PIN 필수화·쓰기 재로그인 = M3 전 필수 |
| CH-2 | 인증 우회(CH-1) + 출력 새니타이즈 누락 → 저장형 XSS 로 CSRF 토큰 탈취 | **불성립**: 승인자/메모의 HTML 은 저장되나 React 텍스트 렌더, CSP `script-src 'self'`, API 응답 `application/json`+`nosniff` | 브라우저 실측 미수행 |
| CH-3 | 설명 속 지시문(프롬프트 인젝션) → AI 가 `topic=life` 주장 → 엄격 모드 우회 → 과장 제목 | **부분 성립**: 25개 키워드 밖 건강 용어에서는 엄격 모드가 꺼져 **경고 수준** 제목이 사람 승인만으로 통과(차단 판정 제목은 여전히 불가). M1 모의 AI 에서는 발생하지 않음 | TC-S9-026b, Q-W10, SEC-024 |
| CH-4 | DNS 리바인딩 → Host/Origin → 세션 발급 | 불성립(nginx 444 + 앱 403 이중) | — |
| CH-5 | 공급망(빌드 시 패키지 코드 실행) → 이미지 → web 컨테이너 → edge 망 → 호스트/LAN | 이론상 가능: 빌드는 해시·`--ignore-scripts`·다이제스트로 완화, 런타임은 비루트·읽기 전용·cap_drop 이나 **edge 경로가 호스트/LAN 으로 열려 있음** | DEF-9-011, DEF-9-010 |
| CH-6 | 호스트 비밀 파일 탈취 → DB 소유자 계정 → 감사 로그 재계산 | 성립(호스트 장악 = 범위 밖 AW-13) | DEF-9-014 |
| CH-7 | 세션 21개 생성 → 소유자 로그아웃 → (PIN 꺼짐) 재로그인 | 성립(가용성만) | DEF-9-003 |
| CH-8 | 세션 탈취 → PIN 변경/해제 | 불성립: 현재 PIN 필요, 틀리면 잠금 | TC-S9-011 |
| CH-9 | 백업 폴더 쓰기 → `.sha256` 삭제 → `restore.ps1` → 덤프 SQL 소유자 권한 실행 | 성립(호스트 사용자 권한 전제 = TW-12 수용 후보) | DEF-9-012 |
| CH-10 | api 침해(가정) → 자기 망 게이트웨이 → 호스트 0.0.0.0 서비스 → (호스트에 있는 다른 서비스) | 성립(Linux 실측) — 선행조건 api 코드 실행(비루트·읽기 전용·cap_drop 으로 완화) | DEF-9-011 (범위 확대) |
| CH-11 | AI 고지·표시광고 안내 부재 + 사람 승인(승인자 자유 입력) → 건강·금융 과장 제목이 "통과" 표시만 믿고 승인 | 부분 성립: 엄격 모드가 차단하는 제목은 막히나 경고 수준·목록 밖 키워드 제목은 승인 가능하고, 화면은 "검증 통과"가 법적 적합성이 아님을 알리지 않음 | DEF-9-007·008, OBS-3 |
### H-3 관찰(결함으로 세지 않음)
- OBS-1 쿠키 `Secure` 없음 — http://127.0.0.1 설계(Q-WA-1). OBS-2 내부 구간 TLS 없음(README §9). OBS-3 엄격 모드 키워드 25개 목록(CH-3). OBS-4 `planned` 잔류 시 해제 수단 없음(안전 쪽, 런북 필요). OBS-5 GET 이 승인 만료 정리 수행. OBS-6 루트 `requirements.txt`(CLI)는 해시 잠금이 아님(웹 이미지는 `requirements-youtube-title.txt` 해시 사용). OBS-7 scrypt N=2^14(OWASP 권고보다 약함; 4~12자리 PIN 은 잠금 정책이 방어선). OBS-8 `GIT연동(CLAUDE-TO-YOUTUBE)2222.MD` 에 소유자 이메일 주소 1건이 들어 있다(개인정보 최소화 관점에서 저장소 공개 여부 확인 필요; 사용자 본인 정보). OBS-10 `/api/readyz` 가 인증 없이 `mode`(demo/live)를 노출(Host 허용 요청 한정, 6단계 질문 W-BE-A). OBS-9 `.claude/settings.json` 이 `git add/commit/push` 를 무확인 허용 — 커밋 전 비밀 검사 훅이 없음(DEF-9-006 과 함께 보완 권장).

## 부록 I. 요구사항 ↔ 9단계 시험 대응표 (S-W01~S-W16, D-01~D-14 — 누락 0 확인)
> 근거: `웹프로그램으로수정요청.md` 7장(D-xx)·9장(S-W). "시험" 열은 TC-S9 묶음 ID(4절)이고 해당 없음/미수행은 사유를 적었다. 이 표에서 시험 연결이 비어 있는 행은 없다.

| 요구 | 9단계 시험·확인 | 결과 |
|---|---|---|
| S-W01 127.0.0.1 한정 게시 | TC-S9-050 | 충족(Linux). Windows 미수행 |
| S-W02 세션·CSRF·Host/Origin | TC-S9-001~007·011·012·051·057·065 | 충족. PIN 꺼짐 시 같은 PC 프로세스 취득 가능(TW-03 수용 대기) |
| S-W03 GET 상태 변경 금지·CSRF·확인 문구 | TC-S9-006·008·030·033 | 충족(OBS-5 GET 이 만료 정리 수행) |
| S-W04 쿠키·보안 헤더 | TC-S9-005·014·056 | 충족 |
| S-W05 XSS | TC-S9-022·045·079(번들) | 충족. 브라우저 미수행 |
| S-W06 프롬프트 인젝션 방어 | TC-S9-025·026·026b | M1 모의 범위 충족, 실서비스 M3(SEC-030) |
| S-W07 AI 전송 최소화·비용 상한 | TC-S9-020·025 | 부분(비용 상한·미리보기 M3) |
| S-W08 비밀·OAuth state/PKCE | TC-S9-040·040b·060·073·084·085·081 | 비밀 관리 충족, OAuth 해당 없음(M2). DEF-9-006·017 |
| S-W09 로그 JSON·마스킹·오류 비노출 | TC-S9-016·032·060·082 | 충족, DEF-9-016 |
| S-W10 업로드 검증 | (해당 없음: 업로드 기능 없음, M2) CSV 내보내기 TC-S9-024 | 해당 없음 |
| S-W11 의존성 실존·라이선스·취약점·고정 | TC-S9-044·070~072·076, 부록 B | 충족, DEF-9-015 |
| S-W12 동시성·이중 반영 | TC-S9-028·065 (재시작 중 이중 반영은 7단계) | PIN 직렬화 실측 충족 |
| S-W13 크기·속도 제한·SQL 바인딩 | TC-S9-012·013·017·021·055·066 | 충족, DEF-9-001 |
| S-W13a DB 보안 | TC-S9-050·060·062·063 | 충족, DEF-9-014 한계 |
| S-W14 컨테이너 격리 | TC-S9-042·059·061·080 | 충족(Linux), DEF-9-011 |
| S-W15 위협 모델 갱신 | 부록 G (갱신 요청) | 요청함(오케스트레이터 반영) |
| S-W16 감사 로그 추가 전용 | TC-S9-029·062·062b | 충족(앱 계정 기준), DEF-9-014 |
| D-01 compose 4서비스·healthy 순서 | 실스택 기동(전 서비스 healthy), TC-S9-042 | 충족. dev/test 프로필 미구현(6단계 기록) |
| D-02 127.0.0.1 게시 | TC-S9-042·050 | 충족 |
| D-03 비루트·읽기 전용·cap_drop | TC-S9-042·059·080 | 충족 |
| D-04 다이제스트 고정·멀티스테이지 | TC-S9-041·075·080 | 충족, DEF-9-009 |
| D-05 .dockerignore·이미지에 비밀 없음 | TC-S9-040·060·073·075·080·081 | 비밀 0, DEF-9-017 |
| D-06 비밀은 secrets 파일 | TC-S9-042·060 | 충족 |
| D-07 명명 볼륨·down -v 금지 | TC-S9-042·046 | 충족 |
| D-07a PostgreSQL 하드닝 | TC-S9-043·062 | 충족 |
| D-07b Alembic 만으로 스키마 변경 | TC-S9-062(앱 계정 DDL 거부)·064(migrate 후 흐름) | 충족 |
| D-08 헬스체크·재시작·로그 제한 | TC-S9-042·059 | 충족(우아한 종료는 7단계) |
| D-09 시간대 | TC-S9-009(만료 시각)·정독 | 충족 |
| D-10 internal 네트워크 | TC-S9-061·078·083 | 부분(DEF-9-011) |
| D-11 이미지 취약점·SBOM | TC-S9-070~076, 부록 C·D | 수행(Trivy, Docker Scout 미수행), DEF-9-010 |
| D-12 Windows 스크립트 | TC-S9-046 (정적), 복원 fail-open 정독 | 정적 충족, DEF-9-012. Windows 실행 미수행 |
| D-13 harness-tmp 접두사·정리 | 이 감사 자체(접두사 `harness-tmp-sec`, 7절) | 충족 |
| D-14 자원 상한 | TC-S9-042·059 | 충족 |

## 부록 J. 규칙 I(규제 민감)·규칙 J(AI) 항목별 실제 반영 여부
| ID | 요구 | 실제 화면·코드 | 판정 |
|---|---|---|---|
| POL-001 | 건강·금융 엄격 모드 | `ai/guard.py`·검증기 구현, 화면 "엄격 모드" 배지+안내문, TC-S9-026 | 구현(키워드 25개 한계 OBS-3) |
| POL-002 | 면책 문구 상시 표기 | 화면·번들·API 0건 | **미반영 — DEF-9-007 Critical** |
| POL-005 | 데모 모드 상시 표시 | `Layout.tsx` `demoBadge`, 번들 3회 | 구현 |
| POL-006 | AI 생성 고지 문장 | "AI 제안" 배지만, 문장 없음 | **미반영 — DEF-9-008 High** |
| POL-008 | AI 한계·표시광고 규정 확인 | 없음 | **미반영 — DEF-9-008** |
| POL-013 | A/B 테스트 확인 | 서버 사전 점검 경고 1줄만, 확인 문구 없음 | 부분 — DEF-9-008 |
| POL-014 | 제외 영상 4단계 차단 | `domain/exclusions.py`(정독) | 구현(동작 시험은 6단계) |
| POL-007·012·016 | 외부 전송 고지·보관·백업 정책 | M3 예정/미구현 | M3·DEF-9-013 |
| SEC-021 | 입력 비신뢰·정제·상한 | `ai/guard.py`, TC-S9-025 | 부분(구획은 M3, 보조일 뿐) |
| SEC-022 | AI 도구 권한 0 | `TitleSuggester.suggest()` 가 세션·게이트웨이를 받지 않음, TC-S9-020(소켓 차단 하 전 흐름) | 구현 |
| SEC-023 | 응답 스키마·길이·URL 폐기 | TC-S9-026 (11종) | 구현 |
| SEC-024 | AI 후보도 검증기·엄격 모드 | TC-S9-026·026b | 구현(키워드 한계) |
| SEC-025 | 사람 승인 없이 반영 불가 | TC-S9-027 | 구현 |
| SEC-026 | 전송 최소화·마스킹 | TC-S9-025 | 부분(미리보기·영상별 제외 없음, M3) |
| SEC-027 | 호출·비용 상한 | 코드 없음(M1 모의) | **미구현(M3 진입 차단)** |
| SEC-028 | 키는 secrets·프롬프트 원문 비저장 | `prompt_hash` 만 저장 | 부분(M3) |
| SEC-029 | AI 응답은 텍스트로 렌더 | 소스 grep 0·ESLint·TC-S9-022 | 구현 |
| SEC-030 | 인젝션 시험 세트 | M1 정제 시험만 | 실서비스 M3 |
| 프롬프트 인젝션 직접 재현 | 설명 속 지시문·역할 탈취·링크/연락처·`tool_calls` 형식 | 모의 AI 출력 정제로 차단. M1 은 실제 LLM 이 없어 지시문이 모델에 도달하지 않음 | 불성립(M1 범위) |
| 출력 기반 XSS | `<script>`·`<img onerror>` 제목 | 검증기 차단 + React 텍스트 렌더 + API JSON/nosniff/CSP none | 불성립 |
| 모델 거버넌스 | 자체 학습/운영 ML 모델 | 없음(모의 제안기 + M3 외부 서비스) | 해당 없음(대상 없음) |
| 관할 | 적용 법규 기준 | decisions.md 기본 대한민국 — 법적 충분성 판단 없음, 전문가 확인 필요 | — |

## 부록 K. 비밀 유출 점검 (현재 트리 + 저장소 이력)
- 현재 트리: Trivy fs(비밀·설정, 저장소 전체 – `.git`·`node_modules`·`.harness-tmp` 제외) 비밀 0·설정 LOW 1, 시험 `test_sec_03` 비밀 패턴 14종 0건·비밀형 파일 0건.
- 이력(96커밋, 전 브랜치, **읽기 전용 git**): ① 파일명 검색 — `.env`·`token*.json`·`client_secret*`·`credentials*.json`·`*.pem`·`*.key`·`*.p12`·`secrets/`·`data/`·DB 덤프 이력 **0건**. ② 추가 줄(+) 정규식 — Google API 키(`AIza…`)·Anthropic/OpenAI 키·개인키 블록·GitHub 토큰·AWS 키·Slack 토큰·OAuth 액세스/리프레시 토큰(`ya29.`·`1//0`)·클라이언트 ID(`*.apps.googleusercontent.com`)·`refresh_token` JSON·`password/secret/token/api_key = "…16자+"` 패턴. 일치한 줄은 전부 시험 더미(`FAKE…`·`…EXAMPLE`·`topsecretvalue`·`SuperSecretValue-12345`·`GOCSPX-fakeclientsecret…`)로 **실제 비밀 0건**.
- 한계: 정규식 기반이라 임의 형식 비밀은 놓칠 수 있다(gitleaks 등 전용 도구는 이 환경에서 미사용). 커밋 전 비밀 검사 훅이 없다는 점은 OBS-9·DEF-9-006 에 기록.
- OBS-8: `GIT연동(CLAUDE-TO-YOUTUBE)2222.MD` 에 소유자 이메일 1건 — 사용자 본인 정보, 공개 저장소 여부 확인 필요.


---

# 개정 2판 — 9단계 보안 재검증 (2026-10-11, M2 구글 읽기·M3 쓰기 게이트웨이·W-FIX 이후)

> **한 줄 결론: 판정 FAIL.** DEF-9-007(Critical)·DEF-9-008(High)은 **닫혔다**(직접 확인). 그러나 **DEF-9-002(롤백이 Studio 수정 내용을 덮어씀)가 실제 모드(M3)에서 재현되어 High 로 확정**됐고, 신규 Medium 4건·Low 5건이 열려 있다. High 가 닫히기 전에는 실제 모드(`YTWEB_LIVE_WRITE=1`) 활성·12단계 배포 승인을 올리지 않는다. **데모 모드(M1)만 쓰는 범위는 새 Critical/High 가 없다.** 소스는 고치지 않았다(결함은 재현 시험 + 권고).
> 이 문서는 정적 분석·코드 리뷰·로컬 재현(가짜 구글)에 한정한다. **법률 자문이 아니다**: 면책·AI 고지·A/B 확인 문구의 법적 충분성은 판단하지 않으며 공개·실연동 전 전문가(변호사 등) 확인이 필요하다. 개인정보 영향평가(PIA)·ISMS-P 해당 여부는 판단하지 않고 **"확인 필요"**로 둔다.

## R0. 침투/동적 점검 범위
| 항목 | 내용 |
|---|---|
| 대상 | `web/backend/ytweb/**`(특히 `youtube/google_oauth.py`·`live_read.py`·`live_write.py`, `routers/google.py`, `domain/live_gateway.py`·`batches.py`·`changes.py`, `core/logsetup.py`·`guard.py`), `web/frontend/src`·빌드 번들 `web/frontend/dist`, `web/compose.yaml`+`compose.online.yaml`(`docker compose config` 렌더링), `web/.env.example`, 의존성 잠금 파일 3종, 위협 모델 W9(TW-37~44) |
| 환경 | 로컬 파이썬 3.13 venv(`.harness-tmp/venv_fix_be`), 임시 SQLite, **가짜 구글(`web/backend/tests/verify_m23/fakegoogle.py`: `urlopen` 대체 + loopback 외 이름 해석 차단)**. 컨테이너 스택은 올리지 않았다(`harness-tmp-s2` 컨테이너·볼륨·네트워크·이미지 0개, 포트 18084 미사용, PostgreSQL 전용 DB `ytweb_test_s2` 미사용) |
| 허용한 기법 | 코드 정독, Host/Origin/Sec-Fetch-Site/CSRF 위조, 교차 사이트 GET 콜백 재생·재사용·교차 종류 시도, 허용 목록 변형 15종(대소문자·공백·NBSP·제로폭·전각·경로·쿼리·쉼표·와일드카드 등), 환경변수 파싱 변형, 모드 전환 중 확정 배치, 롤백 모드 불일치, 모호 응답(타임아웃·5xx) 재시도, 비밀 카나리 문자열의 응답·DB·로그 전수 검색, 소스 사본 변이 7곳, pip-audit/npm audit(레지스트리 조회) |
| 금지·하지 않은 것 | 실제 구글·유튜브·AI·외부 호출(가짜 구글이 비허용 호스트 호출 시 즉시 오류), 운영 8080·남의 컨테이너·포트 18080~18083 접촉, 소스 수정, git 커밋/푸시 |
| 하지 못한 것 → 규칙 A | 외부 침투 테스트·Windows Docker Desktop 실측·실제 구글 OAuth 동의 화면(데스크톱 클라이언트가 `http://127.0.0.1:8080/...` 복귀 주소를 구글이 받는지)·실제 브라우저 CSP 로그·실서비스 LLM 인젝션은 전문 업체/별도 승인된 점검이 필요하다. 컨테이너 이미지 취약점 재스캔(Trivy 바이너리 없음)·실스택 시험 `test_sec_04`·번들 시험 4건(스택 필요)은 **미수행**(사유·잔여 위험은 R8) |

## R1. 개요
- 목적: ① 기존 보안 시험 재실행으로 DEF-9-007·008 종결 확인, ② M2·M3 신규 공격면(TW-37~44) 점검, ③ 의존성·이미지·개인정보·규제 재확인. 입력: `security-web-m1-test.md`(FAIL), W-FIX/M23 검증 결과서 3건, 위협 모델 W9.
- 시험 자산: 기존 `web/tests_security/` + **신규 `test_sec_09_m23_attack.py`(61건, 이 회차에 추가)**. 실행: 신규는 `cd web/backend && python -m pytest ../tests_security/test_sec_09_m23_attack.py -p no:cacheprovider -o addopts='' --noconftest`, 전체 오프라인은 `python -m pytest web/tests_security --ignore=web/tests_security/test_sec_04_live_stack.py -p no:cacheprovider`.

## R2. 범위 / 제외
포함: 위 R0 대상 전부. 제외(미수행): 컨테이너 이미지 Trivy 재스캔, 실스택 `test_sec_04`, 번들 4건(`YTWEB_SEC_LIVE_PORT` 필요 — 대신 `web/frontend/dist` 번들 파일을 직접 검색해 확인), 변이 점검기 `mutation_check.py` 전체(1시간) — 대신 이 회차 신규 시험에 대해 변이 7곳만 수행.

## R3. 환경 / 도구
Linux 6.18, 파이썬 3.13, pytest, pip-audit(임시 `--target` 설치, `.harness-tmp/s2`), npm 10대(`npm audit --package-lock-only`), Docker 29.8.2(`compose config` 렌더링만). 임시 산출물은 모두 `.harness-tmp/s2/` 아래, 정리 결과는 R7.

## R4. 테스트 케이스 및 결과

### R4-1. 기존 보안 시험 재실행 (첫 실행 결과 그대로)
명령: `python -m pytest web/tests_security --ignore=…test_sec_04_live_stack.py`(신규 파일 추가 전 첫 실행, `-x` 없이). **첫 실행 결과: 4 실패 · 245 통과 · 7 건너뜀 · 2 xfail** (45.5초, 재측정 값; 첫 실행 원문 로그는 `docs/harness/verify-logs/web-security-rev2-raw/run1_full.log`).
| 실패 시험 | 원인(제품 결함인가?) | 판단 |
|---|---|---|
| `test_sec_02::test_ytweb_has_no_outbound_capable_imports` | `youtube/{google_oauth,live_read,live_write}.py` 가 `urllib.request` 를 임포트. M2·M3 의 **의도된 외부 통신 3개 모듈**(TW-44 허용 파일 3개)을 옛 시험이 모르는 것 | 시험 자산 미갱신. 의도와 일치하는지는 신규 `test_d4`(정확히 그 3개만 허용)로 별도 확인. **기대값을 고쳐 통과시키지 않았다** → DEF-9B-006 |
| `test_sec_03::test_no_secrets_in_current_tree` | 적중 3건: `verify_m23/test_vm_05_live_write.py:27`(`RT-WRITE-X`)·`test_vm_03_live_read.py:258`(`R-REVOKED-SECRET`)·`web/tests_infra/test_vinf2_live.py:577`(`VIFFAKESECRET…`) — **모두 가짜 시험 값**(실제 비밀 0, 직접 확인) | 오탐. 신규 시험 파일이 allowlist 에 없음 → DEF-9B-006 |
| `test_sec_03::test_no_secret_like_files_in_tree` | `web/.env.example`(이름이 `.env.*` 패턴). 내용은 `YTWEB_LIVE_WRITE=0`·`YTWEB_LIVE_ALLOWED_VIDEOS=` 두 줄(비밀 아님) | 오탐 → DEF-9B-006 |
| `test_sec_03::test_powershell_scripts_have_no_dangerous_constructs…` | `e2e.ps1:19` 의 `Invoke-WebRequest`(기본 대상 `http://127.0.0.1:8080/api/healthz`, `-Base` 매개변수로 바꿀 수 있음) | 시험 규칙이 새 스크립트를 모름. 기본값이 loopback 이라 실제 위험은 Low → DEF-9B-006 |
- **xfail 전환 확인**: 이전 xfail 15건 중 DEF-9-001×2·006×1·007×3·008×5·017×2 의 표식이 제거되어 **통과**(XPASS strict 실패 0건). 남은 xfail 2건 = **DEF-9-002**(`test_rollback_should_refuse_when_title_was_changed_elsewhere`, `…not_overwrite_description_edited_elsewhere`) → 아직 안 고쳐졌다. DEF-9-001 은 직접 재확인: 2⁶⁴ 급 정수 ID 를 `/batches/{id}`·`/changes?page=`·`?batch_id=`·롤백·배치 생성에 넣으면 전부 422(이전 500) — 닫힘.
- **DEF-9-007·008 종결 직접 확인** (R4-4 참고): 통과.

### R4-2. 신규 시험 `test_sec_09_m23_attack.py` — 61건
**첫 실행 결과(실패 포함)**: 작성 직후 1차 46건 중 `test_c4` 1건 실패(롤백 요청에 `Idempotency-Key` 헤더 누락 → 400; **시험 쪽 오류**, 헤더 추가), 이어서 `test_a7` 실패(롤백 성공 코드를 200 으로 가정했으나 201; 시험 오류, 수정), `test_f2` 실패(번들에 "실제 실행" 문구가 없다고 단정 — 이 문구는 서버가 만들어 줌; 시험 오류, 해당 문구 제외). **제품 코드 결함으로 인한 실패는 0건**이었고, 최종 61건 통과. 제품 결함은 `repro_` 성격의 시험(통과 = 결함 재현)으로 고정했다.
| 그룹 | 건수 | 확인한 것 | 결과 |
|---|---|---|---|
| A. OAuth 콜백(TW-37·38·42) | 9 | 위조 state 는 구글 호출·토큰 저장 0; state 1회용(재사용 시 교환 시도 0); 10분 만료; 읽기/쓰기 종류가 다른 저장소에 안 섞임; 복귀 주소 항상 `/#/`(next/redirect/redirect_uri/Referer/X-Forwarded-Host/Origin 변조에도), `Cache-Control: no-store`, 쿠키 미설정; 비허용 Host 403; 인가 URL 은 `accounts.google.com` 고정+PKCE S256+state≥43자; 토큰 파일 0600·`.tmp` 잔재 없음; **비밀 카나리(AT/RT/클라이언트 비밀) 전수 검색**: 읽기·쓰기 연결→배치→실제 반영→롤백→연결 해제 한 사이클 후 모든 API 응답·**DB 전 테이블**·로그 줄에 0건 | 통과. 단 **A6 관찰**: 비밀 폴더가 `0755`(→ DEF-9B-004), **A8 관찰**: 구글 오류 문자열이 길이 제한 없이 감사 기록 detail 에 들어감(3,344자 재현, → DEF-9B-005), **A9**: 세션 없는 교차 사이트 GET 25회 → 감사 기록 25행(→ DEF-9B-001) |
| B. 허용 목록(TW-39) | 33 (변형 15·본문 1·파싱 6·플래그 10·설정 API 1) | 변형 15종(대소문자·앞뒤 공백/개행·제로폭·전각·`/../`·`?part=status`·쉼표 연결·`*`·빈 값·길이 ±1·`%00`) 전부 **네트워크 호출 전** `not_allowed`; 본문 id 불일치·snippet 형식 오류 7종 거부, 정상 1건만 고정 URL `…/videos?part=snippet` 로 전송; 환경변수 파싱은 정확 일치(와일드카드 없음), `YTWEB_LIVE_WRITE` 는 정확히 `"1"` 만 켜짐(`true`·` 1`·`01`·`on`·`1\n` 모두 꺼짐 — fail-closed); 설정 API 로 live 키 5종 설정 시도 400, `daily_apply_cap` 10,000 → 거부 | 통과 |
| C. 모드 전환·롤백·모호 응답·감사(TW-40·41) | 9 | 실제 모드로 확정 후 데모로 전환 / 데모로 확정 후 실제로 전환 → 둘 다 `live_mode_changed` 로 중단, PUT 0건; 실제 모드에서 데모 문구·`실제 실행 1건​`·전각 숫자·NBSP 확인 문구 422; 롤백 `live_mode_mismatch` 409; 타임아웃(미반영)·5xx(반영됨) 모호 응답 후 틱 4회·재배치에도 **PUT 정확히 1회**(planned 유지); 허용 외 영상 PUT 0; 감사 기록에 연결 시작·연결·쓰기 연결·배치 실행·변경 적용·연결 해제·롤백 존재 | 통과 |
| D. 외부 호출 경로(TW-35·44) | 4 | http/file/ftp/대문자 스킴/공백 스킴을 읽기·쓰기·OAuth 전송 3종이 모두 거부; `read_snippet` 이 영상 ID 를 쿼리 한 매개변수로 인코딩(`&part=status&id=…#frag` 주입 불가); `urllib.request` 임포트 파일이 정확히 3개; **D3 재현: 3xx 리다이렉트 시 Authorization 헤더가 다른 호스트로 따라감**(urllib 기본 동작, → DEF-9B-003) | 통과(D3 은 결함 재현) |
| E. 롤백 덮어쓰기 | 1 | **실제 모드** 반영 후 사람이 Studio 에서 설명과 제목을 고쳤다고 가정하고 롤백 → 201 로 성공, 설명·제목이 반영 전 백업 값으로 되돌아가 **Studio 수정이 사라짐** | **DEF-9-002 재현(High)** |
| F. 규칙 I·J (DEF-9-007·008) | 2 | 사전 점검 응답 `notice`=면책 문구, 리포트 `notes` 에 면책 포함; **빌드 번들**에 면책·AI 고지·A/B 확인·실제 수정 모드 배지 문구 존재 | 통과 |
| G. 신규 POST 3종 CSRF | 3 | `connect`·`connect-write`·`disconnect`: CSRF 토큰 없음/틀림/다른 Origin/`Sec-Fetch-Site: cross-site`/세션 없음 → 거부, GET·PUT·DELETE·PATCH 로 호출 불가 | 통과 |
- **변이 점검(신규 시험의 실효성, 소스 사본에서만)**: 허용 목록 검사 제거(15건 실패 검출), `live_mode_changed` 제거(2), 롤백 모드 불일치 제거(1), 토큰 파일 권한 0666(1), state 1회용 제거(1), 실제 모드 확인 문구 데모와 동일화(1), 토큰을 로그에 남기는 줄 주입(1) = **7/7 검출**. 처음 한 번은 사본 경로 설정 오류(`banned_terms.yaml` 없음)로 4곳이 "오류"만 나와 검출로 세지 않았고, 환경을 고쳐 다시 돌려 확인했다.

### R4-3. 위협 모델 W9 TW-37~44 확인 (구현 여부·서술 정확도)
| TW | 위험도(모델) | 완화책이 코드에 있는가 | 모델 서술과 차이 / 비고 |
|---|---|---|---|
| TW-37 로그인 CSRF·콜백 위조 | 중 | **있음** — `PendingAuth`(256비트·1회용·600초·최대 20개)·PKCE S256(`google_oauth.py:67-85,99-105`), 길이 상한(`routers/google.py` code 2048·state 256), 실패 시 저장 0, 고정 복귀 `/#/`. | "모든 시도 감사 기록"은 **세션 없는 교차 사이트 요청도 매번 감사 행을 만든다**는 뜻이 됨 → DEF-9B-001(모델 미서술). 요청한 쿠키 비결합·http 루프백은 모델 서술대로 |
| TW-38 쓰기 토큰 탈취 | **상** | **부분(모델 서술대로)** — 별도 파일 0600 원자 저장·Docker secret·응답/로그/DB 에 없음(위 A7 카나리 0건)·연결 해제 시 둘 다 삭제. 암호화 없음·구글 revoke 호출 없음 | **누락 서술**: 비밀 폴더 0755(DEF-9B-004); 화면의 [연결 해제] 안내에 구글 계정에서 앱 접근 제거 안내가 없음(EVT-001 은 CLI 에서 "계정 회수 절차 안내"를 요구, 웹 `WEB_RUNBOOK` 에만 있음) → DEF-9B-008. SEC-015 "쓰기 토큰은 실행 순간에만 로드"는 웹에서 **상태 조회·사전 점검마다 api 가 쓰기 토큰 파일을 읽는** 구현으로 다름(Low) |
| TW-39 허용 목록 우회 | 중 | **있음** — 4겹 검사(`_eligibility`·`_apply`·`rollback_change`·`LiveYouTubeGateway.update_snippet`) 모두 확인, 우회 변형 15종 거부 | 서술 오류: "환경변수를 컨테이너에 넣는 공식 절차가 아직 없어(Q-11-10)"는 **낡음** — `compose.online.yaml`+`web/.env.example` 가 전달 경로(비밀 없음, 확인). "목록이 비면 수정 0건"은 정확히는 **게이트웨이가 모의로 바뀜**(`select_gateway`)이라 결과는 같음 |
| TW-40 확인 문구 우회 | 중 | **있음(서버)** — `confirm_text` 실제/데모 구분, 변형 4종 거부, `live_mode_changed` | **낡은 서술**: "DEF-VMF-001(High) 수정 전 실제 연결 금지" → 상단 배지는 `dashboard.mode==='live'`로 이제 '실제 수정 모드'를 표시(`Layout.tsx:11-20`, 번들 확인)해 해결된 것으로 확인(TC-VMF-140~142). **A/B 확인은 아직 화면 체크박스뿐 — 서버가 요구하지 않음**(`ExecuteIn` 에 필드 없음) → DEF-9B-002 |
| TW-41 모호 응답 | 중 | **있음** — `_confirm_indeterminate`, planned 유지, 롤백도 `change.rollback_failed`+planned. 이중 반영 0 확인 | 정확. 단 롤백 덮어쓰기는 모델에 없음 → DEF-9-002 |
| TW-42 로그·응답 비밀 | **상** | **있음** — 카나리 전수 검색 0건(응답 9종·DB 전 테이블·로그), OAuth 오류는 고정 한국어 | "구글 오류 응답 본문이 예외 메시지로" 우려: 본문은 쓰이지 않고 `error` 코드 문자열만 `e.code` 로 감사에 들어감(길이 무제한) → DEF-9B-005 |
| TW-43 쿼터 | 중 | **있음** — `reserve_calls`(전부 또는 무), 일 상한, 설정 API 상한 1~20 | 정확 |
| TW-44 egress | 중 | **있음** — `docker compose config` 렌더링: api·worker 만 `egress`(비-internal) 추가, db·web·migrate 는 미연결, 환경변수 3종 비밀 아님 | api 는 외부에서 오는 HTTP 입력을 받는 컴포넌트이면서 egress+쓰기 토큰+DB 비밀번호를 모두 가짐 — 모델이 이 조합의 영향(침해 시 토큰·데이터 외부 반출)을 "중"으로만 봄 → DEF-9B-009 |

### R4-4. DEF-9-007·008 종결 — 직접 확인
- **면책(POL-002)**: 문구 `이 검증은 법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다.` — 위치: ① `ko.ts:42` 한 곳 정의 → 전 화면 푸터 `app/Layout.tsx:128`, 영상 상세 `VideoDetailPage.tsx:116`, 제안 카드 `SuggestionCard.tsx:283`, 배치 사전 점검 `BatchDetailPage.tsx:156`; ② API: 사전 점검 `precheck.notice`(`batches.py:214`), 리포트 `notes[0]`(`reports.py:76`, CSV 에도) — 신규 `test_f1` 로 응답 확인; ③ 빌드 번들 `dist/assets/index-*.js` 에 문구 존재(`test_f2`). 서버/CLI/프런트 문장 동일성은 기존 `test_sec_08`(통과).
- **AI 고지(POL-006)**: `ko.ts:44` "AI가 생성한 제안입니다. 사람이 검토하고 승인한 제목만 반영됩니다." 번들 확인.
- **A/B 확인(POL-013)**: 실행 확인창에 체크박스 `ko.ts:49` 를 체크해야 버튼 활성(`BatchDetailPage.tsx:285-310`, 기존 `test_sec_08` 이 게이트를 검사). **서버 강제는 없음**(DEF-9B-002).
- 실제 렌더링된 컨테이너 화면·브라우저 캡처는 이 회차에 **미수행**(스택 미기동). 번들 파일 검색 + 소스 + 응답 JSON 으로 확인.

## R5. 커버리지
기존 오프라인·정적 시험 258건(통과 245·건너뜀 7·xfail 2·실패 4=시험 자산 문제) + 신규 61건 = **319건: 통과 306 · 실패 4 · 건너뜀 7(모두 컨테이너 스택 필요) · xfail 2**. 신규 공격면 TW-37~44 8개 전부 시험 또는 코드 확인. 미수행: R2.

## R6. 결함 목록 (DEF-9B-NNN 신규, 기존 ID 는 상태 갱신)
| ID | 설명 (관련 ID) | 재현 절차 | 심각도 | 상태 | 권고 |
|---|---|---|---|---|---|
| **DEF-9-002** | **롤백이 "현재 제목 == 방금 반영한 제목"을 확인하지 않고 백업 snippet 통째로 되돌려 쓴다 → 반영 후 Studio 에서 고친 설명·태그·제목이 옛 값으로 덮어써진다.** M3 에서 실제 쓰기 가능해져 **High 로 확정**(1판 6절이 예고한 승격 조건). 관련 TW-14, TW-41, SEC-015/롤백 요구, 사업 영향: 채널 소유자 작업물 소실(복구는 사람이 Studio 이력에서 수동). `changed_since_backup` 은 덮어쓴 **뒤에** 기록만 함(`changes.py:~150`) | `cd web/backend && python -m pytest ../tests_security/test_sec_09_m23_attack.py -k e2 --noconftest -o addopts=''`(통과 = 재현). xfail 2건(`test_sec_02`)도 아직 xfail | **High** | **Open** — 백엔드 소유, 설계 결정 Q-S9-2(미응답) | 롤백 전에 `current.title == target.new_title` 및 보존 필드(`description/tags/categoryId/…`)가 `target.backup_snippet` 과 같은지 확인하고 다르면 `later_edit_exists` 409 로 거부(또는 제목만 바꾸는 본문 + 확인 문구). 고치면 xfail 2건이 XPASS 로 바뀌므로 표식 제거 |
| **DEF-9B-001** | **세션 없는 교차 사이트 GET `/api/v1/google/callback` 이 임의 state 로 감사 기록 행을 만들고(`google.connect.failed`) 화면 안내문(`last_error`)을 바꾼다.** 악성 웹페이지가 `<img src=…/callback?state=x>` 를 반복 호출 → 교차 사이트 한도(분당 600)까지 감사 로그 오염(보관 만료 없음 DEF-9-013 과 결합해 누적), 정상 이벤트 묻힘, 소유자에게 "구글 로그인이 취소됐거나…" 거짓 안내 표시. state 를 모르면 토큰 저장·구글 호출은 불가(확인) (TW-37, S-W03 예외, SEC-008) | 신규 `test_a9`(세션 쿠키 없이 25회 → 감사 25행) | **Medium** | Open | 알 수 없는/만료 state 는 감사·`last_error` 없이 즉시 303; 유효 state 에 대해서만 기록. 콜백 경로 별도 분당 한도(예: 10) |
| **DEF-9B-002** | **'A/B 테스트 중이 아님' 확인이 화면 체크박스뿐이고 서버는 요구하지 않는다**(`ExecuteIn` 에 필드 없음). 같은 PC 의 비브라우저 프로세스(TW-03·24 한계)나 UI 우회 호출은 실제 모드 배치를 확인 없이 실행(문구 `실제 실행 N건`만 필요). POL-013 규칙 I 확인 단계. DEC-047 ②가 "M3 에서 서버 필드 결정"으로 미룸 | `POST /batches/{id}/execute {"confirm_text":"실제 실행 1건"}` 가 A/B 필드 없이 202(`test_c1~c3` 의 `do_execute`) | **Medium** (UI 에서는 반영됨 — 규칙 I 미반영이 아니므로 Critical 아님; **실제 모드 활성 전 결정 필수**) | Open — 사용자 결정 | 실제 모드일 때 `ab_confirmed: true` 필수 필드를 서버가 검사하고 감사에 기록 |
| **DEF-9B-003** | 쓰기·읽기 전송이 urllib 기본 리다이렉트 처리를 쓴다: 첫 URL 만 https 검사하고, 3xx 로 다른 호스트/`http://` 가 오면 `Authorization: Bearer` 가 따라간다(PUT 은 urllib 가 리다이렉트를 따르지 않음 — GET 경로 `default_http_get` 만 해당). 구글 응답 위조/중간자 전제라 가능성 낮음 (TW-35, TW-44) | 신규 `test_d3` | **Low** | Open | 리다이렉트 비활성 opener 사용(`HTTPRedirectHandler.redirect_request` 가 None 반환) |
| **DEF-9B-004** | 토큰 폴더(`/var/lib/ytweb/secrets`)가 `mkdir` 기본 권한 0755 로 만들어진다(파일은 0600). 같은 볼륨을 마운트한 다른 사용자가 파일 이름·존재 여부를 알 수 있음. 컨테이너에서는 명명 볼륨+비루트 단일 사용자라 실제 노출은 작음 (TW-38) | 신규 `test_a6`(`-s` 로 `secrets dir mode 0o755`) | **Low** | Open | `mkdir(mode=0o700)` + `chmod 0700` |
| **DEF-9B-005** | 구글 토큰 교환 오류의 `error` 문자열이 `OAuthError.code`(`"grant_"+값`)로 감사 기록 detail 에 **길이 제한 없이** 저장됨(3,344자 재현). 구글이 보내는 값이라 외부 공격자 제어는 어렵지만 비정상 응답/중간자 시 감사 비대화·비밀 유사 문자열 저장 가능 (TW-42) | 신규 `test_a8` | **Low** | Open | 허용 오류 코드 목록으로 정규화하거나 64자로 자른다 |
| **DEF-9B-006** | 기존 보안 시험 4건이 M2·M3 변경을 반영하지 못해 **스위트가 빨간색**(R4-1). 제품 결함 아님(오탐/미갱신)이며 1~3은 M2·M3 이 의도한 구조 | R4-1 표 | **Low** (프로세스) | Open — 시험 소유자 | 근거를 남기고 allowlist 갱신: 외부 통신 3개 모듈 목록, 가짜 값 3곳·`web/.env.example`, `e2e.ps1`(기본 loopback) — 고칠 때 "기대값을 맞춰 통과시킨 이유"를 결과서에 쓴다. 이 회차에서는 **고치지 않았다** |
| **DEF-9B-007** | 위협 모델 W9 의 낡은/부정확 서술 3곳(TW-39 "공식 절차 없음", TW-40 "DEF-VMF-001 수정 전…", TW-37 "모든 시도 감사"의 의미) — 문서-구현 불일치 | R4-3 | **Low** | Open — 규칙 F 갱신 요청(부록 R-G) | 문구 정정 |
| **DEF-9B-008** | 쓰기 토큰 수명주기: ① 구글에 revoke 요청 안 함(연결 해제는 로컬 삭제만), ② 화면의 [연결 해제] 직후 "구글 계정 → 타사 앱 접근에서 이 앱 제거" 안내 없음(EVT-001 은 CLI 에서 요구, 웹은 `WEB_RUNBOOK` 에만), ③ 토큰 평문(0600)·암호화 없음. `youtube.force-ssl` 토큰이 새면 허용 목록과 무관하게 **채널의 모든 영상 수정·삭제** 가능 (TW-38 위험도 "상", SEC-015, EVT-001, RISK-007) | 코드: `routers/google.py:google_disconnect`(revoke 없음), 모델 W9-1 | **Medium** (호스트/볼륨 접근 선행 필요; 그러나 영향이 채널 전체라 사용자 결정 전 실제 쓰기 연결 금지) | Open — **사용자 수용 결정 필요(Q, 대기)** | 연결 해제 시 `https://oauth2.googleapis.com/revoke` 최선 호출(실패해도 로컬 삭제) + 화면 안내 문구; 평문 저장을 수용하려면 DEC 기록. 수용 결정 없이 실제 쓰기 연결하지 않는다 |
| **DEF-9B-009** | api·worker 에 도메인 제한 없는 egress(TW-44). api 는 웹 입력을 받는 컴포넌트이면서 쓰기 토큰·DB 비밀번호·클라이언트 비밀을 모두 보유 → api 침해 시 외부 반출 가능. DEF-9-011 과 같은 계열 | `docker compose config` 렌더링(R4-3) | **Medium** | Open — 사용자 결정(수용 또는 egress 프록시/방화벽) | 구글 도메인만 허용하는 egress 프록시 또는 쓰기 호출을 worker 로만 한정(api 는 읽기 연결만) 검토 |
- **닫힌 결함(이번 회차 확인)**: DEF-9-007(Critical)·DEF-9-008(High) — R4-4; DEF-9-001 — 422 확인; DEF-9-006 — `git check-ignore` 로 `client_secret*.json`·`web/secrets/`·`web/.env` 무시 확인; DEF-9-018 — `traceability.md` v4 에 POL-005~016·SEC-021~030 등록 확인(21행 검색); DEF-9-017 — `test_sec_08` 통과(이미지 실측은 미수행).
- **변동 없는 열린 결함(코드/설정 diff 없음, 재평가 안 함)**: DEF-9-003·004·005·009·010·011·012·013·014·015·016. 참고: DEF-9-016(nginx 오류 로그 쿼리 문자열)은 M2 콜백(`?code=…&state=…`)으로 영향이 커졌으나 PKCE+1회용이라 **Low 유지**, `compose` 설정은 오류 로그 level=error 만(확인).
- **열린 결함 합계: Critical 0 · High 1(DEF-9-002) · Medium 8(9-010·011·013·014, 9B-001·002·008·009) · Low 12(9-003·004·005·009·012·015·016, 9B-003·004·005·006·007)**.

## R7. 테스트 환경 정리(Teardown) — 규칙 K
- 만든 것: `.harness-tmp/s2/`(로그·XML·`pipaudit` 임시 설치·`cfg`(compose 렌더링용 가짜 비밀 4개)·`mut`(변이 사본)·복사한 `config`·`src`·`web`). **컨테이너·볼륨·네트워크·이미지·PostgreSQL DB 는 만들지 않았다**(`harness-tmp-s2` 자원 0개). 신규 시험 파일 `web/tests_security/test_sec_09_m23_attack.py` 는 의도된 산출물로 남긴다. 임시 시험 파일 `web/backend/tests/_tmp_s2_big.py` 는 실행 직후 삭제했다.
- 정리: 이 절 마지막 줄의 `git status` 와 정리 명령 결과 참고(아래 R7-1).
- 소유 표기: 작업 트리의 `web/tests_integration/test_it_07_rev2.py`, `web/tests_integration/tools/rev2_screens.mjs` 는 **다른 에이전트(7단계 재검증) 소유** — 건드리지 않았다.

## R8. 리스크 및 잔존 이슈 / 미수행
| 미수행 항목 | 사유 | 잔여 위험 |
|---|---|---|
| 컨테이너 이미지 Trivy 재스캔 | 이 환경에 Trivy 바이너리 없음. Dockerfile·베이스 이미지·`requirements*.txt` 는 SBOM 시점(커밋 9cd6fdc) 이후 **diff 없음**(`git diff --stat`: compose 2개만 변경)이라 기존 부록 C 결과가 유효하나 이후 공개된 새 CVE 는 미반영 | DEF-9-010 계열(Medium) 최신성 미확인 |
| 실스택 `test_sec_04`, 번들 4건 | 컨테이너 스택 미기동(시간·범위) — 번들은 `dist/` 파일 검색으로 대체 | nginx 경유 경로에서 `/api/v1/google/callback` 의 헤더·한도 동작은 실측 안 함(코드·TestClient 로만 확인) |
| 실제 구글 OAuth/실제 제목 변경 | 금지(규칙 E, 사용자 승인 전) | `[미검증-실제환경]`: 토큰 갱신·실제 모호 응답·데스크톱 클라이언트 복귀 주소 수락 여부·쿼터 실제 소모 |
| 변이 점검기 전체 | 1시간 소요 — 신규 시험 7곳만 수행 | 기존 시험의 변이 실효성은 1판 값(119곳) 유지 |
| 브라우저 화면 캡처 | 스택 미기동 | 문구의 실제 렌더링 위치/가독성은 6단계 FE 결과서·10단계에서 확인 |

## R9. 결론 및 판정
- [ ] PASS  [ ] CONDITIONAL PASS  [x] **FAIL**
- 사유: **High 1건(DEF-9-002) Open**. Critical/High 가 있으면 PASS 불가. 기술 취약점(인증 우회·인젝션·비밀 노출·허용 목록 우회·이중 반영) 신규 Critical/High 는 **없음**(위 시험으로 확인). 규칙 I·J(면책·AI 고지·A/B 확인 UI)는 반영 확인.
- 다음 단계: DEF-9-002 수정 → 9단계 재검증(xfail 2건 XPASS 전환) 후 PASS/CONDITIONAL 재판정. 데모 모드 범위의 10단계(구동 검증)는 진행 가능하나 **실제 모드 활성·12단계 배포 승인 요청은 금지**. Medium 은 수정 또는 DEC 로 Deferred(수용) — 특히 DEF-9B-002·008·009 는 실제 연결 전 사용자 결정 필요.
- 위협 모델 TW-01~36 재확인(1판 부록 A)은 코드 diff 가 없는 영역이라 변경 없음.

## R10. 내부 검증 (3회)
- 1차(체크리스트): 에이전트 정의 최소 점검 항목 전부 — 인증/인가·권한 경계(G 그룹, 콜백 무세션 예외), 인젝션·입력 검증(허용 목록 변형, 쿼리 인코딩), 시크릿(카나리 전수·`git check-ignore`·키 패턴 grep 모두 가짜 값), 의존성 CVE(`pip-audit` 3개 요구 파일 0건 · `npm audit` 0건), **의존성 환각**(M2·M3 가 새 패키지를 도입하지 않음 — `requirements*.txt`·`package*.json` diff 없음, 표준 라이브러리만 사용 → 신규 패키지 0, 해당 없음 확인), 암호화(토큰 평문 0600 — DEF-9B-008), 에러 노출, 설계-구현 불일치(W9 서술 3곳), 개인정보(아래), 라이선스·SBOM(변경 없음 → 기존 `sbom-web-m1*` 유효, 재생성 불필요 사유 명시), 외부 API 약관(호출 코드는 읽기 최대 40쪽·쓰기 허용 영상만 — 약관 확인 문서는 3단계), 규칙 I·J(R4-4), CI/자동화(`automation/` 변경 없음 → DEF-9-005 유지). 이 과정에서 **내 시험 오류 3건**을 발견·수정(R4-2).
- 2차(공격자 관점, 카테고리 연쇄): ① 교차 사이트 페이지 → 콜백 GET 스팸 → 감사 오염 + 거짓 안내(DEF-9B-001) 발견; ② 비브라우저 프로세스(같은 PC) → 화면 응답 없이 `실제 실행 N건` 직접 호출 → A/B 확인 없음(DEF-9B-002); ③ api 침해 → egress + 토큰/DB 비밀 반출(DEF-9B-009); ④ 인증 우회 + 롤백 덮어쓰기: 세션 탈취 시 롤백으로 사람 작업 소실(DEF-9-002 와 결합, 별개 신규 경로 없음); ⑤ 모드 전환 중 확정 배치 / 롤백 불일치 / 모호 응답 재시도 모두 차단 확인. 변이 7곳으로 시험 실효성 확인.
- 3차(결함 0건 확인 회차): 위 결함 표 외 **신규 결함 0건** 재확인 — 신규 61건 + 기존 258건 재실행(R4-1·R5 수치)이 동일, 소스 diff 없음. 단 Critical/High 0건 조건은 DEF-9-002 때문에 **충족 못 함** → FAIL 유지.
- 검증 로그: `docs/harness/verify-logs/verify-log_security-web-m1-rev2.md`, 원문 `docs/harness/verify-logs/web-security-rev2-raw/`.

## R-F. 개인정보·규제 (법률 자문 아님)
- 수집·저장: 승인자 이름(자유 입력)·영상 메타데이터·구글 OAuth 토큰(개인 구글 계정 접근 자격). 이메일 등 계정 식별자 저장 코드는 없음(확인). 로그는 JSON 에 method/path/status/ms/request_id 만(쿼리·본문·헤더 없음, `logsetup.py`·nginx `$uri`), 토큰·세션·PIN 키는 마스킹.
- 토큰 보관: **평문 0600**, 암호화·구글 revoke 없음 → 위 DEF-9B-008. **사용자 수용 결정 필요(TW-38)**. 보관기간·파기(POL-012/016)는 DEF-9-013 로 미구현 — 개인정보 보호법상 보관·파기 기준 충족 여부는 판단하지 않으며 **확인 필요**(전문가).
- 제3자 제공/위탁: 구글(유튜브 API)로 영상 ID·제목 변경 본문 전송, 읽기 토큰·쓰기 토큰 전송. AI 서비스는 미연결(M3 후속). 이용자 고지·동의 흐름 문서화는 `WEB_LEGAL_NOTICE.md` 대상이며 **확인 필요**.
- 개인정보 영향평가(PIA)·ISMS-P 해당 여부: 판단하지 않음 — **확인 필요**(1인 로컬 도구, 외부 이용자 없음 전제).
- 규제 민감 도메인(건강·금융, 규칙 I): 면책·AI 고지·A/B 확인 UI 반영 확인(R4-4). 문구의 법적 충분성은 전문가 확인 필요.
- 보안 사고 대응(탐지→격리→통지→복구)이 11단계 Runbook 에 담길 근거: `WEB_RUNBOOK.md` 15장·338행(구글 보안 활동 확인)·200행(계정·키 회수)이 있다. 토큰 유출 시 **구글 계정에서 앱 접근 제거를 첫 단계로** 명시할 것(DEF-9B-008 권고와 연결). 접근 권한 관리(최소권한)·계정 회수 절차와 로그 보관·감사 추적은 1판 부록 + 이번 감사 행 확인(연결·실행·적용·롤백·해제 기록)으로 설계와 일치; 로그 보관기간은 DEF-9-013 미결.

## R-G. 규칙 F — 위협 모델 갱신 요청 (`docs/yt/threat_model.md` W9)
1. TW-37 완화 칸: "모든 시도 감사 기록"에 **세션 없는 교차 사이트 요청 포함** 및 DEF-9B-001 잔여 위험 추가. 2. TW-39 잔여: "공식 절차 없음(Q-11-10)" 삭제 → `compose.online.yaml`+`web/.env.example` 경로 명시. 3. TW-40: DEF-VMF-001 해결됨으로 정정, DEF-9B-002(A/B 서버 필드) 유지. 4. TW-38: 비밀 폴더 0755, 연결 해제 시 revoke 없음·화면 회수 안내 없음 추가, SEC-015 "실행 순간에만 로드"와 구현 차이. 5. TW-42: 감사 detail 오류 코드 길이 무제한(DEF-9B-005). 6. TW-35/44: 리다이렉트 시 Authorization 전달(DEF-9B-003) 추가. 7. 신규 TW 후보: **TW-45 롤백 덮어쓰기(DEF-9-002) 실제 모드 영향**. 8. 모델 W9 의 "독립 검증·9단계 재검증은 아직" 문구를 이 판 기준으로 갱신. `traceability.md`: S-W08(비고 칸에 "09단계 확인 2판"), SEC-008·SEC-015·EVT-001·POL-002·006·008·013·010 행의 비고에 **"09단계 확인(2판, 2026-10-11)"** 갱신을 요청한다(이 에이전트는 공유 파일을 수정하지 않는다).

## R-Q. 사용자(오케스트레이터) 결정 요청 (규칙 A)
1. DEF-9-002: 롤백 방식 — (a) 현재 제목·보존 필드가 백업과 다르면 거부(권장) (b) 제목만 되돌리는 본문(설명 보존). 2. DEF-9B-002: 실제 모드 A/B 서버 확인 필드 추가 여부(권장: 추가). 3. DEF-9B-008: 쓰기 토큰 평문 보관 수용 여부와 revoke 호출 추가 여부. 4. DEF-9B-009: egress 도메인 제한 수용 여부. 5. 시험 자산 갱신(DEF-9B-006) 담당 지정.

### R7-1. 정리 결과 (git status 원문, 정리 후)
```
 M docs/harness/security-web-m1-test.md
?? docs/harness/verify-logs/verify-log_security-web-m1-rev2.md
?? docs/harness/verify-logs/web-security-rev2-raw/
?? web/tests_integration/test_it_07_rev2.py        (타 에이전트 소유)
?? web/tests_integration/tools/rev2_screens.mjs    (타 에이전트 소유)
?? web/tests_security/test_sec_09_m23_attack.py
```
`.harness-tmp/s2/` 에는 원문 로그 3개(run1_full.log·run2_full.log·run3.xml; 같은 내용을 `verify-logs/web-security-rev2-raw/` 에 복사)만 남기고 `cfg`·`pipaudit`·`mut`·복사본 폴더는 삭제했다. `docker ps -a/network/volume/images | grep s2` 결과 0건. `.harness-tmp/` 전체 삭제·janitor `--clean`·`pkill` 은 사용하지 않았다.

---
## R-조치. 개정 2판 후 오케스트레이터 조치 (2026-10-11)
첫 실행 결과(위 R0~R-Q)는 그대로 둔다. 조치 후 재실행은 아래에 따로 적는다.
- **조치**: DEF-9-002(High) — 실제 모드 롤백은 반영 뒤 유튜브에서 바뀐 항목이 있으면 409 `live_changed_since_apply` 로 거부(DEC-049, 사용자 확인 대기). DEF-9B-001 — 모르는·만료 state 로는 감사 기록을 쌓지 않음. DEF-9B-003 — 리다이렉트 비추종 opener 설치. DEF-9B-006 — 시험 자산 갱신(구글 통신 모듈 3개 예외, `.env.example` 템플릿 허용, 가짜 값 시험 폴더 허용, e2e.ps1 의 로컬 점검 허용).
- **시험 변경 사유**: 위 재현용 시험 2건(`test_a9_…_repro`, `test_e2_…_repro`)은 결함을 "재현"하는 형태로 통과했었다. 조치 후 같은 시나리오의 기대값을 "결함 없음"으로 뒤집고 이름을 바꿨다(조치 확인). 원래 통과(=결함 재현) 사실은 본문 R 절에 남아 있다.
- **재실행**: 보안 시험(`web/tests_security`, 컨테이너 필요한 `test_sec_04` 제외)과 백엔드 시험 통과, 아래 STATE 에 수치 기록.
- **여전히 열림(사용자 결정 필요, R-Q)**: DEF-9B-002(A/B 서버 필드), DEF-9B-008(쓰기 토큰 평문·revoke), DEF-9B-009(egress 도메인 제한), DEF-9B-004/005/007 Low. 이 때문에 9단계 판정은 사용자 결정 전까지 **CONDITIONAL** 로 본다(데모 모드에서는 Critical/High 없음).
