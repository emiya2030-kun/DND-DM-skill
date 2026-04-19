from __future__ import annotations

from pathlib import Path
import threading

from tinydb import Query

from tools.core.config import ENCOUNTERS_DB_PATH
from tools.core.db import get_db
from tools.models.encounter import Encounter
from tools.services.shared_turns import normalize_shared_turn_state


_REPOSITORY_LOCKS: dict[Path, threading.RLock] = {}
_REPOSITORY_LOCKS_GUARD = threading.Lock()


def _lock_for_path(db_path: Path) -> threading.RLock:
    normalized = Path(db_path).resolve()
    with _REPOSITORY_LOCKS_GUARD:
        lock = _REPOSITORY_LOCKS.get(normalized)
        if lock is None:
            lock = threading.RLock()
            _REPOSITORY_LOCKS[normalized] = lock
        return lock


class EncounterRepository:
    """基于 TinyDB 的 encounter 快照仓储。"""

    def __init__(self, db_path: Path | None = None):
        self._db_path = Path(db_path or ENCOUNTERS_DB_PATH)
        self._db = get_db(self._db_path)
        self._lock = _lock_for_path(self._db_path)

    def save(self, encounter: Encounter) -> Encounter:
        # 这里用 encounter_id 作为业务主键，不把 TinyDB 的内部 doc_id
        # 泄漏到模型层，后面换存储实现也更容易。
        with self._lock:
            query = Query()
            self._db.upsert(encounter.to_dict(), query.encounter_id == encounter.encounter_id)
        return encounter

    def get(self, encounter_id: str) -> Encounter | None:
        with self._lock:
            query = Query()
            record = self._db.get(query.encounter_id == encounter_id)
        if record is None:
            return None
        return normalize_shared_turn_state(Encounter.from_dict(record))

    def delete(self, encounter_id: str) -> int:
        with self._lock:
            query = Query()
            removed_ids = self._db.remove(query.encounter_id == encounter_id)
        return len(removed_ids)

    def list_encounter_ids(self) -> list[str]:
        with self._lock:
            return [record["encounter_id"] for record in self._db.all() if "encounter_id" in record]

    def close(self) -> None:
        with self._lock:
            self._db.close()
