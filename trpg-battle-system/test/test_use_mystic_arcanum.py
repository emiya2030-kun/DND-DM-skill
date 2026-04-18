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
from tools.services.class_features.warlock import UseMysticArcanum


def build_warlock(*, level: int = 13) -> EncounterEntity:
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


def build_encounter(*, level: int = 13) -> Encounter:
    warlock = build_warlock(level=level)
    return Encounter(
        encounter_id="enc_use_mystic_arcanum_test",
        name="Use Mystic Arcanum Test",
        status="active",
        round=1,
        current_entity_id=warlock.entity_id,
        turn_order=[warlock.entity_id],
        entities={warlock.entity_id: warlock},
        map=EncounterMap(
            map_id="map_use_mystic_arcanum_test",
            name="Use Mystic Arcanum Test Map",
            description="A small room.",
            width=8,
            height=8,
        ),
    )


def test_execute_consumes_matching_arcanum_use() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        repo.save(build_encounter(level=13))

        result = UseMysticArcanum(repo).execute(
            encounter_id="enc_use_mystic_arcanum_test",
            actor_id="ent_warlock_001",
            spell_level=7,
            spell_id="plane_shift",
        )

        updated = repo.get("enc_use_mystic_arcanum_test")
        assert updated is not None
        assert updated.entities["ent_warlock_001"].class_features["warlock"]["mystic_arcanum"]["7"]["remaining_uses"] == 0
        assert result["class_feature_result"]["mystic_arcanum"]["spell_level"] == 7
        assert result["class_feature_result"]["mystic_arcanum"]["spell_id"] == "plane_shift"
        repo.close()


def test_execute_rejects_when_tier_not_unlocked() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        repo.save(build_encounter(level=11))

        with pytest.raises(ValueError, match="mystic_arcanum_not_available"):
            UseMysticArcanum(repo).execute(
                encounter_id="enc_use_mystic_arcanum_test",
                actor_id="ent_warlock_001",
                spell_level=7,
            )

        repo.close()
