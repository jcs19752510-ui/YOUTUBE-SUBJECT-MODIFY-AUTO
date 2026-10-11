"""SEC-06 실스택에서 재현되는 알려진 한계 2건(결함을 '재현'하는 시험: 통과하는 동안 한계가 존재한다).

- DEF-9-016(TW-17, S-W08/09): nginx 오류 로그가 요청 줄(쿼리 문자열 포함)을 남긴다. 접근 로그에는 쿼리가 없다.
  M2 에서 OAuth 콜백(?code=&state=)이 생기면 인가 코드가 로그에 남는다 → M2 전 필수 해소.
- DEF-9-011(TW-36, D-10): web(nginx) 컨테이너는 비-internal edge 망의 호스트 게이트웨이를 통해 호스트의 0.0.0.0 서비스에 도달한다.
  이번 재측정에서 internal 망(back)에만 있는 api·worker·db 도 자기 망 게이트웨이 주소로 호스트의 0.0.0.0 서비스에 도달함을 확인(범위 확대, Linux 엔진).
  127.0.0.1 에만 바인딩된 서비스에는 도달하지 못한다(대조군은 test_sec_04 의 포트 검사).
  (시험은 이 프로세스가 0.0.0.0 의 임의 포트를 열고, web 컨테이너 안에서 edge 게이트웨이:그 포트로 연결이 되는지 본다. 외부 인터넷에는 아무것도 보내지 않는다.)

이 파일은 api 컨테이너를 잠시 멈췄다 되살린다(맨 마지막에 실행되도록 파일 이름을 06 으로 둠). YTWEB_SEC_LIVE_PORT 가 있을 때만 돈다.
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import threading
import time
import uuid

import pytest

PORT = os.environ.get("YTWEB_SEC_LIVE_PORT")
PROJECT = os.environ.get("YTWEB_SEC_PROJECT", "harness-tmp-sec")
pytestmark = [pytest.mark.skipif(not PORT, reason="YTWEB_SEC_LIVE_PORT 가 없어 실스택 시험을 건너뜀"), pytest.mark.filterwarnings("ignore")]


def docker(*args: str, timeout=60) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


def test_nginx_error_log_keeps_query_string_on_upstream_error_repro():
    canary = "CANARY" + uuid.uuid4().hex[:12]
    api = f"{PROJECT}-api-1"
    web = f"{PROJECT}-web-1"
    docker("stop", api)
    try:
        time.sleep(1)
        c = http.client.HTTPConnection("127.0.0.1", int(PORT), timeout=10)
        c.request("GET", f"/api/v1/videos?q=abc&code={canary}", headers={"Host": "127.0.0.1:8080"})
        assert c.getresponse().status in (502, 503, 504)
        time.sleep(1)
        logs = docker("logs", web).stdout + docker("logs", web).stderr
    finally:
        docker("start", api)
        for _ in range(60):
            h = docker("inspect", api, "--format", "{{.State.Health.Status}}").stdout.strip()
            if h == "healthy":
                break
            time.sleep(1)
    lines = [l for l in logs.splitlines() if canary in l]
    err_lines = [l for l in lines if "[error]" in l]
    access_lines = [l for l in lines if "[error]" not in l]
    assert err_lines, "오류 로그에 요청 줄이 남지 않는다면 DEF-9-016 이 해소된 것이다 → 이 시험의 기대를 뒤집는다"
    assert not access_lines, "접근 로그에는 쿼리 문자열이 없어야 한다(설계)"


def test_web_container_reaches_host_gateway_listener_repro():
    srv = socket.socket()
    srv.bind(("0.0.0.0", 0))
    srv.listen(5)
    port = srv.getsockname()[1]
    stop = threading.Event()

    def accept_loop():
        srv.settimeout(0.5)
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
                conn.close()
            except OSError:
                pass

    t = threading.Thread(target=accept_loop, daemon=True)
    t.start()
    try:
        gw = json.loads(docker("network", "inspect", f"{PROJECT}_edge").stdout)[0]["IPAM"]["Config"][0]["Gateway"]
        r = docker("exec", f"{PROJECT}-web-1", "sh", "-c", f"nc -z -w 3 {gw} {port} && echo OPEN || echo CLOSED")
        opened = "OPEN" in r.stdout
        # 범위 확대 확인: internal 망(back)에만 있는 api 도 자기 망의 게이트웨이(=호스트 쪽 브리지 주소)로 호스트의 0.0.0.0 서비스에 도달한다(Linux 엔진 실측).
        gw_back = json.loads(docker("network", "inspect", f"{PROJECT}_back").stdout)[0]["IPAM"]["Config"][0]["Gateway"]
        r2 = docker("exec", f"{PROJECT}-api-1", "python", "-c",
                    f"import socket;s=socket.socket();s.settimeout(3)\ntry:\n s.connect(('{gw_back}',{port}));print('OPEN')\nexcept Exception:\n print('CLOSED')")
        api_open = "OPEN" in r2.stdout
    finally:
        stop.set()
        srv.close()
    assert opened, "web→호스트 게이트웨이 연결이 막혔다면 DEF-9-011 이 해소된 것이다 → 이 시험의 기대를 뒤집는다"
    assert api_open, "internal 망의 api 가 호스트 게이트웨이에 도달하지 못한다면 범위 확대 사실이 바뀐 것이다 → 기대를 뒤집는다"


def test_api_image_has_no_dev_cache_directories():
    r = docker("run", "--rm", "--entrypoint", "sh", f"{PROJECT}-api:local", "-c",
               "find /app -name .ruff_cache -o -name .mypy_cache -o -name .pytest_cache -o -name .coverage -o -name '*.egg-info' | head")
    assert r.stdout.strip() == "", r.stdout
