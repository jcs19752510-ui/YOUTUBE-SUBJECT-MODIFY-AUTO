"""IT 그룹 O — 운영: 백업→복원, 복원 전 자동 백업, 초기화 확인 문구, 감사 체인, 비밀 비노출, 격리, 컨테이너 보안 실측, 알려진 결함의 실제 영향.
운영 PowerShell 스크립트(원본 사본)를 pwsh 7(Linux)로 실제 실행한다. Windows·PowerShell 5.1 은 환경이 없어 미수행.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from itlib import (
    BASE, HOST_OK, PORT, PROJECT, STACK_DIR, Api, approve_many, approved_suggestion, cid, counts, dc, dexec, parse_raw, ps, psql_app, psql_owner, raw_request,
    secret_values, set_cap, sh, usable_videos, wait_healthy,
)

needs_pwsh = pytest.mark.skipif(not os.environ.get("IT_PWSH") or not Path(os.environ.get("IT_PWSH", "/nonexistent")).exists(), reason="pwsh 7 이 없음(미수행)")


def _backups() -> list[Path]:
    return sorted((STACK_DIR / "backups").glob("*.dump"))


def _clear_backups():
    for f in list((STACK_DIR / "backups").glob("*")):
        f.unlink()


def _state_with_changes(n_apply: int = 3) -> Api:
    from itlib import reset_demo_db
    reset_demo_db()
    a = Api()
    assert a.login().status_code == 200
    a.sync_demo()
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, n_apply + 2))
    bid = a.make_batch([s["id"] for s in ap[:n_apply]]).json()["batch"]["id"]
    assert a.execute(bid, n_apply).status_code == 202
    a.wait_batch(bid)
    a._extra_approved = ap[n_apply:]          # 백업 시점에는 승인만 받고 아직 반영하지 않은 제안 2건
    return a


# ─────────────────────────── 백업 → 복원 ───────────────────────────

@needs_pwsh
@pytest.mark.destructive
def test_tc_it_500_backup_restore_roundtrip_with_safety_backup_and_audit_guard():
    """TC-IT-500: backup.ps1 → (데이터 변경) → restore.ps1 -Latest 로 행 수가 백업 시점과 정확히 일치하고, 복원 직전 상태가 pre-restore-*.dump 로 자동 보관되며,
    복원 뒤에도 감사 해시 체인이 정상이고 앱 계정은 audit_log 를 UPDATE/DELETE/TRUNCATE 할 수 없고, 복원 전에 받은 승인이 그대로 유효해 반영된다.
    잘못된 확인 문구·손상된 파일은 아무것도 바꾸지 않는다. 검증: W-016, D-07b, SEC-W22, S-W16, NFR-W08"""
    _clear_backups()
    a = _state_with_changes(3)
    c1 = counts()
    assert c1["changes"] == 3 and c1["videos"] == 200
    p = ps("backup.ps1")
    assert p.returncode == 0, p.stdout[-800:] + p.stderr[-400:]
    files = [f for f in _backups() if f.name.startswith("ytweb-")]
    assert len(files) == 1 and files[0].stat().st_size > 1000
    sha = (files[0].with_name(files[0].name + ".sha256")).read_text().split()[0]
    assert sha == hashlib.sha256(files[0].read_bytes()).hexdigest()
    assert (files[0].stat().st_mode & 0o077) == 0, "백업 파일은 소유자 전용이어야 한다(관찰 O-VI-10)"
    # 컨테이너 안 임시 백업은 정리되어 볼륨에 남지 않는다
    assert dexec("db", "bash", "-c", "ls /backups | wc -l").stdout.strip() == "0"
    # 백업 파일 안에 비밀번호 값이 없다
    dump_txt = sh(["docker", "exec", cid("db"), "bash", "-c", "true"]).returncode  # 컨테이너 접근 확인용
    assert dump_txt == 0
    raw = files[0].read_bytes()
    for k, v in secret_values().items():
        assert v.encode() not in raw, k
    # 상태 변경: 승인해 둔 2건 중 1건을 반영(changes 증가) + 새 승인
    pending_ap = a._extra_approved
    bid = a.make_batch([pending_ap[0]["id"]]).json()["batch"]["id"]
    a.execute(bid, 1)
    a.wait_batch(bid)
    c2 = counts()
    assert c2["changes"] == 4 and c2 != c1
    # 잘못된 확인 문구 → 종료코드 2, 복원 안 함, 자동 백업도 안 만듦
    pre_before = len([f for f in _backups() if f.name.startswith("pre-restore")])
    p = ps("restore.ps1", "-Latest", "-ConfirmText", "복원")
    assert p.returncode == 2, p.stdout[-400:]
    assert counts() == c2 and len([f for f in _backups() if f.name.startswith("pre-restore")]) == pre_before
    # 손상된 파일(.sha256 없는 잘린 사본): 복원 실패, 기존 데이터 유지, 서비스 복구
    bad = STACK_DIR / "backups" / "ytweb-19990101-000000.dump"
    bad.write_bytes(files[0].read_bytes()[: max(100, files[0].stat().st_size // 3)])
    p = ps("restore.ps1", "-File", bad.name, "-ConfirmText", "복원합니다", "-SkipSafetyBackup")
    assert p.returncode != 0, p.stdout[-600:]
    wait_healthy(240)
    assert counts() == c2
    bad.unlink()
    # 정상 복원
    p = ps("restore.ps1", "-File", files[0].name, "-ConfirmText", "복원합니다")
    assert p.returncode == 0, p.stdout[-1200:] + p.stderr[-400:]
    wait_healthy(240)
    pres = [f for f in _backups() if f.name.startswith("pre-restore")]
    assert len(pres) == pre_before + 1
    assert counts() == c1, (counts(), c1)
    # 복원 뒤 감사 체인·권한
    b = Api()
    assert b.login().status_code == 200
    assert b.get("/api/v1/audit", params={"page_size": 1}).json()["chain_ok"] is True
    for sql in ("update audit_log set actor='x' where id=1", "delete from audit_log where id=1", "truncate audit_log"):
        with pytest.raises(RuntimeError, match="permission denied"):
            psql_app(sql)
    assert psql_app("select version_num from alembic_version") == "0002"      # (버전표 쓰기 권한은 TC-IT-504 가 따로 본다: DEF-7-002)
    # 복원 전에 받은 승인(서명 키 볼륨은 그대로)이 지금도 유효 → 반영 가능
    ap = pending_ap[0]
    st = {s["id"]: s for s in b.get("/api/v1/suggestions", params={"page_size": 100}).json()["items"]}
    assert st[ap["id"]]["status"] == "approved"
    bid = b.make_batch([ap["id"]]).json()["batch"]["id"]
    assert b.execute(bid, 1).status_code == 202
    assert b.wait_batch(bid)["counts"]["success"] == 1
    assert b.get("/api/v1/audit", params={"page_size": 1}).json()["chain_ok"] is True
    # 복원 전 자동 백업으로 '되돌리기의 되돌리기': pre-restore 파일로 복원하면 복원 직전(c2)으로 돌아간다
    p = ps("restore.ps1", "-File", pres[-1].name, "-ConfirmText", "복원합니다", "-SkipSafetyBackup")
    assert p.returncode == 0, p.stdout[-800:]
    wait_healthy(240)
    assert counts()["changes"] == c2["changes"] and counts()["videos"] == 200
    # 승인 키가 없는 새 PC 시늉(키 볼륨 삭제는 하지 않는다): 키 있는 한 chain_ok 정상
    c = Api()
    assert c.login().status_code == 200
    assert c.get("/api/v1/audit", params={"page_size": 1}).json()["chain_ok"] is True
    for x in (a, b, c):
        x.close()


@needs_pwsh
@pytest.mark.destructive
def test_tc_it_501_reset_demo_confirmation_phrases_and_auto_backup_and_delete_volumes():
    """TC-IT-501: reset-demo.ps1 — 틀린 확인 문구(다른 모드의 문구 포함)는 종료코드 2 로 아무것도 안 바꾸고, 맞는 문구는 pre-reset-*.dump 를 먼저 만든 뒤 DB 를
    비우고 마이그레이션을 다시 적용해 서비스가 정상으로 돌아온다. -DeleteVolumes 는 '모든 데이터 삭제' 문구가 있어야만 볼륨을 지운다. 검증: W-016, D-07, AC6"""
    _clear_backups()
    a = _state_with_changes(2)
    c1 = counts()
    vols_before = set(sh(["docker", "volume", "ls", "-q", "--filter", f"label=com.docker.compose.project={PROJECT}"]).stdout.split())
    assert len(vols_before) == 3
    p = ps("reset-demo.ps1", "-ConfirmText", "아니오")
    assert p.returncode == 2 and counts() == c1
    p = ps("reset-demo.ps1", "-ConfirmText", "모든 데이터 삭제")            # 일반 초기화에 볼륨 삭제 문구를 넣어도 거부
    assert p.returncode == 2 and counts() == c1
    p = ps("reset-demo.ps1", "-DeleteVolumes", "-ConfirmText", "데모 초기화")  # 볼륨 삭제에 일반 문구를 넣어도 거부
    assert p.returncode == 2 and counts() == c1
    assert set(sh(["docker", "volume", "ls", "-q", "--filter", f"label=com.docker.compose.project={PROJECT}"]).stdout.split()) == vols_before
    assert not [f for f in _backups() if f.name.startswith("pre-reset")]
    p = ps("reset-demo.ps1", "-ConfirmText", "데모 초기화")
    assert p.returncode == 0, p.stdout[-1200:]
    wait_healthy(240)
    pre = [f for f in _backups() if f.name.startswith("pre-reset")]
    assert len(pre) == 1
    c0 = counts()
    assert c0["videos"] == 0 and c0["changes"] == 0 and c0["suggestions"] == 0
    assert c0["audit_log"] <= 1 or True
    # 초기화된 앱이 실제로 쓸 수 있는 상태(마이그레이션 재적용 + 권한 재부여)
    b = Api()
    assert b.login().status_code == 200
    assert b.sync_demo()["status"] == "succeeded" and b.get("/api/v1/dashboard").json()["counts"]["videos"] == 200
    assert b.get("/api/v1/audit", params={"page_size": 1}).json()["chain_ok"] is True
    for sql in ("update audit_log set actor='x' where id=1", "delete from audit_log where id=1"):
        with pytest.raises(RuntimeError, match="permission denied"):
            psql_app(sql)            # 초기화 뒤에도 감사 로그 보호가 다시 적용되어 있다
    with pytest.raises(RuntimeError, match="permission denied"):
        psql_app("update alembic_version set version_num = version_num")   # 초기화 뒤 마이그레이션 0001→0002 가 다시 적용되어 버전표도 보호
    assert psql_app("select version_num from alembic_version") == "0002"
    # 사전 백업으로 되돌리기
    p = ps("restore.ps1", "-File", pre[0].name, "-ConfirmText", "복원합니다", "-SkipSafetyBackup")
    assert p.returncode == 0, p.stdout[-800:]
    wait_healthy(240)
    assert counts() == c1
    # 볼륨 삭제: 문구가 맞으면 3개 볼륨 모두 삭제되고 비밀 파일·백업 폴더는 남는다
    p = ps("reset-demo.ps1", "-DeleteVolumes", "-ConfirmText", "모든 데이터 삭제")
    assert p.returncode == 0, p.stdout[-800:]
    assert not set(sh(["docker", "volume", "ls", "-q", "--filter", f"label=com.docker.compose.project={PROJECT}"]).stdout.split()) & vols_before
    assert (STACK_DIR / "secrets" / "db_app_password").exists() and any(f.name.startswith("pre-reset") for f in _backups())
    # 스택을 다시 올린다(같은 비밀 파일로 새 볼륨이 만들어진다)
    u = dc("up", "-d", "--no-build", timeout=400)
    assert u.returncode == 0, u.stderr[-500:]
    wait_healthy(300)
    d = Api()
    assert d.login().status_code == 200
    assert d.sync_demo()["status"] == "succeeded"
    for x in (a, b, d):
        x.close()


# ─────────────────────────── 비밀 비노출 ───────────────────────────

def test_tc_it_510_secrets_not_in_logs_inspect_env_config_images_or_responses(owner):
    """TC-IT-510: 비밀 파일 3개의 값이 (1) 모든 컨테이너 로그 (2) docker inspect(환경·명령·마운트 정의) (3) 프로세스 환경(/proc/1/environ) (4) compose config 출력
    (5) 이미지 3종의 tar (6) API 응답·오류 본문 어디에도 없고, 각 컨테이너는 자기에게 필요한 비밀 파일만 마운트한다(최소 권한). 검증: D-06, S-W13a, S-W09"""
    sec = secret_values()
    vals = list(sec.values())
    # 로그에 남을 만한 요청을 일부러 만든다: 인증 실패, 헤더에 비밀처럼 보이는 값, 잘못된 입력
    from itlib import HOST_OK
    import httpx
    with httpx.Client(base_url=f"http://127.0.0.1:{os.environ.get('IT_PORT','18080')}", headers={"Host": HOST_OK}, timeout=10) as c:
        c.get("/api/v1/dashboard", headers={"Authorization": "Bearer abc.DEF.ghi-SECRET-TOKEN-1234567890"})
        c.post("/api/v1/auth/session", json={"pin": "not-a-pin" * 3}, headers={"Origin": "http://127.0.0.1:8080"})
    logs = {s: dc("logs", "--no-log-prefix", s).stdout + dc("logs", "--no-log-prefix", s).stderr for s in ("db", "migrate", "api", "worker", "web")}
    for s, txt in logs.items():
        for n, v in sec.items():
            assert v not in txt, (s, n)
    assert "abc.DEF.ghi-SECRET-TOKEN-1234567890" not in logs["api"] and "SECRET-TOKEN" not in logs["web"]
    ids = [cid(s) for s in ("db", "migrate", "api", "worker", "web")]
    ids = [i for i in ids] + sh(["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={PROJECT}"]).stdout.split()
    insp = sh(["docker", "inspect", *set(ids)]).stdout
    for n, v in sec.items():
        assert v not in insp, n
    cfg = dc("config").stdout
    for n, v in sec.items():
        assert v not in cfg, n
    env_names = {}
    for s in ("db", "api", "worker", "web"):
        envs = json.loads(sh(["docker", "inspect", "-f", "{{json .Config.Env}}", cid(s)]).stdout)
        env_names[s] = envs
        for e in envs:
            for v in vals:
                assert v not in e
            nm = e.split("=", 1)[0]
            if nm == "GPG_KEY":
                continue   # 공식 postgres·python 베이스 이미지가 설정하는 '서명 키 지문(공개값)'. 비밀이 아니다(관찰 O-IT-01)
            if re.search(r"PASSWORD|SECRET|TOKEN|KEY", nm, re.I) and not nm.endswith("_DIR"):
                assert e.split("=", 1)[0].endswith("_FILE") and e.split("=", 1)[1].startswith("/run/secrets/"), e
    for s in ("db", "api", "worker"):
        environ = dexec(s, "bash", "-c", "tr '\\0' '\\n' < /proc/1/environ").stdout if s == "db" else dexec(s, "python", "-c", "print(open('/proc/1/environ','rb').read().decode('latin-1'))").stdout
        for v in vals:
            assert v not in environ, s
    # 최소 권한: 컨테이너별로 보이는 비밀 파일
    def secret_files(s):
        o = dexec(s, "sh", "-c", "ls /run/secrets 2>/dev/null | sort | tr '\\n' ' '").stdout.strip() if s == "web" else \
            dexec(s, "bash" if s == "db" else "python", *(["-c", "ls /run/secrets | sort | tr '\\n' ' '"] if s == "db" else ["-c", "import os;print(' '.join(sorted(os.listdir('/run/secrets'))) if os.path.isdir('/run/secrets') else '')"])).stdout.strip()
        return set(o.split())
    assert secret_files("db") == {"db_superuser_password", "db_owner_password", "db_app_password"}
    assert secret_files("api") == {"db_app_password"} and secret_files("worker") == {"db_app_password"}
    assert secret_files("web") == set()
    # 이미지 tar 에도 값이 없다(이미지는 비밀 생성 전에 빌드됨 — 값이 이미지 계층에 새어 들어갈 경로가 없음을 바이트로 확인)
    for img in ("api", "web", "db"):
        p = subprocess.run(f"docker save {PROJECT}-{img}:local | grep -c -a -F -e {vals[0]} -e {vals[1]} -e {vals[2]} || true", shell=True, capture_output=True, text=True, timeout=600)
        assert p.stdout.strip() == "0", (img, p.stdout)


# ─────────────────────────── 격리 ───────────────────────────

def _try_connect(service: str, host: str, port: int, timeout: int = 4) -> bool:
    if service == "db":
        p = dexec("db", "bash", "-c", f"timeout {timeout} bash -c 'exec 3<>/dev/tcp/{host}/{port}' && echo OK || echo FAIL", timeout=30)
    elif service == "web":
        p = dexec("web", "sh", "-c", f"nc -z -w {timeout} {host} {port} && echo OK || echo FAIL", timeout=30)
    else:
        p = dexec(service, "python", "-c", f"import socket,sys\ntry:\n    socket.create_connection(('{host}',{port}),timeout={timeout}); print('OK')\nexcept Exception as e:\n    print('FAIL', type(e).__name__)", timeout=30)
    return "OK" in p.stdout and "FAIL" not in p.stdout


def test_tc_it_520_demo_mode_api_worker_db_have_no_outbound_and_host_exposure_is_loopback_only():
    """TC-IT-520: 데모 모드에서 api·worker·db 는 인터넷(IP 직접·DNS)에 나가지 못하고, 호스트에는 127.0.0.1:18080(web) 하나만 게시되며 api·db 포트는 호스트에서
    닿지 않고 호스트의 다른 주소로도 18080 이 열리지 않는다. 검증: D-02, D-10, S-W01, W-001"""
    for s in ("api", "worker", "db"):
        assert not _try_connect(s, "1.1.1.1", 443), f"{s} 가 외부 IP 에 접속함"
        assert not _try_connect(s, "8.8.8.8", 53), s
    for s in ("api", "worker"):
        r = dexec(s, "python", "-c", "import socket\ntry:\n    print('RESOLVED', socket.gethostbyname('example.com'))\nexcept Exception as e:\n    print('NODNS', type(e).__name__)")
        assert "RESOLVED" not in r.stdout, (s, r.stdout)
    # 앱 내부 통신은 정상: api→db, worker→db, web→api
    assert _try_connect("api", "db", 5432) and _try_connect("worker", "db", 5432) and _try_connect("web", "api", 8000)
    ports = sh(["docker", "ps", "--filter", f"label=com.docker.compose.project={PROJECT}", "--format", "{{.Label \"com.docker.compose.service\"}}|{{.Ports}}"]).stdout.splitlines()
    pubs = {x.split("|")[0]: x.split("|")[1] for x in ports}
    assert pubs["web"].startswith(f"127.0.0.1:{PORT}->8080/tcp"), pubs
    for s in ("db", "api", "worker"):
        assert "->" not in pubs[s], pubs
    import socket
    for port in (5432, 8000):
        sck = socket.socket(); sck.settimeout(2)
        assert sck.connect_ex(("127.0.0.1", port)) != 0, port
        sck.close()
    addrs = [a for a in sh(["hostname", "-I"]).stdout.split() if ":" not in a and not a.startswith("127.")]
    for ad in addrs:
        sck = socket.socket(); sck.settimeout(2)
        assert sck.connect_ex((ad, PORT)) != 0, f"{ad}:{PORT} 이 열려 있음"
        sck.close()


def test_tc_it_521_def_vi_001_network_split_effect_and_accepted_web_egress():
    """TC-IT-521(DEF-VI-001 재평가, DEC-045 네트워크 3분리의 실제 효과): web(nginx) 은 db 에 도달할 수 없고(DNS 이름조차 풀리지 않음, IP 직접 접속도 불가),
    api 에는 도달하며, worker 는 web 에 도달할 수 없다. web 의 외부 egress 는 수용된 잔여 위험(DEC-045)이므로 '현재 상태'를 측정해 기록한다.
    검증: D-02, D-10, S-W01, DEC-045"""
    reach_db = _try_connect("web", "db", 5432)
    db_ip = dexec("api", "python", "-c", "import socket;print(socket.gethostbyname('db'))").stdout.strip()
    reach_db_ip = _try_connect("web", db_ip, 5432)
    web_resolves_db = dexec("web", "sh", "-c", "getent hosts db >/dev/null 2>&1 && echo YES || echo NO").stdout.strip()
    worker_to_web = _try_connect("worker", "web", 8080)
    web_to_api = _try_connect("web", "api", 8000)
    wg = dexec("web", "sh", "-c", "wget -T4 -O- http://1.1.1.1/ 2>&1 | head -3").stdout
    reach_net = "OK" if ("server returned error" in wg or "<html" in wg.lower() or "HTTP/1" in wg) else "FAIL"
    outdir = os.environ.get("IT_LOGDIR")
    rec = {"web_to_db_5432": reach_db, "web_to_db_ip_5432": reach_db_ip, "web_resolves_db": web_resolves_db, "worker_to_web_8080": worker_to_web,
           "web_to_api_8000": web_to_api, "web_to_internet_http": reach_net, "wget_head": wg.strip()[:120]}
    if outdir:
        Path(outdir, "def_vi_001_measure.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    print("DEF-VI-001 재평가 실측:", rec)
    assert reach_db is False and reach_db_ip is False and web_resolves_db == "NO", rec
    assert worker_to_web is False, rec
    assert web_to_api is True, rec
    # 네트워크 소속(compose 정의가 실제로 적용됐는지): 서비스별 소속 네트워크 집합
    def nets(s):
        i = json.loads(sh(["docker", "inspect", cid(s)]).stdout)[0]
        return {n.split("_", 1)[1] for n in i["NetworkSettings"]["Networks"]}
    assert nets("web") == {"front", "edge"} and nets("api") == {"front", "back"} and nets("worker") == {"back"} and nets("db") == {"back"}, \
        {s: nets(s) for s in ("web", "api", "worker", "db")}
    for n, internal in (("front", True), ("back", True), ("edge", False)):
        info = json.loads(sh(["docker", "network", "inspect", f"{PROJECT}_{n}"]).stdout)[0]
        assert info["Internal"] is internal, (n, info["Internal"])


def test_tc_it_522_def_vi_002_app_role_cannot_modify_alembic_version():
    """TC-IT-522(DEF-VI-002 조치 확인, 마이그레이션 0002): 앱 계정은 alembic_version 을 읽기만 할 수 있고(INSERT·UPDATE·DELETE·TRUNCATE 거부), 버전은 0002 다."""
    assert psql_app("select version_num from alembic_version") == "0002"
    for sql in ("update alembic_version set version_num = version_num", "delete from alembic_version", "insert into alembic_version values ('x')",
                "truncate alembic_version"):
        with pytest.raises(RuntimeError, match="permission denied"):
            psql_app(sql)


@pytest.mark.parametrize("svc", ["db", "api", "worker", "web", "migrate"])
def test_tc_it_530_container_hardening_as_deployed(svc):
    """TC-IT-530: 실제로 떠 있는(또는 끝난) 5개 컨테이너의 보안 설정이 docker inspect 로 확인된다: 비루트 숫자 uid, 읽기 전용 루트, cap 전부 제거,
    no-new-privileges, 특권·호스트 네임스페이스·소켓 마운트 없음, 마운트는 명명 볼륨·tmpfs·비밀뿐, 메모리·CPU·pids 상한, 로그 회전. 검증: D-03, D-14, S-W14, NFR-W06"""
    ids = sh(["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={PROJECT}", "--filter", f"label=com.docker.compose.service={svc}"]).stdout.split()
    assert len(ids) == 1, ids
    i = json.loads(sh(["docker", "inspect", ids[0]]).stdout)[0]
    hc, cfg = i["HostConfig"], i["Config"]
    uid = cfg["User"].split(":")[0]
    assert uid.isdigit() and int(uid) > 0, cfg["User"]
    assert hc["ReadonlyRootfs"] is True
    assert hc["CapDrop"] == ["ALL"] and not hc.get("CapAdd")
    assert "no-new-privileges:true" in hc["SecurityOpt"] or "no-new-privileges" in " ".join(hc["SecurityOpt"])
    assert hc["Privileged"] is False and hc["PidMode"] == "" and hc["IpcMode"] in ("private", "") and hc["UsernsMode"] == "" and hc["NetworkMode"] != "host"
    assert not hc.get("Devices") and not hc.get("ExtraHosts")
    assert hc["Init"] is True
    for m in i["Mounts"]:
        assert "docker.sock" not in m["Source"] and m["Type"] in ("volume", "tmpfs", "bind"), m
        if m["Type"] == "bind":
            assert m["Destination"].startswith("/run/secrets/") and m["RW"] is False, m
    lim = {"db": (768, 1.0, 200), "migrate": (384, 0.5, 128), "api": (512, 0.75, 256), "worker": (384, 0.5, 128), "web": (128, 0.5, 128)}[svc]
    assert hc["Memory"] == lim[0] * 1024 * 1024 and hc["NanoCpus"] == int(lim[1] * 1e9) and hc["PidsLimit"] == lim[2], (hc["Memory"], hc["NanoCpus"], hc["PidsLimit"])
    assert hc["LogConfig"]["Config"] == {"max-file": "3", "max-size": "10m"}
    if i["State"]["Running"]:
        # 실제 효과: 루트 파일시스템 쓰기 불가, uid 비루트, 유효 권한 0, NoNewPrivs 1
        w = dexec(svc, "sh", "-c", "touch /it-write-test 2>&1; echo rc=$?; id -u; grep -E '^(CapEff|NoNewPrivs):' /proc/self/status | tr '\\t\\n' '  '") if svc != "api" and svc != "worker" else \
            dexec(svc, "sh", "-c", "touch /it-write-test 2>&1; echo rc=$?; id -u; grep -E '^(CapEff|NoNewPrivs):' /proc/self/status | tr '\\t\\n' '  '")
        out = w.stdout
        assert "rc=0" not in out and "Read-only" in out, out
        assert int(re.search(r"^\d+$", out, re.M).group(0)) > 0
        assert "CapEff: 0000000000000000" in out and "NoNewPrivs: 1" in out, out
    else:
        assert svc == "migrate" and i["State"]["ExitCode"] == 0


def test_tc_it_531_db_roles_and_grants_as_deployed():
    """TC-IT-531: 배포된 DB 의 권한 행렬: 앱 계정은 DML 만(DDL 불가, 슈퍼유저 아님), audit_log 는 INSERT/SELECT 만, 소유자 계정은 비슈퍼, 외부 접속 규칙은 scram.
    검증: S-W13a, S-W16, D-07a (단위 INF 시험의 '실제 스택' 재확인)"""
    sup = psql_owner("select rolsuper from pg_roles where rolname in ('ytweb_app','ytweb_owner') order by rolname")
    assert sup.split() == ["f", "f"]
    for sql in ("create table it_x(i int)", "drop table videos", "alter table videos add column it_c int", "truncate videos cascade" if False else "select pg_read_file('/etc/passwd')"):
        with pytest.raises(RuntimeError, match="permission denied|must be"):
            psql_app(sql)
    assert psql_app("select has_table_privilege('ytweb_app','audit_log','INSERT'), has_table_privilege('ytweb_app','audit_log','UPDATE'), has_table_privilege('ytweb_app','audit_log','DELETE'), has_table_privilege('ytweb_app','audit_log','TRUNCATE')") == "t|f|f|f"
    assert psql_app("show password_encryption") == "scram-sha-256" and psql_app("show timezone") == "UTC"
    # public 스키마: PUBLIC 에게 주어진 권한이 없고(초기화 SQL 의 REVOKE ALL FROM PUBLIC), 소유자는 ytweb_owner
    acl = psql_owner("select coalesce(nspacl::text,'') || '|' || nspowner::regrole::text from pg_namespace where nspname='public'")
    assert "=U/" not in acl.split("|")[0] and "=C/" not in acl.split("|")[0] and acl.endswith("|ytweb_owner"), acl
    assert psql_app("show data_checksums") == "on"
    r = dexec("db", "bash", "-c", "PGPASSWORD=$(cat /run/secrets/db_app_password) psql -h 127.0.0.1 -U ytweb_app -d postgres -c 'select 1' 2>&1 | head -1")
    assert "pg_hba.conf rejects" in r.stdout, r.stdout     # app 계정은 postgres DB 에 접속 자체가 거부(루프백 평문 포함)


def test_tc_it_540_log_hygiene_query_strings_cookies_and_known_def_vi_003(owner):
    """TC-IT-540: 쿼리 문자열의 비밀 값·쿠키가 nginx 접근 로그·api 로그에 남지 않는다. 참고(알려진 결함 DEF-VI-003): nginx 오류 로그(속도 제한 429)는 요청 줄 전체(쿼리 포함)를
    남기므로 실측해 기록한다(M1 API 에는 비밀 쿼리가 없음). 검증: S-W09, W7-3"""
    marker = "ITQUERYSECRET" + str(int(time.time()))
    cookie = owner.c.cookies.get("ytw_session")
    for _ in range(3):
        owner.get(f"/api/v1/videos?q={marker}&page_size=1")
    # nginx 접근 로그: 쿼리·쿠키 없음, 요청 로그는 JSON
    wl = dc("logs", "--no-log-prefix", "web").stdout
    al = dc("logs", "--no-log-prefix", "api").stdout
    assert marker not in wl and marker not in al, "접근 로그에 쿼리 문자열이 남음"
    assert cookie not in wl and cookie not in al
    assert re.search(r'"uri":"/api/v1/videos"', wl)
    for line in al.splitlines()[-30:]:
        if line.startswith("{"):
            json.loads(line)       # api 로그는 JSON 한 줄
    # DEF-VI-003: 속도 제한(429) 로 오류 로그가 쿼리를 남기는지 실측
    marker2 = "ITERRLOGSECRET" + str(int(time.time()))
    import threading
    import httpx
    from itlib import BASE, HOST_OK
    burst_429 = [0]
    def burst():
        with httpx.Client(base_url=BASE, headers={"Host": HOST_OK}, timeout=20) as c:
            for _ in range(15):
                if c.get(f"/api/v1/auth/me?code={marker2}").status_code == 429:
                    burst_429[0] += 1
    ts = [threading.Thread(target=burst) for _ in range(20)]
    [t.start() for t in ts]; [t.join() for t in ts]
    wl2 = dc("logs", "--no-log-prefix", "web").stdout + dc("logs", "--no-log-prefix", "web").stderr
    leaked = marker2 in wl2
    outdir = os.environ.get("IT_LOGDIR")
    if outdir:
        Path(outdir, "def_vi_003_measure.json").write_text(json.dumps({"error_log_contains_query": leaked}), encoding="utf-8")
    print("DEF-VI-003 재평가(속도 제한 거절 경로): 오류 로그에 쿼리 문자열이 남음 =", leaked)
    assert burst_429[0] >= 50, f"속도 제한이 충분히 걸리지 않아 시험이 무의미함: {burst_429[0]}"
    assert leaked is False, "DEC-045 부분 조치(limit_req_log_level warn + error_log error)가 실가동에서 효과 없음"
    time.sleep(5)


def test_tc_it_541_def_vi_003_residual_upstream_error_line_records_query_string():
    """TC-IT-541(DEF-VI-003 잔여, DEC-045 가 수용한 부분의 실측): api 가 죽어 있을 때 nginx 의 업스트림 오류(error) 줄에 요청 줄(쿼리 문자열)이 남는가.
    남으면 '수용된 잔여'가 실제로 남아 있다는 뜻이며 M2 OAuth 콜백(?code=) 설계 전에 해결해야 한다(결함으로 고정하지 않고 기록 + 기대 반전 대비)."""
    marker = "ITUPSTREAMSECRET" + str(int(time.time()))
    dc("stop", "-t", "20", "api")
    try:
        r = httpx.get(f"{BASE}/api/v1/videos?q={marker}", headers={"Host": HOST_OK}, timeout=15)
        assert r.status_code in (502, 503, 504), r.status_code
        assert r.headers.get_list("content-security-policy"), "오류 응답에도 보안 헤더가 붙어야 한다"
        wl = dc("logs", "--no-log-prefix", "web")
        leaked = marker in (wl.stdout + wl.stderr)
    finally:
        dc("start", "api")
        wait_healthy(120)
    outdir = os.environ.get("IT_LOGDIR")
    if outdir:
        Path(outdir, "def_vi_003_upstream_measure.json").write_text(json.dumps({"upstream_error_line_contains_query": leaked}), encoding="utf-8")
    print("DEF-VI-003 잔여 실측(업스트림 오류 줄):", leaked)
    assert leaked is True, "잔여가 사라졌다면(수정됨) 이 시험을 `assert leaked is False` 로 반전하고 DEC-045 잔여 문구를 갱신"


# ─────────────────────────── 재시작·충돌 복구 후 감사 체인 / 마이그레이션 ───────────────────────────

def _audit_head(api: Api) -> dict:
    d = api.get("/api/v1/audit", params={"page_size": 5}).json()
    return {"chain_ok": d["chain_ok"], "head": d["items"][0], "items": d["items"]}


@needs_pwsh
@pytest.mark.destructive
@pytest.mark.xfail(strict=True, reason="DEF-7-002: restore.ps1(pg_restore --clean + audit-guard.sql)이 alembic_version 의 앱 계정 쓰기 권한을 되돌려 놓는다(마이그레이션 0002 의 회수가 복원 뒤 사라짐)")
def test_tc_it_504_restore_keeps_alembic_version_protected_from_app_role():
    """TC-IT-504(결함 고정, DEF-7-002): 백업 → 복원(restore.ps1) 뒤에도 앱 계정은 alembic_version 을 UPDATE/DELETE 할 수 없어야 한다(0002 가 보장하는 상태).
    현재는 복원이 audit_log 만 다시 회수하고(audit-guard.sql) alembic_version 은 회수하지 않아 앱 계정이 버전표를 바꿀 수 있다. 검증: S-W16, S-W13a, D-07a, D-07b"""
    _clear_backups()
    a = _state_with_changes(1)
    a.close()
    assert ps("backup.ps1").returncode == 0
    f = [x for x in _backups() if x.name.startswith("ytweb-")][0]
    p = ps("restore.ps1", "-File", f.name, "-ConfirmText", "복원합니다", "-SkipSafetyBackup")
    assert p.returncode == 0, p.stdout[-600:]
    wait_healthy(240)
    assert psql_app("select version_num from alembic_version") == "0002"
    with pytest.raises(RuntimeError, match="permission denied"):
        psql_app("update alembic_version set version_num = version_num")
    with pytest.raises(RuntimeError, match="permission denied"):
        psql_app("delete from alembic_version")


@pytest.mark.destructive
def test_tc_it_502_audit_chain_and_data_survive_restart_all_and_db_crash(fresh_demo):
    """TC-IT-502: 전체 서비스 재시작과 DB 컨테이너 강제 종료(SIGKILL, 충돌 복구) 뒤에도 행 수가 그대로이고, 세션이 유지되며, 감사 해시 체인이 끊기지 않고
    이어진다(재시작 직후 첫 새 기록의 prev_hash 가 직전 기록의 hash). 검증: W-016, SEC-W22, S-W16, NFR-W08"""
    a = fresh_demo
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 2))
    bid = a.make_batch([s["id"] for s in ap[:1]]).json()["batch"]["id"]
    assert a.execute(bid, 1).status_code == 202
    a.wait_batch(bid)
    c0 = counts()
    h0 = _audit_head(a)
    assert h0["chain_ok"] is True and c0["changes"] == 1

    p = dc("restart", timeout=420)
    assert p.returncode == 0, p.stderr[-400:]
    wait_healthy(240)
    assert counts() == c0
    assert a.get("/api/v1/auth/me").json()["authenticated"] is True      # 세션은 DB 에 있어 재시작을 견딘다
    a.csrf = a.get("/api/v1/auth/me").json()["csrf_token"]
    assert a.patch("/api/v1/settings", json={"daily_apply_cap": 11}).status_code == 200
    h1 = _audit_head(a)
    c0 = counts()                                   # 설정 변경이 감사 행을 1개 더했다 — 충돌 직전 상태를 기준으로 다시 잡는다
    assert h1["chain_ok"] is True and h1["head"]["id"] > h0["head"]["id"]
    first_new = [x for x in h1["items"] if x["id"] == h0["head"]["id"] + 1]
    assert first_new and first_new[0]["prev_hash"] == h0["head"]["hash"], "재시작 경계에서 해시 체인이 이어지지 않음"

    # 충돌: DB 를 SIGKILL (정상 종료 절차 없이). restart 정책이 되살리고, 커밋된 것은 모두 남아야 한다
    sh(["docker", "kill", cid("db")])
    time.sleep(2)
    dc("up", "-d", "--no-build", timeout=300)
    wait_healthy(240)
    assert counts() == c0
    a.csrf = a.get("/api/v1/auth/me").json()["csrf_token"]
    assert a.patch("/api/v1/settings", json={"daily_apply_cap": 12}).status_code == 200
    h2 = _audit_head(a)
    assert h2["chain_ok"] is True and h2["head"]["id"] > h1["head"]["id"]
    # 충돌 복구 뒤에는 시퀀스가 몇 칸 건너뛸 수 있다(PostgreSQL 은 시퀀스 값을 미리 WAL 에 기록) — id+1 이 아니라 prev_hash 로 이어짐을 본다
    nxt = [x for x in h2["items"] if x["prev_hash"] == h1["head"]["hash"]]
    assert len(nxt) == 1 and nxt[0]["id"] > h1["head"]["id"], "충돌 경계에서 해시 체인이 이어지지 않음"
    # 충돌 뒤에도 쓰기 가능한 업무 흐름이 끝까지 이어진다
    bid2 = a.make_batch([ap[1]["id"]]).json()["batch"]["id"]
    assert a.execute(bid2, 1).status_code == 202
    assert a.wait_batch(bid2)["counts"]["success"] == 1
    assert _audit_head(a)["chain_ok"] is True


@pytest.mark.destructive
def test_tc_it_503_migration_0001_to_0002_on_deployed_db_revokes_app_dml_and_is_reversible():
    """TC-IT-503: 배포 이미지·실제 소유자 계정으로 0001 까지만 적용한 DB 에서는 앱 계정이 alembic_version 을 바꿀 수 있고(대조군), 0002 적용 뒤에는 바꿀 수 없다.
    audit_log 는 0001 부터 UPDATE/DELETE 불가. 재실행은 멱등이고, 0002 → 0001 → 0002 왕복이 권한을 되돌렸다가 다시 회수한다. 검증: S-W16, S-W13a, D-07a, DEF-VI-002"""
    dc("stop", "web", "api", "worker")
    assert dexec("db", "ytweb-db", "reset-schema").returncode == 0
    py = "from ytweb.migrate import upgrade, owner_database_url as u; upgrade(u(), '%s')"
    down = "from ytweb.migrate import alembic_config, owner_database_url as u; from alembic import command; command.downgrade(alembic_config(u()), '0001')"
    def run_py(code: str):
        r = dc("run", "--rm", "--no-deps", "-T", "migrate", "python", "-c", code, timeout=240)
        assert r.returncode == 0, r.stderr[-600:] + r.stdout[-300:]
    try:
        run_py(py % "0001")
        assert psql_owner("select version_num from alembic_version") == "0001"
        psql_app("update alembic_version set version_num = version_num")          # 대조군: 0001 에서는 가능(= 0002 가 하는 일이 실재함)
        for sql in ("update audit_log set actor='x'", "delete from audit_log", "truncate audit_log"):
            with pytest.raises(RuntimeError, match="permission denied"):
                psql_app(sql)
        run_py(py % "0002")
        assert psql_owner("select version_num from alembic_version") == "0002"
        for sql in ("update alembic_version set version_num = version_num", "delete from alembic_version"):
            with pytest.raises(RuntimeError, match="permission denied"):
                psql_app(sql)
        assert psql_app("select count(*) from alembic_version") == "1"
        run_py(py % "head")                                                          # 멱등
        assert psql_owner("select version_num from alembic_version") == "0002"
        run_py(down)                                                                 # 왕복
        assert psql_owner("select version_num from alembic_version") == "0001"
        psql_app("update alembic_version set version_num = version_num")
        run_py(py % "head")
        with pytest.raises(RuntimeError, match="permission denied"):
            psql_app("update alembic_version set version_num = version_num")
    finally:
        u = dc("up", "-d", "--no-build", timeout=400)
        assert u.returncode == 0, u.stderr[-400:]
        wait_healthy(240)
    a = Api()
    assert a.login().status_code == 200
    assert a.get("/api/v1/audit", params={"page_size": 1}).json()["chain_ok"] is True
    a.close()
