import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.commands import COMMAND_HANDLERS
from runtime.context import build_runtime_context
from runtime.dispatcher import execute_runtime_command
from test.test_use_disengage import build_encounter


class RuntimeUseDisengageTests(unittest.TestCase):
    def test_command_handlers_include_use_disengage(self) -> None:
        self.assertIn("use_disengage", COMMAND_HANDLERS)

    def test_use_disengage_runs_and_returns_encounter_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                context.encounter_repository.save(build_encounter())
                module = __import__("runtime.commands.use_disengage", fromlist=["use_disengage"])

                with patch.object(
                    module.UseDisengage,
                    "execute",
                    return_value={
                        "encounter_id": "enc_disengage_test",
                        "actor_id": "ent_actor_001",
                        "encounter_state": {"encounter_id": "enc_disengage_test"},
                    },
                ) as mocked_execute:
                    result = execute_runtime_command(
                        context,
                        command="use_disengage",
                        args={
                            "encounter_id": "enc_disengage_test",
                            "actor_id": "ent_actor_001",
                        },
                        handlers=COMMAND_HANDLERS,
                    )

                self.assertTrue(result["ok"])
                self.assertEqual(result["encounter_state"]["encounter_id"], "enc_disengage_test")
                _, kwargs = mocked_execute.call_args
                self.assertEqual(kwargs["encounter_id"], "enc_disengage_test")
                self.assertEqual(kwargs["actor_id"], "ent_actor_001")
            finally:
                context.close()
