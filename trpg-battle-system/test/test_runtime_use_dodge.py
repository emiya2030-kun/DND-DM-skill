import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.commands import COMMAND_HANDLERS
from runtime.context import build_runtime_context
from runtime.dispatcher import execute_runtime_command
from test.test_use_dodge import build_encounter


class RuntimeUseDodgeTests(unittest.TestCase):
    def test_command_handlers_include_use_dodge(self) -> None:
        self.assertIn("use_dodge", COMMAND_HANDLERS)

    def test_use_dodge_runs_and_returns_encounter_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                context.encounter_repository.save(build_encounter())
                module = __import__("runtime.commands.use_dodge", fromlist=["use_dodge"])

                with patch.object(
                    module.UseDodge,
                    "execute",
                    return_value={
                        "encounter_id": "enc_dodge_test",
                        "actor_id": "ent_actor_001",
                        "encounter_state": {"encounter_id": "enc_dodge_test"},
                    },
                ) as mocked_execute:
                    result = execute_runtime_command(
                        context,
                        command="use_dodge",
                        args={
                            "encounter_id": "enc_dodge_test",
                            "actor_id": "ent_actor_001",
                        },
                        handlers=COMMAND_HANDLERS,
                    )

                self.assertTrue(result["ok"])
                self.assertEqual(result["encounter_state"]["encounter_id"], "enc_dodge_test")
                _, kwargs = mocked_execute.call_args
                self.assertEqual(kwargs["encounter_id"], "enc_dodge_test")
                self.assertEqual(kwargs["actor_id"], "ent_actor_001")
            finally:
                context.close()
