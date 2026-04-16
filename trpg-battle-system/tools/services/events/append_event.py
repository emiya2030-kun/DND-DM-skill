from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from tools.models.event import Event
from tools.repositories.event_repository import EventRepository


class AppendEvent:
    """本地事件追加服务，负责补齐 event_id / created_at 并写入日志。"""

    def __init__(self, repository: EventRepository):
        self.repository = repository

    def execute(
        self,
        *,
        encounter_id: str,
        round: int,
        event_type: str,
        actor_entity_id: str | None = None,
        target_entity_id: str | None = None,
        request_id: str | None = None,
        payload: dict | None = None,
        event_id: str | None = None,
        created_at: str | None = None,
    ) -> Event:
        """创建并追加一条事件，默认自动生成 id 和时间。"""
        event = Event(
            event_id=event_id or self._generate_event_id(),
            encounter_id=encounter_id,
            round=round,
            event_type=event_type,
            actor_entity_id=actor_entity_id,
            target_entity_id=target_entity_id,
            request_id=request_id,
            payload=payload or {},
            created_at=created_at or datetime.now().isoformat(),
        )
        return self.repository.append(event)

    def list_by_encounter(self, encounter_id: str) -> list[Event]:
        """返回指定 encounter 的全部事件。"""
        return self.repository.list_by_encounter(encounter_id)

    def _generate_event_id(self) -> str:
        return f"evt_{uuid4().hex[:12]}"
