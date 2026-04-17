import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.commands import COMMAND_HANDLERS
from runtime.context import build_runtime_context
from runtime.dispatcher import execute_runtime_command
from test.test_use_grapple import build_grapple_encounter


class RuntimeUseGrappleTests(unittest.TestCase):
    def test_command_handlers_include_use_grapple(self) -> None:
        self.assertIn("use_grapple", COMMAND_HANDLERS)

    def test_use_grapple_runs_and_returns_encounter_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                context.encounter_repository.save(build_grapple_encounter())
                module = __import__("runtime.commands.use_grapple", fromlist=["use_grapple"])

                with patch.object(
                    module.UseGrapple,
                    "execute",
                    return_value={
                        "encounter_id": "enc_grapple_test",
                        "actor_id": "ent_actor_001",
                        "target_id": "ent_target_001",
                        "encounter_state": {"encounter_id": "enc_grapple_test"},
                    },
                ) as mocked_execute:
                    result = execute_runtime_command(
                        context,
                        command="use_grapple",
                        args={
                            "encounter_id": "enc_grapple_test",
                            "actor_id": "ent_actor_001",
                            "target_id": "ent_target_001",
                        },
                        handlers=COMMAND_HANDLERS,
                    )

                self.assertTrue(result["ok"])
                self.assertEqual(result["encounter_state"]["encounter_id"], "enc_grapple_test")
                _, kwargs = mocked_execute.call_args
                self.assertEqual(kwargs["encounter_id"], "enc_grapple_test")
                self.assertEqual(kwargs["actor_id"], "ent_actor_001")
                self.assertEqual(kwargs["target_id"], "ent_target_001")
            finally:
                context.close()
