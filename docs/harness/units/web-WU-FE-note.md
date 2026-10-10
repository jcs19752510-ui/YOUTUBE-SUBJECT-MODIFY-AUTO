# 단위 노트 — W-FE (React 프런트엔드, 웹 M1 데모)

| 항목 | 내용 |
|---|---|
| 작업 단위 | W-FE (WEB_DESIGN §7). 소유 범위 `web/frontend/` 만 수정. 백엔드·인프라와 병렬 웨이브(W-BE-A, W-BE-B, W-INF 동시 진행) |
| 속도 트랙 | 전달받지 못함 → 기본 L3 로 표기 |
| 상태 | 구현 완료, 게이트 1(린트·타입·포맷)·게이트 2(자체 리뷰) 통과. 결과서·검증 로그는 06단계 담당 |
| 한 줄 요약 | 8개 화면 + 모든 상태 화면 + 모의 서버(`npm run dev:mock`) + 테스트 95건 |

## 1. 실행 방법
```
cd web/frontend
npm ci                 # package-lock.json 으로 재현 (Node >= 22.12)
npm run dev:mock       # 모의 API(127.0.0.1:8081) + Vite(127.0.0.1:5173). 브라우저로 http://127.0.0.1:5173
npm run dev            # 실제 백엔드 사용 시. /api 는 VITE_API_PROXY(기본 http://127.0.0.1:8081)로 프록시
npm run check          # typecheck + lint + format:check + test + build 를 한 번에
npm run lint | typecheck | format:check | test | build
```
- 모의 서버 옵션(환경변수): `MOCK_PORT`, `MOCK_PIN`(PIN 화면 확인), `MOCK_EMPTY=1`(영상 0개 시작), `MOCK_STATIC=dist`(빌드 결과 서빙), 개발 전용 `POST /__mock/expire`(세션 만료 시험).
- 라우팅은 **HashRouter**(`#/videos`)다. nginx 에 SPA 대체 응답(try_files) 설정이 없어도 새로고침이 동작한다. 인프라 담당이 try_files 를 넣으면 BrowserRouter 로 바꿀 수 있다(`main.tsx` 한 줄).

## 2. 결과 숫자 (이번 세션 마지막 실행)
| 항목 | 결과 |
|---|---|
| `tsc -b` (strict, noUncheckedIndexedAccess) | 오류 0 |
| ESLint (react-hooks, jsx-a11y, no-explicit-any, dangerouslySetInnerHTML·innerHTML·style 속성·localStorage 금지 규칙) | 오류 0, 경고 0 |
| Prettier `--check` | 통과 |
| Vitest | 9 파일, **95 테스트 통과** (TC-WF-001 ~ 095, 중복·결번 없음 확인) |
| `npm run build` | 성공(JS 389 kB / gzip 118 kB, CSS 16 kB). `dist/index.html` 에 인라인 스크립트·스타일 없음 |
| `npm audit` (개발 의존성 포함) | 취약점 0 |
| `npm ci` 재현 | 빈 디렉터리에서 package.json+lock 만으로 성공 |

## 3. 파일 (모두 `web/frontend/` 아래)
- 설정: `package.json`, `package-lock.json`, `vite.config.ts`, `tsconfig*.json`, `eslint.config.js`, `.prettierrc.json`, `.prettierignore`, `.gitignore`(node_modules, dist), `index.html`, `public/favicon.svg`
- `src/api/`: `types.ts`(계약 타입), `client.ts`(세션·CSRF·멱등키·오류 변환·재발급·연결 상태), `endpoints.ts`(엔드포인트별 함수), `context.tsx`
- `src/app/`: `App.tsx`(라우트), `AuthGate.tsx`(시작/PIN/끊김/로그아웃/만료 오버레이), `Layout.tsx`(사이드바·상단 배지·연결 상태), `PinForm.tsx`, `providers.tsx`
- `src/components/`: Button, Badge, ValidationBadge, Card, Callout, Field, Table(TableWrap·SortHeader), Modal(포커스 트랩·Esc·inert·포커스 복귀), Toast, Tabs(방향키), ConfirmPhrase, Pagination, Skeleton, EmptyState, Progress, TitleDiff, ErrorPanel, QueryView, PageHead
- `src/pages/`: Home, Videos, VideoDetail(+SuggestionCard), Batches, BatchDetail, History, Reports, Settings(+PIN·세션·감사 탭), JobPanel
- `src/styles/`: `tokens.css`, `base.css`, `components.css`, `layout.css`, `index.css`
- `src/i18n/ko.ts`(모든 화면 문구), `src/lib/`(format, diff, labels), `src/hooks/`(선택 유지, 멱등키, 승인자 이름)
- `dev/mock-server.mjs`, `dev/run-dev-mock.mjs`
- 테스트: `src/**/*.test.ts(x)`, `src/test/{utils,fixtures,setup,source-rules.test}`

