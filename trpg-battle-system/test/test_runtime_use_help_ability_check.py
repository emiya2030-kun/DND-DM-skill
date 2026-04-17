import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.commands import COMMAND_HANDLERS
from runtime.context import build_runtime_context
from runtime.dispatcher import execute_runtime_command
from test.test_use_help_ability_check import build_encounter


class RuntimeUseHelpAbilityCheckTests(unittest.TestCase):
    def test_command_handlers_include_use_help_ability_check(self) -> None:
        self.assertIn("use_help_ability_check", COMMAND_HANDLERS)

    def test_use_help_ability_check_runs_and_returns_encounter_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                context.encounter_repository.save(build_encounter())
                module = __import__("runtime.commands.use_help_ability_check", fromlist=["use_help_ability_check"])

                with patch.object(
                    module.UseHelpAbilityCheck,
                    "execute",
                    return_value={
                        "encounter_id": "enc_help_check_test",
                        "actor_id": "ent_actor_001",
                        "ally_id": "ent_ally_001",
                        "encounter_state": {"encounter_id": "enc_help_check_test"},
                    },
                ) as mocked_execute:
                    result = execute_runtime_command(
                        context,
                        command="use_help_ability_check",
                        args={
                            "encounter_id": "enc_help_check_test",
                            "actor_id": "ent_actor_001",
                            "ally_id": "ent_ally_001",
                            "check_type": "skill",
                            "check_key": "investigation",
                        },
                        handlers=COMMAND_HANDLERS,
                    )

                self.assertTrue(result["ok"])
                self.assertEqual(result["encounter_state"]["encounter_id"], "enc_help_check_test")
                _, kwargs = mocked_execute.call_args
                self.assertEqual(kwargs["encounter_id"], "enc_help_check_test")
                self.assertEqual(kwargs["actor_id"], "ent_actor_001")
                self.assertEqual(kwargs["ally_id"], "ent_ally_001")
                self.assertEqual(kwargs["check_type"], "skill")
                self.assertEqual(kwargs["check_key"], "investigation")
            finally:
                context.close()
