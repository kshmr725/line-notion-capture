from __future__ import annotations

import json

from brain_portal.config import PortalSettings
from brain_portal.db import PortalRepository
from scripts.index_brain_portal import main


def test_command_requires_explicit_lexical_only_flag_without_gemini_key(
    tmp_path, capsys
):
    vault = tmp_path / "Kevin_Brain"
    note = vault / "50_Tech_AI自動化" / "Agent.md"
    note.parent.mkdir(parents=True)
    note.write_text("# Agent\n\nA reliable workflow.", encoding="utf-8")
    database = tmp_path / "portal.sqlite3"
    settings = PortalSettings(database_path=str(database), gemini_api_key="")
    args = ["--tenant", "kevin", "--obsidian-root", str(vault)]

    assert main(args, settings=settings) == 1
    assert main([*args, "--lexical-only"], settings=settings) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "lexical-only"
    assert output["indexed"] == 1
    assert [item.title for item in PortalRepository(database).list_items("kevin")] == [
        "Agent"
    ]
