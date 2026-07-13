from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from brain_portal.config import PortalSettings
from brain_portal.db import PortalRepository, init_portal_db
from brain_portal.indexer import normalize_document, run_index
from brain_portal.models import SourceDocument
from scripts import index_brain_portal, verify_brain_portal


REPO_ROOT = Path(__file__).resolve().parents[2]


class FakeEmbedder:
    model_id = "fake-embedding"
    dimensions = 2

    def __init__(self):
        self.calls = 0

    def embed(self, text: str, task_type: str) -> list[float]:
        self.calls += 1
        return [float(len(text)), 1.0]


class TogglableConnector:
    source_type = "obsidian"

    def __init__(self, documents):
        self.documents = documents
        self._should_fail = False

    def fail_next_scan(self) -> None:
        self._should_fail = True

    def iter_documents(self, tenant_id: str):
        if self._should_fail:
            self._should_fail = False
            raise RuntimeError("vault temporarily unavailable")
        yield from self.documents


def _document(source_id: str = "note.md", body: str = "Agent workflow") -> SourceDocument:
    return SourceDocument(
        tenant_id="kevin",
        source_id=source_id,
        source_type="obsidian",
        canonical_ref=f"obsidian://{source_id}",
        title="Agent",
        body=body,
        cloud_key="ai",
        source_revision="rev-1",
        updated_at="2026-07-13T00:00:00+00:00",
        metadata={"concepts": ("agents",)},
    )


class IndexFixture:
    def __init__(self, tmp_path):
        path = tmp_path / "portal.sqlite3"
        init_portal_db(path)
        self.repo = PortalRepository(path)
        self.connector = TogglableConnector([_document()])
        self.embedder = FakeEmbedder()

    def run(self):
        return run_index("kevin", self.connector, self.repo, self.embedder)

    def run_successfully(self):
        report = self.run()
        assert report.failed == 0
        return report


@pytest.fixture
def index_fixture(tmp_path):
    return IndexFixture(tmp_path)


def test_failed_sync_keeps_last_successful_projection(index_fixture):
    index_fixture.run_successfully()
    previous = index_fixture.repo.list_items("kevin")
    index_fixture.connector.fail_next_scan()

    report = index_fixture.run()

    assert report.failed == 1
    assert index_fixture.repo.list_items("kevin") == previous
    assert index_fixture.repo.latest_sync("kevin").status == "stale"


def test_stale_sync_recovers_to_valid_after_a_successful_reindex(index_fixture):
    index_fixture.run_successfully()
    index_fixture.connector.fail_next_scan()
    index_fixture.run()
    stale_report = verify_brain_portal.verify("kevin", str(index_fixture.repo.path))
    assert stale_report["stale_syncs"]
    assert stale_report["valid"] is False

    index_fixture.run_successfully()

    recovered_report = verify_brain_portal.verify("kevin", str(index_fixture.repo.path))
    assert recovered_report["stale_syncs"] == []
    assert recovered_report["valid"] is True


class OtherEmbedder:
    model_id = "other-embedding"
    dimensions = 3

    def embed(self, text: str, task_type: str) -> list[float]:
        return [1.0, 1.0, 1.0]


def test_verify_script_flags_mixed_embedding_spaces(tmp_path):
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)
    repo = PortalRepository(path)
    run_index(
        "kevin", TogglableConnector([_document("note-a.md")]), repo, FakeEmbedder()
    )
    # note-a.md is unchanged (same revision) so it keeps its original embedding
    # space, while note-b.md is newly indexed with a different one. Both stay
    # live, reproducing a real migrated-embedding-model scenario.
    run_index(
        "kevin",
        TogglableConnector([_document("note-a.md"), _document("note-b.md")]),
        repo,
        OtherEmbedder(),
    )

    report = verify_brain_portal.verify("kevin", str(path))

    assert len(repo.list_items("kevin")) == 2
    assert report["valid"] is False
    assert len(report["embedding_spaces"]) == 2


def test_verify_script_ignores_orphaned_chunks_from_soft_deleted_items(tmp_path):
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)
    repo = PortalRepository(path)
    run_index(
        "kevin", TogglableConnector([_document("note-a.md")]), repo, FakeEmbedder()
    )
    # note-a.md is absent from this scan and gets soft-deleted; its old chunks
    # (and their embedding_model) remain in the table but must not count.
    run_index(
        "kevin", TogglableConnector([_document("note-b.md")]), repo, OtherEmbedder()
    )

    report = verify_brain_portal.verify("kevin", str(path))

    assert len(repo.list_items("kevin")) == 1
    assert report["embedding_spaces"] == [{"model": "other-embedding", "dimensions": 3}]
    assert report["valid"] is True


