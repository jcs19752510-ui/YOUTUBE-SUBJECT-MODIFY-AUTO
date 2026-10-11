"""7단계 통합 시험 B 트랙(시나리오·경합·계약) 공용 도구. A 트랙의 itlib.py 를 수정하지 않고 위에 얹는다.

두 가지 환경에서 같은 시험이 돈다.
  네이티브(IT_B_NATIVE=1): 임시 PostgreSQL 16 + uvicorn + 워커(itlib_b_native.py). 도커 없음. 기본 베이스 포트 18090.
  도커 스택(IT_B_NATIVE 없음): A 트랙의 nginx 스택(IT_PORT=18080, IT_STACK_DIR, DOCKER_HOST) — 같은 함수 이름이 itlib 의 도커 구현으로 연결된다.
IT_B_RELAXED=1(네이티브 기본)이면 백엔드 속도 제한을 풀어 둔 서버라서 반복·동시 시험이 빠르다. 제한 자체의 동작은 --strict 스택과 A 트랙(nginx)이 본다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

NATIVE = os.environ.get("IT_B_NATIVE") == "1"
if NATIVE:
    os.environ.setdefault("IT_PORT", os.environ.get("IT_B_API_PORT", "18090"))
RELAXED = NATIVE and os.environ.get("IT_B_RELAXED", "1") == "1"

import itlib  # noqa: E402  (IT_PORT 를 먼저 정해야 한다)
import pytest  # noqa: E402
from itlib import (  # noqa: E402,F401
    BASE, HOST_OK, ORIGIN_OK, REPO, approve_many, approved_suggestion, set_cap, two_pass_suggestions, usable_videos, wait_healthy,
)

if NATIVE:
    import itlib_b_native as nat  # noqa: E402


# ───────────── HTTP 클라이언트 ─────────────

OBSERVED: list[tuple[str, str, int, str, dict | None]] = []   # (method, path, status, code, body) — 세션 전체 기록(TC-IT-421 이 문서와 대조)


ACTIONS_SEEN: dict[str, int] = {}                              # 세션 동안 감사 로그 조회에서 본 action 별 횟수(TC-IT-421 이 문서와 대조)


def _record(method: str, path: str, r) -> None:
    code, body = "", None
    if r.status_code == 200 and path.startswith("/api/v1/audit"):
        try:
            for it in r.json().get("items", []):
                ACTIONS_SEEN[it["action"]] = ACTIONS_SEEN.get(it["action"], 0) + 1
        except Exception:
            pass
    if r.status_code >= 400:
        try:
            body = r.json()
            code = body.get("code", "") if isinstance(body, dict) else ""
        except Exception:
            body = None
    OBSERVED.append((method, path.split("?")[0], r.status_code, code, body))


class Api(itlib.Api):
    """itlib.Api + 429(rate_limited) 자동 재시도(요청이 핸들러에 닿기 전에 거부되므로 재전송이 안전하다). retry429=False 로 끌 수 있다."""

    def __init__(self, *a, retry429: bool = True, throttle: float | None = None, **kw):
        super().__init__(*a, throttle=(0.0 if RELAXED else 0.11) if throttle is None else throttle, **kw)
        self.retry429 = retry429

    def _retry(self, fn):
        for _ in range(10):
            r = fn()
            if r.status_code == 429 and self.retry429:
                try:
                    code = r.json().get("code", "")
                except Exception:
                    code = ""
                if code == "rate_limited":
                    time.sleep(min(float(r.headers.get("retry-after", "3") or 3), 20) + 0.3)
                    continue
            return r
        return r

    def get(self, path, **kw):
        r = self._retry(lambda: super(Api, self).get(path, **dict(kw)))
        _record("GET", path, r)
        return r

    def post(self, path, json=None, idem=None, headers=None, **kw):
        if idem is True:
            idem = "it-" + os.urandom(10).hex()
        r = self._retry(lambda: super(Api, self).post(path, json=json, idem=idem, headers=headers, **kw))
        _record("POST", path, r)
        return r

    def patch(self, path, json=None, headers=None):
        r = self._retry(lambda: super(Api, self).patch(path, json=json, headers=headers))
        _record("PATCH", path, r)
        return r

    def delete(self, path, headers=None):
        r = self._retry(lambda: super(Api, self).delete(path, headers=headers))
        _record("DELETE", path, r)
        return r


def clone_api(a: Api, throttle: float = 0.0) -> Api:
    """같은 세션(쿠키·CSRF)을 쓰는 또 하나의 클라이언트 — 브라우저의 병렬 연결 시늉."""
    c = Api(throttle=throttle, retry429=False)
    c.c.cookies.set("ytw_session", a.c.cookies.get("ytw_session"), domain="127.0.0.1", path="/api")
    c.csrf = a.csrf
    return c


def run_threads(n: int, fn) -> list:
    """fn(i) 를 n 개 스레드에서 동시에 시작(장벽 사용)하고 결과 목록을 돌려준다. 예외도 결과에 담는다."""
    out: list = [None] * n
    bar = threading.Barrier(n)

    def go(i: int):
        try:
            bar.wait(timeout=30)
            out[i] = fn(i)
        except Exception as e:  # noqa: BLE001
            out[i] = e
    ts = [threading.Thread(target=go, args=(i,)) for i in range(n)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    return out


# ───────────── DB ─────────────

def _fmt(v) -> str:
    if v is None:
        return ""
    if v is True:
        return "t"
    if v is False:
        return "f"
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def _rows_to_text(rows: list[tuple]) -> str:
    return "\n".join("|".join(_fmt(x) for x in r) for r in rows)


def psql_app(sql: str) -> str:
    if NATIVE:
        return _rows_to_text(nat.sql(sql, "app"))
    return itlib.psql_app(sql)


def psql_owner(sql: str) -> str:
    if NATIVE:
        return _rows_to_text(nat.sql(sql, "owner"))
    return itlib.psql_owner(sql)


def shift_days(days: int = 1) -> None:
    """'하루가 지났다'를 시늉한다(DB 직접 수정): 반영 예약일·변경 시각·쿼터 날짜를 하루 앞으로 당긴다."""
    psql_owner(
        f"update batch_items set scheduled_date = scheduled_date - {days} where status='pending' and scheduled_date is not null; "
        f"update changes set applied_at = applied_at - interval '{days} day', created_at = created_at - interval '{days} day' where applied_at is not null; "
        f"update quota_usage set pt_date = pt_date - {days}"
    )


def shift_hours(hours: float) -> None:
    """변경 시각만 앞으로 당긴다(72시간 간격 한도 시험용). 예약일·쿼터는 그대로."""
    psql_owner(f"update changes set applied_at = applied_at - interval '{hours} hour', created_at = created_at - interval '{hours} hour' where applied_at is not null")


def counts() -> dict[str, int]:
    rows = psql_owner(
        "select table_name, (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I.%I', table_schema, table_name), false, true, '')))[1]::text "
        "from information_schema.tables where table_schema='public' and table_type='BASE TABLE' order by 1"
    ).splitlines()
    return {r.split("|")[0]: int(r.split("|")[1]) for r in rows}


# ───────────── 프로세스 제어 ─────────────

def worker_stop() -> None:
    if NATIVE:
        nat.proc_stop("worker")
        return
    itlib.worker_stop()


def worker_start() -> None:
    if NATIVE:
        nat.worker_start()
        t0 = time.time()
        while time.time() - t0 < 30:  # 기동 직후 복구 루틴이 도는 동안 잠깐 기다린다
            if nat.proc_alive("worker"):
                time.sleep(0.5)
                return
            time.sleep(0.2)
        raise TimeoutError("worker 시작 실패")
    itlib.worker_start()


def worker_kill_and_restart() -> None:
    """워커를 SIGKILL 로 죽이고 곧바로 다시 띄운다(비정상 종료 시늉)."""
    if NATIVE:
        import signal
        nat.proc_stop("worker", sig=signal.SIGKILL)
        nat.worker_start()
        return
    wid = itlib.cid("worker")
    itlib.sh(["docker", "kill", "-s", "KILL", wid])
    time.sleep(0.5)
    if itlib.sh(["docker", "inspect", "-f", "{{.State.Running}}", wid]).stdout.strip() != "true":
        itlib.sh(["docker", "start", wid])


def api_restart() -> None:
    if NATIVE:
        nat.proc_stop("api")
        nat.api_start(RELAXED)
        nat.wait_api()
        return
    itlib.dc("restart", "api")
    wait_healthy(120)


def db_stop() -> None:
    if NATIVE:
        nat.pg_stop("fast")
        return
    itlib.sh(["docker", "stop", "-t", "10", itlib.cid("db")])


def db_start() -> bool:
    """DB 를 다시 띄우고 api 가 준비될 때까지 기다린다. 돌려주는 값: 그 사이 워커가 죽어 있어서 다시 띄웠는가.
    (네이티브에는 compose 의 `restart: unless-stopped` 가 없으므로, 죽은 워커를 같은 정책으로 다시 띄운다 — 도커에서는 컨테이너 재시작 정책이 한다.)"""
    if NATIVE:
        nat.pg_start()
        wait_healthy(180)
        died = not nat.proc_alive("worker")
        if died:
            nat.proc_stop("worker")
            nat.worker_start()
        return died
    itlib.sh(["docker", "start", itlib.cid("db")])
    wait_healthy(180)
    return False


def db_kill9_and_start() -> bool:
    """DB 서버를 SIGKILL(비정상 종료) 후 다시 띄운다(충돌 복구 포함). 네이티브 전용."""
    assert NATIVE
    nat.pg_kill9()
    return db_start()


def run_extra_workers(n: int, seconds: float) -> None:
    """정식 워커 외에 워커 n 개를 더 띄워 seconds 초 동안 같은 DB 를 처리하게 한다(여러 워커 경합 시험)."""
    if NATIVE:
        names = [f"worker_x{i}" for i in range(n)]
        for nm in names:
            nat.worker_start(nm)
        time.sleep(seconds)
        for nm in names:
            nat.proc_stop(nm)
        return
    script = (
        "import subprocess, sys, time\n"
        f"ps = [subprocess.Popen([sys.executable, '-m', 'ytweb.worker'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for _ in range({n})]\n"
        f"time.sleep({seconds})\n"
        "for p in ps: p.terminate()\n"
        "for p in ps: p.wait(timeout=30)\n"
        "print('done')\n"
    )
    p = itlib.inside_api_python(script, timeout=int(seconds) + 120)
    assert "done" in p.stdout, p.stderr[-400:]


def restart_cycles() -> list:
    """(이름, 실행 함수) 목록: 데이터가 남는 재시작 방식들. 실행 후 스택이 정상이 될 때까지 기다린다."""
    out: list = []
    if NATIVE:
        def graceful():
            nat.proc_stop("worker"); nat.proc_stop("api"); nat.pg_stop("fast")
            nat.pg_start(); nat.api_start(RELAXED); nat.worker_start(); nat.wait_api()

        def kill_all():
            import signal
            nat.proc_stop("worker", sig=signal.SIGKILL); nat.proc_stop("api", sig=signal.SIGKILL)
            nat.pg_kill9(); nat.pg_start(); nat.api_start(RELAXED); nat.worker_start(); nat.wait_api()
        out += [("graceful-stop-start", graceful), ("kill-9-all", kill_all)]
    else:
        out += [("compose-restart", lambda: itlib.dc("restart", timeout=300)),
                ("down-up", lambda: (itlib.dc("down", timeout=300), itlib.dc("up", "-d", "--no-build", timeout=300))),
                ("force-recreate", lambda: itlib.dc("up", "-d", "--no-build", "--force-recreate", "api", "worker", "web", timeout=300))]
    return out


def reset_demo_db() -> None:
    if NATIVE:
        nat.reset_demo(RELAXED)
        return
    itlib.reset_demo_db()


def server_logs() -> str:
    """api·worker(+db) 로그 전체(비밀 노출 점검용)."""
    if NATIVE:
        return "\n".join((nat.LOGS / f"{n}.log").read_text(errors="replace") for n in ("api", "worker", "pg") if (nat.LOGS / f"{n}.log").exists())
    return "\n".join(itlib.dc("logs", "--no-log-prefix", s).stdout for s in ("api", "worker", "db"))


def inside_python(script: str, timeout: int = 600) -> subprocess.CompletedProcess:
    """서버와 같은 코드·같은 DB 환경에서 파이썬 스크립트를 stdin 으로 실행한다(네이티브: venv 파이썬, 도커: api 컨테이너)."""
    if NATIVE:
        return subprocess.run([nat.VENV_PY, "-"], input=script, text=True, capture_output=True, timeout=timeout, env=nat.app_env(), cwd=str(nat.BACKEND))
    return itlib.inside_api_python(script, timeout=timeout)


def forge_approval_expiry(suggestion_id: int, hours_back: float = 25.0, expires_in_seconds: float | None = None) -> None:
    """승인 expires_at 을 옮기고 제품 자신의 compute_mac 으로 서명을 다시 계산한다(서명이 어긋나면 만료가 아니라 변조로 판정되므로)."""
    script = f'''
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from ytweb.config import load_web_settings
from ytweb.db.session import make_engine, make_session_factory
from ytweb.db.models import Approval, Suggestion
from ytweb.domain.suggestions import _load_key, compute_mac
st = load_web_settings(); eng = make_engine(st.database_url); f = make_session_factory(eng)
with f() as s:
    ap = s.execute(select(Approval).where(Approval.suggestion_id == {suggestion_id})).scalar_one()
    sug = s.get(Suggestion, {suggestion_id})
    key = _load_key(st.secrets_dir, create=False)
    ap.expires_at = (datetime.now(timezone.utc) + timedelta(seconds={expires_in_seconds})) if {expires_in_seconds!r} is not None else ap.expires_at - timedelta(hours={hours_back})
    ap.mac = compute_mac(key, suggestion_id=sug.id, video_id=sug.video_id, plan_hash=ap.plan_hash, approver=ap.approver, approved_at=ap.approved_at, expires_at=ap.expires_at)
    s.commit()
print("forged")
'''
    p = inside_python(script)
    assert p.returncode == 0 and "forged" in p.stdout, p.stderr[-600:]


def approval_key_sha() -> str:
    import hashlib
    if NATIVE:
        return hashlib.sha256((nat.APP_SECRETS / "approval_hmac.key").read_bytes()).hexdigest()
    return itlib.dc("exec", "-T", "api", "sha256sum", "/var/lib/ytweb/secrets/approval_hmac.key").stdout.split()[0]


# ───────────── 업무 도우미 ─────────────

def strict_window_clear() -> None:
    """세션 발급 분당 10회 제한(전역)이 걸린 환경이면 최근 1분의 발급 기록이 지워지도록 기다린다(제한을 푼 서버는 즉시 반환)."""
    if not RELAXED:
        time.sleep(62)


def count_success_per_video_max() -> str:
    return psql_app("select coalesce(max(c),0) from (select count(*) c from changes where change_type='apply' and result='success' group by video_id) t")


def video_titles(a: Api) -> dict[str, str]:
    return {v["video_id"]: v["title"] for v in a.videos()}


def wait_until(pred, timeout: float = 60.0, step: float = 0.4, what: str = "조건"):
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        last = pred()
        if last:
            return last
        time.sleep(step)
    raise TimeoutError(f"{what} 미충족 ({timeout}s)")


def approvable_set(a: Api, vids: list[dict], k: int = 3) -> tuple[dict, list[dict]]:
    """같은 영상에서 차단·엄격이 아닌(승인 가능한) 제안이 k개 이상 나오는 영상과 그 제안들(승인 전)."""
    for v in vids:
        got = [x for x in a.make_suggestion(v["video_id"], 5) if x["validation_result"] != "block" and not x["strict"] and x["status"] in ("candidate", "expired")]
        if len(got) >= k:
            return v, got[:k]
    raise AssertionError(f"승인 가능한 제안이 {k}개 이상인 영상을 찾지 못함")


def apply_via_batch(a: Api, sug_id: int, who: str = "통합시험자", timeout: float = 90.0) -> dict:
    """승인된 제안 1건을 배치로 만들어 실행하고 끝날 때까지 기다린 뒤 그 변경 이력을 돌려준다."""
    r = a.make_batch([sug_id])
    assert r.status_code == 201, r.text[:300]
    bid = r.json()["batch"]["id"]
    assert a.execute(bid, 1).status_code == 202
    b = a.wait_batch(bid, timeout=timeout)
    assert b["counts"]["success"] == 1, b
    return a.get("/api/v1/changes", params={"batch_id": bid}).json()["items"][0]


def rollback(a: Api, change: dict, who: str = "복구자", idem=True):
    return a.post(f"/api/v1/changes/{change['id']}/rollback", json={"typed_video_id": change["video_id"], "approver": who}, idem=idem)


def mark_video_title(video_id: str, title: str) -> None:
    """모의 유튜브(videos 표)의 제목을 바꾼다 — 사용자가 Studio 에서 직접 바꾼 상황 시늉(소유자 계정)."""
    t = title.replace("'", "''")
    psql_owner(f"update videos set title='{t}', snippet=jsonb_set(snippet,'{{title}}',to_jsonb('{t}'::text)) where video_id='{video_id}'")


# ───────────── 픽스처 ─────────────

_CACHE: dict = {}


@pytest.fixture()
def fresh_demo():
    """빈 DB → 로그인 → 데모 영상 불러오기까지 끝낸 클라이언트(운영 reset-demo 경로: web/api/worker 정지 → 스키마 초기화 → 기동)."""
    reset_demo_db()
    a = Api()
    assert a.login().status_code == 200
    j = a.sync_demo()
    assert j["status"] == "succeeded"
    yield a
    a.close()
