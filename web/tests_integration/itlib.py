"""7단계 전체 스택 통합 시험 공용 도구(실제 컨테이너를 HTTP 로 두드린다).

환경변수(전부 .harness-tmp/int 아래 값만 쓴다):
  IT_PORT       nginx 가 게시된 호스트 포트(기본 18080)
  IT_PROJECT    compose 프로젝트 이름(기본 harness-tmp-int)
  IT_STACK_DIR  compose.yaml·secrets·scripts 사본 폴더(…/stack/web)
  DOCKER_HOST   시험 전용 dockerd 소켓
"""
from __future__ import annotations

import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

PORT = int(os.environ.get("IT_PORT", "18080"))
BASE = f"http://127.0.0.1:{PORT}"
HOST_OK = "127.0.0.1:8080"          # nginx·백엔드 허용 Host(포트 고정 설계, O-VI-09)
ORIGIN_OK = "http://127.0.0.1:8080"
PROJECT = os.environ.get("IT_PROJECT", "harness-tmp-int")
STACK_DIR = Path(os.environ.get("IT_STACK_DIR", "")) if os.environ.get("IT_STACK_DIR") else None
REPO = Path(__file__).resolve().parents[2]
PWSH = os.environ.get("IT_PWSH", "")


def sh(args: list[str], timeout: int = 180, check: bool = False, input_: str | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, input=input_, cwd=str(cwd) if cwd else None)
    if check and p.returncode != 0:
        raise RuntimeError(f"{args[:4]} -> {p.returncode}\n{p.stdout[-800:]}\n{p.stderr[-800:]}")
    return p


def dc(*args: str, timeout: int = 240, input_: str | None = None) -> subprocess.CompletedProcess:
    """docker compose -p <프로젝트> -f <사본 compose> ..."""
    assert STACK_DIR is not None, "IT_STACK_DIR 가 필요합니다"
    env_prefix = ["env", f"YTWEB_IMAGE_PREFIX={PROJECT}"]
    return sh(env_prefix + ["docker", "compose", "-p", PROJECT, "-f", str(STACK_DIR / "compose.yaml"), *args], timeout=timeout, input_=input_)


def cid(service: str) -> str:
    out = dc("ps", "-q", service).stdout.strip().splitlines()
    return out[0] if out else ""


def dexec(service: str, *cmd: str, timeout: int = 120, user: str | None = None) -> subprocess.CompletedProcess:
    a = ["exec", "-T"]
    if user:
        a += ["-u", user]
    return dc(*a, service, *cmd, timeout=timeout)


def psql_app(sql: str, db: str = "ytweb") -> str:
    """db 컨테이너 안에서 앱 계정(ytweb_app)으로 SQL 실행(비밀번호는 컨테이너 파일에서 읽고 출력하지 않는다)."""
    script = f'export PGPASSWORD="$(tr -d \'\\r\\n\' < /run/secrets/db_app_password)"; psql -At -F "|" --no-psqlrc -h 127.0.0.1 -U ytweb_app -d {db} -c "$1"'
    p = dexec("db", "bash", "-c", script, "_", sql)
    if p.returncode != 0:
        raise RuntimeError(p.stderr[-400:])
    return p.stdout.strip()


def psql_owner(sql: str, db: str = "ytweb") -> str:
    script = f'export PGPASSWORD="$(tr -d \'\\r\\n\' < /run/secrets/db_owner_password)"; psql -At -F "|" --no-psqlrc -h 127.0.0.1 -U ytweb_owner -d {db} -c "$1"'
    p = dexec("db", "bash", "-c", script, "_", sql)
    if p.returncode != 0:
        raise RuntimeError(p.stderr[-400:])
    return p.stdout.strip()


def wait_healthy(timeout: int = 180) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = httpx.get(BASE + "/api/readyz", headers={"Host": HOST_OK}, timeout=3)
            if r.status_code == 200 and r.json().get("db") == "ok":
                return
        except Exception:
            pass
        time.sleep(1)
    raise TimeoutError("스택이 준비되지 않았습니다")


