"""Barbarian rage runtime 与 use_rage 服务测试。"""

import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository
from tools.services.class_features.barbarian import UseRage, ensure_barbarian_runtime


def build_barbarian(*, level: int = 13) -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_barbarian_001",
        name="Barbarian",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 28, "max": 28, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=14,
        proficiency_bonus=3,
        ability_scores={"str": 18, "dex": 14, "con": 16},
        ability_mods={"str": 4, "dex": 2, "con": 3},
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        class_features={
            "barbarian": {
                "level": level,
            }
        },
    )


def build_barbarian_encounter(*, level: int = 1) -> Encounter:
    barbarian = build_barbarian(level=level)
    return Encounter(
        encounter_id="enc_barbarian_test",
        name="Barbarian Test Encounter",
        status="active",
        round=1,
        current_entity_id=barbarian.entity_id,
        turn_order=[barbarian.entity_id],
        entities={barbarian.entity_id: barbarian},
        map=EncounterMap(
            map_id="map_barbarian_test",
            name="Barbarian Test Map",
            description="A small arena.",
            width=8,
            height=8,
        ),
    )


def test_ensure_barbarian_runtime_derives_rage_and_brutal_strike_from_level() -> None:
    entity = build_barbarian(level=13)

    barbarian = ensure_barbarian_runtime(entity)

    assert barbarian["rage"]["max"] == 5
    assert barbarian["rage_damage_bonus"] == 3
    assert barbarian["weapon_mastery_count"] == 4
    assert barbarian["brutal_strike"]["enabled"] is True
    assert barbarian["brutal_strike"]["extra_damage_dice"] == "1d10"
    assert barbarian["brutal_strike"]["max_effects"] == 1


def test_use_rage_consumes_bonus_action_and_rage_use() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        repo.save(build_barbarian_encounter(level=1))

        result = UseRage(repo).execute(
            encounter_id="enc_barbarian_test",
            entity_id="ent_barbarian_001",
        )

        updated = repo.get("enc_barbarian_test")
        assert updated is not None
        barbarian = updated.entities["ent_barbarian_001"]
        rage = barbarian.class_features["barbarian"]["rage"]
        assert barbarian.action_economy["bonus_action_used"] is True
        assert rage["active"] is True
        assert rage["remaining"] == 1
        assert result["class_feature_result"]["rage"]["active"] is True

        repo.close()


def test_use_rage_extend_only_refreshes_duration_without_spending_use() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = build_barbarian_encounter(level=1)
        state = ensure_barbarian_runtime(encounter.entities["ent_barbarian_001"])
        state["rage"]["active"] = True
        state["rage"]["remaining"] = 2
        repo.save(encounter)

        UseRage(repo).execute(
            encounter_id="enc_barbarian_test",
            entity_id="ent_barbarian_001",
            extend_only=True,
        )

        updated = repo.get("enc_barbarian_test")
        assert updated is not None
        rage = updated.entities["ent_barbarian_001"].class_features["barbarian"]["rage"]
        assert rage["remaining"] == 2
        assert rage["ends_at_turn_end_of"] == "ent_barbarian_001"

        repo.close()


def test_use_rage_with_pounce_path_grants_half_speed_free_movement() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        repo.save(build_barbarian_encounter(level=7))

        result = UseRage(repo).execute(
            encounter_id="enc_barbarian_test",
            entity_id="ent_barbarian_001",
            pounce_path=[[3, 2], [4, 2], [5, 2]],
        )

        updated = repo.get("enc_barbarian_test")
        assert updated is not None
        assert updated.entities["ent_barbarian_001"].position == {"x": 5, "y": 2}
        assert result["class_feature_result"]["rage"]["instinctive_pounce_used"] is True

        repo.close()


def test_use_rage_rejects_when_no_remaining_uses() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = build_barbarian_encounter(level=1)
        state = ensure_barbarian_runtime(encounter.entities["ent_barbarian_001"])
        state["rage"]["remaining"] = 0
        repo.save(encounter)

        with pytest.raises(ValueError, match="rage_no_remaining_uses"):
            UseRage(repo).execute(
                encounter_id="enc_barbarian_test",
                entity_id="ent_barbarian_001",
            )

        repo.close()
