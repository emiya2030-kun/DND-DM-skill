from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import ensure_spell_slots_runtime, ensure_warlock_runtime
from tools.services.encounter.get_encounter_state import GetEncounterState


class UseMagicalCunning:
    def __init__(self, encounter_repository: EncounterRepository):
        self.encounter_repository = encounter_repository
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)

        warlock = ensure_warlock_runtime(actor)
        magical_cunning = warlock.get("magical_cunning")
        if not isinstance(magical_cunning, dict) or not bool(magical_cunning.get("enabled")):
            raise ValueError("magical_cunning_not_available")
        if not bool(magical_cunning.get("available")):
            raise ValueError("magical_cunning_unavailable")

        slots_runtime = ensure_spell_slots_runtime(actor)
        pact_magic_slots = slots_runtime.get("pact_magic_slots")
        if not isinstance(pact_magic_slots, dict):
            raise ValueError("magical_cunning_requires_pact_magic")

        maximum = int(pact_magic_slots.get("max", 0) or 0)
        remaining = int(pact_magic_slots.get("remaining", 0) or 0)
        expended = max(0, maximum - remaining)
        if expended <= 0:
            raise ValueError("magical_cunning_no_expended_slots")

        restore_amount = expended if bool(warlock.get("eldritch_master", {}).get("enabled")) else (expended + 1) // 2
        new_remaining = min(maximum, remaining + restore_amount)
        restored_slots = new_remaining - remaining
        pact_magic_slots["remaining"] = new_remaining
        magical_cunning["available"] = False

        self.encounter_repository.save(encounter)
        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "class_feature_result": {
                "magical_cunning": {
                    "restored_slots": restored_slots,
                    "remaining_slots": new_remaining,
                    "slot_level": int(pact_magic_slots.get("slot_level", 0) or 0),
                    "used_eldritch_master": bool(warlock.get("eldritch_master", {}).get("enabled")),
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