## 4. 화면별 구현과 API 사용
| 화면(경로) | 구현 요약 | 사용 API |
|---|---|---|
| 홈 `/` | 오늘 할 일(제안 검토·배치 만들기·대기 확인, 영상 0개면 "데모 영상 불러오기"), 오늘 반영 건수 막대, 남은 사용량(80% 이상 경고), 대기열·다음 실행일, 구글/데모/라이브 꺼짐 상태, 영상 현황(링크로 필터 이동), 진행 중 작업이 있으면 2초 폴링 | GET dashboard, POST videos/sync, GET jobs/{id} |
| 영상 목록 `/videos` | 검색·상태/제외 필터·정렬(제목·길이·조회수·최근 변경, aria-sort)·페이지 크기·페이지네이션, URL 쿼리에 상태 보존(새로고침 유지), 체크박스(전체 선택 indeterminate, 제외 영상 비활성+사유), 선택은 페이지 이동 후에도 유지, 하단 고정 선택 바, "선택 영상 AI 제안 생성" → 작업 진행 모달 | GET videos, POST suggestions/generate, GET jobs/{id} |
| 영상 상세 `/videos/:id` | 현재 제목·메타·설명, 제외 안내, 변경 한도 상태(사유·가능 시각), 제안 카드(통과/경고/차단 뱃지는 기호+글자, 사유 목록, 엄격 모드, 일치율, 글자 수, 변경 전/후 diff), 제목 수정·승인(경고는 사유 확인 체크, 차단은 비활성+사유)·반려(확인 대화상자), 변경 이력 | GET videos/{id}, POST videos/{id}/suggestions, PATCH/POST suggestions/{id}(/approve,/reject) |
| 배치 `/batches` | 승인 항목 선택(최대 50건 안내·차단) → 초안 생성(멱등키) → 초안 화면으로 이동. 지난 배치 목록, 실행 중이면 안내 | GET suggestions?status=approved, POST batches, GET batches |
| 배치 상세 `/batches/:id` | 사전 점검 표(항목 수·예상 사용량·하루 상한·남은 한도·날짜별 일정·경고·제외 항목), 포함 항목 표, 확인 문구 `실행 {n}건` 직접 입력(불일치 시 실행 버튼 비활성), 실행(멱등키, 실패 후 재시도는 같은 키), 진행률(`<progress>`, 서버 상태 2초 폴링, 새로고침 복구), 중지(확인 대화상자), 완료 안내 | GET batches/{id}, POST batches/{id}/execute, POST batches/{id}/cancel |
| 이력·롤백 `/history` | 변경 이력 표(영상·구분·전후 제목·결과·승인자), 영상 ID/결과 필터, 롤백 대화상자(영상 ID 직접 입력 일치+승인자 입력 전엔 실행 비활성, 멱등키), 되돌릴 수 없는 항목은 이유 표시 | GET changes, POST changes/{id}/rollback |
| 성과 리포트 `/reports` | 영상별 카드(데이터 부족 뱃지+사유+수집 예정일 / 비교 표 / 변경 기록 없음), 서버 notes 를 맨 위 경고 박스에 그대로 노출(없으면 원인 단정 금지 기본 문구), CSV 내보내기(blob 다운로드, 오류 표시) | GET reports/changes, GET reports/export.csv |
| 설정 `/settings` | 탭: 안전 설정(하루 상한 1~20, 영상당 제안 1~5, 말투 목록 최대 5개·각 20자 — 범위 검증), **읽기 전용** 라이브/허용 영상 목록(`read_only`) + "이 화면에서는 켤 수 없습니다", PIN 설정·변경·해제(숫자 4~12자리·재입력 일치, PIN 이 있으면 현재 PIN 필수, 해제는 현재 PIN 확인 대화상자; 본문 `{pin:{action,new_pin,current_pin}}`), 세션·연결(서버·구글·모드·로그아웃), 감사 로그(읽기 전용, 무결성 결과를 글자로) | GET/PATCH settings, GET google/status, GET audit, DELETE auth/session |
| 공통 | 상단 항상 "데모 모드 — 유튜브에 아무것도 전송되지 않습니다" 배지, 연결 상태, 로그아웃, 본문 건너뛰기 링크, 화면 이동 시 제목으로 포커스, 404 화면 | GET auth/me, POST auth/session |

