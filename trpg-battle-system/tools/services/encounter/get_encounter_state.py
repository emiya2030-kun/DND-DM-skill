from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.repositories.event_repository import EventRepository
from tools.services.combat.attack.weapon_mastery_effects import (
    build_weapon_mastery_effect_labels,
    get_weapon_mastery_speed_penalty,
)
from tools.services.map.build_map_notes import BuildMapNotes
from tools.services.map.render_battlemap_view import RenderBattlemapView


class GetEncounterState:
    """把底层 Encounter 投影成 `get_encounter_state` 视图对象。"""

    def __init__(
        self,
        repository: EncounterRepository,
        event_repository: EventRepository | None = None,
        battlemap_view_service: RenderBattlemapView | None = None,
        map_notes_service: BuildMapNotes | None = None,
    ):
        self.repository = repository
        self.event_repository = event_repository
        self.battlemap_view_service = battlemap_view_service or RenderBattlemapView()
        self.map_notes_service = map_notes_service or BuildMapNotes()

    def execute(self, encounter_id: str) -> dict[str, Any]:
        """读取指定 encounter，并返回视图层对象。"""
        encounter = self.repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")

        current_entity = self._get_current_entity(encounter)
        recent_forced_movement = self._build_recent_forced_movement(encounter)
        recent_turn_effects = self._build_recent_turn_effects(encounter)
        recent_activity = self._build_recent_activity(encounter)
        spell_area_overlays = self._build_spell_area_overlays(encounter)
        return {
            "encounter_id": encounter.encounter_id,
            "encounter_name": encounter.name,
            "round": encounter.round,
            "current_turn_entity": self._build_current_turn_entity(encounter, current_entity),
            "turn_order": self._build_turn_order(encounter, current_entity),
            "active_spell_summaries": self._build_active_spell_summaries(encounter),
            "retargetable_spell_actions": self._build_retargetable_spell_actions(
                encounter,
                current_entity=current_entity,
            ),
            "battlemap_details": self._build_battlemap_details(encounter),
            "battlemap_view": self.battlemap_view_service.execute(
                encounter,
                recent_forced_movement=recent_forced_movement,
                recent_turn_effects=recent_turn_effects,
                recent_activity=recent_activity,
                spell_area_overlays=spell_area_overlays,
            ),
            "map_notes": self.map_notes_service.execute(encounter),
            "reaction_requests": self._build_reaction_requests(encounter),
            "pending_reaction_window": self._build_pending_reaction_window(encounter),
            "pending_movement": self._build_pending_movement(encounter),
            "spell_area_overlays": spell_area_overlays,
            "recent_activity": recent_activity,
            "recent_forced_movement": recent_forced_movement,
            "recent_turn_effects": recent_turn_effects,
            "encounter_notes": encounter.encounter_notes,
        }

    def _get_current_entity(self, encounter: Encounter) -> EncounterEntity | None:
        if encounter.current_entity_id is None:
            return None
        return encounter.entities.get(encounter.current_entity_id)

    def _build_current_turn_entity(
        self,
        encounter: Encounter,
        entity: EncounterEntity | None,
    ) -> dict[str, Any] | None:
        if entity is None:
            return None

        return {
            "id": entity.entity_id,
            "name": entity.name,
            "level": self._extract_level(entity),
            "hp": self._format_hp(entity),
            "class": entity.entity_def_id,
            "description": self._extract_description(entity),
            "position": self._format_position(entity),
            "movement_remaining": f"{entity.speed['remaining']} feet",
            "ac": entity.ac,
            "speed": max(0, entity.speed["walk"] - get_weapon_mastery_speed_penalty(entity)),
            "spell_save_dc": self._calculate_spell_save_dc(entity),
            "available_actions": {
                "weapons": self._build_weapons_view(entity),
                "spells": self._build_spells_view(entity),
                "spell_slots_available": self._build_spell_slots_view(entity),
            },
            "actions": self._build_actions(entity),
            "weapon_ranges": self._build_weapon_ranges(encounter, entity),
            "conditions": self._format_conditions(encounter, entity),
            "ongoing_effects": self._build_entity_ongoing_effects(encounter, entity),
            "resources": self._build_resources_view(entity),
            "death_saves": self._format_death_saves(entity),
        }

    def _build_turn_order(
        self,
        encounter: Encounter,
        current_entity: EncounterEntity | None,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for entity_id in encounter.turn_order:
            entity = encounter.entities[entity_id]
            items.append(
                {
                    "id": entity.entity_id,
                    "name": entity.name,
                    "type": entity.side,
                    "hp": self._format_hp_status(entity),
                    "ac": entity.ac,
                    "position": self._format_position(entity),
                    "distance_from_current_turn_entity": self._format_distance_from_current(entity, current_entity),
                    "conditions": self._format_conditions(encounter, entity),
                    "ongoing_effects": self._build_entity_ongoing_effects(encounter, entity),
                }
            )
        return items

    def _build_active_spell_summaries(self, encounter: Encounter) -> list[str]:
        summaries: list[str] = []
        for instance in encounter.spell_instances:
            lifecycle = instance.get("lifecycle", {})
            if lifecycle.get("status") != "active":
                continue

            concentration = instance.get("concentration", {})
            caster_name = instance.get("caster_name") or "未知施法者"
            spell_name = instance.get("spell_name") or instance.get("spell_id") or "未知法术"
            if concentration.get("required") and concentration.get("active"):
                summaries.append(f"{caster_name}正在专注：{spell_name}")
            else:
                summaries.append(f"{caster_name}维持效果：{spell_name}")
        return summaries

    def _build_entity_ongoing_effects(self, encounter: Encounter, entity: EncounterEntity) -> list[str]:
        effect_labels: list[str] = []
        for instance in encounter.spell_instances:
            if not self._is_active_spell_instance(instance):
                continue
            for target in instance.get("targets", []):
                if target.get("entity_id") != entity.entity_id:
                    continue
                effect_labels.append(self._format_spell_source_label(instance))
        effect_labels.extend(build_weapon_mastery_effect_labels(entity))
        return self._dedupe_preserve_order(effect_labels)

    def _build_retargetable_spell_actions(
        self,
        encounter: Encounter,
        *,
        current_entity: EncounterEntity | None,
    ) -> list[dict[str, Any]]:
        if current_entity is None:
            return []

        actions: list[dict[str, Any]] = []
        for instance in encounter.spell_instances:
            if not self._is_active_spell_instance(instance):
                continue
            if instance.get("caster_entity_id") != current_entity.entity_id:
                continue

            special_runtime = instance.get("special_runtime")
            if not isinstance(special_runtime, dict):
                continue
            if not bool(special_runtime.get("retargetable")):
                continue
            if not bool(special_runtime.get("retarget_available")):
                continue

            previous_target_id = self._extract_previous_target_id(instance)
            actions.append(
                {
                    "spell_instance_id": instance.get("instance_id"),
                    "spell_id": instance.get("spell_id"),
                    "spell_name": instance.get("spell_name"),
                    "caster_entity_id": instance.get("caster_entity_id"),
                    "caster_name": instance.get("caster_name"),
                    "previous_target_id": previous_target_id,
                    "previous_target_name": self._entity_name_or_fallback(encounter, previous_target_id, "未知目标"),
                    "activation": special_runtime.get("retarget_activation"),
                }
            )
        return actions

    def _build_battlemap_details(self, encounter: Encounter) -> dict[str, Any]:
        return {
            "name": encounter.map.name,
            "description": encounter.map.description,
            "dimensions": f"{encounter.map.width} x {encounter.map.height} tiles",
            "grid_size": f"Each tile represents {encounter.map.grid_size_feet} feet",
        }

    def _build_reaction_requests(self, encounter: Encounter) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for request in encounter.reaction_requests:
            if not isinstance(request, dict):
                continue
            items.append(
                {
                    "request_id": request.get("request_id"),
                    "reaction_type": request.get("reaction_type"),
                    "trigger_type": request.get("trigger_type"),
                    "status": request.get("status"),
                    "actor_entity_id": request.get("actor_entity_id"),
                    "actor_name": request.get("actor_name"),
                    "target_entity_id": request.get("target_entity_id"),
                    "target_name": request.get("target_name"),
                    "ask_player": bool(request.get("ask_player")),
                    "auto_resolve": bool(request.get("auto_resolve")),
                    "source_event_type": request.get("source_event_type"),
                    "source_event_id": request.get("source_event_id"),
                    "payload": request.get("payload", {}),
                }
            )
        return items

    def _build_pending_movement(self, encounter: Encounter) -> dict[str, Any] | None:
        pending = encounter.pending_movement
        if not isinstance(pending, dict):
            return None
        return {
            "movement_id": pending.get("movement_id"),
            "entity_id": pending.get("entity_id"),
            "start_position": pending.get("start_position"),
            "target_position": pending.get("target_position"),
            "current_position": pending.get("current_position"),
            "remaining_path": pending.get("remaining_path", []),
            "count_movement": bool(pending.get("count_movement", True)),
            "use_dash": bool(pending.get("use_dash", False)),
            "status": pending.get("status"),
            "waiting_request_id": pending.get("waiting_request_id"),
        }

    def _build_pending_reaction_window(self, encounter: Encounter) -> dict[str, Any] | None:
        pending = encounter.pending_reaction_window
        if not isinstance(pending, dict):
            return None
        return {
            "window_id": pending.get("window_id"),
            "status": pending.get("status"),
            "trigger_event_id": pending.get("trigger_event_id"),
            "trigger_type": pending.get("trigger_type"),
            "blocking": pending.get("blocking"),
            "host_action_type": pending.get("host_action_type"),
            "host_action_id": pending.get("host_action_id"),
            "host_action_snapshot": pending.get("host_action_snapshot", {}),
            "choice_groups": pending.get("choice_groups", []),
            "resolved_group_ids": pending.get("resolved_group_ids", []),
        }

    def _build_spell_area_overlays(self, encounter: Encounter) -> list[dict[str, Any]]:
        overlays: list[dict[str, Any]] = []
        for note in encounter.encounter_notes:
            if not isinstance(note, dict) or note.get("type") != "spell_area_overlay":
                continue
            payload = note.get("payload")
            if isinstance(payload, dict):
                overlays.append(dict(payload))
        return overlays[-1:]

    def _build_recent_forced_movement(self, encounter: Encounter) -> dict[str, Any] | None:
        events = self._list_events_for_encounter(encounter.encounter_id)
        latest_event = None
        latest_index = None
        for index, event in enumerate(events):
            if event.event_type == "forced_movement_resolved":
                latest_event = event
                latest_index = index
        if latest_event is None:
            return None
        if latest_index is not None and latest_index < len(events) - 1:
            return None

        payload = latest_event.payload if isinstance(latest_event.payload, dict) else {}
        source_entity_id = payload.get("source_entity_id") or latest_event.actor_entity_id
        target_entity_id = latest_event.target_entity_id
        source_name = self._entity_name_or_fallback(encounter, source_entity_id, "未知单位")
        target_name = self._entity_name_or_fallback(encounter, target_entity_id, "未知单位")
        start_position = self._normalize_position(payload.get("from_position"))
        final_position = self._normalize_position(payload.get("to_position"))
        attempted_path = self._normalize_path(payload.get("attempted_path"))
        resolved_path = self._normalize_path(payload.get("resolved_path"))
        moved_feet = int(payload.get("moved_feet", 0) or 0)
        blocked = bool(payload.get("blocked", False))
        block_reason = payload.get("block_reason")
        reason = str(payload.get("reason") or "forced_movement")

        return {
            "reason": reason,
            "source_entity_id": source_entity_id,
            "source_name": source_name,
            "target_entity_id": target_entity_id,
            "target_name": target_name,
            "start_position": start_position,
            "final_position": final_position,
            "attempted_path": attempted_path,
            "resolved_path": resolved_path,
            "moved_feet": moved_feet,
            "blocked": blocked,
            "block_reason": block_reason,
            "summary": self._format_forced_movement_summary(
                reason=reason,
                target_name=target_name,
                moved_feet=moved_feet,
                final_position=final_position,
                blocked=blocked,
                block_reason=block_reason,
            ),
        }

    def _build_recent_turn_effects(self, encounter: Encounter) -> list[dict[str, Any]]:
        events = self._list_events_for_encounter(encounter.encounter_id)
        if not events:
            return []
        if events[-1].event_type != "turn_effect_resolved":
            return []

        recent_events: list[Any] = []
        for event in reversed(events):
            if event.event_type != "turn_effect_resolved":
                break
            recent_events.append(event)
        recent_events.reverse()

        items: list[dict[str, Any]] = []
        for event in recent_events:
            payload = event.payload if isinstance(event.payload, dict) else {}
            source_entity_id = payload.get("source_entity_id") or event.actor_entity_id
            target_entity_id = payload.get("target_entity_id") or event.target_entity_id
            name = str(payload.get("name") or "持续效果")
            trigger = str(payload.get("trigger") or "")
            source_name = self._entity_name_or_fallback(encounter, source_entity_id, "未知来源")
            target_name = self._entity_name_or_fallback(encounter, target_entity_id, "未知目标")

            items.append(
                {
                    "effect_id": payload.get("effect_id"),
                    "name": name,
                    "trigger": trigger,
                    "source_entity_id": source_entity_id,
                    "source_name": source_name,
                    "target_entity_id": target_entity_id,
                    "target_name": target_name,
                    "save": payload.get("save"),
                    "condition_updates": payload.get("condition_updates", []),
                    "effect_removed": bool(payload.get("effect_removed", False)),
                    "summary": self._format_turn_effect_summary(
                        name=name,
                        trigger=trigger,
                        source_name=source_name,
                        target_name=target_name,
                        save=payload.get("save"),
                        trigger_damage_resolution=payload.get("trigger_damage_resolution"),
                        success_damage_resolution=payload.get("success_damage_resolution"),
                        failure_damage_resolution=payload.get("failure_damage_resolution"),
                        condition_updates=payload.get("condition_updates"),
                        effect_removed=bool(payload.get("effect_removed", False)),
                    ),
                }
            )
        return items

    def _build_recent_activity(self, encounter: Encounter) -> list[dict[str, Any]]:
        events = self._list_events_for_encounter(encounter.encounter_id)
        items: list[dict[str, Any]] = []
        for event in reversed(events):
            item = self._build_recent_activity_item(encounter, event)
            if item is None:
                continue
            items.append(item)
            if len(items) >= 6:
                break
        return items

    def _build_recent_activity_item(self, encounter: Encounter, event: Any) -> dict[str, Any] | None:
        event_type = getattr(event, "event_type", None)
        if not isinstance(event_type, str):
            return None

        payload = event.payload if isinstance(event.payload, dict) else {}
        actor_name = self._entity_name_or_fallback(encounter, event.actor_entity_id, "未知单位")
        target_name = self._entity_name_or_fallback(encounter, event.target_entity_id, "未知目标")
        summary = self._format_recent_activity_summary(
            encounter=encounter,
            event_type=event_type,
            payload=payload,
            actor_name=actor_name,
            target_name=target_name,
        )
        if summary is None:
            return None

        return {
            "event_id": event.event_id,
            "event_type": event_type,
            "round": event.round,
            "actor_entity_id": event.actor_entity_id,
            "actor_name": actor_name,
            "target_entity_id": event.target_entity_id,
            "target_name": target_name,
            "summary": summary,
        }

    def _format_recent_activity_summary(
        self,
        *,
        encounter: Encounter,
        event_type: str,
        payload: dict[str, Any],
        actor_name: str,
        target_name: str,
    ) -> str | None:
        if event_type == "movement_resolved":
            from_position = self._format_compact_position(self._normalize_position(payload.get("from_position")))
            to_position = self._format_compact_position(self._normalize_position(payload.get("to_position")))
            feet_cost = payload.get("feet_cost")
            dash_text = "，使用了疾跑" if bool(payload.get("used_dash")) else ""
            cost_text = f"，消耗 {feet_cost} 尺移动力" if isinstance(feet_cost, int) else ""
            return f"{actor_name}从 {from_position} 移动到 {to_position}{cost_text}{dash_text}。"
        if event_type == "attack_resolved":
            attack_name = payload.get("attack_name") or "攻击"
            final_total = payload.get("final_total")
            target_ac = payload.get("target_ac")
            if bool(payload.get("hit")):
                critical_text = "，造成重击" if bool(payload.get("is_critical_hit")) else ""
                return f"{actor_name}用{attack_name}命中{target_name}（{final_total} 对 AC {target_ac}）{critical_text}。"
            return f"{actor_name}用{attack_name}攻击{target_name}未命中（{final_total} 对 AC {target_ac}）。"
        if event_type == "damage_applied":
            hp_change = payload.get("hp_change")
            reason = payload.get("reason") or "伤害"
            if isinstance(hp_change, int):
                return f"{actor_name}对{target_name}造成 {hp_change} 点伤害（{reason}）。"
            return f"{target_name}受到伤害（{reason}）。"
        if event_type == "healing_applied":
            hp_change = payload.get("hp_change")
            reason = payload.get("reason") or "治疗"
            if isinstance(hp_change, int):
                return f"{actor_name}为{target_name}恢复 {abs(hp_change)} 点生命（{reason}）。"
            return f"{target_name}恢复了生命值（{reason}）。"
        if event_type == "spell_declared":
            spell_name = payload.get("spell_name") or payload.get("spell_id") or "法术"
            target_ids = payload.get("target_ids")
            target_label = ""
            if isinstance(target_ids, list) and target_ids:
                target_names = [
                    self._entity_name_or_fallback(encounter, target_id, "未知目标")
                    for target_id in target_ids
                    if isinstance(target_id, str)
                ]
                if target_names:
                    target_label = f"，目标：{'、'.join(target_names)}"
            cast_level = payload.get("cast_level")
            cast_level_text = f"（{cast_level}环）" if isinstance(cast_level, int) and cast_level > 0 else ""
            return f"{actor_name}施放了{spell_name}{cast_level_text}{target_label}。"
        if event_type == "saving_throw_resolved":
            spell_name = payload.get("spell_name") or payload.get("spell_id") or "法术效果"
            save_ability = str(payload.get("save_ability") or "").upper()
            final_total = payload.get("final_total")
            save_dc = payload.get("save_dc")
            result = "成功" if bool(payload.get("success")) else "失败"
            if save_ability:
                return f"{target_name}对{spell_name}进行 {save_ability} 豁免，结果 {final_total} 对 DC {save_dc}，{result}。"
            return f"{target_name}对{spell_name}进行豁免，结果 {result}。"
        if event_type == "forced_movement_resolved":
            source_entity_id = payload.get("source_entity_id")
            target_entity_id = payload.get("target_entity_id")
            source_name = self._entity_name_or_fallback(encounter, source_entity_id, actor_name)
            forced_target_name = self._entity_name_or_fallback(encounter, target_entity_id, target_name)
            return self._format_forced_movement_summary(
                reason=str(payload.get("reason") or "forced_movement"),
                target_name=forced_target_name,
                moved_feet=int(payload.get("moved_feet", 0) or 0),
                final_position=self._normalize_position(payload.get("to_position")),
                blocked=bool(payload.get("blocked", False)),
                block_reason=payload.get("block_reason"),
            ).replace(forced_target_name, forced_target_name, 1)
        if event_type == "zone_effect_resolved":
            zone_name = str(payload.get("zone_name") or payload.get("zone_id") or "区域效果")
            zone_target_name = self._entity_name_or_fallback(encounter, payload.get("target_entity_id"), target_name)
            damage_text = self._format_damage_resolution_summary(payload.get("damage_resolution"))
            condition_text = self._format_turn_effect_condition_summary(payload.get("condition_updates"))
            trigger_label = {
                "enter": "进入区域时",
                "start_of_turn_inside": "回合开始时",
                "end_of_turn_inside": "回合结束时",
            }.get(str(payload.get("trigger") or ""), "区域触发时")
            parts = [f"{zone_target_name}{trigger_label}触发了{zone_name}。"]
            if damage_text is not None:
                parts.append(damage_text)
            if condition_text is not None:
                parts.append(condition_text)
            return " ".join(parts)
        if event_type == "turn_effect_resolved":
            return self._format_turn_effect_summary(
                name=str(payload.get("name") or "持续效果"),
                trigger=str(payload.get("trigger") or ""),
                source_name=self._entity_name_or_fallback(encounter, payload.get("source_entity_id"), actor_name),
                target_name=self._entity_name_or_fallback(encounter, payload.get("target_entity_id"), target_name),
                save=payload.get("save"),
                trigger_damage_resolution=payload.get("trigger_damage_resolution"),
                success_damage_resolution=payload.get("success_damage_resolution"),
                failure_damage_resolution=payload.get("failure_damage_resolution"),
                condition_updates=payload.get("condition_updates"),
                effect_removed=bool(payload.get("effect_removed", False)),
            )
        if event_type == "turn_ended":
            return f"{actor_name}结束了自己的回合。"
        if event_type == "spell_retargeted":
            spell_name = payload.get("spell_name") or payload.get("spell_id") or "标记法术"
            previous_target_name = self._entity_name_or_fallback(encounter, payload.get("previous_target_id"), "未知目标")
            new_target_name = self._entity_name_or_fallback(encounter, payload.get("new_target_id"), "未知目标")
            return f"{actor_name}将{spell_name}从{previous_target_name}转移到了{new_target_name}。"
        return None

    def _build_weapons_view(self, entity: EncounterEntity) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for index, weapon in enumerate(entity.weapons):
            damage_parts = weapon.get("damage", [])
            damage_text = " + ".join(
                f"{part['formula']} {part['type'].capitalize()}" for part in damage_parts if "formula" in part and "type" in part
            )
            items.append(
                {
                    "slot": weapon.get("slot", f"weapon_{index + 1}"),
                    "weapon_id": weapon.get("weapon_id"),
                    "name": weapon.get("name"),
                    "damage": damage_text,
                    "properties": weapon.get("properties", []),
                    "bonus": self._format_weapon_bonus(weapon),
                    "note": weapon.get("note"),
                }
            )
        return items

    def _build_spells_view(self, entity: EncounterEntity) -> dict[str, list[dict[str, Any]]]:
        grouped_spells: dict[str, list[dict[str, Any]]] = {"cantrips": []}
        for spell in entity.spells:
            spell_level = spell.get("level", 0)
            if spell_level == 0:
                group_key = "cantrips"
            else:
                group_key = f"level_{spell_level}_spells"
                grouped_spells.setdefault(group_key, [])

            grouped_spells[group_key].append(
                {
                    "id": spell.get("spell_id"),
                    "name": spell.get("name"),
                    "description": spell.get("description"),
                    "damage": spell.get("damage", []),
                    "requires_attack_roll": spell.get("requires_attack_roll", False),
                    "at_higher_levels": spell.get("at_higher_levels"),
                }
            )
        return grouped_spells

    def _build_spell_slots_view(self, entity: EncounterEntity) -> dict[str, int]:
        spell_slots = entity.resources.get("spell_slots", {})
        return {
            level: slot_data["remaining"]
            for level, slot_data in spell_slots.items()
            if isinstance(slot_data, dict) and "remaining" in slot_data
        }

    def _build_weapon_ranges(self, encounter: Encounter, entity: EncounterEntity) -> dict[str, Any]:
        max_melee_range = self._max_melee_range(entity)
        max_ranged_range = self._max_ranged_range(entity)
        enemy_targets = [
            other_entity
            for other_entity in encounter.entities.values()
            if other_entity.entity_id != entity.entity_id and other_entity.side != entity.side
        ]

        return {
            "max_melee_range": f"{max_melee_range} ft" if max_melee_range else "0 ft",
            "max_ranged_range": f"{max_ranged_range} ft" if max_ranged_range else "0 ft",
            "targets_within_melee_range": self._filter_targets_by_range(entity, enemy_targets, max_melee_range),
            "targets_within_ranged_range": self._filter_targets_by_range(entity, enemy_targets, max_ranged_range),
        }

    def _build_actions(self, entity: EncounterEntity) -> dict[str, bool]:
        action_economy = entity.action_economy or {}
        return {
            "action_used": bool(action_economy.get("action_used")),
            "bonus_action_used": bool(action_economy.get("bonus_action_used")),
            "reaction_used": bool(action_economy.get("reaction_used")),
            "free_interaction_used": bool(action_economy.get("free_interaction_used")),
        }

    def _filter_targets_by_range(
        self,
        source_entity: EncounterEntity,
        targets: list[EncounterEntity],
        max_range_feet: int,
    ) -> list[dict[str, str]]:
        if max_range_feet <= 0:
            return []

        visible_targets: list[dict[str, str]] = []
        for target in targets:
            distance_feet = self._distance_feet(source_entity, target)
            if distance_feet <= max_range_feet:
                visible_targets.append(
                    {
                        "entity_id": target.entity_id,
                        "name": target.name,
                        "distance": f"{distance_feet} ft",
                    }
                )
        return visible_targets

    def _max_melee_range(self, entity: EncounterEntity) -> int:
        melee_ranges: list[int] = []
        for weapon in entity.weapons:
            weapon_range = weapon.get("range", {})
            normal_range = weapon_range.get("normal", 0)
            if normal_range and normal_range <= 10:
                melee_ranges.append(normal_range)
        return max(melee_ranges, default=0)

    def _max_ranged_range(self, entity: EncounterEntity) -> int:
        ranges: list[int] = []
        for weapon in entity.weapons:
            weapon_range = weapon.get("range", {})
            normal_range = weapon_range.get("normal", 0)
            long_range = weapon_range.get("long", 0)
            if normal_range and normal_range > 10:
                ranges.append(max(normal_range, long_range))
        for spell in entity.spells:
            range_feet = spell.get("range_feet", 0)
            if isinstance(range_feet, int) and range_feet > 0:
                ranges.append(range_feet)
        return max(ranges, default=0)

    def _distance_feet(self, source: EncounterEntity, target: EncounterEntity) -> int:
        dx = abs(source.position["x"] - target.position["x"])
        dy = abs(source.position["y"] - target.position["y"])
        return max(dx, dy) * 5

    def _format_distance_from_current(
        self,
        entity: EncounterEntity,
        current_entity: EncounterEntity | None,
    ) -> str | None:
        if current_entity is None or entity.entity_id == current_entity.entity_id:
            return None
        return f"{self._distance_feet(current_entity, entity)} ft"

    def _format_hp(self, entity: EncounterEntity) -> str:
        return f"{entity.hp['current']} / {entity.hp['max']} HP"

    def _format_hp_status(self, entity: EncounterEntity) -> str:
        current_hp = entity.hp["current"]
        max_hp = entity.hp["max"]
        percent = 0 if max_hp == 0 else round((current_hp / max_hp) * 100)
        if current_hp <= 0:
            status = "DOWN"
        elif percent >= 75:
            status = "HEALTHY"
        elif percent >= 35:
            status = "WOUNDED"
        else:
            status = "BLOODIED"
        return f"{current_hp}/{max_hp} HP ({percent}%) [{status}]"

    def _format_position(self, entity: EncounterEntity) -> str:
        return f"({entity.position['x']}, {entity.position['y']})"

    def _format_conditions(self, encounter: Encounter, entity: EncounterEntity) -> str | list[str]:
        effect_labels = self._build_entity_ongoing_effects(encounter, entity)
        if not entity.conditions and not effect_labels:
            return "No active conditions."
        if not effect_labels:
            return ", ".join(entity.conditions)
        return self._dedupe_preserve_order([*entity.conditions, *effect_labels])

    def _build_resources_view(self, entity: EncounterEntity) -> dict[str, Any]:
        spell_slots = self._build_spell_slots_resource_view(entity)
        feature_uses = self._build_feature_uses_resource_view(entity)
        class_features = self._build_class_feature_resource_view(entity)
        return {
            "summary": self._format_resources_summary(entity),
            "spell_slots": spell_slots,
            "feature_uses": feature_uses,
            "class_features": class_features,
        }

    def _format_resources_summary(self, entity: EncounterEntity) -> str:
        parts: list[str] = []

        spell_slots = entity.resources.get("spell_slots", {})
        if spell_slots:
            slot_parts = []
            for level, slot_data in sorted(spell_slots.items(), key=lambda item: item[0]):
                if isinstance(slot_data, dict) and "remaining" in slot_data and "max" in slot_data:
                    slot_parts.append(f"{level}st {slot_data['remaining']}/{slot_data['max']}")
            if slot_parts:
                parts.append("Spell Slots: " + ", ".join(slot_parts))

        feature_uses = entity.resources.get("feature_uses", {})
        if feature_uses:
            feature_parts = []
            for name, use_data in feature_uses.items():
                if isinstance(use_data, dict) and "remaining" in use_data and "max" in use_data:
                    feature_parts.append(f"{name}: {use_data['remaining']}/{use_data['max']}")
            if feature_parts:
                parts.append(", ".join(feature_parts))

        if not parts:
            return "No tracked resources."
        return " | ".join(parts)

    def _build_spell_slots_resource_view(self, entity: EncounterEntity) -> dict[str, dict[str, int]]:
        spell_slots = entity.resources.get("spell_slots", {})
        if not isinstance(spell_slots, dict):
            return {}

        projected: dict[str, dict[str, int]] = {}
        for level, slot_data in spell_slots.items():
            if not isinstance(slot_data, dict):
                continue
            remaining = slot_data.get("remaining")
            maximum = slot_data.get("max")
            if not isinstance(remaining, int) or not isinstance(maximum, int):
                continue
            projected[str(level)] = {
                "remaining": remaining,
                "max": maximum,
            }
        return projected

    def _build_feature_uses_resource_view(self, entity: EncounterEntity) -> dict[str, dict[str, int]]:
        feature_uses = entity.resources.get("feature_uses", {})
        if not isinstance(feature_uses, dict):
            return {}

        projected: dict[str, dict[str, int]] = {}
        for name, use_data in feature_uses.items():
            if not isinstance(use_data, dict):
                continue
            remaining = use_data.get("remaining")
            maximum = use_data.get("max")
            if not isinstance(remaining, int) or not isinstance(maximum, int):
                continue
            projected[str(name)] = {
                "remaining": remaining,
                "max": maximum,
            }
        return projected

    def _build_class_feature_resource_view(self, entity: EncounterEntity) -> dict[str, Any]:
        class_features = entity.class_features if isinstance(entity.class_features, dict) else {}
        fighter = class_features.get("fighter")
        if not isinstance(fighter, dict):
            return {}

        return {
            "fighter": {
                "fighter_level": fighter.get("fighter_level", fighter.get("level")),
                "weapon_proficiencies": fighter.get("weapon_proficiencies", ["simple", "martial"]),
                "second_wind": fighter.get("second_wind"),
                "action_surge": fighter.get("action_surge"),
                "indomitable": fighter.get("indomitable"),
                "extra_attack_count": fighter.get("extra_attack_count"),
                "tactical_master_enabled": bool(fighter.get("tactical_master_enabled")),
                "studied_attacks": fighter.get("studied_attacks", []),
                "temporary_bonuses": fighter.get("temporary_bonuses", {}),
                "turn_counters": fighter.get("turn_counters", {}),
            }
        }

    def _format_death_saves(self, entity: EncounterEntity) -> str:
        combat_flags = entity.combat_flags or {}
        death_saves = combat_flags.get("death_saves")
        if not isinstance(death_saves, dict):
            return "0 成功 / 0 失败"
        successes = death_saves.get("successes", 0)
        failures = death_saves.get("failures", 0)
        if not isinstance(successes, int):
            successes = 0
        if not isinstance(failures, int):
            failures = 0
        return f"{successes} 成功 / {failures} 失败"

    def _format_weapon_bonus(self, weapon: dict[str, Any]) -> str | None:
        attack_bonus = weapon.get("attack_bonus")
        damage_bonus = weapon.get("damage_bonus")
        if attack_bonus is None and damage_bonus is None:
            return None
        parts = []
        if attack_bonus is not None:
            parts.append(f"+{attack_bonus} attack")
        if damage_bonus is not None:
            parts.append(f"+{damage_bonus} damage")
        return ", ".join(parts)

    def _extract_level(self, entity: EncounterEntity) -> int | None:
        source_ref = entity.source_ref
        level = source_ref.get("level")
        return level if isinstance(level, int) else None

    def _extract_description(self, entity: EncounterEntity) -> str | None:
        description = entity.source_ref.get("description")
        return description if isinstance(description, str) else None

    def _calculate_spell_save_dc(self, entity: EncounterEntity) -> int | None:
        spellcasting_ability = entity.source_ref.get("spellcasting_ability")
        if spellcasting_ability is None:
            return None

        ability_mod = entity.ability_mods.get(spellcasting_ability)
        if ability_mod is None:
            return None
        return 8 + entity.proficiency_bonus + ability_mod

    def _is_active_spell_instance(self, instance: dict[str, Any]) -> bool:
        lifecycle = instance.get("lifecycle", {})
        return lifecycle.get("status") == "active"

    def _format_spell_source_label(self, instance: dict[str, Any]) -> str:
        caster_name = instance.get("caster_name") or "未知施法者"
        spell_name = instance.get("spell_name") or instance.get("spell_id") or "未知法术"
        return f"来自{caster_name}的{spell_name}"

    def _dedupe_preserve_order(self, values: list[str]) -> list[str]:
        ordered_values: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            ordered_values.append(value)
        return ordered_values

    def _entity_name_or_fallback(self, encounter: Encounter, entity_id: Any, fallback: str) -> str:
        if isinstance(entity_id, str):
            entity = encounter.entities.get(entity_id)
            if entity is not None:
                return entity.name
        return fallback

    def _extract_previous_target_id(self, instance: dict[str, Any]) -> str | None:
        targets = instance.get("targets")
        if not isinstance(targets, list) or not targets:
            return None
        first_target = targets[0]
        if not isinstance(first_target, dict):
            return None
        entity_id = first_target.get("entity_id")
        return entity_id if isinstance(entity_id, str) else None

    def _normalize_position(self, value: Any) -> dict[str, int] | None:
        if not isinstance(value, dict):
            return None
        x = value.get("x")
        y = value.get("y")
        if not isinstance(x, int) or not isinstance(y, int):
            return None
        return {"x": x, "y": y}

    def _normalize_path(self, value: Any) -> list[dict[str, int]]:
        if not isinstance(value, list):
            return []
        normalized: list[dict[str, int]] = []
        for item in value:
            position = self._normalize_position(item)
            if position is not None:
                normalized.append(position)
        return normalized

    def _format_forced_movement_summary(
        self,
        *,
        reason: str,
        target_name: str,
        moved_feet: int,
        final_position: dict[str, int] | None,
        blocked: bool,
        block_reason: Any,
    ) -> str:
        if reason == "weapon_mastery_push":
            if moved_feet <= 0:
                return f"{target_name}尝试被 Push 推离，但被{self._format_block_reason(block_reason)}阻挡，位置未改变。"
            destination = self._format_compact_position(final_position)
            if blocked:
                return f"{target_name}被 Push 推离 {moved_feet} 尺，移动到 {destination}，随后被{self._format_block_reason(block_reason)}阻挡。"
            return f"{target_name}被 Push 推离 {moved_feet} 尺，移动到 {destination}。"
        destination = self._format_compact_position(final_position)
        return f"{target_name}发生了强制位移，最终到达 {destination}。"

    def _format_compact_position(self, position: dict[str, int] | None) -> str:
        if position is None:
            return "(?,?)"
        return f"({position['x']},{position['y']})"

    def _format_block_reason(self, block_reason: Any) -> str:
        mapping = {
            "wall": "墙壁",
            "out_of_bounds": "边界",
            "occupied_tile": "占位",
        }
        return mapping.get(str(block_reason or ""), "障碍")

    def _format_turn_effect_summary(
        self,
        *,
        name: str,
        trigger: str,
        source_name: str,
        target_name: str,
        save: Any,
        trigger_damage_resolution: Any,
        success_damage_resolution: Any,
        failure_damage_resolution: Any,
        condition_updates: Any,
        effect_removed: bool,
    ) -> str:
        trigger_label = {
            "start_of_turn": "回合开始",
            "end_of_turn": "回合结束",
        }.get(trigger, trigger or "触发时")

        parts = [f"{trigger_label}，{source_name}的{name}对{target_name}结算。"]

        save_text = self._format_turn_effect_save_summary(save)
        if save_text is not None:
            parts.append(save_text)

        damage_texts = self._collect_turn_effect_damage_summaries(
            trigger_damage_resolution=trigger_damage_resolution,
            success_damage_resolution=success_damage_resolution,
            failure_damage_resolution=failure_damage_resolution,
        )
        parts.extend(damage_texts)

        condition_text = self._format_turn_effect_condition_summary(condition_updates)
        if condition_text is not None:
            parts.append(condition_text)

        if effect_removed:
            parts.append("该持续效果已移除。")

        return " ".join(parts)

    def _format_turn_effect_save_summary(self, save: Any) -> str | None:
        if not isinstance(save, dict):
            return None
        ability = str(save.get("ability") or "").upper()
        dc = save.get("dc")
        total = save.get("total")
        success = save.get("success")
        if success is True:
            result = "成功"
        elif success is False:
            result = "失败"
        else:
            result = "未知"
        details: list[str] = []
        if ability:
            details.append(f"{ability} 豁免")
        if isinstance(dc, int):
            details.append(f"DC {dc}")
        if isinstance(total, int):
            details.append(f"结果 {total}")
        if not details:
            return f"豁免{result}。"
        return f"{'，'.join(details)}，{result}。"

    def _collect_turn_effect_damage_summaries(
        self,
        *,
        trigger_damage_resolution: Any,
        success_damage_resolution: Any,
        failure_damage_resolution: Any,
    ) -> list[str]:
        items: list[str] = []
        trigger_text = self._format_damage_resolution_summary(trigger_damage_resolution)
        if trigger_text is not None:
            items.append(f"触发伤害：{trigger_text}")
        success_text = self._format_damage_resolution_summary(success_damage_resolution)
        if success_text is not None:
            items.append(f"豁免成功后：{success_text}")
        failure_text = self._format_damage_resolution_summary(failure_damage_resolution)
        if failure_text is not None:
            items.append(f"豁免失败后：{failure_text}")
        return items

    def _format_damage_resolution_summary(self, resolution: Any) -> str | None:
        if not isinstance(resolution, dict):
            return None
        total_damage = resolution.get("total_damage")
        applied_parts = resolution.get("applied_parts")
        if not isinstance(total_damage, int):
            return None
        if not isinstance(applied_parts, list) or not applied_parts:
            return f"造成 {total_damage} 点伤害。"
        parts: list[str] = []
        for part in applied_parts:
            if not isinstance(part, dict):
                continue
            damage_type = str(part.get("type") or "未知")
            final_damage = part.get("final_damage")
            if isinstance(final_damage, int):
                parts.append(f"{final_damage} 点{damage_type}")
        if not parts:
            return f"造成 {total_damage} 点伤害。"
        return f"造成 {total_damage} 点伤害（{'，'.join(parts)}）。"

    def _format_turn_effect_condition_summary(self, condition_updates: Any) -> str | None:
        if not isinstance(condition_updates, list) or not condition_updates:
            return None
        applied: list[str] = []
        removed: list[str] = []
        for item in condition_updates:
            if not isinstance(item, dict):
                continue
            if not bool(item.get("changed")):
                continue
            condition = item.get("condition")
            if not isinstance(condition, str):
                continue
            operation = item.get("operation")
            if operation == "apply":
                applied.append(condition)
            elif operation == "remove":
                removed.append(condition)

        parts: list[str] = []
        if applied:
            parts.append(f"附加状态：{'、'.join(applied)}。")
        if removed:
            parts.append(f"移除状态：{'、'.join(removed)}。")
        if not parts:
            return None
        return " ".join(parts)

    def _list_events_for_encounter(self, encounter_id: str) -> list[Any]:
        if self.event_repository is not None:
            return self.event_repository.list_by_encounter(encounter_id)
        event_repository = EventRepository()
        try:
            return event_repository.list_by_encounter(encounter_id)
        finally:
            event_repository.close()
