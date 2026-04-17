import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.commands import COMMAND_HANDLERS
from runtime.context import build_runtime_context
from runtime.dispatcher import execute_runtime_command
from test.test_ability_check_request import build_encounter


class RuntimeExecuteAbilityCheckTests(unittest.TestCase):
    def test_command_handlers_include_execute_ability_check(self) -> None:
        self.assertIn("execute_ability_check", COMMAND_HANDLERS)

    def test_execute_ability_check_runs_and_returns_encounter_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                context.encounter_repository.save(build_encounter())
                module = __import__("runtime.commands.execute_ability_check", fromlist=["execute_ability_check"])

                with patch.object(
                    module.ExecuteAbilityCheck,
                    "execute",
                    return_value={
                        "encounter_id": "enc_ability_check_test",
                        "actor_id": "ent_ally_sabur_001",
                        "normalized_check": "stealth",
                        "success": True,
                        "encounter_state": {"encounter_id": "enc_ability_check_test"},
                    },
                ) as mocked_execute:
                    result = execute_runtime_command(
                        context,
                        command="execute_ability_check",
                        args={
                            "encounter_id": "enc_ability_check_test",
                            "actor_id": "ent_ally_sabur_001",
                            "check_type": "skill",
                            "check": "隐匿",
                            "dc": 15,
                        },
                        handlers=COMMAND_HANDLERS,
                    )

                self.assertTrue(result["ok"])
                self.assertEqual(result["result"]["normalized_check"], "stealth")
                self.assertEqual(result["encounter_state"]["encounter_id"], "enc_ability_check_test")
                _, kwargs = mocked_execute.call_args
                self.assertEqual(kwargs["check_type"], "skill")
                self.assertEqual(kwargs["check"], "隐匿")
                self.assertEqual(kwargs["dc"], 15)
                self.assertTrue(kwargs["include_encounter_state"])
            finally:
                context.close()


if __name__ == "__main__":
    unittest.main()
