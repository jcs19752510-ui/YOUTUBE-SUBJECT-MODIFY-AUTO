"""validate: 제목 후보 검증 리포트(EVT-003, FR-005, SCR-002)."""
from __future__ import annotations

import json
from pathlib import Path

from youtube_title.banned_terms import load_dictionary
from youtube_title.candidates import list_candidate_files, load_candidate_file
from youtube_title.errors import InputError
from youtube_title.textsafe import sanitize_for_display
from youtube_title.timeutil import utc_iso
from youtube_title.ui import badge, footer, render_table, title_line
from youtube_title.validator import FileResult, validate_file

NAME = "validate"
_STATUS = {"pass": "filtered", "warn": "filtered", "block": "blocked"}


def register(sub, parent):
    p = sub.add_parser("validate", parents=[parent], help="제목 후보 검증(통과/경고/차단)", description="candidates 폴더의 후보 파일을 규칙(길이·금칙어·영상 일치·엄격 모드)으로 검사하고 결과를 기록합니다. 실제 수정은 하지 않습니다.")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--file", help="검사할 후보 파일(candidates/영상ID.json)")
    g.add_argument("--all", action="store_true", help="candidates 폴더의 모든 후보 파일을 검사")
    p.set_defaults(func=run)


def _description_from_db(conn, video_id: str) -> str | None:
    row = conn.execute("SELECT description_excerpt FROM videos WHERE video_id = ?", (video_id,)).fetchone()
    return row["description_excerpt"] if row and row["description_excerpt"] else None


def record(conn, cf, fr: FileResult, now) -> list[int]:
    """검증 결과를 title_candidates에 기록한다. 같은 파일 내용이면 갱신하고, 이미 승인 이후 단계인 행은 건드리지 않는다."""
    ids = []
    stamp = utc_iso(now)
    with conn:
        for cand, res in zip(cf.candidates, fr.results):
            row = conn.execute("SELECT id, status FROM title_candidates WHERE video_id = ? AND candidate_title = ? AND file_sha256 = ?", (cf.video_id, cand.title, cf.sha256)).fetchone()
            reasons = json.dumps([[x.code, x.severity, x.message] for x in res.findings], ensure_ascii=False)
            if row and row["status"] not in ("candidate", "filtered", "blocked"):
                ids.append(row["id"])
                continue
            vals = (res.result, reasons, fr.dictionary_hash, cf.file_name, _STATUS[res.result], stamp)
            if row:
                conn.execute("UPDATE title_candidates SET validation_result=?, validation_reasons_json=?, dictionary_hash=?, file_name=?, status=?, updated_at=?, strict_mode=? WHERE id=?", vals + (int(res.strict), row["id"]))
                ids.append(row["id"])
            else:
                cur = conn.execute(
                    "INSERT INTO title_candidates (video_id, candidate_title, evidence, source, topic, strict_mode, validation_result, validation_reasons_json, dictionary_hash, file_name, file_sha256, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (cf.video_id, cand.title, cand.evidence, cf.source, cf.topic, int(res.strict), res.result, reasons, fr.dictionary_hash, cf.file_name, cf.sha256, _STATUS[res.result], stamp, stamp),
                )
                ids.append(cur.lastrowid)
    return ids


def _print_report(ctx, cf, fr: FileResult, ids: list[int]) -> None:
    ctx.say(f"영상: {cf.video_id}  현재 제목: {sanitize_for_display(cf.current_title)}")
    topic = {"life": "생활", "health": "건강", "finance": "금융", None: "미지정"}[fr.topic]
    ctx.say(f"주제: {topic}  금칙어 사전: v{fr.dictionary_version} (해시 {fr.dictionary_hash})  영상 설명: {'사용함' if fr.description_used else '설명 미사용(요약만으로 비교)'}")
    if fr.strict:
        ctx.say(f"{badge('caution', ctx.ui)} 엄격 모드: 경고도 차단으로 처리합니다. 이유: {' / '.join(fr.strict_reasons)}")
    rows = []
    for i, (cid, r) in enumerate(zip(ids, fr.results), 1):
        reason = "; ".join(x.message for x in r.findings) or "-"
        ratio = "-" if r.match_ratio is None else f"{r.match_ratio:.0%}"
        rows.append([cid, r.length, badge(r.result, ctx.ui), ratio, r.title, reason])
    ctx.say(render_table(["후보번호", "글자수", "결과", "일치율", "제목", "사유"], rows, ctx.ui))


def run(args, ctx) -> int:
    s = ctx.settings
    if not args.file and not args.all:
        raise InputError("검사할 후보를 지정하지 않았습니다.", "`validate --file candidates/영상ID.json` 또는 `validate --all`을 실행하세요.")
    dictionary = load_dictionary(s.config_dir / "banned_terms.yaml")
    # 상대 경로는 현재 폴더가 아니라 프로젝트 폴더(--base-dir) 기준으로 해석한다
    paths = [Path(args.file) if Path(args.file).is_absolute() else s.base_dir / args.file] if args.file else list_candidate_files(s.candidates_dir)
    ctx.say(title_line("validate", False))
    if not paths:
        ctx.say(f"검사할 후보 파일이 없습니다. `{s.candidates_dir}` 폴더에 `영상ID.json` 파일을 만드세요(형식: docs/yt/DESIGN.md EVT-201).")
        ctx.say(footer())
        return 0
    totals = {"pass": 0, "warn": 0, "block": 0}
    for path in paths:
        cf = load_candidate_file(path, s.candidates_dir)
        fr = validate_file(cf, dictionary, s, description=_description_from_db(ctx.conn, cf.video_id) if cf.description_excerpt is None else None)
        ids = record(ctx.conn, cf, fr, ctx.clock.now())
        _print_report(ctx, cf, fr, ids)
        for r in fr.results:
            totals[r.result] += 1
        ctx.say("")
    ctx.say(f"요약: {badge('pass', ctx.ui)} {totals['pass']}건  {badge('warn', ctx.ui)} {totals['warn']}건  {badge('block', ctx.ui)} {totals['block']}건")
    ctx.say(footer())
    return 0
