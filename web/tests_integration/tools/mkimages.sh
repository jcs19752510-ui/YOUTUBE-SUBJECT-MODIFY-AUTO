#!/usr/bin/env bash
# 시험용 이미지 3종(<prefix>-{api,web,db}:local)을 만든다. 저장소 Dockerfile 은 수정하지 않고, 프록시 CA 두 줄만 덧붙인 사본(.harness-tmp)으로 빌드한다.
#   mkimages.sh <web 소스가 있는 저장소 루트> <작업 폴더> [이미지 접두사=harness-tmp-int] [만들 이미지 목록="db api web"]
# 필요: DOCKER_HOST(시험 전용 dockerd), /root/.ccr/ca-bundle.crt(프록시 CA, 클라우드 한정 — 사용자 PC 에서는 불필요)
set -euo pipefail
ROOT="${1:?저장소 루트}"; WORK="${2:?작업 폴더}"; PFX="${3:-harness-tmp-int}"; WHICH="${4:-db api web}"
CA="${IT_CA_BUNDLE:-/root/.ccr/ca-bundle.crt}"
mkdir -p "$WORK/ctx_ca" "$WORK/dockerfiles"
cp "$CA" "$WORK/ctx_ca/ca.crt"
CALINES='COPY --from=ca ca.crt /usr/local/share/ca-certificates-extra.crt\nENV SSL_CERT_FILE=/usr/local/share/ca-certificates-extra.crt PIP_CERT=/usr/local/share/ca-certificates-extra.crt NODE_EXTRA_CA_CERTS=/usr/local/share/ca-certificates-extra.crt REQUESTS_CA_BUNDLE=/usr/local/share/ca-certificates-extra.crt'
sed "/^FROM \${PYTHON_IMAGE} AS builder/a $CALINES" "$ROOT/web/docker/api.Dockerfile" > "$WORK/dockerfiles/api.Dockerfile"
sed "/^FROM \${NODE_IMAGE} AS build/a $CALINES" "$ROOT/web/docker/web.Dockerfile" > "$WORK/dockerfiles/web.Dockerfile"
cp "$ROOT/web/docker/db.Dockerfile" "$WORK/dockerfiles/db.Dockerfile"
# 차이는 CA 두 줄뿐이어야 한다
for n in api web; do
  d=$(diff "$ROOT/web/docker/$n.Dockerfile" "$WORK/dockerfiles/$n.Dockerfile" | grep -c '^[<>]' || true)
  [ "$d" = "2" ] || { echo "$n.Dockerfile 사본이 원본과 2줄 외에 다름($d)" >&2; exit 1; }
done
for n in $WHICH; do
  docker build -q --build-context ca="$WORK/ctx_ca" -f "$WORK/dockerfiles/$n.Dockerfile" -t "$PFX-$n:local" "$ROOT" >/dev/null
  echo "built $PFX-$n:local"
done
