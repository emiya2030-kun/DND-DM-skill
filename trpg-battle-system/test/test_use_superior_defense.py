"""Superior Defense 服务测试。"""

import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository
from tools.services.class_features.monk import UseSuperiorDefense


def _build_monk() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_monk_001",
        name="Monk",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 66, "max": 66, "temp": 0},
        ac=18,
        speed={"walk": 55, "remaining": 55},
        initiative=16,
        resistances=["poison"],
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        class_features={
            "monk": {
                "level": 18,
                "focus_points": {"max": 18, "remaining": 5},
            }
        },
    )


def _build_encounter() -> Encounter:
    monk = _build_monk()
    return Encounter(
        encounter_id="enc_monk_superior_defense",
        name="Monk Superior Defense Encounter",
        status="active",
        round=1,
        current_entity_id=monk.entity_id,
        turn_order=[monk.entity_id],
        entities={monk.entity_id: monk},
        map=EncounterMap(
            map_id="map_monk_superior_defense",
            name="Monk Test Map",
            description="A quiet shrine.",
            width=8,
            height=8,
        ),
    )


def test_use_superior_defense_spends_focus_and_adds_non_force_resistances() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        repo.save(_build_encounter())

        result = UseSuperiorDefense(repo).execute(
            encounter_id="enc_monk_superior_defense",
            actor_id="ent_monk_001",
        )

        updated = repo.get("enc_monk_superior_defense")
        assert updated is not None
        monk = updated.entities["ent_monk_001"]
        runtime = monk.class_features["monk"]["superior_defense"]
        assert monk.class_features["monk"]["focus_points"]["remaining"] == 2
        assert runtime["active"] is True
        assert runtime["remaining_rounds"] == 10
        assert "force" not in monk.resistances
        assert "poison" in monk.resistances
        assert set(runtime["added_resistances"]) == {
            "acid",
            "bludgeoning",
            "cold",
            "fire",
            "lightning",
            "necrotic",
            "piercing",
            "psychic",
            "radiant",
            "slashing",
            "thunder",
        }
        assert result["class_feature_result"]["superior_defense"]["focus_spent"] == 3

        repo.close()


def test_use_superior_defense_rejects_when_focus_points_insufficient() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = _build_encounter()
        encounter.entities["ent_monk_001"].class_features["monk"]["focus_points"]["remaining"] = 2
        repo.save(encounter)

        with pytest.raises(ValueError, match="superior_defense_requires_focus_points"):
            UseSuperiorDefense(repo).execute(
                encounter_id="enc_monk_superior_defense",
                actor_id="ent_monk_001",
            )

        repo.close()
