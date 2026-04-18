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
from tools.services.class_features.sorcerer import UseInnateSorcery


def build_sorcerer(*, level: int = 3) -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_sorc_001",
        name="Sorcerer",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=14,
        proficiency_bonus=3 if level >= 5 else 2,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        class_features={"sorcerer": {"level": level}},
    )


def build_encounter(*, level: int = 3) -> Encounter:
    sorcerer = build_sorcerer(level=level)
    return Encounter(
        encounter_id="enc_sorc_001",
        name="Sorcerer Test",
        status="active",
        round=1,
        current_entity_id=sorcerer.entity_id,
        turn_order=[sorcerer.entity_id],
        entities={sorcerer.entity_id: sorcerer},
        map=EncounterMap(
            map_id="map_sorc_001",
            name="Sorcerer Test Map",
            description="A small room.",
            width=8,
            height=8,
        ),
    )


def test_use_innate_sorcery_spends_bonus_action_and_consumes_use() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        repo.save(build_encounter(level=3))

        result = UseInnateSorcery(repo).execute(
            encounter_id="enc_sorc_001",
            actor_id="ent_sorc_001",
        )

        updated = repo.get("enc_sorc_001")
        assert updated is not None
        innate = updated.entities["ent_sorc_001"].class_features["sorcerer"]["innate_sorcery"]
        assert innate["active"] is True
        assert innate["uses_current"] == 1
        assert result["class_feature_result"]["innate_sorcery"]["active"] is True
        assert updated.entities["ent_sorc_001"].action_economy["bonus_action_used"] is True
        repo.close()


def test_use_innate_sorcery_allows_level_seven_to_spend_sorcery_points_when_uses_exhausted() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = build_encounter(level=7)
        encounter.entities["ent_sorc_001"].class_features["sorcerer"]["innate_sorcery"] = {
            "enabled": True,
            "uses_max": 2,
            "uses_current": 0,
            "active": False,
        }
        encounter.entities["ent_sorc_001"].class_features["sorcerer"]["sorcery_points"] = {"current": 7, "max": 7}
        repo.save(encounter)

        result = UseInnateSorcery(repo).execute(
            encounter_id="enc_sorc_001",
            actor_id="ent_sorc_001",
        )

        assert result["class_feature_result"]["innate_sorcery"]["used_sorcery_points"] is True
        updated = repo.get("enc_sorc_001")
        assert updated is not None
        assert updated.entities["ent_sorc_001"].class_features["sorcerer"]["sorcery_points"]["current"] == 5
        repo.close()


def test_use_innate_sorcery_rejects_when_no_uses_remaining_below_level_seven() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = build_encounter(level=3)
        encounter.entities["ent_sorc_001"].class_features["sorcerer"]["innate_sorcery"] = {
            "enabled": True,
            "uses_max": 2,
            "uses_current": 0,
            "active": False,
        }
        repo.save(encounter)

        with pytest.raises(ValueError, match="innate_sorcery_no_uses_remaining"):
            UseInnateSorcery(repo).execute(
                encounter_id="enc_sorc_001",
                actor_id="ent_sorc_001",
            )

        repo.close()
