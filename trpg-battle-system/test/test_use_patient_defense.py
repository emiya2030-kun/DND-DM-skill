"""Patient Defense 服务测试。"""

import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository
from tools.services.class_features.monk import UsePatientDefense


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
    return Encounter(
        encounter_id="enc_monk_test",
        name="Monk Test Encounter",
        status="active",
        round=1,
        current_entity_id=monk.entity_id,
        turn_order=[monk.entity_id],
        entities={monk.entity_id: monk},
        map=EncounterMap(
            map_id="map_monk_test",
            name="Monk Test Map",
            description="A small training room.",
            width=8,
            height=8,
        ),
    )


def test_use_patient_defense_base_applies_disengage_and_spends_bonus_action() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        repo.save(_build_encounter())

        result = UsePatientDefense(repo).execute(
            encounter_id="enc_monk_test",
            actor_id="ent_monk_001",
            spend_focus=False,
        )

        updated = repo.get("enc_monk_test")
        assert updated is not None
        monk = updated.entities["ent_monk_001"]
        assert monk.action_economy["bonus_action_used"] is True
        assert any(effect.get("effect_type") == "disengage" for effect in monk.turn_effects)
        assert not any(effect.get("effect_type") == "dodge" for effect in monk.turn_effects)
        assert result["class_feature_result"]["patient_defense"]["spent_focus"] is False

        repo.close()


def test_use_patient_defense_focus_mode_adds_dodge_and_spends_focus_point() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        repo.save(_build_encounter())

        UsePatientDefense(repo).execute(
            encounter_id="enc_monk_test",
            actor_id="ent_monk_001",
            spend_focus=True,
        )

        updated = repo.get("enc_monk_test")
        assert updated is not None
        monk = updated.entities["ent_monk_001"]
        assert any(effect.get("effect_type") == "disengage" for effect in monk.turn_effects)
        assert any(effect.get("effect_type") == "dodge" for effect in monk.turn_effects)
        assert monk.class_features["monk"]["focus_points"]["remaining"] == 1

        repo.close()


def test_use_patient_defense_rejects_when_bonus_action_already_used() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = _build_encounter()
        encounter.entities["ent_monk_001"].action_economy["bonus_action_used"] = True
        repo.save(encounter)

        with pytest.raises(ValueError, match="bonus_action_already_used"):
            UsePatientDefense(repo).execute(
                encounter_id="enc_monk_test",
                actor_id="ent_monk_001",
                spend_focus=False,
            )

        repo.close()


def test_use_patient_defense_heightened_focus_grants_temp_hp_when_spending_focus() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = _build_encounter()
        encounter.entities["ent_monk_001"].class_features["monk"]["level"] = 10
        repo.save(encounter)

        result = UsePatientDefense(repo).execute(
            encounter_id="enc_monk_test",
            actor_id="ent_monk_001",
            spend_focus=True,
            temp_hp_roll={"rolls": [4, 5]},
        )

        updated = repo.get("enc_monk_test")
        assert updated is not None
        monk = updated.entities["ent_monk_001"]
        assert monk.hp["temp"] == 9
        assert result["class_feature_result"]["patient_defense"]["temp_hp_gained"] == 9

        repo.close()
