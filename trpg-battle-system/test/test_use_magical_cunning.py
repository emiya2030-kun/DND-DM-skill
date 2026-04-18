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
from tools.services.class_features.warlock import UseMagicalCunning


def build_warlock(*, level: int = 2) -> EncounterEntity:
    entity = EncounterEntity(
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
        proficiency_bonus=2,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        class_features={"warlock": {"level": level}},
    )
    ensure_spell_slots_runtime(entity)
    return entity


def build_encounter(*, level: int = 2) -> Encounter:
    warlock = build_warlock(level=level)
    return Encounter(
        encounter_id="enc_use_magical_cunning_test",
        name="Use Magical Cunning Test",
        status="active",
        round=1,
        current_entity_id=warlock.entity_id,
        turn_order=[warlock.entity_id],
        entities={warlock.entity_id: warlock},
        map=EncounterMap(
            map_id="map_use_magical_cunning_test",
            name="Use Magical Cunning Test Map",
            description="A small room.",
            width=8,
            height=8,
        ),
    )


def test_execute_restores_half_expended_pact_magic_slots_rounded_up() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = build_encounter(level=5)
        encounter.entities["ent_warlock_001"].resources["pact_magic_slots"]["remaining"] = 0
        repo.save(encounter)

        result = UseMagicalCunning(repo).execute(
            encounter_id="enc_use_magical_cunning_test",
            actor_id="ent_warlock_001",
        )

        updated = repo.get("enc_use_magical_cunning_test")
        assert updated is not None
        assert updated.entities["ent_warlock_001"].resources["pact_magic_slots"]["remaining"] == 1
        assert result["class_feature_result"]["magical_cunning"]["restored_slots"] == 1
        assert result["class_feature_result"]["magical_cunning"]["remaining_slots"] == 1
        repo.close()


def test_execute_restores_all_slots_for_eldritch_master() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = build_encounter(level=20)
        encounter.entities["ent_warlock_001"].resources["pact_magic_slots"]["remaining"] = 0
        repo.save(encounter)

        result = UseMagicalCunning(repo).execute(
            encounter_id="enc_use_magical_cunning_test",
            actor_id="ent_warlock_001",
        )

        updated = repo.get("enc_use_magical_cunning_test")
        assert updated is not None
        assert updated.entities["ent_warlock_001"].resources["pact_magic_slots"]["remaining"] == 4
        assert result["class_feature_result"]["magical_cunning"]["restored_slots"] == 4
        repo.close()


def test_execute_rejects_when_feature_already_used() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = build_encounter(level=5)
        encounter.entities["ent_warlock_001"].class_features["warlock"]["magical_cunning"] = {
            "enabled": True,
            "available": False,
        }
        repo.save(encounter)

        with pytest.raises(ValueError, match="magical_cunning_unavailable"):
            UseMagicalCunning(repo).execute(
                encounter_id="enc_use_magical_cunning_test",
                actor_id="ent_warlock_001",
            )

        repo.close()
