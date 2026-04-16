from __future__ import annotations

from typing import Any

from runtime.context import BattleRuntimeContext
from runtime.presets import random_encounters
from tools.models import Encounter, EncounterMap
from tools.services import EncounterService, RollInitiativeAndStartEncounter


def _bootstrap_encounter_if_missing(context: BattleRuntimeContext, encounter_id: str) -> None:
    if context.encounter_repository.get(encounter_id) is not None:
        return

    EncounterService(
        context.encounter_repository,
        context.entity_definition_repository,
    ).create_encounter(
        Encounter(
            encounter_id=encounter_id,
            name="Runtime Encounter",
            status="active",
            round=1,
            current_entity_id=None,
            turn_order=[],
            entities={},
            map=EncounterMap(
                map_id="map_uninitialized",
                name="Uninitialized Map",
                description="Runtime encounter shell.",
                width=1,
                height=1,
            ),
        )
    )


def start_random_encounter(context: BattleRuntimeContext, args: dict[str, Any]) -> dict[str, Any]:
    encounter_id = str(args.get("encounter_id") or "").strip()
    if not encounter_id:
        raise ValueError("encounter_id is required")

    theme = args.get("theme")
    if theme is not None:
        theme = str(theme).strip() or None

    setup = random_encounters.choose_random_encounter_setup(theme=theme)

    _bootstrap_encounter_if_missing(context, encounter_id)
    context.event_repository.delete_by_encounter(encounter_id)

    EncounterService(
        context.encounter_repository,
        context.entity_definition_repository,
    ).initialize_encounter(
        encounter_id,
        map_setup=setup["map_setup"],
        entity_setups=setup["entity_setups"],
    )

    rolled = RollInitiativeAndStartEncounter(context.encounter_repository).execute_with_state(encounter_id)

    return {
        "encounter_id": encounter_id,
        "result": {
            "encounter_name": setup["encounter_name"],
            "map_name": setup["map_setup"]["name"],
            "initiative_results": rolled["initiative_results"],
            "turn_order": rolled["turn_order"],
            "current_entity_id": rolled["current_entity_id"],
        },
        "encounter_state": rolled["encounter_state"],
    }