def reset_demo_db() -> None:
    """운영 스크립트(reset-demo.ps1 기본 경로)와 같은 순서: web/api/worker 중지 → 스키마 초기화 → up(마이그레이션 재실행)."""
    dc("stop", "web", "api", "worker")
    p = dexec("db", "ytweb-db", "reset-schema")
    assert p.returncode == 0, p.stderr
    u = dc("up", "-d", "--no-build")
    assert u.returncode == 0, u.stderr[-600:]
    wait_healthy()


class Api:
    """세션 쿠키·CSRF·Origin·멱등성 키를 자동으로 붙이는 얇은 HTTP 클라이언트(nginx 경유)."""

    def __init__(self, host: str = HOST_OK, origin: str | None = ORIGIN_OK, timeout: float = 30.0, throttle: float = 0.045):
        self.throttle = throttle  # nginx /api/ 는 초당 30건(버스트 60)이라 순차 호출도 간격을 둔다(0 이면 제한 없이 보냄)
        self._last = 0.0
        self.host = host
        self.origin = origin
        self.c = httpx.Client(base_url=BASE, headers={"Host": host}, timeout=timeout)
        self.csrf: str | None = None

    def close(self) -> None:
        self.c.close()

    def _pace(self) -> None:
        if self.throttle:
            d = self._last + self.throttle - time.monotonic()
            if d > 0:
                time.sleep(d)
            self._last = time.monotonic()

    def _h(self, write: bool, extra: dict | None = None, idem: str | bool | None = None) -> dict:
        h: dict[str, str] = {}
        if self.origin:
            h["Origin"] = self.origin
        if write and self.csrf:
            h["X-CSRF-Token"] = self.csrf
        if idem is True:
            h["Idempotency-Key"] = "it-" + uuid.uuid4().hex[:20]
        elif isinstance(idem, str):
            h["Idempotency-Key"] = idem
        if extra:
            h.update(extra)
        return h

    def login(self, pin: str | None = None, patient: bool = True) -> httpx.Response:
        """세션 발급. patient=True 이면 속도 제한(429)을 만났을 때 Retry-After 만큼 기다렸다 다시 시도한다(시험 사이 한도 공유 때문)."""
        for attempt in range(14):
            self._pace()
            r = self.c.post("/api/v1/auth/session", json=({"pin": pin} if pin else {}), headers=self._h(False))
            if r.status_code == 429 and patient and attempt < 13:
                code = ""
                try:
                    code = r.json().get("code", "")
                except Exception:
                    pass
                if code == "pin_locked":
                    return r
                time.sleep(min(float(r.headers.get("retry-after", "6") or 6), 30) + 0.5)
                continue
            if r.status_code == 200:
                self.csrf = r.json()["csrf_token"]
            return r
        return r

    def get(self, path: str, **kw: Any) -> httpx.Response:
        self._pace()
        return self.c.get(path, headers=self._h(False, kw.pop("headers", None)), **kw)

    def post(self, path: str, json: Any = None, idem: str | bool | None = None, headers: dict | None = None, **kw: Any) -> httpx.Response:
        self._pace()
        return self.c.post(path, json=json, headers=self._h(True, headers, idem), **kw)

    def patch(self, path: str, json: Any = None, headers: dict | None = None) -> httpx.Response:
        self._pace()
        return self.c.patch(path, json=json, headers=self._h(True, headers))

    def delete(self, path: str, headers: dict | None = None) -> httpx.Response:
        self._pace()
        return self.c.delete(path, headers=self._h(True, headers))

    # --- 업무 도우미 ---
    def wait_job(self, job_id: str, timeout: float = 60.0) -> dict:
        t0 = time.time()
        while time.time() - t0 < timeout:
            r = self.get(f"/api/v1/jobs/{job_id}")
            assert r.status_code == 200, (r.status_code, r.text[:300])
            j = r.json()
            if j["status"] in ("succeeded", "failed", "cancelled"):
                return j
            time.sleep(0.4)
        raise TimeoutError(f"job {job_id} 미종료")

    def sync_demo(self) -> dict:
        r = self.post("/api/v1/videos/sync")
        assert r.status_code == 202, r.text[:300]
        return self.wait_job(r.json()["id"])

    def videos(self, **params: Any) -> list[dict]:
        out: list[dict] = []
        page = 1
        while True:
            r = self.get("/api/v1/videos", params={"page": page, "page_size": 200, **params})
            assert r.status_code == 200, r.text[:300]
            d = r.json()
            out += d["items"]
            if len(out) >= d["total"]:
                return out
            page += 1

    def make_suggestion(self, video_id: str, count: int = 1) -> list[dict]:
        r = self.post(f"/api/v1/videos/{video_id}/suggestions", json={"count": count})
        assert r.status_code == 201, (r.status_code, r.text[:300])
        return r.json()

    def approve(self, sid: int, who: str = "통합시험자") -> httpx.Response:
        return self.post(f"/api/v1/suggestions/{sid}/approve", json={"approver": who})

    def make_batch(self, sids: list[int], note: str = "it") -> httpx.Response:
        return self.post("/api/v1/batches", json={"suggestion_ids": sids, "note": note}, idem=True)

    def execute(self, batch_id: int, n: int, idem: str | bool = True) -> httpx.Response:
        return self.post(f"/api/v1/batches/{batch_id}/execute", json={"confirm_text": f"실행 {n}건"}, idem=idem)

    def wait_batch(self, batch_id: int, statuses: tuple = ("done", "cancelled"), timeout: float = 90.0) -> dict:
        t0 = time.time()
        while time.time() - t0 < timeout:
            r = self.get(f"/api/v1/batches/{batch_id}")
            assert r.status_code == 200, r.text[:300]
            b = r.json()
            if b["status"] in statuses:
                return b
            time.sleep(0.5)
        raise TimeoutError(f"batch {batch_id} 미종료: {b['status']} {b['counts']}")


