from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository
from tools.services import AppendEvent, GrantTemporaryHp


def build_target(*, temp_hp: int = 0, current_hp: int = 10) -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_target_001",
        name="Target",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": current_hp, "max": 20, "temp": temp_hp},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
    )


def build_encounter(*, temp_hp: int = 0, current_hp: int = 10) -> Encounter:
    target = build_target(temp_hp=temp_hp, current_hp=current_hp)
    return Encounter(
        encounter_id="enc_grant_temp_hp_test",
        name="Grant Temporary HP Test",
        status="active",
        round=1,
        current_entity_id=target.entity_id,
        turn_order=[target.entity_id],
        entities={target.entity_id: target},
        map=EncounterMap(
            map_id="map_grant_temp_hp_test",
            name="Grant Temporary HP Test Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
    )


class GrantTemporaryHpTests(unittest.TestCase):
    def test_execute_sets_temp_hp_when_target_has_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            result = GrantTemporaryHp(encounter_repo, AppendEvent(event_repo)).execute(
                encounter_id="enc_grant_temp_hp_test",
                target_id="ent_target_001",
                temp_hp_amount=8,
                reason="test_source",
            )

            updated = encounter_repo.get("enc_grant_temp_hp_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_target_001"].hp["temp"], 8)
            self.assertEqual(result["temp_hp_before"], 0)
            self.assertEqual(result["temp_hp_after"], 8)
            self.assertEqual(result["decision"], "replace")
            encounter_repo.close()
            event_repo.close()

    def test_execute_auto_higher_keeps_existing_higher_temp_hp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter(temp_hp=10))

            result = GrantTemporaryHp(encounter_repo, AppendEvent(event_repo)).execute(
                encounter_id="enc_grant_temp_hp_test",
                target_id="ent_target_001",
                temp_hp_amount=8,
                reason="test_source",
            )

            updated = encounter_repo.get("enc_grant_temp_hp_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_target_001"].hp["temp"], 10)
            self.assertEqual(result["temp_hp_before"], 10)
            self.assertEqual(result["temp_hp_after"], 10)
            self.assertEqual(result["decision"], "kept_existing")
            encounter_repo.close()
            event_repo.close()

    def test_execute_replace_mode_overrides_existing_temp_hp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter(temp_hp=10))

            result = GrantTemporaryHp(encounter_repo, AppendEvent(event_repo)).execute(
                encounter_id="enc_grant_temp_hp_test",
                target_id="ent_target_001",
                temp_hp_amount=8,
                reason="test_source",
                mode="replace",
            )

            updated = encounter_repo.get("enc_grant_temp_hp_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_target_001"].hp["temp"], 8)
            self.assertEqual(result["decision"], "replace")
            encounter_repo.close()
            event_repo.close()

    def test_execute_does_not_revive_zero_hp_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter(current_hp=0))

            result = GrantTemporaryHp(encounter_repo, AppendEvent(event_repo)).execute(
                encounter_id="enc_grant_temp_hp_test",
                target_id="ent_target_001",
                temp_hp_amount=7,
                reason="test_source",
            )

            updated = encounter_repo.get("enc_grant_temp_hp_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_target_001"].hp["current"], 0)
            self.assertEqual(updated.entities["ent_target_001"].hp["temp"], 7)
            self.assertEqual(result["current_hp_after"], 0)
            encounter_repo.close()
            event_repo.close()
