# syntax=docker/dockerfile:1
# api / worker / migrate 가 공유하는 이미지. 빌드 컨텍스트는 저장소 루트(.dockerignore 적용).
# 베이스 이미지는 다이제스트로 고정한다. 갱신: web/scripts/pin-digests.ps1
ARG PYTHON_IMAGE=python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

FROM ${PYTHON_IMAGE} AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:${PATH}
WORKDIR /build
COPY web/backend/requirements.txt /build/requirements.txt
COPY web/docker/requirements-ytitle.txt /build/requirements-ytitle.txt
# 해시가 맞지 않거나 휠이 없으면 실패한다(소스 빌드·임의 패키지 설치 금지).
RUN pip install --only-binary=:all: --require-hashes --no-deps -r /build/requirements.txt \
 && pip install --only-binary=:all: --require-hashes --no-deps -r /build/requirements-ytitle.txt

FROM ${PYTHON_IMAGE} AS runtime
ENV PATH=/opt/venv/bin:${PATH} \
    PYTHONPATH=/app/backend:/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    YTWEB_BASE_DIR=/app \
    TZ=Asia/Seoul
RUN groupadd --system --gid 10001 ytweb \
 && useradd --system --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin ytweb \
 && install -d -o 10001 -g 10001 -m 0700 /var/lib/ytweb/secrets
COPY --from=builder /opt/venv /opt/venv
# 코어(src/ytitle)는 복사하지 않고 PYTHONPATH 로 같은 소스를 쓴다(웹 전용 사본 금지, WEB_DESIGN §1).
COPY src/ytitle /app/src/ytitle
COPY config /app/config
COPY web/backend /app/backend
WORKDIR /app/backend
# 읽기 전용 루트에서 .pyc 를 쓸 수 없으므로 빌드 때 미리 만든다. 임포트 스모크 테스트로 의존성 누락을 빌드 단계에서 잡는다.
RUN python -m compileall -q /app/backend /app/src \
 && python -c "import ytitle.config, ytitle.validator, ytitle.limits, ytitle.updater, ytitle.banned_terms, ytweb.app, ytweb.worker, ytweb.migrate"
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=6 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).read()"]
CMD ["uvicorn", "ytweb.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
