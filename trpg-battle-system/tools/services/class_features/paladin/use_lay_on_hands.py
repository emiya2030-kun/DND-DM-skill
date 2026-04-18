from __future__ import annotations

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import ensure_paladin_runtime
from tools.services.combat.shared.update_hp import UpdateHp
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.events.append_event import AppendEvent


class UseLayOnHands:
    _SUPPORTED_RESTORING_TOUCH_CONDITIONS = {
        "blinded",
        "charmed",
        "deafened",
        "frightened",
        "paralyzed",
        "stunned",
    }

    def __init__(self, encounter_repository: EncounterRepository, append_event: AppendEvent):
        self.encounter_repository = encounter_repository
        self.append_event = append_event
        self.update_hp = UpdateHp(encounter_repository, append_event)
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        target_id: str,
        heal_amount: int = 0,
        cure_poison: bool = False,
        remove_conditions: list[str] | None = None,
        allow_out_of_turn_actor: bool = False,
    ) -> dict[str, object]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_entity_or_raise(encounter, actor_id, label="actor")
        target = self._get_entity_or_raise(encounter, target_id, label="target")

        if not allow_out_of_turn_actor:
            self._ensure_actor_turn(encounter, actor_id)
        self._ensure_bonus_action_available(actor)
        self._ensure_touch_range(actor, target)
        requested_conditions = self._normalize_requested_conditions(remove_conditions)
        self._validate_inputs(
            heal_amount=heal_amount,
            cure_poison=cure_poison,
            requested_conditions=requested_conditions,
        )

        paladin = ensure_paladin_runtime(actor)
        lay_on_hands = paladin.get("lay_on_hands")
        if not isinstance(lay_on_hands, dict):
            raise ValueError("lay_on_hands_not_available")

        pool_remaining = lay_on_hands.get("pool_remaining")
        if not isinstance(pool_remaining, int):
            raise ValueError("lay_on_hands_pool_invalid")

        poison_removed = False
        invalid_requested_conditions = [
            condition
            for condition in requested_conditions
            if condition not in self._SUPPORTED_RESTORING_TOUCH_CONDITIONS
        ]
        valid_requested_conditions = [
            condition
            for condition in requested_conditions
            if condition in self._SUPPORTED_RESTORING_TOUCH_CONDITIONS
        ]
        conditions_removed = [condition for condition in valid_requested_conditions if condition in target.conditions]
        conditions_not_present = [
            condition
            for condition in valid_requested_conditions
            if condition not in conditions_removed
        ]
        poison_cost = 5 if cure_poison and "poisoned" in target.conditions else 0
        condition_removal_cost = 5 * len(conditions_removed)
        pool_spent = heal_amount + poison_cost + condition_removal_cost
        if pool_spent > pool_remaining:
            raise ValueError("lay_on_hands_pool_insufficient")

        hp_restored = 0
        if heal_amount > 0:
            hp_update = self.update_hp.execute(
                encounter_id=encounter_id,
                target_id=target_id,
                hp_change=-heal_amount,
                reason="paladin_lay_on_hands",
                source_entity_id=actor_id,
            )
            hp_restored = abs(int(hp_update.get("applied_change", 0) or 0))
            encounter = self._get_encounter_or_raise(encounter_id)
            actor = self._get_entity_or_raise(encounter, actor_id, label="actor")
            target = self._get_entity_or_raise(encounter, target_id, label="target")
            paladin = ensure_paladin_runtime(actor)
            lay_on_hands = paladin.get("lay_on_hands")
            if not isinstance(lay_on_hands, dict):
                raise ValueError("lay_on_hands_not_available")

        if cure_poison and "poisoned" in target.conditions:
            target.conditions = [condition for condition in target.conditions if condition != "poisoned"]
            poison_removed = True
        if conditions_removed:
            target.conditions = [condition for condition in target.conditions if condition not in conditions_removed]

        actor.action_economy["bonus_action_used"] = True
        lay_on_hands["pool_remaining"] = pool_remaining - pool_spent
        self.encounter_repository.save(encounter)

        self.append_event.execute(
            encounter_id=encounter_id,
            round=encounter.round,
            event_type="class_feature_lay_on_hands_used",
            actor_entity_id=actor_id,
            target_entity_id=target_id,
            payload={
                "class_feature_id": "paladin.lay_on_hands",
                "pool_spent": pool_spent,
                "pool_remaining": lay_on_hands["pool_remaining"],
                "hp_restored": hp_restored,
                "poison_removed": poison_removed,
                "conditions_removed": conditions_removed,
                "conditions_not_present": conditions_not_present,
                "invalid_requested_conditions": invalid_requested_conditions,
                "pool_spent_on_condition_removal": condition_removal_cost,
            },
        )

        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "target_id": target_id,
            "pool_spent": pool_spent,
            "pool_remaining": lay_on_hands["pool_remaining"],
            "hp_restored": hp_restored,
            "poison_removed": poison_removed,
            "conditions_requested": requested_conditions,
            "conditions_removed": conditions_removed,
            "conditions_not_present": conditions_not_present,
            "invalid_requested_conditions": invalid_requested_conditions,
            "pool_spent_on_condition_removal": condition_removal_cost,
            "encounter_state": self.get_encounter_state.execute(encounter_id),
        }

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_entity_or_raise(self, encounter: Encounter, entity_id: str, *, label: str) -> EncounterEntity:
        entity = encounter.entities.get(entity_id)
        if entity is None:
            raise ValueError(f"{label} '{entity_id}' not found in encounter")
        return entity

    def _ensure_actor_turn(self, encounter: Encounter, actor_id: str) -> None:
        if encounter.current_entity_id != actor_id:
            raise ValueError("not_actor_turn")

    def _ensure_bonus_action_available(self, actor: EncounterEntity) -> None:
        if bool(actor.action_economy.get("bonus_action_used")):
            raise ValueError("bonus_action_already_used")

    def _ensure_touch_range(self, actor: EncounterEntity, target: EncounterEntity) -> None:
        if self._distance_feet(actor, target) > 5:
            raise ValueError("target_out_of_range")

    def _distance_feet(self, actor: EncounterEntity, target: EncounterEntity) -> int:
        dx = abs(actor.position["x"] - target.position["x"])
        dy = abs(actor.position["y"] - target.position["y"])
        return max(dx, dy) * 5

    def _validate_inputs(
        self,
        *,
        heal_amount: int,
        cure_poison: bool,
        requested_conditions: list[str],
    ) -> None:
        if not isinstance(heal_amount, int) or heal_amount < 0:
            raise ValueError("heal_amount_invalid")
        if not isinstance(cure_poison, bool):
            raise ValueError("cure_poison_invalid")
        if heal_amount == 0 and not cure_poison and not requested_conditions:
            raise ValueError("lay_on_hands_no_effect")

    def _normalize_requested_conditions(self, remove_conditions: list[str] | None) -> list[str]:
        if remove_conditions is None:
            return []
        if not isinstance(remove_conditions, list):
            raise ValueError("remove_conditions_invalid")

        normalized: list[str] = []
        for condition in remove_conditions:
            if not isinstance(condition, str):
                raise ValueError("remove_conditions_invalid")
            normalized_condition = condition.strip().lower()
            if not normalized_condition:
                continue
            if normalized_condition in normalized:
                continue
            normalized.append(normalized_condition)
        return normalized
