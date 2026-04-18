import tempfile
import unittest
from pathlib import Path

from runtime.commands import COMMAND_HANDLERS
from runtime.context import build_runtime_context
from runtime.dispatcher import execute_runtime_command


class RuntimeDispatcherTests(unittest.TestCase):
    def test_command_handlers_include_execute_ability_check(self) -> None:
        self.assertIn("execute_ability_check", COMMAND_HANDLERS)

    def test_command_handlers_include_execute_attack(self) -> None:
        self.assertIn("execute_attack", COMMAND_HANDLERS)

    def test_command_handlers_include_move_entity(self) -> None:
        self.assertIn("move_entity", COMMAND_HANDLERS)

    def test_unknown_command_returns_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                result = execute_runtime_command(
                    context,
                    command="unknown_command",
                    args={"encounter_id": "enc_test"},
                )

                self.assertFalse(result["ok"])
                self.assertEqual(result["command"], "unknown_command")
                self.assertEqual(result["error_code"], "unknown_command")
                self.assertEqual(result["result"], None)
            finally:
                context.close()

    def test_dispatcher_wraps_success_payload_and_encounter_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                def fake_handler(ctx, args):
                    self.assertIs(ctx, context)
                    self.assertEqual(args["encounter_id"], "enc_test")
                    return {
                        "encounter_id": "enc_test",
                        "result": {"message": "ok"},
                        "encounter_state": {"encounter_id": "enc_test", "round": 1},
                    }

                result = execute_runtime_command(
                    context,
                    command="test_command",
                    args={"encounter_id": "enc_test"},
                    handlers={"test_command": fake_handler},
                )

                self.assertTrue(result["ok"])
                self.assertEqual(result["result"]["message"], "ok")
                self.assertEqual(result["encounter_state"]["encounter_id"], "enc_test")
            finally:
                context.close()

    def test_value_error_returns_encounter_state_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                expected_state = {"encounter_id": "enc_test", "round": 42}
                context.get_encounter_state = lambda _: expected_state

                def handler(ctx, args):
                    raise ValueError("handler failure")

                result = execute_runtime_command(
                    context,
                    command="test_command",
                    args={"encounter_id": "enc_test"},
                    handlers={"test_command": handler},
                )

                self.assertFalse(result["ok"])
                self.assertEqual(result["error_code"], "handler failure")
                self.assertEqual(result["encounter_state"], expected_state)
            finally:
                context.close()

    def test_value_error_encounter_state_lookup_failure_is_null(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                def failing_lookup(_: str):
                    raise ValueError("missing encounter")

                context.get_encounter_state = failing_lookup

                def handler(ctx, args):
                    raise ValueError("handler failure")

                result = execute_runtime_command(
                    context,
                    command="test_command",
                    args={"encounter_id": "enc_test"},
                    handlers={"test_command": handler},
                )

                self.assertFalse(result["ok"])
                self.assertEqual(result["encounter_state"], None)
            finally:
                context.close()

    def test_invalid_handler_response_becomes_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                def handler(ctx, args):
                    return None

                result = execute_runtime_command(
                    context,
                    command="test_command",
                    args={"encounter_id": "enc_test"},
                    handlers={"test_command": handler},
                )

                self.assertFalse(result["ok"])
                self.assertEqual(result["error_code"], "invalid_handler_response")
                self.assertIsNone(result["encounter_state"])
            finally:
                context.close()
