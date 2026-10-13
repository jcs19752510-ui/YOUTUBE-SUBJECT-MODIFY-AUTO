# 아티팩트 26개 재게시 내부 테스트 결과서 (2026-10-13)

## 1. 개요
- 요청: `아티팩트/`의 HTML 26개를 현재 계정의 아티팩트로 모두 게시(선생님 지시 "C로 진행"). 에이전트 8개 병렬(A1~A8), 작업 지침 `.harness-tmp/artpub/BRIEF.md`.
- 결과: **26/26 게시, 판정 PASS 26 / FAIL 0 / 미수행(게시) 0.** 단 **미리보기(ArtifactCheck)는 26개 전부 미수행**(이 세션에 도구 없음) → 화면 렌더링은 확인하지 못했다.
- 모든 아티팩트는 **비공개**(소유자만 열람). 공유는 Share 메뉴에서 선생님이 직접 한다.

## 2. 시험 항목(판정 기준)
전체 읽기 → 유형 판별 → 껍데기 제거(필요 시) → 정적 검사 6종(제목·본문 글자 수·script/link 허용 목록·금지 API·비밀 문자열) → 게시 → 게시 후 읽기 확인(제목·mermaid 블록 수·본문 크기).

## 3. 결과 표
| ID | 제목 | 담당 | 게시 URL | 판정 |
|---|---|---|---|---|
| AR-01 | 모의면접 재구축 명세서 | A1 | https://claude.ai/artifact/WDN1cL3ux9D2gGYdE4VzuG | PASS(1차) |
| AR-02 | 랭체인·랭그래프·RAG 내부테스트 결과서 | A2→본인 | https://claude.ai/artifact/XCFH1myxV6QW6B77E1unMa | PASS(재시도) |
| AR-03 | 모의면접 스펙 비교 | A3 | https://claude.ai/artifact/Vp1wQ2TtiwvqyKmkW2NvhV | PASS(1차) |
| AR-04 | 모의면접 기능맵 | A3 | https://claude.ai/artifact/Wz4yEzENq3M8ECeCoXARvN | PASS(1차) |
| AR-05 | 랭체인/랭그래프/RAG 사용메뉴 | A3 | https://claude.ai/artifact/3sqM7hmSuHwtD2LUn5YqmG | PASS(1차) |
| AR-06 | 랭체인/랭그래프/RAG 적용 검토 | A3 | https://claude.ai/artifact/S9pgHp1KFwJreuUHvPEEjn | PASS(1차) |
| AR-07 | 국내주식현상 | A4→본인 | https://claude.ai/artifact/Egr7Bzk6QEPENnxan52Hzq | PASS(재시도) |
| AR-08 | 프로젝트 전체 지도 | A4 | https://claude.ai/artifact/TajELYTbbwKHeYwJ3mArWC | PASS(1차) |
| AR-09 | 대본 한눈에 보기 | A4 | https://claude.ai/artifact/Y6Lpmuc4MoCr5WfJnYXPcp | PASS(1차) |
| AR-10 | FINAL-PROJECT-NEW | A5→본인 | https://claude.ai/artifact/DARzc7CCXDWTg6fSLm4iwW | PASS(재시도) |
| AR-11 | 하네스 진행 현황 | A5 | https://claude.ai/artifact/1fRB8y25GER8m3zpLhtHjL | PASS(1차) |
| AR-12 | 줌챗작업현황 | A5 | https://claude.ai/artifact/5CN8k33CSd51x5xinD3T4L | PASS(1차) |
| AR-13 | PDF-TO-HWPX 진행현황 | A5 | https://claude.ai/artifact/14mGkCQhwTHmspJuryvcCK | PASS(1차) |
| AR-14 | 원본과 개발 프로젝트 스펙 비교 | A6 | https://claude.ai/artifact/HnkueBLjmLWkmDSi3Cf9Dt | PASS(1차) |
| AR-15 | 바이브코딩 블로그 현황판 | A6 | https://claude.ai/artifact/HrEZe1ZAye1Wm5miUvuVU7 | PASS(1차) |
| AR-16 | 제목 수정 도구 화면 | A6 | https://claude.ai/artifact/4ChB5HNnBmPKZES1nFajEG | PASS(1차) |
| AR-17 | 제목 수정 도구 파일 안내 | A6 | https://claude.ai/artifact/GnjKFkU6fFa2gPC5xG2ssx | PASS(속도 제한 후 1회 재호출) |
| AR-18 | 온프리미스 전체 검토 | A7 | https://claude.ai/artifact/FUkDVgJTw2DsthahGgVwEB | PASS(1차) |
| AR-19 | 온프리미스 변경 가능여부 절차 | A7 | https://claude.ai/artifact/Dt1CL94Rk81GZMSo3p57Ev | PASS(1차) |
| AR-20 | 사업자가 해야 할 작업순서 | A7 | https://claude.ai/artifact/2gTv6rSNSoa5VYsrZwW64f | PASS(1차) |
| AR-21 | 샘플 이후 작업 순서 | A7 | https://claude.ai/artifact/5A2AZwwB5AAeYuzTyTETVG | PASS(1차) |
| AR-22 | 영상 제작 단계별 가이드 | A8 | https://claude.ai/artifact/2XzrKQkrRDkE5VTbXpbv5W | PASS(1차) |
| AR-23 | 이력서 제출 절차 | A8 | https://claude.ai/artifact/SMLjdhndgNUjs7iEsKuM4e | PASS(1차) |
| AR-24 | 원본처럼 반영 시 검토 결과 | A8 | https://claude.ai/artifact/9gQLQntAGSU2nBLSSoAdp9 | PASS(1차) |
| AR-25 | 유튜브변경작업(내할일) | A8 | https://claude.ai/artifact/YJ3ghDskUXCe6JTjzxceUK | PASS(속도 제한 후 1회 재호출) |
| AR-26 | 유튜브제목변경-전체진행상황 | A8 | https://claude.ai/artifact/Gm4bSU1mfvLmZjyp4vTKq3 | PASS(1차) |

