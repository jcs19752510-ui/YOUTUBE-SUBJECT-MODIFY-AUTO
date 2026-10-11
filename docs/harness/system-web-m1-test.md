# 시스템 전체 시험 결과서 (web M1) — 8단계

## 8단계 1/2 절 (E2E·결함 종결·구글 기본 상태)

- 시작 2026-10-11 23:17:58 UTC / 종료 23:29 UTC (약 11분, 상한 12분 이내). 스택: compose `harness-tmp-i2`, 127.0.0.1:18083, 재사용(재빌드 없음, 정리하지 않고 둠). 구글·AI 실호출 없음.
- **한 줄 결론: 조건부(미완). 2차(깨끗한) 실행 16건 중 15건 통과, 1건 실패(DEF-8-001). 1차 실행은 오염돼 판정에서 제외.**
- 시험 코드: 기존 `web/tests_integration/test_sys_08_full.py`(001·002, 별도 작성분 재사용)·`test_it_07_rev2.py`(IT-I2-001~050). 새로 만들지 않았고 기대값을 바꾸지 않았다.
- 로그: `.harness-tmp/i2/logs/sys08_12_run1.log`, `sys08_12_run2.log` (git 제외 폴더).

### 첫 실행(run1, 23:18:09~23:21:34) — 오염으로 판정 제외
같은 스택(i2)에 **다른 세션의 7단계 전체 pytest(pid 30390, 23:08 시작, run3.log)가 동시에 돌며 컨테이너를 재시작·DB 초기화**해 연결 끊김(104)·거부(111)·500·assert 어긋남이 났다. 결과: 5 통과, 2 오류, 9 실패(전부 간섭 흔적). 제품 결함으로 세지 않고 원문 로그만 보존. 상대 세션이 23:23에 끝난 뒤 재실행했다. (교훈: 같은 스택을 두 시험이 공유하면 안 된다.)

### 재실행(run2, 23:23:48~23:27:55, 약 4분 7초)
| ID | 내용 | 결과 |
|---|---|---|
| SYS-001 | 기본 상태 google/status 필드·connect/connect-write 409 한국어·dashboard mode=demo·readyz | 합격 |
| SYS-002 | E2E: 세션→불러오기(100건 이상)→제안→승인(approver)→배치 초안(면책 notice·일정)→잘못된 확인 문구 거부→실행→워커 반영 3건→이력→롤백(오입력 거부)→리포트·CSV 면책→감사 chain_ok·핵심 동작 7종→영상당 반영 1회 | 합격 |
| IT-I2-001 | google/status·dashboard 필드 일치(데모·미연결·쓰기 불가) | 합격 |
| IT-I2-002 | connect·connect-write 409 한국어, 상태 불변 | 합격 |
| IT-I2-003 | 잘못된 state 콜백은 토큰 저장 없이 홈 복귀 | 합격 |
| IT-I2-004 | 설정으로 라이브 전환 불가, API 컨테이너 인터넷 없음 | 합격 |
| IT-I2-010 | 면책·AI 고지가 사전 점검→배치→리포트까지 흐름 (DEF-7-011 서버 쪽) | 합격 |
| IT-I2-020 | C-1: 차단 제안의 수정·반려 실제 API | 합격 |
| IT-I2-021 | C-2: 초안 배치 취소 후 같은 제안 재사용 | 합격 |
| IT-I2-022 | C-2: 취소가 다른 초안·미승인에 영향 없음 | 합격 |
| IT-I2-030 | 워커 SIGKILL 후 job 행 종결 (DEF-7B-001) | 합격 |
| IT-I2-040 | api 재시작 중 배치, 이중 반영 없음 | 합격 |
| IT-I2-041 | worker SIGTERM 재시작 중 배치, 이중 반영 없음 | 합격 |
| IT-I2-042 | **db 재시작 중 배치, 모든 항목 success** | **불합격**(아래 DEF-8-001) |
| IT-I2-043 | web 재시작·전체 down/up 후 상태 유지 | 합격 |
| IT-I2-050 | 대시보드 건수가 취소·반영을 따라감 | 합격 |

### 결함
**DEF-8-001 (Medium, 열림, 미수정)** — DB 컨테이너를 배치 20건 반영 도중 재시작(`docker compose restart -t 60 db`)하면 20건 중 19 success·**1 failed**. 이중 반영은 없으나(검증 assert 앞에서 실패, `_no_double_apply` 미도달) 재시작 복구가 그 1건을 완료하지 못해 사용자가 보기에 "일부 실패". 재현: `source .harness-tmp/i2/env.sh; cd web/tests_integration; python -m pytest test_it_07_rev2.py::test_it_i2_042_db_container_restart_mid_batch_no_double_apply -p no:cacheprovider`. 실패 원문: `AssertionError: {'pending': 0, 'running': 0, 'success': 19, 'failed': 1, ...}` (run2 로그 8행). **재현 1/1회, 재실행·원인 분석 미수행(시간 상한)** — 타이밍 의존 재현율 미확인. 5단계 W-BE-B 확인 필요(실패 항목의 failed 사유·`batch.item` 감사 로그 미조회).

### 미수행 (시간 상한 12분)
- 완전한 2회 실행: 깨끗한 실행은 1회뿐(1차는 오염). 042 재실행 미수행.
- 화면(Chromium) 단위 확인, 성능 기준선·부하(SYS-005·006), 입력 검증·멱등(SYS-003·004): 이 절 범위 밖/미수행.
- 호환성·접근성·API 계약·UAT·traceability 100% 판정: 이 조각 범위 밖, 미수행.
- Teardown: 스택은 지시대로 유지. 이 조각이 만든 venv·DB 신규 생성 없음(기존 `.harness-tmp/i2` 재사용). 소유 축 표기: `?? web/tests_integration/test_sys_08_full.py`는 다른 작성자 파일.
