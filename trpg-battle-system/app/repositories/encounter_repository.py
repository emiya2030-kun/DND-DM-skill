from __future__ import annotations

from pathlib import Path

from tinydb import Query

from app.core.config import ENCOUNTERS_DB_PATH
from app.core.db import get_db
from app.models.encounter import Encounter


class EncounterRepository:
    """基于 TinyDB 的 encounter 快照仓储."""

    def __init__(self, db_path: Path | None = None):
        self._db = get_db(db_path or ENCOUNTERS_DB_PATH)

    def save(self, encounter: Encounter) -> Encounter:
        # 这里用 encounter_id 作为业务主键,不把 TinyDB 的内部 doc_id
        # 泄漏到模型层,后面换存储实现也更容易.
        query = Query()
        self._db.upsert(encounter.to_dict(), query.encounter_id == encounter.encounter_id)
        return encounter

    def get(self, encounter_id: str) -> Encounter | None:
        query = Query()
        record = self._db.get(query.encounter_id == encounter_id)
        if record is None:
            return None
        return Encounter.from_dict(record)

    def delete(self, encounter_id: str) -> int:
        query = Query()
        removed_ids = self._db.remove(query.encounter_id == encounter_id)
        return len(removed_ids)

    def list_encounter_ids(self) -> list[str]:
        return [record["encounter_id"] for record in self._db.all() if "encounter_id" in record]

    def close(self) -> None:
        self._db.close()