## 4. 첫 실행 결과(실패 포함, 규칙 4)
- AR-02, AR-07, AR-10: 서브에이전트의 첫 게시 호출이 **"Denied by user"로 거부**됨(선생님이 거부한 것이 아니라 백그라운드 에이전트 권한 거부로 추정, 원인은 확인하지 못함). 에이전트는 재시도하지 않고 보고했다. 이후 **메인 세션에서 변환 사본을 전부 읽고 각 1회 게시, 3건 모두 성공**.
- AR-17, AR-25: 첫 호출이 플랫폼 게시 속도 제한으로 거부, 안내대로 재호출 1회 성공. 중복 게시 없음.

## 5. 변환(플랫폼 껍데기 제거)
- 원본 형식(변환 없음): AR-25, AR-26. 나머지 24개는 `<!doctype>`·html/head/body·meta 2종·reset style(+해당 파일은 mermaid 런타임, highlight.js 런타임)을 제거한 사본으로 게시. 작성자 스크립트·스타일·본문은 유지. 제목은 파일 안 `<title>` 그대로.
- 정적 검사: 제목 일치, 본문 글자 수 일치(끝 줄바꿈 1자 차이만), 외부 script는 AR-22의 cdnjs `marked@4.3.0` 하나뿐(허용 목록·버전 고정 충족), 스타일시트는 fonts.googleapis.com뿐, alert/prompt/print/mailto/form/iframe 없음, 비밀 문자열 0건(AR-01의 `confirm(`은 본문 문구).
- 게시 후 읽기: 제목 일치, mermaid 블록 수 원본과 일치(AR-01 19개, AR-05·06·23 등), 틀 이중 삽입 없음. AR-15는 껍데기 body 배경색 때문에 원본과 6바이트 차이(본문 동일).

## 6. 원본과 동일한 한계·잔여 위험
- AR-03 본문에 옛 계정 아티팩트 링크(`claude.ai/artifact/9WauvNaQgxA57HLeNfH925`)가 그대로 있다. 이 계정에서는 열리지 않을 수 있고, 바꾸지 않았다.
- AR-18 표에 닫는 태그가 어긋난 행이 원본에 있다. 고치지 않았다.
- AR-22는 marked를 인터넷에서 불러와 본문을 그리는 구조라 로드가 막히면 본문이 비어 보인다(원본과 같음).
- AR-23 mermaid 노드 색은 밝은 색으로 고정, AR-25 체크 상태는 브라우저 localStorage에만 저장.
- AR-15 `@import` 위치 문제는 원본 그대로.
- 대시보드형 `제목 수정 자동화 진행판(대시보드형)/`은 일반 페이지로 게시할 수 없어 **게시하지 않았다**(26개에 포함되지 않음).
- 이 저장소의 `아티팩트/` 사본과 게시본은 서로 자동 동기화되지 않는다.

## 7. 검증 로그
1차: 에이전트별 전체 읽기·정적 검사·게시·읽기 확인(`docs/harness/artifact-republish/A1~A8.md`). 2차: 메인 세션에서 거부된 3건의 사본을 전부 다시 읽고(콘텐츠 이상 없음, 비밀 문자열 없음) 게시 결과 URL을 직접 확인, 8개 결과서와 알림 25건(게시 알림)을 대조해 26개 URL 일치 확인.

## 8. 미수행
- 미리보기·콘솔 오류 확인 26개 전부(도구 없음). 특히 mermaid 렌더, AR-09 복사 버튼, AR-22 marked 렌더는 눈으로 확인하지 못했다.
- 거부됐던 AR-02·07·10의 게시 후 `read` 재확인은 미수행(게시 응답의 URL·버전만 확인).

## 9. 임시 파일
`.harness-tmp/artpub/`(저장소에 커밋되지 않음, 규칙 K 정리 대상).

## 10. 결론
게시 26/26 성공, 렌더링 확인은 미수행이므로 "게시 완료, 화면 확인 전"으로 판정한다.
