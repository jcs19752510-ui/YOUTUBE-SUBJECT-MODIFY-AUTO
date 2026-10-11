"""7단계 통합 시험 B 트랙: 변이 점검기. 원본을 건드리지 않고 .harness-tmp/int_b/mut/<ID>/ 아래 격리 사본에 변이 1곳을 넣어
네이티브 스택(api·워커를 그 사본 코드로 기동)에서 통합 시험의 지정 부분집합이 실패하는지(=변이를 잡았는지) 본다.

사용:  python mutate_b.py <회전번호> [ID ...]      (ID 생략 시 전부)   결과는 .harness-tmp/int_b/mut/results_r<회전>.json
규칙: 대상 문자열이 원본에 정확히 1곳이어야 한다(아니면 INVALID). 시험 프로세스의 종료 코드 0 이면 SURVIVED, 1 이면 KILLED.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROOT = Path(os.environ.get("IT_B_ROOT", str(REPO / ".harness-tmp" / "int_b")))
MUT = ROOT / "mut"
RUN = ROOT / "runb.sh"

# (ID, 설명, 파일(저장소 기준), 원문, 변이, 시험 파일, -k 식)
S = "web/backend/ytweb/"
MUTATIONS = [
    ("M01", "승인 1회용 검사 제거", S + "domain/suggestions.py", "if ap.used_at is not None:", "if False and ap.used_at is not None:", "test_it_02_scenarios.py", "112 or 110"),
    ("M02", "승인 만료 검사 제거", S + "domain/suggestions.py", "if ref_time >= ap.expires_at:", "if False:", "test_it_02_scenarios.py", "112 or 102"),
    ("M03", "승인 HMAC 변조 검사 제거", S + "domain/suggestions.py", "if not hmac.compare_digest(expected, ap.mac):", "if False:", "test_it_02_scenarios.py", "112"),
    ("M04", "승인 계획 해시의 영상 정보 대조 제거", S + "domain/suggestions.py", "if sug.plan_hash != ap.plan_hash or plan_hash_for(sug, video, snap) != ap.plan_hash:", "if sug.plan_hash != ap.plan_hash:", "test_it_02_scenarios.py", "112 or 114"),
    ("M05", "승인 유효 시간 2배", S + "domain/suggestions.py", "ttl = timedelta(hours=env.policy.approval_ttl_hours)", "ttl = timedelta(hours=env.policy.approval_ttl_hours * 2)", "test_it_02_scenarios.py", "100"),
    ("M06", "실행 확인 문구 검사 제거", S + "domain/batches.py", "if confirm_text != expected:", "if False:", "test_it_02_scenarios.py", "100 or 104"),
    ("M07", "배치 이중 실행 방지(draft 검사) 제거", S + "domain/batches.py", 'if batch.status != "draft":', "if False:", "test_it_02_scenarios.py", "104 or 105"),
    ("M08", "다른 배치에 담긴 제안 점검 제거", S + "domain/batches.py", "if problem is None and _active_item(session, sid) is not None:", "if False:", "test_it_03_state.py", "307"),
    ("M09", "예약일 배정에서 오늘 반영 수 무시", S + "domain/batches.py", "used = (applied_today(session, now) + overdue) if offset == 0 else future.get(day, 0)", "used = overdue if offset == 0 else future.get(day, 0)", "test_it_02_scenarios.py", "113"),
    ("M10", "워커 틱의 오늘 남은 상한 계산에서 반영 수 무시", S + "domain/batches.py", "remaining = effective_daily_cap(s, env.policy) - applied_today(s, now)", "remaining = effective_daily_cap(s, env.policy)", "test_it_02_scenarios.py", "103b"),
    ("M11", "한도 초과분 이월 대신 건너뜀", S + "domain/batches.py", 'if all(c.code == "DAILY" for c in report.failures):', "if False:", "test_it_03_state.py", "331"),
    ("M12", "배치 취소 시 제안 복귀 제거", S + "domain/batches.py", "            release_after_item(sug, session.get(Video, it.video_id), env, now, batch.executed_at or now)", "            pass", "test_it_02_scenarios.py", "105 or 113"),
    ("M13", "실행 확정 시 제안을 queued 로 바꾸지 않음", S + "domain/batches.py", 'sug.status, sug.updated_at = "queued", now', "sug.updated_at = now", "test_it_02_scenarios.py", "100 or 115"),
    ("M14", "반영 시 승인 소진(used_at) 기록 제거", S + "domain/batches.py", "ap.used_at = now", "pass", "test_it_02_scenarios.py", "100"),
    ("M15", "미확정 변경(planned) 존재 검사 무력화", S + "domain/batches.py", '.where(Change.video_id == video.video_id, Change.result == "planned").limit(1)).first()', '.where(Change.video_id == video.video_id, Change.result == "planned_x").limit(1)).first()', "test_it_02_scenarios.py", "112"),
    ("M16", "승인 만료 기준 시각을 확정 시각 대신 현재로", S + "domain/batches.py", "ref_time = batch.executed_at or now", "ref_time = now", "test_it_02_scenarios.py", "102"),
    ("M17", "롤백: 이후 변경 존재 거부 제거", S + "domain/changes.py", "if later is not None:", "if False:", "test_it_02_scenarios.py", "111"),
    ("M18", "롤백: 영상 ID 직접 입력 확인 제거", S + "domain/changes.py", "if typed_video_id != target.video_id:", "if False:", "test_it_02_scenarios.py", "100 or 106"),
    ("M19", "롤백: 이미 원래 제목 검사 제거", S + "domain/changes.py", 'if current.get("title") == restore_title:', "if False:", "test_it_02_scenarios.py", "106"),
    ("M20", "롤백 가능 표시를 항상 참으로", S + "domain/changes.py", "latest.get(c.video_id) == c.id", "True", "test_it_02_scenarios.py", "106 or 111"),
    ("M21", "멱등성: 같은 키 다른 본문 검사 제거", S + "core/idempotency.py", "if row.route != route or row.request_hash != request_hash:", "if row.route != route:", "test_it_02_scenarios.py", "104"),
    ("M22", "멱등성 키 보관 24시간 -> 240시간", S + "core/idempotency.py", "KEY_TTL = timedelta(hours=24)", "KEY_TTL = timedelta(hours=240)", "test_it_03_state.py", "304"),
    ("M23", "응답 후 commit 수정 되돌림(응답 전 commit 제거)", S + "core/guard.py", "await anyio.to_thread.run_sync(db_session.commit)", "pass", "test_it_03_state.py", "301 or 316 or 300"),
    ("M24", "PIN 실패 카운터 직렬화(어드바이저리 락) 제거", S + "core/pin.py", 'db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _ADVISORY_LOCK_KEY})', "pass", "test_it_03_state.py", "305"),
    ("M25", "감사 로그 체인 직렬화(어드바이저리 락) 제거", S + "core/audit.py", 'session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _ADVISORY_LOCK_KEY})', "pass", "test_it_04_contract.py", "426"),
    ("M26", "PIN 변경 시 다른 세션 폐기 제거", S + "routers/settings.py", "delete_other_sessions(db, info.session_id)", "pass", "test_it_02_scenarios.py", "108"),
    ("M27", "쿼터 경계: 사용+필요==상한도 거부", S + "domain/limits_quota.py", "if used + need > policy.daily_limit_units:", "if used + need >= policy.daily_limit_units:", "test_it_02_scenarios.py", "106"),
    ("M28", "재동기화가 앱이 바꾼 제목을 되돌림", S + "domain/seed.py", "if vid not in touched:", "if True:", "test_it_02_scenarios.py", "100 or 114"),
    ("M29", "PIN 잠금 시작 횟수 5 -> 6", S + "core/pin.py", 'if st["count"] >= MAX_FAILURES:', 'if st["count"] > MAX_FAILURES:', "test_it_03_state.py", "305"),
    ("M30", "교체 한도 72시간 간격 -> 69시간", "src/ytitle/limits.py", "if now >= ready:", "if now >= ready - timedelta(hours=3):", "test_it_02_scenarios.py", "111"),
    ("M31", "교체 한도 횟수 경계(<= 로 완화)", "src/ytitle/limits.py", "if facts.change_count < cap:", "if facts.change_count <= cap:", "test_it_02_scenarios.py", "111"),
    ("M32", "승인 만료 정리(expire_stale) 기준 완화", S + "domain/suggestions.py", "Approval.expires_at <= now", "Approval.expires_at <= now - timedelta(days=30)", "test_it_02_scenarios.py", "102"),
    ("M33", "CSV 수식 무력화 접두 범위 축소", S + "domain/reports.py", '_FORMULA_START = ("=", "+", "-", "@", "\\t", "\\r")', '_FORMULA_START = ("=",)', "test_it_02_scenarios.py", "107"),
    ("M34", "영상 불러오기 연타 방지 제거", S + "routers/videos.py", "if active is not None:", "if False:", "test_it_03_state.py", "317"),
    ("M35", "롤백: 적용 성공이 아닌 변경 거부 제거", S + "domain/changes.py", 'if target.change_type != "apply" or target.result != "success":', "if False:", "test_it_02_scenarios.py", "106"),
    ("M36", "워커: 제안 상태(queued) 재검증 제거", S + "domain/batches.py", 'if sug.status != "queued":', "if False:", "test_it_02_scenarios.py", "112"),
    ("M37", "승인자 이름 길이 제한 제거", S + "domain/common.py", "if len(name) > MAX_APPROVER_CHARS", "if len(name) > 4000", "test_it_04_contract.py", "402"),
    ("M38", "배치 상태: 대기 항목이 없으면 진행 중 항목이 있어도 done", S + "domain/batches.py", 'if c["pending"] == 0 and c["running"] == 0:', 'if c["pending"] == 0:', "test_it_03_state.py", "321 or 310"),
    ("M39", "배치 취소: 끝난(done) 배치도 취소 허용", S + "domain/batches.py", 'if batch.status in ("cancelled", "done"):', 'if batch.status in ("cancelled",):', "test_it_02_scenarios.py", "105"),
    ("M43", "대시보드 다음 실행일에서 과거 보정 제거", S + "domain/dashboard.py", "next_run = max(pending[1], today) if pending[1] is not None else None", "next_run = pending[1]", "test_it_03_state.py", "331"),
    ("M44", "저장된 하루 상한이 범위 밖이어도 그대로 사용", S + "core/settings_store.py", "if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 20:", "if False:", "test_it_02_scenarios.py", "109"),
    ("M45", "PIN 잠금 시간이 늘어나지 않음", S + "core/pin.py", 'lock = min(BASE_LOCK * (2 ** st["lockouts"]), MAX_LOCK)', "lock = BASE_LOCK", "test_it_03_state.py", "305"),
    ("M47", "세션 만료 검사 제거", S + "core/sessions.py", "if row.expires_at <= now:", "if False:", "test_it_03_state.py", "350"),
    ("M48", "세션 최대 개수 20 -> 21", S + "core/sessions.py", "for old in active[MAX_ACTIVE_SESSIONS - 1:]:", "for old in active[MAX_ACTIVE_SESSIONS:]:", "test_it_03_state.py", "350"),
    ("M49", "출처 불명 요청도 소유자 속도 제한에 합산", S + "core/guard.py", "wait = self.limiter.check_foreign() if self._is_foreign(method, req_headers) else self.limiter.check(method, path)", "wait = self.limiter.check(method, path)", "test_it_04_contract.py", "431"),
    ("M50", "멱등성: 업무 오류 뒤 키 자리 정리 제거", S + "domain/deps.py", "session.execute(delete(IdempotencyKey).where(IdempotencyKey.key == key, IdempotencyKey.response_status.is_(None)))", "pass", "test_it_04_contract.py", "430"),
    ("M54", "목록 페이지 시작 위치 오류(page 를 1 쪽 앞으로)", S + "domain/videos.py", "start = (page - 1) * page_size", "start = page * page_size", "test_it_04_contract.py", "425"),
    ("M56", "재동기화가 변경 전 성과 기준선을 다시 만듦", S + "domain/seed.py", "if metrics is not None and vid not in have_snapshot:", "if metrics is not None:", "test_it_02_scenarios.py", "100"),
    ("M58", "롤백 후 제안 상태를 rolled_back 으로 바꾸지 않음", S + "domain/changes.py", 'if sug is not None and sug.status == "applied":', "if False:", "test_it_02_scenarios.py", "115"),
    ("M60", "배치 최대 크기 50 -> 500", S + "domain/batches.py", "if len(suggestion_ids) > MAX_BATCH_ITEMS:", "if len(suggestion_ids) > 500:", "test_it_02_scenarios.py", "118"),
    # ── 2회전 전 추가(워커 상한 계산 · 멱등성 저장 · 작업 큐) ──
    ("W01", "워커 틱: 오늘 남은 상한 0 이하 판정을 음수에서만(< 0)", S + "domain/batches.py", "            if remaining <= 0:", "            if remaining < 0:", "test_it_03_state.py", "332"),
    ("W02", "워커 틱: 오늘 도래분을 '이전 날짜'만으로 좁힘", S + "domain/batches.py", "BatchItem.scheduled_date <= today,", "BatchItem.scheduled_date < today,", "test_it_03_state.py", "330 or 332"),
    ("W03", "이월 예정일을 내일이 아니라 모레로", S + "domain/batches.py", 'item.status, item.scheduled_date, item.updated_at = "pending", kst_today(now) + timedelta(days=1), now', 'item.status, item.scheduled_date, item.updated_at = "pending", kst_today(now) + timedelta(days=2), now', "test_it_03_state.py", "332"),
    ("W04", "오늘 반영 수에서 진행 중(planned) 제외", S + "domain/limits_quota.py", 'COUNTED_RESULTS = ("success", "planned")', 'COUNTED_RESULTS = ("success",)', "test_it_03_state.py", "330 or 332 or 310"),
    ("W05", "반영 직전 어드바이저리 락(워커 직렬화) 제거", S + "domain/batches.py", 'session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _APPLY_LOCK_KEY})', "pass", "test_it_03_state.py", "330 or 331"),
    ("W06", "쿼터 선예약 어드바이저리 락 제거", S + "domain/limits_quota.py", 'session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _QUOTA_LOCK_KEY})', "pass", "test_it_03_state.py", "330 or 331"),
    ("W07", "작업 큐 SKIP LOCKED 제거(워커 둘이 같은 작업을 잡음)", S + "core/jobs.py", "stmt = stmt.with_for_update(skip_locked=True)", "pass", "test_it_03_state.py", "303"),
    ("I01", "멱등성: 저장하는 응답 상태 코드를 항상 200 으로", S + "core/idempotency.py", "    row.response_status = status", "    row.response_status = 200", "test_it_03_state.py", "302 or 304 or 313"),
    ("I02", "멱등성: 저장하는 응답 본문을 빈 객체로", S + "core/idempotency.py", "    row.response_body = encoded", "    row.response_body = {}", "test_it_03_state.py", "302 or 304 or 313"),
    ("I03", "멱등성 키 정리 보관 48시간 -> 1초", S + "worker.py", "IDEMPOTENCY_RETENTION = timedelta(hours=48)", "IDEMPOTENCY_RETENTION = timedelta(seconds=1)", "test_it_03_state.py", "304 or 313"),
    ("I04", "멱등성 키 형식 최소 길이 8 -> 1", S + "core/idempotency.py", r'_KEY_RE = re.compile(r"[A-Za-z0-9._:\-]{8,80}")', r'_KEY_RE = re.compile(r"[A-Za-z0-9._:\-]{1,80}")', "test_it_04_contract.py", "402 or 403 or 430"),
    ("I05", "멱등성: 빈 키 헤더를 키 없음으로 취급하지 않음", S + "core/idempotency.py", 'if key is None or key == "":', "if key is None:", "test_it_04_contract.py", "402 or 403 or 430"),
    ("I06", "멱등성: 동시 삽입 충돌을 진행 중(409)이 아니라 그냥 통과", S + "core/idempotency.py", "    except IntegrityError:\n        session.rollback()\n        raise ProblemError(409, \"idempotency_in_progress\", \"같은 키의 요청이 동시에 처리 중입니다.\",\n                           hint=\"잠시 후 같은 요청을 다시 보내세요.\") from None", "    except IntegrityError:\n        session.rollback()\n        raise ProblemError(500, \"idempotency_in_progress\", \"같은 키의 요청이 동시에 처리 중입니다.\",\n                           hint=\"잠시 후 같은 요청을 다시 보내세요.\") from None", "test_it_03_state.py", "302 or 304"),
]


def run(round_no: int, only: list[str]) -> None:
    MUT.mkdir(parents=True, exist_ok=True)
    out_path = MUT / f"results_r{round_no}.json"
    results = json.loads(out_path.read_text()) if out_path.exists() else {}
    for mid, desc, rel, old, new, test_file, kexpr in MUTATIONS:
        if only and mid not in only:
            continue
        src_file = REPO / rel
        text = src_file.read_text(encoding="utf-8")
        if text.count(old) != 1:
            results[mid] = {"desc": desc, "status": "INVALID", "why": f"원문 {text.count(old)}곳"}
            out_path.write_text(json.dumps(results, ensure_ascii=False, indent=1))
            continue
        d = MUT / mid
        if d.exists():
            shutil.rmtree(d)
        (d / "backend").mkdir(parents=True)
        shutil.copytree(REPO / "web/backend/ytweb", d / "backend" / "ytweb", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(REPO / "web/backend/alembic", d / "backend" / "alembic")
        for f in ("alembic.ini", "pyproject.toml"):
            shutil.copy2(REPO / "web/backend" / f, d / "backend" / f)
        (d / "src").mkdir()
        shutil.copytree(REPO / "src/ytitle", d / "src" / "ytitle", ignore=shutil.ignore_patterns("__pycache__"))
        target = d / rel.replace("web/backend/", "backend/") if rel.startswith("web/backend/") else d / rel
        target.write_text(text.replace(old, new), encoding="utf-8")
        assert (d / rel.replace("web/backend/", "backend/")).read_text(encoding="utf-8").count(new) >= 1
        env = {**os.environ, "IT_B_BACKEND": str(d / "backend"), "IT_B_SRC": str(d / "src")}
        t0 = time.time()
        p = subprocess.run([str(RUN), test_file, "-k", kexpr, "-x", "-q"], env=env, capture_output=True, text=True, timeout=3000)
        tail = (p.stdout + p.stderr)[-1800:]
        status = "SURVIVED" if p.returncode == 0 else ("KILLED" if p.returncode == 1 else f"ERROR({p.returncode})")
        failed = [ln.split("::")[-1].split(" ")[0] for ln in p.stdout.splitlines() if ln.startswith("FAILED")]
        why = [ln.strip()[:200] for ln in p.stdout.splitlines() if ln.startswith("E ")][:3]
        results[mid] = {"desc": desc, "status": status, "tests": f"{test_file} -k '{kexpr}'", "killed_by": failed[:3], "why": why, "secs": round(time.time() - t0), "tail": tail if status.startswith("ERROR") else ""}
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=1))
        print(mid, status, failed[:2], flush=True)
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    rn = int(sys.argv[1])
    run(rn, sys.argv[2:])
