from typing import Iterable, Protocol

from brain_portal.models import SourceDocument


class SourceConnector(Protocol):
    def iter_documents(self, tenant_id: str) -> Iterable[SourceDocument]: ...
