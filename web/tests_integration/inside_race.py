# api 컨테이너 안에서 stdin 으로 실행하는 경합 시험기(IT 그룹 S, IT-301).
# 같은 이미지·같은 PostgreSQL 17 에 연결된 '속도 제한만 풀어 둔' 제2의 uvicorn(127.0.0.1:8001)을 띄우고,
# 응답을 다 받자마자 다음 요청을 곧바로 보내는 연속 호출을 수백 번 반복한다(DEF-VF-B01/VA-010: 응답 후 commit 경합).
# nginx 는 거치지 않는다(속도 제한 때문에 불가능한 반복 횟수이므로). nginx 경유 소량 반복은 IT-300.
import http.client
import json
import os
import sys
import threading
import time

import uvicorn

from ytweb.app import create_app
from ytweb.core.ratelimit import RateLimits

N = int(os.environ.get("RACE_N", "300"))
PORT = 8001
HOST = "127.0.0.1:8080"
ORIGIN = "http://127.0.0.1:8080"

app = create_app(rate_limits=RateLimits(10**9, 10**9, 10**9))
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="critical", access_log=False))
t = threading.Thread(target=server.run, daemon=True)
t.start()
for _ in range(100):
    if server.started:
        break
    time.sleep(0.1)
assert server.started, "서버가 시작되지 않음"


def call(method, path, body=None, cookie=None, csrf=None):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)   # 요청마다 새 연결(브라우저의 병렬 연결과 같은 효과)
    h = {"Host": HOST, "Origin": ORIGIN, "Content-Type": "application/json"}
    if cookie:
        h["Cookie"] = "ytw_session=" + cookie
    if csrf:
        h["X-CSRF-Token"] = csrf
    c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
    r = c.getresponse()
    raw = r.read()
    sc = r.getheader("Set-Cookie")
    c.close()
    try:
        data = json.loads(raw) if raw else None
    except Exception:
        data = None
    return r.status, data, sc


def login():
    st, d, sc = call("POST", "/api/v1/auth/session", {})
    assert st == 200, (st, d)
    return sc.split(";")[0].split("=", 1)[1], d["csrf_token"]


out = {"n": N}
# (a) 세션 발급 직후 첫 요청(조회 + 상태 변경)이 401/403 을 만나지 않는가
bad = []
for i in range(N):
    ck, cs = login()
    st, _, _ = call("GET", "/api/v1/dashboard", cookie=ck)
    st2, d2, _ = call("PATCH", "/api/v1/settings", {"suggestions_per_video": 3}, cookie=ck, csrf=cs)
    if st != 200 or st2 != 200:
        bad.append((i, st, st2))
out["session_then_request_bad"] = bad[:5]
out["session_then_request_bad_count"] = len(bad)

ck, cs = login()
# (b) 작업 생성 직후 조회가 404 를 만나지 않는가(제안 생성 작업)
vids = call("GET", "/api/v1/videos?page_size=50&excluded=false", cookie=ck)[1]["items"]
assert vids, "영상이 없음(먼저 데모 영상을 불러와야 함)"
bad = []
for i in range(N):
    v = vids[i % len(vids)]["video_id"]
    st, d, _ = call("POST", "/api/v1/suggestions/generate", {"video_ids": [v], "count": 1}, cookie=ck, csrf=cs)
    if st != 202:
        bad.append((i, "create", st))
        continue
    st2, _, _ = call("GET", "/api/v1/jobs/" + d["id"], cookie=ck)
    if st2 != 200:
        bad.append((i, "get", st2))
out["job_then_get_bad"] = bad[:5]
out["job_then_get_bad_count"] = len(bad)

# (c) PIN 설정 직후 현재 PIN 없이 변경 시도가 통과(200)하지 않는가(DEF-VF-B01 의 보안 영향)
bad = []
for i in range(N):
    st, d, _ = call("PATCH", "/api/v1/settings", {"pin": {"action": "set", "new_pin": "5151"}}, cookie=ck, csrf=cs)
    if st != 200:
        bad.append((i, "set", st, d and d.get("code")))
        continue
    st2, d2, _ = call("PATCH", "/api/v1/settings", {"pin": {"action": "set", "new_pin": "6262"}}, cookie=ck, csrf=cs)
    if st2 == 200:
        bad.append((i, "CHANGE-WITHOUT-CURRENT-PIN-ACCEPTED", st2))
        # 어쨌든 정리: 현재 PIN 을 모르므로 둘 다 시도
        for p in ("6262", "5151"):
            if call("PATCH", "/api/v1/settings", {"pin": {"action": "clear", "current_pin": p}}, cookie=ck, csrf=cs)[0] == 200:
                break
        continue
    st3, d3, _ = call("PATCH", "/api/v1/settings", {"pin": {"action": "clear", "current_pin": "5151"}}, cookie=ck, csrf=cs)
    if st3 != 200:
        bad.append((i, "clear", st3, d3 and d3.get("code")))
        # 잠금 등으로 막히면 이후 반복이 무의미하므로 중단
        break
out["pin_set_then_change_bad"] = bad[:5]
out["pin_set_then_change_bad_count"] = len(bad)
st, d, _ = call("GET", "/api/v1/settings", cookie=ck)
out["pin_enabled_at_end"] = d and d.get("pin_enabled")
print("RACE_RESULT " + json.dumps(out, ensure_ascii=False))
sys.stdout.flush()
server.should_exit = True
os._exit(0)
