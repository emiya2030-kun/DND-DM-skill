from __future__ import annotations

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import ensure_warlock_runtime, has_selected_warlock_invocation
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.events.append_event import AppendEvent


class UsePactOfTheBlade:
    _SUPPORTED_DAMAGE_TYPES = {"necrotic", "psychic", "radiant"}

    def __init__(self, encounter_repository: EncounterRepository, append_event: AppendEvent):
        self.encounter_repository = encounter_repository
        self.append_event = append_event
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        weapon_id: str,
        damage_type: str | None = None,
    ) -> dict[str, object]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)
        self._ensure_actor_turn(encounter, actor_id)
        self._ensure_bonus_action_available(actor)
        self._ensure_invocation_selected(actor)
        weapon = self._get_weapon_or_raise(actor, weapon_id)
        self._ensure_weapon_is_bindable(weapon)
        normalized_damage_type = self._normalize_damage_type(damage_type)

        warlock = ensure_warlock_runtime(actor)
        pact = warlock.get("pact_of_the_blade")
        if not isinstance(pact, dict):
            raise ValueError("pact_of_the_blade_not_available")

        pact["bound_weapon_id"] = str(weapon.get("weapon_id") or weapon_id)
        pact["bound_weapon_name"] = str(weapon.get("name") or weapon_id)
        pact["damage_type_override"] = normalized_damage_type
        actor.action_economy["bonus_action_used"] = True
        self.encounter_repository.save(encounter)

        self.append_event.execute(
            encounter_id=encounter_id,
            round=encounter.round,
            event_type="class_feature_pact_of_the_blade_used",
            actor_entity_id=actor_id,
            target_entity_id=actor_id,
            payload={
                "class_feature_id": "warlock.pact_of_the_blade",
                "bound_weapon_id": pact["bound_weapon_id"],
                "bound_weapon_name": pact["bound_weapon_name"],
                "damage_type_override": pact["damage_type_override"],
            },
        )

        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "class_feature_result": {
                "pact_of_the_blade": {
                    "bound_weapon_id": pact["bound_weapon_id"],
                    "bound_weapon_name": pact["bound_weapon_name"],
                    "damage_type_override": pact["damage_type_override"],
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

    def _ensure_bonus_action_available(self, actor: EncounterEntity) -> None:
        if bool(actor.action_economy.get("bonus_action_used")):
            raise ValueError("bonus_action_already_used")

    def _ensure_invocation_selected(self, actor: EncounterEntity) -> None:
        if not has_selected_warlock_invocation(actor, "pact_of_the_blade"):
            raise ValueError("pact_of_the_blade_not_available")

    def _get_weapon_or_raise(self, actor: EncounterEntity, weapon_id: str) -> dict[str, object]:
        for weapon in actor.weapons:
            if weapon.get("weapon_id") == weapon_id:
                return weapon
        raise ValueError("weapon_not_found")

    def _ensure_weapon_is_bindable(self, weapon: dict[str, object]) -> None:
        category = str(weapon.get("category") or "").strip().lower()
        kind = str(weapon.get("kind") or "").strip().lower()
        if category not in {"simple", "martial"} or kind != "melee":
            raise ValueError("pact_of_the_blade_invalid_weapon")

    def _normalize_damage_type(self, damage_type: str | None) -> str | None:
        if damage_type is None:
            return None
        normalized = str(damage_type).strip().lower()
        if not normalized:
            return None
        if normalized not in self._SUPPORTED_DAMAGE_TYPES:
            raise ValueError("pact_of_the_blade_invalid_damage_type")
        return normalized
