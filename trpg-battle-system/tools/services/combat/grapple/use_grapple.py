from __future__ import annotations

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.combat.grapple.shared import (
    build_active_grapple_payload,
    get_active_grapple_payload,
    grapple_size_is_legal,
    resolve_grapple_save_dc,
)
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.encounter.movement_rules import get_center_position


class UseGrapple:
    def __init__(self, encounter_repository: EncounterRepository):
        self.encounter_repository = encounter_repository
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(self, *, encounter_id: str, actor_id: str, target_id: str) -> dict[str, object]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)
        target = self._get_target_or_raise(encounter, target_id)
        self._ensure_actor_turn(encounter, actor_id)
        self._ensure_action_available(actor)
        self._ensure_target_is_enemy(actor, target)
        self._ensure_target_within_reach(actor, target)
        self._ensure_size_is_legal(actor, target)
        self._ensure_actor_has_no_active_grapple(actor)

        save_dc = resolve_grapple_save_dc(actor)
        target_save_total = max(
            int(target.ability_mods.get("str", 0)) + (int(target.proficiency_bonus or 0) if "str" in target.save_proficiencies else 0),
            int(target.ability_mods.get("dex", 0)) + (int(target.proficiency_bonus or 0) if "dex" in target.save_proficiencies else 0),
        )

        actor.action_economy["action_used"] = True
        if target_save_total < int(save_dc["dc"]):
            condition = f"grappled:{actor.entity_id}"
            if condition not in target.conditions:
                target.conditions.append(condition)
            if not isinstance(actor.combat_flags, dict):
                actor.combat_flags = {}
            actor.combat_flags["active_grapple"] = build_active_grapple_payload(actor=actor, target=target, save_dc=save_dc)
            status = "grappled"
        else:
            status = "saved"

        self.encounter_repository.save(encounter)
        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "target_id": target_id,
            "result": {"status": status},
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

    def _get_target_or_raise(self, encounter: Encounter, target_id: str) -> EncounterEntity:
        target = encounter.entities.get(target_id)
        if target is None:
            raise ValueError(f"target '{target_id}' not found in encounter")
        return target

    def _ensure_actor_turn(self, encounter: Encounter, actor_id: str) -> None:
        if encounter.current_entity_id != actor_id:
            raise ValueError("not_actor_turn")

    def _ensure_action_available(self, actor: EncounterEntity) -> None:
        if not isinstance(actor.action_economy, dict):
            actor.action_economy = {}
        if bool(actor.action_economy.get("action_used")):
            raise ValueError("action_already_used")

    def _ensure_target_is_enemy(self, actor: EncounterEntity, target: EncounterEntity) -> None:
        if actor.side == target.side:
            raise ValueError("grapple_target_must_be_enemy")

    def _ensure_target_within_reach(self, actor: EncounterEntity, target: EncounterEntity) -> None:
        actor_center = get_center_position(actor)
        target_center = get_center_position(target)
        dx = abs(actor_center["x"] - target_center["x"])
        dy = abs(actor_center["y"] - target_center["y"])
        if max(dx, dy) > 1:
            raise ValueError("grapple_target_out_of_range")

    def _ensure_size_is_legal(self, actor: EncounterEntity, target: EncounterEntity) -> None:
        if not grapple_size_is_legal(actor, target):
            raise ValueError("grapple_target_too_large")

    def _ensure_actor_has_no_active_grapple(self, actor: EncounterEntity) -> None:
        if get_active_grapple_payload(actor) is not None:
            raise ValueError("grapple_already_active")
