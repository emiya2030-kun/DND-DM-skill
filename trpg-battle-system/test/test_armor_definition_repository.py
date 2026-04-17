"""护甲知识库仓储测试：覆盖静态护甲模板读取。"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.repositories import ArmorDefinitionRepository


class ArmorDefinitionRepositoryTests(unittest.TestCase):
    def test_get_returns_armor_definition(self) -> None:
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
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            repo = ArmorDefinitionRepository(knowledge_path)
            definition = repo.get("chain_mail")

            self.assertIsNotNone(definition)
            self.assertEqual(definition["category"], "heavy")
            self.assertEqual(definition["ac"]["base"], 16)
