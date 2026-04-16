from __future__ import annotations

from typing import Any

from tools.models.roll_result import RollResult
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.combat.shared.update_hp import UpdateHp
from tools.services.events.append_event import AppendEvent


class AttackRollResult:
    """处理一次攻击掷骰结果，判定命中并写入事件日志。"""

    def __init__(
        self,
        encounter_repository: EncounterRepository,
        append_event: AppendEvent,
        update_hp: UpdateHp | None = None,
    ):
        self.encounter_repository = encounter_repository
        self.append_event = append_event
        self.update_hp = update_hp

    def execute(
        self,
        *,
        encounter_id: str,
        roll_result: RollResult,
        attack_name: str | None = None,
        attack_kind: str | None = None,
        hp_change: int | None = None,
        damage_reason: str | None = None,
        damage_type: str | None = None,
        force_critical_on_hit: bool = False,
        concentration_vantage: str = "normal",
        enforce_current_turn_actor: bool = True,
    ) -> dict[str, Any]:
        """结算一次攻击掷骰。

        如果命中且提供了 `hp_change`，会继续自动调用 UpdateHp。
        """
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")

        if roll_result.encounter_id != encounter_id:
            raise ValueError("roll_result.encounter_id does not match encounter_id")
        if roll_result.roll_type not in {"attack_roll", "spell_attack"}:
            raise ValueError("roll_result must use an attack roll type")
        if roll_result.actor_entity_id not in encounter.entities:
            raise ValueError("actor_entity_id not found in encounter")
        if roll_result.target_entity_id is None:
            raise ValueError("target_entity_id is required for attack rolls")
        if roll_result.target_entity_id not in encounter.entities:
            raise ValueError("target_entity_id not found in encounter")
        if enforce_current_turn_actor and encounter.current_entity_id != roll_result.actor_entity_id:
            raise ValueError("attack roll actor must be the current entity")
        if hp_change is not None and self.update_hp is None:
            raise ValueError("update_hp service is required when hp_change is provided")

        target = encounter.entities[roll_result.target_entity_id]
        hit = roll_result.final_total >= target.ac
        is_critical_hit = self._is_critical_hit(roll_result)
        if force_critical_on_hit and hit:
            is_critical_hit = True
        result = {
            "encounter_id": encounter.encounter_id,
            "round": encounter.round,
            "actor_entity_id": roll_result.actor_entity_id,
            "target_entity_id": roll_result.target_entity_id,
            "attack_name": attack_name,
            "attack_kind": attack_kind or roll_result.roll_type,
            "final_total": roll_result.final_total,
            "target_ac": target.ac,
            "hit": hit,
            "is_critical_hit": is_critical_hit,
            "needs_damage_roll": hit,
            "comparison": {
                "left_label": "attack_total",
                "left_value": roll_result.final_total,
                "operator": ">=",
                "right_label": "target_ac",
                "right_value": target.ac,
                "passed": hit,
            },
        }

        event = self.append_event.execute(
            encounter_id=encounter.encounter_id,
            round=encounter.round,
            event_type="attack_resolved",
            actor_entity_id=roll_result.actor_entity_id,
            target_entity_id=roll_result.target_entity_id,
            request_id=roll_result.request_id,
            payload=result,
        )
        result["event_id"] = event.event_id

        # 命中后如果已经拿到了伤害值，就直接串到 update_hp。
        if hit and hp_change is not None:
            result["hp_update"] = self.update_hp.execute(
                encounter_id=encounter.encounter_id,
                target_id=roll_result.target_entity_id,
                hp_change=hp_change,
                reason=damage_reason or attack_name or "Attack damage",
                damage_type=damage_type,
                from_critical_hit=is_critical_hit,
                source_entity_id=roll_result.actor_entity_id,
                concentration_vantage=concentration_vantage,
            )

        return result

    def _is_critical_hit(self, roll_result: RollResult) -> bool:
        if bool(roll_result.metadata.get("is_critical_hit")):
            return True

        base_rolls = roll_result.dice_rolls.get("base_rolls", [])
        return isinstance(base_rolls, list) and 20 in base_rolls
