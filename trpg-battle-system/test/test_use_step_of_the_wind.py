"""Step of the Wind 服务测试。"""

import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository
from tools.services.class_features.monk import UseStepOfTheWind


def _build_monk() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_monk_001",
        name="Monk",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 18, "max": 18, "temp": 0},
        ac=16,
        speed={"walk": 30, "remaining": 30},
        initiative=14,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        turn_effects=[],
        class_features={
            "monk": {
                "level": 5,
                "focus_points": {"max": 2, "remaining": 2},
            }
        },
    )


def _build_encounter() -> Encounter:
    monk = _build_monk()
    ally = EncounterEntity(
        entity_id="ent_ally_002",
        name="Ally",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 3, "y": 2},
        hp={"current": 18, "max": 18, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
        size="medium",
    )
    return Encounter(
        encounter_id="enc_monk_test",
        name="Monk Test Encounter",
        status="active",
        round=1,
        current_entity_id=monk.entity_id,
        turn_order=[monk.entity_id],
        entities={monk.entity_id: monk, ally.entity_id: ally},
        map=EncounterMap(
            map_id="map_monk_test",
            name="Monk Test Map",
            description="A small training room.",
            width=8,
            height=8,
        ),
    )


def test_use_step_of_the_wind_base_grants_dash_and_spends_bonus_action() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        repo.save(_build_encounter())

        result = UseStepOfTheWind(repo).execute(
            encounter_id="enc_monk_test",
            actor_id="ent_monk_001",
            spend_focus=False,
        )

        updated = repo.get("enc_monk_test")
        assert updated is not None
        monk = updated.entities["ent_monk_001"]
        assert monk.action_economy["bonus_action_used"] is True
        assert monk.action_economy["dash_available"] == 1
        assert result["class_feature_result"]["step_of_the_wind"]["grants_dash"] is True

        repo.close()


def test_use_step_of_the_wind_focus_mode_adds_disengage_and_jump_multiplier() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        repo.save(_build_encounter())

        result = UseStepOfTheWind(repo).execute(
            encounter_id="enc_monk_test",
            actor_id="ent_monk_001",
            spend_focus=True,
        )

        updated = repo.get("enc_monk_test")
        assert updated is not None
        monk = updated.entities["ent_monk_001"]
        assert monk.class_features["monk"]["focus_points"]["remaining"] == 1
        assert any(effect.get("effect_type") == "disengage" for effect in monk.turn_effects)
        assert any(effect.get("effect_type") == "jump_distance_multiplier" for effect in monk.turn_effects)
        assert result["class_feature_result"]["step_of_the_wind"]["jump_distance_multiplier"] == 2

        repo.close()


def test_use_step_of_the_wind_rejects_when_bonus_action_already_used() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = _build_encounter()
        encounter.entities["ent_monk_001"].action_economy["bonus_action_used"] = True
        repo.save(encounter)

        with pytest.raises(ValueError, match="bonus_action_already_used"):
            UseStepOfTheWind(repo).execute(
                encounter_id="enc_monk_test",
                actor_id="ent_monk_001",
                spend_focus=False,
            )

        repo.close()


def test_use_step_of_the_wind_heightened_focus_can_protect_carried_ally() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = _build_encounter()
        encounter.entities["ent_monk_001"].class_features["monk"]["level"] = 10
        repo.save(encounter)

        result = UseStepOfTheWind(repo).execute(
            encounter_id="enc_monk_test",
            actor_id="ent_monk_001",
            spend_focus=True,
            passenger_id="ent_ally_002",
        )

        updated = repo.get("enc_monk_test")
        assert updated is not None
        ally = updated.entities["ent_ally_002"]
        assert any(effect.get("effect_type") == "disengage" for effect in ally.turn_effects)
        assert result["class_feature_result"]["step_of_the_wind"]["passenger_entity_id"] == "ent_ally_002"

        repo.close()
