# 내부 검증 로그 — 웹 전환 3단계 산출물 개정 (as-built)

## 대상 산출물
- 파일: `docs/yt/DESIGN.md`(Part B 추가, 1~13장 보존), `docs/yt/WEB_DESIGN.md`(v2 개정), `docs/yt/openapi.json`(앱 객체에서 직접 추출), `docs/yt/API.md`(신규)
- 작성 에이전트: 3단계 문서 개정 에이전트(웹 전환 트랙 재개 웨이브 1)
- 적용 Tier: **High** (DEC-032). 최소 2회 검증 — 아래 3회 수행
- 버전: Part B v0(`B-v0`) → v1 → v2(최종, 아직 6단계 독립 검증 결과는 반영 전)
- 한계(정직하게): 이 로그의 "독립 심사자"는 같은 에이전트가 역할을 바꿔 수행한 것이다. 코드 쪽 독립 검증(6단계 4건)은 별도 에이전트가 진행 중이며 그 결과는 반영되지 않았다(DESIGN.md 상단 "검증 대기 항목" V-01~V-09).

## 코드 대조 근거 (재현 방법 포함)
| # | 방법 | 결과 |
|---|---|---|
| E1 | `.harness-tmp/venv_doc_design`(Python 3.12, `pip install --require-hashes -r web/backend/requirements-dev.txt` + 루트 `pip install -e .`)에서 `create_app(WebSettings(...sqlite:///:memory:...)).openapi()`를 덤프해 `docs/yt/openapi.json` 생성. 두 번째로 다시 덤프해 `cmp` | 28경로·**31동작**, 스키마 39개, 재생성본과 **바이트 동일**(결정적) |
| E2 | 라우터 소스 12개 파일을 직접 읽고 엔드포인트별 함수 존재를 스크립트로 확인(`def <fn>(`), 설계(WEB_DESIGN §3 표) 31행과 (메서드,경로) 집합 비교, 성공 상태 코드 비교 | 설계에만 있음 0, 구현에만 있음 0, 상태코드 불일치 0 → DESIGN.md 부록 A-1 |
| E3 | 설계 §3 "주요 스키마" 필드 집합 ↔ openapi `components.schemas` 비교(14개 스키마) | 일치 12, 구현이 상위 집합 2(`VideoDetail.preserved`, `Batch.precheck`) → 부록 A-2 |
| E4 | 프런트 `types.ts` 인터페이스 19개 ↔ openapi 스키마 최상위 필드 비교 | 프런트에만 있는 필드 0, 서버에만 있는 선택 필드 4(`preserved`, `VideoReport.changes/label/target`) + 수작업 `AuditEntry`의 `prev_hash/hash`; 값 집합 불일치(`BatchStatus` 등)는 `types.ts`·`BatchDetailPage.tsx`·`labels.ts` 직접 읽어 확인 → DV-W09 |
| E5 | 모델 `Base.metadata`(14테이블) ↔ `alembic/versions/0001_initial.py` DDL(`CREATE TABLE` 14개) 컬럼 이름 집합 비교 | 14/14 일치, 인덱스 9 + 권한 회수 1 확인 → 부록 A-3 |
| E6 | 임시 SQLite+워커(`Worker.tick`)로 실제 호출: 세션 발급 → 동기화 → 제안 생성 → 승인 → 배치 생성·재생·키 재사용 → 실행 → 워커 처리 → 이력 → 롤백 → 리포트·CSV → 감사 → 설정 → 오류 사례 20여 건 | `API.md`의 JSON 예시는 전부 이 호출 결과. 한국 시간 경계(UTC 16:25 → KST 다음 날 예약) 실제 확인 |
| E7 | 검사 순서·오류 코드 실측 12건(`order_check`): 세션 없음+잘못된 본문→401, 잘못된 Origin→403 `origin_not_allowed`(세션보다 먼저), CSRF 틀림→403, 본문 오류→422, 키 누락→400, 키 형식→400, 빈 목록→422, 없는 PIN 해제→409, PUT→405, `/docs`·`/openapi.json`→404 | 문서의 "검사 순서"·오류 표와 일치. 이 실측으로 `batch_empty` 설명 오류 1건 발견(2차 아님, 1차 결함 5번) |
| E8 | 문서 속 `/api/v1/...` 경로·`file.py` 경로·`UPPER_snake` 오류 코드를 코드/`openapi.json`에서 grep | 미존재 0(동적 생성되는 `limit_*` 4개는 `"limit_"+code.lower()` 규칙으로 문서화) |
| E9 | ID 정합 스크립트: DV-W01~20, Q-W01~18, EVT-W01~31, NFR-W01~12, ADR-011~026이 정의 후 참조되는지, 참조만 있고 정의 없는 ID | 0건 |
| E10 | 마크다운 표 열 수 점검(`|` 개수) | `API.md` 0건, `DESIGN.md` Part B 0건(원문 CLI 부분 1건은 기존), `WEB_DESIGN.md` 4건 발견 → 수정(2차 결함 3번) |
| E11 | 원문 보존: 개정 전 `DESIGN.md`의 모든 줄이 개정 후 파일에 같은 순서로 존재하는지 | 누락 0줄 |
| E12 | 라이선스: `importlib.metadata`로 설치 패키지 메타데이터 조회(fastapi MIT, pydantic MIT, sqlalchemy MIT, alembic MIT, uvicorn BSD-3, starlette BSD-3, PyYAML MIT, python-dotenv BSD-3, tzdata Apache-2.0, **psycopg LGPL-3.0**) | W2-1에 기록, psycopg는 Q-W15로 질문 |

