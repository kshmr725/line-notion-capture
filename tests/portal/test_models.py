import pytest

from brain_portal.models import CitedAnswer


def test_cited_answer_requires_at_least_one_source():
    with pytest.raises(ValueError, match="at least one source_id is required"):
        CitedAnswer(text="Unsupported", source_ids=(), provider="test")
