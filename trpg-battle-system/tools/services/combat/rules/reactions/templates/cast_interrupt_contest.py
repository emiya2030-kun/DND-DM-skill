from __future__ import annotations

from typing import Any


class CastInterruptContest:
    """Placeholder template for cast interruption contests (e.g. Counterspell)."""

    def execute(
        self,
        *,
        encounter_id: str,
        actor_entity_id: str,
        target_entity_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "resolution_mode": "no_effect",
            "reaction_result": {
                "status": "not_implemented",
                "actor_entity_id": actor_entity_id,
                "target_entity_id": target_entity_id,
                "payload": payload or {},
            },
        }
