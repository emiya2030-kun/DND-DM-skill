from __future__ import annotations

"""攻击掷骰请求测试：覆盖请求生成、距离计算和非法输入。"""

import sys
import tempfile
import unittest
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, WeaponDefinitionRepository
from tools.services import AttackRollRequest


def build_actor(
    *,
    position: tuple[int, int] = (2, 2),
    conditions: list[str] | None = None,
    action_economy: dict[str, bool] | None = None,
    ability_scores: dict[str, int] | None = None,
) -> EncounterEntity:
    """构造当前行动的攻击者。"""
    return EncounterEntity(
        entity_id="ent_ally_eric_001",
        name="Eric",
        side="ally",
        category="pc",
        controller="player",
        position={"x": position[0], "y": position[1]},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
        ability_scores=ability_scores or {"str": 12, "dex": 16, "con": 12, "int": 10, "wis": 10, "cha": 14},
        ability_mods={"str": 1, "dex": 3, "con": 1, "int": 0, "wis": 0, "cha": 2},
        proficiency_bonus=2,
        conditions=conditions or [],
        action_economy=action_economy or {},
        weapons=[
            {
                "weapon_id": "rapier",
                "name": "Rapier",
                "attack_bonus": 5,
                "damage": [{"formula": "1d8+3", "type": "piercing"}],
                "properties": ["finesse"],
                "range": {"normal": 5, "long": 5},
            },
            {
                "weapon_id": "shortbow",
                "name": "Shortbow",
                "damage": [{"formula": "1d6+3", "type": "piercing"}],
                "properties": [],
                "range": {"normal": 80, "long": 320},
            },
        ],
    )


def build_actor_with_reach_weapon() -> EncounterEntity:
    actor = build_actor()
    actor.weapons = [
        {
            "weapon_id": "reach_glaive",
            "name": "Reach Glaive",
            "attack_bonus": 5,
            "damage": [{"formula": "1d10+3", "type": "slashing"}],
            "properties": [],
            "range": {"normal": 10, "long": 30},
        }
    ]
    return actor


