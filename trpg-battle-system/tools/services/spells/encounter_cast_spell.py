from __future__ import annotations

from typing import TYPE_CHECKING, Any
from random import randint
from uuid import uuid4

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.armor_definition_repository import ArmorDefinitionRepository
from tools.repositories.encounter_repository import EncounterRepository
from tools.repositories.spell_definition_repository import SpellDefinitionRepository
from tools.repositories.zone_definition_repository import ZoneDefinitionRepository
from tools.services.combat.defense.armor_profile_resolver import ArmorProfileResolver
from tools.services.class_features.shared import (
    consume_exact_spell_slot,
    ensure_paladin_runtime,
    ensure_ranger_runtime,
    ensure_sorcerer_runtime,
    restore_consumed_spell_slot,
)
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.events.append_event import AppendEvent
from tools.services.shared.rule_validation_error import RuleValidationError
from tools.services.spells.area_geometry import build_spell_zone_instance
from tools.services.spells.build_spell_instance import build_spell_instance
from tools.services.spells.build_turn_effect_instance import build_turn_effect_instance
from tools.services.spells.metamagic_support import (
    normalize_transmuted_damage_type,
    spell_supports_extended_spell,
    spell_supports_transmuted_spell,
    spell_supports_twinned_spell,
)
from tools.services.spells.resolve_spellcasting_access import ResolveSpellcastingAccess
from tools.services.spells.summons.create_summoned_entity import (
    create_summoned_entity,
    create_summoned_entity_by_initiative,
)
from tools.services.spells.summons.find_familiar_builder import build_find_familiar_entity
from tools.services.spells.summons.find_steed_builder import build_find_steed_entity
from tools.services.spells.summons.placement import resolve_summon_target_point
from tools.services.combat.shared.turn_actor_guard import (
    get_entity_or_raise,
    resolve_current_turn_actor_or_raise,
)

if TYPE_CHECKING:
    from tools.repositories.reaction_definition_repository import ReactionDefinitionRepository
    from tools.services.combat.rules.reactions.open_reaction_window import OpenReactionWindow


