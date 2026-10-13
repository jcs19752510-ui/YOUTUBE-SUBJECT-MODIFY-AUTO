#!/bin/bash
# 사용: run_server.sh <logfile>  (환경: POOL 변수는 코드 기본값 사용)
cd "$(dirname "$0")/../../.."
export PYTHONPATH=web/backend:src:web/tests_fullcheck/h YTWEB_MODE=demo YTWEB_PORT=8080 YTWEB_ALLOWED_HOSTS=127.0.0.1:8080 \
  YTWEB_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:54329/ytweb_test_h YTWEB_BASE_DIR=$PWD YTWEB_SECRETS_DIR=$PWD/.harness-tmp/h-secrets YTWEB_LOG_JSON=0
mkdir -p .harness-tmp/h-secrets
exec .harness-tmp/be/bin/uvicorn server_app:create_app --factory --host 127.0.0.1 --port 8765 --no-server-header --no-access-log > "$1" 2>&1
