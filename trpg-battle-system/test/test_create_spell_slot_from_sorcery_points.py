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
from tools.services.class_features.shared import ensure_spell_slots_runtime
from tools.services.class_features.sorcerer import CreateSpellSlotFromSorceryPoints


def build_sorcerer() -> EncounterEntity:
    entity = EncounterEntity(
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
        class_features={"sorcerer": {"level": 5, "sorcery_points": {"current": 5, "max": 5}}},
    )
    ensure_spell_slots_runtime(entity)
    return entity


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


def test_create_spell_slot_from_sorcery_points_spends_bonus_action_and_tracks_created_slot() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        repo.save(build_encounter())

        result = CreateSpellSlotFromSorceryPoints(repo).execute(
            encounter_id="enc_sorc_001",
            actor_id="ent_sorc_001",
            slot_level=3,
        )

        assert result["class_feature_result"]["font_of_magic"]["sorcery_points_after"] == 0
        assert result["class_feature_result"]["font_of_magic"]["created_slot_level"] == 3
        updated = repo.get("enc_sorc_001")
        assert updated is not None
        assert updated.entities["ent_sorc_001"].resources["spell_slots"]["3"]["remaining"] == 3
        assert updated.entities["ent_sorc_001"].class_features["sorcerer"]["created_spell_slots"]["3"] == 1
        assert updated.entities["ent_sorc_001"].action_economy["bonus_action_used"] is True
        repo.close()


def test_create_spell_slot_from_sorcery_points_rejects_invalid_level() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        repo.save(build_encounter())

        with pytest.raises(ValueError, match="invalid_created_spell_slot_level"):
            CreateSpellSlotFromSorceryPoints(repo).execute(
                encounter_id="enc_sorc_001",
                actor_id="ent_sorc_001",
                slot_level=6,
            )

        repo.close()


def test_create_spell_slot_from_sorcery_points_rejects_when_points_insufficient() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = build_encounter()
        encounter.entities["ent_sorc_001"].class_features["sorcerer"]["sorcery_points"] = {"current": 2, "max": 5}
        repo.save(encounter)

        with pytest.raises(ValueError, match="insufficient_sorcery_points"):
            CreateSpellSlotFromSorceryPoints(repo).execute(
                encounter_id="enc_sorc_001",
                actor_id="ent_sorc_001",
                slot_level=3,
            )

        repo.close()