class EncounterCastSpell:
    """声明一次施法，并在需要时扣除法术位。"""

    _FIND_FAMILIAR_CREATURE_TYPES = {
        "slaad_tadpole": "aberration",
        "pseudodragon": "dragon",
        "skeleton": "undead",
        "zombie": "undead",
        "sprite": "fey",
        "quasit": "fiend",
        "imp": "fiend",
        "sphinx_of_wonder": "celestial",
    }
    _FIND_FAMILIAR_GENERIC_FORMS = {"owl"}

    def __init__(
        self,
        encounter_repository: EncounterRepository,
        append_event: AppendEvent,
        spell_definition_repository: SpellDefinitionRepository | None = None,
        armor_definition_repository: ArmorDefinitionRepository | None = None,
        zone_definition_repository: ZoneDefinitionRepository | None = None,
        open_reaction_window: "OpenReactionWindow" | None = None,
        reaction_definition_repository: "ReactionDefinitionRepository" | None = None,
    ):
        self.encounter_repository = encounter_repository
        self.append_event = append_event
        self.spell_definition_repository = spell_definition_repository or SpellDefinitionRepository()
        self.resolve_spellcasting_access = ResolveSpellcastingAccess(self.spell_definition_repository)
        self.armor_profile_resolver = ArmorProfileResolver(armor_definition_repository or ArmorDefinitionRepository())
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
        spell_options: dict[str, Any] | None = None,
        metamagic_options: dict[str, Any] | None = None,
        reason: str | None = None,
        include_encounter_state: bool = False,
        apply_no_roll_immediate_effects: bool = True,
        allow_out_of_turn_actor: bool = False,
        skip_reaction_window: bool = False,
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
        armor_profile = self.armor_profile_resolver.resolve(caster)
        if armor_profile["wearing_untrained_armor"]:
            raise ValueError("armor_training_required_for_spellcasting")
        known_spell = self._find_known_spell(caster, spell_id)
        if known_spell is not None:
            spellcasting_access = self.resolve_spellcasting_access.execute(actor=caster, spell_id=spell_id)
            if spellcasting_access["ok"] is False:
                raise ValueError(spellcasting_access["error_code"])
        spell_definition = self._get_spell_definition_or_raise(encounter, caster, spell_id)
        normalized_target_ids = self._normalize_self_targets(
            caster=caster,
            spell_definition=spell_definition,
            target_ids=target_ids or [],
        )
        resolved_target_ids = self._resolve_target_ids(encounter, normalized_target_ids)
        action_cost = self._resolve_action_cost(spell_definition)

        spell_level = self._resolve_spell_level(spell_definition)
        resolved_cast_level = cast_level if cast_level is not None else spell_level
        if spell_level > 0 and resolved_cast_level < spell_level:
            raise ValueError("cast_level cannot be lower than the spell's base level")
        metamagic = self._resolve_metamagic(
            caster=caster,
            spell_id=spell_id,
            spell_definition=spell_definition,
            action_cost=action_cost,
            target_ids=resolved_target_ids,
            metamagic_options=metamagic_options,
        )
        if bool(metamagic.get("quickened_spell")):
            action_cost = "bonus_action"
        noticeability = self._build_noticeability(metamagic=metamagic)
        self._validate_action_cost_available_or_raise(caster=caster, action_cost=action_cost)

        free_find_steed_cast_used = self._is_find_steed_spell(spell_definition) and self._has_faithful_steed_free_cast(caster)
        free_hunters_mark_cast_used = self._is_hunters_mark_spell(spell_definition) and self._has_favored_enemy_free_cast(caster)
        will_consume_spell_slot = self._will_consume_spell_slot_for_cast(
            spell_level=spell_level,
            free_find_steed_cast_used=free_find_steed_cast_used,
            free_hunters_mark_cast_used=free_hunters_mark_cast_used,
        )
        self._validate_spell_slot_cast_limit_or_raise(
            caster=caster,
            will_consume_spell_slot=will_consume_spell_slot,
            action_cost=action_cost,
        )

        if free_find_steed_cast_used:
            slot_consumed = None
            paladin = ensure_paladin_runtime(caster)
            paladin["faithful_steed"]["free_cast_available"] = False
        elif free_hunters_mark_cast_used:
            slot_consumed = None
            ranger = ensure_ranger_runtime(caster)
            favored_enemy = ranger.get("favored_enemy", {})
            favored_enemy["free_cast_uses_remaining"] = max(0, int(favored_enemy.get("free_cast_uses_remaining", 0)) - 1)
        else:
            slot_consumed = self._consume_spell_slot_if_needed(caster, spell_level, resolved_cast_level)
        sorcery_points_consumed = self._consume_sorcery_points_if_needed(
            caster=caster,
            metamagic=metamagic,
        )
        resolved_spell_id = spell_definition.get("spell_id") or spell_definition.get("id") or spell_id
        resolved_spell_name = spell_definition.get("name") or spell_id
        normalized_spell_options = dict(spell_options) if isinstance(spell_options, dict) else {}
        if not skip_reaction_window:
            spell_action_id = f"spell_{uuid4().hex[:12]}"
            trigger_event = {
                "event_id": f"evt_spell_declared_{uuid4().hex[:12]}",
                "trigger_type": "spell_declared",
                "host_action_type": "spell_cast",
                "host_action_id": spell_action_id,
                "host_action_snapshot": {
                    "spell_action_id": spell_action_id,
                    "actor_id": caster.entity_id,
                    "spell_id": resolved_spell_id,
                    "spell_level": spell_level,
                    "cast_level": resolved_cast_level,
                    "target_ids": list(resolved_target_ids),
                    "target_point": target_point,
                    "spell_options": normalized_spell_options,
                    "metamagic": metamagic,
                    "noticeability": noticeability,
                    "action_cost": action_cost,
                    "allow_out_of_turn_actor": allow_out_of_turn_actor,
                    "phase": "before_spell_resolves",
                },
                "caster_entity_id": caster.entity_id,
                "target_entity_id": caster.entity_id,
                "payload": {
                    "metamagic": metamagic,
                    "noticeability": noticeability,
                },
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
        summon_entity: EncounterEntity | None = None
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
                metamagic=metamagic,
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
                    metamagic=metamagic,
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
        if self._is_find_steed_spell(spell_definition):
            self._replace_previous_find_steed_if_needed(encounter=encounter, caster=caster)
            normalized_target_point = resolve_summon_target_point(
                encounter=encounter,
                caster=caster,
                summon_size="large",
                range_feet=30,
                target_point=target_point,
                default_mode="adjacent_open_space",
                out_of_range_error_code="find_steed_target_point_out_of_range",
                missing_target_point_error_code="find_steed_requires_target_point",
            )
            target_point = normalized_target_point
            spell_instance = build_spell_instance(
                spell_definition=spell_definition,
                caster=caster,
                cast_level=resolved_cast_level,
                targets=[],
                started_round=encounter.round,
                metamagic=metamagic,
            )
            encounter.spell_instances.append(spell_instance)
            summon_entity = build_find_steed_entity(
                caster=caster,
                cast_level=resolved_cast_level,
                summon_position={"x": normalized_target_point["x"], "y": normalized_target_point["y"]},
                steed_type="celestial",
                appearance="warhorse",
                source_spell_instance_id=spell_instance["instance_id"],
            )
            create_summoned_entity(
                encounter=encounter,
                summon=summon_entity,
                insert_after_entity_id=caster.entity_id,
            )
            spell_instance["special_runtime"]["summon_entity_ids"] = [summon_entity.entity_id]
        if self._is_find_familiar_spell(spell_definition):
            familiar_form = self._resolve_find_familiar_form_or_raise(normalized_spell_options)
            self._replace_previous_find_familiar_if_needed(encounter=encounter, caster=caster)
            normalized_target_point = resolve_summon_target_point(
                encounter=encounter,
                caster=caster,
                summon_size="tiny",
                range_feet=10,
                target_point=target_point,
                default_mode="adjacent_open_space",
                out_of_range_error_code="find_familiar_target_point_out_of_range",
                missing_target_point_error_code="find_familiar_requires_target_point",
            )
            target_point = normalized_target_point
            spell_instance = build_spell_instance(
                spell_definition=spell_definition,
                caster=caster,
                cast_level=resolved_cast_level,
                targets=[],
                started_round=encounter.round,
                metamagic=metamagic,
            )
            encounter.spell_instances.append(spell_instance)
            summon_entity = build_find_familiar_entity(
                caster=caster,
                summon_position={"x": normalized_target_point["x"], "y": normalized_target_point["y"]},
                familiar_form=familiar_form,
                creature_type=self._resolve_find_familiar_creature_type(
                    familiar_form=familiar_form,
                    spell_options=normalized_spell_options,
                ),
                source_spell_instance_id=spell_instance["instance_id"],
            )
            summon_entity.initiative = randint(1, 20) + int(summon_entity.ability_mods.get("dex", 0) or 0)
            create_summoned_entity_by_initiative(
                encounter=encounter,
                summon=summon_entity,
            )
            spell_instance["special_runtime"]["summon_entity_ids"] = [summon_entity.entity_id]
        payload = {
            "spell_id": resolved_spell_id,
            "spell_name": resolved_spell_name,
            "spell_level": spell_level,
            "cast_level": resolved_cast_level,
            "target_ids": resolved_target_ids,
            "target_point": target_point,
            "spell_options": normalized_spell_options,
            "requires_attack_roll": spell_definition.get("requires_attack_roll", False),
            "save_ability": spell_definition.get("save_ability"),
            "damage": spell_definition.get("damage", []),
            "spell_definition": spell_definition,
            "slot_consumed": slot_consumed,
            "action_cost": action_cost,
            "metamagic": metamagic,
            "noticeability": noticeability,
            "turn_effect_updates": turn_effect_updates,
            "spell_instance": spell_instance,
            "summon_entity_id": summon_entity.entity_id if summon_entity is not None else None,
            "zone_updates": zone_updates,
            "reason": reason or f"Cast {resolved_spell_name}",
        }
        previous_action_economy = dict(caster.action_economy) if isinstance(caster.action_economy, dict) else {}
        self._consume_action_cost_if_needed(caster, action_cost)
        self._record_spell_slot_cast_if_needed(
            caster=caster,
            slot_consumed=slot_consumed,
        )
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
            self._restore_sorcery_points_if_needed(caster=caster, sorcery_points_consumed=sorcery_points_consumed)
            if free_find_steed_cast_used:
                paladin = ensure_paladin_runtime(caster)
                paladin["faithful_steed"]["free_cast_available"] = True
            if free_hunters_mark_cast_used:
                ranger = ensure_ranger_runtime(caster)
                favored_enemy = ranger.get("favored_enemy", {})
                favored_enemy["free_cast_uses_remaining"] = int(favored_enemy.get("free_cast_uses_remaining", 0)) + 1
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
            "metamagic": metamagic,
            "noticeability": noticeability,
            "turn_effect_updates": turn_effect_updates,
            "spell_instance": spell_instance,
            "zone_updates": zone_updates,
            "event_id": event.event_id,
            "event_type": event.event_type,
        }
        if include_encounter_state:
            result["encounter_state"] = GetEncounterState(self.encounter_repository).execute(encounter_id)
        return result

    def _is_find_steed_spell(self, spell_definition: dict[str, Any]) -> bool:
        spell_id = str(spell_definition.get("spell_id") or spell_definition.get("id") or "").strip().lower()
        return spell_id == "find_steed"

    def _is_find_familiar_spell(self, spell_definition: dict[str, Any]) -> bool:
        spell_id = str(spell_definition.get("spell_id") or spell_definition.get("id") or "").strip().lower()
        return spell_id == "find_familiar"

    def _has_faithful_steed_free_cast(self, caster: EncounterEntity) -> bool:
        paladin = ensure_paladin_runtime(caster)
        faithful_steed = paladin.get("faithful_steed")
        if not isinstance(faithful_steed, dict):
            return False
        return bool(faithful_steed.get("enabled")) and bool(faithful_steed.get("free_cast_available"))

    def _is_hunters_mark_spell(self, spell_definition: dict[str, Any]) -> bool:
        spell_id = str(spell_definition.get("spell_id") or spell_definition.get("id") or "").strip().lower()
        return spell_id == "hunters_mark"

    def _has_favored_enemy_free_cast(self, caster: EncounterEntity) -> bool:
        ranger = ensure_ranger_runtime(caster)
        favored_enemy = ranger.get("favored_enemy")
        if not isinstance(favored_enemy, dict):
            return False
        return bool(favored_enemy.get("enabled")) and int(favored_enemy.get("free_cast_uses_remaining", 0) or 0) > 0

    def _replace_previous_find_steed_if_needed(
        self,
        *,
        encounter: Encounter,
        caster: EncounterEntity,
    ) -> None:
        for instance in encounter.spell_instances:
            if instance.get("spell_id") != "find_steed":
                continue
            if instance.get("caster_entity_id") != caster.entity_id:
                continue
            special_runtime = instance.get("special_runtime")
            if not isinstance(special_runtime, dict):
                continue
            summon_entity_ids = special_runtime.get("summon_entity_ids")
            if not isinstance(summon_entity_ids, list) or not summon_entity_ids:
                continue
            for summon_id in list(summon_entity_ids):
                encounter.entities.pop(summon_id, None)
                encounter.turn_order = [entity_id for entity_id in encounter.turn_order if entity_id != summon_id]
                if encounter.current_entity_id == summon_id:
                    encounter.current_entity_id = caster.entity_id
            special_runtime["summon_entity_ids"] = []

    def _replace_previous_find_familiar_if_needed(
        self,
        *,
        encounter: Encounter,
        caster: EncounterEntity,
    ) -> None:
        for instance in encounter.spell_instances:
            if instance.get("spell_id") != "find_familiar":
                continue
            if instance.get("caster_entity_id") != caster.entity_id:
                continue
            special_runtime = instance.get("special_runtime")
            if not isinstance(special_runtime, dict):
                continue
            summon_entity_ids = special_runtime.get("summon_entity_ids")
            if not isinstance(summon_entity_ids, list) or not summon_entity_ids:
                continue
            for summon_id in list(summon_entity_ids):
                encounter.entities.pop(summon_id, None)
                encounter.turn_order = [entity_id for entity_id in encounter.turn_order if entity_id != summon_id]
                if encounter.current_entity_id == summon_id:
                    encounter.current_entity_id = caster.entity_id
            special_runtime["summon_entity_ids"] = []

    def _resolve_find_familiar_form_or_raise(self, spell_options: dict[str, Any]) -> str:
        familiar_form = str(spell_options.get("familiar_form") or "").strip().lower()
        if not familiar_form:
            raise ValueError("find_familiar_requires_familiar_form")
        if familiar_form not in self._FIND_FAMILIAR_CREATURE_TYPES and familiar_form not in self._FIND_FAMILIAR_GENERIC_FORMS:
            raise ValueError("invalid_find_familiar_form")
        return familiar_form

    def _resolve_find_familiar_creature_type(
        self,
        *,
        familiar_form: str,
        spell_options: dict[str, Any],
    ) -> str:
        if familiar_form in self._FIND_FAMILIAR_CREATURE_TYPES:
            return self._FIND_FAMILIAR_CREATURE_TYPES[familiar_form]
        creature_type = str(spell_options.get("creature_type") or "").strip().lower()
        return creature_type or "fey"

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

    def _normalize_self_targets(
        self,
        *,
        caster: EncounterEntity,
        spell_definition: dict[str, Any],
        target_ids: list[str],
    ) -> list[str]:
        if target_ids:
            return list(target_ids)
        targeting = spell_definition.get("targeting")
        if not isinstance(targeting, dict):
            return []
        if str(targeting.get("type") or "").strip().lower() != "self":
            return []
        return [caster.entity_id]

    def _resolve_spell_level(self, spell: dict[str, Any]) -> int:
        spell_level = spell.get("level", 0)
        if not isinstance(spell_level, int) or spell_level < 0:
            raise ValueError("spell.level must be an integer >= 0")
        return spell_level

    def _find_known_spell(self, caster: EncounterEntity, spell_id: str) -> dict[str, Any] | None:
        for spell in caster.spells:
            if spell.get("spell_id") == spell_id:
                return spell
        return None

    def _resolve_spellcasting_class(self, known_spell: dict[str, Any] | None) -> str | None:
        if not isinstance(known_spell, dict):
            return None
        casting_class = known_spell.get("casting_class")
        if isinstance(casting_class, str) and casting_class.strip():
            return casting_class.strip().lower()
        classes = known_spell.get("classes")
        if isinstance(classes, list) and len(classes) == 1:
            current_class = classes[0]
            if isinstance(current_class, str) and current_class.strip():
                return current_class.strip().lower()
        return None

    def _resolve_metamagic(
        self,
        *,
        caster: EncounterEntity,
        spell_id: str,
        spell_definition: dict[str, Any],
        action_cost: str | None,
        target_ids: list[str],
        metamagic_options: dict[str, Any] | None,
    ) -> dict[str, Any]:
        default_result = self._build_default_metamagic()
        if not isinstance(metamagic_options, dict):
            return default_result
        selected = metamagic_options.get("selected")
        if not isinstance(selected, list):
            return default_result

        normalized_selected = [str(item).strip().lower() for item in selected if str(item).strip()]
        if not normalized_selected:
            return default_result
        if len(normalized_selected) > 1:
            raise ValueError("multiple_metamagic_not_supported")

        known_spell = self._find_known_spell(caster, spell_id)
        if self._resolve_spellcasting_class(known_spell) != "sorcerer":
            raise ValueError("metamagic_requires_sorcerer_spell")

        sorcerer = ensure_sorcerer_runtime(caster)
        if int(sorcerer.get("level", 0) or 0) < 2:
            raise ValueError("metamagic_requires_sorcerer_level_2")
        sorcery_points = sorcerer.get("sorcery_points")
        current_points = int(sorcery_points.get("current", 0) or 0) if isinstance(sorcery_points, dict) else 0
        selected_metamagic = normalized_selected[0]
        supported_costs = {
            "subtle_spell": 1,
            "quickened_spell": 2,
            "distant_spell": 1,
            "heightened_spell": 2,
            "careful_spell": 1,
            "empowered_spell": 1,
            "extended_spell": 1,
            "seeking_spell": 1,
            "transmuted_spell": 1,
            "twinned_spell": 1,
        }
        cost = supported_costs.get(selected_metamagic)
        if cost is None:
            raise ValueError("unsupported_metamagic")
        if current_points < cost:
            raise ValueError("insufficient_sorcery_points")

        metamagic = self._build_default_metamagic()
        metamagic["selected"] = [selected_metamagic]
        metamagic[selected_metamagic] = True
        metamagic["sorcery_point_cost"] = cost

        if selected_metamagic == "quickened_spell":
            if action_cost != "action":
                raise ValueError("quickened_spell_requires_action_cast_time")
            return metamagic

        if selected_metamagic == "distant_spell":
            if not self._spell_can_use_distant_spell(spell_definition=spell_definition):
                raise ValueError("distant_spell_requires_range_or_touch_spell")
            metamagic["effective_range_override_feet"] = self._resolve_distant_spell_range_override_feet(
                spell_definition=spell_definition
            )
            return metamagic

        if selected_metamagic == "heightened_spell":
            heightened_target_id = metamagic_options.get("heightened_target_id")
            if not isinstance(heightened_target_id, str) or not heightened_target_id.strip():
                raise ValueError("heightened_spell_requires_target")
            if heightened_target_id not in target_ids:
                raise ValueError("heightened_spell_target_must_be_one_of_the_spell_targets")
            if not self._spell_requires_saving_throw(spell_definition=spell_definition):
                raise ValueError("heightened_spell_requires_save_spell")
            metamagic["heightened_target_id"] = heightened_target_id
            return metamagic

        if selected_metamagic == "careful_spell":
            careful_target_ids = metamagic_options.get("careful_target_ids")
            if not isinstance(careful_target_ids, list) or not careful_target_ids:
                raise ValueError("careful_spell_requires_targets")
            normalized_careful_target_ids = [str(item).strip() for item in careful_target_ids if str(item).strip()]
            max_protected_targets = max(1, int(caster.ability_mods.get("cha", 0) or 0))
            if len(normalized_careful_target_ids) > max_protected_targets:
                raise ValueError("careful_spell_too_many_targets")
            for entity_id in normalized_careful_target_ids:
                if entity_id not in target_ids:
                    raise ValueError("careful_spell_targets_must_be_spell_targets")
            if not self._spell_requires_saving_throw(spell_definition=spell_definition):
                raise ValueError("careful_spell_requires_save_spell")
            metamagic["careful_target_ids"] = normalized_careful_target_ids
            return metamagic

        if selected_metamagic == "empowered_spell":
            if not self._spell_has_damage_resolution(spell_definition=spell_definition):
                raise ValueError("empowered_spell_requires_damage_spell")
            return metamagic

        if selected_metamagic == "extended_spell":
            if not spell_supports_extended_spell(spell_definition):
                raise ValueError("extended_spell_requires_duration_spell")
            return metamagic

        if selected_metamagic == "seeking_spell":
            if not bool(spell_definition.get("requires_attack_roll")):
                raise ValueError("seeking_spell_requires_attack_roll_spell")
            return metamagic

        if selected_metamagic == "transmuted_spell":
            if not spell_supports_transmuted_spell(spell_definition):
                raise ValueError("transmuted_spell_requires_eligible_damage_type")
            transmuted_damage_type = normalize_transmuted_damage_type(metamagic_options.get("transmuted_damage_type"))
            if transmuted_damage_type is None:
                raise ValueError("invalid_transmuted_damage_type")
            metamagic["transmuted_damage_type"] = transmuted_damage_type
            return metamagic

        if selected_metamagic == "twinned_spell":
            if not spell_supports_twinned_spell(spell_definition):
                raise ValueError("twinned_spell_requires_scaling_target_spell")
            metamagic["effective_target_scaling_bonus_levels"] = 1
            return metamagic

        return metamagic

    def _build_default_metamagic(self) -> dict[str, Any]:
        return {
            "selected": [],
            "subtle_spell": False,
            "quickened_spell": False,
            "distant_spell": False,
            "heightened_spell": False,
            "careful_spell": False,
            "empowered_spell": False,
            "extended_spell": False,
            "seeking_spell": False,
            "transmuted_spell": False,
            "twinned_spell": False,
            "sorcery_point_cost": 0,
            "heightened_target_id": None,
            "careful_target_ids": [],
            "effective_range_override_feet": None,
            "transmuted_damage_type": None,
            "effective_target_scaling_bonus_levels": 0,
        }

    def _spell_can_use_distant_spell(self, *, spell_definition: dict[str, Any]) -> bool:
        targeting = spell_definition.get("targeting")
        if isinstance(targeting, dict):
            range_kind = targeting.get("range_kind")
            if isinstance(range_kind, str) and range_kind.strip().lower() == "touch":
                return True
            range_feet = targeting.get("range_feet")
            if isinstance(range_feet, int) and range_feet >= 5:
                return True
        base = spell_definition.get("base")
        if isinstance(base, dict):
            spell_range = base.get("range")
            if isinstance(spell_range, str) and spell_range.strip().lower() == "touch":
                return True
        return False

    def _resolve_distant_spell_range_override_feet(self, *, spell_definition: dict[str, Any]) -> int | None:
        targeting = spell_definition.get("targeting")
        if isinstance(targeting, dict):
            range_kind = targeting.get("range_kind")
            if isinstance(range_kind, str) and range_kind.strip().lower() == "touch":
                return 30
            range_feet = targeting.get("range_feet")
            if isinstance(range_feet, int) and range_feet >= 5:
                return range_feet * 2
        base = spell_definition.get("base")
        if isinstance(base, dict):
            spell_range = base.get("range")
            if isinstance(spell_range, str) and spell_range.strip().lower() == "touch":
                return 30
        return None

    def _spell_requires_saving_throw(self, *, spell_definition: dict[str, Any]) -> bool:
        save_ability = spell_definition.get("save_ability")
        if isinstance(save_ability, str) and save_ability.strip():
            return True
        resolution = spell_definition.get("resolution")
        if isinstance(resolution, dict):
            resolution_save_ability = resolution.get("save_ability")
            if isinstance(resolution_save_ability, str) and resolution_save_ability.strip():
                return True
            return str(resolution.get("mode") or "").strip().lower() == "save"
        return False

    def _build_noticeability(self, *, metamagic: dict[str, Any]) -> dict[str, Any]:
        if bool(metamagic.get("subtle_spell")):
            return {
                "casting_is_perceptible": False,
                "verbal_visible": False,
                "somatic_visible": False,
                "material_visible": False,
                "spell_effect_visible": True,
            }
        return {
            "casting_is_perceptible": True,
            "verbal_visible": True,
            "somatic_visible": True,
            "material_visible": True,
            "spell_effect_visible": True,
        }

    def _consume_spell_slot_if_needed(
        self,
        caster: EncounterEntity,
        spell_level: int,
        cast_level: int,
    ) -> dict[str, Any] | None:
        # 戏法不消耗法术位，所以这里直接返回 None。
        if spell_level == 0:
            return None

        return consume_exact_spell_slot(caster, cast_level)

    def _consume_sorcery_points_if_needed(
        self,
        *,
        caster: EncounterEntity,
        metamagic: dict[str, Any],
    ) -> dict[str, Any] | None:
        cost = int(metamagic.get("sorcery_point_cost", 0) or 0)
        if cost <= 0:
            return None
        sorcerer = ensure_sorcerer_runtime(caster)
        sorcery_points = sorcerer.setdefault("sorcery_points", {})
        current_points = int(sorcery_points.get("current", 0) or 0)
        if current_points < cost:
            raise ValueError("insufficient_sorcery_points")
        sorcery_points["current"] = current_points - cost
        return {"amount": cost}

    def _rollback_spell_slot_if_needed(
        self,
        caster: EncounterEntity,
        slot_consumed: dict[str, Any] | None,
    ) -> None:
        if slot_consumed is None:
            return

        restore_consumed_spell_slot(caster, slot_consumed)

    def _restore_sorcery_points_if_needed(
        self,
        *,
        caster: EncounterEntity,
        sorcery_points_consumed: dict[str, Any] | None,
    ) -> None:
        if sorcery_points_consumed is None:
            return
        amount = int(sorcery_points_consumed.get("amount", 0) or 0)
        if amount <= 0:
            return
        sorcerer = ensure_sorcerer_runtime(caster)
        sorcery_points = sorcerer.setdefault("sorcery_points", {})
        current_points = int(sorcery_points.get("current", 0) or 0)
        sorcery_points["current"] = current_points + amount

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

    def _validate_action_cost_available_or_raise(
        self,
        *,
        caster: EncounterEntity,
        action_cost: str | None,
    ) -> None:
        action_economy = caster.action_economy if isinstance(caster.action_economy, dict) else {}
        if action_cost == "action" and bool(action_economy.get("action_used")):
            raise ValueError("action_already_used")
        if action_cost == "bonus_action" and bool(action_economy.get("bonus_action_used")):
            raise ValueError("bonus_action_already_used")
        if action_cost == "reaction" and bool(action_economy.get("reaction_used")):
            raise ValueError("reaction_already_used")

    def _will_consume_spell_slot_for_cast(
        self,
        *,
        spell_level: int,
        free_find_steed_cast_used: bool,
        free_hunters_mark_cast_used: bool,
    ) -> bool:
        if spell_level <= 0:
            return False
        return not free_find_steed_cast_used and not free_hunters_mark_cast_used

    def _validate_spell_slot_cast_limit_or_raise(
        self,
        *,
        caster: EncounterEntity,
        will_consume_spell_slot: bool,
        action_cost: str | None = None,
    ) -> None:
        if not will_consume_spell_slot:
            return
        if action_cost == "reaction":
            return
        action_economy = caster.action_economy if isinstance(caster.action_economy, dict) else {}
        if bool(action_economy.get("spell_slot_cast_used_this_turn")):
            raise RuleValidationError(
                "spell_slot_cast_already_used_this_turn",
                "本回合你已通过自身施法消耗过一次法术位，不能再以动作或附赠动作施展会消耗法术位的法术；反应法术、物品施法与其他不消耗法术位的施法不受此限制。",
                rule_context={
                    "casting_source": "self_spellcasting",
                    "consumes_spell_slot": True,
                    "action_cost": action_cost,
                    "reaction_spell_exception": True,
                    "item_cast_exception": True,
                    "non_slot_cast_exception": True,
                },
            )

    def _record_spell_slot_cast_if_needed(
        self,
        *,
        caster: EncounterEntity,
        slot_consumed: dict[str, Any] | None,
    ) -> None:
        if slot_consumed is None:
            return
        if not isinstance(caster.action_economy, dict):
            caster.action_economy = {}
        caster.action_economy["spell_slot_cast_used_this_turn"] = True

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
                self._maybe_apply_ranger_hunters_mark_overrides(
                    caster=caster,
                    spell_definition=spell_definition,
                    turn_effect_instance=instance,
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

    def _maybe_apply_ranger_hunters_mark_overrides(
        self,
        *,
        caster: EncounterEntity,
        spell_definition: dict[str, Any],
        turn_effect_instance: dict[str, Any],
    ) -> None:
        if not self._is_hunters_mark_spell(spell_definition):
            return
        ranger = ensure_ranger_runtime(caster)
        foe_slayer = ranger.get("foe_slayer")
        if not isinstance(foe_slayer, dict) or not foe_slayer.get("enabled"):
            return
        damage_die = foe_slayer.get("hunters_mark_damage_die")
        if not isinstance(damage_die, str) or not damage_die.strip():
            return
        damage_parts = turn_effect_instance.get("attack_bonus_damage_parts")
        if not isinstance(damage_parts, list) or not damage_parts:
            return
        first_part = damage_parts[0]
        if not isinstance(first_part, dict):
            return
        first_part["formula"] = damage_die.strip()

    def _maybe_build_no_roll_spell_instance(
        self,
        *,
        encounter: Encounter,
        caster: EncounterEntity,
        spell_definition: dict[str, Any],
        cast_level: int,
        target_ids: list[str],
        turn_effect_updates: list[dict[str, Any]],
        metamagic: dict[str, Any],
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
            metamagic=metamagic,
        )
        encounter.spell_instances.append(instance)
        return instance

    def _spell_has_damage_resolution(self, *, spell_definition: dict[str, Any]) -> bool:
        on_cast = spell_definition.get("on_cast")
        if not isinstance(on_cast, dict):
            return False
        for key in ("on_hit", "on_failed_save", "on_successful_save"):
            outcome = on_cast.get(key)
            if not isinstance(outcome, dict):
                continue
            damage_parts = outcome.get("damage_parts")
            if isinstance(damage_parts, list) and damage_parts:
                return True
        return False

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
