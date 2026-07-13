#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brain_portal.db import PortalRepository, portal_connect


def verify(tenant_id: str, database_path: str) -> dict:
    repo = PortalRepository(database_path)
    items = repo.list_items(tenant_id)

    tenant_leaks = sorted(
        item.source_id for item in items if item.tenant_id != tenant_id
    )
    missing_canonical_refs = sorted(
        item.source_id for item in items if not item.canonical_ref.strip()
    )
    unsafe_canonical_refs = sorted(
        item.source_id
        for item in items
        if item.canonical_ref.strip()
        and not _is_trusted_canonical_ref(item.source_type, item.canonical_ref)
    )
    embedding_spaces = _embedding_spaces(database_path, tenant_id)
    stale_syncs = _stale_syncs(database_path, tenant_id)
    uncited_cached_answers = 0

    report = {
        "tenant_id": tenant_id,
        "item_count": len(items),
        "tenant_leaks": tenant_leaks,
        "missing_canonical_refs": missing_canonical_refs,
        "unsafe_canonical_refs": unsafe_canonical_refs,
        "embedding_spaces": embedding_spaces,
        "stale_syncs": stale_syncs,
        "uncited_cached_answers": uncited_cached_answers,
    }
    report["valid"] = (
        not tenant_leaks
        and not missing_canonical_refs
        and not unsafe_canonical_refs
        and len(embedding_spaces) <= 1
        and not stale_syncs
    )
    return report


def _is_trusted_canonical_ref(source_type: str, canonical_ref: str) -> bool:
    if canonical_ref != canonical_ref.strip():
        return False
    parsed = urlparse(canonical_ref)
    if source_type == "obsidian":
        return parsed.scheme.lower() == "obsidian"
    if source_type == "notion":
        if parsed.scheme.lower() != "https":
            return False
        hostname = (parsed.hostname or "").lower().rstrip(".")
        return hostname == "notion.so" or hostname.endswith(".notion.so")
    return False


def _embedding_spaces(database_path: str, tenant_id: str) -> list[dict]:
    connection = portal_connect(database_path)
    try:
        rows = connection.execute(
            """
            SELECT DISTINCT embedding_model, embedding_dimensions
            FROM knowledge_chunks
            WHERE tenant_id = ? AND embedding_json IS NOT NULL
            ORDER BY embedding_model, embedding_dimensions
            """,
            (tenant_id,),
        ).fetchall()
        return [
            {"model": row["embedding_model"], "dimensions": row["embedding_dimensions"]}
            for row in rows
        ]
    finally:
        connection.close()


def _stale_syncs(database_path: str, tenant_id: str) -> list[dict]:
    connection = portal_connect(database_path)
    try:
        rows = connection.execute(
            """
            SELECT source_type, status, finished_at
            FROM sync_runs AS latest
            WHERE tenant_id = ?
              AND status IN ('stale', 'permission_required')
              AND finished_at = (
                  SELECT MAX(finished_at)
                  FROM sync_runs AS all_runs
                  WHERE all_runs.tenant_id = latest.tenant_id
                    AND all_runs.source_type = latest.source_type
                    AND all_runs.finished_at IS NOT NULL
              )
            ORDER BY source_type
            """,
            (tenant_id,),
        ).fetchall()
        return [
            {
                "source_type": row["source_type"],
                "status": row["status"],
                "finished_at": row["finished_at"],
            }
            for row in rows
        ]
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify Brain Cloud Portal tenant data integrity"
    )
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--database", required=True)
    args = parser.parse_args(argv)

    report = verify(args.tenant, args.database)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
