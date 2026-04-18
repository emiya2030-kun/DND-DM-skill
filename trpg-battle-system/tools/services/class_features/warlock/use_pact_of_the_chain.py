from __future__ import annotations

from random import randint
from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import ensure_warlock_runtime
from tools.services.class_features.shared.warlock_invocations import has_selected_warlock_invocation
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.events.append_event import AppendEvent
from tools.services.spells.summons import (
    build_find_familiar_entity,
    create_summoned_entity_by_initiative,
    resolve_summon_target_point,
)


_FAMILIAR_CREATURE_TYPES = {
    "slaad_tadpole": "aberration",
    "pseudodragon": "dragon",
    "skeleton": "undead",
    "zombie": "undead",
    "sprite": "fey",
    "quasit": "fiend",
    "imp": "fiend",
    "sphinx_of_wonder": "celestial",
}
_GENERIC_FAMILIAR_FORMS = {"owl"}


class UsePactOfTheChain:
    def __init__(self, encounter_repository: EncounterRepository, append_event: AppendEvent):
        self.encounter_repository = encounter_repository
        self.append_event = append_event
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        familiar_form: str,
        creature_type: str | None = None,
        target_point: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)
        self._ensure_actor_turn(encounter, actor_id)
        self._ensure_action_available(actor)
        self._ensure_invocation_selected(actor)

        normalized_form = self._normalize_familiar_form(familiar_form)
        normalized_target_point = resolve_summon_target_point(
            encounter=encounter,
            caster=actor,
            summon_size="tiny",
            range_feet=10,
            target_point=target_point,
            default_mode="adjacent_open_space",
            out_of_range_error_code="find_familiar_target_point_out_of_range",
            missing_target_point_error_code="find_familiar_requires_target_point",
        )

        warlock = ensure_warlock_runtime(actor)
        pact = warlock.get("pact_of_the_chain")
        if not isinstance(pact, dict) or not bool(pact.get("enabled")):
            raise ValueError("pact_of_the_chain_not_available")

        self._replace_previous_familiar_if_needed(encounter=encounter, pact=pact)
        summon = build_find_familiar_entity(
            caster=actor,
            summon_position={"x": normalized_target_point["x"], "y": normalized_target_point["y"]},
            familiar_form=normalized_form,
            creature_type=self._resolve_creature_type(normalized_form=normalized_form, creature_type=creature_type),
            source_spell_instance_id=f"pact_of_the_chain_{actor.entity_id}",
        )
        summon.initiative = randint(1, 20) + int(summon.ability_mods.get("dex", 0) or 0)
        create_summoned_entity_by_initiative(
            encounter=encounter,
            summon=summon,
        )

        pact["familiar_entity_id"] = summon.entity_id
        pact["familiar_name"] = summon.name
        pact["familiar_form_id"] = normalized_form
        actor.action_economy["action_used"] = True
        self.encounter_repository.save(encounter)

        self.append_event.execute(
            encounter_id=encounter_id,
            round=encounter.round,
            event_type="class_feature_pact_of_the_chain_used",
            actor_entity_id=actor_id,
            target_entity_id=summon.entity_id,
            payload={
                "class_feature_id": "warlock.pact_of_the_chain",
                "familiar_entity_id": summon.entity_id,
                "familiar_name": summon.name,
                "familiar_form_id": normalized_form,
                "target_point": normalized_target_point,
                "initiative": summon.initiative,
            },
        )

        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "class_feature_result": {
                "pact_of_the_chain": {
                    "familiar_entity_id": summon.entity_id,
                    "familiar_name": summon.name,
                    "familiar_form_id": normalized_form,
                    "initiative": summon.initiative,
                    "target_point": normalized_target_point,
                    "cast_without_spell_slot": True,
                }
            },
            "encounter_state": self.get_encounter_state.execute(encounter_id),
        }

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_actor_or_raise(self, encounter: Encounter, actor_id: str) -> EncounterEntity:
        actor = encounter.entities.get(actor_id)
        if actor is None:
            raise ValueError(f"actor '{actor_id}' not found in encounter")
        return actor

    def _ensure_actor_turn(self, encounter: Encounter, actor_id: str) -> None:
        if encounter.current_entity_id != actor_id:
            raise ValueError("not_actor_turn")

    def _ensure_action_available(self, actor: EncounterEntity) -> None:
        if bool(actor.action_economy.get("action_used")):
            raise ValueError("action_already_used")

    def _ensure_invocation_selected(self, actor: EncounterEntity) -> None:
        if not has_selected_warlock_invocation(actor, "pact_of_the_chain"):
            raise ValueError("pact_of_the_chain_not_available")

    def _normalize_familiar_form(self, familiar_form: str) -> str:
        normalized = str(familiar_form or "").strip().lower()
        if normalized not in _FAMILIAR_CREATURE_TYPES and normalized not in _GENERIC_FAMILIAR_FORMS:
            raise ValueError("invalid_find_familiar_form")
        return normalized

    def _resolve_creature_type(self, *, normalized_form: str, creature_type: str | None) -> str:
        if normalized_form in _FAMILIAR_CREATURE_TYPES:
            return _FAMILIAR_CREATURE_TYPES[normalized_form]
        normalized_creature_type = str(creature_type or "").strip().lower()
        return normalized_creature_type or "fey"

    def _replace_previous_familiar_if_needed(self, *, encounter: Encounter, pact: dict[str, Any]) -> None:
        familiar_entity_id = pact.get("familiar_entity_id")
        if isinstance(familiar_entity_id, str) and familiar_entity_id:
            encounter.entities.pop(familiar_entity_id, None)
            encounter.turn_order = [entity_id for entity_id in encounter.turn_order if entity_id != familiar_entity_id]
            if encounter.current_entity_id == familiar_entity_id:
                encounter.current_entity_id = None

        pact["familiar_entity_id"] = None
        pact["familiar_name"] = None
        pact["familiar_form_id"] = None
