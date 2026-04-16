import tempfile
import unittest
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

from runtime.commands.end_turn_and_advance import end_turn_and_advance
from runtime.context import build_runtime_context
from scripts.run_battlemap_localhost import ensure_preview_encounter


class RuntimeEndTurnAndAdvanceTests(unittest.TestCase):
    def test_runs_end_advance_start_and_returns_new_current_entity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                ensure_preview_encounter(context.encounter_repository)

                result = end_turn_and_advance(context, {"encounter_id": "enc_preview_demo"})

                self.assertIn("ended_entity_id", result["result"])
                self.assertIn("current_entity_id", result["result"])
                self.assertEqual(
                    result["encounter_state"]["current_turn_entity"]["id"],
                    result["result"]["current_entity_id"],
                )
            finally:
                context.close()

    def test_turn_effect_resolutions_come_from_turn_services(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                ensure_preview_encounter(context.encounter_repository)
                command_module = import_module("runtime.commands.end_turn_and_advance")
                end_resolutions = [{"source": "end"}]
                start_resolutions = [{"source": "start"}]

                with patch.object(
                    command_module.EndTurn,
                    "execute_with_state",
                    return_value={"turn_effect_resolutions": end_resolutions, "encounter_state": {}},
                ):
                    with patch.object(command_module.AdvanceTurn, "execute", return_value=None):
                        with patch.object(
                            command_module.StartTurn,
                            "execute_with_state",
                            return_value={"turn_effect_resolutions": start_resolutions, "encounter_state": {}},
                        ):
                            result = command_module.end_turn_and_advance(
                                context, {"encounter_id": "enc_preview_demo"}
                            )

                self.assertEqual(
                    result["result"]["turn_effect_resolutions"],
                    end_resolutions + start_resolutions,
                )
            finally:
                context.close()
