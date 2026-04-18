from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import ensure_warlock_runtime
from tools.services.encounter.get_encounter_state import GetEncounterState


class UseMysticArcanum:
    def __init__(self, encounter_repository: EncounterRepository):
        self.encounter_repository = encounter_repository
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        spell_level: int,
        spell_id: str | None = None,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)

        warlock = ensure_warlock_runtime(actor)
        mystic_arcanum = warlock.get("mystic_arcanum")
        if not isinstance(mystic_arcanum, dict):
            raise ValueError("mystic_arcanum_not_available")

        key = str(spell_level)
        bucket = mystic_arcanum.get(key)
        if not isinstance(bucket, dict) or not bool(bucket.get("enabled")):
            raise ValueError("mystic_arcanum_not_available")

        remaining_uses = bucket.get("remaining_uses")
        if not isinstance(remaining_uses, int) or remaining_uses <= 0:
            raise ValueError("mystic_arcanum_unavailable")

        bucket["remaining_uses"] = remaining_uses - 1
        self.encounter_repository.save(encounter)
        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "class_feature_result": {
                "mystic_arcanum": {
                    "spell_level": spell_level,
                    "spell_id": spell_id,
                    "cast_without_spell_slot": True,
                    "remaining_uses": bucket["remaining_uses"],
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
