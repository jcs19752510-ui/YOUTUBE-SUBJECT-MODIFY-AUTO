#!/usr/bin/env bash
# 시험용 스택 폴더를 만든다(원본 web/ 은 수정하지 않는다).
#   mkstack.sh <web 소스 루트> <대상 폴더> [호스트 포트=18080]
# 결과: <대상>/compose.yaml(호스트 게시 포트만 바꾼 사본), <대상>/scripts(원본 사본), <대상>/secrets(무작위 64자 16진수 3개, 0644 — 0600 이면 비루트 컨테이너가 못 읽음)
set -euo pipefail
SRC="${1:?web 소스 루트}"; DEST="${2:?대상 폴더}"; PORT="${3:-18080}"
mkdir -p "$DEST/secrets" "$DEST/backups"
sed "s|\"127.0.0.1:8080:8080\"|\"127.0.0.1:${PORT}:8080\"|" "$SRC/compose.yaml" > "$DEST/compose.yaml"
rm -rf "$DEST/scripts"; cp -a "$SRC/scripts" "$DEST/scripts"
for n in db_superuser_password db_owner_password db_app_password; do
  if [ ! -s "$DEST/secrets/$n" ]; then
    python3 -c "import secrets,sys;sys.stdout.write(secrets.token_hex(32))" > "$DEST/secrets/$n"
    chmod 644 "$DEST/secrets/$n"
  fi
done
# compose.yaml 이 원본과 다른 곳은 호스트 게시 포트 한 줄뿐이어야 한다
n=$(diff "$SRC/compose.yaml" "$DEST/compose.yaml" | grep -c '^[<>]' || true)
[ "$n" = "2" ] || [ "$PORT" = "8080" ] || { echo "compose 사본이 원본과 포트 한 줄 이상 다름" >&2; exit 1; }
echo "stack ready: $DEST (port $PORT)"
