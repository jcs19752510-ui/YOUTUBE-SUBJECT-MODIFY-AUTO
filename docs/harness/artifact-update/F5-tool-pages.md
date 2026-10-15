# F5 제목 수정 도구 아티팩트 2종 갱신 결과 (2026-10-14)

시작 01:34:50 UTC, 발행 완료 약 01:37 UTC (상한 12분 이내). 두 페이지는 웹이 아니라 옛 터미널(CLI) 도구 `src/youtube_title`를 설명하는 페이지다(CLI 코드는 저장소에 그대로 있음). 그래서 CLI 설명은 유지하고 낡은 부분만 고쳤다.

게시: 제목 수정 도구 화면 https://claude.ai/artifact/4ChB5HNnBmPKZES1nFajEG (버전 2, 1791941771-7886) / 파일 안내 https://claude.ai/artifact/GnjKFkU6fFa2gPC5xG2ssx (버전 2, 1791941774-59bb). 게시 직전 read로 현재 게시본이 옛 저장본과 같음을 확인했다. 게시 후 재읽기는 하지 않았다(publish 성공 응답만 확인).

## 제목 수정 도구 화면 (AR-16)
| 옛 | 새 | 근거 |
|---|---|---|
| 이름 `ytitle` (본문·명령줄·캡처 출력 전부) | `youtube_title` | CLAUDE.md(2026-10-11 이름 변경), `src/youtube_title/` |
| 웹 프로그램 언급 없음 | 상단에 안내 상자 추가: 웹(127.0.0.1:8080, web/), 메뉴 7개와 홈의 구글 연결 카드, 사용법은 WEB_USER_MANUAL.md | `web/frontend/src/i18n/ko.ts` nav, `web/README.md`, CLAUDE.md |
| 배지 "개발 중"(approve, apply, apply --live) | "내부 테스트 합격(실제 유튜브 미확인)" | 파일 안내 페이지의 unit-5 합격 기재, `docs/harness/units/unit-5-test.md` |
| 배지 "구현 완료, 독립 검증 대기"(plan, report), "계획은 구현 완료, --live는 개발 중"(rollback) | plan, report는 "내부 테스트 합격", rollback은 "내부 테스트 합격(실제 유튜브 미확인)" | `docs/harness/units/unit-3,4,6-test.md` 존재 |
| 배지 "내부 검증 완료"(4곳) | "내부 테스트 합격" | 용어 통일 |
| 하단 개발 상태 문장 | WU-0~6 내부 테스트 합격, 실제 구글·유튜브 접속과 실제 변경·되돌리기는 한 번도 안 함 | CLAUDE.md "한 번도 안 한 것" |

## 제목 수정 도구 파일 안내 (AR-17)
| 옛 | 새 | 근거 |
|---|---|---|
| `ytitle`, `src/ytitle/`, `python -m ytitle` | `youtube_title` 계열 | `git ls-files src` |
| 웹 파일 설명 없음 | 도입부 안내 문단, 바로가기 "웹 프로그램 파일", 맨 아래 새 절(17행: web/backend, frontend, docker, compose, scripts, .env.example, README, WEB_* 문서, API, 웹 시험 결과서) | `git ls-files web`, `ls docs/yt docs/harness`, 각 문서 첫 줄 |

src 부품 표(34개 파일)와 명령어 표(9개), 설계 문서 8행은 현재 파일과 일치해 그대로 뒀다.

## 확인하지 못해 그대로 둔 항목
- 캡처한 출력 문구는 이름만 치환했고 CLI를 다시 실행하지는 않았다. 현재 출력과 글자 단위로 같은지는 미확인.
- 7개 시험의 TC 수·변이 점검·커버리지 숫자는 재확인하지 않았다(옛 값 유지). 이후 CLI 코드가 바뀌었는지도 미확인.
- 낱말 풀이, 테스트 카드 목록에 웹 용어(데모 모드, 배치, 일괄 승인)는 추가하지 않았다.
- 파일 안내 설계 문서 표의 DESIGN.md, 04_ux_design.md 설명은 웹 개정(v4) 내용을 반영하지 않았다.

## 질문
1. 두 페이지를 CLI 안내로 유지할지, 웹 화면 기준으로 새로 만들지 결정이 필요하다(이번에는 최소 수정).
2. 저장소 사본(`아티팩트/*.html`, 껍데기 포함)에도 같은 수정을 적용했다. git 쓰기는 금지라 커밋은 하지 않았다.
