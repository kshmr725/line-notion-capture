#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brain_portal.config import PortalSettings
from brain_portal.connectors.notion import NotionConnector
from brain_portal.connectors.obsidian import ObsidianConnector
from brain_portal.db import PortalRepository, init_portal_db
from brain_portal.embeddings import GeminiEmbeddingProvider
from brain_portal.indexer import run_index


def _build_connector(args: argparse.Namespace, settings: PortalSettings):
    if args.obsidian_root:
        return ObsidianConnector(args.obsidian_root)
    return NotionConnector(
        token=settings.notion_token,
        database_id=args.notion_connection,
        api_version=settings.notion_api_version,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Index Brain Cloud Portal sources")
    parser.add_argument("--tenant", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--obsidian-root")
    source.add_argument("--notion-connection")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--database", default=None)
    args = parser.parse_args(argv)

    settings = PortalSettings()
    database_path = args.database or settings.database_path
    connector = _build_connector(args, settings)

    if args.dry_run:
        documents = list(connector.iter_documents(args.tenant))
        print(
            json.dumps(
                {"tenant": args.tenant, "dry_run": True, "would_index": len(documents)},
                indent=2,
            )
        )
        return 0

    gemini_key = settings.gemini_api_key.strip()
    if not gemini_key:
        print("GEMINI_API_KEY is required to index (embeddings)", file=sys.stderr)
        return 1

    init_portal_db(database_path)
    repo = PortalRepository(database_path)
    embedder = GeminiEmbeddingProvider(gemini_key, timeout=settings.ai_timeout_seconds)

    report = run_index(args.tenant, connector, repo, embedder)
    print(
        json.dumps(
            {
                "tenant": args.tenant,
                "indexed": report.indexed,
                "unchanged": report.unchanged,
                "deleted": report.deleted,
                "failed": report.failed,
            },
            indent=2,
        )
    )
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
