"""최근 변경(changes)의 반영 후 검증 결과를 보여 준다(읽기 전용): `python -m ytweb.change_report [변경번호]`.
어떤 보존 항목(설명·태그·카테고리·언어)이나 제목이 달라서 verify_failed 가 됐는지 알려 준다. 값 자체(설명 전문 등)는 출력하지 않는다."""
from __future__ import annotations

import sys

from sqlalchemy import select

from ytweb.config import load_web_settings
from ytweb.db.models import Change
from ytweb.db.session import make_engine, make_session_factory, session_scope


def main(argv: list[str]) -> int:
    factory = make_session_factory(make_engine(load_web_settings().database_url))
    with session_scope(factory) as s:
        stmt = select(Change).order_by(Change.id.desc())
        if argv:
            stmt = select(Change).where(Change.id == int(argv[0]))
        changes = s.execute(stmt.limit(1 if argv else 3)).scalars().all()
        if not changes:
            print("변경 기록이 없습니다.")
            return 0
        for c in changes:
            v = c.verify_result or {}
            print(f"--- 변경 #{c.id} | 영상 {c.video_id} | 방식 {c.mode} | 결과 {c.result} | 오류코드 {c.error_code or '-'} ---")
            print(f"이전 제목: {c.previous_title}")
            print(f"새 제목:   {c.new_title}")
            print(f"재조회 확인 여부: {v.get('checked')}  제목 일치: {v.get('title_ok')}")
            print("보존 항목 일치:", {k: ("같음" if ok else "다름") for k, ok in (v.get("preserved") or {}).items()})
            print("그 밖에 달라진 항목:", v.get("other_changed"))
            print("달라진 항목 상세(길이·처음 달라진 위치·글자 코드):", v.get("diff_detail"))
            if v.get("reason"):
                print("사유:", v["reason"])
            bs = c.backup_snippet or {}
            print("반영 전 보존 항목 길이:", {k: (len(bs[k]) if isinstance(bs.get(k), (str, list)) else bs.get(k)) for k in ("description", "tags", "categoryId", "defaultLanguage", "defaultAudioLanguage") if k in bs})
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
