"""Action Surge 服务测试。"""

import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository
from tools.services.class_features.fighter import UseActionSurge


def _build_fighter() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_fighter_001",
        name="Fighter",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 30, "max": 30, "temp": 0},
        ac=16,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        class_features={
            "fighter": {
                "level": 3,
                "action_surge": {"remaining_uses": 1, "used_this_turn": False},
                "temporary_bonuses": {"extra_non_magic_action_available": 0},
            }
        },
    )


def _build_other_actor() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_other_001",
        name="Other Actor",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 4, "y": 2},
        hp={"current": 12, "max": 12, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
    )


def _build_encounter() -> Encounter:
    fighter = _build_fighter()
    return Encounter(
        encounter_id="enc_fighter_test",
        name="Fighter Test Encounter",
        status="active",
        round=1,
        current_entity_id=fighter.entity_id,
        turn_order=[fighter.entity_id],
        entities={fighter.entity_id: fighter},
        map=EncounterMap(
            map_id="map_fighter_test",
            name="Fighter Test Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
    )


def test_use_action_surge_grants_extra_non_magic_action() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        repo.save(_build_encounter())

        result = UseActionSurge(repo).execute(encounter_id="enc_fighter_test", actor_id="ent_fighter_001")
        updated = repo.get("enc_fighter_test")
        assert updated is not None
        fighter = updated.entities["ent_fighter_001"].class_features["fighter"]
        assert fighter["temporary_bonuses"]["extra_non_magic_action_available"] == 1
        assert fighter["action_surge"]["remaining_uses"] == 0
        assert fighter["action_surge"]["used_this_turn"] is True
        assert result["encounter_state"]["encounter_id"] == "enc_fighter_test"

        repo.close()


def test_use_action_surge_rejects_when_not_actor_turn() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = _build_encounter()
        other = _build_other_actor()
        encounter.current_entity_id = other.entity_id
        encounter.turn_order.append(other.entity_id)
        encounter.entities[other.entity_id] = other
        repo.save(encounter)

        with pytest.raises(ValueError, match="not_actor_turn"):
            UseActionSurge(repo).execute(encounter_id="enc_fighter_test", actor_id="ent_fighter_001")

        repo.close()


def test_use_action_surge_rejects_when_already_used_this_turn() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = _build_encounter()
        encounter.entities["ent_fighter_001"].class_features["fighter"]["action_surge"]["used_this_turn"] = True
        repo.save(encounter)

        with pytest.raises(ValueError, match="action_surge_already_used_this_turn"):
            UseActionSurge(repo).execute(encounter_id="enc_fighter_test", actor_id="ent_fighter_001")

        repo.close()


def test_use_action_surge_rejects_when_no_remaining_uses() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = _build_encounter()
        encounter.entities["ent_fighter_001"].class_features["fighter"]["action_surge"]["remaining_uses"] = 0
        repo.save(encounter)

        with pytest.raises(ValueError, match="action_surge_no_remaining_uses"):
            UseActionSurge(repo).execute(encounter_id="enc_fighter_test", actor_id="ent_fighter_001")

        repo.close()