### 상태 화면 매핑 (F-07)
로딩=Skeleton(`role=status`) / 빈 상태=EmptyState(다음 행동 링크·버튼) / 오류=ErrorPanel(제목·상세·"다음에 할 일"·오류 코드·다시 시도) / 한도 초과=ErrorPanel 경고 톤(429·한도 계열 코드) / 세션 만료=연결 중 PIN 재입력 모달(화면 유지), 로그인 필요 시 조용히 재발급 1회 / 서버 연결 끊김=시작 시 전체 화면, 사용 중에는 배너+상단 상태 / 진행 중 새로고침 복구=배치는 `GET /batches/{id}` 폴링, 초안 점검표는 history.state(HashRouter)에서 복원, 서버가 `precheck` 를 주면 그것을 우선.

## 5. API 클라이언트 동작 (`src/api/client.ts`)
1. 시작 시 `GET auth/me` → 미인증이면 `POST auth/session`(PIN 필요하면 PIN 화면, `{pin}` 전송). `csrf_token` 은 클래스 인스턴스 메모리에만 보관(저장소 규칙 테스트·ESLint 로 localStorage/sessionStorage 금지).
2. 상태 변경에 `X-CSRF-Token` 자동 부착, `risky`(배치 생성·실행, 롤백)는 `Idempotency-Key` 부착. 같은 요청 재시도는 `IdempotencyKeys`(요청 지문 기준)로 같은 키 재사용, 내용이 바뀌면 새 키.
3. problem+json → `ApiError{status,code,title,detail,hint}`; JSON 아닌 오류도 안전한 기본 문구.
4. 401(또는 CSRF 403)이면 재발급 1회 후 같은 멱등키로 재시도. PIN 이 필요하면 `session_expired` 오류 + 만료 모달.
5. 네트워크 오류는 `network_error` 로 구분하고 연결 상태 `offline`→성공 시 `online` 복구. 로그아웃은 서버에 성공했을 때만 "로그아웃됨"으로 바꾼다.

## 6. 디자인 토큰 요약 (`src/styles/tokens.css`)
- 색: 표면(bg/surface/surface-2/border), 글자(text 16:1, muted 7:1 이상), 의미색 4종(success/warning/danger/info)은 배경+글자+테두리 3벌, primary `#1d4ed8`(흰 글자 6.7:1), 입력 경계 `#5b6676`(비텍스트 3:1 이상), 데모 배지 전용색. 라이트 기본 + `prefers-color-scheme: dark` 대응(선택 기능, 화면 확인함).
- 타이포: 시스템 한글 폰트 스택(원격 폰트·CDN 없음), 최소 글자 16px(1rem, 정적 테스트로 CSS 에서 16px 미만 금지 확인), 행간 1.6, `word-break: keep-all`.
- 간격 4px 단위 7단계, 반지름 3단계, 그림자 2단계, 조작 영역 최소 44px(`--hit`), 포커스 링 3px(`:focus-visible`), `prefers-reduced-motion` 존중.
- 상태 표시는 색+기호+글자 병기(✓ 통과 / ▲ 경고 / ✕ 차단), diff 는 취소선·밑줄+스크린리더용 "삭제됨/추가됨" 문구.

