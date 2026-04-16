from __future__ import annotations

from uuid import uuid4

from tools.models import EncounterEntity


def build_opportunity_request(
    *,
    actor: EncounterEntity,
    target: EncounterEntity,
    trigger_position: dict[str, int],
    weapon: dict[str, str],
) -> dict[str, object]:
    return {
        "request_id": f"react_{uuid4().hex[:12]}",
        "reaction_type": "opportunity_attack",
        "trigger_type": "leave_melee_reach",
        "status": "pending",
        "actor_entity_id": actor.entity_id,
        "actor_name": actor.name,
        "target_entity_id": target.entity_id,
        "target_name": target.name,
        "ask_player": actor.controller == "player",
        "auto_resolve": actor.controller != "player",
        "source_event_type": "movement_trigger_check",
        "source_event_id": None,
        "payload": {
            "weapon_id": weapon["weapon_id"],
            "weapon_name": weapon["name"],
            "trigger_position": trigger_position,
            "reason": "目标离开了你的近战触及",
        },
    }
