# syntax=docker/dockerfile:1
# 공식 PostgreSQL 이미지 + 역할 초기화/관리 스크립트(바인드 마운트 없이 이미지에 포함, Windows 줄바꿈 문제 방지).
# 메이저 17: 지원 ~2029-11(01-axisB 3-1), 볼륨 경로가 /var/lib/postgresql/data 로 안정적. 갱신: web/scripts/pin-digests.ps1
ARG POSTGRES_IMAGE=postgres:17-bookworm@sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826

FROM ${POSTGRES_IMAGE}
COPY --chmod=0755 web/docker/db/init/01-roles.sh /docker-entrypoint-initdb.d/01-roles.sh
COPY --chmod=0644 web/docker/db/schema-grants.sql /usr/local/share/ytweb/schema-grants.sql
COPY --chmod=0644 web/docker/db/audit-guard.sql /usr/local/share/ytweb/audit-guard.sql
COPY --chmod=0755 web/docker/db/bin/ytweb-db /usr/local/bin/ytweb-db
COPY --chmod=0644 web/docker/db/pg_hba.conf /etc/postgresql/pg_hba.conf
RUN sed -i 's/\r$//' /docker-entrypoint-initdb.d/01-roles.sh /usr/local/bin/ytweb-db /usr/local/share/ytweb/*.sql /etc/postgresql/pg_hba.conf \
 && chmod 0755 /usr/local/share/ytweb \
 && install -d -o 999 -g 999 -m 0700 /backups
USER 999:999