def test_verify_cli_prints_json_and_exits_zero_for_a_healthy_tenant(tmp_path):
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/verify_brain_portal.py",
            "--tenant",
            "kevin",
            "--database",
            str(path),
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )

    payload = json.loads(completed.stdout)
    assert payload["tenant_id"] == "kevin"
    assert payload["item_count"] == 0
    assert completed.returncode == 0
    assert payload["valid"] is True


def test_verify_cli_exits_nonzero_for_an_invalid_tenant(tmp_path):
    path = tmp_path / "portal.sqlite3"
    init_portal_db(path)
    repo = PortalRepository(path)
    doc = SourceDocument(
        tenant_id="kevin",
        source_id="note-1",
        source_type="obsidian",
        canonical_ref=" ",
        title="Note",
        body="Body",
        cloud_key="ai",
        source_revision="rev-1",
        updated_at="2026-07-13T00:00:00+00:00",
        metadata={},
    )
    repo.upsert_item("kevin", normalize_document(doc), chunks=["Body"])

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/verify_brain_portal.py",
            "--tenant",
            "kevin",
            "--database",
            str(path),
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )

    payload = json.loads(completed.stdout)
    assert completed.returncode == 1
    assert payload["valid"] is False
    assert "note-1" in payload["missing_canonical_refs"]


def test_index_script_requires_exactly_one_source():
    with pytest.raises(SystemExit) as exc_info:
        index_brain_portal.main(["--tenant", "kevin"])
    assert exc_info.value.code == 2


def test_index_script_rejects_both_sources():
    with pytest.raises(SystemExit) as exc_info:
        index_brain_portal.main(
            [
                "--tenant",
                "kevin",
                "--obsidian-root",
                "x",
                "--notion-connection",
                "y",
            ]
        )
    assert exc_info.value.code == 2


def test_index_script_dry_run_reports_counts_without_writing(tmp_path, capsys):
    root = tmp_path / "Kevin_Brain"
    note = root / "50_Tech_AI自動化" / "Note.md"
    note.parent.mkdir(parents=True)
    note.write_text("# Note\n\nAgent workflow", encoding="utf-8")
    database_path = tmp_path / "portal.sqlite3"

    exit_code = index_brain_portal.main(
        [
            "--tenant",
            "kevin",
            "--obsidian-root",
            str(root),
            "--dry-run",
            "--database",
            str(database_path),
        ]
    )

    assert exit_code == 0
    assert not database_path.exists()
    output = json.loads(capsys.readouterr().out)
    assert output["dry_run"] is True
    assert output["would_index"] == 1


def test_index_script_requires_a_gemini_key_for_a_real_run(tmp_path, capsys):
    root = tmp_path / "Kevin_Brain"
    note = root / "50_Tech_AI自動化" / "Note.md"
    note.parent.mkdir(parents=True)
    note.write_text("# Note\n\nAgent workflow", encoding="utf-8")
    database_path = tmp_path / "portal.sqlite3"
    settings = PortalSettings(gemini_api_key="", notion_token="token")

    exit_code = index_brain_portal.main(
        [
            "--tenant",
            "kevin",
            "--obsidian-root",
            str(root),
            "--database",
            str(database_path),
        ],
        settings=settings,
    )

    assert exit_code == 1
    output = capsys.readouterr()
    assert "GEMINI_API_KEY" in output.err
    assert not database_path.exists()


def test_index_script_reports_a_clean_error_for_a_missing_notion_token(tmp_path, capsys):
    database_path = tmp_path / "portal.sqlite3"
    settings = PortalSettings(gemini_api_key="", notion_token="")

    exit_code = index_brain_portal.main(
        [
            "--tenant",
            "kevin",
            "--notion-connection",
            "db-1",
            "--dry-run",
            "--database",
            str(database_path),
        ],
        settings=settings,
    )

    output = capsys.readouterr()
    assert exit_code == 1
    assert "NOTION_TOKEN" in output.err
    assert "Traceback" not in output.err
