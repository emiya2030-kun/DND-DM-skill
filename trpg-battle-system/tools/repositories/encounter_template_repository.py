from __future__ import annotations

from pathlib import Path
import threading
from typing import Any

from tinydb import Query

from tools.core.config import DATA_DIR
from tools.core.db import get_db


ENCOUNTER_TEMPLATES_DB_PATH = DATA_DIR / "encounter_templates.json"

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


class EncounterTemplateRepository:
    """基于 TinyDB 的样板快照仓储。"""

    def __init__(self, db_path: Path | None = None):
        self._db_path = Path(db_path or ENCOUNTER_TEMPLATES_DB_PATH)
        self._db = get_db(self._db_path)
        self._lock = _lock_for_path(self._db_path)

    def save(self, template_record: dict[str, Any]) -> dict[str, Any]:
        template_id = str(template_record.get("template_id") or "").strip()
        if not template_id:
            raise ValueError("template_id must be a non-empty string")
        with self._lock:
            query = Query()
            self._db.upsert(dict(template_record), query.template_id == template_id)
        return dict(template_record)

    def get(self, template_id: str) -> dict[str, Any] | None:
        normalized_template_id = str(template_id or "").strip()
        if not normalized_template_id:
            raise ValueError("template_id must be a non-empty string")
        with self._lock:
            query = Query()
            record = self._db.get(query.template_id == normalized_template_id)
        return dict(record) if isinstance(record, dict) else None

    def delete(self, template_id: str) -> int:
        normalized_template_id = str(template_id or "").strip()
        if not normalized_template_id:
            raise ValueError("template_id must be a non-empty string")
        with self._lock:
            query = Query()
            removed_ids = self._db.remove(query.template_id == normalized_template_id)
        return len(removed_ids)

    def list_templates(self) -> list[dict[str, Any]]:
        with self._lock:
            records = [dict(record) for record in self._db.all() if isinstance(record, dict)]
        return sorted(records, key=lambda item: (str(item.get("name") or ""), str(item.get("template_id") or "")))

    def close(self) -> None:
        with self._lock:
            self._db.close()
