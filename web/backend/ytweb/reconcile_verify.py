"""실제 모드에서 '반영은 됐는데 재조회가 이전 제목을 줘서 실패로 남은' 항목을 다시 확인해 바로잡는다: `python -m ytweb.reconcile_verify [배치번호]`.
유튜브의 현재 제목이 새 제목과 같고 보존 항목도 같으면 항목을 성공으로 고친다. 다르면 그대로 둔다. 유튜브에는 아무것도 쓰지 않는다(읽기만)."""
from __future__ import annotations

import sys
from datetime import datetime, timezone

from ytweb.config import load_web_settings
from ytweb.db.session import make_engine, make_session_factory
from ytweb.domain import live_gateway
from ytweb.domain.batches import reconcile_verify_failed


def main(argv: list[str]) -> int:
    factory = make_session_factory(make_engine(load_web_settings().database_url))
    now = datetime.now(timezone.utc)
    with factory() as s:
        gw = live_gateway.select_gateway(s, now)
        if not live_gateway.is_live(gw):
            print("실제 모드가 아니라 아무것도 하지 않았습니다.")
            return 1
        rows = reconcile_verify_failed(s, gw, now, int(argv[0]) if argv else None)
        s.commit()
    for iid, msg in rows or [(0, "대상 없음")]:
        print(f"항목 #{iid}: {msg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
