from __future__ import annotations

from uuid import uuid4

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.models.roll_request import RollRequest
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared.warlock_invocations import has_selected_warlock_invocation


class RequestConcentrationCheck:
    """在实体受到伤害后生成一次专注维持检定请求。"""

    def __init__(self, encounter_repository: EncounterRepository):
        self.encounter_repository = encounter_repository

    def execute(
        self,
        *,
        encounter_id: str,
        target_id: str,
        damage_taken: int,
        vantage: str = "normal",
        source_entity_id: str | None = None,
        reason: str | None = None,
    ) -> RollRequest:
        """根据实际受到的伤害计算专注检定 DC。

        当前按 2024 规则的通用骨架处理：
        - 受到伤害后进行 CON 豁免
        - DC = max(10, floor(damage_taken / 2))
        """
        encounter = self._get_encounter_or_raise(encounter_id)
        target = self._get_entity_or_raise(encounter, target_id)
        normalized_vantage = self._normalize_vantage(vantage)
        normalized_vantage = self._apply_eldritch_mind_vantage(target=target, current_vantage=normalized_vantage)

        if not bool(target.combat_flags.get("is_concentrating")):
            raise ValueError(f"entity '{target_id}' is not concentrating")
        if not isinstance(damage_taken, int) or damage_taken <= 0:
            raise ValueError("damage_taken must be an integer > 0")

        save_dc = max(10, damage_taken // 2)
        return RollRequest(
            request_id=self._generate_request_id(),
            encounter_id=encounter_id,
            actor_entity_id=target.entity_id,
            target_entity_id=target.entity_id,
            roll_type="concentration_check",
            formula="1d20+con_save_bonus",
            reason=reason or f"{target.name} makes a concentration check",
            context={
                "save_ability": "con",
                "save_dc": save_dc,
                "damage_taken": damage_taken,
                "vantage": normalized_vantage,
                "source_entity_id": source_entity_id,
                "source_entity_name": encounter.entities[source_entity_id].name
                if source_entity_id is not None and source_entity_id in encounter.entities
                else None,
            },
        )

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_entity_or_raise(self, encounter: Encounter, entity_id: str) -> EncounterEntity:
        entity = encounter.entities.get(entity_id)
        if entity is None:
            raise ValueError(f"entity '{entity_id}' not found in encounter")
        return entity

    def _normalize_vantage(self, vantage: str) -> str:
        if vantage not in {"normal", "advantage", "disadvantage"}:
            raise ValueError("vantage must be 'normal', 'advantage', or 'disadvantage'")
        return vantage

    def _apply_eldritch_mind_vantage(self, *, target: EncounterEntity, current_vantage: str) -> str:
        if not has_selected_warlock_invocation(target, "eldritch_mind"):
            return current_vantage
        if current_vantage == "disadvantage":
            return "normal"
        if current_vantage == "normal":
            return "advantage"
        return current_vantage

    def _generate_request_id(self) -> str:
        return f"req_concentration_{uuid4().hex[:12]}"