## 1차 검증 (작성자 관점 자가 재검토)
- 검증자(역할): 작성자 / 일시: 2026-10-10
- 체크리스트
  - [x] 입력 계약: 요청서·decisions·구현 노트 4건·코드(라우터 12·도메인·코어·모델·마이그레이션·compose·nginx·Dockerfile·db 스크립트·프런트 타입/엔드포인트) 직접 읽음
  - [x] 출력 계약: 아키텍처(4+1서비스, 작업 단위 확정표), ADR, 14테이블, 게이트 14단계 이식 현황·M3 목록, 시간대, 배포 토폴로지, 비기능, 마일스톤, 부록 대조표, 편차 표, 질문 목록 — 존재
  - [x] 상위 문서와 모순 없음: 모순은 숨기지 않고 편차 표로 올림(DV-W01~20)
  - [x] 추측: 성능·SLO·RTO/RPO 수치는 "제안·미실측"으로 표기, 질문으로 전환(Q-W07). 추정 문장 없음
  - [x] 구조/논리 결함 점검
  - [x] 오탈자·표 형식 점검
- 발견된 결함 목록 (6건)
  1. `API.md` 헤더 표: Cookie 행이 `auth/me`도 쿠키 필수인 것처럼 읽힘 (실제로는 쿠키 없이 호출 가능)
  2. `API.md` 감사 `action` 목록이 `videos.sync_request`, `suggestion.generate`, `suggestion.generate_failed`를 빠뜨림 (코드 grep 결과와 불일치)
  3. `API.md` `batch_empty` 설명이 "선택 없음"까지 포함해 실제(빈 목록은 스키마 단계 422 `validation_error`, E7)와 어긋남
  4. Part B W11/W4-3 초안의 "응답 모델 7개 라우터" → 실제 8개 모듈
  5. Q-W02 ②가 확인하지 않은 사실("웹은 skip_reason 전체 표시 확인")을 단정
  6. Q-W18 항목명이 질문과 무관한 단어(psycopg)로 시작, A-2b의 "불일치" 의미가 오해 소지(서버에만 있는 선택 필드라는 설명 없음)
- 조치 내용: 6건 모두 수정 → v1

## 2차 검증 (독립 심사자 관점 — "이 문서로 구현할 개발자/승인할 사용자")
- 검증자(역할): 독립 심사자(역할 전환) / 일시: 2026-10-10
- 체크리스트
  - [x] 1차 지적 6건 반영 재확인(E8, E9 재실행)
  - [x] 엣지 케이스: 오류 응답 형식 3계층(백엔드 problem+json / nginx 444·429 / 스키마 없는 openapi) 구분해 서술 — 확인 완료
  - [x] 문서만으로 다음 단계가 질문 없이 시작 가능한가: 8단계 계약 테스트가 **무엇을 기준으로 삼는지**(openapi + API.md 표) 명시 — OK
  - [x] 비가역 결정의 근거: PostgreSQL 17, 세션 방식, 감사 체인, 작업 큐 ADR에 대안·기각 사유·되돌리기 난이도 있음
  - [x] 보안/운영 위험: 같은 PC 프로그램 위험(PIN 꺼짐)을 숨기지 않고 W9-6에 올림 + Q-W12
