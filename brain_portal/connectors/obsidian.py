from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Union

from brain_portal.models import SourceDocument


PathLike = Union[str, Path]

FOLDER_CLOUDS = {
    "11_Web3_商業研究": "web3",
    "50_Tech_AI自動化": "ai",
    "71_Food_美食與咖啡地圖": "food",
}


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
                title=candidate.stem,
                body=content.decode("utf-8"),
                cloud_key=FOLDER_CLOUDS[relative.parts[0]],
                source_revision=hashlib.sha256(content).hexdigest(),
                updated_at=datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
                metadata=_source_metadata(relative.parts[0], candidate.stem),
            )


def _source_metadata(folder: str, title: str) -> dict[str, object]:
    if FOLDER_CLOUDS.get(folder) != "food":
        return {}
    place_name = re.sub(r"^\d{4}-\d{2}-\d{2}\s*", "", title).strip()
    category_match = re.search(r"\[([^\]]+)\]", place_name)
    category = category_match.group(1).strip() if category_match else ""
    if category_match:
        place_name = (place_name[: category_match.start()] + place_name[category_match.end() :]).strip()
    place_name = re.sub(r"^[^\w\u4e00-\u9fff]+", "", place_name).strip()
    place: dict[str, object] = {"name": place_name or title}
    if category:
        place["category"] = category
    return {"item_type": "place", "place": place}