def build_target(
    *,
    position: tuple[int, int] = (3, 2),
    conditions: list[str] | None = None,
    entity_id: str = "ent_enemy_goblin_001",
    name: str = "Goblin",
) -> EncounterEntity:
    """构造攻击目标。"""
    return EncounterEntity(
        entity_id=entity_id,
        name=name,
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": position[0], "y": position[1]},
        hp={"current": 7, "max": 7, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
        conditions=conditions or [],
    )


def build_encounter(
    *,
    actor: EncounterEntity | None = None,
    target: EncounterEntity | None = None,
    terrain: list[dict] | None = None,
    width: int = 8,
    height: int = 8,
) -> Encounter:
    """构造攻击请求测试用 encounter。"""
    actor = actor or build_actor()
    target = target or build_target()
    return Encounter(
        encounter_id="enc_attack_request_test",
        name="Attack Request Test Encounter",
        status="active",
        round=1,
        current_entity_id=actor.entity_id,
        turn_order=[actor.entity_id, target.entity_id],
        entities={actor.entity_id: actor, target.entity_id: target},
        map=EncounterMap(
            map_id="map_attack_request_test",
            name="Attack Request Test Map",
            description="A small combat room.",
            width=width,
            height=height,
            terrain=terrain or [],
        ),
    )


class AttackRollRequestTests(unittest.TestCase):
    def test_execute_rejects_non_current_turn_actor(self) -> None:
        """测试显式传入的 actor 不是当前行动者时会被拒绝。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            actor = build_actor()
            target = build_target()
            bystander = build_target(
                position=(2, 3),
                entity_id="ent_ally_lia_001",
                name="Lia",
            )
            bystander.side = "ally"
            bystander.category = "pc"
            bystander.controller = "player"
            repo.save(
                Encounter(
                    encounter_id="enc_attack_request_test",
                    name="Attack Request Test Encounter",
                    status="active",
                    round=1,
                    current_entity_id=actor.entity_id,
                    turn_order=[actor.entity_id, bystander.entity_id, target.entity_id],
                    entities={
                        actor.entity_id: actor,
                        bystander.entity_id: bystander,
                        target.entity_id: target,
                    },
                    map=EncounterMap(
                        map_id="map_attack_request_test",
                        name="Attack Request Test Map",
                        description="A small combat room.",
                        width=8,
                        height=8,
                    ),
                )
            )

            with self.assertRaisesRegex(ValueError, "actor_not_current_turn_entity"):
                AttackRollRequest(repo).execute(
                    encounter_id="enc_attack_request_test",
                    actor_id=bystander.entity_id,
                    target_id=target.entity_id,
                    weapon_id="rapier",
                )
            repo.close()

    def test_execute_non_proficient_weapon_does_not_add_proficiency_bonus(self) -> None:
        """测试不熟练武器不会把熟练加值计入攻击检定。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            actor = build_actor()
            actor.weapons = [{"weapon_id": "rapier", "is_proficient": False}]
            repo.save(build_encounter(actor=actor))

            request = AttackRollRequest(repo).execute(
                encounter_id="enc_attack_request_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
            )

            self.assertEqual(request.formula, "1d20+3")
            self.assertEqual(request.context["proficiency_bonus"], 0)
            self.assertFalse(request.context["weapon_is_proficient"])
            repo.close()

    def test_execute_applies_disadvantage_for_heavy_ranged_weapon_with_low_dex(self) -> None:
        """测试敏捷低于 13 时，重型远程武器攻击应有劣势。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
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
            actor = build_actor(ability_scores={"str": 12, "dex": 12, "con": 12, "int": 10, "wis": 10, "cha": 14})
            actor.weapons = [{"weapon_id": "longbow", "is_proficient": True}]
            repo.save(build_encounter(actor=actor))

            request = AttackRollRequest(
                repo,
                weapon_definition_repository=WeaponDefinitionRepository(knowledge_path),
            ).execute(
                encounter_id="enc_attack_request_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="longbow",
            )

            self.assertEqual(request.context["vantage"], "disadvantage")
            self.assertIn("heavy_ranged_low_dex", request.context["vantage_sources"]["disadvantage"])
            repo.close()

    def test_execute_applies_disadvantage_for_heavy_melee_weapon_with_low_str(self) -> None:
        """测试力量低于 13 时，重型近战武器攻击应有劣势。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
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
            actor = build_actor(ability_scores={"str": 12, "dex": 16, "con": 12, "int": 10, "wis": 10, "cha": 14})
            actor.weapons = [{"weapon_id": "greatsword", "is_proficient": True}]
            repo.save(build_encounter(actor=actor))

            request = AttackRollRequest(
                repo,
                weapon_definition_repository=WeaponDefinitionRepository(knowledge_path),
            ).execute(
                encounter_id="enc_attack_request_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="greatsword",
            )

            self.assertEqual(request.context["vantage"], "disadvantage")
            self.assertIn("heavy_melee_low_str", request.context["vantage_sources"]["disadvantage"])
            repo.close()

    def test_execute_reach_property_extends_melee_attack_to_10_feet(self) -> None:
        """测试 reach 词条本身会把近战触及扩到 10 尺。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            knowledge_path = Path(tmp_dir) / "weapon_definitions.json"
            knowledge_path.write_text(
                json.dumps(
                    {
                        "weapon_definitions": {
                            "glaive": {
                                "id": "glaive",
                                "name": "长柄刀",
                                "category": "martial",
                                "kind": "melee",
                                "base_damage": {"formula": "1d10", "damage_type": "slashing"},
                                "properties": ["heavy", "reach", "two_handed"],
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
            actor.weapons = [{"weapon_id": "glaive", "is_proficient": True}]
            repo.save(build_encounter(actor=actor, target=build_target(position=(4, 2))))

            request = AttackRollRequest(
                repo,
                weapon_definition_repository=WeaponDefinitionRepository(knowledge_path),
            ).execute(
                encounter_id="enc_attack_request_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="glaive",
            )

            self.assertEqual(request.context["distance_to_target_feet"], 10)
            self.assertEqual(request.context["attack_kind"], "melee_weapon")
            repo.close()

    def test_execute_thrown_attack_uses_thrown_range_and_melee_modifier_rule(self) -> None:
        """测试投掷近战武器时使用 thrown_range 且沿用近战属性规则。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
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
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_actor()
            actor.weapons = [{"weapon_id": "dagger", "is_proficient": True}]
            repo.save(build_encounter(actor=actor, target=build_target(position=(6, 2)), width=10))

            request = AttackRollRequest(
                repo,
                weapon_definition_repository=WeaponDefinitionRepository(knowledge_path),
            ).execute(
                encounter_id="enc_attack_request_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="dagger",
                attack_mode="thrown",
            )

            self.assertEqual(request.context["attack_kind"], "ranged_weapon")
            self.assertEqual(request.context["modifier"], "dex")
            self.assertEqual(request.context["distance_to_target_feet"], 20)
            repo.close()

    def test_execute_rejects_light_bonus_attack_without_prior_light_attack(self) -> None:
        """测试未先用轻型武器执行攻击动作时，不能直接发起 light 额外攻击。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
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
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_actor()
            actor.weapons = [{"weapon_id": "shortsword", "slot": "main_hand", "is_proficient": True}]
            repo.save(build_encounter(actor=actor))

            with self.assertRaisesRegex(ValueError, "light_bonus_not_available"):
                AttackRollRequest(
                    repo,
                    weapon_definition_repository=WeaponDefinitionRepository(knowledge_path),
                ).execute(
                    encounter_id="enc_attack_request_test",
                    target_id="ent_enemy_goblin_001",
                    weapon_id="shortsword",
                    attack_mode="light_bonus",
                )
            repo.close()

    def test_execute_rejects_two_handed_attack_when_other_hand_is_occupied(self) -> None:
        """测试双手武器攻击时，若另一只手被占用则不能发起攻击。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
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
            repo.save(build_encounter(actor=actor))

            with self.assertRaisesRegex(ValueError, "two_handed_requires_two_free_hands"):
                AttackRollRequest(
                    repo,
                    weapon_definition_repository=WeaponDefinitionRepository(knowledge_path),
                ).execute(
                    encounter_id="enc_attack_request_test",
                    target_id="ent_enemy_goblin_001",
                    weapon_id="longbow",
                )
            repo.close()

    def test_execute_applies_disadvantage_for_ranged_attack_when_hostile_is_within_5_feet(self) -> None:
        """测试远程武器攻击时，若 5 尺内有可见且未失能的敌人，会获得贴脸劣势。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            actor = build_actor(position=(2, 2))
            actor.weapons = [
                {
                    "weapon_id": "shortbow",
                    "name": "Shortbow",
                    "damage": [{"formula": "1d6+3", "type": "piercing"}],
                    "properties": [],
                    "range": {"normal": 80, "long": 320},
                }
            ]
            target = build_target(position=(8, 2))
            adjacent_enemy = build_target(
                position=(3, 2),
                entity_id="ent_enemy_orc_001",
                name="Orc",
            )
            encounter = build_encounter(actor=actor, target=target, width=10, height=10)
            encounter.entities[adjacent_enemy.entity_id] = adjacent_enemy
            encounter.turn_order.append(adjacent_enemy.entity_id)
            repo.save(encounter)

            request = AttackRollRequest(repo).execute(
                encounter_id="enc_attack_request_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="shortbow",
            )

            self.assertEqual(request.context["attack_kind"], "ranged_weapon")
            self.assertEqual(request.context["vantage"], "disadvantage")
            self.assertIn(
                "close_range_hostile:ent_enemy_orc_001",
                request.context["vantage_sources"]["disadvantage"],
            )
            repo.close()

    def test_execute_ignores_close_range_disadvantage_when_adjacent_hostile_cannot_see_or_act(self) -> None:
        """测试邻近敌人若看不见你或已失能，则不会施加贴脸劣势。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            actor = build_actor(position=(2, 2))
            actor.weapons = [
                {
                    "weapon_id": "shortbow",
                    "name": "Shortbow",
                    "damage": [{"formula": "1d6+3", "type": "piercing"}],
                    "properties": [],
                    "range": {"normal": 80, "long": 320},
                }
            ]
            target = build_target(position=(8, 2))
            adjacent_enemy = build_target(
                position=(3, 2),
                entity_id="ent_enemy_orc_001",
                name="Orc",
                conditions=["blinded", "incapacitated"],
            )
            encounter = build_encounter(actor=actor, target=target, width=10, height=10)
            encounter.entities[adjacent_enemy.entity_id] = adjacent_enemy
            encounter.turn_order.append(adjacent_enemy.entity_id)
            repo.save(encounter)

            request = AttackRollRequest(repo).execute(
                encounter_id="enc_attack_request_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="shortbow",
            )

            self.assertEqual(request.context["attack_kind"], "ranged_weapon")
            self.assertEqual(request.context["vantage"], "normal")
            self.assertNotIn(
                "close_range_hostile:ent_enemy_orc_001",
                request.context["vantage_sources"]["disadvantage"],
            )
            repo.close()

    def test_execute_ignores_close_range_disadvantage_when_actor_has_override(self) -> None:
        """测试角色若有规则覆盖，可忽略远程贴脸劣势。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            actor = build_actor(position=(2, 2))
            actor.weapons = [
                {
                    "weapon_id": "shortbow",
                    "name": "Shortbow",
                    "damage": [{"formula": "1d6+3", "type": "piercing"}],
                    "properties": [],
                    "range": {"normal": 80, "long": 320},
                }
            ]
            actor.combat_flags = {
                "attack_rule_overrides": {
                    "ignore_close_range_disadvantage": {
                        "applies_to": ["ranged_weapon"],
                    }
                }
            }
            target = build_target(position=(8, 2))
            adjacent_enemy = build_target(
                position=(3, 2),
                entity_id="ent_enemy_orc_001",
                name="Orc",
            )
            encounter = build_encounter(actor=actor, target=target, width=10, height=10)
            encounter.entities[adjacent_enemy.entity_id] = adjacent_enemy
            encounter.turn_order.append(adjacent_enemy.entity_id)
            repo.save(encounter)

            request = AttackRollRequest(repo).execute(
                encounter_id="enc_attack_request_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="shortbow",
            )

            self.assertEqual(request.context["attack_kind"], "ranged_weapon")
            self.assertEqual(request.context["vantage"], "normal")
            self.assertNotIn(
                "close_range_hostile:ent_enemy_orc_001",
                request.context["vantage_sources"]["disadvantage"],
            )
            repo.close()

    def test_execute_thrown_attack_applies_disadvantage_at_long_thrown_range(self) -> None:
        """测试投掷武器在长射程内会自动带 disadvantage。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
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
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_actor()
            actor.weapons = [{"weapon_id": "dagger", "is_proficient": True}]
            repo.save(build_encounter(actor=actor, target=build_target(position=(8, 2)), width=12))

            request = AttackRollRequest(
                repo,
                weapon_definition_repository=WeaponDefinitionRepository(knowledge_path),
            ).execute(
                encounter_id="enc_attack_request_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="dagger",
                attack_mode="thrown",
            )

            self.assertEqual(request.context["distance_to_target_feet"], 30)
            self.assertEqual(request.context["vantage"], "disadvantage")
            self.assertIn("long_range", request.context["vantage_sources"]["disadvantage"])
            repo.close()

    def test_execute_rejects_thrown_attack_beyond_long_range(self) -> None:
        """测试投掷武器超出最大射程时不会生成请求。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
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
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_actor()
            actor.weapons = [{"weapon_id": "dagger", "is_proficient": True}]
            repo.save(build_encounter(actor=actor, target=build_target(position=(16, 2)), width=20))

            with self.assertRaisesRegex(ValueError, "target_out_of_range"):
                AttackRollRequest(
                    repo,
                    weapon_definition_repository=WeaponDefinitionRepository(knowledge_path),
                ).execute(
                    encounter_id="enc_attack_request_test",
                    target_id="ent_enemy_goblin_001",
                    weapon_id="dagger",
                    attack_mode="thrown",
                )
            repo.close()

    def test_execute_reads_weapon_definition_and_merges_entity_runtime_fields(self) -> None:
        """测试攻击请求可从武器知识库读取模板，并合并实体运行时覆写。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
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
            actor.weapons = [
                {
                    "weapon_id": "rapier",
                    "display_name": "炼狱刺剑",
                    "is_proficient": True,
                    "extra_damage_parts": [{"formula": "1d8", "type": "fire"}],
                }
            ]
            repo.save(build_encounter(actor=actor))

            request = AttackRollRequest(
                repo,
                weapon_definition_repository=WeaponDefinitionRepository(knowledge_path),
            ).execute(
                encounter_id="enc_attack_request_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
            )

            self.assertEqual(request.reason, "炼狱刺剑 attack")
            self.assertEqual(request.context["attack_name"], "炼狱刺剑")
            self.assertEqual(request.context["weapon_category"], "martial")
            self.assertTrue(request.context["weapon_is_proficient"])
            repo.close()

    def test_execute_builds_weapon_attack_request(self) -> None:
        """测试会为当前行动者生成完整的武器攻击请求。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            request = AttackRollRequest(repo).execute(
                encounter_id="enc_attack_request_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
            )

            self.assertEqual(request.actor_entity_id, "ent_ally_eric_001")
            self.assertEqual(request.target_entity_id, "ent_enemy_goblin_001")
            self.assertEqual(request.formula, "1d20+5")
            self.assertEqual(request.context["modifier"], "dex")
            self.assertEqual(request.context["distance_to_target_feet"], 5)
            self.assertEqual(request.context["distance_to_target"], "5 ft")
            repo.close()

    def test_execute_builds_ranged_attack_when_weapon_has_long_range(self) -> None:
        """测试远程武器会使用 dex 修正并标记为 ranged_weapon。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            target = build_target(position=(6, 2))
            repo.save(build_encounter(target=target))

            request = AttackRollRequest(repo).execute(
                encounter_id="enc_attack_request_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="shortbow",
                vantage="advantage",
            )

            self.assertEqual(request.context["attack_kind"], "ranged_weapon")
            self.assertEqual(request.context["modifier"], "dex")
            self.assertEqual(request.context["proficiency_bonus"], 2)
            self.assertEqual(request.context["vantage"], "advantage")
            repo.close()

    def test_execute_rejects_unknown_weapon(self) -> None:
        """测试找不到武器时会直接报错。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            with self.assertRaises(ValueError):
                AttackRollRequest(repo).execute(
                    encounter_id="enc_attack_request_test",
                    target_id="ent_enemy_goblin_001",
                    weapon_id="missing_weapon",
                )
            repo.close()

    def test_execute_rejects_missing_target(self) -> None:
        """测试目标不存在时不会生成请求。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            with self.assertRaises(ValueError):
                AttackRollRequest(repo).execute(
                    encounter_id="enc_attack_request_test",
                    target_id="ent_missing",
                    weapon_id="rapier",
                )
            repo.close()

    def test_execute_rejects_melee_target_out_of_range(self) -> None:
        """测试近战武器超出触及范围时会直接报错。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter(target=build_target(position=(5, 4))))

            with self.assertRaisesRegex(ValueError, "target_out_of_range"):
                AttackRollRequest(repo).execute(
                    encounter_id="enc_attack_request_test",
                    target_id="ent_enemy_goblin_001",
                    weapon_id="rapier",
                )
            repo.close()

    def test_execute_rejects_ranged_target_beyond_long_range(self) -> None:
        """测试远程武器超出长射程时不会生成请求。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(
                build_encounter(
                    target=build_target(position=(70, 2)),
                    width=80,
                    height=20,
                )
            )

            with self.assertRaisesRegex(ValueError, "target_out_of_range"):
                AttackRollRequest(repo).execute(
                    encounter_id="enc_attack_request_test",
                    target_id="ent_enemy_goblin_001",
                    weapon_id="shortbow",
                )
            repo.close()

    def test_execute_applies_disadvantage_for_long_range_shot(self) -> None:
        """测试远程武器在长射程内会自动带 disadvantage。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(
                build_encounter(
                    target=build_target(position=(22, 2)),
                    width=30,
                    height=20,
                )
            )

            request = AttackRollRequest(repo).execute(
                encounter_id="enc_attack_request_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="shortbow",
            )

            self.assertEqual(request.context["distance_to_target_feet"], 100)
            self.assertEqual(request.context["vantage"], "disadvantage")
            self.assertIn("long_range", request.context["vantage_sources"]["disadvantage"])
            repo.close()

    def test_execute_rejects_when_action_is_already_used(self) -> None:
        """测试已经用过 action 时不能再发起武器攻击。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(
                build_encounter(
                    actor=build_actor(action_economy={"action_used": True}),
                )
            )

            with self.assertRaisesRegex(ValueError, "action_already_used"):
                AttackRollRequest(repo).execute(
                    encounter_id="enc_attack_request_test",
                    target_id="ent_enemy_goblin_001",
                    weapon_id="rapier",
                )
            repo.close()

    def test_execute_rejects_when_attack_action_sequence_is_already_exhausted(self) -> None:
        """测试 Extra Attack 序列已耗尽时，即使有 fighter runtime 也不能继续请求。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            actor = build_actor(action_economy={"action_used": True})
            actor.class_features = {
                "fighter": {
                    "extra_attack_count": 2,
                    "turn_counters": {"attack_action_attacks_used": 2},
                }
            }
            repo.save(build_encounter(actor=actor))

            with self.assertRaisesRegex(ValueError, "action_already_used"):
                AttackRollRequest(repo).execute(
                    encounter_id="enc_attack_request_test",
                    target_id="ent_enemy_goblin_001",
                    weapon_id="rapier",
                )
            repo.close()

    def test_execute_rejects_when_wall_blocks_line_of_sight(self) -> None:
        """测试墙体阻挡视线时不会生成攻击请求。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(
                build_encounter(
                    target=build_target(position=(5, 2)),
                    terrain=[{"terrain_id": "wall_01", "type": "wall", "x": 4, "y": 2, "blocks_los": True}],
                )
            )

            with self.assertRaisesRegex(ValueError, "blocked_by_line_of_sight"):
                AttackRollRequest(repo).execute(
                    encounter_id="enc_attack_request_test",
                    target_id="ent_enemy_goblin_001",
                    weapon_id="shortbow",
                )
            repo.close()

    def test_execute_rejects_when_actor_condition_prevents_attack(self) -> None:
        """测试失能类状态会直接阻止攻击。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter(actor=build_actor(conditions=["stunned"])))

            with self.assertRaisesRegex(ValueError, "actor_cannot_attack"):
                AttackRollRequest(repo).execute(
                    encounter_id="enc_attack_request_test",
                    target_id="ent_enemy_goblin_001",
                    weapon_id="rapier",
                )
            repo.close()

    def test_execute_merges_condition_based_vantage(self) -> None:
        """测试会把 condition 自动归并成最终 advantage/disadvantage。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(
                build_encounter(
                    actor=build_actor(conditions=["blinded"]),
                    target=build_target(conditions=["restrained"]),
                )
            )

            request = AttackRollRequest(repo).execute(
                encounter_id="enc_attack_request_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
            )

            self.assertEqual(request.context["vantage"], "normal")
            self.assertIn("actor_blinded", request.context["vantage_sources"]["disadvantage"])
            self.assertIn("target_restrained", request.context["vantage_sources"]["advantage"])
            repo.close()

    def test_execute_applies_exhaustion_penalty(self) -> None:
        """测试力竭会令攻击加值下降并记录 penalty。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            actor = build_actor(conditions=["exhaustion:2"])
            repo.save(build_encounter(actor=actor))

            request = AttackRollRequest(repo).execute(
                encounter_id="enc_attack_request_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
            )

            self.assertEqual(request.formula, "1d20+1")
            self.assertEqual(request.context["base_attack_bonus"], 5)
            self.assertEqual(request.context["attack_bonus"], 1)
            self.assertEqual(request.context["exhaustion_penalty"], 4)
            repo.close()

    def test_execute_rejects_when_actor_charmed_target(self) -> None:
        """测试被魅惑的实体不能攻击魅惑者。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(
                build_encounter(actor=build_actor(conditions=["charmed:ent_enemy_goblin_001"]))
            )

            with self.assertRaisesRegex(ValueError, "actor_cannot_attack_charmed_target"):
                AttackRollRequest(repo).execute(
                    encounter_id="enc_attack_request_test",
                    target_id="ent_enemy_goblin_001",
                    weapon_id="rapier",
                )
            repo.close()

    def test_execute_grappled_actor_has_disadvantage_only_against_other_targets(self) -> None:
        """测试被某人擒抱时攻击其他目标会带 disadvantage。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            actor = build_actor(conditions=["grappled:ent_enemy_orc_001"])
            target = build_target()
            other = build_target()
            other.entity_id = "ent_enemy_orc_001"
            other.position = {"x": 4, "y": 2}
            encounter = build_encounter(actor=actor, target=target)
            encounter.entities[other.entity_id] = other
            encounter.turn_order.append(other.entity_id)
            repo.save(encounter)

            request = AttackRollRequest(repo).execute(
                encounter_id="enc_attack_request_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
            )

            self.assertEqual(request.context["vantage"], "disadvantage")
            self.assertIn(
                "actor_grappled_by_ent_enemy_orc_001",
                request.context["vantage_sources"]["disadvantage"],
            )
            repo.close()

    def test_execute_grappled_actor_against_grappler_stays_normal(self) -> None:
        """测试攻击自己的擒抱者不会再额外提供 disadvantage。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(
                build_encounter(actor=build_actor(conditions=["grappled:ent_enemy_goblin_001"]))
            )

            request = AttackRollRequest(repo).execute(
                encounter_id="enc_attack_request_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
            )

            self.assertEqual(request.context["vantage"], "normal")
            self.assertFalse(
                any(
                    source.startswith("actor_grappled_by_")
                    for source in request.context["vantage_sources"]["disadvantage"]
                )
            )
            repo.close()

    def test_execute_flags_melee_auto_crit_for_paralyzed_targets(self) -> None:
        """测试近战攻击麻痹目标时会在请求里标记 auto crit。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(
                build_encounter(target=build_target(conditions=["paralyzed"]))
            )

            request = AttackRollRequest(repo).execute(
                encounter_id="enc_attack_request_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="rapier",
            )

            self.assertTrue(request.context["melee_auto_crit"])
            repo.close()

    def test_execute_prone_target_far_produces_disadvantage(self) -> None:
        """测试远程 prone 目标应该产生 disadvantage 而不是 normal。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            actor = build_actor_with_reach_weapon()
            repo.save(
                build_encounter(
                    actor=actor,
                    target=build_target(position=(4, 2), conditions=["prone"]),
                )
            )

            request = AttackRollRequest(repo).execute(
                encounter_id="enc_attack_request_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="reach_glaive",
            )

            self.assertEqual(request.context["distance_to_target_feet"], 10)
            self.assertEqual(request.context["vantage"], "disadvantage")
            self.assertIn("target_prone_far", request.context["vantage_sources"]["disadvantage"])
            self.assertNotIn("target_prone_close", request.context["vantage_sources"]["advantage"])
            repo.close()

    def test_execute_reach_melee_paralyzed_target_not_auto_crit(self) -> None:
        """测试带 reach 的近战在 5 ft 之外攻击麻痹目标不会自动暴击。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            actor = build_actor_with_reach_weapon()
            target = build_target(position=(4, 2), conditions=["paralyzed"])
            repo.save(build_encounter(actor=actor, target=target))

            request = AttackRollRequest(repo).execute(
                encounter_id="enc_attack_request_test",
                target_id="ent_enemy_goblin_001",
                weapon_id="reach_glaive",
            )

            self.assertEqual(request.context["distance_to_target_feet"], 10)
            self.assertEqual(request.context["attack_kind"], "melee_weapon")
            self.assertFalse(request.context["melee_auto_crit"])
            repo.close()


if __name__ == "__main__":
    unittest.main()
