import math

import requests


class GeminiEmbeddingProvider:
    model_id = "models/gemini-embedding-001"
    dimensions = 768

    def __init__(self, api_key: str, timeout: int = 25):
        self.api_key = api_key
        self.timeout = timeout

    def embed(self, text: str, task_type: str) -> list[float]:
        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-embedding-001:embedContent",
            headers={
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            json={
                "model": self.model_id,
                "taskType": task_type,
                "outputDimensionality": self.dimensions,
                "content": {"parts": [{"text": text[:8000]}]},
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        vector = [float(value) for value in response.json()["embedding"]["values"]]
        if len(vector) != self.dimensions:
            raise ValueError("Gemini embedding response must have 768 dimensions")
        return vector


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(
        sum(value * value for value in right)
    )
    if not denominator:
        return 0.0
    return sum(x * y for x, y in zip(left, right)) / denominator
