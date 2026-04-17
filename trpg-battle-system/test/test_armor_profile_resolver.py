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
            self.assertEqual(profile["armor_training"], ["heavy", "light", "medium", "shield"])