## 7. 요구사항 ↔ 구현 ↔ TC
| 요구 | 구현 | TC |
|---|---|---|
| F-01 React+TS strict, Vite, ESLint·Prettier·타입 검사 | 설정 파일, `npm run check` | 게이트(린트·타입·포맷 통과), TC-WF-081(소스 규칙) |
| F-02 서버 상태는 TanStack Query | 모든 화면 useQuery/useMutation | 화면 테스트 전반 |
| F-02 타입 생성 | **미수행**: 오픈API 생성 대신 §3 계약을 손으로 옮김(사유: 서버 스키마가 아직 완성 전, 지시 사항 `types.ts` 직접 작성) | - |
| F-03 서버 측 필터·정렬·페이지네이션, 선택 유지 | VideosPage, SelectionProvider | TC-027, 028, 029, 030 |
| F-03 가상 스크롤 | **미적용**: 설계서 §6 이 "페이지네이션 허용"으로 완화, 25/50/100/200개 페이지 | - |
| F-04 CDN·원격 폰트 금지 | 시스템 폰트, 외부 주소 없음 | TC-083 |
| F-05 dangerouslySetInnerHTML 금지, 외부 문자열 텍스트 | ESLint 규칙 + 정적 테스트, TitleDiff 텍스트 렌더링 | TC-018, 081 |
| F-06 CSRF·멱등키 자동, 중복 클릭 방지, 확인 단계 | client.ts, Button `busy`, ConfirmPhrase, 반려/중지/롤백/PIN 해제 대화상자 | TC-001, 005~008, 012, 044, 046, 050, 051, 055, 060 |
| F-07 상태 화면 전부 | §4 매핑 | TC-031~033, 041~043, 048, 052~054, 059, 063, 065, 072~073, 076~079 |
| F-08 한국어, 문구 한곳, dry-run→미리보기 | `i18n/ko.ts` | TC-084, 049 |
| F-09 접근성 WCAG 2.2 AA 목표 | 라벨·aria-live·포커스 관리·키보드·토큰 대비·색 비의존 | TC-019~021, 024, 086~093(axe) |
| F-10 PC 우선, 최소 1024px, Chrome/Edge | 1024px·1280px 에서 가로 넘침 없음 확인 | 스크린샷 확인 |
| F-11 디자인 시스템 먼저, 다크/라이트 | tokens.css, 다크 선택 지원 | 스크린샷 확인 |
| S-W02/S-W03 CSRF, 상태 변경 비-GET | client.ts | TC-005 |
| S-W04 CSP 호환 | 인라인 스크립트·스타일·style 속성 없음, `dist/index.html` 확인 | TC-081 |
| S-W05 XSS | 위 F-05 | TC-018, 081 |
| 설정 읽기 전용(라이브·허용 영상) | SettingsPage | TC-067, 069, 070, 094, 095 |
| 원인 단정 금지 문구 노출 | ReportsPage | TC-064, 065 |
| 승인 규칙(차단 불가, 경고 사유 확인) | SuggestionCard | TC-036, 037, 038 |

## 8. 스크린샷으로 확인한 사항 (Chromium 1194, 임시 스크립트는 `.harness-tmp/`, 끝나고 삭제; 모의 서버와 실제 백엔드 양쪽에서 확인)
홈, 영상 목록(200개, 제외 배지), 영상 상세(통과 카드), 승인 대화상자, 배치 선택·사전 점검·확인 문구·진행·완료, 이력, 롤백 대화상자, 리포트(비교 가능/데이터 부족), 설정(읽기 전용 구역), PIN 화면, 세션 만료 오버레이, 빈 홈(데모 영상 불러오기), 1024px 폭, 다크 모드를 눈으로 확인하고 고친 점:
- 토스트가 겹쳐 쌓임 → 세로 간격 적용
- 이력 표의 "롤백" 버튼이 두 줄로 깨짐 → 버튼 `nowrap`
- 리포트의 "비교 가능" 배지가 전체 너비로 늘어남 → 정렬 수정
- 세션 만료 오버레이 뒤 배너가 "서버 연결 끊김"으로 잘못 표시 → 상태별 라벨("세션 확인 필요")로 분리
- 표 머리글 세로 정렬 어긋남 → 가운데 정렬
- 1024px·1280px 모두 가로 스크롤 없음(scrollWidth==innerWidth), 콘솔 오류 없음(의도한 401 응답 제외).
- 제한: 스크린샷으로는 색 대비 수치를 측정하지 못했다(토큰 값 설계로 AA 를 맞췄고 axe 의 색 대비 규칙은 jsdom 에서 계산 불가라 꺼 둠 → 아래 "미수행").

