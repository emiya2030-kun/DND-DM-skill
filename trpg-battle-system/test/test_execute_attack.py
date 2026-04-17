"""完整攻击执行测试:覆盖请求生成、攻击结算和命中后自动扣血."""

import sys
import tempfile
import unittest
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository, WeaponDefinitionRepository
from tools.services import AppendEvent, AttackRollRequest, AttackRollResult, ExecuteAttack, UpdateHp


@contextmanager
def make_repositories() -> Iterator[tuple[EncounterRepository, EventRepository]]:
    """创建测试仓储，并确保在临时目录释放前关闭文件句柄."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        try:
            yield encounter_repo, event_repo
        finally:
            try:
                encounter_repo.close()
            finally:
                event_repo.close()


def build_actor() -> EncounterEntity:
    """构造完整攻击测试里的攻击者."""
    return EncounterEntity(
        entity_id="ent_ally_eric_001",
        name="Eric",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
        ability_mods={"str": 1, "dex": 3, "con": 1, "int": 0, "wis": 0, "cha": 2},
        proficiency_bonus=2,
        weapons=[
            {
                "weapon_id": "rapier",
                "name": "Rapier",
                "attack_bonus": 5,
                "damage": [{"formula": "1d8+3", "type": "piercing"}],
                "properties": ["finesse"],
                "range": {"normal": 5, "long": 5},
            }
        ],
    )


def build_fighter_actor_for_extra_attack(
    *,
    attack_action_attacks_used: int = 0,
    action_used: bool = False,
    extra_attack_count: Optional[int] = None,
    extra_attack_sources: Optional[list[dict[str, int]]] = None,
    fighter_level: int = 5,
    studied_attacks: Optional[list[dict[str, object]]] = None,
    tactical_master_enabled: bool = False,
) -> EncounterEntity:
    fighter_state: dict[str, object] = {
        "level": fighter_level,
        "fighter_level": fighter_level,
        "turn_counters": {"attack_action_attacks_used": attack_action_attacks_used},
    }
    if extra_attack_count is not None:
        fighter_state["extra_attack_count"] = extra_attack_count
    if extra_attack_sources is not None:
        fighter_state["extra_attack_sources"] = extra_attack_sources
    if studied_attacks is not None:
        fighter_state["studied_attacks"] = studied_attacks
    if tactical_master_enabled:
        fighter_state["tactical_master_enabled"] = True

    return EncounterEntity(
        entity_id="ent_fighter_001",
        name="Fighter",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 30, "max": 30, "temp": 0},
        ac=16,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
        ability_mods={"str": 4, "dex": 1, "con": 3, "int": 0, "wis": 1, "cha": 0},
        proficiency_bonus=3,
        action_economy={"action_used": action_used, "bonus_action_used": False, "reaction_used": False},
        weapons=[
            {
                "weapon_id": "rapier",
                "name": "Rapier",
                "attack_bonus": 7,
                "damage": [{"formula": "1d8+4", "type": "piercing"}],
                "properties": ["finesse"],
                "range": {"normal": 5, "long": 5},
            }
        ],
        class_features={"fighter": fighter_state},
    )


def build_target() -> EncounterEntity:
    """构造完整攻击测试里的目标."""
    return EncounterEntity(
        entity_id="ent_enemy_goblin_001",
        name="Goblin",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 3, "y": 2},
        hp={"current": 9, "max": 9, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
    )


def build_fighter_encounter_for_extra_attack(
    actor: Optional[EncounterEntity] = None,
    target: Optional[EncounterEntity] = None,
) -> Encounter:
    actor = actor or build_fighter_actor_for_extra_attack()
    target = target or build_target()
    return Encounter(
        encounter_id="enc_fighter_test",
        name="Fighter Test Encounter",
        status="active",
        round=1,
        current_entity_id=actor.entity_id,
        turn_order=[actor.entity_id, target.entity_id],
        entities={actor.entity_id: actor, target.entity_id: target},
        map=EncounterMap(
            map_id="map_fighter_test",
            name="Fighter Test Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
    )


def build_humanoid_target(*, category: str = "npc", hp_current: int = 7) -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_enemy_bandit_001",
        name="Bandit",
        side="enemy",
        category=category,
        controller="gm" if category == "npc" else "player",
        position={"x": 3, "y": 2},
        hp={"current": hp_current, "max": 10, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
        combat_flags={"is_active": True, "is_defeated": False},
    )


def build_encounter(actor: Optional[EncounterEntity] = None, target: Optional[EncounterEntity] = None) -> Encounter:
    """构造完整攻击测试需要的最小 encounter."""
    actor = actor or build_actor()
    target = target or build_target()
    return Encounter(
        encounter_id="enc_execute_attack_test",
        name="Execute Attack Test Encounter",
        status="active",
        round=1,
        current_entity_id=actor.entity_id,
        turn_order=[actor.entity_id, target.entity_id],
        entities={actor.entity_id: actor, target.entity_id: target},
        map=EncounterMap(
            map_id="map_execute_attack_test",
            name="Execute Attack Test Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
    )


def build_actor_with_infernal_rapier() -> EncounterEntity:
    """构造拿着多段伤害武器的攻击者."""
    actor = build_actor()
    actor.weapons = [
        {
            "weapon_id": "infernal_rapier",
            "name": "Infernal Rapier",
            "attack_bonus": 5,
            "damage": [
                {"formula": "1d8+3", "type": "piercing"},
                {"formula": "1d8", "type": "fire"},
            ],
            "properties": ["finesse"],
            "range": {"normal": 5, "long": 5},
        }
    ]
    return actor


class ExecuteAttackTests(unittest.TestCase):
    def test_execute_applies_knockout_protection_when_melee_attack_drops_humanoid_to_zero_hp(self) -> None:
        with make_repositories() as (encounter_repo, event_repo):
            actor = build_actor()
            target = build_humanoid_target(category="npc", hp_current=7)
            encounter_repo.save(build_encounter(actor=actor, target=target))

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id=target.entity_id,
                weapon_id="rapier",
                final_total=15,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [4]}],
                zero_hp_intent="knockout",
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertIsNotNone(updated)
            updated_target = updated.entities[target.entity_id]
            protection_effects = [
                effect
                for effect in updated_target.turn_effects
                if effect.get("effect_type") == "knockout_protection"
            ]
            self.assertTrue(result["resolution"]["hit"])
            self.assertEqual(updated_target.hp["current"], 0)
            self.assertIn("unconscious", updated_target.conditions)
            self.assertEqual(updated_target.combat_flags["death_saves"], {"successes": 0, "failures": 0})
            self.assertEqual(len(protection_effects), 1)
            self.assertEqual(protection_effects[0]["duration_seconds"], 3600)

    def test_execute_ignores_knockout_intent_for_ranged_attack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            knowledge_path = Path(tmp_dir) / "weapon_definitions.json"
            knowledge_path.write_text(
                json.dumps(
                    {
                        "weapon_definitions": {
                            "longbow": {
                                "id": "longbow",
                                "name": "长弓",
                                "category": "martial",
                                "kind": "ranged",
                                "base_damage": {"formula": "1d8", "damage_type": "piercing"},
                                "properties": ["heavy", "two_handed"],
                                "mastery": "slow",
                                "range": {"normal": 150, "long": 600},
                                "hands": {"mode": "two_handed"}
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_actor()
            actor.weapons = [{"weapon_id": "longbow", "is_proficient": True}]
            actor.position = {"x": 1, "y": 1}
            target = build_humanoid_target(category="pc", hp_current=7)
            target.position = {"x": 6, "y": 1}
            encounter_repo.save(build_encounter(actor=actor, target=target))

            append_event = AppendEvent(event_repo)
            weapon_repo = WeaponDefinitionRepository(knowledge_path)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo, weapon_definition_repository=weapon_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id=target.entity_id,
                weapon_id="longbow",
                final_total=15,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:longbow:part_0", "rolls": [4]}],
                zero_hp_intent="knockout",
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertIsNotNone(updated)
            updated_target = updated.entities[target.entity_id]
            protection_effects = [
                effect
                for effect in updated_target.turn_effects
                if effect.get("effect_type") == "knockout_protection"
            ]
            self.assertTrue(result["resolution"]["hit"])
            self.assertEqual(updated_target.hp["current"], 0)
            self.assertIn("unconscious", updated_target.conditions)
            self.assertEqual(updated_target.combat_flags["death_saves"], {"successes": 0, "failures": 0})
            self.assertEqual(protection_effects, [])
            encounter_repo.close()
            event_repo.close()

    def test_execute_applies_vex_effect_and_consumes_it_on_next_attack(self) -> None:
        """测试 Vex 命中后会挂效果，并在下一次对同目标攻击时提供优势后被消耗。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            knowledge_path = Path(tmp_dir) / "weapon_definitions.json"
            knowledge_path.write_text(
                json.dumps(
                    {
                        "weapon_definitions": {
                            "rapier": {
                                "id": "rapier",
                                "name": "刺剑",
                                "category": "martial",
                                "kind": "melee",
                                "base_damage": {"formula": "1d8", "damage_type": "piercing"},
                                "properties": ["finesse"],
                                "mastery": "vex",
                                "range": {"normal": 5, "long": 5},
                                "hands": {"mode": "one_handed"}
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_actor()
            actor.weapons = [{"weapon_id": "rapier", "is_proficient": True}]
            encounter_repo.save(build_encounter(actor=actor))

            append_event = AppendEvent(event_repo)
            weapon_repo = WeaponDefinitionRepository(knowledge_path)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo, weapon_definition_repository=weapon_repo),
                AttackRollResult(encounter_repo, append_event, UpdateHp(encounter_repo, append_event)),
            )

            first = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=15,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [4]}],
            )

            mid_state = encounter_repo.get("enc_execute_attack_test")
            self.assertTrue(first["resolution"]["hit"])
            self.assertEqual(len(mid_state.entities["ent_ally_eric_001"].turn_effects), 1)
            self.assertEqual(mid_state.entities["ent_ally_eric_001"].turn_effects[0]["mastery"], "vex")
            first_effect_id = mid_state.entities["ent_ally_eric_001"].turn_effects[0]["effect_id"]

            mid_state.entities["ent_ally_eric_001"].action_economy["action_used"] = False
            encounter_repo.save(mid_state)

            second = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=15,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [3]}],
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertEqual(second["request"]["context"]["vantage"], "advantage")
            self.assertIn("mastery_vex", ",".join(second["request"]["context"]["vantage_sources"]["advantage"]))
            self.assertEqual(len(updated.entities["ent_ally_eric_001"].turn_effects), 1)
            self.assertEqual(updated.entities["ent_ally_eric_001"].turn_effects[0]["mastery"], "vex")
            self.assertNotEqual(updated.entities["ent_ally_eric_001"].turn_effects[0]["effect_id"], first_effect_id)
            encounter_repo.close()
            event_repo.close()

    def test_execute_applies_sap_effect_and_consumes_it_on_target_next_attack(self) -> None:
        """测试 Sap 命中后会让目标下一次攻击劣势，并在使用后被消耗。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            knowledge_path = Path(tmp_dir) / "weapon_definitions.json"
            knowledge_path.write_text(
                json.dumps(
                    {
                        "weapon_definitions": {
                            "mace": {
                                "id": "mace",
                                "name": "硬头锤",
                                "category": "simple",
                                "kind": "melee",
                                "base_damage": {"formula": "1d6", "damage_type": "bludgeoning"},
                                "properties": [],
                                "mastery": "sap",
                                "range": {"normal": 5, "long": 5},
                                "hands": {"mode": "one_handed"}
                            },
                            "rapier": {
                                "id": "rapier",
                                "name": "刺剑",
                                "category": "martial",
                                "kind": "melee",
                                "base_damage": {"formula": "1d8", "damage_type": "piercing"},
                                "properties": ["finesse"],
                                "mastery": "vex",
                                "range": {"normal": 5, "long": 5},
                                "hands": {"mode": "one_handed"}
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_actor()
            actor.weapons = [{"weapon_id": "mace", "is_proficient": True}]
            target = build_target()
            target.weapons = [
                {
                    "weapon_id": "rapier",
                    "name": "Rapier",
                    "attack_bonus": 5,
                    "damage": [{"formula": "1d8+3", "type": "piercing"}],
                    "properties": ["finesse"],
                    "range": {"normal": 5, "long": 5},
                }
            ]
            encounter = build_encounter(actor=actor, target=target)
            encounter_repo.save(encounter)

            append_event = AppendEvent(event_repo)
            weapon_repo = WeaponDefinitionRepository(knowledge_path)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo, weapon_definition_repository=weapon_repo),
                AttackRollResult(encounter_repo, append_event, UpdateHp(encounter_repo, append_event)),
            )

            first = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="mace",
                final_total=15,
                dice_rolls={"base_rolls": [12], "modifier": 3},
                damage_rolls=[{"source": "weapon:mace:part_0", "rolls": [4]}],
            )

            mid_state = encounter_repo.get("enc_execute_attack_test")
            self.assertTrue(first["resolution"]["hit"])
            self.assertEqual(len(mid_state.entities["ent_enemy_goblin_001"].turn_effects), 1)
            self.assertEqual(mid_state.entities["ent_enemy_goblin_001"].turn_effects[0]["mastery"], "sap")
            sap_effect_id = mid_state.entities["ent_enemy_goblin_001"].turn_effects[0]["effect_id"]
            mid_state.current_entity_id = "ent_enemy_goblin_001"
            mid_state.entities["ent_enemy_goblin_001"].action_economy["action_used"] = False
            encounter_repo.save(mid_state)

            second = service.execute(
                encounter_id="enc_execute_attack_test",
                actor_id="ent_enemy_goblin_001",
                target_id="ent_ally_eric_001",
                weapon_id="rapier",
                final_total=15,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [3]}],
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertEqual(second["request"]["context"]["vantage"], "disadvantage")
            self.assertIn("mastery_sap", ",".join(second["request"]["context"]["vantage_sources"]["disadvantage"]))
            self.assertEqual(len(updated.entities["ent_enemy_goblin_001"].turn_effects), 1)
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].turn_effects[0]["mastery"], "vex")
            self.assertNotEqual(updated.entities["ent_enemy_goblin_001"].turn_effects[0]["effect_id"], sap_effect_id)
            encounter_repo.close()
            event_repo.close()

    def test_execute_applies_slow_effect_and_reduces_target_remaining_speed(self) -> None:
        """测试 Slow 命中并造成伤害后会给目标挂减速效果并立刻减少剩余速度。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            knowledge_path = Path(tmp_dir) / "weapon_definitions.json"
            knowledge_path.write_text(
                json.dumps(
                    {
                        "weapon_definitions": {
                            "longbow": {
                                "id": "longbow",
                                "name": "长弓",
                                "category": "martial",
                                "kind": "ranged",
                                "base_damage": {"formula": "1d8", "damage_type": "piercing"},
                                "properties": ["heavy", "two_handed"],
                                "mastery": "slow",
                                "range": {"normal": 150, "long": 600},
                                "hands": {"mode": "two_handed"}
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_actor()
            actor.position = {"x": 1, "y": 1}
            actor.weapons = [{"weapon_id": "longbow", "is_proficient": True}]
            target = build_target()
            target.position = {"x": 6, "y": 1}
            encounter_repo.save(build_encounter(actor=actor, target=target))

            append_event = AppendEvent(event_repo)
            weapon_repo = WeaponDefinitionRepository(knowledge_path)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo, weapon_definition_repository=weapon_repo),
                AttackRollResult(encounter_repo, append_event, UpdateHp(encounter_repo, append_event)),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="longbow",
                final_total=15,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:longbow:part_0", "rolls": [4]}],
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertTrue(result["resolution"]["hit"])
            self.assertEqual(len(updated.entities["ent_enemy_goblin_001"].turn_effects), 1)
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].turn_effects[0]["mastery"], "slow")
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].speed["remaining"], 20)
            encounter_repo.close()
            event_repo.close()

    def test_execute_applies_topple_prone_when_target_fails_save(self) -> None:
        """测试 Topple 命中后若目标体质豁免失败，会自动附加 prone。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            knowledge_path = Path(tmp_dir) / "weapon_definitions.json"
            knowledge_path.write_text(
                json.dumps(
                    {
                        "weapon_definitions": {
                            "quarterstaff": {
                                "id": "quarterstaff",
                                "name": "长棍",
                                "category": "simple",
                                "kind": "melee",
                                "base_damage": {"formula": "1d6", "damage_type": "bludgeoning"},
                                "properties": ["versatile"],
                                "mastery": "topple",
                                "range": {"normal": 5, "long": 5},
                                "hands": {"mode": "versatile"}
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_actor()
            actor.weapons = [{"weapon_id": "quarterstaff", "is_proficient": True}]
            target = build_target()
            target.ability_mods = {"str": 0, "dex": 2, "con": 1, "int": 0, "wis": 0, "cha": 0}
            encounter_repo.save(build_encounter(actor=actor, target=target))

            append_event = AppendEvent(event_repo)
            weapon_repo = WeaponDefinitionRepository(knowledge_path)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo, weapon_definition_repository=weapon_repo),
                AttackRollResult(encounter_repo, append_event, UpdateHp(encounter_repo, append_event)),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="quarterstaff",
                final_total=15,
                dice_rolls={"base_rolls": [12], "modifier": 3},
                damage_rolls=[{"source": "weapon:quarterstaff:part_0", "rolls": [4]}],
                mastery_rolls={"topple": {"base_roll": 5}},
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertTrue(result["resolution"]["hit"])
            self.assertIn("prone", updated.entities["ent_enemy_goblin_001"].conditions)
            topple = result["resolution"]["weapon_mastery_updates"]["topple"]
            self.assertEqual(topple["save"]["dc"], 11)
            self.assertFalse(topple["save"]["success"])
            encounter_repo.close()
            event_repo.close()

    def test_execute_returns_pending_topple_save_when_roll_missing(self) -> None:
        """测试 Topple 命中但未提供豁免掷骰时，会返回待结算保存信息而不阻断攻击。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            knowledge_path = Path(tmp_dir) / "weapon_definitions.json"
            knowledge_path.write_text(
                json.dumps(
                    {
                        "weapon_definitions": {
                            "quarterstaff": {
                                "id": "quarterstaff",
                                "name": "长棍",
                                "category": "simple",
                                "kind": "melee",
                                "base_damage": {"formula": "1d6", "damage_type": "bludgeoning"},
                                "properties": ["versatile"],
                                "mastery": "topple",
                                "range": {"normal": 5, "long": 5},
                                "hands": {"mode": "versatile"}
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_actor()
            actor.weapons = [{"weapon_id": "quarterstaff", "is_proficient": True}]
            encounter_repo.save(build_encounter(actor=actor))

            append_event = AppendEvent(event_repo)
            weapon_repo = WeaponDefinitionRepository(knowledge_path)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo, weapon_definition_repository=weapon_repo),
                AttackRollResult(encounter_repo, append_event, UpdateHp(encounter_repo, append_event)),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="quarterstaff",
                final_total=15,
                dice_rolls={"base_rolls": [12], "modifier": 3},
                damage_rolls=[{"source": "weapon:quarterstaff:part_0", "rolls": [4]}],
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertTrue(result["resolution"]["hit"])
            self.assertNotIn("prone", updated.entities["ent_enemy_goblin_001"].conditions)
            topple = result["resolution"]["weapon_mastery_updates"]["topple"]
            self.assertEqual(topple["status"], "pending_save")
            self.assertEqual(topple["save_dc"], 11)
            encounter_repo.close()
            event_repo.close()

    def test_execute_applies_graze_damage_when_attack_misses(self) -> None:
        """测试 Graze 武器失手时仍会造成等同属性调整值的伤害。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            knowledge_path = Path(tmp_dir) / "weapon_definitions.json"
            knowledge_path.write_text(
                json.dumps(
                    {
                        "weapon_definitions": {
                            "greatsword": {
                                "id": "greatsword",
                                "name": "巨剑",
                                "category": "martial",
                                "kind": "melee",
                                "base_damage": {"formula": "2d6", "damage_type": "slashing"},
                                "properties": ["heavy", "two_handed"],
                                "mastery": "graze",
                                "range": {"normal": 5, "long": 5},
                                "hands": {"mode": "two_handed"}
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_actor()
            actor.ability_mods["str"] = 3
            actor.ability_scores = {"str": 16, "dex": 12, "con": 12, "int": 10, "wis": 10, "cha": 14}
            actor.weapons = [{"weapon_id": "greatsword", "is_proficient": True}]
            target = build_target()
            target.ac = 20
            encounter_repo.save(build_encounter(actor=actor, target=target))

            append_event = AppendEvent(event_repo)
            weapon_repo = WeaponDefinitionRepository(knowledge_path)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo, weapon_definition_repository=weapon_repo),
                AttackRollResult(encounter_repo, append_event, UpdateHp(encounter_repo, append_event)),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="greatsword",
                final_total=8,
                dice_rolls={"base_rolls": [5], "modifier": 3},
                damage_rolls=[],
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertFalse(result["resolution"]["hit"])
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["current"], 6)
            graze = result["resolution"]["weapon_mastery_updates"]["graze"]
            self.assertEqual(graze["status"], "resolved")
            self.assertEqual(graze["damage"], 3)
            encounter_repo.close()
            event_repo.close()

    def test_execute_graze_zero_hp_knockout_still_applies_knockout_protection(self) -> None:
        """测试 Graze 伤害把 humanoid 打到 0 HP 时，也会透传 knockout intent。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            knowledge_path = Path(tmp_dir) / "weapon_definitions.json"
            knowledge_path.write_text(
                json.dumps(
                    {
                        "weapon_definitions": {
                            "greatsword": {
                                "id": "greatsword",
                                "name": "巨剑",
                                "category": "martial",
                                "kind": "melee",
                                "base_damage": {"formula": "2d6", "damage_type": "slashing"},
                                "properties": ["heavy", "two_handed"],
                                "mastery": "graze",
                                "range": {"normal": 5, "long": 5},
                                "hands": {"mode": "two_handed"}
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_actor()
            actor.ability_mods["str"] = 3
            actor.ability_scores = {"str": 16, "dex": 12, "con": 12, "int": 10, "wis": 10, "cha": 14}
            actor.weapons = [{"weapon_id": "greatsword", "is_proficient": True}]
            target = build_humanoid_target(category="pc", hp_current=3)
            target.ac = 20
            encounter_repo.save(build_encounter(actor=actor, target=target))

            append_event = AppendEvent(event_repo)
            weapon_repo = WeaponDefinitionRepository(knowledge_path)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo, weapon_definition_repository=weapon_repo),
                AttackRollResult(encounter_repo, append_event, UpdateHp(encounter_repo, append_event)),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id=target.entity_id,
                weapon_id="greatsword",
                final_total=8,
                dice_rolls={"base_rolls": [5], "modifier": 3},
                damage_rolls=[],
                zero_hp_intent="knockout",
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertFalse(result["resolution"]["hit"])
            self.assertIsNotNone(updated)
            updated_target = updated.entities[target.entity_id]
            protection_effects = [
                effect
                for effect in updated_target.turn_effects
                if effect.get("effect_type") == "knockout_protection"
            ]
            self.assertEqual(updated_target.hp["current"], 0)
            self.assertIn("unconscious", updated_target.conditions)
            self.assertEqual(len(protection_effects), 1)
            encounter_repo.close()
            event_repo.close()

    def test_execute_skips_graze_when_modifier_is_not_positive(self) -> None:
        """测试 Graze 在属性修正不为正时不会造成额外伤害。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            knowledge_path = Path(tmp_dir) / "weapon_definitions.json"
            knowledge_path.write_text(
                json.dumps(
                    {
                        "weapon_definitions": {
                            "greatsword": {
                                "id": "greatsword",
                                "name": "巨剑",
                                "category": "martial",
                                "kind": "melee",
                                "base_damage": {"formula": "2d6", "damage_type": "slashing"},
                                "properties": ["heavy", "two_handed"],
                                "mastery": "graze",
                                "range": {"normal": 5, "long": 5},
                                "hands": {"mode": "two_handed"}
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_actor()
            actor.ability_mods["str"] = -1
            actor.ability_scores = {"str": 8, "dex": 12, "con": 12, "int": 10, "wis": 10, "cha": 14}
            actor.weapons = [{"weapon_id": "greatsword", "is_proficient": True}]
            target = build_target()
            target.ac = 20
            encounter_repo.save(build_encounter(actor=actor, target=target))

            append_event = AppendEvent(event_repo)
            weapon_repo = WeaponDefinitionRepository(knowledge_path)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo, weapon_definition_repository=weapon_repo),
                AttackRollResult(encounter_repo, append_event, UpdateHp(encounter_repo, append_event)),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="greatsword",
                final_total=4,
                dice_rolls={"base_rolls": [5], "modifier": -1},
                damage_rolls=[],
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertFalse(result["resolution"]["hit"])
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["current"], 9)
            graze = result["resolution"]["weapon_mastery_updates"]["graze"]
            self.assertEqual(graze["status"], "no_effect")
            encounter_repo.close()
            event_repo.close()

    def test_execute_applies_push_forced_movement_when_attack_hits(self) -> None:
        """测试 Push 命中后会把目标沿直线推离 10 尺。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            knowledge_path = Path(tmp_dir) / "weapon_definitions.json"
            knowledge_path.write_text(
                json.dumps(
                    {
                        "weapon_definitions": {
                            "warhammer": {
                                "id": "warhammer",
                                "name": "战锤",
                                "category": "martial",
                                "kind": "melee",
                                "base_damage": {"formula": "1d8", "damage_type": "bludgeoning"},
                                "properties": ["versatile"],
                                "mastery": "push",
                                "range": {"normal": 5, "long": 5},
                                "hands": {"mode": "one_handed"},
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_actor()
            actor.ability_mods["str"] = 3
            actor.ability_scores = {"str": 16, "dex": 12, "con": 12, "int": 10, "wis": 10, "cha": 14}
            actor.weapons = [{"weapon_id": "warhammer", "is_proficient": True}]
            target = build_target()
            encounter_repo.save(build_encounter(actor=actor, target=target))

            append_event = AppendEvent(event_repo)
            weapon_repo = WeaponDefinitionRepository(knowledge_path)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo, weapon_definition_repository=weapon_repo),
                AttackRollResult(encounter_repo, append_event, UpdateHp(encounter_repo, append_event)),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="warhammer",
                final_total=15,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:warhammer:part_0", "rolls": [4]}],
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertTrue(result["resolution"]["hit"])
            push = result["resolution"]["weapon_mastery_updates"]["push"]
            self.assertEqual(push["status"], "resolved")
            self.assertEqual(push["moved_feet"], 10)
            self.assertFalse(push["blocked"])
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].position, {"x": 5, "y": 2})
            encounter_repo.close()
            event_repo.close()

    def test_execute_push_stops_when_second_step_blocked(self) -> None:
        """测试 Push 第二步被墙挡住时会停在第一格。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            knowledge_path = Path(tmp_dir) / "weapon_definitions.json"
            knowledge_path.write_text(
                json.dumps(
                    {
                        "weapon_definitions": {
                            "warhammer": {
                                "id": "warhammer",
                                "name": "战锤",
                                "category": "martial",
                                "kind": "melee",
                                "base_damage": {"formula": "1d8", "damage_type": "bludgeoning"},
                                "properties": ["versatile"],
                                "mastery": "push",
                                "range": {"normal": 5, "long": 5},
                                "hands": {"mode": "one_handed"},
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_actor()
            actor.ability_mods["str"] = 3
            actor.ability_scores = {"str": 16, "dex": 12, "con": 12, "int": 10, "wis": 10, "cha": 14}
            actor.weapons = [{"weapon_id": "warhammer", "is_proficient": True}]
            target = build_target()
            encounter = build_encounter(actor=actor, target=target)
            encounter.map.terrain = [{"x": 5, "y": 2, "type": "wall"}]
            encounter_repo.save(encounter)

            append_event = AppendEvent(event_repo)
            weapon_repo = WeaponDefinitionRepository(knowledge_path)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo, weapon_definition_repository=weapon_repo),
                AttackRollResult(encounter_repo, append_event, UpdateHp(encounter_repo, append_event)),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="warhammer",
                final_total=15,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:warhammer:part_0", "rolls": [4]}],
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            push = result["resolution"]["weapon_mastery_updates"]["push"]
            self.assertEqual(push["status"], "resolved")
            self.assertEqual(push["moved_feet"], 5)
            self.assertTrue(push["blocked"])
            self.assertEqual(push["block_reason"], "wall")
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].position, {"x": 4, "y": 2})
            encounter_repo.close()
            event_repo.close()

    def test_execute_push_has_no_effect_on_huge_target(self) -> None:
        """测试 Push 对超大型目标无效。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            knowledge_path = Path(tmp_dir) / "weapon_definitions.json"
            knowledge_path.write_text(
                json.dumps(
                    {
                        "weapon_definitions": {
                            "pike": {
                                "id": "pike",
                                "name": "长矛",
                                "category": "martial",
                                "kind": "melee",
                                "base_damage": {"formula": "1d10", "damage_type": "piercing"},
                                "properties": ["heavy", "reach", "two_handed"],
                                "mastery": "push",
                                "range": {"normal": 10, "long": 10},
                                "hands": {"mode": "two_handed"},
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_actor()
            actor.ability_mods["str"] = 3
            actor.ability_scores = {"str": 16, "dex": 12, "con": 12, "int": 10, "wis": 10, "cha": 14}
            actor.weapons = [{"weapon_id": "pike", "is_proficient": True}]
            target = build_target()
            target.size = "huge"
            encounter_repo.save(build_encounter(actor=actor, target=target))

            append_event = AppendEvent(event_repo)
            weapon_repo = WeaponDefinitionRepository(knowledge_path)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo, weapon_definition_repository=weapon_repo),
                AttackRollResult(encounter_repo, append_event, UpdateHp(encounter_repo, append_event)),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="pike",
                final_total=15,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:pike:part_0", "rolls": [4]}],
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            push = result["resolution"]["weapon_mastery_updates"]["push"]
            self.assertEqual(push["status"], "no_effect")
            self.assertEqual(push["reason"], "target_too_large")
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].position, {"x": 3, "y": 2})
            encounter_repo.close()
            event_repo.close()

    def test_execute_nick_light_bonus_does_not_consume_bonus_action(self) -> None:
        """测试 Nick 允许的轻型额外攻击不会消耗附赠动作。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            knowledge_path = Path(tmp_dir) / "weapon_definitions.json"
            knowledge_path.write_text(
                json.dumps(
                    {
                        "weapon_definitions": {
                            "dagger": {
                                "id": "dagger",
                                "name": "匕首",
                                "category": "simple",
                                "kind": "melee",
                                "base_damage": {"formula": "1d4", "damage_type": "piercing"},
                                "properties": ["finesse", "light", "thrown"],
                                "mastery": "nick",
                                "range": {"normal": 5, "long": 5},
                                "hands": {"mode": "one_handed"},
                                "thrown_range": {"normal": 20, "long": 60}
                            },
                            "shortsword": {
                                "id": "shortsword",
                                "name": "短剑",
                                "category": "martial",
                                "kind": "melee",
                                "base_damage": {"formula": "1d6", "damage_type": "piercing"},
                                "properties": ["finesse", "light"],
                                "mastery": "vex",
                                "range": {"normal": 5, "long": 5},
                                "hands": {"mode": "one_handed"}
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_actor()
            actor.weapons = [
                {"weapon_id": "dagger", "slot": "main_hand", "is_proficient": True},
                {"weapon_id": "shortsword", "slot": "off_hand", "is_proficient": True},
            ]
            actor.action_economy = {"action_used": False, "bonus_action_used": False, "reaction_used": False}
            encounter_repo.save(build_encounter(actor=actor))

            append_event = AppendEvent(event_repo)
            weapon_repo = WeaponDefinitionRepository(knowledge_path)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo, weapon_definition_repository=weapon_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            first = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="dagger",
                final_total=15,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:dagger:part_0", "rolls": [3]}],
            )

            second = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="shortsword",
                attack_mode="light_bonus",
                final_total=15,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:shortsword:part_0", "rolls": [4]}],
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertIsNotNone(updated)
            self.assertTrue(first["resolution"]["hit"])
            self.assertTrue(second["resolution"]["hit"])
            self.assertFalse(updated.entities["ent_ally_eric_001"].action_economy["bonus_action_used"])
            encounter_repo.close()
            event_repo.close()

    def test_execute_nick_light_bonus_still_works_when_bonus_action_already_used(self) -> None:
        """测试 Nick 允许的轻型额外攻击在附赠动作已用时仍可执行。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            knowledge_path = Path(tmp_dir) / "weapon_definitions.json"
            knowledge_path.write_text(
                json.dumps(
                    {
                        "weapon_definitions": {
                            "dagger": {
                                "id": "dagger",
                                "name": "匕首",
                                "category": "simple",
                                "kind": "melee",
                                "base_damage": {"formula": "1d4", "damage_type": "piercing"},
                                "properties": ["finesse", "light", "thrown"],
                                "mastery": "nick",
                                "range": {"normal": 5, "long": 5},
                                "hands": {"mode": "one_handed"},
                                "thrown_range": {"normal": 20, "long": 60}
                            },
                            "shortsword": {
                                "id": "shortsword",
                                "name": "短剑",
                                "category": "martial",
                                "kind": "melee",
                                "base_damage": {"formula": "1d6", "damage_type": "piercing"},
                                "properties": ["finesse", "light"],
                                "mastery": "vex",
                                "range": {"normal": 5, "long": 5},
                                "hands": {"mode": "one_handed"}
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_actor()
            actor.weapons = [
                {"weapon_id": "dagger", "slot": "main_hand", "is_proficient": True},
                {"weapon_id": "shortsword", "slot": "off_hand", "is_proficient": True},
            ]
            actor.action_economy = {"action_used": False, "bonus_action_used": True, "reaction_used": False}
            encounter_repo.save(build_encounter(actor=actor))

            append_event = AppendEvent(event_repo)
            weapon_repo = WeaponDefinitionRepository(knowledge_path)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo, weapon_definition_repository=weapon_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            first = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="dagger",
                final_total=15,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:dagger:part_0", "rolls": [3]}],
            )

            second = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="shortsword",
                attack_mode="light_bonus",
                final_total=15,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:shortsword:part_0", "rolls": [4]}],
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertIsNotNone(updated)
            self.assertTrue(first["resolution"]["hit"])
            self.assertTrue(second["resolution"]["hit"])
            self.assertTrue(updated.entities["ent_ally_eric_001"].action_economy["bonus_action_used"])
            encounter_repo.close()
            event_repo.close()

    def test_execute_allows_light_bonus_attack_and_omits_positive_damage_modifier(self) -> None:
        """测试轻型额外攻击会消耗附赠动作，且第二击不加正属性伤害。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            knowledge_path = Path(tmp_dir) / "weapon_definitions.json"
            knowledge_path.write_text(
                json.dumps(
                    {
                        "weapon_definitions": {
                            "shortsword": {
                                "id": "shortsword",
                                "name": "短剑",
                                "category": "martial",
                                "kind": "melee",
                                "base_damage": {"formula": "1d6", "damage_type": "piercing"},
                                "properties": ["finesse", "light"],
                                "mastery": "vex",
                                "range": {"normal": 5, "long": 5},
                                "hands": {"mode": "one_handed"}
                            },
                            "dagger": {
                                "id": "dagger",
                                "name": "匕首",
                                "category": "simple",
                                "kind": "melee",
                                "base_damage": {"formula": "1d4", "damage_type": "piercing"},
                                "properties": ["finesse", "light", "thrown"],
                                "mastery": "nick",
                                "range": {"normal": 5, "long": 5},
                                "hands": {"mode": "one_handed"},
                                "thrown_range": {"normal": 20, "long": 60}
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_actor()
            actor.weapons = [
                {"weapon_id": "shortsword", "slot": "main_hand", "is_proficient": True},
                {"weapon_id": "dagger", "slot": "off_hand", "is_proficient": True},
            ]
            actor.action_economy = {"action_used": False, "bonus_action_used": False, "reaction_used": False}
            encounter_repo.save(build_encounter(actor=actor))

            append_event = AppendEvent(event_repo)
            weapon_repo = WeaponDefinitionRepository(knowledge_path)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo, weapon_definition_repository=weapon_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            first = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="shortsword",
                final_total=15,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:shortsword:part_0", "rolls": [4]}],
            )

            second = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="dagger",
                attack_mode="light_bonus",
                final_total=15,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:dagger:part_0", "rolls": [3]}],
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertIsNotNone(updated)
            self.assertTrue(first["resolution"]["hit"])
            self.assertTrue(second["resolution"]["hit"])
            self.assertEqual(second["resolution"]["damage_resolution"]["parts"][0]["resolved_formula"], "1d4")
            self.assertTrue(updated.entities["ent_ally_eric_001"].action_economy["action_used"])
            self.assertTrue(updated.entities["ent_ally_eric_001"].action_economy["bonus_action_used"])
            encounter_repo.close()
            event_repo.close()

    def test_execute_returns_structured_invalid_attack_when_target_out_of_range(self) -> None:
        """测试非法攻击会返回结构化 invalid_attack，而不是直接抛错。"""
        with make_repositories() as (encounter_repo, event_repo):
            target = build_target()
            target.position = {"x": 6, "y": 2}
            encounter_repo.save(build_encounter(target=target))

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [4]}],
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertIsNotNone(updated)
            self.assertEqual(result["status"], "invalid_attack")
            self.assertEqual(result["reason"], "target_out_of_range")
            self.assertEqual(result["message_for_llm"], "当前目标不在攻击范围内，请重新选择目标或调整位置。")
            self.assertIn("encounter_state", result)
            self.assertFalse(updated.entities["ent_ally_eric_001"].action_economy.get("action_used", False))

    def test_execute_returns_structured_invalid_attack_when_line_of_sight_is_blocked(self) -> None:
        """测试视线阻挡也会返回结构化 invalid_attack。"""
        with make_repositories() as (encounter_repo, event_repo):
            actor = build_actor()
            actor.weapons.append(
                {
                    "weapon_id": "shortbow",
                    "name": "Shortbow",
                    "damage": [{"formula": "1d6+3", "type": "piercing"}],
                    "properties": [],
                    "range": {"normal": 80, "long": 320},
                }
            )
            target = build_target()
            target.position = {"x": 5, "y": 2}
            encounter = build_encounter(actor=actor, target=target)
            encounter.map.terrain = [{"terrain_id": "wall_01", "type": "wall", "x": 4, "y": 2, "blocks_los": True}]
            encounter_repo.save(encounter)

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="shortbow",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:shortbow:part_0", "rolls": [4]}],
            )

            self.assertEqual(result["status"], "invalid_attack")
            self.assertEqual(result["reason"], "blocked_by_line_of_sight")
            self.assertEqual(result["message_for_llm"], "当前无法攻击该目标，因为视线被阻挡。请重新选择目标或位置。")

    def test_execute_returns_structured_invalid_attack_when_two_handed_weapon_has_occupied_hand(self) -> None:
        """测试双手武器攻击时若手被占用，会返回结构化 invalid_attack。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            knowledge_path = Path(tmp_dir) / "weapon_definitions.json"
            knowledge_path.write_text(
                json.dumps(
                    {
                        "weapon_definitions": {
                            "longbow": {
                                "id": "longbow",
                                "name": "长弓",
                                "category": "martial",
                                "kind": "ranged",
                                "base_damage": {"formula": "1d8", "damage_type": "piercing"},
                                "properties": ["ammunition", "heavy", "two_handed"],
                                "mastery": "slow",
                                "range": {"normal": 150, "long": 600},
                                "hands": {"mode": "two_handed"},
                                "ammunition": {"type": "arrow"}
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_actor()
            actor.weapons = [{"weapon_id": "longbow", "is_proficient": True}]
            actor.combat_flags = {"occupied_hand_slots": ["off_hand"]}
            encounter_repo.save(build_encounter(actor=actor))

            append_event = AppendEvent(event_repo)
            weapon_repo = WeaponDefinitionRepository(knowledge_path)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo, weapon_definition_repository=weapon_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="longbow",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:longbow:part_0", "rolls": [4]}],
            )

            self.assertEqual(result["status"], "invalid_attack")
            self.assertEqual(result["reason"], "two_handed_requires_two_free_hands")
            self.assertEqual(result["message_for_llm"], "当前无法用双手持用这把武器，因为至少一只手正被其他物品占用。")
            encounter_repo.close()
            event_repo.close()

    def test_execute_resolves_structured_damage_from_weapon_definition(self) -> None:
        """测试完整攻击可用武器知识库模板生成伤害段。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            knowledge_path = Path(tmp_dir) / "weapon_definitions.json"
            knowledge_path.write_text(
                json.dumps(
                    {
                        "weapon_definitions": {
                            "rapier": {
                                "id": "rapier",
                                "name": "刺剑",
                                "category": "martial",
                                "kind": "melee",
                                "base_damage": {"formula": "1d8", "damage_type": "piercing"},
                                "properties": ["finesse"],
                                "mastery": "vex",
                                "range": {"normal": 5, "long": 5},
                                "hands": {"mode": "one_handed"},
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_actor()
            actor.weapons = [{"weapon_id": "rapier", "is_proficient": True}]
            encounter_repo.save(build_encounter(actor=actor))

            append_event = AppendEvent(event_repo)
            weapon_repo = WeaponDefinitionRepository(knowledge_path)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo, weapon_definition_repository=weapon_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [4]}],
            )

            damage_resolution = result["resolution"]["damage_resolution"]
            self.assertEqual(damage_resolution["parts"][0]["source"], "weapon:rapier:part_0")
            self.assertEqual(damage_resolution["parts"][0]["damage_type"], "piercing")
            self.assertEqual(damage_resolution["parts"][0]["resolved_formula"], "1d8+3")
            encounter_repo.close()
            event_repo.close()

    def test_execute_uses_versatile_damage_when_grip_mode_is_two_handed(self) -> None:
        """测试多用武器双手持握时会改用 versatile_damage。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            knowledge_path = Path(tmp_dir) / "weapon_definitions.json"
            knowledge_path.write_text(
                json.dumps(
                    {
                        "weapon_definitions": {
                            "longsword": {
                                "id": "longsword",
                                "name": "长剑",
                                "category": "martial",
                                "kind": "melee",
                                "base_damage": {"formula": "1d8", "damage_type": "slashing"},
                                "versatile_damage": {"formula": "1d10", "damage_type": "slashing"},
                                "properties": ["versatile"],
                                "mastery": "sap",
                                "range": {"normal": 5, "long": 5},
                                "hands": {"mode": "versatile"}
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_actor()
            actor.weapons = [{"weapon_id": "longsword", "is_proficient": True}]
            encounter_repo.save(build_encounter(actor=actor))

            append_event = AppendEvent(event_repo)
            weapon_repo = WeaponDefinitionRepository(knowledge_path)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo, weapon_definition_repository=weapon_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="longsword",
                grip_mode="two_handed",
                final_total=15,
                dice_rolls={"base_rolls": [12], "modifier": 3},
                damage_rolls=[{"source": "weapon:longsword:part_0", "rolls": [6]}],
            )

            damage_resolution = result["resolution"]["damage_resolution"]
            self.assertEqual(damage_resolution["parts"][0]["resolved_formula"], "1d10+1")
            encounter_repo.close()
            event_repo.close()

    def test_execute_applies_hex_bonus_damage_from_target_turn_effect(self) -> None:
        """测试命中被 Hex 标记的目标时会追加 1d6 暗蚀附伤。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter = build_encounter()
            encounter.entities["ent_enemy_goblin_001"].turn_effects = [
                {
                    "effect_id": "effect_hex_001",
                    "name": "Hex Curse",
                    "source_entity_id": "ent_ally_eric_001",
                    "source_ref": "hex",
                    "trigger": "end_of_turn",
                    "save": None,
                    "on_trigger": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                    "on_save_success": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                    "on_save_failure": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                    "remove_after_trigger": False,
                    "attack_bonus_damage_parts": [
                        {
                            "source": "spell:hex:bonus_damage",
                            "formula": "1d6",
                            "damage_type": "necrotic"
                        }
                    ]
                }
            ]
            encounter_repo.save(encounter)

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[
                    {"source": "weapon:rapier:part_0", "rolls": [4]},
                    {"source": "effect:effect_hex_001:part_0", "rolls": [5]},
                ],
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertIsNotNone(updated)

            damage_resolution = result["resolution"]["damage_resolution"]
            self.assertEqual(len(damage_resolution["parts"]), 2)
            self.assertEqual(damage_resolution["parts"][1]["damage_type"], "necrotic")
            self.assertEqual(damage_resolution["total_damage"], 12)
            self.assertNotIn("ent_enemy_goblin_001", updated.entities)
            self.assertEqual(getattr(updated.map, "remains", [])[0]["position"], {"x": 3, "y": 2})

    def test_execute_can_consume_reaction_without_action_for_opportunity_attack(self) -> None:
        """测试借机攻击可由非当前行动者发起，且只消耗 reaction。"""
        with make_repositories() as (encounter_repo, event_repo):
            actor = build_actor()
            actor.action_economy = {"action_used": False, "reaction_used": False}
            target = build_target()
            encounter = build_encounter(actor=actor, target=target)
            encounter.current_entity_id = target.entity_id
            encounter.turn_order = [target.entity_id, actor.entity_id]
            encounter_repo.save(encounter)

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                actor_id=actor.entity_id,
                target_id=target.entity_id,
                weapon_id="rapier",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [4]}],
                consume_action=False,
                consume_reaction=True,
                allow_out_of_turn_actor=True,
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertIsNotNone(updated)
            self.assertFalse(updated.entities[actor.entity_id].action_economy.get("action_used", False))
            self.assertTrue(updated.entities[actor.entity_id].action_economy["reaction_used"])
            self.assertTrue(result["resolution"]["hit"])

    def test_execute_runs_full_flow_and_auto_applies_damage(self) -> None:
        """测试新主路径会串起请求、命中判定、事件写入和自动扣血."""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [4]}],
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertIsNotNone(updated)

            self.assertEqual(result["request"]["context"]["distance_to_target_feet"], 5)
            self.assertEqual(result["roll_result"]["request_id"], result["request"]["request_id"])
            self.assertTrue(result["resolution"]["hit"])
            self.assertEqual(result["resolution"]["attack_name"], "Rapier")
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["current"], 2)
            event_types = [event.event_type for event in event_repo.list_by_encounter("enc_execute_attack_test")]
            self.assertIn("attack_resolved", event_types)
            self.assertIn("damage_applied", event_types)

    def test_execute_marks_action_used_for_actor(self) -> None:
        """攻击完成后应把当前实体的 action_used 记为 True."""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [4]}],
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertIsNotNone(updated)

            self.assertTrue(updated.entities["ent_ally_eric_001"].action_economy.get("action_used"))

    def test_execute_attack_consumes_one_attack_from_attack_action_sequence(self) -> None:
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(
                build_fighter_encounter_for_extra_attack(
                    actor=build_fighter_actor_for_extra_attack(
                        attack_action_attacks_used=0,
                        extra_attack_count=2,
                    )
                )
            )

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_fighter_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=17,
                dice_rolls={"base_rolls": [10], "modifier": 7},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [3]}],
            )

            updated = encounter_repo.get("enc_fighter_test")
            self.assertIsNotNone(updated)
            fighter = updated.entities["ent_fighter_001"].class_features["fighter"]
            self.assertTrue(result["resolution"]["hit"])
            self.assertEqual(fighter["turn_counters"]["attack_action_attacks_used"], 1)
            self.assertIs(updated.entities["ent_fighter_001"].action_economy["action_used"], False)

    def test_execute_attack_marks_action_used_after_last_extra_attack_is_spent(self) -> None:
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(
                build_fighter_encounter_for_extra_attack(
                    actor=build_fighter_actor_for_extra_attack(
                        attack_action_attacks_used=1,
                        action_used=True,
                        extra_attack_count=2,
                    )
                )
            )

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_fighter_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=17,
                dice_rolls={"base_rolls": [10], "modifier": 7},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [3]}],
            )

            updated = encounter_repo.get("enc_fighter_test")
            self.assertIsNotNone(updated)
            fighter = updated.entities["ent_fighter_001"].class_features["fighter"]
            self.assertTrue(result["resolution"]["hit"])
            self.assertEqual(fighter["turn_counters"]["attack_action_attacks_used"], 2)
            self.assertIs(updated.entities["ent_fighter_001"].action_economy["action_used"], True)

    def test_execute_attack_allows_sequence_when_action_used_but_no_attack_spent_yet(self) -> None:
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(
                build_fighter_encounter_for_extra_attack(
                    actor=build_fighter_actor_for_extra_attack(
                        attack_action_attacks_used=0,
                        action_used=True,
                        extra_attack_count=2,
                    )
                )
            )

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_fighter_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=17,
                dice_rolls={"base_rolls": [10], "modifier": 7},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [3]}],
            )

            updated = encounter_repo.get("enc_fighter_test")
            self.assertIsNotNone(updated)
            fighter = updated.entities["ent_fighter_001"].class_features["fighter"]
            self.assertTrue(result["resolution"]["hit"])
            self.assertEqual(fighter["turn_counters"]["attack_action_attacks_used"], 1)
            self.assertIs(updated.entities["ent_fighter_001"].action_economy["action_used"], False)

    def test_missed_attack_adds_studied_attacks_mark_for_target(self) -> None:
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(
                build_fighter_encounter_for_extra_attack(
                    actor=build_fighter_actor_for_extra_attack(fighter_level=13),
                )
            )

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_fighter_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=8,
                dice_rolls={"base_rolls": [1], "modifier": 7},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [3]}],
            )

            updated = encounter_repo.get("enc_fighter_test")
            self.assertIsNotNone(updated)
            fighter = updated.entities["ent_fighter_001"].class_features["fighter"]
            marks = fighter["studied_attacks"]
            self.assertFalse(result["resolution"]["hit"])
            self.assertEqual(len(marks), 1)
            self.assertEqual(marks[0]["target_entity_id"], "ent_enemy_goblin_001")
            self.assertFalse(marks[0]["consumed"])

    def test_next_attack_against_marked_target_gets_advantage_and_consumes_mark(self) -> None:
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(
                build_fighter_encounter_for_extra_attack(
                    actor=build_fighter_actor_for_extra_attack(
                        fighter_level=13,
                        studied_attacks=[
                            {
                                "target_entity_id": "ent_enemy_goblin_001",
                                "expires_at": "end_of_next_turn",
                                "consumed": False,
                            }
                        ],
                    ),
                )
            )

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_fighter_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=17,
                dice_rolls={"base_rolls": [10, 4], "chosen_roll": 10, "modifier": 7, "vantage": "advantage"},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [3]}],
            )

            updated = encounter_repo.get("enc_fighter_test")
            self.assertIsNotNone(updated)
            fighter = updated.entities["ent_fighter_001"].class_features["fighter"]
            marks = fighter["studied_attacks"]
            self.assertEqual(result["request"]["context"]["vantage"], "advantage")
            self.assertIn("studied_attacks", result["request"]["context"]["vantage_sources"]["advantage"])
            self.assertTrue(result["resolution"]["hit"])
            self.assertEqual(len(marks), 1)
            self.assertTrue(marks[0]["consumed"])

    def test_resolve_extra_attack_count_takes_highest_source_only_in_attack_flow(self) -> None:
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(
                build_fighter_encounter_for_extra_attack(
                    actor=build_fighter_actor_for_extra_attack(
                        attack_action_attacks_used=0,
                        extra_attack_count=1,
                        extra_attack_sources=[
                            {"source": "fighter", "attack_count": 2},
                            {"source": "multiclass_other_feature", "attack_count": 1},
                        ],
                    )
                )
            )

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_fighter_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=17,
                dice_rolls={"base_rolls": [10], "modifier": 7},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [3]}],
            )

            updated = encounter_repo.get("enc_fighter_test")
            self.assertIsNotNone(updated)
            fighter = updated.entities["ent_fighter_001"].class_features["fighter"]
            self.assertTrue(result["resolution"]["hit"])
            self.assertEqual(fighter["turn_counters"]["attack_action_attacks_used"], 1)
            self.assertIs(updated.entities["ent_fighter_001"].action_economy["action_used"], False)

    def test_tactical_master_allows_push_override_on_valid_weapon_attack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            knowledge_path = Path(tmp_dir) / "weapon_definitions.json"
            knowledge_path.write_text(
                json.dumps(
                    {
                        "weapon_definitions": {
                            "longsword": {
                                "id": "longsword",
                                "name": "长剑",
                                "category": "martial",
                                "kind": "melee",
                                "base_damage": {"formula": "1d8", "damage_type": "slashing"},
                                "properties": ["versatile"],
                                "mastery": "sap",
                                "range": {"normal": 5, "long": 5},
                                "hands": {"mode": "one_handed"},
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_fighter_actor_for_extra_attack(fighter_level=9, tactical_master_enabled=True)
            actor.ability_mods["str"] = 4
            actor.ability_scores = {"str": 18, "dex": 10, "con": 14, "int": 10, "wis": 10, "cha": 10}
            actor.weapons = [{"weapon_id": "longsword", "is_proficient": True}]
            target = build_target()
            encounter_repo.save(build_fighter_encounter_for_extra_attack(actor=actor, target=target))

            append_event = AppendEvent(event_repo)
            weapon_repo = WeaponDefinitionRepository(knowledge_path)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo, weapon_definition_repository=weapon_repo),
                AttackRollResult(encounter_repo, append_event, UpdateHp(encounter_repo, append_event)),
            )

            result = service.execute(
                encounter_id="enc_fighter_test",
                target_id=target.entity_id,
                weapon_id="longsword",
                final_total=18,
                dice_rolls={"base_rolls": [11], "modifier": 7},
                damage_rolls=[{"source": "weapon:longsword:part_0", "rolls": [4]}],
                mastery_override="push",
            )

            updated = encounter_repo.get("enc_fighter_test")
            self.assertIsNotNone(updated)
            self.assertTrue(result["resolution"]["hit"])
            self.assertEqual(result["request"]["context"]["weapon_mastery"], "push")
            push = result["resolution"]["weapon_mastery_updates"]["push"]
            self.assertEqual(push["status"], "resolved")
            self.assertEqual(updated.entities[target.entity_id].position, {"x": 5, "y": 2})
            encounter_repo.close()
            event_repo.close()

    def test_tactical_master_rejects_override_when_feature_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            knowledge_path = Path(tmp_dir) / "weapon_definitions.json"
            knowledge_path.write_text(
                json.dumps(
                    {
                        "weapon_definitions": {
                            "longsword": {
                                "id": "longsword",
                                "name": "长剑",
                                "category": "martial",
                                "kind": "melee",
                                "base_damage": {"formula": "1d8", "damage_type": "slashing"},
                                "properties": ["versatile"],
                                "mastery": "sap",
                                "range": {"normal": 5, "long": 5},
                                "hands": {"mode": "one_handed"},
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_fighter_actor_for_extra_attack(fighter_level=9, tactical_master_enabled=False)
            actor.weapons = [{"weapon_id": "longsword", "is_proficient": True}]
            target = build_target()
            encounter_repo.save(build_fighter_encounter_for_extra_attack(actor=actor, target=target))

            append_event = AppendEvent(event_repo)
            weapon_repo = WeaponDefinitionRepository(knowledge_path)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo, weapon_definition_repository=weapon_repo),
                AttackRollResult(encounter_repo, append_event, UpdateHp(encounter_repo, append_event)),
            )

            with self.assertRaisesRegex(ValueError, "invalid_mastery_override"):
                service.execute(
                    encounter_id="enc_fighter_test",
                    target_id=target.entity_id,
                    weapon_id="longsword",
                    final_total=18,
                    dice_rolls={"base_rolls": [11], "modifier": 7},
                    damage_rolls=[{"source": "weapon:longsword:part_0", "rolls": [4]}],
                    mastery_override="push",
                )

            encounter_repo.close()
            event_repo.close()

    def test_execute_marks_action_used_even_when_attack_misses_with_legacy_damage_inputs(self) -> None:
        """测试旧 hp_change 兼容路径在未命中时也会标记 action_used."""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=8,
                dice_rolls={"base_rolls": [3], "modifier": 5},
                hp_change=4,
                damage_reason="Missed attack should not deal damage",
                damage_type="piercing",
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertIsNotNone(updated)

            self.assertFalse(result["resolution"]["hit"])
            self.assertTrue(updated.entities["ent_ally_eric_001"].action_economy.get("action_used"))

    def test_execute_keeps_damage_unapplied_when_attack_misses_with_legacy_damage_inputs(self) -> None:
        """测试旧 hp_change 兼容路径在未命中时不会错误扣血."""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=8,
                dice_rolls={"base_rolls": [3], "modifier": 5},
                hp_change=4,
                damage_reason="Missed attack should not deal damage",
                damage_type="piercing",
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertIsNotNone(updated)

            self.assertFalse(result["resolution"]["hit"])
            self.assertNotIn("hp_update", result["resolution"])
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["current"], 9)
            event_types = [event.event_type for event in event_repo.list_by_encounter("enc_execute_attack_test")]
            self.assertEqual(event_types.count("attack_resolved"), 1)
            self.assertNotIn("damage_applied", event_types)

    def test_execute_passes_advantage_and_description_into_request(self) -> None:
        """测试完整攻击入口会把优势和描述继续传给攻击请求层."""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                vantage="advantage",
                description="Eric lunges with the rapier",
            )

            self.assertEqual(result["request"]["context"]["vantage"], "advantage")
            self.assertEqual(result["request"]["reason"], "Eric lunges with the rapier")
            self.assertTrue(result["resolution"]["hit"])

    def test_execute_can_include_latest_encounter_state(self) -> None:
        """测试完整攻击入口只在最外层返回最新前端状态."""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [4]}],
                include_encounter_state=True,
            )

            self.assertIn("encounter_state", result)
            self.assertEqual(result["encounter_state"]["encounter_id"], "enc_execute_attack_test")
            self.assertEqual(
                result["encounter_state"]["turn_order"][1]["id"],
                "ent_enemy_goblin_001",
            )
            self.assertTrue(
                result["encounter_state"]["current_turn_entity"]["actions"]["action_used"]
            )

    def test_execute_resolves_weapon_damage_and_returns_breakdown(self) -> None:
        """测试命中伤害会生成 damage_resolution 并自动扣血."""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [4]}],
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertIsNotNone(updated)

            self.assertTrue(result["resolution"]["hit"])
            damage_resolution = result["resolution"]["damage_resolution"]
            self.assertEqual(damage_resolution["total_damage"], 7)
            self.assertEqual(damage_resolution["parts"][0]["source"], "weapon:rapier:part_0")
            self.assertEqual(damage_resolution["parts"][0]["adjusted_total"], 7)
            self.assertEqual(result["resolution"]["hp_update"]["adjusted_hp_change"], 7)
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["current"], 2)

    def test_execute_resolves_multi_part_damage_on_critical_hit(self) -> None:
        """测试暴击会翻倍多段伤害并返回 resolved_formula."""
        with make_repositories() as (encounter_repo, event_repo):
            actor = build_actor_with_infernal_rapier()
            encounter_repo.save(build_encounter(actor=actor))

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="infernal_rapier",
                final_total=25,
                dice_rolls={"base_rolls": [20], "modifier": 5},
                damage_rolls=[
                    {"source": "weapon:infernal_rapier:part_0", "rolls": [6, 2]},
                    {"source": "weapon:infernal_rapier:part_1", "rolls": [5, 1]},
                ],
            )

            self.assertTrue(result["resolution"]["is_critical_hit"])
            parts = result["resolution"]["damage_resolution"]["parts"]
            self.assertEqual(parts[0]["resolved_formula"], "2d8+3")
            self.assertEqual(parts[1]["resolved_formula"], "2d8")
            self.assertEqual(result["resolution"]["damage_resolution"]["total_damage"], 17)

    def test_execute_melee_hit_on_paralyzed_target_becomes_critical(self) -> None:
        """测试近战攻击麻痹目标会自动暴击并翻倍伤害."""
        with make_repositories() as (encounter_repo, event_repo):
            actor = build_actor()
            target = build_target()
            target.conditions = ["paralyzed"]
            encounter_repo.save(build_encounter(actor=actor, target=target))

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=15,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [4, 5]}],
            )

            self.assertTrue(result["resolution"]["hit"])
            self.assertTrue(result["resolution"]["is_critical_hit"])
            damage_resolution = result["resolution"]["damage_resolution"]
            self.assertTrue(damage_resolution["is_critical_hit"])
            self.assertEqual(damage_resolution["parts"][0]["resolved_formula"], "2d8+3")
            self.assertEqual(damage_resolution["total_damage"], 12)
            self.assertEqual(result["resolution"]["hp_update"]["adjusted_hp_change"], 12)
            self.assertTrue(result["resolution"]["hp_update"]["from_critical_hit"])

    def test_execute_applies_target_resistance_inside_damage_resolution(self) -> None:
        """测试抗性会在 damage_resolution 里按段计算并把 damage_type 清空."""
        with make_repositories() as (encounter_repo, event_repo):
            actor = build_actor_with_infernal_rapier()
            target = build_target()
            target.resistances = ["fire"]
            encounter_repo.save(build_encounter(actor=actor, target=target))

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="infernal_rapier",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[
                    {"source": "weapon:infernal_rapier:part_0", "rolls": [4]},
                    {"source": "weapon:infernal_rapier:part_1", "rolls": [6]},
                ],
            )

            fire_part = result["resolution"]["damage_resolution"]["parts"][1]
            self.assertEqual(fire_part["adjustment_rule"], "resistance")
            self.assertEqual(fire_part["adjusted_total"], 3)
            self.assertEqual(result["resolution"]["damage_resolution"]["total_damage"], 10)
            self.assertIsNone(result["resolution"]["hp_update"]["damage_type"])

    def test_execute_rejects_missing_damage_roll_source(self) -> None:
        """测试缺少 damage_rolls 的 source 会报错."""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            with self.assertRaisesRegex(ValueError, "missing_damage_roll_sources: weapon:rapier:part_0"):
                service.execute(
                    encounter_id="enc_execute_attack_test",
                    target_id="ent_enemy_goblin_001",
                    weapon_id="rapier",
                    final_total=17,
                    dice_rolls={"base_rolls": [12], "modifier": 5},
                    damage_rolls=[],
                )

    def test_execute_rejects_unknown_damage_roll_source(self) -> None:
        """测试未知 damage_rolls source 会报错."""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            with self.assertRaisesRegex(ValueError, "unknown_damage_roll_sources: weapon:rapier:part_9"):
                service.execute(
                    encounter_id="enc_execute_attack_test",
                    target_id="ent_enemy_goblin_001",
                    weapon_id="rapier",
                    final_total=17,
                    dice_rolls={"base_rolls": [12], "modifier": 5},
                    damage_rolls=[
                        {"source": "weapon:rapier:part_0", "rolls": [4]},
                        {"source": "weapon:rapier:part_9", "rolls": [5]},
                    ],
                )

    def test_execute_rejects_duplicate_damage_roll_source(self) -> None:
        """测试重复 damage_rolls source 会报错."""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            with self.assertRaisesRegex(ValueError, "duplicate_damage_roll_source: weapon:rapier:part_0"):
                service.execute(
                    encounter_id="enc_execute_attack_test",
                    target_id="ent_enemy_goblin_001",
                    weapon_id="rapier",
                    final_total=17,
                    dice_rolls={"base_rolls": [12], "modifier": 5},
                    damage_rolls=[
                        {"source": "weapon:rapier:part_0", "rolls": [4]},
                        {"source": "weapon:rapier:part_0", "rolls": [5]},
                    ],
                )

    def test_execute_applies_sneak_attack_damage_once_per_turn(self) -> None:
        with make_repositories() as (encounter_repo, event_repo):
            actor = build_actor()
            target = build_target()
            target.hp = {"current": 50, "max": 50, "temp": 0}
            actor.class_features = {
                "rogue": {
                    "level": 5,
                    "sneak_attack": {"damage_dice": "3d6", "used_this_turn": False},
                }
            }
            encounter_repo.save(build_encounter(actor=actor, target=target))

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            first = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                consume_action=False,
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[
                    {"source": "weapon:rapier:part_0", "rolls": [5]},
                    {"source": "rogue_sneak_attack", "rolls": [3, 4, 5]},
                ],
                class_feature_options={"sneak_attack": True},
            )

            second = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                consume_action=False,
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [5]}],
                class_feature_options={"sneak_attack": True},
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertIsNotNone(updated)
            self.assertEqual(first["resolution"]["damage_resolution"]["total_damage"], 20)
            self.assertEqual(len(first["resolution"]["damage_resolution"]["parts"]), 2)
            self.assertEqual(first["resolution"]["damage_resolution"]["parts"][1]["source"], "rogue_sneak_attack")
            self.assertTrue(
                updated.entities["ent_ally_eric_001"].class_features["rogue"]["sneak_attack"]["used_this_turn"]
            )
            self.assertEqual(second["resolution"]["damage_resolution"]["total_damage"], 8)
            self.assertEqual(len(second["resolution"]["damage_resolution"]["parts"]), 1)

    def test_execute_martial_arts_bonus_consumes_bonus_action(self) -> None:
        with make_repositories() as (encounter_repo, event_repo):
            actor = build_actor()
            actor.action_economy = {"action_used": False, "bonus_action_used": False, "reaction_used": False}
            actor.class_features = {
                "monk": {
                    "level": 5,
                    "focus_points": {"max": 5, "remaining": 5},
                    "martial_arts_die": "1d8",
                }
            }
            target = build_target()
            target.hp = {"current": 30, "max": 30, "temp": 0}
            encounter_repo.save(build_encounter(actor=actor, target=target))

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id=target.entity_id,
                weapon_id="unarmed_strike",
                attack_mode="martial_arts_bonus",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:unarmed_strike:part_0", "rolls": [6]}],
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertIsNotNone(updated)
            self.assertTrue(result["resolution"]["hit"])
            self.assertFalse(updated.entities[actor.entity_id].action_economy["action_used"])
            self.assertTrue(updated.entities[actor.entity_id].action_economy["bonus_action_used"])

    def test_execute_flurry_of_blows_spends_focus_and_bonus_action(self) -> None:
        with make_repositories() as (encounter_repo, event_repo):
            actor = build_actor()
            actor.action_economy = {"action_used": False, "bonus_action_used": False, "reaction_used": False}
            actor.class_features = {
                "monk": {
                    "level": 5,
                    "focus_points": {"max": 5, "remaining": 5},
                    "martial_arts_die": "1d8",
                }
            }
            target = build_target()
            target.hp = {"current": 30, "max": 30, "temp": 0}
            encounter_repo.save(build_encounter(actor=actor, target=target))

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id=target.entity_id,
                weapon_id="unarmed_strike",
                attack_mode="flurry_of_blows",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:unarmed_strike:part_0", "rolls": [6]}],
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertIsNotNone(updated)
            self.assertTrue(result["resolution"]["hit"])
            self.assertFalse(updated.entities[actor.entity_id].action_economy["action_used"])
            self.assertTrue(updated.entities[actor.entity_id].action_economy["bonus_action_used"])
            self.assertEqual(updated.entities[actor.entity_id].class_features["monk"]["focus_points"]["remaining"], 4)

    def test_execute_stunning_strike_failed_save_applies_stunned_and_consumes_focus(self) -> None:
        with make_repositories() as (encounter_repo, event_repo):
            actor = build_actor()
            actor.class_features = {
                "monk": {
                    "level": 5,
                    "focus_points": {"max": 5, "remaining": 5},
                    "martial_arts_die": "1d8",
                    "stunning_strike": {"uses_this_turn": 0, "max_per_turn": 1},
                }
            }
            target = build_target()
            target.hp = {"current": 30, "max": 30, "temp": 0}
            encounter_repo.save(build_encounter(actor=actor, target=target))

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id=target.entity_id,
                weapon_id="unarmed_strike",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:unarmed_strike:part_0", "rolls": [6]}],
                class_feature_options={"stunning_strike": {"enabled": True, "save_roll": 4}},
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertIsNotNone(updated)
            self.assertIn("stunned", updated.entities[target.entity_id].conditions)
            self.assertEqual(updated.entities[actor.entity_id].class_features["monk"]["focus_points"]["remaining"], 4)
            self.assertEqual(updated.entities[actor.entity_id].class_features["monk"]["stunning_strike"]["uses_this_turn"], 1)
            self.assertEqual(result["resolution"]["stunning_strike"]["status"], "failed_save")
            self.assertFalse(result["resolution"]["stunning_strike"]["save"]["success"])

    def test_execute_stunning_strike_success_applies_turn_effect_marker_and_consumes_focus(self) -> None:
        with make_repositories() as (encounter_repo, event_repo):
            actor = build_actor()
            actor.class_features = {
                "monk": {
                    "level": 5,
                    "focus_points": {"max": 5, "remaining": 5},
                    "martial_arts_die": "1d8",
                    "stunning_strike": {"uses_this_turn": 0, "max_per_turn": 1},
                }
            }
            target = build_target()
            target.hp = {"current": 30, "max": 30, "temp": 0}
            encounter_repo.save(build_encounter(actor=actor, target=target))

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id=target.entity_id,
                weapon_id="unarmed_strike",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:unarmed_strike:part_0", "rolls": [6]}],
                class_feature_options={"stunning_strike": {"enabled": True, "save_roll": 18}},
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertIsNotNone(updated)
            self.assertNotIn("stunned", updated.entities[target.entity_id].conditions)
            self.assertEqual(updated.entities[actor.entity_id].class_features["monk"]["focus_points"]["remaining"], 4)
            self.assertEqual(result["resolution"]["stunning_strike"]["status"], "successful_save")
            self.assertTrue(result["resolution"]["stunning_strike"]["save"]["success"])
            success_effects = [
                effect
                for effect in updated.entities[target.entity_id].turn_effects
                if effect.get("effect_type") == "monk_stunning_strike_success"
            ]
            self.assertEqual(len(success_effects), 1)

    def test_stunning_strike_advantage_consumes_turn_effect(self) -> None:
        with make_repositories() as (encounter_repo, event_repo):
            actor = build_actor()
            target = build_target()
            target.hp = {"current": 30, "max": 30, "temp": 0}
            target.turn_effects.append(
                {
                    "effect_id": "effect_stunning_strike_test",
                    "effect_type": "monk_stunning_strike_success",
                    "source_entity_id": actor.entity_id,
                    "target_entity_id": target.entity_id,
                    "next_attack_advantage_once": True,
                    "trigger": "start_of_turn",
                    "remove_after_trigger": True,
                }
            )
            encounter_repo.save(build_encounter(actor=actor, target=target))

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            service.execute(
                encounter_id="enc_execute_attack_test",
                target_id=target.entity_id,
                weapon_id="rapier",
                final_total=20,
                dice_rolls={"base_rolls": [15], "modifier": 5},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [6]}],
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertIsNotNone(updated)
            self.assertFalse(
                any(
                    effect.get("effect_type") == "monk_stunning_strike_success"
                    for effect in updated.entities[target.entity_id].turn_effects
                )
            )

    def test_execute_stunning_strike_rejects_second_use_in_same_turn(self) -> None:
        with make_repositories() as (encounter_repo, event_repo):
            actor = build_actor()
            actor.class_features = {
                "monk": {
                    "level": 5,
                    "focus_points": {"max": 5, "remaining": 5},
                    "martial_arts_die": "1d8",
                    "stunning_strike": {"uses_this_turn": 0, "max_per_turn": 1},
                }
            }
            target = build_target()
            target.hp = {"current": 60, "max": 60, "temp": 0}
            encounter_repo.save(build_encounter(actor=actor, target=target))

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            service.execute(
                encounter_id="enc_execute_attack_test",
                target_id=target.entity_id,
                weapon_id="unarmed_strike",
                consume_action=False,
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:unarmed_strike:part_0", "rolls": [6]}],
                class_feature_options={"stunning_strike": {"enabled": True, "save_roll": 18}},
            )
            with self.assertRaisesRegex(ValueError, "stunning_strike_max_per_turn_reached"):
                service.execute(
                    encounter_id="enc_execute_attack_test",
                    target_id=target.entity_id,
                    weapon_id="unarmed_strike",
                    consume_action=False,
                    final_total=17,
                    dice_rolls={"base_rolls": [12], "modifier": 5},
                    damage_rolls=[{"source": "weapon:unarmed_strike:part_0", "rolls": [6]}],
                    class_feature_options={"stunning_strike": {"enabled": True, "save_roll": 18}},
                )

    def test_execute_ignores_damage_rolls_when_attack_misses(self) -> None:
        """测试未命中时应忽略 damage_rolls，结果中不包含伤害分解."""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=8,
                dice_rolls={"base_rolls": [3], "modifier": 5},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [4]}],
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertIsNotNone(updated)

            self.assertFalse(result["resolution"]["hit"])
            self.assertNotIn("damage_resolution", result["resolution"])
            self.assertNotIn("hp_update", result["resolution"])
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["current"], 9)

    def test_execute_ignores_invalid_damage_rolls_when_attack_misses(self) -> None:
        """测试未命中时即使 damage_rolls source 不匹配，也不会让攻击失败."""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_attack_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
                final_total=8,
                dice_rolls={"base_rolls": [3], "modifier": 5},
                damage_rolls=[{"source": "weapon:rapier:part_9", "rolls": [4]}],
            )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertIsNotNone(updated)

            self.assertFalse(result["resolution"]["hit"])
            self.assertNotIn("damage_resolution", result["resolution"])
            self.assertNotIn("hp_update", result["resolution"])
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["current"], 9)

    def test_execute_auto_rolls_attack_and_damage_when_rolls_omitted(self) -> None:
        """测试未提供攻击骰与伤害骰时，后端会自动掷骰并完成结算."""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            with patch("random.randint", side_effect=[12, 4]):
                result = service.execute(
                    encounter_id="enc_execute_attack_test",
                    target_id="ent_enemy_goblin_001",
                    weapon_id="rapier",
                )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertIsNotNone(updated)

            self.assertEqual(result["roll_result"]["final_total"], 17)
            self.assertEqual(result["roll_result"]["dice_rolls"]["base_rolls"], [12])
            self.assertEqual(result["roll_result"]["dice_rolls"]["modifier"], 5)
            self.assertTrue(result["resolution"]["hit"])
            self.assertEqual(result["resolution"]["damage_resolution"]["total_damage"], 7)
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["current"], 2)

    def test_execute_auto_rolls_miss_without_damage_rolls(self) -> None:
        """测试自动攻击未命中时不会继续掷伤害骰，也不会改动目标生命值."""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            with patch("random.randint", side_effect=[3]) as mocked_randint:
                result = service.execute(
                    encounter_id="enc_execute_attack_test",
                    target_id="ent_enemy_goblin_001",
                    weapon_id="rapier",
                )

            updated = encounter_repo.get("enc_execute_attack_test")
            self.assertIsNotNone(updated)

            self.assertEqual(mocked_randint.call_count, 1)
            self.assertFalse(result["resolution"]["hit"])
            self.assertEqual(result["roll_result"]["final_total"], 8)
            self.assertNotIn("damage_resolution", result["resolution"])
            self.assertNotIn("hp_update", result["resolution"])
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["current"], 9)


if __name__ == "__main__":
    unittest.main()