- 발견된 결함 목록 (3건)
  1. **누락**: 출력 계약 8번 "기획서 대비 트레이드오프 및 미해결 사항", 기획서 가정 중 설계에 영향 주는 것, 레퍼런스 비교 참조 여부(레퍼런스 없음이라는 사유)가 별도 절로 없었음
  2. **누락**: 가정이 틀렸을 때의 파급(특히 PIN 기본 꺼짐 → M3 High)이 한곳에 모여 있지 않음
  3. 형식 오류: `WEB_DESIGN.md`의 표 행 4개에서 코드 스팬 안의 `|`가 열 구분자로 읽혀 열 수가 어긋남(E10)
- 조치 내용: W12-1 절 신설(레퍼런스 해당 없음 사유, 02 개정과의 관계, 가정-반영-파급 표, 트레이드오프 6건, 미해결 포인터), 표 4행의 `|`를 `\|`로 이스케이프 → v2

## 3차 검증 (수정 확인)
- 방법: E9·E10·E11을 재실행하고 W12-1 내용을 코드/결정 로그와 대조(Q-1/3/5/6/8/9/10 항목은 DEC-034 원문과 대조)
- 결과: 정의 없이 참조된 ID 0건, 표 열 수 어긋남 0건(기존 CLI 부분 1건 제외), 원문 줄 누락 0건, 가정 표 DEC-034 내용과 일치
- 발견된 결함: **0건**

## 최종 판정
- [x] **PASS** (결함 0건, 검증 3회, 코드 대조 근거 E1~E12) — 단 "PASS"는 **문서와 현재 코드의 일치**에 대한 판정이다. 아래는 PASS에 포함되지 않는다.
  - 6단계 독립 검증 4건·7단계 통합 시험 결과의 반영(미수행 — 검증 대기 항목 V-01~V-05)
  - 사용자 PC(Docker Desktop, PowerShell 5.1, 브라우저 쿠키·CSP) 실측(미수행 — V-06)
  - 위협 모델(STRIDE) 갱신 `docs/yt/threat_model.md`와 `04_ux_design.md`·2단계 기획서 개정(이 에이전트 범위 밖, 별도 산출)
  - 성능·SLO 수치의 실측(없음 — 제안값)
  - 사용자 결정 18건(W13)

## 설계-구현 편차 요약 (결정 대기 — 임의로 한쪽을 택하지 않음)
편차 20건은 `DESIGN.md` W12 표에 있다. 사용자·오케스트레이터 판단이 필요한 핵심:
| ID | 요지 |
|---|---|
| DV-W05/06/09 | `openapi.json`이 필수 헤더·오류 본문·일부 응답을 표현하지 못하고 시각 표기가 `Z`/`+00:00` 혼재, 프런트 타입이 손작업 |
| DV-W07 | 경고 제안 승인 시 "사유 확인"을 서버가 강제하지 않음 |
| DV-W08 | **문서(DEC-041 ④, README)는 "감사 서명 키"를 말하지만 코드의 감사 체인은 키 없는 SHA-256**, 실제 키는 승인용 하나 — 복원 시 영향은 감사 체인이 아니라 기존 승인 무효 |
| DV-W10 | DEC-035 "React 18, TanStack Router" ≠ 실제 React 19.3.0·react-router-dom 7 |
| DV-W14/15/17 | 결정은 났으나 코드 미반영(운영 빌드 테스트 제외, 데모 최소 노출수 0, 워커 하트비트) |
| DV-W04/20 | 요청서 W-014(재변경 간격·금칙어·AI 설정 화면), W-016(백업 암호화·보관) 대비 범위 |

## 사용자 확인 필요 질문 (모음 — 상세 선택지·권장안은 `DESIGN.md` W13)
Q-W01 WU-5 질문 5가지 · Q-W02 UI 이상 6건 · Q-W03 속도 제한 · Q-W04 금칙어 사전 · Q-W05 경고 승인 서버 강제 · Q-W06 로그/감사 보관·파기 · Q-W07 RTO/RPO·SLO · Q-W08 알림 채널 · Q-W09 AI 비용 상한 · Q-W10 감사 체인 키 · Q-W11 승인 만료 기준(M3) · Q-W12 M3 전 PIN 필수 · Q-W13 edge 네트워크·프로필 · Q-W14 openapi 보정 · Q-W15 psycopg LGPL 배포 여부 · Q-W16 ruff 설정 시점 · Q-W17 기존 대기 항목(10건·8080 등) · Q-W18 사용자 PC 확인 항목

