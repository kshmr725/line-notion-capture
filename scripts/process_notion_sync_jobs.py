from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brain_portal.config import PortalSettings
from brain_portal.db import PortalRepository, init_portal_db
from brain_portal.embeddings import GeminiEmbeddingProvider
from brain_portal.notion_jobs import process_next_notion_job


def main() -> int:
    settings = PortalSettings()
    database_target = getattr(settings, "database_target", settings.database_path)
    init_portal_db(database_target)
    repository = PortalRepository(database_target)
    embedder = (
        GeminiEmbeddingProvider(settings.gemini_api_key, timeout=settings.ai_timeout_seconds)
        if settings.gemini_api_key.strip()
        else None
    )
    status = process_next_notion_job(settings, repository, embedder)
    print(status or "idle")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
