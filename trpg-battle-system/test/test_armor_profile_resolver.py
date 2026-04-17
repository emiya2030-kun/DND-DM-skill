"""护甲解析器测试：覆盖 AC、受训和速度惩罚。"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import EncounterEntity
from tools.repositories import ArmorDefinitionRepository
from tools.services.combat.defense.armor_profile_resolver import ArmorProfileResolver


def build_actor() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_fighter_001",
        name="Fighter",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=10,
        speed={"walk": 30, "remaining": 30},
        initiative=14,
        ability_scores={"str": 12, "dex": 2},
        ability_mods={"str": 1, "dex": 2},
        proficiency_bonus=2,
    )


class ArmorProfileResolverTests(unittest.TestCase):
    def test_resolve_unarmored_defense_for_monk_without_armor_or_shield(self) -> None:
        actor = build_actor()
        actor.ac = 12
        actor.ability_mods["dex"] = 3
        actor.ability_mods["wis"] = 2
        actor.class_features = {"monk": {"level": 3}}

        profile = ArmorProfileResolver().resolve(actor)

        self.assertEqual(profile["base_ac"], 15)
        self.assertEqual(profile["current_ac"], 15)

    def test_resolve_unarmored_defense_does_not_apply_when_wearing_armor(self) -> None:
        actor = build_actor()
        actor.ability_mods["dex"] = 3
        actor.ability_mods["wis"] = 2
        actor.class_features = {"monk": {"level": 3}}
        actor.equipped_armor = {"armor_id": "leather_armor"}

        profile = ArmorProfileResolver().resolve(actor)

        self.assertNotEqual(profile["base_ac"], 15)

    def test_resolve_unarmored_defense_does_not_apply_when_using_shield(self) -> None:
        actor = build_actor()
        actor.ability_mods["dex"] = 3
        actor.ability_mods["wis"] = 2
        actor.class_features = {"monk": {"level": 3}}
        actor.equipped_shield = {"armor_id": "shield"}

        profile = ArmorProfileResolver().resolve(actor)

        self.assertNotEqual(profile["base_ac"], 15)

    def test_resolve_unarmored_defense_for_barbarian_without_armor_allows_shield(self) -> None:
        actor = build_actor()
        actor.ability_mods["dex"] = 2
        actor.ability_mods["con"] = 3
        actor.class_features = {"barbarian": {"level": 1}}
        actor.equipped_armor = None
        actor.equipped_shield = {"armor_id": "shield", "category": "shield", "ac": {"bonus": 2}}

        profile = ArmorProfileResolver().resolve(actor)

        self.assertEqual(profile["base_ac"], 17)
        self.assertEqual(profile["current_ac"], 17)

    def test_resolve_chain_mail_and_shield_for_fighter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            knowledge_path = Path(tmp_dir) / "armor_definitions.json"
            knowledge_path.write_text(
                json.dumps(
                    {
                        "armor_definitions": {
                            "chain_mail": {
                                "armor_id": "chain_mail",
                                "name": "链甲",
                                "category": "heavy",
                                "ac": {"base": 16},
                                "strength_requirement": 13,
                                "stealth_disadvantage": True,
                            },
                            "shield": {
                                "armor_id": "shield",
                                "name": "盾牌",
                                "category": "shield",
                                "ac": {"bonus": 2},
                                "stealth_disadvantage": False,
                            },
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_actor()
            actor.equipped_armor = {"armor_id": "chain_mail"}
            actor.equipped_shield = {"armor_id": "shield"}
            actor.class_features = {"fighter": {"level": 1}}

            profile = ArmorProfileResolver(ArmorDefinitionRepository(knowledge_path)).resolve(actor)

            self.assertEqual(profile["base_ac"], 18)
            self.assertEqual(profile["speed_penalty_feet"], 10)
            self.assertFalse(profile["wearing_untrained_armor"])
            self.assertEqual(profile["armor_training"], ["light", "medium", "heavy", "shield"])

    def test_resolve_chain_mail_and_shield_for_fighter_uses_shared_resolver(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            knowledge_path = Path(tmp_dir) / "armor_definitions.json"
            knowledge_path.write_text(
                json.dumps(
                    {
                        "armor_definitions": {
                            "chain_mail": {
                                "armor_id": "chain_mail",
                                "name": "链甲",
                                "category": "heavy",
                                "ac": {"base": 16},
                                "strength_requirement": 13,
                                "stealth_disadvantage": True,
                            },
                            "shield": {
                                "armor_id": "shield",
                                "name": "盾牌",
                                "category": "shield",
                                "ac": {"bonus": 2},
                                "stealth_disadvantage": False,
                            },
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_actor()
            actor.equipped_armor = {"armor_id": "chain_mail"}
            actor.equipped_shield = {"armor_id": "shield"}
            actor.class_features = {"fighter": {"level": 1}}

            profile = ArmorProfileResolver(ArmorDefinitionRepository(knowledge_path)).resolve(actor)

            self.assertFalse(profile["wearing_untrained_armor"])
            self.assertTrue(profile["shield_trained"])
            self.assertEqual(profile["current_ac"], 18)

    def test_resolve_defense_style_adds_one_ac_while_wearing_armor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            knowledge_path = Path(tmp_dir) / "armor_definitions.json"
            knowledge_path.write_text(
                json.dumps(
                    {
                        "armor_definitions": {
                            "leather_armor": {
                                "armor_id": "leather_armor",
                                "name": "皮甲",
                                "category": "light",
                                "ac": {"base": 11, "add_dex_modifier": True},
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            actor = build_actor()
            actor.equipped_armor = {"armor_id": "leather_armor"}
            actor.class_features = {"fighter": {"level": 1, "fighting_style": {"style_id": "defense"}}}

            profile = ArmorProfileResolver(ArmorDefinitionRepository(knowledge_path)).resolve(actor)

            self.assertEqual(profile["current_ac"], 14)
            self.assertEqual(profile["ac_breakdown"]["fighting_style_bonus"], 1)
