"""法术实例构造测试：覆盖 Hold Person 与 Hex 的最小运行时结构。"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import EncounterEntity
from tools.repositories import SpellDefinitionRepository
from tools.services.spells.build_spell_instance import build_spell_instance


def build_caster() -> EncounterEntity:
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
    )


class BuildSpellInstanceTests(unittest.TestCase):
    def test_build_spell_instance_for_hold_person(self) -> None:
        repo = SpellDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/spell_definitions.json"))
        spell_definition = repo.get("hold_person")
        self.assertIsNotNone(spell_definition)

        instance = build_spell_instance(
            spell_definition=spell_definition,
            caster=build_caster(),
            cast_level=2,
            targets=[
                {
                    "entity_id": "ent_enemy_iron_duster_001",
                    "applied_conditions": ["paralyzed"],
                    "turn_effect_ids": ["effect_hold_person_001"],
                }
            ],
            started_round=1,
        )

        self.assertEqual(instance["spell_id"], "hold_person")
        self.assertEqual(instance["caster_entity_id"], "ent_ally_eric_001")
        self.assertEqual(instance["cast_level"], 2)
        self.assertTrue(instance["concentration"]["required"])
        self.assertEqual(instance["targets"][0]["applied_conditions"], ["paralyzed"])
        self.assertEqual(instance["targets"][0]["turn_effect_ids"], ["effect_hold_person_001"])

    def test_build_spell_instance_for_hex_marks_retargetable_runtime(self) -> None:
        repo = SpellDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/spell_definitions.json"))
        spell_definition = repo.get("hex")
        self.assertIsNotNone(spell_definition)

        instance = build_spell_instance(
            spell_definition=spell_definition,
            caster=build_caster(),
            cast_level=1,
            targets=[
                {
                    "entity_id": "ent_enemy_goblin_001",
                    "applied_conditions": [],
                    "turn_effect_ids": ["effect_hex_001"],
                }
            ],
            started_round=1,
        )

        self.assertEqual(instance["spell_id"], "hex")
        self.assertTrue(instance["special_runtime"]["retargetable"])
        self.assertEqual(instance["special_runtime"]["current_target_id"], "ent_enemy_goblin_001")

    def test_build_spell_instance_for_hunters_mark_marks_retargetable_runtime(self) -> None:
        repo = SpellDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/spell_definitions.json"))
        spell_definition = repo.get("hunters_mark")
        self.assertIsNotNone(spell_definition)

        instance = build_spell_instance(
            spell_definition=spell_definition,
            caster=build_caster(),
            cast_level=1,
            targets=[
                {
                    "entity_id": "ent_enemy_goblin_001",
                    "applied_conditions": [],
                    "turn_effect_ids": ["effect_hunters_mark_001"],
                }
            ],
            started_round=1,
        )

        self.assertEqual(instance["spell_id"], "hunters_mark")
        self.assertTrue(instance["special_runtime"]["retargetable"])
        self.assertEqual(instance["special_runtime"]["current_target_id"], "ent_enemy_goblin_001")
