from __future__ import annotations

from typing import Any

from runtime.context import BattleRuntimeContext
from tools.services import AdvanceTurn, EndTurn, StartTurn
from tools.services.events.append_event import AppendEvent


def _extract_turn_effect_resolutions(payload: dict[str, object]) -> list[dict[str, object]]:
    value = payload.get("turn_effect_resolutions")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def end_turn_and_advance(context: BattleRuntimeContext, args: dict[str, object]) -> dict[str, Any]:
    encounter_id = str(args.get("encounter_id") or "").strip()
    if not encounter_id:
        raise ValueError("encounter_id is required")

    encounter = context.encounter_repository.get(encounter_id)
    if encounter is None:
        raise ValueError(f"encounter '{encounter_id}' not found")
    ended_entity_id = encounter.current_entity_id

    append_event = AppendEvent(context.event_repository)
    end_payload = EndTurn(context.encounter_repository, append_event=append_event).execute_with_state(encounter_id)
    AdvanceTurn(context.encounter_repository).execute(encounter_id)
    start_payload = StartTurn(context.encounter_repository, append_event=append_event).execute_with_state(encounter_id)

    updated = context.encounter_repository.get(encounter_id)
    if updated is None:
        raise ValueError(f"encounter '{encounter_id}' not found")

    return {
        "encounter_id": encounter_id,
        "result": {
            "ended_entity_id": ended_entity_id,
            "current_entity_id": updated.current_entity_id,
            "round": updated.round,
            "turn_effect_resolutions": _extract_turn_effect_resolutions(end_payload)
            + _extract_turn_effect_resolutions(start_payload),
        },
        "encounter_state": context.get_encounter_state(encounter_id),
    }
