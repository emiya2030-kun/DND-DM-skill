from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository
from tools.services import AppendEvent
from tools.services.class_features.shared import ensure_druid_runtime
from tools.services.class_features.druid import UseWildShape


def _build_druid() -> EncounterEntity:
    druid = EncounterEntity(
        entity_id="ent_druid_001",
        name="Druid",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 22, "max": 22, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=14,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        class_features={"druid": {"level": 6}},
    )
    ensure_druid_runtime(druid)
    return druid


def _build_encounter() -> Encounter:
    druid = _build_druid()
    return Encounter(
        encounter_id="enc_druid_test",
        name="Druid Test Encounter",
        status="active",
        round=1,
        current_entity_id=druid.entity_id,
        turn_order=[druid.entity_id],
        entities={druid.entity_id: druid},
        map=EncounterMap(
            map_id="map_druid_test",
            name="Druid Grove",
            description="A small grove.",
            width=8,
            height=8,
        ),
    )


def test_use_wild_shape_consumes_use_and_marks_active_form() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        append_event = AppendEvent(event_repo)
        repo.save(_build_encounter())

        result = UseWildShape(repo, append_event).execute(
            encounter_id="enc_druid_test",
            actor_id="ent_druid_001",
            form_name="Wolf",
        )

        updated = repo.get("enc_druid_test")
        assert updated is not None
        druid = updated.entities["ent_druid_001"]
        wild_shape = druid.class_features["druid"]["wild_shape"]
        assert wild_shape["remaining_uses"] == 2
        assert wild_shape["active"] is True
        assert wild_shape["active_form_name"] == "Wolf"
        assert wild_shape["active_temp_hp"] == 6
        assert druid.hp["temp"] == 6
        assert druid.action_economy["bonus_action_used"] is True
        assert result["class_feature_result"]["wild_shape"]["active_form_name"] == "Wolf"

        events = append_event.list_by_encounter("enc_druid_test")
        assert events[-1].event_type == "class_feature_wild_shape_used"
        assert events[-1].payload["class_feature_id"] == "druid.wild_shape"

        repo.close()
        event_repo.close()


def test_use_wild_shape_rejects_when_no_remaining_uses() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        append_event = AppendEvent(event_repo)
        encounter = _build_encounter()
        encounter.entities["ent_druid_001"].class_features["druid"]["wild_shape"]["remaining_uses"] = 0
        repo.save(encounter)

        with pytest.raises(ValueError, match="wild_shape_no_remaining_uses"):
            UseWildShape(repo, append_event).execute(
                encounter_id="enc_druid_test",
                actor_id="ent_druid_001",
                form_name="Wolf",
            )

        repo.close()
        event_repo.close()


def test_use_wild_shape_rejects_when_already_active() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        append_event = AppendEvent(event_repo)
        encounter = _build_encounter()
        encounter.entities["ent_druid_001"].class_features["druid"]["wild_shape"]["active"] = True
        encounter.entities["ent_druid_001"].class_features["druid"]["wild_shape"]["active_form_name"] = "Bear"
        repo.save(encounter)

        with pytest.raises(ValueError, match="wild_shape_already_active"):
            UseWildShape(repo, append_event).execute(
                encounter_id="enc_druid_test",
                actor_id="ent_druid_001",
                form_name="Wolf",
            )

        repo.close()
        event_repo.close()
