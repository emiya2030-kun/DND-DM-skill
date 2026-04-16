from __future__ import annotations

"""武器知识库仓储测试。"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.repositories import WeaponDefinitionRepository


class WeaponDefinitionRepositoryTests(unittest.TestCase):
    def test_get_returns_weapon_definition_by_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "weapon_definitions.json"
            path.write_text(
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

            repository = WeaponDefinitionRepository(path)
            weapon = repository.get("rapier")

            self.assertIsNotNone(weapon)
            self.assertEqual(weapon["name"], "刺剑")
            self.assertEqual(weapon["base_damage"]["formula"], "1d8")


if __name__ == "__main__":
    unittest.main()