## 9. 알려진 제한·미수행
- **axe 색 대비 규칙은 jsdom 에서 계산할 수 없어 자동 시험에서 제외**했다. 대비는 토큰 설계값으로 보증했고 실제 브라우저 자동 측정은 하지 않았다(브라우저 자동화 도구는 저장소에 넣지 않는다는 DEC-034 때문). 06단계에서 수동 점검 권장.
- 스크린리더(NVDA 등)·실제 Edge 수동 시험 미수행(환경 없음).
- 가상 스크롤, OpenAPI 타입 생성 미적용(위 표).
- 실제 백엔드 연동은 SQLite+워커 구성에서 수동 확인함(10장). PostgreSQL·nginx·compose 경유 구성과 자동화된 통합 테스트는 미수행.
- 폴링 중 탭이 백그라운드이면 TanStack Query 기본 설정대로 멈춘다(의도).
- ESLint 는 **9.39.5**(EOL 표시 경고가 npm 에 뜸): eslint 10 은 `eslint-plugin-jsx-a11y` 6.10.2 의 peer 범위(≤9) 밖이라 접근성 린트를 유지하려고 9 로 고정. jsx-a11y 가 10 을 지원하면 올릴 것.
- TypeScript **5.9.3**(조사축 D 권고, typescript-eslint 가 <6.1 요구). vitest-axe 0.1.0 은 2025-01 이후 갱신이 없고 Vitest 5 호환 미검증이라 쓰지 않고 `axe-core` 를 직접 호출한다(`src/test/utils.tsx`). axe-core 는 MPL-2.0, 개발 전용.
- 승인자 이름은 탭 메모리에만 기억(저장소 사용 금지 규칙). 새로고침하면 다시 입력.
- 썸네일 이미지는 표시하지 않음(coordinator 지시: CDN 금지, 데모 영상에 썸네일 없음).

## 10. 서버 계약 확인 (W-BE-A 구현 기준으로 맞춤 + 실제 백엔드로 확인)
**실제 백엔드 연동 확인(이 세션)**: W-BE-A/B 코드를 SQLite(`YTWEB_AUTO_CREATE=1`) + 워커로 띄우고 Vite 프록시(`VITE_API_PROXY`)로 연결해 Chromium 으로 확인했다. 데모 영상 불러오기(작업) → 목록 → 선택·AI 제안 생성(작업 진행) → 상세(경고/통과 카드) → 승인 → 배치 초안·사전 점검 → 확인 문구·실행 → 완료 → 이력 → 롤백 → 리포트(데이터 부족) → 설정 → 감사 로그, PIN 설정 → 로그아웃 → PIN 화면(틀린 PIN 안내) → 로그인 → 현재 PIN 틀림(안내)/맞음으로 해제까지 **콘솔 오류·예상 밖 4xx 없이** 동작했다(의도한 401 은 틀린 PIN 시험뿐). 시험 후 서버·임시 DB 정리함. 맞춘 내용: 설정 응답은 `{daily_apply_cap,suggestions_per_video,tone[],pin_enabled,mode,read_only{enable_live,live_allowlist[],note}}`, PIN 변경 본문 `{pin:{action:"set"|"clear",new_pin?,current_pin?}}`, 배치 상태 `done` 을 완료로 표시, 주제 코드(`life` 등)는 한국어로 매핑(모르는 코드는 원문).
아직 서버 문서에 없어 프런트가 가정한 것(서버 담당 확인 요청, 규칙 A):
1. `GET /batches/{id}` 응답에 `precheck` 포함 요청(화면은 있으면 사용, 없으면 history.state·항목 수 기준으로 대체). 실제 서버로 새로고침 복구를 끝까지 확인하지는 않았다.
2. 일부 날짜가 미래인 항목이 남은 배치의 `status`(계속 `running` 이면 화면이 2초 폴링을 계속함).
3. `GET /videos` 의 `sort` 허용 값 `title|views|duration_sec|last_change_at`, `status`·`excluded` 필터 값(실제 서버에서 목록·필터 기본 동작만 확인, 모든 정렬 키는 미확인).
4. 승인 만료 시 제안 `status` 가 `expired` 로 내려오는지(화면은 `candidate|expired` 에서 승인 버튼 표시).
5. 배치 상태 값 전체 집합(`draft|running|done|cancelled|failed` 로 가정), 작업 상태(`queued|running|succeeded|failed` 확인됨 일부).
6. 인프라 담당: HashRouter 를 써서 nginx `try_files` 가 없어도 된다. CSP `default-src 'self'` 로 충분(인라인 스크립트·스타일 없음, 외부 폰트·이미지 없음, CSV 는 `blob:` 앵커 다운로드).

