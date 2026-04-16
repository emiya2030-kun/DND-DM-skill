from __future__ import annotations

from pathlib import Path

from tinydb import Query

from tools.core.config import EVENTS_DB_PATH
from tools.core.db import get_db
from tools.models.event import Event


class EventRepository:
    """基于 TinyDB 的事件日志仓储，只负责追加和查询，不负责状态结算。"""

    def __init__(self, db_path: Path | None = None):
        self._db = get_db(db_path or EVENTS_DB_PATH)

    def append(self, event: Event) -> Event:
        """追加一条事件；相同 event_id 不允许重复写入。"""
        query = Query()
        existing = self._db.get(query.event_id == event.event_id)
        if existing is not None:
            raise ValueError(f"event '{event.event_id}' already exists")

        self._db.insert(event.to_dict())
        return event

    def get(self, event_id: str) -> Event | None:
        """按 event_id 读取单条事件。"""
        query = Query()
        record = self._db.get(query.event_id == event_id)
        if record is None:
            return None
        return Event.from_dict(record)

    def list_by_encounter(self, encounter_id: str) -> list[Event]:
        """按 encounter_id 返回事件列表，保持追加顺序。"""
        query = Query()
        records = self._db.search(query.encounter_id == encounter_id)
        return [Event.from_dict(record) for record in records]

    def delete_by_encounter(self, encounter_id: str) -> None:
        """删除指定 encounter 的全部事件。"""
        query = Query()
        self._db.remove(query.encounter_id == encounter_id)

    def list_all(self) -> list[Event]:
        """返回所有事件，主要用于调试和测试。"""
        return [Event.from_dict(record) for record in self._db.all()]

    def close(self) -> None:
        self._db.close()
