"""도메인 서비스(데모 모드 M1). 라우터는 이 계층만 호출하고, 이 계층은 HTTP를 모른다."""

from ytweb.domain import handlers  # noqa: E402,F401  (작업 핸들러 등록: 워커가 domain 의 어느 모듈만 가져와도 3종이 등록되게)
