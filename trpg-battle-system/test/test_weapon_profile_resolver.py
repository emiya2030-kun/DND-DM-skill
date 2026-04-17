"""武器解析器测试：覆盖职业模板提供的具体武器熟练。"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import EncounterEntity
from tools.repositories import WeaponDefinitionRepository
from tools.services.combat.attack.weapon_profile_resolver import WeaponProfileResolver


class WeaponProfileResolverTests(unittest.TestCase):
    def test_resolve_marks_rogue_rapier_as_proficient_from_class_template(self) -> None:
        actor = EncounterEntity(
            entity_id="ent_rogue_001",
            name="Rogue",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 1, "y": 1},
            hp={"current": 12, "max": 12, "temp": 0},
            ac=13,
            speed={"walk": 30, "remaining": 30},
            initiative=14,
            ability_scores={"dex": 16},
            ability_mods={"dex": 3},
            proficiency_bonus=2,
            weapons=[{"weapon_id": "rapier"}],
            class_features={"rogue": {"level": 1}},
        )

        profile = WeaponProfileResolver(
            WeaponDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/weapon_definitions.json"))
        ).resolve(actor, "rapier")

        self.assertTrue(profile["is_proficient"])

    def test_resolve_marks_wizard_rapier_as_not_proficient(self) -> None:
        actor = EncounterEntity(
            entity_id="ent_wizard_001",
            name="Wizard",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 1, "y": 1},
            hp={"current": 10, "max": 10, "temp": 0},
            ac=12,
            speed={"walk": 30, "remaining": 30},
            initiative=12,
            ability_scores={"dex": 14},
            ability_mods={"dex": 2},
            proficiency_bonus=2,
            weapons=[{"weapon_id": "rapier"}],
            class_features={"wizard": {"level": 1}},
        )

        profile = WeaponProfileResolver(
            WeaponDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/weapon_definitions.json"))
        ).resolve(actor, "rapier")

        self.assertFalse(profile["is_proficient"])


if __name__ == "__main__":
    unittest.main()
