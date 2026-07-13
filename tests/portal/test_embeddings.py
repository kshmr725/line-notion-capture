import pytest

from brain_portal.embeddings import GeminiEmbeddingProvider, cosine_similarity


class FakeResponse:
    def __init__(self, values):
        self.values = values

    def raise_for_status(self):
        return None

    def json(self):
        return {"embedding": {"values": self.values}}


def test_gemini_embedding_uses_required_model_dimensions_and_task(monkeypatch):
    request = {}

    def fake_post(url, **kwargs):
        request.update(url=url, **kwargs)
        return FakeResponse([0.0] * 768)

    monkeypatch.setattr("brain_portal.embeddings.requests.post", fake_post)
    provider = GeminiEmbeddingProvider("secret", timeout=7)

    vector = provider.embed("x" * 9000, "RETRIEVAL_QUERY")

    assert len(vector) == 768
    assert request["url"].endswith("gemini-embedding-001:embedContent")
    assert request["headers"]["x-goog-api-key"] == "secret"
    assert request["json"]["model"] == "models/gemini-embedding-001"
    assert request["json"]["taskType"] == "RETRIEVAL_QUERY"
    assert request["json"]["outputDimensionality"] == 768
    assert len(request["json"]["content"]["parts"][0]["text"]) == 8000
    assert request["timeout"] == 7
    assert provider.model_id == "models/gemini-embedding-001"


def test_gemini_embedding_rejects_the_wrong_response_dimensions(monkeypatch):
    monkeypatch.setattr(
        "brain_portal.embeddings.requests.post",
        lambda *args, **kwargs: FakeResponse([1.0, 2.0]),
    )

    with pytest.raises(ValueError, match="768 dimensions"):
        GeminiEmbeddingProvider("secret").embed("query", "RETRIEVAL_QUERY")


@pytest.mark.parametrize(
    ("left", "right"),
    [([], [],), ([1.0], [1.0, 2.0]), ([0.0, 0.0], [1.0, 0.0])],
)
def test_cosine_invalid_or_zero_vectors_return_zero(left, right):
    assert cosine_similarity(left, right) == 0.0


def test_cosine_similarity_compares_compatible_vectors():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