def usable_videos(api: Api, n: int, want_pass: bool = True) -> list[dict]:
    """제외되지 않은 영상 n개."""
    vs = [v for v in api.videos() if not v["excluded"]]
    assert len(vs) >= n, f"사용 가능 영상 {len(vs)}개"
    return vs[:n]


def approved_suggestion(api: Api, video_id: str, who: str = "통합시험자") -> dict:
    """제안을 만들고 차단이 아닌 것을 골라 승인한다(경고는 화면 체크 후 승인에 해당)."""
    for s in api.make_suggestion(video_id, 5):
        if s["validation_result"] != "block" and not (s["strict"] and s["validation_result"] != "pass") and s["status"] in ("candidate", "expired"):
            r = api.approve(s["id"], who)
            if r.status_code == 200:
                return r.json()
    raise AssertionError(f"{video_id}: 승인 가능한 제안이 없음")


SECRET_RE = re.compile(r"[0-9a-f]{64}")


def raw_request(data: bytes, timeout: float = 6.0, port: int = PORT) -> bytes:
    """소켓으로 원문 HTTP 요청을 보내고 응답 전체(또는 연결 종료까지)를 돌려준다. 빈 bytes 는 '응답 없이 연결 종료'(nginx 444)."""
    import socket

    s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    try:
        s.sendall(data)
        chunks = []
        while True:
            try:
                b = s.recv(65536)
            except (TimeoutError, socket.timeout):
                break
            if not b:
                break
            chunks.append(b)
        return b"".join(chunks)
    finally:
        s.close()


def parse_raw(resp: bytes) -> tuple[int, dict[str, list[str]], bytes]:
    if not resp:
        return 0, {}, b""
    head, _, body = resp.partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    status = int(lines[0].split()[1])
    hdrs: dict[str, list[str]] = {}
    for ln in lines[1:]:
        k, _, v = ln.partition(":")
        hdrs.setdefault(k.strip().lower(), []).append(v.strip())
    return status, hdrs, body


def inside_api_python(script: str, timeout: int = 600, service: str = "api") -> subprocess.CompletedProcess:
    """api 컨테이너 안(같은 이미지·같은 DB)에서 파이썬 스크립트를 stdin 으로 실행한다(이미지 읽기 전용 루트에 파일을 쓰지 않는다)."""
    return dc("exec", "-T", service, "python", "-", timeout=timeout, input_=script)


