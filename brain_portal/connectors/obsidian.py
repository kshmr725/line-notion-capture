from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Union

from brain_portal.models import SourceDocument
from brain_portal.presentation import food_place_metadata, parse_obsidian_metadata


PathLike = Union[str, Path]

FOLDER_CLOUDS = {
    "11_Web3_商業研究": "web3",
    "50_Tech_AI自動化": "ai",
    "71_Food_美食與咖啡地圖": "food",
}
NORMALIZER_VERSION = b"portal-normalizer-v2"


class ObsidianConnector:
    source_type = "obsidian"

    def __init__(self, root: PathLike):
        self.root = Path(root).expanduser().resolve()

    def iter_documents(self, tenant_id: str):
        if not self.root.is_dir():
            raise FileNotFoundError(f"Obsidian root does not exist: {self.root}")
        for candidate in sorted(self.root.rglob("*"), key=lambda path: str(path)):
            relative = candidate.relative_to(self.root)
            if any(part.startswith(".") for part in relative.parts):
                continue
            if candidate.suffix.casefold() != ".md":
                continue
            if candidate.name.casefold() == "instructions.md":
                continue
            if not relative.parts or relative.parts[0] not in FOLDER_CLOUDS:
                continue
            resolved = candidate.resolve(strict=True)
            try:
                resolved.relative_to(self.root)
            except ValueError as error:
                raise PermissionError(
                    f"source path escapes configured root: {relative.as_posix()}"
                ) from error
            if not resolved.is_file():
                continue
            content = resolved.read_bytes()
            stat = resolved.stat()
            source_id = relative.as_posix()
            yield SourceDocument(
                tenant_id=tenant_id,
                source_id=source_id,
                source_type=self.source_type,
                canonical_ref=f"obsidian://{source_id}",
                title=_source_title(relative.parts[0], content.decode("utf-8"), candidate.stem),
                body=content.decode("utf-8"),
                cloud_key=FOLDER_CLOUDS[relative.parts[0]],
                source_revision=hashlib.sha256(content + b"\0" + NORMALIZER_VERSION).hexdigest(),
                updated_at=datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
                metadata=_source_metadata(relative.parts[0], content.decode("utf-8"), candidate.stem),
            )


def _source_title(folder: str, body: str, title: str) -> str:
    if FOLDER_CLOUDS.get(folder) == "food":
        return str(food_place_metadata(body, title)["display_title"])
    return str(parse_obsidian_metadata(body, title)["title"])


def _source_metadata(folder: str, body: str, title: str) -> dict[str, object]:
    if FOLDER_CLOUDS.get(folder) == "food":
        return food_place_metadata(body, title)
    return {}
