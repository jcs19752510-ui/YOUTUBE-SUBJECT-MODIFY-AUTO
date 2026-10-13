"""DEF-LIVE-006: 화면이 제안기(모의·규칙·Gemini)를 구분하려면 API 응답의 source 가 제안기 이름을 담아야 한다."""
from datetime import datetime, timezone

import pytest

from ytweb.db.models import Suggestion
from ytweb.domain.serialize import suggestion_dict

NOW = datetime(2026, 10, 13, tzinfo=timezone.utc)


@pytest.mark.parametrize("source", ["ai:mock", "ai:rule", "ai:gemini", "ai:gemini+edited", "manual"])
def test_suggestion_source_is_passed_through_unchanged(source):
    s = Suggestion(id=1, video_id="v", title="t", evidence="e", source=source, topic="life", status="candidate", created_at=NOW, updated_at=NOW)
    d = suggestion_dict(s)
    assert d["source"] == source
    assert {"id", "video_id", "title", "evidence", "topic", "strict", "status", "created_at"} <= d.keys()  # 기존 필드 유지


def test_generate_records_provider_in_source():
    """suggestions.py 가 제안 source 를 f"ai:{제안기 이름}" 으로 저장하는 코드가 남아 있어야 한다(화면 구분의 근거)."""
    import inspect
    from ytweb.domain import suggestions
    assert 'f"ai:{suggester.name}"' in inspect.getsource(suggestions)
