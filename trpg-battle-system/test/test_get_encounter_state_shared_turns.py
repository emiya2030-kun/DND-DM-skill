from __future__ import annotations

import tempfile
from pathlib import Path

from tools.repositories import EncounterRepository
from tools.services import GetEncounterState
from test.test_use_help_attack import build_encounter, build_shared_turn_summon


def test_get_encounter_state_projects_current_turn_group_for_owner_and_summon() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = build_encounter()
        summon = build_shared_turn_summon()
        encounter.entities[summon.entity_id] = summon
        repo.save(encounter)

        state = GetEncounterState(repo).execute("enc_help_attack_test")

        assert state["current_turn_group"]["owner_entity_id"] == "ent_actor_001"
        assert [item["name"] for item in state["current_turn_group"]["controlled_members"]] == [
            "Sabur",
            "Sphinx of Wonder",
        ]

        repo.close()
