import sys
from pathlib import Path
from datetime import datetime, timezone
from youtube_title.config import load_settings
from ytweb.db.models import Base
from ytweb.db.session import make_engine, make_session_factory
from ytweb.domain.seed import seed_demo
REPO = Path(__file__).resolve().parents[3]
eng = make_engine(sys.argv[1]); Base.metadata.drop_all(eng); Base.metadata.create_all(eng)
with make_session_factory(eng)() as s:
    seed_demo(s, datetime.now(timezone.utc), load_settings(REPO, env={}), count=200); s.commit()
print("seeded")
