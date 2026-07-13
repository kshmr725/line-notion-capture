import hashlib

import pytest

from brain_portal.connectors.obsidian import ObsidianConnector


def test_connector_maps_folder_to_cloud_without_writing(tmp_path):
    root = tmp_path / "Kevin_Brain"
    note = root / "50_Tech_AI自動化" / "Claude Code.md"
    note.parent.mkdir(parents=True)
    note.write_text("# Claude Code\n\nAgent workflow", encoding="utf-8")
    before = note.stat().st_mtime_ns

    docs = list(ObsidianConnector(root).iter_documents("kevin"))

    assert docs[0].cloud_key == "ai"
    assert docs[0].canonical_ref.endswith("50_Tech_AI自動化/Claude Code.md")
    assert note.stat().st_mtime_ns == before


def test_food_note_filename_becomes_an_honest_place_projection(tmp_path):
    root = tmp_path / "Kevin_Brain"
    note = root / "71_Food_美食與咖啡地圖" / "2026-06-12 [咖啡廳] Cozzi Café 敦南店.md"
    note.parent.mkdir(parents=True)
    note.write_text("# Cozzi\n\nA saved place.", encoding="utf-8")

    [document] = list(ObsidianConnector(root).iter_documents("kevin"))

    assert document.metadata["item_type"] == "place"
    assert document.metadata["place"] == {
        "name": "Cozzi Café 敦南店",
        "category": "咖啡廳",
    }


def test_connector_filters_every_path_outside_the_mvp_policy(tmp_path):
    root = tmp_path / "Kevin_Brain"
    valid = root / "11_Web3_商業研究" / "Visible.md"
    valid.parent.mkdir(parents=True)
    valid.write_text("visible", encoding="utf-8")
    excluded = {
        root / "11_Web3_商業研究" / ".private.md": "private",
        root / "11_Web3_商業研究" / "instructions.md": "instructions",
        root / "11_Web3_商業研究" / "draft.txt": "not markdown",
        root / ".hidden" / "Hidden.md": "hidden folder",
        root / "99_Unmapped" / "Other.md": "unmapped",
    }
    for path, content in excluded.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    docs = list(ObsidianConnector(root).iter_documents("kevin"))

    assert [doc.source_id for doc in docs] == ["11_Web3_商業研究/Visible.md"]
    assert docs[0].cloud_key == "web3"


def test_connector_rejects_a_symlink_that_escapes_the_root(tmp_path):
    root = tmp_path / "Kevin_Brain"
    folder = root / "71_Food_美食與咖啡地圖"
    folder.mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("must not be read", encoding="utf-8")
    (folder / "escape.md").symlink_to(outside)

    with pytest.raises(PermissionError, match="escapes configured root"):
        list(ObsidianConnector(root).iter_documents("kevin"))


def test_connector_revision_is_the_sha256_of_file_bytes(tmp_path):
    root = tmp_path / "Kevin_Brain"
    note = root / "71_Food_美食與咖啡地圖" / "Cafe.md"
    note.parent.mkdir(parents=True)
    content = "# Café\n\nTaipei coffee".encode("utf-8")
    note.write_bytes(content)

    [doc] = list(ObsidianConnector(root).iter_documents("kevin"))

    assert doc.source_revision == hashlib.sha256(content).hexdigest()
    assert doc.source_type == "obsidian"
    assert doc.title == "Cafe"
    assert doc.cloud_key == "food"