## 공유 문서 갱신 요청 (오케스트레이터가 반영 — 이 에이전트는 공유 문서를 수정하지 않았다)
**traceability.md**
- W-001~W-017, D-01~D-14, S-W01~S-W16의 "설계 매핑" 컬럼: `DESIGN.md` 부록 A-6 표 그대로.
- 신규 ID 등록: `EVT-W01~W31`(API, 부록 A-1), `NFR-W01~W12`, `SEC-W17~W23`(S-W에서 파생된 구현 사실), `ADR-011~026`, `DV-W01~W20`, `Q-W01~W18`. (다른 에이전트가 같은 번호 대역을 쓰는지 충돌 확인 필요 — 이 문서는 충돌을 피하려고 `-W` 접미 네임스페이스를 썼다.)
- 상태 컬럼 후보: W-003~W-013·W-017 = "구현됨(데모 모드, 독립 검증 대기)", D-01 = "부분(dev/test 프로필 미구현, migrate 포함 5서비스)", D-05 = "부분", D-07b = "부분(자동 사전 백업 없음)", D-11 = "미충족(9단계)", F-02 = "부분(타입 수작업)", F-03 = "부분(가상 스크롤 미적용)", W-014 = "부분(DV-W04)", W-016 = "부분(DV-W20)", S-W07 = "M1 모의만", S-W08·S-W10 = "M2 대기", S-W15 = "대기".

**decisions.md** (기록 요청, 규칙 G append-only이므로 새 항목으로)
1. DEC-035 정정: 프런트 실제 채택 = React 19.3.0 / Vite 8.3.4 / react-router-dom 7(HashRouter) (DV-W10, ADR-012).
2. DEC-041 ④ 정정: "감사 HMAC 키" 서술은 사실과 다름 — 감사 체인은 키 없는 SHA-256, 서명 키는 승인용 하나(DV-W08, Q-W10 결정 대기).
3. 미기록 결정: web만 `edge` 네트워크 추가(ADR-023), 코어 `PYTHONPATH` 공유(ADR-024), migrate 별도 서비스·소유자 계정(ADR-025), ESLint 9 고정·axe-core 직접 사용·HashRouter(ADR-012, 026), BE-B D2(검증 불일치는 success+verify_failed, 자동 롤백 없음), D5~D9(중복 제안 재사용, 목록 `items:[]`, 롤백도 쿼터 사용, 배치 상태 값 집합).
4. 승인 TTL 기준 시각(배치 실행 확정 시각)은 DEC-042 D3로 이미 기록됨 — M3 재평가 트리거로 유지(Q-W11).
5. 결정은 났으나 코드 미반영 3건(DEC-042 D1, DEC-041 ⑤, 워커 하트비트)을 STATE "후속"에 유지.

**STATE.md**
- §6 "문서 개정 3건" 중 3단계(DESIGN/WEB_DESIGN/openapi/API)가 초안 완료(6단계 검증 결과 반영 대기). 2단계·4단계 개정은 별도 진행.
- 임시 산출물 정리 기록: 이 에이전트가 만든 `.harness-tmp/venv_doc_design`, `.harness-tmp/venv_doc_design_dir`, `.harness-tmp/doc_design/`는 아래 Teardown에서 삭제.

## 7. Teardown (규칙 K — 자기가 만든 것만)
| 항목 | 조치 |
|---|---|
| `.harness-tmp/venv_doc_design/`(가상환경) | 삭제 |
| `.harness-tmp/venv_doc_design_dir/`(실수로 만든 빈 폴더) | 삭제 |
| `.harness-tmp/doc_design/`(임시 SQLite·샘플 실행 폴더) | 삭제 |
| 스크래치패드의 스크립트(저장소 밖) | 유지(저장소 미포함) |
| 외부 호출 | 없음 — 구글·YouTube·AI 호출 0, 네트워크는 패키지 설치만, 공유 PostgreSQL 미사용(SQLite 임시 파일만) |
| git | 조회(`git status`)만 사용. 커밋·푸시 안 함 |
