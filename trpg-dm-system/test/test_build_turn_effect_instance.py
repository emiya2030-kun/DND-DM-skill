"""持续效果实例化测试：覆盖法术模板 effect -> turn_effects。"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import EncounterEntity
from tools.repositories import SpellDefinitionRepository
from tools.services.spells.build_turn_effect_instance import build_turn_effect_instance


def build_entity(entity_id: str, name: str) -> EncounterEntity:
    return EncounterEntity(
        entity_id=entity_id,
        name=name,
        side="ally",
        category="pc",
        controller="player",
        position={"x": 1, "y": 1},
        hp={"current": 10, "max": 10, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
    )


class BuildTurnEffectInstanceTests(unittest.TestCase):
    def test_build_turn_effect_instance_resolves_template_and_dc(self) -> None:
        repo = SpellDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/spell_definitions.json"))
        spell_definition = repo.get("hold_person")
        self.assertIsNotNone(spell_definition)

        caster = build_entity("ent_caster", "吸血鬼法师")

        result = build_turn_effect_instance(
            spell_definition=spell_definition,
            effect_template_id="hold_person_repeat_save",
            caster=caster,
            save_dc=15,
        )

        self.assertEqual(result["trigger"], "end_of_turn")
        self.assertEqual(result["source_entity_id"], "ent_caster")
        self.assertEqual(result["source_ref"], "hold_person")
        self.assertEqual(result["save"]["dc"], 15)
        self.assertEqual(result["on_save_success"]["remove_conditions"], ["paralyzed"])
