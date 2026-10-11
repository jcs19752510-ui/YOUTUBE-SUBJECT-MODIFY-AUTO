# syntax=docker/dockerfile:1
# React(Vite) 정적 파일을 빌드해 비루트 nginx 에 넣는다. 최종 이미지에는 node·소스·소스맵이 없다.
# 베이스 이미지는 다이제스트로 고정한다. 갱신: web/scripts/pin-digests.ps1
ARG NODE_IMAGE=node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392
ARG NGINX_IMAGE=nginxinc/nginx-unprivileged:stable-alpine@sha256:15c994d10d6d78658721c3bcafff14cb281fba2a4bdf9d5ba92c416a472516e3

FROM ${NODE_IMAGE} AS build
WORKDIR /src/web/frontend
COPY web/frontend/package.json web/frontend/package-lock.json ./
# 설치 스크립트(postinstall 등)는 실행하지 않는다(공급망 방어, S-W11). 빌드가 막히면 해당 패키지와 사유를 기록한 뒤 예외로 허용한다.
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY web/frontend/ ./
RUN npm run build \
 && find dist -name '*.map' -type f -delete \
 && test -f dist/index.html

FROM ${NGINX_IMAGE} AS runtime
COPY --chown=0:0 web/docker/nginx/nginx.conf /etc/nginx/nginx.conf
COPY --chown=0:0 web/docker/nginx/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --chown=0:0 web/docker/nginx/security-headers-api.conf /etc/nginx/snippets/security-headers-api.conf
COPY --chown=0:0 web/docker/nginx/proxy.conf /etc/nginx/snippets/proxy.conf
COPY --from=build --chown=0:0 /src/web/frontend/dist /usr/share/nginx/html
USER 101:101
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=6 \
  CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/nginx-health"]
ENTRYPOINT ["nginx", "-g", "daemon off;"]
