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
from tools.services.class_features.sorcerer import UseSorcerousRestoration


def build_sorcerer() -> EncounterEntity:
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
        proficiency_bonus=3,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        class_features={
            "sorcerer": {
                "level": 6,
                "sorcery_points": {"current": 1, "max": 6},
                "sorcerous_restoration": {"enabled": True, "used_since_long_rest": False},
            }
        },
    )


def build_encounter() -> Encounter:
    sorcerer = build_sorcerer()
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


def test_use_sorcerous_restoration_recovers_half_level_sorcery_points_once_per_long_rest() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        repo.save(build_encounter())

        result = UseSorcerousRestoration(repo).execute(
            encounter_id="enc_sorc_001",
            actor_id="ent_sorc_001",
        )

        assert result["class_feature_result"]["sorcerous_restoration"]["restored_points"] == 3
        assert result["class_feature_result"]["sorcerous_restoration"]["used_since_long_rest"] is True
        updated = repo.get("enc_sorc_001")
        assert updated is not None
        assert updated.entities["ent_sorc_001"].class_features["sorcerer"]["sorcery_points"]["current"] == 4
        repo.close()


def test_use_sorcerous_restoration_rejects_repeat_use_in_same_long_rest_cycle() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = build_encounter()
        encounter.entities["ent_sorc_001"].class_features["sorcerer"]["sorcerous_restoration"]["used_since_long_rest"] = True
        repo.save(encounter)

        with pytest.raises(ValueError, match="sorcerous_restoration_already_used"):
            UseSorcerousRestoration(repo).execute(
                encounter_id="enc_sorc_001",
                actor_id="ent_sorc_001",
            )

        repo.close()
