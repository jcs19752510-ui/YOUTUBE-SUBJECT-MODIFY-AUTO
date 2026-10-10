#!/bin/bash
# 데이터 디렉터리가 비어 있을 때 한 번만 실행된다(공식 postgres 이미지 규칙).
# 슈퍼유저(POSTGRES_USER)와 별도로 소유자(ytweb_owner)·앱(ytweb_app) 역할과 ytweb 데이터베이스를 만든다.
# 비밀번호는 비밀 파일에서 읽어 psql 프로세스 환경으로만 넘긴다(명령행·로그에 남기지 않음).
set -Eeuo pipefail

SECRETS_DIR="${YTWEB_DB_SECRETS_DIR:-/run/secrets}"
SHARE_DIR="${YTWEB_DB_SHARE_DIR:-/usr/local/share/ytweb}"

read_secret() {
    local file="$SECRETS_DIR/$1"
    if [ ! -s "$file" ]; then
        echo "[ytweb-init] 비밀 파일이 없거나 비어 있습니다: $1" >&2
        exit 1
    fi
    tr -d '\r\n' < "$file"
}

owner_pw="$(read_secret db_owner_password)"
app_pw="$(read_secret db_app_password)"
if [ "${#owner_pw}" -lt 16 ] || [ "${#app_pw}" -lt 16 ]; then
    echo "[ytweb-init] 비밀번호는 16자 이상이어야 합니다." >&2
    exit 1
fi
if [ "$owner_pw" = "$app_pw" ]; then
    echo "[ytweb-init] 소유자와 앱 비밀번호는 서로 달라야 합니다." >&2
    exit 1
fi

YTWEB_OWNER_PW="$owner_pw" YTWEB_APP_PW="$app_pw" \
psql -v ON_ERROR_STOP=1 --no-psqlrc --username "$POSTGRES_USER" --dbname postgres <<'SQL'
-- 실패한 문장이 서버 로그에 비밀번호째로 남지 않게 한다.
SET log_min_error_statement = 'panic';
SET log_statement = 'none';
\getenv owner_pw YTWEB_OWNER_PW
\getenv app_pw YTWEB_APP_PW

CREATE ROLE ytweb_owner LOGIN PASSWORD :'owner_pw'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 10;
CREATE ROLE ytweb_app LOGIN PASSWORD :'app_pw'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 30;
ALTER ROLE ytweb_owner SET timezone TO 'UTC';
ALTER ROLE ytweb_app SET timezone TO 'UTC';

CREATE DATABASE ytweb OWNER ytweb_owner TEMPLATE template0 ENCODING 'UTF8';
REVOKE ALL ON DATABASE ytweb FROM PUBLIC;
GRANT CONNECT ON DATABASE ytweb TO ytweb_app;
SQL

psql -v ON_ERROR_STOP=1 --no-psqlrc --username "$POSTGRES_USER" --dbname ytweb -f "$SHARE_DIR/schema-grants.sql"
# 헬스체크가 이 표식을 본다. 초기화가 중간에 실패한 볼륨은 재시작해도 정상으로 보이지 않게 한다.
touch "${PGDATA:-/var/lib/postgresql/data}/.ytweb-init-ok"
echo "[ytweb-init] 역할(ytweb_owner, ytweb_app)과 ytweb 데이터베이스를 만들었습니다."
