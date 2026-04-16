from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.repositories.spell_definition_repository import SpellDefinitionRepository
from tools.repositories.zone_definition_repository import ZoneDefinitionRepository
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.events.append_event import AppendEvent
from tools.services.spells.area_geometry import build_spell_zone_instance
from tools.services.spells.build_spell_instance import build_spell_instance
from tools.services.spells.build_turn_effect_instance import build_turn_effect_instance
from tools.services.combat.shared.turn_actor_guard import (
    get_entity_or_raise,
    resolve_current_turn_actor_or_raise,
)

if TYPE_CHECKING:
    from tools.repositories.reaction_definition_repository import ReactionDefinitionRepository
    from tools.services.combat.rules.reactions.open_reaction_window import OpenReactionWindow


class EncounterCastSpell:
    """声明一次施法，并在需要时扣除法术位。"""

    def __init__(
        self,
        encounter_repository: EncounterRepository,
        append_event: AppendEvent,
        spell_definition_repository: SpellDefinitionRepository | None = None,
        zone_definition_repository: ZoneDefinitionRepository | None = None,
        open_reaction_window: "OpenReactionWindow" | None = None,
        reaction_definition_repository: "ReactionDefinitionRepository" | None = None,
    ):
        self.encounter_repository = encounter_repository
        self.append_event = append_event
        self.spell_definition_repository = spell_definition_repository or SpellDefinitionRepository()
        self.zone_definition_repository = zone_definition_repository or ZoneDefinitionRepository()
        if open_reaction_window is None:
            from tools.repositories.reaction_definition_repository import ReactionDefinitionRepository
            from tools.services.combat.rules.reactions.open_reaction_window import OpenReactionWindow

            reaction_definition_repository = reaction_definition_repository or ReactionDefinitionRepository()
            open_reaction_window = OpenReactionWindow(encounter_repository, reaction_definition_repository)
        self.open_reaction_window = open_reaction_window

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str | None = None,
        spell_id: str,
        target_ids: list[str] | None = None,
        target_point: dict[str, Any] | None = None,
        cast_level: int | None = None,
        reason: str | None = None,
        include_encounter_state: bool = False,
        apply_no_roll_immediate_effects: bool = True,
        allow_out_of_turn_actor: bool = False,
    ) -> dict[str, Any]:
        """声明当前行动者施放一个法术。

        当前这一层先做三件事：
        1. 校验当前行动者和法术是否存在
        2. 如果是非戏法，则扣除法术位
        3. 记录一条 `spell_declared` 事件

        真正的命中、豁免、伤害和 condition 处理，交给后续独立 service。
        """
        encounter = self._get_encounter_or_raise(encounter_id)
        caster = self._get_caster_or_raise(
            encounter,
            actor_id=actor_id,
            allow_out_of_turn_actor=allow_out_of_turn_actor,
        )
        spell_definition = self._get_spell_definition_or_raise(encounter, caster, spell_id)
        resolved_target_ids = self._resolve_target_ids(encounter, target_ids or [])
        action_cost = self._resolve_action_cost(spell_definition)

        spell_level = self._resolve_spell_level(spell_definition)
        resolved_cast_level = cast_level if cast_level is not None else spell_level
        if spell_level > 0 and resolved_cast_level < spell_level:
            raise ValueError("cast_level cannot be lower than the spell's base level")

        slot_consumed = self._consume_spell_slot_if_needed(caster, spell_level, resolved_cast_level)
        resolved_spell_id = spell_definition.get("spell_id") or spell_definition.get("id") or spell_id
        resolved_spell_name = spell_definition.get("name") or spell_id
        spell_action_id = f"spell_{uuid4().hex[:12]}"
        trigger_event = {
            "event_id": f"evt_spell_declared_{uuid4().hex[:12]}",
            "trigger_type": "spell_declared",
            "host_action_type": "spell_cast",
            "host_action_id": spell_action_id,
            "host_action_snapshot": {
                "spell_action_id": spell_action_id,
                "caster_entity_id": caster.entity_id,
                "spell_id": resolved_spell_id,
                "spell_level": spell_level,
                "cast_level": resolved_cast_level,
                "target_ids": list(resolved_target_ids),
                "target_point": target_point,
                "action_cost": action_cost,
                "phase": "before_spell_resolves",
            },
            "caster_entity_id": caster.entity_id,
            "target_entity_id": caster.entity_id,
        }
        window_result = self.open_reaction_window.execute(
            encounter_id=encounter_id,
            trigger_event=trigger_event,
        )
        if window_result["status"] == "waiting_reaction":
            return {
                "status": "waiting_reaction",
                "pending_reaction_window": window_result["pending_reaction_window"],
                "reaction_requests": window_result["reaction_requests"],
                "encounter_state": GetEncounterState(self.encounter_repository).execute(encounter_id),
            }
        turn_effect_updates: list[dict[str, Any]] = []
        spell_instance: dict[str, Any] | None = None
        if apply_no_roll_immediate_effects:
            turn_effect_updates = self._maybe_apply_no_roll_turn_effects(
                encounter=encounter,
                caster=caster,
                target_ids=resolved_target_ids,
                spell_definition=spell_definition,
            )
            spell_instance = self._maybe_build_no_roll_spell_instance(
                encounter=encounter,
                caster=caster,
                spell_definition=spell_definition,
                cast_level=resolved_cast_level,
                target_ids=resolved_target_ids,
                turn_effect_updates=turn_effect_updates,
            )
        zone_updates: list[dict[str, Any]] = []
        if self._is_sustained_area_spell(spell_definition):
            normalized_target_point = self._normalize_target_point(target_point)
            if normalized_target_point is None:
                raise ValueError("sustained_area_spell_requires_target_point")
            if spell_instance is None:
                spell_instance = build_spell_instance(
                    spell_definition=spell_definition,
                    caster=caster,
                    cast_level=resolved_cast_level,
                    targets=[],
                    started_round=encounter.round,
                )
                encounter.spell_instances.append(spell_instance)
            zone = self._build_sustained_spell_zone(
                encounter=encounter,
                caster=caster,
                spell_definition=spell_definition,
                target_point=normalized_target_point,
                spell_instance=spell_instance,
            )
            encounter.map.zones.append(zone)
            special_runtime = spell_instance.get("special_runtime")
            if not isinstance(special_runtime, dict):
                special_runtime = {"linked_zone_ids": []}
                spell_instance["special_runtime"] = special_runtime
            linked_zone_ids = special_runtime.get("linked_zone_ids")
            if not isinstance(linked_zone_ids, list):
                linked_zone_ids = []
                special_runtime["linked_zone_ids"] = linked_zone_ids
            linked_zone_ids.append(zone["zone_id"])
            zone_updates.append({"zone_id": zone["zone_id"], "target_point": normalized_target_point})
        payload = {
            "spell_id": resolved_spell_id,
            "spell_name": resolved_spell_name,
            "spell_level": spell_level,
            "cast_level": resolved_cast_level,
            "target_ids": resolved_target_ids,
            "target_point": target_point,
            "requires_attack_roll": spell_definition.get("requires_attack_roll", False),
            "save_ability": spell_definition.get("save_ability"),
            "damage": spell_definition.get("damage", []),
            "spell_definition": spell_definition,
            "slot_consumed": slot_consumed,
            "action_cost": action_cost,
            "turn_effect_updates": turn_effect_updates,
            "spell_instance": spell_instance,
            "zone_updates": zone_updates,
            "reason": reason or f"Cast {resolved_spell_name}",
        }
        previous_action_economy = dict(caster.action_economy) if isinstance(caster.action_economy, dict) else {}
        self._consume_action_cost_if_needed(caster, action_cost)
        self.encounter_repository.save(encounter)
        try:
            event = self.append_event.execute(
                encounter_id=encounter.encounter_id,
                round=encounter.round,
                event_type="spell_declared",
                actor_entity_id=caster.entity_id,
                payload=payload,
            )
        except Exception:
            self._rollback_spell_slot_if_needed(caster, slot_consumed)
            caster.action_economy = previous_action_economy
            self.encounter_repository.save(encounter)
            raise

        result = {
            "encounter_id": encounter.encounter_id,
            "caster_entity_id": caster.entity_id,
            "spell_id": resolved_spell_id,
            "spell_name": resolved_spell_name,
            "spell_level": spell_level,
            "cast_level": resolved_cast_level,
            "target_ids": resolved_target_ids,
            "target_point": target_point,
            "slot_consumed": slot_consumed,
            "action_cost": action_cost,
            "turn_effect_updates": turn_effect_updates,
            "spell_instance": spell_instance,
            "zone_updates": zone_updates,
            "event_id": event.event_id,
            "event_type": event.event_type,
        }
        if include_encounter_state:
            result["encounter_state"] = GetEncounterState(self.encounter_repository).execute(encounter_id)
        return result

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_caster_or_raise(
        self,
        encounter: Encounter,
        *,
        actor_id: str | None,
        allow_out_of_turn_actor: bool,
    ) -> EncounterEntity:
        return resolve_current_turn_actor_or_raise(
            encounter,
            actor_id=actor_id,
            allow_out_of_turn_actor=allow_out_of_turn_actor,
            entity_label="actor",
        )

    def _get_spell_definition_or_raise(
        self,
        encounter: Encounter,
        caster: EncounterEntity,
        spell_id: str,
    ) -> dict[str, Any]:
        global_spell_definition = self.spell_definition_repository.get(spell_id)
        if isinstance(global_spell_definition, dict):
            return global_spell_definition

        encounter_metadata = getattr(encounter, "metadata", None)
        if isinstance(encounter_metadata, dict):
            encounter_spell_definitions = encounter_metadata.get("spell_definitions")
            if isinstance(encounter_spell_definitions, dict):
                spell_definition = encounter_spell_definitions.get(spell_id)
                if isinstance(spell_definition, dict):
                    return spell_definition

        source_ref_spell_definitions = caster.source_ref.get("spell_definitions")
        if isinstance(source_ref_spell_definitions, dict):
            spell_definition = source_ref_spell_definitions.get(spell_id)
            if isinstance(spell_definition, dict):
                return spell_definition

        for spell in caster.spells:
            if spell.get("spell_id") == spell_id:
                embedded_spell_definition = spell.get("spell_definition")
                if isinstance(embedded_spell_definition, dict):
                    return embedded_spell_definition
                return spell
        raise ValueError(f"spell '{spell_id}' not found on caster '{caster.entity_id}'")

    def _resolve_target_ids(self, encounter: Encounter, target_ids: list[str]) -> list[str]:
        normalized_target_ids: list[str] = []
        for target_id in target_ids:
            normalized_target_ids.append(
                get_entity_or_raise(encounter, target_id, entity_label="target").entity_id
            )
        return normalized_target_ids

    def _resolve_spell_level(self, spell: dict[str, Any]) -> int:
        spell_level = spell.get("level", 0)
        if not isinstance(spell_level, int) or spell_level < 0:
            raise ValueError("spell.level must be an integer >= 0")
        return spell_level

    def _consume_spell_slot_if_needed(
        self,
        caster: EncounterEntity,
        spell_level: int,
        cast_level: int,
    ) -> dict[str, Any] | None:
        # 戏法不消耗法术位，所以这里直接返回 None。
        if spell_level == 0:
            return None

        spell_slots = caster.resources.get("spell_slots")
        if not isinstance(spell_slots, dict):
            raise ValueError("caster.resources.spell_slots must be a dict")
        slot_key = str(cast_level)
        slot_info = spell_slots.get(slot_key)
        if not isinstance(slot_info, dict):
            raise ValueError(f"spell slot level '{slot_key}' is not available")
        remaining = slot_info.get("remaining")
        if not isinstance(remaining, int):
            raise ValueError(f"spell slot level '{slot_key}' remaining must be an integer")
        if remaining <= 0:
            raise ValueError(f"spell slot level '{slot_key}' has no remaining uses")

        before = remaining
        slot_info["remaining"] = before - 1
        return {
            "slot_level": cast_level,
            "remaining_before": before,
            "remaining_after": slot_info["remaining"],
        }

    def _rollback_spell_slot_if_needed(
        self,
        caster: EncounterEntity,
        slot_consumed: dict[str, Any] | None,
    ) -> None:
        if slot_consumed is None:
            return

        spell_slots = caster.resources.get("spell_slots")
        if not isinstance(spell_slots, dict):
            return
        slot_key = str(slot_consumed.get("slot_level"))
        slot_info = spell_slots.get(slot_key)
        if not isinstance(slot_info, dict):
            return
        remaining_before = slot_consumed.get("remaining_before")
        if isinstance(remaining_before, int):
            slot_info["remaining"] = remaining_before

    def _resolve_action_cost(self, spell_definition: dict[str, Any]) -> str | None:
        resolution = spell_definition.get("resolution")
        if isinstance(resolution, dict):
            activation = resolution.get("activation")
            if isinstance(activation, str):
                normalized = activation.strip().lower().replace(" ", "_")
                if normalized in {"action", "bonus_action", "reaction"}:
                    return normalized
        base = spell_definition.get("base")
        if isinstance(base, dict):
            casting_time = base.get("casting_time")
            if isinstance(casting_time, str):
                lowered = casting_time.strip().lower()
                if "bonus" in lowered:
                    return "bonus_action"
                if "reaction" in lowered:
                    return "reaction"
                if "action" in lowered:
                    return "action"
        return None

    def _consume_action_cost_if_needed(self, caster: EncounterEntity, action_cost: str | None) -> None:
        if not isinstance(caster.action_economy, dict):
            caster.action_economy = {}
        if action_cost == "action":
            caster.action_economy["action_used"] = True
        elif action_cost == "bonus_action":
            caster.action_economy["bonus_action_used"] = True
        elif action_cost == "reaction":
            caster.action_economy["reaction_used"] = True

    def _maybe_apply_no_roll_turn_effects(
        self,
        *,
        encounter: Encounter,
        caster: EncounterEntity,
        target_ids: list[str],
        spell_definition: dict[str, Any],
    ) -> list[dict[str, Any]]:
        resolution = spell_definition.get("resolution")
        if not isinstance(resolution, dict):
            return []
        if resolution.get("mode") != "no_roll":
            return []

        on_cast = spell_definition.get("on_cast")
        if not isinstance(on_cast, dict):
            return []
        on_resolve = on_cast.get("on_resolve")
        if not isinstance(on_resolve, dict):
            return []

        raw_effects = on_resolve.get("apply_turn_effects", [])
        if not isinstance(raw_effects, list) or not raw_effects:
            return []

        updates: list[dict[str, Any]] = []
        for target_id in target_ids:
            target = encounter.entities.get(target_id)
            if target is None:
                continue
            for index, item in enumerate(raw_effects):
                if not isinstance(item, dict):
                    raise ValueError(f"apply_turn_effects[{index}] must be a dict")
                effect_template_id = item.get("effect_template_id")
                if not isinstance(effect_template_id, str) or not effect_template_id.strip():
                    raise ValueError(f"apply_turn_effects[{index}].effect_template_id must be a non-empty string")
                instance = build_turn_effect_instance(
                    spell_definition=spell_definition,
                    effect_template_id=effect_template_id.strip(),
                    caster=caster,
                    save_dc=None,
                )
                target.turn_effects.append(instance)
                updates.append(
                    {
                        "target_id": target_id,
                        "effect_id": instance["effect_id"],
                        "effect_template_id": effect_template_id.strip(),
                        "trigger": instance.get("trigger"),
                    }
                )
        return updates

    def _maybe_build_no_roll_spell_instance(
        self,
        *,
        encounter: Encounter,
        caster: EncounterEntity,
        spell_definition: dict[str, Any],
        cast_level: int,
        target_ids: list[str],
        turn_effect_updates: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        resolution = spell_definition.get("resolution")
        if not isinstance(resolution, dict) or resolution.get("mode") != "no_roll":
            return None
        if not target_ids:
            return None

        updates_by_target: dict[str, list[str]] = {}
        for update in turn_effect_updates:
            if not isinstance(update, dict):
                continue
            target_id = update.get("target_id")
            effect_id = update.get("effect_id")
            if not isinstance(target_id, str) or not isinstance(effect_id, str):
                continue
            updates_by_target.setdefault(target_id, []).append(effect_id)

        targets = [
            {
                "entity_id": target_id,
                "applied_conditions": [],
                "turn_effect_ids": updates_by_target.get(target_id, []),
            }
            for target_id in target_ids
        ]
        instance = build_spell_instance(
            spell_definition=spell_definition,
            caster=caster,
            cast_level=cast_level,
            targets=targets,
            started_round=encounter.round,
        )
        encounter.spell_instances.append(instance)
        return instance

    def _is_sustained_area_spell(self, spell_definition: dict[str, Any]) -> bool:
        area_template = spell_definition.get("area_template")
        return isinstance(area_template, dict) and area_template.get("persistence") == "sustained"

    def _normalize_target_point(self, target_point: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(target_point, dict):
            return None
        x = target_point.get("x")
        y = target_point.get("y")
        if not isinstance(x, int) or not isinstance(y, int):
            return None
        anchor = target_point.get("anchor", "cell_center")
        if anchor != "cell_center":
            return None
        return {
            "x": x,
            "y": y,
            "anchor": "cell_center",
        }

    def _build_sustained_spell_zone(
        self,
        *,
        encounter: Encounter,
        caster: EncounterEntity,
        spell_definition: dict[str, Any],
        target_point: dict[str, Any],
        spell_instance: dict[str, Any],
    ) -> dict[str, Any]:
        area_template = spell_definition.get("area_template")
        if not isinstance(area_template, dict):
            raise ValueError("sustained_area_spell_requires_area_template")
        zone_definition = None
        zone_definition_id = area_template.get("zone_definition_id")
        if isinstance(zone_definition_id, str) and zone_definition_id.strip():
            zone_definition = self.zone_definition_repository.get(zone_definition_id.strip())
        return build_spell_zone_instance(
            encounter=encounter,
            spell_definition=spell_definition,
            caster=caster,
            target_point=target_point,
            persistence="sustained",
            zone_definition=zone_definition,
            spell_instance_id=spell_instance.get("instance_id"),
        )
