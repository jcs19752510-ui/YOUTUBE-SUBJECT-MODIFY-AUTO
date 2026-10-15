import subprocess, sys, shutil, json, time, os
ROOT = "/home/user/youtube-subject-modify-auto/.harness-tmp/vm23/mutwork/web/backend"
PY = "/home/user/youtube-subject-modify-auto/.harness-tmp/venv_fix_be/bin/python"
T = "tests/verify_m23/"
F = lambda *n: [T + x for x in n]
f1, f2, f3, f4, f5, f6, f7, f8, f10 = ("test_vm_01_oauth_core.py", "test_vm_02_google_router.py", "test_vm_03_live_read.py", "test_vm_04_live_sync.py", "test_vm_05_live_write.py", "test_vm_06_live_gateway.py", "test_vm_07_live_e2e.py", "test_vm_08_recovery_live.py", "test_vm_10_wfixbe_and_hints.py")
LW, LG, GO, RG, BA, CH, LS, LR = "ytweb/youtube/live_write.py", "ytweb/domain/live_gateway.py", "ytweb/youtube/google_oauth.py", "ytweb/routers/google.py", "ytweb/domain/batches.py", "ytweb/domain/changes.py", "ytweb/domain/live_sync.py", "ytweb/youtube/live_read.py"
M = [
 ("M01 허용목록 검사 제거(update_snippet)", LW, "if video_id not in self._allowed:", "if False:", [f5, f7]),
 ("M02 허용목록 검사 반전", LW, "if video_id not in self._allowed:", "if video_id in self._allowed:", [f5, f7]),
 ("M03 응답 제목 확인 제거", LW, 'or out.get("title") != snippet["title"]:', "or False:", [f5, f7]),
 ("M04 unconfirmed definite True", LW, "반영 여부를 확인해야 합니다.\", definite=False)\n        return out" if False else '새 제목을 확인하지 못했습니다. 반영 여부를 확인해야 합니다.", definite=False', '새 제목을 확인하지 못했습니다. 반영 여부를 확인해야 합니다.", definite=True', [f5, f7]),
 ("M05 5xx definite True", LW, '서버 오류입니다. 반영 여부를 확인해야 합니다.", definite=False', '서버 오류입니다. 반영 여부를 확인해야 합니다.", definite=True', [f5]),
 ("M06 네트워크 단절 definite True", LW, '연결이 끊겼습니다. 반영 여부를 확인해야 합니다.", definite=False', '연결이 끊겼습니다. 반영 여부를 확인해야 합니다.", definite=True', [f5, f7]),
 ("M07 categoryId 검사 제거", LW, 'if not isinstance(snippet.get("categoryId"), str) or not snippet["categoryId"]:', "if False:", [f5]),
 ("M08 본문 id 일치 검사 제거", LW, 'if body.get("id") != video_id or not isinstance(snippet, dict):', "if not isinstance(snippet, dict):", [f5]),
 ("M09 허용목록 공백/빈칸 처리 제거", LG, "frozenset(v.strip() for v in raw.split(\",\") if v.strip())", "frozenset(v for v in raw.split(\",\"))", [f6]),
 ("M10 LIVE_WRITE 판정 완화", LG, '.get("YTWEB_LIVE_WRITE", "0") == "1"', '.get("YTWEB_LIVE_WRITE", "0") in ("1", "true")', [f6]),
 ("M11 허용목록 비어도 준비됨", LG, "live_write_enabled(env) and bool(allowed_videos(env)) and", "live_write_enabled(env) and", [f6, f7]),
 ("M12 not_allowed_reason 무력화", LG, "video_id not in allowed_videos(env):", "False:", [f6, f7]),
 ("M13 확인 문구 분기 반전", LG, 'return f"{LIVE_CONFIRM_PREFIX} {n}건" if live else f"실행 {n}건"', 'return f"{LIVE_CONFIRM_PREFIX} {n}건" if not live else f"실행 {n}건"', [f6, f7]),
 ("M14 쓰기 게이트웨이가 읽기 토큰 파일 사용", LG, "oauth.TokenStore(secrets_dir / WRITE_TOKEN_FILE)", 'oauth.TokenStore(secrets_dir / "google_token.json")', [f6, f7]),
 ("M15 DB 제목 동기화 제거", LG, 'video.snippet, video.title = copy.deepcopy(out), out["title"]', "video.snippet = copy.deepcopy(out)", [f6, f7]),
 ("M16 state 1회용 해제(pop→get)", GO, 'self._items.pop(state or "", None)', 'self._items.get(state or "", None)', [f1, f2]),
 ("M17 state 만료 경계(>=→>)", GO, "or self._clock() - item[1] >= STATE_TTL_SECONDS:", "or self._clock() - item[1] > STATE_TTL_SECONDS:", [f1]),
 ("M18 대기 한도 20→21", GO, "while len(self._items) >= MAX_PENDING:", "while len(self._items) > MAX_PENDING:", [f1]),
 ("M19 PKCE S256→sha1", GO, "hashlib.sha256(verifier.encode(\"ascii\"))", "hashlib.sha1(verifier.encode(\"ascii\"))", [f1, f2]),
 ("M20 토큰 파일 권한 0600→0644", GO, "os.O_TRUNC, 0o600)", "os.O_TRUNC, 0o644)", [f1, f2]),
 ("M21 기본 scope=쓰기", GO, "challenge: str, scope: str = SCOPE_READ)", "challenge: str, scope: str = SCOPE_WRITE)", [f1, f2]),
 ("M22 갱신 시 refresh 토큰 유실", GO, 'refresh = resp.get("refresh_token") or keep_refresh', 'refresh = resp.get("refresh_token")', [f1, f3]),
 ("M23 만료 여유 60초 제거", GO, "- timedelta(seconds=margin_seconds) > now", "- timedelta(seconds=0) > now", [f1]),
 ("M24 쓰기 콜백이 읽기 저장소로", RG, "if is_write and ctx.write_store is not None:", "if False:", [f2, f6, f7]),
 ("M25 connect-write 가 읽기 scope", RG, "state, challenge, scope=oauth.SCOPE_WRITE)", "state, challenge)", [f2]),
 ("M26 쓰기 state 소진 제거", RG, "ctx.write_states.discard(state)\n", "pass\n", [f2]),
 ("M27 해제 시 쓰기 토큰 유지", RG, "        ctx.write_store.clear()\n", "        pass\n", [f2]),
 ("M28 감사 기록에 접근 토큰 포함", RG, 'action="google.connected", detail={"scope": tokens.get("scope", "")}', 'action="google.connected", detail={"scope": tokens.get("scope", ""), "t": tokens["access_token"]}', [f2, f7]),
 ("M29 확인 문구 실제 모드 무시", BA, "live_gateway.confirm_text(len(items), live_gateway.live_mode(env.secrets_dir))", "live_gateway.confirm_text(len(items), False)", [f7]),
 ("M30 초안 단계 허용목록 차단 제거", BA, "    if not_allowed:\n        return \"live_not_allowed\", not_allowed", "    if False:\n        return \"live_not_allowed\", not_allowed", [f7]),
 ("M31 반영 직전 허용목록 차단 제거", BA, "    if not_allowed:\n        raise StepFailure(\"live_not_allowed\", not_allowed)", "    if False:\n        raise StepFailure(\"live_not_allowed\", not_allowed)", [f7]),
 ("M32 롤백 허용목록 차단 제거", CH, "    if not_allowed:\n        raise ProblemError(409, \"live_not_allowed\"", "    if False:\n        raise ProblemError(409, \"live_not_allowed\"", [f7]),
 ("M33 반영 변경 기록 mode 항상 demo", BA, 'result="planned", mode="live" if live_gateway.is_live(gateway) else "demo", created_at=now,', 'result="planned", mode="demo", created_at=now,', [f7]),
 ("M34 데모 기록 있어도 삭제 진행", LS, "    if used:\n        raise ProblemError(409", "    if False:\n        raise ProblemError(409", [f4]),
 ("M35 변경 이력 영상 보존 해제", LS, "if v.video_id not in touched:", "if True:", [f4]),
 ("M36 Shorts 경계(<=→<)", LS, "v.duration_sec <= policy.shorts_max_seconds", "v.duration_sec < policy.shorts_max_seconds", [f4]),
 ("M37 videos.list 묶음 50→51", LR, "BATCH = 50", "BATCH = 51", [f3]),
 ("M38 목록 쪽 상한 40→41", LR, "MAX_PAGES = 40", "MAX_PAGES = 41", [f3]),
 ("M39 영상 ID 중복 제거 해제", LR, "ids = list(dict.fromkeys(self.video_ids(self.uploads_playlist())))", "ids = list(self.video_ids(self.uploads_playlist()))", [f3]),
 ("M40 401 오류 번역 제거", LR, "if e.code == 401:", "if e.code == 40100:", [f3]),
 ("M41 실제 모드 경고 맨 앞 삽입 해제", BA, "warnings.insert(0, f\"실제 모드입니다.", "warnings.append(f\"실제 모드입니다.", [f7]),
 ("M42 초안 취소 was_draft 기록 오류", BA, '"cancelled_items": cancelled, "was_draft": was_draft}', '"cancelled_items": cancelled, "was_draft": False}', [f10]),
 ("M43 모호 응답 후 재조회 확인 생략", BA, 'if snap is None or snap.get("title") != new_title:', "if False:", [f7]),
 ("M44 복구 시 이중 반영 방지(planned 유지) 해제", BA, "state.keep_planned = True\n        raise StepFailure(\"result_unknown\"", "raise StepFailure(\"result_unknown\"", [f7]),
 ("M45 chmod 0600→0644(교체 후)", GO, "os.chmod(self.path, 0o600)", "os.chmod(self.path, 0o644)", [f1, f2]),
 ("M46 os.open·chmod 모두 0644", GO, ["os.O_TRUNC, 0o600)", "os.chmod(self.path, 0o600)"], ["os.O_TRUNC, 0o644)", "os.chmod(self.path, 0o644)"], [f1, f2]),
 ("M47 롤백 확인 문구 대신 영상 ID 입력 검사 제거", CH, "if typed_video_id != target.video_id:", "if False:", [f7]),
 ("M48 롤백 mode 항상 demo", CH, 'mode="live" if live_gateway.is_live(gateway) else "demo"', 'mode="demo"', [f7]),
]
only = sys.argv[1:] 
results = []
for name, path, old, new, files in M:
    tag = name.split()[0]
    if only and tag not in only: continue
    p = os.path.join(ROOT, path)
    orig = open(p, encoding="utf-8").read()
    olds, news = (old, new) if isinstance(old, list) else ([old], [new])
    n = min(orig.count(o) for o in olds)
    if n < 1:
        results.append((name, "APPLY-FAIL", f"문자열 {n}회")); print(name, "APPLY-FAIL", n, flush=True); continue
    mut = orig
    for o, nw in zip(olds, news):
        mut = mut.replace(o, nw, 1)
    open(p, "w", encoding="utf-8").write(mut)
    try:
        t0 = time.time()
        r = subprocess.run([PY, "-m", "pytest", *["tests/verify_m23/" + x for x in files], "-p", "no:cacheprovider", "-o", "addopts=", "-q", "-x", "-W", "ignore"], cwd=ROOT, capture_output=True, text=True, timeout=500)
        killed = r.returncode != 0
        last = [l for l in r.stdout.splitlines() if l.startswith("FAILED") or "passed" in l or "failed" in l]
        results.append((name, "KILLED" if killed else "SURVIVED", (last[0] if last else "")[:160]))
        print(name, "KILLED" if killed else "SURVIVED", f"{time.time()-t0:.0f}s", (last[0] if last else "")[:140], flush=True)
    finally:
        open(p, "w", encoding="utf-8").write(orig)
json.dump(results, open("/home/user/youtube-subject-modify-auto/.harness-tmp/vm23/mutation_results.json", "w"), ensure_ascii=False, indent=1)
print("DONE", sum(1 for r in results if r[1] == "KILLED"), "/", len(results))
