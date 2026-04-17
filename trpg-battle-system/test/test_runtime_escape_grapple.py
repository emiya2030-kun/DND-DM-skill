import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.commands import COMMAND_HANDLERS
from runtime.context import build_runtime_context
from runtime.dispatcher import execute_runtime_command
from test.test_escape_grapple import build_escape_encounter


class RuntimeEscapeGrappleTests(unittest.TestCase):
    def test_command_handlers_include_escape_grapple(self) -> None:
        self.assertIn("escape_grapple", COMMAND_HANDLERS)

    def test_escape_grapple_runs_and_returns_encounter_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                context.encounter_repository.save(build_escape_encounter())
                module = __import__("runtime.commands.escape_grapple", fromlist=["escape_grapple"])

                with patch.object(
                    module.EscapeGrapple,
                    "execute",
                    return_value={
                        "encounter_id": "enc_escape_test",
                        "actor_id": "ent_target_001",
                        "encounter_state": {"encounter_id": "enc_escape_test"},
                    },
                ) as mocked_execute:
                    result = execute_runtime_command(
                        context,
                        command="escape_grapple",
                        args={
                            "encounter_id": "enc_escape_test",
                            "actor_id": "ent_target_001",
                        },
                        handlers=COMMAND_HANDLERS,
                    )

                self.assertTrue(result["ok"])
                self.assertEqual(result["encounter_state"]["encounter_id"], "enc_escape_test")
                _, kwargs = mocked_execute.call_args
                self.assertEqual(kwargs["encounter_id"], "enc_escape_test")
                self.assertEqual(kwargs["actor_id"], "ent_target_001")
            finally:
                context.close()
