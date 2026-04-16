"""模型层测试：覆盖 schema 校验和序列化行为。"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap, Event, RollRequest, RollResult


def build_entity(entity_id: str = "ent_ally_eric_001") -> EncounterEntity:
    """构造一个合法的基础实体，供其他测试复用。"""
    return EncounterEntity(
        entity_id=entity_id,
        entity_def_id="pc_eric_lv5",
        source_ref={"character_id": "pc_eric_001"},
        name="Eric",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 15, "y": 19},
        hp={"current": 80, "max": 80, "temp": 0},
        ac=16,
        speed={"walk": 30, "remaining": 30},
        initiative=17,
        ability_scores={"str": 10, "dex": 18, "con": 12, "int": 14, "wis": 10, "cha": 16},
        ability_mods={"str": 0, "dex": 4, "con": 1, "int": 2, "wis": 0, "cha": 3},
        proficiency_bonus=3,
        save_proficiencies=["wis", "cha"],
        skill_modifiers={"arcana": 5, "stealth": 7},
        conditions=[],
        resources={"spell_slots": {"1": {"max": 2, "remaining": 2}}},
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        combat_flags={"is_active": True, "is_defeated": False, "is_concentrating": False},
        weapons=[],
        spells=[],
        resistances=[],
        immunities=[],
        vulnerabilities=[],
        notes=[],
    )


def build_map() -> EncounterMap:
    """构造一个最小可用地图，方便创建 encounter。"""
    return EncounterMap(
        map_id="map_factory_floor_01",
        name="Factory Floor",
        description="A metal floor with narrow walkways.",
        width=30,
        height=30,
        grid_size_feet=5,
    )


class EncounterModelTests(unittest.TestCase):
    def test_encounter_roundtrip(self) -> None:
        """测试合法的 encounter 在 to_dict/from_dict 后仍能保持关键信息不变。"""
        entity = build_entity()
        encounter = Encounter(
            encounter_id="enc_day1_iron_duster",
            name="Iron Duster Ambush",
            status="active",
            round=1,
            current_entity_id=entity.entity_id,
            turn_order=[entity.entity_id],
            entities={entity.entity_id: entity},
            map=build_map(),
            encounter_notes=[],
        )

        roundtrip = Encounter.from_dict(encounter.to_dict())

        self.assertEqual(roundtrip.encounter_id, encounter.encounter_id)
        self.assertEqual(roundtrip.current_entity_id, entity.entity_id)
        self.assertIn(entity.entity_id, roundtrip.entities)

    def test_encounter_roundtrip_preserves_spell_instances(self) -> None:
        entity = build_entity()
        encounter = Encounter(
            encounter_id="enc_day1_hold_person",
            name="Hold Person Encounter",
            status="active",
            round=1,
            current_entity_id=entity.entity_id,
            turn_order=[entity.entity_id],
            entities={entity.entity_id: entity},
            map=build_map(),
            encounter_notes=[],
            spell_instances=[
                {
                    "instance_id": "spell_hold_person_001",
                    "spell_id": "hold_person",
                    "spell_name": "Hold Person",
                    "caster_entity_id": "ent_enemy_a",
                    "caster_name": "敌人A",
                    "cast_level": 2,
                    "concentration": {"required": True, "active": True},
                    "targets": [
                        {
                            "entity_id": entity.entity_id,
                            "applied_conditions": ["paralyzed"],
                            "turn_effect_ids": ["effect_hold_person_001"],
                        }
                    ],
                    "lifecycle": {"status": "active", "started_round": 1},
                    "special_runtime": {"retargetable": False},
                }
            ],
        )

        roundtrip = Encounter.from_dict(encounter.to_dict())

        self.assertEqual(roundtrip.spell_instances[0]["spell_id"], "hold_person")
        self.assertEqual(roundtrip.spell_instances[0]["targets"][0]["entity_id"], entity.entity_id)

    def test_encounter_roundtrip_preserves_reaction_requests_and_pending_movement(self) -> None:
        entity = build_entity()
        encounter = Encounter(
            encounter_id="enc_day1_reaction_request",
            name="Reaction Request Encounter",
            status="active",
            round=1,
            current_entity_id=entity.entity_id,
            turn_order=[entity.entity_id],
            entities={entity.entity_id: entity},
            map=build_map(),
            encounter_notes=[],
            reaction_requests=[
                {
                    "request_id": "react_001",
                    "reaction_type": "opportunity_attack",
                    "trigger_type": "leave_melee_reach",
                    "status": "pending",
                    "actor_entity_id": entity.entity_id,
                    "actor_name": entity.name,
                    "target_entity_id": "ent_enemy_001",
                    "target_name": "Enemy",
                    "ask_player": True,
                    "auto_resolve": False,
                    "source_event_type": "movement_trigger_check",
                    "source_event_id": None,
                    "payload": {
                        "weapon_id": "rapier",
                        "weapon_name": "Rapier",
                        "trigger_position": {"x": 5, "y": 4},
                        "reason": "目标离开了你的近战触及",
                    },
                }
            ],
            pending_movement={
                "movement_id": "move_001",
                "entity_id": entity.entity_id,
                "start_position": {"x": 4, "y": 4},
                "target_position": {"x": 8, "y": 4},
                "current_position": {"x": 5, "y": 4},
                "remaining_path": [{"x": 6, "y": 4}],
                "count_movement": True,
                "use_dash": False,
                "status": "waiting_reaction",
                "waiting_request_id": "react_001",
            },
        )

        roundtrip = Encounter.from_dict(encounter.to_dict())

        self.assertEqual(roundtrip.reaction_requests[0]["request_id"], "react_001")
        self.assertEqual(roundtrip.pending_movement["movement_id"], "move_001")

    def test_encounter_accepts_pending_reaction_window_and_serializes_it(self) -> None:
        entity = build_entity()
        encounter = Encounter(
            encounter_id="enc_reaction_window_test",
            name="Reaction Window Test",
            status="active",
            round=1,
            current_entity_id=entity.entity_id,
            turn_order=[entity.entity_id],
            entities={entity.entity_id: entity},
            map=build_map(),
            encounter_notes=[],
            reaction_requests=[
                {
                    "request_id": "react_001",
                    "status": "pending",
                    "reaction_type": "shield",
                    "template_type": "targeted_defense_rewrite",
                }
            ],
            pending_reaction_window={
                "window_id": "rw_001",
                "status": "waiting_reaction",
                "trigger_type": "attack_declared",
                "host_action_type": "attack",
                "host_action_id": "atk_001",
                "host_action_snapshot": {"phase": "before_hit_locked"},
                "choice_groups": [],
                "resolved_group_ids": [],
            },
        )

        payload = encounter.to_dict()

        self.assertEqual(payload["pending_reaction_window"]["window_id"], "rw_001")
        self.assertEqual(payload["reaction_requests"][0]["template_type"], "targeted_defense_rewrite")

    def test_entity_roundtrip_preserves_turn_effects(self) -> None:
        entity = build_entity()
        entity.turn_effects = [
            {
                "effect_id": "effect_hold_person_001",
                "name": "定身术持续效果",
                "trigger": "end_of_turn",
            }
        ]

        roundtrip = EncounterEntity.from_dict(entity.to_dict())

        self.assertEqual(
            roundtrip.turn_effects,
            [
                {
                    "effect_id": "effect_hold_person_001",
                    "name": "定身术持续效果",
                    "trigger": "end_of_turn",
                }
            ],
        )

    def test_current_entity_must_exist_in_entities(self) -> None:
        """测试 current_entity_id 不能指向 entities 中不存在的实体。"""
        entity = build_entity()

        with self.assertRaises(ValueError):
            Encounter(
                encounter_id="enc_day1_iron_duster",
                name="Iron Duster Ambush",
                status="active",
                round=1,
                current_entity_id="ent_missing",
                turn_order=[entity.entity_id],
                entities={entity.entity_id: entity},
                map=build_map(),
            )

    def test_turn_order_must_not_reference_unknown_entity(self) -> None:
        """测试 turn_order 不能引用 entities 之外的未知实体。"""
        entity = build_entity()

        with self.assertRaises(ValueError):
            Encounter(
                encounter_id="enc_day1_iron_duster",
                name="Iron Duster Ambush",
                status="active",
                round=1,
                current_entity_id=entity.entity_id,
                turn_order=[entity.entity_id, "ent_missing"],
                entities={entity.entity_id: entity},
                map=build_map(),
            )

    def test_roll_and_event_models_validate(self) -> None:
        """测试 RollRequest、RollResult、Event 的类型标记和基本序列化结果。"""
        request = RollRequest(
            request_id="req_attack_001",
            encounter_id="enc_day1_iron_duster",
            actor_entity_id="ent_ally_eric_001",
            target_entity_id="ent_enemy_iron_duster_001",
            roll_type="spell_attack",
            formula="1d20+7",
            context={"target_ac": 16},
        )
        result = RollResult(
            request_id=request.request_id,
            encounter_id=request.encounter_id,
            actor_entity_id=request.actor_entity_id,
            target_entity_id=request.target_entity_id,
            roll_type=request.roll_type,
            final_total=10,
            dice_rolls={"base_rolls": [3], "modifier": 4, "proficiency": 3},
        )
        event = Event(
            event_id="evt_001",
            encounter_id=request.encounter_id,
            round=1,
            event_type="attack_resolved",
            actor_entity_id=request.actor_entity_id,
            target_entity_id=request.target_entity_id,
            request_id=request.request_id,
            payload={"attack_total": 10, "hit": False},
        )

        self.assertEqual(request.to_dict()["type"], "request_roll")
        self.assertEqual(result.to_dict()["type"], "roll_result")
        self.assertEqual(event.to_dict()["event_type"], "attack_resolved")


if __name__ == "__main__":
    unittest.main()
