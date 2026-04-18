from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository
from tools.services.class_features.warlock import UseContactPatron


def build_warlock(*, level: int = 9) -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_warlock_001",
        name="Warlock",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 14, "max": 14, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=14,
        class_features={"warlock": {"level": level}},
    )


def build_encounter(*, level: int = 9) -> Encounter:
    warlock = build_warlock(level=level)
    return Encounter(
        encounter_id="enc_use_contact_patron_test",
        name="Use Contact Patron Test",
        status="active",
        round=1,
        current_entity_id=warlock.entity_id,
        turn_order=[warlock.entity_id],
        entities={warlock.entity_id: warlock},
        map=EncounterMap(
            map_id="map_use_contact_patron_test",
            name="Use Contact Patron Test Map",
            description="A small room.",
            width=8,
            height=8,
        ),
    )


def test_execute_consumes_free_cast_and_returns_summary() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        repo.save(build_encounter(level=9))

        result = UseContactPatron(repo).execute(
            encounter_id="enc_use_contact_patron_test",
            actor_id="ent_warlock_001",
        )

        updated = repo.get("enc_use_contact_patron_test")
        assert updated is not None
        assert updated.entities["ent_warlock_001"].class_features["warlock"]["contact_patron"]["free_cast_available"] is False
        assert result["class_feature_result"]["contact_patron"]["spell_id"] == "contact_other_plane"
        assert result["class_feature_result"]["contact_patron"]["auto_succeeds_save"] is True
        repo.close()


def test_execute_rejects_when_unavailable() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = build_encounter(level=9)
        encounter.entities["ent_warlock_001"].class_features["warlock"]["contact_patron"] = {
            "enabled": True,
            "free_cast_available": False,
        }
        repo.save(encounter)

        with pytest.raises(ValueError, match="contact_patron_unavailable"):
            UseContactPatron(repo).execute(
                encounter_id="enc_use_contact_patron_test",
                actor_id="ent_warlock_001",
            )

        repo.close()
