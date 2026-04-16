import tempfile
import unittest
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

from runtime.context import build_runtime_context
from scripts.run_battlemap_localhost import ensure_preview_encounter


class RuntimeExecuteAttackTests(unittest.TestCase):
    def test_execute_attack_runs_normal_attack_and_returns_encounter_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                ensure_preview_encounter(context.encounter_repository)
                execute_attack_module = import_module("runtime.commands.execute_attack")
                with patch.object(
                    execute_attack_module.ExecuteAttack,
                    "execute",
                    return_value={
                        "request": {"encounter_id": "enc_preview_demo"},
                        "roll_result": {"final_total": 16},
                        "resolution": {"hit": True},
                        "encounter_state": {"encounter_id": "enc_preview_demo"},
                    },
                ) as mocked_execute:
                    result = execute_attack_module.execute_attack(
                        context,
                        {
                            "encounter_id": "enc_preview_demo",
                            "actor_id": "ent_ally_wizard_001",
                            "target_id": "ent_enemy_brute_001",
                            "weapon_id": "dagger",
                        },
                    )

                self.assertEqual(result["encounter_id"], "enc_preview_demo")
                self.assertEqual(result["encounter_state"]["encounter_id"], "enc_preview_demo")
                _, kwargs = mocked_execute.call_args
                self.assertEqual(kwargs["actor_id"], "ent_ally_wizard_001")
                self.assertEqual(kwargs["target_id"], "ent_enemy_brute_001")
                self.assertEqual(kwargs["weapon_id"], "dagger")
                self.assertTrue(kwargs["include_encounter_state"])
            finally:
                context.close()


if __name__ == "__main__":
    unittest.main()
