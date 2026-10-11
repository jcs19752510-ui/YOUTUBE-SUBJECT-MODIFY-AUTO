"""7단계 통합 시험 B 트랙: 도커 없는 '네이티브 스택'(임시 PostgreSQL 16 + uvicorn api + 워커)을 만들고 제어한다.

모든 임시 파일은 .harness-tmp/int_b/ 아래(규칙 K). 사용:
  python itlib_b_native.py up [--strict]   # PG 초기화/기동 → 역할·스키마 권한 → 마이그레이션 → api·워커 기동 (기본: 속도 제한 해제 서버, --strict 면 제품 기본 제한)
  python itlib_b_native.py down            # api·워커·PG 중지(데이터 유지)
  python itlib_b_native.py destroy         # 중지 + 데이터 폴더 삭제
  python itlib_b_native.py status

환경변수: IT_B_ROOT(기본 <저장소>/.harness-tmp/int_b), IT_B_BACKEND(기본 <저장소>/web/backend; 변이 사본 경로를 줄 수 있음),
IT_B_SRC(기본 <저장소>/src), IT_B_API_PORT(기본 18090), IT_B_PG_PORT(기본 54341).
이 모듈은 도커를 쓰지 않는다. pkill/killall 을 쓰지 않고 자기가 띄운 PID 만 종료한다.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = Path(os.environ.get("IT_B_ROOT", str(REPO / ".harness-tmp" / "int_b")))
BACKEND = Path(os.environ.get("IT_B_BACKEND", str(REPO / "web" / "backend")))
SRC = Path(os.environ.get("IT_B_SRC", str(REPO / "src")))
API_PORT = int(os.environ.get("IT_B_API_PORT", "18090"))
PG_PORT = int(os.environ.get("IT_B_PG_PORT", "54341"))
PGBIN = Path("/usr/lib/postgresql/16/bin")
PGDATA = ROOT / "pg"
PGSOCK = ROOT / "pgsock"
SECRETS = ROOT / "secrets"            # DB 비밀번호(시험 전용, 임의 생성)
APP_SECRETS = ROOT / "app_secrets"    # 앱 승인 서명 키 폴더(YTWEB_SECRETS_DIR)
LOGS = ROOT / "logs"
PIDS = ROOT / "pids.json"
HERE = Path(__file__).resolve().parent
VENV_PY = os.environ.get("IT_B_PYTHON", str(ROOT / "venv" / "bin" / "python"))
DB = "ytweb"


# ───────────── 공통 ─────────────

def _priv_postgres(cmd: list[str]) -> list[str]:
    if os.geteuid() == 0:
        return ["setpriv", "--reuid=postgres", "--regid=postgres", "--init-groups", *cmd]
    return cmd


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def _secret(name: str) -> str:
    return (SECRETS / name).read_text().strip()


def db_url(role: str = "app", host: str = "127.0.0.1", driver: str = "postgresql+psycopg") -> str:
    user, pw = {"app": ("ytweb_app", _secret("db_app_password")), "owner": ("ytweb_owner", _secret("db_owner_password")),
                "super": ("postgres", _secret("db_superuser_password"))}[role]
    db = "postgres" if role == "super" else DB
    return f"{driver}://{user}:{pw}@{host}:{PG_PORT}/{db}"


def _pids() -> dict:
    try:
        return json.loads(PIDS.read_text())
    except Exception:
        return {}


def _save_pids(d: dict) -> None:
    PIDS.write_text(json.dumps(d))


def alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:  # 좀비는 죽은 것으로 본다
        return Path(f"/proc/{pid}/stat").read_text().split(") ")[-1][0] != "Z"
    except Exception:
        return False


# ───────────── PostgreSQL ─────────────

def pg_running() -> bool:
    p = _run([str(PGBIN / "pg_isready"), "-h", "127.0.0.1", "-p", str(PG_PORT)])
    return p.returncode == 0


def pg_init() -> None:
    if (PGDATA / "PG_VERSION").exists():
        return
    for d in (ROOT, SECRETS, APP_SECRETS, LOGS):
        d.mkdir(parents=True, exist_ok=True)
    SECRETS.chmod(0o700)
    for n in ("db_superuser_password", "db_owner_password", "db_app_password"):
        if not (SECRETS / n).exists():
            (SECRETS / n).write_text(secrets.token_hex(32))
            (SECRETS / n).chmod(0o600)
    PGDATA.mkdir(parents=True, exist_ok=True)
    PGSOCK.mkdir(parents=True, exist_ok=True)
    pwfile = ROOT / "pgpw.tmp"
    pwfile.write_text(_secret("db_superuser_password"))
    for d in (PGDATA, PGSOCK, pwfile):
        shutil.chown(d, "postgres", "postgres")
    p = _run(_priv_postgres([str(PGBIN / "initdb"), "-D", str(PGDATA), "-U", "postgres", "--pwfile", str(pwfile), "--auth=scram-sha-256",
                             "--encoding=UTF8", "--locale=C.UTF-8", "--data-checksums"]))
    pwfile.unlink(missing_ok=True)
    if p.returncode != 0:
        raise RuntimeError("initdb 실패: " + p.stderr[-400:])


def pg_start() -> None:
    if pg_running():
        return
    PGSOCK.mkdir(parents=True, exist_ok=True)
    shutil.chown(PGSOCK, "postgres", "postgres")
    opts = (f"-p {PG_PORT} -c listen_addresses=127.0.0.1 -c unix_socket_directories={PGSOCK} -c max_connections=50 -c timezone=UTC "
            f"-c log_timezone=UTC -c password_encryption=scram-sha-256 -c log_statement=none -c fsync=off -c synchronous_commit=off")
    logf = LOGS / "pg.log"
    LOGS.mkdir(parents=True, exist_ok=True)
    if not logf.exists():
        logf.touch()
    shutil.chown(logf, "postgres", "postgres")
    for attempt in range(15):    # SIGKILL 직후에는 남은 백엔드 프로세스가 공유 메모리를 놓을 때까지 잠깐 걸린다
        p = _run(_priv_postgres([str(PGBIN / "pg_ctl"), "-D", str(PGDATA), "-l", str(logf), "-o", opts, "-w", "-t", "60", "start"]))
        if p.returncode == 0:
            return
        time.sleep(1.0)
    raise RuntimeError("pg_ctl start 실패: " + (p.stderr or p.stdout)[-400:])


def pg_stop(mode: str = "fast") -> None:
    if not (PGDATA / "postmaster.pid").exists():
        return
    _run(_priv_postgres([str(PGBIN / "pg_ctl"), "-D", str(PGDATA), "-m", mode, "-w", "-t", "60", "stop"]))


def pg_kill9() -> None:
    """postmaster 를 SIGKILL(비정상 종료 시늉). 자기 PID 파일의 PID 만 쓴다."""
    pidfile = PGDATA / "postmaster.pid"
    if pidfile.exists():
        pid = int(pidfile.read_text().splitlines()[0])
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        time.sleep(1.0)


def connect(role: str = "app", autocommit: bool = True):
    import psycopg
    return psycopg.connect(db_url(role, driver="postgresql"), autocommit=autocommit)


def sql(query: str, role: str = "app", params: tuple | None = None) -> list[tuple]:
    with connect(role) as c:
        cur = c.execute(query, params)
        try:
            return cur.fetchall()
        except Exception:
            return []


def pg_bootstrap_roles() -> None:
    """01-roles.sh 와 같은 역할·DB 구성 + schema-grants.sql. 이미 있으면 건너뛴다."""
    import psycopg
    with psycopg.connect(db_url("super", driver="postgresql"), autocommit=True) as c:
        have = c.execute("select 1 from pg_database where datname=%s", (DB,)).fetchone()
        if have:
            return
        owner_pw, app_pw = _secret("db_owner_password"), _secret("db_app_password")
        c.execute("SET log_min_error_statement = 'panic'")
        for role, pw, lim in (("ytweb_owner", owner_pw, 10), ("ytweb_app", app_pw, 30)):
            c.execute(f"CREATE ROLE {role} LOGIN PASSWORD %s NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT {lim}".replace("%s", "'" + pw + "'"))
            c.execute(f"ALTER ROLE {role} SET timezone TO 'UTC'")
        c.execute(f"CREATE DATABASE {DB} OWNER ytweb_owner TEMPLATE template0 ENCODING 'UTF8'")
        c.execute(f"REVOKE ALL ON DATABASE {DB} FROM PUBLIC")
        c.execute(f"GRANT CONNECT ON DATABASE {DB} TO ytweb_app")
    _apply_grants("super")


def _apply_grants(role: str) -> None:
    import psycopg
    text = (REPO / "web" / "docker" / "db" / "schema-grants.sql").read_text(encoding="utf-8")
    url = f"postgresql://postgres:{_secret('db_superuser_password')}@127.0.0.1:{PG_PORT}/{DB}" if role == "super" else db_url(role, driver="postgresql")
    with psycopg.connect(url, autocommit=True) as c:
        c.execute(text)


def reset_schema() -> None:
    """`ytweb-db reset-schema` 와 같은 동작: public 스키마를 지우고 권한을 다시 준다(소유자 계정)."""
    import psycopg
    with psycopg.connect(db_url("owner", driver="postgresql"), autocommit=True) as c:
        c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public AUTHORIZATION ytweb_owner;")
    _apply_grants("owner")


# ───────────── 앱 프로세스 ─────────────

def app_env(extra: dict | None = None) -> dict:
    e = {k: v for k, v in os.environ.items() if not k.startswith(("YTWEB_", "PYTHONPATH"))}
    e.update({
        "YTWEB_MODE": "demo", "YTWEB_PORT": "8080", "YTWEB_ALLOWED_HOSTS": "127.0.0.1:8080,localhost:8080", "YTWEB_BASE_DIR": str(REPO),
        "YTWEB_SECRETS_DIR": str(APP_SECRETS), "YTWEB_DATABASE_URL": db_url("app"), "YTWEB_MIGRATE_DATABASE_URL": db_url("owner"),
        "YTWEB_ENABLE_DOCS": "0", "YTWEB_LOG_JSON": "1", "TZ": "Asia/Seoul", "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join([str(BACKEND), str(SRC), str(HERE)]),
    })
    e.update(extra or {})
    return e


def migrate(target: str = "head", down: bool = False) -> subprocess.CompletedProcess:
    code = ("from ytweb.migrate import alembic_config, owner_database_url; from alembic import command; import sys\n"
            "cfg = alembic_config(owner_database_url())\n"
            "(command.downgrade if sys.argv[2] == 'down' else command.upgrade)(cfg, sys.argv[1]); print('migrated', sys.argv[1])")
    return _run([VENV_PY, "-c", code, target, "down" if down else "up"], env=app_env(), cwd=str(BACKEND))


def _spawn(name: str, argv: list[str], extra_env: dict | None = None) -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    log = open(LOGS / f"{name}.log", "ab")
    p = subprocess.Popen(argv, env=app_env(extra_env), cwd=str(BACKEND), stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    d = _pids()
    d[name] = p.pid
    _save_pids(d)
    return p.pid


def api_start(relaxed: bool = True, port: int = API_PORT, name: str = "api") -> int:
    app = "itlib_b_native:relaxed_app" if relaxed else "ytweb.app:create_app"
    return _spawn(name, [VENV_PY, "-m", "uvicorn", app, "--factory", "--host", "127.0.0.1", "--port", str(port), "--no-server-header", "--no-access-log"])


def worker_start(name: str = "worker") -> int:
    return _spawn(name, [VENV_PY, "-m", "ytweb.worker"])


def proc_stop(name: str, sig: int = signal.SIGTERM, wait: float = 40.0) -> None:
    pid = _pids().get(name)
    if pid and alive(pid):
        os.kill(pid, sig)
        t0 = time.time()
        while alive(pid) and time.time() - t0 < wait:
            time.sleep(0.1)
        if alive(pid):
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.3)
    d = _pids()
    d.pop(name, None)
    _save_pids(d)


def proc_alive(name: str) -> bool:
    return alive(_pids().get(name))


def relaxed_app():
    """속도 제한만 사실상 해제한 앱(시험 속도용). 그 밖의 설정은 제품 기본값과 같다."""
    from ytweb.app import create_app
    from ytweb.core.ratelimit import RateLimits
    return create_app(rate_limits=RateLimits(10**9, 10**9, 10**9))


def wait_api(port: int = API_PORT, timeout: float = 60.0) -> None:
    import httpx
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/api/readyz", headers={"Host": "127.0.0.1:8080"}, timeout=3)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.3)
    raise TimeoutError("api 가 준비되지 않았습니다")


def up(relaxed: bool = True) -> None:
    pg_init()
    pg_start()
    pg_bootstrap_roles()
    APP_SECRETS.mkdir(parents=True, exist_ok=True)
    m = migrate()
    if m.returncode != 0:
        raise RuntimeError("migrate 실패: " + (m.stderr or m.stdout)[-600:])
    proc_stop("api")
    proc_stop("worker")
    api_start(relaxed)
    worker_start()
    wait_api()


def down() -> None:
    for n in ("worker", "api", "worker2", "worker3", "api2"):
        proc_stop(n)
    pg_stop()


def destroy() -> None:
    down()
    if PGDATA.exists():
        shutil.rmtree(PGDATA, ignore_errors=True)


def reset_demo(relaxed: bool = True) -> None:
    """reset-demo 경로: web/api/worker 중지 → 스키마 초기화 → 마이그레이션 → 기동."""
    proc_stop("worker")
    proc_stop("api")
    for n in ("worker_x0", "worker_x1", "worker_x2", "worker_x3", "worker_x4", "worker_x5"):
        proc_stop(n)
    pg_start()          # 앞선 시험이 DB 를 죽인 채 끝났어도 다음 시험이 시작할 수 있게 한다
    reset_schema()
    m = migrate()
    assert m.returncode == 0, m.stderr[-600:]
    api_start(relaxed)
    worker_start()
    wait_api()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "up":
        up(relaxed="--strict" not in sys.argv)
        print("up", {"api": _pids().get("api"), "worker": _pids().get("worker"), "pg_port": PG_PORT, "api_port": API_PORT})
    elif cmd == "down":
        down()
        print("down")
    elif cmd == "destroy":
        destroy()
        print("destroyed")
    else:
        print(json.dumps({"pg": pg_running(), "pids": _pids(), "alive": {k: alive(v) for k, v in _pids().items()}}))