## 11. 게이트 2 — 자체 코드 리뷰 체크리스트
- [x] 설계서/요청서 명세와 구현 일치(§7 표, 미적용 2건은 사유 명시)
- [x] 에러 처리 누락 없음: 모든 mutation/query 오류를 화면에 표시, 로그아웃 실패는 토스트로 알림(삼키는 catch 없음, 클라이언트의 JSON 파싱 실패 catch 는 기본 문구로 대체한다고 주석)
- [x] 시스템 경계 입력 검증: 폼(범위·길이·PIN·확인 문구), URL 쿼리 파싱(`readParams` 화이트리스트), 서버 응답은 타입 단언이므로 **런타임 스키마 검증은 하지 않음**(제한)
- [x] 하드코딩 비밀 없음(PIN 기본값 등 없음, 모의 서버의 `MOCK_PIN` 은 환경변수)
- [x] 새 의존성은 모두 `npm view` 로 실존·버전·라이선스 확인 후 정확한 버전 고정(react/react-dom 19.3.0, @tanstack/react-query 5.104.1, react-router-dom 7.18.4, vite 8.3.4, @vitejs/plugin-react 6.1.2, typescript 5.9.3, vitest 5.0.3, jsdom 30.1.2, @testing-library/{react 16.3.3, dom 10.4.2, user-event 14.6.7, jest-dom 7.0.1}, axe-core 4.14.0(MPL-2.0), eslint 9.39.5, @eslint/js 9.39.5, typescript-eslint 8.71.1, eslint-plugin-react-hooks 7.1.1, eslint-plugin-jsx-a11y 6.10.2, globals 17.13.0, prettier 3.9.10, @types/react·react-dom 19.3.0, @types/node 22) — 모두 MIT(axe-core 만 MPL-2.0). 브라우저 자동화 도구는 넣지 않음.
- [x] 범위 밖 변경 없음(`web/frontend/` 와 이 노트 외 수정 없음. 단 `.harness-tmp/` 에 임시 스크립트를 만들고 지웠다)

## 12. 공유 문서 갱신 요청 (오케스트레이터가 반영)
| REQ-ID | 컬럼 | 값 |
|---|---|---|
| F-01, F-02(타입 생성 제외), F-04~F-11 | 작업 단위 / 구현 상태 | W-FE / 구현 완료(단위테스트 06단계 대기) |
| F-03 | 구현 상태 | 부분(가상 스크롤 미적용, 설계서 §6 완화 근거) |
| S-W02, S-W03, S-W04(프런트 측), S-W05 | 구현 상태 | 프런트 측 구현 완료(서버·nginx 측은 다른 단위) |
| decisions.md | 기록 요청 | HashRouter 채택(새로고침 안전), ESLint 9 고정(jsx-a11y peer), vitest-axe 대신 axe-core 직접 사용, 색 대비 자동 측정 미수행 |

## 13. 6단계 테스터를 위한 인수 조건
1. `npm ci && npm run check` 가 모두 통과한다(95 테스트).
2. `npm run dev:mock` 후 http://127.0.0.1:5173 에서: 영상 선택(여러 쪽) → 제안 생성 → 상세에서 통과/경고/차단 확인 → 승인 → 배치 초안 → 사전 점검 → 확인 문구 틀리게 입력 시 실행 비활성 → `실행 1건` 정확히 입력 후 실행 → 진행·완료 → 이력에서 롤백(영상 ID 직접 입력).
3. `MOCK_PIN=1234 npm run mock`(+ `npm run dev` 를 `VITE_API_PROXY=http://127.0.0.1:8081` 로) 으로 PIN 화면, 틀린 PIN 메시지, `POST /__mock/expire` 후 화면 조작 시 PIN 재입력 모달.
4. 모의 서버를 끄면 "서버 연결 끊김" 표시, 켜면 "다시 연결"로 복구.
5. 설정에서 라이브/허용 영상은 읽기 전용이고 "이 화면에서는 켤 수 없습니다"가 보인다.
6. 키보드만으로 위 흐름이 가능하고 포커스 링이 보인다(수동). 색 대비는 브라우저 도구로 별도 측정.
