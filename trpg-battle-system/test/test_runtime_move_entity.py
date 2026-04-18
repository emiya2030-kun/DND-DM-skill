import tempfile
import unittest
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

from runtime.context import build_runtime_context
from scripts.run_battlemap_localhost import ensure_preview_encounter


class RuntimeMoveEntityTests(unittest.TestCase):
    def test_returns_waiting_reaction_when_move_is_interrupted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                ensure_preview_encounter(context.encounter_repository)
                move_entity_module = import_module("runtime.commands.move_entity")

                with patch.object(
                    move_entity_module.BeginMoveEncounterEntity,
                    "execute_with_state",
                    return_value={
                        "encounter_id": "enc_preview_demo",
                        "entity_id": "ent_enemy_brute_001",
                        "movement_status": "waiting_reaction",
                        "reaction_requests": [{"request_id": "react_001"}],
                        "encounter_state": {
                            "encounter_id": "enc_preview_demo",
                            "reaction_requests": [{"request_id": "react_001"}],
                        },
                    },
                ) as mocked_move:
                    result = move_entity_module.move_entity(
                        context,
                        {
                            "encounter_id": "enc_preview_demo",
                            "actor_id": "ent_enemy_brute_001",
                            "target_position": {"x": 11, "y": 10},
                            "movement_mode": "fly",
                        },
                    )

                self.assertEqual(result["result"]["movement_status"], "waiting_reaction")
                mocked_move.assert_called_once_with(
                    encounter_id="enc_preview_demo",
                    entity_id="ent_enemy_brute_001",
                    target_position={"x": 11, "y": 10},
                    use_dash=False,
                    movement_mode="fly",
                )
            finally:
                context.close()

    def test_returns_completed_move_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                ensure_preview_encounter(context.encounter_repository)
                move_entity_module = import_module("runtime.commands.move_entity")

                with patch.object(
                    move_entity_module.BeginMoveEncounterEntity,
                    "execute_with_state",
                    return_value={
                        "encounter_id": "enc_preview_demo",
                        "entity_id": "ent_ally_ranger_001",
                        "movement_status": "completed",
                        "reaction_requests": [],
                        "encounter_state": {"encounter_id": "enc_preview_demo"},
                    },
                ):
                    result = move_entity_module.move_entity(
                        context,
                        {
                            "encounter_id": "enc_preview_demo",
                            "actor_id": "ent_ally_ranger_001",
                            "target_position": {"x": 8, "y": 10},
                        },
                    )

                self.assertEqual(result["encounter_id"], "enc_preview_demo")
                self.assertEqual(result["result"]["movement_status"], "completed")
                self.assertEqual(result["encounter_state"]["encounter_id"], "enc_preview_demo")
            finally:
                context.close()

    def test_raises_value_error_when_required_field_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = build_runtime_context(data_dir=Path(tmp_dir))
            try:
                ensure_preview_encounter(context.encounter_repository)
                move_entity_module = import_module("runtime.commands.move_entity")

                with self.assertRaisesRegex(ValueError, "target_position is required"):
                    move_entity_module.move_entity(
                        context,
                        {
                            "encounter_id": "enc_preview_demo",
                            "actor_id": "ent_ally_ranger_001",
                        },
                    )
            finally:
                context.close()


if __name__ == "__main__":
    unittest.main()
