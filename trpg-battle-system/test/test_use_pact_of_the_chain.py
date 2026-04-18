from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository
from tools.services import AppendEvent, GetEncounterState, UsePactOfTheChain


def build_actor(*, level: int = 5) -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_warlock_001",
        name="Warlock",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 24, "max": 24, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
        ability_scores={"str": 8, "dex": 14, "con": 14, "int": 12, "wis": 10, "cha": 18},
        ability_mods={"str": -1, "dex": 2, "con": 2, "int": 1, "wis": 0, "cha": 4},
        proficiency_bonus=3,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        class_features={
            "warlock": {
                "level": level,
                "eldritch_invocations": {
                    "selected": [{"invocation_id": "pact_of_the_chain"}]
                },
            }
        },
    )


def build_enemy() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_enemy_001",
        name="Bandit",
        side="enemy",
        category="npc",
        controller="gm",
        position={"x": 8, "y": 2},
        hp={"current": 12, "max": 12, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
    )


def build_encounter() -> Encounter:
    actor = build_actor()
    enemy = build_enemy()
    return Encounter(
        encounter_id="enc_use_pact_of_the_chain_test",
        name="Use Pact of the Chain Test",
        status="active",
        round=1,
        current_entity_id=actor.entity_id,
        turn_order=[actor.entity_id, enemy.entity_id],
        entities={actor.entity_id: actor, enemy.entity_id: enemy},
        map=EncounterMap(
            map_id="map_use_pact_of_the_chain_test",
            name="Use Pact of the Chain Test Map",
            description="A small combat room.",
            width=12,
            height=12,
        ),
    )


def test_execute_summons_special_familiar_consumes_action_without_creating_separate_turn() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        encounter_repo.save(build_encounter())

        with patch("tools.services.class_features.warlock.use_pact_of_the_chain.randint", return_value=12):
            result = UsePactOfTheChain(
                encounter_repo,
                AppendEvent(event_repo),
            ).execute(
                encounter_id="enc_use_pact_of_the_chain_test",
                actor_id="ent_warlock_001",
                familiar_form="pseudodragon",
            )

        updated = encounter_repo.get("enc_use_pact_of_the_chain_test")
        assert updated is not None
        warlock = updated.entities["ent_warlock_001"]
        pact = warlock.class_features["warlock"]["pact_of_the_chain"]
        familiar_id = pact["familiar_entity_id"]
        familiar = updated.entities[familiar_id]

        assert warlock.action_economy["action_used"] is True
        assert familiar.name == "Pseudodragon"
        assert familiar.source_ref["familiar_form_id"] == "pseudodragon"
        assert familiar.initiative == 14
        assert updated.turn_order == ["ent_warlock_001", "ent_enemy_001"]
        assert result["class_feature_result"]["pact_of_the_chain"]["familiar_entity_id"] == familiar_id

        encounter_repo.close()
        event_repo.close()


def test_execute_replaces_previous_familiar_from_same_warlock() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        encounter_repo.save(build_encounter())
        service = UsePactOfTheChain(encounter_repo, AppendEvent(event_repo))

        with patch("tools.services.class_features.warlock.use_pact_of_the_chain.randint", side_effect=[12, 11]):
            service.execute(
                encounter_id="enc_use_pact_of_the_chain_test",
                actor_id="ent_warlock_001",
                familiar_form="pseudodragon",
            )
            updated = encounter_repo.get("enc_use_pact_of_the_chain_test")
            assert updated is not None
            first_familiar_id = updated.entities["ent_warlock_001"].class_features["warlock"]["pact_of_the_chain"][
                "familiar_entity_id"
            ]
            updated.entities["ent_warlock_001"].action_economy["action_used"] = False
            encounter_repo.save(updated)

            service.execute(
                encounter_id="enc_use_pact_of_the_chain_test",
                actor_id="ent_warlock_001",
                familiar_form="sprite",
            )

        final_state = encounter_repo.get("enc_use_pact_of_the_chain_test")
        assert final_state is not None
        pact = final_state.entities["ent_warlock_001"].class_features["warlock"]["pact_of_the_chain"]
        active_familiar_id = pact["familiar_entity_id"]
        assert first_familiar_id != active_familiar_id
        assert first_familiar_id not in final_state.entities
        assert final_state.entities[active_familiar_id].source_ref["familiar_form_id"] == "sprite"
        assert active_familiar_id not in final_state.turn_order

        encounter_repo.close()
        event_repo.close()


def test_execute_rejects_unknown_special_form() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        encounter_repo.save(build_encounter())

        with pytest.raises(ValueError, match="invalid_find_familiar_form"):
            UsePactOfTheChain(
                encounter_repo,
                AppendEvent(event_repo),
            ).execute(
                encounter_id="enc_use_pact_of_the_chain_test",
                actor_id="ent_warlock_001",
                familiar_form="owlbear_cub",
            )

        encounter_repo.close()
        event_repo.close()


def test_execute_supports_normal_owl_form() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        encounter_repo.save(build_encounter())

        with patch("tools.services.class_features.warlock.use_pact_of_the_chain.randint", return_value=9):
            result = UsePactOfTheChain(
                encounter_repo,
                AppendEvent(event_repo),
            ).execute(
                encounter_id="enc_use_pact_of_the_chain_test",
                actor_id="ent_warlock_001",
                familiar_form="owl",
                creature_type="celestial",
            )

        updated = encounter_repo.get("enc_use_pact_of_the_chain_test")
        assert updated is not None
        familiar_id = result["class_feature_result"]["pact_of_the_chain"]["familiar_entity_id"]
        familiar = updated.entities[familiar_id]
        assert familiar.name == "Owl"
        assert familiar.source_ref["creature_type"] == "celestial"
        assert familiar.initiative == 10

        encounter_repo.close()
        event_repo.close()


def test_get_encounter_state_projects_pact_of_the_chain_summary() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = build_encounter()
        player = encounter.entities["ent_warlock_001"]
        player.class_features["warlock"]["pact_of_the_chain"] = {
            "enabled": True,
            "familiar_entity_id": "ent_familiar_001",
            "familiar_name": "Sprite",
            "familiar_form_id": "sprite",
        }
        repo.save(encounter)

        state = GetEncounterState(repo).execute("enc_use_pact_of_the_chain_test")
        warlock = state["current_turn_entity"]["resources"]["class_features"]["warlock"]

        assert warlock["pact_of_the_chain"]["enabled"] is True
        assert warlock["pact_of_the_chain"]["familiar_name"] == "Sprite"
        assert warlock["pact_of_the_chain"]["familiar_form_id"] == "sprite"
        assert "pact_of_the_chain" in warlock["available_features"]
        repo.close()