def forge_approval_expiry(suggestion_id: int, hours_back: float = 25.0, expires_in_seconds: float | None = None) -> None:
    """'24시간이 지났다'를 시늉한다: 승인의 expires_at 을 과거로 옮기고, 제품 자신의 compute_mac 으로 서명을 다시 계산해 넣는다
    (서명이 어긋나면 만료가 아니라 변조로 판정되므로). api 컨테이너 안에서 앱 계정(ytweb_app, approvals UPDATE 권한 있음)으로 실행."""
    script = f'''
from datetime import timedelta
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
    from datetime import datetime, timezone
    ap.expires_at = (datetime.now(timezone.utc) + timedelta(seconds={expires_in_seconds})) if {expires_in_seconds!r} is not None else ap.expires_at - timedelta(hours={hours_back})
    ap.mac = compute_mac(key, suggestion_id=sug.id, video_id=sug.video_id, plan_hash=ap.plan_hash, approver=ap.approver, approved_at=ap.approved_at, expires_at=ap.expires_at)
    s.commit()
print("forged")
'''
    p = inside_api_python(script)
    assert p.returncode == 0 and "forged" in p.stdout, p.stderr[-600:]


def worker_stop() -> None:
    p = dc("stop", "-t", "30", "worker")
    assert p.returncode == 0, p.stderr


def worker_start() -> None:
    p = dc("start", "worker")
    assert p.returncode == 0, p.stderr
    t0 = time.time()
    while time.time() - t0 < 60:
        out = sh(["docker", "inspect", "-f", "{{.State.Running}}", cid("worker")]).stdout.strip()
        if out == "true":
            return
        time.sleep(1)
    raise TimeoutError("worker 시작 실패")


def set_cap(api: "Api", n: int) -> None:
    r = api.patch("/api/v1/settings", json={"daily_apply_cap": n})
    assert r.status_code == 200, r.text


def approve_many(api: "Api", videos: list[dict], who: str = "통합시험자") -> list[dict]:
    return [approved_suggestion(api, v["video_id"], who) for v in videos]


def shift_days(days: int = 1) -> None:
    """'하루가 지났다'를 시늉한다: 반영 예약일·변경 시각을 하루 앞으로 당긴다(DB 직접 수정, 소유자 계정). 시계를 바꿀 수 없는 컨테이너 환경의 대체 수단."""
    psql_owner(
        f"update batch_items set scheduled_date = scheduled_date - {days} where status='pending' and scheduled_date is not null; "
        f"update changes set applied_at = applied_at - interval '{days} day', created_at = created_at - interval '{days} day' where applied_at is not null; "
        f"update quota_usage set pt_date = pt_date - {days}"
    )


def two_pass_suggestions(api: "Api", vids: list[dict], n: int = 2) -> list[dict]:
    """같은 영상에서 '통과'(비엄격) 제안이 n개 이상 나오는 영상을 찾아 그 제안들을 돌려준다(모의 제안기는 영상마다 결과가 정해져 있다)."""
    for v in vids:
        got = [x for x in api.make_suggestion(v["video_id"], 5) if x["validation_result"] == "pass" and not x["strict"]]
        if len(got) >= n:
            return got[:n]
    raise AssertionError("통과 제안이 %d개 이상인 영상을 찾지 못함" % n)


def ps(script: str, *args: str, timeout: int = 900) -> subprocess.CompletedProcess:
    """운영 PowerShell 스크립트(사본 폴더의 원본 스크립트)를 pwsh 7 로 실행한다. 프로젝트·이미지 접두사는 환경변수로 시험용에 맞춘다."""
    assert PWSH and Path(PWSH).exists(), "IT_PWSH(pwsh 7 실행 파일)가 필요합니다"
    env = {**os.environ, "YTWEB_PROJECT": PROJECT, "YTWEB_IMAGE_PREFIX": PROJECT}
    return subprocess.run([PWSH, "-NoProfile", "-File", str(STACK_DIR / "scripts" / script), *args], env=env, capture_output=True, text=True, timeout=timeout)


def secret_values() -> dict[str, str]:
    return {n: (STACK_DIR / "secrets" / n).read_text().strip() for n in ("db_superuser_password", "db_owner_password", "db_app_password")}


def counts() -> dict[str, int]:
    out = dc("exec", "-T", "db", "ytweb-db", "counts").stdout.strip().splitlines()
    return {ln.split()[0]: int(ln.split()[1]) for ln in out if ln.strip()}
