# 9단계 보안 시험 (web/tests_security)

공격자 관점 시험 모음이다. **운영 코드는 읽기만 하고 고치지 않는다.** 결과와 해석은 `docs/harness/security-web-m1-test.md` 에 있다.

| 파일 | 종류 | 무엇을 하나 | 필요한 것 |
|---|---|---|---|
| `test_sec_01_http_boundary.py` | 오프라인(임시 SQLite) | Host·Origin·Sec-Fetch-Site·CSRF·세션·PIN·속도/크기 제한·헤더·오류 노출·정적 경로 순회 | 파이썬 venv |
| `test_sec_02_injection_ai_integrity.py` | 오프라인 | SQL/XSS/CSV 주입, AI 입력·출력 정제(규칙 J), 승인 HMAC 변조, 감사 체인, 멱등성, 롤백 안전, 외부 통신 부재, 로그 마스킹 | 파이썬 venv |
| `test_sec_03_static_repo.py` | 정적 | 비밀 유출(현재 파일 트리), .gitignore/.dockerignore, compose·Dockerfile·nginx·DB 설정, 의존성 잠금, 프런트 금지 패턴, 스크립트, CI 예시 | 파이썬 venv + PyYAML |
| `test_sec_04_live_stack.py` | 실스택(컨테이너) | nginx 경유 공격(Host·밀수·경로·크기·느린 헤더), docker inspect 하드닝, 네트워크 격리 행렬, DB 권한 공격, 백업 스크립트 이름 주입, PIN 동시 추측 | docker, 임시 스택 |
| `mutation_check.py` | 변이 점검 | 위 시험이 보안 통제 파괴를 실제로 잡는지 원본 사본에 변이를 넣어 확인 | 파이썬 venv |

## 재실행

```bash
# 1) 파이썬 환경 (저장소 해시 잠금 파일로 설치)
python3 -m venv .harness-tmp/sec/venv_be
.harness-tmp/sec/venv_be/bin/pip install --require-hashes --no-deps -r web/backend/requirements-dev.txt
.harness-tmp/sec/venv_be/bin/pip install --require-hashes --no-deps -r web/docker/requirements-ytitle.txt

# 2) 오프라인·정적 시험 (약 2분)
.harness-tmp/sec/venv_be/bin/python -m pytest web/tests_security -q -p no:cacheprovider

# 3) 변이 점검 (코드 74곳 + 설정 45곳, 약 1시간. 병렬은 --only 로 나눈다)
.harness-tmp/sec/venv_be/bin/python web/tests_security/mutation_check.py --out .harness-tmp/sec/out/mut.json
.harness-tmp/sec/venv_be/bin/python web/tests_security/mutation_check.py --infra --out .harness-tmp/sec/out/mut_infra.json

# 4) 실스택 시험: 임시 스택을 '운영 8080 이 아닌' 포트와 임시 비밀로 띄운다
#    - 이미지는 harness-tmp-sec-{api,web,db}:local 로 빌드, 프로젝트 이름 harness-tmp-sec, 호스트 포트 127.0.0.1:18380
#    - web/compose.yaml 사본에서 "127.0.0.1:8080:8080" 만 "127.0.0.1:18380:8080" 으로 바꾼다. 비밀 파일 3개는 임의 문자열로 만든다(저장소 밖).
YTWEB_IMAGE_PREFIX=harness-tmp-sec docker compose -p harness-tmp-sec -f <사본>/compose.yaml up -d --no-build
YTWEB_SEC_LIVE_PORT=18380 YTWEB_SEC_PROJECT=harness-tmp-sec YTWEB_SEC_SECRETS_DIR=<임시 secrets 폴더> \
  .harness-tmp/sec/venv_be/bin/python -m pytest web/tests_security/test_sec_04_live_stack.py -q -p no:cacheprovider
#    끝나면 docker compose -p harness-tmp-sec down -v 와 harness-tmp-sec-* 이미지 삭제(규칙 K).
```

## 읽는 법

- `xfail(strict=True)` 시험은 **바람직한 동작**을 적어 둔 것이다. 지금은 결함(DEF-9-nnn) 때문에 실패하는 것이 정상이며, 결함을 고치면 XPASS 가 되어 **일부러 실패**한다 → 그때 `xfail` 표식을 지운다.
- 이름에 `repro`/`limitation` 이 든 시험은 알려진 한계를 **재현**한다. 통과하는 동안 한계가 존재한다.
- `test_sec_04` 의 `test_zz_nginx_rate_limits_trigger` 는 마지막에 속도 제한을 소모한다. 이어서 다시 돌릴 때는 1분 뒤에 실행하라(세션 발급 10/분).
- 실스택 시험은 스택 안의 데이터(제안·승인)를 쌓는다. 후보가 바닥나면 스택을 새로 만든다.
