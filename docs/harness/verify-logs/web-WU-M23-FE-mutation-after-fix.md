# 검증 로그: M23 프런트 조치 후 변이 점검
- 1회차(2026-10-11 23:48~23:54): 39/39 killed 로 보였으나 대조군 실패로 무효(notice.verify 경로 ENOENT).
- 2회차(23:56~23:59): notice.verify 제외, 대조군(무변이) survived 확인, 39곳 변이 39 killed, survived 0.
- 소스 변경 없음: git diff --stat -- web/frontend/src = 0줄. 상세는 docs/harness/units/web-WU-M23-FE-test.md 부록 C.
